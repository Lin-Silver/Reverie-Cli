"""Desktop-facing model catalogs and configuration mutation helpers.

The desktop UI deliberately asks the core for this metadata instead of
duplicating provider/model capability tables in JavaScript.  This keeps the
TUI, one-shot CLI, and Electron host on the same source of truth.
"""

from __future__ import annotations

from typing import Any, Callable, Dict, List, Optional

from .config import (
    Config,
    ModelConfig,
    MODEL_SOURCE_DISPLAY_NAMES,
    SUPPORTED_ACTIVE_MODEL_SOURCES,
    model_source_display_name,
    normalize_active_model_source,
    normalize_model_provider,
)


_PROVIDER_CONFIG_FIELDS: Dict[str, List[Dict[str, Any]]] = {
    "codex": [
        {"key": "auth_mode", "label": "Authentication", "kind": "choice", "choices": ["auto", "codex", "api_key", "none"]},
        {"key": "api_key", "label": "API key", "kind": "secret"},
        {"key": "api_url", "label": "API URL", "kind": "url"},
        {"key": "api_key_env", "label": "API key environment variable", "kind": "text"},
        {"key": "timeout", "label": "Timeout (seconds)", "kind": "int", "min": 10, "max": 3600},
    ],
    "webgemini": [
        {"key": "cookie", "label": "Google cookie", "kind": "secret", "multiline": True},
        {"key": "cookie_file", "label": "Cookie file", "kind": "path"},
        {"key": "auth_user", "label": "Auth user", "kind": "text"},
        {"key": "xsrf_token", "label": "XSRF token", "kind": "secret"},
        {"key": "proxy", "label": "Proxy", "kind": "url"},
        {"key": "timeout", "label": "Timeout (seconds)", "kind": "int", "min": 10, "max": 3600},
        {"key": "retry_attempts", "label": "Retry attempts", "kind": "int", "min": 0, "max": 12},
    ],
    "opencode": [
        {"key": "api_key", "label": "API key", "kind": "secret", "optional": True},
        {"key": "api_url", "label": "API URL", "kind": "url"},
        {"key": "timeout", "label": "Timeout (seconds)", "kind": "int", "min": 10, "max": 3600},
        {"key": "temperature", "label": "Temperature", "kind": "float", "min": 0, "max": 2},
    ],
    "aihubmix": [
        {"key": "api_key", "label": "API key", "kind": "secret"},
        {"key": "api_url", "label": "API URL", "kind": "url"},
        {"key": "timeout", "label": "Timeout (seconds)", "kind": "int", "min": 10, "max": 3600},
        {"key": "temperature", "label": "Temperature", "kind": "float", "min": 0, "max": 2},
    ],
    "agnes": [
        {"key": "api_key", "label": "API key", "kind": "secret"},
        {"key": "api_url", "label": "API URL", "kind": "url"},
        {"key": "live_model_list", "label": "Load live model list", "kind": "bool"},
        {"key": "timeout", "label": "Timeout (seconds)", "kind": "int", "min": 10, "max": 3600},
        {"key": "temperature", "label": "Temperature", "kind": "float", "min": 0, "max": 2},
    ],
    "unlimitedsurf": [
        {"key": "api_key", "label": "API key", "kind": "secret", "optional": True},
        {"key": "api_url", "label": "API URL", "kind": "url"},
        {"key": "timeout", "label": "Timeout (seconds)", "kind": "int", "min": 10, "max": 3600},
    ],
    "sensenova": [
        {"key": "api_key", "label": "API key", "kind": "secret"},
        {"key": "api_url", "label": "API URL", "kind": "url"},
        {"key": "timeout", "label": "Timeout (seconds)", "kind": "int", "min": 10, "max": 3600},
        {"key": "temperature", "label": "Temperature", "kind": "float", "min": 0, "max": 2},
        {"key": "top_p", "label": "Top P", "kind": "float", "min": 0, "max": 1},
    ],
    "modelscope": [
        {"key": "api_key", "label": "API key", "kind": "secret"},
        {"key": "api_url", "label": "API URL", "kind": "url"},
        {"key": "timeout", "label": "Timeout (seconds)", "kind": "int", "min": 10, "max": 3600},
    ],
    "nvidia": [
        {"key": "api_key", "label": "API key", "kind": "secret"},
        {"key": "api_url", "label": "API URL", "kind": "url"},
        {"key": "timeout", "label": "Timeout (seconds)", "kind": "int", "min": 10, "max": 3600},
        {"key": "temperature", "label": "Temperature", "kind": "float", "min": 0, "max": 2},
        {"key": "top_p", "label": "Top P", "kind": "float", "min": 0, "max": 1},
        {"key": "reasoning_budget", "label": "Reasoning budget", "kind": "int", "min": -1, "max": 32768},
    ],
}

