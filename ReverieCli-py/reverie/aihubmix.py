"""AIhubMix OpenAI-compatible source helpers."""

from __future__ import annotations

import os
from typing import Any, Dict, List, Optional


AIHUBMIX_DEFAULT_API_URL = "https://aihubmix.com/v1"
AIHUBMIX_DEFAULT_MODEL_ID = "gpt-5.5-free"
AIHUBMIX_DEFAULT_MODEL_DISPLAY_NAME = "GPT-5.5 Free"
AIHUBMIX_API_KEY_HINT_URL = "https://aihubmix.com"
AIHUBMIX_DEFAULT_CONTEXT_TOKENS = 128_000
AIHUBMIX_DEFAULT_MAX_TOKENS = 16_384
AIHUBMIX_DEFAULT_TEMPERATURE = 0.7
AIHUBMIX_DEFAULT_TOP_P = 1.0


def _aihubmix_model(
    model_id: str,
    display_name: str,
    description: str,
    *,
    context_length: int = AIHUBMIX_DEFAULT_CONTEXT_TOKENS,
    max_output_tokens: int = AIHUBMIX_DEFAULT_MAX_TOKENS,
    reasoning_variant: str = "",
    vision: bool = False,
) -> Dict[str, Any]:
    return {
        "id": model_id,
        "display_name": display_name,
        "description": description,
        "transport": "openai-sdk",
        "context_length": int(context_length),
        "max_output_tokens": int(max_output_tokens),
        "reasoning_variant": str(reasoning_variant or "").strip(),
        "vision": bool(vision),
        "thinking": bool(reasoning_variant and str(reasoning_variant).strip().lower() != "none"),
        "tool_calling": True,
    }


_AIHUBMIX_MODEL_CATALOG: List[Dict[str, Any]] = [
    _aihubmix_model(
        "gpt-5.5-free",
        "GPT-5.5 Free",
        "AIhubMix OpenAI-compatible chat completions model with provider default reasoning depth.",
        reasoning_variant="none",
    ),
    _aihubmix_model(
        "gpt-5.5-free-high",
        "GPT-5.5 Free High",
        "AIhubMix GPT-5.5 free high-reasoning variant.",
        reasoning_variant="high",
    ),
    _aihubmix_model(
        "gpt-5.5-free-low",
        "GPT-5.5 Free Low",
        "AIhubMix GPT-5.5 free low-reasoning variant.",
        reasoning_variant="low",
    ),
    _aihubmix_model(
        "gpt-4o-free",
        "GPT-4o Free",
        "AIhubMix GPT-4o free OpenAI-compatible chat completions model.",
    ),
    _aihubmix_model(
        "gpt-4.1-free",
        "GPT-4.1 Free",
        "AIhubMix GPT-4.1 free OpenAI-compatible chat completions model.",
    ),
]

_AIHUBMIX_MODEL_METADATA = {
    str(item["id"]).strip().lower(): dict(item) for item in _AIHUBMIX_MODEL_CATALOG
}


def default_aihubmix_config() -> Dict[str, Any]:
    """Default AIhubMix provider config stored in config.json."""
    return {
        "enabled": True,
        "api_key": "",
        "selected_model_id": AIHUBMIX_DEFAULT_MODEL_ID,
        "selected_model_display_name": AIHUBMIX_DEFAULT_MODEL_DISPLAY_NAME,
        "api_url": AIHUBMIX_DEFAULT_API_URL,
        "endpoint": "",
        "max_context_tokens": AIHUBMIX_DEFAULT_CONTEXT_TOKENS,
        "timeout": 60,
        "max_tokens": AIHUBMIX_DEFAULT_MAX_TOKENS,
        "temperature": AIHUBMIX_DEFAULT_TEMPERATURE,
        "top_p": AIHUBMIX_DEFAULT_TOP_P,
    }


def get_aihubmix_model_catalog() -> List[Dict[str, Any]]:
    """Return the supported AIhubMix model catalog."""
    return [dict(item) for item in _AIHUBMIX_MODEL_CATALOG]


def get_aihubmix_model_metadata(model_id: Any) -> Optional[Dict[str, Any]]:
    """Return metadata for one AIhubMix model id."""
    wanted = str(model_id or "").strip().lower()
    if not wanted:
        return None
    found = _AIHUBMIX_MODEL_METADATA.get(wanted)
    return dict(found) if found else None


def resolve_aihubmix_selected_model(aihubmix_config: Any, model_id: Optional[str] = None) -> Optional[Dict[str, Any]]:
    """Resolve selected AIhubMix model metadata from config or override."""
    cfg = default_aihubmix_config()
    if isinstance(aihubmix_config, dict):
        cfg.update(aihubmix_config)

    wanted = str(model_id or cfg.get("selected_model_id", AIHUBMIX_DEFAULT_MODEL_ID) or "").strip().lower()
    matched = get_aihubmix_model_metadata(wanted)
    if matched:
        return matched
    return get_aihubmix_model_catalog()[0]


def resolve_aihubmix_sdk_base_url(api_url: Any) -> str:
    """Resolve an OpenAI SDK base URL for AIhubMix."""
    base = str(api_url or "").strip()
    if not base:
        return AIHUBMIX_DEFAULT_API_URL
    if not base.startswith(("http://", "https://")):
        base = f"https://{base}"
    base = base.rstrip("/")
    lower_base = base.lower()
    for suffix in ("/chat/completions", "/v1/chat/completions"):
        if lower_base.endswith(suffix):
            base = base[: -len(suffix)]
            lower_base = base.lower()
    if lower_base.endswith("/v1"):
        return base
    return f"{base}/v1"


