"""
NVIDIA integration helpers.

This source supports a mixed NVIDIA-hosted catalog where each model can require
its own transport, payload defaults, and transcript normalization policy.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional


NVIDIA_DEFAULT_API_URL = "https://integrate.api.nvidia.com/v1"
NVIDIA_DEFAULT_REQUEST_ENDPOINT = "/chat/completions"
NVIDIA_DEFAULT_MODEL_ID = "qwen/qwen3.5-397b-a17b"
NVIDIA_DEFAULT_MODEL_DISPLAY_NAME = "Qwen3.5-397B-A17B"
NVIDIA_API_KEY_HINT_URL = "https://build.nvidia.com/settings/api-keys"
NVIDIA_DEFAULT_IMAGE_TOKEN_ESTIMATE = 1024
NVIDIA_DEFAULT_CONTEXT_TOKENS = 262_144


def _request_model(
    model_id: str,
    display_name: str,
    description: str,
    *,
    vision: bool = False,
    thinking: bool = False,
    context_length: Optional[int] = None,
    tool_calling: bool = True,
    system_message_first: bool = True,
) -> Dict[str, Any]:
    # NVIDIA request-transport models in this catalog are treated as agentic
    # by default so tool loops stay enabled unless an entry opts out.
    return {
        "id": model_id,
        "display_name": display_name,
        "description": description,
        "transport": "request",
        "vision": bool(vision),
        "thinking": bool(thinking),
        "context_length": context_length,
        "tool_calling": bool(tool_calling),
        "system_message_first": bool(system_message_first),
    }


def _openai_model(
    model_id: str,
    display_name: str,
    description: str,
    *,
    vision: bool = False,
    thinking: bool = False,
    context_length: Optional[int] = None,
    tool_calling: bool = True,
    system_message_first: bool = True,
) -> Dict[str, Any]:
    return {
        "id": model_id,
        "display_name": display_name,
        "description": description,
        "transport": "openai-sdk",
        "vision": bool(vision),
        "thinking": bool(thinking),
        "context_length": context_length,
        "tool_calling": bool(tool_calling),
        "system_message_first": bool(system_message_first),
    }


_NVIDIA_MODEL_CATALOG: List[Dict[str, Any]] = [
    _request_model(
        "mistralai/mistral-small-4-119b-2603",
        "Mistral Small 4 119B",
        "Request transport, reasoning_effort=high.",
        vision=True,
        thinking=True,
        context_length=NVIDIA_DEFAULT_CONTEXT_TOKENS,
    ),
    _request_model(
        "qwen/qwen3.5-122b-a10b",
        "Qwen3.5 122B A10B",
        "Request transport with enable_thinking.",
        vision=True,
        thinking=True,
        context_length=NVIDIA_DEFAULT_CONTEXT_TOKENS,
    ),
    _openai_model(
        "nvidia/nemotron-3-super-120b-a12b",
        "Nemotron 3 Super 120B",
        "OpenAI SDK transport with reasoning_budget. Supports up to 1M context; default serving is 256k.",
        thinking=True,
        context_length=NVIDIA_DEFAULT_CONTEXT_TOKENS,
    ),
    _openai_model(
        "minimaxai/minimax-m2.5",
        "MiniMax M2.5",
        "OpenAI SDK transport.",
        context_length=204800,
    ),
    _request_model(
        "qwen/qwen3.5-397b-a17b",
        "Qwen3.5 397B A17B",
        "Request transport with enable_thinking, top_k, and repetition controls.",
        vision=True,
        thinking=True,
        context_length=NVIDIA_DEFAULT_CONTEXT_TOKENS,
    ),
    _openai_model(
        "z-ai/glm5",
        "GLM-5",
        "OpenAI SDK transport with clear_thinking=False.",
        thinking=True,
        context_length=205000,
    ),
    _openai_model(
        "stepfun-ai/step-3.5-flash",
        "Step-3.5-Flash",
        "OpenAI SDK transport.",
        thinking=True,
        context_length=256000,
    ),
    _request_model(
        "moonshotai/kimi-k2.5",
        "Kimi K2.5",
        "Request transport with chat_template_kwargs.thinking.",
        vision=True,
        thinking=True,
        context_length=NVIDIA_DEFAULT_CONTEXT_TOKENS,
    ),
    _request_model(
        "mistralai/mistral-large-3-675b-instruct-2512",
        "Mistral Large 3 675B",
        "Request transport with instruct defaults.",
        vision=True,
        context_length=NVIDIA_DEFAULT_CONTEXT_TOKENS,
    ),
    _openai_model(
        "openai/gpt-oss-120b",
        "GPT-OSS-120B",
        "OpenAI SDK transport.",
        thinking=True,
        context_length=128000,
    ),
]

_NVIDIA_MODEL_METADATA = {
    str(item["id"]).strip().lower(): dict(item) for item in _NVIDIA_MODEL_CATALOG
}
_NVIDIA_API_HOSTS = ("integrate.api.nvidia.com",)


def default_nvidia_config() -> Dict[str, Any]:
    """Default NVIDIA provider config stored inside Reverie config.json."""
    return {
        "enabled": True,
        "api_key": "",
        "selected_model_id": NVIDIA_DEFAULT_MODEL_ID,
        "selected_model_display_name": NVIDIA_DEFAULT_MODEL_DISPLAY_NAME,
        "api_url": NVIDIA_DEFAULT_API_URL,
        "endpoint": NVIDIA_DEFAULT_REQUEST_ENDPOINT,
        "max_context_tokens": NVIDIA_DEFAULT_CONTEXT_TOKENS,
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


def get_nvidia_model_metadata(model_id: Any) -> Optional[Dict[str, Any]]:
    """Return metadata for one NVIDIA model id."""
    wanted = str(model_id or "").strip().lower()
    if not wanted:
        return None
    found = _NVIDIA_MODEL_METADATA.get(wanted)
    return dict(found) if found else None


def is_nvidia_model(model_id: Any) -> bool:
    """Whether the given model id is part of Reverie's NVIDIA catalog."""
    return get_nvidia_model_metadata(model_id) is not None


