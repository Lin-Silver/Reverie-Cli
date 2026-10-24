from types import SimpleNamespace

import pytest
from rich.console import Console

from reverie.cli.commands import CommandHandler
from reverie.cli.tui_selector import SelectorAction
from reverie.config import Config, ConfigManager
from reverie.desktop_catalog import apply_model_selection, build_model_sources_payload
from reverie.nvidia import (
    build_nvidia_openai_options,
    build_nvidia_request_defaults,
    build_nvidia_runtime_model_data,
    get_nvidia_model_catalog,
    get_nvidia_model_metadata,
    normalize_nvidia_config,
    nvidia_model_requires_preserved_reasoning_history,
)


RETIRED_MODELS = (
    "deepseek-ai/deepseek-v4-flash-0731",
    "deepseek-ai/deepseek-v4-pro-0813",
    "moonshotai/kimi-k3",
    "minimaxai/minimax-m3",
    "stepfun-ai/step-3.7-flash",
    "openai/gpt-oss-120b",
    "z-ai/glm-5.3",
)


@pytest.mark.parametrize("model_id", RETIRED_MODELS)
def test_retired_hosted_models_fall_back_to_available_default(model_id):
    assert get_nvidia_model_metadata(model_id) is None
    normalized = normalize_nvidia_config({"selected_model_id": model_id})
    assert normalized["selected_model_id"] == "meta/muse-glimmer-30b"
    runtime = build_nvidia_runtime_model_data({**normalized, "api_key": "test"})
    assert runtime["model"] == "meta/muse-glimmer-30b"


def test_new_hosted_models_are_shared_with_desktop_catalog():
    expected = {
        "minimaxai/minimax-m3.1-flash": (262144, ["image", "video"]),
        "nvidia/nemotron-3.5-super-vl-120b-a12b": (262144, ["image", "video"]),
        "stepfun-ai/step-5-preview": (1048576, ["image"]),
        "deepseek-ai/deepseek-v4.1-flash": (1048576, ["image"]),
        "z-ai/glm-5.3-flash": (1048576, ["image"]),
        "openai/gpt-oss-20b": (131072, []),
    }
    config = Config()
    payload = build_model_sources_payload(config)
    desktop = next(source for source in payload["sources"] if source["id"] == "nvidia")
    desktop_ids = {model["id"] for model in desktop["models"]}
    assert desktop_ids == {model["id"] for model in get_nvidia_model_catalog()}
    assert not desktop_ids.intersection(RETIRED_MODELS)
    assert "z-ai/glm-5.3" not in desktop_ids
    for model in desktop["models"]:
        if model["id"] in {"deepseek-ai/deepseek-v4.1-flash", "z-ai/glm-5.3-flash"}:
            assert "可能尚未针对该模型进行多并发调用优化" in model["description"]
            assert "本次验证多次超时" in model["description"]
    for model_id, (context_length, modalities) in expected.items():
        assert model_id in desktop_ids
        apply_model_selection(config, "nvidia", model_id)
        assert config.nvidia["selected_model_id"] == model_id
        assert config.nvidia["max_context_tokens"] == context_length
        assert get_nvidia_model_metadata(model_id)["vision_modalities"] == modalities


def test_minimax_m31_has_its_own_reasoning_and_output_profile():
    model_id = "minimaxai/minimax-m3.1-flash"
    config = {"selected_model_id": model_id, "reasoning_effort": "xhigh", "max_tokens": 1000000}
    options = build_nvidia_openai_options(config)

    assert options == {
        "temperature": 1.0,
        "top_p": 0.95,
        "max_tokens": 65536,
        "extra_body": {"chat_template_kwargs": {"reasoning_effort": "xhigh"}},
    }
    assert nvidia_model_requires_preserved_reasoning_history(model_id)
    assert build_nvidia_openai_options({"selected_model_id": model_id})["max_tokens"] == 65536


@pytest.mark.parametrize("effort", ["none", "low", "high"])
def test_nemotron_35_super_uses_native_reasoning_and_hosted_output_cap(effort):
    options = build_nvidia_openai_options({
        "selected_model_id": "nvidia/nemotron-3.5-super-vl-120b-a12b",
        "reasoning_effort": effort,
        "max_tokens": 1048576,
    })
    assert options["extra_body"] == {"reasoning_effort": effort}
    assert options["max_tokens"] == 131072
    assert options["temperature"] == 1.0
    assert options["top_p"] == 0.95


