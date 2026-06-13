"""Facade for Reverie's Context Engine + Memory OS."""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any, Dict, Iterable, Optional

from .assembler import ContextAssembler
from .consolidator import MemoryConsolidator
from .event_store import EventStore
from .evolution import EvolutionFeedbackPipeline
from .models import ContextPackage, EventRecord
from .retriever import MemoryRetriever
from .store import MemoryStore


def workspace_id_for_path(path: Any) -> str:
    raw = str(path or "").strip()
    if not raw:
        return ""
    normalized = raw.replace("\\", "/").rstrip("/").lower()
    return hashlib.sha1(normalized.encode("utf-8", errors="replace")).hexdigest()[:16]


class MemoryOS:
    """Single entry point for events, memories, retrieval, assembly, and evolution."""

    def __init__(self, project_data_dir: Path, *, project_root: Optional[Path] = None):
        self.project_data_dir = Path(project_data_dir)
        self.project_root = Path(project_root).resolve() if project_root else None
        self.workspace_id = workspace_id_for_path(self.project_root or self.project_data_dir)
        self.event_store = EventStore(self.project_data_dir, workspace_id=self.workspace_id)
        self.memory_store = MemoryStore(self.project_data_dir)
        self.retriever = MemoryRetriever(self.memory_store)
        self.consolidator = MemoryConsolidator(self.event_store, self.memory_store)
        self.assembler = ContextAssembler(self.retriever)
        self.evolution = EvolutionFeedbackPipeline(
            self.project_data_dir,
            self.event_store,
            self.memory_store,
        )

    def record_event(
        self,
        event_type: str,
        payload: Optional[Dict[str, Any]] = None,
        *,
        actor: str = "",
        session_id: str = "",
        tags: Optional[Iterable[Any]] = None,
        consolidate: bool = True,
    ) -> EventRecord:
        event = self.event_store.append(
            event_type,
            payload or {},
            actor=actor,
            session_id=session_id,
            tags=tags,
        )
        if consolidate:
            try:
                self.consolidator.extract_event(event)
            except Exception:
                pass
        return event

    def assemble_context(
        self,
        query: str,
        *,
        code_retriever: Any = None,
        session_id: str = "",
        recent_messages: Optional[list[dict[str, Any]]] = None,
        max_tokens: int = 6000,
    ) -> ContextPackage:
        return self.assembler.assemble(
            query,
            code_retriever=code_retriever,
            session_id=session_id,
            recent_messages=recent_messages,
            max_tokens=max_tokens,
        )
