"""SenseNova chat and media source helpers."""

from __future__ import annotations

import os
import time
from typing import Any, Dict, List, Optional

import requests

from .diagnostics import report_suppressed_exception
from .model_catalog_cache import model_catalog_key, remember_model_catalog, remembered_model_catalog
from .proxy import normalize_proxy_url, requests_proxy_dict


SENSENOVA_DEFAULT_API_URL = "https://token.sensenova.cn"
SENSENOVA_DEFAULT_MODEL_ID = "deepseek-v4-flash"
SENSENOVA_DEFAULT_MODEL_DISPLAY_NAME = "DeepSeek V4 Flash"
SENSENOVA_DEFAULT_CONTEXT_TOKENS = 1_048_576
SENSENOVA_DEFAULT_MAX_TOKENS = 65_536
SENSENOVA_DEFAULT_TEMPERATURE = 0.6
SENSENOVA_DEFAULT_TOP_P = 0.95
SENSENOVA_DEFAULT_REASONING_EFFORT = "medium"
SENSENOVA_REASONING_EFFORTS = ("none", "low", "medium", "high", "max")
SENSENOVA_FLASH_LITE_DEFAULT_TEMPERATURE = 0.7
SENSENOVA_FLASH_LITE_DEFAULT_TOP_P = 0.8
SENSENOVA_FLASH_LITE_DEFAULT_TOP_K = 20
SENSENOVA_FLASH_LITE_DEFAULT_MIN_P = 0.0
SENSENOVA_FLASH_LITE_DEFAULT_PRESENCE_PENALTY = 1.5
SENSENOVA_FLASH_LITE_DEFAULT_REPETITION_PENALTY = 1.0
SENSENOVA_MODEL_CACHE_TTL_SECONDS = 60.0
# Migrate legacy saved selections only before a live inventory is available.
SENSENOVA_MODEL_ID_MIGRATIONS: Dict[str, str] = {
    "sensenova-6.7-flash-lite": "sensenova-6.8-flash-lite",
}


def _sensenova_model(
    model_id: str,
    display_name: str,
    description: str,
    *,
    context_length: int = SENSENOVA_DEFAULT_CONTEXT_TOKENS,
    max_output_tokens: int = SENSENOVA_DEFAULT_MAX_TOKENS,
    vision: bool = False,
    thinking: bool = True,
    transport: str = "anthropic",
    thinking_control: Optional[str] = None,
    supports_thinking_disable: bool = True,
    fixed_temperature: Optional[float] = None,
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
        "supports_thinking_disable": supports_thinking_disable,
        "fixed_temperature": fixed_temperature,
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
        "SenseNova DeepSeek V4 Flash with 1M context and selectable reasoning effort.",
    ),
    _sensenova_model(
        "deepseek-flash",
        "DeepSeek Flash",
        "SenseNova-hosted DeepSeek Flash with a 1M context window.",
        thinking_control="provider-managed",
    ),
    _sensenova_model(
        "glm-5.2",
        "GLM-5.2",
        "SenseNova-hosted GLM-5.2 with a 1M context window for long-horizon tasks.",
        context_length=1_048_576,
        max_output_tokens=131_072,
        thinking_control="provider-managed",
    ),
    _sensenova_model(
        "kimi-k3",
        "Kimi K3",
        "SenseNova-hosted Kimi K3 with a 1M context window.",
        context_length=1_048_576,
        thinking_control="provider-managed",
        fixed_temperature=1.0,
    ),
    _sensenova_model(
        "sensenova-6.8-flash-lite",
        "SenseNova 6.8 Flash Lite",
        "SenseNova lightweight multimodal agent model for text and image workflows.",
        context_length=262_144,
        vision=True,
        thinking_control="provider-managed",
    ),
    _sensenova_model(
        "sensenova-6.8-flash", "SenseNova 6.8 Flash",
        "SenseNova multimodal agent model for text and image workflows.",
        context_length=262_144, vision=True, thinking_control="provider-managed",
    ),
    _sensenova_model(
        "glm-5.3", "GLM-5.3",
        "SenseNova-hosted GLM-5.3 with a 1M context window.",
        max_output_tokens=131_072, thinking_control="provider-managed",
        supports_thinking_disable=False,
    ),
]

_SENSENOVA_MODEL_METADATA = {
    str(item["id"]).strip().lower(): dict(item) for item in _SENSENOVA_MODEL_CATALOG
}
_MODEL_CACHE: Dict[str, Any] = {"key": "", "expires_at": 0.0, "models": []}


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


def _sensenova_models_url(api_url: Any) -> str:
    return f"{resolve_sensenova_sdk_base_url(api_url)}/models"