_SECRET_FIELDS = {"api_key", "cookie", "xsrf_token"}


def _external_catalog(source: str, config: Config, *, fetch_live: bool = False) -> List[Dict[str, Any]]:
    """Load one provider catalog using the provider's native helper."""
    if source == "codex":
        from .codex import get_codex_model_catalog

        return get_codex_model_catalog()
    if source == "webgemini":
        from .webgemini import get_webgemini_model_catalog

        return get_webgemini_model_catalog()
    if source == "opencode":
        from .opencode import get_opencode_model_catalog

        return get_opencode_model_catalog()
    if source == "aihubmix":
        from .aihubmix import get_aihubmix_model_catalog

        return get_aihubmix_model_catalog()
    if source == "agnes":
        from .agnes import get_agnes_model_catalog

        return get_agnes_model_catalog(getattr(config, "agnes", {}))
    if source == "unlimitedsurf":
        from .unlimitedsurf import get_unlimitedsurf_model_catalog

        cfg = getattr(config, "unlimitedsurf", {}) or {}
        return get_unlimitedsurf_model_catalog(cfg.get("api_url"), fetch_live=fetch_live, timeout=8)
    if source == "sensenova":
        from .sensenova import get_sensenova_model_catalog

        return get_sensenova_model_catalog()
    if source == "modelscope":
        from .modelscope import get_modelscope_model_catalog

        return get_modelscope_model_catalog()
    if source == "nvidia":
        from .nvidia import get_nvidia_model_catalog

        return get_nvidia_model_catalog()
    return []


def _standard_catalog(config: Config) -> List[Dict[str, Any]]:
    models: List[Dict[str, Any]] = []
    for index, model in enumerate(getattr(config, "models", []) or []):
        models.append(
            {
                "id": str(index),
                "model": model.model,
                "display_name": model.model_display_name or model.model,
                "description": f"Custom {normalize_model_provider(model.provider)} model",
                "transport": normalize_model_provider(model.provider),
                "context_length": model.max_context_tokens,
                "vision": bool(model.supports_vision),
                "tool_calling": True,
                "thinking": False,
                "thinking_control": "none",
                "thinking_options": [],
                "base_url": model.base_url,
                "endpoint": model.endpoint,
                "configured": bool(str(model.api_key or "").strip() or model.provider in {"webgemini", "codex"}),
            }
        )
    return models


def _reasoning_metadata(source: str, model: Dict[str, Any], provider_config: Dict[str, Any]) -> Dict[str, Any]:
    model_id = str(model.get("id") or "")
    if source == "codex":
        from .codex import get_codex_reasoning_catalog, normalize_codex_reasoning_choice

        options = get_codex_reasoning_catalog(model_id)
        value = normalize_codex_reasoning_choice(provider_config.get("reasoning_effort"))
        return {"control": "effort", "options": options, "value": value}
    if source == "nvidia":
        from .nvidia import get_nvidia_thinking_options, resolve_nvidia_thinking_choice

        control = str(model.get("thinking_control") or "none")
        return {
            "control": control,
            "options": get_nvidia_thinking_options(model_id),
            "value": resolve_nvidia_thinking_choice(provider_config, model_id),
        }
    if source == "agnes":
        from .agnes import get_agnes_thinking_catalog, normalize_agnes_thinking_mode

        supports = bool(model.get("thinking", False))
        return {
            "control": "effort" if supports else "none",
            "options": get_agnes_thinking_catalog(supports_thinking=supports) if supports else [],
            "value": normalize_agnes_thinking_mode(provider_config.get("thinking_mode"), supports_thinking=supports),
        }
    if source == "sensenova":
        from .sensenova import normalize_sensenova_reasoning_effort

        return {
            "control": str(model.get("thinking_control") or "none"),
            "options": list(model.get("thinking_options") or []),
            "value": normalize_sensenova_reasoning_effort(provider_config.get("reasoning_effort")),
        }

    control = str(model.get("thinking_control") or "")
    if not control:
        control = "fixed" if bool(model.get("thinking", False)) else "none"
    return {"control": control, "options": list(model.get("thinking_options") or []), "value": ""}


