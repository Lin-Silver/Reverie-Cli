"""
Codex CLI integration helpers.

This module centralizes:
- Local Codex CLI credential detection (`~/.codex`)
- Codex model catalog definitions
- Codex request translation helpers
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
import json
import time
import uuid

from .security_utils import write_json_secure


CODEX_DEFAULT_API_URL = "https://chatgpt.com/backend-api/codex"
CODEX_DEFAULT_ENDPOINT = ""
CODEX_DEFAULT_RESPONSE_ENDPOINT = "/responses"
CODEX_TOKEN_URL = "https://auth.openai.com/oauth/token"
CODEX_CLIENT_ID = "app_EMoamEEZ73f0CkXaXp7hrann"
CODEX_CLIENT_VERSION = "0.101.0"
CODEX_USER_AGENT = "codex_cli_rs/0.101.0 (Windows NT 10.0; Win64; x64) Reverie/2.1.3"
CODEX_DEFAULT_REASONING_EFFORT = "medium"
CODEX_DEFAULT_MAX_CONTEXT_TOKENS = 258_000
CODEX_REASONING_PRESETS = (
    {
        "id": "low",
        "label": "Low",
        "description": "Fast responses with lighter reasoning",
        "aliases": ("1", "low"),
    },
    {
        "id": "medium",
        "label": "Medium",
        "description": "Balances speed and reasoning depth for everyday tasks",
        "aliases": ("2", "medium", "balanced"),
    },
    {
        "id": "high",
        "label": "High",
        "description": "Greater reasoning depth for complex problems",
        "aliases": ("3", "high"),
    },
    {
        "id": "xhigh",
        "label": "Extra High",
        "description": "Extra high reasoning depth for complex problems",
        "aliases": ("4", "xhigh", "x-high", "extra high", "extra-high", "extra_high"),
    },
)

_CODEX_ALLOWED_MODELS = [
    {
        "id": "gpt-5.3-codex",
        "display_name": "GPT-5.3-Codex",
        "description": "GPT-5.3 Codex",
        "context_length": 258_000,
        "reasoning_levels": ["low", "medium", "high", "xhigh"],
    },
    {
        "id": "gpt-5.4",
        "display_name": "GPT-5.4",
        "description": "GPT-5.4",
        "context_length": 258_000,
        "reasoning_levels": ["low", "medium", "high", "xhigh"],
    },
    {
        "id": "gpt-5.2-codex",
        "display_name": "GPT-5.2-Codex",
        "description": "GPT-5.2 Codex",
        "context_length": 258_000,
        "reasoning_levels": ["low", "medium", "high", "xhigh"],
    },
    {
        "id": "gpt-5.1-codex-max",
        "display_name": "GPT-5.1-Codex-Max",
        "description": "GPT-5.1 Codex Max",
        "context_length": 258_000,
        "reasoning_levels": ["low", "medium", "high", "xhigh"],
    },
    {
        "id": "gpt-5.2",
        "display_name": "GPT-5.2",
        "description": "GPT-5.2",
        "context_length": 258_000,
        "reasoning_levels": ["low", "medium", "high", "xhigh"],
    },
    {
        "id": "gpt-5.1-codex-mini",
        "display_name": "GPT-5.1-Codex-Mini",
        "description": "GPT-5.1 Codex Mini",
        "context_length": 258_000,
        "reasoning_levels": ["medium", "high"],
    },
]
_CODEX_ALLOWED_MODEL_IDS = tuple(item["id"] for item in _CODEX_ALLOWED_MODELS)
_CODEX_ALLOWED_MODEL_SET = {item["id"].lower() for item in _CODEX_ALLOWED_MODELS}
_CODEX_MODEL_METADATA = {item["id"].lower(): dict(item) for item in _CODEX_ALLOWED_MODELS}
_CODEX_REASONING_PRESET_BY_ID = {
    item["id"]: {k: v for k, v in item.items() if k != "aliases"}
    for item in CODEX_REASONING_PRESETS
}
_CODEX_REASONING_ALIAS_MAP = {}
for _preset in CODEX_REASONING_PRESETS:
    for _alias in _preset.get("aliases", ()):
        _CODEX_REASONING_ALIAS_MAP[str(_alias).strip().lower()] = _preset["id"]
    _CODEX_REASONING_ALIAS_MAP[_preset["id"]] = _preset["id"]


def _safe_string(value: Any) -> str:
    """Normalize nullable values from local Codex auth/cache files."""
    if value is None:
        return ""
    return str(value).strip()


def default_codex_config() -> Dict[str, Any]:
    """Default Codex config stored inside Reverie config.json."""
    return {
        "selected_model_id": "",
        "selected_model_display_name": "",
        "api_url": CODEX_DEFAULT_API_URL,
        "endpoint": CODEX_DEFAULT_ENDPOINT,
        "reasoning_effort": CODEX_DEFAULT_REASONING_EFFORT,
        "max_context_tokens": CODEX_DEFAULT_MAX_CONTEXT_TOKENS,
        "timeout": 1200,
    }


def _normalize_api_url(value: Any) -> str:
    url = str(value or "").strip()
    if not url:
        return CODEX_DEFAULT_API_URL
    if not url.startswith("http://") and not url.startswith("https://"):
        url = f"https://{url}"
    return url.rstrip("/")


def _normalize_endpoint(endpoint: Any) -> str:
    value = str(endpoint or "").strip()
    if not value:
        return ""
    if value.lower() in ("none", "off", "default", "clear"):
        return ""
    return value


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


def normalize_codex_reasoning_choice(value: Any) -> str:
    """Normalize user-facing reasoning labels into Codex effort ids."""
    raw_value = _safe_string(value).lower()
    if not raw_value:
        return ""
    return _CODEX_REASONING_ALIAS_MAP.get(raw_value, raw_value.replace(" ", ""))


def get_codex_reasoning_catalog(
    model_id: str = "",
    catalog: Optional[List[Dict[str, Any]]] = None,
) -> List[Dict[str, str]]:
    """Return reasoning choices with CLI-style labels for a model."""
    available_levels = set(get_codex_reasoning_efforts(model_id, catalog=catalog))
    items: List[Dict[str, str]] = []
    for preset in CODEX_REASONING_PRESETS:
        if preset["id"] not in available_levels:
            continue
        items.append(dict(_CODEX_REASONING_PRESET_BY_ID[preset["id"]]))
    return items


def get_codex_reasoning_label(level: Any) -> str:
    """Return the CLI-style label for a reasoning effort."""
    normalized = normalize_codex_reasoning_choice(level)
    if normalized in _CODEX_REASONING_PRESET_BY_ID:
        return str(_CODEX_REASONING_PRESET_BY_ID[normalized]["label"])
    return _safe_string(level) or CODEX_DEFAULT_REASONING_EFFORT.title()


def _normalize_reasoning_effort(value: Any, available_levels: Optional[List[str]] = None) -> str:
    effort = normalize_codex_reasoning_choice(value) or CODEX_DEFAULT_REASONING_EFFORT
    levels = [
        normalize_codex_reasoning_choice(level)
        for level in (available_levels or [])
        if normalize_codex_reasoning_choice(level)
    ]
    if not levels:
        levels = list(_CODEX_MODEL_METADATA["gpt-5.3-codex"]["reasoning_levels"])
    if effort in levels:
        return effort
    if CODEX_DEFAULT_REASONING_EFFORT in levels:
        return CODEX_DEFAULT_REASONING_EFFORT
    return levels[0]


def _auth_path() -> Path:
    return Path.home() / ".codex" / "auth.json"


def _models_cache_path() -> Path:
    return Path.home() / ".codex" / "models_cache.json"


def _parse_codex_model_cache(errors: List[str]) -> List[Dict[str, Any]]:
    path = _models_cache_path()
    if not path.exists():
        return []

    data = _load_json_dict(path, errors)
    if not isinstance(data, dict):
        return []

    models = data.get("models")
    if not isinstance(models, list):
        return []

    catalog: List[Dict[str, Any]] = []
    seen_ids = set()
    for item in models:
        if not isinstance(item, dict):
            continue
        model_id = _safe_string(item.get("slug", ""))
        if not model_id:
            continue
        if model_id.lower() not in _CODEX_ALLOWED_MODEL_SET:
            continue
        if not bool(item.get("supported_in_api", True)):
            continue
        lower_id = model_id.lower()
        if lower_id in seen_ids:
            continue
        seen_ids.add(lower_id)
        metadata = _CODEX_MODEL_METADATA.get(lower_id, {})
        context_length = int(metadata.get("context_length", CODEX_DEFAULT_MAX_CONTEXT_TOKENS))
        raw_reasoning_levels = item.get("supported_reasoning_levels", [])
        reasoning_levels = []
        if isinstance(raw_reasoning_levels, list):
            for level in raw_reasoning_levels:
                if isinstance(level, dict):
                    effort = _safe_string(level.get("effort", "")).lower()
                else:
                    effort = _safe_string(level).lower()
                if effort and effort not in reasoning_levels:
                    reasoning_levels.append(effort)
        if not reasoning_levels:
            reasoning_levels = list(metadata.get("reasoning_levels", []))
        catalog.append(
            {
                "id": model_id,
                "display_name": _safe_string(metadata.get("display_name", item.get("display_name", model_id))) or model_id,
                "description": _safe_string(metadata.get("description", item.get("description", ""))),
                "context_length": context_length,
                "visibility": _safe_string(item.get("visibility", "")),
                "reasoning_levels": reasoning_levels,
            }
        )
    return catalog


def get_codex_model_catalog() -> List[Dict[str, Any]]:
    """Return Codex model catalog, preferring the local Codex CLI cache."""
    errors: List[str] = []
    cached = _parse_codex_model_cache(errors)
    cached_by_id = {
        str(item.get("id", "")).strip().lower(): item
        for item in cached
        if str(item.get("id", "")).strip()
    }

    catalog: List[Dict[str, Any]] = []
    for item in _CODEX_ALLOWED_MODELS:
        lower_id = item["id"].lower()
        cached_item = cached_by_id.get(lower_id, {})
        metadata_levels = [
            normalize_codex_reasoning_choice(level)
            for level in item.get("reasoning_levels", [])
            if normalize_codex_reasoning_choice(level)
        ]
        cached_levels = [
            normalize_codex_reasoning_choice(level)
            for level in cached_item.get("reasoning_levels", [])
            if normalize_codex_reasoning_choice(level)
        ]
        merged_levels: List[str] = []
        for level in metadata_levels + cached_levels:
            if level and level not in merged_levels:
                merged_levels.append(level)

        metadata_context_length = int(item.get("context_length", CODEX_DEFAULT_MAX_CONTEXT_TOKENS))

        catalog.append(
            {
                "id": item["id"],
                "display_name": _safe_string(cached_item.get("display_name", item["display_name"])) or item["display_name"],
                "description": _safe_string(cached_item.get("description", item.get("description", ""))) or item.get("description", ""),
                "context_length": metadata_context_length,
                "visibility": _safe_string(cached_item.get("visibility", "")),
                "reasoning_levels": merged_levels or metadata_levels,
            }
        )
    return catalog


def get_codex_reasoning_efforts(
    model_id: str = "",
    catalog: Optional[List[Dict[str, Any]]] = None,
) -> List[str]:
    """Return supported reasoning efforts for a Codex model."""
    items = catalog if isinstance(catalog, list) else get_codex_model_catalog()
    matched = find_codex_model(model_id, catalog=items) if model_id else None
    levels = []
    if matched:
        levels = [
            _safe_string(level).lower()
            for level in matched.get("reasoning_levels", [])
            if _safe_string(level)
        ]
    if not levels:
        levels = list(_CODEX_MODEL_METADATA["gpt-5.3-codex"]["reasoning_levels"])
    return levels


def find_codex_model(model_id: str, catalog: Optional[List[Dict[str, Any]]] = None) -> Optional[Dict[str, Any]]:
    wanted = str(model_id or "").strip().lower()
    if not wanted:
        return None
    items = catalog if isinstance(catalog, list) else get_codex_model_catalog()
    for item in items:
        if str(item.get("id", "")).strip().lower() == wanted:
            return item
    return None


def normalize_codex_config(raw_codex: Any) -> Dict[str, Any]:
    """Normalize Codex config for persistence and runtime usage."""
    cfg = default_codex_config()
    if isinstance(raw_codex, dict):
        cfg.update(raw_codex)

    cfg["selected_model_id"] = str(cfg.get("selected_model_id", "")).strip()
    cfg["selected_model_display_name"] = str(cfg.get("selected_model_display_name", "")).strip()
    cfg["api_url"] = _normalize_api_url(cfg.get("api_url", CODEX_DEFAULT_API_URL))
    cfg["endpoint"] = _normalize_endpoint(cfg.get("endpoint", ""))

    try:
        max_tokens = int(cfg.get("max_context_tokens", CODEX_DEFAULT_MAX_CONTEXT_TOKENS))
    except (TypeError, ValueError):
        max_tokens = CODEX_DEFAULT_MAX_CONTEXT_TOKENS
    if max_tokens <= 0:
        max_tokens = CODEX_DEFAULT_MAX_CONTEXT_TOKENS
    cfg["max_context_tokens"] = max_tokens

    try:
        timeout_int = int(cfg.get("timeout", 1200))
    except (TypeError, ValueError):
        timeout_int = 1200
    if timeout_int <= 0:
        timeout_int = 1200
    cfg["timeout"] = timeout_int

    catalog = get_codex_model_catalog()
    matched = find_codex_model(cfg["selected_model_id"], catalog=catalog)
    available_levels = get_codex_reasoning_efforts(cfg["selected_model_id"], catalog=catalog)
    cfg["reasoning_effort"] = _normalize_reasoning_effort(cfg.get("reasoning_effort", CODEX_DEFAULT_REASONING_EFFORT), available_levels)
    if matched:
        cfg["selected_model_id"] = matched["id"]
        cfg["selected_model_display_name"] = matched["display_name"]
        cfg["max_context_tokens"] = int(matched.get("context_length", cfg["max_context_tokens"]))
    elif cfg["selected_model_id"]:
        cfg["selected_model_id"] = ""
        cfg["selected_model_display_name"] = ""

    return cfg


def resolve_codex_selected_model(codex_config: Any) -> Optional[Dict[str, Any]]:
    """Resolve selected Codex model metadata from config."""
    cfg = normalize_codex_config(codex_config)
    model_id = cfg.get("selected_model_id", "")
    if not model_id:
        return None

    catalog = get_codex_model_catalog()
    matched = find_codex_model(model_id, catalog=catalog)
    if matched:
        return matched

    display_name = cfg.get("selected_model_display_name") or model_id
    return {
        "id": model_id,
        "display_name": display_name,
        "description": "Custom Codex model id",
        "context_length": cfg.get("max_context_tokens", CODEX_DEFAULT_MAX_CONTEXT_TOKENS),
        "reasoning_levels": get_codex_reasoning_efforts(model_id),
    }


def detect_codex_cli_credentials() -> Dict[str, Any]:
    """Detect Codex CLI credentials from ~/.codex/auth.json."""
    result = {
        "found": False,
        "api_key": "",
        "refresh_token": "",
        "account_id": "",
        "email": "",
        "source_file": "",
        "source_field": "",
        "auth_mode": "",
        "errors": [],
    }

    auth_file = _auth_path()
    if not auth_file.exists():
        return result

    data = _load_json_dict(auth_file, result["errors"])
    if not isinstance(data, dict):
        return result

    auth_mode = _safe_string(data.get("auth_mode", ""))
    api_key = _safe_string(data.get("OPENAI_API_KEY", ""))
    tokens = data.get("tokens")
    if not api_key and isinstance(tokens, dict):
        api_key = _safe_string(tokens.get("access_token", ""))
        result["refresh_token"] = _safe_string(tokens.get("refresh_token", ""))
        result["account_id"] = _safe_string(tokens.get("account_id", ""))

    if not api_key:
        return result

    result["found"] = True
    result["api_key"] = api_key
    result["source_file"] = str(auth_file)
    result["source_field"] = "OPENAI_API_KEY" if _safe_string(data.get("OPENAI_API_KEY", "")) else "tokens.access_token"
    result["auth_mode"] = auth_mode
    if isinstance(tokens, dict):
        result["email"] = _safe_string(tokens.get("email", ""))
    return result


def codex_oauth_login(force_refresh: bool = True) -> Dict[str, Any]:
    """Validate or refresh Codex CLI credentials from local cache."""
    cred = detect_codex_cli_credentials()
    if not cred.get("found"):
        error = "Codex CLI credentials not found. Run `codex login` and retry."
        if cred.get("errors"):
            error = f"{error} Details: {' | '.join(str(x) for x in cred.get('errors', []))}"
        return {"success": False, "error": error}

    refresh_token = str(cred.get("refresh_token", "")).strip()
    if force_refresh and refresh_token:
        try:
            refreshed = refresh_codex_access_token(refresh_token)
        except Exception as exc:
            return {"success": False, "error": str(exc)}
        if refreshed:
            cred.update(refreshed)
            cred["refreshed"] = True

    return {
        "success": True,
        "access_token": cred.get("api_key", ""),
        "refresh_token": cred.get("refresh_token", ""),
        "account_id": cred.get("account_id", ""),
        "source_file": cred.get("source_file", ""),
        "auth_mode": cred.get("auth_mode", ""),
        "refreshed": bool(cred.get("refreshed")),
        "errors": cred.get("errors", []),
    }


def refresh_codex_access_token(refresh_token: str) -> Optional[Dict[str, Any]]:
    """Refresh Codex OAuth tokens and persist them back to ~/.codex/auth.json."""
    token = str(refresh_token or "").strip()
    if not token:
        return None

    try:
        import requests

        response = requests.post(
            CODEX_TOKEN_URL,
            headers={
                "Content-Type": "application/x-www-form-urlencoded",
                "Accept": "application/json",
            },
            data={
                "client_id": CODEX_CLIENT_ID,
                "grant_type": "refresh_token",
                "refresh_token": token,
                "scope": "openid profile email",
            },
            timeout=30,
        )
    except Exception as exc:
        raise RuntimeError(f"Codex token refresh request failed: {exc}") from exc

    if not response.ok:
        raise RuntimeError(f"Codex token refresh failed ({response.status_code})")

    try:
        response_data = response.json()
    except Exception as exc:
        raise RuntimeError(f"Codex token refresh parse failed: {exc}") from exc

    access_token = str(response_data.get("access_token", "")).strip()
    new_refresh_token = str(response_data.get("refresh_token", "")).strip() or token
    id_token = str(response_data.get("id_token", "")).strip()
    if not access_token:
        raise RuntimeError("Codex token refresh returned no access_token")

    auth_file = _auth_path()
    current: Dict[str, Any] = {}
    if auth_file.exists():
        try:
            with open(auth_file, "r", encoding="utf-8") as f:
                loaded = json.load(f)
            if isinstance(loaded, dict):
                current.update(loaded)
        except Exception:
            pass

    tokens = current.get("tokens")
    if not isinstance(tokens, dict):
        tokens = {}
    tokens["access_token"] = access_token
    tokens["refresh_token"] = new_refresh_token
    if id_token:
        tokens["id_token"] = id_token
    current["tokens"] = tokens
    current["last_refresh"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())

    write_json_secure(auth_file, current)

    return {
        "api_key": access_token,
        "refresh_token": new_refresh_token,
        "account_id": str(tokens.get("account_id", "")).strip(),
    }


def resolve_codex_request_url(base_url: str, endpoint: str) -> str:
    """Resolve Codex request URL with optional endpoint override."""
    endpoint_value = str(endpoint or "").strip()
    if endpoint_value:
        if endpoint_value.startswith("http://") or endpoint_value.startswith("https://"):
            return endpoint_value
        base = _normalize_api_url(base_url)
        if endpoint_value.startswith("/"):
            return f"{base}{endpoint_value}"
        return f"{base}/{endpoint_value}"

    base = _normalize_api_url(base_url)
    return f"{base}{CODEX_DEFAULT_RESPONSE_ENDPOINT}"


def get_codex_request_headers(
    api_key: str,
    account_id: str = "",
    auth_mode: str = "",
    extra_headers: Optional[Dict[str, str]] = None,
    stream: bool = True,
) -> Dict[str, str]:
    """Build Codex upstream headers."""
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
        "Accept": "text/event-stream" if stream else "application/json",
        "Connection": "Keep-Alive",
        "Version": CODEX_CLIENT_VERSION,
        "Session_id": str(uuid.uuid4()),
        "User-Agent": CODEX_USER_AGENT,
    }
    if str(auth_mode or "").strip().lower() != "api_key":
        headers["Originator"] = "codex_cli_rs"
        if str(account_id or "").strip():
            headers["Chatgpt-Account-Id"] = str(account_id).strip()
    if isinstance(extra_headers, dict):
        for key, value in extra_headers.items():
            k = str(key or "").strip()
            v = str(value or "").strip()
            if k and v:
                headers[k] = v
    return headers


def build_codex_runtime_model_data(codex_config: Any) -> Optional[Dict[str, Any]]:
    """Build runtime model config dict for Codex."""
    cfg = normalize_codex_config(codex_config)
    selected = resolve_codex_selected_model(cfg)
    if not selected:
        return None

    cred = detect_codex_cli_credentials()
    api_key = cred["api_key"] if cred.get("found") else ""

    return {
        "model": selected["id"],
        "model_display_name": selected["display_name"],
        "base_url": cfg["api_url"],
        "api_key": api_key,
        "max_context_tokens": selected.get("context_length", cfg.get("max_context_tokens", CODEX_DEFAULT_MAX_CONTEXT_TOKENS)),
        "provider": "codex",
        "thinking_mode": cfg.get("reasoning_effort", CODEX_DEFAULT_REASONING_EFFORT),
        "endpoint": cfg.get("endpoint", ""),
    }


def build_codex_request_payload(
    model_name: str,
    messages: List[Dict[str, Any]],
    tools: Optional[List[Dict[str, Any]]] = None,
    reasoning_effort: str = "medium",
    stream: bool = True,
) -> Dict[str, Any]:
    """Translate OpenAI-style messages/tools into Codex responses payload."""
    effort = _normalize_reasoning_effort(
        reasoning_effort,
        get_codex_reasoning_efforts(model_name),
    )
    payload: Dict[str, Any] = {
        "instructions": "",
        "stream": bool(stream),
        "store": False,
        "parallel_tool_calls": True,
        "include": ["reasoning.encrypted_content"],
        "reasoning": {
            "effort": effort,
            "summary": "auto",
        },
        "model": model_name,
        "input": [],
    }

    for message in messages:
        role = str(message.get("role", "")).strip().lower()
        if role == "tool":
            payload["input"].append(
                {
                    "type": "function_call_output",
                    "call_id": str(message.get("tool_call_id", "")).strip(),
                    "output": str(message.get("content", "") or ""),
                }
            )
            continue

        input_role = "developer" if role == "system" else role
        item: Dict[str, Any] = {
            "type": "message",
            "role": input_role,
            "content": [],
        }

        content = str(message.get("content", "") or "")
        if content:
            content_type = "output_text" if role == "assistant" else "input_text"
            item["content"].append({"type": content_type, "text": content})

        payload["input"].append(item)

        if role == "assistant":
            for tool_call in message.get("tool_calls", []) or []:
                if str(tool_call.get("type", "")).strip().lower() != "function":
                    continue
                function_data = tool_call.get("function") or {}
                payload["input"].append(
                    {
                        "type": "function_call",
                        "call_id": str(tool_call.get("id", "")).strip(),
                        "name": str(function_data.get("name", "")).strip(),
                        "arguments": str(function_data.get("arguments", "") or ""),
                    }
                )

    if tools:
        payload["tools"] = []
        for tool in tools:
            if str(tool.get("type", "")).strip().lower() != "function":
                continue
            function_data = tool.get("function") or {}
            name = str(function_data.get("name", "")).strip()
            if not name:
                continue
            parameters = function_data.get("parameters")
            if not isinstance(parameters, dict):
                parameters = {"type": "object", "properties": {}}
            payload["tools"].append(
                {
                    "type": "function",
                    "name": name,
                    "description": str(function_data.get("description", "")).strip(),
                    "parameters": parameters,
                }
            )

    return payload


def parse_codex_sse_event(data_str: str, state: Optional[Dict[str, Any]] = None) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    """Parse a single Codex SSE `data:` payload into generic delta events."""
    if state is None:
        state = {
            "response_id": "",
            "created_at": 0,
            "model": "",
            "tool_index": -1,
            "has_received_arguments_delta": False,
            "has_tool_call_announced": False,
        }

    try:
        payload = json.loads(data_str)
    except Exception:
        return [], state

    event_type = str(payload.get("type", "")).strip()
    events: List[Dict[str, Any]] = []

    if event_type == "response.created":
        response = payload.get("response") or {}
        state["response_id"] = str(response.get("id", "")).strip()
        state["created_at"] = int(response.get("created_at", 0) or 0)
        state["model"] = str(response.get("model", "")).strip()
        return events, state

    response_usage = payload.get("response", {}).get("usage")
    if isinstance(response_usage, dict):
        events.append({"type": "usage", "usage": response_usage})

    if event_type == "response.reasoning_summary_text.delta":
        delta = str(payload.get("delta", "") or "")
        if delta:
            events.append({"type": "reasoning", "text": delta})
    elif event_type == "response.reasoning_summary_text.done":
        events.append({"type": "reasoning", "text": "\n\n"})
    elif event_type == "response.output_text.delta":
        delta = str(payload.get("delta", "") or "")
        if delta:
            events.append({"type": "content", "text": delta})
    elif event_type == "response.output_item.added":
        item = payload.get("item") or {}
        if str(item.get("type", "")).strip() == "function_call":
            state["tool_index"] = int(state.get("tool_index", -1)) + 1
            state["has_received_arguments_delta"] = False
            state["has_tool_call_announced"] = True
            events.append(
                {
                    "type": "tool_call_start",
                    "index": state["tool_index"],
                    "id": str(item.get("call_id", "")).strip(),
                    "name": str(item.get("name", "")).strip(),
                }
            )
    elif event_type == "response.function_call_arguments.delta":
        state["has_received_arguments_delta"] = True
        delta = str(payload.get("delta", "") or "")
        events.append(
            {
                "type": "tool_call_args",
                "index": int(state.get("tool_index", 0) or 0),
                "arguments": delta,
            }
        )
    elif event_type == "response.function_call_arguments.done":
        if not bool(state.get("has_received_arguments_delta")):
            events.append(
                {
                    "type": "tool_call_args",
                    "index": int(state.get("tool_index", 0) or 0),
                    "arguments": str(payload.get("arguments", "") or ""),
                }
            )
    elif event_type == "response.output_item.done":
        item = payload.get("item") or {}
        if str(item.get("type", "")).strip() == "function_call" and not bool(state.get("has_tool_call_announced")):
            state["tool_index"] = int(state.get("tool_index", -1)) + 1
            events.append(
                {
                    "type": "tool_call",
                    "index": int(state.get("tool_index", 0) or 0),
                    "id": str(item.get("call_id", "")).strip(),
                    "name": str(item.get("name", "")).strip(),
                    "arguments": str(item.get("arguments", "") or ""),
                }
            )
        state["has_tool_call_announced"] = False
    elif event_type == "response.completed":
        finish_reason = "tool_calls" if int(state.get("tool_index", -1) or -1) >= 0 else "stop"
        events.append({"type": "finish", "reason": finish_reason, "response": payload.get("response")})

    return events, state


def mask_secret(secret: str) -> str:
    """Mask secret for safe terminal display."""
    value = str(secret or "").strip()
    if len(value) <= 8:
        return "*" * len(value)
    return f"{value[:4]}...{value[-4:]}"


def is_codex_api_url(url: str) -> bool:
    """Whether the URL points to the Codex backend."""
    value = str(url or "").strip().lower()
    return "chatgpt.com/backend-api/codex" in value or "auth.openai.com" in value
