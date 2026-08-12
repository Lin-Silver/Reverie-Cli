import json
from pathlib import Path

import pytest
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
    get_nvidia_model_vision_modalities,
    get_nvidia_thinking_options,
    normalize_nvidia_config,
    normalize_nvidia_reasoning_effort,
    resolve_nvidia_model_profile_name,
    resolve_nvidia_thinking_choice,
)


def test_nvidia_catalog_contains_minimax_m3_multimodal_request_model():
    metadata = get_nvidia_model_metadata("minimaxai/minimax-m3")

    assert metadata is not None
    assert metadata["id"] == "minimaxai/minimax-m3"
    assert metadata["display_name"] == "MiniMax M3"
    assert metadata["transport"] == "request"
    assert metadata["vision"] is True
    assert metadata["thinking"] is True
    assert metadata["thinking_control"] == "effort"
    assert [item["id"] for item in metadata["thinking_options"]] == ["high", "none"]
    assert metadata["vision_modalities"] == ["image", "video"]
    assert get_nvidia_model_vision_modalities("minimaxai/minimax-m3") == ["image", "video"]

    defaults = build_nvidia_request_defaults(
        {"selected_model_id": "minimaxai/minimax-m3", "max_tokens": 16384},
        "minimaxai/minimax-m3",
    )
    assert defaults == {
        "temperature": 1.0,
        "top_p": 0.95,
        "max_tokens": 8192,
        "chat_template_kwargs": {"thinking_mode": "enabled"},
    }


def test_nvidia_minimax_m3_thinking_defaults_to_high_and_can_select_none():
    runtime = build_nvidia_runtime_model_data(
        {"api_key": "nv-test", "selected_model_id": "minimaxai/minimax-m3"}
    )
    off = apply_nvidia_thinking_choice(
        {"selected_model_id": "minimaxai/minimax-m3"},
        "minimaxai/minimax-m3",
        "none",
    )
    off_defaults = build_nvidia_request_defaults(off, "minimaxai/minimax-m3")

    assert runtime["thinking_mode"] == "high"
    assert off["reasoning_effort"] == "none"
    assert off["enable_thinking"] is False
    assert off_defaults["chat_template_kwargs"] == {"thinking_mode": "disabled"}


def test_nvidia_default_timeout_matches_global_api_timeout_default():
    assert default_nvidia_config()["timeout"] == 60


def test_nvidia_profiles_raise_output_budget_to_model_output_limit():
    options = build_nvidia_openai_options(
        {"selected_model_id": "openai/gpt-oss-120b", "max_tokens": 32768},
        "openai/gpt-oss-120b",
    )
    muse_options = build_nvidia_openai_options(
        {"selected_model_id": "meta/muse-glimmer-30b", "max_tokens": 1_000_000},
        "meta/muse-glimmer-30b",
    )
    lightning_options = build_nvidia_openai_options(
        {"selected_model_id": "nvidia/nemotron-3.5-lightning-30b-a3b", "max_tokens": 1_000_000},
        "nvidia/nemotron-3.5-lightning-30b-a3b",
    )

    assert options["max_tokens"] == 128000
    assert muse_options["max_tokens"] == 16384
    assert lightning_options["max_tokens"] == 32768


def test_nvidia_runtime_model_data_uses_sdk_base_url_for_muse_glimmer():
    runtime = build_nvidia_runtime_model_data(
        {
            "enabled": True,
            "api_key": "nvapi-test",
            "api_url": "https://integrate.api.nvidia.com/v1",
            "selected_model_id": "meta/muse-glimmer-30b",
        }
    )

    assert runtime is not None
    assert runtime["model"] == "meta/muse-glimmer-30b"
    assert runtime["model_display_name"] == "Muse Glimmer 30B"
    assert runtime["provider"] == "openai-sdk"
    assert runtime["base_url"] == "https://integrate.api.nvidia.com/v1"
    assert runtime["max_context_tokens"] == 131072
    assert runtime["supports_vision"] is True
    assert runtime["profile"] == "muse_glimmer"


def test_nvidia_catalog_context_lengths_match_model_cards():
    expected_context_lengths = {
        "meta/muse-glimmer-30b": 131072,
        "nvidia/nemotron-3.5-lightning-30b-a3b": 1048576,
        "nvidia/nemotron-3-super-120b-a12b": 1000000,
        "minimaxai/minimax-m3": 1000000,
        "z-ai/glm-5.2": 1000000,
        "nvidia/nemotron-3-ultra-550b-a55b": 1000000,
        "poolside/laguna-xs-2.1": 262000,
        "stepfun-ai/step-3.7-flash": 256000,
        "openai/gpt-oss-120b": 128000,
    }
    catalog_by_id = {item["id"]: item for item in get_nvidia_model_catalog()}

    assert set(expected_context_lengths) == set(catalog_by_id)
    for model_id, context_length in expected_context_lengths.items():
        assert catalog_by_id[model_id]["context_length"] == context_length
        assert get_nvidia_model_metadata(model_id)["context_length"] == context_length


