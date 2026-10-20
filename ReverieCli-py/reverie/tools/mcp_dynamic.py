"""Dynamic MCP tool wrapper for Reverie's tool system."""

from __future__ import annotations

from typing import Any, Dict, Optional

from .base import BaseTool, ToolResult
from ..mcp import MCPClientError
from ..modes import normalize_mode


class MCPDynamicTool(BaseTool):
    """Expose one discovered MCP tool through Reverie's BaseTool interface."""

    def __init__(self, context: Optional[Dict[str, Any]], metadata: Dict[str, Any]):
        super().__init__(context=context)
        self.metadata = dict(metadata or {})
        self.name = str(self.metadata.get("name", "") or "").strip() or "mcp_tool"
        self.aliases = tuple(self.metadata.get("aliases", []) or ())
        self.search_hint = str(self.metadata.get("search_hint", "") or "").strip()
        self.tool_category = str(self.metadata.get("category", "") or "").strip() or "mcp"
        self.tool_tags = tuple(self.metadata.get("tags", []) or ())
        self.read_only = bool(self.metadata.get("read_only", False))
        self.concurrency_safe = bool(self.metadata.get("concurrency_safe", False))
        self.destructive = bool(self.metadata.get("destructive", False))
        self.should_defer = bool(self.metadata.get("should_defer", False))
        self.always_load = bool(self.metadata.get("always_load", False))
        qualified_name = str(self.metadata.get("qualified_name", "") or "").strip()
        description = str(self.metadata.get("description", "") or "").strip()
        trust_label = "trusted" if bool(self.metadata.get("trust", False)) else "confirmation-required"
        transport = str(self.metadata.get("transport", "") or "").strip() or "mcp"
        self.description = (
            description
            or f"MCP tool {qualified_name or self.name}."
        )
        if qualified_name:
            self.description = f"{self.description} [server={qualified_name}, transport={transport}, {trust_label}]"
        self.parameters = dict(self.metadata.get("parameters", {})) if isinstance(self.metadata.get("parameters"), dict) else {
            "type": "object",
            "properties": {},
            "required": [],
        }
        self.include_modes = {
            normalize_mode(mode)
            for mode in (self.metadata.get("include_modes", []) or [])
            if str(mode or "").strip()
        }
        self.exclude_modes = {
            normalize_mode(mode)
            for mode in (self.metadata.get("exclude_modes", []) or [])
            if str(mode or "").strip()
        }

    def _runtime(self):
        runtime = self.context.get("mcp_runtime")
        if runtime is None:
            raise MCPClientError("MCP runtime is not available.")
        return runtime

    def execute(self, **kwargs) -> ToolResult:
        runtime = self._runtime()
        binding = self.context.get("mcp_app_binding")
        visibility = self.metadata.get("ui", {}).get("visibility", ["model", "app"])
        if "model" not in visibility and not binding:
            return ToolResult.fail("Tool visibility does not allow model calls.")
        try:
            options = {"app_binding": binding} if binding else {}
            response = runtime.call_tool(
                str(self.metadata.get("server_name", "") or ""),
                str(self.metadata.get("tool_name", "") or ""),
                kwargs,
                **options,
            )
        except Exception as exc:
            return ToolResult.fail(str(exc))

        output = str(response.get("output", "") or "").strip()
        payload = response.get("data", {}) if isinstance(response.get("data"), dict) else {}
        capture = self.context.get("mcp_app_result_handler")
        if callable(capture):
            capture(response.get("result"))
        elif self.metadata.get("ui", {}).get("resourceUri"):
            try:
                from ..mcp_apps import publish_mcp_app
                payload["view"] = publish_mcp_app(self.context, self.metadata, kwargs, response, output or "MCP tool completed.")
                view = payload["view"]
                reference = f"Interactive view ready (view_id={view['view_id']}, revision={view['revision']})."
                output = f"{output}\n{reference}".strip()
                payload.setdefault("message_content", []).append({"type": "text", "text": reference})
            except Exception as exc:
                # A UI failure must never destroy the tool's useful text result.
                from ..diagnostics import report_suppressed_exception
                report_suppressed_exception("MCP App unavailable")
                fallback = f"UI unavailable: {exc}"
                output = f"{output}\n{fallback}".strip()
                payload.setdefault("message_content", []).append({"type": "text", "text": fallback})
        if response.get("success", True):
            return ToolResult.ok(output or "MCP tool completed successfully.", data=payload)
        result = ToolResult.fail(output or "MCP tool reported an error.")
        result.data = payload
        return result

    def get_execution_message(self, **kwargs) -> str:
        qualified_name = str(self.metadata.get("qualified_name", "") or self.name).strip()
        return f"Calling {qualified_name}..."

    def visible_in_mode(self, mode: object, *, audience: str = "model") -> bool:
        if audience not in self.metadata.get("ui", {}).get("visibility", ["model", "app"]):
            return False
        normalized = normalize_mode(mode)
        if self.include_modes and normalized not in self.include_modes:
            return False
        if normalized in self.exclude_modes:
            return False
        return True
