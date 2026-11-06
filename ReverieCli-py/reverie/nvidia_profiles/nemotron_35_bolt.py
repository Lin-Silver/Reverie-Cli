"""NVIDIA-hosted text-only Nemotron 3.5 Bolt E4B profile."""

from __future__ import annotations

from typing import Any, Dict

from .common import max_output_tokens


CONTEXT_TOKENS = 65_536
MAX_OUTPUT_TOKENS = 65_536


def build_openai_options(cfg: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "temperature": 1.0,
        "top_p": 0.95,
        "max_tokens": max_output_tokens(cfg, maximum=MAX_OUTPUT_TOKENS),
        "extra_body": {
            "chat_template_kwargs": {"enable_thinking": bool(cfg.get("enable_thinking", True))},
            "skip_special_tokens": False,
        },
    }
