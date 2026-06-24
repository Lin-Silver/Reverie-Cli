"""unlimited.surf request-provider helpers."""

from __future__ import annotations

import json
import os
from typing import Any, Dict, List, Optional

import requests


UNLIMITEDSURF_DEFAULT_BASE_URL = "https://unlimited.surf"
UNLIMITEDSURF_DEFAULT_CHAT_ENDPOINT = "/api/chat"
UNLIMITEDSURF_DEFAULT_MODELS_ENDPOINT = "/api/models"
UNLIMITEDSURF_DEFAULT_MODEL_ID = "gateway-gpt-5"
UNLIMITEDSURF_DEFAULT_MODEL_DISPLAY_NAME = "GPT-5"
UNLIMITEDSURF_DEFAULT_CONTEXT_TOKENS = 128_000
UNLIMITEDSURF_DEFAULT_MAX_TOKENS = 16_384
UNLIMITEDSURF_DEFAULT_EFFORT = "medium"
UNLIMITEDSURF_EFFORTS = ("low", "medium", "high")
UNLIMITEDSURF_API_KEY_HINT_URL = "https://unlimited.surf"


def _unlimitedsurf_model(
    model_id: str,
    display_name: str,
    description: str,
    *,
    provider: str = "",
    tier: str = "",
    context_length: int = UNLIMITEDSURF_DEFAULT_CONTEXT_TOKENS,
    max_output_tokens: int = UNLIMITEDSURF_DEFAULT_MAX_TOKENS,
) -> Dict[str, Any]:
    return {
        "id": str(model_id or "").strip(),
        "display_name": str(display_name or model_id or "").strip(),
        "description": str(description or "").strip(),
        "transport": "request",
        "context_length": int(context_length or UNLIMITEDSURF_DEFAULT_CONTEXT_TOKENS),
        "max_output_tokens": int(max_output_tokens or UNLIMITEDSURF_DEFAULT_MAX_TOKENS),
        "provider": str(provider or "").strip(),
        "tier": str(tier or "").strip(),
        "vision": False,
        "thinking": True,
        "tool_calling": False,
    }


_UNLIMITEDSURF_FALLBACK_MODEL_CATALOG: List[Dict[str, Any]] = [
    _unlimitedsurf_model(
        UNLIMITEDSURF_DEFAULT_MODEL_ID,
        UNLIMITEDSURF_DEFAULT_MODEL_DISPLAY_NAME,
        "unlimited.surf gateway model from the public API examples.",
        provider="openai",
        tier="flagship",
    )
]


def default_unlimitedsurf_config() -> Dict[str, Any]:
    """Default unlimited.surf provider config stored in config.json."""
    return {
        "enabled": True,
        "api_key": "",
        "selected_model_id": UNLIMITEDSURF_DEFAULT_MODEL_ID,
        "selected_model_display_name": UNLIMITEDSURF_DEFAULT_MODEL_DISPLAY_NAME,
        "api_url": UNLIMITEDSURF_DEFAULT_BASE_URL,
        "endpoint": UNLIMITEDSURF_DEFAULT_CHAT_ENDPOINT,
        "max_context_tokens": UNLIMITEDSURF_DEFAULT_CONTEXT_TOKENS,
        "timeout": 60,
        "max_tokens": UNLIMITEDSURF_DEFAULT_MAX_TOKENS,
        "effort": UNLIMITEDSURF_DEFAULT_EFFORT,
    }


def _display_name_from_id(model_id: Any) -> str:
    text = str(model_id or "").strip()
    if not text:
        return UNLIMITEDSURF_DEFAULT_MODEL_DISPLAY_NAME
    return text.replace("_", " ").replace("-", " ").title()


