"""NVIDIA-hosted Meta Muse Glimmer 30B profile."""

from __future__ import annotations

from typing import Any, Dict

from .common import max_output_tokens


CONTEXT_TOKENS = 131_072
MAX_OUTPUT_TOKENS = 16_384


def build_openai_options(cfg: Dict[str, Any]) -> Dict[str, Any]:
    effort = str(cfg.get("reasoning_effort", "high") or "high").strip().lower()
    return {
        "temperature": 1.0,
        "top_p": 0.95,
        "max_tokens": max_output_tokens(cfg, default=8_192, maximum=MAX_OUTPUT_TOKENS),
        "extra_body": {"reasoning_effort": effort},
    }
