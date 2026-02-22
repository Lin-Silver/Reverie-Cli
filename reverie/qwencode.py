"""
Qwen Code integration helpers.

This module centralizes:
- Local Qwen CLI credential detection (`~/.qwen`)
- Qwen Code model catalog definitions
- Qwen Code API settings helpers
"""

from pathlib import Path
from typing import Any, Dict, List, Optional
import json


# Default DashScope API URL (fallback if resource_url not found in credentials)
QWENCODE_DEFAULT_API_URL = "https://dashscope.aliyuncs.com/compatible-mode/v1"

_QWENCODE_CREDENTIAL_FILES = (
    ("oauth_creds.json", "access_token"),
    ("qwen_accounts.json", "access_token"),
)

_QWENCODE_BASE_MODELS = [
    {
        "id": "qwen3-coder-plus",
        "display_name": "Qwen3-Coder-Plus",
        "description": "Qwen3 Coder Plus - Advanced code generation and understanding",
        "context_length": 32768,
    },
    {
        "id": "qwen3-coder-flash",
        "display_name": "Qwen3-Coder-Flash",
        "description": "Qwen3 Coder Flash - Fast code generation",
        "context_length": 8192,
    },
    {
        "id": "coder-model",
        "display_name": "Qwen3.5-Plus",
        "description": "Qwen 3.5 Plus - Efficient hybrid model with leading coding performance",
        "context_length": 262144,
    },
    {
        "id": "vision-model",
        "display_name": "Qwen3-Vision",
        "description": "Qwen3 Vision Model - Multimodal vision understanding",
        "context_length": 32768,
    },
]


def default_qwencode_config() -> Dict[str, Any]:
    """Default Qwen Code config stored inside Reverie config.json."""
    return {
        "selected_model_id": "",
        "selected_model_display_name": "",
        "api_url": QWENCODE_DEFAULT_API_URL,
        "max_context_tokens": 200000,
        "timeout": 1200,
    }


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
                "context_length": item.get("context_length", 32768),
            }
        )

    return catalog


def find_qwencode_model(model_id: str, catalog: Optional[List[Dict[str, Any]]] = None) -> Optional[Dict[str, Any]]:
    """Find Qwen Code model by id (case-insensitive)."""
    wanted = str(model_id or "").strip().lower()
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

    cfg["selected_model_id"] = str(cfg.get("selected_model_id", "")).strip()
    cfg["selected_model_display_name"] = str(cfg.get("selected_model_display_name", "")).strip()
    cfg["api_url"] = str(cfg.get("api_url", QWENCODE_DEFAULT_API_URL)).strip() or QWENCODE_DEFAULT_API_URL

    try:
        max_tokens = int(cfg.get("max_context_tokens", 200000))
    except (TypeError, ValueError):
        max_tokens = 200000
    if max_tokens <= 0:
        max_tokens = 200000
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
        cfg["selected_model_display_name"] = matched["display_name"]
    elif cfg["selected_model_id"] and not cfg["selected_model_display_name"]:
        cfg["selected_model_display_name"] = cfg["selected_model_id"]

    return cfg


def resolve_qwencode_selected_model(qwencode_config: Any) -> Optional[Dict[str, Any]]:
    """Resolve selected Qwen Code model metadata from config."""
    cfg = normalize_qwencode_config(qwencode_config)
    model_id = cfg.get("selected_model_id", "")
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
        "context_length": 32768,
    }


def build_qwencode_runtime_model_data(qwencode_config: Any) -> Optional[Dict[str, Any]]:
    """
    Build runtime model config dict for agent initialization.

    This keeps Qwen Code models independent from the `/model` list.
    """
    cfg = normalize_qwencode_config(qwencode_config)
    selected = resolve_qwencode_selected_model(cfg)
    if not selected:
        return None

    cred = detect_qwencode_cli_credentials()
    api_key = cred["api_key"] if cred.get("found") else ""
    
    # Use resource_url from credentials if available, otherwise use config api_url
    # This matches qwen-code behavior: resource_url from OAuth response is the actual API endpoint
    api_url = cred.get("resource_url", cfg["api_url"])
    
    # Ensure the URL has /v1 suffix (matching qwen-code's getCurrentEndpoint logic)
    if api_url and not api_url.endswith("/v1"):
        api_url = api_url.rstrip("/") + "/v1"

    # Use the model's actual context_length as max_context_tokens
    max_context_tokens = selected.get("context_length", cfg["max_context_tokens"])

    return {
        "model": selected["id"],
        "model_display_name": selected["display_name"],
        "base_url": api_url,
        "api_key": api_key,
        "max_context_tokens": max_context_tokens,
        "provider": "openai-sdk",
        "thinking_mode": None,
    }