def _normalized_model(source: str, raw_model: Dict[str, Any], provider_config: Dict[str, Any]) -> Dict[str, Any]:
    model = dict(raw_model)
    model.setdefault("display_name", str(model.get("id") or model.get("model") or "Model"))
    model.setdefault("description", "")
    model.setdefault("context_length", None)
    model.setdefault("max_output_tokens", None)
    model.setdefault("vision", False)
    model.setdefault("tool_calling", True)
    model.setdefault("thinking", False)
    model["reasoning"] = _reasoning_metadata(source, model, provider_config)
    return model


def _safe_provider_config(source: str, config: Config) -> Dict[str, Any]:
    provider_config = dict(getattr(config, source, {}) or {})
    configured_secrets: Dict[str, bool] = {}
    for key in _SECRET_FIELDS:
        if key in provider_config:
            configured_secrets[key] = bool(str(provider_config.get(key) or "").strip())
            provider_config[key] = ""
    return {"values": provider_config, "configured_secrets": configured_secrets}


def build_model_sources_payload(config: Config, *, fetch_live: bool = False) -> Dict[str, Any]:
    """Return source, model, provider-field, and reasoning metadata for desktop clients."""
    sources: List[Dict[str, Any]] = []
    active_source = normalize_active_model_source(getattr(config, "active_model_source", "standard"))
    for source in SUPPORTED_ACTIVE_MODEL_SOURCES:
        provider_config = dict(getattr(config, source, {}) or {}) if source != "standard" else {}
        raw_models = _standard_catalog(config) if source == "standard" else _external_catalog(source, config, fetch_live=fetch_live)
        models = [_normalized_model(source, item, provider_config) for item in raw_models]
        selected_id = ""
        if source == "standard":
            if models:
                selected_id = str(min(max(int(getattr(config, "active_model_index", 0) or 0), 0), len(models) - 1))
        else:
            selected_id = str(provider_config.get("selected_model_id") or "")
        selected = next((item for item in models if str(item.get("id", "")).lower() == selected_id.lower()), None)
        if selected is None and models:
            selected = models[0]
            selected_id = str(selected.get("id") or "")
        source_payload: Dict[str, Any] = {
            "id": source,
            "display_name": model_source_display_name(source),
            "active": source == active_source,
            "selected_model_id": selected_id,
            "selected_reasoning": dict(
                (selected or {}).get("reasoning")
                or {"control": "none", "options": [], "value": ""}
            ),
            "models": models,
            "config_fields": list(_PROVIDER_CONFIG_FIELDS.get(source, [])),
        }
        if source != "standard":
            source_payload["config"] = _safe_provider_config(source, config)
        sources.append(source_payload)

    active_model = config.active_model
    return {
        "active_source": active_source,
        "active_model": {
            "id": str(getattr(active_model, "model", "") or ""),
            "display_name": str(getattr(active_model, "model_display_name", "") or ""),
            "provider": str(getattr(active_model, "provider", "") or ""),
        }
        if active_model
        else None,
        "sources": sources,
    }


