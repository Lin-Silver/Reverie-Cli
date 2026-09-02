"""NVIDIA-hosted Moonshot AI Kimi K3 profile."""

from __future__ import annotations

from typing import Any, Dict

from .common import max_output_tokens


CONTEXT_TOKENS = 1_048_576
MAX_OUTPUT_TOKENS = 65_536


def build_openai_options(cfg: Dict[str, Any]) -> Dict[str, Any]:
    effort = str(cfg.get("reasoning_effort", "max") or "max").strip().lower()
    return {
        "temperature": 1.0,
        "max_tokens": max_output_tokens(cfg, default=16_384, maximum=MAX_OUTPUT_TOKENS),
        # NVIDIA exposes this as a top-level request field. OpenAI's `extra_body`
        # merges it into that top level without relying on SDK enum support.
        "extra_body": {"reasoning_effort": effort},
    }
