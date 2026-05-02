"""NVIDIA Qwen3.5 profiles."""

from __future__ import annotations

from typing import Any, Dict

from .common import max_output_tokens


CONTEXT_TOKENS = 262_144


def _thinking_enabled(cfg: Dict[str, Any]) -> bool:
    return bool(cfg.get("enable_thinking", True))


def build_122b_request_defaults(cfg: Dict[str, Any]) -> Dict[str, Any]:
    thinking_enabled = _thinking_enabled(cfg)
    return {
        "max_tokens": max_output_tokens(cfg),
        "temperature": 0.60 if thinking_enabled else 0.70,
        "top_p": 0.95 if thinking_enabled else 0.80,
        "chat_template_kwargs": {"enable_thinking": thinking_enabled},
    }


def build_397b_request_defaults(cfg: Dict[str, Any]) -> Dict[str, Any]:
    thinking_enabled = _thinking_enabled(cfg)
    return {
        "max_tokens": max_output_tokens(cfg),
        "temperature": 0.60 if thinking_enabled else 0.70,
        "top_p": 0.95 if thinking_enabled else 0.80,
        "top_k": 20,
        "presence_penalty": 0.0 if thinking_enabled else 1.5,
        "repetition_penalty": 1.0,
        "chat_template_kwargs": {"enable_thinking": thinking_enabled},
    }
