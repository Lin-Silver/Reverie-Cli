"""MemoryItem retrieval and explanation."""

from __future__ import annotations

import math
import re
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from .models import MemoryItem, MemorySearchHit, normalize_memory_type, normalize_scope
from .store import MemoryStore


_TOKEN_RE = re.compile(r"[A-Za-z_][A-Za-z0-9_]{2,}|[\u4e00-\u9fff]{2,}")


def tokenize(text: Any) -> List[str]:
    raw = str(text or "").lower()
    tokens = _TOKEN_RE.findall(raw)
    expanded: List[str] = []
    for token in tokens:
        expanded.append(token)
        if "/" in token or "\\" in token:
            expanded.extend(part for part in re.split(r"[\\/_.-]+", token) if len(part) >= 3)
    return list(dict.fromkeys(expanded))


def _parse_time(value: str) -> Optional[datetime]:
    text = str(value or "").strip()
    if not text:
        return None
    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00"))
    except Exception:
        return None


class MemoryRetriever:
    """Rank structured memory against the active request."""

    TYPE_PRIORITIES: Dict[str, float] = {
        "user_correction": 3.2,
        "preference": 3.0,
        "project_decision": 2.8,
        "failure_experience": 2.4,
        "success_workflow": 2.2,
        "procedure": 2.0,
        "tool_guidance": 2.0,
        "retrieval_ranking": 1.8,
        "prompt_digest": 1.6,
        "fact": 1.4,
        "feedback": 1.2,
    }

    SCOPE_PRIORITIES: Dict[str, float] = {
        "session": 1.25,
        "project": 1.15,
        "workflow": 1.05,
        "procedural": 1.0,
    }

    def __init__(self, store: MemoryStore):
        self.store = store

    def search(
        self,
        query: str,
        *,
        scope: str = "",
        memory_type: str = "",
        tags: Optional[List[str]] = None,
        limit: int = 8,
        session_id: str = "",
    ) -> List[MemorySearchHit]:
        query_tokens = set(tokenize(query))
        wanted_scope = normalize_scope(scope, "") if scope else ""
        wanted_type = normalize_memory_type(memory_type, "") if memory_type else ""
        wanted_tags = {str(tag or "").strip().lower() for tag in (tags or []) if str(tag or "").strip()}
        now = datetime.now(timezone.utc)
        hits: List[MemorySearchHit] = []

        for item in self.store.load_items():
            if wanted_scope and item.scope != wanted_scope:
                continue
            if wanted_type and item.memory_type != wanted_type:
                continue
            if wanted_tags and not wanted_tags.intersection(set(item.tags or [])):
                continue
            if session_id and item.scope == "session":
                item_session = str((item.metadata or {}).get("session_id", "") or "")
                if item_session and item_session != str(session_id):
                    continue

            item_tokens = set(tokenize(" ".join([item.content, " ".join(item.tags or [])])))
            overlap = query_tokens.intersection(item_tokens)
            score = 0.0
            reasons: List[str] = []
            if overlap:
                score += min(4.0, len(overlap) * 0.7)
                reasons.append("token_overlap:" + ",".join(sorted(overlap)[:6]))
            if not query_tokens:
                score += 0.2

            memory_type = normalize_memory_type(item.memory_type)
            scope_name = normalize_scope(item.scope)
            score += self.TYPE_PRIORITIES.get(memory_type, 1.0)
            score += self.SCOPE_PRIORITIES.get(scope_name, 1.0)
            score += max(0.0, min(1.0, float(item.confidence or 0.0))) * 1.5

            updated = _parse_time(item.updated_at)
            if updated:
                days = max(0.0, (now - updated).total_seconds() / 86400.0)
                decay = max(0.0, min(1.0, float(item.decay or 0.0)))
                score *= math.exp(-decay * min(days, 365.0) / 30.0)
                if days <= 7:
                    score += 0.45
                    reasons.append("recent")

            if memory_type in {"user_correction", "preference"}:
                score += 0.4
                reasons.append(memory_type)
            if query_tokens and not overlap and memory_type not in {"preference", "project_decision", "user_correction"}:
                score *= 0.55

            if score <= 0:
                continue
            hits.append(MemorySearchHit(item=item, score=score, reasons=reasons or ["type_scope_prior"]))

        hits.sort(key=lambda hit: hit.score, reverse=True)
        return hits[: max(1, int(limit or 1))]
