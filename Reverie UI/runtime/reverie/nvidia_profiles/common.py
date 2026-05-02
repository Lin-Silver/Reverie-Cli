"""Shared helpers for NVIDIA model profiles."""

from __future__ import annotations

from typing import Any, Dict


DEFAULT_MAX_OUTPUT_TOKENS = 16_384


def max_output_tokens(cfg: Dict[str, Any], default: int = DEFAULT_MAX_OUTPUT_TOKENS) -> int:
    """Return the configured full-output token budget for a profile."""
    try:
        value = int((cfg or {}).get("max_tokens", default) or default)
    except (TypeError, ValueError):
        value = default
    return max(1, value)
