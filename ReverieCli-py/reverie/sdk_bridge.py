"""Small JSONL bridge for settings and runtime-plugin management."""

from __future__ import annotations

import json
import os
import sys
import threading
import time
import uuid
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional


_BACKGROUND_DISPATCH_ACTIONS = frozenset({"runPrompt", "compactContext", "workspaceMentions", "indexWorkspace"})


def _interactive_context_worker_limit(cpu_count: Optional[int] = None) -> int:
    """Leave CPU capacity for desktop IPC and model/provider interactions."""
    available = max(1, int(cpu_count if cpu_count is not None else (os.cpu_count() or 1)))
    return max(1, min(2, available - 1 if available > 1 else 1))


def _json_safe(value: Any) -> Any:
    """Coerce a payload into something `json.dumps` accepts.

    Containers are returned unchanged when nothing inside them needed coercing.
    Almost every payload the desktop asks for -- a whole transcript, most of
    all -- is already plain JSON, and rebuilding it verbatim used to copy every
    dict and list in it on the way out.
    """
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, dict):
        converted: Dict[Any, Any] = {}
        changed = False
        for key, item in value.items():
            safe_key = key if type(key) is str else str(key)
            safe_item = _json_safe(item)
            if safe_key is not key or safe_item is not item:
                changed = True
            converted[safe_key] = safe_item
        return converted if changed else value
    if isinstance(value, list):
        converted_items = [_json_safe(item) for item in value]
        for original, safe_item in zip(value, converted_items):
            if safe_item is not original:
                return converted_items
        return value
    if isinstance(value, (tuple, set)):
        return [_json_safe(item) for item in value]
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    return str(value)


def _desktop_tool_record(record: Dict[str, Any]) -> Dict[str, Any]:
    tool = record.get("tool")
    metadata = dict(record.get("metadata", {}) or {})
    module_name = str(getattr(type(tool), "__module__", "") or "").lower()
    class_name = str(getattr(type(tool), "__name__", "") or "").lower()
    if "rats" in module_name or class_name in {"ratsdynamictool", "ratscatalogtool"}:
        kind = "rats"
    elif "mcp" in module_name or class_name == "mcpdynamictool":
        kind = "mcp"
    elif "plugin" in module_name or "plugin" in class_name or metadata.get("plugin_id"):
        kind = "runtime-plugin"
    else:
        kind = "built-in"
    traits = [
        label
        for key, label in (
            ("read_only", "read-only"),
            ("concurrency_safe", "parallel"),
            ("destructive", "destructive"),
            ("should_defer", "deferred"),
        )
        if bool(metadata.get(key, False))
    ]
    return {
        "name": str(record.get("name", "") or "").strip(),
        "description": str(record.get("description", "") or "").strip(),
        "kind": kind,
        "category": str(metadata.get("category", "general") or "general").strip() or "general",
        "aliases": [
            str(item).strip()
            for item in (metadata.get("aliases", []) or [])
            if str(item).strip()
        ],
        "tags": [
            str(item).strip()
            for item in (metadata.get("tags", []) or [])
            if str(item).strip()
        ],
        "traits": traits,
        "required": list(record.get("required", []) or []),
        "properties": list(record.get("properties", []) or []),
        "supported_modes": list(record.get("supported_modes", []) or []),
    }


