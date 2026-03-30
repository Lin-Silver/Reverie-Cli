"""Dynamic tool wrapper for Reverie CLI runtime plugins."""

from __future__ import annotations

from typing import Any, Dict, Optional

from reverie.modes import normalize_mode
from reverie.tools.base import BaseTool, ToolResult


class RuntimePluginDynamicTool(BaseTool):
    """Expose one runtime-plugin command through Reverie's tool interface."""

    def __init__(self, context: Optional[Dict[str, Any]], metadata: Dict[str, Any]):
        super().__init__(context=context)
        self.metadata = dict(metadata or {})
        self.name = str(self.metadata.get("name", "") or "").strip() or "rc_plugin_tool"
        self.description = str(self.metadata.get("description", "") or "").strip() or self.name
        self.parameters = (
            dict(self.metadata.get("parameters", {}))
            if isinstance(self.metadata.get("parameters"), dict)
            else {"type": "object", "properties": {}, "required": []}
        )
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

    def _manager(self):
        manager = self.context.get("runtime_plugin_manager")
        if manager is None:
            raise RuntimeError("Runtime plugin manager is not available.")
        return manager

    def execute(self, **kwargs) -> ToolResult:
        manager = self._manager()
        try:
            response = manager.call_tool(
                str(self.metadata.get("plugin_id", "") or ""),
                str(self.metadata.get("command_name", "") or ""),
                kwargs,
            )
        except Exception as exc:
            return ToolResult.fail(str(exc))

        output = str(response.get("output", "") or "").strip()
        payload = response.get("data", {}) if isinstance(response.get("data"), dict) else {}
        if response.get("success", True):
            return ToolResult.ok(output or "Runtime plugin command completed successfully.", data=payload)
        return ToolResult.fail(output or str(response.get("error", "") or "Runtime plugin command failed."))

    def get_execution_message(self, **kwargs) -> str:
        qualified_name = str(self.metadata.get("qualified_name", "") or self.name).strip()
        return f"Calling runtime plugin {qualified_name}..."

    def visible_in_mode(self, mode: object) -> bool:
        normalized = normalize_mode(mode)
        if self.include_modes and normalized not in self.include_modes:
            return False
        if normalized in self.exclude_modes:
            return False
        return True
