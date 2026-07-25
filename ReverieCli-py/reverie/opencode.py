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
OPENCODE_DEFAULT_CONTEXT_TOKENS = 200_000
OPENCODE_DEFAULT_MAX_TOKENS = 16_384
OPENCODE_DEFAULT_TEMPERATURE = 0.7
OPENCODE_DEFAULT_TOP_P = 1.0

_REASONING_LABELS = {
    "none": ("Non-think", "Disable reasoning for a faster direct response."),
    "low": ("Low", "Use a low reasoning effort."),
    "medium": ("Medium", "Use the provider-recommended balanced reasoning effort."),
    "high": ("High", "Use a high reasoning effort for complex work."),
    "max": ("Max", "Use the model's maximum reasoning effort."),
}


def _reasoning_options(*values: str) -> List[Dict[str, str]]:
    return [
        {
            "id": value,
            "label": _REASONING_LABELS[value][0],
            "description": _REASONING_LABELS[value][1],
        }
        for value in values
    ]


def _opencode_model(
    model_id: str,
    display_name: str,
    description: str,
    *,
    context_length: int = OPENCODE_DEFAULT_CONTEXT_TOKENS,
    max_output_tokens: int = OPENCODE_DEFAULT_MAX_TOKENS,
    vision: bool = False,
    vision_modalities: Optional[List[str]] = None,
    thinking: bool = True,
    thinking_control: str = "fixed",
    thinking_options: Optional[List[Dict[str, str]]] = None,
    default_thinking_choice: str = "",
) -> Dict[str, Any]:
    return {
        "id": str(model_id or "").strip(),
        "display_name": str(display_name or model_id or "").strip(),
        "description": str(description or "").strip(),
        "transport": "openai-chat",
        "context_length": int(context_length or OPENCODE_DEFAULT_CONTEXT_TOKENS),
        "max_output_tokens": int(max_output_tokens or OPENCODE_DEFAULT_MAX_TOKENS),
        "vision": bool(vision),
        "vision_modalities": list(vision_modalities or (["image"] if vision else [])),
        "thinking": bool(thinking),
        "thinking_control": str(thinking_control or ("fixed" if thinking else "none")),
        "thinking_options": list(thinking_options or []),
        "default_thinking_choice": str(default_thinking_choice or ""),
        "tool_calling": True,
        "free": True,
    }