def resolve_aihubmix_api_key(aihubmix_config: Any) -> str:
    """Resolve the effective AIhubMix API key from config or environment."""
    cfg = default_aihubmix_config()
    if isinstance(aihubmix_config, dict):
        cfg.update(aihubmix_config)

    key = str(cfg.get("api_key", "") or "").strip()
    if key:
        return key
    for env_name in ("AIHUBMIX_API_KEY", "AIHUBMIX_TOKEN"):
        value = str(os.getenv(env_name, "") or "").strip()
        if value:
            return value
    return ""


def normalize_aihubmix_config(raw_aihubmix: Any) -> Dict[str, Any]:
    """Normalize AIhubMix config for persistence and runtime usage."""
    cfg = default_aihubmix_config()
    if isinstance(raw_aihubmix, dict):
        cfg.update(raw_aihubmix)

    cfg["api_key"] = str(cfg.get("api_key", "") or "").strip()
    cfg["api_url"] = resolve_aihubmix_sdk_base_url(cfg.get("api_url", AIHUBMIX_DEFAULT_API_URL))
    cfg["endpoint"] = str(cfg.get("endpoint", "") or "").strip()
    cfg["selected_model_id"] = (
        str(cfg.get("selected_model_id", AIHUBMIX_DEFAULT_MODEL_ID) or "").strip()
        or AIHUBMIX_DEFAULT_MODEL_ID
    )
    cfg["selected_model_display_name"] = (
        str(cfg.get("selected_model_display_name", AIHUBMIX_DEFAULT_MODEL_DISPLAY_NAME) or "").strip()
        or AIHUBMIX_DEFAULT_MODEL_DISPLAY_NAME
    )

    for key, default_value in (
        ("max_context_tokens", AIHUBMIX_DEFAULT_CONTEXT_TOKENS),
        ("timeout", 60),
        ("max_tokens", AIHUBMIX_DEFAULT_MAX_TOKENS),
    ):
        try:
            value = int(cfg.get(key, default_value))
        except (TypeError, ValueError):
            value = default_value
        if value <= 0:
            value = default_value
        cfg[key] = value

    for key, default_value in (
        ("temperature", AIHUBMIX_DEFAULT_TEMPERATURE),
        ("top_p", AIHUBMIX_DEFAULT_TOP_P),
    ):
        try:
            cfg[key] = float(cfg.get(key, default_value))
        except (TypeError, ValueError):
            cfg[key] = default_value

    matched = resolve_aihubmix_selected_model(cfg)
    if matched:
        cfg["selected_model_id"] = str(matched["id"])
        cfg["selected_model_display_name"] = str(matched["display_name"])
        context_length = matched.get("context_length")
        if context_length:
            cfg["max_context_tokens"] = int(context_length)
        output_limit = int(matched.get("max_output_tokens") or AIHUBMIX_DEFAULT_MAX_TOKENS)
        cfg["max_tokens"] = min(int(cfg.get("max_tokens") or output_limit), output_limit)

    return cfg


def build_aihubmix_runtime_model_data(aihubmix_config: Any, model_id: Optional[str] = None) -> Optional[Dict[str, Any]]:
    """Build runtime model config dict for agent initialization."""
    cfg = normalize_aihubmix_config(aihubmix_config)
    if not cfg.get("enabled", True):
        return None

    api_key = resolve_aihubmix_api_key(cfg)
    if not api_key:
        return None

    selected = resolve_aihubmix_selected_model(cfg, model_id=model_id)
    if not selected:
        return None

    return {
        "model": selected["id"],
        "model_display_name": selected["display_name"],
        "base_url": resolve_aihubmix_sdk_base_url(cfg.get("api_url", AIHUBMIX_DEFAULT_API_URL)),
        "api_key": api_key,
        "max_context_tokens": int(selected.get("context_length") or cfg.get("max_context_tokens", AIHUBMIX_DEFAULT_CONTEXT_TOKENS)),
        "provider": "openai-sdk",
        "supports_vision": bool(selected.get("vision", False)),
        "thinking_mode": None,
        "endpoint": str(cfg.get("endpoint", "") or ""),
        "custom_headers": {},
        "vision": bool(selected.get("vision", False)),
    }


def build_aihubmix_openai_options(aihubmix_config: Any, model_id: Optional[str] = None) -> Dict[str, Any]:
    """Return OpenAI SDK request options for AIhubMix chat completions."""
    cfg = normalize_aihubmix_config(aihubmix_config)
    selected = resolve_aihubmix_selected_model(cfg, model_id=model_id)
    output_limit = int((selected or {}).get("max_output_tokens") or AIHUBMIX_DEFAULT_MAX_TOKENS)
    try:
        max_tokens = int(cfg.get("max_tokens", AIHUBMIX_DEFAULT_MAX_TOKENS))
    except (TypeError, ValueError):
        max_tokens = AIHUBMIX_DEFAULT_MAX_TOKENS
    if max_tokens <= 0:
        max_tokens = AIHUBMIX_DEFAULT_MAX_TOKENS
    return {
        "temperature": float(cfg.get("temperature", AIHUBMIX_DEFAULT_TEMPERATURE)),
        "top_p": float(cfg.get("top_p", AIHUBMIX_DEFAULT_TOP_P)),
        "max_tokens": min(max_tokens, output_limit),
    }


def mask_secret(secret: str) -> str:
    """Mask secrets for safe terminal display."""
    value = str(secret or "").strip()
    if len(value) <= 8:
        return "*" * len(value)
    return f"{value[:4]}...{value[-4:]}"
