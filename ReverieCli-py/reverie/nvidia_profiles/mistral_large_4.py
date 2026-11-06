"""NVIDIA-hosted Mistral Large 4 request profile."""

from __future__ import annotations

from typing import Any, Dict

from .common import max_output_tokens


CONTEXT_TOKENS = 262_144
MAX_OUTPUT_TOKENS = 262_144


def build_openai_options(cfg: Dict[str, Any]) -> Dict[str, Any]:
    # The hosted recipe accepts high; none returned HTTP 400 in qualification.
    return {
        "temperature": 1.0,
        "top_p": 0.95,
        "max_tokens": max_output_tokens(cfg, maximum=MAX_OUTPUT_TOKENS),
        "extra_body": {"reasoning_effort": "high"},
    }
