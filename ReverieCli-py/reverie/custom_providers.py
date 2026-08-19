"""User-defined ("custom") provider sources.

A custom provider is described by exactly four user inputs: a base URL, an API
key, an API request format, and a display name.  Everything else -- the model
catalog, context windows, and vision support -- is discovered from the
provider's own ``/models`` endpoint so the same record works for any
OpenAI-compatible or Anthropic-compatible gateway.

Unlike the built-in sources, custom providers are stored as a list under a
single ``custom_providers`` config section and share one ``active_model_source``
value (``"custom"``).  The active provider is named by
``custom_providers.active_provider_id``, which keeps ``active_model_source`` a
closed enum while still allowing any number of user providers.
"""

from __future__ import annotations

import os
import re
import time
from dataclasses import asdict, dataclass, field
from hashlib import sha256
from typing import Any, Dict, List, Optional, Tuple

import requests

from .diagnostics import report_suppressed_exception
from .request_identity import apply_reverie_client_identity


CUSTOM_PROVIDER_SOURCE = "custom"
CUSTOM_PROVIDER_DEFAULT_CONTEXT_TOKENS = 128_000
CUSTOM_PROVIDER_DEFAULT_MAX_TOKENS = 16_384
CUSTOM_PROVIDER_DEFAULT_TIMEOUT = 60
CUSTOM_PROVIDER_MODEL_CACHE_TTL_SECONDS = 300
CUSTOM_PROVIDER_ANTHROPIC_VERSION = "2023-06-01"
CUSTOM_PROVIDER_MAX_PROVIDERS = 64

# A gateway rarely publishes a trustworthy context window, so the limit is asked
# once per model and then reused.  These bounds only reject values that could
# not describe a real window.
CUSTOM_PROVIDER_MIN_CONTEXT_TOKENS = 1_000
CUSTOM_PROVIDER_MAX_CONTEXT_TOKENS = 10_000_000

# Every ``/provider <id> <action>`` pair offered as a completion once a provider
# is stored, so the command surface grows with the user's own providers.
CUSTOM_PROVIDER_COMMAND_ACTIONS: Tuple[Tuple[str, str], ...] = (
    ("", "Show this provider in detail"),
    ("models", "Refresh the catalog and pick a model"),
    ("test", "Verify with one real minimal request"),
    ("use", "Make this provider the active model source"),
    ("context", "Set the context limit for the selected model"),
    ("thinking", "Turn thinking mode on or off"),
    ("key", "Replace the stored API key"),
    ("url", "Change the base URL"),
    ("format", "Change the API request format"),
    ("rename", "Rename this provider"),
    ("enable", "Keep this provider stored and usable"),
    ("disable", "Keep this provider stored but skip it"),
    ("remove", "Delete this provider"),
)

# Request formats a custom provider may speak.  Each one maps onto a transport
# the agent already implements, so no new request path is introduced here.
CUSTOM_PROVIDER_FORMATS: Tuple[str, ...] = (
    "openai-chat",
    "openai-responses",
    "anthropic",
)

_FORMAT_SPECS: Dict[str, Dict[str, str]] = {
    "openai-chat": {
        "label": "OpenAI Chat Completions",
        "description": "POST /chat/completions - the format used by OpenAI and most relay gateways.",
        "transport": "openai-chat",
        "chat_path": "/chat/completions",
        "models_path": "/models",
        "auth": "bearer",
    },
    "openai-responses": {
        "label": "OpenAI Responses",
        "description": "POST /responses - OpenAI's newer stateful Responses API.",
        "transport": "openai-responses",
        "chat_path": "/responses",
        "models_path": "/models",
        "auth": "bearer",
    },
    "anthropic": {
        "label": "Anthropic Messages",
        "description": "POST /messages with x-api-key - the format used by Anthropic and compatible relays.",
        "transport": "anthropic",
        "chat_path": "/messages",
        "models_path": "/models",
        "auth": "x-api-key",
    },
}

# Suffixes users routinely paste from provider docs.  They are trimmed so the
# stored base URL stays a root the model and chat paths can both hang off.
_TRIMMED_BASE_URL_SUFFIXES: Tuple[str, ...] = (
    "/chat/completions",
    "/completions",
    "/responses",
    "/messages",
    "/models",
)

_FORMAT_ALIASES: Dict[str, str] = {
    "openai": "openai-chat",
    "openai-sdk": "openai-chat",
    "openai-compatible": "openai-chat",
    "chat": "openai-chat",
    "chat-completions": "openai-chat",
    "chat.completions": "openai-chat",
    "completions": "openai-chat",
    "responses": "openai-responses",
    "openai-response": "openai-responses",
    "openai-res": "openai-responses",
    "claude": "anthropic",
    "messages": "anthropic",
    "anthropic-messages": "anthropic",
}

# Model payloads rarely declare modality, so an explicit signal is preferred and
# these name fragments are only a last resort.
_VISION_NAME_HINTS: Tuple[str, ...] = (
    "vision", "-vl", "vl-", "omni", "gpt-4o", "gpt-4.1", "gpt-5",
    "claude-3", "claude-4", "claude-5", "claude-opus", "claude-sonnet", "claude-haiku",
    "gemini", "llava", "qwen-vl", "internvl", "pixtral",
)

