"""NVIDIA MiniMax profiles."""

from __future__ import annotations

from typing import Any, Dict

from .common import max_output_tokens


M3_CONTEXT_TOKENS = 1_000_000
M3_MAX_OUTPUT_TOKENS = 8_192


def build_m3_request_defaults(cfg: Dict[str, Any]) -> Dict[str, Any]:
    effort = str(cfg.get("reasoning_effort", "high") or "high").strip().lower()
    thinking_mode = "disabled" if effort == "none" else "enabled"
    return {
        "temperature": 1.0,
        "top_p": 0.95,
        "max_tokens": max_output_tokens(cfg, default=M3_MAX_OUTPUT_TOKENS, maximum=M3_MAX_OUTPUT_TOKENS),
        "chat_template_kwargs": {"thinking_mode": thinking_mode},
    }
