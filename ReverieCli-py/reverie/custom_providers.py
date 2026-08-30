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

# Reasoning depth for a custom provider.  The user picks one rung of a shared
# ladder and it is resolved against whatever the model's own catalog entry
# declares, so ``max`` means "as deep as this model admits to going" rather than
# a literal effort string some gateway may never have heard of.
CUSTOM_PROVIDER_REASONING_CHOICES: Tuple[Tuple[str, str], ...] = (
    ("off", "Send no reasoning flags at all"),
    ("minimal", "Shortest reasoning the model offers"),
    ("low", "Short reasoning"),
    ("medium", "Balanced reasoning"),
    ("high", "Long reasoning"),
    ("xhigh", "Longest named reasoning level"),
    ("max", "The deepest level this model publishes"),
)
CUSTOM_PROVIDER_DEFAULT_REASONING_EFFORT = "max"

# Every spelling seen in the wild for a depth, collapsed onto one rank so a
# provider's own level names can be compared with the user's choice.
_REASONING_RANKS: Dict[str, int] = {
    "off": 0, "none": 0, "no": 0, "false": 0, "disable": 0, "disabled": 0, "never": 0, "hidden": 0,
    "minimal": 1, "min": 1, "minimum": 1, "lowest": 1, "brief": 1, "tiny": 1,
    "low": 2, "short": 2, "fast": 2, "quick": 2,
    "medium": 3, "med": 3, "default": 3, "balanced": 3, "normal": 3, "standard": 3, "auto": 3, "mid": 3,
    "high": 4, "long": 4, "deep": 4, "thorough": 4,
    "xhigh": 5, "x_high": 5, "x-high": 5, "extra_high": 5, "extra-high": 5,
    "very_high": 5, "very-high": 5, "veryhigh": 5, "ultra": 5, "deepest": 5, "xtreme": 5,
    "max": 6, "maximum": 6, "highest": 6, "full": 6, "true": 6, "on": 6, "yes": 6, "always": 6,
}
_REASONING_BY_RANK: Tuple[str, ...] = ("off", "minimal", "low", "medium", "high", "xhigh", "max")

# Reasoning request fields, grouped by how safe each group is to keep.  The agent
# drops one group at a time when a gateway rejects the payload, so a provider
# that only understands plain ``reasoning_effort`` still ends up with thinking on
# instead of losing it to a single all-or-nothing strip.
CUSTOM_PROVIDER_REASONING_FIELD_TIERS: Tuple[Tuple[str, ...], ...] = (
    # Chat-template and budget knobs: the most vendor-specific, dropped first.
    ("chat_template_kwargs", "enable_thinking", "clear_thinking", "thinking_budget", "reasoning_format"),
    # Anthropic-shaped block plus the OpenRouter surfacing switch.
    ("thinking", "include_reasoning"),
    # The structured reasoning object, leaving the plain effort field behind.
    ("reasoning",),
    # Last resort before no reasoning at all.
    ("reasoning_effort",),
)
CUSTOM_PROVIDER_REASONING_FIELDS: Tuple[str, ...] = tuple(
    field for tier in CUSTOM_PROVIDER_REASONING_FIELD_TIERS for field in tier
)

# An Anthropic-style thinking budget below this is rejected outright, and a
# budget must leave room for the visible answer inside the same output cap.
CUSTOM_PROVIDER_MIN_THINKING_BUDGET = 1_024
_REASONING_BUDGET_SHARE: Dict[str, float] = {
    "minimal": 0.20,
    "low": 0.35,
    "medium": 0.55,
    "high": 0.70,
    "xhigh": 0.80,
    "max": 0.80,
}

