"""
ModelScope integration helpers.

ModelScope's API-Inference Anthropic-compatible endpoint is intentionally
simple: use the Anthropic SDK, point it at the ModelScope root URL, and send
the ModelScope repository model id as the model name.
"""

from __future__ import annotations

import os
from typing import Any, Dict, List, Optional


MODELSCOPE_DEFAULT_API_URL = "https://api-inference.modelscope.cn"
MODELSCOPE_DEFAULT_MODEL_ID = "ZhipuAI/GLM-5.1"
MODELSCOPE_DEFAULT_MODEL_DISPLAY_NAME = "GLM-5.1"
MODELSCOPE_API_KEY_HINT_URL = "https://www.modelscope.cn/my/access/token"
MODELSCOPE_DEFAULT_CONTEXT_TOKENS = 202_752
MODELSCOPE_DEFAULT_MAX_TOKENS = 16_384
MODELSCOPE_DEEPSEEK_CONTEXT_TOKENS = 128_000
MODELSCOPE_GLM_CONTEXT_TOKENS = 202_752
MODELSCOPE_KIMI_CONTEXT_TOKENS = 262_144
MODELSCOPE_MINIMAX_CONTEXT_TOKENS = 204_800
MODELSCOPE_QWEN_CONTEXT_TOKENS = 262_144


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
) -> Dict[str, Any]:
    return {
        "id": model_id,
        "display_name": display_name,
        "description": description,
        "transport": "anthropic",
        "context_length": int(context_length),
        "max_output_tokens": int(max_output_tokens),
        "vision": bool(vision),
        "thinking": bool(thinking),
        "tool_calling": bool(tool_calling),
    }


_MODELSCOPE_MODEL_CATALOG: List[Dict[str, Any]] = [
    _modelscope_model(
        "ZhipuAI/GLM-5.1",
        "GLM-5.1",
        "Z.ai GLM-5.1 model on ModelScope.",
        context_length=MODELSCOPE_GLM_CONTEXT_TOKENS,
        max_output_tokens=65_536,
        thinking=True,
    ),
    _modelscope_model(
        "deepseek-ai/DeepSeek-V3.2",
        "DeepSeek V3.2",
        "Anthropic SDK transport through ModelScope API-Inference.",
        context_length=MODELSCOPE_DEEPSEEK_CONTEXT_TOKENS,
        max_output_tokens=65_536,
        thinking=True,
    ),
    _modelscope_model(
        "ZhipuAI/GLM-5",
        "GLM-5",
        "Z.ai GLM-5 model on ModelScope.",
        context_length=MODELSCOPE_GLM_CONTEXT_TOKENS,
        max_output_tokens=65_536,
        thinking=True,
    ),
    _modelscope_model(
        "moonshotai/Kimi-K2.5",
        "Kimi K2.5",
        "Moonshot Kimi K2.5 multimodal agentic model on ModelScope.",
        context_length=MODELSCOPE_KIMI_CONTEXT_TOKENS,
        max_output_tokens=65_536,
        vision=True,
        thinking=True,
    ),
    _modelscope_model(
        "MiniMax/MiniMax-M2.7",
        "MiniMax M2.7",
        "MiniMax M2.7 agentic coding model on ModelScope.",
        context_length=MODELSCOPE_MINIMAX_CONTEXT_TOKENS,
        max_output_tokens=65_536,
        thinking=True,
    ),
    _modelscope_model(
        "Qwen/Qwen3.5-397B-A17B",
        "Qwen3.5 397B A17B",
        "Qwen3.5 397B-A17B model on ModelScope.",
        context_length=MODELSCOPE_QWEN_CONTEXT_TOKENS,
        max_output_tokens=65_536,
        vision=True,
        thinking=True,
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
        "max_context_tokens": MODELSCOPE_DEFAULT_CONTEXT_TOKENS,
        "timeout": 300,
        "max_tokens": MODELSCOPE_DEFAULT_MAX_TOKENS,
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
    return get_modelscope_model_catalog()[0]


def _normalize_api_url(api_url: Any) -> str:
    base = str(api_url or "").strip()
    if not base:
        return MODELSCOPE_DEFAULT_API_URL
    if not base.startswith(("http://", "https://")):
        base = f"https://{base}"
    return base.rstrip("/") or MODELSCOPE_DEFAULT_API_URL


def resolve_modelscope_anthropic_base_url(api_url: Any) -> str:
    """Resolve the Anthropic SDK base URL for ModelScope.

    The Anthropic SDK appends `/v1/messages` itself, so pasted OpenAI-style or
    full Messages API URLs are normalized back to the provider root.
    """
    base = _normalize_api_url(api_url)
    lower_base = base.lower()
    for suffix in ("/v1/messages", "/messages", "/v1"):
        if lower_base.endswith(suffix):
            base = base[: -len(suffix)]
            lower_base = base.lower()
    return base.rstrip("/") or MODELSCOPE_DEFAULT_API_URL


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
    if isinstance(raw_modelscope, dict):
        cfg.update(raw_modelscope)

    cfg["api_key"] = str(cfg.get("api_key", "") or "").strip()
    cfg["api_url"] = resolve_modelscope_anthropic_base_url(cfg.get("api_url", MODELSCOPE_DEFAULT_API_URL))
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

    return cfg


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
        "base_url": resolve_modelscope_anthropic_base_url(cfg.get("api_url", MODELSCOPE_DEFAULT_API_URL)),
        "api_key": api_key,
        "max_context_tokens": int(selected.get("context_length") or cfg.get("max_context_tokens", MODELSCOPE_DEFAULT_CONTEXT_TOKENS)),
        "provider": "anthropic",
        "thinking_mode": None,
        "endpoint": "",
        "custom_headers": {},
        "vision": bool(selected.get("vision", False)),
    }


def build_modelscope_anthropic_options(modelscope_config: Any, model_id: Optional[str] = None) -> Dict[str, Any]:
    """Return Anthropic SDK request options for the selected ModelScope model."""
    cfg = normalize_modelscope_config(modelscope_config)
    selected = resolve_modelscope_selected_model(cfg, model_id=model_id)
    model_limit = int((selected or {}).get("max_output_tokens") or MODELSCOPE_DEFAULT_MAX_TOKENS)
    try:
        configured_limit = int(cfg.get("max_tokens", MODELSCOPE_DEFAULT_MAX_TOKENS))
    except (TypeError, ValueError):
        configured_limit = MODELSCOPE_DEFAULT_MAX_TOKENS
    if configured_limit <= 0:
        configured_limit = MODELSCOPE_DEFAULT_MAX_TOKENS
    return {"max_tokens": min(configured_limit, model_limit)}


def mask_secret(secret: str) -> str:
    """Mask secrets for safe terminal display."""
    value = str(secret or "").strip()
    if len(value) <= 8:
        return "*" * len(value)
    return f"{value[:4]}...{value[-4:]}"
