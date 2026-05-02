"""NVIDIA GPT-OSS-120B profile."""

from __future__ import annotations

from typing import Any, Dict

from .common import max_output_tokens


CONTEXT_TOKENS = 128_000


def build_openai_options(cfg: Dict[str, Any]) -> Dict[str, Any]:
    effort = str(cfg.get("reasoning_effort", "medium") or "medium").strip().lower()
    return {
        "temperature": 0.6,
        "top_p": 0.7,
        "max_tokens": max_output_tokens(cfg),
        "extra_body": {"reasoning_effort": effort},
    }
