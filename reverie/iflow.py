"""
iFlow integration helpers.

This module centralizes:
- Local iFlow CLI credential detection (`~/.iflow`)
- iFlow model catalog definitions
- iFlow proxy settings helpers
"""

from pathlib import Path
from typing import Any, Dict, List, Optional
import json


IFLOW_API_URL = "https://apis.iflow.cn/v1/chat/completions"
IFLOW_THINKING_DEPTHS = ("minimal", "low", "medium", "high", "xhigh", "auto")

_IFLOW_CREDENTIAL_FILES = (
    ("iflow_accounts.json", "iflowApiKey"),
    ("oauth_creds.json", "apiKey"),
)

_IFLOW_BASE_MODELS = [
    {
        "id": "tstars2.0",
        "display_name": "TStars-2.0",
        "description": "iFlow TStars-2.0 multimodal assistant",
    },
    {
        "id": "qwen3-coder-plus",
        "display_name": "Qwen3-Coder-Plus",
        "description": "Qwen3 coding enhanced model",
    },
    {
        "id": "qwen3-max",
        "display_name": "Qwen3-Max",
        "description": "Qwen3 flagship model",
    },
    {
        "id": "qwen3-vl-plus",
        "display_name": "Qwen3-VL-Plus",
        "description": "Qwen3 multimodal vision-language model",
    },
    {
        "id": "qwen3-max-preview",
        "display_name": "Qwen3-Max-Preview",
        "description": "Qwen3 Max preview model",
    },
    {
        "id": "kimi-k2-0905",
        "display_name": "Kimi-K2-Instruct-0905",
        "description": "Moonshot Kimi K2 instruct model (0905)",
    },
    {
        "id": "glm-4.6",
        "display_name": "GLM-4.6",
        "description": "Zhipu GLM 4.6 general model",
    },
    {
        "id": "glm-4.7",
        "display_name": "GLM-4.7",
        "description": "Zhipu GLM 4.7 general model",
    },
    {
        "id": "glm-5",
        "display_name": "GLM-5",
        "description": "Zhipu GLM 5 general model",
    },
    {
        "id": "kimi-k2",
        "display_name": "Kimi-K2",
        "description": "Moonshot Kimi K2 general model",
    },
    {
        "id": "kimi-k2-thinking",
        "display_name": "Kimi-K2-Thinking",
        "description": "Moonshot Kimi K2 thinking model",
    },
    {
        "id": "deepseek-v3.2-chat",
        "display_name": "DeepSeek-V3.2-Chat",
        "description": "DeepSeek V3.2 chat model",
    },
    {
        "id": "deepseek-v3.2-reasoner",
        "display_name": "DeepSeek-V3.2-Reasoner",
        "description": "DeepSeek V3.2 reasoning model",
    },
    {
        "id": "deepseek-v3.2",
        "display_name": "DeepSeek-V3.2-Exp",
        "description": "DeepSeek V3.2 experimental model",
    },
    {
        "id": "deepseek-v3.1",
        "display_name": "DeepSeek-V3.1-Terminus",
        "description": "DeepSeek V3.1 Terminus model",
    },
    {
        "id": "deepseek-r1",
        "display_name": "DeepSeek-R1",
        "description": "DeepSeek R1 reasoning model",
    },
    {
        "id": "deepseek-v3",
        "display_name": "DeepSeek-V3-671B",
        "description": "DeepSeek V3 671B model",
    },
    {
        "id": "qwen3-32b",
        "display_name": "Qwen3-32B",
        "description": "Qwen3 32B model",
    },
    {
        "id": "qwen3-235b-a22b-thinking-2507",
        "display_name": "Qwen3-235B-Thinking",
        "description": "Qwen3 235B A22B thinking model (2507)",
    },
    {
        "id": "qwen3-235b-a22b-instruct",
        "display_name": "Qwen3-235B-Instruct",
        "description": "Qwen3 235B A22B instruct model",
    },
    {
        "id": "qwen3-235b",
        "display_name": "Qwen3-235B-A22B",
        "description": "Qwen3 235B A22B model",
    },
    {
        "id": "minimax-m2",
        "display_name": "MiniMax-M2",
        "description": "MiniMax M2 model",
    },
    {
        "id": "minimax-m2.1",
        "display_name": "MiniMax-M2.1",
        "description": "MiniMax M2.1 model",
    },
    {
        "id": "minimax-m2.5",
        "display_name": "MiniMax-M2.5",
        "description": "MiniMax M2.5 model",
    },
    {
        "id": "iflow-rome-30ba3b",
        "display_name": "iFlow-ROME",
        "description": "iFlow Rome 30BA3B model",
    },
    {
        "id": "kimi-k2.5",
        "display_name": "Kimi-K2.5",
        "description": "Moonshot Kimi K2.5 model",
    },
]

