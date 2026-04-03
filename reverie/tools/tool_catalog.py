"""Tool discovery helpers for Reverie's runtime tool surface."""

from __future__ import annotations

from typing import Any, Dict, Iterable, List
import re

from ..modes import get_mode_display_name, get_mode_tool_discovery_profile, normalize_mode
from ..plugin.dynamic_tool import RuntimePluginDynamicTool
from .base import BaseTool, ToolResult
from .mcp_dynamic import MCPDynamicTool


_TOKEN_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]*")
_READ_INTENT_TOKENS = {
    "read",
    "view",
    "list",
    "inspect",
    "show",
    "find",
    "search",
    "lookup",
    "resource",
    "docs",
    "document",
}
_WRITE_INTENT_TOKENS = {
    "edit",
    "write",
    "create",
    "insert",
    "replace",
    "modify",
    "update",
    "delete",
    "remove",
    "rename",
    "move",
}


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
    aliases = ("tool_search", "tools_help")
    search_hint = "find inspect and recommend the right tool"
    tool_category = "orchestration"
    tool_tags = ("tool", "discover", "inspect", "schema", "recommend")
    read_only = True
    concurrency_safe = True
    always_load = True

    description = """Discover the tools currently visible to the active agent.

Use this tool when you need to search for the right tool, inspect one tool's
schema, compare tool groups, or get recommendations for which tool to call
next in the active mode.
"""

    parameters = {
        "type": "object",
        "properties": {
            "operation": {
                "type": "string",
                "enum": ["list", "search", "inspect", "recommend", "groups"],
                "description": "Whether to list tools, search by keywords, inspect one tool, recommend likely tools, or summarize tool groups",
            },
            "query": {
                "type": "string",
                "description": "For search/recommend: keywords or a short task description to match against tool names, aliases, descriptions, tags, and parameter names",
            },
            "tool_name": {
                "type": "string",
                "description": "For inspect: exact tool name or alias to inspect",
            },
            "mode": {
                "type": "string",
                "description": "Optional mode override. Defaults to the active agent mode.",
            },
            "max_results": {
                "type": "integer",
                "description": "Maximum rows to return for list/search/recommend (default: 8, max: 25)",
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

    def _tool_metadata(self, tool: BaseTool) -> Dict[str, Any]:
        metadata = {}
        if hasattr(tool, "get_metadata"):
            try:
                metadata = dict(tool.get_metadata() or {})
            except Exception:
                metadata = {}
        return metadata

    def _visible_tool_records(self, mode: str) -> List[Dict[str, Any]]:
        executor = self._tool_executor()
        if callable(getattr(executor, "get_tool_records", None)):
            records = list(executor.get_tool_records(mode=mode))
        else:
            schemas = executor.get_tool_schemas(mode=mode)
            records = []
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
                        "schema": schema,
                        "description": str(function.get("description", "") or getattr(tool, "description", "") or "").strip(),
                        "required": list(parameters.get("required", [])) if isinstance(parameters, dict) else [],
                        "properties": list(properties.keys()) if isinstance(properties, dict) else [],
                        "property_schemas": dict(properties) if isinstance(properties, dict) else {},
                        "metadata": self._tool_metadata(tool),
                        "supported_modes": [],
                    }
                )

        normalized_records: List[Dict[str, Any]] = []
        for record in records:
            tool = record.get("tool")
            if tool is None:
                continue

            metadata = dict(record.get("metadata", {}) or {})
            aliases = [
                str(alias).strip()
                for alias in (metadata.get("aliases", []) or [])
                if str(alias).strip()
            ]
            tags = [
                str(tag).strip()
                for tag in (metadata.get("tags", []) or [])
                if str(tag).strip()
            ]
            property_schemas = dict(record.get("property_schemas", {}) or {})
            normalized_records.append(
                {
                    "name": str(record.get("name", "") or "").strip(),
                    "tool": tool,
                    "kind": self._classify_tool_kind(tool),
                    "description": str(record.get("description", "") or "").strip(),
                    "schema": record.get("schema"),
                    "required": list(record.get("required", []) or []),
                    "properties": list(record.get("properties", []) or []),
                    "property_schemas": property_schemas,
                    "aliases": aliases,
                    "search_hint": str(metadata.get("search_hint", "") or "").strip(),
                    "category": str(metadata.get("category", "general") or "general").strip() or "general",
                    "tags": tags,
                    "read_only": bool(metadata.get("read_only", False)),
                    "concurrency_safe": bool(metadata.get("concurrency_safe", False)),
                    "destructive": bool(metadata.get("destructive", False)),
                    "should_defer": bool(metadata.get("should_defer", False)),
                    "always_load": bool(metadata.get("always_load", False)),
                    "supported_modes": [
                        str(item).strip()
                        for item in (record.get("supported_modes", []) or [])
                        if str(item).strip()
                    ],
                }
            )

        normalized_records.sort(key=lambda item: (item["category"], item["kind"], item["name"].lower()))
        return normalized_records

    def _iter_searchable_chunks(self, record: Dict[str, Any]) -> Iterable[str]:
        yield str(record.get("name", "") or "")
        yield str(record.get("kind", "") or "")
        yield str(record.get("description", "") or "")
        yield str(record.get("search_hint", "") or "")
        yield str(record.get("category", "") or "")
        for item in record.get("aliases", []) or []:
            yield str(item or "")
        for item in record.get("tags", []) or []:
            yield str(item or "")
        for item in record.get("required", []) or []:
            yield str(item or "")
        for item in record.get("properties", []) or []:
            yield str(item or "")
        for prop_schema in (record.get("property_schemas", {}) or {}).values():
            if isinstance(prop_schema, dict):
                yield str(prop_schema.get("description", "") or "")

    def _score_record(self, record: Dict[str, Any], query: str) -> int:
        normalized_query = str(query or "").strip().lower()
        if not normalized_query:
            return 0

        name = str(record.get("name", "") or "").strip().lower()
        aliases = [str(item).strip().lower() for item in (record.get("aliases", []) or []) if str(item).strip()]
        description = str(record.get("description", "") or "").strip().lower()
        search_hint = str(record.get("search_hint", "") or "").strip().lower()
        category = str(record.get("category", "") or "").strip().lower()
        tags = {str(tag).strip().lower() for tag in (record.get("tags", []) or []) if str(tag).strip()}

        haystack_tokens = set()
        for chunk in self._iter_searchable_chunks(record):
            haystack_tokens |= _extract_tokens(chunk)

        score = 0
        if name == normalized_query:
            score += 220
        elif name.startswith(normalized_query):
            score += 140
        elif normalized_query in name:
            score += 90

        for alias in aliases:
            if alias == normalized_query:
                score += 190
            elif alias.startswith(normalized_query):
                score += 110
            elif normalized_query in alias:
                score += 70

        query_tokens = _extract_tokens(normalized_query)
        overlap = haystack_tokens & query_tokens
        score += len(overlap) * 18

        if query_tokens and query_tokens.issubset(haystack_tokens):
            score += 34

        for token in query_tokens:
            if token in name:
                score += 18
            if token in aliases:
                score += 14
            if token in search_hint:
                score += 16
            if token in description:
                score += 10
            if token == category:
                score += 14
            if token in tags:
                score += 12

        return score

    def _mode_adjustment(self, record: Dict[str, Any], mode: str, query: str, *, strong: bool = False) -> float:
        profile = get_mode_tool_discovery_profile(mode)
        category = str(record.get("category", "") or "").strip().lower()
        name = str(record.get("name", "") or "").strip()
        query_tokens = _extract_tokens(query)
        domain_tokens = {token.lower() for token in profile.get("domain_tokens", ())}
        focus_categories = {item.lower() for item in profile.get("focus_categories", ())}
        deemphasize_categories = {item.lower() for item in profile.get("deemphasize_categories", ())}
        boost_tools = set(profile.get("boost_tools", ()))
        domain_overlap = bool(query_tokens & domain_tokens)

        adjustment = 0.0
        if category and category in focus_categories:
            adjustment += 6.0 if not strong else 10.0
        if name in boost_tools:
            adjustment += 7.0 if not strong else 12.0
        if category and category in deemphasize_categories:
            adjustment -= 4.0 if not strong else 7.0

        if domain_overlap:
            if category and category in focus_categories:
                adjustment += 5.0 if not strong else 9.0
            if name in boost_tools:
                adjustment += 6.0 if not strong else 10.0

        return adjustment

    def _mode_adjusted_score(self, record: Dict[str, Any], query: str, mode: str, *, strong: bool = False) -> float:
        return float(self._score_record(record, query)) + self._mode_adjustment(record, mode, query, strong=strong)

    def _query_intent(self, query: str) -> Dict[str, bool]:
        tokens = _extract_tokens(query)
        return {
            "read_heavy": bool(tokens & _READ_INTENT_TOKENS),
            "write_heavy": bool(tokens & _WRITE_INTENT_TOKENS),
        }

    def _reason_fragments(self, record: Dict[str, Any], query: str) -> List[str]:
        query_text = str(query or "").strip().lower()
        query_tokens = _extract_tokens(query_text)
        reasons: List[str] = []

        name = str(record.get("name", "") or "").strip().lower()
        aliases = [str(item).strip().lower() for item in (record.get("aliases", []) or []) if str(item).strip()]
        search_hint = str(record.get("search_hint", "") or "").strip().lower()
        tags = {str(tag).strip().lower() for tag in (record.get("tags", []) or []) if str(tag).strip()}
        properties = {str(item).strip().lower() for item in (record.get("properties", []) or []) if str(item).strip()}

        if query_text == name:
            reasons.append("exact tool name match")
        elif query_text in aliases:
            reasons.append("exact alias match")

        overlapping_tags = sorted(query_tokens & tags)
        if overlapping_tags:
            reasons.append(f"tags match: {', '.join(overlapping_tags[:3])}")

        if query_tokens and query_tokens & properties:
            matched = sorted(query_tokens & properties)
            reasons.append(f"parameter match: {', '.join(matched[:3])}")

        hint_tokens = query_tokens & _extract_tokens(search_hint)
        if hint_tokens:
            reasons.append(f"capability hint: {', '.join(sorted(hint_tokens)[:3])}")

        intent = self._query_intent(query)
        if intent["read_heavy"] and record.get("read_only"):
            reasons.append("read-only and safe for inspection/search work")
        if intent["write_heavy"] and not record.get("read_only"):
            reasons.append("supports editing or state-changing work")
        if record.get("destructive"):
            reasons.append("destructive action available")

        if not reasons:
            reasons.append("broad semantic match against tool description")

        return reasons[:3]

    def _trait_labels(self, record: Dict[str, Any]) -> List[str]:
        labels: List[str] = []
        if record.get("read_only"):
            labels.append("read-only")
        else:
            labels.append("read-write")
        if record.get("concurrency_safe"):
            labels.append("parallel-safe")
        if record.get("destructive"):
            labels.append("destructive")
        if record.get("should_defer"):
            labels.append("deferred")
        if record.get("always_load"):
            labels.append("always-load")
        return labels

    def _format_record_line(self, record: Dict[str, Any]) -> str:
        description = _clip(record.get("description", ""), 140)
        properties = record.get("properties", []) or []
        prop_preview = ", ".join(str(item) for item in properties[:4]) if properties else "(no params)"
        if len(properties) > 4:
            prop_preview = f"{prop_preview}, +{len(properties) - 4} more"
        aliases = record.get("aliases", []) or []
        alias_text = ", ".join(str(item) for item in aliases[:3]) if aliases else "(none)"
        if len(aliases) > 3:
            alias_text = f"{alias_text}, +{len(aliases) - 3} more"
        traits = ", ".join(self._trait_labels(record))
        return (
            f"- {record['name']} [{record['kind']} | {record['category']}]\n"
            f"  description: {description}\n"
            f"  traits: {traits}\n"
            f"  aliases: {alias_text}\n"
            f"  params: {prop_preview}"
        )

    def _render_list(self, mode: str, records: List[Dict[str, Any]], max_results: int) -> ToolResult:
        visible = records[:max_results]
        category_counts: Dict[str, int] = {}
        for record in records:
            category = str(record.get("category", "general") or "general")
            category_counts[category] = category_counts.get(category, 0) + 1

        lines = [
            f"Visible tools for mode '{mode}' ({get_mode_display_name(mode)}): {len(records)} total",
            f"Categories: {', '.join(f'{category}={count}' for category, count in sorted(category_counts.items())) or '(none)'}",
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
                "categories": category_counts,
                "items": [
                    {
                        "name": record["name"],
                        "kind": record["kind"],
                        "category": record["category"],
                        "aliases": list(record["aliases"]),
                        "traits": self._trait_labels(record),
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

        scored = [(self._mode_adjusted_score(record, query, mode, strong=False), record) for record in records]
        matches = [record for score, record in scored if score > 0]
        matches.sort(key=lambda item: (-self._mode_adjusted_score(item, query, mode, strong=False), item["name"].lower()))
        visible = matches[:max_results]

        lines = [f"Tool search for '{query}' in mode '{mode}': {len(matches)} matches"]
        if not visible:
            lines.append("- No matching tools found. Try broader keywords, `operation=\"recommend\"`, or `operation=\"list\"`.")
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
                        "category": record["category"],
                        "supported_modes": list(record.get("supported_modes", []) or []),
                        "aliases": list(record["aliases"]),
                        "traits": self._trait_labels(record),
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

        record = next(
            (
                item
                for item in records
                if wanted == str(item["name"]).lower()
                or wanted in {alias.lower() for alias in item.get("aliases", []) or []}
            ),
            None,
        )
        if record is None:
            return ToolResult.fail(
                f"Tool '{tool_name}' is not visible in mode '{mode}'. Use operation='search' or operation='list' to inspect the active tool surface."
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
            f"Category: {record['category']}",
            f"Supported modes: {', '.join(record.get('supported_modes', []) or []) if record.get('supported_modes') else '(dynamic or runtime-managed)'}",
            f"Aliases: {', '.join(record.get('aliases', []) or []) if record.get('aliases') else '(none)'}",
            f"Search hint: {record.get('search_hint') or '(none)'}",
            f"Tags: {', '.join(record.get('tags', []) or []) if record.get('tags') else '(none)'}",
            f"Traits: {', '.join(self._trait_labels(record))}",
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
            "category": record["category"],
            "supported_modes": list(record.get("supported_modes", []) or []),
            "aliases": list(record.get("aliases", []) or []),
            "search_hint": record.get("search_hint", ""),
            "tags": list(record.get("tags", []) or []),
            "traits": self._trait_labels(record),
            "description": record["description"],
            "required": sorted(required),
            "properties": properties,
        }
        if include_schema:
            data["schema"] = schema

        return ToolResult.ok("\n".join(lines), data=data)

    def _render_recommend(self, mode: str, records: List[Dict[str, Any]], query: str, max_results: int) -> ToolResult:
        if not str(query or "").strip():
            return ToolResult.fail("query is required for operation='recommend'")

        intent = self._query_intent(query)
        scored: List[tuple[float, Dict[str, Any]]] = []
        for record in records:
            base_score = self._mode_adjusted_score(record, query, mode, strong=True)
            if base_score <= 0:
                continue

            adjusted = base_score
            if intent["read_heavy"] and record.get("read_only"):
                adjusted += 10
            if intent["read_heavy"] and not intent["write_heavy"] and record.get("destructive"):
                adjusted -= 18
            if intent["write_heavy"] and not record.get("read_only"):
                adjusted += 10
            if intent["write_heavy"] and record.get("destructive"):
                adjusted += 3
            if not intent["write_heavy"] and not record.get("read_only"):
                adjusted -= 4
            scored.append((adjusted, record))

        scored.sort(key=lambda item: (-item[0], item[1]["name"].lower()))
        visible = [record for _, record in scored[:max_results]]

        lines = [f"Tool recommendations for '{query}' in mode '{mode}': {len(scored)} candidates"]
        if not visible:
            lines.append("- No strong recommendations found. Try `operation=\"search\"` with broader keywords or inspect the full catalog.")
        else:
            lines.append("")
            for record in visible:
                reasons = "; ".join(self._reason_fragments(record, query))
                lines.append(
                    f"- {record['name']} [{record['kind']} | {record['category']}]\n"
                    f"  why: {reasons}\n"
                    f"  traits: {', '.join(self._trait_labels(record))}\n"
                    f"  params: {', '.join(record.get('properties', [])[:5]) or '(no params)'}"
                )

        return ToolResult.ok(
            "\n".join(lines),
            data={
                "mode": mode,
                "query": query,
                "count": len(scored),
                "items": [
                    {
                        "name": record["name"],
                        "kind": record["kind"],
                        "category": record["category"],
                        "supported_modes": list(record.get("supported_modes", []) or []),
                        "aliases": list(record["aliases"]),
                        "traits": self._trait_labels(record),
                        "reasons": self._reason_fragments(record, query),
                        "description": record["description"],
                        "required": list(record["required"]),
                        "properties": list(record["properties"]),
                    }
                    for record in visible
                ],
            },
        )

    def _render_groups(self, mode: str, records: List[Dict[str, Any]]) -> ToolResult:
        by_category: Dict[str, List[str]] = {}
        by_kind: Dict[str, List[str]] = {}

        for record in records:
            by_category.setdefault(str(record.get("category", "general") or "general"), []).append(record["name"])
            by_kind.setdefault(str(record.get("kind", "built-in") or "built-in"), []).append(record["name"])

        lines = [f"Tool groups for mode '{mode}' ({get_mode_display_name(mode)})"]
        if not records:
            lines.append("- No tools are currently visible.")
        else:
            lines.append("")
            lines.append("By category:")
            for category, items in sorted(by_category.items()):
                lines.append(f"- {category}: {len(items)} tool(s) -> {', '.join(items[:8])}{' ...' if len(items) > 8 else ''}")
            lines.append("")
            lines.append("By kind:")
            for kind, items in sorted(by_kind.items()):
                lines.append(f"- {kind}: {len(items)} tool(s) -> {', '.join(items[:8])}{' ...' if len(items) > 8 else ''}")

        return ToolResult.ok(
            "\n".join(lines),
            data={
                "mode": mode,
                "count": len(records),
                "by_category": {key: list(value) for key, value in sorted(by_category.items())},
                "by_kind": {key: list(value) for key, value in sorted(by_kind.items())},
            },
        )

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
        if operation == "recommend":
            return self._render_recommend(mode, records, kwargs.get("query", ""), max_results)
        if operation == "groups":
            return self._render_groups(mode, records)
        return ToolResult.fail(f"Unknown operation: {operation}")
