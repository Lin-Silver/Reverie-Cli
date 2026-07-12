"""Facade for Reverie's Context Engine + Memory OS."""

from __future__ import annotations

import hashlib
import re
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

from ..diagnostics import report_suppressed_exception
from .assembler import ContextAssembler
from .consolidator import MemoryConsolidator
from .event_store import EventStore
from .evolution import EvolutionFeedbackPipeline
from .models import MemoryContextPackage, EventRecord, MemoryItem, coerce_tags, new_id, utc_now
from .retriever import MemoryRetriever, tokenize
from .safety import redact_memory_text
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
                report_suppressed_exception("consolidate memory event")
        return event

    def remember(
        self,
        content: str,
        *,
        memory_type: str = "fact",
        scope: str = "project",
        tags: Optional[Iterable[Any]] = None,
        confidence: float = 0.8,
        provenance: str = "explicit_statement",
        source: str = "agent",
        session_id: str = "",
        topic: str = "",
        supersedes: Optional[Iterable[str]] = None,
    ) -> Dict[str, Any]:
        """Persist one typed memory and make it searchable in the same transaction."""
        safe_content = redact_memory_text(content).strip()
        if not safe_content:
            raise ValueError("Memory content is required.")
        event = self.event_store.append(
            "memory_remembered",
            {
                "content": safe_content,
                "memory_type": memory_type,
                "scope": scope,
                "topic": topic,
            },
            actor=source,
            session_id=session_id,
            tags=coerce_tags(tags),
        )
        item = MemoryItem(
            id=new_id("mem"),
            scope=scope,
            memory_type=memory_type,
            content=safe_content,
            evidence=[{"event_id": event.id, "event_type": event.event_type, "timestamp": event.timestamp}],
            confidence=max(0.0, min(1.0, float(confidence or 0.0))),
            tags=coerce_tags(tags),
            created_at=utc_now(),
            updated_at=utc_now(),
            source_event_ids=[event.id],
            metadata={
                "session_id": session_id,
                "workspace_id": self.workspace_id,
                **({"topic": str(topic).strip().lower()} if str(topic or "").strip() else {}),
            },
            provenance=str(provenance or "explicit_statement"),
            source=str(source or "agent"),
            valid_from=utc_now(),
        )
        conflicts = self.detect_conflicts(item)
        if conflicts:
            item.metadata["conflict_ids"] = [conflict.id for conflict in conflicts]
        superseded_ids = [str(value) for value in (supersedes or []) if str(value or "").strip()]
        stored = self.memory_store.supersede(superseded_ids, item) if superseded_ids else self.memory_store.upsert(item)
        immediate_hits = self.retriever.search(safe_content, limit=3)
        return {
            "memory": stored,
            "conflicts": conflicts,
            "searchable_immediately": any(hit.item.id == stored.id for hit in immediate_hits),
        }

    def detect_conflicts(self, candidate: MemoryItem) -> List[MemoryItem]:
        """Detect likely contradictions without silently overwriting either record."""
        candidate_topic = str((candidate.metadata or {}).get("topic") or "").strip().lower()
        candidate_tokens = set(tokenize(candidate.content))
        candidate_polarity = self._polarity(candidate.content)
        conflicts: List[MemoryItem] = []
        decision_types = {"decision", "project_decision", "instruction", "preference", "commitment", "goal"}
        for existing in self.memory_store.load_items():
            if existing.id == candidate.id or existing.fingerprint() == candidate.fingerprint():
                continue
            if existing.scope != candidate.scope:
                continue
            if existing.memory_type != candidate.memory_type and not {
                existing.memory_type,
                candidate.memory_type,
            }.issubset(decision_types):
                continue
            existing_topic = str((existing.metadata or {}).get("topic") or "").strip().lower()
            explicit_topic_conflict = bool(candidate_topic and existing_topic and candidate_topic == existing_topic)
            existing_tokens = set(tokenize(existing.content))
            overlap = len(candidate_tokens.intersection(existing_tokens)) / max(
                1, min(len(candidate_tokens), len(existing_tokens))
            )
            polarity_conflict = candidate_polarity != 0 and self._polarity(existing.content) == -candidate_polarity
            if explicit_topic_conflict or (overlap >= 0.45 and polarity_conflict):
                conflicts.append(existing)
        return conflicts[:20]

    @staticmethod
    def _polarity(content: str) -> int:
        text = str(content or "").lower()
        negative = bool(re.search(r"\b(no|not|never|avoid|disable|forbid|without|don't|do not)\b|不|勿|禁止|避免", text))
        positive = bool(re.search(r"\b(always|must|use|enable|prefer|required|should)\b|必须|使用|启用|应该|默认", text))
        if negative and not positive:
            return -1
        if positive and not negative:
            return 1
        return 0

    def recall(self, query: str, **filters: Any):
        """Recall ranked memories using the hybrid project-local retriever."""
        return self.retriever.search(query, **filters)

    def answer(self, question: str, *, limit: int = 8, **filters: Any) -> Dict[str, Any]:
        """Return an evidence-grounded extractive answer for the active agent."""
        hits = self.recall(question, limit=limit, **filters)
        if not hits:
            return {"answer": "No project memory supports an answer.", "sources": [], "grounded": False}
        lines = ["Project memory evidence:"]
        sources: List[Dict[str, Any]] = []
        for hit in hits:
            lines.append(f"- {hit.item.content}")
            sources.append(
                {
                    "memory_id": hit.item.id,
                    "type": hit.item.memory_type,
                    "score": hit.score,
                    "confidence": hit.item.confidence,
                    "provenance": hit.item.provenance,
                    "version": hit.item.version,
                    "evidence_event_ids": list(hit.item.source_event_ids or []),
                }
            )
        return {"answer": "\n".join(lines), "sources": sources, "grounded": True}

    def status(self) -> Dict[str, Any]:
        return {
            **self.memory_store.status(),
            "workspace_id": self.workspace_id,
            "project_root": str(self.project_root or ""),
            "project_isolated": True,
            "cross_session": True,
        }

    def assemble_context(
        self,
        query: str,
        *,
        code_retriever: Any = None,
        session_id: str = "",
        recent_messages: Optional[list[dict[str, Any]]] = None,
        max_tokens: int = 6000,
    ) -> MemoryContextPackage:
        return self.assembler.assemble(
            query,
            code_retriever=code_retriever,
            session_id=session_id,
            recent_messages=recent_messages,
            max_tokens=max_tokens,
        )