_IFLOW_THINKING_BASES = [
    {
        "id": "glm-4.6",
        "display_name": "GLM-4.6-thinking",
        "description": "GLM-4.6 thinking profile",
    },
    {
        "id": "glm-4.7",
        "display_name": "GLM-4.7-thinking",
        "description": "GLM-4.7 thinking profile",
    },
    {
        "id": "glm-5",
        "display_name": "GLM-5-thinking",
        "description": "GLM-5 thinking profile",
    },
    {
        "id": "qwen3-max-preview",
        "display_name": "Qwen3-Max-Preview-thinking",
        "description": "Qwen3 Max preview thinking profile",
    },
    {
        "id": "qwen3-235b-a22b-thinking-2507",
        "display_name": "Qwen3-235B-Thinking-depth",
        "description": "Qwen3 235B thinking profile with depth control",
    },
    {
        "id": "kimi-k2-thinking",
        "display_name": "Kimi-K2-thinking-depth",
        "description": "Kimi K2 thinking profile with depth control",
    },
    {
        "id": "deepseek-v3.2-reasoner",
        "display_name": "DeepSeek-V3.2-Reasoner-thinking",
        "description": "DeepSeek V3.2 reasoner profile with depth control",
    },
    {
        "id": "deepseek-r1",
        "display_name": "DeepSeek-R1-thinking",
        "description": "DeepSeek R1 reasoning profile with depth control",
    },
    {
        "id": "minimax-m2.5",
        "display_name": "MiniMax-M2.5-thinking",
        "description": "MiniMax M2.5 reasoning profile with depth control",
    },
]


def default_iflow_config() -> Dict[str, Any]:
    """Default iFlow config stored inside Reverie config.json."""
    return {
        "selected_model_id": "",
        "selected_model_display_name": "",
        "api_url": IFLOW_API_URL,
        "max_context_tokens": 128000,
    }


def get_iflow_model_catalog() -> List[Dict[str, Any]]:
    """Return iFlow model catalog including thinking-depth variants."""
    catalog: List[Dict[str, Any]] = []
    seen_model_ids = set()

    for item in _IFLOW_BASE_MODELS:
        model_id = str(item.get("id", "")).strip()
        if not model_id or model_id.lower() in seen_model_ids:
            continue
        seen_model_ids.add(model_id.lower())
        catalog.append(
            {
                "id": model_id,
                "display_name": str(item.get("display_name", model_id)).strip(),
                "description": str(item.get("description", "")).strip(),
                "is_thinking": False,
                "thinking_depth": "none",
                "base_model_id": model_id,
            }
        )

    for base in _IFLOW_THINKING_BASES:
        base_model_id = str(base.get("id", "")).strip()
        base_display_name = str(base.get("display_name", base_model_id)).strip()
        base_description = str(base.get("description", "")).strip()

        if not base_model_id:
            continue

        for depth in IFLOW_THINKING_DEPTHS:
            model_id = f"{base_model_id}({depth})"
            model_id_key = model_id.lower()
            if model_id_key in seen_model_ids:
                continue

            seen_model_ids.add(model_id_key)
            catalog.append(
                {
                    "id": model_id,
                    "display_name": f"{base_display_name} [{depth}]",
                    "description": f"{base_description}; depth={depth}",
                    "is_thinking": True,
                    "thinking_depth": depth,
                    "base_model_id": base_model_id,
                }
            )

    return catalog


def find_iflow_model(model_id: str, catalog: Optional[List[Dict[str, Any]]] = None) -> Optional[Dict[str, Any]]:
    """Find iFlow model by id (case-insensitive)."""
    wanted = str(model_id or "").strip().lower()
    if not wanted:
        return None

    items = catalog if isinstance(catalog, list) else get_iflow_model_catalog()
    for item in items:
        if str(item.get("id", "")).strip().lower() == wanted:
            return item
    return None


