"""Hybrid project-memory retrieval with temporal and provenance-aware ranking."""

from __future__ import annotations

import math
import re
from datetime import datetime, timezone
from typing import Any, Dict, Iterable, List, Optional, Set

from .models import MemoryItem, MemorySearchHit, normalize_memory_type, normalize_scope
from .store import MemoryStore


_TOKEN_RE = re.compile(r"[A-Za-z_][A-Za-z0-9_]{1,}|\d+|[\u4e00-\u9fff]{2,}")


def tokenize(text: Any) -> List[str]:
    """Tokenize identifiers and CJK text without an embedding/indexing wait."""
    raw = str(text or "").lower()
    expanded: List[str] = []
    for token in _TOKEN_RE.findall(raw):
        expanded.append(token)
        if re.fullmatch(r"[\u4e00-\u9fff]{2,}", token):
            expanded.extend(token[index : index + 2] for index in range(len(token) - 1))
            continue
        expanded.extend(part for part in re.split(r"[\\/_.-]+", token) if len(part) >= 2)
        expanded.extend(part.lower() for part in re.findall(r"[A-Z]?[a-z]+|[A-Z]+(?=[A-Z]|$)|\d+", token) if len(part) >= 2)
    return list(dict.fromkeys(expanded))


def _parse_time(value: str) -> Optional[datetime]:
    text = str(value or "").strip()
    if not text:
        return None
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
        return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)
    except (TypeError, ValueError):
        return None


def _character_ngrams(value: Any, size: int = 3) -> Set[str]:
    normalized = re.sub(r"\s+", " ", str(value or "").lower()).strip()
    if not normalized:
        return set()
    if len(normalized) <= size:
        return {normalized}
    return {normalized[index : index + size] for index in range(len(normalized) - size + 1)}


def _jaccard(left: Iterable[str], right: Iterable[str]) -> float:
    a, b = set(left), set(right)
    if not a or not b:
        return 0.0
    return len(a.intersection(b)) / max(1, len(a.union(b)))


