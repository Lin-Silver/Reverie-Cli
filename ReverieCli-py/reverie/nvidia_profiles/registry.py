"""Registry for model-specific NVIDIA request profiles."""

from __future__ import annotations

import sys
from typing import Any, Callable, Dict, Optional

from . import (
    deepseek_v4_flash_0731,
    deepseek_v4_pro_0813,
    gpt_oss_120b,
    kimi_k3,
    minimax,
    muse_glimmer,
    nemotron_3_super,
    nemotron_3_ultra,
    nemotron_35_lightning,
    step_37_flash,
)


ProfileBuilder = Callable[[Dict[str, Any]], Dict[str, Any]]

_OPENAI_PROFILES: Dict[str, ProfileBuilder] = {
    "deepseek-ai/deepseek-v4-flash-0731": deepseek_v4_flash_0731.build_openai_options,
    "deepseek-ai/deepseek-v4-pro-0813": deepseek_v4_pro_0813.build_openai_options,
    "moonshotai/kimi-k3": kimi_k3.build_openai_options,
    "meta/muse-glimmer-30b": muse_glimmer.build_openai_options,
    "nvidia/nemotron-3.5-lightning-30b-a3b": nemotron_35_lightning.build_openai_options,
    "nvidia/nemotron-3-super-120b-a12b": nemotron_3_super.build_openai_options,
    "nvidia/nemotron-3-ultra-550b-a55b": nemotron_3_ultra.build_openai_options,
    "openai/gpt-oss-120b": gpt_oss_120b.build_openai_options,
}

_REQUEST_PROFILES: Dict[str, ProfileBuilder] = {
    "minimaxai/minimax-m3": minimax.build_m3_request_defaults,
    "stepfun-ai/step-3.7-flash": step_37_flash.build_request_defaults,
}

_CONTEXT_OVERRIDES: Dict[str, int] = {
    "minimaxai/minimax-m3": minimax.M3_CONTEXT_TOKENS,
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
    key = _model_key(model_id)
    if key in _CONTEXT_OVERRIDES:
        return _CONTEXT_OVERRIDES[key]
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