def test_nvidia_catalog_contains_nemotron_3_ultra():
    metadata = get_nvidia_model_metadata("nvidia/nemotron-3-ultra-550b-a55b")

    assert metadata is not None
    assert metadata["transport"] == "openai-sdk"
    assert metadata["thinking_control"] == "fixed"
    assert metadata["context_length"] == 1000000


def test_nvidia_catalog_contains_laguna_xs():
    laguna = get_nvidia_model_metadata("poolside/laguna-xs-2.1")

    assert laguna is not None
    assert laguna["max_output_tokens"] == 8_192


def test_nvidia_catalog_contains_glm_52():
    metadata = get_nvidia_model_metadata("z-ai/glm-5.2")
    alias_metadata = get_nvidia_model_metadata("z-ai/glm5.2")

    assert metadata is not None
    assert metadata["id"] == "z-ai/glm-5.2"
    assert metadata["display_name"] == "GLM-5.2"
    assert metadata["transport"] == "openai-sdk"
    assert metadata["thinking"] is True
    assert metadata["thinking_control"] == "fixed"
    assert metadata["context_length"] == 1000000
    assert alias_metadata is not None
    assert alias_metadata["id"] == "z-ai/glm-5.2"


def test_nvidia_openai_options_for_glm_52_match_expected_defaults():
    options = build_nvidia_openai_options(
        {"selected_model_id": "z-ai/glm-5.2"},
        "z-ai/glm-5.2",
    )

    assert options == {
        "temperature": 1.0,
        "top_p": 1.0,
        "max_tokens": 16384,
    }


def test_nvidia_openai_options_for_glm_52_caps_requested_output_tokens():
    options = build_nvidia_openai_options(
        {
            "selected_model_id": "z-ai/glm-5.2",
            "max_tokens": 65536,
        },
        "z-ai/glm-5.2",
    )

    assert options["max_tokens"] == 32768


def test_nvidia_openai_options_for_nemotron_3_ultra_match_provider_example():
    options = build_nvidia_openai_options(
        {"selected_model_id": "nvidia/nemotron-3-ultra-550b-a55b"},
        "nvidia/nemotron-3-ultra-550b-a55b",
    )

    assert options == {
        "temperature": 1.0,
        "top_p": 0.95,
        "max_tokens": 16384,
        "extra_body": {
            "chat_template_kwargs": {"enable_thinking": True},
            "reasoning_budget": 16384,
        },
    }


def test_nvidia_catalog_excludes_removed_legacy_models():
    catalog_by_id = {item["id"]: item for item in get_nvidia_model_catalog()}

    assert "z-ai/glm5" not in catalog_by_id
    assert "z-ai/glm4.7" not in catalog_by_id
    assert "qwen/qwen3.5-122b-a10b" not in catalog_by_id
    assert "minimaxai/minimax-m2.5" not in catalog_by_id
    assert "moonshotai/kimi-k2.5" not in catalog_by_id
    assert "moonshotai/kimi-k2-thinking" not in catalog_by_id


@pytest.mark.parametrize(
    "retired_model_id",
    [
        "z-ai/glm4.7",
        "qwen/qwen3.5-122b-a10b",
        "mistralai/mistral-small-4-119b-2603",
        "mistralai/mistral-medium-3.5-128b",
        "minimaxai/minimax-m2.7",
        "qwen/qwen3.5-397b-a17b",
        "stepfun-ai/step-3.5-flash",
        "deepseek-ai/deepseek-v4-pro",
        "deepseek-ai/deepseek-v4-flash",
        "mistralai/mistral-large-3-675b-instruct-2512",
        "nvidia/nemotron-3.5-nano-30b-a3b",
        "moonshotai/kimi-k2.6",
    ],
)
def test_nvidia_retired_model_config_migrates_to_current_default(retired_model_id: str):
    assert get_nvidia_model_metadata(retired_model_id) is None

    normalized = normalize_nvidia_config({"selected_model_id": retired_model_id})

    assert normalized["selected_model_id"] == "meta/muse-glimmer-30b"
    assert normalized["selected_model_display_name"] == "Muse Glimmer 30B"


def test_nvidia_catalog_contains_step_37_flash_vision_request_model():
    metadata = get_nvidia_model_metadata("stepfun-ai/step-3.7-flash")

    assert metadata is not None
    assert metadata["id"] == "stepfun-ai/step-3.7-flash"
    assert metadata["display_name"] == "Step-3.7-Flash"
    assert metadata["transport"] == "request"
    assert metadata["vision"] is True
    assert metadata["context_length"] == 256000
    assert metadata["max_output_tokens"] == 16384
    assert resolve_nvidia_model_profile_name("stepfun-ai/step-3.7-flash") == "step_37_flash"


def test_nvidia_request_defaults_for_step_37_flash_match_provider_example():
    options = build_nvidia_request_defaults(
        {"selected_model_id": "stepfun-ai/step-3.7-flash"},
        "stepfun-ai/step-3.7-flash",
    )

    assert options == {
        "max_tokens": 16384,
        "temperature": 1.00,
        "top_p": 0.95,
    }


