"""SenseNova OpenAI-compatible source helpers."""

from __future__ import annotations

import os
from typing import Any, Dict, List, Optional


SENSENOVA_DEFAULT_API_URL = "https://token.sensenova.cn/v1"
SENSENOVA_DEFAULT_MODEL_ID = "deepseek-v4-flash"
SENSENOVA_DEFAULT_MODEL_DISPLAY_NAME = "DeepSeek V4 Flash"
SENSENOVA_DEFAULT_CONTEXT_TOKENS = 1_000_000
SENSENOVA_DEFAULT_MAX_TOKENS = 65_536
SENSENOVA_DEFAULT_TEMPERATURE = 0.6
SENSENOVA_DEFAULT_TOP_P = 0.95
SENSENOVA_DEFAULT_REASONING_EFFORT = "medium"
SENSENOVA_REASONING_EFFORTS = ("none", "low", "medium", "high")


def _sensenova_model(
    model_id: str,
    display_name: str,
    description: str,
    *,
    context_length: int = SENSENOVA_DEFAULT_CONTEXT_TOKENS,
    max_output_tokens: int = SENSENOVA_DEFAULT_MAX_TOKENS,
    vision: bool = False,
    thinking: bool = True,
) -> Dict[str, Any]:
    return {
        "id": model_id,
        "display_name": display_name,
        "description": description,
        "transport": "openai-sdk",
        "context_length": int(context_length),
        "max_output_tokens": int(max_output_tokens),
        "vision": bool(vision),
        "thinking": bool(thinking),
        "tool_calling": True,
        "thinking_control": "effort" if thinking else "none",
        "thinking_options": [
            {
                "id": "none",
                "label": "Non-think",
                "description": "Disable reasoning tokens for faster direct replies.",
            },
            {
                "id": "low",
                "label": "Low",
                "description": "Low-effort reasoning with lower latency.",
            },
            {
                "id": "medium",
                "label": "Medium",
                "description": "Provider-recommended balanced reasoning.",
            },
            {
                "id": "high",
                "label": "High",
                "description": "Detailed reasoning for complex prompts.",
            },
        ]
        if thinking
        else [],
        "default_thinking_choice": SENSENOVA_DEFAULT_REASONING_EFFORT if thinking else "",
    }


_SENSENOVA_MODEL_CATALOG: List[Dict[str, Any]] = [
    _sensenova_model(
        "deepseek-v4-flash",
        "DeepSeek V4 Flash",
        "SenseNova DeepSeek V4 Flash with 1M context and selectable reasoning_effort.",
    ),
    _sensenova_model(
        "sensenova-6.7-flash-lite",
        "SenseNova 6.7 Flash Lite",
        "SenseNova lightweight OpenAI-compatible flash model.",
        context_length=262_144,
        vision=True,
    ),
]

_SENSENOVA_MODEL_METADATA = {
    str(item["id"]).strip().lower(): dict(item) for item in _SENSENOVA_MODEL_CATALOG
}


def normalize_sensenova_reasoning_effort(value: Any) -> str:
    text = str(value or "").strip().lower().replace("_", "-")
    aliases = {
        "": SENSENOVA_DEFAULT_REASONING_EFFORT,
        "default": SENSENOVA_DEFAULT_REASONING_EFFORT,
        "auto": SENSENOVA_DEFAULT_REASONING_EFFORT,
        "normal": SENSENOVA_DEFAULT_REASONING_EFFORT,
        "off": "none",
        "false": "none",
        "0": "none",
        "no": "none",
        "non-think": "none",
        "nonthink": "none",
        "no-thinking": "none",
        "light": "low",
        "med": "medium",
    }
    normalized = aliases.get(text, text)
    if normalized not in SENSENOVA_REASONING_EFFORTS:
        normalized = SENSENOVA_DEFAULT_REASONING_EFFORT
    return normalized


def default_sensenova_config() -> Dict[str, Any]:
    return {
        "enabled": True,
        "api_key": "",
        "selected_model_id": SENSENOVA_DEFAULT_MODEL_ID,
        "selected_model_display_name": SENSENOVA_DEFAULT_MODEL_DISPLAY_NAME,
        "api_url": SENSENOVA_DEFAULT_API_URL,
        "endpoint": "",
        "max_context_tokens": SENSENOVA_DEFAULT_CONTEXT_TOKENS,
        "timeout": 300,
        "max_tokens": SENSENOVA_DEFAULT_MAX_TOKENS,
        "temperature": SENSENOVA_DEFAULT_TEMPERATURE,
        "top_p": SENSENOVA_DEFAULT_TOP_P,
        "reasoning_effort": SENSENOVA_DEFAULT_REASONING_EFFORT,
    }


def get_sensenova_model_catalog() -> List[Dict[str, Any]]:
    return [dict(item) for item in _SENSENOVA_MODEL_CATALOG]


def get_sensenova_model_metadata(model_id: Any) -> Optional[Dict[str, Any]]:
    wanted = str(model_id or "").strip().lower()
    if not wanted:
        return None
    found = _SENSENOVA_MODEL_METADATA.get(wanted)
    return dict(found) if found else None


