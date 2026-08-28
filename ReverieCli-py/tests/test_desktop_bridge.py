import json
from pathlib import Path
import threading
from types import SimpleNamespace

import pytest

from reverie.config import Config, ModelConfig
from reverie.desktop_catalog import (
    add_standard_model,
    apply_model_selection,
    build_model_sources_payload,
    delete_standard_model,
    update_standard_model,
)
from reverie.session.manager import SessionManager, session_title_from_prompt
from reverie.sdk_bridge import _desktop_tool_record


def test_kernel_info_contract(capsys) -> None:
    from reverie.__main__ import main

    assert main(["--kernel-info"]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["schema"] == "reverie.kernel.v1"
    assert payload["version"] == "2.5.0"
    assert payload["bridge_protocol"] == "sdk-bridge.v1"
    assert payload["platform"]
    assert payload["arch"]


def _source(payload: dict, source_id: str) -> dict:
    return next(item for item in payload["sources"] if item["id"] == source_id)


def test_desktop_catalog_uses_native_model_reasoning_metadata() -> None:
    config = Config()
    payload = build_model_sources_payload(config)
    assert "unlimitedsurf" not in {source["id"] for source in payload["sources"]}

    assert {item["id"] for item in payload["sources"]} >= {
        "standard",
        "codex",
        "nvidia",
        "sensenova",
        "agnes",
    }

    standard = _source(payload, "standard")
    if not standard["models"]:
        assert standard["selected_reasoning"] == {"control": "none", "options": [], "value": ""}

    codex = _source(payload, "codex")
    assert codex["models"]
    assert codex["models"][0]["reasoning"]["control"] == "effort"
    assert {item["id"] for item in codex["models"][0]["reasoning"]["options"]} >= {
        "low",
        "medium",
        "high",
    }

    nvidia = _source(payload, "nvidia")
    toggle_model = next(item for item in nvidia["models"] if item["reasoning"]["control"] == "toggle")
    assert {item["id"] for item in toggle_model["reasoning"]["options"]} == {"true", "false"}

    agnes = _source(payload, "agnes")
    pro = next(item for item in agnes["models"] if item["id"] == "agnes-2.5-pro-alpha")
    assert pro["thinking"] is True
    assert pro["reasoning"]["control"] == "effort"
    assert [item["id"] for item in pro["reasoning"]["options"]] == ["none", "low", "medium", "high"]
    assert agnes["modalities"] == {"live": False, "llm": 3, "tti": 2, "ttv": 1}

    opencode = _source(payload, "opencode")
    deepseek = next(item for item in opencode["models"] if item["id"] == "deepseek-v4-flash-free")
    assert deepseek["reasoning"]["control"] == "effort"
    assert [item["id"] for item in deepseek["reasoning"]["options"]] == ["low", "high", "max"]

    modelscope = _source(payload, "modelscope")
    step = next(item for item in modelscope["models"] if item["id"] == "stepfun-ai/Step-3.7-Flash")
    assert step["vision"] is True
    assert [item["id"] for item in step["reasoning"]["options"]] == ["low", "medium", "high"]
    modelscope_deepseek = next(
        item for item in modelscope["models"] if item["id"] == "deepseek-ai/DeepSeek-V4-Flash"
    )
    assert modelscope_deepseek["reasoning"]["control"] == "toggle"
    assert [item["id"] for item in modelscope_deepseek["reasoning"]["options"]] == ["true", "false"]

    for source in payload["sources"]:
        for model in source["models"]:
            assert isinstance(model["vision"], bool)
            assert isinstance(model["thinking"], bool)
            reasoning = model["reasoning"]
            assert isinstance(reasoning["options"], list)
            if reasoning["options"]:
                assert reasoning["control"] in {"effort", "toggle"}
                assert reasoning["value"] in {item["id"] for item in reasoning["options"]}


def test_desktop_live_refresh_passes_sensenova_config_to_provider(monkeypatch) -> None:
    from reverie import sensenova as sensenova_module

    captured = {}

    def fake_catalog(provider_config, *, fetch_live=False, force_refresh=False):
        captured.update(
            provider_config=dict(provider_config),
            fetch_live=fetch_live,
            force_refresh=force_refresh,
        )
        return [{
            "id": "future-chat-model",
            "display_name": "Future Chat Model",
            "description": "Discovered live.",
            "transport": "openai-chat",
            "context_length": 123_456,
            "max_output_tokens": 7_890,
            "vision": False,
            "thinking": False,
            "tool_calling": True,
            "thinking_control": "none",
            "thinking_options": [],
            "default_thinking_choice": "",
            "catalog_source": "api",
        }]

    monkeypatch.setattr(sensenova_module, "get_sensenova_model_catalog", fake_catalog)
    config = Config(sensenova={"api_key": "sense-test", "selected_model_id": "future-chat-model"})

    payload = build_model_sources_payload(config, fetch_live=True)
    source = _source(payload, "sensenova")

    assert captured["provider_config"]["api_key"] == "sense-test"
    assert captured["fetch_live"] is True
    assert captured["force_refresh"] is True
    assert [item["id"] for item in source["models"]] == ["future-chat-model"]
    assert source["catalog_live"] is True


def test_model_selection_updates_model_specific_reasoning() -> None:
    config = Config()
    selected = apply_model_selection(config, "codex", "gpt-5.6-sol", "high")
    assert selected["id"] == "gpt-5.6-sol"
    assert config.active_model_source == "codex"
    assert config.codex["reasoning_effort"] == "high"

    nvidia_payload = build_model_sources_payload(config)
    nvidia = _source(nvidia_payload, "nvidia")
    toggle_model = next(item for item in nvidia["models"] if item["reasoning"]["control"] == "toggle")
    apply_model_selection(config, "nvidia", toggle_model["id"], "false")
    assert config.nvidia["selected_model_id"] == toggle_model["id"]
    assert config.nvidia["enable_thinking"] is False

    apply_model_selection(config, "opencode", "hy3-free", "high")
    assert config.opencode["selected_model_id"] == "hy3-free"
    assert config.opencode["reasoning_effort"] == "high"

    apply_model_selection(config, "modelscope", "ZhipuAI/GLM-5.2", "none")
    assert config.modelscope["selected_model_id"] == "ZhipuAI/GLM-5.2"
    assert config.modelscope["reasoning_effort"] == "none"


def _custom_provider_config() -> Config:
    """A config whose active source is one user-added provider.

    The base URL uses the reserved ``.invalid`` TLD so a code path that skips
    the fake transport fails loudly instead of calling a real gateway.
    """
    from reverie.custom_providers import default_custom_providers_config, upsert_custom_provider

    config = Config()
    config.custom_providers = upsert_custom_provider(
        default_custom_providers_config(),
        {
            "id": "xkiro",
            "name": "xkiro",
            "base_url": "https://api.xkiro.invalid/v1",
            "api_key": "xk-live-abcdef123456",
            "format": "openai-chat",
            "models": [
                {"id": "kiro-pro", "display_name": "Kiro Pro", "context_length": 200000},
                {"id": "kiro-mini", "display_name": "Kiro Mini", "context_length": 32000},
            ],
            "selected_model_id": "kiro-pro",
        },
        activate=True,
    )
    config.active_model_source = "custom"
    return config


def test_desktop_catalog_exposes_the_active_custom_provider_without_its_key() -> None:
    payload = build_model_sources_payload(_custom_provider_config())
    source = _source(payload, "custom")

    assert source["active"] is True
    assert source["selected_model_id"] == "kiro-pro"
    assert [item["id"] for item in source["models"]] == ["kiro-pro", "kiro-mini"]
    assert source["config"]["values"]["base_url"] == "https://api.xkiro.invalid/v1"
    assert source["config"]["values"]["api_key"] == ""
    assert source["config"]["configured_secrets"]["api_key"] is True


def test_desktop_catalog_reports_no_models_until_a_custom_provider_exists() -> None:
    source = _source(build_model_sources_payload(Config()), "custom")

    assert source["models"] == []
    assert source["active"] is False


def test_desktop_model_selection_writes_back_to_the_custom_provider_record(monkeypatch) -> None:
    from reverie import custom_providers as custom_providers_module
    from reverie.custom_providers import find_custom_provider

    class FakeResponse:
        def raise_for_status(self):
            return None

        def json(self):
            return {"data": [{"id": "kiro-pro"}, {"id": "kiro-mini", "context_length": 32000}]}

    def fake_get(url, *, headers, timeout):
        return FakeResponse()

    monkeypatch.setattr(custom_providers_module.requests, "get", fake_get)
    config = _custom_provider_config()

    selected = apply_model_selection(config, "custom", "kiro-mini")

    assert selected["id"] == "kiro-mini"
    assert config.active_model_source == "custom"
    record = find_custom_provider(config.custom_providers, "xkiro")
    assert record["selected_model_id"] == "kiro-mini"
    assert record["max_context_tokens"] == 32000


def test_desktop_provider_patches_are_refused_for_custom_providers() -> None:
    from reverie.desktop_catalog import apply_provider_config_patch

    with pytest.raises(ValueError, match="/provider"):
        apply_provider_config_patch(
            _custom_provider_config(), "custom", {"base_url": "https://x.invalid"}
        )


class _FakeCatalogResponse:
    """Minimal stand-in for the ``requests`` response of a ``/models`` call."""

    def __init__(self, model_ids=("kiro-pro", "kiro-mini")) -> None:
        self._model_ids = list(model_ids)

    def raise_for_status(self) -> None:
        return None

    def json(self):
        return {"data": [{"id": model_id} for model_id in self._model_ids]}


def _install_fake_catalog(monkeypatch, model_ids=("kiro-pro", "kiro-mini")) -> list:
    """Serve one canned catalog and record the URLs that were asked for."""
    from reverie import custom_providers as custom_providers_module

    calls: list = []

    def fake_get(url, *, headers, timeout):
        calls.append(url)
        return _FakeCatalogResponse(model_ids)

    monkeypatch.setattr(custom_providers_module.requests, "get", fake_get)
    return calls


def _two_custom_providers() -> Config:
    """One active provider plus a second, so activation is observable."""
    from reverie.custom_providers import upsert_custom_provider

    config = _custom_provider_config()
    config.custom_providers = upsert_custom_provider(
        config.custom_providers,
        {
            "id": "relay",
            "name": "My Relay",
            "base_url": "https://relay.invalid",
            "api_key": "sk-relay-987654321",
            "format": "anthropic",
            "models": [{"id": "claude-x", "display_name": "Claude X", "context_length": 64000}],
        },
    )
    return config


def test_desktop_payload_lists_every_custom_provider_without_its_key() -> None:
    from reverie.custom_providers import CUSTOM_PROVIDER_FORMATS

    source = _source(build_model_sources_payload(_two_custom_providers()), "custom")

    providers = source["custom_providers"]
    assert [item["id"] for item in providers] == ["xkiro", "relay"]
    assert [item["active"] for item in providers] == [True, False]
    assert providers[0]["api_key_masked"] == "xk-l...3456"
    assert providers[0]["api_key_configured"] is True
    assert providers[0]["api_key_source"] == "config"
    assert providers[1]["format_label"] == "Anthropic Messages"
    assert providers[1]["models_url"] == "https://relay.invalid/models"
    assert "xk-live-abcdef123456" not in json.dumps(source)
    assert [item["id"] for item in source["custom_provider_formats"]] == list(CUSTOM_PROVIDER_FORMATS)


def test_desktop_add_custom_provider_uses_four_fields_and_pulls_the_catalog(monkeypatch) -> None:
    from reverie.desktop_catalog import create_custom_provider

    calls = _install_fake_catalog(monkeypatch)
    config = Config()

    provider = create_custom_provider(
        config,
        {
            # A pasted request URL, not a bare base: the suffix is trimmed for us.
            "base_url": "api.xkiro.invalid/v1/chat/completions",
            "api_key": "xk-live-abcdef123456",
            "format": "openai-chat",
            "name": "xKiro Relay",
        },
    )

    assert calls == ["https://api.xkiro.invalid/v1/models"]
    assert provider["id"] == "xkiro-relay"
    assert provider["name"] == "xKiro Relay"
    assert provider["base_url"] == "https://api.xkiro.invalid/v1"
    assert [item["id"] for item in provider["models"]] == ["kiro-mini", "kiro-pro"]
    assert provider["models_synced_at"] > 0
    assert "sync_error" not in provider
    # Adding stocks the catalog; picking a model is the separate, activating step.
    assert provider["selected_model_id"] == ""
    assert config.active_model_source == "standard"


@pytest.mark.parametrize(
    ("field", "value", "message"),
    [
        ("name", "", "letters or digits"),
        ("name", "!!!", "letters or digits"),
        ("base_url", "", "base URL is required"),
        ("api_key", "", "API key is required"),
    ],
)
def test_desktop_add_custom_provider_requires_each_field(field, value, message) -> None:
    from reverie.desktop_catalog import create_custom_provider

    payload = {
        "name": "xkiro",
        "base_url": "https://api.xkiro.invalid/v1",
        "api_key": "xk-live-abcdef123456",
        "format": "openai-chat",
    }
    payload[field] = value

    with pytest.raises(ValueError, match=message):
        create_custom_provider(Config(), payload)


@pytest.mark.parametrize("name", ["codex", "sensenova", "standard", "custom"])
def test_desktop_add_custom_provider_refuses_built_in_source_names(name) -> None:
    from reverie.desktop_catalog import create_custom_provider

    with pytest.raises(ValueError, match="built-in source name"):
        create_custom_provider(
            Config(),
            {
                "name": name,
                "base_url": "https://api.xkiro.invalid/v1",
                "api_key": "xk-live-abcdef123456",
                "format": "openai-chat",
            },
        )


def test_desktop_add_custom_provider_refuses_a_duplicate() -> None:
    from reverie.desktop_catalog import create_custom_provider

    with pytest.raises(ValueError, match="already exists"):
        create_custom_provider(
            _custom_provider_config(),
            {
                "name": "xkiro",
                "base_url": "https://api.xkiro.invalid/v1",
                "api_key": "xk-live-abcdef123456",
                "format": "openai-chat",
            },
        )


def test_desktop_add_custom_provider_keeps_the_record_when_the_catalog_call_fails(monkeypatch) -> None:
    """A wrong URL should not discard the other three fields the user typed."""
    from reverie import custom_providers as custom_providers_module
    from reverie.custom_providers import find_custom_provider
    from reverie.desktop_catalog import create_custom_provider

    def fake_get(url, *, headers, timeout):
        raise custom_providers_module.requests.ConnectionError("name resolution failed")

    monkeypatch.setattr(custom_providers_module.requests, "get", fake_get)
    config = Config()

    provider = create_custom_provider(
        config,
        {
            "name": "xkiro",
            "base_url": "https://api.xkiro.invalid/v1",
            "api_key": "xk-live-abcdef123456",
            "format": "openai-chat",
        },
    )

    assert provider["models"] == []
    assert "name resolution failed" in provider["sync_error"]
    assert find_custom_provider(config.custom_providers, "xkiro") is not None


def test_desktop_update_custom_provider_preserves_an_omitted_key(monkeypatch) -> None:
    from reverie.custom_providers import find_custom_provider
    from reverie.desktop_catalog import update_custom_provider

    calls = _install_fake_catalog(monkeypatch, ("kiro-pro", "kiro-ultra"))
    config = _custom_provider_config()

    provider = update_custom_provider(
        config, "xkiro", {"name": "xKiro EU", "base_url": "https://eu.xkiro.invalid/v1", "api_key": ""}
    )

    assert provider["name"] == "xKiro EU"
    assert provider["base_url"] == "https://eu.xkiro.invalid/v1"
    # The endpoint moved, so the catalog is re-read rather than left stale.
    assert calls == ["https://eu.xkiro.invalid/v1/models"]
    assert [item["id"] for item in provider["models"]] == ["kiro-pro", "kiro-ultra"]
    assert find_custom_provider(config.custom_providers, "xkiro")["api_key"] == "xk-live-abcdef123456"


def test_desktop_update_custom_provider_leaves_the_catalog_alone_for_a_rename(monkeypatch) -> None:
    from reverie.desktop_catalog import update_custom_provider

    calls = _install_fake_catalog(monkeypatch)

    update_custom_provider(_custom_provider_config(), "xkiro", {"name": "Renamed"})

    assert calls == []


def test_desktop_update_custom_provider_rejects_undeclared_fields() -> None:
    from reverie.desktop_catalog import update_custom_provider

    with pytest.raises(ValueError, match="Unsupported custom provider field"):
        update_custom_provider(_custom_provider_config(), "xkiro", {"max_tokens": 999})


def test_desktop_select_custom_provider_model_activates_that_provider() -> None:
    from reverie.custom_providers import find_custom_provider
    from reverie.desktop_catalog import select_custom_provider_model

    config = _two_custom_providers()

    provider = select_custom_provider_model(config, "relay", "claude-x")

    assert provider["id"] == "relay"
    assert provider["active"] is True
    assert provider["selected_model_id"] == "claude-x"
    assert config.active_model_source == "custom"
    assert config.custom_providers["active_provider_id"] == "relay"
    assert find_custom_provider(config.custom_providers, "relay")["max_context_tokens"] == 64000


def test_desktop_select_custom_provider_model_refuses_a_model_outside_the_catalog() -> None:
    from reverie.desktop_catalog import select_custom_provider_model

    with pytest.raises(ValueError, match="Refresh it first"):
        select_custom_provider_model(_custom_provider_config(), "xkiro", "gpt-9")


def test_desktop_payload_reports_which_models_still_owe_a_context_limit() -> None:
    from reverie.custom_providers import set_custom_provider_model_context_limit, upsert_custom_provider

    config = _custom_provider_config()
    config.custom_providers = upsert_custom_provider(
        config.custom_providers,
        set_custom_provider_model_context_limit(
            next(item for item in config.custom_providers["providers"] if item["id"] == "xkiro"),
            "kiro-pro",
            256000,
        ),
    )

    provider = _source(build_model_sources_payload(config), "custom")["custom_providers"][0]

    assert provider["thinking"] is True  # on by default
    assert provider["model_context_limits"] == {"kiro-pro": 256000}
    models = {item["id"]: item for item in provider["models"]}
    assert models["kiro-pro"]["context_limit"] == 256000
    assert models["kiro-pro"]["needs_context_limit"] is False
    # Never chosen, so the desktop knows to ask once before using it.
    assert models["kiro-mini"]["context_limit"] == 0
    assert models["kiro-mini"]["needs_context_limit"] is True
    assert models["kiro-mini"]["suggested_context_limit"] == 32000


def test_desktop_selection_saves_the_confirmed_context_limit_once() -> None:
    from reverie.custom_providers import find_custom_provider
    from reverie.desktop_catalog import select_custom_provider_model

    config = _custom_provider_config()

    provider = select_custom_provider_model(config, "xkiro", "kiro-mini", "64k")

    assert provider["selected_model_id"] == "kiro-mini"
    assert provider["model_context_limits"] == {"kiro-mini": 64000}
    assert provider["max_context_tokens"] == 64000  # the answer beats the published 32000

    # Selecting it again without a limit reuses the saved one instead of resetting it.
    select_custom_provider_model(config, "xkiro", "kiro-mini")
    record = find_custom_provider(config.custom_providers, "xkiro")
    assert record["model_context_limits"] == {"kiro-mini": 64000}


def test_desktop_selection_without_an_answer_falls_back_to_the_suggestion() -> None:
    from reverie.desktop_catalog import select_custom_provider_model

    provider = select_custom_provider_model(_custom_provider_config(), "xkiro", "kiro-mini")

    # No model is ever left without a limit, even if the desktop skips the ask.
    assert provider["model_context_limits"] == {"kiro-mini": 32000}


def test_desktop_selection_refuses_a_nonsense_context_limit() -> None:
    from reverie.desktop_catalog import select_custom_provider_model

    with pytest.raises(ValueError, match="not a usable context limit"):
        select_custom_provider_model(_custom_provider_config(), "xkiro", "kiro-mini", "plenty")


def test_desktop_update_custom_provider_toggles_thinking_mode(monkeypatch) -> None:
    from reverie.custom_providers import find_custom_provider
    from reverie.desktop_catalog import update_custom_provider

    calls = _install_fake_catalog(monkeypatch)
    config = _custom_provider_config()

    provider = update_custom_provider(config, "xkiro", {"thinking": False})

    assert provider["thinking"] is False
    assert find_custom_provider(config.custom_providers, "xkiro")["thinking"] is False
    assert calls == []  # a local flag, so the catalog is left alone

    assert update_custom_provider(config, "xkiro", {"thinking": True})["thinking"] is True


def test_desktop_command_palette_grows_with_each_custom_provider() -> None:
    from reverie.sdk_bridge import ReverieSdkBridge

    config = _two_custom_providers()
    bridge = ReverieSdkBridge()
    bridge.ensure_interface = lambda *args, **kwargs: SimpleNamespace(
        config_manager=SimpleNamespace(load=lambda: config)
    )

    entries = {item["command"]: item for item in bridge.commands_payload()["items"]}

    assert "/provider" in entries  # the built-in topic is still listed
    for provider_id in ("xkiro", "relay"):
        entry = entries[f"/provider {provider_id}"]
        assert entry["section"] == "Providers"
        usages = [item["usage"] for item in entry["subcommands"]]
        for action in ("models", "test", "use", "context", "thinking", "remove"):
            assert f"/provider {provider_id} {action}" in usages


def test_desktop_command_palette_is_unchanged_without_custom_providers() -> None:
    from reverie.sdk_bridge import ReverieSdkBridge

    bridge = ReverieSdkBridge()
    bridge.ensure_interface = lambda *args, **kwargs: SimpleNamespace(
        config_manager=SimpleNamespace(load=lambda: Config())
    )

    commands = [item["command"] for item in bridge.commands_payload()["items"]]

    assert "/provider" in commands
    assert not any(command.startswith("/provider ") for command in commands)


def test_desktop_delete_custom_provider_falls_back_to_the_standard_source() -> None:
    from reverie.custom_providers import find_custom_provider
    from reverie.desktop_catalog import delete_custom_provider

    config = _custom_provider_config()

    delete_custom_provider(config, "xkiro")

    assert find_custom_provider(config.custom_providers, "xkiro") is None
    assert config.active_model_source == "standard"


def test_desktop_delete_custom_provider_keeps_custom_active_when_another_remains() -> None:
    from reverie.desktop_catalog import delete_custom_provider, select_custom_provider_model

    config = _two_custom_providers()
    select_custom_provider_model(config, "relay", "claude-x")

    delete_custom_provider(config, "xkiro")

    assert config.active_model_source == "custom"
    assert config.custom_providers["active_provider_id"] == "relay"


def test_desktop_disabling_the_active_custom_provider_falls_back_to_standard() -> None:
    from reverie.desktop_catalog import update_custom_provider

    config = _custom_provider_config()

    provider = update_custom_provider(config, "xkiro", {"enabled": False})

    assert provider["enabled"] is False
    assert config.active_model_source == "standard"


def test_desktop_probe_reports_one_row_per_requested_provider(monkeypatch) -> None:
    from reverie.desktop_catalog import probe_provider_availability

    calls = _install_fake_catalog(monkeypatch, ("kiro-pro", "kiro-mini", "kiro-ultra"))
    config = _two_custom_providers()

    probes = probe_provider_availability(config, ["custom:xkiro", "custom:relay"])

    assert [item["key"] for item in probes] == ["custom:xkiro", "custom:relay"]
    assert [item["status"] for item in probes] == ["online", "online"]
    assert [item["model_count"] for item in probes] == [3, 3]
    assert probes[0]["name"] == "xkiro"
    assert probes[0]["provider_id"] == "xkiro"
    assert probes[0]["kind"] == "custom"
    assert sorted(calls) == ["https://api.xkiro.invalid/v1/models", "https://relay.invalid/models"]
    assert "xk-live-abcdef123456" not in json.dumps(probes)


def test_desktop_probe_marks_unprobeable_builtins_without_calling(monkeypatch) -> None:
    from reverie.desktop_catalog import probe_provider_availability

    calls = _install_fake_catalog(monkeypatch)

    probes = probe_provider_availability(_custom_provider_config(), ["codex", "webgemini"])

    assert [item["key"] for item in probes] == ["codex", "webgemini"]
    assert [item["status"] for item in probes] == ["not-probed", "not-probed"]
    assert all(item["probeable"] is False for item in probes)
    assert all("/provider" in item["detail"] for item in probes)
    assert calls == []


def test_standard_model_crud_preserves_secret_when_update_omits_it() -> None:
    config = Config()
    index = add_standard_model(
        config,
        {
            "model": "local-model",
            "model_display_name": "Local Model",
            "base_url": "http://127.0.0.1:8000/v1",
            "api_key": "secret-key",
            "provider": "openai-chat",
        },
    )
    assert index == 0
    update_standard_model(config, index, {"model_display_name": "Renamed Model", "api_key": ""})
    assert config.models[index].model_display_name == "Renamed Model"
    assert config.models[index].api_key == "secret-key"
    delete_standard_model(config, index)
    assert config.models == []


def test_prompt_cli_accepts_uppercase_p_and_runtime_model_overrides(monkeypatch, tmp_path: Path) -> None:
    from reverie import __main__ as entrypoint
    import reverie.cli.interface as interface_module

    captured = {}

    class _Result:
        success = True
        output_text = "ok"
        error = ""

    class _Interface:
        def __init__(self, project_root: Path, headless: bool = False):
            captured["project_root"] = project_root
            captured["headless"] = headless

        def run_prompt_once(self, prompt: str, **kwargs):
            captured["prompt"] = prompt
            captured.update(kwargs)
            return _Result()

    monkeypatch.setattr(interface_module, "ReverieInterface", _Interface)
    code = entrypoint.main(
        [
            str(tmp_path),
            "-P",
            "hello",
            "-source",
            "codex",
            "-model",
            "gpt-5.6-sol",
            "-reasoning",
            "high",
        ]
    )

    assert code == 0
    assert captured["prompt"] == "hello"
    assert captured["source_override"] == "codex"
    assert captured["model_override"] == "gpt-5.6-sol"
    assert captured["reasoning_override"] == "high"


def test_desktop_approval_request_can_be_resolved_while_prompt_waits() -> None:
    from reverie.sdk_bridge import ReverieSdkBridge

    published = threading.Event()
    events = []

    def write_event(message: dict) -> None:
        events.append(message)
        published.set()

    bridge = ReverieSdkBridge(event_writer=write_event)
    result = {}
    tool = type("Tool", (), {"name": "write_file"})()

    worker = threading.Thread(
        target=lambda: result.update(
            decision=bridge._request_tool_approval("prompt-1", tool, {"path": "note.txt"}, "Write access required")
        )
    )
    worker.start()
    assert published.wait(timeout=1)

    request = events[0]["event"]
    response = bridge.dispatch(
        {
            "id": "approval-1",
            "action": "resolveApproval",
            "payload": {"approvalId": request["approval_id"], "decision": "once"},
        }
    )
    worker.join(timeout=1)

    assert response["type"] == "approval.resolved"
    assert result["decision"] == "once"


def test_sdk_bridge_exposes_rats_task_status_events_cancel_and_logs_actions() -> None:
    from reverie.sdk_bridge import ReverieSdkBridge

    sync_calls = []

    class FakeRatsRuntime:
        def sync_tasks(self, **kwargs):
            sync_calls.append(dict(kwargs))
            return [{"service_id": kwargs.get("service_id", ""), "task_id": "run-1", "status": {"running": True}}]

        def task_status(self, service_id, task_id, **kwargs):
            return {"task_id": task_id, "running": True}

        def task_events(self, service_id, task_id, **kwargs):
            return {"schema": "reverie.rtp.task/1", "task_id": task_id, "events": []}

        def cancel_task(self, service_id, task_id, **kwargs):
            return {"task_id": task_id, "cancelled": True}

        def task_logs(self, service_id, task_id, **kwargs):
            return {"task_id": task_id, "text": "hello"}

    bridge = ReverieSdkBridge()
    bridge.rats_runtime = FakeRatsRuntime()
    tasks = bridge.dispatch({"id": "tasks", "action": "ratsTasks", "payload": {"serviceId": "rats-1-test"}})
    assert tasks["type"] == "rats.tasks" and tasks["tasks"][0]["task_id"] == "run-1"
    all_tasks = bridge.dispatch({"id": "all-tasks", "action": "ratsTasks", "payload": {}})
    assert all_tasks["type"] == "rats.tasks" and all_tasks["service_id"] == "" and all_tasks["provider_id"] == ""
    assert sync_calls[-1] == {"service_id": "", "provider_id": ""}
    status = bridge.dispatch({"id": "status", "action": "ratsTaskStatus", "payload": {"serviceId": "rats-1-test", "taskId": "run-1"}})
    assert status["type"] == "rats.task.status" and status["result"]["running"] is True
    events = bridge.dispatch({"id": "events", "action": "ratsTaskEvents", "payload": {"serviceId": "rats-1-test", "taskId": "run-1"}})
    assert events["type"] == "rats.task.events" and events["result"]["schema"] == "reverie.rtp.task/1"
    cancelled = bridge.dispatch({"id": "cancel", "action": "ratsTaskCancel", "payload": {"serviceId": "rats-1-test", "taskId": "run-1"}})
    assert cancelled["type"] == "rats.task.cancelled" and cancelled["result"]["cancelled"] is True
    logs = bridge.dispatch({"id": "logs", "action": "ratsTaskLogs", "payload": {"serviceId": "rats-1-test", "taskId": "run-1"}})
    assert logs["type"] == "rats.task.logs" and logs["result"]["text"] == "hello"


def test_sdk_bridge_exposes_subagent_dashboard_and_sanitized_run_log(tmp_path: Path) -> None:
    from reverie.sdk_bridge import ReverieSdkBridge

    spec = SimpleNamespace(to_dict=lambda: {
        "id": "reviewer",
        "name": "Reviewer",
        "enabled": True,
        "color": "#7c8cff",
        "mode": "reverie",
        "model_ref": {"display_name": "Review Model"},
    })
    run_payload = {
        "run_id": "reviewer-run-1",
        "subagent_id": "reviewer",
        "task_id": "task-1",
        "status": "completed",
        "started_at": "2026-08-14T10:00:00Z",
        "ended_at": "2026-08-14T10:00:02Z",
        "summary": "Validated the selected files.",
        "error": "",
        "log_path": str(tmp_path / "run.json"),
    }
    run = SimpleNamespace(to_dict=lambda: dict(run_payload))

    class _Manager:
        @staticmethod
        def is_available():
            return True

        @staticmethod
        def list_specs():
            return [spec]

        @staticmethod
        def list_recent_runs():
            return [run]

        @staticmethod
        def get_run(run_id):
            return run if run_id == "reviewer-run-1" else None

        @staticmethod
        def get_run_log(run_id):
            return {
                "run": run_payload,
                "subagent": spec.to_dict(),
                "model": {"model": "review-model", "display_name": "Review Model", "provider": "request"},
                "assignment": "Validate the selected files.",
                "events": [{"status": "success", "message": "Validation complete"}],
            }

    bridge = ReverieSdkBridge()
    bridge.project_root = tmp_path.resolve()
    bridge.interface = SimpleNamespace(subagent_manager=_Manager())

    dashboard = bridge.dispatch({"id": "agents", "action": "getSubagents", "payload": {}})
    log = bridge.dispatch({"id": "log", "action": "getSubagentRunLog", "payload": {"runId": "reviewer-run-1"}})

    assert dashboard["type"] == "subagents"
    assert dashboard["subagents"]["agents"][0]["id"] == "reviewer"
    assert dashboard["subagents"]["runs"][0]["status"] == "completed"
    assert log["type"] == "subagent.log"
    assert log["log"]["assignment"] == "Validate the selected files."
    assert "api_key" not in log["log"]["model"]


def test_session_titles_are_compact_and_legacy_names_are_upgraded(tmp_path: Path) -> None:
    manager = SessionManager(tmp_path / "state", project_root=tmp_path)
    session = manager.create_session("Prompt Run 2026-07-15 10:00:00")
    session.messages = [
        {"role": "system", "content": "workspace memory"},
        {"role": "user", "content": "  Diagnose   the history interaction and fix it completely.  "},
    ]
    manager.save_session(session)

    assert manager.refresh_generated_session_names() == 1
    assert manager.list_sessions()[0].name == "Diagnose the history interaction and fix it completely."
    assert session_title_from_prompt("x" * 100, max_length=20) == f"{'x' * 19}…"


def test_desktop_session_actions_keep_a_valid_active_session(tmp_path: Path) -> None:
    from reverie.sdk_bridge import ReverieSdkBridge

    manager = SessionManager(tmp_path / "state", project_root=tmp_path)
    first = manager.create_session()
    first.messages = [
        {"role": "user", "content": "First request"},
        {"role": "assistant", "content": "First answer"},
    ]
    manager.save_session(first)
    second = manager.create_session("Pinned conversation")
    manager.save_session(second)
    manager.load_session(first.id)

    class _Agent:
        history = []

        def set_history(self, messages):
            self.history = list(messages)

    class _Interface:
        session_manager = manager
        agent = _Agent()

    bridge = ReverieSdkBridge()
    bridge.project_root = tmp_path.resolve()
    bridge.interface = _Interface()

    renamed = bridge.dispatch(
        {"id": "rename", "action": "renameSession", "payload": {"sessionId": first.id, "name": "Renamed"}}
    )
    assert renamed["session"]["name"] == "Renamed"

    forked = bridge.dispatch(
        {"id": "fork", "action": "forkSession", "payload": {"sessionId": first.id, "messageCount": 1}}
    )
    fork_id = forked["session"]["id"]
    assert len(forked["session"]["messages"]) == 1

    rewound = bridge.dispatch(
        {
            "id": "rewind",
            "action": "rewindSession",
            "payload": {"sessionId": fork_id, "messageCount": 0, "confirmed": True},
        }
    )
    assert rewound["session"]["messages"] == []

    deleted = bridge.dispatch(
        {"id": "delete", "action": "deleteSession", "payload": {"sessionId": fork_id, "confirmed": True}}
    )
    assert deleted["session"] is not None
    assert deleted["sessions"]["current_session_id"] == deleted["session"]["id"]
    assert {item["id"] for item in deleted["sessions"]["items"]} == {first.id, second.id}


def test_sdk_bridge_compacts_the_requested_desktop_session_with_shared_context_tool(
    tmp_path: Path,
    monkeypatch,
) -> None:
    from reverie.sdk_bridge import ReverieSdkBridge, _BACKGROUND_DISPATCH_ACTIONS
    from reverie.tools.base import ToolResult
    from reverie.tools.context_management import ContextManagementTool

    manager = SessionManager(tmp_path / "state", project_root=tmp_path)
    session = manager.create_session("Long session")
    session.messages = [
        {"role": "user" if index % 2 == 0 else "assistant", "content": f"message {index}"}
        for index in range(12)
    ]
    manager.save_session(session)

    class _Agent:
        def __init__(self):
            self.history = []

        def get_history(self):
            return list(self.history)

        def set_history(self, messages):
            self.history = list(messages)

    captured = {}
    agent = _Agent()

    class _Interface:
        session_manager = manager

        def __init__(self):
            self.agent = agent

        def _init_agent(self, **kwargs):
            captured["init"] = kwargs

        def _get_app_context(self):
            return {"agent": self.agent, "session_manager": manager, "project_root": tmp_path}

    def fake_execute(tool, **kwargs):
        captured["context"] = tool.context
        captured["execute"] = kwargs
        compacted = [
            {"role": "system", "content": "# Continuation Summary\n## Current objective\nKeep GUI parity."},
            *agent.get_history()[-2:],
        ]
        agent.set_history(compacted)
        manager.update_messages(compacted)
        return ToolResult.ok("Context compressed: 120 -> 30 tokens")

    monkeypatch.setattr(ContextManagementTool, "execute", fake_execute)
    bridge = ReverieSdkBridge()
    bridge.project_root = tmp_path.resolve()
    bridge.interface = _Interface()
    monkeypatch.setattr(bridge, "recovery_payload", lambda: {"summary": {}, "checkpoints": [], "operations": []})
    monkeypatch.setattr(
        bridge,
        "context_status_payload",
        lambda: {"ready": True, "indexing": False, "files": 1, "symbols": 2, "progress": 100, "label": "Ready", "automatic_retrieval": True},
    )

    response = bridge.dispatch(
        {
            "id": "compact-1",
            "action": "compactContext",
            "payload": {
                "sessionId": session.id,
                "focus": "preserve provider failures",
                "projectRoot": str(tmp_path),
            },
        }
    )

    assert "compactContext" in _BACKGROUND_DISPATCH_ACTIONS
    assert captured["init"] == {"persist_config_changes": False, "defer_runtime_enrichment": True}
    assert captured["execute"] == {
        "action": "compress",
        "keep_last_messages": 8,
        "focus": "preserve provider failures",
    }
    assert captured["context"]["session_manager"] is manager
    assert response["type"] == "context.compacted"
    assert response["message"] == "Context compressed: 120 -> 30 tokens"
    assert response["session"]["messages"][0]["content"].startswith("# Continuation Summary")
    assert manager.get_current_session().messages == response["session"]["messages"]


def test_renaming_or_deleting_a_background_session_preserves_the_active_session(tmp_path: Path) -> None:
    from reverie.sdk_bridge import ReverieSdkBridge

    manager = SessionManager(tmp_path / "state", project_root=tmp_path)
    active = manager.create_session("Active")
    manager.save_session(active)
    background = manager.create_session("Background")
    manager.save_session(background)
    manager.load_session(active.id)

    class _Agent:
        history = []

        def set_history(self, messages):
            self.history = list(messages)

    class _Interface:
        session_manager = manager
        agent = _Agent()

    bridge = ReverieSdkBridge()
    bridge.project_root = tmp_path.resolve()
    bridge.interface = _Interface()

    renamed = bridge.dispatch(
        {"id": "rename-background", "action": "renameSession", "payload": {"sessionId": background.id, "name": "Renamed"}}
    )
    assert renamed["session"]["id"] == active.id
    assert renamed["updated_session"]["id"] == background.id
    assert renamed["updated_session"]["name"] == "Renamed"
    assert manager.get_current_session().id == active.id

    deleted = bridge.dispatch(
        {"id": "delete-background", "action": "deleteSession", "payload": {"sessionId": background.id, "confirmed": True}}
    )
    assert deleted["session"]["id"] == active.id
    assert manager.get_current_session().id == active.id
    assert {item["id"] for item in deleted["sessions"]["items"]} == {active.id}


def test_bulk_deleting_archived_sessions_preserves_an_unarchived_active_session(tmp_path: Path) -> None:
    from reverie.sdk_bridge import ReverieSdkBridge

    manager = SessionManager(tmp_path / "state", project_root=tmp_path)
    active = manager.create_session("Active")
    manager.save_session(active)
    archived_one = manager.create_session("Archived one")
    manager.save_session(archived_one)
    archived_two = manager.create_session("Archived two")
    manager.save_session(archived_two)
    manager.load_session(active.id)

    class _Agent:
        history = []

        def set_history(self, messages):
            self.history = list(messages)

    class _Interface:
        session_manager = manager
        agent = _Agent()

    bridge = ReverieSdkBridge()
    bridge.project_root = tmp_path.resolve()
    bridge.interface = _Interface()

    deleted = bridge.dispatch(
        {
            "id": "delete-archived",
            "action": "deleteSessions",
            "payload": {
                "sessionIds": [archived_one.id, archived_two.id, archived_one.id],
                "confirmed": True,
            },
        }
    )

    assert deleted["session"]["id"] == active.id
    assert deleted["deleted_session_ids"] == [archived_one.id, archived_two.id]
    assert {item["id"] for item in deleted["sessions"]["items"]} == {active.id}
    assert manager.load_session(archived_one.id) is None
    assert manager.load_session(archived_two.id) is None


def test_session_search_covers_titles_reasoning_and_tool_calls(tmp_path: Path) -> None:
    manager = SessionManager(tmp_path / "state", project_root=tmp_path)
    session = manager.create_session("Architecture review")
    session.messages = [
        {"role": "assistant", "content": None, "reasoning_content": "inspect the persistence boundary"},
        {
            "role": "assistant",
            "content": None,
            "tool_calls": [{"function": {"name": "read_session_index", "arguments": "{}"}}],
        },
    ]
    manager.save_session(session)

    assert manager.search_sessions("Architecture")[0]["message_index"] == -1
    assert manager.search_sessions("persistence")[0]["message_index"] == 0
    assert manager.search_sessions("read_session_index")[0]["message_index"] == 1


def test_sdk_bridge_forces_utf8_stdio_for_frozen_windows_build(monkeypatch) -> None:
    import reverie.sdk_bridge as sdk_bridge

    class _Stream:
        configured = None

        def reconfigure(self, **kwargs):
            self.configured = kwargs

    streams = [_Stream(), _Stream(), _Stream()]
    monkeypatch.setattr(sdk_bridge.sys, "stdin", streams[0])
    monkeypatch.setattr(sdk_bridge.sys, "stdout", streams[1])
    monkeypatch.setattr(sdk_bridge.sys, "stderr", streams[2])

    sdk_bridge._configure_utf8_stdio()

    assert [stream.configured for stream in streams] == [
        {"encoding": "utf-8", "errors": "strict"},
        {"encoding": "utf-8", "errors": "strict"},
        {"encoding": "utf-8", "errors": "strict"},
    ]


def test_desktop_tool_record_flattens_schema_metadata_for_the_gui() -> None:
    tool = type("ReadFileTool", (), {"__module__": "reverie.tools.read_file"})()
    payload = _desktop_tool_record(
        {
            "name": "read_file",
            "tool": tool,
            "description": "Read text from a workspace file.",
            "required": ["path"],
            "properties": ["path", "line_start"],
            "supported_modes": ["reverie", "writer"],
            "metadata": {
                "category": "filesystem",
                "aliases": ["cat_file"],
                "tags": ["read", "file"],
                "read_only": True,
                "concurrency_safe": True,
            },
        }
    )

    assert payload == {
        "name": "read_file",
        "description": "Read text from a workspace file.",
        "kind": "built-in",
        "category": "filesystem",
        "aliases": ["cat_file"],
        "tags": ["read", "file"],
        "traits": ["read-only", "parallel"],
        "required": ["path"],
        "properties": ["path", "line_start"],
        "supported_modes": ["reverie", "writer"],
    }


def test_sdk_bridge_switches_workspace_interfaces_without_replacing_the_bridge(monkeypatch, tmp_path: Path) -> None:
    from reverie.cli import interface as interface_module
    from reverie.sdk_bridge import ReverieSdkBridge

    first_root = tmp_path / "first"
    second_root = tmp_path / "second"
    first_root.mkdir()
    second_root.mkdir()

    class _OldInterface:
        closed = False

        def close(self):
            self.closed = True

    class _NewInterface:
        def __init__(self, project_root: Path, headless: bool = False):
            self.project_root = project_root
            self.headless = headless

    bridge = ReverieSdkBridge()
    old_interface = _OldInterface()
    bridge.project_root = first_root.resolve()
    bridge.interface = old_interface
    monkeypatch.setattr(interface_module, "ReverieInterface", _NewInterface)

    next_interface = bridge.ensure_interface(second_root)

    assert old_interface.closed is True
    assert bridge.project_root == second_root.resolve()
    assert next_interface.project_root == second_root.resolve()
    assert next_interface.headless is True


def test_delete_project_data_removes_reverie_records_but_preserves_project_files(monkeypatch, tmp_path: Path) -> None:
    from reverie.config import ConfigManager
    from reverie.sdk_bridge import ReverieSdkBridge

    project_root = tmp_path / "project"
    project_root.mkdir()
    source_file = project_root / "keep.py"
    source_file.write_text("print('keep')\n", encoding="utf-8")
    monkeypatch.setenv("REVERIE_APP_ROOT", str(tmp_path / "app"))
    config_manager = ConfigManager(project_root)
    config_manager.ensure_dirs()
    sessions_dir = config_manager.project_data_dir / "sessions"
    sessions_dir.mkdir(parents=True, exist_ok=True)
    (sessions_dir / "one.json").write_text("{}", encoding="utf-8")
    (sessions_dir / "two.json").write_text("{}", encoding="utf-8")
    workspace_config = config_manager.project_data_dir / "config.json"
    workspace_rules = config_manager.project_data_dir / "rules.txt"
    workspace_config.write_text('{"workspace": true}', encoding="utf-8")
    workspace_rules.write_text("Keep project conventions.\n", encoding="utf-8")
    context_cache = project_root / ".reverie" / "context_cache"
    context_cache.mkdir(parents=True)
    (context_cache / "index.json").write_text("{}", encoding="utf-8")

    response = ReverieSdkBridge().dispatch(
        {
            "id": "delete-project",
            "action": "deleteProjectData",
            "payload": {"projectRoot": str(project_root), "confirmed": True},
        }
    )

    assert response["deleted_sessions"] == 2
    assert not sessions_dir.exists()
    assert workspace_config.read_text(encoding="utf-8") == '{"workspace": true}'
    assert workspace_rules.read_text(encoding="utf-8") == "Keep project conventions.\n"
    assert not context_cache.exists()
    assert source_file.read_text(encoding="utf-8") == "print('keep')\n"


def test_workspace_mentions_prioritize_context_engine_recommendations(tmp_path: Path) -> None:
    from reverie.cli.interface import ReverieInterface

    target = tmp_path / "src" / "composer.tsx"
    target.parent.mkdir()
    target.write_text("export const Composer = () => null;\n", encoding="utf-8")

    class _SessionManager:
        @staticmethod
        def get_current_session():
            return SimpleNamespace(messages=[{"role": "user", "content": "fix the composer attachment picker"}])

    class _Retriever:
        @staticmethod
        def retrieve_for_task(*args, **kwargs):
            return SimpleNamespace(
                relevant_files=[
                    SimpleNamespace(
                        file_path=str(target),
                        score=17.0,
                        reasons=["task:composer"],
                        summary="Composer attachment controls",
                    )
                ],
                relevant_symbols=[],
            )

    fake_interface = SimpleNamespace(
        project_root=tmp_path,
        session_manager=_SessionManager(),
        retriever=_Retriever(),
        indexer=None,
        ensure_context_engine=lambda **kwargs: False,
        ensure_git_integration=lambda **kwargs: False,
    )

    candidates = ReverieInterface._collect_workspace_mention_candidates(fake_interface, "", limit=8)

    assert candidates[0]["path"] == "src/composer.tsx"
    assert candidates[0]["source"] == "context-engine"
    assert candidates[0]["reason"] == "task:composer"


def test_workspace_mentions_fall_back_to_partial_filename_matches(tmp_path: Path) -> None:
    from reverie.cli.interface import ReverieInterface

    target = tmp_path / "src" / "composer.tsx"
    target.parent.mkdir()
    target.write_text("export const Composer = () => null;\n", encoding="utf-8")
    (tmp_path / "README.md").write_text("Project notes.\n", encoding="utf-8")

    fake_interface = SimpleNamespace(
        project_root=tmp_path,
        session_manager=SimpleNamespace(get_current_session=lambda: None),
        retriever=None,
        indexer=None,
        ensure_context_engine=lambda **kwargs: False,
        ensure_git_integration=lambda **kwargs: False,
    )

    candidates = ReverieInterface._collect_workspace_mention_candidates(
        fake_interface,
        "composer attachment",
        limit=8,
    )

    assert [item["path"] for item in candidates] == ["src/composer.tsx"]
    assert candidates[0]["source"] == "workspace-scan"


def test_standard_catalog_exposes_enough_to_prefill_the_desktop_edit_form() -> None:
    config = Config()
    index = add_standard_model(
        config,
        {
            "model": "gpt-5.4",
            "model_display_name": "GPT-5.4",
            "base_url": "https://api.example.com/v1",
            "endpoint": "/chat/completions",
            "api_key": "secret-key",
            "provider": "openai-chat",
            "max_context_tokens": 200_000,
            "custom_headers": {"x-tenant": "reverie"},
        },
    )
    entry = _source(build_model_sources_payload(config), "standard")["models"][index]

    assert entry["id"] == str(index)
    assert entry["endpoint"] == "/chat/completions"
    assert entry["context_length"] == 200_000
    assert entry["custom_headers"] == {"x-tenant": "reverie"}
    # `configured` is also true for the keyless transports, so the edit form needs
    # its own answer to "is a key stored?" -- and never the key itself.
    assert entry["api_key_configured"] is True
    assert "api_key" not in entry
    assert "secret-key" not in json.dumps(entry)

    keyless = Config()
    add_standard_model(
        keyless,
        {
            "model": "gemini-web",
            "model_display_name": "Gemini Web",
            "base_url": "https://gemini.example.com",
            "provider": "webgemini",
        },
    )
    keyless_entry = _source(build_model_sources_payload(keyless), "standard")["models"][0]
    assert keyless_entry["configured"] is True
    assert keyless_entry["api_key_configured"] is False
    assert keyless_entry["custom_headers"] == {}


def test_wire_sessions_keep_provider_facing_roles_without_a_round_trip() -> None:
    from reverie.session.manager import Session

    session = Session(id="s1", name="Wire", created_at="2026-07-15T10:00:00", updated_at="2026-07-15T10:01:00", messages=[
        {"role": "user", "content": "Ask"},
        {"role": "assistant", "content": "Answer", "tool_calls": [{"id": "c1"}]},
    ])
    session.metadata = {"workspace_id": "w1"}
    wire = session.to_wire_dict()
    stored = session.to_dict()

    assert [message["role"] for message in wire["messages"]] == ["user", "assistant"]
    assert wire["messages"][1]["tool_calls"] == [{"id": "c1"}]
    assert set(wire) == set(stored)
    assert wire["id"] == "s1" and wire["name"] == "Wire"
    # Relabelling is what the *stored* form is for; the wire form must not have
    # visited it on the way out.
    assert [message["role"] for message in stored["messages"]] == ["user", "Reverie"]
    # Serializing either way leaves the live transcript alone -- a relabelled turn
    # is copied, never mutated in place.
    assert [message["role"] for message in session.messages] == ["user", "assistant"]
    assert stored["messages"][1] is not session.messages[1]
    assert wire["metadata"] == {"workspace_id": "w1"}


def test_json_safe_reuses_containers_that_need_no_coercion() -> None:
    from reverie.sdk_bridge import _json_safe

    transcript = {"messages": [{"role": "user", "content": "Ask"}], "count": 1, "ok": True}
    assert _json_safe(transcript) is transcript
    assert _json_safe(transcript["messages"]) is transcript["messages"]

    needs_coercion = {"root": Path("/tmp/x"), "messages": transcript["messages"]}
    coerced = _json_safe(needs_coercion)
    assert coerced is not needs_coercion
    assert coerced["root"] == str(Path("/tmp/x"))
    # An untouched subtree is shared, not re-copied.
    assert coerced["messages"] is needs_coercion["messages"]
    assert json.dumps(coerced)

    nested = {"outer": [{"path": Path("/tmp/y")}]}
    safe_nested = _json_safe(nested)
    assert safe_nested is not nested
    assert safe_nested["outer"][0]["path"] == str(Path("/tmp/y"))
    assert _json_safe({1: "a"}) == {"1": "a"}
    assert _json_safe(("a", "b")) == ["a", "b"]


def test_session_index_survives_a_foreign_file_without_rereading_every_transcript(tmp_path: Path) -> None:
    manager = SessionManager(tmp_path / "state", project_root=tmp_path)
    first = manager.create_session("First")
    first.messages = [{"role": "user", "content": "First request"}]
    manager.save_session(first)
    second = manager.create_session("Second")
    manager.save_session(second)
    manager.flush_session_index()

    # A session belonging to another workspace is skipped while indexing, so an
    # entry-count heuristic could never agree with the directory again.
    (manager.sessions_dir / "foreign.json").write_text(json.dumps({
        "id": "foreign",
        "name": "Another workspace",
        "messages": [],
        "metadata": {"workspace_id": "other-workspace", "workspace_path": "/elsewhere"},
    }), encoding="utf-8")
    (manager.sessions_dir / "broken.json").write_text("{not json", encoding="utf-8")

    reads = []
    original = SessionManager._read_session_index_entry

    def _counting_read(self, session_id):
        reads.append(session_id)
        return original(self, session_id)

    SessionManager._read_session_index_entry = _counting_read
    try:
        assert {info.id for info in manager.list_sessions()} == {first.id, second.id}
        first_pass = list(reads)
        for _ in range(5):
            assert {info.id for info in manager.list_sessions()} == {first.id, second.id}
    finally:
        SessionManager._read_session_index_entry = original

    assert sorted(first_pass) == ["broken", "foreign"]
    # Everything after the first scan is answered from the mtime fingerprint.
    assert reads == first_pass

    # A genuine outside edit is still picked up.
    second_path = manager.sessions_dir / f"{second.id}.json"
    payload = json.loads(second_path.read_text(encoding="utf-8"))
    payload["name"] = "Renamed outside Reverie"
    second_path.write_text(json.dumps(payload), encoding="utf-8")
    manager._scanned_session_files[second.id] = 0
    assert {info.name for info in manager.list_sessions()} == {"First", "Renamed outside Reverie"}

    # And a deleted file leaves the index.
    second_path.unlink()
    assert {info.id for info in manager.list_sessions()} == {first.id}


def test_generated_name_refresh_reads_an_untitleable_session_only_once(tmp_path: Path) -> None:
    manager = SessionManager(tmp_path / "state", project_root=tmp_path)
    untitleable = manager.create_session("Prompt Run 2026-07-15 10:00:00")
    untitleable.messages = [{"role": "user", "content": "   "}]
    manager.save_session(untitleable)
    empty = manager.create_session("Prompt Run 2026-07-15 10:05:00")
    manager.save_session(empty)
    manager.flush_session_index()

    reads = []
    original = Path.read_text

    def _counting_read_text(self, *args, **kwargs):
        if self.parent == manager.sessions_dir:
            reads.append(self)
        return original(self, *args, **kwargs)

    Path.read_text = _counting_read_text
    try:
        for _ in range(4):
            assert manager.refresh_generated_session_names() == 0
    finally:
        Path.read_text = original

    # The blank prompt yields no title, and a session with no messages has no
    # prompt at all -- neither is worth re-reading on every session switch.
    assert reads == [manager.sessions_dir / f"{untitleable.id}.json"]

    # Once a real prompt lands, the next refresh sees it and renames the session.
    untitleable.messages = [{"role": "user", "content": "Diagnose the switch latency"}]
    manager.save_session(untitleable)
    assert manager.refresh_generated_session_names() == 1
    assert {info.name for info in manager.list_sessions()} == {
        "Diagnose the switch latency",
        empty.name,
    }


def test_reloading_the_active_session_skips_a_redundant_parse(tmp_path: Path) -> None:
    manager = SessionManager(tmp_path / "state", project_root=tmp_path)
    session = manager.create_session("Active")
    session.messages = [{"role": "user", "content": "Ask"}, {"role": "assistant", "content": "Answer"}]
    manager.save_session(session)
    manager.load_session(session.id)

    loads = []
    original = json.load

    def _counting_load(handle, *args, **kwargs):
        loads.append(str(getattr(handle, "name", "")))
        return original(handle, *args, **kwargs)

    json.load = _counting_load
    try:
        assert manager.load_session(session.id) is session
        assert loads == []

        # An outside write invalidates the fingerprint, so the transcript is
        # re-read rather than served stale.
        manager._scanned_session_files[session.id] = 0
        reloaded = manager.load_session(session.id)
    finally:
        json.load = original

    assert reloaded is not None
    assert [message["content"] for message in reloaded.messages] == ["Ask", "Answer"]
    assert any(str(session.id) in name for name in loads)
