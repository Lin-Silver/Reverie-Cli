from __future__ import annotations

from types import SimpleNamespace
import json

import pytest

from reverie.agent.agent import ReverieAgent, _invoke_system_curl
from reverie.config import (
    Config,
    ConfigManager,
    EXTERNAL_MODEL_SOURCES,
    MODEL_SOURCE_DISPLAY_NAMES,
    ModelConfig,
    SUPPORTED_ACTIVE_MODEL_SOURCES,
    is_config_version_older,
    model_source_display_name,
    normalize_model_provider,
)
from reverie.cli.interface import ReverieInterface


@pytest.mark.parametrize(
    ("alias", "canonical"),
    [
        ("openai", "openai-chat"),
        ("openai-old", "openai-chat"),
        ("chat.completions", "openai-chat"),
        ("openai-sdk", "openai-chat"),
        ("openai-res", "openai-responses"),
        ("openai-response", "openai-responses"),
        ("responses", "openai-responses"),
        ("request", "request"),
        ("anthropic", "anthropic"),
        ("curl", "curl"),
    ],
)
def test_model_provider_aliases_have_one_persisted_name(alias: str, canonical: str) -> None:
    assert normalize_model_provider(alias) == canonical
    model = ModelConfig.from_dict(
        {"model": "demo", "model_display_name": "Demo", "base_url": "https://example.test/v1", "provider": alias}
    )
    assert model.provider == canonical
    assert model.to_dict()["provider"] == canonical


def test_old_config_serializes_as_235_with_openai_chat() -> None:
    config = Config.from_dict(
        {
            "config_version": "2.3.3",
            "models": [
                {"model": "demo", "model_display_name": "Demo", "base_url": "https://example.test/v1", "provider": "openai"}
            ],
        }
    )
    config.config_version = "2.3.5"
    payload = config.to_dict()
    assert payload["config_version"] == "2.3.5"
    assert payload["models"][0]["provider"] == "openai-chat"
    assert is_config_version_older("2.3.3") is True
    assert is_config_version_older("2.3.4") is True
    assert is_config_version_older("2.3.5") is False


