"""Keep the last successful API inventory separate from built-in fallbacks."""

from copy import deepcopy
from hashlib import sha256
from typing import Any, Dict, List, Optional

_OPENAI_MODEL_CACHE: Dict[str, Dict[str, Any]] = {}


def model_catalog_key(url: str, api_key: str, *connection_options: str) -> str:
    return sha256("\0".join((url, api_key, *connection_options)).encode("utf-8")).hexdigest()


def remember_model_catalog(config: Any, key: str, models: List[Dict[str, Any]]) -> None:
    if isinstance(config, dict):
        config["model_catalog"] = {"connection_key": key, "models": deepcopy(models)}


def remembered_model_catalog(
    config: Any, key: str, cache: Optional[Dict[str, Any]] = None,
) -> Optional[List[Dict[str, Any]]]:
    """None means no successful inventory; an empty inventory is authoritative."""
    for snapshot in (cache, config.get("model_catalog") if isinstance(config, dict) else None):
        if not isinstance(snapshot, dict):
            continue
        if snapshot.get("connection_key", snapshot.get("key")) == key and isinstance(snapshot.get("models"), list):
            return deepcopy(snapshot["models"])
    return None


def openai_source_catalog(config: Any, base_url: str, api_key: str,
                         builtin: List[Dict[str, Any]], *, fetch_live: bool = False) -> List[Dict[str, Any]]:
    """Use the shared /models reader for built-in OpenAI-compatible sources."""
    from .diagnostics import report_suppressed_exception

    url = base_url.rstrip("/") + "/models"
    key = model_catalog_key(url, api_key)
    if fetch_live and api_key:
        try:
            return fetch_openai_source_catalog(config, base_url, api_key, builtin)
        except Exception:
            report_suppressed_exception("fetch built-in provider live model catalog")
    latest = remembered_model_catalog(config, key, _OPENAI_MODEL_CACHE.get(key))
    return latest if latest is not None else deepcopy(builtin)


def fetch_openai_source_catalog(config: Any, base_url: str, api_key: str,
                               builtin: List[Dict[str, Any]], *, timeout: int = 10) -> List[Dict[str, Any]]:
    import requests
    from .custom_providers import _parse_model_list_payload
    from .proxy import requests_proxy_dict

    url = base_url.rstrip("/") + "/models"
    response = requests.get(url, headers={"Authorization": "Bearer " + api_key, "Accept": "application/json"},
                            timeout=timeout, proxies=requests_proxy_dict((config or {}).get("proxy", "")))
    response.raise_for_status()
    payload = response.json()
    parsed = _parse_model_list_payload(payload)
    raw_models = payload if isinstance(payload, list) else next(payload[name] for name in ("data", "models", "results") if isinstance(payload.get(name), list))
    known = {item["id"].lower(): item for item in builtin}
    raw_by_id = {str(item.get("id") or item.get("model") or item.get("name") or "").lower(): item for item in raw_models if isinstance(item, dict)}
    models = []
    for item in parsed:
        raw = raw_by_id.get(item["id"].lower(), {})
        if raw.get("output_modalities") and "text" not in raw["output_modalities"]:
            continue
        model = {**known.get(item["id"].lower(), {}), **{k: v for k, v in item.items() if v is not None}}
        if not any(field in raw for field in ("vision", "input_modalities", "architecture", "capabilities")):
            model["vision"] = bool(known.get(item["id"].lower(), {}).get("vision", item["vision"]))
        for field in ("transport", "endpoint", "thinking_control", "thinking_options"):
            if field in raw:
                model[field] = deepcopy(raw[field])
        if item.get("reasoning") is not None:
            model["thinking"] = bool(item["reasoning"])
            if not model["thinking"]:
                model.update(thinking_control="none", thinking_options=[])
        models.append(model)
    key = model_catalog_key(url, api_key)
    _OPENAI_MODEL_CACHE[key] = {"key": key, "models": deepcopy(models)}
    remember_model_catalog(config, key, models)
    return models
