"""
Gemini CLI integration helpers.

This module centralizes:
- Local Gemini CLI credential detection (`~/.gemini`)
- Gemini CLI model catalog definitions
- Gemini CLI request translation helpers
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
import json
import re
import shutil
import time
import uuid
from urllib.parse import urlparse

from .security_utils import read_first_env, write_json_secure


GEMINICLI_DEFAULT_API_URL = "https://cloudcode-pa.googleapis.com"
GEMINICLI_DEFAULT_STREAM_ENDPOINT = "/v1internal:streamGenerateContent?alt=sse"
GEMINICLI_DEFAULT_NON_STREAM_ENDPOINT = "/v1internal:generateContent"
GEMINICLI_DEFAULT_COUNT_TOKENS_ENDPOINT = "/v1internal:countTokens"
GEMINICLI_DEFAULT_LOAD_ENDPOINT = "/v1internal:loadCodeAssist"
GEMINICLI_DEFAULT_ONBOARD_ENDPOINT = "/v1internal:onboardUser"
GEMINICLI_TOKEN_URL = "https://oauth2.googleapis.com/token"
GEMINICLI_CLIENT_ID_ENV_VARS = (
    "REVERIE_GEMINICLI_CLIENT_ID",
    "GEMINICLI_CLIENT_ID",
    "GOOGLE_OAUTH_CLIENT_ID",
)
GEMINICLI_CLIENT_SECRET_ENV_VARS = (
    "REVERIE_GEMINICLI_CLIENT_SECRET",
    "GEMINICLI_CLIENT_SECRET",
    "GOOGLE_OAUTH_CLIENT_SECRET",
)
GEMINICLI_REFRESH_BUFFER_MS = 30 * 60 * 1000
GEMINICLI_VERSION = "0.33.0"
GEMINICLI_API_CLIENT_HEADER = "google-genai-sdk/1.41.0 gl-node/v22.19.0"
GEMINICLI_OPERATION_POLL_SECONDS = 2.0
GEMINICLI_OPERATION_POLL_ATTEMPTS = 15

_GEMINICLI_PROJECT_CACHE: Dict[str, str] = {}
_GEMINICLI_OAUTH_CLIENT_CACHE: Optional[Tuple[str, str]] = None

_GEMINICLI_DEFAULT_SAFETY_SETTINGS = [
    {"category": "HARM_CATEGORY_HARASSMENT", "threshold": "OFF"},
    {"category": "HARM_CATEGORY_HATE_SPEECH", "threshold": "OFF"},
    {"category": "HARM_CATEGORY_SEXUALLY_EXPLICIT", "threshold": "OFF"},
    {"category": "HARM_CATEGORY_DANGEROUS_CONTENT", "threshold": "OFF"},
    {"category": "HARM_CATEGORY_CIVIC_INTEGRITY", "threshold": "BLOCK_NONE"},
]

_GEMINICLI_MODELS = [
    {
        "id": "gemini-3-flash-preview",
        "display_name": "Gemini 3 Flash Preview",
        "description": "Gemini 3 Flash Preview",
        "context_length": 1_048_576,
        "max_output_tokens": 65_536,
    },
    {
        "id": "gemini-3.1-flash-lite-preview",
        "display_name": "Gemini 3.1 Flash Lite Preview",
        "description": "Gemini 3.1 Flash Lite Preview",
        "context_length": 1_048_576,
        "max_output_tokens": 65_536,
    },
    {
        "id": "gemini-2.5-flash",
        "display_name": "Gemini 2.5 Flash",
        "description": "Gemini 2.5 Flash",
        "context_length": 1_048_576,
        "max_output_tokens": 65_536,
    },
    {
        "id": "gemini-2.5-flash-lite",
        "display_name": "Gemini 2.5 Flash Lite",
        "description": "Gemini 2.5 Flash Lite",
        "context_length": 1_048_576,
        "max_output_tokens": 65_536,
    },
]


def default_geminicli_config() -> Dict[str, Any]:
    """Default Gemini CLI config stored inside Reverie config.json."""
    return {
        "selected_model_id": "",
        "selected_model_display_name": "",
        "api_url": GEMINICLI_DEFAULT_API_URL,
        "endpoint": "",
        "project_id": "",
        "max_context_tokens": 1_048_576,
        "timeout": 1200,
    }


def _normalize_resource_url(value: Any) -> str:
    url = str(value or "").strip()
    if not url:
        return ""
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


def _normalize_api_url(value: Any) -> str:
    url = _normalize_resource_url(value)
    return url or GEMINICLI_DEFAULT_API_URL


def _split_geminicli_target(value: Any) -> Tuple[str, str]:
    """Split a target path into `(path, query)` with a guaranteed leading slash."""
    raw = str(value or "").strip()
    if not raw:
        return "", ""
    if "?" in raw:
        path, query = raw.split("?", 1)
    else:
        path, query = raw, ""
    path = f"/{path.lstrip('/')}" if path else ""
    return path, query


def _resolve_geminicli_url(base_url: str, target: str) -> str:
    """Resolve a Gemini CLI URL while avoiding double-appending known endpoints."""
    normalized_base = _normalize_api_url(base_url)
    parsed = urlparse(normalized_base)
    base_path = str(parsed.path or "").rstrip("/")
    lower_base_path = base_path.lower()
    target_path, target_query = _split_geminicli_target(target)
    if not target_path:
        return parsed._replace(fragment="").geturl().rstrip("/")

    known_paths = sorted(
        {
            GEMINICLI_DEFAULT_STREAM_ENDPOINT.split("?", 1)[0].lower(),
            GEMINICLI_DEFAULT_NON_STREAM_ENDPOINT.lower(),
            GEMINICLI_DEFAULT_COUNT_TOKENS_ENDPOINT.lower(),
            GEMINICLI_DEFAULT_LOAD_ENDPOINT.lower(),
            GEMINICLI_DEFAULT_ONBOARD_ENDPOINT.lower(),
        },
        key=len,
        reverse=True,
    )

    prefix_path = base_path
    for known_path in known_paths:
        if lower_base_path.endswith(known_path):
            prefix_path = base_path[:-len(known_path)]
            break

    if prefix_path.endswith("/") and target_path.startswith("/"):
        prefix_path = prefix_path[:-1]

    rebuilt = parsed._replace(
        path=f"{prefix_path}{target_path}" if prefix_path else target_path,
        query=target_query,
        fragment="",
    )
    return rebuilt.geturl().rstrip("/")


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


def _oauth_creds_path() -> Path:
    return Path.home() / ".gemini" / "oauth_creds.json"


def _google_accounts_path() -> Path:
    return Path.home() / ".gemini" / "google_accounts.json"


def _load_geminicli_oauth_client(errors: Optional[List[str]] = None) -> Optional[Tuple[str, str]]:
    """Load Gemini OAuth client credentials from environment variables."""
    global _GEMINICLI_OAUTH_CLIENT_CACHE

    if _GEMINICLI_OAUTH_CLIENT_CACHE is not None:
        return _GEMINICLI_OAUTH_CLIENT_CACHE

    client_id = read_first_env(GEMINICLI_CLIENT_ID_ENV_VARS)
    client_secret = read_first_env(GEMINICLI_CLIENT_SECRET_ENV_VARS)
    if client_id and client_secret:
        _GEMINICLI_OAUTH_CLIENT_CACHE = (client_id, client_secret)
        return _GEMINICLI_OAUTH_CLIENT_CACHE

    local_cli_client = _load_geminicli_oauth_client_from_local_install(errors)
    if local_cli_client is not None:
        _GEMINICLI_OAUTH_CLIENT_CACHE = local_cli_client
        return _GEMINICLI_OAUTH_CLIENT_CACHE

    if errors is not None:
        errors.append(
            "Gemini OAuth refresh requires environment variables "
            "REVERIE_GEMINICLI_CLIENT_ID and REVERIE_GEMINICLI_CLIENT_SECRET, "
            "or a local official Gemini CLI installation."
        )
    return None


def _candidate_geminicli_bundle_paths() -> List[Path]:
    candidates: List[Path] = []

    gemini_executable = shutil.which("gemini")
    if gemini_executable:
        executable_path = Path(gemini_executable).resolve()
        candidates.append(executable_path.parent / "node_modules" / "@google" / "gemini-cli" / "bundle" / "gemini.js")

    appdata = str(os.environ.get("APPDATA", "") or "").strip()
    if appdata:
        candidates.append(Path(appdata) / "npm" / "node_modules" / "@google" / "gemini-cli" / "bundle" / "gemini.js")

    candidates.extend(
        [
            Path("/usr/local/lib/node_modules/@google/gemini-cli/bundle/gemini.js"),
            Path("/opt/homebrew/lib/node_modules/@google/gemini-cli/bundle/gemini.js"),
            Path.home() / ".npm-global" / "lib" / "node_modules" / "@google" / "gemini-cli" / "bundle" / "gemini.js",
        ]
    )

    unique_paths: List[Path] = []
    seen: set[str] = set()
    for path in candidates:
        key = str(path)
        if key in seen:
            continue
        seen.add(key)
        unique_paths.append(path)
    return unique_paths


def _load_geminicli_oauth_client_from_local_install(
    errors: Optional[List[str]] = None,
) -> Optional[Tuple[str, str]]:
    for bundle_path in _candidate_geminicli_bundle_paths():
        if not bundle_path.exists():
            continue
        try:
            text = bundle_path.read_text(encoding="utf-8", errors="ignore")
        except Exception as exc:
            if errors is not None:
                errors.append(f"{bundle_path}: {exc}")
            continue

        client_id_match = re.search(r'OAUTH_CLIENT_ID\s*=\s*"([^"]+)"', text)
        client_secret_match = re.search(r'OAUTH_CLIENT_SECRET\s*=\s*"([^"]+)"', text)
        if client_id_match and client_secret_match:
            client_id = str(client_id_match.group(1)).strip()
            client_secret = str(client_secret_match.group(1)).strip()
            if client_id and client_secret:
                return client_id, client_secret

    if errors is not None:
        errors.append("Official Gemini CLI OAuth client metadata was not found in the local installation.")
    return None


def _load_active_gemini_email(errors: List[str]) -> str:
    path = _google_accounts_path()
    if not path.exists():
        return ""
    data = _load_json_dict(path, errors)
    if not isinstance(data, dict):
        return ""
    active = str(data.get("active", "")).strip()
    return active


def _refresh_geminicli_oauth_credentials(
    credentials: Dict[str, Any],
    errors: List[str],
) -> Optional[Dict[str, Any]]:
    refresh_token = str(credentials.get("refresh_token", "")).strip()
    if not refresh_token:
        errors.append("oauth_creds.json missing refresh_token; cannot refresh access token")
        return None

    oauth_client = _load_geminicli_oauth_client(errors)
    if oauth_client is None:
        return None
    client_id, client_secret = oauth_client

    try:
        import requests

        response = requests.post(
            GEMINICLI_TOKEN_URL,
            headers={"Content-Type": "application/x-www-form-urlencoded"},
            data={
                "grant_type": "refresh_token",
                "client_id": client_id,
                "client_secret": client_secret,
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
    refreshed["token_type"] = str(response_data.get("token_type", refreshed.get("token_type", "Bearer"))).strip() or "Bearer"

    try:
        _save_oauth_credentials_data(refreshed)
    except Exception as exc:
        errors.append(f"save refreshed credentials failed: {exc}")
        return None

    return refreshed


def _save_oauth_credentials_data(data: Dict[str, Any]) -> None:
    creds_file = _oauth_creds_path()
    creds_file.parent.mkdir(parents=True, exist_ok=True)

    merged: Dict[str, Any] = {}
    if creds_file.exists():
        try:
            with open(creds_file, "r", encoding="utf-8") as f:
                loaded = json.load(f)
            if isinstance(loaded, dict):
                merged.update(loaded)
        except Exception:
            pass

    merged.update(data)
    write_json_secure(creds_file, merged)


def get_geminicli_model_catalog() -> List[Dict[str, Any]]:
    """Return Gemini CLI model catalog."""
    return [
        {
            "id": str(item["id"]),
            "display_name": str(item["display_name"]),
            "description": str(item.get("description", "")),
            "context_length": int(item.get("context_length", 1_048_576)),
            "max_output_tokens": int(item.get("max_output_tokens", 65_536)),
        }
        for item in _GEMINICLI_MODELS
    ]


def find_geminicli_model(
    model_id: str,
    catalog: Optional[List[Dict[str, Any]]] = None,
) -> Optional[Dict[str, Any]]:
    wanted = str(model_id or "").strip().lower()
    if not wanted:
        return None

    items = catalog if isinstance(catalog, list) else get_geminicli_model_catalog()
    for item in items:
        if str(item.get("id", "")).strip().lower() == wanted:
            return item
    return None


def normalize_geminicli_config(raw_geminicli: Any) -> Dict[str, Any]:
    """Normalize Gemini CLI config for persistence and runtime usage."""
    cfg = default_geminicli_config()
    if isinstance(raw_geminicli, dict):
        cfg.update(raw_geminicli)

    cfg["selected_model_id"] = str(cfg.get("selected_model_id", "")).strip()
    cfg["selected_model_display_name"] = str(cfg.get("selected_model_display_name", "")).strip()
    cfg["api_url"] = _normalize_api_url(cfg.get("api_url", GEMINICLI_DEFAULT_API_URL))
    cfg["endpoint"] = _normalize_endpoint(cfg.get("endpoint", ""))
    cfg["project_id"] = str(cfg.get("project_id", "")).strip()

    try:
        max_tokens = int(cfg.get("max_context_tokens", 1_048_576))
    except (TypeError, ValueError):
        max_tokens = 1_048_576
    if max_tokens <= 0:
        max_tokens = 1_048_576
    cfg["max_context_tokens"] = max_tokens

    try:
        timeout_int = int(cfg.get("timeout", 1200))
    except (TypeError, ValueError):
        timeout_int = 1200
    if timeout_int <= 0:
        timeout_int = 1200
    cfg["timeout"] = timeout_int

    catalog = get_geminicli_model_catalog()
    matched = find_geminicli_model(cfg["selected_model_id"], catalog=catalog)
    if matched:
        cfg["selected_model_display_name"] = matched["display_name"]
    elif cfg["selected_model_id"] and not cfg["selected_model_display_name"]:
        cfg["selected_model_display_name"] = cfg["selected_model_id"]

    return cfg


def resolve_geminicli_selected_model(geminicli_config: Any) -> Optional[Dict[str, Any]]:
    """Resolve selected Gemini CLI model metadata from config."""
    cfg = normalize_geminicli_config(geminicli_config)
    model_id = cfg.get("selected_model_id", "")
    if not model_id:
        return None

    catalog = get_geminicli_model_catalog()
    matched = find_geminicli_model(model_id, catalog=catalog)
    if matched:
        return matched

    display_name = cfg.get("selected_model_display_name") or model_id
    return {
        "id": model_id,
        "display_name": display_name,
        "description": "Custom Gemini CLI model id",
        "context_length": cfg.get("max_context_tokens", 1_048_576),
        "max_output_tokens": 65_536,
    }


def detect_geminicli_cli_credentials(
    refresh_if_needed: bool = True,
    force_refresh: bool = False,
) -> Dict[str, Any]:
    """
    Detect Gemini CLI credentials from local cache.

    Priority:
    1) ~/.gemini/oauth_creds.json
    """
    result = {
        "found": False,
        "api_key": "",
        "refresh_token": "",
        "source_file": "",
        "source_field": "",
        "expires_at": None,
        "is_expired": None,
        "refreshed": False,
        "email": "",
        "errors": [],
    }

    oauth_file = _oauth_creds_path()
    if not oauth_file.exists():
        return result

    oauth_data = _load_json_dict(oauth_file, result["errors"])
    if not isinstance(oauth_data, dict):
        return result

    access_token = str(oauth_data.get("access_token", "")).strip()
    refresh_token = str(oauth_data.get("refresh_token", "")).strip()
    expiry_ms = _parse_expiry_ms(oauth_data.get("expiry_date"))
    now_ms = int(time.time() * 1000)
    is_expired = bool(expiry_ms is not None and expiry_ms <= now_ms)
    needs_refresh = bool(
        refresh_if_needed
        and expiry_ms is not None
        and expiry_ms <= now_ms + GEMINICLI_REFRESH_BUFFER_MS
    )

    if access_token and (force_refresh or needs_refresh):
        refreshed = _refresh_geminicli_oauth_credentials(oauth_data, result["errors"])
        if isinstance(refreshed, dict):
            oauth_data = refreshed
            access_token = str(oauth_data.get("access_token", "")).strip()
            refresh_token = str(oauth_data.get("refresh_token", refresh_token)).strip()
            expiry_ms = _parse_expiry_ms(oauth_data.get("expiry_date"))
            is_expired = bool(expiry_ms is not None and expiry_ms <= int(time.time() * 1000))
            result["refreshed"] = True

    if not access_token:
        return result

    if is_expired:
        result["errors"].append("Gemini CLI access token is expired and could not be refreshed.")
        return result

    result["found"] = True
    result["api_key"] = access_token
    result["refresh_token"] = refresh_token
    result["source_file"] = str(oauth_file)
    result["source_field"] = "access_token"
    result["expires_at"] = expiry_ms
    result["is_expired"] = is_expired
    result["email"] = _load_active_gemini_email(result["errors"])
    return result


def geminicli_oauth_login(force_refresh: bool = True) -> Dict[str, Any]:
    """Validate or refresh Gemini CLI OAuth credentials from local cache."""
    cred = detect_geminicli_cli_credentials(refresh_if_needed=True, force_refresh=force_refresh)
    if cred.get("found"):
        return {
            "success": True,
            "access_token": cred.get("api_key", ""),
            "source_file": cred.get("source_file", ""),
            "refreshed": bool(cred.get("refreshed")),
            "expires_at": cred.get("expires_at"),
            "is_expired": cred.get("is_expired"),
            "email": cred.get("email", ""),
            "errors": cred.get("errors", []),
        }

    error = "Gemini CLI credentials not found. Run `gemini` and complete login, then retry."
    if cred.get("errors"):
        error = f"{error} Details: {' | '.join(str(x) for x in cred.get('errors', []))}"
    return {
        "success": False,
        "error": error,
    }


def resolve_geminicli_request_url(base_url: str, endpoint: str, stream: bool) -> str:
    """Resolve Gemini CLI request URL with optional endpoint override."""
    endpoint_value = str(endpoint or "").strip()
    if endpoint_value:
        if endpoint_value.startswith("http://") or endpoint_value.startswith("https://"):
            return endpoint_value
        return _resolve_geminicli_url(base_url, endpoint_value)

    default_endpoint = GEMINICLI_DEFAULT_STREAM_ENDPOINT if stream else GEMINICLI_DEFAULT_NON_STREAM_ENDPOINT
    return _resolve_geminicli_url(base_url, default_endpoint)


def geminicli_count_tokens_url(base_url: str, endpoint: str = "") -> str:
    endpoint_value = str(endpoint or "").strip()
    if endpoint_value:
        return resolve_geminicli_request_url(base_url, endpoint_value, stream=False)
    return _resolve_geminicli_url(base_url, GEMINICLI_DEFAULT_COUNT_TOKENS_ENDPOINT)


def _resolve_geminicli_internal_url(base_url: str, path: str) -> str:
    return _resolve_geminicli_url(base_url, path)


def _resolve_geminicli_operation_url(base_url: str, operation_name: str) -> str:
    return _resolve_geminicli_url(base_url, f"/v1internal/{str(operation_name or '').lstrip('/')}")


def _geminicli_core_client_metadata(project_id: str = "") -> Dict[str, str]:
    metadata: Dict[str, str] = {
        "ideType": "IDE_UNSPECIFIED",
        "platform": "PLATFORM_UNSPECIFIED",
        "pluginType": "GEMINI",
    }
    duet_project = str(project_id or "").strip()
    if duet_project:
        metadata["duetProject"] = duet_project
    return metadata


def _select_geminicli_onboard_tier(load_response: Dict[str, Any]) -> Dict[str, Any]:
    allowed_tiers = load_response.get("allowedTiers")
    if isinstance(allowed_tiers, list):
        for item in allowed_tiers:
            if isinstance(item, dict) and item.get("isDefault") is True:
                return item
        for item in allowed_tiers:
            if isinstance(item, dict):
                return item
    return {
        "id": "standard-tier",
        "name": "standard-tier",
    }


def _geminicli_setup_error_message(load_response: Dict[str, Any]) -> str:
    ineligible_tiers = load_response.get("ineligibleTiers")
    if isinstance(ineligible_tiers, list):
        reasons = [
            str(item.get("reasonMessage", "")).strip()
            for item in ineligible_tiers
            if isinstance(item, dict) and str(item.get("reasonMessage", "")).strip()
        ]
        if reasons:
            return "; ".join(reasons)
    return ""


def resolve_geminicli_project_id(
    base_url: str,
    access_token: str,
    configured_project_id: str = "",
    extra_headers: Optional[Dict[str, str]] = None,
    timeout: int = 30,
) -> str:
    """Resolve a managed Code Assist project id for Gemini CLI accounts."""
    explicit_project = str(configured_project_id or "").strip()
    if explicit_project:
        return explicit_project

    env_project = (
        str(os.environ.get("GOOGLE_CLOUD_PROJECT", "") or "").strip()
        or str(os.environ.get("GOOGLE_CLOUD_PROJECT_ID", "") or "").strip()
    )
    active_email = _load_active_gemini_email([])
    cache_key = (
        active_email.strip().lower()
        or env_project.lower()
        or str(access_token or "")[-24:]
    )
    if cache_key and cache_key in _GEMINICLI_PROJECT_CACHE:
        return _GEMINICLI_PROJECT_CACHE[cache_key]

    import requests

    headers = get_geminicli_request_headers(
        model_id="gemini-cli-bootstrap",
        access_token=access_token,
        stream=False,
        extra_headers=extra_headers,
    )

    load_request = {
        "metadata": _geminicli_core_client_metadata(env_project),
    }
    if env_project:
        load_request["cloudaicompanionProject"] = env_project
    load_response = requests.post(
        _resolve_geminicli_internal_url(base_url, GEMINICLI_DEFAULT_LOAD_ENDPOINT),
        headers=headers,
        json=load_request,
        timeout=timeout,
    )
    load_response.raise_for_status()
    load_data = load_response.json() if load_response.content else {}

    current_tier = load_data.get("currentTier")
    if isinstance(current_tier, dict):
        resolved_project = str(load_data.get("cloudaicompanionProject", "") or "").strip() or env_project
        if not resolved_project:
            detail = _geminicli_setup_error_message(load_data)
            if detail:
                raise ValueError(f"Gemini CLI account is not ready: {detail}")
            raise ValueError(
                "Gemini CLI account needs a Google Cloud project or managed project bootstrap, but none was returned."
            )
        if cache_key:
            _GEMINICLI_PROJECT_CACHE[cache_key] = resolved_project
        return resolved_project

    tier = _select_geminicli_onboard_tier(load_data)
    tier_id = str(tier.get("id", "") or "").strip() or "standard-tier"
    onboard_project = env_project or None
    onboard_metadata = _geminicli_core_client_metadata(env_project)
    if tier_id == "free-tier":
        onboard_project = None
        onboard_metadata = _geminicli_core_client_metadata("")

    onboard_request = {
        "tierId": tier_id,
        "metadata": onboard_metadata,
    }
    if onboard_project:
        onboard_request["cloudaicompanionProject"] = onboard_project

    onboard_response = requests.post(
        _resolve_geminicli_internal_url(base_url, GEMINICLI_DEFAULT_ONBOARD_ENDPOINT),
        headers=headers,
        json=onboard_request,
        timeout=timeout,
    )
    onboard_response.raise_for_status()
    operation = onboard_response.json() if onboard_response.content else {}

    operation_name = str(operation.get("name", "") or "").strip()
    for _ in range(GEMINICLI_OPERATION_POLL_ATTEMPTS):
        if operation.get("done") is True:
            break
        if not operation_name:
            break
        time.sleep(GEMINICLI_OPERATION_POLL_SECONDS)
        operation_response = requests.get(
            _resolve_geminicli_operation_url(base_url, operation_name),
            headers=headers,
            timeout=timeout,
        )
        operation_response.raise_for_status()
        operation = operation_response.json() if operation_response.content else {}

    response_payload = operation.get("response")
    if isinstance(response_payload, dict):
        project_meta = response_payload.get("cloudaicompanionProject")
        if isinstance(project_meta, dict):
            resolved_project = str(project_meta.get("id", "") or "").strip()
            if resolved_project:
                if cache_key:
                    _GEMINICLI_PROJECT_CACHE[cache_key] = resolved_project
                return resolved_project

    if env_project:
        if cache_key:
            _GEMINICLI_PROJECT_CACHE[cache_key] = env_project
        return env_project

    detail = _geminicli_setup_error_message(load_data)
    if detail:
        raise ValueError(f"Gemini CLI account is not ready: {detail}")
    raise ValueError("Gemini CLI onboarding did not return a managed project id.")


def get_geminicli_request_headers(
    model_id: str,
    access_token: str,
    stream: bool,
    extra_headers: Optional[Dict[str, str]] = None,
) -> Dict[str, str]:
    """Build Gemini CLI upstream headers."""
    platform = "win32" if os.name == "nt" else os.name
    machine = os.environ.get("PROCESSOR_ARCHITECTURE", "").lower() or os.environ.get("PROCESSOR_ARCHITEW6432", "").lower()
    if machine in ("amd64", "x86_64"):
        arch = "x64"
    elif machine in ("x86", "i386", "i686"):
        arch = "x86"
    else:
        arch = machine or "x64"

    model_name = str(model_id or "unknown").strip() or "unknown"
    headers = {
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/json",
        "User-Agent": f"GeminiCLI/{GEMINICLI_VERSION}/{model_name} ({platform}; {arch})",
        "X-Goog-Api-Client": GEMINICLI_API_CLIENT_HEADER,
        "Accept": "text/event-stream" if stream else "application/json",
    }
    if isinstance(extra_headers, dict):
        for key, value in extra_headers.items():
            k = str(key or "").strip()
            v = str(value or "").strip()
            if k and v:
                headers[k] = v
    return headers


def build_geminicli_runtime_model_data(geminicli_config: Any) -> Optional[Dict[str, Any]]:
    """Build runtime model config dict for Gemini CLI."""
    cfg = normalize_geminicli_config(geminicli_config)
    selected = resolve_geminicli_selected_model(cfg)
    if not selected:
        return None

    cred = detect_geminicli_cli_credentials(refresh_if_needed=True)
    api_key = cred["api_key"] if cred.get("found") else ""

    return {
        "model": selected["id"],
        "model_display_name": selected["display_name"],
        "base_url": cfg["api_url"],
        "api_key": api_key,
        "max_context_tokens": selected.get("context_length", cfg.get("max_context_tokens", 1_048_576)),
        "provider": "gemini-cli",
        "thinking_mode": None,
        "endpoint": cfg.get("endpoint", ""),
    }


def _build_geminicli_user_prompt_id(user_prompt_id: str = "", session_id: str = "") -> str:
    prompt_value = str(user_prompt_id or "").strip()
    if prompt_value:
        return prompt_value

    session_value = str(session_id or "").strip().replace(" ", "-")
    if not session_value:
        session_value = "default"
    return f"reverie-{session_value}-{uuid.uuid4().hex[:12]}"


def _ensure_geminicli_active_loop_thought_signatures(contents: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Mirror Gemini CLI's active-loop signature requirement for tool turns."""
    active_loop_start_index = -1
    for i in range(len(contents) - 1, -1, -1):
        content = contents[i]
        if not isinstance(content, dict):
            continue
        if str(content.get("role", "")).strip().lower() != "user":
            continue
        parts = content.get("parts")
        if not isinstance(parts, list):
            continue
        if any(isinstance(part, dict) and str(part.get("text", "") or "").strip() for part in parts):
            active_loop_start_index = i
            break

    if active_loop_start_index < 0:
        return contents

    updated = list(contents)
    for i in range(active_loop_start_index, len(updated)):
        content = updated[i]
        if not isinstance(content, dict):
            continue
        if str(content.get("role", "")).strip().lower() != "model":
            continue
        parts = content.get("parts")
        if not isinstance(parts, list):
            continue
        new_parts = list(parts)
        changed = False
        for j, part in enumerate(new_parts):
            if not isinstance(part, dict):
                continue
            if not isinstance(part.get("functionCall"), dict):
                continue
            if str(part.get("thoughtSignature", "") or "").strip():
                break
            replacement = dict(part)
            replacement["thoughtSignature"] = "AQ=="
            new_parts[j] = replacement
            changed = True
            break
        if changed:
            replacement_content = dict(content)
            replacement_content["parts"] = new_parts
            updated[i] = replacement_content
    return updated