def test_step_5_preserves_reasoning_and_respects_configured_output_budget():
    config = {"selected_model_id": "stepfun-ai/step-5-preview", "max_tokens": 8192}
    options = build_nvidia_request_defaults(config)
    assert options == {"temperature": 1.0, "top_p": 0.95, "top_k": 0, "max_tokens": 8192}
    assert nvidia_model_requires_preserved_reasoning_history(config["selected_model_id"])
    assert get_nvidia_model_metadata(config["selected_model_id"])["thinking_control"] == "fixed"


def test_deepseek_41_uses_provider_example_budget_without_legacy_template_kwargs():
    options = build_nvidia_openai_options({"selected_model_id": "deepseek-ai/deepseek-v4.1-flash"})
    assert options == {"temperature": 1.0, "top_p": 0.95, "max_tokens": 262144}


@pytest.mark.parametrize("model_id,budget", [
    ("deepseek-ai/deepseek-v4.1-flash", 262144),
    ("minimaxai/minimax-m3.1-flash", 65536),
    ("stepfun-ai/step-5-preview", 4096),
])
def test_cli_and_desktop_selection_apply_model_default_budget(tmp_path, monkeypatch, model_id, budget):
    config = Config()
    apply_model_selection(config, "nvidia", model_id)
    assert config.nvidia["max_tokens"] == budget
    config.nvidia["max_tokens"] = 2048
    apply_model_selection(config, "nvidia", model_id)
    assert config.nvidia["max_tokens"] == 2048

    app_root = tmp_path / "app"
    project_root = tmp_path / "project"
    project_root.mkdir()
    monkeypatch.setattr("reverie.config.get_app_root", lambda: app_root)
    monkeypatch.setattr("reverie.config.get_launcher_root", lambda: app_root)
    manager = ConfigManager(project_root)
    handler = CommandHandler(
        Console(force_terminal=False), {"config_manager": manager, "project_root": project_root},
    )
    monkeypatch.setattr(handler, "_configure_nvidia_thinking_for_model", lambda cfg, model: cfg)
    assert handler._cmd_nvidia_model(model_id) is True
    assert manager.load().nvidia["max_tokens"] == budget


def test_cli_selector_puts_nvidia_concurrency_note_before_model_id(tmp_path, monkeypatch):
    app_root = tmp_path / "app"
    project_root = tmp_path / "project"
    project_root.mkdir()
    monkeypatch.setattr("reverie.config.get_app_root", lambda: app_root)
    monkeypatch.setattr("reverie.config.get_launcher_root", lambda: app_root)
    captured = []

    def capture_selector(selector):
        captured.extend(selector.items)
        return SimpleNamespace(action=SelectorAction.CANCEL, selected_item=None)

    monkeypatch.setattr("reverie.cli.tui_selector.ModelSelector.run", capture_selector)
    handler = CommandHandler(
        Console(force_terminal=False),
        {"config_manager": ConfigManager(project_root), "project_root": project_root},
    )
    assert handler._cmd_nvidia_model("") is True
    for model_id in ("deepseek-ai/deepseek-v4.1-flash", "z-ai/glm-5.3-flash"):
        description = next(item.description for item in captured if model_id in item.description)
        assert description.startswith("NVIDIA 可能尚未针对该模型进行多并发调用优化")


@pytest.mark.parametrize("effort", ["low", "high", "max"])
def test_glm_53_flash_uses_native_effort_and_clears_chat_thinking(effort):
    options = build_nvidia_openai_options({
        "selected_model_id": "z-ai/glm-5.3-flash", "reasoning_effort": effort,
    })
    assert options["extra_body"] == {
        "reasoning_effort": effort, "chat_template_kwargs": {"clear_thinking": True},
    }
    assert options["temperature"] == 1.0
    assert options["top_p"] == 0.95


def test_gpt_oss_20b_uses_hosted_output_cap_and_model_specific_reasoning():
    options = build_nvidia_openai_options({
        "selected_model_id": "openai/gpt-oss-20b", "max_tokens": 16384,
    })
    assert options == {
        "temperature": 1.0, "top_p": 1.0, "max_tokens": 4096,
        "extra_body": {"reasoning_effort": "medium"},
    }
