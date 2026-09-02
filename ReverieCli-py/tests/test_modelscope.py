from types import SimpleNamespace

from reverie.agent.agent import ReverieAgent
from reverie.config import Config
from reverie.modelscope import (
    MODELSCOPE_DEFAULT_API_URL,
    MODELSCOPE_DEFAULT_MODEL_ID,
    apply_modelscope_thinking_choice,
    build_modelscope_openai_options,
    build_modelscope_runtime_model_data,
    default_modelscope_config,
    get_modelscope_model_catalog,
    get_modelscope_model_metadata,
    normalize_modelscope_config,
    resolve_modelscope_openai_base_url,
    resolve_modelscope_thinking_choice,
)
from reverie.provider_smoke import _redact, parse_model_overrides, run_provider_smoke


def test_modelscope_default_model_is_live_verified_step_37_flash() -> None:
    cfg = default_modelscope_config()

    assert MODELSCOPE_DEFAULT_MODEL_ID == "stepfun-ai/Step-3.7-Flash"
    assert cfg["selected_model_id"] == "stepfun-ai/Step-3.7-Flash"
    assert cfg["selected_model_display_name"] == "Step-3.7-Flash"
    assert cfg["max_context_tokens"] == 262144


def test_modelscope_catalog_exactly_matches_requested_models_and_capabilities() -> None:
    expected = {
        "stepfun-ai/Step-3.7-Flash": {
            "context": 262144,
            "vision": True,
            "reasoning": ["low", "medium", "high"],
        },
        "ZhipuAI/GLM-5.2": {
            "context": 1048576,
            "vision": False,
            "reasoning": ["none", "high", "max"],
        },
        "deepseek-ai/DeepSeek-V4-Pro": {
            "context": 1048576,
            "vision": False,
            "reasoning": ["true", "false"],
        },
        "deepseek-ai/DeepSeek-V4-Flash": {
            "context": 1048576,
            "vision": False,
            "reasoning": ["true", "false"],
        },
    }
    catalog = {item["id"]: item for item in get_modelscope_model_catalog()}

    assert set(catalog) == set(expected)
    for model_id, capability in expected.items():
        metadata = catalog[model_id]
        assert metadata["transport"] == "openai-chat"
        assert metadata["context_length"] == capability["context"]
        assert metadata["vision"] is capability["vision"]
        assert [item["id"] for item in metadata["thinking_options"]] == capability["reasoning"]
        assert get_modelscope_model_metadata(model_id.lower())["id"] == model_id


def test_modelscope_base_url_normalizes_openai_and_legacy_anthropic_paths() -> None:
    assert resolve_modelscope_openai_base_url("api-inference.modelscope.cn/v1/messages") == MODELSCOPE_DEFAULT_API_URL
    assert resolve_modelscope_openai_base_url("https://api-inference.modelscope.cn/v1") == MODELSCOPE_DEFAULT_API_URL
    assert resolve_modelscope_openai_base_url("https://api-inference.modelscope.cn/v1/chat/completions") == MODELSCOPE_DEFAULT_API_URL
    assert resolve_modelscope_openai_base_url("https://proxy.example.com/messages") == "https://proxy.example.com/v1"


def test_modelscope_runtime_uses_openai_chat_and_preserves_vision(monkeypatch) -> None:
    monkeypatch.setenv("MODELSCOPE_API_KEY", "ms-test")
    runtime = build_modelscope_runtime_model_data(
        {
            "api_url": "https://api-inference.modelscope.cn/v1/messages",
            "selected_model_id": "stepfun-ai/Step-3.7-Flash",
        }
    )

    assert runtime is not None
    assert runtime["model"] == "stepfun-ai/Step-3.7-Flash"
    assert runtime["provider"] == "openai-chat"
    assert runtime["base_url"] == MODELSCOPE_DEFAULT_API_URL
    assert runtime["api_key"] == "ms-test"
    assert runtime["max_context_tokens"] == 262144
    assert runtime["supports_vision"] is True
    assert runtime["vision_modalities"] == ["image"]


def test_modelscope_openai_options_apply_each_models_native_reasoning_format() -> None:
    step = build_modelscope_openai_options(
        {"selected_model_id": "stepfun-ai/Step-3.7-Flash", "reasoning_effort": "high"},
    )
    assert step["extra_body"] == {"chat_template_kwargs": {"reasoning_effort": "high"}}
    assert (step["temperature"], step["top_p"]) == (1.0, 0.95)

    glm = build_modelscope_openai_options(
        {"selected_model_id": "ZhipuAI/GLM-5.2", "reasoning_effort": "none"},
    )
    assert glm["extra_body"] == {"chat_template_kwargs": {"enable_thinking": False}}

    deepseek = build_modelscope_openai_options(
        {"selected_model_id": "deepseek-ai/DeepSeek-V4-Flash", "reasoning_effort": "false"},
    )
    assert deepseek["extra_body"] == {
        "chat_template_kwargs": {"reasoning_effort": False},
    }


