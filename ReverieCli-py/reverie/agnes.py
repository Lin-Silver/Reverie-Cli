"""Agnes OpenAI-compatible source helpers."""

from __future__ import annotations

import json
import os
import time
from typing import Any, Dict, List, Optional
from urllib.request import Request, urlopen


AGNES_DEFAULT_API_URL = "https://apihub.agnes-ai.com/v1"
AGNES_DEFAULT_MODEL_ID = "agnes-2.0-flash"
AGNES_DEFAULT_MODEL_DISPLAY_NAME = "Agnes 2.0 Flash"
AGNES_API_KEY_HINT_URL = "https://platform.agnes-ai.com/settings/apiKeys"
AGNES_DEFAULT_CONTEXT_TOKENS = 256_000
AGNES_DEFAULT_MAX_TOKENS = 65_536
AGNES_DEFAULT_TEMPERATURE = 0.7
AGNES_DEFAULT_TOP_P = 1.0
AGNES_DEFAULT_THINKING_MODE = "low"
AGNES_THINKING_BUDGETS = {
    "low": 1024,
    "medium": 4096,
    "high": 8192,
}
AGNES_THINKING_LABELS = {
    "none": "Off",
    "low": "Low",
    "medium": "Medium",
    "high": "High",
}
AGNES_THINKING_DESCRIPTIONS = {
    "none": "Disable Agnes thinking for lower latency.",
    "low": "Use a small thinking budget for straightforward prompts.",
    "medium": "Use the provider-recommended thinking budget for heavier coding and reasoning.",
    "high": "Use a larger thinking budget for complex coding, debugging, and agent tasks.",
}

_MODEL_CACHE_TTL_SECONDS = 300
_MODEL_CACHE: Dict[str, Any] = {"key": "", "expires_at": 0.0, "models": []}


def _agnes_model(
    model_id: str,
    display_name: str,
    description: str,
    *,
    context_length: int = AGNES_DEFAULT_CONTEXT_TOKENS,
    max_output_tokens: int = AGNES_DEFAULT_MAX_TOKENS,
    vision: bool = False,
    thinking: bool = False,
    deprecated: bool = False,
    owned_by: str = "agnes-ai",
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
        "deprecated": bool(deprecated),
        "owned_by": owned_by,
    }


_AGNES_STATIC_MODEL_CATALOG: List[Dict[str, Any]] = [
    _agnes_model(
        "agnes-2.0-flash",
        "Agnes 2.0 Flash",
        "Agnes OpenAI-compatible text model with vision, reasoning, coding, and tool-calling support.",
        context_length=256_000,
        max_output_tokens=65_536,
        vision=True,
        thinking=True,
    ),
    _agnes_model(
        "agnes-1.5-flash",
        "Agnes 1.5 Flash",
        "Agnes OpenAI-compatible fast text model.",
        context_length=256_000,
        max_output_tokens=65_536,
        vision=True,
    ),
]


def _static_model_metadata() -> Dict[str, Dict[str, Any]]:
    return {str(item["id"]).strip().lower(): dict(item) for item in _AGNES_STATIC_MODEL_CATALOG}


def default_agnes_config() -> Dict[str, Any]:
    """Default Agnes provider config stored in config.json."""
    return {
        "enabled": True,
        "api_key": "",
        "selected_model_id": AGNES_DEFAULT_MODEL_ID,
        "selected_model_display_name": AGNES_DEFAULT_MODEL_DISPLAY_NAME,
        "api_url": AGNES_DEFAULT_API_URL,
        "endpoint": "",
        "max_context_tokens": AGNES_DEFAULT_CONTEXT_TOKENS,
        "timeout": 60,
        "max_tokens": AGNES_DEFAULT_MAX_TOKENS,
        "temperature": AGNES_DEFAULT_TEMPERATURE,
        "top_p": AGNES_DEFAULT_TOP_P,
        "thinking_mode": AGNES_DEFAULT_THINKING_MODE,
        "live_model_list": True,
    }


