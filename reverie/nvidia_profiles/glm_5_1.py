"""NVIDIA GLM-5.1 profile.

Matches the NVIDIA Build sample shape: OpenAI SDK chat completions with
`chat_template_kwargs.enable_thinking` and `clear_thinking=False`.
"""

from __future__ import annotations

from typing import Any, Dict

from .common import max_output_tokens


# NVIDIA NIM's GLM-5.1 API reference currently lists 131,072 input tokens
# and 131,072 output tokens for the hosted endpoint. Some non-NVIDIA
# aggregators publish ~205K total context for GLM-5.1, but that is not the
# Build.NVIDIA.com hosted limit.
CONTEXT_TOKENS = 131_072


def build_openai_options(cfg: Dict[str, Any]) -> Dict[str, Any]:
    thinking_enabled = bool(cfg.get("enable_thinking", True))
    return {
        "temperature": 1.0,
        "top_p": 1.0,
        "max_tokens": max_output_tokens(cfg),
        "extra_body": {
            "chat_template_kwargs": {
                "enable_thinking": thinking_enabled,
                "clear_thinking": False,
            }
        },
    }