def build_geminicli_request_payload(
    model_name: str,
    messages: List[Dict[str, Any]],
    tools: Optional[List[Dict[str, Any]]] = None,
    project_id: str = "",
    reasoning_effort: Optional[str] = None,
    session_id: str = "",
    user_prompt_id: str = "",
) -> Dict[str, Any]:
    """Translate OpenAI-style messages/tools into Gemini CLI request payload."""
    payload: Dict[str, Any] = {
        "model": model_name,
        "request": {
            "contents": [],
            "safetySettings": list(_GEMINICLI_DEFAULT_SAFETY_SETTINGS),
        },
    }
    payload["user_prompt_id"] = _build_geminicli_user_prompt_id(
        user_prompt_id=user_prompt_id,
        session_id=session_id,
    )
    project_value = str(project_id or "").strip()
    if project_value:
        payload["project"] = project_value
    session_value = str(session_id or "").strip()
    if session_value:
        payload["request"]["session_id"] = session_value

    if reasoning_effort:
        effort = str(reasoning_effort).strip().lower()
        if effort:
            thinking_cfg: Dict[str, Any] = {"includeThoughts": effort != "none"}
            if effort == "auto":
                thinking_cfg["thinkingBudget"] = -1
            else:
                thinking_cfg["thinkingLevel"] = effort
            payload["request"].setdefault("generationConfig", {})["thinkingConfig"] = thinking_cfg

    tool_call_meta_by_id: Dict[str, Dict[str, str]] = {}
    tool_responses: Dict[str, str] = {}
    for message in messages:
        if str(message.get("role", "")).strip().lower() == "assistant":
            for tool_call in message.get("tool_calls", []) or []:
                if str(tool_call.get("type", "")).strip().lower() != "function":
                    continue
                tool_call_id = str(tool_call.get("id", "")).strip()
                name = str(((tool_call.get("function") or {}).get("name", ""))).strip()
                thought_signature = str(
                    tool_call.get("thought_signature")
                    or tool_call.get("gemini_thought_signature")
                    or ""
                ).strip()
                if tool_call_id and name:
                    tool_call_meta_by_id[tool_call_id] = {
                        "name": name,
                        "thought_signature": thought_signature,
                    }
        elif str(message.get("role", "")).strip().lower() == "tool":
            tool_call_id = str(message.get("tool_call_id", "")).strip()
            content = str(message.get("content", "") or "")
            if tool_call_id:
                tool_responses[tool_call_id] = content or "{}"

    for message in messages:
        role = str(message.get("role", "")).strip().lower()
        content = message.get("content", "")
        if role in ("system", "developer"):
            if len(messages) > 1:
                system_instruction = payload["request"].setdefault("systemInstruction", {"role": "user", "parts": []})
                if str(content or "").strip():
                    system_instruction["parts"].append({"text": str(content)})
                continue
            role = "user"

        if role == "tool":
            continue

        if role == "assistant":
            node = {"role": "model", "parts": []}
            if str(content or "").strip():
                node["parts"].append({"text": str(content)})

            assistant_tool_calls = message.get("tool_calls", []) or []
            if assistant_tool_calls:
                for tool_call in assistant_tool_calls:
                    if str(tool_call.get("type", "")).strip().lower() != "function":
                        continue
                    function_data = tool_call.get("function") or {}
                    name = str(function_data.get("name", "")).strip()
                    args_raw = str(function_data.get("arguments", "") or "").strip() or "{}"
                    tool_call_id = str(tool_call.get("id", "")).strip()
                    try:
                        args_obj = json.loads(args_raw)
                    except Exception:
                        args_obj = args_raw
                    part: Dict[str, Any] = {
                        "functionCall": {
                            "name": name,
                            "args": args_obj,
                        }
                    }
                    if tool_call_id:
                        part["functionCall"]["id"] = tool_call_id
                    thought_signature = str(
                        tool_call.get("thought_signature")
                        or tool_call.get("gemini_thought_signature")
                        or ""
                    ).strip()
                    if thought_signature:
                        part["thoughtSignature"] = thought_signature
                    node["parts"].append(part)
                payload["request"]["contents"].append(node)

                response_node = {"role": "user", "parts": []}
                for tool_call in assistant_tool_calls:
                    tool_call_id = str(tool_call.get("id", "")).strip()
                    tool_meta = tool_call_meta_by_id.get(tool_call_id, {})
                    name = str(tool_meta.get("name", "")).strip()
                    if not tool_call_id or not name:
                        continue
                    raw_result = tool_responses.get(tool_call_id, "{}")
                    try:
                        parsed_result = json.loads(raw_result)
                    except Exception:
                        parsed_result = raw_result
                    response_part: Dict[str, Any] = {
                        "functionResponse": {
                            "name": name,
                            "response": {
                                "result": parsed_result,
                            },
                        }
                    }
                    if tool_call_id:
                        response_part["functionResponse"]["id"] = tool_call_id
                    thought_signature = str(tool_meta.get("thought_signature", "")).strip()
                    if thought_signature:
                        response_part["thoughtSignature"] = thought_signature
                    response_node["parts"].append(response_part)
                if response_node["parts"]:
                    payload["request"]["contents"].append(response_node)
                continue

            payload["request"]["contents"].append(node)
            continue

        if role == "user":
            node = {"role": "user", "parts": []}
            if str(content or "").strip():
                node["parts"].append({"text": str(content)})
            payload["request"]["contents"].append(node)

    if tools:
        function_declarations: List[Dict[str, Any]] = []
        for tool in tools:
            if str(tool.get("type", "")).strip().lower() != "function":
                continue
            fn = tool.get("function") or {}
            name = str(fn.get("name", "")).strip()
            if not name:
                continue
            parameters = fn.get("parameters")
            if not isinstance(parameters, dict):
                parameters = {"type": "object", "properties": {}}
            function_declarations.append(
                {
                    "name": name,
                    "description": str(fn.get("description", "")).strip(),
                    "parametersJsonSchema": parameters,
                }
            )
        if function_declarations:
            payload["request"]["tools"] = [{"functionDeclarations": function_declarations}]

    payload["request"]["contents"] = _ensure_geminicli_active_loop_thought_signatures(
        payload["request"]["contents"]
    )
    return payload


