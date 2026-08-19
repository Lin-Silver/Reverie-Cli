"""One availability view over every model source, built-in or user-defined.

``/provider list`` needs a single table that mixes Reverie's built-in sources
with the providers a user added through ``/provider add``. Built-in sources keep
their own config shape, so each one is adapted here into the same record the
custom-provider probe already understands: base URL, credential, and API format.
That way one HTTP path (GET ``<base>/models``) reports online state for all of
them, with identical status names, latency, and redaction.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

from .config import (
    Config,
    EXTERNAL_MODEL_SOURCES,
    model_source_display_name,
)
from .custom_providers import (
    CustomProviderProbe,
    custom_provider_format_label,
    custom_provider_models_url,
    default_custom_provider,
    list_custom_providers,
    mask_secret,
    normalize_custom_providers_config,
    probe_custom_provider,
    resolve_custom_provider_api_key,
)

# Sources that answer an OpenAI-style GET <base>/models listing.
PROBEABLE_BUILTIN_SOURCES: Tuple[str, ...] = (
    "aihubmix",
    "agnes",
    "sensenova",
    "modelscope",
    "nvidia",
    "opencode",
)
# Sources with no public catalog endpoint; only a real call can verify them.
UNPROBEABLE_BUILTIN_SOURCES: Tuple[str, ...] = ("codex", "webgemini")

# Sources whose gateway may legitimately accept anonymous requests.
_KEYLESS_SOURCES: Tuple[str, ...] = ("opencode",)

# Credential help text for sources that do not use a plain API key field.
_CREDENTIAL_NOTES: Dict[str, str] = {
    "codex": "ChatGPT OAuth credentials",
    "webgemini": "browser session cookies",
}


@dataclass
class ProviderRow:
    """One line of the unified provider table."""

    key: str
    name: str
    kind: str
    source: str
    format_label: str
    base_url: str
    models_url: str
    key_state: str
    key_hint: str
    selected_model_id: str
    selected_model_display_name: str
    active: bool
    enabled: bool = True
    probeable: bool = False
    probe_note: str = ""
    require_api_key: bool = True
    record: Dict[str, Any] = field(default_factory=dict)

    @property
    def configured(self) -> bool:
        """True when the row has everything needed to reach the provider."""
        return bool(self.base_url) and self.key_state in {"set", "env", "n/a"}


def _builtin_endpoint(source: str, config: Config) -> Tuple[str, str, str, str, str]:
    """Return (base_url, api_key, api_format, selected_id, selected_name)."""
    raw = dict(getattr(config, source, {}) or {})
    if source == "aihubmix":
        from .aihubmix import (
            AIHUBMIX_DEFAULT_API_URL,
            normalize_aihubmix_config,
            resolve_aihubmix_api_key,
            resolve_aihubmix_sdk_base_url,
        )

        cfg = normalize_aihubmix_config(raw)
        base = resolve_aihubmix_sdk_base_url(cfg.get("api_url", AIHUBMIX_DEFAULT_API_URL))
        return base, resolve_aihubmix_api_key(cfg), "openai-chat", str(cfg.get("selected_model_id", "") or ""), str(cfg.get("selected_model_display_name", "") or "")
    if source == "agnes":
        from .agnes import (
            AGNES_DEFAULT_API_URL,
            normalize_agnes_config,
            resolve_agnes_api_key,
            resolve_agnes_sdk_base_url,
        )

        cfg = normalize_agnes_config(raw)
        base = resolve_agnes_sdk_base_url(cfg.get("api_url", AGNES_DEFAULT_API_URL))
        return base, resolve_agnes_api_key(cfg), "openai-chat", str(cfg.get("selected_model_id", "") or ""), str(cfg.get("selected_model_display_name", "") or "")
    if source == "sensenova":
        from .sensenova import (
            SENSENOVA_DEFAULT_API_URL,
            normalize_sensenova_config,
            resolve_sensenova_api_key,
            resolve_sensenova_sdk_base_url,
        )

        cfg = normalize_sensenova_config(raw)
        base = resolve_sensenova_sdk_base_url(cfg.get("api_url", SENSENOVA_DEFAULT_API_URL))
        return base, resolve_sensenova_api_key(cfg), "openai-chat", str(cfg.get("selected_model_id", "") or ""), str(cfg.get("selected_model_display_name", "") or "")
    if source == "modelscope":
        from .modelscope import (
            MODELSCOPE_DEFAULT_API_URL,
            normalize_modelscope_config,
            resolve_modelscope_api_key,
            resolve_modelscope_openai_base_url,
        )

        cfg = normalize_modelscope_config(raw)
        base = resolve_modelscope_openai_base_url(cfg.get("api_url", MODELSCOPE_DEFAULT_API_URL))
        return base, resolve_modelscope_api_key(cfg), "openai-chat", str(cfg.get("selected_model_id", "") or ""), str(cfg.get("selected_model_display_name", "") or "")
    if source == "nvidia":
        from .nvidia import (
            normalize_nvidia_config,
            resolve_nvidia_api_key,
            resolve_nvidia_sdk_base_url,
        )

        cfg = normalize_nvidia_config(raw)
        base = resolve_nvidia_sdk_base_url(cfg.get("api_url", ""))
        return base, resolve_nvidia_api_key(cfg), "openai-chat", str(cfg.get("selected_model_id", "") or ""), str(cfg.get("selected_model_display_name", "") or "")
    if source == "opencode":
        from .opencode import (
            OPENCODE_DEFAULT_API_URL,
            normalize_opencode_config,
            resolve_opencode_api_key,
            resolve_opencode_sdk_base_url,
        )

        cfg = normalize_opencode_config(raw)
        base = resolve_opencode_sdk_base_url(cfg.get("api_url", OPENCODE_DEFAULT_API_URL))
        return base, resolve_opencode_api_key(cfg), "openai-chat", str(cfg.get("selected_model_id", "") or ""), str(cfg.get("selected_model_display_name", "") or "")
    if source == "codex":
        from .codex import (
            normalize_codex_config,
            resolve_codex_credentials,
            resolve_codex_request_url,
        )

        cfg = normalize_codex_config(raw)
        request_url = resolve_codex_request_url(cfg.get("api_url", ""), cfg.get("endpoint", ""))
        credentials = resolve_codex_credentials(cfg, request_url=request_url)
        api_key = str(credentials.get("api_key", "") or "") if credentials.get("found") else ""
        return str(cfg.get("api_url", "") or ""), api_key, "openai-responses", str(cfg.get("selected_model_id", "") or ""), str(cfg.get("selected_model_display_name", "") or "")
    if source == "webgemini":
        from .webgemini import normalize_webgemini_config

        cfg = normalize_webgemini_config(raw)
        return str(cfg.get("api_url", "") or ""), "", "openai-chat", str(cfg.get("selected_model_id", "") or ""), str(cfg.get("selected_model_display_name", "") or "")
    return "", "", "openai-chat", str(raw.get("selected_model_id", "") or ""), str(raw.get("selected_model_display_name", "") or "")


def _builtin_enabled(source: str, config: Config) -> bool:
    raw = getattr(config, source, {})
    if not isinstance(raw, dict):
        return True
    return bool(raw.get("enabled", True))


def _key_state(source: str, config_key: str, effective_key: str) -> Tuple[str, str]:
    """Classify the credential state into (state, hint)."""
    note = _CREDENTIAL_NOTES.get(source, "")
    if effective_key and str(config_key or "").strip():
        return "set", mask_secret(effective_key)
    if effective_key:
        return "env", f"{mask_secret(effective_key)} ({note or 'env'})"
    if note:
        return "n/a", note
    if source in _KEYLESS_SOURCES:
        return "n/a", "not required"
    return "missing", "not set"


def _builtin_row(source: str, config: Config) -> ProviderRow:
    base_url, api_key, api_format, selected_id, selected_name = _builtin_endpoint(source, config)
    raw = getattr(config, source, {})
    config_key = str((raw or {}).get("api_key", "") or "") if isinstance(raw, dict) else ""
    key_state, key_hint = _key_state(source, config_key, api_key)
    probeable = source in PROBEABLE_BUILTIN_SOURCES
    record: Dict[str, Any] = {}
    if probeable:
        record = default_custom_provider(
            provider_id=source,
            name=model_source_display_name(source),
            base_url=base_url,
            api_key=api_key,
            provider_format=api_format,
        )
        record["selected_model_id"] = selected_id
        record["selected_model_display_name"] = selected_name
    return ProviderRow(
        key=source,
        name=model_source_display_name(source),
        kind="builtin",
        source=source,
        format_label=custom_provider_format_label(api_format),
        base_url=base_url,
        models_url=custom_provider_models_url(record) if record else "",
        key_state=key_state,
        key_hint=key_hint,
        selected_model_id=selected_id,
        selected_model_display_name=selected_name or selected_id,
        active=str(getattr(config, "active_model_source", "") or "").strip().lower() == source,
        enabled=_builtin_enabled(source, config),
        probeable=probeable,
        probe_note="" if probeable else f"No catalog endpoint; run /provider {source} test.",
        require_api_key=source not in _KEYLESS_SOURCES,
        record=record,
    )


def _custom_row(provider: Dict[str, Any], config: Config) -> ProviderRow:
    api_key = resolve_custom_provider_api_key(provider)
    key_state, key_hint = _key_state("custom", str(provider.get("api_key", "") or ""), api_key)
    active_source = str(getattr(config, "active_model_source", "") or "").strip().lower()
    active_id = str(
        normalize_custom_providers_config(getattr(config, "custom_providers", {})).get("active_provider_id", "")
        or ""
    )
    return ProviderRow(
        key=f"custom:{provider['id']}",
        name=str(provider.get("name") or provider["id"]),
        kind="custom",
        source="custom",
        format_label=custom_provider_format_label(provider.get("format")),
        base_url=str(provider.get("base_url", "") or ""),
        models_url=custom_provider_models_url(provider),
        key_state=key_state,
        key_hint=key_hint,
        selected_model_id=str(provider.get("selected_model_id", "") or ""),
        selected_model_display_name=str(
            provider.get("selected_model_display_name") or provider.get("selected_model_id") or ""
        ),
        active=active_source == "custom" and active_id == provider["id"],
        enabled=bool(provider.get("enabled", True)),
        probeable=True,
        require_api_key=True,
        record=dict(provider),
    )


def collect_provider_rows(config: Config, *, include_builtin: bool = True) -> List[ProviderRow]:
    """Build the unified provider table for one config."""
    rows: List[ProviderRow] = []
    if include_builtin:
        rows.extend(_builtin_row(source, config) for source in EXTERNAL_MODEL_SOURCES)
    rows.extend(
        _custom_row(provider, config)
        for provider in list_custom_providers(getattr(config, "custom_providers", {}))
    )
    return rows


def probe_provider_rows(
    rows: List[ProviderRow],
    *,
    timeout: int = 10,
    max_workers: int = 8,
) -> Dict[str, CustomProviderProbe]:
    """Probe every probeable row in parallel, keyed by ``ProviderRow.key``."""
    targets = [row for row in rows if row.probeable and row.record]
    if not targets:
        return {}

    def _run(row: ProviderRow) -> Tuple[str, CustomProviderProbe]:
        probe = probe_custom_provider(
            row.record,
            timeout=timeout,
            require_api_key=row.require_api_key,
        )
        probe.name = row.name
        return row.key, probe

    if len(targets) == 1:
        key, probe = _run(targets[0])
        return {key: probe}

    from concurrent.futures import ThreadPoolExecutor

    workers = max(1, min(int(max_workers or 8), len(targets)))
    with ThreadPoolExecutor(max_workers=workers) as pool:
        return dict(pool.map(_run, targets))


def find_provider_row(rows: List[ProviderRow], query: Any) -> Optional[ProviderRow]:
    """Resolve one row by source name, provider id, display name, or prefix."""
    wanted = str(query or "").strip().lower()
    if not wanted:
        return None
    for row in rows:
        candidates = {
            row.key.lower(),
            row.source.lower(),
            row.name.lower(),
            row.key.split(":", 1)[-1].lower(),
        }
        if wanted in candidates:
            return row
    matches = [
        row
        for row in rows
        if wanted in row.key.lower() or wanted in row.name.lower()
    ]
    return matches[0] if len(matches) == 1 else None
