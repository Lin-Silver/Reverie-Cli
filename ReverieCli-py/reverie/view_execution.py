"""RIU callbacks use the ordinary executor, policy/reviewer and approval owner."""
from __future__ import annotations

import json
import uuid
from typing import Any, Dict

from .desktop_control import RunControl
from .provider_transport import request_scope
from .modes import normalize_mode
from .tools.base import BaseTool
from .tools.mcp_dynamic import MCPDynamicTool
from .views import MAX_VIEW_CALL_BYTES


def run_view_tool(bridge: Any, request_id: Any, payload: Dict[str, Any]) -> Dict[str, Any]:
    for key in ("viewId", "toolName", "callId"):
        if not isinstance(payload.get(key), str) or not payload[key].strip():
            raise ValueError(f"callViewTool requires a {key}.")
    view_id, tool_name, call_id = (payload[key].strip() for key in ("viewId", "toolName", "callId"))
    arguments = payload.get("arguments", {})
    if not isinstance(arguments, dict):
        raise ValueError("callViewTool arguments must be an object.")
    if len(json.dumps(arguments, ensure_ascii=False, allow_nan=False).encode("utf-8")) > MAX_VIEW_CALL_BYTES:
        raise ValueError("callViewTool arguments exceed the bridge limit.")
    base = {"id": request_id, "type": "view.tool_result", "viewId": view_id, "callId": call_id, "duplicate": False}
    if not bridge._run_lock.acquire(blocking=False):
        return {**base, "status": "busy", "error": "A run is already active in this executor."}
    executor = None
    previous = {}
    try:
        interface = bridge.ensure_interface()
        requested_session = payload.get("sessionId")
        if requested_session and interface.session_manager.load_session(requested_session) is None:
            raise ValueError("View session no longer exists.")
        init = getattr(interface, "_init_agent", None)
        if callable(init):
            init(persist_config_changes=False, defer_runtime_enrichment=True)
        if interface.agent is None:
            raise ValueError("Configure a model before using view tools.")
        session = interface.session_manager.get_current_session()
        session_id = str(getattr(session, "id", "") or "")
        store = bridge._view_store()
        manifest = store.current_manifest(session_id, view_id, payload.get("revision"))
        app_binding = None
        if manifest.source.get("kind") == "mcp":
            runtime = interface.agent.tool_executor.context.get("mcp_runtime")
            if runtime is None:
                raise ValueError("MCP app connection expired.")
            runtime.require_app_identity(manifest.source.get("server_name", ""), manifest.source)
            app_binding = manifest.source
            tool_name = manifest.source.get("tool_bindings", {}).get(tool_name, "")
        if tool_name not in manifest.callable_tools:
            return {**base, "status": "error", "reason": "restricted-tool", "error": f"Tool {tool_name!r} is not callable from this view."}
        executor = interface.agent.tool_executor
        executor._sync_dynamic_tools()
        tool = executor.get_tool(tool_name)
        if app_binding is not None:
            if not isinstance(tool, MCPDynamicTool) or tool.metadata.get("server_name") != app_binding.get("server_name") or "app" not in tool.metadata.get("ui", {}).get("visibility", []):
                return {**base, "status": "error", "reason": "restricted-tool", "error": "MCP app tool visibility or server binding changed."}
            active_mode = normalize_mode(getattr(interface.agent, "mode", "reverie"))
            if active_mode == "writer" or not tool.visible_in_mode(active_mode, audience="app"):
                return {**base, "status": "error", "reason": "restricted-tool", "error": "MCP app tool is not available in the current mode."}
        elif manifest.source.get("kind") not in {"model", "generated"} or isinstance(tool, MCPDynamicTool):
            return {**base, "status": "error", "reason": "unsupported-source", "error": "MCP view tool binding is not supported by this capability profile."}
        if tool is None:
            return {**base, "status": "error", "error": "Tool is not currently enabled."}
        invalid = BaseTool.validate_params(tool, arguments) or tool.validate_params(arguments)
        if invalid:
            return {**base, "status": "error", "reason": "invalid-arguments", "error": invalid}
        recorded = store.begin_call(session_id, view_id, manifest.revision, call_id, tool_name, arguments)
        if recorded is not None:
            return {**base, **{k: v for k, v in recorded.items() if k != "fingerprint"}, "id": request_id, "duplicate": True}
        bridge._run_identity = {"project_root": str(bridge.project_root), "session_id": session_id,
                                "run_id": str(payload.get("runId") or uuid.uuid4().hex),
                                "view_id": view_id, "view_title": manifest.title, "call_id": call_id, "source": "component"}
        control = RunControl(lambda event: bridge._emit_request_event(request_id, event))
        bridge._run_control = control
        captured = []
        previous = {key: executor.context.get(key) for key in ("desktop_run_control", "tool_approval_handler", "desktop_view_call", "mcp_app_binding", "mcp_app_result_handler")}
        executor.update_context("mcp_app_binding", app_binding)
        executor.update_context("mcp_app_result_handler", captured.append if app_binding else None)
        executor.update_context("desktop_view_call", True)
        executor.update_context("desktop_run_control", control)
        executor.update_context("tool_approval_handler", lambda tool, arguments, denial, details=None:
                                bridge._request_tool_approval(request_id, tool, arguments, denial, details))
        try:
            with request_scope(control):
                result = executor.execute(tool_name, arguments, tool_call_id=call_id)
            if control.cancelled.is_set():
                outcome = {**base, "status": "cancelled", "error": "Stopped. Check the authoritative tool state before starting a new operation."}
            else:
                outcome = {**base, "status": "success" if result.success else "error", "output": result.output,
                           "error": result.error, "data": result.data, "source": "component"}
                if captured and isinstance(captured[-1], dict):
                    outcome["toolResult"] = captured[-1]
            # Persist the receipt before delivering it. Errors and Stop consume the id too.
            from .sdk_bridge import _json_safe
            outcome = _json_safe(outcome)
            store.finish_call(session_id, view_id, manifest.revision, call_id, outcome)
            receipt = store.begin_call(session_id, view_id, manifest.revision, call_id, tool_name, arguments)
            return {**base, **{k: v for k, v in receipt.items() if k != "fingerprint"}}
        except Exception:
            # The write-ahead unknown receipt survives disconnects/crashes; never replay.
            if control.cancelled.is_set():
                outcome = {**base, "status": "cancelled", "error": "Run stopped; check completed actions before continuing."}
                store.finish_call(session_id, view_id, manifest.revision, call_id, outcome)
                return outcome
            raise
    finally:
        if executor is not None:
            for key, value in previous.items():
                executor.update_context(key, value)
        bridge._run_control = None
        bridge._run_identity = {}
        bridge._run_lock.release()