_MODEL_CACHE: Dict[str, Dict[str, Any]] = {}


def custom_provider_format_choices() -> List[Dict[str, str]]:
    """Return the selectable API request formats with user-facing copy."""
    return [
        {
            "id": name,
            "label": _FORMAT_SPECS[name]["label"],
            "description": _FORMAT_SPECS[name]["description"],
        }
        for name in CUSTOM_PROVIDER_FORMATS
    ]


def normalize_custom_provider_format(value: Any, default: str = "openai-chat") -> str:
    """Normalize a persisted or typed request-format name."""
    candidate = str(value or "").strip().lower().replace("_", "-")
    candidate = _FORMAT_ALIASES.get(candidate, candidate)
    if candidate in CUSTOM_PROVIDER_FORMATS:
        return candidate
    return default


def custom_provider_format_label(value: Any) -> str:
    """Return the user-facing label for a request format."""
    return _FORMAT_SPECS[normalize_custom_provider_format(value)]["label"]


def custom_provider_transport(value: Any) -> str:
    """Return the agent transport (``ModelConfig.provider``) for a format."""
    return _FORMAT_SPECS[normalize_custom_provider_format(value)]["transport"]


def slugify_provider_name(name: Any) -> str:
    """Derive a stable command-safe id from a provider display name."""
    text = str(name or "").strip().lower()
    slug = re.sub(r"[^a-z0-9]+", "-", text).strip("-")
    return slug[:48]


def resolve_custom_provider_base_url(base_url: Any) -> str:
    """Normalize a user-supplied base URL without guessing a version prefix.

    A custom gateway may or may not use ``/v1``, so whatever the user typed is
    preserved; only a scheme is added and well-known request paths are trimmed.
    """
    base = str(base_url or "").strip()
    if not base:
        return ""
    if not base.startswith(("http://", "https://")):
        base = f"https://{base}"
    base = base.rstrip("/")
    changed = True
    while changed:
        changed = False
        lowered = base.lower()
        for suffix in _TRIMMED_BASE_URL_SUFFIXES:
            if lowered.endswith(suffix):
                base = base[: -len(suffix)].rstrip("/")
                changed = True
                break
    return base


def custom_provider_models_url(provider: Any) -> str:
    """Return the model-list URL for one provider record."""
    record = normalize_custom_provider(provider)
    if not record:
        return ""
    base = str(record.get("base_url") or "")
    if not base:
        return ""
    spec = _FORMAT_SPECS[normalize_custom_provider_format(record.get("format"))]
    return f"{base}{spec['models_path']}"


def custom_provider_chat_url(provider: Any) -> str:
    """Return the chat/completion URL for one provider record."""
    record = normalize_custom_provider(provider)
    if not record:
        return ""
    base = str(record.get("base_url") or "")
    if not base:
        return ""
    spec = _FORMAT_SPECS[normalize_custom_provider_format(record.get("format"))]
    return f"{base}{spec['chat_path']}"


def resolve_custom_provider_api_key(provider: Any) -> str:
    """Resolve the effective API key, falling back to a per-provider env var."""
    record = provider if isinstance(provider, dict) else {}
    key = str(record.get("api_key", "") or "").strip()
    if key:
        return key
    env_name = str(record.get("api_key_env", "") or "").strip()
    if env_name:
        value = str(os.getenv(env_name, "") or "").strip()
        if value:
            return value
    provider_id = str(record.get("id", "") or "").strip()
    if provider_id:
        derived = "REVERIE_" + re.sub(r"[^A-Z0-9]+", "_", provider_id.upper()).strip("_") + "_API_KEY"
        value = str(os.getenv(derived, "") or "").strip()
        if value:
            return value
    return ""


def custom_provider_auth_headers(provider: Any) -> Dict[str, str]:
    """Return authentication and content headers for one provider record."""
    record = normalize_custom_provider(provider) or {}
    api_key = resolve_custom_provider_api_key(record)
    fmt = normalize_custom_provider_format(record.get("format"))
    headers: Dict[str, str] = {"Accept": "application/json"}
    if _FORMAT_SPECS[fmt]["auth"] == "x-api-key":
        if api_key:
            headers["x-api-key"] = api_key
        headers["anthropic-version"] = CUSTOM_PROVIDER_ANTHROPIC_VERSION
    elif api_key:
        headers["Authorization"] = f"Bearer {api_key}"
    for key, value in (record.get("custom_headers") or {}).items():
        name = str(key or "").strip()
        text = str(value or "").strip()
        if name and text:
            headers[name] = text
    return apply_reverie_client_identity(headers)


