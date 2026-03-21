"""
Qwen Code integration helpers.

This module centralizes:
- Local Qwen CLI credential detection (`~/.qwen`)
- Qwen Code model catalog definitions
- Qwen Code API settings helpers
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Optional
from urllib.parse import urlsplit
import json
import time

from .security_utils import write_json_secure


QWENCODE_DEFAULT_API_URL = "https://dashscope.aliyuncs.com/compatible-mode/v1"
QWENCODE_DEFAULT_ENDPOINT = ""
QWENCODE_TOKEN_URL = "https://chat.qwen.ai/api/v1/oauth2/token"
QWENCODE_CLIENT_ID = "f0304373b74a44d2b584a3fb70ca9e56"
QWENCODE_REFRESH_BUFFER_MS = 60 * 60 * 1000
QWENCODE_DEFAULT_CHANNEL = "reverie-cli"

_QWENCODE_THINKING_SUFFIXES = {"auto", "low", "medium", "high", "xhigh", "minimal"}

_QWENCODE_DEFAULT_HEADERS = {
    "User-Agent": "QwenCode/0.11.1 (win32; x64)",
    "X-DashScope-UserAgent": "QwenCode/0.11.1 (win32; x64)",
    "X-DashScope-CacheControl": "enable",
    "X-DashScope-AuthType": "qwen-oauth",
    "X-Stainless-Runtime-Version": "v22.17.0",
    "X-Stainless-Lang": "js",
    "X-Stainless-Arch": "x64",
    "X-Stainless-Package-Version": "5.11.0",
    "X-Stainless-Os": "Windows",
    "X-Stainless-Runtime": "node",
    "X-Stainless-Retry-Count": "0",
    "Sec-Fetch-Mode": "cors",
}

_QWENCODE_MODEL_ALIASES = {
    "qwen3-coder-plus": "coder-model",
    "qwen3.5plus": "coder-model",
    "qwen3.5-plus": "coder-model",
    "qwen-3.5-plus": "coder-model",
    "qwen3.5 plus": "coder-model",
}

_QWENCODE_BASE_MODELS = [
    {
        "id": "coder-model",
        "display_name": "coder-model",
        "description": "Qwen 3.5 Plus - efficient hybrid model with leading coding performance",
        "context_length": 1_000_000,
    },
]


def default_qwencode_config() -> Dict[str, Any]:
    """Default Qwen Code config stored inside Reverie config.json."""
    return {
        "selected_model_id": "",
        "selected_model_display_name": "",
        "api_url": QWENCODE_DEFAULT_API_URL,
        "endpoint": QWENCODE_DEFAULT_ENDPOINT,
        "custom_headers": {},
        "max_context_tokens": 1_000_000,
        "timeout": 1200,
    }


def _canonicalize_qwencode_model_id(model_id: Any) -> str:
    value = str(model_id or "").strip()
    if not value:
        return ""
    return _QWENCODE_MODEL_ALIASES.get(value.lower(), value)


def _normalize_qwencode_endpoint(endpoint: Any) -> str:
    value = str(endpoint or "").strip()
    if not value:
        return ""
    lowered = value.lower()
    if lowered in ("none", "off", "default", "clear"):
        return ""
    return value


def _normalize_custom_headers(raw_headers: Any) -> Dict[str, str]:
    headers: Dict[str, str] = {}
    if not isinstance(raw_headers, dict):
        return headers

    for key, value in raw_headers.items():
        k = str(key or "").strip()
        v = str(value or "").strip()
        if k and v:
            headers[k] = v
    return headers


def _normalize_resource_url(value: str) -> str:
    url = str(value or "").strip()
    if not url:
        return ""
    if not url.startswith("http://") and not url.startswith("https://"):
        url = f"https://{url}"
    return url.rstrip("/")


def _ensure_v1_suffix(api_url: str) -> str:
    url = str(api_url or "").strip().rstrip("/")
    if not url:
        return ""
    if not url.endswith("/v1"):
        url = f"{url}/v1"
    return url


def _normalize_qwencode_api_url(value: Any) -> str:
    url = _normalize_resource_url(str(value or ""))
    if not url:
        url = QWENCODE_DEFAULT_API_URL
    return _ensure_v1_suffix(url)


def resolve_qwencode_request_url(api_url: str, endpoint: str = "") -> str:
    """Resolve Qwen request URL with optional endpoint override."""
    endpoint_value = str(endpoint or "").strip()
    if endpoint_value:
        if endpoint_value.startswith("http://") or endpoint_value.startswith("https://"):
            return endpoint_value
        base = _normalize_qwencode_api_url(api_url)
        if endpoint_value.startswith("/"):
            return f"{base}{endpoint_value}"
        return f"{base}/{endpoint_value}"
    base = _normalize_qwencode_api_url(api_url)
    if base.lower().endswith("/chat/completions"):
        return base
    return f"{base}/chat/completions"


def get_qwencode_request_headers(extra_headers: Optional[Dict[str, str]] = None) -> Dict[str, str]:
    """Build Qwen request headers matching the CLI as closely as practical."""
    headers = dict(_QWENCODE_DEFAULT_HEADERS)
    if isinstance(extra_headers, dict):
        for key, value in extra_headers.items():
            k = str(key or "").strip()
            v = str(value or "").strip()
            if k and v:
                headers[k] = v
    return headers


def normalize_qwencode_model_for_request(model_name: Any) -> tuple[str, Optional[bool]]:
    """
    Normalize model id and extract any user-facing thinking toggle suffix.

    Supported suffix examples:
    - `coder-model(high)` -> (`coder-model`, True)
    - `coder-model(none)` -> (`coder-model`, False)
    """
    raw_model = str(model_name or "").strip()
    if not raw_model:
        return "", None

    base_model = raw_model
    enable_thinking: Optional[bool] = None

    if "(" in raw_model and ")" in raw_model:
        base_model = raw_model.split("(", 1)[0].strip()
        suffix = raw_model.split("(", 1)[1].split(")", 1)[0].strip().lower()
        if suffix in _QWENCODE_THINKING_SUFFIXES or suffix.isdigit():
            enable_thinking = True
        elif suffix in {"none", "0", "off", "false"}:
            enable_thinking = False

    normalized_model = _canonicalize_qwencode_model_id(base_model or raw_model)
    return normalized_model, enable_thinking


def resolve_qwencode_thinking_enabled(model_name: Any, thinking_mode: Any = None) -> bool:
    """
    Resolve whether Qwen thinking should be enabled.

    Qwen Code's DashScope-compatible flow commonly exposes reasoning by default,
    so Reverie mirrors that unless the user explicitly disables it.
    """
    if isinstance(thinking_mode, str):
        lowered = thinking_mode.strip().lower()
        if lowered == "true":
            return True
        if lowered == "false":
            return False

    _, suffix_choice = normalize_qwencode_model_for_request(model_name)
    if suffix_choice is not None:
        return suffix_choice

    return True


def build_qwencode_request_metadata(
    session_id: str = "",
    user_prompt_id: str = "",
    channel: str = QWENCODE_DEFAULT_CHANNEL,
) -> Dict[str, Any]:
    """Build Qwen-style request metadata similar to the official CLI."""
    metadata: Dict[str, Any] = {}
    if str(session_id or "").strip():
        metadata["sessionId"] = str(session_id).strip()
    if str(user_prompt_id or "").strip():
        metadata["promptId"] = str(user_prompt_id).strip()
    if str(channel or "").strip():
        metadata["channel"] = str(channel).strip()
    return metadata


def apply_qwencode_request_defaults(
    payload: Dict[str, Any],
    *,
    session_id: str = "",
    user_prompt_id: str = "",
    thinking_mode: Any = None,
) -> Dict[str, Any]:
    """Apply Qwen Code request defaults that mirror the official CLI more closely."""
    prepared = dict(payload or {})

    normalized_model, suffix_choice = normalize_qwencode_model_for_request(prepared.get("model", ""))
    if normalized_model:
        prepared["model"] = normalized_model

    if isinstance(prepared.get("stream"), bool) and prepared.get("stream"):
        stream_options = prepared.get("stream_options")
        if not isinstance(stream_options, dict):
            stream_options = {}
            prepared["stream_options"] = stream_options
        stream_options["include_usage"] = True

    if not isinstance(prepared.get("enable_thinking"), bool):
        prepared["enable_thinking"] = (
            resolve_qwencode_thinking_enabled(normalized_model or prepared.get("model", ""), thinking_mode)
            if suffix_choice is None
            else bool(suffix_choice)
        )

    existing_metadata = prepared.get("metadata")
    merged_metadata = dict(existing_metadata) if isinstance(existing_metadata, dict) else {}
    merged_metadata.update(
        build_qwencode_request_metadata(
            session_id=session_id,
            user_prompt_id=user_prompt_id,
        )
    )
    if merged_metadata:
        prepared["metadata"] = merged_metadata

    return prepared


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


def _parse_expiry_ms(value: Any) -> Optional[int]:
    try:
        expiry = int(value)
    except (TypeError, ValueError):
        return None
    if expiry <= 0:
        return None
    if expiry < 10_000_000_000:
        expiry *= 1000
    return expiry


def _oauth_creds_path() -> Path:
    return Path.home() / ".qwen" / "oauth_creds.json"


def _refresh_qwencode_oauth_credentials(credentials: Dict[str, Any], errors: List[str]) -> Optional[Dict[str, Any]]:
    refresh_token = str(credentials.get("refresh_token", "")).strip()
    if not refresh_token:
        errors.append("oauth_creds.json missing refresh_token; cannot refresh access token")
        return None

    try:
        import requests

        response = requests.post(
            QWENCODE_TOKEN_URL,
            headers={"Content-Type": "application/x-www-form-urlencoded"},
            data={
                "grant_type": "refresh_token",
                "client_id": QWENCODE_CLIENT_ID,
                "refresh_token": refresh_token,
            },
            timeout=30,
        )
    except Exception as exc:
        errors.append(f"refresh request failed: {exc}")
        return None

    if not response.ok:
        errors.append(f"refresh failed ({response.status_code})")
        return None

    try:
        response_data = response.json()
    except Exception as exc:
        errors.append(f"refresh response parse failed: {exc}")
        return None

    access_token = str(response_data.get("access_token", "")).strip()
    expires_in = response_data.get("expires_in")
    try:
        expires_in_int = int(expires_in)
    except (TypeError, ValueError):
        expires_in_int = 0

    if not access_token or expires_in_int <= 0:
        errors.append("refresh response missing access_token or expires_in")
        return None

    refreshed = dict(credentials)
    refreshed["access_token"] = access_token
    refreshed["refresh_token"] = str(response_data.get("refresh_token", refresh_token)).strip() or refresh_token
    refreshed["expiry_date"] = int(time.time() * 1000) + expires_in_int * 1000

    incoming_resource_url = str(response_data.get("resource_url", "")).strip()
    if incoming_resource_url:
        refreshed["resource_url"] = incoming_resource_url

    try:
        _save_oauth_credentials_data(refreshed)
    except Exception as exc:
        errors.append(f"save refreshed credentials failed: {exc}")
        return None

    return refreshed


def _save_oauth_credentials_data(data: Dict[str, Any]) -> None:
    creds_file = _oauth_creds_path()
    creds_file.parent.mkdir(parents=True, exist_ok=True)

    merged_data: Dict[str, Any] = {}
    if creds_file.exists():
        try:
            with open(creds_file, "r", encoding="utf-8") as f:
                loaded = json.load(f)
            if isinstance(loaded, dict):
                merged_data.update(loaded)
        except Exception:
            pass

    merged_data.update(data)
    write_json_secure(creds_file, merged_data)


def get_qwencode_model_catalog() -> List[Dict[str, Any]]:
    """Return Qwen Code model catalog."""
    catalog: List[Dict[str, Any]] = []
    seen_model_ids = set()

    for item in _QWENCODE_BASE_MODELS:
        model_id = str(item.get("id", "")).strip()
        if not model_id or model_id.lower() in seen_model_ids:
            continue
        seen_model_ids.add(model_id.lower())
        catalog.append(
            {
                "id": model_id,
                "display_name": str(item.get("display_name", model_id)).strip(),
                "description": str(item.get("description", "")).strip(),
                "context_length": int(item.get("context_length", 32768)),
            }
        )

    return catalog


def find_qwencode_model(model_id: str, catalog: Optional[List[Dict[str, Any]]] = None) -> Optional[Dict[str, Any]]:
    """Find Qwen Code model by id (case-insensitive)."""
    wanted = _canonicalize_qwencode_model_id(model_id).lower()
    if not wanted:
        return None

    items = catalog if isinstance(catalog, list) else get_qwencode_model_catalog()
    for item in items:
        if str(item.get("id", "")).strip().lower() == wanted:
            return item
    return None


def normalize_qwencode_config(raw_qwencode: Any) -> Dict[str, Any]:
    """Normalize Qwen Code config for persistence and runtime usage."""
    cfg = default_qwencode_config()
    if isinstance(raw_qwencode, dict):
        cfg.update(raw_qwencode)

    cfg["selected_model_id"] = _canonicalize_qwencode_model_id(cfg.get("selected_model_id", ""))
    cfg["selected_model_display_name"] = str(cfg.get("selected_model_display_name", "")).strip()
    cfg["api_url"] = _normalize_qwencode_api_url(cfg.get("api_url", QWENCODE_DEFAULT_API_URL))
    cfg["endpoint"] = _normalize_qwencode_endpoint(cfg.get("endpoint", ""))
    cfg["custom_headers"] = _normalize_custom_headers(cfg.get("custom_headers", {}))

    try:
        max_tokens = int(cfg.get("max_context_tokens", 1_000_000))
    except (TypeError, ValueError):
        max_tokens = 1_000_000
    if max_tokens <= 0:
        max_tokens = 1_000_000
    cfg["max_context_tokens"] = max_tokens

    try:
        timeout_int = int(cfg.get("timeout", 1200))
    except (TypeError, ValueError):
        timeout_int = 1200
    if timeout_int <= 0:
        timeout_int = 1200
    cfg["timeout"] = timeout_int

    catalog = get_qwencode_model_catalog()
    matched = find_qwencode_model(cfg["selected_model_id"], catalog=catalog)
    if matched:
        cfg["selected_model_id"] = matched["id"]
        cfg["selected_model_display_name"] = matched["display_name"]
        cfg["max_context_tokens"] = int(matched.get("context_length", cfg["max_context_tokens"]))
    elif cfg["selected_model_id"]:
        cfg["selected_model_id"] = ""
        cfg["selected_model_display_name"] = ""
        cfg["max_context_tokens"] = 1_000_000

    return cfg


def resolve_qwencode_selected_model(qwencode_config: Any) -> Optional[Dict[str, Any]]:
    """Resolve selected Qwen Code model metadata from config."""
    cfg = normalize_qwencode_config(qwencode_config)
    model_id = _canonicalize_qwencode_model_id(cfg.get("selected_model_id", ""))
    if not model_id:
        return None

    catalog = get_qwencode_model_catalog()
    matched = find_qwencode_model(model_id, catalog=catalog)
    if matched:
        return matched

    display_name = cfg.get("selected_model_display_name") or model_id
    return {
        "id": model_id,
        "display_name": display_name,
        "description": "Custom Qwen Code model id",
        "context_length": cfg.get("max_context_tokens", 1_000_000),
    }


def build_qwencode_runtime_model_data(qwencode_config: Any) -> Optional[Dict[str, Any]]:
    """Build runtime model config dict for agent initialization."""
    cfg = normalize_qwencode_config(qwencode_config)
    selected = resolve_qwencode_selected_model(cfg)
    if not selected:
        return None

    cred = detect_qwencode_cli_credentials(refresh_if_needed=True)
    api_key = cred["api_key"] if cred.get("found") else ""
    api_url = _normalize_qwencode_api_url(cred.get("resource_url") or cfg["api_url"])
    max_context_tokens = selected.get("context_length", cfg["max_context_tokens"])

    return {
        "model": _canonicalize_qwencode_model_id(selected["id"]),
        "model_display_name": selected["display_name"],
        "base_url": resolve_qwencode_request_url(api_url, cfg.get("endpoint", "")),
        "api_key": api_key,
        "max_context_tokens": max_context_tokens,
        "provider": "request",
        "thinking_mode": None,
        "endpoint": "",
        "custom_headers": get_qwencode_request_headers(cfg.get("custom_headers", {})),
    }


def detect_qwencode_cli_credentials(
    refresh_if_needed: bool = True,
    force_refresh: bool = False,
) -> Dict[str, Any]:
    """
    Detect Qwen Code CLI credentials from local cache.

    Priority:
    1) ~/.qwen/oauth_creds.json -> access_token + resource_url
    2) ~/.qwen/qwen_accounts.json -> access_token
    """
    qwen_dir = Path.home() / ".qwen"
    result = {
        "found": False,
        "api_key": "",
        "resource_url": "",
        "source_file": "",
        "source_field": "",
        "expires_at": None,
        "is_expired": None,
        "refreshed": False,
        "errors": [],
    }

    oauth_file = _oauth_creds_path()
    if oauth_file.exists():
        oauth_data = _load_json_dict(oauth_file, result["errors"])
        if isinstance(oauth_data, dict):
            access_token = str(oauth_data.get("access_token", "")).strip()
            expiry_ms = _parse_expiry_ms(oauth_data.get("expiry_date"))
            is_expired = bool(expiry_ms is not None and expiry_ms <= int(time.time() * 1000))
            needs_refresh = bool(
                refresh_if_needed
                and expiry_ms is not None
                and expiry_ms <= int(time.time() * 1000) + QWENCODE_REFRESH_BUFFER_MS
            )

            if access_token and (force_refresh or needs_refresh):
                refreshed = _refresh_qwencode_oauth_credentials(oauth_data, result["errors"])
                if isinstance(refreshed, dict):
                    oauth_data = refreshed
                    access_token = str(oauth_data.get("access_token", "")).strip()
                    expiry_ms = _parse_expiry_ms(oauth_data.get("expiry_date"))
                    is_expired = bool(expiry_ms is not None and expiry_ms <= int(time.time() * 1000))
                    result["refreshed"] = True

            if access_token:
                result["found"] = True
                result["api_key"] = access_token
                result["source_file"] = str(oauth_file)
                result["source_field"] = "access_token"
                result["expires_at"] = expiry_ms
                result["is_expired"] = is_expired
                result["resource_url"] = _normalize_resource_url(oauth_data.get("resource_url", ""))
                return result

    accounts_file = qwen_dir / "qwen_accounts.json"
    if accounts_file.exists():
        accounts_data = _load_json_dict(accounts_file, result["errors"])
        if isinstance(accounts_data, dict):
            access_token = str(accounts_data.get("access_token", "")).strip()
            if access_token:
                result["found"] = True
                result["api_key"] = access_token
                result["source_file"] = str(accounts_file)
                result["source_field"] = "access_token"
                return result

    return result


def mask_secret(secret: str) -> str:
    """Mask secret for safe terminal display."""
    value = str(secret or "").strip()
    if len(value) <= 8:
        return "*" * len(value)
    return f"{value[:4]}...{value[-4:]}"


def is_qwencode_api_url(url: str) -> bool:
    """Whether the URL points to Qwen Code API endpoint."""
    value = str(url or "").strip().lower()
    return any(
        host in value
        for host in (
            "dashscope.aliyuncs.com",
            "dashscope-intl.aliyuncs.com",
            "portal.qwen.ai",
        )
    )


def qwen_oauth_login(force_refresh: bool = True) -> Dict[str, Any]:
    """Validate or refresh Qwen OAuth credentials from local CLI cache."""
    cred = detect_qwencode_cli_credentials(refresh_if_needed=True, force_refresh=force_refresh)
    if cred.get("found"):
        return {
            "success": True,
            "access_token": cred.get("api_key", ""),
            "resource_url": cred.get("resource_url", ""),
            "source_file": cred.get("source_file", ""),
            "refreshed": bool(cred.get("refreshed")),
            "expires_at": cred.get("expires_at"),
            "is_expired": cred.get("is_expired"),
            "errors": cred.get("errors", []),
        }

    error = "Qwen CLI credentials not found. Run `qwen`, complete OAuth login, then retry."
    if cred.get("errors"):
        error = f"{error} Details: {' | '.join(str(x) for x in cred.get('errors', []))}"
    return {
        "success": False,
        "error": error,
    }


def save_qwen_credentials(access_token: str, refresh_token: str, resource_url: str = "") -> bool:
    """Save Qwen OAuth credentials to ~/.qwen/oauth_creds.json."""
    try:
        now_ms = int(time.time() * 1000)
        creds_data = {
            "access_token": access_token,
            "refresh_token": refresh_token,
            "token_type": "Bearer",
            "expiry_date": now_ms + (3600 * 1000),
        }

        if resource_url:
            creds_data["resource_url"] = _normalize_resource_url(resource_url)

        _save_oauth_credentials_data(creds_data)
        return True
    except Exception as e:
        print(f"Error saving credentials: {e}")
        return False