def _live_sensenova_model(raw_model: Any) -> Optional[Dict[str, Any]]:
    if not isinstance(raw_model, dict):
        return None
    model_id = str(raw_model.get("id") or raw_model.get("model") or "").strip()
    if not model_id:
        return None
    output_modalities = [str(item).strip().lower() for item in raw_model.get("output_modalities", [])]
    if output_modalities and "text" not in output_modalities:
        return None

    known = get_sensenova_model_metadata(model_id)
    features = {str(item).strip().lower() for item in raw_model.get("supported_features", [])}
    input_modalities = {str(item).strip().lower() for item in raw_model.get("input_modalities", [])}
    if known:
        model = known
    else:
        display_name = str(raw_model.get("name") or model_id).strip()
        model = _sensenova_model(
            model_id,
            display_name,
            "SenseNova text model discovered from the live /models endpoint.",
            thinking="reasoning" in features,
            thinking_control="provider-managed" if "reasoning" in features else "none",
        )

    model["display_name"] = str(raw_model.get("name") or model["display_name"]).strip()
    model["description"] = str(raw_model.get("description") or model["description"]).strip()
    model["context_length"] = int(raw_model.get("context_length") or model["context_length"])
    model["max_output_tokens"] = int(raw_model.get("max_output_length") or model["max_output_tokens"])
    if "input_modalities" in raw_model:
        model["vision"] = "image" in input_modalities
    if "supported_features" in raw_model:
        model["tool_calling"] = "tools" in features
        model["thinking"] = "reasoning" in features
        if not model["thinking"]:
            model.update(thinking_control="none", thinking_options=[], default_thinking_choice="")
    model["transport"] = "anthropic"
    for field in (
        "input_modalities",
        "output_modalities",
        "supported_features",
        "supported_sampling_parameters",
        "pricing",
        "supports_thinking_disable",
        "fixed_temperature",
    ):
        if field in raw_model:
            model[field] = raw_model[field]
    model["catalog_source"] = "api"
    return model


def fetch_sensenova_model_catalog(
    sensenova_config: Any,
    *,
    timeout: int = 5,
    force_refresh: bool = False,
    proxy: Any = "",
) -> List[Dict[str, Any]]:
    """Fetch chat-capable models available to the configured SenseNova account."""
    cfg = default_sensenova_config()
    if isinstance(sensenova_config, dict):
        cfg.update(sensenova_config)
    api_key = resolve_sensenova_api_key(cfg)
    if not api_key:
        return []
    models_url = _sensenova_models_url(cfg.get("api_url"))
    configured_proxy = normalize_proxy_url(proxy)
    cache_key = model_catalog_key(models_url, api_key)
    now = time.monotonic()
    if (
        not force_refresh
        and _MODEL_CACHE.get("key") == cache_key
        and float(_MODEL_CACHE.get("expires_at") or 0.0) > now
    ):
        models = [dict(item) for item in _MODEL_CACHE.get("models", [])]
        remember_model_catalog(sensenova_config, cache_key, models)
        return models

    request_kwargs: Dict[str, Any] = {
        "headers": {"Authorization": f"Bearer {api_key}", "Accept": "application/json"},
        "timeout": max(1, int(timeout or 5)),
    }
    if configured_proxy:
        request_kwargs["proxies"] = requests_proxy_dict(configured_proxy)
    response = requests.get(models_url, **request_kwargs)
    response.raise_for_status()
    payload = response.json()
    raw_models = payload.get("data", payload.get("models")) if isinstance(payload, dict) else payload
    if not isinstance(raw_models, list):
        raise ValueError("SenseNova model catalog response must contain a model list.")
    models = [model for item in raw_models if (model := _live_sensenova_model(item)) is not None]
    _MODEL_CACHE.update(key=cache_key, expires_at=now + SENSENOVA_MODEL_CACHE_TTL_SECONDS, models=models)
    remember_model_catalog(sensenova_config, cache_key, models)
    return [dict(item) for item in models]


def get_sensenova_model_catalog(
    sensenova_config: Any = None,
    *,
    fetch_live: bool = False,
    force_refresh: bool = False,
    proxy: Any = "",
) -> List[Dict[str, Any]]:
    cfg = default_sensenova_config()
    if isinstance(sensenova_config, dict):
        cfg.update(sensenova_config)
    key = model_catalog_key(_sensenova_models_url(cfg.get("api_url")), resolve_sensenova_api_key(cfg))
    if fetch_live and resolve_sensenova_api_key(cfg):
        try:
            return fetch_sensenova_model_catalog(
                sensenova_config,
                force_refresh=force_refresh,
                proxy=proxy,
            )
        except Exception:
            report_suppressed_exception("fetch SenseNova live model catalog")
    latest = remembered_model_catalog(cfg, key, _MODEL_CACHE)
    if latest is not None:
        return latest
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
    key = model_catalog_key(_sensenova_models_url(cfg.get("api_url")), resolve_sensenova_api_key(cfg))
    latest = remembered_model_catalog(cfg, key, _MODEL_CACHE)
    if latest is not None:
        matched = next((item for item in latest if str(item["id"]).lower() == wanted), None)
        return matched or (latest[0] if latest else None)
    wanted = SENSENOVA_MODEL_ID_MIGRATIONS.get(wanted, wanted)
    matched = get_sensenova_model_metadata(wanted)
    if matched:
        return matched
    if wanted:
        return _sensenova_model(
            wanted,
            str(cfg.get("selected_model_display_name") or wanted).strip(),
            "SenseNova model selected from the live /models endpoint.",
            context_length=int(cfg.get("max_context_tokens") or SENSENOVA_DEFAULT_CONTEXT_TOKENS),
            max_output_tokens=int(cfg.get("max_tokens") or SENSENOVA_DEFAULT_MAX_TOKENS),
            thinking_control="provider-managed",
        )
    return get_sensenova_model_catalog()[0]