def normalize_unlimitedsurf_effort(value: Any) -> str:
    """Normalize the unlimited.surf `effort` request field."""
    text = str(value or "").strip().lower().replace("_", "-")
    aliases = {
        "": UNLIMITEDSURF_DEFAULT_EFFORT,
        "default": UNLIMITEDSURF_DEFAULT_EFFORT,
        "auto": UNLIMITEDSURF_DEFAULT_EFFORT,
        "normal": UNLIMITEDSURF_DEFAULT_EFFORT,
        "med": "medium",
        "minimal": "low",
        "light": "low",
        "deep": "high",
        "max": "high",
    }
    normalized = aliases.get(text, text)
    if normalized not in UNLIMITEDSURF_EFFORTS:
        return UNLIMITEDSURF_DEFAULT_EFFORT
    return normalized


def resolve_unlimitedsurf_base_url(api_url: Any) -> str:
    """Resolve and normalize the unlimited.surf base URL."""
    base = str(api_url or "").strip()
    if not base:
        return UNLIMITEDSURF_DEFAULT_BASE_URL
    if not base.startswith(("http://", "https://")):
        base = f"https://{base}"
    base = base.rstrip("/")
    lower = base.lower()
    for suffix in (
        UNLIMITEDSURF_DEFAULT_CHAT_ENDPOINT,
        UNLIMITEDSURF_DEFAULT_MODELS_ENDPOINT,
        "/api",
    ):
        if lower.endswith(suffix):
            base = base[: -len(suffix)]
            lower = base.lower()
    return base.rstrip("/") or UNLIMITEDSURF_DEFAULT_BASE_URL


def resolve_unlimitedsurf_chat_url(api_url: Any, endpoint: Any = "") -> str:
    """Resolve the effective unlimited.surf chat endpoint URL."""
    base = resolve_unlimitedsurf_base_url(api_url)
    raw_endpoint = str(endpoint or UNLIMITEDSURF_DEFAULT_CHAT_ENDPOINT).strip()
    if not raw_endpoint or raw_endpoint.lower() in {"clear", "default", "none", "off"}:
        raw_endpoint = UNLIMITEDSURF_DEFAULT_CHAT_ENDPOINT
    if raw_endpoint.startswith(("http://", "https://")):
        return raw_endpoint.rstrip("/")
    if raw_endpoint.startswith("/"):
        return f"{base}{raw_endpoint}"
    return f"{base}/{raw_endpoint}"


def resolve_unlimitedsurf_models_url(api_url: Any) -> str:
    """Resolve the public unlimited.surf model-list URL."""
    return f"{resolve_unlimitedsurf_base_url(api_url)}{UNLIMITEDSURF_DEFAULT_MODELS_ENDPOINT}"


def resolve_unlimitedsurf_api_key(unlimitedsurf_config: Any) -> str:
    """Resolve the effective unlimited.surf API key from config or environment."""
    cfg = default_unlimitedsurf_config()
    if isinstance(unlimitedsurf_config, dict):
        cfg.update(unlimitedsurf_config)

    key = str(cfg.get("api_key", "") or "").strip()
    if key:
        return key
    for env_name in ("UNLIMITEDSURF_API_KEY", "UNLIMITED_SURF_API_KEY", "US_API_KEY"):
        value = str(os.getenv(env_name, "") or "").strip()
        if value:
            return value
    return ""


def normalize_unlimitedsurf_model_item(raw_item: Any) -> Optional[Dict[str, Any]]:
    """Normalize one model entry returned by `/api/models`."""
    if not isinstance(raw_item, dict):
        return None

    model_id = str(raw_item.get("id") or raw_item.get("model") or "").strip()
    if not model_id:
        return None

    display_name = str(
        raw_item.get("display_name")
        or raw_item.get("name")
        or raw_item.get("label")
        or _display_name_from_id(model_id)
    ).strip()
    provider = str(raw_item.get("provider") or "").strip()
    tier = str(raw_item.get("tier") or raw_item.get("category") or "").strip()
    description_parts = ["unlimited.surf model"]
    if provider:
        description_parts.append(f"provider={provider}")
    if tier:
        description_parts.append(f"tier={tier}")

    try:
        context_length = int(
            raw_item.get("context_length")
            or raw_item.get("context")
            or raw_item.get("max_context_tokens")
            or UNLIMITEDSURF_DEFAULT_CONTEXT_TOKENS
        )
    except (TypeError, ValueError):
        context_length = UNLIMITEDSURF_DEFAULT_CONTEXT_TOKENS

    try:
        max_output_tokens = int(
            raw_item.get("max_output_tokens")
            or raw_item.get("max_tokens")
            or UNLIMITEDSURF_DEFAULT_MAX_TOKENS
        )
    except (TypeError, ValueError):
        max_output_tokens = UNLIMITEDSURF_DEFAULT_MAX_TOKENS

    return _unlimitedsurf_model(
        model_id,
        display_name,
        " | ".join(description_parts),
        provider=provider,
        tier=tier,
        context_length=context_length,
        max_output_tokens=max_output_tokens,
    )


