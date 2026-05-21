"""NVIDIA Mistral Medium 3.5 profile."""

from __future__ import annotations

from typing import Any, Dict

from .common import max_output_tokens


CONTEXT_TOKENS = 262_144


def build_request_defaults(cfg: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "max_tokens": max_output_tokens(cfg),
        "temperature": 0.70,
        "top_p": 1.00,
        "reasoning_effort": str(cfg.get("reasoning_effort", "high") or "high").strip().lower(),
    }