def nvidia_model_allows_tools(model_id: Any) -> bool:
    """Whether Reverie should send tool-calling fields for this NVIDIA model."""
    metadata = get_nvidia_model_metadata(model_id)
    return bool(metadata and metadata.get("tool_calling"))


def nvidia_model_requires_system_message_first(model_id: Any) -> bool:
    """Whether a NVIDIA-served model requires all system instructions to lead the transcript."""
    metadata = get_nvidia_model_metadata(model_id)
    if not metadata:
        return False
    return bool(metadata.get("system_message_first", True))


def is_nvidia_api_url(api_url: Any) -> bool:
    """Whether the given URL points at NVIDIA's hosted integrate API."""
    value = str(api_url or "").strip().lower()
    if not value:
        return False
    return any(host in value for host in _NVIDIA_API_HOSTS)


def normalize_nvidia_config(raw_nvidia: Any) -> Dict[str, Any]:
    """Normalize NVIDIA config for persistence and runtime usage."""
    cfg = default_nvidia_config()
    if isinstance(raw_nvidia, dict):
        cfg.update(raw_nvidia)

    cfg["api_key"] = str(cfg.get("api_key", "") or "").strip()
    cfg["selected_model_id"] = (
        str(cfg.get("selected_model_id", NVIDIA_DEFAULT_MODEL_ID) or "").strip()
        or NVIDIA_DEFAULT_MODEL_ID
    )
    cfg["selected_model_display_name"] = (
        str(cfg.get("selected_model_display_name", NVIDIA_DEFAULT_MODEL_DISPLAY_NAME) or "").strip()
        or NVIDIA_DEFAULT_MODEL_DISPLAY_NAME
    )

    api_url = str(cfg.get("api_url", NVIDIA_DEFAULT_API_URL) or "").strip()
    if api_url and not api_url.startswith(("http://", "https://")):
        api_url = f"https://{api_url}"
    cfg["api_url"] = api_url.rstrip("/") or NVIDIA_DEFAULT_API_URL

    endpoint = str(cfg.get("endpoint", NVIDIA_DEFAULT_REQUEST_ENDPOINT) or "").strip()
    if endpoint.lower() in {"clear", "none", "default", "off"}:
        endpoint = NVIDIA_DEFAULT_REQUEST_ENDPOINT
    cfg["endpoint"] = endpoint or NVIDIA_DEFAULT_REQUEST_ENDPOINT

    for key, default_value in (
        ("max_context_tokens", NVIDIA_DEFAULT_CONTEXT_TOKENS),
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
        context_length = matched.get("context_length")
        if context_length:
            cfg["max_context_tokens"] = int(context_length)

    return cfg


def _normalize_api_url(api_url: Any) -> str:
    base = str(api_url or "").strip().rstrip("/")
    if not base:
        return NVIDIA_DEFAULT_API_URL
    if not base.startswith(("http://", "https://")):
        base = f"https://{base}"
    return base.rstrip("/")


def resolve_nvidia_request_url(api_url: str, endpoint: str = "") -> str:
    """Resolve the effective NVIDIA chat-completions URL."""
    base = _normalize_api_url(api_url)
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


def resolve_nvidia_sdk_base_url(api_url: Any) -> str:
    """Resolve the NVIDIA SDK base URL and strip any chat-completions suffix."""
    base = _normalize_api_url(api_url)
    lower_base = base.lower()
    if lower_base.endswith("/chat/completions"):
        return base[: -len("/chat/completions")]
    return base


def resolve_nvidia_selected_model(nvidia_config: Any) -> Optional[Dict[str, Any]]:
    """Resolve selected NVIDIA model metadata from config."""
    cfg = default_nvidia_config()
    if isinstance(nvidia_config, dict):
        cfg.update(nvidia_config)
    wanted = str(cfg.get("selected_model_id", NVIDIA_DEFAULT_MODEL_ID) or "").strip().lower()
    matched = get_nvidia_model_metadata(wanted)
    if matched:
        return matched
    return get_nvidia_model_catalog()[0]


def get_nvidia_default_vision_model() -> Dict[str, Any]:
    """Return the default NVIDIA model that supports image input."""
    selected = get_nvidia_model_metadata(NVIDIA_DEFAULT_MODEL_ID)
    if selected and selected.get("vision"):
        return selected
    for item in get_nvidia_model_catalog():
        if item.get("vision"):
            return item
    return get_nvidia_model_catalog()[0]


def is_nvidia_model_vision_capable(model_id: Any) -> bool:
    """Whether the given NVIDIA model supports inline image input."""
    metadata = get_nvidia_model_metadata(model_id)
    return bool(metadata and metadata.get("vision"))


def build_nvidia_runtime_model_data(nvidia_config: Any) -> Optional[Dict[str, Any]]:
    """Build runtime model config dict for agent initialization."""
    cfg = normalize_nvidia_config(nvidia_config)
    if not cfg.get("enabled", True):
        return None

    selected = resolve_nvidia_selected_model(cfg)
    if not selected:
        return None

    transport = str(selected.get("transport", "request")).strip().lower()
    provider = "request" if transport == "request" else "openai-sdk"
    base_url = (
        resolve_nvidia_request_url(cfg["api_url"], cfg.get("endpoint", ""))
        if provider == "request"
        else resolve_nvidia_sdk_base_url(cfg["api_url"])
    )

    return {
        "model": selected["id"],
        "model_display_name": selected["display_name"],
        "base_url": base_url,
        "api_key": cfg.get("api_key", ""),
        "max_context_tokens": int(selected.get("context_length") or cfg.get("max_context_tokens", NVIDIA_DEFAULT_CONTEXT_TOKENS)),
        "provider": provider,
        "thinking_mode": "true" if bool(cfg.get("enable_thinking", True)) else "false",
        "endpoint": "" if provider != "request" else "",
        "custom_headers": {},
        "vision": bool(selected.get("vision", False)),
    }


def _build_request_mistral_small_options() -> Dict[str, Any]:
    return {
        "max_tokens": 16384,
        "temperature": 0.10,
        "top_p": 1.00,
        "reasoning_effort": "high",
    }


def _build_request_qwen_122_options() -> Dict[str, Any]:
    return {
        "max_tokens": 16384,
        "temperature": 0.60,
        "top_p": 0.95,
        "chat_template_kwargs": {"enable_thinking": True},
    }


def _build_request_qwen_397_options() -> Dict[str, Any]:
    return {
        "max_tokens": 16384,
        "temperature": 0.60,
        "top_p": 0.95,
        "top_k": 20,
        "presence_penalty": 0.0,
        "repetition_penalty": 1.0,
        "chat_template_kwargs": {"enable_thinking": True},
    }


def _build_request_kimi_k25_options() -> Dict[str, Any]:
    return {
        "max_tokens": 16384,
        "temperature": 1.00,
        "top_p": 1.00,
        "chat_template_kwargs": {"thinking": True},
    }


def _build_request_mistral_large_options() -> Dict[str, Any]:
    return {
        "max_tokens": 2048,
        "temperature": 0.15,
        "top_p": 1.00,
        "frequency_penalty": 0.0,
        "presence_penalty": 0.0,
    }


_NVIDIA_REQUEST_OPTION_BUILDERS = {
    "mistralai/mistral-small-4-119b-2603": _build_request_mistral_small_options,
    "qwen/qwen3.5-122b-a10b": _build_request_qwen_122_options,
    "qwen/qwen3.5-397b-a17b": _build_request_qwen_397_options,
    "moonshotai/kimi-k2.5": _build_request_kimi_k25_options,
    "mistralai/mistral-large-3-675b-instruct-2512": _build_request_mistral_large_options,
}


def _build_openai_nemotron_options() -> Dict[str, Any]:
    return {
        "temperature": 1.0,
        "top_p": 0.95,
        "max_tokens": 16384,
        "extra_body": {
            "chat_template_kwargs": {"enable_thinking": True},
            "reasoning_budget": 16384,
        },
    }


def _build_openai_minimax_options() -> Dict[str, Any]:
    return {
        "temperature": 1.0,
        "top_p": 0.95,
        "max_tokens": 8192,
    }


def _build_openai_glm5_options() -> Dict[str, Any]:
    return {
        "temperature": 1.0,
        "top_p": 1.0,
        "max_tokens": 16384,
        "extra_body": {
            "chat_template_kwargs": {
                "enable_thinking": True,
                "clear_thinking": False,
            }
        },
    }


def _build_openai_step_flash_options() -> Dict[str, Any]:
    return {
        "temperature": 1.0,
        "top_p": 0.9,
        "max_tokens": 16384,
    }


def _build_openai_gpt_oss_options() -> Dict[str, Any]:
    return {
        "temperature": 1.0,
        "top_p": 1.0,
        "max_tokens": 4096,
    }


_NVIDIA_OPENAI_OPTION_BUILDERS = {
    "nvidia/nemotron-3-super-120b-a12b": _build_openai_nemotron_options,
    "minimaxai/minimax-m2.5": _build_openai_minimax_options,
    "z-ai/glm5": _build_openai_glm5_options,
    "stepfun-ai/step-3.5-flash": _build_openai_step_flash_options,
    "openai/gpt-oss-120b": _build_openai_gpt_oss_options,
}


def _merge_nested_dict(target: Dict[str, Any], extra: Dict[str, Any]) -> Dict[str, Any]:
    """Merge one level of nested dicts without mutating the source."""
    merged = dict(target)
    for key, value in extra.items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            nested = dict(merged.get(key, {}))
            nested.update(value)
            merged[key] = nested
        else:
            merged[key] = value
    return merged


def build_nvidia_request_defaults(nvidia_config: Any, model_id: Optional[str] = None) -> Dict[str, Any]:
    """Return request-provider defaults for the selected NVIDIA model."""
    cfg = normalize_nvidia_config(nvidia_config)
    selected = get_nvidia_model_metadata(model_id or cfg.get("selected_model_id"))
    if not selected:
        selected = resolve_nvidia_selected_model(cfg)
    if not selected or str(selected.get("transport", "")).strip().lower() != "request":
        return {}

    builder = _NVIDIA_REQUEST_OPTION_BUILDERS.get(str(selected["id"]).strip().lower())
    return dict(builder() if callable(builder) else {})


def apply_nvidia_request_defaults(payload: Dict[str, Any], nvidia_config: Any) -> Dict[str, Any]:
    """Merge the NVIDIA model's dedicated request payload defaults."""
    prepared = dict(payload or {})
    defaults = build_nvidia_request_defaults(nvidia_config, prepared.get("model"))
    if not defaults:
        return prepared

    for key, value in defaults.items():
        if key == "chat_template_kwargs" and isinstance(value, dict):
            existing = prepared.get("chat_template_kwargs")
            if not isinstance(existing, dict):
                existing = {}
            prepared["chat_template_kwargs"] = _merge_nested_dict(existing, value)
            continue
        prepared.setdefault(key, value)
    return prepared


def build_nvidia_openai_options(nvidia_config: Any, model_id: Optional[str] = None) -> Dict[str, Any]:
    """Return OpenAI SDK request options for the selected NVIDIA model."""
    cfg = normalize_nvidia_config(nvidia_config)
    selected = get_nvidia_model_metadata(model_id or cfg.get("selected_model_id"))
    if not selected:
        selected = resolve_nvidia_selected_model(cfg)
    if not selected or str(selected.get("transport", "")).strip().lower() != "openai-sdk":
        return {}

    builder = _NVIDIA_OPENAI_OPTION_BUILDERS.get(str(selected["id"]).strip().lower())
    return dict(builder() if callable(builder) else {})


def build_nvidia_inline_image_notice(attachments: List[Dict[str, Any]]) -> str:
    """Return a compact attachment summary appended to user text blocks."""
    if not attachments:
        return ""
    lines = ["Attached local image files:"]
    for item in attachments:
        path_text = str(item.get("file_path", "") or "").strip()
        file_name = str(item.get("file_name", "") or "").strip() or path_text
        lines.append(f"- {file_name} ({path_text})")
    return "\n".join(lines)


def mask_secret(secret: str) -> str:
    """Mask secrets for safe terminal display."""
    value = str(secret or "").strip()
    if len(value) <= 8:
        return "*" * len(value)
    return f"{value[:4]}...{value[-4:]}"