def fetch_unlimitedsurf_model_catalog(api_url: Any = "", *, timeout: int = 15) -> List[Dict[str, Any]]:
    """Fetch the public unlimited.surf model catalog."""
    response = requests.get(
        resolve_unlimitedsurf_models_url(api_url),
        headers={"Accept": "application/json"},
        timeout=max(1, int(timeout or 15)),
    )
    response.raise_for_status()
    payload = response.json()
    if isinstance(payload, dict):
        raw_models = payload.get("data") or payload.get("models") or []
    elif isinstance(payload, list):
        raw_models = payload
    else:
        raw_models = []

    models: List[Dict[str, Any]] = []
    seen_ids: set[str] = set()
    for raw_model in raw_models:
        item = normalize_unlimitedsurf_model_item(raw_model)
        if not item:
            continue
        model_id = str(item.get("id", "")).strip()
        key = model_id.lower()
        if not model_id or key in seen_ids:
            continue
        seen_ids.add(key)
        models.append(item)
    return models


def get_unlimitedsurf_model_catalog(
    api_url: Any = "",
    *,
    fetch_live: bool = False,
    timeout: int = 15,
) -> List[Dict[str, Any]]:
    """Return unlimited.surf models, optionally refreshed from the public endpoint."""
    if fetch_live:
        try:
            live_models = fetch_unlimitedsurf_model_catalog(api_url, timeout=timeout)
            if live_models:
                return live_models
        except Exception:
            pass
    return [dict(item) for item in _UNLIMITEDSURF_FALLBACK_MODEL_CATALOG]


def get_unlimitedsurf_model_metadata(model_id: Any, catalog: Optional[List[Dict[str, Any]]] = None) -> Optional[Dict[str, Any]]:
    """Return metadata for one unlimited.surf model id."""
    wanted = str(model_id or "").strip().lower()
    if not wanted:
        return None
    for item in catalog or _UNLIMITEDSURF_FALLBACK_MODEL_CATALOG:
        if str(item.get("id", "") or "").strip().lower() == wanted:
            return dict(item)
    return None


def resolve_unlimitedsurf_selected_model(
    unlimitedsurf_config: Any,
    model_id: Optional[str] = None,
    *,
    catalog: Optional[List[Dict[str, Any]]] = None,
) -> Optional[Dict[str, Any]]:
    """Resolve selected unlimited.surf model metadata from config or override."""
    cfg = default_unlimitedsurf_config()
    if isinstance(unlimitedsurf_config, dict):
        cfg.update(unlimitedsurf_config)

    wanted = str(model_id or cfg.get("selected_model_id", UNLIMITEDSURF_DEFAULT_MODEL_ID) or "").strip()
    if not wanted:
        wanted = UNLIMITEDSURF_DEFAULT_MODEL_ID

    matched = get_unlimitedsurf_model_metadata(wanted, catalog=catalog)
    if matched:
        return matched

    display_name = str(cfg.get("selected_model_display_name", "") or "").strip()
    if not display_name or str(cfg.get("selected_model_id", "") or "").strip().lower() != wanted.lower():
        display_name = _display_name_from_id(wanted)
    return _unlimitedsurf_model(
        wanted,
        display_name,
        "Configured unlimited.surf model id.",
        context_length=int(cfg.get("max_context_tokens") or UNLIMITEDSURF_DEFAULT_CONTEXT_TOKENS),
        max_output_tokens=int(cfg.get("max_tokens") or UNLIMITEDSURF_DEFAULT_MAX_TOKENS),
    )


