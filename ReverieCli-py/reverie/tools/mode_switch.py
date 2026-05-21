"""
Mode switch tool.

Lets the active agent inspect available modes, get a recommendation, or move
between supported non-desktop-control modes when the task would benefit from a
different workflow or tool surface.
"""

from __future__ import annotations

from typing import Any
import re

from .base import BaseTool, ToolResult
from ..modes import (
    get_mode_description,
    get_mode_display_name,
    get_mode_tool_discovery_profile,
    list_modes,
    normalize_mode,
)


_TOKEN_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]*")


def _extract_tokens(value: Any) -> set[str]:
    return {
        str(match.group(0) or "").strip("._-").lower()
        for match in _TOKEN_RE.finditer(str(value or ""))
        if str(match.group(0) or "").strip("._-")
    }


class ModeSwitchTool(BaseTool):
    """Inspect or switch the current Reverie mode without leaving the session."""

    aliases = ("change_mode", "set_mode", "enter_mode", "mode_catalog")
    search_hint = "list modes recommend the best mode and switch into it"
    tool_category = "coordination"
    tool_tags = ("mode", "switch", "workflow", "specialist", "discover")
    name = "switch_mode"
    description = (
        "List available modes, recommend the best mode for a task, or switch Reverie into a different task mode "
        "when another workflow is a better fit. Available targets exclude Computer Controller mode."
    )
    parameters = {
        "type": "object",
        "properties": {
            "operation": {
                "type": "string",
                "enum": ["switch", "list", "recommend"],
                "description": "Whether to switch modes, list available modes, or recommend the best mode for a task description.",
            },
            "mode": {
                "type": "string",
                "enum": list_modes(include_computer=False, switchable_only=True),
                "description": "Target mode to activate when operation='switch'.",
            },
            "reason": {
                "type": "string",
                "description": "Short reason for the mode transition.",
            },
            "query": {
                "type": "string",
                "description": "Short task description used when operation='recommend'.",
            },
        },
        "required": [],
    }

    def execute(
        self,
        operation: str = "",
        mode: str = "",
        reason: str = "",
        query: str = "",
    ) -> ToolResult:
        current_mode = normalize_mode(getattr(self.context.get("agent"), "mode", "reverie"))
        normalized_operation = str(operation or "").strip().lower()
        if not normalized_operation:
            if str(query or "").strip():
                normalized_operation = "recommend"
            elif str(mode or "").strip():
                normalized_operation = "switch"
            else:
                normalized_operation = "list"

        if normalized_operation == "list":
            return self._list_modes(current_mode)
        if normalized_operation == "recommend":
            return self._recommend_mode(current_mode, query)
        if normalized_operation != "switch":
            return ToolResult.fail("Unsupported operation. Use one of: switch, list, recommend.")
        if not str(mode or "").strip():
            return self._list_modes(current_mode)
        return self._switch_mode(current_mode, mode, reason)

    def _visible_tool_names_for_mode(self, mode: str) -> list[str]:
        agent = self.context.get("agent")
        executor = getattr(agent, "tool_executor", None) if agent is not None else None
        if executor is None or not callable(getattr(executor, "get_tool_schemas", None)):
            return []

        names: list[str] = []
        try:
            schemas = executor.get_tool_schemas(mode=mode)
        except Exception:
            return []

        for schema in schemas or []:
            if not isinstance(schema, dict):
                continue
            function = schema.get("function", {})
            if not isinstance(function, dict):
                continue
            name = str(function.get("name", "") or "").strip()
            if name and name not in names:
                names.append(name)
        return names

    def _primary_tool_names_for_mode(self, mode: str, *, limit: int = 10) -> list[str]:
        visible = self._visible_tool_names_for_mode(mode)
        if not visible:
            return []

        visible_set = set(visible)
        profile = get_mode_tool_discovery_profile(mode)
        preferred: list[str] = []
        for name in profile.get("boost_tools", ()):
            if name in visible_set and name not in preferred:
                preferred.append(name)
        for name in visible:
            if name == "switch_mode" or name in preferred:
                continue
            preferred.append(name)
        return preferred[: max(1, limit)]

    def _list_modes(self, current_mode: str) -> ToolResult:
        items: list[dict[str, Any]] = []
        lines = [f"Available modes (current: {current_mode})"]
        for mode_name in list_modes(include_computer=False, switchable_only=True):
            primary_tools = self._primary_tool_names_for_mode(mode_name, limit=8)
            primary_tool_text = ", ".join(primary_tools) if primary_tools else "(tool surface will be shown in the next request)"
            lines.append(
                f"- {mode_name}: {get_mode_display_name(mode_name)} :: {get_mode_description(mode_name)}\n"
                f"  primary tools: {primary_tool_text}"
            )
            items.append(
                {
                    "mode": mode_name,
                    "display_name": get_mode_display_name(mode_name),
                    "description": get_mode_description(mode_name),
                    "current": "true" if mode_name == current_mode else "false",
                    "primary_tools": primary_tools,
                }
            )
        return ToolResult.ok(
            "\n".join(lines),
            data={
                "current_mode": current_mode,
                "items": items,
            },
        )

    def _recommend_mode(self, current_mode: str, query: str) -> ToolResult:
        if not str(query or "").strip():
            return ToolResult.fail("query is required for operation='recommend'")

        query_text = str(query or "").strip()
        query_tokens = _extract_tokens(query_text)
        scored: list[tuple[int, str, list[str]]] = []

        for mode_name in list_modes(include_computer=False, switchable_only=True):
            description = get_mode_description(mode_name)
            display_name = get_mode_display_name(mode_name)
            mode_tokens = _extract_tokens(f"{mode_name} {display_name} {description}")
            profile = get_mode_tool_discovery_profile(mode_name)
            reasons: list[str] = []
            score = 0

            domain_hits = sorted(query_tokens & set(profile.get("domain_tokens", ())))
            if domain_hits:
                score += len(domain_hits) * 4
                reasons.append(f"domain tokens: {', '.join(domain_hits[:5])}")

            description_hits = sorted(query_tokens & mode_tokens)
            if description_hits:
                score += len(description_hits) * 2
                reasons.append(f"description overlap: {', '.join(description_hits[:5])}")

            focus_hits = sorted(query_tokens & set(profile.get("focus_categories", ())))
            if focus_hits:
                score += len(focus_hits) * 3
                reasons.append(f"focus fit: {', '.join(focus_hits[:5])}")

            lowered_query = query_text.lower()
            if mode_name in lowered_query or display_name.lower() in lowered_query:
                score += 8
                reasons.append("explicit mode mention")

            if not reasons and mode_name == "reverie":
                score += 1
                reasons.append("safe general fallback")

            scored.append((score, mode_name, reasons))

        scored.sort(key=lambda item: (-item[0], item[1]))
        best_score, recommended_mode, best_reasons = scored[0]
        top_items = [
            {
                "mode": mode_name,
                "display_name": get_mode_display_name(mode_name),
                "description": get_mode_description(mode_name),
                "score": score,
                "reasons": reasons,
                "primary_tools": self._primary_tool_names_for_mode(mode_name, limit=8),
            }
            for score, mode_name, reasons in scored[:3]
        ]

        if best_score <= 0:
            recommended_mode = "reverie"
            best_reasons = ["no strong specialist signal; general coding mode is the safest default"]

        return ToolResult.ok(
            "\n".join(
                [
                    f"Recommended mode for '{query_text}': {recommended_mode}",
                    f"Current mode: {current_mode}",
                    f"Why: {'; '.join(best_reasons)}",
                    "",
                    "Top candidates:",
                    *[
                        f"- {item['mode']} :: {item['description']} (score={item['score']}; primary tools={', '.join(item['primary_tools']) or 'n/a'})"
                        for item in top_items
                    ],
                ]
            ),
            data={
                "current_mode": current_mode,
                "query": query_text,
                "recommended_mode": recommended_mode,
                "candidates": top_items,
            },
        )

    def _switch_mode(self, current_mode: str, mode: str, reason: str) -> ToolResult:
        normalized_mode = normalize_mode(mode)
        if normalized_mode not in list_modes(include_computer=False, switchable_only=True):
            return ToolResult.fail(
                "Unsupported mode target. Available modes: "
                + ", ".join(list_modes(include_computer=False, switchable_only=True))
            )

        agent = self.context.get("agent")
        config_manager = self.context.get("config_manager")
        session_manager = self.context.get("session_manager")

        if not agent:
            return ToolResult.fail("Agent context is unavailable; cannot switch mode")

        if current_mode == normalized_mode:
            visible_tools = self._visible_tool_names_for_mode(normalized_mode)
            primary_tools = self._primary_tool_names_for_mode(normalized_mode, limit=12)
            return ToolResult.ok(
                f"Mode already set to {normalized_mode}.\n"
                f"Primary tools: {', '.join(primary_tools) if primary_tools else 'unavailable until the next request'}",
                data={
                    "mode": normalized_mode,
                    "previous_mode": current_mode,
                    "visible_tools": visible_tools,
                    "primary_tools": primary_tools,
                    "tool_surface_changed": False,
                },
            )

        agent.update_mode(normalized_mode)

        if config_manager:
            config = config_manager.load()
            config.mode = normalized_mode
            config_manager.save(config)

        if session_manager and session_manager.get_current_session():
            session = session_manager.get_current_session()
            metadata = dict(getattr(session, "metadata", {}) or {})
            metadata["mode"] = normalized_mode
            session.metadata = metadata
            session_manager.save_session(session)

        reason_text = f" Reason: {reason.strip()}" if str(reason or "").strip() else ""
        visible_tools = self._visible_tool_names_for_mode(normalized_mode)
        primary_tools = self._primary_tool_names_for_mode(normalized_mode, limit=12)
        tool_text = ", ".join(primary_tools) if primary_tools else "the target mode's schemas will be exposed on the next model request"
        return ToolResult.ok(
            f"Switched mode from {current_mode} to {normalized_mode}.{reason_text}\n"
            f"New workflow: {get_mode_description(normalized_mode)}\n"
            f"Primary tools now available: {tool_text}",
            data={
                "mode": normalized_mode,
                "previous_mode": current_mode,
                "reason": str(reason or "").strip(),
                "visible_tools": visible_tools,
                "primary_tools": primary_tools,
                "tool_surface_changed": True,
            },
        )

    def get_execution_message(
        self,
        operation: str = "",
        mode: str = "",
        reason: str = "",
        query: str = "",
    ) -> str:
        normalized_operation = str(operation or "").strip().lower()
        if not normalized_operation:
            if str(query or "").strip():
                normalized_operation = "recommend"
            elif str(mode or "").strip():
                normalized_operation = "switch"
            else:
                normalized_operation = "list"
        if normalized_operation == "list":
            return "Listing available modes"
        if normalized_operation == "recommend":
            return f"Recommending a mode for: {query or 'current task'}"
        normalized_mode = normalize_mode(mode)
        if reason:
            return f"Switching mode to {normalized_mode} ({reason})"
        return f"Switching mode to {normalized_mode}"
