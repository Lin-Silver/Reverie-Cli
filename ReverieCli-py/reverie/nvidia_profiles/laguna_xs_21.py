"""NVIDIA-hosted Laguna XS 2.1 profile."""

from __future__ import annotations

from typing import Any, Dict

from .common import max_output_tokens


CONTEXT_TOKENS = 262_000
MAX_OUTPUT_TOKENS = 8_192


def build_openai_options(cfg: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "temperature": 1.0,
        "top_p": 1.0,
        "max_tokens": max_output_tokens(cfg, default=8_192, maximum=MAX_OUTPUT_TOKENS),
        "extra_body": {"top_k": 20, "min_p": 0.0},
    }
