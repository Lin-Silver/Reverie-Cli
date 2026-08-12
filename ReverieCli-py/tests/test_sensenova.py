import base64
import sys
from types import SimpleNamespace

from rich.console import Console

from reverie import sensenova as sensenova_module
from reverie.agent.agent import ReverieAgent, _convert_messages_to_anthropic_format
from reverie.cli.commands import CommandHandler
from reverie.config import Config
from reverie.media_capabilities import build_media_capabilities
from reverie.sensenova import (
    build_sensenova_runtime_model_data,
    default_sensenova_config,
    fetch_sensenova_model_catalog,
    get_sensenova_model_catalog,
    normalize_sensenova_config,
    normalize_sensenova_reasoning_effort,
    build_sensenova_openai_options,
    resolve_sensenova_sdk_base_url,
)
from reverie.sensenova_tti_profiles.registry import get_sensenova_tti_model_catalog, get_sensenova_tti_profile
from reverie.provider_smoke import BUILTIN_PROVIDER_NAMES, SMOKE_RUNNERS


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
    assert normalize_sensenova_reasoning_effort("max") == "max"


def test_sensenova_catalog_only_exposes_flash_lite_for_vision():
    catalog = {item["id"]: item for item in get_sensenova_model_catalog()}
    assert set(catalog) == {"deepseek-v4-flash", "glm-5.2", "sensenova-6.8-flash-lite"}
    assert [item["id"] for item in catalog.values() if item["vision"]] == ["sensenova-6.8-flash-lite"]


def test_sensenova_live_catalog_uses_official_models_endpoint_and_filters_non_chat_models(monkeypatch):
    payload = {
        "data": [
            {
                "id": "sensenova-6.7-flash-lite",
                "name": "sensenova-6.7-flash-lite",
                "context_length": 262_144,
                "max_output_length": 65_536,
                "input_modalities": ["text", "image"],
                "output_modalities": ["text"],
                "supported_features": ["tools", "reasoning"],
            },
            {
                "id": "sensenova-6.8-flash-lite",
                "name": "SenseNova 6.8 Flash Lite",
                "description": "Current multimodal agent model.",
                "context_length": 262_144,
                "max_output_length": 65_536,
                "input_modalities": ["text", "image"],
                "output_modalities": ["text"],
                "supported_features": ["tools", "json_mode", "reasoning"],
            },
            {
                "id": "future-chat-model",
                "name": "Future Chat Model",
                "description": "Discovered from the live API.",
                "context_length": 123_456,
                "max_output_length": 7_890,
                "input_modalities": ["text"],
                "output_modalities": ["text"],
                "supported_features": ["tools"],
            },
            {
                "id": "sensenova-u1-fast",
                "name": "SenseNova U1 Fast",
                "input_modalities": ["text"],
                "output_modalities": ["image"],
            },
        ]
    }
    captured = {}

    class _Response:
        def raise_for_status(self):
            return None

        def json(self):
            return payload

    def fake_get(url, *, headers, timeout):
        captured["url"] = url
        captured["authorization"] = headers["Authorization"]
        captured["timeout"] = timeout
        return _Response()

    monkeypatch.setattr(sensenova_module, "_MODEL_CACHE", {"key": "", "expires_at": 0.0, "models": []})
    monkeypatch.setattr(sensenova_module.requests, "get", fake_get)

    catalog = fetch_sensenova_model_catalog(
        {"api_key": "sense-test", "api_url": "https://token.sensenova.cn/v1/chat/completions"},
        timeout=3,
        force_refresh=True,
    )

    assert captured == {
        "url": "https://token.sensenova.cn/v1/models",
        "authorization": "Bearer sense-test",
        "timeout": 3,
    }
    assert [item["id"] for item in catalog] == ["sensenova-6.8-flash-lite", "future-chat-model"]
    assert catalog[0]["vision"] is True
    assert catalog[0]["tool_calling"] is True
    assert catalog[0]["context_length"] == 262_144
    assert catalog[1]["display_name"] == "Future Chat Model"
    assert catalog[1]["max_output_tokens"] == 7_890


