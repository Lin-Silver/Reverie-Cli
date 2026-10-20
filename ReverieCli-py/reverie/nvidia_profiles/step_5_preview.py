"""NVIDIA-hosted Step 5 Preview request profile."""

from __future__ import annotations

from typing import Any, Dict

from .common import max_output_tokens


CONTEXT_TOKENS = 1_048_576
MAX_OUTPUT_TOKENS = 1_048_576


def build_request_defaults(cfg: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "temperature": 1.0,
        "top_p": 0.95,
        "top_k": 0,
        "max_tokens": max_output_tokens(cfg, default=4_096, maximum=MAX_OUTPUT_TOKENS),
    }
