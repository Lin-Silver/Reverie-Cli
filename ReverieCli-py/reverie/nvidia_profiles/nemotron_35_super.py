"""NVIDIA-hosted Nemotron 3.5 Super VL profile."""

from __future__ import annotations

from typing import Any, Dict

from .common import max_output_tokens


CONTEXT_TOKENS = 262_144
MAX_OUTPUT_TOKENS = 131_072


def build_openai_options(cfg: Dict[str, Any]) -> Dict[str, Any]:
    effort = str(cfg.get("reasoning_effort", "high") or "high").strip().lower()
    return {
        "temperature": 0.6 if cfg.get("has_visual_input") else 1.0,
        "top_p": 0.95,
        "max_tokens": max_output_tokens(cfg, maximum=MAX_OUTPUT_TOKENS),
        "extra_body": {"reasoning_effort": effort},
    }
