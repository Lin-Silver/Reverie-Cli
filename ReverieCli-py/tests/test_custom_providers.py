"""Tests for user-defined ("custom") providers and the /provider command family.

A custom provider is described by exactly four user inputs -- name, base URL,
API key, and request format -- so these tests pin the derivations that turn
those four fields into a working request: the normalized base URL, the model
and chat endpoints, the auth headers per format, the catalog parse, and the
runtime ModelConfig payload. Everything reaching the network is faked.
"""

from __future__ import annotations

import threading

import pytest
import requests
from rich.console import Console

from reverie import custom_providers as cp
from reverie import provider_probe as pp
from reverie.cli import commands as commands_module
from reverie.cli.commands import CommandHandler
from reverie.cli.help_catalog import HELP_TOPICS, normalize_help_topic
from reverie.config import EXTERNAL_MODEL_SOURCES, Config, ConfigManager
from reverie.custom_providers import (
    CUSTOM_PROVIDER_ANTHROPIC_VERSION,
    CUSTOM_PROVIDER_COMMAND_ACTIONS,
    CUSTOM_PROVIDER_DEFAULT_CONTEXT_TOKENS,
    CUSTOM_PROVIDER_DEFAULT_REASONING_EFFORT,
    CUSTOM_PROVIDER_FORMATS,
    CUSTOM_PROVIDER_MAX_CONTEXT_TOKENS,
    CUSTOM_PROVIDER_MAX_PROVIDERS,
    CUSTOM_PROVIDER_MIN_THINKING_BUDGET,
    CUSTOM_PROVIDER_REASONING_FIELD_TIERS,
    build_custom_provider_anthropic_options,
    build_custom_provider_command_completions,
    build_custom_provider_openai_options,
    build_custom_provider_reasoning_extra_body,
    build_custom_provider_responses_options,
    build_custom_provider_runtime_model_data,
    custom_provider_auth_headers,
    custom_provider_chat_url,
    custom_provider_sdk_base_url,
    custom_provider_format_choices,
    custom_provider_format_label,
    custom_provider_models_url,
    custom_provider_model_needs_context_limit,
    custom_provider_reasoning_budget,
    custom_provider_reasoning_choices,
    custom_provider_reasoning_options,
    custom_provider_transport,
    default_custom_provider,
    default_custom_providers_config,
    fetch_custom_provider_models,
    find_custom_provider,
    get_custom_provider_model_context_limit,
    list_custom_providers,
    mask_secret,
    narrow_custom_provider_reasoning_payload,
    normalize_custom_provider,
    normalize_custom_provider_format,
    normalize_custom_provider_reasoning_effort,
    normalize_custom_providers_config,
    parse_context_token_limit,
    probe_custom_provider,
    probe_custom_provider_chat,
    remember_custom_provider_reasoning_narrowing,
    remove_custom_provider,
    reset_custom_provider_reasoning_narrowing,
    resolve_active_custom_provider,
    resolve_custom_provider_api_key,
    resolve_custom_provider_base_url,
    resolve_custom_provider_reasoning_level,
    set_custom_provider_model_context_limit,
    slugify_provider_name,
    suggest_custom_provider_model_context_limit,
    upsert_custom_provider,
)
from reverie.request_identity import REVERIE_CLIENT_HEADER


@pytest.fixture(autouse=True)
def clear_model_cache():
    """The catalog cache is module-global; keep it from leaking across tests."""
    cp._MODEL_CACHE.clear()
    yield
    cp._MODEL_CACHE.clear()


class FakeResponse:
    """Minimal stand-in for a requests.Response."""

    def __init__(self, payload=None, status_code: int = 200, text: str = ""):
        self._payload = payload if payload is not None else {"data": []}
        self.status_code = status_code
        self.text = text or ""

    def raise_for_status(self):
        if self.status_code >= 400:
            raise requests.HTTPError(f"HTTP {self.status_code}", response=self)

    def json(self):
        return self._payload


def _xkiro_record(**overrides):
    """The worked example from the feature request, as a stored record."""
    record = {
        "id": "xkiro",
        "name": "xkiro",
        "base_url": "https://api.xkiro.invalid/v1",
        "api_key": "xk-live-abcdef123456",
        "format": "openai-chat",
        "models": [
            {
                "id": "kiro-pro",
                "display_name": "Kiro Pro",
                "context_length": 200000,
                "max_output_tokens": 8192,
                "vision": True,
            },
            {"id": "kiro-mini", "context_length": 32000},
        ],
        "selected_model_id": "kiro-pro",
    }
    record.update(overrides)
    return record


# --------------------------------------------------------------------------
# The four user inputs
# --------------------------------------------------------------------------


def test_format_choices_cover_every_supported_format_and_transport() -> None:
    choices = custom_provider_format_choices()

    assert [choice["id"] for choice in choices] == list(CUSTOM_PROVIDER_FORMATS)
    assert all(choice["label"] and choice["description"] for choice in choices)
    assert {name: custom_provider_transport(name) for name in CUSTOM_PROVIDER_FORMATS} == {
        "openai-chat": "openai-chat",
        "openai-responses": "openai-responses",
        "anthropic": "anthropic",
    }
    assert custom_provider_format_label("anthropic") == "Anthropic Messages"


@pytest.mark.parametrize(
    ("typed", "expected"),
    [
        ("openai", "openai-chat"),
        ("OpenAI-Compatible", "openai-chat"),
        ("chat_completions", "openai-chat"),
        ("responses", "openai-responses"),
        ("claude", "anthropic"),
        ("messages", "anthropic"),
        ("anthropic", "anthropic"),
        ("", "openai-chat"),
        ("nonsense", "openai-chat"),
    ],
)
def test_format_aliases_normalize_to_an_implemented_transport(typed: str, expected: str) -> None:
    assert normalize_custom_provider_format(typed) == expected


@pytest.mark.parametrize(
    ("name", "expected"),
    [
        ("xkiro", "xkiro"),
        ("My Kiro Gateway!", "my-kiro-gateway"),
        ("  Relay  #2  ", "relay-2"),
        ("!!!", ""),
        ("", ""),
    ],
)
def test_provider_name_slugs_are_command_safe(name: str, expected: str) -> None:
    assert slugify_provider_name(name) == expected


def test_provider_slug_is_capped_for_command_use() -> None:
    assert len(slugify_provider_name("a" * 200)) == 48


@pytest.mark.parametrize(
    ("typed", "expected"),
    [
        ("https://api.xkiro.invalid/v1", "https://api.xkiro.invalid/v1"),
        ("api.xkiro.invalid/v1", "https://api.xkiro.invalid/v1"),
        ("https://api.xkiro.invalid/v1/", "https://api.xkiro.invalid/v1"),
        ("https://api.xkiro.invalid/v1/chat/completions", "https://api.xkiro.invalid/v1"),
        ("https://api.xkiro.invalid/v1/messages", "https://api.xkiro.invalid/v1"),
        ("https://api.xkiro.invalid/v1/models", "https://api.xkiro.invalid/v1"),
        ("http://localhost:8080/api", "http://localhost:8080/api"),
        ("", ""),
    ],
)
def test_base_url_is_normalized_without_guessing_a_version_prefix(typed: str, expected: str) -> None:
    assert resolve_custom_provider_base_url(typed) == expected


def test_base_url_never_invents_a_v1_segment() -> None:
    # Some gateways serve /models at the root; guessing /v1 would break them.
    assert resolve_custom_provider_base_url("https://api.example.com") == "https://api.example.com"


@pytest.mark.parametrize(
    ("provider_format", "chat_path"),
    [
        ("openai-chat", "/chat/completions"),
        ("openai-responses", "/responses"),
        ("anthropic", "/messages"),
    ],
)
def test_endpoints_follow_the_selected_request_format(provider_format: str, chat_path: str) -> None:
    record = default_custom_provider(
        provider_id="xkiro",
        name="xkiro",
        base_url="https://api.xkiro.invalid/v1",
        api_key="xk-live-abcdef123456",
        provider_format=provider_format,
    )

    assert custom_provider_models_url(record) == "https://api.xkiro.invalid/v1/models"
    assert custom_provider_chat_url(record) == f"https://api.xkiro.invalid/v1{chat_path}"


def test_endpoints_are_empty_without_a_base_url() -> None:
    record = default_custom_provider(provider_id="x", name="x", base_url="", api_key="k")

    assert custom_provider_models_url(record) == ""
    assert custom_provider_chat_url(record) == ""


