"""NVIDIA-hosted GPT-OSS-20B profile."""

from __future__ import annotations

from typing import Any, Dict

from .common import max_output_tokens


CONTEXT_TOKENS = 131_072
MAX_OUTPUT_TOKENS = 4_096


def build_openai_options(cfg: Dict[str, Any]) -> Dict[str, Any]:
    effort = str(cfg.get("reasoning_effort", "medium") or "medium").strip().lower()
    return {
        "temperature": 1.0,
        "top_p": 1.0,
        "max_tokens": max_output_tokens(cfg, default=4_096, maximum=MAX_OUTPUT_TOKENS),
        "extra_body": {"reasoning_effort": effort},
    }