# Every ``/provider <id> <action>`` pair offered as a completion once a provider
# is stored, so the command surface grows with the user's own providers.
CUSTOM_PROVIDER_COMMAND_ACTIONS: Tuple[Tuple[str, str], ...] = (
    ("", "Show this provider in detail"),
    ("models", "Refresh the catalog and pick a model"),
    ("test", "Verify with one real minimal request"),
    ("use", "Make this provider the active model source"),
    ("context", "Set the context limit for the selected model"),
    ("thinking", "Set reasoning depth, or turn thinking off"),
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


def custom_provider_sdk_base_url(provider: Any) -> str:
    """Return the base URL the transport's own SDK expects.

    The Anthropic SDK appends ``/v1/messages`` itself, so a gateway typed in as
    ``https://host/v1`` has to be handed ``https://host`` or the request lands on
    ``/v1/v1/messages``. Every other transport takes the URL as typed, because a
    custom gateway may legitimately have no version prefix at all.
    """
    record = normalize_custom_provider(provider)
    if not record:
        return ""
    base = str(record.get("base_url") or "")
    if not base:
        return ""
    if custom_provider_transport(record.get("format")) != "anthropic":
        return base
    return base[:-3].rstrip("/") if base.lower().endswith("/v1") else base


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
        "reasoning_effort": CUSTOM_PROVIDER_DEFAULT_REASONING_EFFORT,
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


def normalize_custom_provider_reasoning_effort(
    value: Any,
    default: str = CUSTOM_PROVIDER_DEFAULT_REASONING_EFFORT,
) -> str:
    """Collapse any depth spelling onto one rung of Reverie's shared ladder."""
    if isinstance(value, bool):
        return CUSTOM_PROVIDER_DEFAULT_REASONING_EFFORT if value else "off"
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        # A bare number reads as a thinking budget: any positive budget means on.
        return "off" if int(value) <= 0 else CUSTOM_PROVIDER_DEFAULT_REASONING_EFFORT
    text = str(value or "").strip().lower().replace(" ", "_")
    if not text:
        return default
    rank = _REASONING_RANKS.get(text)
    if rank is None:
        if text.isdigit():
            return "off" if int(text) == 0 else CUSTOM_PROVIDER_DEFAULT_REASONING_EFFORT
        return default
    return _REASONING_BY_RANK[rank]


_REASONING_LABELS: Dict[str, str] = {
    "off": "Off",
    "minimal": "Minimal",
    "low": "Low",
    "medium": "Medium",
    "high": "High",
    "xhigh": "X-High",
    "max": "Max",
}


def _reasoning_rank(value: Any, default: int = 0) -> int:
    """Look up a depth rank, tolerating the spellings gateways actually use."""
    key = str(value or "").strip().lower().replace("-", "_").replace(" ", "_")
    return _REASONING_RANKS.get(key, default)


def custom_provider_reasoning_label(level: Any) -> str:
    """Return the user-facing name for one reasoning depth."""
    normalized = normalize_custom_provider_reasoning_effort(level, default="off")
    return _REASONING_LABELS.get(normalized, normalized.title())


def custom_provider_reasoning_choices() -> List[Dict[str, str]]:
    """Return the selectable reasoning depths with user-facing copy."""
    return [
        {"id": level, "label": custom_provider_reasoning_label(level), "description": description}
        for level, description in CUSTOM_PROVIDER_REASONING_CHOICES
    ]


def custom_provider_reasoning_options(model: Any) -> List[Dict[str, str]]:
    """Return the depths worth offering for one catalog entry.

    A model that publishes its own effort names gets exactly those, plus ``off``
    to stop sending reasoning at all and ``max`` to always track the deepest one
    it offers. A catalog that stays silent gets the whole ladder, because
    guessing narrow would hide a level the model may well accept.
    """
    record = model if isinstance(model, dict) else {}
    if record.get("reasoning") is False:
        return []
    declared = [level for level in (record.get("reasoning_levels") or []) if _reasoning_rank(level)]
    if not declared:
        return custom_provider_reasoning_choices()
    allowed = {"off", "max"}
    for level in declared:
        allowed.add(_REASONING_BY_RANK[_reasoning_rank(level)])
    return [item for item in custom_provider_reasoning_choices() if item["id"] in allowed]


def _parse_reasoning_levels(raw_model: Dict[str, Any]) -> List[str]:
    """Read the effort names a catalog entry claims to accept, deepest last.

    Gateways spell this several ways -- xkiro publishes
    ``reasoning_efforts: {"levels": [...], "default": "medium"}`` -- so any list
    of names found under a reasoning key is accepted and sorted by depth.
    """
    candidates: List[Any] = []
    for key in (
        "reasoning_efforts",
        "reasoning_effort",
        "supported_reasoning_efforts",
        "reasoning_levels",
        "thinking_levels",
    ):
        value = raw_model.get(key)
        if isinstance(value, dict):
            for inner in ("levels", "values", "options", "supported", "efforts", "choices"):
                nested = value.get(inner)
                if isinstance(nested, (list, tuple)) and nested:
                    candidates = list(nested)
                    break
        elif isinstance(value, (list, tuple)) and value:
            candidates = list(value)
        if candidates:
            break

    levels: List[str] = []
    seen: set = set()
    for item in candidates:
        text = str(item or "").strip()
        key = text.lower()
        if not text or key in seen:
            continue
        seen.add(key)
        levels.append(text)
    # Keep the provider's own spelling but order it by depth so "the deepest
    # level published" is a well-defined choice even for an unsorted list.
    levels.sort(key=lambda name: _REASONING_RANKS.get(name.strip().lower().replace(" ", "_"), 3))
    return levels


def _parse_reasoning_default(raw_model: Dict[str, Any]) -> str:
    """Read the effort a catalog entry says it falls back to."""
    stored = str(raw_model.get("reasoning_default") or "").strip()
    if stored:
        return stored
    for key in ("reasoning_efforts", "reasoning_effort", "reasoning"):
        value = raw_model.get(key)
        if isinstance(value, dict):
            for inner in ("default", "default_effort", "value", "effort"):
                text = str(value.get(inner) or "").strip()
                if text:
                    return text
        elif isinstance(value, str) and value.strip():
            return value.strip()
    return ""


def _declares_reasoning(raw_model: Dict[str, Any], levels: List[str]) -> Optional[bool]:
    """Whether a catalog entry states that the model reasons, if it says at all."""
    capabilities = raw_model.get("capabilities")
    if isinstance(capabilities, dict):
        for key in ("reasoning", "thinking", "reasoning_content"):
            if isinstance(capabilities.get(key), bool):
                return bool(capabilities[key])
    for key in ("reasoning", "thinking", "supports_reasoning", "supports_thinking"):
        if isinstance(raw_model.get(key), bool):
            return bool(raw_model[key])
    if levels:
        return True
    return None


def _capability_flag(raw_model: Dict[str, Any], *names: str) -> Optional[bool]:
    """Read one boolean capability, preferring a ``capabilities`` block."""
    capabilities = raw_model.get("capabilities")
    if isinstance(capabilities, dict):
        for name in names:
            if isinstance(capabilities.get(name), bool):
                return bool(capabilities[name])
    for name in names:
        if isinstance(raw_model.get(name), bool):
            return bool(raw_model[name])
    return None



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
    reasoning_levels = _parse_reasoning_levels(raw_model)
    declared_reasoning = _declares_reasoning(raw_model, reasoning_levels)
    vision = _capability_flag(raw_model, "vision", "image", "images")
    tool_calling = _capability_flag(raw_model, "tools", "tool_calling", "function_calling")
    return {
        "id": model_id,
        "display_name": display_name,
        "description": str(raw_model.get("description") or "").strip(),
        "context_length": context_length or None,
        "max_output_tokens": max_output_tokens or None,
        "vision": bool(raw_model.get("vision", False)) if vision is None else vision,
        "tool_calling": bool(raw_model.get("tool_calling", True)) if tool_calling is None else tool_calling,
        # ``None`` means the catalog stayed silent, which is not the same as a
        # model that says it cannot reason: silence still gets thinking flags.
        "reasoning": declared_reasoning,
        "reasoning_levels": reasoning_levels,
        "reasoning_default": _parse_reasoning_default(raw_model),
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
    # reasoning model, and the user can still turn it off per provider.  Depth
    # and the on/off flag are two views of the same setting, so whichever one
    # says "no reasoning" wins.
    thinking = _coerce_bool(raw_provider.get("thinking", True), True)
    reasoning_effort = normalize_custom_provider_reasoning_effort(
        raw_provider.get("reasoning_effort")
    )
    if not thinking:
        reasoning_effort = "off"
    elif reasoning_effort == "off":
        thinking = False
    cfg["thinking"] = thinking
    cfg["reasoning_effort"] = reasoning_effort
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
            # The catalog is the authority on the selected model's modalities, so
            # a stale `supports_vision` from a name guess is corrected here
            # rather than only ever being turned on.
            cfg["supports_vision"] = bool(matched.get("vision"))
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
    # A published capability is the last word: `openai/gpt-5.3-codex-spark` says
    # `vision: false`, and the "gpt-5" name hint must not talk it back into
    # accepting images.
    declared = _capability_flag(raw_model, "vision", "image", "images")
    if declared is not None:
        return declared
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
        # Nothing is known about a model that predates the catalog, and silence
        # earns the full reasoning payload rather than none of it.
        "reasoning": None,
        "reasoning_levels": [],
        "reasoning_default": "",
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
    reasoning_level = resolve_custom_provider_reasoning_level(record, selected["id"])
    return {
        "model": selected["id"],
        "model_display_name": selected.get("display_name") or selected["id"],
        "base_url": custom_provider_sdk_base_url(record),
        "api_key": api_key,
        "max_context_tokens": context_tokens,
        "provider": custom_provider_transport(record.get("format")),
        "supports_vision": supports_vision,
        # ``ModelConfig.thinking_mode`` is a free-form string for
        # OpenAI-compatible transports: the resolved depth is more useful than a
        # bare ``true``, and ``false`` still reads as off everywhere.
        "thinking_mode": reasoning_level or "false",
        "endpoint": "",
        "custom_headers": dict(record.get("custom_headers") or {}),
        "vision": supports_vision,
    }


def _resolve_output_cap(record: Dict[str, Any], selected: Dict[str, Any]) -> int:
    """Return the output-token cap: the lower of the provider and model limits."""
    max_tokens = _normalize_int(record.get("max_tokens"), CUSTOM_PROVIDER_DEFAULT_MAX_TOKENS)
    output_limit = _normalize_int(selected.get("max_output_tokens"), max_tokens)
    return min(max_tokens, output_limit)


def _resolve_provider_and_model(
    custom_providers_config: Any,
    provider_ref: Optional[str] = None,
    model_id: Optional[str] = None,
) -> Tuple[Dict[str, Any], Dict[str, Any]]:
    """Resolve the provider record and its selected model from a config section."""
    cfg = normalize_custom_providers_config(custom_providers_config)
    record = (
        find_custom_provider(cfg, provider_ref)
        if provider_ref
        else resolve_active_custom_provider(cfg)
    ) or {}
    selected = resolve_custom_provider_selected_model(record, model_id=model_id) or {}
    return record, selected


def custom_provider_reasoning_level_for_model(model: Any, desired: Any) -> str:
    """Map a requested depth onto the rungs one catalog entry publishes.

    Returns ``""`` when no reasoning should be sent at all.
    """
    wanted = normalize_custom_provider_reasoning_effort(desired)
    if wanted == "off":
        return ""
    selected = model if isinstance(model, dict) else {}
    # A catalog that states the model cannot reason is believed: sending the
    # flags anyway only buys a rejection.  Silence is not a refusal, so a
    # gateway that publishes no capabilities still gets the full payload.
    if selected.get("reasoning") is False:
        return ""

    ranked = [
        (str(level), _reasoning_rank(level, 3))
        for level in (selected.get("reasoning_levels") or [])
        if str(level or "").strip()
    ]
    ranked = [item for item in ranked if item[1] > 0]
    if not ranked:
        return "high" if wanted == "max" else wanted

    wanted_rank = _reasoning_rank(wanted, 6)
    eligible = [item for item in ranked if item[1] <= wanted_rank]
    if eligible:
        return max(eligible, key=lambda item: item[1])[0]
    # The shallowest level published is still closer to the request than nothing.
    return min(ranked, key=lambda item: item[1])[0]


def resolve_custom_provider_reasoning_level(
    provider: Any,
    model_id: Optional[str] = None,
    *,
    desired: Any = None,
) -> str:
    """Resolve the effort string to send, or ``""`` to send no reasoning at all.

    The chosen rung is mapped onto whatever the model publishes, so ``max``
    becomes ``xhigh`` for a model that lists it and ``high`` for one that lists
    nothing -- ``high`` being the deepest value every OpenAI-compatible gateway
    is known to accept.
    """
    record = normalize_custom_provider(provider) or {}
    wanted = normalize_custom_provider_reasoning_effort(
        desired if desired not in (None, "") else record.get("reasoning_effort"),
    )
    if wanted == "off" or not record.get("thinking", True):
        return ""

    selected = resolve_custom_provider_selected_model(record, model_id=model_id) or {}
    return custom_provider_reasoning_level_for_model(selected, wanted)


def custom_provider_reasoning_budget(level: str, output_tokens: Any) -> int:
    """Size a thinking budget that still leaves room for the visible answer."""
    rank = _reasoning_rank(level, 6)
    if rank <= 0:
        return 0
    cap = _normalize_int(output_tokens, 0, minimum=1)
    if cap <= CUSTOM_PROVIDER_MIN_THINKING_BUDGET:
        return 0
    share = _REASONING_BUDGET_SHARE.get(_REASONING_BY_RANK[rank], 0.8)
    # Anthropic-shaped providers require the budget to fit strictly inside the
    # output cap, so the answer always keeps at least a kilotoken of room.
    budget = min(int(cap * share), cap - CUSTOM_PROVIDER_MIN_THINKING_BUDGET)
    return budget if budget >= CUSTOM_PROVIDER_MIN_THINKING_BUDGET else 0


def build_custom_provider_reasoning_extra_body(
    provider: Any,
    model_id: Optional[str] = None,
    *,
    desired: Any = None,
    output_tokens: Any = 0,
) -> Optional[Dict[str, Any]]:
    """Build the widest reasoning payload a chat gateway might understand.

    Every dialect Reverie has met is sent at once -- OpenAI's
    ``reasoning_effort``, OpenRouter's ``reasoning`` block with
    ``include_reasoning``, Anthropic's ``thinking``, DashScope's
    ``enable_thinking``/``thinking_budget``, Groq's ``reasoning_format``, and
    vLLM's ``chat_template_kwargs`` -- because a gateway is far more likely to
    ignore a field it does not recognize than to reject it, and the agent narrows
    the payload one tier at a time when one does reject it.
    """
    record = normalize_custom_provider(provider) or {}
    level = resolve_custom_provider_reasoning_level(record, model_id, desired=desired)
    if not level:
        return None

    selected = resolve_custom_provider_selected_model(record, model_id=model_id) or {}
    cap = _normalize_int(output_tokens, 0, minimum=1) or _resolve_output_cap(record, selected)
    target_model = str(model_id or record.get("selected_model_id") or "").lower()

    payload: Dict[str, Any] = {
        "reasoning_effort": level,
        "reasoning": {"effort": level, "enabled": True, "exclude": False},
        "include_reasoning": True,
        "enable_thinking": True,
        # Groq-style gateways hide the trace unless asked to surface it parsed.
        "reasoning_format": "parsed",
        "chat_template_kwargs": {"enable_thinking": True, "thinking": True},
    }
    if "glm" in target_model:
        # GLM's template drops earlier reasoning unless told to keep it.
        payload["chat_template_kwargs"]["clear_thinking"] = False

    budget = custom_provider_reasoning_budget(level, cap)
    if budget:
        payload["reasoning"]["max_tokens"] = budget
        payload["thinking_budget"] = budget
        # Only shaped when it can carry a legal budget: Anthropic-compatible
        # gateways reject `type: enabled` without one.
        payload["thinking"] = {"type": "enabled", "budget_tokens": budget}

    dropped = custom_provider_reasoning_narrowing(record.get("id"), model_id or record.get("selected_model_id"))
    for _ in range(dropped):
        narrowed = narrow_custom_provider_reasoning_payload(payload)
        if narrowed is None:
            return None
        payload = narrowed
    return payload or None


def build_custom_provider_anthropic_thinking(
    provider: Any,
    model_id: Optional[str] = None,
    *,
    desired: Any = None,
    output_tokens: Any = 0,
) -> Optional[Dict[str, Any]]:
    """Build the native Anthropic ``thinking`` block for a custom provider."""
    record = normalize_custom_provider(provider) or {}
    level = resolve_custom_provider_reasoning_level(record, model_id, desired=desired)
    if not level:
        return None
    selected = resolve_custom_provider_selected_model(record, model_id=model_id) or {}
    cap = _normalize_int(output_tokens, 0, minimum=1) or _resolve_output_cap(record, selected)
    budget = custom_provider_reasoning_budget(level, cap)
    if not budget:
        return None
    return {"type": "enabled", "budget_tokens": budget}


def build_custom_provider_responses_reasoning(
    provider: Any,
    model_id: Optional[str] = None,
    *,
    desired: Any = None,
) -> Optional[Dict[str, Any]]:
    """Build the OpenAI Responses ``reasoning`` block for a custom provider."""
    level = resolve_custom_provider_reasoning_level(provider, model_id, desired=desired)
    if not level:
        return None
    # `detailed` is what makes the summary long enough to be worth rendering.
    return {"effort": level, "summary": "detailed"}


def narrow_custom_provider_reasoning_payload(
    extra_body: Any,
) -> Optional[Dict[str, Any]]:
    """Drop the most vendor-specific reasoning tier still present.

    Returns the narrowed payload, or ``None`` once nothing reasoning-related is
    left to drop, so a caller can tell "try again with less" from "give up".
    """
    if not isinstance(extra_body, dict):
        return None
    for tier in CUSTOM_PROVIDER_REASONING_FIELD_TIERS:
        if not any(field in extra_body for field in tier):
            continue
        return {key: value for key, value in extra_body.items() if key not in tier}
    return None


# Which narrowing tier a provider/model pair settled on, remembered for the life
# of the process so a gateway that rejects a dialect is not re-probed on every
# turn.  Deliberately not persisted: a gateway that gains support for a field
# should get the full payload again after a restart.
_REASONING_NARROWING: Dict[str, int] = {}


def _reasoning_narrowing_key(provider_ref: Any, model_id: Any) -> str:
    provider_key = slugify_provider_name(provider_ref) or str(provider_ref or "").strip().lower()
    return f"{provider_key}:{_model_limit_key(model_id)}"


def custom_provider_reasoning_narrowing(provider_ref: Any, model_id: Any) -> int:
    """How many reasoning tiers this provider/model pair has already refused."""
    return int(_REASONING_NARROWING.get(_reasoning_narrowing_key(provider_ref, model_id), 0))


def remember_custom_provider_reasoning_narrowing(
    provider_ref: Any,
    model_id: Any,
    dropped_tiers: int,
) -> None:
    """Record that a provider/model pair needed the payload narrowed."""
    key = _reasoning_narrowing_key(provider_ref, model_id)
    count = max(0, int(dropped_tiers or 0))
    if count <= 0:
        return
    if count > _REASONING_NARROWING.get(key, 0):
        _REASONING_NARROWING[key] = min(count, len(CUSTOM_PROVIDER_REASONING_FIELD_TIERS))


def reset_custom_provider_reasoning_narrowing() -> None:
    """Forget every remembered narrowing (used by tests and by /provider edits)."""
    _REASONING_NARROWING.clear()


def build_custom_provider_openai_options(
    custom_providers_config: Any,
    provider_ref: Optional[str] = None,
    model_id: Optional[str] = None,
) -> Dict[str, Any]:
    """Return request options -- an output cap plus the reasoning payload."""
    record, selected = _resolve_provider_and_model(custom_providers_config, provider_ref, model_id)
    output_cap = _resolve_output_cap(record, selected)
    options: Dict[str, Any] = {"max_tokens": output_cap}
    extra_body = build_custom_provider_reasoning_extra_body(
        record,
        model_id=model_id,
        output_tokens=output_cap,
    )
    if extra_body:
        options["extra_body"] = extra_body
    return options


def build_custom_provider_anthropic_options(
    custom_providers_config: Any,
    provider_ref: Optional[str] = None,
    model_id: Optional[str] = None,
) -> Dict[str, Any]:
    """Return Anthropic Messages options -- an output cap plus a thinking block."""
    record, selected = _resolve_provider_and_model(custom_providers_config, provider_ref, model_id)
    output_cap = _resolve_output_cap(record, selected)
    options: Dict[str, Any] = {"max_tokens": output_cap}
    thinking = build_custom_provider_anthropic_thinking(
        record,
        model_id=model_id,
        output_tokens=output_cap,
    )
    if thinking:
        options["thinking"] = thinking
    return options


def build_custom_provider_responses_options(
    custom_providers_config: Any,
    provider_ref: Optional[str] = None,
    model_id: Optional[str] = None,
) -> Dict[str, Any]:
    """Return OpenAI Responses options -- an output cap plus a reasoning block."""
    record, selected = _resolve_provider_and_model(custom_providers_config, provider_ref, model_id)
    options: Dict[str, Any] = {"max_output_tokens": _resolve_output_cap(record, selected)}
    reasoning = build_custom_provider_responses_reasoning(record, model_id=model_id)
    if reasoning:
        options["reasoning"] = reasoning
        # Without this the trace is summarized away and never reaches the stream.
        options["include"] = ["reasoning.encrypted_content"]
    return options


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
