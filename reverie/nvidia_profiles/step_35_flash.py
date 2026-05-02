"""NVIDIA Step-3.5-Flash profile."""

from __future__ import annotations

from typing import Any, Dict

from .common import max_output_tokens


CONTEXT_TOKENS = 256_000


def build_openai_options(cfg: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "temperature": 1.0,
        "top_p": 0.9,
        "max_tokens": max_output_tokens(cfg),
        "extra_body": {
            "reasoning_format": {"type": "deepseek-style"},
        },
    }