def _catalog_match(catalog: List[Dict[str, Any]], query: Any) -> Optional[Dict[str, Any]]:
    wanted = str(query or "").strip().lower()
    if not wanted:
        return catalog[0] if catalog else None
    exact = next(
        (
            item
            for item in catalog
            if wanted
            in {
                str(item.get("id") or "").strip().lower(),
                str(item.get("model") or "").strip().lower(),
                str(item.get("display_name") or "").strip().lower(),
            }
        ),
        None,
    )
    if exact:
        return exact
    matches = [
        item
        for item in catalog
        if wanted in str(item.get("id") or "").lower()
        or wanted in str(item.get("display_name") or "").lower()
    ]
    return matches[0] if len(matches) == 1 else None


def apply_model_selection(
    config: Config,
    source: Any,
    model_id: Any = "",
    reasoning: Any = None,
) -> Dict[str, Any]:
    """Apply a source/model/reasoning selection to a Config instance."""
    normalized_source = normalize_active_model_source(source)
    catalog = _standard_catalog(config) if normalized_source == "standard" else _external_catalog(normalized_source, config)
    selection_query = model_id
    if not str(selection_query or "").strip():
        selection_query = (
            str(getattr(config, "active_model_index", 0))
            if normalized_source == "standard"
            else str((getattr(config, normalized_source, {}) or {}).get("selected_model_id") or "")
        )
    selected = _catalog_match(catalog, selection_query)
    if selected is None:
        raise ValueError(f"Unknown or ambiguous model for {model_source_display_name(normalized_source)}: {model_id}")

    if normalized_source == "standard":
        config.active_model_index = int(selected["id"])
        config.active_model_source = "standard"
        return selected

    provider_config = dict(getattr(config, normalized_source, {}) or {})
    provider_config["selected_model_id"] = str(selected.get("id") or "")
    provider_config["selected_model_display_name"] = str(selected.get("display_name") or selected.get("id") or "")
    if selected.get("context_length"):
        provider_config["max_context_tokens"] = int(selected["context_length"])
    if selected.get("max_output_tokens") and "max_tokens" in provider_config:
        provider_config["max_tokens"] = min(
            int(provider_config.get("max_tokens") or selected["max_output_tokens"]),
            int(selected["max_output_tokens"]),
        )

    if normalized_source == "codex":
        from .codex import get_codex_reasoning_efforts, normalize_codex_config, normalize_codex_reasoning_choice

        if reasoning is not None:
            choice = normalize_codex_reasoning_choice(reasoning)
            if choice not in get_codex_reasoning_efforts(selected["id"], catalog=catalog):
                raise ValueError(f"Reasoning level {reasoning!r} is not supported by {selected['id']}")
            provider_config["reasoning_effort"] = choice
        provider_config = normalize_codex_config(provider_config)
    elif normalized_source == "nvidia":
        from .nvidia import apply_nvidia_thinking_choice, normalize_nvidia_config

        if reasoning is not None:
            provider_config = apply_nvidia_thinking_choice(provider_config, selected["id"], reasoning)
        provider_config = normalize_nvidia_config(provider_config)
    elif normalized_source == "agnes":
        from .agnes import normalize_agnes_config, normalize_agnes_thinking_mode

        if reasoning is not None:
            provider_config["thinking_mode"] = normalize_agnes_thinking_mode(
                reasoning,
                supports_thinking=bool(selected.get("thinking", False)),
            )
        provider_config = normalize_agnes_config(provider_config)
    elif normalized_source == "sensenova":
        from .sensenova import normalize_sensenova_config, normalize_sensenova_reasoning_effort

        if reasoning is not None:
            choices = {str(item.get("id") or "") for item in selected.get("thinking_options", [])}
            choice = normalize_sensenova_reasoning_effort(reasoning)
            if choices and choice not in choices:
                raise ValueError(f"Reasoning level {reasoning!r} is not supported by {selected['id']}")
            provider_config["reasoning_effort"] = choice
        provider_config = normalize_sensenova_config(provider_config)
    else:
        normalizer: Optional[Callable[[Any], Dict[str, Any]]] = None
        if normalized_source == "webgemini":
            from .webgemini import normalize_webgemini_config as normalizer
        elif normalized_source == "opencode":
            from .opencode import normalize_opencode_config as normalizer
        elif normalized_source == "aihubmix":
            from .aihubmix import normalize_aihubmix_config as normalizer
        elif normalized_source == "unlimitedsurf":
            from .unlimitedsurf import normalize_unlimitedsurf_config as normalizer
        elif normalized_source == "modelscope":
            from .modelscope import normalize_modelscope_config as normalizer
        if normalizer:
            provider_config = normalizer(provider_config)

    setattr(config, normalized_source, provider_config)
    config.active_model_source = normalized_source
    return selected