# --------------------------------------------------------------------------
# Credentials and headers
# --------------------------------------------------------------------------


def test_api_key_resolution_prefers_stored_then_named_env_then_derived_env(monkeypatch) -> None:
    monkeypatch.setenv("XKIRO_TOKEN", "from-named-env")
    monkeypatch.setenv("REVERIE_XKIRO_API_KEY", "from-derived-env")

    stored = {"id": "xkiro", "api_key": "from-config", "api_key_env": "XKIRO_TOKEN"}
    named = {"id": "xkiro", "api_key": "", "api_key_env": "XKIRO_TOKEN"}
    derived = {"id": "xkiro", "api_key": "", "api_key_env": ""}

    assert resolve_custom_provider_api_key(stored) == "from-config"
    assert resolve_custom_provider_api_key(named) == "from-named-env"
    assert resolve_custom_provider_api_key(derived) == "from-derived-env"

    monkeypatch.delenv("REVERIE_XKIRO_API_KEY")
    assert resolve_custom_provider_api_key(derived) == ""


def test_openai_formats_authenticate_with_a_bearer_token() -> None:
    headers = custom_provider_auth_headers(_xkiro_record())

    assert headers["Authorization"] == "Bearer xk-live-abcdef123456"
    assert "x-api-key" not in headers
    assert headers[REVERIE_CLIENT_HEADER]


def test_anthropic_format_authenticates_with_x_api_key_and_a_version() -> None:
    headers = custom_provider_auth_headers(_xkiro_record(format="anthropic"))

    assert headers["x-api-key"] == "xk-live-abcdef123456"
    assert headers["anthropic-version"] == CUSTOM_PROVIDER_ANTHROPIC_VERSION
    assert "Authorization" not in headers


def test_custom_headers_merge_but_cannot_forge_the_client_identity() -> None:
    record = _xkiro_record(
        custom_headers={"X-Org": "reverie", REVERIE_CLIENT_HEADER: "spoofed", "": "dropped"}
    )

    headers = custom_provider_auth_headers(record)

    assert headers["X-Org"] == "reverie"
    assert headers[REVERIE_CLIENT_HEADER] != "spoofed"
    assert "" not in headers


def test_mask_secret_never_reveals_a_short_key() -> None:
    assert mask_secret("xk-live-abcdef123456") == "xk-l...3456"
    assert mask_secret("short") == "*****"
    assert mask_secret("") == ""


# --------------------------------------------------------------------------
# Live model catalog
# --------------------------------------------------------------------------


def _install_fake_get(monkeypatch, payload, calls: list) -> None:
    def fake_get(url, *, headers, timeout):
        calls.append({"url": url, "headers": dict(headers), "timeout": timeout})
        return FakeResponse(payload)

    monkeypatch.setattr(cp.requests, "get", fake_get)


def test_model_list_is_fetched_from_the_format_specific_endpoint(monkeypatch) -> None:
    calls: list = []
    _install_fake_get(
        monkeypatch,
        {"data": [{"id": "kiro-pro", "context_length": 200000}, {"id": "kiro-mini"}]},
        calls,
    )

    models = fetch_custom_provider_models(_xkiro_record(), force_refresh=True)

    assert [item["id"] for item in models] == ["kiro-mini", "kiro-pro"]
    assert calls[0]["url"] == "https://api.xkiro.invalid/v1/models"
    assert calls[0]["headers"]["Authorization"] == "Bearer xk-live-abcdef123456"


@pytest.mark.parametrize(
    "payload",
    [
        {"data": [{"id": "b"}, {"id": "a"}]},
        {"models": [{"id": "b"}, {"id": "a"}]},
        {"results": [{"id": "b"}, {"id": "a"}]},
        [{"id": "b"}, {"id": "a"}],
        ["b", "a"],
    ],
)
def test_catalog_parsing_accepts_every_common_payload_shape(monkeypatch, payload) -> None:
    _install_fake_get(monkeypatch, payload, [])

    models = fetch_custom_provider_models(_xkiro_record(), force_refresh=True)

    assert [item["id"] for item in models] == ["a", "b"]


def test_catalog_parsing_drops_duplicates_and_unusable_entries(monkeypatch) -> None:
    _install_fake_get(
        monkeypatch,
        {"data": [{"id": "dup"}, {"id": "DUP"}, {"id": ""}, {"no_id": 1}, 42, {"id": "keep"}]},
        [],
    )

    models = fetch_custom_provider_models(_xkiro_record(), force_refresh=True)

    assert [item["id"] for item in models] == ["dup", "keep"]


def test_catalog_infers_vision_from_modalities_then_from_the_model_name(monkeypatch) -> None:
    _install_fake_get(
        monkeypatch,
        {
            "data": [
                {"id": "text-only", "input_modalities": ["text"]},
                {"id": "multimodal", "architecture": {"input_modalities": ["text", "image"]}},
                {"id": "some-vision-model"},
                {"id": "plain-relay-model"},
            ]
        },
        [],
    )

    models = {item["id"]: item for item in fetch_custom_provider_models(_xkiro_record(), force_refresh=True)}

    assert models["text-only"]["vision"] is False
    assert models["multimodal"]["vision"] is True
    assert models["some-vision-model"]["vision"] is True
    assert models["plain-relay-model"]["vision"] is False


def test_catalog_is_cached_until_a_refresh_is_forced(monkeypatch) -> None:
    calls: list = []
    _install_fake_get(monkeypatch, {"data": [{"id": "kiro-pro"}]}, calls)
    record = _xkiro_record()

    fetch_custom_provider_models(record, force_refresh=True)
    fetch_custom_provider_models(record)
    assert len(calls) == 1

    fetch_custom_provider_models(record, force_refresh=True)
    assert len(calls) == 2


def test_catalog_cache_is_keyed_by_credential_so_a_new_key_refetches(monkeypatch) -> None:
    calls: list = []
    _install_fake_get(monkeypatch, {"data": [{"id": "kiro-pro"}]}, calls)

    fetch_custom_provider_models(_xkiro_record(), force_refresh=True)
    fetch_custom_provider_models(_xkiro_record(api_key="xk-live-999999999999"))

    assert len(calls) == 2


def test_fetching_without_a_base_url_reports_why() -> None:
    with pytest.raises(ValueError):
        fetch_custom_provider_models({"id": "x", "name": "x", "base_url": ""})


# --------------------------------------------------------------------------
# Record and section normalization
# --------------------------------------------------------------------------


def test_normalized_record_adopts_the_selected_model_capabilities() -> None:
    record = normalize_custom_provider(_xkiro_record(max_tokens=16384))

    assert record["id"] == "xkiro"
    assert record["max_context_tokens"] == 200000
    assert record["max_tokens"] == 8192  # capped by the model's own output limit
    assert record["supports_vision"] is True
    assert record["selected_model_display_name"] == "Kiro Pro"


def test_normalized_record_keeps_a_selection_made_before_a_catalog_refresh() -> None:
    record = normalize_custom_provider(
        {"id": "xkiro", "name": "xkiro", "base_url": "https://api.xkiro.invalid/v1", "selected_model_id": "gone"}
    )

    assert record["selected_model_id"] == "gone"
    assert record["selected_model_display_name"] == "gone"


def test_unusable_records_are_rejected() -> None:
    assert normalize_custom_provider(None) is None
    assert normalize_custom_provider({"name": "!!!"}) is None


def test_section_deduplicates_providers_and_tolerates_a_hand_edited_mapping() -> None:
    section = normalize_custom_providers_config(
        {
            "providers": {
                "xkiro": {"name": "xkiro", "base_url": "https://a.example.com"},
                "other": {"name": "Other", "base_url": "https://b.example.com"},
            }
        }
    )

    assert [record["id"] for record in section["providers"]] == ["xkiro", "other"]


def test_section_enforces_the_provider_cap() -> None:
    raw = {
        "providers": [
            {"id": f"p{index}", "name": f"p{index}", "base_url": "https://x.example.com"}
            for index in range(CUSTOM_PROVIDER_MAX_PROVIDERS + 10)
        ]
    }

    assert len(normalize_custom_providers_config(raw)["providers"]) == CUSTOM_PROVIDER_MAX_PROVIDERS


