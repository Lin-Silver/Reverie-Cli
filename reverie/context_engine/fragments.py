"""Typed, bounded context fragments for prompt assembly."""

from __future__ import annotations

from dataclasses import dataclass, field
from hashlib import sha256
from typing import Any, Dict, Iterable, List, Optional


def estimate_tokens(text: str) -> int:
    """Cheap token estimate used for deterministic local budgeting."""
    normalized = str(text or "")
    if not normalized:
        return 0
    return max(1, (len(normalized) + 3) // 4)


def truncate_to_token_cap(text: str, token_cap: int) -> str:
    """Return text bounded to approximately token_cap tokens."""
    raw = str(text or "")
    try:
        cap = int(token_cap)
    except (TypeError, ValueError):
        cap = 0
    if cap <= 0 or estimate_tokens(raw) <= cap:
        return raw
    char_cap = max(16, cap * 4)
    return raw[: max(0, char_cap - 3)].rstrip() + "..."


@dataclass(frozen=True)
class ContextFragment:
    """A typed unit of context with explicit source and token budget."""

    fragment_type: str
    source: str
    content: str
    token_cap: int
    priority: float = 0.0
    stable_order: int = 0
    cache_key: str = ""
    metadata: Dict[str, Any] = field(default_factory=dict)

    def bounded_content(self) -> str:
        return truncate_to_token_cap(self.content, self.token_cap)

    def effective_cache_key(self) -> str:
        if self.cache_key:
            return self.cache_key
        digest = sha256(
            "\n".join(
                [
                    str(self.fragment_type or ""),
                    str(self.source or ""),
                    str(self.content or ""),
                    str(sorted((self.metadata or {}).items())),
                ]
            ).encode("utf-8", errors="replace")
        ).hexdigest()
        return digest[:24]


def make_context_fragment(
    fragment_type: str,
    source: str,
    content: str,
    *,
    token_cap: int,
    priority: float = 0.0,
    stable_order: int = 0,
    metadata: Optional[Dict[str, Any]] = None,
) -> ContextFragment:
    """Create a context fragment with a stable cache key."""
    base = ContextFragment(
        fragment_type=str(fragment_type or "generic"),
        source=str(source or "unknown"),
        content=str(content or ""),
        token_cap=max(1, int(token_cap or 1)),
        priority=float(priority or 0.0),
        stable_order=int(stable_order or 0),
        metadata=dict(metadata or {}),
    )
    return ContextFragment(
        fragment_type=base.fragment_type,
        source=base.source,
        content=base.content,
        token_cap=base.token_cap,
        priority=base.priority,
        stable_order=base.stable_order,
        cache_key=base.effective_cache_key(),
        metadata=base.metadata,
    )


def sort_context_fragments(fragments: Iterable[ContextFragment]) -> List[ContextFragment]:
    """Sort fragments by priority, then stable source/order/cache key."""
    return sorted(
        list(fragments or []),
        key=lambda fragment: (
            -float(fragment.priority or 0.0),
            str(fragment.source or ""),
            int(fragment.stable_order or 0),
            fragment.effective_cache_key(),
        ),
    )


def render_context_fragments(
    fragments: Iterable[ContextFragment],
    *,
    title: str = "Context Fragments",
    max_tokens: int = 12000,
) -> str:
    """Render fragments as a deterministic bounded prompt block."""
    remaining = max(1, int(max_tokens or 1))
    lines = [f"## {title}"]
    for fragment in sort_context_fragments(fragments):
        if remaining <= 0:
            break
        cap = min(remaining, max(1, int(fragment.token_cap or 1)))
        body = truncate_to_token_cap(fragment.content, cap).strip()
        if not body:
            continue
        used = estimate_tokens(body)
        remaining -= used
        lines.append(f"- [{fragment.fragment_type}] {fragment.source}: {body}")
    return "\n".join(lines).strip()