class ReverieSdkBridge:
    """Long-lived bridge used by desktop/settings hosts."""

    def __init__(self, event_writer: Optional[Callable[[Dict[str, Any]], None]] = None) -> None:
        from .rats import RatsRuntime

        self.project_root = Path.cwd().resolve()
        self.interface = None
        self.tool_executor = None
        self.event_writer = event_writer
        self._approval_waiters: Dict[str, Dict[str, Any]] = {}
        self._approval_lock = threading.Lock()
        self._workspace_index_lock = threading.Lock()
        self._workspace_index_completed_at = 0.0
        self._workspace_index_result = None
        self.rats_runtime = RatsRuntime()

    def _dispose_interface(self) -> None:
        """Release workspace-scoped services without stopping the bridge process."""
        interface = self.interface
        self.interface = None
        self.tool_executor = None
        if interface is None:
            return
        close = getattr(interface, "close", None)
        if callable(close):
            close()

    def ensure_interface(self, project_root: Optional[Path] = None):
        from .cli.interface import ReverieInterface

        root = Path(project_root or self.project_root).expanduser().resolve()
        if not root.is_dir():
            raise ValueError(f"Workspace does not exist: {root}")
        if self.interface is None or self.project_root != root:
            if self.interface is not None:
                self._dispose_interface()
            self.project_root = root
            self.interface = ReverieInterface(root, headless=True)
            self.interface._context_worker_limit = _interactive_context_worker_limit()
            self.interface.rats_runtime = self.rats_runtime
        elif self.interface is not None:
            self.interface.rats_runtime = self.rats_runtime
        return self.interface

    def ensure_tool_executor(self):
        from .agent.tool_executor import ToolExecutor

        interface = self.ensure_interface()
        if self.tool_executor is None:
            self.tool_executor = ToolExecutor(project_root=self.project_root)
        config = interface.config_manager.load()
        self.tool_executor.update_context("security", getattr(config, "security", {}))
        self.tool_executor.update_context("runtime_plugin_manager", interface.runtime_plugin_manager)
        self.tool_executor.update_context("workspace_stats_manager", interface.workspace_stats_manager)
        self.tool_executor.update_context("rats_runtime", self.rats_runtime)
        return self.tool_executor

    def _setting_value(self, item: Dict[str, Any], config: Any, interface: Any) -> Any:
        from .settings_catalog import SECURITY_SETTING_KEYS, security_setting_value

        kind = str(item.get("kind") or "")
        key = str(item.get("key") or "")
        if kind == "plugin-bool":
            return bool(interface.runtime_plugin_manager.get_plugin_state(item.get("plugin_id", "")).get("enabled"))
        if kind == "workspace":
            return bool(interface.config_manager.is_workspace_mode())
        if kind == "rules":
            return "\n".join(interface.rules_manager.get_rules())
        if key in SECURITY_SETTING_KEYS:
            # These live inside `config.security`, so a plain getattr() reads None.
            return security_setting_value(key, config)
        return getattr(config, key, None)

    def settings_payload(self) -> Dict[str, Any]:
        from .settings_catalog import get_setting_items

        interface = self.ensure_interface()
        config = interface.config_manager.load()
        items = []
        for item in get_setting_items(
            config,
            interface.config_manager,
            interface.rules_manager,
            interface.runtime_plugin_manager,
        ):
            normalized = dict(item)
            normalized["value"] = self._setting_value(item, config, interface)
            items.append(_json_safe(normalized))
        return {
            "items": items,
            "config_path": str(interface.config_manager.config_path),
            "workspace_mode": bool(interface.config_manager.is_workspace_mode()),
        }

    @staticmethod
    def _plugin_record(record: Any) -> Dict[str, Any]:
        protocol = getattr(record, "protocol", None)
        return {
            "id": record.plugin_id,
            "name": record.display_name,
            "family": record.runtime_family,
            "version": record.version,
            "status": record.status,
            "status_label": record.status_label,
            "enabled": bool(record.enabled),
            "trusted": bool(record.trusted),
            "protocol_status": record.protocol_status,
            "protocol_label": record.protocol_label,
            "tool_count": record.protocol_tool_count,
            "command_count": record.protocol_command_count,
            "skill_count": len(protocol.skills) if protocol else 0,
            "system_prompt": protocol.system_prompt if protocol else "",
            "entry_path": record.entry_path,
            "install_dir": record.install_dir,
        }

    def plugins_payload(self, *, force_refresh: bool = False) -> Dict[str, Any]:
        manager = self.ensure_interface().runtime_plugin_manager
        snapshot = manager.get_snapshot(force_refresh=force_refresh)
        return {
            "summary": _json_safe(manager.get_status_summary(force_refresh=False)),
            "records": [self._plugin_record(record) for record in snapshot.records],
        }

    def _refresh_plugin_dependents(self) -> None:
        interface = self.ensure_interface()
        interface.skills_manager.scan()
        if interface.agent is not None:
            interface._refresh_agent_prompt_guidance()

    @staticmethod
    def _skill_record(record: Any, pinned_keys: Any = ()) -> Dict[str, Any]:
        lookup_key = str(getattr(record, "lookup_key", "") or "")
        return {
            "key": lookup_key,
            "name": getattr(record, "name", ""),
            "description": getattr(record, "description", ""),
            "summary": getattr(record, "summary", ""),
            "path": getattr(record, "display_path", ""),
            "scope": getattr(record, "scope_label", ""),
            "root": getattr(record, "root_label", ""),
            "plugin_id": getattr(record, "plugin_id", ""),
            "allow_implicit_invocation": bool(getattr(record, "allow_implicit_invocation", True)),
            "pinned": lookup_key in pinned_keys,
        }

    def skills_payload(self, *, force_refresh: bool = False) -> Dict[str, Any]:
        """Describe every discovered skill plus the session pin set for the desktop."""
        manager = self.ensure_interface().skills_manager
        snapshot = manager.get_snapshot(force_refresh=force_refresh)
        state = manager.pinned_state(force_refresh=False)
        pinned_keys = frozenset(getattr(manager, "pinned_keys", ()) or ())
        return {
            "count": len(snapshot.records),
            "invalid_count": len(snapshot.errors),
            "records": [self._skill_record(record, pinned_keys) for record in snapshot.records],
            "pinned": {
                "max": int(state.get("max", 0) or 0),
                "keys": sorted(pinned_keys),
                "names": [str(name) for name in state.get("names", [])],
                "unresolved": [str(name) for name in state.get("unresolved", [])],
            },
            "errors": _json_safe(manager.list_error_rows(force_refresh=False)),
        }

    def _refresh_pinned_skills(self) -> None:
        """Rebuild the system prompt so a pin change lands on the next desktop turn."""
        interface = self.ensure_interface()
        if interface.agent is not None:
            interface._refresh_agent_prompt_guidance()

    def _refresh_agent(self) -> None:
        interface = self.ensure_interface()
        if interface.agent is not None:
            interface._init_agent(
                config_override=interface.config_manager.load(),
                persist_config_changes=False,
            )

    def _run_workspace_index(self) -> Any:
        """Coalesce overlapping desktop reindex requests without blocking bridge IPC."""
        requested_at = time.monotonic()
        with self._workspace_index_lock:
            if (
                self._workspace_index_result is not None
                and self._workspace_index_completed_at >= requested_at
            ):
                return self._workspace_index_result

            interface = self.ensure_interface()
            interface.ensure_context_engine(announce=False)
            if interface.indexer is None:
                raise RuntimeError("Context Engine indexer is unavailable.")

            if bool(getattr(interface, "_indexing_in_progress", False)):
                interface._wait_for_context_indexing(announce=False)
                result = getattr(interface.indexer, "_last_index_result", None)
            else:
                result = interface._run_context_indexing_with_progress()
            if result is None:
                raise RuntimeError("Context Engine indexing did not produce a result.")

            self._workspace_index_result = result
            self._workspace_index_completed_at = time.monotonic()
            return result

    def _emit_request_event(self, request_id: Any, event: Dict[str, Any]) -> None:
        if self.event_writer is None:
            return
        self.event_writer(
            {
                "id": request_id,
                "type": "prompt.event",
                "event": _json_safe(event),
            }
        )

    def _request_tool_approval(
        self,
        request_id: Any,
        tool: Any,
        arguments: Dict[str, Any],
        denial: str,
        details: Optional[Dict[str, Any]] = None,
    ) -> Any:
        info = details if isinstance(details, dict) else {}
        approval_id = uuid.uuid4().hex
        waiter = {"event": threading.Event(), "decision": "deny", "message": ""}
        with self._approval_lock:
            self._approval_waiters[approval_id] = waiter
        self._emit_request_event(
            request_id,
            {
                "type": "approval.request",
                "approval_id": approval_id,
                "tool": str(getattr(tool, "name", "tool") or "tool"),
                "message": str(
                    denial
                    or str(info.get("reason") or "")
                    or "This tool requires additional permission."
                ),
                "risk": str(info.get("risk") or ""),
                "permission_mode": str(info.get("permission_mode") or ""),
                "concerns": list(info.get("concerns") or []),
                "review_source": str(info.get("review_source") or ""),
                "read_only": bool(info.get("read_only", False)),
            },
        )
        waiter["event"].wait(timeout=300)
        with self._approval_lock:
            resolved = self._approval_waiters.pop(approval_id, waiter)
        decision = str(resolved.get("decision") or "deny").strip().lower()
        message = str(resolved.get("message") or "").strip()
        if message:
            return {"decision": "message", "message": message}
        return decision if decision in {"once", "session", "deny"} else "deny"

    def model_sources_payload(self, *, fetch_live: bool = False) -> Dict[str, Any]:
        from .desktop_catalog import build_model_sources_payload

        interface = self.ensure_interface()
        return _json_safe(build_model_sources_payload(interface.config_manager.load(), fetch_live=fetch_live))

    @staticmethod
    def _session_info_payload(info: Any) -> Dict[str, Any]:
        return {
            "id": str(getattr(info, "id", "") or ""),
            "name": str(getattr(info, "name", "") or ""),
            "created_at": str(getattr(info, "created_at", "") or ""),
            "updated_at": str(getattr(info, "updated_at", "") or ""),
            "message_count": int(getattr(info, "message_count", 0) or 0),
        }

    def sessions_payload(self) -> Dict[str, Any]:
        manager = self.ensure_interface().session_manager
        manager.refresh_generated_session_names()
        current = manager.get_current_session() or manager.restore_last_session()
        return {
            "current_session_id": str(getattr(current, "id", "") or ""),
            "items": [self._session_info_payload(info) for info in manager.list_sessions()],
        }

    def active_session_payload(self, session_id: str = "") -> Optional[Dict[str, Any]]:
        manager = self.ensure_interface().session_manager
        session = manager.load_session(session_id) if session_id else manager.get_current_session()
        if session is None:
            return None
        if self.interface.agent is not None:
            self.interface.agent.set_history(session.messages)
        return _json_safe(session.to_wire_dict())

    def commands_payload(self) -> Dict[str, Any]:
        from .cli.help_catalog import HELP_SECTION_ORDER, HELP_TOPICS

        items = [dict(item, id=topic_id) for topic_id, item in HELP_TOPICS.items()]
        # A user's own providers become real commands, so the desktop palette
        # lists them next to the built-in topics instead of hiding them behind
        # the generic /provider entry.
        provider_commands = self._custom_provider_command_items()
        if provider_commands:
            items.extend(provider_commands)
        return {
            "sections": list(HELP_SECTION_ORDER),
            "items": items,
        }

    def _custom_provider_command_items(self) -> List[Dict[str, Any]]:
        """Return one palette entry per stored custom provider."""
        try:
            from .custom_providers import (
                CUSTOM_PROVIDER_COMMAND_ACTIONS,
                list_custom_providers,
            )

            interface = self.ensure_interface()
            config = interface.config_manager.load()
            records = list_custom_providers(getattr(config, "custom_providers", {}))
        except Exception:
            from .diagnostics import report_suppressed_exception

            report_suppressed_exception("build custom provider command payload")
            return []

        items: List[Dict[str, Any]] = []
        for record in records:
            provider_id = str(record.get("id") or "").strip()
            if not provider_id:
                continue
            label = str(record.get("name") or provider_id).strip() or provider_id
            items.append({
                "id": f"provider:{provider_id}",
                "command": f"/provider {provider_id}",
                "section": "Providers",
                "summary": f"{label}: inspect, pick a model, test, or activate this custom provider.",
                "overview": " | ".join(action for action, _ in CUSTOM_PROVIDER_COMMAND_ACTIONS if action),
                "subcommands": [
                    {
                        "usage": f"/provider {provider_id}{' ' + action if action else ''}",
                        "description": description,
                    }
                    for action, description in CUSTOM_PROVIDER_COMMAND_ACTIONS
                ],
                "examples": [
                    f"/provider {provider_id} models",
                    f"/provider {provider_id} test",
                    f"/provider {provider_id} use",
                ],
            })
        return items

    def recovery_payload(self) -> Dict[str, Any]:
        interface = self.ensure_interface()
        checkpoints = interface.rollback_manager.checkpoint_manager.list_checkpoints()
        operations = interface.operation_history.get_operations(limit=100)
        return {
            "summary": _json_safe(interface.rollback_manager.get_operation_summary()),
            "checkpoints": [_json_safe(checkpoint.to_dict()) for checkpoint in checkpoints[:100]],
            "operations": [_json_safe(operation.to_dict()) for operation in operations],
        }

    def workspace_payload(self) -> Dict[str, Any]:
        interface = self.ensure_interface()
        config = interface.config_manager.load()
        active_model = config.active_model
        context_engine = self.context_status_payload()
        return {
            "project_root": str(self.project_root),
            "project_name": self.project_root.name,
            "project_data_dir": str(interface.project_data_dir),
            "config_path": str(interface.config_manager.get_active_config_path()),
            "mode": str(config.mode),
            "active_source": str(config.active_model_source),
            "active_model": {
                "id": str(getattr(active_model, "model", "") or ""),
                "display_name": str(getattr(active_model, "model_display_name", "") or ""),
                "provider": str(getattr(active_model, "provider", "") or ""),
            }
            if active_model
            else None,
            "index_ready": bool(context_engine["ready"]),
            "context_engine": context_engine,
        }

    def context_status_payload(self) -> Dict[str, Any]:
        """Return compact Context Engine health and utilization metadata for desktop."""
        interface = self.ensure_interface()
        indexer = getattr(interface, "indexer", None)
        status: Dict[str, Any] = {}
        if indexer is not None:
            try:
                status = dict(indexer.get_index_status() or {})
            except Exception:
                status = {}
        file_info = getattr(indexer, "_file_info", {}) if indexer is not None else {}
        symbol_table = getattr(indexer, "symbol_table", None) if indexer is not None else None
        warmup_thread = getattr(interface, "_context_engine_warmup_thread", None)
        warming = bool(warmup_thread is not None and warmup_thread.is_alive())
        return {
            "ready": bool(indexer is not None and getattr(interface, "retriever", None) is not None),
            "indexing": bool(getattr(interface, "_indexing_in_progress", False)),
            "files": len(file_info) if isinstance(file_info, dict) else 0,
            "symbols": len(symbol_table) if symbol_table is not None else 0,
            "progress": float(status.get("display_percent", status.get("percent", 0.0)) or 0.0),
            "label": str(status.get("display_label") or ("Warming" if warming else "On demand")),
            "automatic_retrieval": True,
        }

    def desktop_state_payload(self) -> Dict[str, Any]:
        from .version import CORE_INTERFACE_VERSION, RELEASE_STATUS, __version__

        return {
            "protocol_version": 1,
            "core": {
                "version": __version__,
                "interface_version": CORE_INTERFACE_VERSION,
                "release_status": RELEASE_STATUS,
            },
            "workspace": self.workspace_payload(),
            "models": self.model_sources_payload(),
            "settings": self.settings_payload(),
            "sessions": self.sessions_payload(),
            "plugins": self.plugins_payload(),
            "skills": self.skills_payload(),
            "commands": self.commands_payload(),
            "recovery": self.recovery_payload(),
        }

    def dispatch(self, message: Dict[str, Any]) -> Dict[str, Any]:
        action = str(message.get("action") or "").strip()
        payload = message.get("payload") if isinstance(message.get("payload"), dict) else {}
        request_id = message.get("id")

        if action == "hello":
            return {
                "id": request_id,
                "type": "ready",
                "protocol_version": 1,
                "project_root": str(self.project_root),
            }
        if action == "initialize":
            interface = self.ensure_interface(Path(str(payload.get("projectRoot") or self.project_root)))
            interface._prime_context_engine_background()
            return {
                "id": request_id,
                "type": "state",
                "state": self.desktop_state_payload(),
            }
        if action == "getState":
            return {
                "id": request_id,
                "type": "state",
                "state": self.desktop_state_payload(),
            }
        if action == "getContextStatus":
            return {
                "id": request_id,
                "type": "context.status",
                "context_engine": self.context_status_payload(),
            }
        if action == "getSubagents":
            manager = self.ensure_interface().subagent_manager
            return {
                "id": request_id,
                "type": "subagents",
                "subagents": {
                    "available": bool(manager.is_available()),
                    "agents": [spec.to_dict() for spec in manager.list_specs()],
                    "runs": [run.to_dict() for run in manager.list_recent_runs()[:100]],
                },
            }
        if action == "getSubagentRunLog":
            manager = self.ensure_interface().subagent_manager
            run_id = str(payload.get("runId") or "").strip()
            if not run_id:
                raise ValueError("runId is required.")
            run = manager.get_run(run_id)
            if run is None:
                raise ValueError(f"Subagent run not found: {run_id}")
            log = manager.get_run_log(run_id) or {
                "run": run.to_dict(),
                "subagent": {},
                "model": {},
                "assignment": "",
                "events": [],
            }
            return {
                "id": request_id,
                "type": "subagent.log",
                "run_id": run_id,
                "log": _json_safe(log),
            }
        if action == "resolveApproval":
            approval_id = str(payload.get("approvalId") or payload.get("id") or "").strip()
            decision = str(payload.get("decision") or "deny").strip().lower()
            message = str(payload.get("message") or "").strip()[:2000]
            if decision not in {"once", "session", "deny", "message"}:
                raise ValueError("Approval decision must be once, session, deny, or message.")
            if decision == "message" and not message:
                raise ValueError("A 'message' decision requires message text for the model.")
            with self._approval_lock:
                waiter = self._approval_waiters.get(approval_id)
                if waiter is None:
                    raise ValueError(f"Approval request is no longer active: {approval_id}")
                waiter["decision"] = decision
                waiter["message"] = message if decision == "message" else ""
                waiter["event"].set()
            return {"id": request_id, "type": "approval.resolved", "approval_id": approval_id, "decision": decision}
        if action == "runPrompt":
            interface = self.ensure_interface(
                Path(str(payload.get("projectRoot") or self.project_root))
            )
            prompt = str(payload.get("prompt") or payload.get("message") or "")
            session_id = str(payload.get("sessionId") or "").strip()
            if session_id and interface.session_manager.load_session(session_id) is None:
                raise ValueError(f"Session not found: {session_id}")
            result = interface.run_prompt_once(
                prompt,
                mode_override=str(payload.get("mode") or "").strip() or None,
                stream=payload.get("stream") if isinstance(payload.get("stream"), bool) else None,
                no_index=bool(payload.get("noIndex", False)),
                fresh_session=bool(payload.get("freshSession", False)),
                event_callback=lambda event: self._emit_request_event(request_id, event),
                approval_callback=lambda tool, arguments, denial, details=None: self._request_tool_approval(
                    request_id,
                    tool,
                    arguments,
                    denial,
                    details,
                ),
                source_override=str(payload.get("source") or "").strip() or None,
                model_override=str(payload.get("model") or "").strip() or None,
                reasoning_override=str(payload.get("reasoning") or "").strip() or None,
            )
            return {
                "id": request_id,
                "type": "prompt.result",
                "result": _json_safe(result.to_dict()),
                "sessions": self.sessions_payload(),
                "recovery": self.recovery_payload(),
            }
        if action == "compactContext":
            from .tools.context_management import ContextManagementTool

            interface = self.ensure_interface(
                Path(str(payload.get("projectRoot") or self.project_root))
            )
            session_id = str(payload.get("sessionId") or "").strip()
            session = interface.session_manager.load_session(session_id) if session_id else None
            if session is None:
                raise ValueError(f"Session not found: {session_id}")

            interface._init_agent(
                persist_config_changes=False,
                defer_runtime_enrichment=True,
            )
            if interface.agent is None:
                raise RuntimeError("Context compression requires an active model.")

            # Agent initialization can refresh runtime scope, so make the requested
            # Desktop session authoritative immediately before compression.
            session = interface.session_manager.load_session(session_id)
            if session is None:
                raise ValueError(f"Session not found: {session_id}")
            interface.agent.set_history(session.messages)

            result = ContextManagementTool(interface._get_app_context()).execute(
                action="compress",
                keep_last_messages=8,
                focus=str(payload.get("focus") or "").strip(),
            )
            if not result.success:
                raise RuntimeError(result.error or result.output or "Context compression failed.")

            session = interface.session_manager.get_current_session()
            if session is None:
                raise RuntimeError("Context compression completed without an active session.")
            return {
                "id": request_id,
                "type": "context.compacted",
                "success": True,
                "message": result.output,
                "session": _json_safe(session.to_wire_dict()),
                "sessions": self.sessions_payload(),
                "recovery": self.recovery_payload(),
                "context_engine": self.context_status_payload(),
            }
        if action in {"getModelSources", "refreshModelSources"}:
            return {
                "id": request_id,
                "type": "models",
                "models": self.model_sources_payload(fetch_live=action == "refreshModelSources"),
            }
        if action == "selectModel":
            from .desktop_catalog import apply_model_selection

            interface = self.ensure_interface()
            config = interface.config_manager.load()
            selected = apply_model_selection(
                config,
                payload.get("source") or config.active_model_source,
                payload.get("modelId") or payload.get("model") or "",
                payload.get("reasoning") if "reasoning" in payload else None,
            )
            interface.config_manager.save(config)
            self._refresh_agent()
            return {
                "id": request_id,
                "type": "model.selected",
                "selected": _json_safe(selected),
                "models": self.model_sources_payload(),
                "workspace": self.workspace_payload(),
            }
        if action == "setProviderConfig":
            from .desktop_catalog import apply_provider_config_patch

            interface = self.ensure_interface()
            config = interface.config_manager.load()
            apply_provider_config_patch(
                config,
                payload.get("source"),
                payload.get("patch") if isinstance(payload.get("patch"), dict) else {},
                payload.get("clearFields") if isinstance(payload.get("clearFields"), list) else [],
            )
            interface.config_manager.save(config)
            self._refresh_agent()
            return {
                "id": request_id,
                "type": "provider.updated",
                "models": self.model_sources_payload(),
                "workspace": self.workspace_payload(),
            }
        if action in {"addStandardModel", "updateStandardModel", "deleteStandardModel"}:
            from .desktop_catalog import add_standard_model, delete_standard_model, update_standard_model

            interface = self.ensure_interface()
            config = interface.config_manager.load()
            if action == "addStandardModel":
                index = add_standard_model(config, payload.get("model") if isinstance(payload.get("model"), dict) else payload)
            else:
                index = int(payload.get("index"))
                if action == "updateStandardModel":
                    update_standard_model(
                        config,
                        index,
                        payload.get("model") if isinstance(payload.get("model"), dict) else {},
                    )
                else:
                    delete_standard_model(config, index)
            interface.config_manager.save(config)
            self._refresh_agent()
            return {
                "id": request_id,
                "type": "standard-model.updated",
                "index": index,
                "models": self.model_sources_payload(),
                "workspace": self.workspace_payload(),
            }
        if action in {
            "addCustomProvider",
            "updateCustomProvider",
            "deleteCustomProvider",
            "refreshCustomProviderModels",
            "selectCustomProviderModel",
        }:
            from .desktop_catalog import (
                create_custom_provider,
                delete_custom_provider,
                refresh_custom_provider_models,
                select_custom_provider_model,
                update_custom_provider,
            )

            interface = self.ensure_interface()
            config = interface.config_manager.load()
            provider_ref = payload.get("providerId") or payload.get("provider") or ""
            provider: Optional[Dict[str, Any]] = None
            if action == "addCustomProvider":
                provider = create_custom_provider(
                    config,
                    payload.get("provider") if isinstance(payload.get("provider"), dict) else payload,
                )
            elif action == "updateCustomProvider":
                provider = update_custom_provider(
                    config,
                    provider_ref,
                    payload.get("patch") if isinstance(payload.get("patch"), dict) else {},
                )
            elif action == "deleteCustomProvider":
                delete_custom_provider(config, provider_ref)
            elif action == "refreshCustomProviderModels":
                provider = refresh_custom_provider_models(config, provider_ref)
            else:
                provider = select_custom_provider_model(
                    config,
                    provider_ref,
                    payload.get("modelId") or payload.get("model") or "",
                    payload.get("contextLimit"),
                )
            interface.config_manager.save(config)
            self._refresh_agent()
            return {
                "id": request_id,
                "type": "custom-provider.updated",
                "provider": _json_safe(provider),
                "models": self.model_sources_payload(),
                "workspace": self.workspace_payload(),
            }
        if action == "probeProviders":
            from .desktop_catalog import probe_provider_availability

            interface = self.ensure_interface()
            config = interface.config_manager.load()
            keys = payload.get("keys")
            return {
                "id": request_id,
                "type": "providers.probed",
                "probes": _json_safe(
                    probe_provider_availability(
                        config,
                        [str(key) for key in keys] if isinstance(keys, list) else None,
                    )
                ),
            }
        if action == "listSessions":
            return {"id": request_id, "type": "sessions", "sessions": self.sessions_payload()}
        if action == "getSession":
            session_id = str(payload.get("sessionId") or payload.get("id") or "").strip()
            session = self.active_session_payload(session_id)
            if session is None:
                raise ValueError(f"Session not found: {session_id}")
            return {"id": request_id, "type": "session", "session": session, "sessions": self.sessions_payload()}
        if action == "createSession":
            interface = self.ensure_interface()
            name = str(payload.get("name") or "").strip() or None
            session = interface.session_manager.create_session(name)
            if interface.agent is not None:
                interface.agent.set_history(session.messages)
            return {
                "id": request_id,
                "type": "session.created",
                "session": _json_safe(session.to_wire_dict()),
                "sessions": self.sessions_payload(),
            }
        if action == "deleteSessions":
            if not bool(payload.get("confirmed", False)):
                raise ValueError("Deleting sessions requires confirmed=true.")
            raw_ids = payload.get("sessionIds")
            if not isinstance(raw_ids, list):
                raise ValueError("sessionIds must be a list.")
            requested_ids = list(dict.fromkeys(
                str(session_id or "").strip()
                for session_id in raw_ids
                if str(session_id or "").strip()
            ))
            if not requested_ids:
                raise ValueError("At least one session id is required.")

            interface = self.ensure_interface()
            manager = interface.session_manager
            previous_session = manager.get_current_session() or manager.restore_last_session()
            deleted_ids = []
            for session_id in requested_ids:
                session = manager.load_session(session_id)
                if session is not None and manager.delete_session(session.id):
                    deleted_ids.append(session.id)

            deleted_id_set = set(deleted_ids)
            if previous_session is not None and previous_session.id not in deleted_id_set:
                session = manager.load_session(previous_session.id)
            else:
                remaining = manager.list_sessions()
                session = manager.load_session(remaining[0].id) if remaining else None
            if interface.agent is not None:
                interface.agent.set_history(session.messages if session is not None else [])
            return {
                "id": request_id,
                "type": "sessions.deleted",
                "deleted_session_ids": deleted_ids,
                "session": _json_safe(session.to_wire_dict()) if session is not None else None,
                "sessions": self.sessions_payload(),
            }
        if action in {"renameSession", "deleteSession", "forkSession", "rewindSession"}:
            interface = self.ensure_interface()
            manager = interface.session_manager
            previous_session = manager.get_current_session() or manager.restore_last_session()
            session_id = str(payload.get("sessionId") or payload.get("id") or "").strip()
            session = manager.load_session(session_id) if session_id else manager.get_current_session()
            if session is None:
                raise ValueError(f"Session not found: {session_id}")
            updated_session = None
            if action == "renameSession":
                name = str(payload.get("name") or "").strip()
                if not name:
                    raise ValueError("Session name is required.")
                session.name = name
                manager.save_session(session)
                updated_session = session
                if previous_session is not None and previous_session.id != session.id:
                    session = manager.load_session(previous_session.id)
            elif action == "deleteSession":
                if not bool(payload.get("confirmed", False)):
                    raise ValueError("Deleting a session requires confirmed=true.")
                manager.delete_session(session.id)
                if previous_session is not None and previous_session.id != session.id:
                    session = manager.load_session(previous_session.id)
                else:
                    remaining = manager.list_sessions()
                    session = manager.load_session(remaining[0].id) if remaining else None
            elif action == "forkSession":
                count = payload.get("messageCount")
                session = manager.fork_current_session(
                    int(count) if count is not None else None,
                    str(payload.get("name") or "").strip() or None,
                )
            else:
                if not bool(payload.get("confirmed", False)):
                    raise ValueError("Rewinding a session requires confirmed=true.")
                session = manager.rewind_current_session(int(payload.get("messageCount", 0)))
            if session is not None and interface.agent is not None:
                interface.agent.set_history(session.messages)
            return {
                "id": request_id,
                "type": "session.updated",
                "session": _json_safe(session.to_wire_dict()) if session is not None else None,
                "updated_session": _json_safe(updated_session.to_wire_dict()) if updated_session is not None else None,
                "sessions": self.sessions_payload(),
            }
        if action == "searchSessions":
            query = str(payload.get("query") or "").strip()
            return {
                "id": request_id,
                "type": "session.search",
                "query": query,
                "results": _json_safe(self.ensure_interface().session_manager.search_sessions(query)),
            }
        if action == "deleteProjectData":
            if not bool(payload.get("confirmed", False)):
                raise ValueError("Deleting project data requires confirmed=true.")
            from .config import ConfigManager
            from .security_utils import purge_workspace_state

            root = Path(str(payload.get("projectRoot") or self.project_root)).expanduser().resolve()
            if not root.is_dir():
                raise ValueError(f"Workspace does not exist: {root}")
            config_manager = ConfigManager(root)
            config_manager.ensure_dirs()
            project_data_dir = config_manager.project_data_dir.resolve()
            sessions_dir = project_data_dir / "sessions"
            session_count = sum(1 for _ in sessions_dir.glob("*.json")) if sessions_dir.is_dir() else 0
            if self.interface is not None and self.project_root == root:
                self._dispose_interface()
            result = purge_workspace_state(root, project_data_dir)
            if result.get("errors"):
                raise RuntimeError("; ".join(str(item) for item in result["errors"]))
            return {
                "id": request_id,
                "type": "project.deleted",
                "project_root": str(root),
                "project_data_dir": str(project_data_dir),
                "deleted_sessions": session_count,
                "deleted": _json_safe(result.get("deleted", [])),
            }
        if action == "listCommands":
            return {"id": request_id, "type": "commands", "commands": self.commands_payload()}
        if action == "workspaceMentions":
            query = str(payload.get("query") or "").strip()
            limit = max(1, min(100, int(payload.get("limit", 24) or 24)))
            interface = self.ensure_interface()
            started = time.perf_counter()
            candidates = interface._collect_workspace_mention_candidates(query, limit=limit)
            return {
                "id": request_id,
                "type": "workspace.mentions",
                "query": query,
                "items": _json_safe(candidates),
                "elapsed_ms": int((time.perf_counter() - started) * 1000),
                "context_engine": self.context_status_payload(),
            }
        if action == "indexWorkspace":
            result = self._run_workspace_index()
            return {
                "id": request_id,
                "type": "workspace.indexed",
                "result": _json_safe(vars(result)),
                "workspace": self.workspace_payload(),
            }
        if action == "getRecovery":
            return {"id": request_id, "type": "recovery", "recovery": self.recovery_payload()}
        if action == "rollbackCheckpoint":
            if not bool(payload.get("confirmed", False)):
                raise ValueError("Rolling back a checkpoint requires confirmed=true.")
            interface = self.ensure_interface()
            result = interface.rollback_manager.rollback_to_checkpoint(str(payload.get("checkpointId") or ""))
            if result.success and result.restored_messages is not None:
                session = interface.session_manager.get_current_session()
                if session is not None:
                    session.messages = list(result.restored_messages)
                    interface.session_manager.save_session(session)
                    if interface.agent is not None:
                        interface.agent.set_history(session.messages)
            return {
                "id": request_id,
                "type": "rollback.result",
                "result": _json_safe(vars(result)),
                "recovery": self.recovery_payload(),
            }
        if action == "listSettings":
            return {"id": request_id, "type": "settings", "settings": self.settings_payload()}
        if action == "setSetting":
            from .settings_catalog import apply_setting_value

            interface = self.ensure_interface()
            config = interface.config_manager.load()
            success, detail, reinit = apply_setting_value(
                config,
                interface.config_manager,
                interface.rules_manager,
                str(payload.get("key") or ""),
                payload.get("value"),
                interface.runtime_plugin_manager,
            )
            if success and not str(payload.get("key") or "").startswith("plugin_enabled:"):
                interface.config_manager.save(config)
            if success:
                self._refresh_plugin_dependents()
                if reinit and interface.agent is not None:
                    interface._init_agent(config_override=interface.config_manager.load(), persist_config_changes=False)
            return {
                "id": request_id,
                "type": "setting.updated",
                "success": success,
                "message": detail,
                "settings": self.settings_payload(),
                "models": self.model_sources_payload(),
                "workspace": self.workspace_payload(),
            }
        if action in {"listPlugins", "refreshPlugins"}:
            return {
                "id": request_id,
                "type": "plugins",
                "plugins": self.plugins_payload(force_refresh=action == "refreshPlugins"),
            }
        if action in {"setPluginEnabled", "setPluginTrust"}:
            from .settings_catalog import parse_bool

            interface = self.ensure_interface()
            manager = interface.runtime_plugin_manager
            plugin_id = str(payload.get("pluginId") or payload.get("id") or "").strip()
            if not plugin_id:
                raise ValueError("Plugin id is required.")
            if action == "setPluginEnabled":
                enabled = parse_bool(payload.get("enabled"))
                if enabled is None:
                    raise ValueError("Plugin enabled value must be a boolean.")
                manager.set_plugin_enabled(plugin_id, enabled)
            else:
                trusted = parse_bool(payload.get("trusted"))
                if trusted is None:
                    raise ValueError("Plugin trusted value must be a boolean.")
                manager.set_plugin_trust(plugin_id, trusted)
            self._refresh_plugin_dependents()
            return {
                "id": request_id,
                "type": "plugin.updated",
                "plugin_id": plugin_id,
                "plugins": self.plugins_payload(),
                "settings": self.settings_payload(),
            }
        if action == "inspectPlugin":
            manager = self.ensure_interface().runtime_plugin_manager
            plugin_id = str(payload.get("pluginId") or payload.get("id") or "").strip()
            record = manager.get_record(plugin_id, force_refresh=False)
            return {
                "id": request_id,
                "type": "plugin.inspect",
                "record": self._plugin_record(record) if record else None,
            }
        if action in {"listSkills", "refreshSkills"}:
            return {
                "id": request_id,
                "type": "skills",
                "skills": self.skills_payload(force_refresh=action == "refreshSkills"),
            }
        if action in {"pinSkill", "unpinSkill", "clearPinnedSkills"}:
            manager = self.ensure_interface().skills_manager
            wanted = str(payload.get("skill") or payload.get("name") or payload.get("key") or "").strip()
            if action == "clearPinnedSkills":
                released = manager.clear_pinned_skills()
                result = {"status": "cleared", "name": "", "released": released}
            else:
                if not wanted:
                    raise ValueError("Skill name is required.")
                if action == "pinSkill":
                    outcome = manager.pin_skill(wanted.lstrip("$"), force_refresh=True)
                else:
                    outcome = manager.unpin_skill(wanted.lstrip("$"))
                result = {
                    "status": str(outcome.get("status") or ""),
                    "name": str(outcome.get("name") or wanted),
                    "released": [],
                }
            # A pin is an instruction for the next turn, so the system prompt has
            # to be rebuilt now rather than at the next agent re-init.
            self._refresh_pinned_skills()
            return {
                "id": request_id,
                "type": "skill.pinned",
                "status": result["status"],
                "name": result["name"],
                "released": result["released"],
                "skills": self.skills_payload(),
            }
        if action == "inspectSkill":
            manager = self.ensure_interface().skills_manager
            wanted = str(payload.get("skill") or payload.get("name") or payload.get("key") or "").strip()
            record = manager.get_record(wanted.lstrip("$"), force_refresh=False) if wanted else None
            pinned_keys = frozenset(getattr(manager, "pinned_keys", ()) or ())
            detail = None
            if record is not None:
                detail = self._skill_record(record, pinned_keys)
                detail["body"] = str(getattr(record, "body", "") or "")
                detail["metadata"] = _json_safe(dict(getattr(record, "metadata", {}) or {}))
            return {
                "id": request_id,
                "type": "skill.inspect",
                "record": detail,
            }
        if action == "listTools":
            mode = str(payload.get("mode") or "reverie").strip()
            records = self.ensure_tool_executor().get_tool_records(mode)
            return {
                "id": request_id,
                "type": "tools",
                "mode": mode,
                "tools": _json_safe([_desktop_tool_record(record) for record in records]),
            }
        if action == "ratsState":
            return {"id": request_id, "type": "rats.state", "rats": _json_safe(self.rats_runtime.refresh())}
        if action in {"ratsRegisterProvider", "ratsAddEngine"}:
            executable = str(payload.get("executable") or "").strip()
            if not executable:
                raise ValueError("A RATS provider executable is required.")
            provider_id = str(payload.get("providerId") or "reverie.engine").strip()
            if action == "ratsAddEngine":
                # Compatibility alias for packaged Desktop clients; the runtime has one implementation.
                state = self.rats_runtime.add_engine(Path(executable))
            else:
                state = self.rats_runtime.register_provider_executable(provider_id, Path(executable))
            return {"id": request_id, "type": "rats.state", "rats": _json_safe(state)}
        if action == "ratsRemoveRoot":
            root = str(payload.get("root") or "").strip()
            if not root:
                raise ValueError("A RATS discovery root is required.")
            state = self.rats_runtime.remove_discovery_root(Path(root))
            return {"id": request_id, "type": "rats.state", "rats": _json_safe(state)}
        if action in {"ratsSetProviderEnabled", "ratsSetEnabled"}:
            executable = str(payload.get("executable") or "").strip()
            enabled = payload.get("enabled")
            if not executable or not isinstance(enabled, bool):
                raise ValueError("RATS executable and boolean enabled state are required.")
            provider_id = str(payload.get("providerId") or "reverie.engine").strip()
            if action == "ratsSetEnabled":
                # Compatibility alias for packaged Desktop clients; the runtime has one implementation.
                state = self.rats_runtime.set_engine_enabled(executable, enabled, payload.get("permissions"))
            else:
                state = self.rats_runtime.set_provider_enabled(
                    provider_id,
                    executable,
                    enabled,
                    payload.get("permissions"),
                )
            return {"id": request_id, "type": "rats.state", "rats": _json_safe(state)}
        if action == "ratsTasks":
            service_id = str(payload.get("serviceId") or "").strip()
            provider_id = str(payload.get("providerId") or "").strip()
            tasks = self.rats_runtime.sync_tasks(service_id=service_id, provider_id=provider_id)
            return {
                "id": request_id,
                "type": "rats.tasks",
                "service_id": service_id,
                "provider_id": provider_id,
                "tasks": _json_safe(tasks),
            }
        if action == "ratsTaskStatus":
            service_id = str(payload.get("serviceId") or "").strip()
            task_id = str(payload.get("taskId") or "").strip()
            provider_id = str(payload.get("providerId") or "").strip()
            if not service_id or not task_id:
                raise ValueError("RATS task status requires serviceId and taskId.")
            result = self.rats_runtime.task_status(
                service_id,
                task_id,
                provider_id=provider_id,
                deadline_ms=payload.get("deadlineMs"),
            )
            return {"id": request_id, "type": "rats.task.status", "service_id": service_id, "task_id": task_id, "result": _json_safe(result)}
        if action == "ratsTaskEvents":
            service_id = str(payload.get("serviceId") or "").strip()
            task_id = str(payload.get("taskId") or "").strip()
            provider_id = str(payload.get("providerId") or "").strip()
            if not service_id or not task_id:
                raise ValueError("RATS task events requires serviceId and taskId.")
            cursor = payload.get("cursor")
            result = self.rats_runtime.task_events(
                service_id,
                task_id,
                provider_id=provider_id,
                cursor=cursor,
                limit=payload.get("limit", 32),
                deadline_ms=payload.get("deadlineMs"),
            )
            return {"id": request_id, "type": "rats.task.events", "service_id": service_id, "task_id": task_id, "result": _json_safe(result)}
        if action == "ratsTaskCancel":
            service_id = str(payload.get("serviceId") or "").strip()
            task_id = str(payload.get("taskId") or "").strip()
            provider_id = str(payload.get("providerId") or "").strip()
            if not service_id or not task_id:
                raise ValueError("RATS task cancellation requires serviceId and taskId.")
            result = self.rats_runtime.cancel_task(
                service_id,
                task_id,
                provider_id=provider_id,
                deadline_ms=payload.get("deadlineMs"),
            )
            return {"id": request_id, "type": "rats.task.cancelled", "service_id": service_id, "task_id": task_id, "result": _json_safe(result)}
        if action == "ratsTaskLogs":
            service_id = str(payload.get("serviceId") or "").strip()
            task_id = str(payload.get("taskId") or "").strip()
            provider_id = str(payload.get("providerId") or "").strip()
            if not service_id or not task_id:
                raise ValueError("RATS task logs requires serviceId and taskId.")
            result = self.rats_runtime.task_logs(
                service_id,
                task_id,
                provider_id=provider_id,
                cursor=payload.get("cursor"),
                limit=payload.get("limit", 65_536),
                deadline_ms=payload.get("deadlineMs"),
            )
            return {"id": request_id, "type": "rats.task.logs", "service_id": service_id, "task_id": task_id, "result": _json_safe(result)}
        if action == "ratsDescribe":
            service_id = str(payload.get("serviceId") or "").strip()
            provider_id = str(payload.get("providerId") or "").strip()
            names = payload.get("names") if isinstance(payload.get("names"), list) else []
            definitions = self.rats_runtime.describe(service_id, names, provider_id=provider_id)
            return {
                "id": request_id,
                "type": "rats.definitions",
                "provider_id": provider_id,
                "service_id": service_id,
                "definitions": _json_safe(definitions),
            }
        if action == "callPluginTool":
            from .plugin.dynamic_tool import RuntimePluginDynamicTool

            tool_name = str(payload.get("toolName") or payload.get("name") or "").strip()
            arguments = payload.get("arguments") if isinstance(payload.get("arguments"), dict) else {}
            if not tool_name:
                raise ValueError("Plugin tool name is required.")
            executor = self.ensure_tool_executor()
            tool = executor.get_tool(tool_name)
            if not isinstance(tool, RuntimePluginDynamicTool):
                raise ValueError(f"Not a runtime plugin tool: {tool_name}")
            result = executor.execute(tool_name, arguments)
            self.ensure_interface().workspace_stats_manager.flush()
            return {
                "id": request_id,
                "type": "plugin.tool.result",
                "tool_name": tool.name,
                "success": bool(result.success),
                "output": result.output,
                "error": result.error,
                "data": _json_safe(result.data),
                "status": str(getattr(result.status, "value", result.status)),
            }
        if action == "shutdown":
            self.rats_runtime.shutdown()
            return {"id": request_id, "type": "shutdown"}
        raise ValueError(f"Unknown action: {action}")