def normalize_agnes_thinking_mode(value: Any, *, supports_thinking: bool = True) -> str:
    candidate = str(value or "").strip().lower()
    aliases = {
        "off": "none",
        "false": "none",
        "disabled": "none",
        "disable": "none",
        "no": "none",
        "on": AGNES_DEFAULT_THINKING_MODE,
        "true": AGNES_DEFAULT_THINKING_MODE,
        "enabled": AGNES_DEFAULT_THINKING_MODE,
        "enable": AGNES_DEFAULT_THINKING_MODE,
        "default": AGNES_DEFAULT_THINKING_MODE,
    }
    candidate = aliases.get(candidate, candidate)
    if candidate not in {"none", *AGNES_THINKING_BUDGETS.keys()}:
        candidate = AGNES_DEFAULT_THINKING_MODE
    if not supports_thinking:
        return "none"
    return candidate


def get_agnes_thinking_label(mode: Any) -> str:
    normalized = normalize_agnes_thinking_mode(mode)
    return AGNES_THINKING_LABELS.get(normalized, AGNES_THINKING_LABELS[AGNES_DEFAULT_THINKING_MODE])


def get_agnes_thinking_catalog(*, supports_thinking: bool = True) -> List[Dict[str, str]]:
    modes = ("none", "low", "medium", "high") if supports_thinking else ("none",)
    return [
        {
            "id": mode,
            "label": AGNES_THINKING_LABELS[mode],
            "description": AGNES_THINKING_DESCRIPTIONS[mode],
        }
        for mode in modes
    ]


def build_agnes_thinking_payload(mode: Any) -> Optional[Dict[str, Any]]:
    normalized = normalize_agnes_thinking_mode(mode)
    if normalized == "none":
        return None
    return {
        "type": "enabled",
        "budget_tokens": AGNES_THINKING_BUDGETS[normalized],
    }


def resolve_agnes_sdk_base_url(api_url: Any) -> str:
    """Resolve an OpenAI SDK base URL for Agnes."""
    base = str(api_url or "").strip()
    if not base:
        return AGNES_DEFAULT_API_URL
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


def resolve_agnes_api_root(api_url: Any) -> str:
    """Return Agnes API root without the trailing /v1 path."""
    base = resolve_agnes_sdk_base_url(api_url)
    if base.lower().endswith("/v1"):
        return base[:-3].rstrip("/")
    return base.rstrip("/")


def resolve_agnes_api_key(agnes_config: Any) -> str:
    """Resolve the effective Agnes API key from config or environment."""
    cfg = default_agnes_config()
    if isinstance(agnes_config, dict):
        cfg.update(agnes_config)

    key = str(cfg.get("api_key", "") or "").strip()
    if key:
        return key
    for env_name in ("AGNES_API_KEY", "AGNES_TOKEN"):
        value = str(os.getenv(env_name, "") or "").strip()
        if value:
            return value
    return ""


def _display_name_from_model_id(model_id: Any) -> str:
    raw = str(model_id or "").strip()
    if not raw:
        return ""
    parts = [part for part in raw.replace("_", "-").split("-") if part]
    if not parts:
        return raw
    titled = []
    for part in parts:
        if part.lower() == "agnes":
            titled.append("Agnes")
        elif part.replace(".", "").isdigit():
            titled.append(part)
        else:
            titled.append(part.capitalize())
    return " ".join(titled)


def _is_text_model_id(model_id: Any) -> bool:
    model = str(model_id or "").strip().lower()
    if not model:
        return False
    if model.startswith(("agnes-image-", "agnes-video-")):
        return False
    return model.startswith("agnes-")


def _is_agnes_model_id(model_id: Any) -> bool:
    return str(model_id or "").strip().lower().startswith("agnes-")


def _agnes_model_kind(model_id: Any) -> str:
    model = str(model_id or "").strip().lower()
    if model.startswith("agnes-image-"):
        return "tti"
    if model.startswith("agnes-video-"):
        return "ttv"
    return "llm" if _is_text_model_id(model) else ""


def _live_cache_key(cfg: Dict[str, Any], api_key: str) -> str:
    return f"{resolve_agnes_sdk_base_url(cfg.get('api_url', AGNES_DEFAULT_API_URL))}|{api_key[:10]}"


