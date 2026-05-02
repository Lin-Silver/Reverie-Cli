import json
from pathlib import Path

from rich.console import Console

from reverie.cli.commands import CommandHandler
from reverie.cli.tui_selector import SelectorAction, SelectorResult
from reverie.config import ConfigManager
from reverie.nvidia import (
    apply_nvidia_thinking_choice,
    build_nvidia_openai_options,
    build_nvidia_request_defaults,
    build_nvidia_runtime_model_data,
    default_nvidia_config,
    get_nvidia_reasoning_effort_label,
    get_nvidia_model_catalog,
    get_nvidia_model_metadata,
    get_nvidia_thinking_options,
    normalize_nvidia_reasoning_effort,
    resolve_nvidia_model_profile_name,
    resolve_nvidia_thinking_choice,
)


def test_nvidia_catalog_contains_minimax_m27():
    metadata = get_nvidia_model_metadata("minimaxai/minimax-m2.7")

    assert metadata is not None
    assert metadata["id"] == "minimaxai/minimax-m2.7"
    assert metadata["display_name"] == "MiniMax M2.7"
    assert metadata["transport"] == "openai-sdk"


def test_nvidia_default_timeout_matches_global_api_timeout_default():
    assert default_nvidia_config()["timeout"] == 60


def test_nvidia_openai_options_for_minimax_m27_match_expected_defaults():
    options = build_nvidia_openai_options(
        {"selected_model_id": "minimaxai/minimax-m2.7"},
        "minimaxai/minimax-m2.7",
    )

    assert options == {
        "temperature": 1.0,
        "top_p": 0.95,
        "max_tokens": 204800,
    }


def test_nvidia_profiles_raise_output_budget_to_full_context_window():
    options = build_nvidia_openai_options(
        {"selected_model_id": "openai/gpt-oss-120b", "max_tokens": 32768},
        "openai/gpt-oss-120b",
    )
    request_defaults = build_nvidia_request_defaults(
        {"selected_model_id": "mistralai/mistral-large-3-675b-instruct-2512", "max_tokens": 32768},
        "mistralai/mistral-large-3-675b-instruct-2512",
    )

    assert options["max_tokens"] == 128000
    assert request_defaults["max_tokens"] == 262144


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
    assert runtime["profile"] == "minimax"


