"""NVIDIA Kimi K2.6 profile."""

from __future__ import annotations

from typing import Any, Dict

from .common import max_output_tokens


CONTEXT_TOKENS = 262_144


def build_request_defaults(cfg: Dict[str, Any]) -> Dict[str, Any]:
    thinking_enabled = bool(cfg.get("enable_thinking", True))
    return {
        "max_tokens": max_output_tokens(cfg),
        "temperature": 1.0,
        "top_p": 1.0,
        "chat_template_kwargs": {"thinking": thinking_enabled},
    }