def parse_geminicli_sse_event(data_str: str) -> List[Dict[str, Any]]:
    """Parse a single Gemini CLI SSE `data:` payload into generic delta events."""
    try:
        payload = json.loads(data_str)
    except Exception:
        return []

    response = payload.get("response")
    if not isinstance(response, dict):
        return []

    events: List[Dict[str, Any]] = []
    usage = response.get("usageMetadata")
    if isinstance(usage, dict):
        events.append({"type": "usage", "usage": usage})

    candidates = response.get("candidates")
    if not isinstance(candidates, list) or not candidates:
        return events

    candidate = candidates[0] if isinstance(candidates[0], dict) else {}
    content = candidate.get("content")
    parts = content.get("parts") if isinstance(content, dict) else None
    if isinstance(parts, list):
        tool_index = 0
        for part in parts:
            if not isinstance(part, dict):
                continue
            text = str(part.get("text", "") or "")
            if text:
                if part.get("thought") is True:
                    events.append({"type": "reasoning", "text": text})
                else:
                    events.append({"type": "content", "text": text})
            function_call = part.get("functionCall")
            if isinstance(function_call, dict):
                name = str(function_call.get("name", "")).strip()
                thought_signature = str(part.get("thoughtSignature", "") or "").strip()
                function_call_id = str(function_call.get("id", "") or "").strip()
                args_obj = function_call.get("args", {})
                try:
                    arguments = json.dumps(args_obj, ensure_ascii=False, separators=(",", ":"))
                except Exception:
                    arguments = "{}"
                events.append(
                    {
                        "type": "tool_call",
                        "index": tool_index,
                        "id": function_call_id or f"{name}-{tool_index}-{int(time.time() * 1000)}",
                        "name": name,
                        "arguments": arguments,
                        "thought_signature": thought_signature,
                    }
                )
                tool_index += 1

    finish_reason = str(response.get("stop_reason") or candidate.get("finishReason") or "").strip()
    if finish_reason:
        native = finish_reason.lower()
        if any(event.get("type") == "tool_call" for event in events):
            finish_reason = "tool_calls"
        elif native in ("stop", "max_tokens"):
            finish_reason = native
        else:
            finish_reason = "stop"
        events.append({"type": "finish", "reason": finish_reason})

    return events


def mask_secret(secret: str) -> str:
    """Mask secret for safe terminal display."""
    value = str(secret or "").strip()
    if len(value) <= 8:
        return "*" * len(value)
    return f"{value[:4]}...{value[-4:]}"


def is_geminicli_api_url(url: str) -> bool:
    """Whether the URL points to the Gemini CLI API endpoint."""
    value = str(url or "").strip().lower()
    return "cloudcode-pa.googleapis.com" in value


def infer_geminicli_project_id(project_root: Any) -> str:
    """Best-effort project id lookup from local Gemini CLI workspace mapping."""
    projects_path = Path.home() / ".gemini" / "projects.json"
    if not projects_path.exists():
        return ""
    try:
        with open(projects_path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except Exception:
        return ""

    if not isinstance(data, dict):
        return ""
    projects = data.get("projects")
    if not isinstance(projects, dict):
        return ""

    current = str(project_root or "").strip().lower()
    if not current:
        return ""

    matched_value = ""
    matched_length = -1
    for key, value in projects.items():
        workspace = str(key or "").strip().lower()
        if workspace and current.startswith(workspace) and len(workspace) > matched_length:
            matched_value = str(value or "").strip()
            matched_length = len(workspace)
    return matched_value