def default_custom_provider(
    *,
    provider_id: str = "",
    name: str = "",
    base_url: str = "",
    api_key: str = "",
    provider_format: str = "openai-chat",
) -> Dict[str, Any]:
    """Build a provider record from the four user-supplied inputs."""
    display_name = str(name or "").strip()
    resolved_id = slugify_provider_name(provider_id or display_name)
    return {
        "id": resolved_id,
        "name": display_name or resolved_id,
        "base_url": resolve_custom_provider_base_url(base_url),
        "api_key": str(api_key or "").strip(),
        "api_key_env": "",
        "format": normalize_custom_provider_format(provider_format),
        "enabled": True,
        "selected_model_id": "",
        "selected_model_display_name": "",
        "max_context_tokens": CUSTOM_PROVIDER_DEFAULT_CONTEXT_TOKENS,
        "max_tokens": CUSTOM_PROVIDER_DEFAULT_MAX_TOKENS,
        "timeout": CUSTOM_PROVIDER_DEFAULT_TIMEOUT,
        "supports_vision": False,
        "thinking": True,
        "model_context_limits": {},
        "custom_headers": {},
        "models": [],
        "models_synced_at": 0.0,
    }


def default_custom_providers_config() -> Dict[str, Any]:
    """Default ``custom_providers`` section stored in config.json."""
    return {"active_provider_id": "", "providers": []}


def _normalize_int(value: Any, default: int, *, minimum: int = 1) -> int:
    try:
        number = int(value)
    except (TypeError, ValueError):
        return default
    if number < minimum:
        return default
    return number


def _coerce_bool(value: Any, default: bool) -> bool:
    """Read a persisted or typed on/off value without treating text as truthy."""
    if isinstance(value, bool):
        return value
    if value is None:
        return default
    if isinstance(value, (int, float)):
        return bool(value)
    text = str(value).strip().lower()
    if text in ("true", "yes", "on", "1", "enable", "enabled"):
        return True
    if text in ("false", "no", "off", "0", "disable", "disabled", "none"):
        return False
    return default


def parse_context_token_limit(value: Any) -> Optional[int]:
    """Parse a typed context limit such as ``128000``, ``128k``, or ``1.2m``.

    Returns ``None`` for anything that cannot describe a real context window so
    the caller can ask again instead of storing a nonsense limit.
    """
    if isinstance(value, bool):
        return None
    text = str(value if value is not None else "").strip().lower()
    if not text:
        return None
    text = text.replace(",", "").replace("_", "").replace(" ", "")
    for suffix in ("tokens", "token", "tok"):
        if text.endswith(suffix):
            text = text[: -len(suffix)].strip()
            break
    multiplier = 1
    if text.endswith("k"):
        multiplier, text = 1_000, text[:-1]
    elif text.endswith("m"):
        multiplier, text = 1_000_000, text[:-1]
    try:
        number = int(float(text) * multiplier)
    except (TypeError, ValueError):
        return None
    if number < CUSTOM_PROVIDER_MIN_CONTEXT_TOKENS:
        return None
    return min(number, CUSTOM_PROVIDER_MAX_CONTEXT_TOKENS)


def _model_limit_key(model_id: Any) -> str:
    """Return the map key used for one model's stored context limit."""
    return str(model_id or "").strip().lower()


def get_custom_provider_model_context_limit(provider: Any, model_id: Any = None) -> Optional[int]:
    """Return the context limit the user saved for one model, if any."""
    record = normalize_custom_provider(provider)
    if not record:
        return None
    key = _model_limit_key(model_id or record.get("selected_model_id"))
    if not key:
        return None
    limit = record.get("model_context_limits", {}).get(key)
    return int(limit) if limit else None


def custom_provider_model_needs_context_limit(provider: Any, model_id: Any) -> bool:
    """Report whether this model is being selected for the first time.

    The limit is only ever asked once per provider and model; every later
    selection reuses the stored value.
    """
    return get_custom_provider_model_context_limit(provider, model_id) is None


def suggest_custom_provider_model_context_limit(provider: Any, model_id: Any) -> int:
    """Return the best default to offer when asking for a model's limit."""
    saved = get_custom_provider_model_context_limit(provider, model_id)
    if saved:
        return saved
    record = normalize_custom_provider(provider) or {}
    key = _model_limit_key(model_id)
    for item in record.get("models") or []:
        if _model_limit_key(item.get("id")) == key:
            published = parse_context_token_limit(item.get("context_length"))
            if published:
                return published
            break
    return CUSTOM_PROVIDER_DEFAULT_CONTEXT_TOKENS


def set_custom_provider_model_context_limit(
    provider: Any, model_id: Any, limit: Any
) -> Dict[str, Any]:
    """Store one model's context limit on a provider record.

    Returns a normalized copy of the record; an unparseable limit leaves the
    stored map untouched so a bad answer cannot erase a good one.
    """
    record = normalize_custom_provider(provider)
    if not record:
        return {}
    key = _model_limit_key(model_id)
    parsed = parse_context_token_limit(limit)
    if not key or not parsed:
        return record
    limits = dict(record.get("model_context_limits") or {})
    limits[key] = parsed
    record["model_context_limits"] = limits
    return normalize_custom_provider(record) or record


