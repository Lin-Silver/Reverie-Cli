"""OpenCode Zen free-model source helpers."""

from __future__ import annotations

import os
from typing import Any, Dict, List, Optional


OPENCODE_DEFAULT_API_URL = "https://opencode.ai/zen/v1"
OPENCODE_DEFAULT_ENDPOINT = "/chat/completions"
OPENCODE_DEFAULT_MODELS_URL = "https://opencode.ai/zen/v1/models"
OPENCODE_DEFAULT_MODEL_ID = "deepseek-v4-flash-free"
OPENCODE_DEFAULT_MODEL_DISPLAY_NAME = "DeepSeek V4 Flash Free"
OPENCODE_API_KEY_HINT_URL = "https://opencode.ai/zen"
OPENCODE_DEFAULT_CONTEXT_TOKENS = 128_000
OPENCODE_DEFAULT_MAX_TOKENS = 16_384
OPENCODE_DEFAULT_TEMPERATURE = 0.7
OPENCODE_DEFAULT_TOP_P = 1.0


def _opencode_model(
    model_id: str,
    display_name: str,
    description: str,
    *,
    context_length: int = OPENCODE_DEFAULT_CONTEXT_TOKENS,
    max_output_tokens: int = OPENCODE_DEFAULT_MAX_TOKENS,
    vision: bool = False,
) -> Dict[str, Any]:
    return {
        "id": str(model_id or "").strip(),
        "display_name": str(display_name or model_id or "").strip(),
        "description": str(description or "").strip(),
        "transport": "openai-chat",
        "context_length": int(context_length or OPENCODE_DEFAULT_CONTEXT_TOKENS),
        "max_output_tokens": int(max_output_tokens or OPENCODE_DEFAULT_MAX_TOKENS),
        "vision": bool(vision),
        "thinking": True,
        "tool_calling": True,
        "free": True,
    }


_OPENCODE_MODEL_CATALOG: List[Dict[str, Any]] = [
    _opencode_model(
        "big-pickle",
        "Big Pickle",
        "OpenCode Zen stealth free model exposed through chat.completions.",
    ),
    _opencode_model(
        "deepseek-v4-flash-free",
        "DeepSeek V4 Flash Free",
        "OpenCode Zen free DeepSeek V4 Flash chat.completions model.",
    ),
    _opencode_model(
        "mimo-v2.5-free",
        "MiMo-V2.5 Free",
        "OpenCode Zen free MiMo-V2.5 chat.completions model.",
    ),
    _opencode_model(
        "north-mini-code-free",
        "North Mini Code Free",
        "OpenCode Zen free North Mini Code chat.completions model.",
    ),
    _opencode_model(
        "nemotron-3-ultra-free",
        "Nemotron 3 Ultra Free",
        "OpenCode Zen free Nemotron 3 Ultra chat.completions model.",
    ),
    _opencode_model(
        "hy3-free",
        "Hy3 Free",
        "OpenCode Zen hidden free model id listed by the live /zen/v1/models endpoint.",
    ),
]

_OPENCODE_MODEL_METADATA = {
    str(item["id"]).strip().lower(): dict(item) for item in _OPENCODE_MODEL_CATALOG
}


def default_opencode_config() -> Dict[str, Any]:
    """Default OpenCode source config stored in config.json."""
    return {
        "enabled": True,
        "api_key": "",
        "selected_model_id": OPENCODE_DEFAULT_MODEL_ID,
        "selected_model_display_name": OPENCODE_DEFAULT_MODEL_DISPLAY_NAME,
        "api_url": OPENCODE_DEFAULT_API_URL,
        "endpoint": OPENCODE_DEFAULT_ENDPOINT,
        "max_context_tokens": OPENCODE_DEFAULT_CONTEXT_TOKENS,
        "timeout": 60,
        "max_tokens": OPENCODE_DEFAULT_MAX_TOKENS,
        "temperature": OPENCODE_DEFAULT_TEMPERATURE,
        "top_p": OPENCODE_DEFAULT_TOP_P,
    }


