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
        try:
            response = runtime.call_tool(
                str(self.metadata.get("server_name", "") or ""),
                str(self.metadata.get("tool_name", "") or ""),
                kwargs,
            )
        except Exception as exc:
            return ToolResult.fail(str(exc))

        output = str(response.get("output", "") or "").strip()
        payload = response.get("data", {}) if isinstance(response.get("data"), dict) else {}
        if response.get("success", True):
            return ToolResult.ok(output or "MCP tool completed successfully.", data=payload)
        return ToolResult.fail(output or "MCP tool reported an error.")

    def get_execution_message(self, **kwargs) -> str:
        qualified_name = str(self.metadata.get("qualified_name", "") or self.name).strip()
        return f"Calling {qualified_name}..."

    def visible_in_mode(self, mode: object) -> bool:
        normalized = normalize_mode(mode)
        if self.include_modes and normalized not in self.include_modes:
            return False
        if normalized in self.exclude_modes:
            return False
        return True
