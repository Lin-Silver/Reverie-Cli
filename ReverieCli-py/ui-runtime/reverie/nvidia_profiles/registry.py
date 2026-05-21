"""Registry for model-specific NVIDIA request profiles."""

from __future__ import annotations

import sys
from typing import Any, Callable, Dict, Optional

from . import (
    deepseek_v4,
    glm_5_1,
    gpt_oss_120b,
    kimi_k2_6,
    minimax,
    mistral_large_3,
    mistral_medium_35,
    mistral_small_4,
    nemotron_3_super,
    qwen_35,
    step_35_flash,
)


ProfileBuilder = Callable[[Dict[str, Any]], Dict[str, Any]]

_OPENAI_PROFILES: Dict[str, ProfileBuilder] = {
    "nvidia/nemotron-3-super-120b-a12b": nemotron_3_super.build_openai_options,
    "minimaxai/minimax-m2.7": minimax.build_m27_openai_options,
    "z-ai/glm-5.1": glm_5_1.build_openai_options,
    "stepfun-ai/step-3.5-flash": step_35_flash.build_openai_options,
    "deepseek-ai/deepseek-v4-pro": deepseek_v4.build_openai_options,
    "deepseek-ai/deepseek-v4-flash": deepseek_v4.build_openai_options,
    "openai/gpt-oss-120b": gpt_oss_120b.build_openai_options,
}

_REQUEST_PROFILES: Dict[str, ProfileBuilder] = {
    "mistralai/mistral-small-4-119b-2603": mistral_small_4.build_request_defaults,
    "mistralai/mistral-medium-3.5-128b": mistral_medium_35.build_request_defaults,
    "qwen/qwen3.5-122b-a10b": qwen_35.build_122b_request_defaults,
    "qwen/qwen3.5-397b-a17b": qwen_35.build_397b_request_defaults,
    "mistralai/mistral-large-3-675b-instruct-2512": mistral_large_3.build_request_defaults,
    "moonshotai/kimi-k2.6": kimi_k2_6.build_request_defaults,
}


def _model_key(model_id: Any) -> str:
    return str(model_id or "").strip().lower()


def get_profile_name(model_id: Any, *, transport: str) -> Optional[str]:
    """Return the profile module basename selected for one model id."""
    key = _model_key(model_id)
    profiles = _REQUEST_PROFILES if str(transport).strip().lower() == "request" else _OPENAI_PROFILES
    builder = profiles.get(key)
    if builder is None:
        return None
    return str(getattr(builder, "__module__", "")).rsplit(".", 1)[-1] or None


def _profile_builder(model_id: Any, *, transport: str) -> Optional[ProfileBuilder]:
    profiles = _REQUEST_PROFILES if str(transport).strip().lower() == "request" else _OPENAI_PROFILES
    return profiles.get(_model_key(model_id))


def get_context_tokens(model_id: Any, *, transport: str, fallback: Optional[int] = None) -> Optional[int]:
    """Return the profile-owned context window for one NVIDIA-hosted model."""
    builder = _profile_builder(model_id, transport=transport)
    if builder is None:
        return fallback
    module = sys.modules.get(str(getattr(builder, "__module__", "")))
    value = getattr(module, "CONTEXT_TOKENS", fallback) if module is not None else fallback
    try:
        return int(value) if value is not None else fallback
    except (TypeError, ValueError):
        return fallback


def build_openai_options(model_id: Any, cfg: Dict[str, Any]) -> Dict[str, Any]:
    """Build model-specific OpenAI SDK kwargs for a NVIDIA-hosted model."""
    builder = _OPENAI_PROFILES.get(_model_key(model_id))
    if not builder:
        return {}
    return dict(builder(dict(cfg or {})))


def build_request_defaults(model_id: Any, cfg: Dict[str, Any]) -> Dict[str, Any]:
    """Build model-specific raw request defaults for a NVIDIA-hosted model."""
    builder = _REQUEST_PROFILES.get(_model_key(model_id))
    if not builder:
        return {}
    return dict(builder(dict(cfg or {})))