def build_custom_provider_command_completions(raw_config: Any) -> Dict[str, str]:
    """Return ``/provider <id> <action>`` completions for every stored provider.

    The generated entries are what makes a user's own provider feel like a
    first-class command: once ``xkiro`` exists, ``/provider xkiro model`` and the
    rest of its actions complete like any built-in command.
    """
    completions: Dict[str, str] = {}
    for record in list_custom_providers(raw_config):
        provider_id = str(record.get("id") or "").strip()
        if not provider_id:
            continue
        label = str(record.get("name") or provider_id).strip() or provider_id
        for action, description in CUSTOM_PROVIDER_COMMAND_ACTIONS:
            command = f"/provider {provider_id}{' ' + action if action else ''}"
            completions[command] = f"{label}: {description}"
    return completions


def normalize_custom_provider_model(raw_model: Any) -> Optional[Dict[str, Any]]:
    """Normalize one catalog entry so it renders in the shared model selector."""
    if not isinstance(raw_model, dict):
        return None
    model_id = str(raw_model.get("id") or raw_model.get("model") or raw_model.get("name") or "").strip()
    if not model_id:
        return None
    display_name = str(
        raw_model.get("display_name") or raw_model.get("name") or model_id
    ).strip() or model_id
    context_length = _normalize_int(
        raw_model.get("context_length")
        or raw_model.get("context_window")
        or raw_model.get("max_context_tokens")
        or raw_model.get("max_input_tokens")
        or 0,
        0,
        minimum=1,
    )
    max_output_tokens = _normalize_int(
        raw_model.get("max_output_tokens") or raw_model.get("max_tokens") or 0,
        0,
        minimum=1,
    )
    return {
        "id": model_id,
        "display_name": display_name,
        "description": str(raw_model.get("description") or "").strip(),
        "context_length": context_length or None,
        "max_output_tokens": max_output_tokens or None,
        "vision": bool(raw_model.get("vision", False)),
        "tool_calling": bool(raw_model.get("tool_calling", True)),
        "owned_by": str(raw_model.get("owned_by") or "").strip(),
        "catalog_source": str(raw_model.get("catalog_source") or "api").strip() or "api",
    }


def normalize_custom_provider(raw_provider: Any) -> Optional[Dict[str, Any]]:
    """Normalize one provider record, or return None when it is unusable."""
    if not isinstance(raw_provider, dict):
        return None

    display_name = str(raw_provider.get("name") or "").strip()
    provider_id = slugify_provider_name(raw_provider.get("id") or display_name)
    if not provider_id:
        return None

    cfg = default_custom_provider(
        provider_id=provider_id,
        name=display_name or provider_id,
        base_url=raw_provider.get("base_url"),
        api_key=raw_provider.get("api_key"),
        provider_format=raw_provider.get("format") or raw_provider.get("provider"),
    )

    cfg["api_key_env"] = str(raw_provider.get("api_key_env", "") or "").strip()
    cfg["enabled"] = bool(raw_provider.get("enabled", True))
    cfg["supports_vision"] = bool(raw_provider.get("supports_vision", False))
    # Thinking is on by default: a custom gateway is usually pointed at a
    # reasoning model, and the user can still turn it off per provider.
    cfg["thinking"] = _coerce_bool(raw_provider.get("thinking", True), True)
    cfg["max_context_tokens"] = _normalize_int(
        raw_provider.get("max_context_tokens"), CUSTOM_PROVIDER_DEFAULT_CONTEXT_TOKENS
    )
    cfg["max_tokens"] = _normalize_int(raw_provider.get("max_tokens"), CUSTOM_PROVIDER_DEFAULT_MAX_TOKENS)
    cfg["timeout"] = _normalize_int(raw_provider.get("timeout"), CUSTOM_PROVIDER_DEFAULT_TIMEOUT, minimum=1)

    context_limits: Dict[str, int] = {}
    raw_limits = raw_provider.get("model_context_limits")
    if isinstance(raw_limits, dict):
        for raw_key, raw_value in raw_limits.items():
            model_key = _model_limit_key(raw_key)
            limit = parse_context_token_limit(raw_value)
            if model_key and limit:
                context_limits[model_key] = limit
    cfg["model_context_limits"] = context_limits

    headers: Dict[str, str] = {}
    raw_headers = raw_provider.get("custom_headers")
    if isinstance(raw_headers, dict):
        for key, value in raw_headers.items():
            name = str(key or "").strip()
            text = str(value or "").strip()
            if name and text:
                headers[name] = text
    cfg["custom_headers"] = headers

    models: List[Dict[str, Any]] = []
    seen_ids = set()
    for item in raw_provider.get("models") or []:
        model = normalize_custom_provider_model(item)
        if not model:
            continue
        key = model["id"].lower()
        if key in seen_ids:
            continue
        seen_ids.add(key)
        models.append(model)
    cfg["models"] = models

    try:
        cfg["models_synced_at"] = max(0.0, float(raw_provider.get("models_synced_at") or 0.0))
    except (TypeError, ValueError):
        cfg["models_synced_at"] = 0.0

    selected_id = str(raw_provider.get("selected_model_id", "") or "").strip()
    selected_name = str(raw_provider.get("selected_model_display_name", "") or "").strip()
    if selected_id:
        cfg["selected_model_id"] = selected_id
        matched = next((item for item in models if item["id"].lower() == selected_id.lower()), None)
        cfg["selected_model_display_name"] = selected_name or (
            matched["display_name"] if matched else selected_id
        )
        # A limit the user typed for this exact model outranks whatever the
        # gateway published, and survives a catalog refresh that drops it.
        saved_limit = context_limits.get(_model_limit_key(selected_id))
        if saved_limit:
            cfg["max_context_tokens"] = saved_limit
        elif matched and matched.get("context_length"):
            cfg["max_context_tokens"] = int(matched["context_length"])
        if matched:
            if matched.get("max_output_tokens"):
                cfg["max_tokens"] = min(cfg["max_tokens"], int(matched["max_output_tokens"]))
            if matched.get("vision"):
                cfg["supports_vision"] = True
    return cfg