def apply_unlimitedsurf_model_selection(
    unlimitedsurf_config: Any,
    selected_model: Dict[str, Any],
) -> Dict[str, Any]:
    """Apply selected model metadata to a config dict."""
    cfg = default_unlimitedsurf_config()
    if isinstance(unlimitedsurf_config, dict):
        cfg.update(unlimitedsurf_config)
    if isinstance(selected_model, dict):
        cfg["selected_model_id"] = str(selected_model.get("id") or cfg["selected_model_id"]).strip()
        cfg["selected_model_display_name"] = str(
            selected_model.get("display_name")
            or selected_model.get("name")
            or cfg["selected_model_display_name"]
        ).strip()
        try:
            cfg["max_context_tokens"] = int(selected_model.get("context_length") or cfg["max_context_tokens"])
        except (TypeError, ValueError):
            pass
        try:
            cfg["max_tokens"] = int(selected_model.get("max_output_tokens") or cfg["max_tokens"])
        except (TypeError, ValueError):
            pass
    return normalize_unlimitedsurf_config(cfg)


def normalize_unlimitedsurf_config(raw_unlimitedsurf: Any) -> Dict[str, Any]:
    """Normalize unlimited.surf config for persistence and runtime usage."""
    cfg = default_unlimitedsurf_config()
    if isinstance(raw_unlimitedsurf, dict):
        cfg.update(raw_unlimitedsurf)

    cfg["enabled"] = bool(cfg.get("enabled", True))
    cfg["api_key"] = str(cfg.get("api_key", "") or "").strip()
    cfg["api_url"] = resolve_unlimitedsurf_base_url(cfg.get("api_url", UNLIMITEDSURF_DEFAULT_BASE_URL))
    cfg["endpoint"] = str(cfg.get("endpoint", UNLIMITEDSURF_DEFAULT_CHAT_ENDPOINT) or "").strip()
    if not cfg["endpoint"] or cfg["endpoint"].lower() in {"clear", "default", "none", "off"}:
        cfg["endpoint"] = UNLIMITEDSURF_DEFAULT_CHAT_ENDPOINT
    cfg["selected_model_id"] = (
        str(cfg.get("selected_model_id", UNLIMITEDSURF_DEFAULT_MODEL_ID) or "").strip()
        or UNLIMITEDSURF_DEFAULT_MODEL_ID
    )
    cfg["selected_model_display_name"] = (
        str(cfg.get("selected_model_display_name", "") or "").strip()
        or _display_name_from_id(cfg["selected_model_id"])
    )
    cfg["effort"] = normalize_unlimitedsurf_effort(cfg.get("effort", UNLIMITEDSURF_DEFAULT_EFFORT))

    for key, default_value in (
        ("max_context_tokens", UNLIMITEDSURF_DEFAULT_CONTEXT_TOKENS),
        ("timeout", 60),
        ("max_tokens", UNLIMITEDSURF_DEFAULT_MAX_TOKENS),
    ):
        try:
            value = int(cfg.get(key, default_value))
        except (TypeError, ValueError):
            value = default_value
        if value <= 0:
            value = default_value
        cfg[key] = value

    selected = resolve_unlimitedsurf_selected_model(cfg)
    if selected:
        cfg["selected_model_id"] = str(selected["id"])
        cfg["selected_model_display_name"] = str(selected["display_name"])

    return cfg


