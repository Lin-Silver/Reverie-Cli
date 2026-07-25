"""
ModelScope integration helpers.

ModelScope API-Inference exposes an OpenAI-compatible Chat Completions API.
Each catalog entry carries the model-specific chat-template reasoning choices
that desktop clients render directly from the core payload.
"""

from __future__ import annotations

import os
from typing import Any, Dict, List, Optional


MODELSCOPE_DEFAULT_API_URL = "https://api-inference.modelscope.cn/v1"
MODELSCOPE_DEFAULT_ENDPOINT = "/chat/completions"
MODELSCOPE_DEFAULT_MODEL_ID = "stepfun-ai/Step-3.7-Flash"
MODELSCOPE_DEFAULT_MODEL_DISPLAY_NAME = "Step-3.7-Flash"
MODELSCOPE_API_KEY_HINT_URL = "https://www.modelscope.cn/my/access/token"
MODELSCOPE_DEFAULT_CONTEXT_TOKENS = 262_144
MODELSCOPE_DEFAULT_MAX_TOKENS = 16_384
MODELSCOPE_DEEPSEEK_CONTEXT_TOKENS = 1_048_576
MODELSCOPE_DEEPSEEK_MAX_TOKENS = 393_216
MODELSCOPE_GLM_CONTEXT_TOKENS = 1_048_576
MODELSCOPE_GLM_MAX_TOKENS = 131_072
MODELSCOPE_STEP_CONTEXT_TOKENS = 262_144
MODELSCOPE_STEP_MAX_TOKENS = 65_536