def detect_qwencode_cli_credentials() -> Dict[str, Any]:
    """
    Detect Qwen Code CLI credentials from local cache.

    Priority:
    1) ~/.qwen/oauth_creds.json -> access_token + resource_url
    2) ~/.qwen/qwen_accounts.json -> access_token
    
    Returns dict with:
    - found: bool
    - api_key: str (access_token)
    - resource_url: str (API endpoint from OAuth, e.g., dashscope.aliyuncs.com)
    - source_file: str
    - source_field: str
    - errors: list
    """
    qwen_dir = Path.home() / ".qwen"
    result = {
        "found": False,
        "api_key": "",
        "resource_url": "",
        "source_file": "",
        "source_field": "",
        "errors": [],
    }

    for filename, field_name in _QWENCODE_CREDENTIAL_FILES:
        path = qwen_dir / filename
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
            
            # Extract resource_url if present (from OAuth credentials)
            resource_url = str(data.get("resource_url", "")).strip()
            if resource_url:
                # Normalize: add https:// if missing
                if not resource_url.startswith("http"):
                    resource_url = f"https://{resource_url}"
                result["resource_url"] = resource_url
            
            return result

    return result


def mask_secret(secret: str) -> str:
    """Mask secret for safe terminal display."""
    value = str(secret or "").strip()
    if len(value) <= 8:
        return "*" * len(value)
    return f"{value[:4]}...{value[-4:]}"


def is_qwencode_api_url(url: str) -> bool:
    """Whether the URL points to Qwen Code API endpoint (DashScope)."""
    value = str(url or "").strip().lower()
    # Check for DashScope endpoints (the actual API used by qwen-code)
    return "dashscope.aliyuncs.com" in value or "portal.qwen.ai" in value


def qwen_oauth_login() -> Dict[str, Any]:
    """
    Perform Qwen OAuth device flow login.
    
    Note: This is a placeholder. The actual OAuth flow should be implemented
    using the qwen-code CLI or a similar OAuth client library.
    
    For now, users should use the qwen-code CLI to authenticate:
        qwen-code auth
    
    Returns:
        Dict with success status and credentials or error message
    """
    return {
        "success": False,
        "error": "OAuth login not yet implemented. Please use 'qwen-code auth' CLI command to authenticate."
    }


def save_qwen_credentials(access_token: str, refresh_token: str, resource_url: str = "") -> bool:
    """
    Save Qwen OAuth credentials to ~/.qwen/oauth_creds.json
    
    Args:
        access_token: OAuth access token
        refresh_token: OAuth refresh token
        resource_url: API endpoint URL (optional)
    
    Returns:
        True if saved successfully, False otherwise
    """
    import time
    
    qwen_dir = Path.home() / ".qwen"
    creds_file = qwen_dir / "oauth_creds.json"
    
    try:
        # Create directory if it doesn't exist
        qwen_dir.mkdir(parents=True, exist_ok=True)
        
        # Prepare credentials data
        creds_data = {
            "access_token": access_token,
            "refresh_token": refresh_token,
            "token_type": "Bearer",
            "expiry_date": int(time.time() * 1000) + (3600 * 1000),  # 1 hour from now
        }
        
        if resource_url:
            creds_data["resource_url"] = resource_url
        
        # Write to file
        with open(creds_file, "w", encoding="utf-8") as f:
            json.dump(creds_data, f, indent=2)
        
        return True
    except Exception as e:
        print(f"Error saving credentials: {e}")
        return False