_OPENCODE_MODEL_CATALOG: List[Dict[str, Any]] = [
    _opencode_model(
        "big-pickle",
        "Big Pickle",
        "OpenCode Zen stealth free model exposed through chat.completions.",
        context_length=200_000,
        max_output_tokens=32_000,
    ),
    _opencode_model(
        "deepseek-v4-flash-free",
        "DeepSeek V4 Flash Free",
        "OpenCode Zen free DeepSeek V4 Flash model with selectable reasoning effort.",
        context_length=200_000,
        max_output_tokens=128_000,
        thinking_control="effort",
        thinking_options=_reasoning_options("none", "high", "max"),
        default_thinking_choice="high",
    ),
    _opencode_model(
        "mimo-v2.5-free",
        "MiMo-V2.5 Free",
        "OpenCode Zen free native multimodal MiMo-V2.5 model.",
        context_length=200_000,
        max_output_tokens=32_000,
        vision=True,
        vision_modalities=["image", "audio", "video"],
    ),
    _opencode_model(
        "north-mini-code-free",
        "North Mini Code Free",
        "OpenCode Zen free North Mini Code model with selectable reasoning.",
        context_length=256_000,
        max_output_tokens=64_000,
        thinking_control="effort",
        thinking_options=_reasoning_options("none", "high"),
        default_thinking_choice="high",
    ),
    _opencode_model(
        "nemotron-3-ultra-free",
        "Nemotron 3 Ultra Free",
        "OpenCode Zen free Nemotron 3 Ultra chat.completions model.",
        context_length=1_000_000,
        max_output_tokens=128_000,
    ),
    _opencode_model(
        "ling-3.0-flash-free",
        "Ling 3.0 Flash Free",
        "OpenCode Zen free Ling 3.0 Flash model with selectable reasoning effort.",
        context_length=262_144,
        max_output_tokens=32_768,
        thinking_control="effort",
        thinking_options=_reasoning_options("low", "medium", "high"),
        default_thinking_choice="medium",
    ),
    _opencode_model(
        "laguna-s-2.1-free",
        "Laguna S 2.1 Free",
        "OpenCode Zen free Laguna S 2.1 coding model with selectable reasoning effort.",
        context_length=256_000,
        max_output_tokens=32_000,
        thinking_control="effort",
        thinking_options=_reasoning_options("low", "medium", "high"),
        default_thinking_choice="medium",
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
        "reasoning_effort": "high",
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
    raw_has_reasoning_effort = False
    if isinstance(raw_opencode, dict):
        raw_has_reasoning_effort = "reasoning_effort" in raw_opencode
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
        raw_choice = cfg.get("reasoning_effort") if raw_has_reasoning_effort else ""
        cfg["reasoning_effort"] = normalize_opencode_reasoning_choice(matched["id"], raw_choice)

    return cfg


def normalize_opencode_reasoning_choice(model_id: Any, value: Any) -> str:
    """Normalize one model-specific OpenCode reasoning selection."""
    selected = get_opencode_model_metadata(model_id) or {}
    options = [str(item.get("id") or "") for item in selected.get("thinking_options", [])]
    default = str(selected.get("default_thinking_choice") or "")
    candidate = str(value or "").strip().lower().replace("_", "-")
    candidate = {
        "off": "none",
        "false": "none",
        "no-think": "none",
        "non-think": "none",
        "med": "medium",
        "extra-high": "max",
        "xhigh": "max",
    }.get(candidate, candidate)
    if options:
        return candidate if candidate in options else (default if default in options else options[0])
    return "fixed" if bool(selected.get("thinking")) else ""


def resolve_opencode_thinking_choice(opencode_config: Any, model_id: Optional[str] = None) -> str:
    cfg = default_opencode_config()
    if isinstance(opencode_config, dict):
        cfg.update(opencode_config)
    selected = resolve_opencode_selected_model(cfg, model_id=model_id)
    if not selected:
        return ""
    return normalize_opencode_reasoning_choice(selected["id"], cfg.get("reasoning_effort"))


def apply_opencode_thinking_choice(opencode_config: Any, model_id: Any, choice: Any) -> Dict[str, Any]:
    cfg = default_opencode_config()
    if isinstance(opencode_config, dict):
        cfg.update(opencode_config)
    selected = resolve_opencode_selected_model(cfg, model_id=str(model_id or ""))
    if not selected:
        return normalize_opencode_config(cfg)
    normalized = normalize_opencode_reasoning_choice(selected["id"], choice)
    valid = {str(item.get("id") or "") for item in selected.get("thinking_options", [])}
    if valid and normalized not in valid:
        raise ValueError(f"Reasoning level {choice!r} is not supported by {selected['id']}")
    cfg["selected_model_id"] = str(selected["id"])
    cfg["selected_model_display_name"] = str(selected["display_name"])
    if valid:
        cfg["reasoning_effort"] = normalized
    return normalize_opencode_config(cfg)


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
        "thinking_mode": resolve_opencode_thinking_choice(cfg, selected["id"]),
        "endpoint": str(cfg.get("endpoint", OPENCODE_DEFAULT_ENDPOINT) or OPENCODE_DEFAULT_ENDPOINT),
        "custom_headers": {},
        "vision": bool(selected.get("vision", False)),
        "vision_modalities": list(selected.get("vision_modalities") or (["image"] if selected.get("vision") else [])),
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
    options: Dict[str, Any] = {
        "temperature": float(cfg.get("temperature", OPENCODE_DEFAULT_TEMPERATURE)),
        "top_p": float(cfg.get("top_p", OPENCODE_DEFAULT_TOP_P)),
        "max_tokens": min(max_tokens, output_limit),
    }
    if selected and str(selected.get("thinking_control") or "") == "effort":
        options["extra_body"] = {
            "reasoning_effort": resolve_opencode_thinking_choice(cfg, str(selected["id"])),
        }
    return options


def mask_secret(secret: str) -> str:
    """Mask secrets for safe terminal display."""
    value = str(secret or "").strip()
    if not value:
        return "(not set)"
    if len(value) <= 8:
        return "*" * len(value)
    return f"{value[:4]}...{value[-4:]}"