def build_unlimitedsurf_runtime_model_data(
    unlimitedsurf_config: Any,
    model_id: Optional[str] = None,
) -> Optional[Dict[str, Any]]:
    """Build runtime model config dict for agent initialization."""
    cfg = normalize_unlimitedsurf_config(unlimitedsurf_config)
    if not cfg.get("enabled", True):
        return None

    api_key = resolve_unlimitedsurf_api_key(cfg)
    if not api_key:
        return None

    selected = resolve_unlimitedsurf_selected_model(cfg, model_id=model_id)
    if not selected:
        return None

    return {
        "model": selected["id"],
        "model_display_name": selected["display_name"],
        "base_url": resolve_unlimitedsurf_chat_url(cfg.get("api_url", UNLIMITEDSURF_DEFAULT_BASE_URL), cfg.get("endpoint", "")),
        "api_key": api_key,
        "max_context_tokens": int(selected.get("context_length") or cfg.get("max_context_tokens", UNLIMITEDSURF_DEFAULT_CONTEXT_TOKENS)),
        "provider": "request",
        "supports_vision": False,
        "thinking_mode": normalize_unlimitedsurf_effort(cfg.get("effort")),
        "endpoint": "",
        "custom_headers": {},
        "vision": False,
    }


def _message_content_to_text(content: Any) -> str:
    if content is None:
        return ""
    if isinstance(content, str):
        return content
    if isinstance(content, (int, float, bool)):
        return str(content)
    if isinstance(content, (list, tuple)):
        parts = [_message_content_to_text(item) for item in content]
        return "\n".join(part for part in parts if part)
    if isinstance(content, dict):
        part_type = str(content.get("type", "") or "").strip().lower()
        if part_type in {"text", "input_text", "output_text"}:
            return _message_content_to_text(content.get("text"))
        if "text" in content:
            return _message_content_to_text(content.get("text"))
        if "content" in content:
            return _message_content_to_text(content.get("content"))
        if part_type in {"image", "input_image", "image_url", "video_url"}:
            return "[unsupported visual attachment omitted]"
        return ""
    return str(content)


def build_unlimitedsurf_message_text(messages: List[Dict[str, Any]]) -> str:
    """Flatten Reverie chat messages into unlimited.surf's single `message` field."""
    normalized: List[tuple[str, str]] = []
    for message in messages or []:
        if not isinstance(message, dict):
            continue
        role = str(message.get("role", "message") or "message").strip().lower()
        content = _message_content_to_text(message.get("content")).strip()
        if not content:
            continue
        normalized.append((role, content))

    if len(normalized) == 1 and normalized[0][0] == "user":
        return normalized[0][1]

    role_labels = {
        "system": "System",
        "user": "User",
        "assistant": "Assistant",
        "tool": "Tool",
    }
    lines = []
    for role, content in normalized:
        label = role_labels.get(role, role.title() or "Message")
        lines.append(f"{label}: {content}")
    return "\n\n".join(lines).strip()


def build_unlimitedsurf_chat_payload(
    *,
    messages: List[Dict[str, Any]],
    model_id: Any,
    effort: Any = UNLIMITEDSURF_DEFAULT_EFFORT,
) -> Dict[str, Any]:
    """Build the unlimited.surf `/api/chat` request payload."""
    return {
        "message": build_unlimitedsurf_message_text(messages),
        "model": str(model_id or UNLIMITEDSURF_DEFAULT_MODEL_ID).strip() or UNLIMITEDSURF_DEFAULT_MODEL_ID,
        "effort": normalize_unlimitedsurf_effort(effort),
    }


def parse_unlimitedsurf_stream_event(data_str: Any) -> Optional[Dict[str, Any]]:
    """Translate one unlimited.surf SSE data frame into a normalized stream event."""
    text = str(data_str or "").strip()
    if not text or text == "[DONE]":
        return None
    try:
        payload = json.loads(text)
    except json.JSONDecodeError:
        return {"type": "content", "text": text}
    if not isinstance(payload, dict):
        return None

    error = payload.get("error")
    if error:
        raise RuntimeError(str(error))

    delta = payload.get("delta")
    if delta is not None:
        delta_text = str(delta)
        if delta_text:
            return {"type": "content", "text": delta_text}

    if payload.get("finish") or payload.get("done"):
        return {"type": "finish", "reason": str(payload.get("reason") or "stop")}

    return None


def mask_secret(value: Any) -> str:
    """Mask secrets for safe terminal display."""
    text = str(value or "").strip()
    if not text:
        return "(not set)"
    if len(text) <= 8:
        return "***"
    return f"{text[:4]}***{text[-4:]}"