def test_config_manager_automatically_migrates_pre_235_config(monkeypatch, tmp_path) -> None:
    app_root = tmp_path / "app"
    config_path = app_root / ".reverie" / "config.json"
    config_path.parent.mkdir(parents=True)
    config_path.write_text(
        json.dumps(
            {
                "config_version": "2.3.3",
                "models": [
                    {
                        "model": "demo",
                        "model_display_name": "Demo",
                        "base_url": "https://example.test/v1",
                        "api_key": "secret",
                        "provider": "openai",
                        "supports_vision": False,
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr("reverie.config.get_app_root", lambda: app_root)

    config = ConfigManager(tmp_path / "workspace").load()
    saved = json.loads(config_path.read_text(encoding="utf-8"))

    assert config.config_version == "2.3.5"
    assert config.models[0].provider == "openai-chat"
    assert saved["config_version"] == "2.3.5"
    assert saved["models"][0]["provider"] == "openai-chat"


@pytest.mark.parametrize("source", EXTERNAL_MODEL_SOURCES)
def test_external_startup_provider_labels_always_use_source_name(source: str) -> None:
    config = Config(active_model_source=source)
    assert ReverieInterface._resolve_provider_label(object(), config) == MODEL_SOURCE_DISPLAY_NAMES[source]


@pytest.mark.parametrize(
    ("provider", "expected"),
    [
        ("openai-chat", "OpenAI Chat Completions"),
        ("openai-responses", "OpenAI Responses"),
        ("anthropic", "Anthropic"),
        ("request", "Python requests"),
        ("curl", "curl"),
    ],
)
def test_standard_source_provider_label_uses_call_method(provider: str, expected: str) -> None:
    config = Config(
        models=[ModelConfig("demo", "Demo", "https://example.test/v1", provider=provider)],
        active_model_source="standard",
    )
    assert ReverieInterface._resolve_provider_label(object(), config) == expected


def test_unconfigured_standard_source_has_neutral_provider_label() -> None:
    assert ReverieInterface._resolve_provider_label(object(), Config()) == "Custom Provider"


def test_source_display_table_covers_every_supported_source() -> None:
    assert set(MODEL_SOURCE_DISPLAY_NAMES) == set(SUPPORTED_ACTIVE_MODEL_SOURCES)
    for source in SUPPORTED_ACTIVE_MODEL_SOURCES:
        assert model_source_display_name(source) == MODEL_SOURCE_DISPLAY_NAMES[source]


@pytest.mark.parametrize(
    ("source", "builder_name"),
    [
        ("codex", "build_codex_runtime_model_data"),
        ("aihubmix", "build_aihubmix_runtime_model_data"),
        ("agnes", "build_agnes_runtime_model_data"),
        ("sensenova", "build_sensenova_runtime_model_data"),
        ("unlimitedsurf", "build_unlimitedsurf_runtime_model_data"),
        ("nvidia", "build_nvidia_runtime_model_data"),
        ("modelscope", "build_modelscope_runtime_model_data"),
        ("webgemini", "build_webgemini_runtime_model_data"),
    ],
)
def test_unavailable_external_source_never_falls_back_to_standard_model(monkeypatch, source: str, builder_name: str) -> None:
    monkeypatch.setattr(f"reverie.config.{builder_name}", lambda *args, **kwargs: None)
    config = Config(
        models=[ModelConfig("fallback", "Fallback", "https://example.test/v1")],
        active_model_source=source,
    )
    assert config.active_model is None


@pytest.mark.parametrize("source", EXTERNAL_MODEL_SOURCES)
def test_agent_request_status_labels_use_external_source_name(tmp_path, source: str) -> None:
    config = Config(active_model_source=source)
    agent = ReverieAgent(
        base_url="https://example.test/v1",
        api_key="secret",
        model="demo",
        project_root=tmp_path,
        provider="openai-chat",
        config=config,
    )
    expected = f"{MODEL_SOURCE_DISPLAY_NAMES[source]} API"
    assert agent._openai_sdk_provider_label() == expected
    assert agent._request_provider_label() == expected
    assert agent._responses_provider_label() == expected


def test_sensenova_runtime_timeout_is_honored(tmp_path) -> None:
    config = Config(active_model_source="sensenova", sensenova={"timeout": 300})
    agent = ReverieAgent(
        base_url="https://token.sensenova.cn/v1",
        api_key="secret",
        model="deepseek-v4-flash",
        project_root=tmp_path,
        provider="openai-chat",
        config=config,
    )
    assert agent._resolve_provider_timeout() == 300


def test_sensenova_vision_model_is_accepted_by_attachment_checks() -> None:
    config = Config(
        active_model_source="sensenova",
        sensenova={"api_key": "secret", "selected_model_id": "sensenova-6.7-flash-lite"},
    )
    assert ReverieInterface._can_attach_inline_images(object(), config) == (True, "")
    assert ReverieInterface._current_inline_media_modalities(object(), config) == ["image"]


def test_curl_endpoint_auto_detects_responses(tmp_path) -> None:
    agent = ReverieAgent(
        base_url="https://example.test/v1/responses",
        api_key="secret",
        model="demo",
        project_root=tmp_path,
        provider="curl",
    )
    assert agent._resolve_curl_url() == "https://example.test/v1/responses"
    assert agent._curl_uses_responses() is True

    agent.base_url = "https://example.test/v1"
    assert agent._resolve_curl_url() == "https://example.test/v1/chat/completions"
    assert agent._curl_uses_responses() is False


def test_responses_result_extracts_text_and_function_calls(tmp_path) -> None:
    agent = ReverieAgent(
        base_url="https://api.openai.com/v1",
        api_key="secret",
        model="demo",
        project_root=tmp_path,
        provider="openai-responses",
    )
    state, usage = agent._responses_result_state(
        {
            "output": [
                {"type": "message", "content": [{"type": "output_text", "text": "hello"}]},
                {"type": "function_call", "call_id": "call_1", "name": "demo_tool", "arguments": '{"x":1}'},
            ],
            "usage": {"input_tokens": 3, "output_tokens": 2},
        }
    )
    assert state.cleaned_content() == "hello"
    assert state.tool_calls[0]["id"] == "call_1"
    assert state.tool_calls[0]["function"]["name"] == "demo_tool"
    assert usage == {"input_tokens": 3, "output_tokens": 2}


def test_openai_responses_provider_calls_sdk_responses_endpoint(tmp_path) -> None:
    captured = {}

    class FakeResponses:
        def create(self, **kwargs):
            captured.update(kwargs)
            return {
                "output": [{"type": "message", "content": [{"type": "output_text", "text": "hello"}]}],
                "usage": {"input_tokens": 1, "output_tokens": 1},
            }

    agent = ReverieAgent(
        base_url="https://api.openai.com/v1/responses",
        api_key="secret",
        model="demo",
        project_root=tmp_path,
        provider="openai-responses",
    )
    agent._client = SimpleNamespace(responses=FakeResponses())
    agent._client_config_key = agent._provider_client_key()

    result = agent._process_non_streaming_openai_responses()

    assert result == "hello"
    assert captured["model"] == "demo"
    assert captured["stream"] is False
    assert isinstance(captured["input"], list)


def test_system_curl_uses_argument_list_without_shell(monkeypatch) -> None:
    captured = {}

    def fake_run(command, **kwargs):
        captured["command"] = command
        captured["kwargs"] = kwargs
        return SimpleNamespace(stdout='{"choices": []}', stderr="", returncode=0)

    monkeypatch.setattr("shutil.which", lambda name: "curl.exe")
    monkeypatch.setattr("subprocess.run", fake_run)
    response = _invoke_system_curl(
        url="https://example.test/v1/chat/completions",
        headers={"Authorization": "Bearer secret", "Content-Type": "application/json"},
        payload={"model": "demo", "messages": [], "stream": False},
        stream=False,
        timeout=60,
    )

    assert response.json() == {"choices": []}
    assert captured["command"][0] == "curl.exe"
    assert captured["kwargs"]["check"] is False
    assert "shell" not in captured["kwargs"]