def get_opencode_model_catalog() -> List[Dict[str, Any]]:
    """Return the supported OpenCode free-model catalog."""
    return [dict(item) for item in _OPENCODE_MODEL_CATALOG]


def get_opencode_model_metadata(model_id: Any) -> Optional[Dict[str, Any]]:
    """Return metadata for one OpenCode model id."""
    wanted = str(model_id or "").strip().lower()
    if not wanted:
        return None
    found = _OPENCODE_MODEL_METADATA.get(wanted)
    return dict(found) if found else None


def resolve_opencode_selected_model(opencode_config: Any, model_id: Optional[str] = None) -> Optional[Dict[str, Any]]:
    """Resolve selected OpenCode model metadata from config or override."""
    cfg = default_opencode_config()
    if isinstance(opencode_config, dict):
        cfg.update(opencode_config)

    wanted = str(model_id or cfg.get("selected_model_id", OPENCODE_DEFAULT_MODEL_ID) or "").strip().lower()
    matched = get_opencode_model_metadata(wanted)
    if matched:
        return matched
    return get_opencode_model_catalog()[0]


def resolve_opencode_sdk_base_url(api_url: Any) -> str:
    """Resolve an OpenAI-compatible `/v1` base URL for OpenCode Zen."""
    base = str(api_url or "").strip()
    if not base:
        return OPENCODE_DEFAULT_API_URL
    if not base.startswith(("http://", "https://")):
        base = f"https://{base}"
    base = base.rstrip("/")
    lower_base = base.lower()
    for suffix in (
        "/chat/completions",
        "/v1/chat/completions",
        "/models",
        "/v1/models",
    ):
        if lower_base.endswith(suffix):
            base = base[: -len(suffix)]
            lower_base = base.lower()
    if lower_base.endswith("/v1"):
        return base
    return f"{base}/v1"


def resolve_opencode_request_url(api_url: Any, endpoint: Any = "") -> str:
    """Resolve the concrete chat-completions request URL."""
    candidate_endpoint = str(endpoint or "").strip() or OPENCODE_DEFAULT_ENDPOINT
    if candidate_endpoint.startswith(("http://", "https://")):
        return candidate_endpoint
    base = resolve_opencode_sdk_base_url(api_url).rstrip("/")
    if candidate_endpoint.startswith("/"):
        return f"{base}{candidate_endpoint}"
    return f"{base}/{candidate_endpoint}"


def resolve_opencode_api_key(opencode_config: Any) -> str:
    """Resolve the effective OpenCode API key from config or environment."""
    cfg = default_opencode_config()
    if isinstance(opencode_config, dict):
        cfg.update(opencode_config)

    key = str(cfg.get("api_key", "") or "").strip()
    if key:
        return key
    for env_name in ("OPENCODE_API_KEY", "OPENCODE_TOKEN"):
        value = str(os.getenv(env_name, "") or "").strip()
        if value:
            return value
    return ""