def test_section_falls_back_to_the_first_provider_that_can_serve_a_request() -> None:
    section = normalize_custom_providers_config(
        {
            "active_provider_id": "does-not-exist",
            "providers": [
                {"id": "nokey", "name": "nokey", "base_url": "https://a.example.com", "selected_model_id": "m"},
                _xkiro_record(),
            ],
        }
    )

    assert section["active_provider_id"] == "xkiro"


def test_default_section_is_empty() -> None:
    assert default_custom_providers_config() == {"active_provider_id": "", "providers": []}


def test_upsert_replaces_by_id_and_can_activate() -> None:
    section = upsert_custom_provider(default_custom_providers_config(), _xkiro_record(), activate=True)
    section = upsert_custom_provider(section, _xkiro_record(name="xkiro renamed"))

    assert len(section["providers"]) == 1
    assert section["providers"][0]["name"] == "xkiro renamed"
    assert section["active_provider_id"] == "xkiro"


def test_remove_clears_the_active_pointer_and_reports_a_miss() -> None:
    section = upsert_custom_provider(default_custom_providers_config(), _xkiro_record(), activate=True)

    section, removed = remove_custom_provider(section, "xkiro")
    assert removed is True
    assert section == default_custom_providers_config()

    section, removed = remove_custom_provider(section, "xkiro")
    assert removed is False


def test_providers_resolve_by_id_display_name_or_unique_prefix() -> None:
    # No stored id, so the display name drives the slug -- the /provider add path.
    section = upsert_custom_provider(
        default_custom_providers_config(), _xkiro_record(id="", name="X Kiro Relay")
    )

    assert find_custom_provider(section, "x-kiro-relay")["id"] == "x-kiro-relay"
    assert find_custom_provider(section, "X Kiro Relay")["id"] == "x-kiro-relay"
    assert find_custom_provider(section, "x-kiro")["id"] == "x-kiro-relay"
    assert find_custom_provider(section, "") is None
    assert find_custom_provider(section, "nope") is None


def test_an_ambiguous_prefix_resolves_to_nothing() -> None:
    section = upsert_custom_provider(default_custom_providers_config(), {"id": "relay-a", "name": "relay-a"})
    section = upsert_custom_provider(section, {"id": "relay-b", "name": "relay-b"})

    assert find_custom_provider(section, "relay") is None


# --------------------------------------------------------------------------
# Per-model context limits and thinking mode
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    "typed, expected",
    [
        ("128000", 128000),
        ("128k", 128000),
        ("128K", 128000),
        ("1.2m", 1200000),
        ("  256,000 tokens ", 256000),
        ("32_000", 32000),
        (200000, 200000),
        ("999", None),  # below the floor a real window could have
        ("", None),
        ("plenty", None),
        (None, None),
        (True, None),  # a bool is never a token count
    ],
)
def test_a_typed_context_limit_is_parsed_or_refused(typed, expected) -> None:
    assert parse_context_token_limit(typed) == expected


def test_an_absurd_context_limit_is_clamped_rather_than_refused() -> None:
    assert parse_context_token_limit("900m") == CUSTOM_PROVIDER_MAX_CONTEXT_TOKENS


def test_thinking_mode_is_on_by_default_and_can_be_turned_off() -> None:
    assert normalize_custom_provider(_xkiro_record())["thinking"] is True
    assert normalize_custom_provider(_xkiro_record(thinking=False))["thinking"] is False
    assert normalize_custom_provider(_xkiro_record(thinking="off"))["thinking"] is False


def test_a_fresh_record_owes_a_limit_for_every_model() -> None:
    record = normalize_custom_provider(_xkiro_record())

    assert record["model_context_limits"] == {}
    assert custom_provider_model_needs_context_limit(record, "kiro-pro") is True
    assert get_custom_provider_model_context_limit(record, "kiro-pro") is None


def test_a_saved_limit_is_reused_and_never_asked_for_twice() -> None:
    record = set_custom_provider_model_context_limit(_xkiro_record(), "Kiro-Pro", "256k")

    # The key is case-folded, so the same model is recognized however it is typed.
    assert record["model_context_limits"] == {"kiro-pro": 256000}
    assert custom_provider_model_needs_context_limit(record, "kiro-pro") is False
    assert get_custom_provider_model_context_limit(record, "KIRO-PRO") == 256000

    # A model the user never chose is left alone.
    assert custom_provider_model_needs_context_limit(record, "kiro-mini") is True


def test_the_selected_model_limit_is_the_default_lookup() -> None:
    record = set_custom_provider_model_context_limit(_xkiro_record(), "kiro-pro", 256000)

    assert get_custom_provider_model_context_limit(record) == 256000


def test_a_bad_answer_cannot_erase_a_saved_limit() -> None:
    record = set_custom_provider_model_context_limit(_xkiro_record(), "kiro-pro", 256000)
    record = set_custom_provider_model_context_limit(record, "kiro-pro", "nonsense")

    assert record["model_context_limits"] == {"kiro-pro": 256000}


def test_a_suggested_limit_prefers_the_saved_value_then_the_published_window() -> None:
    record = _xkiro_record()

    # Published by the gateway.
    assert suggest_custom_provider_model_context_limit(record, "kiro-pro") == 200000
    # Not in the catalog at all.
    assert (
        suggest_custom_provider_model_context_limit(record, "kiro-ghost")
        == CUSTOM_PROVIDER_DEFAULT_CONTEXT_TOKENS
    )
    # Saved by the user, which outranks whatever the gateway published.
    saved = set_custom_provider_model_context_limit(record, "kiro-pro", 256000)
    assert suggest_custom_provider_model_context_limit(saved, "kiro-pro") == 256000


def test_hand_edited_limits_are_filtered_when_the_config_loads() -> None:
    record = normalize_custom_provider(
        _xkiro_record(
            model_context_limits={
                "Kiro-Pro": "256k",
                "kiro-mini": 0,
                "": 128000,
                "kiro-broken": "plenty",
            }
        )
    )

    assert record["model_context_limits"] == {"kiro-pro": 256000}


def test_a_saved_limit_outranks_the_published_context_window() -> None:
    record = set_custom_provider_model_context_limit(_xkiro_record(), "kiro-pro", 256000)
    section = upsert_custom_provider(default_custom_providers_config(), record, activate=True)

    data = build_custom_provider_runtime_model_data(section)

    assert data["max_context_tokens"] == 256000  # not the catalog's 200000
    # A catalog that publishes no effort names still gets thinking, at the
    # deepest level every OpenAI-compatible gateway is known to accept.
    assert data["thinking_mode"] == "high"


def test_thinking_mode_reaches_the_runtime_payload_as_a_string() -> None:
    section = upsert_custom_provider(
        default_custom_providers_config(), _xkiro_record(thinking=False), activate=True
    )

    assert build_custom_provider_runtime_model_data(section)["thinking_mode"] == "false"


# --------------------------------------------------------------------------
# Generated command completions
# --------------------------------------------------------------------------


def test_every_stored_provider_contributes_its_own_commands() -> None:
    section = upsert_custom_provider(default_custom_providers_config(), _xkiro_record())

    completions = build_custom_provider_command_completions(section)

    assert len(completions) == len(CUSTOM_PROVIDER_COMMAND_ACTIONS)
    for action, _ in CUSTOM_PROVIDER_COMMAND_ACTIONS:
        command = f"/provider xkiro{' ' + action if action else ''}"
        assert command in completions
        assert completions[command].startswith("xkiro: ")
    for expected in ("/provider xkiro models", "/provider xkiro context", "/provider xkiro thinking"):
        assert expected in completions


def test_command_completions_follow_the_provider_id_not_its_display_name() -> None:
    section = upsert_custom_provider(
        default_custom_providers_config(), {"id": "x-kiro-relay", "name": "X Kiro Relay"}
    )

    completions = build_custom_provider_command_completions(section)

    assert "/provider x-kiro-relay models" in completions
    assert completions["/provider x-kiro-relay models"].startswith("X Kiro Relay: ")


def test_no_providers_generate_no_commands() -> None:
    assert build_custom_provider_command_completions(default_custom_providers_config()) == {}
    assert build_custom_provider_command_completions(None) == {}


# --------------------------------------------------------------------------
# Runtime model payload
# --------------------------------------------------------------------------


