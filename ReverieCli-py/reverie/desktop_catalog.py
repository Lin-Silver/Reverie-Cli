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
    if source == "custom":
        from .custom_providers import (
            get_custom_provider_model_catalog,
            resolve_active_custom_provider,
        )

        provider = resolve_active_custom_provider(getattr(config, "custom_providers", {}))
        if not provider:
            return []
        return get_custom_provider_model_catalog(
            provider,
            fetch_live=fetch_live,
            force_refresh=fetch_live,
        )
    if source == "codex":
        from .codex import get_codex_model_catalog

        return get_codex_model_catalog()
    if source == "webgemini":
        from .webgemini import get_webgemini_model_catalog

        return get_webgemini_model_catalog()
    if source == "opencode":
        from .opencode import get_opencode_model_catalog

        return get_opencode_model_catalog(
            getattr(config, "opencode", {}),
            fetch_live=fetch_live,
            force_refresh=fetch_live,
        )
    if source == "aihubmix":
        from .aihubmix import get_aihubmix_model_catalog

        return get_aihubmix_model_catalog()
    if source == "agnes":
        from .agnes import get_agnes_model_catalog

        return get_agnes_model_catalog(getattr(config, "agnes", {}))
    if source == "sensenova":
        from .sensenova import get_sensenova_model_catalog

        return get_sensenova_model_catalog(
            getattr(config, "sensenova", {}),
            fetch_live=fetch_live,
            force_refresh=fetch_live,
        )
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
                # Enough to prefill the desktop's edit form without ever sending
                # the key itself: `configured` also covers keyless transports, so
                # the form needs to know whether a key is actually stored.
                "api_key_configured": bool(str(model.api_key or "").strip()),
                "custom_headers": dict(getattr(model, "custom_headers", {}) or {}),
            }
        )
    return models