def normalize_opencode_config(raw_opencode: Any) -> Dict[str, Any]:
    """Normalize OpenCode config for persistence and runtime usage."""
    cfg = default_opencode_config()
    if isinstance(raw_opencode, dict):
        cfg.update(raw_opencode)

    cfg["enabled"] = bool(cfg.get("enabled", True))
    cfg["api_key"] = str(cfg.get("api_key", "") or "").strip()
    cfg["api_url"] = resolve_opencode_sdk_base_url(cfg.get("api_url", OPENCODE_DEFAULT_API_URL))
    cfg["endpoint"] = OPENCODE_DEFAULT_ENDPOINT
    cfg["selected_model_id"] = (
        str(cfg.get("selected_model_id", OPENCODE_DEFAULT_MODEL_ID) or "").strip()
        or OPENCODE_DEFAULT_MODEL_ID
    )
    cfg["selected_model_display_name"] = (
        str(cfg.get("selected_model_display_name", OPENCODE_DEFAULT_MODEL_DISPLAY_NAME) or "").strip()
        or OPENCODE_DEFAULT_MODEL_DISPLAY_NAME
    )

    for key, default_value in (
        ("max_context_tokens", OPENCODE_DEFAULT_CONTEXT_TOKENS),
        ("timeout", 60),
        ("max_tokens", OPENCODE_DEFAULT_MAX_TOKENS),
    ):
        try:
            value = int(cfg.get(key, default_value))
        except (TypeError, ValueError):
            value = default_value
        if value <= 0:
            value = default_value
        cfg[key] = value

    for key, default_value in (
        ("temperature", OPENCODE_DEFAULT_TEMPERATURE),
        ("top_p", OPENCODE_DEFAULT_TOP_P),
    ):
        try:
            cfg[key] = float(cfg.get(key, default_value))
        except (TypeError, ValueError):
            cfg[key] = default_value

    matched = resolve_opencode_selected_model(cfg)
    if matched:
        cfg["selected_model_id"] = str(matched["id"])
        cfg["selected_model_display_name"] = str(matched["display_name"])
        context_length = matched.get("context_length")
        if context_length:
            cfg["max_context_tokens"] = int(context_length)
        output_limit = int(matched.get("max_output_tokens") or OPENCODE_DEFAULT_MAX_TOKENS)
        cfg["max_tokens"] = min(int(cfg.get("max_tokens") or output_limit), output_limit)

    return cfg


def build_opencode_runtime_model_data(opencode_config: Any, model_id: Optional[str] = None) -> Optional[Dict[str, Any]]:
    """Build runtime model config dict for agent initialization."""
    cfg = normalize_opencode_config(opencode_config)
    if not cfg.get("enabled", True):
        return None

    selected = resolve_opencode_selected_model(cfg, model_id=model_id)
    if not selected:
        return None

    return {
        "model": selected["id"],
        "model_display_name": selected["display_name"],
        "base_url": resolve_opencode_sdk_base_url(cfg.get("api_url", OPENCODE_DEFAULT_API_URL)),
        "api_key": resolve_opencode_api_key(cfg),
        "max_context_tokens": int(selected.get("context_length") or cfg.get("max_context_tokens", OPENCODE_DEFAULT_CONTEXT_TOKENS)),
        "provider": "openai-chat",
        "supports_vision": bool(selected.get("vision", False)),
        "thinking_mode": None,
        "endpoint": str(cfg.get("endpoint", OPENCODE_DEFAULT_ENDPOINT) or OPENCODE_DEFAULT_ENDPOINT),
        "custom_headers": {},
        "vision": bool(selected.get("vision", False)),
    }


def build_opencode_openai_options(opencode_config: Any, model_id: Optional[str] = None) -> Dict[str, Any]:
    """Return OpenAI-compatible request options for OpenCode chat completions."""
    cfg = normalize_opencode_config(opencode_config)
    selected = resolve_opencode_selected_model(cfg, model_id=model_id)
    output_limit = int((selected or {}).get("max_output_tokens") or OPENCODE_DEFAULT_MAX_TOKENS)
    try:
        max_tokens = int(cfg.get("max_tokens", OPENCODE_DEFAULT_MAX_TOKENS))
    except (TypeError, ValueError):
        max_tokens = OPENCODE_DEFAULT_MAX_TOKENS
    if max_tokens <= 0:
        max_tokens = OPENCODE_DEFAULT_MAX_TOKENS
    return {
        "temperature": float(cfg.get("temperature", OPENCODE_DEFAULT_TEMPERATURE)),
        "top_p": float(cfg.get("top_p", OPENCODE_DEFAULT_TOP_P)),
        "max_tokens": min(max_tokens, output_limit),
    }


def mask_secret(secret: str) -> str:
    """Mask secrets for safe terminal display."""
    value = str(secret or "").strip()
    if not value:
        return "(not set)"
    if len(value) <= 8:
        return "*" * len(value)
    return f"{value[:4]}...{value[-4:]}"