def test_sensenova_live_catalog_failure_falls_back_and_legacy_flash_lite_migrates(monkeypatch):
    monkeypatch.setattr(
        sensenova_module.requests,
        "get",
        lambda url, *, headers, timeout: (_ for _ in ()).throw(OSError("offline")),
    )
    catalog = get_sensenova_model_catalog(
        {"api_key": "sense-test"},
        fetch_live=True,
        force_refresh=True,
    )
    assert {item["id"] for item in catalog} == {
        "deepseek-v4-flash",
        "glm-5.2",
        "sensenova-6.8-flash-lite",
    }

    migrated = normalize_sensenova_config({"selected_model_id": "sensenova-6.7-flash-lite"})
    assert migrated["selected_model_id"] == "sensenova-6.8-flash-lite"
    assert migrated["selected_model_display_name"] == "SenseNova 6.8 Flash Lite"


def test_sensenova_model_command_fetches_live_catalog_before_selection(tmp_path, monkeypatch):
    captured = {}

    class _Manager:
        def __init__(self):
            self.config = Config(sensenova={"api_key": "sense-test"})

        def load(self):
            return self.config

        def save(self, config):
            self.config = config

    def fake_catalog(provider_config, *, fetch_live=False, force_refresh=False):
        captured.update(
            provider_config=dict(provider_config),
            fetch_live=fetch_live,
            force_refresh=force_refresh,
        )
        return [sensenova_module._sensenova_model(
            "future-chat-model",
            "Future Chat Model",
            "Discovered live.",
        )]

    monkeypatch.setattr(sensenova_module, "get_sensenova_model_catalog", fake_catalog)
    manager = _Manager()
    handler = CommandHandler(
        Console(record=True, force_terminal=False, width=120),
        {"config_manager": manager, "project_root": tmp_path},
    )

    assert handler._cmd_sensenova_model("future-chat-model") is True
    assert captured["provider_config"]["api_key"] == "sense-test"
    assert captured["fetch_live"] is True
    assert captured["force_refresh"] is True
    assert manager.config.active_model_source == "sensenova"
    assert manager.config.sensenova["selected_model_id"] == "future-chat-model"


def test_sensenova_is_registered_for_provider_smoke():
    assert "sensenova" in BUILTIN_PROVIDER_NAMES
    assert "sensenova" in SMOKE_RUNNERS


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
    assert runtime["provider"] == "openai-chat"
    assert runtime["max_context_tokens"] == 1_000_000
    assert runtime["thinking_mode"] == "none"

    flash_lite = build_sensenova_runtime_model_data(cfg, model_id="sensenova-6.8-flash-lite")
    assert flash_lite is not None
    assert flash_lite["provider"] == "openai-chat"
    assert flash_lite["base_url"] == "https://token.sensenova.cn/v1"
    assert flash_lite["thinking_mode"] == "provider-managed"
    assert {item["id"]: item for item in get_sensenova_model_catalog()}[
        "sensenova-6.8-flash-lite"
    ]["thinking_control"] == "provider-managed"

    options = build_sensenova_openai_options({**cfg, "max_tokens": 2048}, "sensenova-6.8-flash-lite")
    assert options["max_tokens"] == 2048
    assert options["temperature"] == 0.7
    assert options["top_p"] == 0.8
    assert options["presence_penalty"] == 1.5
    assert options["extra_body"] == {
        "reasoning_effort": "none",
        "top_k": 20,
        "min_p": 0.0,
        "repetition_penalty": 1.0,
    }


def test_sensenova_flash_lite_uses_bounded_default_output_budget():
    options = build_sensenova_openai_options(
        {
            **default_sensenova_config(),
            "selected_model_id": "sensenova-6.8-flash-lite",
        }
    )

    assert options["max_tokens"] == 6144
    assert options["extra_body"]["reasoning_effort"] == "medium"
    assert "output_config" not in options["extra_body"]


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
    assert config.active_model.provider == "openai-chat"


