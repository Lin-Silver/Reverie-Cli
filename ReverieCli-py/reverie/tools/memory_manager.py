"""Memory management tool for corrections, deletion, and consolidation."""

from __future__ import annotations

from typing import Any, Dict, List

from .base import BaseTool, ToolResult
from .memory_retrieval import get_memory_os_from_context


class MemoryManagerTool(BaseTool):
    """Remember, version, inspect, and curate project MemoryItems."""

    name = "memory_manager"
    aliases = ("memory-manager", "manage_memory")
    search_hint = "remember persist list correct delete conflicts status consolidate project memory"
    tool_category = "retrieval"
    tool_tags = ("memory", "manager", "correction", "deletion", "consolidation")
    read_only = False
    concurrency_safe = False

    description = """Manage Reverie's project-isolated persistent MemoryItems.

Use remember for explicit durable instructions, facts, decisions, goals, commitments, preferences, relationships, context, events, learnings, observations, artifacts, or errors. Never store credentials or transient chatter. Corrections create a new version; conflicts are surfaced rather than silently overwritten."""

    parameters = {
        "type": "object",
        "properties": {
            "action": {
                "type": "string",
                "enum": ["remember", "list", "get", "correct", "delete", "consolidate", "conflicts", "status"],
                "description": "Memory management action.",
            },
            "memory_id": {"type": "string", "description": "Target memory id for get/correct/delete.", "default": ""},
            "query": {"type": "string", "description": "Optional search query for list.", "default": ""},
            "content": {"type": "string", "description": "Replacement content for correct.", "default": ""},
            "scope": {"type": "string", "description": "Optional scope filter for list.", "default": ""},
            "memory_type": {"type": "string", "description": "Optional type filter for list.", "default": ""},
            "tags": {"type": "array", "items": {"type": "string"}, "description": "Durable memory tags.", "default": []},
            "confidence": {"type": "number", "description": "Confidence from 0 to 1.", "default": 0.8},
            "provenance": {"type": "string", "description": "Origin such as explicit_statement, inferred_from_event, or verified_artifact.", "default": "explicit_statement"},
            "source": {"type": "string", "description": "Source actor or artifact.", "default": "agent"},
            "topic": {"type": "string", "description": "Stable topic key used for conflict detection and versioning.", "default": ""},
            "supersedes": {"type": "array", "items": {"type": "string"}, "description": "Memory ids explicitly replaced by this version.", "default": []},
            "limit": {"type": "integer", "description": "Maximum list/consolidation count.", "default": 20},
            "hard": {"type": "boolean", "description": "Hard-delete the MemoryItem record instead of marking deleted.", "default": False},
        },
        "required": ["action"],
    }

    def execute(self, **kwargs) -> ToolResult:
        action = str(kwargs.get("action") or "").strip().lower()
        memory_os = get_memory_os_from_context(self.context)
        if action == "remember":
            content = str(kwargs.get("content") or "").strip()
            if not content:
                return ToolResult.fail("content is required for remember")
            remembered = memory_os.remember(
                content,
                memory_type=str(kwargs.get("memory_type") or "fact"),
                scope=str(kwargs.get("scope") or "project"),
                tags=list(kwargs.get("tags") or []),
                confidence=self._float(kwargs.get("confidence"), 0.8),
                provenance=str(kwargs.get("provenance") or "explicit_statement"),
                source=str(kwargs.get("source") or "agent"),
                topic=str(kwargs.get("topic") or ""),
                supersedes=list(kwargs.get("supersedes") or []),
            )
            item = remembered["memory"]
            conflicts = remembered["conflicts"]
            return ToolResult.ok(
                f"Remembered {item.id}; immediately searchable=yes; conflicts={len(conflicts)}.",
                {
                    "memory": item.to_dict(),
                    "conflicts": [conflict.to_dict() for conflict in conflicts],
                    "searchable_immediately": remembered["searchable_immediately"],
                },
            )
        if action == "status":
            status = memory_os.status()
            return ToolResult.ok("Project memory status loaded.", status)
        if action == "conflicts":
            items = memory_os.memory_store.load_items()
            conflicts = [
                {"memory": item.to_dict(), "conflict_ids": list((item.metadata or {}).get("conflict_ids") or [])}
                for item in items
                if (item.metadata or {}).get("conflict_ids")
            ]
            return ToolResult.ok(f"Found {len(conflicts)} unresolved conflict record(s).", {"conflicts": conflicts})
        if action == "consolidate":
            created = memory_os.consolidator.consolidate_recent(limit=self._int(kwargs.get("limit"), 200))
            return ToolResult.ok(
                f"Consolidated recent event store into {len(created)} MemoryItem updates.",
                {"memory_ids": [item.id for item in created]},
            )
        if action == "list":
            return self._list(memory_os, kwargs)
        if action == "get":
            memory_id = str(kwargs.get("memory_id") or "").strip()
            item = memory_os.memory_store.get(memory_id, include_deleted=True)
            if not item:
                return ToolResult.fail(f"MemoryItem not found: {memory_id}")
            return ToolResult.ok(self._format_item(item), {"memory": item.to_dict()})
        if action == "correct":
            memory_id = str(kwargs.get("memory_id") or "").strip()
            content = str(kwargs.get("content") or "").strip()
            if not memory_id or not content:
                return ToolResult.fail("memory_id and content are required for correct")
            item = memory_os.memory_store.correct(memory_id, content, tags=["corrected"])
            if not item:
                return ToolResult.fail(f"MemoryItem not found: {memory_id}")
            memory_os.record_event(
                "memory_corrected",
                {"memory_id": memory_id, "content": content},
                actor="tool",
                tags=["memory", "correction"],
                consolidate=False,
            )
            return ToolResult.ok(f"Corrected MemoryItem {item.id}.", {"memory": item.to_dict()})
        if action == "delete":
            memory_id = str(kwargs.get("memory_id") or "").strip()
            if not memory_id:
                return ToolResult.fail("memory_id is required for delete")
            deleted = memory_os.memory_store.delete(memory_id, hard=self._bool(kwargs.get("hard"), False))
            if not deleted:
                return ToolResult.fail(f"MemoryItem not found: {memory_id}")
            memory_os.record_event(
                "memory_deleted",
                {"memory_id": memory_id, "hard": self._bool(kwargs.get("hard"), False)},
                actor="tool",
                tags=["memory", "delete"],
                consolidate=False,
            )
            return ToolResult.ok(f"Deleted MemoryItem {memory_id}.", {"memory_id": memory_id})
        return ToolResult.fail("Unsupported memory action")

    def _list(self, memory_os, kwargs: Dict[str, Any]) -> ToolResult:
        query = str(kwargs.get("query") or "").strip()
        limit = self._int(kwargs.get("limit"), 20)
        if query:
            hits = memory_os.retriever.search(
                query,
                scope=str(kwargs.get("scope") or ""),
                memory_type=str(kwargs.get("memory_type") or ""),
                limit=limit,
            )
            items = [hit.item for hit in hits]
        else:
            items = memory_os.memory_store.load_items()[:limit]
        if not items:
            return ToolResult.ok("No structured memories found.", {"memories": []})
        lines = ["# Structured Memories"]
        lines.extend(self._format_item(item) for item in items)
        return ToolResult.ok("\n".join(lines), {"memories": [item.to_dict() for item in items]})

    @staticmethod
    def _format_item(item) -> str:
        evidence_ids = ",".join((item.source_event_ids or [])[:4])
        tags = ",".join(item.tags or [])
        suffix: List[str] = []
        if tags:
            suffix.append(f"tags={tags}")
        if evidence_ids:
            suffix.append(f"evidence={evidence_ids}")
        return (
            f"- {item.id} [{item.scope}/{item.memory_type} confidence={item.confidence:.2f} "
            f"version={item.version} provenance={item.provenance} decay={item.decay:.2f} status={item.status}] {item.content}"
            + (f" ({'; '.join(suffix)})" if suffix else "")
        )

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
        return max(1, min(parsed, 500))

    @staticmethod
    def _float(value: Any, default: float) -> float:
        try:
            parsed = float(value)
        except (TypeError, ValueError):
            parsed = default
        return max(0.0, min(parsed, 1.0))