def _reasoning_metadata(source: str, model: Dict[str, Any], provider_config: Dict[str, Any]) -> Dict[str, Any]:
    model_id = str(model.get("id") or "")
    if source == "codex":
        from .codex import get_codex_reasoning_catalog, normalize_codex_reasoning_choice

        options = get_codex_reasoning_catalog(model_id)
        value = normalize_codex_reasoning_choice(provider_config.get("reasoning_effort"))
        option_ids = {str(item.get("id") or "") for item in options}
        if value not in option_ids:
            value = "medium" if "medium" in option_ids else (str(options[0].get("id") or "") if options else "")
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
    if source == "opencode":
        from .opencode import resolve_opencode_thinking_choice

        return {
            "control": str(model.get("thinking_control") or "none"),
            "options": list(model.get("thinking_options") or []),
            "value": resolve_opencode_thinking_choice(provider_config, model_id),
        }
    if source == "modelscope":
        from .modelscope import resolve_modelscope_thinking_choice

        return {
            "control": str(model.get("thinking_control") or "none"),
            "options": list(model.get("thinking_options") or []),
            "value": resolve_modelscope_thinking_choice(provider_config, model_id),
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


def _raw_provider_config(source: str, config: Config) -> Dict[str, Any]:
    """Return the provider settings dict backing one source.

    Custom providers live in a list under ``custom_providers``, so the active
    record stands in for the flat section the built-in sources use.
    """
    if source == "custom":
        from .custom_providers import resolve_active_custom_provider

        return dict(resolve_active_custom_provider(getattr(config, "custom_providers", {})) or {})
    return dict(getattr(config, source, {}) or {})


def _safe_provider_config(source: str, config: Config) -> Dict[str, Any]:
    provider_config = _raw_provider_config(source, config)
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
        provider_config = _raw_provider_config(source, config) if source != "standard" else {}
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
        if source == "custom":
            # The GUI edits a list of records, not one flat section, so it needs
            # every provider rather than only the active one. The aggregate keeps
            # its generic label on purpose: it titles the management panel, while
            # the picker names each provider from the records below.
            source_payload["custom_providers"] = custom_provider_entries(config)
            source_payload["custom_provider_formats"] = custom_provider_format_options()
        if source in {"sensenova", "opencode"}:
            source_payload["catalog_live"] = bool(models) and all(
                item.get("catalog_source") == "api" for item in models
            )
        if source == "agnes":
            from .agnes import get_agnes_source_catalog

            agnes_catalog = get_agnes_source_catalog(provider_config)
            source_payload["modalities"] = {
                "live": bool(agnes_catalog.get("live", False)),
                "llm": len(agnes_catalog.get("llm", [])),
                "tti": len(agnes_catalog.get("tti", [])),
                "ttv": len(agnes_catalog.get("ttv", [])),
            }
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


def _apply_custom_provider_selection(config: Config, selected: Dict[str, Any]) -> Dict[str, Any]:
    """Store a model choice on the active custom provider record."""
    from .custom_providers import resolve_active_custom_provider, upsert_custom_provider

    provider = resolve_active_custom_provider(getattr(config, "custom_providers", {}))
    if not provider:
        raise ValueError("No custom provider is configured. Add one with /provider add.")
    provider = dict(provider)
    provider["selected_model_id"] = str(selected.get("id") or "")
    provider["selected_model_display_name"] = str(selected.get("display_name") or selected.get("id") or "")
    if selected.get("context_length"):
        provider["max_context_tokens"] = int(selected["context_length"])
    if selected.get("max_output_tokens"):
        provider["max_tokens"] = min(
            int(provider.get("max_tokens") or selected["max_output_tokens"]),
            int(selected["max_output_tokens"]),
        )
    if selected.get("vision") is not None:
        provider["supports_vision"] = bool(selected.get("vision"))
    config.custom_providers = upsert_custom_provider(
        getattr(config, "custom_providers", {}),
        provider,
        activate=True,
    )
    config.active_model_source = "custom"
    return selected


def apply_model_selection(
    config: Config,
    source: Any,
    model_id: Any = "",
    reasoning: Any = None,
) -> Dict[str, Any]:
    """Apply a source/model/reasoning selection to a Config instance."""
    normalized_source = normalize_active_model_source(source)
    catalog = (
        _standard_catalog(config)
        if normalized_source == "standard"
        else _external_catalog(
            normalized_source,
            config,
            fetch_live=normalized_source in {"sensenova", "opencode", "custom"},
        )
    )
    selection_query = model_id
    if not str(selection_query or "").strip():
        selection_query = (
            str(getattr(config, "active_model_index", 0))
            if normalized_source == "standard"
            else str(_raw_provider_config(normalized_source, config).get("selected_model_id") or "")
        )
    selected = _catalog_match(catalog, selection_query)
    if selected is None:
        raise ValueError(f"Unknown or ambiguous model for {model_source_display_name(normalized_source)}: {model_id}")

    if normalized_source == "standard":
        config.active_model_index = int(selected["id"])
        config.active_model_source = "standard"
        return selected

    if normalized_source == "custom":
        return _apply_custom_provider_selection(config, selected)

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
    elif normalized_source == "opencode":
        from .opencode import apply_opencode_thinking_choice, normalize_opencode_config

        if reasoning is not None:
            provider_config = apply_opencode_thinking_choice(provider_config, selected["id"], reasoning)
        provider_config = normalize_opencode_config(provider_config)
    elif normalized_source == "modelscope":
        from .modelscope import apply_modelscope_thinking_choice, normalize_modelscope_config

        if reasoning is not None:
            provider_config = apply_modelscope_thinking_choice(provider_config, selected["id"], reasoning)
        provider_config = normalize_modelscope_config(provider_config)
    else:
        normalizer: Optional[Callable[[Any], Dict[str, Any]]] = None
        if normalized_source == "webgemini":
            from .webgemini import normalize_webgemini_config as normalizer
        elif normalized_source == "aihubmix":
            from .aihubmix import normalize_aihubmix_config as normalizer
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
    if normalized_source == "custom":
        raise ValueError(
            "Custom providers are a list of records, not a flat section; "
            "edit them with the custom provider actions or /provider."
        )
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


def custom_provider_format_options() -> List[Dict[str, str]]:
    """Return the API request formats the desktop add-provider form may offer."""
    from .custom_providers import custom_provider_format_choices

    return [dict(choice) for choice in custom_provider_format_choices()]


def _custom_provider_entry(config: Config, record: Dict[str, Any]) -> Dict[str, Any]:
    """Describe one provider for the desktop without leaking its API key."""
    from .custom_providers import (
        custom_provider_format_label,
        custom_provider_models_url,
        get_custom_provider_model_context_limit,
        mask_secret,
        resolve_custom_provider_api_key,
        suggest_custom_provider_model_context_limit,
    )

    resolved_key = resolve_custom_provider_api_key(record)
    stored_key = str(record.get("api_key") or "").strip()
    key_source = "config" if stored_key else "env" if resolved_key else "none"
    models = []
    for item in record.get("models", []):
        model = _normalized_model("custom", item, record)
        # The desktop needs to know which models still owe the user a context
        # limit, so it can ask once on first selection just like the CLI does.
        saved_limit = get_custom_provider_model_context_limit(record, model.get("id"))
        model["context_limit"] = int(saved_limit or 0)
        model["needs_context_limit"] = not saved_limit
        model["suggested_context_limit"] = int(
            suggest_custom_provider_model_context_limit(record, model.get("id"))
        )
        models.append(model)
    active_provider_id = str(
        (getattr(config, "custom_providers", {}) or {}).get("active_provider_id") or ""
    ).strip()
    return {
        "id": str(record.get("id") or ""),
        "name": str(record.get("name") or record.get("id") or ""),
        "base_url": str(record.get("base_url") or ""),
        "models_url": custom_provider_models_url(record),
        "format": str(record.get("format") or ""),
        "format_label": custom_provider_format_label(record.get("format")),
        "enabled": bool(record.get("enabled", True)),
        "active": bool(
            record.get("id")
            and record.get("id") == active_provider_id
            and normalize_active_model_source(getattr(config, "active_model_source", "standard")) == "custom"
        ),
        "api_key_masked": mask_secret(resolved_key),
        "api_key_configured": bool(resolved_key),
        "api_key_source": key_source,
        "selected_model_id": str(record.get("selected_model_id") or ""),
        "selected_model_display_name": str(record.get("selected_model_display_name") or ""),
        "max_context_tokens": int(record.get("max_context_tokens") or 0),
        "max_tokens": int(record.get("max_tokens") or 0),
        "supports_vision": bool(record.get("supports_vision", False)),
        "thinking": bool(record.get("thinking", True)),
        "model_context_limits": {
            str(key): int(value)
            for key, value in (record.get("model_context_limits") or {}).items()
            if value
        },
        "models_synced_at": float(record.get("models_synced_at") or 0.0),
        "models": models,
    }


def custom_provider_entries(config: Config) -> List[Dict[str, Any]]:
    """Return every registered custom provider, key-masked, in stored order."""
    from .custom_providers import list_custom_providers

    return [
        _custom_provider_entry(config, record)
        for record in list_custom_providers(getattr(config, "custom_providers", {}))
    ]


def _require_custom_provider(config: Config, provider_ref: Any) -> Dict[str, Any]:
    from .custom_providers import find_custom_provider

    record = find_custom_provider(getattr(config, "custom_providers", {}), provider_ref)
    if not record:
        raise ValueError(f"No custom provider matches '{provider_ref}'.")
    return record


def _sync_custom_provider_models(
    config: Config,
    record: Dict[str, Any],
    *,
    force_refresh: bool = True,
) -> Dict[str, Any]:
    """Fetch the live catalog for one provider and store it on the record.

    Raises the transport failure so the desktop can show why a refresh failed
    instead of silently rendering a stale list.
    """
    import time

    from .custom_providers import fetch_custom_provider_models, upsert_custom_provider

    models = fetch_custom_provider_models(record, force_refresh=force_refresh)
    updated = dict(record)
    updated["models"] = models
    updated["models_synced_at"] = time.time()
    config.custom_providers = upsert_custom_provider(
        getattr(config, "custom_providers", {}), updated
    )
    return _require_custom_provider(config, updated["id"])


def create_custom_provider(config: Config, payload: Dict[str, Any]) -> Dict[str, Any]:
    """Register one provider from the four desktop inputs and pull its catalog.

    Validation mirrors ``/provider add`` so the GUI cannot create a record the
    CLI would have rejected.
    """
    from .config import EXTERNAL_MODEL_SOURCES
    from .custom_providers import (
        CUSTOM_PROVIDER_MAX_PROVIDERS,
        default_custom_provider,
        list_custom_providers,
        resolve_custom_provider_base_url,
        slugify_provider_name,
        upsert_custom_provider,
    )

    existing = list_custom_providers(getattr(config, "custom_providers", {}))
    if len(existing) >= CUSTOM_PROVIDER_MAX_PROVIDERS:
        raise ValueError(f"Provider limit reached ({CUSTOM_PROVIDER_MAX_PROVIDERS}). Remove one first.")

    name = str(payload.get("name") or "").strip()
    provider_id = slugify_provider_name(name)
    if not provider_id:
        raise ValueError("Provider name must contain letters or digits.")
    if provider_id in set(EXTERNAL_MODEL_SOURCES) | {"standard", "custom"}:
        raise ValueError(f"'{provider_id}' is a built-in source name. Pick another.")
    if any(record["id"] == provider_id for record in existing):
        raise ValueError(f"Provider '{provider_id}' already exists.")

    base_url = resolve_custom_provider_base_url(payload.get("base_url"))
    if not base_url:
        raise ValueError("A base URL is required.")
    api_key = str(payload.get("api_key") or "").strip()
    if not api_key:
        raise ValueError("An API key is required.")

    provider = default_custom_provider(
        provider_id=provider_id,
        name=name,
        base_url=base_url,
        api_key=api_key,
        provider_format=payload.get("format") or payload.get("provider_format") or "openai-chat",
    )
    config.custom_providers = upsert_custom_provider(getattr(config, "custom_providers", {}), provider)
    record = _require_custom_provider(config, provider_id)
    try:
        record = _sync_custom_provider_models(config, record)
    except Exception as error:  # The provider is saved; the catalog can be retried.
        return {**_custom_provider_entry(config, record), "sync_error": str(error)}
    return _custom_provider_entry(config, record)


def update_custom_provider(
    config: Config, provider_ref: Any, patch: Dict[str, Any]
) -> Dict[str, Any]:
    """Edit one provider's four fields, preserving an omitted API key."""
    from .custom_providers import (
        normalize_custom_provider_format,
        resolve_custom_provider_base_url,
        upsert_custom_provider,
    )

    record = dict(_require_custom_provider(config, provider_ref))
    patch = dict(patch or {})
    unsupported = set(patch) - {"name", "base_url", "api_key", "format", "enabled", "thinking"}
    if unsupported:
        raise ValueError(f"Unsupported custom provider field: {sorted(unsupported)[0]}")

    endpoint_changed = False
    if "name" in patch:
        name = str(patch.get("name") or "").strip()
        if not name:
            raise ValueError("Provider name cannot be empty.")
        record["name"] = name
    if "base_url" in patch:
        base_url = resolve_custom_provider_base_url(patch.get("base_url"))
        if not base_url:
            raise ValueError("A base URL is required.")
        endpoint_changed = endpoint_changed or base_url != record.get("base_url")
        record["base_url"] = base_url
    if "api_key" in patch and str(patch.get("api_key") or "").strip():
        api_key = str(patch["api_key"]).strip()
        endpoint_changed = endpoint_changed or api_key != record.get("api_key")
        record["api_key"] = api_key
    if "format" in patch:
        provider_format = normalize_custom_provider_format(patch.get("format"))
        endpoint_changed = endpoint_changed or provider_format != record.get("format")
        record["format"] = provider_format
    if "enabled" in patch:
        record["enabled"] = bool(patch["enabled"])
    if "thinking" in patch:
        record["thinking"] = bool(patch["thinking"])

    config.custom_providers = upsert_custom_provider(getattr(config, "custom_providers", {}), record)
    stored = _require_custom_provider(config, record["id"])
    if endpoint_changed:
        try:
            stored = _sync_custom_provider_models(config, stored)
        except Exception as error:  # Keep the edit; report the failed refresh.
            _resync_active_custom_provider(config)
            return {**_custom_provider_entry(config, stored), "sync_error": str(error)}
    _resync_active_custom_provider(config)
    return _custom_provider_entry(config, stored)


def delete_custom_provider(config: Config, provider_ref: Any) -> None:
    """Remove one provider and fall back to the standard source when needed."""
    from .custom_providers import remove_custom_provider

    record = _require_custom_provider(config, provider_ref)
    config.custom_providers, removed = remove_custom_provider(
        getattr(config, "custom_providers", {}), record["id"]
    )
    if not removed:
        raise ValueError(f"No custom provider matches '{provider_ref}'.")
    _resync_active_custom_provider(config)


def refresh_custom_provider_models(config: Config, provider_ref: Any) -> Dict[str, Any]:
    """Re-fetch one provider's catalog from its live ``/models`` endpoint."""
    record = _require_custom_provider(config, provider_ref)
    stored = _sync_custom_provider_models(config, record)
    _resync_active_custom_provider(config)
    return _custom_provider_entry(config, stored)


def select_custom_provider_model(
    config: Config, provider_ref: Any, model_id: Any, context_limit: Any = None
) -> Dict[str, Any]:
    """Activate one provider and pin the model the user picked.

    The desktop only ever offers models from the catalog it rendered, so an id
    that is not in the stored catalog means a stale view rather than a
    pre-refresh selection worth honouring.

    ``context_limit`` carries the answer to the first-selection prompt.  When it
    is omitted and the model has no stored limit, the suggested default is saved
    so no selected model is ever left without one.
    """
    from .custom_providers import (
        custom_provider_model_needs_context_limit,
        parse_context_token_limit,
        set_custom_provider_model_context_limit,
        suggest_custom_provider_model_context_limit,
        upsert_custom_provider,
    )

    record = dict(_require_custom_provider(config, provider_ref))
    wanted = str(model_id or "").strip()
    selected = next(
        (
            dict(item)
            for item in record.get("models") or []
            if str(item.get("id") or "").lower() == wanted.lower()
        ),
        None,
    )
    if not selected:
        raise ValueError(
            f"Model '{wanted}' is not in {record.get('name') or record.get('id')}'s catalog. Refresh it first."
        )
    record["enabled"] = True
    record["selected_model_id"] = str(selected.get("id") or "")
    record["selected_model_display_name"] = str(selected.get("display_name") or selected.get("id") or "")

    requested_limit = parse_context_token_limit(context_limit)
    if context_limit not in (None, "") and not requested_limit:
        raise ValueError(f"'{context_limit}' is not a usable context limit.")
    if not requested_limit and custom_provider_model_needs_context_limit(record, record["selected_model_id"]):
        requested_limit = suggest_custom_provider_model_context_limit(record, record["selected_model_id"])
    if requested_limit:
        record = set_custom_provider_model_context_limit(
            record, record["selected_model_id"], requested_limit
        )

    config.custom_providers = upsert_custom_provider(
        getattr(config, "custom_providers", {}), record, activate=True
    )
    config.active_model_source = "custom"
    return _custom_provider_entry(config, _require_custom_provider(config, record["id"]))


def _resync_active_custom_provider(config: Config) -> None:
    """Re-run the section normalizer and leave ``custom`` only if it still works."""
    from .custom_providers import (
        build_custom_provider_runtime_model_data,
        normalize_custom_providers_config,
    )

    config.custom_providers = normalize_custom_providers_config(
        getattr(config, "custom_providers", {})
    )
    if normalize_active_model_source(getattr(config, "active_model_source", "standard")) != "custom":
        return
    if not build_custom_provider_runtime_model_data(config.custom_providers):
        config.active_model_source = "standard"


def probe_provider_availability(
    config: Config, keys: Optional[List[str]] = None, *, timeout: int = 10
) -> List[Dict[str, Any]]:
    """Probe sources concurrently, mirroring what ``/provider list`` reports.

    ``keys`` accepts the row keys from the returned payload (``custom:<id>`` for
    a user-added provider, the bare source id for a built-in); omitting it
    probes every source.
    """
    from .provider_probe import collect_provider_rows, probe_provider_rows

    wanted = {str(key).strip() for key in keys or [] if str(key).strip()}
    rows = [row for row in collect_provider_rows(config) if not wanted or row.key in wanted]
    probes = probe_provider_rows(rows, timeout=timeout)
    results: List[Dict[str, Any]] = []
    for row in rows:
        probe = probes.get(row.key)
        entry: Dict[str, Any] = {
            "key": row.key,
            "name": row.name,
            "kind": row.kind,
            "source": row.source,
            "provider_id": "",
            "format_label": row.format_label,
            "base_url": row.base_url,
            "key_state": row.key_state,
            "key_hint": row.key_hint,
            "active": row.active,
            "enabled": row.enabled,
            "probeable": row.probeable,
            "probe_note": row.probe_note,
        }
        entry.update(
            probe.to_dict()
            if probe
            else {"status": "not-probed", "latency_ms": None, "model_count": 0, "detail": row.probe_note}
        )
        # ``to_dict`` carries the probe's own name/id, which for a built-in row is
        # a synthesized stand-in record; the row is the authority here.
        entry["name"] = row.name
        entry["provider_id"] = str(row.record.get("id") or "") if row.kind == "custom" else ""
        results.append(entry)
    return results
