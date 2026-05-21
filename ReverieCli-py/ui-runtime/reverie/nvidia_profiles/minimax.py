"""NVIDIA MiniMax profiles."""

from __future__ import annotations

from typing import Any, Dict

from .common import max_output_tokens


CONTEXT_TOKENS = 204_800


def _options(cfg: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "temperature": 1.0,
        "top_p": 0.95,
        "max_tokens": max_output_tokens(cfg),
    }


def build_m27_openai_options(cfg: Dict[str, Any]) -> Dict[str, Any]:
    return _options(cfg)
