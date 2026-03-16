"""
NVIDIA-hosted Qwen integration helpers.

This source powers the Computer Controller mode through the NVIDIA
OpenAI-compatible chat completions endpoint.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional


NVIDIA_DEFAULT_API_URL = "https://integrate.api.nvidia.com/v1"
NVIDIA_DEFAULT_MODEL_ID = "qwen/qwen3.5-397b-a17b"
NVIDIA_DEFAULT_MODEL_DISPLAY_NAME = "Qwen3.5-397B-A17B"
NVIDIA_DEFAULT_REQUEST_ENDPOINT = "/chat/completions"

_NVIDIA_MODEL_CATALOG: List[Dict[str, Any]] = [
    {
        "id": NVIDIA_DEFAULT_MODEL_ID,
        "display_name": NVIDIA_DEFAULT_MODEL_DISPLAY_NAME,
        "description": "Qwen 3.5 hosted by NVIDIA for multimodal desktop control",
        "context_length": 131072,
        "max_output_tokens": 16384,
        "vision": True,
        "thinking": True,
    }
]


def default_nvidia_config() -> Dict[str, Any]:
    """Default NVIDIA provider config stored inside Reverie config.json."""
    return {
        "enabled": True,
        "api_key": "",
        "selected_model_id": NVIDIA_DEFAULT_MODEL_ID,
        "selected_model_display_name": NVIDIA_DEFAULT_MODEL_DISPLAY_NAME,
        "api_url": NVIDIA_DEFAULT_API_URL,
        "endpoint": NVIDIA_DEFAULT_REQUEST_ENDPOINT,
        "max_context_tokens": 131072,
        "timeout": 300,
        "max_tokens": 16384,
        "temperature": 0.60,
        "top_p": 0.95,
        "top_k": 20,
        "presence_penalty": 0.0,
        "repetition_penalty": 1.0,
        "enable_thinking": True,
    }


def get_nvidia_model_catalog() -> List[Dict[str, Any]]:
    """Return the supported NVIDIA model catalog."""
    return [dict(item) for item in _NVIDIA_MODEL_CATALOG]


def normalize_nvidia_config(raw_nvidia: Any) -> Dict[str, Any]:
    """Normalize NVIDIA config for persistence and runtime usage."""
    cfg = default_nvidia_config()
    if isinstance(raw_nvidia, dict):
        cfg.update(raw_nvidia)

    cfg["api_key"] = str(cfg.get("api_key", "") or "").strip()
    cfg["selected_model_id"] = str(cfg.get("selected_model_id", NVIDIA_DEFAULT_MODEL_ID) or "").strip() or NVIDIA_DEFAULT_MODEL_ID
    cfg["selected_model_display_name"] = str(
        cfg.get("selected_model_display_name", NVIDIA_DEFAULT_MODEL_DISPLAY_NAME) or ""
    ).strip() or NVIDIA_DEFAULT_MODEL_DISPLAY_NAME

    api_url = str(cfg.get("api_url", NVIDIA_DEFAULT_API_URL) or "").strip()
    if api_url and not api_url.startswith(("http://", "https://")):
        api_url = f"https://{api_url}"
    cfg["api_url"] = api_url.rstrip("/") or NVIDIA_DEFAULT_API_URL

    endpoint = str(cfg.get("endpoint", NVIDIA_DEFAULT_REQUEST_ENDPOINT) or "").strip()
    if endpoint.lower() in {"clear", "none", "default", "off"}:
        endpoint = NVIDIA_DEFAULT_REQUEST_ENDPOINT
    cfg["endpoint"] = endpoint or NVIDIA_DEFAULT_REQUEST_ENDPOINT

    for key, default_value in (
        ("max_context_tokens", 131072),
        ("timeout", 300),
        ("max_tokens", 16384),
        ("top_k", 20),
    ):
        try:
            value = int(cfg.get(key, default_value))
        except (TypeError, ValueError):
            value = default_value
        if value <= 0:
            value = default_value
        cfg[key] = value

    for key, default_value in (
        ("temperature", 0.60),
        ("top_p", 0.95),
        ("presence_penalty", 0.0),
        ("repetition_penalty", 1.0),
    ):
        try:
            cfg[key] = float(cfg.get(key, default_value))
        except (TypeError, ValueError):
            cfg[key] = default_value

    cfg["enable_thinking"] = bool(cfg.get("enable_thinking", True))

    matched = resolve_nvidia_selected_model(cfg)
    if matched:
        cfg["selected_model_id"] = str(matched["id"])
        cfg["selected_model_display_name"] = str(matched["display_name"])
        cfg["max_context_tokens"] = int(matched.get("context_length", cfg["max_context_tokens"]))

    return cfg


def resolve_nvidia_request_url(api_url: str, endpoint: str = "") -> str:
    """Resolve the effective NVIDIA chat-completions URL."""
    base = str(api_url or "").strip().rstrip("/") or NVIDIA_DEFAULT_API_URL
    override = str(endpoint or "").strip()

    if override:
        if override.startswith(("http://", "https://")):
            return override
        if override.startswith("/"):
            return f"{base}{override}"
        return f"{base}/{override}"

    if base.lower().endswith("/chat/completions"):
        return base
    return f"{base}{NVIDIA_DEFAULT_REQUEST_ENDPOINT}"


def resolve_nvidia_selected_model(nvidia_config: Any) -> Optional[Dict[str, Any]]:
    """Resolve selected NVIDIA model metadata from config."""
    cfg = default_nvidia_config()
    if isinstance(nvidia_config, dict):
        cfg.update(nvidia_config)
    wanted = str(cfg.get("selected_model_id", NVIDIA_DEFAULT_MODEL_ID) or "").strip().lower()
    for item in get_nvidia_model_catalog():
        if str(item.get("id", "")).strip().lower() == wanted:
            return item
    return get_nvidia_model_catalog()[0]


def build_nvidia_runtime_model_data(nvidia_config: Any) -> Optional[Dict[str, Any]]:
    """Build runtime model config dict for agent initialization."""
    cfg = normalize_nvidia_config(nvidia_config)
    if not cfg.get("enabled", True):
        return None

    selected = resolve_nvidia_selected_model(cfg)
    if not selected:
        return None

    return {
        "model": selected["id"],
        "model_display_name": selected["display_name"],
        "base_url": resolve_nvidia_request_url(cfg["api_url"], cfg.get("endpoint", "")),
        "api_key": cfg.get("api_key", ""),
        "max_context_tokens": int(selected.get("context_length", cfg.get("max_context_tokens", 131072))),
        "provider": "request",
        "thinking_mode": "true" if bool(cfg.get("enable_thinking", True)) else "false",
        "endpoint": "",
        "custom_headers": {},
    }


def build_nvidia_request_defaults(nvidia_config: Any) -> Dict[str, Any]:
    """Return default request payload knobs for NVIDIA-hosted Qwen."""
    cfg = normalize_nvidia_config(nvidia_config)
    return {
        "max_tokens": int(cfg.get("max_tokens", 16384)),
        "temperature": float(cfg.get("temperature", 0.60)),
        "top_p": float(cfg.get("top_p", 0.95)),
        "top_k": int(cfg.get("top_k", 20)),
        "presence_penalty": float(cfg.get("presence_penalty", 0.0)),
        "repetition_penalty": float(cfg.get("repetition_penalty", 1.0)),
        "chat_template_kwargs": {
            "enable_thinking": bool(cfg.get("enable_thinking", True)),
        },
    }


def mask_secret(secret: str) -> str:
    """Mask secrets for safe terminal display."""
    value = str(secret or "").strip()
    if len(value) <= 8:
        return "*" * len(value)
    return f"{value[:4]}...{value[-4:]}"

