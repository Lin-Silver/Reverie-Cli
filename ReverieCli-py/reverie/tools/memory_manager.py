"""Memory management tool for corrections, deletion, and consolidation."""

from __future__ import annotations

from typing import Any, Dict, List

from .base import BaseTool, ToolResult
from .memory_retrieval import get_memory_os_from_context


class MemoryManagerTool(BaseTool):
    """Inspect and curate structured MemoryItems."""

    name = "memory_manager"
    aliases = ("memory-manager", "manage_memory")
    search_hint = "list correct delete consolidate structured memory items"
    tool_category = "retrieval"
    tool_tags = ("memory", "manager", "correction", "deletion", "consolidation")
    read_only = False
    concurrency_safe = False

    description = """Manage Reverie's structured MemoryItems.

Supported actions: list, get, correct, delete, consolidate. Corrections and deletions affect structured MemoryItems only; the append-only event store remains as evidence."""

    parameters = {
        "type": "object",
        "properties": {
            "action": {
                "type": "string",
                "enum": ["list", "get", "correct", "delete", "consolidate"],
                "description": "Memory management action.",
            },
            "memory_id": {"type": "string", "description": "Target memory id for get/correct/delete.", "default": ""},
            "query": {"type": "string", "description": "Optional search query for list.", "default": ""},
            "content": {"type": "string", "description": "Replacement content for correct.", "default": ""},
            "scope": {"type": "string", "description": "Optional scope filter for list.", "default": ""},
            "memory_type": {"type": "string", "description": "Optional type filter for list.", "default": ""},
            "limit": {"type": "integer", "description": "Maximum list/consolidation count.", "default": 20},
            "hard": {"type": "boolean", "description": "Hard-delete the MemoryItem record instead of marking deleted.", "default": False},
        },
        "required": ["action"],
    }

    def execute(self, **kwargs) -> ToolResult:
        action = str(kwargs.get("action") or "").strip().lower()
        memory_os = get_memory_os_from_context(self.context)
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
        return ToolResult.fail("action must be one of list, get, correct, delete, consolidate")

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
            f"decay={item.decay:.2f} status={item.status}] {item.content}"
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
