"""NVIDIA Nemotron 3.5 Lightning profile."""

from __future__ import annotations

from typing import Any, Dict

from .common import max_output_tokens


CONTEXT_TOKENS = 1_048_576
MAX_OUTPUT_TOKENS = 32_768
DEFAULT_REASONING_BUDGET = 16_384


def build_openai_options(cfg: Dict[str, Any]) -> Dict[str, Any]:
    thinking_enabled = bool(cfg.get("enable_thinking", True))
    extra_body: Dict[str, Any] = {
        "chat_template_kwargs": {"enable_thinking": thinking_enabled},
    }
    if thinking_enabled:
        extra_body["reasoning_budget"] = int(
            cfg.get("reasoning_budget", DEFAULT_REASONING_BUDGET) or DEFAULT_REASONING_BUDGET
        )
    return {
        "temperature": 1.0,
        "top_p": 0.95,
        "max_tokens": max_output_tokens(cfg, default=16_384, maximum=MAX_OUTPUT_TOKENS),
        "extra_body": extra_body,
    }