def test_nvidia_reasoning_effort_defaults_to_high_and_normalizes_aliases():
    assert normalize_nvidia_reasoning_effort("") == "high"
    assert normalize_nvidia_reasoning_effort("extra high") == "max"
    assert normalize_nvidia_reasoning_effort("High") == "high"
    assert normalize_nvidia_reasoning_effort("med") == "medium"
    assert normalize_nvidia_reasoning_effort("light") == "low"
    assert normalize_nvidia_reasoning_effort("off") == "none"
    assert get_nvidia_reasoning_effort_label("none") == "Non-think"


def test_nvidia_catalog_and_options_for_muse_glimmer():
    metadata = get_nvidia_model_metadata("meta/muse-glimmer-30b")
    options = build_nvidia_openai_options(
        {"selected_model_id": "meta/muse-glimmer-30b"},
        "meta/muse-glimmer-30b",
    )

    assert metadata is not None
    assert metadata["vision"] is True
    assert metadata["tool_calling"] is True
    assert metadata["context_length"] == 131072
    assert metadata["max_output_tokens"] == 16384
    assert [item["id"] for item in metadata["thinking_options"]] == [
        "none", "minimal", "low", "medium", "high", "max"
    ]
    assert options == {
        "temperature": 1.0,
        "top_p": 0.95,
        "max_tokens": 16384,
        "extra_body": {"reasoning_effort": "high"},
    }


def test_nvidia_catalog_and_options_for_nemotron_35_lightning():
    metadata = get_nvidia_model_metadata("nvidia/nemotron-3.5-lightning-30b-a3b")
    enabled = build_nvidia_openai_options(
        {"selected_model_id": "nvidia/nemotron-3.5-lightning-30b-a3b"},
        "nvidia/nemotron-3.5-lightning-30b-a3b",
    )
    disabled = build_nvidia_openai_options(
        {
            "selected_model_id": "nvidia/nemotron-3.5-lightning-30b-a3b",
            "enable_thinking": False,
        },
        "nvidia/nemotron-3.5-lightning-30b-a3b",
    )

    assert metadata is not None
    assert metadata["vision"] is False
    assert metadata["tool_calling"] is True
    assert metadata["context_length"] == 1048576
    assert metadata["max_output_tokens"] == 32768
    assert [item["id"] for item in metadata["thinking_options"]] == ["true", "false"]
    assert enabled["extra_body"] == {
        "chat_template_kwargs": {"enable_thinking": True},
        "reasoning_budget": 16384,
    }
    assert disabled["extra_body"] == {"chat_template_kwargs": {"enable_thinking": False}}


def test_nvidia_catalog_contains_model_specific_thinking_options():
    assert [item["id"] for item in get_nvidia_thinking_options("meta/muse-glimmer-30b")] == ["none", "minimal", "low", "medium", "high", "max"]
    assert [item["id"] for item in get_nvidia_thinking_options("nvidia/nemotron-3.5-lightning-30b-a3b")] == ["true", "false"]
    assert [item["id"] for item in get_nvidia_thinking_options("nvidia/nemotron-3-super-120b-a12b")] == ["high", "low", "none"]
    assert [item["id"] for item in get_nvidia_thinking_options("openai/gpt-oss-120b")] == ["low", "medium", "high"]
    assert resolve_nvidia_thinking_choice({"selected_model_id": "openai/gpt-oss-120b"}, "openai/gpt-oss-120b") == "medium"


def test_nvidia_apply_thinking_choice_updates_toggle_and_effort_config():
    lightning_cfg = apply_nvidia_thinking_choice(
        {"selected_model_id": "nvidia/nemotron-3.5-lightning-30b-a3b", "enable_thinking": True},
        "nvidia/nemotron-3.5-lightning-30b-a3b",
        "off",
    )
    assert lightning_cfg["enable_thinking"] is False
    assert resolve_nvidia_thinking_choice(lightning_cfg, "nvidia/nemotron-3.5-lightning-30b-a3b") == "false"

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
    assert resolve_nvidia_model_profile_name("meta/muse-glimmer-30b") == "muse_glimmer"
    assert resolve_nvidia_model_profile_name("nvidia/nemotron-3.5-lightning-30b-a3b") == "nemotron_35_lightning"
    assert resolve_nvidia_model_profile_name("z-ai/glm-5.2") == "glm_5_2"
    assert resolve_nvidia_model_profile_name("nvidia/nemotron-3-ultra-550b-a55b") == "nemotron_3_ultra"


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

    assert handler._cmd_nvidia_model("poolside/laguna-xs-2.1") is True

    workspace_config = config_manager.load()
    global_data = json.loads((app_root / ".reverie" / "config.json").read_text(encoding="utf-8"))

    assert workspace_config.active_model_source == "nvidia"
    assert workspace_config.nvidia["selected_model_id"] == "poolside/laguna-xs-2.1"
    assert workspace_config.nvidia["max_context_tokens"] == 262000
    assert workspace_config.nvidia["max_tokens"] == 8192
    assert global_data["active_model_source"] == "nvidia"
    assert global_data["nvidia"]["selected_model_id"] == "poolside/laguna-xs-2.1"
    assert global_data["nvidia"]["max_context_tokens"] == 262000
    assert global_data["nvidia"]["max_tokens"] == 8192
