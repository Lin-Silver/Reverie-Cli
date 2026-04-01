"""Tool discovery helpers for Reverie's runtime tool surface."""

from __future__ import annotations

from typing import Any, Dict, Iterable, List
import re

from ..modes import get_mode_display_name, normalize_mode
from ..plugin.dynamic_tool import RuntimePluginDynamicTool
from .base import BaseTool, ToolResult
from .mcp_dynamic import MCPDynamicTool


_TOKEN_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]*")


def _extract_tokens(value: Any) -> set[str]:
    """Extract normalized search tokens from free text."""
    return {
        str(match.group(0) or "").strip("._-").lower()
        for match in _TOKEN_RE.finditer(str(value or ""))
        if str(match.group(0) or "").strip("._-")
    }


def _clip(value: Any, limit: int = 180) -> str:
    """Clip text to a predictable one-line summary."""
    text = re.sub(r"\s+", " ", str(value or "").strip())
    if len(text) <= limit:
        return text
    return f"{text[: max(1, limit - 3)].rstrip()}..."


class ToolCatalogTool(BaseTool):
    """Search and inspect the tools currently visible to the active agent."""

    name = "tool_catalog"

    description = """Discover the tools currently visible to the active agent.

Use this tool when you need to search for the right tool, inspect one tool's
schema, or understand which dynamic MCP/runtime-plugin tools are currently
available in the active mode.
"""

    parameters = {
        "type": "object",
        "properties": {
            "operation": {
                "type": "string",
                "enum": ["list", "search", "inspect"],
                "description": "Whether to list tools, search by keywords, or inspect one tool in detail",
            },
            "query": {
                "type": "string",
                "description": "For search: keywords to match against tool names, descriptions, and parameters",
            },
            "tool_name": {
                "type": "string",
                "description": "For inspect: exact tool name to inspect",
            },
            "mode": {
                "type": "string",
                "description": "Optional mode override. Defaults to the active agent mode.",
            },
            "max_results": {
                "type": "integer",
                "description": "Maximum rows to return for list/search (default: 8, max: 25)",
                "default": 8,
            },
            "include_schema": {
                "type": "boolean",
                "description": "For inspect: include the full JSON schema in the result data payload",
                "default": True,
            },
        },
        "required": ["operation"],
    }

    def _tool_executor(self):
        agent = self.context.get("agent")
        tool_executor = getattr(agent, "tool_executor", None) if agent is not None else None
        if tool_executor is None:
            raise RuntimeError("Tool executor is not available in the current context.")
        return tool_executor

    def _resolve_mode(self, mode_override: Any) -> str:
        if str(mode_override or "").strip():
            return normalize_mode(mode_override)
        agent = self.context.get("agent")
        return normalize_mode(getattr(agent, "mode", "reverie"))

    def _classify_tool_kind(self, tool: BaseTool) -> str:
        if isinstance(tool, MCPDynamicTool):
            return "mcp"
        if isinstance(tool, RuntimePluginDynamicTool):
            return "runtime-plugin"
        return "built-in"

    def _visible_tool_records(self, mode: str) -> List[Dict[str, Any]]:
        executor = self._tool_executor()
        schemas = executor.get_tool_schemas(mode=mode)
        records: List[Dict[str, Any]] = []

        for schema in schemas:
            if not isinstance(schema, dict):
                continue
            function = schema.get("function", {})
            name = str(function.get("name", "") or "").strip()
            if not name:
                continue
            tool = executor.get_tool(name)
            if tool is None:
                continue
            parameters = function.get("parameters", {}) if isinstance(function, dict) else {}
            properties = parameters.get("properties", {}) if isinstance(parameters, dict) else {}
            records.append(
                {
                    "name": name,
                    "tool": tool,
                    "kind": self._classify_tool_kind(tool),
                    "description": str(function.get("description", "") or getattr(tool, "description", "") or "").strip(),
                    "schema": schema,
                    "required": list(parameters.get("required", [])) if isinstance(parameters, dict) else [],
                    "properties": list(properties.keys()) if isinstance(properties, dict) else [],
                }
            )

        records.sort(key=lambda item: (item["kind"], item["name"].lower()))
        return records

    def _iter_searchable_chunks(self, record: Dict[str, Any]) -> Iterable[str]:
        yield str(record.get("name", "") or "")
        yield str(record.get("kind", "") or "")
        yield str(record.get("description", "") or "")
        for item in record.get("required", []) or []:
            yield str(item or "")
        for item in record.get("properties", []) or []:
            yield str(item or "")

    def _score_record(self, record: Dict[str, Any], query: str) -> int:
        normalized_query = str(query or "").strip().lower()
        if not normalized_query:
            return 0

        name = str(record.get("name", "") or "").strip().lower()
        description = str(record.get("description", "") or "").strip().lower()
        haystack_tokens = set()
        for chunk in self._iter_searchable_chunks(record):
            haystack_tokens |= _extract_tokens(chunk)

        score = 0
        if name == normalized_query:
            score += 200
        elif name.startswith(normalized_query):
            score += 120
        elif normalized_query in name:
            score += 80

        query_tokens = _extract_tokens(normalized_query)
        overlap = haystack_tokens & query_tokens
        score += len(overlap) * 18

        if query_tokens and query_tokens.issubset(haystack_tokens):
            score += 30

        for token in query_tokens:
            if token in name:
                score += 16
            if token in description:
                score += 8

        return score

    def _format_record_line(self, record: Dict[str, Any]) -> str:
        description = _clip(record.get("description", ""), 140)
        properties = record.get("properties", []) or []
        prop_preview = ", ".join(str(item) for item in properties[:4]) if properties else "(no params)"
        if len(properties) > 4:
            prop_preview = f"{prop_preview}, +{len(properties) - 4} more"
        return (
            f"- {record['name']} [{record['kind']}]\n"
            f"  description: {description}\n"
            f"  params: {prop_preview}"
        )

    def _render_list(self, mode: str, records: List[Dict[str, Any]], max_results: int) -> ToolResult:
        visible = records[:max_results]
        lines = [
            f"Visible tools for mode '{mode}' ({get_mode_display_name(mode)}): {len(records)} total",
        ]
        if not visible:
            lines.append("- No tools are currently visible.")
        else:
            lines.append("")
            lines.extend(self._format_record_line(record) for record in visible)
            if len(records) > len(visible):
                lines.append("")
                lines.append(f"... {len(records) - len(visible)} additional tools omitted.")

        return ToolResult.ok(
            "\n".join(lines),
            data={
                "mode": mode,
                "count": len(records),
                "items": [
                    {
                        "name": record["name"],
                        "kind": record["kind"],
                        "description": record["description"],
                        "required": list(record["required"]),
                        "properties": list(record["properties"]),
                    }
                    for record in visible
                ],
            },
        )

    def _render_search(self, mode: str, records: List[Dict[str, Any]], query: str, max_results: int) -> ToolResult:
        if not str(query or "").strip():
            return ToolResult.fail("query is required for operation='search'")

        scored = [
            (self._score_record(record, query), record)
            for record in records
        ]
        matches = [record for score, record in scored if score > 0]
        matches.sort(key=lambda item: (-self._score_record(item, query), item["name"].lower()))
        visible = matches[:max_results]

        lines = [
            f"Tool search for '{query}' in mode '{mode}': {len(matches)} matches",
        ]
        if not visible:
            lines.append("- No matching tools found. Try broader keywords or use operation='list'.")
        else:
            lines.append("")
            lines.extend(self._format_record_line(record) for record in visible)
            if len(matches) > len(visible):
                lines.append("")
                lines.append(f"... {len(matches) - len(visible)} additional matches omitted.")

        return ToolResult.ok(
            "\n".join(lines),
            data={
                "mode": mode,
                "query": query,
                "count": len(matches),
                "items": [
                    {
                        "name": record["name"],
                        "kind": record["kind"],
                        "description": record["description"],
                        "required": list(record["required"]),
                        "properties": list(record["properties"]),
                    }
                    for record in visible
                ],
            },
        )

    def _render_inspect(
        self,
        mode: str,
        records: List[Dict[str, Any]],
        tool_name: str,
        include_schema: bool,
    ) -> ToolResult:
        wanted = str(tool_name or "").strip().lower()
        if not wanted:
            return ToolResult.fail("tool_name is required for operation='inspect'")

        record = next((item for item in records if str(item["name"]).lower() == wanted), None)
        if record is None:
            return ToolResult.fail(
                f"Tool '{tool_name}' is not visible in mode '{mode}'. Use operation='list' to inspect the active tool surface."
            )

        schema = record["schema"]
        function = schema.get("function", {}) if isinstance(schema, dict) else {}
        parameters = function.get("parameters", {}) if isinstance(function, dict) else {}
        properties = parameters.get("properties", {}) if isinstance(parameters, dict) else {}
        required = set(record.get("required", []) or [])

        lines = [
            f"Tool: {record['name']}",
            f"Mode: {mode} ({get_mode_display_name(mode)})",
            f"Kind: {record['kind']}",
            f"Description: {_clip(record.get('description', ''), 400)}",
            f"Required parameters: {', '.join(sorted(required)) if required else '(none)'}",
        ]

        if properties:
            lines.append("")
            lines.append("Parameters:")
            for prop_name, prop_schema in properties.items():
                prop_schema = prop_schema if isinstance(prop_schema, dict) else {}
                prop_type = str(prop_schema.get("type", "any") or "any")
                enum_values = prop_schema.get("enum")
                enum_text = f" enum={enum_values}" if isinstance(enum_values, list) and enum_values else ""
                requirement = "required" if prop_name in required else "optional"
                description = _clip(prop_schema.get("description", ""), 180)
                lines.append(
                    f"- {prop_name} ({prop_type}, {requirement}){enum_text}: {description or '(no description)'}"
                )
        else:
            lines.append("")
            lines.append("Parameters: (none)")

        data: Dict[str, Any] = {
            "mode": mode,
            "name": record["name"],
            "kind": record["kind"],
            "description": record["description"],
            "required": sorted(required),
            "properties": properties,
        }
        if include_schema:
            data["schema"] = schema

        return ToolResult.ok("\n".join(lines), data=data)

    def execute(self, **kwargs) -> ToolResult:
        operation = str(kwargs.get("operation", "") or "").strip().lower()
        mode = self._resolve_mode(kwargs.get("mode"))
        max_results = kwargs.get("max_results", 8)
        include_schema = bool(kwargs.get("include_schema", True))

        try:
            max_results = int(max_results)
        except (TypeError, ValueError):
            return ToolResult.fail("max_results must be an integer")
        max_results = max(1, min(max_results, 25))

        records = self._visible_tool_records(mode)

        if operation == "list":
            return self._render_list(mode, records, max_results)
        if operation == "search":
            return self._render_search(mode, records, kwargs.get("query", ""), max_results)
        if operation == "inspect":
            return self._render_inspect(mode, records, kwargs.get("tool_name", ""), include_schema)
        return ToolResult.fail(f"Unknown operation: {operation}")
