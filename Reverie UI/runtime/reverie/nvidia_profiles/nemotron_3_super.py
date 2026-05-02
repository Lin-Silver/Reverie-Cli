"""NVIDIA Nemotron 3 Super profile."""

from __future__ import annotations

from typing import Any, Dict

from .common import max_output_tokens


CONTEXT_TOKENS = 1_000_000


def build_openai_options(cfg: Dict[str, Any]) -> Dict[str, Any]:
    effort = str(cfg.get("reasoning_effort", "high") or "high").strip().lower()
    chat_template_kwargs: Dict[str, Any] = {
        "enable_thinking": effort != "none",
        "force_nonempty_content": True,
    }
    if effort == "low":
        chat_template_kwargs["low_effort"] = True

    return {
        "temperature": 1.0,
        "top_p": 0.95,
        "max_tokens": max_output_tokens(cfg),
        "extra_body": {
            "chat_template_kwargs": chat_template_kwargs,
        },
    }