def test_nvidia_catalog_context_lengths_match_model_cards():
    expected_context_lengths = {
        "mistralai/mistral-small-4-119b-2603": 262144,
        "mistralai/mistral-medium-3.5-128b": 262144,
        "qwen/qwen3.5-122b-a10b": 262144,
        "nvidia/nemotron-3-super-120b-a12b": 1000000,
        "minimaxai/minimax-m2.7": 204800,
        "qwen/qwen3.5-397b-a17b": 262144,
        "z-ai/glm-5.1": 131072,
        "stepfun-ai/step-3.5-flash": 256000,
        "deepseek-ai/deepseek-v4-pro": 1000000,
        "deepseek-ai/deepseek-v4-flash": 1000000,
        "mistralai/mistral-large-3-675b-instruct-2512": 262144,
        "moonshotai/kimi-k2.6": 262144,
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


def test_nvidia_catalog_contains_mistral_medium_35_128b():
    metadata = get_nvidia_model_metadata("mistralai/mistral-medium-3.5-128b")

    assert metadata is not None
    assert metadata["id"] == "mistralai/mistral-medium-3.5-128b"
    assert metadata["display_name"] == "Mistral Medium 3.5 128B"
    assert metadata["transport"] == "request"
    assert metadata["vision"] is True
    assert metadata["thinking"] is True
    assert metadata["thinking_control"] == "effort"
    assert [item["id"] for item in metadata["thinking_options"]] == ["high", "none"]


def test_nvidia_request_defaults_for_mistral_medium_35_match_provider_example():
    options = build_nvidia_request_defaults(
        {"selected_model_id": "mistralai/mistral-medium-3.5-128b"},
        "mistralai/mistral-medium-3.5-128b",
    )

    assert options == {
        "max_tokens": 262144,
        "temperature": 0.70,
        "top_p": 1.00,
        "reasoning_effort": "high",
    }


def test_nvidia_openai_options_for_glm_51_match_expected_defaults():
    options = build_nvidia_openai_options(
        {"selected_model_id": "z-ai/glm-5.1"},
        "z-ai/glm-5.1",
    )

    assert options == {
        "temperature": 1.0,
        "top_p": 1.0,
        "max_tokens": 131072,
        "extra_body": {
            "chat_template_kwargs": {
                "enable_thinking": True,
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
        "max_tokens": 131072,
        "extra_body": {
            "chat_template_kwargs": {
                "enable_thinking": False,
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


def test_nvidia_catalog_contains_kimi_k2_6_and_removed_legacy_models():
    catalog_by_id = {item["id"]: item for item in get_nvidia_model_catalog()}

    assert "z-ai/glm5" not in catalog_by_id
    assert "minimaxai/minimax-m2.5" not in catalog_by_id
    assert "moonshotai/kimi-k2.5" not in catalog_by_id
    assert "moonshotai/kimi-k2-thinking" not in catalog_by_id
    assert catalog_by_id["moonshotai/kimi-k2.6"]["transport"] == "request"
    assert catalog_by_id["moonshotai/kimi-k2.6"]["vision"] is True
    assert catalog_by_id["moonshotai/kimi-k2.6"]["thinking_control"] == "toggle"


def test_nvidia_request_defaults_for_kimi_k2_6_match_provider_example():
    options = build_nvidia_request_defaults(
        {"selected_model_id": "moonshotai/kimi-k2.6"},
        "moonshotai/kimi-k2.6",
    )
    disabled = build_nvidia_request_defaults(
        {"selected_model_id": "moonshotai/kimi-k2.6", "enable_thinking": False},
        "moonshotai/kimi-k2.6",
    )

    assert options == {
        "max_tokens": 262144,
        "temperature": 1.0,
        "top_p": 1.0,
        "chat_template_kwargs": {"thinking": True},
    }
    assert disabled["chat_template_kwargs"] == {"thinking": False}


def test_nvidia_openai_options_for_step_flash_use_deepseek_reasoning_format():
    options = build_nvidia_openai_options(
        {"selected_model_id": "stepfun-ai/step-3.5-flash"},
        "stepfun-ai/step-3.5-flash",
    )

    assert options == {
        "temperature": 1.0,
        "top_p": 0.9,
        "max_tokens": 256000,
        "extra_body": {
            "reasoning_format": {"type": "deepseek-style"},
        },
    }


def test_nvidia_catalog_contains_deepseek_v4_models_with_effort_control():
    catalog_by_id = {item["id"]: item for item in get_nvidia_model_catalog()}

    for model_id in ("deepseek-ai/deepseek-v4-pro", "deepseek-ai/deepseek-v4-flash"):
        metadata = catalog_by_id[model_id]
        assert metadata["transport"] == "openai-sdk"
        assert metadata["context_length"] == 1000000
        assert metadata["thinking"] is True
        assert metadata["thinking_control"] == "effort"
        assert [item["id"] for item in metadata["thinking_options"]] == ["high", "max", "none"]


def test_nvidia_reasoning_effort_defaults_to_high_and_normalizes_aliases():
    assert normalize_nvidia_reasoning_effort("") == "high"
    assert normalize_nvidia_reasoning_effort("extra high") == "max"
    assert normalize_nvidia_reasoning_effort("High") == "high"
    assert normalize_nvidia_reasoning_effort("med") == "medium"
    assert normalize_nvidia_reasoning_effort("light") == "low"
    assert normalize_nvidia_reasoning_effort("off") == "none"
    assert get_nvidia_reasoning_effort_label("none") == "Non-think"


def test_nvidia_openai_options_for_deepseek_v4_default_to_high_reasoning():
    options = build_nvidia_openai_options(
        {"selected_model_id": "deepseek-ai/deepseek-v4-pro"},
        "deepseek-ai/deepseek-v4-pro",
    )

    assert options == {
        "temperature": 1.0,
        "top_p": 0.95,
        "max_tokens": 1000000,
        "extra_body": {
            "chat_template_kwargs": {
                "thinking": True,
                "reasoning_effort": "high",
            },
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

    assert high["extra_body"] == {
        "chat_template_kwargs": {
            "thinking": True,
            "reasoning_effort": "high",
        }
    }
    assert off["extra_body"] == {"chat_template_kwargs": {"thinking": False}}


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


def test_nvidia_catalog_contains_model_specific_thinking_options():
    assert [item["id"] for item in get_nvidia_thinking_options("mistralai/mistral-small-4-119b-2603")] == ["high", "none"]
    assert [item["id"] for item in get_nvidia_thinking_options("mistralai/mistral-medium-3.5-128b")] == ["high", "none"]
    assert [item["id"] for item in get_nvidia_thinking_options("moonshotai/kimi-k2.6")] == ["true", "false"]
    assert [item["id"] for item in get_nvidia_thinking_options("nvidia/nemotron-3-super-120b-a12b")] == ["high", "low", "none"]
    assert [item["id"] for item in get_nvidia_thinking_options("openai/gpt-oss-120b")] == ["low", "medium", "high"]
    assert resolve_nvidia_thinking_choice({"selected_model_id": "openai/gpt-oss-120b"}, "openai/gpt-oss-120b") == "medium"


def test_nvidia_apply_thinking_choice_updates_toggle_and_effort_config():
    qwen_cfg = apply_nvidia_thinking_choice(
        {"selected_model_id": "qwen/qwen3.5-397b-a17b", "enable_thinking": True},
        "qwen/qwen3.5-397b-a17b",
        "off",
    )
    assert qwen_cfg["enable_thinking"] is False
    assert resolve_nvidia_thinking_choice(qwen_cfg, "qwen/qwen3.5-397b-a17b") == "false"

    gpt_cfg = apply_nvidia_thinking_choice(
        {"selected_model_id": "openai/gpt-oss-120b"},
        "openai/gpt-oss-120b",
        "high",
    )
    assert gpt_cfg["reasoning_effort"] == "high"
    assert gpt_cfg["enable_thinking"] is True


def test_nvidia_openai_options_for_nemotron_and_gpt_oss_use_model_specific_effort():
    nemotron = build_nvidia_openai_options(
        {"selected_model_id": "nvidia/nemotron-3-super-120b-a12b", "reasoning_effort": "low"},
        "nvidia/nemotron-3-super-120b-a12b",
    )
    gpt_oss = build_nvidia_openai_options(
        {"selected_model_id": "openai/gpt-oss-120b"},
        "openai/gpt-oss-120b",
    )

    assert nemotron["extra_body"] == {
        "chat_template_kwargs": {
            "enable_thinking": True,
            "force_nonempty_content": True,
            "low_effort": True,
        }
    }
    assert gpt_oss["extra_body"] == {"reasoning_effort": "medium"}


def test_nvidia_model_specific_profiles_are_resolved_by_model_id():
    assert resolve_nvidia_model_profile_name("z-ai/glm-5.1") == "glm_5_1"
    assert resolve_nvidia_model_profile_name("deepseek-ai/deepseek-v4-pro") == "deepseek_v4"
    assert resolve_nvidia_model_profile_name("mistralai/mistral-medium-3.5-128b") == "mistral_medium_35"
    assert resolve_nvidia_model_profile_name("moonshotai/kimi-k2.6") == "kimi_k2_6"


def test_nvidia_model_selection_opens_fixed_thinking_selector(tmp_path: Path, monkeypatch) -> None:
    app_root = tmp_path / "app"
    project_root = tmp_path / "project"
    project_root.mkdir(parents=True, exist_ok=True)

    monkeypatch.setattr("reverie.config.get_app_root", lambda: app_root)
    monkeypatch.setattr("reverie.config.get_launcher_root", lambda: app_root)

    seen: dict[str, object] = {}

    def fake_selector_run(self):
        seen["title"] = self.title
        seen["ids"] = [item.id for item in self.items]
        return SelectorResult(SelectorAction.SELECT, self.items[2])

    monkeypatch.setattr("reverie.cli.tui_selector.TUISelector.run", fake_selector_run)

    config_manager = ConfigManager(project_root)
    handler = CommandHandler(
        Console(record=True, force_terminal=False, width=120),
        {"config_manager": config_manager, "project_root": project_root},
    )

    assert handler._cmd_nvidia_model("openai/gpt-oss-120b") is True

    reloaded = config_manager.load()
    assert reloaded.active_model_source == "nvidia"
    assert reloaded.nvidia["selected_model_id"] == "openai/gpt-oss-120b"
    assert reloaded.nvidia["reasoning_effort"] == "high"
    assert seen["ids"] == ["low", "medium", "high"]
    assert "NVIDIA Thinking" in str(seen["title"])


def test_nvidia_model_selection_syncs_global_config_in_workspace_mode(tmp_path: Path, monkeypatch) -> None:
    app_root = tmp_path / "app"
    project_root = tmp_path / "project"
    project_root.mkdir(parents=True, exist_ok=True)

    monkeypatch.setattr("reverie.config.get_app_root", lambda: app_root)
    monkeypatch.setattr("reverie.config.get_launcher_root", lambda: app_root)

    config_manager = ConfigManager(project_root)
    config_manager.load()
    assert config_manager.copy_config_to_workspace() is True
    assert config_manager.set_workspace_config_enabled(True) is True
    config_manager = ConfigManager(project_root)
    assert config_manager.is_workspace_mode() is True

    handler = CommandHandler(
        Console(record=True, force_terminal=False, width=120),
        {"config_manager": config_manager, "project_root": project_root},
    )

    assert handler._cmd_nvidia_model("minimaxai/minimax-m2.7") is True

    workspace_config = config_manager.load()
    global_data = json.loads((app_root / ".reverie" / "config.json").read_text(encoding="utf-8"))

    assert workspace_config.active_model_source == "nvidia"
    assert workspace_config.nvidia["selected_model_id"] == "minimaxai/minimax-m2.7"
    assert workspace_config.nvidia["max_context_tokens"] == 204800
    assert workspace_config.nvidia["max_tokens"] == 204800
    assert global_data["active_model_source"] == "nvidia"
    assert global_data["nvidia"]["selected_model_id"] == "minimaxai/minimax-m2.7"
    assert global_data["nvidia"]["max_context_tokens"] == 204800
    assert global_data["nvidia"]["max_tokens"] == 204800
