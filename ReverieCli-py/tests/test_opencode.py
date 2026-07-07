from rich.console import Console

from reverie.agent.agent import ReverieAgent
from reverie.cli.commands import CommandHandler
from reverie.cli.help_catalog import HELP_TOPICS, normalize_help_topic
from reverie.config import Config, ConfigManager
from reverie.opencode import (
    build_opencode_openai_options,
    build_opencode_runtime_model_data,
    get_opencode_model_catalog,
    normalize_opencode_config,
    resolve_opencode_request_url,
    resolve_opencode_sdk_base_url,
)


def test_opencode_catalog_contains_requested_free_models() -> None:
    ids = {item["id"] for item in get_opencode_model_catalog()}

    assert {
        "big-pickle",
        "deepseek-v4-flash-free",
        "mimo-v2.5-free",
        "north-mini-code-free",
        "nemotron-3-ultra-free",
        "hy3-free",
    } <= ids


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
        opencode=normalize_opencode_config({"selected_model_id": "hy3-free"}),
    )

    active = config.active_model

    assert active is not None
    assert active.model == "hy3-free"
    assert active.model_display_name == "Hy3 Free"
    assert active.provider == "openai-chat"
    assert active.endpoint == "/chat/completions"


def test_opencode_openai_options_match_provider_defaults() -> None:
    options = build_opencode_openai_options({"selected_model_id": "big-pickle"})

    assert options == {
        "temperature": 0.7,
        "top_p": 1.0,
        "max_tokens": 16384,
    }


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


def test_opencode_help_uses_alias_and_mentions_hidden_model() -> None:
    topic = HELP_TOPICS["opencode"]

    assert topic["command"] == "/opencode"
    assert "/oc" in topic["aliases"]
    assert "hy3-free" in topic["detail"]
    assert normalize_help_topic("oc") == "opencode"
    assert normalize_help_topic("opencode") == "opencode"