def normalize_custom_providers_config(raw_config: Any) -> Dict[str, Any]:
    """Normalize the whole ``custom_providers`` section for persistence."""
    cfg = default_custom_providers_config()
    if not isinstance(raw_config, dict):
        return cfg

    providers: List[Dict[str, Any]] = []
    seen: set = set()
    raw_providers = raw_config.get("providers")
    if isinstance(raw_providers, dict):
        # Tolerate a mapping of id -> record from hand-edited config files.
        raw_providers = [
            {**value, "id": value.get("id") or key}
            for key, value in raw_providers.items()
            if isinstance(value, dict)
        ]
    for item in raw_providers or []:
        record = normalize_custom_provider(item)
        if not record or record["id"] in seen:
            continue
        seen.add(record["id"])
        providers.append(record)
        if len(providers) >= CUSTOM_PROVIDER_MAX_PROVIDERS:
            break
    cfg["providers"] = providers

    active_id = slugify_provider_name(raw_config.get("active_provider_id"))
    if active_id not in seen:
        active_id = ""
    if not active_id:
        # Fall back to the first provider that could actually serve a request.
        for record in providers:
            if record["enabled"] and record["selected_model_id"] and resolve_custom_provider_api_key(record):
                active_id = record["id"]
                break
    cfg["active_provider_id"] = active_id
    return cfg


def list_custom_providers(raw_config: Any) -> List[Dict[str, Any]]:
    """Return every normalized provider record."""
    return list(normalize_custom_providers_config(raw_config)["providers"])


def find_custom_provider(raw_config: Any, provider_ref: Any) -> Optional[Dict[str, Any]]:
    """Resolve a provider by id or display name, allowing a unique prefix."""
    providers = list_custom_providers(raw_config)
    wanted = str(provider_ref or "").strip().lower()
    if not wanted:
        return None
    slug = slugify_provider_name(wanted)
    for record in providers:
        if record["id"] == slug or record["name"].strip().lower() == wanted:
            return record
    partial = [
        record
        for record in providers
        if slug and (record["id"].startswith(slug) or slug in record["name"].strip().lower())
    ]
    return partial[0] if len(partial) == 1 else None


def resolve_active_custom_provider(raw_config: Any) -> Optional[Dict[str, Any]]:
    """Return the provider record backing the ``custom`` model source."""
    cfg = normalize_custom_providers_config(raw_config)
    active_id = cfg["active_provider_id"]
    if not active_id:
        return None
    return next((record for record in cfg["providers"] if record["id"] == active_id), None)


def upsert_custom_provider(raw_config: Any, provider: Any, *, activate: bool = False) -> Dict[str, Any]:
    """Insert or replace one provider record and return the updated section."""
    cfg = normalize_custom_providers_config(raw_config)
    record = normalize_custom_provider(provider)
    if not record:
        return cfg
    providers = [item for item in cfg["providers"] if item["id"] != record["id"]]
    providers.append(record)
    cfg["providers"] = providers
    if activate:
        cfg["active_provider_id"] = record["id"]
    return normalize_custom_providers_config(cfg)


def remove_custom_provider(raw_config: Any, provider_ref: Any) -> Tuple[Dict[str, Any], bool]:
    """Delete one provider record, reporting whether anything was removed."""
    cfg = normalize_custom_providers_config(raw_config)
    record = find_custom_provider(cfg, provider_ref)
    if not record:
        return cfg, False
    cfg["providers"] = [item for item in cfg["providers"] if item["id"] != record["id"]]
    if cfg["active_provider_id"] == record["id"]:
        cfg["active_provider_id"] = ""
    return normalize_custom_providers_config(cfg), True


