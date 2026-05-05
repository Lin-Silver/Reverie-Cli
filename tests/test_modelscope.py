import sys
import types
from types import SimpleNamespace

from reverie.agent.agent import ReverieAgent
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
from reverie.provider_smoke import _redact, parse_model_overrides, run_provider_smoke


def test_modelscope_default_model_is_glm_51() -> None:
    cfg = default_modelscope_config()

    assert MODELSCOPE_DEFAULT_MODEL_ID == "ZhipuAI/GLM-5.1"
    assert cfg["selected_model_id"] == "ZhipuAI/GLM-5.1"
    assert cfg["selected_model_display_name"] == "GLM-5.1"
    assert cfg["max_context_tokens"] == 202752


def test_modelscope_catalog_context_lengths_match_model_cards() -> None:
    expected_context_lengths = {
        "ZhipuAI/GLM-5.1": 202752,
        "deepseek-ai/DeepSeek-V4-Pro": 1048576,
        "deepseek-ai/DeepSeek-V4-Flash": 1048576,
        "ZhipuAI/GLM-5": 202752,
        "moonshotai/Kimi-K2.6": 262144,
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
    assert resolve_modelscope_anthropic_base_url("https://api-inference.modelscope.cn/v1/chat/completions") == MODELSCOPE_DEFAULT_API_URL
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


def test_modelscope_latest_catalog_removes_superseded_models() -> None:
    catalog_by_id = {item["id"]: item for item in get_modelscope_model_catalog()}

    assert "deepseek-ai/DeepSeek-V3.2" not in catalog_by_id
    assert "moonshotai/Kimi-K2.5" not in catalog_by_id
    assert catalog_by_id["deepseek-ai/DeepSeek-V4-Pro"]["max_output_tokens"] == 393216
    assert catalog_by_id["deepseek-ai/DeepSeek-V4-Flash"]["max_output_tokens"] == 393216
    assert catalog_by_id["moonshotai/Kimi-K2.6"]["max_output_tokens"] == 98304


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


def test_modelscope_anthropic_stream_does_not_pass_stream_kwarg(monkeypatch, tmp_path) -> None:
    seen = {}

    class FakeStream:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def __iter__(self):
            return iter([SimpleNamespace(type="message_stop")])

        def get_final_message(self):
            return SimpleNamespace(content=[], stop_reason="end_turn", usage=None)

    class FakeMessages:
        def stream(self, **kwargs):
            seen["stream_kwargs"] = dict(kwargs)
            return FakeStream()

    class FakeAnthropic:
        def __init__(self, **kwargs):
            seen["init_kwargs"] = dict(kwargs)
            self.messages = FakeMessages()

    fake_module = types.ModuleType("anthropic")
    fake_module.Anthropic = FakeAnthropic
    monkeypatch.setitem(sys.modules, "anthropic", fake_module)

    config = SimpleNamespace(
        api_max_retries=1,
        api_initial_backoff=0.01,
        api_timeout=17,
        api_enable_debug_logging=False,
        active_model_source="modelscope",
        modelscope={
            "selected_model_id": "deepseek-ai/DeepSeek-V4-Pro",
            "selected_model_display_name": "DeepSeek V4 Pro",
            "max_tokens": 700000,
            "timeout": 29,
        },
    )
    agent = ReverieAgent(
        base_url=MODELSCOPE_DEFAULT_API_URL,
        api_key="ms-test",
        model="deepseek-ai/DeepSeek-V4-Pro",
        project_root=tmp_path,
        provider="anthropic",
        config=config,
    )
    agent.tool_executor.get_tool_schemas = lambda mode="reverie": []
    agent.messages.append({"role": "user", "content": "hello"})

    list(agent._process_streaming_anthropic())

    assert seen["init_kwargs"]["base_url"] == MODELSCOPE_DEFAULT_API_URL
    assert seen["init_kwargs"]["timeout"] == 29
    assert seen["stream_kwargs"]["model"] == "deepseek-ai/DeepSeek-V4-Pro"
    assert seen["stream_kwargs"]["max_tokens"] == 393216
    assert "stream" not in seen["stream_kwargs"]


def test_provider_smoke_redacts_secrets_and_skips_unknown(tmp_path) -> None:
    fake_modelscope_token = "ms-" + "abcdef1234567890"
    assert fake_modelscope_token[:9] not in _redact(f"Authorization: Bearer {fake_modelscope_token}")

    config_path = tmp_path / "config.json"
    config_path.write_text("{}", encoding="utf-8")
    results = run_provider_smoke(["unknown"], config_path=config_path, timeout_seconds=5)

    assert results[0].status == "skipped"
    assert results[0].error_class == "unknown_provider"


def test_provider_smoke_parses_model_overrides() -> None:
    single = parse_model_overrides("z-ai/glm-5.1,z-ai/glm4.7", ["nvidia"])
    multi = parse_model_overrides("nvidia:z-ai/glm-5.1|z-ai/glm4.7,modelscope:ZhipuAI/GLM-5.1", ["nvidia", "modelscope"])

    assert single == {"nvidia": ["z-ai/glm-5.1", "z-ai/glm4.7"]}
    assert multi == {
        "nvidia": ["z-ai/glm-5.1", "z-ai/glm4.7"],
        "modelscope": ["ZhipuAI/GLM-5.1"],
    }
