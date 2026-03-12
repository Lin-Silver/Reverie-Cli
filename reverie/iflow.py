"""
iFlow integration helpers.

This module centralizes:
- Local iFlow CLI credential detection (`~/.iflow`)
- iFlow model catalog definitions
- iFlow reverse-proxy settings helpers
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import urlsplit
import hashlib
import hmac
import json
import time
import uuid


IFLOW_API_URL = "https://apis.iflow.cn/v1/chat/completions"
IFLOW_MODELS_URL = "https://apis.iflow.cn/v1/models"
IFLOW_THINKING_DEPTHS = ("minimal", "low", "medium", "high", "xhigh", "auto")

_IFLOW_CREDENTIAL_FILES = (
    ("iflow_accounts.json", "iflowApiKey"),
    ("oauth_creds.json", "apiKey"),
)

_IFLOW_MODEL_METADATA = {
    "glm-4.7": {
        "display_name": "GLM-4.7",
        "description": "Zhipu GLM 4.7",
        "context_length": 128000,
        "thinking": True,
    },
    "iflow-rome-30ba3b": {
        "display_name": "iFlow-ROME-30BA3B(Preview)",
        "description": "iFlow ROME 30BA3B preview model",
        "context_length": 128000,
        "thinking": False,
    },
    "deepseek-v3.2": {
        "display_name": "DeepSeek-V3.2",
        "description": "DeepSeek V3.2",
        "context_length": 64000,
        "thinking": True,
    },
    "glm-5": {
        "display_name": "GLM-5",
        "description": "Zhipu GLM 5",
        "context_length": 128000,
        "thinking": True,
    },
    "qwen3-coder-plus": {
        "display_name": "Qwen3-Coder-Plus",
        "description": "Qwen3 coder model",
        "context_length": 32768,
        "thinking": False,
    },
    "kimi-k2-thinking": {
        "display_name": "Kimi-K2-Thinking",
        "description": "Moonshot Kimi K2 thinking model",
        "context_length": 128000,
        "thinking": True,
    },
    "minimax-m2.5": {
        "display_name": "MiniMax-M2.5",
        "description": "MiniMax M2.5 model",
        "context_length": 200000,
        "thinking": True,
    },
    "kimi-k2.5": {
        "display_name": "Kimi-K2.5",
        "description": "Moonshot Kimi K2.5 model",
        "context_length": 128000,
        "thinking": False,
    },
    "kimi-k2-0905": {
        "display_name": "Kimi-K2-0905",
        "description": "Moonshot Kimi K2 0905 model",
        "context_length": 128000,
        "thinking": False,
    },
}

_IFLOW_FALLBACK_ORDER = [
    "glm-4.7",
    "iflow-rome-30ba3b",
    "deepseek-v3.2",
    "glm-5",
    "qwen3-coder-plus",
    "kimi-k2-thinking",
    "minimax-m2.5",
    "kimi-k2.5",
    "kimi-k2-0905",
]
_IFLOW_ALLOWED_BASE_MODEL_SET = {model_id.lower() for model_id in _IFLOW_FALLBACK_ORDER}


def default_iflow_config() -> Dict[str, Any]:
    """Default iFlow config stored inside Reverie config.json."""
    return {
        "selected_model_id": "",
        "selected_model_display_name": "",
        "api_url": IFLOW_API_URL,
        "endpoint": "",
        "max_context_tokens": 200000,
        "timeout": 1200,
    }


def _normalize_iflow_api_url(value: Any) -> str:
    url = str(value or "").strip()
    if not url:
        return IFLOW_API_URL
    if not url.startswith("http://") and not url.startswith("https://"):
        url = f"https://{url}"
    return url.rstrip("/")


def _normalize_iflow_endpoint(value: Any) -> str:
    endpoint = str(value or "").strip()
    if not endpoint:
        return ""
    if endpoint.lower() in ("none", "off", "default", "clear"):
        return ""
    return endpoint


def _load_json_dict(path: Path, errors: List[str]) -> Optional[Dict[str, Any]]:
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except Exception as exc:
        errors.append(f"{path}: {exc}")
        return None

    if isinstance(data, dict):
        return data
    errors.append(f"{path}: invalid JSON object")
    return None


def _generate_iflow_signature(api_key: str, session_id: str, timestamp_ms: int) -> str:
    payload = f"iFlow-Cli:{session_id}:{timestamp_ms}"
    digest = hmac.new(api_key.encode(), payload.encode(), hashlib.sha256)
    return digest.hexdigest()


def _build_iflow_auth_headers(api_key: str, accept: str = "application/json") -> Dict[str, str]:
    session_id = f"session-{uuid.uuid4()}"
    timestamp = int(time.time() * 1000)
    return {
        "Authorization": f"Bearer {api_key}",
        "User-Agent": "iFlow-Cli",
        "session-id": session_id,
        "x-iflow-timestamp": str(timestamp),
        "x-iflow-signature": _generate_iflow_signature(api_key, session_id, timestamp),
        "Accept": accept,
    }


def _build_iflow_base_catalog() -> List[Dict[str, Any]]:
    catalog: List[Dict[str, Any]] = []
    seen_ids = set()
    for model_id in _IFLOW_FALLBACK_ORDER:
        meta = _IFLOW_MODEL_METADATA.get(model_id, {})
        lower_id = model_id.lower()
        if lower_id in seen_ids:
            continue
        seen_ids.add(lower_id)
        catalog.append(
            {
                "id": model_id,
                "display_name": str(meta.get("display_name", model_id)),
                "description": str(meta.get("description", "")),
                "is_thinking": False,
                "thinking_depth": "none",
                "base_model_id": model_id,
                "context_length": int(meta.get("context_length", 128000)),
            }
        )
    return catalog


def _append_iflow_thinking_variants(catalog: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    items = list(catalog)
    seen = {str(item.get("id", "")).strip().lower() for item in items}
    for item in list(catalog):
        model_id = str(item.get("id", "")).strip()
        meta = _IFLOW_MODEL_METADATA.get(model_id, {})
        if not meta.get("thinking"):
            continue
        for depth in IFLOW_THINKING_DEPTHS:
            thinking_id = f"{model_id}({depth})"
            lower_id = thinking_id.lower()
            if lower_id in seen:
                continue
            seen.add(lower_id)
            items.append(
                {
                    "id": thinking_id,
                    "display_name": f"{item['display_name']} [{depth}]",
                    "description": f"{item['description']}; depth={depth}",
                    "is_thinking": True,
                    "thinking_depth": depth,
                    "base_model_id": model_id,
                    "context_length": int(item.get("context_length", 128000)),
                }
            )
    return items


def _fetch_remote_iflow_models(api_key: str, errors: List[str]) -> List[Dict[str, Any]]:
    if not api_key:
        return []

    try:
        import requests

        response = requests.get(
            IFLOW_MODELS_URL,
            headers=_build_iflow_auth_headers(api_key),
            timeout=20,
        )
    except Exception as exc:
        errors.append(f"remote model fetch failed: {exc}")
        return []

    if not response.ok:
        errors.append(f"remote model fetch failed ({response.status_code})")
        return []

    try:
        payload = response.json()
    except Exception as exc:
        errors.append(f"remote model fetch parse failed: {exc}")
        return []

    data = payload.get("data")
    if not isinstance(data, list):
        return []

    catalog: List[Dict[str, Any]] = []
    seen_ids = set()
    for item in data:
        if not isinstance(item, dict):
            continue
        model_id = str(item.get("id", "")).strip()
        if not model_id:
            continue
        lower_id = model_id.lower()
        if lower_id not in _IFLOW_ALLOWED_BASE_MODEL_SET:
            continue
        if lower_id in seen_ids:
            continue
        seen_ids.add(lower_id)
        meta = _IFLOW_MODEL_METADATA.get(model_id, {})
        catalog.append(
            {
                "id": model_id,
                "display_name": str(meta.get("display_name", model_id)),
                "description": str(meta.get("description", "")),
                "is_thinking": False,
                "thinking_depth": "none",
                "base_model_id": model_id,
                "context_length": int(meta.get("context_length", 128000)),
                "created": item.get("created"),
            }
        )
    return catalog


def get_iflow_model_catalog() -> List[Dict[str, Any]]:
    """Return iFlow model catalog, preferring the current remote account model list."""
    cred = detect_iflow_cli_credentials()
    errors = cred.get("errors", []) if isinstance(cred.get("errors"), list) else []
    remote_catalog = _fetch_remote_iflow_models(str(cred.get("api_key", "")).strip(), errors)
    base_catalog = _build_iflow_base_catalog()
    if remote_catalog:
        remote_by_id = {
            str(item.get("id", "")).strip().lower(): item
            for item in remote_catalog
            if str(item.get("id", "")).strip()
        }
        merged_catalog: List[Dict[str, Any]] = []
        for item in base_catalog:
            merged = dict(item)
            remote_item = remote_by_id.get(str(item.get("id", "")).strip().lower(), {})
            if remote_item:
                if remote_item.get("created") is not None:
                    merged["created"] = remote_item.get("created")
            merged_catalog.append(merged)
        return _append_iflow_thinking_variants(merged_catalog)
    return _append_iflow_thinking_variants(base_catalog)


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

    if not str(cfg.get("api_url", "")).strip():
        legacy_url = str(cfg.get("proxy_base_url", "")).strip()
        if legacy_url and "127.0.0.1:8000" not in legacy_url:
            cfg["api_url"] = legacy_url

    cfg["selected_model_id"] = str(cfg.get("selected_model_id", "")).strip()
    cfg["selected_model_display_name"] = str(cfg.get("selected_model_display_name", "")).strip()
    cfg["api_url"] = _normalize_iflow_api_url(cfg.get("api_url", IFLOW_API_URL))
    cfg["endpoint"] = _normalize_iflow_endpoint(cfg.get("endpoint", ""))
    cfg.pop("proxy_base_url", None)
    cfg.pop("proxy_api_key", None)

    try:
        max_tokens = int(cfg.get("max_context_tokens", 200000))
    except (TypeError, ValueError):
        max_tokens = 200000
    if max_tokens <= 0:
        max_tokens = 200000
    cfg["max_context_tokens"] = max_tokens

    timeout_val = cfg.get("timeout", cfg.get("iflow_timeout", 1200))
    try:
        timeout_int = int(timeout_val)
    except (TypeError, ValueError):
        timeout_int = 1200
    if timeout_int <= 0:
        timeout_int = 1200
    cfg["timeout"] = timeout_int
    cfg.pop("iflow_timeout", None)

    catalog = get_iflow_model_catalog()
    matched = find_iflow_model(cfg["selected_model_id"], catalog=catalog)
    if matched:
        cfg["selected_model_id"] = matched["id"]
        cfg["selected_model_display_name"] = matched["display_name"]
        cfg["max_context_tokens"] = int(matched.get("context_length", cfg["max_context_tokens"]))
    elif cfg["selected_model_id"]:
        cfg["selected_model_id"] = ""
        cfg["selected_model_display_name"] = ""

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
        "context_length": cfg.get("max_context_tokens", 128000),
    }


def resolve_iflow_request_url(api_url: str, endpoint: str = "") -> str:
    """Resolve iFlow request URL with optional endpoint override."""
    endpoint_value = str(endpoint or "").strip()
    if endpoint_value:
        if endpoint_value.startswith("http://") or endpoint_value.startswith("https://"):
            return endpoint_value
        base = _normalize_iflow_api_url(api_url)
        if base.lower().endswith("/chat/completions"):
            split = urlsplit(base)
            base = f"{split.scheme}://{split.netloc}"
        if endpoint_value.startswith("/"):
            return f"{base}{endpoint_value}"
        return f"{base}/{endpoint_value}"

    return _normalize_iflow_api_url(api_url)


def build_iflow_runtime_model_data(iflow_config: Any) -> Optional[Dict[str, Any]]:
    """Build runtime model config dict for agent initialization."""
    cfg = normalize_iflow_config(iflow_config)
    selected = resolve_iflow_selected_model(cfg)
    if not selected:
        return None

    cred = detect_iflow_cli_credentials()
    api_key = cred["api_key"] if cred.get("found") else ""
    context_length = selected.get("context_length", cfg.get("max_context_tokens", 200000))

    return {
        "model": selected["id"],
        "model_display_name": selected["display_name"],
        "base_url": resolve_iflow_request_url(cfg["api_url"], cfg.get("endpoint", "")),
        "api_key": api_key,
        "max_context_tokens": context_length,
        "provider": "request",
        "thinking_mode": None,
        "endpoint": "",
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

        data = _load_json_dict(path, result["errors"])
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
    """Whether the URL points to an iFlow chat completions endpoint."""
    value = str(url or "").strip().lower()
    return "apis.iflow.cn" in value and "/chat/completions" in value
