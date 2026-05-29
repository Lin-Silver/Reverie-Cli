from reverie.aihubmix import (
    build_aihubmix_openai_options,
    build_aihubmix_runtime_model_data,
    get_aihubmix_model_catalog,
    normalize_aihubmix_config,
    resolve_aihubmix_sdk_base_url,
)
from reverie.config import Config


def test_aihubmix_catalog_contains_requested_models() -> None:
    ids = {item["id"] for item in get_aihubmix_model_catalog()}

    assert {
        "gpt-5.5-free",
        "gpt-5.5-free-high",
        "gpt-5.5-free-low",
        "gpt-4o-free",
        "gpt-4.1-free",
    } <= ids


def test_aihubmix_base_url_normalizes_chat_completion_urls() -> None:
    assert resolve_aihubmix_sdk_base_url("aihubmix.com/v1/chat/completions") == "https://aihubmix.com/v1"
    assert resolve_aihubmix_sdk_base_url("https://aihubmix.com") == "https://aihubmix.com/v1"


def test_aihubmix_runtime_model_data_uses_env_key(monkeypatch) -> None:
    monkeypatch.setenv("AIHUBMIX_API_KEY", "ahm-test")

    runtime = build_aihubmix_runtime_model_data(
        {
            "selected_model_id": "gpt-4.1-free",
            "api_url": "https://aihubmix.com/v1/chat/completions",
        }
    )

    assert runtime is not None
    assert runtime["model"] == "gpt-4.1-free"
    assert runtime["model_display_name"] == "GPT-4.1 Free"
    assert runtime["provider"] == "openai-sdk"
    assert runtime["base_url"] == "https://aihubmix.com/v1"
    assert runtime["api_key"] == "ahm-test"


def test_config_active_model_resolves_aihubmix(monkeypatch) -> None:
    monkeypatch.setenv("AIHUBMIX_API_KEY", "ahm-test")
    config = Config(
        active_model_source="aihubmix",
        aihubmix=normalize_aihubmix_config({"selected_model_id": "gpt-5.5-free-high"}),
    )

    active = config.active_model

    assert active is not None
    assert active.model == "gpt-5.5-free-high"
    assert active.model_display_name == "GPT-5.5 Free High"
    assert active.provider == "openai-sdk"


def test_aihubmix_openai_options_match_provider_defaults() -> None:
    options = build_aihubmix_openai_options({"selected_model_id": "gpt-5.5-free"})

    assert options == {
        "temperature": 0.7,
        "top_p": 1.0,
        "max_tokens": 16384,
    }