def resolve_sensenova_sdk_base_url(api_url: Any) -> str:
    base = str(api_url or "").strip().rstrip("/")
    if not base:
        base = SENSENOVA_DEFAULT_API_URL
    if not base.startswith(("http://", "https://")):
        base = f"https://{base}"
    lower = base.lower()
    for suffix in ("/chat/completions", "/messages"):
        if lower.endswith(suffix):
            base = base[: -len(suffix)]
            break
    if not base.lower().endswith("/v1"):
        base += "/v1"
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
    env_name = str(cfg.get("api_key_env", "") or "").strip()
    if env_name:
        return str(os.getenv(env_name, "") or "").strip()
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
    cfg["api_url"] = resolve_sensenova_anthropic_base_url(cfg.get("api_url", SENSENOVA_DEFAULT_API_URL))
    cfg["endpoint"] = "/v1/messages"
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
        if matched.get("fixed_temperature") is not None:
            cfg["temperature"] = float(matched["fixed_temperature"])

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
    thinking_control = str(selected.get("thinking_control") or "none").strip().lower()
    return {
        "model": selected["id"],
        "model_display_name": selected["display_name"],
        "base_url": resolve_sensenova_anthropic_base_url(cfg.get("api_url", SENSENOVA_DEFAULT_API_URL)),
        "api_key": api_key,
        "max_context_tokens": int(selected.get("context_length") or cfg.get("max_context_tokens", SENSENOVA_DEFAULT_CONTEXT_TOKENS)),
        "provider": "anthropic",
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


def build_sensenova_anthropic_options(sensenova_config: Any, model_id: Optional[str] = None) -> Dict[str, Any]:
    """Build native Messages options without OpenAI-only sampling fields."""
    cfg = normalize_sensenova_config(sensenova_config)
    selected = resolve_sensenova_selected_model(cfg, model_id=model_id) or {}
    temperature = selected.get("fixed_temperature")
    options: Dict[str, Any] = {"temperature": float(cfg["temperature"] if temperature is None else temperature)}
    if not selected.get("thinking", False):
        return options
    effort = normalize_sensenova_reasoning_effort(cfg.get("reasoning_effort"))
    if effort == "none":
        if selected.get("supports_thinking_disable", True):
            options["thinking"] = {"type": "disabled"}
    elif selected.get("thinking_control") == "effort":
        options["thinking"] = {"type": "adaptive"}
        options["extra_body"] = {"output_config": {"effort": effort}}
    return options


class _SenseNovaMessageEvents:
    """Normalize the provider's null initial content before SDK accumulation."""

    def __init__(self, stream: Any) -> None:
        self.stream = stream
        self.response = stream.response

    def __iter__(self):
        for event in self.stream:
            if event.type == "message_start" and event.message.content is None:
                event.message.content = []
            yield event

    def close(self) -> None:
        self.stream.close()


def stream_sensenova_messages(client: Any, **kwargs: Any) -> Any:
    """Keep native SDK streaming while accepting SenseNova's initial SSE shape."""
    from anthropic import NOT_GIVEN
    from anthropic.lib.streaming import MessageStream

    stream = client.messages.create(stream=True, **kwargs)
    return MessageStream(_SenseNovaMessageEvents(stream), NOT_GIVEN)


def build_sensenova_openai_options(sensenova_config: Any, model_id: Optional[str] = None) -> Dict[str, Any]:
    """Build OpenAI Chat options for SenseNova models that use that transport."""
    cfg = normalize_sensenova_config(sensenova_config)
    selected = resolve_sensenova_selected_model(cfg, model_id=model_id)
    selected_id = str((selected or {}).get("id") or "").strip().lower()
    output_limit = int((selected or {}).get("max_output_tokens") or SENSENOVA_DEFAULT_MAX_TOKENS)
    requested_max_tokens = max(1, int(cfg.get("max_tokens") or output_limit))
    is_flash_lite = selected_id == "sensenova-6.8-flash-lite"
    supports_reasoning_effort = selected_id in {
        "deepseek-v4-flash",
        "sensenova-6.8-flash-lite",
    }
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
