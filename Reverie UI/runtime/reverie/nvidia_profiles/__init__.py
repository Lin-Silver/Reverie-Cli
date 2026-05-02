"""Model-specific NVIDIA request profiles.

Each module in this package owns the request shape for one NVIDIA-hosted
model family.  The agent selects a profile by model id instead of forcing every
model through one generic OpenAI-compatible payload.
"""

from .registry import build_openai_options, build_request_defaults, get_context_tokens, get_profile_name

__all__ = [
    "build_openai_options",
    "build_request_defaults",
    "get_context_tokens",
    "get_profile_name",
]