def fetch_agnes_provider_model_catalog(agnes_config: Any, *, timeout: int = 5) -> List[Dict[str, Any]]:
    """Fetch every Agnes model advertised by the provider's /models endpoint."""
    cfg = default_agnes_config()
    if isinstance(agnes_config, dict):
        cfg.update(agnes_config)
    api_key = resolve_agnes_api_key(cfg)
    if not api_key:
        return []

    cache_key = _live_cache_key(cfg, api_key)
    now = time.time()
    if _MODEL_CACHE.get("key") == cache_key and float(_MODEL_CACHE.get("expires_at", 0.0) or 0.0) > now:
        return [dict(item) for item in _MODEL_CACHE.get("models", []) if isinstance(item, dict)]

    request = Request(
        f"{resolve_agnes_sdk_base_url(cfg.get('api_url', AGNES_DEFAULT_API_URL))}/models",
        headers={
            "Authorization": f"Bearer {api_key}",
            "Accept": "application/json",
            "User-Agent": "ReverieCLI-Agnes/1.0",
        },
    )
    with urlopen(request, timeout=max(1, int(timeout or 5))) as response:
        payload = json.loads(response.read().decode("utf-8"))

    data_items = payload.get("data", []) if isinstance(payload, dict) else []
    if not isinstance(data_items, list):
        data_items = []

    models: List[Dict[str, Any]] = []
    seen: set[str] = set()
    for item in data_items:
        if not isinstance(item, dict):
            continue
        model_id = str(item.get("id", "") or "").strip()
        if not _is_agnes_model_id(model_id):
            continue
        key = model_id.lower()
        if key in seen:
            continue
        seen.add(key)
        base = {
            "id": model_id,
            "object": str(item.get("object") or "model"),
            "owned_by": str(item.get("owned_by") or "agnes-ai"),
            "kind": _agnes_model_kind(model_id),
        }
        if item.get("created") is not None:
            base["created"] = item.get("created")
        models.append(base)

    _MODEL_CACHE.update({"key": cache_key, "expires_at": now + _MODEL_CACHE_TTL_SECONDS, "models": models})
    return [dict(item) for item in models]


