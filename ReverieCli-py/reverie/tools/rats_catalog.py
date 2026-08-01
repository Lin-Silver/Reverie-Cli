"""Token-efficient progressive discovery for executable-local RATS tools."""

from __future__ import annotations

import json
from typing import Any, Dict

from .base import BaseTool, ToolResult


class RatsCatalogTool(BaseTool):
    """Search compact catalogs and progressively load native provider schemas."""

    name = "rats_catalog"
    aliases = ("rats_tools", "reverie_engine_tools", "rtp_catalog")
    search_hint = "discover load inspect and call native RATS provider tools through RTP"
    tool_category = "orchestration"
    tool_tags = ("rats", "rtp", "discover", "tool")
    read_only = True
    concurrency_safe = False
    always_load = True
    description = (
        "Search the compact catalogs of enabled RATS provider services. "
        "Search/load progressively reveals only relevant native schemas; those tools become directly callable on the next agent step."
    )
    parameters = {
        "type": "object",
        "properties": {
            "operation": {
                "type": "string",
                "enum": ["list", "search", "load"],
                "description": "List compact entries, search and load matching schemas, or load exact names.",
            },
            "query": {"type": "string", "description": "Task keywords for search."},
            "service_id": {"type": "string", "description": "Optional exact connected RATS service id."},
            "provider_id": {"type": "string", "description": "Optional exact allowlisted RATS provider id."},
            "names": {
                "type": "array",
                "items": {"type": "string"},
                "maxItems": 16,
                "description": "Exact native provider tool names for load.",
            },
            "max_results": {"type": "integer", "minimum": 1, "maximum": 16, "default": 5},
        },
        "required": ["operation"],
    }

    def _runtime(self):
        runtime = self.context.get("rats_runtime")
        if runtime is None:
            raise RuntimeError("The RATS runtime is not available.")
        return runtime

    @staticmethod
    def _output(payload: Any) -> str:
        return json.dumps(payload, ensure_ascii=False, separators=(",", ":"))

    def execute(self, **kwargs) -> ToolResult:
        runtime = self._runtime()
        operation = str(kwargs.get("operation") or "").strip().lower()
        service_id = str(kwargs.get("service_id") or "").strip()
        provider_id = str(kwargs.get("provider_id") or "").strip()
        try:
            if operation == "list":
                rows = runtime.compact_catalog()
                limit = min(16, max(1, int(kwargs.get("max_results", 5) or 5)))
                payload = {"count": len(rows), "tools": rows[:limit], "truncated": len(rows) > limit}
            elif operation == "search":
                matches = runtime.search(
                    str(kwargs.get("query") or ""),
                    limit=min(16, max(1, int(kwargs.get("max_results", 5) or 5))),
                    service_id=service_id,
                    provider_id=provider_id,
                    load=True,
                )
                payload = {
                    "matches": matches,
                    "loaded_for_next_step": [str(item.get("name") or "") for item in matches],
                }
            elif operation == "load":
                names = kwargs.get("names") if isinstance(kwargs.get("names"), list) else []
                definitions = runtime.describe(service_id, names, provider_id=provider_id)
                payload = {
                    "loaded_for_next_step": [str(item.get("name") or "") for item in definitions],
                    "definitions": definitions,
                }
            else:
                return ToolResult.fail("RATS operation must be list, search, or load.")
        except Exception as exc:
            return ToolResult.fail(str(exc))
        return ToolResult.ok(self._output(payload), data=payload if isinstance(payload, dict) else {"value": payload})


__all__ = ["RatsCatalogTool"]
