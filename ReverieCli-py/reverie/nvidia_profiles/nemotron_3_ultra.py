"""NVIDIA Nemotron 3 Ultra profile."""

from __future__ import annotations

from typing import Any, Dict

from .common import max_output_tokens


CONTEXT_TOKENS = 1_000_000
MAX_OUTPUT_TOKENS = 16_384


def build_openai_options(cfg: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "temperature": 1.0,
        "top_p": 0.95,
        "max_tokens": max_output_tokens(cfg, maximum=MAX_OUTPUT_TOKENS),
        "extra_body": {
            "chat_template_kwargs": {"enable_thinking": True},
            "reasoning_budget": 16_384,
        },
    }