def test_active_provider_builds_a_runtime_model_for_its_transport() -> None:
    section = upsert_custom_provider(default_custom_providers_config(), _xkiro_record(), activate=True)

    data = build_custom_provider_runtime_model_data(section)

    assert data["model"] == "kiro-pro"
    assert data["model_display_name"] == "Kiro Pro"
    assert data["base_url"] == "https://api.xkiro.invalid/v1"
    assert data["api_key"] == "xk-live-abcdef123456"
    assert data["provider"] == "openai-chat"
    assert data["max_context_tokens"] == 200000
    assert data["supports_vision"] is True


def test_anthropic_format_selects_the_anthropic_transport() -> None:
    section = upsert_custom_provider(
        default_custom_providers_config(), _xkiro_record(format="anthropic"), activate=True
    )

    data = build_custom_provider_runtime_model_data(section)
    assert data["provider"] == "anthropic"
    # The Anthropic SDK appends ``/v1/messages`` itself, so the runtime base URL
    # has to shed the ``/v1`` the user typed or the request lands on ``/v1/v1``.
    assert data["base_url"] == "https://api.xkiro.invalid"
    # The raw HTTP path is unaffected: it still builds the full endpoint.
    assert custom_provider_chat_url(_xkiro_record(format="anthropic")) == (
        "https://api.xkiro.invalid/v1/messages"
    )


@pytest.mark.parametrize(
    ("fmt", "expected"),
    [
        ("openai-chat", "https://api.xkiro.invalid/v1"),
        ("openai-responses", "https://api.xkiro.invalid/v1"),
        ("anthropic", "https://api.xkiro.invalid"),
    ],
)
def test_only_the_anthropic_sdk_base_url_drops_the_version_prefix(fmt: str, expected: str) -> None:
    assert custom_provider_sdk_base_url(_xkiro_record(format=fmt)) == expected


def test_a_gateway_without_a_version_prefix_is_left_alone() -> None:
    record = _xkiro_record(format="anthropic", base_url="https://api.xkiro.invalid")
    assert custom_provider_sdk_base_url(record) == "https://api.xkiro.invalid"
    assert custom_provider_sdk_base_url({}) == ""


@pytest.mark.parametrize(
    "record",
    [
        _xkiro_record(enabled=False),
        _xkiro_record(base_url=""),
        _xkiro_record(api_key=""),
        _xkiro_record(selected_model_id=""),
    ],
    ids=["disabled", "no-base-url", "no-key", "no-model"],
)
def test_an_incomplete_provider_cannot_serve_requests(record) -> None:
    section = upsert_custom_provider(default_custom_providers_config(), record, activate=True)

    assert build_custom_provider_runtime_model_data(section, "xkiro") is None


def test_an_empty_section_has_no_runtime_model() -> None:
    assert build_custom_provider_runtime_model_data(default_custom_providers_config()) is None


def test_output_cap_is_the_lower_of_the_provider_and_model_limits() -> None:
    section = upsert_custom_provider(default_custom_providers_config(), _xkiro_record(), activate=True)

    assert build_custom_provider_openai_options(section)["max_tokens"] == 8192
    assert build_custom_provider_openai_options(section, model_id="kiro-mini")["max_tokens"] == 8192


def test_thinking_off_leaves_the_request_completely_plain() -> None:
    record = _xkiro_record(reasoning_effort="off")
    section = upsert_custom_provider(default_custom_providers_config(), record, activate=True)

    assert build_custom_provider_openai_options(section) == {"max_tokens": 8192}
    assert build_custom_provider_runtime_model_data(section)["thinking_mode"] == "false"


# --------------------------------------------------------------------------
# Reasoning depth
# --------------------------------------------------------------------------


def _reasoning_record(**overrides):
    """A record whose catalog publishes its own effort ladder, as xkiro does."""
    record = _xkiro_record(
        models=[
            {
                "id": "codex-spark",
                "display_name": "Codex Spark",
                "context_length": 128000,
                "max_output_tokens": 65536,
                "capabilities": {"vision": False},
                "reasoning_efforts": {
                    "levels": ["low", "medium", "high", "xhigh"],
                    "default": "medium",
                },
            },
            {"id": "plain-mini", "context_length": 32000, "max_output_tokens": 8192},
        ],
        selected_model_id="codex-spark",
        max_tokens=20000,
    )
    record.update(overrides)
    return record


@pytest.fixture(autouse=True)
def clear_reasoning_narrowing():
    reset_custom_provider_reasoning_narrowing()
    yield
    reset_custom_provider_reasoning_narrowing()


def test_reasoning_depth_defaults_to_the_deepest_level_available() -> None:
    assert CUSTOM_PROVIDER_DEFAULT_REASONING_EFFORT == "max"
    assert default_custom_provider()["reasoning_effort"] == "max"


@pytest.mark.parametrize(
    "value,expected",
    [
        ("MAX", "max"),
        ("Extra-High", "xhigh"),
        ("very high", "xhigh"),
        ("balanced", "medium"),
        ("disabled", "off"),
        (True, "max"),
        (False, "off"),
        (0, "off"),
        (3, "max"),
        (None, "max"),
        ("nonsense", "max"),
    ],
)
def test_every_depth_spelling_lands_on_a_rung(value, expected) -> None:
    assert normalize_custom_provider_reasoning_effort(value) == expected


def test_max_resolves_to_the_deepest_level_the_model_publishes() -> None:
    record = _reasoning_record()

    assert resolve_custom_provider_reasoning_level(record) == "xhigh"
    assert resolve_custom_provider_reasoning_level(record, desired="medium") == "medium"
    # ``minimal`` is below every published rung, so the shallowest one stands in
    # rather than silently upgrading to a deep -- or dropping thinking entirely.
    assert resolve_custom_provider_reasoning_level(record, desired="minimal") == "low"
    assert resolve_custom_provider_reasoning_level(record, desired="off") == ""


def test_a_silent_catalog_still_gets_thinking_at_the_safest_deep_level() -> None:
    record = _reasoning_record()

    assert resolve_custom_provider_reasoning_level(record, "plain-mini") == "high"
    assert resolve_custom_provider_reasoning_level(record, "plain-mini", desired="xhigh") == "xhigh"


def test_a_catalog_that_denies_reasoning_is_believed() -> None:
    record = _reasoning_record(
        models=[{"id": "no-think", "context_length": 32000, "capabilities": {"reasoning": False}}],
        selected_model_id="no-think",
    )

    assert resolve_custom_provider_reasoning_level(record) == ""
    assert build_custom_provider_reasoning_extra_body(record) is None
    assert custom_provider_reasoning_options(
        {"id": "no-think", "reasoning": False, "reasoning_levels": []}
    ) == []


def test_the_two_views_of_the_setting_stay_in_agreement() -> None:
    off_by_switch = normalize_custom_provider(_xkiro_record(thinking=False))
    assert off_by_switch["reasoning_effort"] == "off"

    off_by_depth = normalize_custom_provider(_xkiro_record(reasoning_effort="off"))
    assert off_by_depth["thinking"] is False

    deep = normalize_custom_provider(_xkiro_record(thinking=True, reasoning_effort="low"))
    assert (deep["thinking"], deep["reasoning_effort"]) == (True, "low")


def test_the_extra_body_speaks_every_reasoning_dialect_at_once() -> None:
    payload = build_custom_provider_reasoning_extra_body(_reasoning_record(), output_tokens=20000)

    assert payload["reasoning_effort"] == "xhigh"
    assert payload["reasoning"] == {
        "effort": "xhigh",
        "enabled": True,
        "exclude": False,
        "max_tokens": payload["thinking_budget"],
    }
    assert payload["include_reasoning"] is True
    assert payload["enable_thinking"] is True
    assert payload["reasoning_format"] == "parsed"
    assert payload["chat_template_kwargs"] == {"enable_thinking": True, "thinking": True}
    assert payload["thinking"] == {
        "type": "enabled",
        "budget_tokens": payload["thinking_budget"],
    }
    # Every field the narrowing ladder knows about is one this payload can carry.
    assert set(payload) <= set(
        field for tier in CUSTOM_PROVIDER_REASONING_FIELD_TIERS for field in tier
    )


def test_glm_keeps_its_thinking_block_instead_of_having_it_cleared() -> None:
    record = _reasoning_record(
        models=[{"id": "glm-4.6", "context_length": 128000, "max_output_tokens": 32000}],
        selected_model_id="glm-4.6",
    )

    payload = build_custom_provider_reasoning_extra_body(record, output_tokens=20000)

    assert payload["chat_template_kwargs"]["clear_thinking"] is False