_REASONING_LABELS = {
    "none": ("Non-think", "Disable thinking for a faster direct response."),
    "no_think": ("Non-think", "Use the model's direct-response mode."),
    "low": ("Low", "Use a low reasoning effort."),
    "medium": ("Medium", "Use the provider-recommended balanced reasoning effort."),
    "high": ("High", "Use a high reasoning effort for complex work."),
    "max": ("Max", "Use the model's maximum reasoning effort."),
    "true": ("Thinking on", "Enable the ModelScope-hosted reasoning mode."),
    "false": ("Thinking off", "Disable the ModelScope-hosted reasoning mode."),
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


def _modelscope_model(
    model_id: str,
    display_name: str,
    description: str,
    *,
    context_length: int,
    max_output_tokens: int = MODELSCOPE_DEFAULT_MAX_TOKENS,
    vision: bool = False,
    thinking: bool = False,
    tool_calling: bool = True,
    thinking_options: Optional[List[Dict[str, str]]] = None,
    default_thinking_choice: str = "",
    thinking_control: str = "",
) -> Dict[str, Any]:
    return {
        "id": model_id,
        "display_name": display_name,
        "description": description,
        "transport": "openai-chat",
        "context_length": int(context_length),
        "max_output_tokens": int(max_output_tokens),
        "vision": bool(vision),
        "thinking": bool(thinking),
        "thinking_control": str(
            thinking_control or ("effort" if thinking_options else ("fixed" if thinking else "none"))
        ),
        "thinking_options": list(thinking_options or []),
        "default_thinking_choice": str(default_thinking_choice or ""),
        "tool_calling": bool(tool_calling),
    }


_MODELSCOPE_MODEL_CATALOG: List[Dict[str, Any]] = [
    _modelscope_model(
        "stepfun-ai/Step-3.7-Flash",
        "Step-3.7-Flash",
        "StepFun multimodal agent model with low, medium, and high reasoning.",
        context_length=MODELSCOPE_STEP_CONTEXT_TOKENS,
        max_output_tokens=MODELSCOPE_STEP_MAX_TOKENS,
        vision=True,
        thinking=True,
        thinking_options=_reasoning_options("low", "medium", "high"),
        default_thinking_choice="medium",
    ),
    _modelscope_model(
        "ZhipuAI/GLM-5.2",
        "GLM-5.2",
        "Z.ai long-context coding model with selectable reasoning effort.",
        context_length=MODELSCOPE_GLM_CONTEXT_TOKENS,
        max_output_tokens=MODELSCOPE_GLM_MAX_TOKENS,
        thinking=True,
        thinking_options=_reasoning_options("none", "high", "max"),
        default_thinking_choice="max",
    ),
    _modelscope_model(
        "deepseek-ai/DeepSeek-V4-Pro",
        "DeepSeek V4 Pro",
        "DeepSeek V4 Pro flagship MoE model with the hosted API's reasoning toggle.",
        context_length=MODELSCOPE_DEEPSEEK_CONTEXT_TOKENS,
        max_output_tokens=MODELSCOPE_DEEPSEEK_MAX_TOKENS,
        thinking=True,
        thinking_options=_reasoning_options("true", "false"),
        default_thinking_choice="true",
        thinking_control="toggle",
    ),
    _modelscope_model(
        "deepseek-ai/DeepSeek-V4-Flash",
        "DeepSeek V4 Flash",
        "DeepSeek V4 Flash fast MoE model with the hosted API's reasoning toggle.",
        context_length=MODELSCOPE_DEEPSEEK_CONTEXT_TOKENS,
        max_output_tokens=MODELSCOPE_DEEPSEEK_MAX_TOKENS,
        thinking=True,
        thinking_options=_reasoning_options("true", "false"),
        default_thinking_choice="true",
        thinking_control="toggle",
    ),
]

_MODELSCOPE_MODEL_METADATA = {
    str(item["id"]).strip().lower(): dict(item) for item in _MODELSCOPE_MODEL_CATALOG
}


def default_modelscope_config() -> Dict[str, Any]:
    """Default ModelScope provider config stored in config.json."""
    return {
        "enabled": True,
        "api_key": "",
        "selected_model_id": MODELSCOPE_DEFAULT_MODEL_ID,
        "selected_model_display_name": MODELSCOPE_DEFAULT_MODEL_DISPLAY_NAME,
        "api_url": MODELSCOPE_DEFAULT_API_URL,
        "endpoint": MODELSCOPE_DEFAULT_ENDPOINT,
        "max_context_tokens": MODELSCOPE_DEFAULT_CONTEXT_TOKENS,
        "timeout": 300,
        "max_tokens": MODELSCOPE_DEFAULT_MAX_TOKENS,
        "reasoning_effort": "medium",
    }


def get_modelscope_model_catalog() -> List[Dict[str, Any]]:
    """Return the supported ModelScope model catalog."""
    return [dict(item) for item in _MODELSCOPE_MODEL_CATALOG]


def get_modelscope_model_metadata(model_id: Any) -> Optional[Dict[str, Any]]:
    """Return metadata for one ModelScope model id."""
    wanted = str(model_id or "").strip().lower()
    if not wanted:
        return None
    found = _MODELSCOPE_MODEL_METADATA.get(wanted)
    return dict(found) if found else None


def resolve_modelscope_selected_model(modelscope_config: Any, model_id: Optional[str] = None) -> Optional[Dict[str, Any]]:
    """Resolve selected ModelScope model metadata from config or override."""
    cfg = default_modelscope_config()
    if isinstance(modelscope_config, dict):
        cfg.update(modelscope_config)

    wanted = str(model_id or cfg.get("selected_model_id", MODELSCOPE_DEFAULT_MODEL_ID) or "").strip().lower()
    matched = get_modelscope_model_metadata(wanted)
    if matched:
        return matched
    return get_modelscope_model_metadata(MODELSCOPE_DEFAULT_MODEL_ID)


def _normalize_api_url(api_url: Any) -> str:
    base = str(api_url or "").strip()
    if not base:
        return MODELSCOPE_DEFAULT_API_URL
    if not base.startswith(("http://", "https://")):
        base = f"https://{base}"
    return base.rstrip("/") or MODELSCOPE_DEFAULT_API_URL


def resolve_modelscope_openai_base_url(api_url: Any) -> str:
    """Resolve the OpenAI SDK `/v1` base URL for ModelScope."""
    base = _normalize_api_url(api_url)
    lower_base = base.lower()
    for suffix in ("/v1/chat/completions", "/chat/completions", "/v1/messages", "/messages", "/v1"):
        if lower_base.endswith(suffix):
            base = base[: -len(suffix)]
            lower_base = base.lower()
    root = base.rstrip("/")
    return f"{root}/v1" if root else MODELSCOPE_DEFAULT_API_URL


def resolve_modelscope_anthropic_base_url(api_url: Any) -> str:
    """Backward-compatible alias retained for older configuration callers."""
    return resolve_modelscope_openai_base_url(api_url)


def resolve_modelscope_api_key(modelscope_config: Any) -> str:
    """Resolve the effective ModelScope API key from config or environment."""
    cfg = default_modelscope_config()
    if isinstance(modelscope_config, dict):
        cfg.update(modelscope_config)

    key = str(cfg.get("api_key", "") or "").strip()
    if key:
        return key
    for env_name in ("MODELSCOPE_API_KEY", "MODELSCOPE_TOKEN", "MODELSCOPE_ACCESS_TOKEN"):
        value = str(os.getenv(env_name, "") or "").strip()
        if value:
            return value
    return ""


def normalize_modelscope_config(raw_modelscope: Any) -> Dict[str, Any]:
    """Normalize ModelScope config for persistence and runtime usage."""
    cfg = default_modelscope_config()
    raw_has_reasoning_effort = False
    if isinstance(raw_modelscope, dict):
        raw_has_reasoning_effort = "reasoning_effort" in raw_modelscope
        cfg.update(raw_modelscope)

    cfg["enabled"] = bool(cfg.get("enabled", True))
    cfg["api_key"] = str(cfg.get("api_key", "") or "").strip()
    cfg["api_url"] = resolve_modelscope_openai_base_url(cfg.get("api_url", MODELSCOPE_DEFAULT_API_URL))
    cfg["endpoint"] = MODELSCOPE_DEFAULT_ENDPOINT
    cfg["selected_model_id"] = (
        str(cfg.get("selected_model_id", MODELSCOPE_DEFAULT_MODEL_ID) or "").strip()
        or MODELSCOPE_DEFAULT_MODEL_ID
    )
    cfg["selected_model_display_name"] = (
        str(cfg.get("selected_model_display_name", MODELSCOPE_DEFAULT_MODEL_DISPLAY_NAME) or "").strip()
        or MODELSCOPE_DEFAULT_MODEL_DISPLAY_NAME
    )

    for key, default_value in (
        ("max_context_tokens", MODELSCOPE_DEFAULT_CONTEXT_TOKENS),
        ("timeout", 300),
        ("max_tokens", MODELSCOPE_DEFAULT_MAX_TOKENS),
    ):
        try:
            value = int(cfg.get(key, default_value))
        except (TypeError, ValueError):
            value = default_value
        if value <= 0:
            value = default_value
        cfg[key] = value

    matched = resolve_modelscope_selected_model(cfg)
    if matched:
        cfg["selected_model_id"] = str(matched["id"])
        cfg["selected_model_display_name"] = str(matched["display_name"])
        context_length = matched.get("context_length")
        if context_length:
            cfg["max_context_tokens"] = int(context_length)
        output_limit = int(matched.get("max_output_tokens") or MODELSCOPE_DEFAULT_MAX_TOKENS)
        cfg["max_tokens"] = min(int(cfg.get("max_tokens") or output_limit), output_limit)
        raw_choice = cfg.get("reasoning_effort") if raw_has_reasoning_effort else ""
        cfg["reasoning_effort"] = normalize_modelscope_reasoning_choice(matched["id"], raw_choice)

    return cfg


def normalize_modelscope_reasoning_choice(model_id: Any, value: Any) -> str:
    selected = get_modelscope_model_metadata(model_id) or {}
    options = [str(item.get("id") or "") for item in selected.get("thinking_options", [])]
    default = str(selected.get("default_thinking_choice") or "")
    candidate = str(value or "").strip().lower().replace("-", "_")
    candidate = {
        "off": "none",
        "non_think": "none",
        "nothink": "no_think",
        "med": "medium",
        "xhigh": "max",
        "extra_high": "max",
    }.get(candidate, candidate)
    if "true" in options:
        candidate = {
            "on": "true",
            "enabled": "true",
            "enable": "true",
            "high": "true",
            "max": "true",
            "off": "false",
            "disabled": "false",
            "disable": "false",
            "none": "false",
        }.get(candidate, candidate)
    if "no_think" in options and candidate == "none":
        candidate = "no_think"
    if options:
        return candidate if candidate in options else (default if default in options else options[0])
    return "fixed" if bool(selected.get("thinking")) else ""


def resolve_modelscope_thinking_choice(modelscope_config: Any, model_id: Optional[str] = None) -> str:
    cfg = default_modelscope_config()
    if isinstance(modelscope_config, dict):
        cfg.update(modelscope_config)
    selected = resolve_modelscope_selected_model(cfg, model_id=model_id)
    if not selected:
        return ""
    return normalize_modelscope_reasoning_choice(selected["id"], cfg.get("reasoning_effort"))


def apply_modelscope_thinking_choice(modelscope_config: Any, model_id: Any, choice: Any) -> Dict[str, Any]:
    cfg = default_modelscope_config()
    if isinstance(modelscope_config, dict):
        cfg.update(modelscope_config)
    selected = resolve_modelscope_selected_model(cfg, model_id=str(model_id or ""))
    if not selected:
        return normalize_modelscope_config(cfg)
    cfg["selected_model_id"] = str(selected["id"])
    cfg["selected_model_display_name"] = str(selected["display_name"])
    cfg["reasoning_effort"] = normalize_modelscope_reasoning_choice(selected["id"], choice)
    return normalize_modelscope_config(cfg)


def build_modelscope_runtime_model_data(modelscope_config: Any, model_id: Optional[str] = None) -> Optional[Dict[str, Any]]:
    """Build runtime model config dict for agent initialization."""
    cfg = normalize_modelscope_config(modelscope_config)
    if not cfg.get("enabled", True):
        return None

    api_key = resolve_modelscope_api_key(cfg)
    if not api_key:
        return None

    selected = resolve_modelscope_selected_model(cfg, model_id=model_id)
    if not selected:
        return None

    return {
        "model": selected["id"],
        "model_display_name": selected["display_name"],
        "base_url": resolve_modelscope_openai_base_url(cfg.get("api_url", MODELSCOPE_DEFAULT_API_URL)),
        "api_key": api_key,
        "max_context_tokens": int(selected.get("context_length") or cfg.get("max_context_tokens", MODELSCOPE_DEFAULT_CONTEXT_TOKENS)),
        "provider": "openai-chat",
        "supports_vision": bool(selected.get("vision", False)),
        "thinking_mode": resolve_modelscope_thinking_choice(cfg, selected["id"]),
        "endpoint": MODELSCOPE_DEFAULT_ENDPOINT,
        "custom_headers": {},
        "vision": bool(selected.get("vision", False)),
        "vision_modalities": ["image"] if selected.get("vision") else [],
    }


def build_modelscope_openai_options(modelscope_config: Any, model_id: Optional[str] = None) -> Dict[str, Any]:
    """Return OpenAI Chat Completions options for the selected ModelScope model."""
    cfg = normalize_modelscope_config(modelscope_config)
    selected = resolve_modelscope_selected_model(cfg, model_id=model_id)
    model_limit = int((selected or {}).get("max_output_tokens") or MODELSCOPE_DEFAULT_MAX_TOKENS)
    try:
        configured_limit = int(cfg.get("max_tokens", MODELSCOPE_DEFAULT_MAX_TOKENS))
    except (TypeError, ValueError):
        configured_limit = MODELSCOPE_DEFAULT_MAX_TOKENS
    if configured_limit <= 0:
        configured_limit = MODELSCOPE_DEFAULT_MAX_TOKENS
    selected_id = str((selected or {}).get("id") or "")
    choice = resolve_modelscope_thinking_choice(cfg, selected_id)
    if selected_id == "stepfun-ai/Step-3.7-Flash":
        template_kwargs = {"reasoning_effort": choice}
        temperature, top_p = 1.0, 0.95
    elif selected_id == "ZhipuAI/GLM-5.2":
        template_kwargs = {"enable_thinking": choice != "none"}
        if choice != "none":
            template_kwargs["reasoning_effort"] = choice
        temperature, top_p = 1.0, 1.0
    else:
        template_kwargs = {"reasoning_effort": choice == "true"}
        temperature, top_p = 1.0, 1.0
    return {
        "temperature": temperature,
        "top_p": top_p,
        "max_tokens": min(configured_limit, model_limit),
        "extra_body": {"chat_template_kwargs": template_kwargs},
    }


def build_modelscope_anthropic_options(modelscope_config: Any, model_id: Optional[str] = None) -> Dict[str, Any]:
    """Backward-compatible alias for callers migrated from Anthropic transport."""
    return build_modelscope_openai_options(modelscope_config, model_id)


def mask_secret(secret: str) -> str:
    """Mask secrets for safe terminal display."""
    value = str(secret or "").strip()
    if len(value) <= 8:
        return "*" * len(value)
    return f"{value[:4]}...{value[-4:]}"
