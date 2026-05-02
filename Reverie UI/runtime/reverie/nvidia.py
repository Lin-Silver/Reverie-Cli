"""
NVIDIA integration helpers.

This source supports a mixed NVIDIA-hosted catalog where each model can require
its own transport, payload defaults, and transcript normalization policy.
"""

from __future__ import annotations

import os
from typing import Any, Dict, List, Optional

from .nvidia_profiles import (
    build_openai_options as build_nvidia_profile_openai_options,
    build_request_defaults as build_nvidia_profile_request_defaults,
    get_context_tokens as get_nvidia_profile_context_tokens,
    get_profile_name as get_nvidia_profile_name,
)


NVIDIA_DEFAULT_API_URL = "https://integrate.api.nvidia.com/v1"
NVIDIA_DEFAULT_REQUEST_ENDPOINT = "/chat/completions"
NVIDIA_DEFAULT_MODEL_ID = "qwen/qwen3.5-397b-a17b"
NVIDIA_DEFAULT_MODEL_DISPLAY_NAME = "Qwen3.5 397B A17B"
NVIDIA_COMPUTER_CONTROLLER_MODEL_ID = NVIDIA_DEFAULT_MODEL_ID
NVIDIA_COMPUTER_CONTROLLER_MODEL_DISPLAY_NAME = NVIDIA_DEFAULT_MODEL_DISPLAY_NAME
NVIDIA_API_KEY_HINT_URL = "https://build.nvidia.com/settings/api-keys"
NVIDIA_DEFAULT_IMAGE_TOKEN_ESTIMATE = 1024
NVIDIA_DEFAULT_CONTEXT_TOKENS = 262_144
NVIDIA_NEMOTRON_3_SUPER_CONTEXT_TOKENS = 1_000_000
NVIDIA_MINIMAX_CONTEXT_TOKENS = 204_800
NVIDIA_GLM_CONTEXT_TOKENS = 131_072
NVIDIA_STEP_FLASH_CONTEXT_TOKENS = 256_000
NVIDIA_GPT_OSS_120B_CONTEXT_TOKENS = 128_000
NVIDIA_KIMI_K2_6_CONTEXT_TOKENS = 262_144
NVIDIA_DEEPSEEK_V4_CONTEXT_TOKENS = 1_000_000
NVIDIA_DEFAULT_REASONING_EFFORT = "high"
NVIDIA_DEFAULT_REASONING_BUDGET = 16_384
NVIDIA_REASONING_EFFORTS = ("max", "high", "medium", "low", "none")


def _coerce_bool(value: Any, default: bool = True) -> bool:
    if isinstance(value, bool):
        return value
    if value is None:
        return default
    text = str(value).strip().lower()
    if text in {"1", "true", "yes", "y", "on", "enable", "enabled", "thinking"}:
        return True
    if text in {"0", "false", "no", "n", "off", "disable", "disabled", "none", "non-think"}:
        return False
    return default


def normalize_nvidia_reasoning_effort(value: Any, default: str = NVIDIA_DEFAULT_REASONING_EFFORT) -> str:
    """Normalize a compact NVIDIA hosted-model thinking depth value."""
    text = str(value or "").strip().lower().replace("_", " ").replace("-", " ")
    aliases = {
        "": default,
        "default": default,
        "auto": default,
        "max": "max",
        "maximum": "max",
        "extra high": "max",
        "xhigh": "max",
        "high": "high",
        "think high": "high",
        "medium": "medium",
        "med": "medium",
        "normal": "medium",
        "low": "low",
        "light": "low",
        "low effort": "low",
        "none": "none",
        "off": "none",
        "false": "none",
        "0": "none",
        "no": "none",
        "non think": "none",
        "nonthinking": "none",
        "non thinking": "none",
        "no thinking": "none",
    }
    normalized = aliases.get(text, text)
    if normalized not in NVIDIA_REASONING_EFFORTS:
        normalized = default if default in NVIDIA_REASONING_EFFORTS else NVIDIA_DEFAULT_REASONING_EFFORT
    return normalized