def test_the_thinking_budget_always_leaves_room_for_the_answer() -> None:
    assert custom_provider_reasoning_budget("xhigh", 20000) == 16000
    assert custom_provider_reasoning_budget("low", 20000) == 7000
    assert custom_provider_reasoning_budget("off", 20000) == 0
    # Too small to split: a budget that crowds out the reply is worse than none.
    assert custom_provider_reasoning_budget("max", CUSTOM_PROVIDER_MIN_THINKING_BUDGET) == 0
    assert custom_provider_reasoning_budget("max", 0) == 0


def test_a_budget_that_would_not_fit_is_simply_left_out() -> None:
    record = _reasoning_record(
        models=[{"id": "tiny", "context_length": 8000, "max_output_tokens": 512}],
        selected_model_id="tiny",
        max_tokens=512,
    )

    payload = build_custom_provider_reasoning_extra_body(record, output_tokens=512)

    assert payload["reasoning_effort"] == "high"
    assert "thinking_budget" not in payload
    assert "thinking" not in payload
    assert "max_tokens" not in payload["reasoning"]


def test_narrowing_drops_the_most_vendor_specific_tier_first() -> None:
    payload = build_custom_provider_reasoning_extra_body(_reasoning_record(), output_tokens=20000)

    step1 = narrow_custom_provider_reasoning_payload(payload)
    assert set(step1) == {"reasoning", "include_reasoning", "reasoning_effort", "thinking"}

    step2 = narrow_custom_provider_reasoning_payload(step1)
    assert set(step2) == {"reasoning", "reasoning_effort"}

    step3 = narrow_custom_provider_reasoning_payload(step2)
    assert set(step3) == {"reasoning_effort"}

    step4 = narrow_custom_provider_reasoning_payload(step3)
    assert step4 == {}

    # Nothing reasoning-related left means "give up", not "try again with less".
    assert narrow_custom_provider_reasoning_payload(step4) is None
    assert narrow_custom_provider_reasoning_payload(None) is None


def test_a_remembered_narrowing_is_applied_before_the_next_request() -> None:
    record = _reasoning_record()
    full = build_custom_provider_reasoning_extra_body(record, output_tokens=20000)

    remember_custom_provider_reasoning_narrowing("xkiro", "codex-spark", 2)
    narrowed = build_custom_provider_reasoning_extra_body(record, output_tokens=20000)

    assert set(narrowed) == {"reasoning", "reasoning_effort"}
    assert narrowed["reasoning_effort"] == full["reasoning_effort"]
    # A different model on the same provider is unaffected.
    assert "chat_template_kwargs" in (
        build_custom_provider_reasoning_extra_body(record, "plain-mini", output_tokens=20000) or {}
    )

    reset_custom_provider_reasoning_narrowing()
    assert build_custom_provider_reasoning_extra_body(record, output_tokens=20000) == full


def test_anthropic_options_fit_the_budget_inside_the_output_cap() -> None:
    record = _reasoning_record(format="anthropic")
    section = upsert_custom_provider(default_custom_providers_config(), record, activate=True)

    options = build_custom_provider_anthropic_options(section)

    assert options["thinking"]["type"] == "enabled"
    assert options["thinking"]["budget_tokens"] < options["max_tokens"]


def test_responses_options_ask_for_a_reasoning_summary() -> None:
    record = _reasoning_record(format="openai-responses")
    section = upsert_custom_provider(default_custom_providers_config(), record, activate=True)

    options = build_custom_provider_responses_options(section)

    assert options["reasoning"] == {"effort": "xhigh", "summary": "detailed"}
    assert options["include"] == ["reasoning.encrypted_content"]


def test_the_offered_depths_follow_what_the_model_publishes() -> None:
    ladder = [item["id"] for item in custom_provider_reasoning_choices()]
    assert ladder == ["off", "minimal", "low", "medium", "high", "xhigh", "max"]

    published = custom_provider_reasoning_options(
        {"id": "codex-spark", "reasoning": True, "reasoning_levels": ["low", "medium", "high", "xhigh"]}
    )
    assert [item["id"] for item in published] == ["off", "low", "medium", "high", "xhigh", "max"]

    # Silence is not a refusal, so the whole ladder stays on offer.
    silent = custom_provider_reasoning_options({"id": "mystery", "reasoning": None, "reasoning_levels": []})
    assert [item["id"] for item in silent] == ladder


def test_the_runtime_payload_carries_the_resolved_depth() -> None:
    section = upsert_custom_provider(default_custom_providers_config(), _reasoning_record(), activate=True)

    data = build_custom_provider_runtime_model_data(section)

    assert data["thinking_mode"] == "xhigh"
    # The catalog says this model is text-only, so the name hint must not win.
    assert data["supports_vision"] is False


# --------------------------------------------------------------------------
# Availability probes
# --------------------------------------------------------------------------


def test_a_reachable_provider_reports_online_with_its_model_count(monkeypatch) -> None:
    _install_fake_get(monkeypatch, {"data": [{"id": "kiro-pro"}, {"id": "kiro-mini"}]}, [])

    probe = probe_custom_provider(_xkiro_record())

    assert probe.ok is True
    assert probe.status == "online"
    assert probe.model_count == 2
    assert probe.probe == "models"
    assert "models" not in probe.to_dict()


def test_a_reachable_provider_with_no_catalog_reports_empty(monkeypatch) -> None:
    _install_fake_get(monkeypatch, {"data": []}, [])

    probe = probe_custom_provider(_xkiro_record())

    assert probe.status == "empty"
    assert probe.ok is False


@pytest.mark.parametrize(
    ("status_code", "status"),
    [(401, "unauthorized"), (403, "unauthorized"), (404, "error"), (429, "throttled"), (503, "offline")],
)
def test_http_failures_map_onto_actionable_statuses(monkeypatch, status_code: int, status: str) -> None:
    def fake_get(url, *, headers, timeout):
        return FakeResponse(status_code=status_code, text="denied")

    monkeypatch.setattr(cp.requests, "get", fake_get)

    assert probe_custom_provider(_xkiro_record()).status == status


@pytest.mark.parametrize(
    ("exception", "status"),
    [
        (requests.Timeout("slow"), "offline"),
        (requests.ConnectionError("refused"), "offline"),
        (ValueError("not json"), "error"),
    ],
)
def test_transport_failures_are_reported_not_raised(monkeypatch, exception, status: str) -> None:
    def fake_get(url, *, headers, timeout):
        raise exception

    monkeypatch.setattr(cp.requests, "get", fake_get)

    probe = probe_custom_provider(_xkiro_record())
    assert probe.status == status
    assert probe.detail


def test_probe_details_never_echo_the_api_key(monkeypatch) -> None:
    def fake_get(url, *, headers, timeout):
        return FakeResponse(
            status_code=401,
            text="rejected key xk-live-abcdef123456 and token sk-abcdef1234567890",
        )

    monkeypatch.setattr(cp.requests, "get", fake_get)

    detail = probe_custom_provider(_xkiro_record()).detail

    assert "xk-live-abcdef123456" not in detail
    assert "sk-abcdef1234567890" not in detail
    assert "***" in detail


def test_an_unconfigured_provider_is_not_called_at_all(monkeypatch) -> None:
    def fail_get(*args, **kwargs):  # pragma: no cover - must never run
        raise AssertionError("probed a provider with no credentials")

    monkeypatch.setattr(cp.requests, "get", fail_get)

    assert probe_custom_provider(_xkiro_record(api_key="")).status == "unconfigured"
    assert probe_custom_provider(_xkiro_record(base_url="")).status == "unconfigured"


def test_a_keyless_gateway_can_be_probed_anonymously(monkeypatch) -> None:
    calls: list = []
    _install_fake_get(monkeypatch, {"data": [{"id": "free-model"}]}, calls)

    probe = probe_custom_provider(_xkiro_record(api_key=""), require_api_key=False)

    assert probe.status == "online"
    assert "Authorization" not in calls[0]["headers"]