def _infer_vision(model_id: str, raw_model: Dict[str, Any]) -> bool:
    """Prefer an explicit modality signal, then fall back to a name hint."""
    for key in ("input_modalities", "modalities", "supported_input_modalities"):
        values = raw_model.get(key)
        if isinstance(values, (list, tuple)) and values:
            return any(str(item).strip().lower() in {"image", "vision"} for item in values)
    architecture = raw_model.get("architecture")
    if isinstance(architecture, dict):
        values = architecture.get("input_modalities")
        if isinstance(values, (list, tuple)) and values:
            return any(str(item).strip().lower() in {"image", "vision"} for item in values)
    if isinstance(raw_model.get("vision"), bool):
        return bool(raw_model["vision"])
    lowered = model_id.lower()
    return any(hint in lowered for hint in _VISION_NAME_HINTS)


def _parse_model_list_payload(payload: Any) -> List[Dict[str, Any]]:
    """Extract catalog entries from an OpenAI- or Anthropic-shaped response."""
    raw_models: Any = []
    if isinstance(payload, dict):
        for key in ("data", "models", "results"):
            value = payload.get(key)
            if isinstance(value, list):
                raw_models = value
                break
    elif isinstance(payload, list):
        raw_models = payload

    models: List[Dict[str, Any]] = []
    seen: set = set()
    for item in raw_models:
        if isinstance(item, str):
            item = {"id": item}
        model = normalize_custom_provider_model(item)
        if not model:
            continue
        key = model["id"].lower()
        if key in seen:
            continue
        seen.add(key)
        model["vision"] = _infer_vision(model["id"], item if isinstance(item, dict) else {})
        models.append(model)
    models.sort(key=lambda item: item["id"].lower())
    return models


def fetch_custom_provider_models(
    provider: Any,
    *,
    timeout: int = 10,
    force_refresh: bool = False,
) -> List[Dict[str, Any]]:
    """Fetch the live model catalog for one provider.

    Raises the underlying ``requests`` or ``ValueError`` failure so callers can
    surface why a refresh did not work.
    """
    record = normalize_custom_provider(provider)
    if not record:
        raise ValueError("Provider record is incomplete.")
    models_url = custom_provider_models_url(record)
    if not models_url:
        raise ValueError("Provider has no base URL configured.")

    api_key = resolve_custom_provider_api_key(record)
    auth_hash = sha256(api_key.encode("utf-8")).hexdigest() if api_key else "anonymous"
    cache_key = f"{models_url}:{record['format']}:{auth_hash}"
    now = time.monotonic()
    cached = _MODEL_CACHE.get(cache_key)
    if not force_refresh and cached and float(cached.get("expires_at") or 0.0) > now:
        return [dict(item) for item in cached.get("models", [])]

    response = requests.get(
        models_url,
        headers=custom_provider_auth_headers(record),
        timeout=max(1, int(timeout or 10)),
    )
    response.raise_for_status()
    models = _parse_model_list_payload(response.json())
    _MODEL_CACHE[cache_key] = {
        "expires_at": now + CUSTOM_PROVIDER_MODEL_CACHE_TTL_SECONDS,
        "models": models,
    }
    return [dict(item) for item in models]


def get_custom_provider_model_catalog(
    provider: Any,
    *,
    fetch_live: bool = False,
    force_refresh: bool = False,
    timeout: int = 10,
) -> List[Dict[str, Any]]:
    """Return the provider catalog, preferring live data and falling back to cache."""
    record = normalize_custom_provider(provider) or {}
    if fetch_live:
        try:
            live_models = fetch_custom_provider_models(
                record, timeout=timeout, force_refresh=force_refresh
            )
            if live_models:
                return live_models
        except Exception:
            report_suppressed_exception("fetch custom provider live model catalog")
    return [dict(item) for item in record.get("models", [])]


def resolve_custom_provider_selected_model(
    provider: Any, model_id: Optional[str] = None
) -> Optional[Dict[str, Any]]:
    """Resolve the selected model record for a provider."""
    record = normalize_custom_provider(provider)
    if not record:
        return None
    wanted = str(model_id or record.get("selected_model_id") or "").strip()
    if not wanted:
        return None
    saved_limit = record.get("model_context_limits", {}).get(_model_limit_key(wanted))
    models = record.get("models") or []
    matched = next((item for item in models if item["id"].lower() == wanted.lower()), None)
    if matched:
        resolved = dict(matched)
        if saved_limit:
            resolved["context_length"] = int(saved_limit)
        return resolved
    # A selection made before a catalog refresh is still callable by id.
    return {
        "id": wanted,
        "display_name": str(record.get("selected_model_display_name") or wanted),
        "description": "",
        "context_length": int(
            saved_limit or record.get("max_context_tokens") or CUSTOM_PROVIDER_DEFAULT_CONTEXT_TOKENS
        ),
        "max_output_tokens": int(record.get("max_tokens") or CUSTOM_PROVIDER_DEFAULT_MAX_TOKENS),
        "vision": bool(record.get("supports_vision", False)),
        "tool_calling": True,
        "owned_by": "",
        "catalog_source": "config",
    }