def apply_provider_config_patch(
    config: Config,
    source: Any,
    patch: Dict[str, Any],
    clear_fields: Optional[List[str]] = None,
) -> None:
    """Apply only desktop-declared provider fields, preserving omitted secrets."""
    normalized_source = normalize_active_model_source(source)
    if normalized_source == "standard":
        raise ValueError("Standard models are edited through the standard model actions.")
    field_specs = {item["key"]: item for item in _PROVIDER_CONFIG_FIELDS.get(normalized_source, [])}
    provider_config = dict(getattr(config, normalized_source, {}) or {})
    for key, value in dict(patch or {}).items():
        spec = field_specs.get(str(key))
        if spec is None:
            raise ValueError(f"Unsupported {normalized_source} configuration field: {key}")
        kind = str(spec.get("kind") or "text")
        if kind == "secret" and value in (None, ""):
            continue
        if kind == "bool":
            value = bool(value)
        elif kind == "int":
            value = int(value)
        elif kind == "float":
            value = float(value)
        else:
            value = str(value or "").strip()
        provider_config[str(key)] = value
    for key in clear_fields or []:
        if key not in field_specs or str(field_specs[key].get("kind")) != "secret":
            raise ValueError(f"Only declared secret fields can be cleared: {key}")
        provider_config[key] = ""
    setattr(config, normalized_source, provider_config)
    # Re-apply the current selection so the provider's native normalizer runs.
    apply_model_selection(
        config,
        normalized_source,
        provider_config.get("selected_model_id", ""),
        provider_config.get("reasoning_effort", provider_config.get("thinking_mode")),
    )


def add_standard_model(config: Config, payload: Dict[str, Any]) -> int:
    """Append one validated custom model and return its index."""
    model_id = str(payload.get("model") or "").strip()
    display_name = str(payload.get("model_display_name") or model_id).strip()
    base_url = str(payload.get("base_url") or "").strip()
    if not model_id or not display_name or not base_url:
        raise ValueError("Model id, display name, and base URL are required.")
    model = ModelConfig.from_dict(
        {
            "model": model_id,
            "model_display_name": display_name,
            "base_url": base_url,
            "api_key": str(payload.get("api_key") or "").strip(),
            "max_context_tokens": payload.get("max_context_tokens"),
            "provider": normalize_model_provider(payload.get("provider", "openai-chat")),
            "supports_vision": bool(payload.get("supports_vision", False)),
            "endpoint": str(payload.get("endpoint") or "").strip(),
            "custom_headers": payload.get("custom_headers") if isinstance(payload.get("custom_headers"), dict) else {},
        }
    )
    config.models.append(model)
    config.active_model_index = len(config.models) - 1
    config.active_model_source = "standard"
    return config.active_model_index


def update_standard_model(config: Config, index: int, payload: Dict[str, Any]) -> None:
    """Update one custom model while preserving an omitted API key."""
    if index < 0 or index >= len(config.models):
        raise ValueError("Standard model index is out of range.")
    current = config.models[index]
    merged = current.to_dict()
    for key, value in dict(payload or {}).items():
        if key == "api_key" and value in (None, ""):
            continue
        merged[key] = value
    replacement_config = Config(models=[])
    new_index = add_standard_model(replacement_config, merged)
    config.models[index] = replacement_config.models[new_index]


def delete_standard_model(config: Config, index: int) -> None:
    if index < 0 or index >= len(config.models):
        raise ValueError("Standard model index is out of range.")
    config.models.pop(index)
    config.active_model_index = min(config.active_model_index, max(0, len(config.models) - 1))
