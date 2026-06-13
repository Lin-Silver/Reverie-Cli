"""Deterministic extraction from events into structured MemoryItems."""

from __future__ import annotations

import re
from typing import Any, Dict, Iterable, List

from .event_store import EventStore
from .models import EventRecord, MemoryItem, new_id, utc_now
from .store import MemoryStore


_PREFERENCE_RE = re.compile(
    r"\b(always|never|prefer|preference|default|by default|do not|don't|avoid|must|should)\b",
    re.IGNORECASE,
)
_CORRECTION_RE = re.compile(
    r"\b(actually|correction|correct|wrong|not that|instead|should be|应当|应该|不是|纠正|默认|不要|只)\b",
    re.IGNORECASE,
)
_DECISION_RE = re.compile(r"\b(decided|decision|choose|adopt|keep|决定|采用|保留)\b", re.IGNORECASE)


def _compact_text(value: Any, limit: int = 900) -> str:
    text = " ".join(str(value or "").split())
    if len(text) <= limit:
        return text
    return text[: max(0, limit - 3)].rstrip() + "..."


def _event_evidence(event: EventRecord, note: str = "") -> Dict[str, Any]:
    evidence = {
        "event_id": event.id,
        "event_type": event.event_type,
        "timestamp": event.timestamp,
    }
    if note:
        evidence["note"] = note
    return evidence


class MemoryConsolidator:
    """Extract conservative MemoryItems from recent event evidence."""

    def __init__(self, event_store: EventStore, memory_store: MemoryStore):
        self.event_store = event_store
        self.memory_store = memory_store

    def consolidate_recent(self, *, limit: int = 200) -> List[MemoryItem]:
        created: List[MemoryItem] = []
        for event in self.event_store.tail(limit=limit):
            created.extend(self.extract_event(event))
        return created

    def extract_event(self, event: EventRecord) -> List[MemoryItem]:
        items: List[MemoryItem] = []
        payload = dict(event.payload or {})
        event_type = event.event_type

        if event_type == "user_message":
            content = _compact_text(payload.get("content") or payload.get("display_text"))
            if not content:
                return []
            if _CORRECTION_RE.search(content):
                items.append(
                    self._make_item(
                        event,
                        scope="project",
                        memory_type="user_correction",
                        content=f"User correction/preference: {content}",
                        confidence=0.86,
                        tags=["user", "correction"],
                    )
                )
            elif _PREFERENCE_RE.search(content):
                items.append(
                    self._make_item(
                        event,
                        scope="project",
                        memory_type="preference",
                        content=f"User preference: {content}",
                        confidence=0.74,
                        tags=["user", "preference"],
                    )
                )
            if _DECISION_RE.search(content):
                items.append(
                    self._make_item(
                        event,
                        scope="project",
                        memory_type="project_decision",
                        content=f"Project decision signal from user: {content}",
                        confidence=0.68,
                        tags=["decision"],
                    )
                )

        elif event_type == "tool_result":
            tool_name = str(payload.get("tool_name") or "").strip()
            success = bool(payload.get("success"))
            summary = _compact_text(payload.get("output") if success else payload.get("error"), 700)
            if not success:
                items.append(
                    self._make_item(
                        event,
                        scope="workflow",
                        memory_type="failure_experience",
                        content=f"Tool failure: {tool_name} failed with {summary}",
                        confidence=0.72,
                        tags=["tool", "failure", tool_name],
                    )
                )
            elif tool_name in {"command_exec", "str_replace_editor", "create_file", "delete_file", "file_ops"}:
                items.append(
                    self._make_item(
                        event,
                        scope="workflow",
                        memory_type="success_workflow",
                        content=f"Successful tool workflow: {tool_name} completed. {summary}",
                        confidence=0.55,
                        tags=["tool", "success", tool_name],
                        decay=0.08,
                    )
                )

        elif event_type == "file_diff":
            path = str(payload.get("path") or "").strip()
            diff_summary = _compact_text(payload.get("diff") or payload.get("summary"), 600)
            if path and diff_summary:
                items.append(
                    self._make_item(
                        event,
                        scope="session",
                        memory_type="fact",
                        content=f"File changed during session: {path}. Diff evidence: {diff_summary}",
                        confidence=0.64,
                        tags=["file_diff", path.split("/")[-1].lower()],
                        decay=0.12,
                    )
                )

        elif event_type in {"error", "exception"}:
            message = _compact_text(payload.get("message") or payload.get("error"), 700)
            if message:
                items.append(
                    self._make_item(
                        event,
                        scope="workflow",
                        memory_type="failure_experience",
                        content=f"Runtime error experience: {message}",
                        confidence=0.78,
                        tags=["error", "failure"],
                    )
                )

        elif event_type in {"explicit_feedback", "implicit_feedback"}:
            feedback = _compact_text(payload.get("feedback") or payload.get("content"), 900)
            if feedback:
                items.append(
                    self._make_item(
                        event,
                        scope="project",
                        memory_type="feedback",
                        content=f"User feedback: {feedback}",
                        confidence=0.82,
                        tags=["feedback"],
                    )
                )

        stored: List[MemoryItem] = []
        for item in items:
            stored.append(self.memory_store.upsert(item))
        return stored

    def extract_events(self, events: Iterable[EventRecord]) -> List[MemoryItem]:
        stored: List[MemoryItem] = []
        for event in events:
            stored.extend(self.extract_event(event))
        return stored

    @staticmethod
    def _make_item(
        event: EventRecord,
        *,
        scope: str,
        memory_type: str,
        content: str,
        confidence: float,
        tags: List[str],
        decay: float = 0.02,
    ) -> MemoryItem:
        return MemoryItem(
            id=new_id("mem"),
            scope=scope,
            memory_type=memory_type,
            content=_compact_text(content, 1200),
            evidence=[_event_evidence(event)],
            confidence=confidence,
            tags=[tag for tag in tags if tag],
            decay=decay,
            created_at=utc_now(),
            updated_at=utc_now(),
            source_event_ids=[event.id],
            metadata={"session_id": event.session_id} if event.session_id else {},
        )
