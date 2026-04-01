"""Agent-callable skill discovery and inspection for Reverie."""

from __future__ import annotations

from typing import Any, Dict, List
import re

from ..skills_manager import SkillRecord
from .base import BaseTool, ToolResult


_TOKEN_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]*")


def _extract_tokens(value: Any) -> set[str]:
    """Extract normalized tokens from free text."""
    return {
        str(match.group(0) or "").strip("._-").lower()
        for match in _TOKEN_RE.finditer(str(value or ""))
        if str(match.group(0) or "").strip("._-")
    }


def _clip(value: Any, limit: int = 240) -> str:
    """Clip text to a stable preview length."""
    text = re.sub(r"\s+", " ", str(value or "").strip())
    if len(text) <= limit:
        return text
    return f"{text[: max(1, limit - 3)].rstrip()}..."


class SkillLookupTool(BaseTool):
    """Search and inspect discovered Codex-style skills."""

    name = "skill_lookup"

    description = """Search or inspect the SKILL.md files Reverie has discovered.

Use this tool when a skill seems relevant but you need to inspect its exact
instructions, summary, or file path before acting.
"""

    parameters = {
        "type": "object",
        "properties": {
            "operation": {
                "type": "string",
                "enum": ["list", "search", "inspect"],
                "description": "Whether to list skills, search by keywords, or inspect one skill body",
            },
            "query": {
                "type": "string",
                "description": "For search: keywords to match against skill names, descriptions, and body text",
            },
            "skill_name": {
                "type": "string",
                "description": "For inspect: exact skill name, directory name, or SKILL.md path",
            },
            "max_results": {
                "type": "integer",
                "description": "Maximum items to return for list/search (default: 8, max: 20)",
                "default": 8,
            },
            "max_body_chars": {
                "type": "integer",
                "description": "For inspect: maximum number of skill-body characters to include (default: 6000)",
                "default": 6000,
            },
            "force_refresh": {
                "type": "boolean",
                "description": "Rescan skill roots before serving the request",
                "default": False,
            },
        },
        "required": ["operation"],
    }

    def _skills_manager(self):
        manager = self.context.get("skills_manager")
        if manager is None:
            raise RuntimeError("Skills manager is not available in the current context.")
        return manager

    def _score_record(self, record: SkillRecord, query: str) -> int:
        normalized_query = str(query or "").strip().lower()
        if not normalized_query:
            return 0

        name = str(record.name or "").strip().lower()
        description = str(record.description or "").strip().lower()
        body = str(record.body or "").strip().lower()
        query_tokens = _extract_tokens(normalized_query)
        skill_tokens = set(record.match_tokens) | _extract_tokens(body)

        score = 0
        if name == normalized_query:
            score += 200
        elif name.startswith(normalized_query):
            score += 120
        elif normalized_query in name:
            score += 80

        overlap = query_tokens & skill_tokens
        score += len(overlap) * 18
        if query_tokens and query_tokens.issubset(skill_tokens):
            score += 24

        for token in query_tokens:
            if token in name:
                score += 16
            if token in description:
                score += 10
            if token in body:
                score += 4

        return score

    def _list_rows(self, records: List[SkillRecord], max_results: int) -> List[Dict[str, Any]]:
        visible = records[:max_results]
        return [
            {
                "name": record.name,
                "description": record.summary,
                "path": record.display_path,
                "scope": record.scope_label,
                "root": record.root_label,
            }
            for record in visible
        ]

    def _render_rows(self, records: List[SkillRecord]) -> List[str]:
        return [
            (
                f"- {record.name} [{record.scope_label} / {record.root_label}]\n"
                f"  description: {record.summary}\n"
                f"  path: {record.display_path}"
            )
            for record in records
        ]

    def execute(self, **kwargs) -> ToolResult:
        operation = str(kwargs.get("operation", "") or "").strip().lower()
        force_refresh = bool(kwargs.get("force_refresh", False))
        max_results = kwargs.get("max_results", 8)
        max_body_chars = kwargs.get("max_body_chars", 6000)

        try:
            max_results = int(max_results)
            max_body_chars = int(max_body_chars)
        except (TypeError, ValueError):
            return ToolResult.fail("max_results and max_body_chars must be integers")

        max_results = max(1, min(max_results, 20))
        max_body_chars = max(200, min(max_body_chars, 20_000))

        manager = self._skills_manager()
        snapshot = manager.get_snapshot(force_refresh=force_refresh)
        records = list(snapshot.records)

        if operation == "list":
            visible = records[:max_results]
            lines = [f"Discovered skills: {len(records)} valid, {len(snapshot.errors)} invalid"]
            if not visible:
                lines.append("- No valid SKILL.md files were found.")
            else:
                lines.append("")
                lines.extend(self._render_rows(visible))
                if len(records) > len(visible):
                    lines.append("")
                    lines.append(f"... {len(records) - len(visible)} additional skills omitted.")
            return ToolResult.ok(
                "\n".join(lines),
                data={
                    "count": len(records),
                    "invalid_count": len(snapshot.errors),
                    "items": self._list_rows(records, max_results),
                },
            )

        if operation == "search":
            query = str(kwargs.get("query", "") or "").strip()
            if not query:
                return ToolResult.fail("query is required for operation='search'")

            scored = [(self._score_record(record, query), record) for record in records]
            matches = [record for score, record in scored if score > 0]
            matches.sort(key=lambda item: (-self._score_record(item, query), item.name.lower()))
            visible = matches[:max_results]

            lines = [f"Skill search for '{query}': {len(matches)} matches"]
            if not visible:
                lines.append("- No matching skills found.")
            else:
                lines.append("")
                lines.extend(self._render_rows(visible))
                if len(matches) > len(visible):
                    lines.append("")
                    lines.append(f"... {len(matches) - len(visible)} additional matches omitted.")
            return ToolResult.ok(
                "\n".join(lines),
                data={
                    "query": query,
                    "count": len(matches),
                    "items": self._list_rows(matches, max_results),
                },
            )

        if operation == "inspect":
            skill_name = str(kwargs.get("skill_name", "") or "").strip()
            if not skill_name:
                return ToolResult.fail("skill_name is required for operation='inspect'")

            record = manager.get_record(skill_name, force_refresh=False)
            if record is None:
                return ToolResult.fail(
                    f"Skill '{skill_name}' was not found. Use operation='list' or operation='search' first."
                )

            body = str(record.body or "").strip() or str(record.description or "").strip()
            body_preview = body
            was_truncated = False
            if len(body_preview) > max_body_chars:
                body_preview = f"{body_preview[: max_body_chars - 3].rstrip()}..."
                was_truncated = True

            metadata_keys = sorted(str(key) for key in (record.metadata or {}).keys())
            lines = [
                f"Skill: {record.name}",
                f"Scope: {record.scope_label} / {record.root_label}",
                f"Path: {record.display_path}",
                f"Description: {_clip(record.description, 320)}",
                f"Metadata keys: {', '.join(metadata_keys) if metadata_keys else '(none)'}",
                "",
                "Skill body:",
                body_preview or "(empty skill body)",
            ]
            if was_truncated:
                lines.append("")
                lines.append(f"[preview truncated to {max_body_chars} characters]")

            return ToolResult.ok(
                "\n".join(lines),
                data={
                    "name": record.name,
                    "description": record.description,
                    "path": record.display_path,
                    "scope": record.scope_label,
                    "root": record.root_label,
                    "metadata": dict(record.metadata or {}),
                    "body": body_preview,
                    "truncated": was_truncated,
                },
            )

        return ToolResult.fail(f"Unknown operation: {operation}")