def build_custom_provider_runtime_model_data(
    custom_providers_config: Any,
    provider_ref: Optional[str] = None,
    model_id: Optional[str] = None,
) -> Optional[Dict[str, Any]]:
    """Build the runtime ``ModelConfig`` payload for the active custom provider."""
    cfg = normalize_custom_providers_config(custom_providers_config)
    record = (
        find_custom_provider(cfg, provider_ref)
        if provider_ref
        else resolve_active_custom_provider(cfg)
    )
    if not record or not record.get("enabled", True):
        return None
    if not record.get("base_url"):
        return None

    api_key = resolve_custom_provider_api_key(record)
    if not api_key:
        return None

    selected = resolve_custom_provider_selected_model(record, model_id=model_id)
    if not selected:
        return None

    context_tokens = int(
        selected.get("context_length")
        or record.get("max_context_tokens")
        or CUSTOM_PROVIDER_DEFAULT_CONTEXT_TOKENS
    )
    supports_vision = bool(selected.get("vision") or record.get("supports_vision", False))
    return {
        "model": selected["id"],
        "model_display_name": selected.get("display_name") or selected["id"],
        "base_url": str(record["base_url"]),
        "api_key": api_key,
        "max_context_tokens": context_tokens,
        "provider": custom_provider_transport(record.get("format")),
        "supports_vision": supports_vision,
        # ``true``/``false`` is the string contract ``ModelConfig.thinking_mode``
        # already uses for OpenAI-compatible transports.
        "thinking_mode": "true" if record.get("thinking", True) else "false",
        "endpoint": "",
        "custom_headers": dict(record.get("custom_headers") or {}),
        "vision": supports_vision,
    }


def build_custom_provider_openai_options(
    custom_providers_config: Any,
    provider_ref: Optional[str] = None,
    model_id: Optional[str] = None,
) -> Dict[str, Any]:
    """Return request options (currently just an output cap) for a custom provider."""
    cfg = normalize_custom_providers_config(custom_providers_config)
    record = (
        find_custom_provider(cfg, provider_ref)
        if provider_ref
        else resolve_active_custom_provider(cfg)
    ) or {}
    selected = resolve_custom_provider_selected_model(record, model_id=model_id) or {}
    max_tokens = _normalize_int(record.get("max_tokens"), CUSTOM_PROVIDER_DEFAULT_MAX_TOKENS)
    output_limit = _normalize_int(selected.get("max_output_tokens"), max_tokens)
    return {"max_tokens": min(max_tokens, output_limit)}


@dataclass
class CustomProviderProbe:
    """One availability check result rendered by ``/provider list`` and ``test``."""

    provider_id: str
    name: str
    status: str = "error"
    latency_ms: int = 0
    model_count: int = 0
    detail: str = ""
    probe: str = "models"
    models: List[Dict[str, Any]] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return self.status == "online"

    def to_dict(self) -> Dict[str, Any]:
        payload = asdict(self)
        payload.pop("models", None)
        return payload


def _redact_detail(text: Any, api_key: str = "") -> str:
    """Strip credentials and collapse a failure message for terminal display."""
    value = " ".join(str(text or "").split())
    secret = str(api_key or "").strip()
    if secret and len(secret) >= 8:
        value = value.replace(secret, "***")
    value = re.sub(r"(sk-[A-Za-z0-9_\-]{6,})", "***", value)
    value = re.sub(r"(Bearer\s+)[A-Za-z0-9._\-]+", r"\1***", value)
    if len(value) > 180:
        value = value[:177] + "..."
    return value


def _probe_status_for_http(status_code: int) -> Tuple[str, str]:
    if status_code in (401, 403):
        return "unauthorized", f"HTTP {status_code} - the API key was rejected."
    if status_code == 404:
        return "error", f"HTTP {status_code} - endpoint not found; check the base URL."
    if status_code == 429:
        return "throttled", f"HTTP {status_code} - rate limited."
    if status_code >= 500:
        return "offline", f"HTTP {status_code} - the provider returned a server error."
    return "error", f"HTTP {status_code}."


def probe_custom_provider(
    provider: Any,
    *,
    timeout: int = 10,
    require_api_key: bool = True,
) -> CustomProviderProbe:
    """Check a provider by listing its models. Never raises.

    ``require_api_key=False`` lets keyless gateways be probed anonymously
    instead of being reported as unconfigured.
    """
    record = normalize_custom_provider(provider) or {}
    result = CustomProviderProbe(
        provider_id=str(record.get("id") or ""),
        name=str(record.get("name") or record.get("id") or "unknown"),
        probe="models",
    )
    if not record.get("base_url"):
        result.status = "unconfigured"
        result.detail = "No base URL configured."
        return result
    api_key = resolve_custom_provider_api_key(record)
    if not api_key and require_api_key:
        result.status = "unconfigured"
        result.detail = "No API key configured."
        return result

    started = time.monotonic()
    try:
        models = fetch_custom_provider_models(record, timeout=timeout, force_refresh=True)
    except requests.HTTPError as exc:
        result.latency_ms = int((time.monotonic() - started) * 1000)
        status_code = int(getattr(getattr(exc, "response", None), "status_code", 0) or 0)
        result.status, result.detail = _probe_status_for_http(status_code)
        body = str(getattr(getattr(exc, "response", None), "text", "") or "")
        if body:
            result.detail = f"{result.detail} {_redact_detail(body, api_key)}".strip()
        return result
    except requests.Timeout:
        result.latency_ms = int((time.monotonic() - started) * 1000)
        result.status = "offline"
        result.detail = f"Timed out after {timeout}s."
        return result
    except requests.RequestException as exc:
        result.latency_ms = int((time.monotonic() - started) * 1000)
        result.status = "offline"
        result.detail = _redact_detail(exc, api_key) or exc.__class__.__name__
        return result
    except Exception as exc:  # malformed JSON, unusable record, ...
        result.latency_ms = int((time.monotonic() - started) * 1000)
        result.status = "error"
        result.detail = _redact_detail(exc, api_key) or exc.__class__.__name__
        return result

    result.latency_ms = int((time.monotonic() - started) * 1000)
    result.model_count = len(models)
    result.models = models
    if models:
        result.status = "online"
        result.detail = f"{len(models)} models available."
    else:
        result.status = "empty"
        result.detail = "Reachable, but the provider returned no models."
    return result


