from reverie.nvidia import (
    build_nvidia_openai_options,
    build_nvidia_runtime_model_data,
    get_nvidia_reasoning_effort_label,
    get_nvidia_model_catalog,
    get_nvidia_model_metadata,
    normalize_nvidia_reasoning_effort,
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


def test_nvidia_catalog_context_lengths_match_model_cards():
    expected_context_lengths = {
        "mistralai/mistral-small-4-119b-2603": 262144,
        "qwen/qwen3.5-122b-a10b": 262144,
        "nvidia/nemotron-3-super-120b-a12b": 1000000,
        "minimaxai/minimax-m2.5": 204800,
        "minimaxai/minimax-m2.7": 204800,
        "qwen/qwen3.5-397b-a17b": 262144,
        "z-ai/glm-5.1": 205000,
        "stepfun-ai/step-3.5-flash": 256000,
        "deepseek-ai/deepseek-v4-pro": 1000000,
        "deepseek-ai/deepseek-v4-flash": 1000000,
        "mistralai/mistral-large-3-675b-instruct-2512": 262144,
        "moonshotai/kimi-k2-thinking": 256000,
        "openai/gpt-oss-120b": 128000,
    }
    catalog_by_id = {item["id"]: item for item in get_nvidia_model_catalog()}

    assert set(expected_context_lengths) == set(catalog_by_id)
    for model_id, context_length in expected_context_lengths.items():
        assert catalog_by_id[model_id]["context_length"] == context_length
        assert get_nvidia_model_metadata(model_id)["context_length"] == context_length


def test_nvidia_catalog_contains_glm_51():
    metadata = get_nvidia_model_metadata("z-ai/glm-5.1")

    assert metadata is not None
    assert metadata["id"] == "z-ai/glm-5.1"
    assert metadata["display_name"] == "GLM-5.1"
    assert metadata["transport"] == "openai-sdk"
    assert metadata["thinking"] is True
    assert metadata["thinking_control"] == "toggle"


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
                "thinking": True,
                "clear_thinking": False,
            }
        },
    }


def test_nvidia_openai_options_for_glm_51_can_disable_thinking_without_changing_sampling():
    options = build_nvidia_openai_options(
        {
            "selected_model_id": "z-ai/glm-5.1",
            "enable_thinking": False,
        },
        "z-ai/glm-5.1",
    )

    assert options == {
        "temperature": 1.0,
        "top_p": 1.0,
        "max_tokens": 16384,
        "extra_body": {
            "chat_template_kwargs": {
                "enable_thinking": False,
                "thinking": False,
                "clear_thinking": False,
            }
        },
    }


def test_nvidia_runtime_model_data_uses_selected_glm_thinking_toggle():
    runtime = build_nvidia_runtime_model_data(
        {
            "enabled": True,
            "api_key": "nvapi-test",
            "selected_model_id": "z-ai/glm-5.1",
            "enable_thinking": False,
        }
    )

    assert runtime is not None
    assert runtime["model"] == "z-ai/glm-5.1"
    assert runtime["thinking_mode"] == "false"


def test_nvidia_catalog_contains_kimi_k2_thinking_and_removed_legacy_models():
    catalog_by_id = {item["id"]: item for item in get_nvidia_model_catalog()}

    assert "z-ai/glm5" not in catalog_by_id
    assert "moonshotai/kimi-k2.5" not in catalog_by_id
    assert catalog_by_id["moonshotai/kimi-k2-thinking"]["thinking_control"] == "fixed"


def test_nvidia_openai_options_for_step_flash_use_deepseek_reasoning_format():
    options = build_nvidia_openai_options(
        {"selected_model_id": "stepfun-ai/step-3.5-flash"},
        "stepfun-ai/step-3.5-flash",
    )

    assert options == {
        "temperature": 1.0,
        "top_p": 0.9,
        "max_tokens": 16384,
        "extra_body": {
            "reasoning_format": {"type": "deepseek-style"},
        },
    }


def test_nvidia_openai_options_for_kimi_k2_thinking_match_provider_example():
    options = build_nvidia_openai_options(
        {"selected_model_id": "moonshotai/kimi-k2-thinking", "enable_thinking": False},
        "moonshotai/kimi-k2-thinking",
    )

    assert options == {
        "temperature": 1.0,
        "top_p": 0.9,
        "max_tokens": 16384,
    }

    runtime = build_nvidia_runtime_model_data(
        {
            "enabled": True,
            "api_key": "nvapi-test",
            "selected_model_id": "moonshotai/kimi-k2-thinking",
            "enable_thinking": False,
        }
    )
    assert runtime is not None
    assert runtime["thinking_mode"] is None


def test_nvidia_catalog_contains_deepseek_v4_models_with_effort_control():
    catalog_by_id = {item["id"]: item for item in get_nvidia_model_catalog()}

    for model_id in ("deepseek-ai/deepseek-v4-pro", "deepseek-ai/deepseek-v4-flash"):
        metadata = catalog_by_id[model_id]
        assert metadata["transport"] == "openai-sdk"
        assert metadata["context_length"] == 1000000
        assert metadata["thinking"] is True
        assert metadata["thinking_control"] == "effort"


def test_nvidia_reasoning_effort_defaults_to_max_and_normalizes_aliases():
    assert normalize_nvidia_reasoning_effort("") == "max"
    assert normalize_nvidia_reasoning_effort("extra high") == "max"
    assert normalize_nvidia_reasoning_effort("High") == "high"
    assert normalize_nvidia_reasoning_effort("off") == "none"
    assert get_nvidia_reasoning_effort_label("none") == "Non-think"


def test_nvidia_openai_options_for_deepseek_v4_default_to_max_reasoning():
    options = build_nvidia_openai_options(
        {"selected_model_id": "deepseek-ai/deepseek-v4-pro"},
        "deepseek-ai/deepseek-v4-pro",
    )

    assert options == {
        "temperature": 1.0,
        "top_p": 0.95,
        "max_tokens": 16384,
        "extra_body": {
            "chat_template_kwargs": {
                "thinking": True,
                "reasoning_effort": "max",
            }
        },
    }


def test_nvidia_openai_options_for_deepseek_v4_can_select_high_or_non_think():
    high = build_nvidia_openai_options(
        {"selected_model_id": "deepseek-ai/deepseek-v4-flash", "reasoning_effort": "high"},
        "deepseek-ai/deepseek-v4-flash",
    )
    off = build_nvidia_openai_options(
        {"selected_model_id": "deepseek-ai/deepseek-v4-flash", "reasoning_effort": "off"},
        "deepseek-ai/deepseek-v4-flash",
    )

    assert high["extra_body"]["chat_template_kwargs"] == {"thinking": True, "reasoning_effort": "high"}
    assert off["extra_body"]["chat_template_kwargs"] == {"thinking": False}


def test_nvidia_runtime_model_data_uses_deepseek_v4_context_and_effort_mode():
    runtime = build_nvidia_runtime_model_data(
        {
            "enabled": True,
            "api_key": "nvapi-test",
            "selected_model_id": "deepseek-ai/deepseek-v4-pro",
            "reasoning_effort": "high",
        }
    )

    assert runtime is not None
    assert runtime["model"] == "deepseek-ai/deepseek-v4-pro"
    assert runtime["provider"] == "openai-sdk"
    assert runtime["max_context_tokens"] == 1000000
    assert runtime["thinking_mode"] == "high"
