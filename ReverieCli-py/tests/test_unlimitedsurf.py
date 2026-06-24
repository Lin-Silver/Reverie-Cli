from types import SimpleNamespace

from rich.console import Console

from reverie.agent.agent import ReverieAgent
from reverie.cli.commands import CommandHandler
from reverie.cli.help_catalog import HELP_TOPICS, normalize_help_topic
from reverie.config import Config, ConfigManager
from reverie.unlimitedsurf import (
    build_unlimitedsurf_chat_payload,
    build_unlimitedsurf_runtime_model_data,
    get_unlimitedsurf_model_catalog,
    normalize_unlimitedsurf_config,
    resolve_unlimitedsurf_base_url,
    resolve_unlimitedsurf_chat_url,
)


def test_unlimitedsurf_catalog_fetches_public_model_list(monkeypatch) -> None:
    class FakeResponse:
        def raise_for_status(self):
            return None

        def json(self):
            return {
                "object": "list",
                "data": [
                    {
                        "id": "gateway-gpt-5",
                        "name": "GPT-5",
                        "provider": "openai",
                        "tier": "flagship",
                    },
                    {
                        "id": "gateway-claude-opus-4-7",
                        "name": "Claude Opus 4.7",
                        "provider": "anthropic",
                        "tier": "flagship",
                    },
                ],
            }

    seen = {}

    def fake_get(url, headers=None, timeout=None):
        seen["url"] = url
        seen["headers"] = headers
        seen["timeout"] = timeout
        return FakeResponse()

    monkeypatch.setattr("reverie.unlimitedsurf.requests.get", fake_get)

    catalog = get_unlimitedsurf_model_catalog(fetch_live=True, timeout=3)

    assert seen["url"] == "https://unlimited.surf/api/models"
    assert seen["headers"] == {"Accept": "application/json"}
    assert seen["timeout"] == 3
    assert [item["id"] for item in catalog] == [
        "gateway-gpt-5",
        "gateway-claude-opus-4-7",
    ]
    assert catalog[0]["display_name"] == "GPT-5"
    assert catalog[0]["provider"] == "openai"


def test_unlimitedsurf_url_resolution_accepts_root_or_endpoint() -> None:
    assert resolve_unlimitedsurf_base_url("unlimited.surf/api/chat") == "https://unlimited.surf"
    assert resolve_unlimitedsurf_base_url("https://unlimited.surf/api/models") == "https://unlimited.surf"
    assert resolve_unlimitedsurf_chat_url("https://unlimited.surf") == "https://unlimited.surf/api/chat"


def test_unlimitedsurf_runtime_model_data_uses_env_key(monkeypatch) -> None:
    monkeypatch.setenv("UNLIMITEDSURF_API_KEY", "ua__test")

    runtime = build_unlimitedsurf_runtime_model_data(
        {
            "selected_model_id": "gateway-gpt-5",
            "selected_model_display_name": "GPT-5",
        }
    )

    assert runtime is not None
    assert runtime["model"] == "gateway-gpt-5"
    assert runtime["model_display_name"] == "GPT-5"
    assert runtime["provider"] == "request"
    assert runtime["base_url"] == "https://unlimited.surf/api/chat"
    assert runtime["api_key"] == "ua__test"
    assert runtime["thinking_mode"] == "medium"


def test_config_active_model_resolves_unlimitedsurf(monkeypatch) -> None:
    monkeypatch.setenv("UNLIMITEDSURF_API_KEY", "ua__test")
    config = Config(
        active_model_source="unlimitedsurf",
        unlimitedsurf=normalize_unlimitedsurf_config({"selected_model_id": "gateway-gpt-5"}),
    )

    active = config.active_model

    assert active is not None
    assert active.model == "gateway-gpt-5"
    assert active.provider == "request"
    assert active.base_url == "https://unlimited.surf/api/chat"


