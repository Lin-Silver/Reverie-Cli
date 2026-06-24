from reverie.config import Config
from reverie.sensenova import (
    build_sensenova_runtime_model_data,
    default_sensenova_config,
    get_sensenova_model_catalog,
    normalize_sensenova_config,
    normalize_sensenova_reasoning_effort,
)


def test_sensenova_deepseek_v4_flash_catalog_contract():
    catalog_by_id = {item["id"]: item for item in get_sensenova_model_catalog()}
    flash = catalog_by_id["deepseek-v4-flash"]

    assert flash["context_length"] == 1_000_000
    assert [item["id"] for item in flash["thinking_options"]] == ["none", "low", "medium", "high"]
    assert flash["default_thinking_choice"] == "medium"
    assert normalize_sensenova_reasoning_effort("off") == "none"
    assert normalize_sensenova_reasoning_effort("low") == "low"
    assert normalize_sensenova_reasoning_effort("medium") == "medium"
    assert normalize_sensenova_reasoning_effort("high") == "high"
    assert normalize_sensenova_reasoning_effort("max") == "medium"


def test_sensenova_config_and_runtime_model_data():
    cfg = normalize_sensenova_config(
        {
            **default_sensenova_config(),
            "api_key": "sk-test",
            "reasoning_effort": "none",
        }
    )

    assert cfg["selected_model_id"] == "deepseek-v4-flash"
    assert cfg["max_context_tokens"] == 1_000_000
    assert cfg["reasoning_effort"] == "none"

    runtime = build_sensenova_runtime_model_data(cfg)
    assert runtime is not None
    assert runtime["model"] == "deepseek-v4-flash"
    assert runtime["base_url"] == "https://token.sensenova.cn/v1"
    assert runtime["max_context_tokens"] == 1_000_000
    assert runtime["thinking_mode"] == "none"


def test_config_accepts_sensenova_active_source():
    config = Config.from_dict(
        {
            "active_model_source": "sensenova",
            "sensenova": {"api_key": "sk-test", "selected_model_id": "deepseek-v4-flash"},
        }
    )

    assert config.active_model_source == "sensenova"
    assert config.sensenova["selected_model_id"] == "deepseek-v4-flash"
    assert config.active_model is not None
    assert config.active_model.model == "deepseek-v4-flash"
