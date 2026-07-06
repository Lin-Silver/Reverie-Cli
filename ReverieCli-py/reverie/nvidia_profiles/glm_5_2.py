"""NVIDIA GLM-5.2 profile.

Matches NVIDIA's OpenAI-compatible chat-completions example for
`z-ai/glm-5.2`: plain sampling controls plus per-call `max_tokens`.
"""

from __future__ import annotations

from typing import Any, Dict

from .common import max_output_tokens


CONTEXT_TOKENS = 1_000_000
MAX_OUTPUT_TOKENS = 32_768


def build_openai_options(cfg: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "temperature": 1.0,
        "top_p": 1.0,
        "max_tokens": max_output_tokens(cfg, maximum=MAX_OUTPUT_TOKENS),
    }