def get_nvidia_reasoning_effort_label(value: Any) -> str:
    effort = normalize_nvidia_reasoning_effort(value)
    return {
        "max": "Max",
        "high": "High",
        "medium": "Medium",
        "low": "Low",
        "none": "Non-think",
    }.get(effort, "High")


def _thinking_option(option_id: str, label: str, description: str) -> Dict[str, str]:
    return {
        "id": str(option_id).strip().lower(),
        "label": str(label).strip(),
        "description": str(description).strip(),
    }


NVIDIA_THINKING_TOGGLE_OPTIONS = (
    _thinking_option("true", "Thinking ON", "Enable provider-side thinking for this model."),
    _thinking_option("false", "Thinking OFF", "Disable provider-side thinking for faster direct replies."),
)
NVIDIA_REASONING_NONE_HIGH_OPTIONS = (
    _thinking_option("high", "High", "Full reasoning mode for complex work."),
    _thinking_option("none", "Non-think", "Disable reasoning for faster lightweight replies."),
)
NVIDIA_REASONING_NONE_LOW_HIGH_OPTIONS = (
    _thinking_option("high", "High", "Full reasoning mode."),
    _thinking_option("low", "Low", "Low-effort reasoning with fewer reasoning tokens."),
    _thinking_option("none", "Non-think", "Disable reasoning tokens."),
)
NVIDIA_REASONING_NONE_HIGH_MAX_OPTIONS = (
    _thinking_option("high", "High", "High reasoning mode."),
    _thinking_option("max", "Max", "Maximum reasoning effort."),
    _thinking_option("none", "Non-think", "Disable thinking."),
)
NVIDIA_REASONING_LOW_MEDIUM_HIGH_OPTIONS = (
    _thinking_option("low", "Low", "Basic reasoning with lower latency."),
    _thinking_option("medium", "Medium", "Balanced reasoning depth."),
    _thinking_option("high", "High", "Detailed step-by-step reasoning."),
)


def _normalize_thinking_options(options: Any) -> List[Dict[str, str]]:
    normalized: List[Dict[str, str]] = []
    if not isinstance(options, (list, tuple)):
        return normalized
    seen: set[str] = set()
    for item in options:
        if not isinstance(item, dict):
            continue
        option_id = str(item.get("id", "") or "").strip().lower()
        if not option_id or option_id in seen:
            continue
        seen.add(option_id)
        normalized.append(
            _thinking_option(
                option_id,
                str(item.get("label") or get_nvidia_reasoning_effort_label(option_id)),
                str(item.get("description") or ""),
            )
        )
    return normalized


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
    thinking_control: str = "none",
    thinking_options: Optional[List[Dict[str, str]]] = None,
    default_thinking_choice: str = "",
) -> Dict[str, Any]:
    profile_context_length = get_nvidia_profile_context_tokens(
        model_id,
        transport="request",
        fallback=context_length,
    )
    # NVIDIA request-transport models in this catalog are treated as agentic
    # by default so tool loops stay enabled unless an entry opts out.
    metadata = {
        "id": model_id,
        "display_name": display_name,
        "description": description,
        "transport": "request",
        "vision": bool(vision),
        "thinking": bool(thinking),
        "context_length": profile_context_length,
        "tool_calling": bool(tool_calling),
        "system_message_first": bool(system_message_first),
        "thinking_control": str(thinking_control or ("toggle" if thinking else "none")).strip().lower(),
        "profile": str(model_id).strip().lower(),
    }
    options = _normalize_thinking_options(thinking_options)
    if options:
        metadata["thinking_options"] = options
        option_ids = {item["id"] for item in options}
        normalized_default = str(default_thinking_choice or "").strip().lower()
        metadata["default_thinking_choice"] = normalized_default if normalized_default in option_ids else options[0]["id"]
    return metadata


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
    thinking_control: str = "none",
    thinking_options: Optional[List[Dict[str, str]]] = None,
    default_thinking_choice: str = "",
) -> Dict[str, Any]:
    profile_context_length = get_nvidia_profile_context_tokens(
        model_id,
        transport="openai-sdk",
        fallback=context_length,
    )
    metadata = {
        "id": model_id,
        "display_name": display_name,
        "description": description,
        "transport": "openai-sdk",
        "vision": bool(vision),
        "thinking": bool(thinking),
        "context_length": profile_context_length,
        "tool_calling": bool(tool_calling),
        "system_message_first": bool(system_message_first),
        "thinking_control": str(thinking_control or ("toggle" if thinking else "none")).strip().lower(),
        "profile": str(model_id).strip().lower(),
    }
    options = _normalize_thinking_options(thinking_options)
    if options:
        metadata["thinking_options"] = options
        option_ids = {item["id"] for item in options}
        normalized_default = str(default_thinking_choice or "").strip().lower()
        metadata["default_thinking_choice"] = normalized_default if normalized_default in option_ids else options[0]["id"]
    return metadata