@pytest.mark.parametrize(
    ("provider_format", "path", "expected_keys"),
    [
        ("openai-chat", "/chat/completions", {"model", "max_tokens", "messages"}),
        ("openai-responses", "/responses", {"model", "input", "max_output_tokens"}),
        ("anthropic", "/messages", {"model", "max_tokens", "messages"}),
    ],
)
def test_the_chat_probe_sends_the_smallest_valid_body_for_each_format(
    monkeypatch, provider_format: str, path: str, expected_keys: set
) -> None:
    captured: list = []

    def fake_post(url, *, headers, json, timeout):
        captured.append({"url": url, "headers": dict(headers), "json": json})
        return FakeResponse({"ok": True})

    monkeypatch.setattr(cp.requests, "post", fake_post)

    probe = probe_custom_provider_chat(_xkiro_record(format=provider_format))

    assert probe.status == "online"
    assert probe.probe == "chat"
    assert captured[0]["url"] == f"https://api.xkiro.invalid/v1{path}"
    assert set(captured[0]["json"]) == expected_keys
    assert captured[0]["json"]["model"] == "kiro-pro"
    assert captured[0]["headers"]["Content-Type"] == "application/json"


def test_the_chat_probe_requires_a_model_selection(monkeypatch) -> None:
    def fail_post(*args, **kwargs):  # pragma: no cover - must never run
        raise AssertionError("called chat without a selected model")

    monkeypatch.setattr(cp.requests, "post", fail_post)

    probe = probe_custom_provider_chat(_xkiro_record(selected_model_id=""))

    assert probe.status == "unconfigured"
    assert "models" in probe.detail


# --------------------------------------------------------------------------
# Unified provider table
# --------------------------------------------------------------------------


def _config_with_xkiro(**overrides) -> Config:
    config = Config()
    config.custom_providers = upsert_custom_provider(
        default_custom_providers_config(), _xkiro_record(**overrides), activate=True
    )
    config.active_model_source = "custom"
    return config


def test_the_table_lists_every_builtin_source_alongside_custom_providers() -> None:
    rows = pp.collect_provider_rows(_config_with_xkiro())

    keys = [row.key for row in rows]
    assert keys[: len(EXTERNAL_MODEL_SOURCES)] == list(EXTERNAL_MODEL_SOURCES)
    assert keys[-1] == "custom:xkiro"
    assert [row.kind for row in rows][-1] == "custom"


def test_the_active_custom_provider_is_flagged_in_the_table() -> None:
    rows = pp.collect_provider_rows(_config_with_xkiro())
    row = pp.find_provider_row(rows, "xkiro")

    assert row.active is True
    assert row.configured is True
    assert row.key_state == "set"
    assert row.key_hint == mask_secret("xk-live-abcdef123456")
    assert row.selected_model_display_name == "Kiro Pro"
    assert row.format_label == "OpenAI Chat Completions"


def test_sources_without_a_catalog_endpoint_are_marked_unprobeable() -> None:
    rows = {row.key: row for row in pp.collect_provider_rows(Config())}

    for source in pp.UNPROBEABLE_BUILTIN_SOURCES:
        assert rows[source].probeable is False
        assert rows[source].probe_note
    for source in pp.PROBEABLE_BUILTIN_SOURCES:
        assert rows[source].probeable is True
        assert rows[source].probe_note == ""


def test_a_keyless_builtin_source_is_not_reported_as_missing_a_key() -> None:
    row = {row.key: row for row in pp.collect_provider_rows(Config())}["opencode"]

    assert row.key_state == "n/a"
    assert row.require_api_key is False


def test_a_provider_without_a_key_is_reported_as_unconfigured() -> None:
    config = Config()
    config.custom_providers = upsert_custom_provider(
        default_custom_providers_config(), _xkiro_record(api_key="")
    )

    row = pp.find_provider_row(pp.collect_provider_rows(config), "xkiro")

    assert row.key_state == "missing"
    assert row.configured is False


def test_rows_resolve_by_source_name_provider_id_or_prefix() -> None:
    rows = pp.collect_provider_rows(_config_with_xkiro())

    assert pp.find_provider_row(rows, "codex").source == "codex"
    assert pp.find_provider_row(rows, "custom:xkiro").key == "custom:xkiro"
    assert pp.find_provider_row(rows, "xkir").key == "custom:xkiro"
    assert pp.find_provider_row(rows, "") is None
    assert pp.find_provider_row(rows, "no-such-provider") is None


def test_every_probeable_row_is_checked_concurrently(monkeypatch) -> None:
    config = Config()
    section = default_custom_providers_config()
    for index in range(4):
        section = upsert_custom_provider(
            section,
            _xkiro_record(id=f"relay{index}", name=f"relay{index}", base_url=f"https://r{index}.example.com"),
        )
    config.custom_providers = section

    rows = [row for row in pp.collect_provider_rows(config, include_builtin=False)]
    assert len(rows) == 4

    # Every worker must reach the barrier before any is released, so this only
    # completes if the four probes really do run at the same time.
    barrier = threading.Barrier(4, timeout=15)

    def fake_get(url, *, headers, timeout):
        barrier.wait()
        return FakeResponse({"data": [{"id": "m"}]})

    monkeypatch.setattr(cp.requests, "get", fake_get)

    probes = pp.probe_provider_rows(rows, timeout=5, max_workers=8)

    assert set(probes) == {row.key for row in rows}
    assert all(probe.status == "online" for probe in probes.values())
    assert {probe.name for probe in probes.values()} == {f"relay{index}" for index in range(4)}


def test_probing_nothing_probeable_makes_no_requests(monkeypatch) -> None:
    def fail_get(*args, **kwargs):  # pragma: no cover - must never run
        raise AssertionError("probed an unprobeable row")

    monkeypatch.setattr(cp.requests, "get", fail_get)

    rows = [row for row in pp.collect_provider_rows(Config()) if not row.probeable]

    assert pp.probe_provider_rows(rows) == {}


# --------------------------------------------------------------------------
# Persistence
# --------------------------------------------------------------------------


def _isolated_manager(tmp_path, monkeypatch):
    app_root = tmp_path / "app"
    project_root = tmp_path / "project"
    project_root.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr("reverie.config.get_app_root", lambda: app_root)
    monkeypatch.setattr("reverie.config.get_launcher_root", lambda: app_root)
    return ConfigManager(project_root), project_root


def test_custom_providers_round_trip_through_the_shared_config_file(tmp_path, monkeypatch) -> None:
    config_manager, _ = _isolated_manager(tmp_path, monkeypatch)

    config = config_manager.load()
    assert config.custom_providers == default_custom_providers_config()

    config.custom_providers = upsert_custom_provider(
        config.custom_providers, _xkiro_record(), activate=True
    )
    config.active_model_source = "custom"
    config_manager.save(config)

    reloaded = config_manager.load()
    assert reloaded.active_model_source == "custom"
    assert [record["id"] for record in list_custom_providers(reloaded.custom_providers)] == ["xkiro"]
    assert resolve_active_custom_provider(reloaded.custom_providers)["id"] == "xkiro"

    active = reloaded.active_model
    assert active is not None
    assert active.model == "kiro-pro"
    assert active.base_url == "https://api.xkiro.invalid/v1"
    assert active.provider == "openai-chat"


def test_the_active_model_is_none_while_the_selection_is_incomplete(tmp_path, monkeypatch) -> None:
    config_manager, _ = _isolated_manager(tmp_path, monkeypatch)

    config = config_manager.load()
    config.custom_providers = upsert_custom_provider(
        config.custom_providers, _xkiro_record(selected_model_id=""), activate=True
    )
    config.active_model_source = "custom"
    config_manager.save(config)

    assert config_manager.load().active_model is None


# --------------------------------------------------------------------------
# /provider command surface
# --------------------------------------------------------------------------


def _handler(tmp_path, monkeypatch):
    config_manager, project_root = _isolated_manager(tmp_path, monkeypatch)
    handler = CommandHandler(
        Console(record=True, force_terminal=False, width=160),
        {"config_manager": config_manager, "project_root": project_root},
    )
    return handler, config_manager


def _output(handler) -> str:
    return handler.console.export_text()


def test_provider_is_registered_with_its_alias() -> None:
    handler = CommandHandler(Console(record=True, force_terminal=False, width=120), {})

    assert handler.commands["provider"] == handler.cmd_provider
    assert handler.commands["providers"] == handler.cmd_provider