def _text_catalog_from_provider_models(provider_models: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    static = _static_model_metadata()
    models: List[Dict[str, Any]] = []
    for item in provider_models:
        model_id = str(item.get("id", "") or "").strip()
        if not _is_text_model_id(model_id):
            continue
        key = model_id.lower()
        base = static.get(key) or _agnes_model(
            model_id,
            _display_name_from_model_id(model_id) or model_id,
            "Agnes text model returned by the OpenAI-compatible /v1/models endpoint.",
        )
        base["owned_by"] = str(item.get("owned_by") or base.get("owned_by") or "agnes-ai")
        if item.get("created") is not None:
            base["created"] = item.get("created")
        models.append(base)
    return models


def fetch_agnes_model_catalog(agnes_config: Any, *, timeout: int = 5) -> List[Dict[str, Any]]:
    """Fetch Agnes LLM models from the provider's OpenAI-compatible /models endpoint."""
    return _text_catalog_from_provider_models(
        fetch_agnes_provider_model_catalog(agnes_config, timeout=timeout)
    )


def get_agnes_model_catalog(agnes_config: Any = None) -> List[Dict[str, Any]]:
    """Return Agnes text models, preferring the live API catalog when available."""
    cfg = default_agnes_config()
    if isinstance(agnes_config, dict):
        cfg.update(agnes_config)

    models: List[Dict[str, Any]] = []
    if bool(cfg.get("live_model_list", True)) and resolve_agnes_api_key(cfg):
        try:
            models = fetch_agnes_model_catalog(cfg, timeout=min(8, int(cfg.get("timeout", 60) or 60)))
        except Exception:
            models = []

    return models or [dict(item) for item in _AGNES_STATIC_MODEL_CATALOG]


def get_agnes_source_catalog(agnes_config: Any = None) -> Dict[str, Any]:
    """Return usable Agnes LLM, TTI, and TTV models from one provider inventory."""
    from .agnes_tti_profiles.registry import get_agnes_tti_model_catalog
    from .agnes_ttv_profiles.registry import get_agnes_ttv_model_catalog

    cfg = default_agnes_config()
    if isinstance(agnes_config, dict):
        cfg.update(agnes_config)

    provider_models: List[Dict[str, Any]] = []
    if bool(cfg.get("live_model_list", True)) and resolve_agnes_api_key(cfg):
        try:
            provider_models = fetch_agnes_provider_model_catalog(
                cfg,
                timeout=min(8, int(cfg.get("timeout", 60) or 60)),
            )
        except Exception:
            provider_models = []

    tti_models = get_agnes_tti_model_catalog()
    ttv_models = get_agnes_ttv_model_catalog()
    if not provider_models:
        return {
            "live": False,
            "llm": [dict(item) for item in _AGNES_STATIC_MODEL_CATALOG],
            "tti": tti_models,
            "ttv": ttv_models,
        }

    available_ids = {
        str(item.get("id", "") or "").strip().lower()
        for item in provider_models
        if str(item.get("id", "") or "").strip()
    }
    return {
        "live": True,
        "llm": _text_catalog_from_provider_models(provider_models),
        "tti": [item for item in tti_models if str(item.get("id", "")).lower() in available_ids],
        "ttv": [item for item in ttv_models if str(item.get("id", "")).lower() in available_ids],
    }


def get_agnes_model_metadata(model_id: Any, agnes_config: Any = None) -> Optional[Dict[str, Any]]:
    """Return metadata for one Agnes text model id."""
    wanted = str(model_id or "").strip().lower()
    if not wanted:
        return None
    for item in get_agnes_model_catalog(agnes_config):
        if str(item.get("id", "")).strip().lower() == wanted:
            return dict(item)
    return None


def resolve_agnes_selected_model(agnes_config: Any, model_id: Optional[str] = None) -> Optional[Dict[str, Any]]:
    """Resolve selected Agnes model metadata from config or override."""
    cfg = default_agnes_config()
    if isinstance(agnes_config, dict):
        cfg.update(agnes_config)

    wanted = str(model_id or cfg.get("selected_model_id", AGNES_DEFAULT_MODEL_ID) or "").strip()
    matched = get_agnes_model_metadata(wanted, cfg)
    if matched:
        return matched
    if wanted and _is_text_model_id(wanted):
        return _agnes_model(
            wanted,
            _display_name_from_model_id(wanted) or wanted,
            "Agnes text model selected from config.",
        )
    catalog = get_agnes_model_catalog(cfg)
    return catalog[0] if catalog else None


def normalize_agnes_config(raw_agnes: Any) -> Dict[str, Any]:
    """Normalize Agnes config for persistence and runtime usage."""
    cfg = default_agnes_config()
    if isinstance(raw_agnes, dict):
        cfg.update(raw_agnes)

    cfg["enabled"] = bool(cfg.get("enabled", True))
    cfg["api_key"] = str(cfg.get("api_key", "") or "").strip()
    cfg["api_url"] = resolve_agnes_sdk_base_url(cfg.get("api_url", AGNES_DEFAULT_API_URL))
    cfg["endpoint"] = str(cfg.get("endpoint", "") or "").strip()
    cfg["selected_model_id"] = str(cfg.get("selected_model_id", AGNES_DEFAULT_MODEL_ID) or "").strip() or AGNES_DEFAULT_MODEL_ID
    cfg["selected_model_display_name"] = (
        str(cfg.get("selected_model_display_name", AGNES_DEFAULT_MODEL_DISPLAY_NAME) or "").strip()
        or AGNES_DEFAULT_MODEL_DISPLAY_NAME
    )
    cfg["live_model_list"] = bool(cfg.get("live_model_list", True))

    for key, default_value in (
        ("max_context_tokens", AGNES_DEFAULT_CONTEXT_TOKENS),
        ("timeout", 60),
        ("max_tokens", AGNES_DEFAULT_MAX_TOKENS),
    ):
        try:
            value = int(cfg.get(key, default_value))
        except (TypeError, ValueError):
            value = default_value
        if value <= 0:
            value = default_value
        cfg[key] = value

    for key, default_value in (
        ("temperature", AGNES_DEFAULT_TEMPERATURE),
        ("top_p", AGNES_DEFAULT_TOP_P),
    ):
        try:
            cfg[key] = float(cfg.get(key, default_value))
        except (TypeError, ValueError):
            cfg[key] = default_value

    matched = resolve_agnes_selected_model({**cfg, "live_model_list": False})
    if matched:
        cfg["selected_model_id"] = str(matched["id"])
        cfg["selected_model_display_name"] = str(matched["display_name"])
        cfg["thinking_mode"] = normalize_agnes_thinking_mode(
            cfg.get("thinking_mode", AGNES_DEFAULT_THINKING_MODE),
            supports_thinking=bool(matched.get("thinking", False)),
        )
        context_length = matched.get("context_length")
        if context_length:
            cfg["max_context_tokens"] = int(context_length)
        output_limit = int(matched.get("max_output_tokens") or AGNES_DEFAULT_MAX_TOKENS)
        cfg["max_tokens"] = min(int(cfg.get("max_tokens") or output_limit), output_limit)
    else:
        cfg["thinking_mode"] = normalize_agnes_thinking_mode(cfg.get("thinking_mode", AGNES_DEFAULT_THINKING_MODE))

    return cfg


def build_agnes_runtime_model_data(agnes_config: Any, model_id: Optional[str] = None) -> Optional[Dict[str, Any]]:
    """Build runtime model config dict for agent initialization."""
    cfg = normalize_agnes_config(agnes_config)
    if not cfg.get("enabled", True):
        return None

    api_key = resolve_agnes_api_key(cfg)
    if not api_key:
        return None

    selected = resolve_agnes_selected_model(cfg, model_id=model_id)
    if not selected:
        return None

    return {
        "model": selected["id"],
        "model_display_name": selected["display_name"],
        "base_url": resolve_agnes_sdk_base_url(cfg.get("api_url", AGNES_DEFAULT_API_URL)),
        "api_key": api_key,
        "max_context_tokens": int(selected.get("context_length") or cfg.get("max_context_tokens", AGNES_DEFAULT_CONTEXT_TOKENS)),
        "provider": "openai-sdk",
        "supports_vision": bool(selected.get("vision", False)),
        "thinking_mode": normalize_agnes_thinking_mode(
            cfg.get("thinking_mode", AGNES_DEFAULT_THINKING_MODE),
            supports_thinking=bool(selected.get("thinking", False)),
        ),
        "endpoint": str(cfg.get("endpoint", "") or ""),
        "custom_headers": {},
        "vision": bool(selected.get("vision", False)),
    }


def build_agnes_openai_options(agnes_config: Any, model_id: Optional[str] = None) -> Dict[str, Any]:
    """Return OpenAI SDK request options for Agnes chat completions."""
    cfg = normalize_agnes_config(agnes_config)
    selected = resolve_agnes_selected_model(cfg, model_id=model_id)
    output_limit = int((selected or {}).get("max_output_tokens") or AGNES_DEFAULT_MAX_TOKENS)
    try:
        max_tokens = int(cfg.get("max_tokens", AGNES_DEFAULT_MAX_TOKENS))
    except (TypeError, ValueError):
        max_tokens = AGNES_DEFAULT_MAX_TOKENS
    if max_tokens <= 0:
        max_tokens = AGNES_DEFAULT_MAX_TOKENS
    options = {
        "temperature": float(cfg.get("temperature", AGNES_DEFAULT_TEMPERATURE)),
        "top_p": float(cfg.get("top_p", AGNES_DEFAULT_TOP_P)),
        "max_tokens": min(max_tokens, output_limit),
    }
    thinking = build_agnes_thinking_payload(
        normalize_agnes_thinking_mode(
            cfg.get("thinking_mode", AGNES_DEFAULT_THINKING_MODE),
            supports_thinking=bool((selected or {}).get("thinking", False)),
        )
    )
    if thinking:
        options["extra_body"] = {"thinking": thinking}
    return options


def mask_secret(secret: str) -> str:
    """Mask secrets for safe terminal display."""
    value = str(secret or "").strip()
    if len(value) <= 8:
        return "*" * len(value)
    return f"{value[:4]}...{value[-4:]}"
