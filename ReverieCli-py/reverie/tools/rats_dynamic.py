"""Dynamic wrappers for native tools exposed by a RATS/RTP service."""

from __future__ import annotations

import json
from typing import Any, Dict, Optional

from .base import BaseTool, ToolResult
from ..rats import RatsClientError


class RatsDynamicTool(BaseTool):
    """Expose one progressively loaded Reverie Engine tool to the agent."""

    def __init__(self, context: Optional[Dict[str, Any]], metadata: Dict[str, Any]):
        super().__init__(context=context)
        self.metadata = dict(metadata or {})
        self.name = str(self.metadata.get("name", "") or "").strip() or "rats_tool"
        self.search_hint = str(self.metadata.get("qualified_name", "") or "").strip()
        self.tool_category = str(self.metadata.get("category", "") or "rats").strip() or "rats"
        self.tool_tags = tuple(self.metadata.get("tags", []) or ()) + ("rats", "rtp", "reverie-engine")
        self.read_only = bool(self.metadata.get("read_only", False))
        self.concurrency_safe = bool(self.metadata.get("concurrency_safe", False))
        self.destructive = bool(self.metadata.get("destructive", False))
        self.description = str(self.metadata.get("description", "") or "").strip() or "Native Reverie Engine tool."
        qualified_name = str(self.metadata.get("qualified_name", "") or "").strip()
        permission = str(self.metadata.get("permission", "") or "none").strip()
        if qualified_name:
            self.description = f"{self.description} [RATS={qualified_name}, permission={permission}]"
        parameters = self.metadata.get("parameters")
        self.parameters = dict(parameters) if isinstance(parameters, dict) else {
            "type": "object",
            "properties": {},
            "required": [],
        }

    def _runtime(self):
        runtime = self.context.get("rats_runtime")
        if runtime is None:
            raise RatsClientError("The RATS runtime is not available.", code="runtime_unavailable")
        return runtime

    def execute(self, **kwargs) -> ToolResult:
        runtime = self._runtime()
        try:
            response = runtime.call_tool(
                str(self.metadata.get("service_id", "") or ""),
                str(self.metadata.get("engine_tool_name", "") or ""),
                kwargs,
            )
        except Exception as exc:
            return ToolResult.fail(str(exc))
        output = response.get("output", {}) if isinstance(response, dict) else {}
        return ToolResult.ok(
            json.dumps(output, ensure_ascii=False, separators=(",", ":")),
            data=output if isinstance(output, dict) else {"value": output},
        )

    def get_execution_message(self, **kwargs) -> str:
        qualified_name = str(self.metadata.get("qualified_name", "") or self.name).strip()
        return f"Calling {qualified_name} through RATS..."


__all__ = ["RatsDynamicTool"]
