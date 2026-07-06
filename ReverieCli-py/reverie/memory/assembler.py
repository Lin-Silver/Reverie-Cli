"""Build bounded context packages from code evidence and memory."""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from ..context_engine.fragments import estimate_tokens, truncate_to_token_cap
from .models import ContextPackage, MEMORY_CONTEXT_PROMPT_HEADER, MemorySearchHit
from .retriever import MemoryRetriever


class ContextAssembler:
    """Assemble high-density context for one model turn."""

    def __init__(self, memory_retriever: MemoryRetriever):
        self.memory_retriever = memory_retriever
        self._cache: Dict[tuple[Any, ...], ContextPackage] = {}

    def assemble(
        self,
        query: str,
        *,
        code_retriever: Any = None,
        session_id: str = "",
        recent_messages: Optional[List[Dict[str, Any]]] = None,
        max_tokens: int = 6000,
    ) -> ContextPackage:
        query_text = str(query or "").strip()
        max_tokens = max(800, int(max_tokens or 6000))
        cache_key = (
            query_text.lower(),
            str(session_id or ""),
            len(recent_messages or []),
            id(code_retriever) if code_retriever is not None else 0,
            max_tokens,
            self.memory_retriever.store.revision,
        )
        cached = self._cache.get(cache_key)
        if cached:
            return cached

        memory_budget = max(600, int(max_tokens * 0.44))
        code_budget = max(600, int(max_tokens * 0.36))
        recent_budget = max(200, int(max_tokens * 0.12))

        memory_hits = self.memory_retriever.search(
            query_text,
            limit=10,
            session_id=session_id,
        )
        memory_block = self._render_memory_hits(memory_hits, token_budget=memory_budget)
        code_block, code_sources = self._render_code_context(
            code_retriever,
            query_text,
            token_budget=code_budget,
        )
        recent_block = self._render_recent_turns(recent_messages or [], token_budget=recent_budget)

        sections = [
            MEMORY_CONTEXT_PROMPT_HEADER,
            "Use this package as retrieved evidence, not as hidden conversation history. Prefer cited evidence over assumptions.",
            f"Current request: {truncate_to_token_cap(query_text, 160)}" if query_text else "",
            code_block,
            memory_block,
            recent_block,
        ]
        content = "\n\n".join(section for section in sections if section).strip()
        content = truncate_to_token_cap(content, max_tokens)
        package = ContextPackage(
            query=query_text,
            content=content,
            token_estimate=estimate_tokens(content),
            memory_ids=[hit.item.id for hit in memory_hits],
            event_ids=list(
                dict.fromkeys(
                    event_id
                    for hit in memory_hits
                    for event_id in (hit.item.source_event_ids or [])
                    if event_id
                )
            ),
            sources=["memory"] + code_sources + (["recent_tail"] if recent_block else []),
        )
        self._cache[cache_key] = package
        if len(self._cache) > 12:
            self._cache.pop(next(iter(self._cache)))
        return package

    def _render_memory_hits(self, hits: List[MemorySearchHit], *, token_budget: int) -> str:
        if not hits:
            return ""
        lines = ["Relevant structured memory:"]
        remaining = max(1, int(token_budget or 1))
        for hit in hits:
            item = hit.item
            evidence_ids = ",".join((item.source_event_ids or [])[:3])
            body = (
                f"- {item.id} [{item.scope}/{item.memory_type} "
                f"confidence={item.confidence:.2f} version={item.version} "
                f"provenance={item.provenance} decay={item.decay:.2f}] "
                f"{item.content}"
            )
            if item.tags:
                body += f" tags={','.join(item.tags[:5])}"
            if evidence_ids:
                body += f" evidence={evidence_ids}"
            body = truncate_to_token_cap(body, min(180, remaining))
            used = estimate_tokens(body)
            if used > remaining:
                break
            lines.append(body)
            remaining -= used
            if remaining <= 0:
                break
        return "\n".join(lines)

    def _render_code_context(self, code_retriever: Any, query: str, *, token_budget: int) -> tuple[str, List[str]]:
        if not code_retriever or not query:
            return "", []
        if not hasattr(code_retriever, "retrieve_for_task"):
            return "", []
        try:
            result = code_retriever.retrieve_for_task(
                query,
                max_tokens=max(1000, int(token_budget or 1000)),
                max_files=4,
                max_symbols=8,
                include_history=True,
                include_memory=False,
            )
        except Exception:
            return "", []
        context_string = str(getattr(result, "context_string", "") or "").strip()
        if not context_string:
            return "", []
        return (
            "Relevant code/project context:\n" + truncate_to_token_cap(context_string, token_budget),
            ["code_index"],
        )

    def _render_recent_turns(self, messages: List[Dict[str, Any]], *, token_budget: int) -> str:
        if not messages:
            return ""
        lines = ["Recent working tail:"]
        remaining = max(1, int(token_budget or 1))
        for message in messages[-6:]:
            if not isinstance(message, dict):
                continue
            role = str(message.get("role", "") or "").strip()
            if role == "system":
                continue
            content = str(message.get("content") or "")
            if not content and message.get("tool_calls"):
                content = f"tool_calls={message.get('tool_calls')}"
            if not content:
                continue
            line = f"- {role}: {truncate_to_token_cap(content, 80)}"
            used = estimate_tokens(line)
            if used > remaining:
                break
            lines.append(line)
            remaining -= used
        return "\n".join(lines) if len(lines) > 1 else ""