def test_provider_list_no_probe_makes_no_network_calls(tmp_path, monkeypatch) -> None:
    handler, config_manager = _handler(tmp_path, monkeypatch)

    config = config_manager.load()
    config.custom_providers = upsert_custom_provider(
        config.custom_providers, _xkiro_record(), activate=True
    )
    config.active_model_source = "custom"
    config_manager.save(config)

    def fail_get(*args, **kwargs):  # pragma: no cover - must never run
        raise AssertionError("/provider list --no-probe hit the network")

    monkeypatch.setattr(cp.requests, "get", fail_get)

    assert handler.cmd_provider("list --no-probe") is True

    text = _output(handler)
    assert "xkiro" in text
    assert "Kiro Pro" in text
    assert "built-in" in text
    assert "custom" in text


def test_provider_list_probes_every_configured_source_in_parallel(tmp_path, monkeypatch) -> None:
    handler, config_manager = _handler(tmp_path, monkeypatch)

    config = config_manager.load()
    config.custom_providers = upsert_custom_provider(
        config.custom_providers, _xkiro_record(), activate=True
    )
    config_manager.save(config)

    # Which rows will actually issue a request depends on the credentials the
    # developer's environment happens to expose, so derive the count instead of
    # assuming it -- then make every one of them meet at a barrier, which only
    # clears if they are in flight at the same time.
    rows = pp.collect_provider_rows(config_manager.load())
    live = [
        row
        for row in rows
        if row.probeable
        and row.record.get("base_url")
        and (not row.require_api_key or resolve_custom_provider_api_key(row.record))
    ]
    assert any(row.kind == "custom" for row in live)

    calls: list = []
    barrier = threading.Barrier(len(live), timeout=20)

    def fake_get(url, *, headers, timeout):
        calls.append(url)
        barrier.wait()
        return FakeResponse({"data": [{"id": "m"}]})

    monkeypatch.setattr(cp.requests, "get", fake_get)

    assert handler.cmd_provider("list") is True

    assert sorted(calls) == sorted(row.models_url for row in live)
    text = _output(handler)
    assert "online" in text
    assert "not probed" in text  # codex / webgemini have no catalog endpoint


def _install_fake_selector(monkeypatch, model_id: str) -> None:
    """Replace the full-screen model selector with a headless pick.

    ``ModelSelector`` is handed rows whose ``id`` is the catalog index and whose
    ``metadata['model']`` is the catalog entry, so the fake resolves the wanted
    model id back to that index the same way a keypress would.
    """
    from reverie.cli import tui_selector

    class FakeSelector:
        def __init__(self, *, console, models, current_model=None):
            self._models = list(models)

        def run(self):
            picked = next(
                (row for row in self._models if str((row.get("model") or {}).get("id", "")) == model_id),
                None,
            )
            if picked is None:
                return tui_selector.SelectorResult(action=tui_selector.SelectorAction.CANCEL)
            return tui_selector.SelectorResult(
                action=tui_selector.SelectorAction.SELECT,
                selected_item=tui_selector.SelectorItem(id=picked["id"], title=picked["name"]),
            )

    monkeypatch.setattr(tui_selector, "ModelSelector", FakeSelector)


def _install_fake_prompts(monkeypatch, *answers: str) -> list:
    """Answer Rich prompts in order and record every question that was asked.

    Choosing a model now asks for that model's context limit the first time, so
    command tests declare the answers they expect to be needed; anything asked
    beyond that falls back to the offered default.
    """
    asked: list = []
    remaining = list(answers)

    def fake_ask(prompt="", **kwargs):
        asked.append(str(prompt))
        if remaining:
            return remaining.pop(0)
        return str(kwargs.get("default", "") or "")

    monkeypatch.setattr(commands_module.Prompt, "ask", staticmethod(fake_ask))
    return asked


def test_adding_a_provider_asks_for_exactly_four_fields(tmp_path, monkeypatch) -> None:
    handler, config_manager = _handler(tmp_path, monkeypatch)

    asked: list = []
    answers = iter(
        ["xkiro", "api.xkiro.invalid/v1/chat/completions", "xk-live-abcdef123456", "1", "256k"]
    )

    def fake_ask(prompt="", **kwargs):
        asked.append(str(prompt))
        return next(answers)

    monkeypatch.setattr(commands_module.Prompt, "ask", staticmethod(fake_ask))
    _install_fake_get(
        monkeypatch,
        {"data": [{"id": "kiro-pro", "context_length": 200000}, {"id": "kiro-mini"}]},
        [],
    )
    _install_fake_selector(monkeypatch, "kiro-pro")

    assert handler.cmd_provider("add") is True

    # Exactly four questions describe the provider: name, base URL, API key,
    # request format.  The only extra question belongs to the chosen model, and
    # it is asked once per model rather than once per provider.
    assert len(asked) == 5
    assert "Context limit" in asked[4]

    reloaded = config_manager.load()
    record = find_custom_provider(reloaded.custom_providers, "xkiro")
    assert record is not None
    assert record["base_url"] == "https://api.xkiro.invalid/v1"  # request path trimmed
    assert record["api_key"] == "xk-live-abcdef123456"
    assert record["format"] == "openai-chat"
    assert record["selected_model_id"] == "kiro-pro"
    assert record["model_context_limits"] == {"kiro-pro": 256000}
    assert record["models_synced_at"] > 0
    assert reloaded.active_model_source == "custom"


def test_adding_a_provider_refuses_a_builtin_source_name(tmp_path, monkeypatch) -> None:
    handler, config_manager = _handler(tmp_path, monkeypatch)

    monkeypatch.setattr(commands_module.Prompt, "ask", staticmethod(lambda prompt="", **kwargs: "codex"))

    assert handler.cmd_provider("add") is True
    assert "built-in source name" in _output(handler)
    assert list_custom_providers(config_manager.load().custom_providers) == []


def test_adding_a_provider_refuses_a_duplicate_id(tmp_path, monkeypatch) -> None:
    handler, config_manager = _handler(tmp_path, monkeypatch)

    config = config_manager.load()
    config.custom_providers = upsert_custom_provider(config.custom_providers, _xkiro_record())
    config_manager.save(config)

    monkeypatch.setattr(commands_module.Prompt, "ask", staticmethod(lambda prompt="", **kwargs: "xkiro"))

    assert handler.cmd_provider("add") is True
    assert "already exists" in _output(handler)


def test_selecting_a_model_by_query_skips_the_selector(tmp_path, monkeypatch) -> None:
    handler, config_manager = _handler(tmp_path, monkeypatch)

    config = config_manager.load()
    config.custom_providers = upsert_custom_provider(
        config.custom_providers, _xkiro_record(selected_model_id="")
    )
    config_manager.save(config)

    _install_fake_get(monkeypatch, {"data": [{"id": "kiro-pro"}, {"id": "kiro-mini"}]}, [])
    _install_fake_prompts(monkeypatch, "64k")

    assert handler.cmd_provider("xkiro models kiro-mini") is True

    record = find_custom_provider(config_manager.load().custom_providers, "xkiro")
    assert record["selected_model_id"] == "kiro-mini"
    assert config_manager.load().active_model_source == "custom"


def test_a_models_context_limit_is_asked_once_and_reused_afterwards(tmp_path, monkeypatch) -> None:
    handler, config_manager = _handler(tmp_path, monkeypatch)

    config = config_manager.load()
    config.custom_providers = upsert_custom_provider(
        config.custom_providers, _xkiro_record(selected_model_id="")
    )
    config_manager.save(config)

    _install_fake_get(monkeypatch, {"data": [{"id": "kiro-pro"}, {"id": "kiro-mini"}]}, [])
    asked = _install_fake_prompts(monkeypatch, "64k")

    assert handler.cmd_provider("xkiro models kiro-mini") is True

    assert len(asked) == 1
    assert "Context limit" in asked[0]
    record = find_custom_provider(config_manager.load().custom_providers, "xkiro")
    assert record["model_context_limits"] == {"kiro-mini": 64000}

    # Choosing the same model again reuses the stored limit without asking.
    cp._MODEL_CACHE.clear()
    asked.clear()
    assert handler.cmd_provider("xkiro models kiro-mini") is True

    assert asked == []
    assert "64,000 tokens (saved earlier)" in _output(handler)

    # A different model of the same provider still owes an answer.
    asked.clear()
    cp._MODEL_CACHE.clear()
    assert handler.cmd_provider("xkiro models kiro-pro") is True

    assert len(asked) == 1
    limits = find_custom_provider(config_manager.load().custom_providers, "xkiro")[
        "model_context_limits"
    ]
    assert limits == {"kiro-mini": 64000, "kiro-pro": CUSTOM_PROVIDER_DEFAULT_CONTEXT_TOKENS}


