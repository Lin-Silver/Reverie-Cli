"""Provider-neutral prompt-cache hints and compatibility fallbacks."""

from __future__ import annotations

from contextlib import contextmanager
import hashlib
import json
import logging
import sys
from typing import Any, Callable, Dict, Iterator, Mapping, Optional


logger = logging.getLogger(__name__)

_OPENAI_CACHE_FIELDS = {
    "prompt_cache_key",
    "prompt_cache_options",
    "prompt_cache_retention",
    "cache_prompt",
}
_ANTHROPIC_CACHE_FIELDS = {"cache_control"}
_ALL_CACHE_FIELDS = _OPENAI_CACHE_FIELDS | _ANTHROPIC_CACHE_FIELDS


def _canonical_json(value: Any) -> str:
    try:
        return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    except (TypeError, ValueError):
        return str(value or "")


def _first_stable_message(payload: Mapping[str, Any]) -> Any:
    messages = payload.get("messages")
    if isinstance(messages, list):
        for message in messages:
            if not isinstance(message, dict):
                continue
            if str(message.get("role", "") or "").strip().lower() in {"system", "developer"}:
                return {
                    "role": message.get("role"),
                    "content": message.get("content"),
                }
            break

    response_input = payload.get("input")
    if isinstance(response_input, list):
        for item in response_input:
            if not isinstance(item, dict):
                continue
            if (
                str(item.get("type", "") or "").strip().lower() == "message"
                and str(item.get("role", "") or "").strip().lower() in {"system", "developer"}
            ):
                return {
                    "role": item.get("role"),
                    "content": item.get("content"),
                }
            break
    return None


def build_prompt_cache_key(payload: Mapping[str, Any], *, namespace: str = "model") -> str:
    """Return a privacy-preserving key shared by requests with the same stable prefix."""
    identity = {
        "namespace": str(namespace or "model").strip().lower() or "model",
        "model": str(payload.get("model", "") or "").strip().lower(),
        "instructions": payload.get("instructions", ""),
        "system": _first_stable_message(payload),
        "tools": payload.get("tools") if isinstance(payload.get("tools"), list) else None,
    }
    digest = hashlib.sha256(_canonical_json(identity).encode("utf-8")).hexdigest()[:32]
    namespace_text = str(namespace or "model").strip().lower().replace(" ", "-") or "model"
    return f"reverie:{namespace_text[:20]}:{digest}"


def apply_openai_prompt_cache(
    payload: Mapping[str, Any],
    *,
    namespace: str = "model",
    include_legacy_cache_prompt: bool = False,
) -> Dict[str, Any]:
    """Prefer OpenAI prefix caching while retaining an unmodified compatible shape."""
    prepared = dict(payload or {})
    prepared.setdefault("prompt_cache_key", build_prompt_cache_key(prepared, namespace=namespace))
    if include_legacy_cache_prompt:
        # llama.cpp and a few compatible local servers use this opt-in spelling.
        prepared.setdefault("cache_prompt", True)
    return prepared


def apply_anthropic_prompt_cache(payload: Mapping[str, Any]) -> Dict[str, Any]:
    """Enable Anthropic automatic prompt caching with its default five-minute TTL."""
    prepared = dict(payload or {})
    prepared.setdefault("cache_control", {"type": "ephemeral"})
    return prepared


def has_prompt_cache_hints(payload: Mapping[str, Any]) -> bool:
    if any(field in payload for field in _ALL_CACHE_FIELDS):
        return True
    extra_body = payload.get("extra_body")
    return isinstance(extra_body, dict) and any(field in extra_body for field in _ALL_CACHE_FIELDS)


def without_prompt_cache(payload: Mapping[str, Any]) -> Dict[str, Any]:
    """Remove only Reverie's request-level cache hints for compatibility retry."""
    prepared = dict(payload or {})
    for field in _ALL_CACHE_FIELDS:
        prepared.pop(field, None)
    extra_body = prepared.get("extra_body")
    if isinstance(extra_body, dict):
        cleaned_extra = dict(extra_body)
        for field in _ALL_CACHE_FIELDS:
            cleaned_extra.pop(field, None)
        if cleaned_extra:
            prepared["extra_body"] = cleaned_extra
        else:
            prepared.pop("extra_body", None)
    return prepared


def _error_status_code(exc: BaseException) -> Optional[int]:
    status = getattr(exc, "status_code", None)
    if not isinstance(status, int):
        status = getattr(getattr(exc, "response", None), "status_code", None)
    return status if isinstance(status, int) else None


def _error_text(exc: BaseException) -> str:
    parts = [str(exc or "")]
    response = getattr(exc, "response", None)
    if response is not None:
        try:
            parts.append(_canonical_json(response.json()))
        except (AttributeError, TypeError, ValueError):
            response_text = getattr(response, "text", "")
            if response_text:
                parts.append(str(response_text))
    return " ".join(parts).lower()


def is_prompt_cache_rejection(exc: BaseException) -> bool:
    """Return whether a failed first attempt should be retried without cache hints."""
    text = _error_text(exc)
    cache_markers = (
        "prompt_cache_key",
        "prompt_cache_options",
        "prompt_cache_retention",
        "cache_prompt",
        "cache_control",
        "prompt cache",
        "prompt caching",
    )
    mentions_cache = any(marker in text for marker in cache_markers)
    if not mentions_cache:
        return False
    status = _error_status_code(exc)
    if status in {400, 404, 405, 415, 422}:
        return True
    return any(
        marker in text
        for marker in ("unexpected", "unknown", "unsupported", "invalid", "not permitted", "extra")
    )


def call_with_prompt_cache_fallback(
    call: Callable[..., Any],
    payload: Mapping[str, Any],
    *,
    log: Optional[logging.Logger] = None,
) -> Any:
    """Call with cache hints first, then retry once only for compatibility rejection."""
    prepared = dict(payload or {})
    try:
        return call(**prepared)
    except Exception as exc:
        if not has_prompt_cache_hints(prepared) or not is_prompt_cache_rejection(exc):
            raise
        (log or logger).warning("Provider rejected prompt-cache hints; retrying once without them")
        return call(**without_prompt_cache(prepared))


@contextmanager
def anthropic_stream_with_prompt_cache_fallback(
    create_stream: Callable[..., Any],
    payload: Mapping[str, Any],
    *,
    log: Optional[logging.Logger] = None,
) -> Iterator[Any]:
    """Enter an Anthropic stream, retrying only if cache hints are rejected on open."""
    prepared = dict(payload or {})
    manager = None
    try:
        try:
            manager = create_stream(**prepared)
            stream = manager.__enter__()
        except Exception as exc:
            if not has_prompt_cache_hints(prepared) or not is_prompt_cache_rejection(exc):
                raise
            (log or logger).warning("Provider rejected Anthropic cache_control; retrying once without it")
            manager = create_stream(**without_prompt_cache(prepared))
            stream = manager.__enter__()
        try:
            yield stream
        finally:
            if manager is not None:
                manager.__exit__(*sys.exc_info())
    finally:
        manager = None