def test_config_reuses_legacy_sensenova_model_api_key():
    config = Config.from_dict(
        {
            "models": [
                {
                    "model": "sensenova-6.7-flash-lite",
                    "name": "SenseNova",
                    "base_url": "https://token.sensenova.cn/v1",
                    "api_key": "legacy-secret",
                }
            ],
            "sensenova": {"api_key": ""},
        }
    )

    assert config.sensenova["api_key"] == "legacy-secret"


def test_sensenova_sdk_url_and_openai_options():
    assert resolve_sensenova_sdk_base_url("https://token.sensenova.cn/v1/chat/completions") == "https://token.sensenova.cn/v1"
    options = build_sensenova_openai_options(
        {
            **default_sensenova_config(),
            "api_key": "secret",
            "reasoning_effort": "high",
            "max_tokens": 4096,
            "temperature": 0.7,
            "top_p": 0.9,
        },
        "deepseek-v4-flash",
    )
    assert options["temperature"] == 0.7
    assert options["top_p"] == 0.9
    assert options["max_tokens"] == 4096
    assert options["extra_body"] == {"reasoning_effort": "high"}


def test_sensenova_openai_client_uses_standard_api_key(monkeypatch, tmp_path):
    captured = {}

    class FakeOpenAI:
        def __init__(self, **kwargs):
            captured.update(kwargs)
            self.chat = SimpleNamespace(completions=SimpleNamespace())

    monkeypatch.setitem(sys.modules, "openai", SimpleNamespace(OpenAI=FakeOpenAI))
    config = Config(
        active_model_source="sensenova",
        sensenova={"api_key": "secret", "selected_model_id": "deepseek-v4-flash", "timeout": 123},
    )
    agent = ReverieAgent(
        base_url="https://token.sensenova.cn/v1",
        api_key="secret",
        model="deepseek-v4-flash",
        project_root=tmp_path,
        provider="openai-chat",
        config=config,
    )

    agent._init_client()

    assert captured["api_key"] == "secret"
    assert captured["base_url"] == "https://token.sensenova.cn/v1"
    assert captured["timeout"] == 123
    assert "auth_token" not in captured


def test_anthropic_message_conversion_preserves_url_and_base64_images():
    encoded = base64.b64encode(b"image").decode()
    _, messages = _convert_messages_to_anthropic_format(
        [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": "describe"},
                    {"type": "image_url", "image_url": {"url": "https://example.test/a.png"}},
                    {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{encoded}"}},
                ],
            }
        ]
    )
    blocks = messages[0]["content"]
    assert blocks[1] == {"type": "image", "source": {"type": "url", "url": "https://example.test/a.png"}}
    assert blocks[2] == {"type": "image", "source": {"type": "base64", "media_type": "image/png", "data": encoded}}


def test_sensenova_u1_fast_tti_profile_and_capabilities(tmp_path):
    catalog = get_sensenova_tti_model_catalog()
    assert [item["id"] for item in catalog] == ["sensenova-u1-fast"]
    assert catalog[0]["input_modalities"] == ["text"]

    captured = {}

    class Images:
        def generate(self, **kwargs):
            captured.update(kwargs)
            return SimpleNamespace(data=[SimpleNamespace(b64_json=base64.b64encode(b"png").decode(), url=None)])

    profile = get_sensenova_tti_profile("sensenova-u1-fast")
    result = profile.generate_image(
        SimpleNamespace(images=Images()),
        prompt="infographic",
        output_path=tmp_path,
        size="2048x2048",
        n=4,
    )
    assert captured == {"model": "sensenova-u1-fast", "prompt": "infographic", "size": "2048x2048", "n": 1}
    assert len(result["saved_images"]) == 1

    config = Config(sensenova={"api_key": "secret"})
    capabilities = build_media_capabilities(config=config, project_root=tmp_path)
    assert capabilities["image"]["sources"]["sensenova"]["models"][0]["id"] == "sensenova-u1-fast"