def _chat_probe_request(record: Dict[str, Any], model_id: str) -> Tuple[str, Dict[str, Any]]:
    """Build the smallest valid request body for a provider's format."""
    fmt = normalize_custom_provider_format(record.get("format"))
    url = custom_provider_chat_url(record)
    if fmt == "anthropic":
        return url, {
            "model": model_id,
            "max_tokens": 1,
            "messages": [{"role": "user", "content": "Hi"}],
        }
    if fmt == "openai-responses":
        return url, {"model": model_id, "input": "Hi", "max_output_tokens": 16}
    return url, {
        "model": model_id,
        "max_tokens": 1,
        "messages": [{"role": "user", "content": "Hi"}],
    }


def probe_custom_provider_chat(
    provider: Any,
    *,
    model_id: str = "",
    timeout: int = 30,
    require_api_key: bool = True,
) -> CustomProviderProbe:
    """Verify a provider end to end with one minimal, non-streaming call."""
    record = normalize_custom_provider(provider) or {}
    result = CustomProviderProbe(
        provider_id=str(record.get("id") or ""),
        name=str(record.get("name") or record.get("id") or "unknown"),
        probe="chat",
    )
    wanted_model = str(model_id or record.get("selected_model_id") or "").strip()
    if not record.get("base_url"):
        result.status = "unconfigured"
        result.detail = "No base URL configured."
        return result
    api_key = resolve_custom_provider_api_key(record)
    if not api_key and require_api_key:
        result.status = "unconfigured"
        result.detail = "No API key configured."
        return result
    if not wanted_model:
        result.status = "unconfigured"
        result.detail = "No model selected. Run /provider <name> models first."
        return result

    url, payload = _chat_probe_request(record, wanted_model)
    headers = custom_provider_auth_headers(record)
    headers["Content-Type"] = "application/json"
    started = time.monotonic()
    try:
        response = requests.post(url, headers=headers, json=payload, timeout=max(1, int(timeout or 30)))
        result.latency_ms = int((time.monotonic() - started) * 1000)
        if response.status_code >= 400:
            result.status, result.detail = _probe_status_for_http(response.status_code)
            body = _redact_detail(response.text, api_key)
            if body:
                result.detail = f"{result.detail} {body}".strip()
            return result
        result.status = "online"
        result.detail = f"{wanted_model} answered in {result.latency_ms} ms."
        return result
    except requests.Timeout:
        result.latency_ms = int((time.monotonic() - started) * 1000)
        result.status = "offline"
        result.detail = f"Timed out after {timeout}s."
        return result
    except requests.RequestException as exc:
        result.latency_ms = int((time.monotonic() - started) * 1000)
        result.status = "offline"
        result.detail = _redact_detail(exc, api_key) or exc.__class__.__name__
        return result
    except Exception as exc:
        result.latency_ms = int((time.monotonic() - started) * 1000)
        result.status = "error"
        result.detail = _redact_detail(exc, api_key) or exc.__class__.__name__
        return result


def probe_custom_providers(
    providers: Any,
    *,
    timeout: int = 10,
    max_workers: int = 8,
) -> List[CustomProviderProbe]:
    """Probe many providers concurrently, preserving input order."""
    records = [record for record in (normalize_custom_provider(item) for item in providers or []) if record]
    if not records:
        return []
    if len(records) == 1:
        return [probe_custom_provider(records[0], timeout=timeout)]

    from concurrent.futures import ThreadPoolExecutor

    workers = max(1, min(int(max_workers or 8), len(records)))
    with ThreadPoolExecutor(max_workers=workers) as pool:
        return list(pool.map(lambda record: probe_custom_provider(record, timeout=timeout), records))


def mask_secret(secret: Any) -> str:
    """Mask secrets for safe terminal display."""
    value = str(secret or "").strip()
    if not value:
        return ""
    if len(value) <= 8:
        return "*" * len(value)
    return f"{value[:4]}...{value[-4:]}"