class MemoryRetriever:
    """Fuse FTS5, token, character, temporal, confidence, and type signals."""

    TYPE_PRIORITIES: Dict[str, float] = {
        "instruction": 3.4,
        "user_correction": 3.3,
        "preference": 3.1,
        "decision": 3.0,
        "project_decision": 3.0,
        "goal": 2.8,
        "commitment": 2.7,
        "error": 2.6,
        "failure_experience": 2.6,
        "learning": 2.4,
        "success_workflow": 2.4,
        "procedure": 2.3,
        "tool_guidance": 2.2,
        "relationship": 2.0,
        "context": 1.9,
        "artifact": 1.9,
        "observation": 1.8,
        "event": 1.6,
        "retrieval_ranking": 1.8,
        "prompt_digest": 1.6,
        "fact": 1.5,
        "feedback": 1.4,
    }

    SCOPE_PRIORITIES: Dict[str, float] = {
        "session": 1.15,
        "project": 1.3,
        "workflow": 1.1,
        "procedural": 1.05,
    }

    DURABLE_WITHOUT_OVERLAP = {
        "instruction",
        "user_correction",
        "preference",
        "decision",
        "project_decision",
        "goal",
        "commitment",
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
        min_confidence: float = 0.0,
        as_of: str = "",
        changed_since: str = "",
    ) -> List[MemorySearchHit]:
        query_text = str(query or "").strip()
        query_tokens = set(tokenize(query_text))
        query_ngrams = _character_ngrams(query_text)
        wanted_scope = normalize_scope(scope, "") if scope else ""
        wanted_type = normalize_memory_type(memory_type, "") if memory_type else ""
        wanted_tags = {str(tag or "").strip().lower() for tag in (tags or []) if str(tag or "").strip()}
        confidence_floor = max(0.0, min(1.0, float(min_confidence or 0.0)))
        as_of_time = _parse_time(as_of)
        changed_since_time = _parse_time(changed_since)
        now = datetime.now(timezone.utc)

        fts_ids = self.store.search_fts(query_text, limit=max(80, int(limit or 8) * 12))
        fts_rank = {memory_id: rank for rank, memory_id in enumerate(fts_ids, start=1)}
        include_history = as_of_time is not None
        hits: List[MemorySearchHit] = []

        for item in self.store.load_items(include_deleted=include_history):
            if item.status == "deleted":
                continue
            if not include_history and item.status != "active":
                continue
            if wanted_scope and item.scope != wanted_scope:
                continue
            if wanted_type and item.memory_type != wanted_type:
                continue
            if wanted_tags and not wanted_tags.intersection(set(item.tags or [])):
                continue
            if float(item.confidence or 0.0) < confidence_floor:
                continue
            if session_id and item.scope == "session":
                item_session = str((item.metadata or {}).get("session_id", "") or "")
                if item_session and item_session != str(session_id):
                    continue

            created = _parse_time(item.created_at)
            updated = _parse_time(item.updated_at)
            valid_from = _parse_time(item.valid_from)
            valid_to = _parse_time(item.valid_to)
            if as_of_time:
                if created and created > as_of_time:
                    continue
                if valid_from and valid_from > as_of_time:
                    continue
                if valid_to and valid_to <= as_of_time:
                    continue
            if changed_since_time and (updated is None or updated < changed_since_time):
                continue

            searchable = " ".join([item.content, " ".join(item.tags or []), str((item.metadata or {}).get("topic") or "")])
            item_tokens = set(tokenize(searchable))
            overlap = query_tokens.intersection(item_tokens)
            token_similarity = _jaccard(query_tokens, item_tokens)
            char_similarity = _jaccard(query_ngrams, _character_ngrams(searchable))
            exact_phrase = bool(query_text and query_text.lower() in searchable.lower())
            memory_type_name = normalize_memory_type(item.memory_type)

            if (
                query_tokens
                and not overlap
                and char_similarity < 0.035
                and item.id not in fts_rank
                and memory_type_name not in self.DURABLE_WITHOUT_OVERLAP
            ):
                continue

            components: Dict[str, float] = {}
            components["fts_rrf"] = 2.5 * (60.0 / (60.0 + fts_rank[item.id])) if item.id in fts_rank else 0.0
            components["token"] = min(4.0, len(overlap) * 0.72) + token_similarity * 2.2
            components["character"] = min(1.8, char_similarity * 5.0)
            components["phrase"] = 1.5 if exact_phrase else 0.0
            components["type"] = self.TYPE_PRIORITIES.get(memory_type_name, 1.0)
            components["scope"] = self.SCOPE_PRIORITIES.get(normalize_scope(item.scope), 1.0)
            components["confidence"] = max(0.0, min(1.0, float(item.confidence or 0.0))) * 1.7

            recency = 0.0
            decay_multiplier = 1.0
            if updated:
                days = max(0.0, (now - updated).total_seconds() / 86400.0)
                decay = max(0.0, min(1.0, float(item.decay or 0.0)))
                decay_multiplier = math.exp(-decay * min(days, 730.0) / 30.0)
                recency = 0.55 * math.exp(-days / 45.0)
            components["recency"] = recency
            components["access"] = min(0.35, math.log1p(max(0, int(item.access_count or 0))) * 0.08)

            score = sum(components.values()) * decay_multiplier
            if query_tokens and not overlap and item.id not in fts_rank:
                score *= 0.72 if memory_type_name in self.DURABLE_WITHOUT_OVERLAP else 0.5

            reasons: List[str] = []
            if overlap:
                reasons.append("token_overlap:" + ",".join(sorted(overlap)[:8]))
            if item.id in fts_rank:
                reasons.append(f"fts5_rank:{fts_rank[item.id]}")
            if exact_phrase:
                reasons.append("exact_phrase")
            if char_similarity >= 0.08:
                reasons.append(f"character_similarity:{char_similarity:.2f}")
            if updated and (now - updated).total_seconds() <= 7 * 86400:
                reasons.append("recent")
            reasons.extend([f"provenance:{item.provenance}", f"version:{item.version}"])
            hits.append(MemorySearchHit(item=item, score=score, reasons=reasons, components=components))

        selected = self._diversify(hits, limit=max(1, min(int(limit or 1), 50)))
        self.store.touch_access(hit.item.id for hit in selected)
        return selected

    @staticmethod
    def _diversify(hits: List[MemorySearchHit], *, limit: int) -> List[MemorySearchHit]:
        """Apply a small MMR-style redundancy penalty to the fused ranking."""
        remaining = sorted(hits, key=lambda hit: (-hit.score, hit.item.id))
        selected: List[MemorySearchHit] = []
        while remaining and len(selected) < limit:
            best_index = 0
            best_utility = float("-inf")
            for index, hit in enumerate(remaining[: max(40, limit * 4)]):
                redundancy = max(
                    (_jaccard(tokenize(hit.item.content), tokenize(chosen.item.content)) for chosen in selected),
                    default=0.0,
                )
                utility = hit.score - redundancy * 1.25
                if utility > best_utility:
                    best_index = index
                    best_utility = utility
            selected.append(remaining.pop(best_index))
        return selected


__all__ = ["MemoryRetriever", "tokenize"]