def test_modelscope_reasoning_selection_round_trips_through_config() -> None:
    cfg = apply_modelscope_thinking_choice(
        {"selected_model_id": "stepfun-ai/Step-3.7-Flash"},
        "ZhipuAI/GLM-5.2",
        "high",
    )
    assert cfg["selected_model_id"] == "ZhipuAI/GLM-5.2"
    assert cfg["reasoning_effort"] == "high"
    assert resolve_modelscope_thinking_choice(cfg) == "high"


def test_modelscope_saved_removed_selection_falls_back_to_default(monkeypatch) -> None:
    monkeypatch.setenv("MODELSCOPE_TOKEN", "ms-token")

    cfg = normalize_modelscope_config({"selected_model_id": "ZhipuAI/GLM-5.1"})
    runtime = build_modelscope_runtime_model_data(cfg)

    assert cfg["selected_model_id"] == "stepfun-ai/Step-3.7-Flash"
    assert runtime is not None
    assert runtime["model"] == "stepfun-ai/Step-3.7-Flash"


def test_config_active_model_resolves_modelscope_openai_transport(monkeypatch) -> None:
    monkeypatch.setenv("MODELSCOPE_TOKEN", "ms-token")
    config = Config(
        models=[],
        active_model_source="modelscope",
        modelscope=normalize_modelscope_config({"selected_model_id": "deepseek-ai/DeepSeek-V4-Pro"}),
    )

    active_model = config.active_model

    assert active_model is not None
    assert active_model.provider == "openai-chat"
    assert active_model.model == "deepseek-ai/DeepSeek-V4-Pro"
    assert active_model.base_url == MODELSCOPE_DEFAULT_API_URL
    assert active_model.max_context_tokens == 1048576


def test_modelscope_agent_builds_openai_kwargs_from_core_capabilities(tmp_path) -> None:
    cfg = SimpleNamespace(
        active_model_source="modelscope",
        modelscope={
            "selected_model_id": "ZhipuAI/GLM-5.2",
            "reasoning_effort": "high",
            "max_tokens": 70000,
        },
    )
    agent = ReverieAgent(
        base_url=MODELSCOPE_DEFAULT_API_URL,
        api_key="ms-test",
        model="ZhipuAI/GLM-5.2",
        project_root=tmp_path,
        provider="openai-chat",
        config=cfg,
    )

    kwargs = agent._build_openai_chat_completion_kwargs(
        messages=[{"role": "user", "content": "hello"}],
        tools=[],
        stream=True,
    )

    assert kwargs["model"] == "ZhipuAI/GLM-5.2"
    assert kwargs["max_tokens"] == 70000
    assert kwargs["extra_body"] == {
        "chat_template_kwargs": {"enable_thinking": True, "reasoning_effort": "high"},
    }


def test_provider_smoke_redacts_secrets_and_skips_unknown(tmp_path) -> None:
    fake_modelscope_token = "ms-" + "abcdef1234567890"
    assert fake_modelscope_token[:9] not in _redact(f"Authorization: Bearer {fake_modelscope_token}")

    config_path = tmp_path / "config.json"
    config_path.write_text("{}", encoding="utf-8")
    results = run_provider_smoke(["unknown"], config_path=config_path, timeout_seconds=5)

    assert results[0].status == "skipped"
    assert results[0].error_class == "unknown_provider"


def test_provider_smoke_parses_model_overrides() -> None:
    single = parse_model_overrides("moonshotai/kimi-k3,meta/muse-glimmer-30b", ["nvidia"])
    multi = parse_model_overrides(
        "nvidia:moonshotai/kimi-k3|meta/muse-glimmer-30b,modelscope:stepfun-ai/Step-3.7-Flash",
        ["nvidia", "modelscope"],
    )

    assert single == {"nvidia": ["moonshotai/kimi-k3", "meta/muse-glimmer-30b"]}
    assert multi == {
        "nvidia": ["moonshotai/kimi-k3", "meta/muse-glimmer-30b"],
        "modelscope": ["stepfun-ai/Step-3.7-Flash"],
    }
