"""NVIDIA-hosted GLM 5.3 Flash profile."""

from __future__ import annotations

from typing import Any, Dict

from .common import max_output_tokens


CONTEXT_TOKENS = 1_048_576
MAX_OUTPUT_TOKENS = 1_048_576


def build_openai_options(cfg: Dict[str, Any]) -> Dict[str, Any]:
    effort = str(cfg.get("reasoning_effort", "max") or "max").strip().lower()
    return {
        "temperature": 1.0,
        "top_p": 0.95,
        "max_tokens": max_output_tokens(cfg, maximum=MAX_OUTPUT_TOKENS),
        "extra_body": {
            "reasoning_effort": effort,
            "chat_template_kwargs": {"clear_thinking": True},
        },
    }
