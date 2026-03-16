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

IFLOW_DEFAULT_BASE_URL = "https://apis.iflow.cn/v1"
IFLOW_API_URL = f"{IFLOW_DEFAULT_BASE_URL}/chat/completions"
IFLOW_MODELS_URL = f"{IFLOW_DEFAULT_BASE_URL}/models"
IFLOW_THINKING_DEPTHS = ("minimal", "low", "medium", "high", "xhigh", "auto")
IFLOW_SETTINGS_FILE = "settings.json"
IFLOW_USER_AGENT = "iFlow-Cli"

_IFLOW_CREDENTIAL_FILES = (
    (IFLOW_SETTINGS_FILE, "apiKey"),
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
    "qwen3-max": {
        "display_name": "Qwen3-Max",
        "description": "Qwen3 Max model",
        "context_length": 131072,
        "thinking": False,
    },
    "qwen3-vl-plus": {
        "display_name": "Qwen3-VL-Plus",
        "description": "Qwen3 multimodal model",
        "context_length": 32768,
        "thinking": False,
    },
    "qwen3-max-preview": {
        "display_name": "Qwen3-Max-Preview",
        "description": "Qwen3 Max preview model",
        "context_length": 131072,
        "thinking": False,
    },
    "kimi-k2": {
        "display_name": "Kimi-K2",
        "description": "Moonshot Kimi K2 model",
        "context_length": 128000,
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
    "deepseek-r1": {
        "display_name": "DeepSeek-R1",
        "description": "DeepSeek reasoning model",
        "context_length": 128000,
        "thinking": False,
    },
    "deepseek-v3": {
        "display_name": "DeepSeek-V3",
        "description": "DeepSeek V3 model",
        "context_length": 64000,
        "thinking": False,
    },
    "qwen3-32b": {
        "display_name": "Qwen3-32B",
        "description": "Qwen3 32B model",
        "context_length": 131072,
        "thinking": False,
    },
    "qwen3-235b-a22b-thinking-2507": {
        "display_name": "Qwen3-235B-A22B-Thinking-2507",
        "description": "Qwen3 235B thinking model",
        "context_length": 131072,
        "thinking": False,
    },
    "qwen3-235b-a22b-instruct": {
        "display_name": "Qwen3-235B-A22B-Instruct",
        "description": "Qwen3 235B instruct model",
        "context_length": 131072,
        "thinking": False,
    },
    "qwen3-235b": {
        "display_name": "Qwen3-235B",
        "description": "Qwen3 235B model",
        "context_length": 131072,
        "thinking": False,
    },
}

_IFLOW_FALLBACK_ORDER = [
    "iflow-rome-30ba3b",
    "qwen3-coder-plus",
    "qwen3-max",
    "qwen3-vl-plus",
    "qwen3-max-preview",
    "kimi-k2",
    "kimi-k2-0905",
    "deepseek-v3.2",
    "deepseek-r1",
    "deepseek-v3",
    "qwen3-32b",
    "qwen3-235b-a22b-thinking-2507",
    "qwen3-235b-a22b-instruct",
    "qwen3-235b",
    "glm-5",
    "glm-4.7",
    "kimi-k2-thinking",
    "minimax-m2.5",
    "kimi-k2.5",
]


def default_iflow_config() -> Dict[str, Any]:
    """Default iFlow config stored inside Reverie config.json."""
    return {
        "selected_model_id": "",
        "selected_model_display_name": "",
        "api_url": IFLOW_DEFAULT_BASE_URL,
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


def _load_iflow_settings(errors: Optional[List[str]] = None) -> Dict[str, Any]:
    """Load ~/.iflow/settings.json if present."""
    path = Path.home() / ".iflow" / IFLOW_SETTINGS_FILE
    if not path.exists():
        return {}
    data = _load_json_dict(path, errors if isinstance(errors, list) else [])
    return data if isinstance(data, dict) else {}


def _build_iflow_auth_headers(api_key: str, accept: str = "application/json") -> Dict[str, str]:
    return {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
        "Accept": accept,
    }


def create_iflow_signature(user_agent: str, session_id: str, timestamp_ms: int, api_key: str) -> str:
    """Generate iFlow-compatible HMAC signature for direct chat requests."""
    secret = str(api_key or "").strip()
    if not secret:
        return ""
    payload = f"{user_agent}:{session_id}:{int(timestamp_ms)}".encode("utf-8")
    return hmac.new(secret.encode("utf-8"), payload, hashlib.sha256).hexdigest()


def build_iflow_request_headers(
    api_key: str,
    stream: bool = False,
    custom_headers: Optional[Dict[str, Any]] = None,
) -> Dict[str, str]:
    """Build direct-request headers compatible with the current iFlow CLI flow."""
    user_agent = IFLOW_USER_AGENT
    session_id = f"session-{uuid.uuid4()}"
    timestamp_ms = int(time.time() * 1000)
    headers = {
        "Authorization": f"Bearer {str(api_key or '').strip()}",
        "Content-Type": "application/json",
        "Accept": "text/event-stream" if stream else "application/json",
        "User-Agent": user_agent,
        "session-id": session_id,
        "x-iflow-timestamp": str(timestamp_ms),
    }
    signature = create_iflow_signature(user_agent, session_id, timestamp_ms, api_key)
    if signature:
        headers["x-iflow-signature"] = signature

    if isinstance(custom_headers, dict):
        for key, value in custom_headers.items():
            key_text = str(key or "").strip()
            if not key_text:
                continue
            headers[key_text] = str(value)
    return headers


def _merge_iflow_metadata(model_id: str, raw_item: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """Merge static metadata with any remotely discovered model fields."""
    item = raw_item if isinstance(raw_item, dict) else {}
    meta = _IFLOW_MODEL_METADATA.get(model_id, {})
    return {
        "display_name": str(meta.get("display_name") or item.get("display_name") or model_id),
        "description": str(meta.get("description") or item.get("description") or model_id),
        "context_length": int(item.get("context_length") or meta.get("context_length", 128000)),
        "thinking": bool(meta.get("thinking", False)),
    }


def _build_iflow_base_catalog() -> List[Dict[str, Any]]:
    catalog: List[Dict[str, Any]] = []
    seen_ids = set()
    for model_id in _IFLOW_FALLBACK_ORDER:
        meta = _merge_iflow_metadata(model_id)
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
                "remote_available": False,
            }
        )
    return catalog


def _append_iflow_thinking_variants(catalog: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    items = list(catalog)
    seen = {str(item.get("id", "")).strip().lower() for item in items}
    for item in list(catalog):
        model_id = str(item.get("id", "")).strip()
        meta = _merge_iflow_metadata(model_id)
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


def _resolve_iflow_models_url(api_url: str) -> str:
    """Resolve the models endpoint from a configured iFlow base URL."""
    base = _normalize_iflow_api_url(api_url)
    if base.lower().endswith("/models"):
        return base
    if base.lower().endswith("/chat/completions"):
        split = urlsplit(base)
        return f"{split.scheme}://{split.netloc}/v1/models"
    return f"{base}/models"


def _fetch_remote_iflow_models(api_key: str, api_url: str, errors: List[str]) -> List[Dict[str, Any]]:
    if not api_key:
        return []

    try:
        import requests

        response = requests.get(
            _resolve_iflow_models_url(api_url),
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
        if lower_id in seen_ids:
            continue
        seen_ids.add(lower_id)
        meta = _merge_iflow_metadata(model_id, item)
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
                "remote_available": True,
            }
        )
    return catalog


def get_iflow_model_catalog() -> List[Dict[str, Any]]:
    """Return iFlow model catalog, preferring the current remote account model list."""
    cred = detect_iflow_cli_credentials()
    errors = cred.get("errors", []) if isinstance(cred.get("errors"), list) else []
    remote_catalog = _fetch_remote_iflow_models(
        str(cred.get("api_key", "")).strip(),
        str(cred.get("base_url", "")).strip() or IFLOW_DEFAULT_BASE_URL,
        errors,
    )
    base_catalog = _build_iflow_base_catalog()
    if remote_catalog:
        merged_by_id = {
            str(item.get("id", "")).strip().lower(): dict(item)
            for item in base_catalog
            if str(item.get("id", "")).strip()
        }
        for remote_item in remote_catalog:
            model_id = str(remote_item.get("id", "")).strip()
            if not model_id:
                continue
            lower_id = model_id.lower()
            merged = dict(merged_by_id.get(lower_id, {}))
            merged.update(remote_item)
            merged["id"] = model_id
            merged["base_model_id"] = model_id
            merged["is_thinking"] = False
            merged["thinking_depth"] = "none"
            merged["remote_available"] = True
            merged_by_id[lower_id] = merged

        order_index = {model_id.lower(): idx for idx, model_id in enumerate(_IFLOW_FALLBACK_ORDER)}
        merged_catalog = sorted(
            merged_by_id.values(),
            key=lambda item: (
                order_index.get(str(item.get("id", "")).strip().lower(), 10_000),
                str(item.get("display_name", item.get("id", ""))).lower(),
            ),
        )
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
    settings = _load_iflow_settings()
    settings_base_url = str(settings.get("baseUrl", "") or "").strip()
    settings_model_id = str(settings.get("modelName", "") or "").strip()

    if not str(cfg.get("api_url", "")).strip():
        legacy_url = str(cfg.get("proxy_base_url", "")).strip()
        if legacy_url and "127.0.0.1:8000" not in legacy_url:
            cfg["api_url"] = legacy_url
        elif settings_base_url:
            cfg["api_url"] = settings_base_url

    cfg["selected_model_id"] = str(cfg.get("selected_model_id", "")).strip()
    cfg["selected_model_display_name"] = str(cfg.get("selected_model_display_name", "")).strip()
    cfg["api_url"] = _normalize_iflow_api_url(cfg.get("api_url", settings_base_url or IFLOW_DEFAULT_BASE_URL))
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
    has_remote_catalog = any(bool(item.get("remote_available")) for item in catalog)
    if not cfg["selected_model_id"] and settings_model_id:
        matched = find_iflow_model(settings_model_id, catalog=catalog)
        if matched and (bool(matched.get("remote_available")) or not has_remote_catalog):
            cfg["selected_model_id"] = matched["id"]
            cfg["selected_model_display_name"] = matched["display_name"]
    matched = find_iflow_model(cfg["selected_model_id"], catalog=catalog)
    if matched and has_remote_catalog and not bool(matched.get("remote_available")):
        matched = None
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

    base = _normalize_iflow_api_url(api_url)
    if base.lower().endswith("/chat/completions"):
        return base
    return f"{base}/chat/completions"


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
        "base_url": "",
        "model_name": "",
        "auth_type": "",
        "errors": [],
    }
    settings = _load_iflow_settings(result["errors"])
    if isinstance(settings, dict):
        result["base_url"] = str(settings.get("baseUrl", "")).strip()
        result["model_name"] = str(settings.get("modelName", "")).strip()
        result["auth_type"] = str(settings.get("selectedAuthType", "")).strip()

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
