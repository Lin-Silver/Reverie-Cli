from reverie.config import Config
from reverie.modelscope import (
    MODELSCOPE_DEFAULT_API_URL,
    MODELSCOPE_DEFAULT_MODEL_ID,
    build_modelscope_anthropic_options,
    build_modelscope_runtime_model_data,
    default_modelscope_config,
    get_modelscope_model_catalog,
    get_modelscope_model_metadata,
    normalize_modelscope_config,
    resolve_modelscope_anthropic_base_url,
)


def test_modelscope_default_model_is_glm_51() -> None:
    cfg = default_modelscope_config()

    assert MODELSCOPE_DEFAULT_MODEL_ID == "ZhipuAI/GLM-5.1"
    assert cfg["selected_model_id"] == "ZhipuAI/GLM-5.1"
    assert cfg["selected_model_display_name"] == "GLM-5.1"
    assert cfg["max_context_tokens"] == 202752


def test_modelscope_catalog_context_lengths_match_model_cards() -> None:
    expected_context_lengths = {
        "ZhipuAI/GLM-5.1": 202752,
        "deepseek-ai/DeepSeek-V3.2": 128000,
        "ZhipuAI/GLM-5": 202752,
        "moonshotai/Kimi-K2.5": 262144,
        "MiniMax/MiniMax-M2.7": 204800,
        "Qwen/Qwen3.5-397B-A17B": 262144,
    }
    catalog_by_id = {item["id"]: item for item in get_modelscope_model_catalog()}

    assert set(expected_context_lengths) == set(catalog_by_id)
    for model_id, context_length in expected_context_lengths.items():
        assert catalog_by_id[model_id]["context_length"] == context_length
        assert get_modelscope_model_metadata(model_id)["context_length"] == context_length
        assert get_modelscope_model_metadata(model_id.lower())["id"] == model_id


def test_modelscope_base_url_normalizes_anthropic_messages_paths() -> None:
    assert resolve_modelscope_anthropic_base_url("api-inference.modelscope.cn/v1/messages") == MODELSCOPE_DEFAULT_API_URL
    assert resolve_modelscope_anthropic_base_url("https://api-inference.modelscope.cn/v1") == MODELSCOPE_DEFAULT_API_URL
    assert resolve_modelscope_anthropic_base_url("https://proxy.example.com/messages") == "https://proxy.example.com"


def test_modelscope_runtime_model_data_uses_anthropic_provider_and_env_key(monkeypatch) -> None:
    monkeypatch.setenv("MODELSCOPE_API_KEY", "ms-test")
    runtime = build_modelscope_runtime_model_data(
        {
            "api_url": "https://api-inference.modelscope.cn/v1/messages",
            "selected_model_id": "ZhipuAI/GLM-5.1",
        }
    )

    assert runtime is not None
    assert runtime["model"] == "ZhipuAI/GLM-5.1"
    assert runtime["model_display_name"] == "GLM-5.1"
    assert runtime["provider"] == "anthropic"
    assert runtime["base_url"] == MODELSCOPE_DEFAULT_API_URL
    assert runtime["api_key"] == "ms-test"
    assert runtime["max_context_tokens"] == 202752


def test_modelscope_anthropic_options_clamp_max_tokens() -> None:
    options = build_modelscope_anthropic_options(
        {
            "selected_model_id": "ZhipuAI/GLM-5.1",
            "max_tokens": 70000,
        },
        "ZhipuAI/GLM-5.1",
    )

    assert options == {"max_tokens": 65536}


def test_config_active_model_resolves_modelscope(monkeypatch) -> None:
    monkeypatch.setenv("MODELSCOPE_TOKEN", "ms-token")
    config = Config(
        models=[],
        active_model_source="modelscope",
        modelscope=normalize_modelscope_config({"selected_model_id": "MiniMax/MiniMax-M2.7"}),
    )

    active_model = config.active_model

    assert active_model is not None
    assert active_model.provider == "anthropic"
    assert active_model.model == "MiniMax/MiniMax-M2.7"
    assert active_model.base_url == MODELSCOPE_DEFAULT_API_URL
    assert active_model.max_context_tokens == 204800