def normalize_iflow_config(raw_iflow: Any) -> Dict[str, Any]:
    """Normalize iFlow config for persistence and runtime usage."""
    cfg = default_iflow_config()
    if isinstance(raw_iflow, dict):
        cfg.update(raw_iflow)

    # Migrate legacy keys from previous local-proxy design.
    if not str(cfg.get("api_url", "")).strip():
        legacy_url = str(cfg.get("proxy_base_url", "")).strip()
        if legacy_url and "127.0.0.1:8000" not in legacy_url:
            cfg["api_url"] = legacy_url

    cfg["selected_model_id"] = str(cfg.get("selected_model_id", "")).strip()
    cfg["selected_model_display_name"] = str(cfg.get("selected_model_display_name", "")).strip()
    cfg["api_url"] = str(cfg.get("api_url", IFLOW_API_URL)).strip() or IFLOW_API_URL
    cfg.pop("proxy_base_url", None)
    cfg.pop("proxy_api_key", None)

    try:
        max_tokens = int(cfg.get("max_context_tokens", 128000))
    except (TypeError, ValueError):
        max_tokens = 128000
    if max_tokens <= 0:
        max_tokens = 128000
    cfg["max_context_tokens"] = max_tokens

    catalog = get_iflow_model_catalog()
    matched = find_iflow_model(cfg["selected_model_id"], catalog=catalog)
    if matched:
        cfg["selected_model_display_name"] = matched["display_name"]
    elif cfg["selected_model_id"] and not cfg["selected_model_display_name"]:
        cfg["selected_model_display_name"] = cfg["selected_model_id"]

    return cfg


def resolve_iflow_selected_model(iflow_config: Any) -> Optional[Dict[str, Any]]:
    """Resolve selected iFlow model metadata from config."""
    cfg = normalize_iflow_config(iflow_config)
    model_id = cfg.get("selected_model_id", "")
    if not model_id:
        return None

    catalog = get_iflow_model_catalog()
    matched = find_iflow_model(model_id, catalog=catalog)
    if matched:
        return matched

    display_name = cfg.get("selected_model_display_name") or model_id
    return {
        "id": model_id,
        "display_name": display_name,
        "description": "Custom iFlow model id",
        "is_thinking": False,
        "thinking_depth": "none",
        "base_model_id": model_id,
    }


def build_iflow_runtime_model_data(iflow_config: Any) -> Optional[Dict[str, Any]]:
    """
    Build runtime model config dict for agent initialization.

    This keeps iFlow models independent from the `/model` list.
    """
    cfg = normalize_iflow_config(iflow_config)
    selected = resolve_iflow_selected_model(cfg)
    if not selected:
        return None

    cred = detect_iflow_cli_credentials()
    api_key = cred["api_key"] if cred.get("found") else ""

    return {
        "model": selected["id"],
        "model_display_name": selected["display_name"],
        "base_url": cfg["api_url"],
        "api_key": api_key,
        "max_context_tokens": cfg["max_context_tokens"],
        "provider": "request",
        "thinking_mode": None,
    }


def detect_iflow_cli_credentials() -> Dict[str, Any]:
    """
    Detect iFlow CLI credentials from local cache.

    Priority:
    1) ~/.iflow/iflow_accounts.json -> iflowApiKey
    2) ~/.iflow/oauth_creds.json -> apiKey
    """
    iflow_dir = Path.home() / ".iflow"
    result = {
        "found": False,
        "api_key": "",
        "source_file": "",
        "source_field": "",
        "errors": [],
    }

    for filename, field_name in _IFLOW_CREDENTIAL_FILES:
        path = iflow_dir / filename
        if not path.exists():
            continue

        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
        except Exception as exc:
            result["errors"].append(f"{path}: {exc}")
            continue

        if not isinstance(data, dict):
            continue

        value = str(data.get(field_name, "")).strip()
        if value:
            result["found"] = True
            result["api_key"] = value
            result["source_file"] = str(path)
            result["source_field"] = field_name
            return result

    return result


def mask_secret(secret: str) -> str:
    """Mask secret for safe terminal display."""
    value = str(secret or "").strip()
    if len(value) <= 8:
        return "*" * len(value)
    return f"{value[:4]}...{value[-4:]}"


def is_iflow_direct_api_url(url: str) -> bool:
    """Whether the URL points to iFlow direct chat completions endpoint."""
    value = str(url or "").strip().lower()
    return "apis.iflow.cn" in value and "/v1/chat/completions" in value
