"""NVIDIA Step-3.7-Flash request profile."""

from __future__ import annotations

from typing import Any, Dict

from .common import max_output_tokens


CONTEXT_TOKENS = 256_000
MAX_OUTPUT_TOKENS = 16_384


def build_request_defaults(cfg: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "max_tokens": max_output_tokens(cfg, default=MAX_OUTPUT_TOKENS, maximum=MAX_OUTPUT_TOKENS),
        "temperature": 1.00,
        "top_p": 0.95,
    }
