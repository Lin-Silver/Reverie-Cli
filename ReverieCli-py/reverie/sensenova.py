"""SenseNova chat and media source helpers."""

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
SENSENOVA_REASONING_EFFORTS = ("none", "low", "medium", "high", "max")
SENSENOVA_FLASH_LITE_DEFAULT_MAX_TOKENS = 6_144
SENSENOVA_FLASH_LITE_DEFAULT_TEMPERATURE = 0.7
SENSENOVA_FLASH_LITE_DEFAULT_TOP_P = 0.8
SENSENOVA_FLASH_LITE_DEFAULT_TOP_K = 20
SENSENOVA_FLASH_LITE_DEFAULT_MIN_P = 0.0
SENSENOVA_FLASH_LITE_DEFAULT_PRESENCE_PENALTY = 1.5
SENSENOVA_FLASH_LITE_DEFAULT_REPETITION_PENALTY = 1.0


def _sensenova_model(
    model_id: str,
    display_name: str,
    description: str,
    *,
    context_length: int = SENSENOVA_DEFAULT_CONTEXT_TOKENS,
    max_output_tokens: int = SENSENOVA_DEFAULT_MAX_TOKENS,
    vision: bool = False,
    thinking: bool = True,
    transport: str = "openai-chat",
    thinking_control: Optional[str] = None,
) -> Dict[str, Any]:
    resolved_thinking_control = thinking_control or ("effort" if thinking else "none")
    supports_effort_control = resolved_thinking_control == "effort"
    return {
        "id": model_id,
        "display_name": display_name,
        "description": description,
        "transport": transport,
        "context_length": int(context_length),
        "max_output_tokens": int(max_output_tokens),
        "vision": bool(vision),
        "thinking": bool(thinking),
        "tool_calling": True,
        "thinking_control": resolved_thinking_control,
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
        if supports_effort_control
        else [],
        "default_thinking_choice": SENSENOVA_DEFAULT_REASONING_EFFORT if supports_effort_control else "",
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
        transport="openai-chat",
        thinking_control="provider-managed",
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
        "top_k": SENSENOVA_FLASH_LITE_DEFAULT_TOP_K,
        "min_p": SENSENOVA_FLASH_LITE_DEFAULT_MIN_P,
        "presence_penalty": SENSENOVA_FLASH_LITE_DEFAULT_PRESENCE_PENALTY,
        "repetition_penalty": SENSENOVA_FLASH_LITE_DEFAULT_REPETITION_PENALTY,
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


def resolve_sensenova_anthropic_base_url(api_url: Any) -> str:
    """Return the root URL expected by the Anthropic SDK."""
    base = resolve_sensenova_sdk_base_url(api_url)
    lower = base.lower()
    for suffix in ("/v1/messages", "/messages", "/v1"):
        if lower.endswith(suffix):
            base = base[: -len(suffix)]
            break
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
        ("min_p", SENSENOVA_FLASH_LITE_DEFAULT_MIN_P),
        ("presence_penalty", SENSENOVA_FLASH_LITE_DEFAULT_PRESENCE_PENALTY),
        ("repetition_penalty", SENSENOVA_FLASH_LITE_DEFAULT_REPETITION_PENALTY),
    ):
        try:
            cfg[key] = float(cfg.get(key, default_value))
        except (TypeError, ValueError):
            cfg[key] = default_value
    try:
        cfg["top_k"] = max(1, int(cfg.get("top_k", SENSENOVA_FLASH_LITE_DEFAULT_TOP_K)))
    except (TypeError, ValueError):
        cfg["top_k"] = SENSENOVA_FLASH_LITE_DEFAULT_TOP_K

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
    transport = str(selected.get("transport") or "openai-chat").strip().lower()
    use_openai_chat = transport != "anthropic"
    thinking_control = str(selected.get("thinking_control") or "none").strip().lower()
    return {
        "model": selected["id"],
        "model_display_name": selected["display_name"],
        "base_url": (
            resolve_sensenova_sdk_base_url(cfg.get("api_url", SENSENOVA_DEFAULT_API_URL))
            if use_openai_chat
            else resolve_sensenova_anthropic_base_url(cfg.get("api_url", SENSENOVA_DEFAULT_API_URL))
        ),
        "api_key": api_key,
        "max_context_tokens": int(selected.get("context_length") or cfg.get("max_context_tokens", SENSENOVA_DEFAULT_CONTEXT_TOKENS)),
        "provider": "openai-chat" if use_openai_chat else "anthropic",
        "supports_vision": bool(selected.get("vision", False)),
        "thinking_mode": (
            normalize_sensenova_reasoning_effort(cfg.get("reasoning_effort"))
            if thinking_control == "effort"
            else thinking_control
        ),
        "endpoint": str(cfg.get("endpoint", "") or ""),
        "custom_headers": {},
        "vision": bool(selected.get("vision", False)),
    }


def build_sensenova_openai_options(sensenova_config: Any, model_id: Optional[str] = None) -> Dict[str, Any]:
    """Build OpenAI Chat options for SenseNova models that use that transport."""
    cfg = normalize_sensenova_config(sensenova_config)
    selected = resolve_sensenova_selected_model(cfg, model_id=model_id)
    selected_id = str((selected or {}).get("id") or "").strip().lower()
    output_limit = int((selected or {}).get("max_output_tokens") or SENSENOVA_DEFAULT_MAX_TOKENS)
    requested_max_tokens = max(1, int(cfg.get("max_tokens") or output_limit))
    is_flash_lite = selected_id == "sensenova-6.7-flash-lite"
    supports_reasoning_effort = selected_id in {"deepseek-v4-flash", "sensenova-6.7-flash-lite"}
    if is_flash_lite and requested_max_tokens == SENSENOVA_DEFAULT_MAX_TOKENS:
        requested_max_tokens = SENSENOVA_FLASH_LITE_DEFAULT_MAX_TOKENS
    temperature = float(cfg.get("temperature", SENSENOVA_DEFAULT_TEMPERATURE))
    top_p = float(cfg.get("top_p", SENSENOVA_DEFAULT_TOP_P))
    if is_flash_lite and temperature == SENSENOVA_DEFAULT_TEMPERATURE:
        temperature = SENSENOVA_FLASH_LITE_DEFAULT_TEMPERATURE
    if is_flash_lite and top_p == SENSENOVA_DEFAULT_TOP_P:
        top_p = SENSENOVA_FLASH_LITE_DEFAULT_TOP_P

    extra_body: Dict[str, Any] = {}
    if supports_reasoning_effort:
        extra_body["reasoning_effort"] = normalize_sensenova_reasoning_effort(
            cfg.get("reasoning_effort", SENSENOVA_DEFAULT_REASONING_EFFORT)
        )
    if is_flash_lite:
        extra_body.update(
            {
                "top_k": int(cfg.get("top_k", SENSENOVA_FLASH_LITE_DEFAULT_TOP_K)),
                "min_p": float(cfg.get("min_p", SENSENOVA_FLASH_LITE_DEFAULT_MIN_P)),
                "repetition_penalty": float(
                    cfg.get("repetition_penalty", SENSENOVA_FLASH_LITE_DEFAULT_REPETITION_PENALTY)
                ),
            }
        )
    return {
        "temperature": temperature,
        "top_p": top_p,
        "presence_penalty": float(
            cfg.get("presence_penalty", SENSENOVA_FLASH_LITE_DEFAULT_PRESENCE_PENALTY)
        ),
        "max_tokens": min(requested_max_tokens, output_limit),
        "extra_body": extra_body,
    }
