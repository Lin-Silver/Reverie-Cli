"""Shared helpers for NVIDIA model profiles."""

from __future__ import annotations

from typing import Any, Dict


DEFAULT_MAX_OUTPUT_TOKENS = 16_384


def max_output_tokens(
    cfg: Dict[str, Any],
    default: int = DEFAULT_MAX_OUTPUT_TOKENS,
    *,
    maximum: int | None = None,
) -> int:
    """Return the configured full-output token budget for a profile."""
    try:
        value = int((cfg or {}).get("max_tokens", default) or default)
    except (TypeError, ValueError):
        value = default
    if maximum is not None:
        try:
            limit = int(maximum)
        except (TypeError, ValueError):
            limit = 0
        if limit > 0:
            value = min(value, limit)
    return max(1, value)