def resolve_sensenova_selected_model(sensenova_config: Any, model_id: Optional[str] = None) -> Optional[Dict[str, Any]]:
    cfg = default_sensenova_config()
    if isinstance(sensenova_config, dict):
        cfg.update(sensenova_config)
    wanted = str(model_id or cfg.get("selected_model_id", SENSENOVA_DEFAULT_MODEL_ID) or "").strip().lower()
    matched = get_sensenova_model_metadata(wanted)
    if matched:
        return matched
    return get_sensenova_model_catalog()[0]


def resolve_sensenova_sdk_base_url(api_url: Any) -> str:
    base = str(api_url or "").strip().rstrip("/")
    if not base:
        return SENSENOVA_DEFAULT_API_URL
    if not base.startswith(("http://", "https://")):
        base = f"https://{base}"
    lower = base.lower()
    if lower.endswith("/chat/completions"):
        base = base[: -len("/chat/completions")]
    return base.rstrip("/")


def resolve_sensenova_api_key(sensenova_config: Any) -> str:
    cfg = default_sensenova_config()
    if isinstance(sensenova_config, dict):
        cfg.update(sensenova_config)
    key = str(cfg.get("api_key", "") or "").strip()
    if key:
        return key
    return str(os.getenv("SENSENOVA_API_KEY") or os.getenv("SENSE_API_KEY") or "").strip()


def mask_secret(value: Any) -> str:
    text = str(value or "").strip()
    if not text:
        return "(not set)"
    if len(text) <= 8:
        return "***"
    return f"{text[:4]}***{text[-4:]}"


def normalize_sensenova_config(raw_sensenova: Any) -> Dict[str, Any]:
    cfg = default_sensenova_config()
    if isinstance(raw_sensenova, dict):
        cfg.update(raw_sensenova)

    cfg["enabled"] = bool(cfg.get("enabled", True))
    cfg["api_key"] = str(cfg.get("api_key", "") or "").strip()
    cfg["api_url"] = resolve_sensenova_sdk_base_url(cfg.get("api_url", SENSENOVA_DEFAULT_API_URL))
    cfg["endpoint"] = str(cfg.get("endpoint", "") or "").strip()
    cfg["selected_model_id"] = str(cfg.get("selected_model_id", SENSENOVA_DEFAULT_MODEL_ID) or "").strip() or SENSENOVA_DEFAULT_MODEL_ID
    cfg["selected_model_display_name"] = str(
        cfg.get("selected_model_display_name", SENSENOVA_DEFAULT_MODEL_DISPLAY_NAME) or ""
    ).strip() or SENSENOVA_DEFAULT_MODEL_DISPLAY_NAME
    cfg["reasoning_effort"] = normalize_sensenova_reasoning_effort(
        cfg.get("reasoning_effort", SENSENOVA_DEFAULT_REASONING_EFFORT)
    )

    for key, default_value in (
        ("max_context_tokens", SENSENOVA_DEFAULT_CONTEXT_TOKENS),
        ("timeout", 300),
        ("max_tokens", SENSENOVA_DEFAULT_MAX_TOKENS),
    ):
        try:
            value = int(cfg.get(key, default_value))
        except (TypeError, ValueError):
            value = default_value
        if value <= 0:
            value = default_value
        cfg[key] = value

    for key, default_value in (
        ("temperature", SENSENOVA_DEFAULT_TEMPERATURE),
        ("top_p", SENSENOVA_DEFAULT_TOP_P),
    ):
        try:
            cfg[key] = float(cfg.get(key, default_value))
        except (TypeError, ValueError):
            cfg[key] = default_value

    matched = resolve_sensenova_selected_model(cfg)
    if matched:
        cfg["selected_model_id"] = str(matched["id"])
        cfg["selected_model_display_name"] = str(matched["display_name"])
        cfg["max_context_tokens"] = int(matched.get("context_length") or cfg["max_context_tokens"])
        output_limit = int(matched.get("max_output_tokens") or SENSENOVA_DEFAULT_MAX_TOKENS)
        cfg["max_tokens"] = min(int(cfg.get("max_tokens") or output_limit), output_limit)

    return cfg


def build_sensenova_runtime_model_data(sensenova_config: Any, model_id: Optional[str] = None) -> Optional[Dict[str, Any]]:
    cfg = normalize_sensenova_config(sensenova_config)
    if not cfg.get("enabled", True):
        return None
    api_key = resolve_sensenova_api_key(cfg)
    if not api_key:
        return None
    selected = resolve_sensenova_selected_model(cfg, model_id=model_id)
    if not selected:
        return None
    return {
        "model": selected["id"],
        "model_display_name": selected["display_name"],
        "base_url": resolve_sensenova_sdk_base_url(cfg.get("api_url", SENSENOVA_DEFAULT_API_URL)),
        "api_key": api_key,
        "max_context_tokens": int(selected.get("context_length") or cfg.get("max_context_tokens", SENSENOVA_DEFAULT_CONTEXT_TOKENS)),
        "provider": "openai-sdk",
        "supports_vision": bool(selected.get("vision", False)),
        "thinking_mode": normalize_sensenova_reasoning_effort(cfg.get("reasoning_effort")),
        "endpoint": str(cfg.get("endpoint", "") or ""),
        "custom_headers": {},
        "vision": bool(selected.get("vision", False)),
    }
