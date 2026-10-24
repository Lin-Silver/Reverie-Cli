"""NVIDIA-hosted MiniMax M3.1 Flash request profile."""

from __future__ import annotations

from typing import Any, Dict

from .common import max_output_tokens


CONTEXT_TOKENS = 262_144
MAX_OUTPUT_TOKENS = 65_536


def build_openai_options(cfg: Dict[str, Any]) -> Dict[str, Any]:
    effort = str(cfg.get("reasoning_effort", "high") or "high").strip().lower()
    return {
        "temperature": 1.0,
        "top_p": 0.95,
        "max_tokens": max_output_tokens(cfg, default=MAX_OUTPUT_TOKENS, maximum=MAX_OUTPUT_TOKENS),
        "extra_body": {"chat_template_kwargs": {"reasoning_effort": effort}},
    }
