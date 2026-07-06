"""Tools for querying Reverie's structured Memory OS."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, Optional

from .base import BaseTool, ToolResult
from ..config import get_project_data_dir
from ..memory import MemoryOS


def get_memory_os_from_context(context: Optional[Dict[str, Any]]) -> MemoryOS:
    ctx = context if isinstance(context, dict) else {}
    existing = ctx.get("memory_os")
    if isinstance(existing, MemoryOS):
        return existing
    project_root = Path(ctx.get("project_root") or Path.cwd())
    project_data_dir = Path(ctx.get("project_data_dir") or get_project_data_dir(project_root))
    memory_os = MemoryOS(project_data_dir, project_root=project_root)
    ctx["memory_os"] = memory_os
    return memory_os


class MemoryRetrievalTool(BaseTool):
    """Query structured project/session/workflow memory with evidence."""

    name = "memory_retrieval"
    aliases = ("memory-retrieval", "query_memory", "memory_search")
    search_hint = "query structured long term memory preferences decisions failures workflows evidence"
    tool_category = "retrieval"
    tool_tags = ("memory", "context", "retrieval", "evidence")
    read_only = True
    concurrency_safe = True

    description = """Recall or answer from Reverie's project-isolated persistent Memory OS.

Use this proactively before making claims about user preferences, project decisions, previous failures, successful workflows, or continuation state. Results are immediately searchable and include provenance, versions, temporal signals, and evidence."""

    parameters = {
        "type": "object",
        "properties": {
            "action": {
                "type": "string",
                "enum": ["recall", "answer"],
                "description": "Recall ranked records or produce an evidence-grounded answer.",
                "default": "recall",
            },
            "query": {"type": "string", "description": "Current request or search query."},
            "scope": {
                "type": "string",
                "enum": ["", "session", "project", "workflow", "procedural"],
                "description": "Optional memory scope filter.",
                "default": "",
            },
            "memory_type": {
                "type": "string",
                "description": "Optional type filter such as preference, project_decision, failure_experience, success_workflow, or user_correction.",
                "default": "",
            },
            "limit": {"type": "integer", "description": "Maximum results.", "default": 8},
            "min_confidence": {"type": "number", "description": "Optional confidence floor from 0 to 1.", "default": 0.0},
            "as_of": {"type": "string", "description": "Optional ISO timestamp for historical recall.", "default": ""},
            "changed_since": {"type": "string", "description": "Optional ISO timestamp for memories changed since a point in time.", "default": ""},
            "explain": {"type": "boolean", "description": "Include ranking reasons and evidence ids.", "default": True},
        },
        "required": ["query"],
    }

    def execute(self, **kwargs) -> ToolResult:
        query = str(kwargs.get("query") or "").strip()
        if not query:
            return ToolResult.fail("query is required")
        limit = self._int(kwargs.get("limit"), 8)
        memory_os = get_memory_os_from_context(self.context)
        filters = {
            "scope": str(kwargs.get("scope") or ""),
            "memory_type": str(kwargs.get("memory_type") or ""),
            "min_confidence": self._float(kwargs.get("min_confidence"), 0.0),
            "as_of": str(kwargs.get("as_of") or ""),
            "changed_since": str(kwargs.get("changed_since") or ""),
        }
        if str(kwargs.get("action") or "recall").strip().lower() == "answer":
            answer = memory_os.answer(query, limit=limit, **filters)
            return ToolResult.ok(answer["answer"], answer)
        hits = memory_os.retriever.search(
            query,
            limit=limit,
            **filters,
        )
        if not hits:
            return ToolResult.ok("No matching structured memories found.", {"memories": []})

        explain = self._bool(kwargs.get("explain"), True)
        lines = ["# Memory Retrieval Results"]
        data = []
        for index, hit in enumerate(hits, start=1):
            item = hit.item
            evidence_ids = ",".join((item.source_event_ids or [])[:4])
            line = (
                f"{index}. {item.id} [{item.scope}/{item.memory_type}] "
                f"score={hit.score:.2f} confidence={item.confidence:.2f} - {item.content}"
            )
            if explain:
                reasons = "; ".join(hit.reasons or [])
                suffix = []
                if reasons:
                    suffix.append(f"reasons: {reasons}")
                if evidence_ids:
                    suffix.append(f"evidence: {evidence_ids}")
                if suffix:
                    line += f"\n   {'; '.join(suffix)}"
            lines.append(line)
            data.append(
                {
                    "id": item.id,
                    "scope": item.scope,
                    "type": item.memory_type,
                    "content": item.content,
                    "confidence": item.confidence,
                    "score": hit.score,
                    "reasons": hit.reasons,
                    "evidence_event_ids": item.source_event_ids,
                    "tags": item.tags,
                    "provenance": item.provenance,
                    "source": item.source,
                    "version": item.version,
                    "supersedes": item.supersedes,
                    "components": hit.components,
                }
            )
        return ToolResult.ok("\n".join(lines), {"memories": data})

    @staticmethod
    def _bool(value: Any, default: bool) -> bool:
        if isinstance(value, bool):
            return value
        if value is None:
            return default
        return str(value).strip().lower() in {"1", "true", "yes", "on"}

    @staticmethod
    def _int(value: Any, default: int) -> int:
        try:
            parsed = int(value)
        except (TypeError, ValueError):
            parsed = default
        return max(1, min(parsed, 50))

    @staticmethod
    def _float(value: Any, default: float) -> float:
        try:
            parsed = float(value)
        except (TypeError, ValueError):
            parsed = default
        return max(0.0, min(parsed, 1.0))