def _configure_utf8_stdio() -> None:
    """Keep the frozen Windows JSONL bridge lossless for non-ASCII history."""
    for stream in (sys.stdin, sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if not callable(reconfigure):
            continue
        try:
            reconfigure(encoding="utf-8", errors="strict")
        except (OSError, ValueError):
            pass


def main() -> int:
    _configure_utf8_stdio()
    write_lock = threading.Lock()

    def _write_message(message: Dict[str, Any]) -> None:
        with write_lock:
            sys.stdout.write(json.dumps(_json_safe(message), ensure_ascii=False) + "\n")
            sys.stdout.flush()

    bridge = ReverieSdkBridge(event_writer=_write_message)
    _write_message({"type": "ready", "protocol_version": 1})

    def _dispatch_and_write(message: Dict[str, Any]) -> Dict[str, Any]:
        request_id = message.get("id")
        try:
            result = bridge.dispatch(message)
        except Exception as exc:
            result = {"id": request_id, "type": "error", "error": str(exc)}
        _write_message(result)
        return result

    for raw_line in sys.stdin:
        raw_line = str(raw_line or "").lstrip("\ufeff").strip()
        if not raw_line:
            continue
        try:
            message = json.loads(raw_line)
        except Exception as exc:
            _write_message({"id": None, "type": "error", "error": str(exc)})
            continue
        if not isinstance(message, dict):
            _write_message({"id": None, "type": "error", "error": "Bridge message must be a JSON object."})
            continue
        action = str(message.get("action") or "")
        if action in _BACKGROUND_DISPATCH_ACTIONS:
            threading.Thread(
                target=_dispatch_and_write,
                args=(message,),
                name=f"reverie-desktop-{action.lower()}",
                daemon=True,
            ).start()
            continue
        result = _dispatch_and_write(message)
        if result.get("type") == "shutdown":
            break
    bridge.rats_runtime.shutdown()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