def test_the_saved_limit_drives_the_runtime_model_after_a_catalog_refresh(
    tmp_path, monkeypatch
) -> None:
    handler, config_manager = _handler(tmp_path, monkeypatch)

    config = config_manager.load()
    config.custom_providers = upsert_custom_provider(
        config.custom_providers, _xkiro_record(selected_model_id="")
    )
    config_manager.save(config)

    # The gateway publishes 200k; the user says 256k, and the user wins.
    _install_fake_get(monkeypatch, {"data": [{"id": "kiro-pro", "context_length": 200000}]}, [])
    _install_fake_prompts(monkeypatch, "256k")

    assert handler.cmd_provider("xkiro models kiro-pro") is True

    section = config_manager.load().custom_providers
    assert build_custom_provider_runtime_model_data(section)["max_context_tokens"] == 256000


def test_the_context_command_stores_a_typed_limit(tmp_path, monkeypatch) -> None:
    handler, config_manager = _handler(tmp_path, monkeypatch)

    config = config_manager.load()
    config.custom_providers = upsert_custom_provider(
        config.custom_providers, _xkiro_record(), activate=True
    )
    config_manager.save(config)

    assert handler.cmd_provider("xkiro context 256k") is True

    record = find_custom_provider(config_manager.load().custom_providers, "xkiro")
    assert record["model_context_limits"] == {"kiro-pro": 256000}
    assert "256,000 tokens" in _output(handler)


def test_the_context_command_refuses_a_nonsense_limit(tmp_path, monkeypatch) -> None:
    handler, config_manager = _handler(tmp_path, monkeypatch)

    config = config_manager.load()
    config.custom_providers = upsert_custom_provider(config.custom_providers, _xkiro_record())
    config_manager.save(config)

    assert handler.cmd_provider("xkiro context plenty") is True

    assert "not a usable context limit" in _output(handler)
    assert find_custom_provider(config_manager.load().custom_providers, "xkiro")[
        "model_context_limits"
    ] == {}


def test_the_context_command_needs_a_selected_model(tmp_path, monkeypatch) -> None:
    handler, config_manager = _handler(tmp_path, monkeypatch)

    config = config_manager.load()
    config.custom_providers = upsert_custom_provider(
        config.custom_providers, _xkiro_record(selected_model_id="")
    )
    config_manager.save(config)

    assert handler.cmd_provider("xkiro context 256k") is True

    assert "no model selected yet" in _output(handler)


def test_the_thinking_command_turns_the_stored_flag_off_and_back_on(tmp_path, monkeypatch) -> None:
    handler, config_manager = _handler(tmp_path, monkeypatch)

    config = config_manager.load()
    config.custom_providers = upsert_custom_provider(config.custom_providers, _xkiro_record())
    config_manager.save(config)

    assert handler.cmd_provider("xkiro thinking off") is True
    stored = find_custom_provider(config_manager.load().custom_providers, "xkiro")
    assert (stored["thinking"], stored["reasoning_effort"]) == (False, "off")

    assert handler.cmd_provider("xkiro thinking on") is True
    stored = find_custom_provider(config_manager.load().custom_providers, "xkiro")
    assert (stored["thinking"], stored["reasoning_effort"]) == (True, "max")

    assert handler.cmd_provider("xkiro thinking toggle") is True
    assert find_custom_provider(config_manager.load().custom_providers, "xkiro")["thinking"] is False


def test_the_thinking_command_also_sets_the_depth(tmp_path, monkeypatch) -> None:
    handler, config_manager = _handler(tmp_path, monkeypatch)

    config = config_manager.load()
    config.custom_providers = upsert_custom_provider(config.custom_providers, _reasoning_record())
    config_manager.save(config)

    assert handler.cmd_provider("xkiro thinking medium") is True
    stored = find_custom_provider(config_manager.load().custom_providers, "xkiro")
    assert (stored["thinking"], stored["reasoning_effort"]) == (True, "medium")

    # An alias for a rung is accepted, and the resolved level is shown alongside.
    assert handler.cmd_provider("xkiro thinking extra-high") is True
    assert find_custom_provider(config_manager.load().custom_providers, "xkiro")["reasoning_effort"] == "xhigh"

    assert handler.cmd_provider("xkiro thinking status") is True
    assert handler.cmd_provider("xkiro thinking as deep as it goes") is True
    text = _output(handler)
    assert "xhigh" in text
    assert "off, low, medium, high, xhigh, max" in text
    # ``max`` is a wish; the detail view reports the rung the request will carry.
    assert handler.cmd_provider("xkiro thinking max") is True
    assert handler.cmd_provider("xkiro") is True
    assert "max" in _output(handler)


def test_context_and_thinking_are_custom_only(tmp_path, monkeypatch) -> None:
    handler, _ = _handler(tmp_path, monkeypatch)

    assert handler.cmd_provider("codex context 256k") is True
    assert handler.cmd_provider("codex thinking off") is True

    assert _output(handler).count("built-in source") == 2


def test_action_first_word_order_is_accepted(tmp_path, monkeypatch) -> None:
    handler, config_manager = _handler(tmp_path, monkeypatch)

    config = config_manager.load()
    config.custom_providers = upsert_custom_provider(config.custom_providers, _xkiro_record())
    config_manager.save(config)

    _install_fake_get(monkeypatch, {"data": [{"id": "kiro-pro"}, {"id": "kiro-mini"}]}, [])
    _install_fake_prompts(monkeypatch, "64k")

    assert handler.cmd_provider("models xkiro kiro-mini") is True
    assert find_custom_provider(config_manager.load().custom_providers, "xkiro")["selected_model_id"] == "kiro-mini"


def test_an_unknown_provider_lists_the_known_ones(tmp_path, monkeypatch) -> None:
    handler, _ = _handler(tmp_path, monkeypatch)

    assert handler.cmd_provider("nope models") is True

    text = _output(handler)
    assert "Unknown provider" in text
    assert "codex" in text


@pytest.mark.parametrize("action", ["url", "format", "rename", "remove", "disable"])
def test_builtin_sources_reject_custom_only_edits(tmp_path, monkeypatch, action: str) -> None:
    handler, _ = _handler(tmp_path, monkeypatch)

    assert handler.cmd_provider(f"codex {action}") is True
    assert "built-in source" in _output(handler)


def test_disabling_the_active_provider_falls_back_to_manual_models(tmp_path, monkeypatch) -> None:
    handler, config_manager = _handler(tmp_path, monkeypatch)

    config = config_manager.load()
    config.custom_providers = upsert_custom_provider(
        config.custom_providers, _xkiro_record(), activate=True
    )
    config.active_model_source = "custom"
    config_manager.save(config)

    assert handler.cmd_provider("xkiro disable") is True

    reloaded = config_manager.load()
    assert find_custom_provider(reloaded.custom_providers, "xkiro")["enabled"] is False
    assert reloaded.active_model_source == "standard"


def test_removing_a_provider_deletes_it_from_the_config(tmp_path, monkeypatch) -> None:
    handler, config_manager = _handler(tmp_path, monkeypatch)

    config = config_manager.load()
    config.custom_providers = upsert_custom_provider(
        config.custom_providers, _xkiro_record(), activate=True
    )
    config.active_model_source = "custom"
    config_manager.save(config)

    monkeypatch.setattr(commands_module.Confirm, "ask", staticmethod(lambda *args, **kwargs: True))

    assert handler.cmd_provider("xkiro remove") is True

    reloaded = config_manager.load()
    assert list_custom_providers(reloaded.custom_providers) == []
    assert reloaded.active_model_source == "standard"


def test_provider_help_documents_the_command_surface() -> None:
    assert normalize_help_topic("/provider") == "provider"
    assert normalize_help_topic("providers") == "provider"
    assert normalize_help_topic("custom") == "provider"

    topic = HELP_TOPICS["provider"]
    assert topic["command"] == "/provider"
    subcommands = " ".join(str(item) for item in topic["subcommands"])
    for expected in (
        "list",
        "add",
        "models",
        "test",
        "use",
        "key",
        "url",
        "format",
        "remove",
        "context",
        "thinking",
    ):
        assert expected in subcommands