def test_unlimitedsurf_model_command_prompts_key_before_switching(tmp_path, monkeypatch) -> None:
    app_root = tmp_path / "app"
    project_root = tmp_path / "project"
    project_root.mkdir(parents=True, exist_ok=True)

    monkeypatch.delenv("UNLIMITEDSURF_API_KEY", raising=False)
    monkeypatch.delenv("UNLIMITED_SURF_API_KEY", raising=False)
    monkeypatch.delenv("US_API_KEY", raising=False)
    monkeypatch.setattr("reverie.config.get_app_root", lambda: app_root)
    monkeypatch.setattr("reverie.config.get_launcher_root", lambda: app_root)
    monkeypatch.setattr("reverie.cli.commands.Prompt.ask", lambda *args, **kwargs: "ua__prompted")
    monkeypatch.setattr(
        "reverie.unlimitedsurf.get_unlimitedsurf_model_catalog",
        lambda *args, **kwargs: [
            {
                "id": "gateway-claude-opus-4-8",
                "display_name": "Claude Opus 4.8",
                "description": "unlimited.surf model",
                "transport": "request",
                "context_length": 256_000,
                "max_output_tokens": 16_384,
                "provider": "anthropic",
                "tier": "flagship",
                "vision": False,
                "thinking": True,
                "tool_calling": False,
            }
        ],
    )

    config_manager = ConfigManager(project_root)
    handler = CommandHandler(
        Console(record=True, force_terminal=False, width=120),
        {"config_manager": config_manager, "project_root": project_root},
    )

    assert handler._cmd_unlimitedsurf_model("gateway-claude-opus-4-8") is True

    reloaded = config_manager.load()
    active = reloaded.active_model
    assert reloaded.active_model_source == "unlimitedsurf"
    assert reloaded.unlimitedsurf["api_key"] == "ua__prompted"
    assert reloaded.unlimitedsurf["selected_model_id"] == "gateway-claude-opus-4-8"
    assert active is not None
    assert active.model == "gateway-claude-opus-4-8"
    assert active.model_display_name == "Claude Opus 4.8"


def test_unlimitedsurf_key_command_accepts_inline_value(tmp_path, monkeypatch) -> None:
    app_root = tmp_path / "app"
    project_root = tmp_path / "project"
    project_root.mkdir(parents=True, exist_ok=True)

    monkeypatch.setattr("reverie.config.get_app_root", lambda: app_root)
    monkeypatch.setattr("reverie.config.get_launcher_root", lambda: app_root)

    config_manager = ConfigManager(project_root)
    handler = CommandHandler(
        Console(record=True, force_terminal=False, width=120),
        {"config_manager": config_manager, "project_root": project_root},
    )

    assert handler.cmd_unlimitedsurf("key ua__inline") is True

    reloaded = config_manager.load()
    assert reloaded.unlimitedsurf["api_key"] == "ua__inline"


def test_unlimitedsurf_chat_payload_flattens_messages() -> None:
    payload = build_unlimitedsurf_chat_payload(
        messages=[
            {"role": "system", "content": "Follow the rules."},
            {"role": "user", "content": "Hello"},
        ],
        model_id="gateway-gpt-5",
        effort="high",
    )

    assert payload == {
        "message": "System: Follow the rules.\n\nUser: Hello",
        "model": "gateway-gpt-5",
        "effort": "high",
    }


def test_agent_prepares_unlimitedsurf_payload_and_parses_stream(tmp_path) -> None:
    config = SimpleNamespace(
        api_max_retries=1,
        api_initial_backoff=0.01,
        api_timeout=17,
        api_enable_debug_logging=False,
        active_model_source="unlimitedsurf",
        unlimitedsurf={"effort": "high"},
    )
    agent = ReverieAgent(
        base_url="https://unlimited.surf/api/chat",
        api_key="ua__test",
        model="gateway-gpt-5",
        project_root=tmp_path,
        provider="request",
        config=config,
    )
    prepared = agent._prepare_request_payload(
        {
            "model": "gateway-gpt-5",
            "messages": [
                {"role": "system", "content": "Rules"},
                {"role": "user", "content": "Hello"},
            ],
            "tools": [{"type": "function", "function": {"name": "tool"}}],
            "stream": True,
        }
    )

    assert prepared == {
        "message": "System: Rules\n\nUser: Hello",
        "model": "gateway-gpt-5",
        "effort": "high",
    }
    assert agent.get_visible_tool_schemas() == []

    class FakeResponse:
        def iter_lines(self, decode_unicode=False, chunk_size=None):
            yield 'data: {"status":"streaming","streamId":"abc123"}'
            yield ""
            yield 'data: {"delta":"OK"}'
            yield ""
            yield 'data: {"finish":true,"reason":"stop"}'
            yield ""

    events = list(agent._iter_request_stream_events(FakeResponse(), "unlimited.surf API"))

    assert events == [
        {"type": "content", "text": "OK"},
        {"type": "finish", "reason": "stop"},
    ]


def test_unlimitedsurf_help_uses_us_command_and_full_name() -> None:
    topic = HELP_TOPICS["unlimitedsurf"]

    assert topic["command"] == "/us"
    assert "unlimited.surf" in topic["detail"]
    assert normalize_help_topic("us") == "unlimitedsurf"
    assert normalize_help_topic("unlimited.surf") == "unlimitedsurf"
