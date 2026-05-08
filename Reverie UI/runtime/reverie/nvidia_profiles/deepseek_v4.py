"""NVIDIA DeepSeek V4 profile."""

from __future__ import annotations

from typing import Any, Dict

from .common import max_output_tokens


CONTEXT_TOKENS = 1_000_000
MAX_OUTPUT_TOKENS = 262_144


def build_openai_options(cfg: Dict[str, Any]) -> Dict[str, Any]:
    effort = str(cfg.get("reasoning_effort", "high") or "high").strip().lower()
    thinking_enabled = effort != "none"
    chat_template_kwargs: Dict[str, Any] = {"thinking": thinking_enabled}
    if thinking_enabled:
        chat_template_kwargs["reasoning_effort"] = effort

    return {
        "temperature": 1.0,
        "top_p": 0.95,
        "max_tokens": max_output_tokens(cfg, default=MAX_OUTPUT_TOKENS, maximum=MAX_OUTPUT_TOKENS),
        "extra_body": {
            "chat_template_kwargs": chat_template_kwargs,
        },
    }