_NVIDIA_MODEL_CATALOG: List[Dict[str, Any]] = [
    _request_model(
        "mistralai/mistral-small-4-119b-2603",
        "Mistral Small 4 119B",
        "Request transport with selectable reasoning_effort none/high.",
        vision=True,
        thinking=True,
        thinking_control="effort",
        thinking_options=list(NVIDIA_REASONING_NONE_HIGH_OPTIONS),
        default_thinking_choice="high",
        context_length=NVIDIA_DEFAULT_CONTEXT_TOKENS,
    ),
    _request_model(
        "mistralai/mistral-medium-3.5-128b",
        "Mistral Medium 3.5 128B",
        "Request transport with 256k multimodal context and selectable reasoning_effort none/high.",
        vision=True,
        thinking=True,
        thinking_control="effort",
        thinking_options=list(NVIDIA_REASONING_NONE_HIGH_OPTIONS),
        default_thinking_choice="high",
        context_length=NVIDIA_DEFAULT_CONTEXT_TOKENS,
    ),
    _request_model(
        "qwen/qwen3.5-122b-a10b",
        "Qwen3.5 122B A10B",
        "Request transport with enable_thinking.",
        vision=True,
        thinking=True,
        thinking_control="toggle",
        thinking_options=list(NVIDIA_THINKING_TOGGLE_OPTIONS),
        default_thinking_choice="true",
        context_length=NVIDIA_DEFAULT_CONTEXT_TOKENS,
    ),
    _openai_model(
        "nvidia/nemotron-3-super-120b-a12b",
        "Nemotron 3 Super 120B",
        "OpenAI SDK transport with selectable none/low/high reasoning and optional reasoning_budget.",
        thinking=True,
        thinking_control="effort",
        thinking_options=list(NVIDIA_REASONING_NONE_LOW_HIGH_OPTIONS),
        default_thinking_choice="high",
        context_length=NVIDIA_NEMOTRON_3_SUPER_CONTEXT_TOKENS,
    ),
    _openai_model(
        "minimaxai/minimax-m2.7",
        "MiniMax M2.7",
        "OpenAI SDK transport.",
        context_length=NVIDIA_MINIMAX_CONTEXT_TOKENS,
    ),
    _request_model(
        "qwen/qwen3.5-397b-a17b",
        "Qwen3.5 397B A17B",
        "Request transport with enable_thinking, top_k, and repetition controls.",
        vision=True,
        thinking=True,
        thinking_control="toggle",
        thinking_options=list(NVIDIA_THINKING_TOGGLE_OPTIONS),
        default_thinking_choice="true",
        context_length=NVIDIA_DEFAULT_CONTEXT_TOKENS,
    ),
    _openai_model(
        "z-ai/glm-5.1",
        "GLM-5.1",
        "OpenAI SDK transport with clear_thinking=False.",
        thinking=True,
        thinking_control="toggle",
        thinking_options=list(NVIDIA_THINKING_TOGGLE_OPTIONS),
        default_thinking_choice="true",
        context_length=NVIDIA_GLM_CONTEXT_TOKENS,
    ),
    _openai_model(
        "stepfun-ai/step-3.5-flash",
        "Step-3.5-Flash",
        "OpenAI SDK transport.",
        thinking=True,
        thinking_control="fixed",
        context_length=NVIDIA_STEP_FLASH_CONTEXT_TOKENS,
    ),
    _openai_model(
        "deepseek-ai/deepseek-v4-pro",
        "DeepSeek V4 Pro",
        "OpenAI SDK transport with 1M context and selectable Non-think/High/Max chat-template reasoning.",
        thinking=True,
        thinking_control="effort",
        thinking_options=list(NVIDIA_REASONING_NONE_HIGH_MAX_OPTIONS),
        default_thinking_choice="high",
        context_length=NVIDIA_DEEPSEEK_V4_CONTEXT_TOKENS,
    ),
    _openai_model(
        "deepseek-ai/deepseek-v4-flash",
        "DeepSeek V4 Flash",
        "OpenAI SDK transport with 1M context and selectable Non-think/High/Max chat-template reasoning.",
        thinking=True,
        thinking_control="effort",
        thinking_options=list(NVIDIA_REASONING_NONE_HIGH_MAX_OPTIONS),
        default_thinking_choice="high",
        context_length=NVIDIA_DEEPSEEK_V4_CONTEXT_TOKENS,
    ),
    _request_model(
        "mistralai/mistral-large-3-675b-instruct-2512",
        "Mistral Large 3 675B",
        "Request transport with instruct defaults.",
        vision=True,
        context_length=NVIDIA_DEFAULT_CONTEXT_TOKENS,
    ),
    _request_model(
        "moonshotai/kimi-k2.6",
        "Kimi K2.6",
        "Request transport with chat-template thinking controls.",
        vision=True,
        thinking=True,
        thinking_control="toggle",
        thinking_options=list(NVIDIA_THINKING_TOGGLE_OPTIONS),
        default_thinking_choice="true",
        context_length=NVIDIA_KIMI_K2_6_CONTEXT_TOKENS,
    ),
    _openai_model(
        "openai/gpt-oss-120b",
        "GPT-OSS-120B",
        "OpenAI SDK transport with selectable low/medium/high reasoning_effort.",
        thinking=True,
        thinking_control="effort",
        thinking_options=list(NVIDIA_REASONING_LOW_MEDIUM_HIGH_OPTIONS),
        default_thinking_choice="medium",
        context_length=NVIDIA_GPT_OSS_120B_CONTEXT_TOKENS,
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
        "timeout": 60,
        "max_tokens": 16384,
        "temperature": 0.60,
        "top_p": 0.95,
        "top_k": 20,
        "presence_penalty": 0.0,
        "repetition_penalty": 1.0,
        "enable_thinking": True,
        "reasoning_effort": NVIDIA_DEFAULT_REASONING_EFFORT,
        "reasoning_budget": NVIDIA_DEFAULT_REASONING_BUDGET,
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


def get_nvidia_thinking_options(model_id: Any) -> List[Dict[str, str]]:
    """Return fixed user-selectable thinking options for one NVIDIA model."""
    metadata = get_nvidia_model_metadata(model_id)
    if not metadata:
        return []
    return [dict(item) for item in _normalize_thinking_options(metadata.get("thinking_options", []))]


def get_nvidia_default_thinking_choice(model_id: Any) -> str:
    """Return the default thinking option id for one NVIDIA model."""
    options = get_nvidia_thinking_options(model_id)
    if not options:
        return ""
    option_ids = {item["id"] for item in options}
    metadata = get_nvidia_model_metadata(model_id) or {}
    configured = str(metadata.get("default_thinking_choice", "") or "").strip().lower()
    return configured if configured in option_ids else options[0]["id"]


def normalize_nvidia_thinking_choice(model_id: Any, value: Any, default: Optional[str] = None) -> str:
    """Normalize a model-specific NVIDIA thinking option id."""
    options = get_nvidia_thinking_options(model_id)
    if not options:
        return str(default or "").strip().lower()

    option_ids = {item["id"] for item in options}
    fallback = str(default or "").strip().lower()
    if fallback not in option_ids:
        fallback = get_nvidia_default_thinking_choice(model_id)

    text = str(value or "").strip().lower().replace("_", " ").replace("-", " ")
    control = str((get_nvidia_model_metadata(model_id) or {}).get("thinking_control", "") or "").strip().lower()
    aliases = {
        "": fallback,
        "default": fallback,
        "auto": fallback,
        "on": "true" if "true" in option_ids else fallback,
        "enable": "true" if "true" in option_ids else fallback,
        "enabled": "true" if "true" in option_ids else fallback,
        "true": "true" if "true" in option_ids else fallback,
        "yes": "true" if "true" in option_ids else fallback,
        "1": "true" if "true" in option_ids else fallback,
        "off": "false" if "false" in option_ids else ("none" if "none" in option_ids else fallback),
        "disable": "false" if "false" in option_ids else ("none" if "none" in option_ids else fallback),
        "disabled": "false" if "false" in option_ids else ("none" if "none" in option_ids else fallback),
        "false": "false" if "false" in option_ids else ("none" if "none" in option_ids else fallback),
        "no": "false" if "false" in option_ids else ("none" if "none" in option_ids else fallback),
        "0": "false" if "false" in option_ids else ("none" if "none" in option_ids else fallback),
        "non think": "none" if "none" in option_ids else fallback,
        "nonthinking": "none" if "none" in option_ids else fallback,
        "non thinking": "none" if "none" in option_ids else fallback,
        "no thinking": "none" if "none" in option_ids else fallback,
        "none": "none" if "none" in option_ids else fallback,
        "max": "max",
        "maximum": "max",
        "extra high": "max",
        "xhigh": "max",
        "high": "high",
        "medium": "medium",
        "med": "medium",
        "normal": "medium",
        "low": "low",
        "light": "low",
        "low effort": "low",
    }
    normalized = aliases.get(text, text)
    if normalized not in option_ids and control == "toggle":
        normalized = "true" if _coerce_bool(value, fallback != "false") else "false"
    if normalized not in option_ids:
        normalized = fallback
    return normalized


def get_nvidia_thinking_choice_label(model_id: Any, value: Any) -> str:
    """Return a human-readable label for one model-specific thinking option."""
    choice = normalize_nvidia_thinking_choice(model_id, value)
    for item in get_nvidia_thinking_options(model_id):
        if item["id"] == choice:
            return item["label"]
    return get_nvidia_reasoning_effort_label(choice)


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


def nvidia_model_supports_thinking_toggle(model_id: Any) -> bool:
    """Whether this NVIDIA model supports user-selectable thinking on/off."""
    metadata = get_nvidia_model_metadata(model_id)
    return bool(metadata and metadata.get("thinking_control") == "toggle")


def nvidia_model_has_fixed_thinking(model_id: Any) -> bool:
    """Whether this NVIDIA model is a dedicated thinking/reasoning model."""
    metadata = get_nvidia_model_metadata(model_id)
    return bool(metadata and metadata.get("thinking_control") == "fixed")


def resolve_nvidia_model_profile_name(model_id: Any) -> str:
    """Return the concrete NVIDIA profile module selected for one model."""
    metadata = get_nvidia_model_metadata(model_id)
    if not metadata:
        return ""
    profile_name = get_nvidia_profile_name(
        metadata.get("id"),
        transport=str(metadata.get("transport", "") or ""),
    )
    return profile_name or ""


def is_nvidia_api_url(api_url: Any) -> bool:
    """Whether the given URL points at NVIDIA's hosted integrate API."""
    value = str(api_url or "").strip().lower()
    if not value:
        return False
    return any(host in value for host in _NVIDIA_API_HOSTS)


def normalize_nvidia_config(raw_nvidia: Any) -> Dict[str, Any]:
    """Normalize NVIDIA config for persistence and runtime usage."""
    cfg = default_nvidia_config()
    raw_has_reasoning_effort = False
    if isinstance(raw_nvidia, dict):
        raw_has_reasoning_effort = "reasoning_effort" in raw_nvidia
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
        ("timeout", 60),
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

    try:
        reasoning_budget = int(cfg.get("reasoning_budget", NVIDIA_DEFAULT_REASONING_BUDGET))
    except (TypeError, ValueError):
        reasoning_budget = NVIDIA_DEFAULT_REASONING_BUDGET
    if reasoning_budget < -1:
        reasoning_budget = NVIDIA_DEFAULT_REASONING_BUDGET
    cfg["reasoning_budget"] = min(reasoning_budget, 32768)

    cfg["enable_thinking"] = _coerce_bool(cfg.get("enable_thinking", True), True)

    matched = resolve_nvidia_selected_model(cfg)
    if matched:
        cfg["selected_model_id"] = str(matched["id"])
        cfg["selected_model_display_name"] = str(matched["display_name"])
        context_length = matched.get("context_length")
        if context_length:
            cfg["max_context_tokens"] = int(context_length)
        thinking_control = str(matched.get("thinking_control", "none") or "none").strip().lower()
        raw_reasoning_effort = cfg.get("reasoning_effort") if raw_has_reasoning_effort else ""
        if thinking_control == "effort":
            cfg["reasoning_effort"] = normalize_nvidia_thinking_choice(matched["id"], raw_reasoning_effort)
            cfg["enable_thinking"] = cfg["reasoning_effort"] != "none"
        else:
            cfg["reasoning_effort"] = normalize_nvidia_reasoning_effort(cfg.get("reasoning_effort", NVIDIA_DEFAULT_REASONING_EFFORT))

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


def resolve_nvidia_api_key(nvidia_config: Any) -> str:
    """Resolve the effective NVIDIA API key from config or environment."""
    cfg = default_nvidia_config()
    if isinstance(nvidia_config, dict):
        cfg.update(nvidia_config)

    key = str(cfg.get("api_key", "") or "").strip()
    if key:
        return key
    return str(os.getenv("NVIDIA_API_KEY", "") or "").strip()


def resolve_nvidia_selected_model(nvidia_config: Any, model_id: Optional[str] = None) -> Optional[Dict[str, Any]]:
    """Resolve selected NVIDIA model metadata from config or an explicit override."""
    cfg = default_nvidia_config()
    if isinstance(nvidia_config, dict):
        cfg.update(nvidia_config)

    wanted = str(model_id or cfg.get("selected_model_id", NVIDIA_DEFAULT_MODEL_ID) or "").strip().lower()
    matched = get_nvidia_model_metadata(wanted)
    if matched:
        return matched
    return get_nvidia_model_catalog()[0]


def resolve_nvidia_thinking_choice(nvidia_config: Any, model_id: Optional[str] = None) -> str:
    """Resolve the effective persisted thinking option for the selected NVIDIA model."""
    cfg = default_nvidia_config()
    raw_has_effort = False
    if isinstance(nvidia_config, dict):
        raw_has_effort = "reasoning_effort" in nvidia_config
        cfg.update(nvidia_config)

    selected = resolve_nvidia_selected_model(cfg, model_id=model_id)
    if not selected:
        return ""

    selected_id = str(selected.get("id", "") or "")
    thinking_control = str(selected.get("thinking_control", "none") or "none").strip().lower()
    if thinking_control == "toggle":
        return "true" if _coerce_bool(cfg.get("enable_thinking", True), True) else "false"
    if thinking_control == "effort":
        raw_effort = cfg.get("reasoning_effort") if raw_has_effort else ""
        return normalize_nvidia_thinking_choice(selected_id, raw_effort)
    if thinking_control == "fixed":
        return "fixed"
    return ""


def apply_nvidia_thinking_choice(nvidia_config: Any, model_id: Any, choice: Any) -> Dict[str, Any]:
    """Apply a model-specific thinking option to an NVIDIA config dict."""
    cfg = default_nvidia_config()
    if isinstance(nvidia_config, dict):
        cfg.update(nvidia_config)

    selected = resolve_nvidia_selected_model(cfg, model_id=str(model_id or ""))
    if not selected:
        return normalize_nvidia_config(cfg)

    selected_id = str(selected.get("id", "") or "")
    cfg["selected_model_id"] = selected_id
    cfg["selected_model_display_name"] = str(selected.get("display_name", cfg.get("selected_model_display_name", "")))
    thinking_control = str(selected.get("thinking_control", "none") or "none").strip().lower()
    normalized_choice = normalize_nvidia_thinking_choice(selected_id, choice)
    if thinking_control == "toggle":
        cfg["enable_thinking"] = normalized_choice != "false"
    elif thinking_control == "effort":
        cfg["reasoning_effort"] = normalized_choice
        cfg["enable_thinking"] = normalized_choice != "none"
    return normalize_nvidia_config(cfg)


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


def build_nvidia_runtime_model_data(nvidia_config: Any, model_id: Optional[str] = None) -> Optional[Dict[str, Any]]:
    """Build runtime model config dict for agent initialization."""
    cfg = normalize_nvidia_config(nvidia_config)
    if not cfg.get("enabled", True):
        return None

    api_key = resolve_nvidia_api_key(cfg)
    if not api_key:
        return None

    selected = resolve_nvidia_selected_model(cfg, model_id=model_id)
    if not selected:
        return None

    transport = str(selected.get("transport", "request")).strip().lower()
    provider = "request" if transport == "request" else "openai-sdk"
    base_url = (
        resolve_nvidia_request_url(cfg["api_url"], cfg.get("endpoint", ""))
        if provider == "request"
        else resolve_nvidia_sdk_base_url(cfg["api_url"])
    )
    thinking_control = str(selected.get("thinking_control", "") or "").strip().lower()

    return {
        "model": selected["id"],
        "model_display_name": selected["display_name"],
        "base_url": base_url,
        "api_key": api_key,
        "max_context_tokens": int(selected.get("context_length") or cfg.get("max_context_tokens", NVIDIA_DEFAULT_CONTEXT_TOKENS)),
        "provider": provider,
        "thinking_mode": (
            ("true" if bool(cfg.get("enable_thinking", True)) else "false")
            if thinking_control == "toggle"
            else (
                resolve_nvidia_thinking_choice(cfg, selected["id"])
                if thinking_control == "effort"
                else None
            )
        ),
        "endpoint": "" if provider != "request" else "",
        "custom_headers": {},
        "vision": bool(selected.get("vision", False)),
        "profile": resolve_nvidia_model_profile_name(selected["id"]),
    }


def build_nvidia_computer_controller_runtime_model_data(nvidia_config: Any) -> Optional[Dict[str, Any]]:
    """Build runtime model data for Computer Controller mode's pinned NVIDIA model."""
    cfg = normalize_nvidia_config(nvidia_config)
    cfg["enabled"] = True
    return build_nvidia_runtime_model_data(cfg, model_id=NVIDIA_COMPUTER_CONTROLLER_MODEL_ID)


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

    try:
        cfg["max_tokens"] = max(int(cfg.get("max_tokens", 0) or 0), int(selected.get("context_length") or 0))
    except (TypeError, ValueError):
        pass
    return build_nvidia_profile_request_defaults(selected["id"], cfg)


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

    try:
        cfg["max_tokens"] = max(int(cfg.get("max_tokens", 0) or 0), int(selected.get("context_length") or 0))
    except (TypeError, ValueError):
        pass
    return build_nvidia_profile_openai_options(selected["id"], cfg)


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
