"""Typed records for Reverie's memory engine."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List
from uuid import uuid4


MEMORY_CONTEXT_PROMPT_HEADER = "[REVERIE CONTEXT ENGINE MEMORY PACKAGE]"

MEMORY_SCOPES = ("session", "project", "workflow", "procedural")
MEMORY_TYPES = (
    "fact",
    "preference",
    "project_decision",
    "failure_experience",
    "success_workflow",
    "procedure",
    "user_correction",
    "tool_guidance",
    "retrieval_ranking",
    "prompt_digest",
    "feedback",
)


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def new_id(prefix: str) -> str:
    return f"{prefix}_{uuid4().hex[:16]}"


def normalize_scope(value: Any, default: str = "project") -> str:
    text = str(value or "").strip().lower().replace("-", "_")
    return text if text in MEMORY_SCOPES else default


def normalize_memory_type(value: Any, default: str = "fact") -> str:
    text = str(value or "").strip().lower().replace("-", "_")
    aliases = {
        "decision": "project_decision",
        "failure": "failure_experience",
        "success": "success_workflow",
        "workflow": "success_workflow",
        "correction": "user_correction",
        "guidance": "tool_guidance",
    }
    text = aliases.get(text, text)
    return text if text in MEMORY_TYPES else default


def coerce_tags(values: Any) -> List[str]:
    if values is None:
        return []
    if isinstance(values, str):
        raw_values = values.replace(";", ",").split(",")
    elif isinstance(values, (list, tuple, set)):
        raw_values = list(values)
    else:
        raw_values = [values]
    tags: List[str] = []
    seen: set[str] = set()
    for value in raw_values:
        tag = str(value or "").strip().lower().replace(" ", "_")
        if not tag or tag in seen:
            continue
        tags.append(tag[:64])
        seen.add(tag)
    return tags[:16]


@dataclass
class EventRecord:
    """One append-only, lossless event-store entry."""

    id: str
    timestamp: str
    event_type: str
    actor: str
    session_id: str = ""
    workspace_id: str = ""
    tags: List[str] = field(default_factory=list)
    payload: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "timestamp": self.timestamp,
            "event_type": self.event_type,
            "actor": self.actor,
            "session_id": self.session_id,
            "workspace_id": self.workspace_id,
            "tags": list(self.tags),
            "payload": dict(self.payload or {}),
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "EventRecord":
        return cls(
            id=str(data.get("id") or new_id("evt")),
            timestamp=str(data.get("timestamp") or utc_now()),
            event_type=str(data.get("event_type") or "event"),
            actor=str(data.get("actor") or ""),
            session_id=str(data.get("session_id") or ""),
            workspace_id=str(data.get("workspace_id") or ""),
            tags=coerce_tags(data.get("tags")),
            payload=dict(data.get("payload") or {}),
        )


@dataclass
class MemoryItem:
    """A structured long-term memory distilled from event evidence."""

    id: str
    scope: str
    memory_type: str
    content: str
    evidence: List[Dict[str, Any]] = field(default_factory=list)
    confidence: float = 0.5
    tags: List[str] = field(default_factory=list)
    decay: float = 0.02
    created_at: str = field(default_factory=utc_now)
    updated_at: str = field(default_factory=utc_now)
    source_event_ids: List[str] = field(default_factory=list)
    status: str = "active"
    metadata: Dict[str, Any] = field(default_factory=dict)

    def fingerprint(self) -> str:
        import hashlib

        raw = "\n".join(
            [
                normalize_scope(self.scope),
                normalize_memory_type(self.memory_type),
                " ".join(str(self.content or "").lower().split()),
            ]
        )
        return hashlib.sha1(raw.encode("utf-8", errors="replace")).hexdigest()[:24]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "scope": normalize_scope(self.scope),
            "type": normalize_memory_type(self.memory_type),
            "content": str(self.content or ""),
            "evidence": list(self.evidence or []),
            "confidence": max(0.0, min(1.0, float(self.confidence or 0.0))),
            "tags": coerce_tags(self.tags),
            "decay": max(0.0, min(1.0, float(self.decay or 0.0))),
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "source_event_ids": list(self.source_event_ids or []),
            "status": str(self.status or "active"),
            "metadata": dict(self.metadata or {}),
            "fingerprint": self.fingerprint(),
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "MemoryItem":
        return cls(
            id=str(data.get("id") or new_id("mem")),
            scope=normalize_scope(data.get("scope")),
            memory_type=normalize_memory_type(data.get("type", data.get("memory_type"))),
            content=str(data.get("content") or ""),
            evidence=list(data.get("evidence") or []),
            confidence=float(data.get("confidence") or 0.0),
            tags=coerce_tags(data.get("tags")),
            decay=float(data.get("decay") or 0.0),
            created_at=str(data.get("created_at") or utc_now()),
            updated_at=str(data.get("updated_at") or utc_now()),
            source_event_ids=[str(item) for item in (data.get("source_event_ids") or []) if str(item or "").strip()],
            status=str(data.get("status") or "active"),
            metadata=dict(data.get("metadata") or {}),
        )


@dataclass
class MemorySearchHit:
    item: MemoryItem
    score: float
    reasons: List[str] = field(default_factory=list)


@dataclass
class ContextPackage:
    query: str
    content: str
    token_estimate: int
    memory_ids: List[str] = field(default_factory=list)
    event_ids: List[str] = field(default_factory=list)
    sources: List[str] = field(default_factory=list)


@dataclass
class LearningProposal:
    """Validated path for feedback-driven evolution."""

    id: str
    proposal_type: str
    summary: str
    target: str
    evidence: List[Dict[str, Any]] = field(default_factory=list)
    status: str = "pending_validation"
    evaluation: Dict[str, Any] = field(default_factory=dict)
    created_at: str = field(default_factory=utc_now)
    updated_at: str = field(default_factory=utc_now)
    applied_memory_id: str = ""
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "proposal_type": str(self.proposal_type or "workflow_memory"),
            "summary": str(self.summary or ""),
            "target": str(self.target or "workflow_memory"),
            "evidence": list(self.evidence or []),
            "status": str(self.status or "pending_validation"),
            "evaluation": dict(self.evaluation or {}),
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "applied_memory_id": str(self.applied_memory_id or ""),
            "metadata": dict(self.metadata or {}),
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "LearningProposal":
        return cls(
            id=str(data.get("id") or new_id("learn")),
            proposal_type=str(data.get("proposal_type") or "workflow_memory"),
            summary=str(data.get("summary") or ""),
            target=str(data.get("target") or "workflow_memory"),
            evidence=list(data.get("evidence") or []),
            status=str(data.get("status") or "pending_validation"),
            evaluation=dict(data.get("evaluation") or {}),
            created_at=str(data.get("created_at") or utc_now()),
            updated_at=str(data.get("updated_at") or utc_now()),
            applied_memory_id=str(data.get("applied_memory_id") or ""),
            metadata=dict(data.get("metadata") or {}),
        )
