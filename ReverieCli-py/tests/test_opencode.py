from rich.console import Console

from reverie.agent.agent import ReverieAgent
from reverie.cli.commands import CommandHandler
from reverie.cli.help_catalog import HELP_TOPICS, normalize_help_topic
from reverie.config import Config, ConfigManager
from reverie.opencode import (
    apply_opencode_thinking_choice,
    build_opencode_openai_options,
    build_opencode_runtime_model_data,
    get_opencode_model_catalog,
    normalize_opencode_config,
    resolve_opencode_thinking_choice,
    resolve_opencode_request_url,
    resolve_opencode_sdk_base_url,
)


def test_opencode_catalog_matches_live_free_models_and_capabilities() -> None:
    catalog = {item["id"]: item for item in get_opencode_model_catalog()}

    assert set(catalog) == {
        "big-pickle",
        "deepseek-v4-flash-free",
        "mimo-v2.5-free",
        "north-mini-code-free",
        "nemotron-3-ultra-free",
        "ling-3.0-flash-free",
        "laguna-s-2.1-free",
    }
    assert catalog["mimo-v2.5-free"]["vision"] is True
    assert catalog["mimo-v2.5-free"]["vision_modalities"] == ["image", "audio", "video"]
    assert [item["id"] for item in catalog["deepseek-v4-flash-free"]["thinking_options"]] == [
        "none",
        "high",
        "max",
    ]
    assert [item["id"] for item in catalog["north-mini-code-free"]["thinking_options"]] == ["none", "high"]
    assert [item["id"] for item in catalog["ling-3.0-flash-free"]["thinking_options"]] == ["low", "medium", "high"]
    assert [item["id"] for item in catalog["laguna-s-2.1-free"]["thinking_options"]] == ["low", "medium", "high"]


def test_opencode_base_url_normalizes_chat_completion_urls() -> None:
    assert resolve_opencode_sdk_base_url("opencode.ai/zen/v1/chat/completions") == "https://opencode.ai/zen/v1"
    assert resolve_opencode_sdk_base_url("https://opencode.ai/zen") == "https://opencode.ai/zen/v1"


def test_opencode_runtime_model_data_supports_anonymous_free_models() -> None:
    runtime = build_opencode_runtime_model_data(
        {
            "selected_model_id": "deepseek-v4-flash-free",
            "api_url": "https://opencode.ai/zen/v1/chat/completions",
        }
    )

    assert runtime is not None
    assert runtime["model"] == "deepseek-v4-flash-free"
    assert runtime["model_display_name"] == "DeepSeek V4 Flash Free"
    assert runtime["provider"] == "openai-chat"
    assert runtime["base_url"] == "https://opencode.ai/zen/v1"
    assert runtime["endpoint"] == "/chat/completions"
    assert runtime["api_key"] == ""


def test_config_active_model_resolves_opencode_without_key() -> None:
    config = Config(
        active_model_source="opencode",
        opencode=normalize_opencode_config({"selected_model_id": "laguna-s-2.1-free"}),
    )

    active = config.active_model

    assert active is not None
    assert active.model == "laguna-s-2.1-free"
    assert active.model_display_name == "Laguna S 2.1 Free"
    assert active.provider == "openai-chat"
    assert active.endpoint == "/chat/completions"


def test_opencode_openai_options_match_provider_defaults() -> None:
    options = build_opencode_openai_options({"selected_model_id": "big-pickle"})

    assert options == {
        "temperature": 0.7,
        "top_p": 1.0,
        "max_tokens": 16384,
    }


def test_opencode_reasoning_choice_is_model_specific_and_sent_to_gateway() -> None:
    cfg = apply_opencode_thinking_choice(
        {"selected_model_id": "deepseek-v4-flash-free"},
        "deepseek-v4-flash-free",
        "max",
    )
    assert resolve_opencode_thinking_choice(cfg) == "max"
    assert build_opencode_openai_options(cfg)["extra_body"] == {"reasoning_effort": "max"}

    ling = normalize_opencode_config({"selected_model_id": "ling-3.0-flash-free"})
    assert resolve_opencode_thinking_choice(ling) == "medium"


def test_opencode_activate_does_not_require_a_key(tmp_path, monkeypatch) -> None:
    app_root = tmp_path / "app"
    project_root = tmp_path / "project"
    project_root.mkdir(parents=True, exist_ok=True)

    monkeypatch.setattr("reverie.config.get_app_root", lambda: app_root)
    monkeypatch.setattr("reverie.config.get_launcher_root", lambda: app_root)

    config_manager = ConfigManager(project_root)
    handler = CommandHandler(
        Console(record=True, force_terminal=False, width=120),
        {"config_manager": config_manager, "project_root": project_root},
    )

    assert handler.cmd_opencode("activate") is True

    reloaded = config_manager.load()
    active = reloaded.active_model
    assert reloaded.active_model_source == "opencode"
    assert reloaded.opencode["api_key"] == ""
    assert active is not None
    assert active.model == "deepseek-v4-flash-free"


def test_opencode_request_url_uses_chat_completions_path() -> None:
    assert resolve_opencode_request_url("https://opencode.ai/zen/v1", "") == "https://opencode.ai/zen/v1/chat/completions"


def test_request_headers_omit_authorization_when_api_key_is_empty(tmp_path) -> None:
    config = Config(active_model_source="opencode")
    agent = ReverieAgent(
        base_url="https://opencode.ai/zen/v1",
        api_key="",
        model="big-pickle",
        project_root=tmp_path,
        provider="request",
        config=config,
    )

    headers = agent._build_request_headers(stream=False)

    assert "Authorization" not in headers
    assert headers["Content-Type"] == "application/json"
    assert headers["Accept"] == "application/json"


def test_opencode_help_uses_alias_and_mentions_current_free_models() -> None:
    topic = HELP_TOPICS["opencode"]

    assert topic["command"] == "/opencode"
    assert "/oc" in topic["aliases"]
    assert "ling-3.0-flash-free" in topic["detail"]
    assert "laguna-s-2.1-free" in topic["detail"]
    assert normalize_help_topic("oc") == "opencode"
    assert normalize_help_topic("opencode") == "opencode"
