from reverie.nvidia import (
    build_nvidia_openai_options,
    build_nvidia_runtime_model_data,
    get_nvidia_model_metadata,
)


def test_nvidia_catalog_contains_minimax_m27():
    metadata = get_nvidia_model_metadata("minimaxai/minimax-m2.7")

    assert metadata is not None
    assert metadata["id"] == "minimaxai/minimax-m2.7"
    assert metadata["display_name"] == "MiniMax M2.7"
    assert metadata["transport"] == "openai-sdk"


def test_nvidia_openai_options_for_minimax_m27_match_expected_defaults():
    options = build_nvidia_openai_options(
        {"selected_model_id": "minimaxai/minimax-m2.7"},
        "minimaxai/minimax-m2.7",
    )

    assert options == {
        "temperature": 1.0,
        "top_p": 0.95,
        "max_tokens": 8192,
    }


def test_nvidia_runtime_model_data_uses_sdk_base_url_for_minimax_m27():
    runtime = build_nvidia_runtime_model_data(
        {
            "enabled": True,
            "api_key": "nvapi-test",
            "api_url": "https://integrate.api.nvidia.com/v1",
            "selected_model_id": "minimaxai/minimax-m2.7",
        }
    )

    assert runtime is not None
    assert runtime["model"] == "minimaxai/minimax-m2.7"
    assert runtime["model_display_name"] == "MiniMax M2.7"
    assert runtime["provider"] == "openai-sdk"
    assert runtime["base_url"] == "https://integrate.api.nvidia.com/v1"
    assert runtime["max_context_tokens"] == 204800


def test_nvidia_catalog_contains_glm_51():
    metadata = get_nvidia_model_metadata("z-ai/glm-5.1")

    assert metadata is not None
    assert metadata["id"] == "z-ai/glm-5.1"
    assert metadata["display_name"] == "GLM-5.1"
    assert metadata["transport"] == "openai-sdk"
    assert metadata["thinking"] is True


def test_nvidia_openai_options_for_glm_51_match_expected_defaults():
    options = build_nvidia_openai_options(
        {"selected_model_id": "z-ai/glm-5.1"},
        "z-ai/glm-5.1",
    )

    assert options == {
        "temperature": 1.0,
        "top_p": 1.0,
        "max_tokens": 16384,
        "extra_body": {
            "chat_template_kwargs": {
                "enable_thinking": True,
                "clear_thinking": False,
            }
        },
    }
