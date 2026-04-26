import sys
import types
from types import SimpleNamespace

from rich.console import Console

from reverie.agent.agent import ReverieAgent, decode_stream_event
from reverie.cli.display import DisplayComponents
from reverie.cli.help_catalog import HELP_TOPICS


def _nvidia_config() -> SimpleNamespace:
    return SimpleNamespace(
        api_max_retries=1,
        api_initial_backoff=0.01,
        api_timeout=17,
        api_enable_debug_logging=False,
        active_model_source="nvidia",
        nvidia={
            "selected_model_id": "deepseek-ai/deepseek-v4-pro",
            "selected_model_display_name": "DeepSeek V4 Pro",
            "reasoning_effort": "max",
            "timeout": 23,
        },
    )


def _install_fake_openai(monkeypatch, seen: dict):
    class FakeCompletions:
        def create(self, **kwargs):
            seen["create_kwargs"] = dict(kwargs)
            return iter(())

    class FakeOpenAI:
        def __init__(self, **kwargs):
            seen["init_kwargs"] = dict(kwargs)
            self.chat = SimpleNamespace(completions=FakeCompletions())

    fake_module = types.ModuleType("openai")
    fake_module.OpenAI = FakeOpenAI
    monkeypatch.setitem(sys.modules, "openai", fake_module)


def test_openai_sdk_client_receives_resolved_provider_timeout(monkeypatch, tmp_path):
    seen = {}
    _install_fake_openai(monkeypatch, seen)

    ReverieAgent(
        base_url="https://integrate.api.nvidia.com/v1",
        api_key="test-key",
        model="deepseek-ai/deepseek-v4-pro",
        project_root=tmp_path,
        provider="openai-sdk",
        config=_nvidia_config(),
    )

    assert seen["init_kwargs"]["timeout"] == 23


def test_legacy_nvidia_default_timeout_does_not_override_global_timeout(monkeypatch, tmp_path):
    seen = {}
    _install_fake_openai(monkeypatch, seen)
    config = _nvidia_config()
    config.api_timeout = 41
    config.nvidia["timeout"] = 300

    ReverieAgent(
        base_url="https://integrate.api.nvidia.com/v1",
        api_key="test-key",
        model="deepseek-ai/deepseek-v4-pro",
        project_root=tmp_path,
        provider="openai-sdk",
        config=config,
    )

    assert seen["init_kwargs"]["timeout"] == 41


def test_openai_sdk_stream_emits_visible_wait_event_before_request(monkeypatch, tmp_path):
    seen = {}
    _install_fake_openai(monkeypatch, seen)
    agent = ReverieAgent(
        base_url="https://integrate.api.nvidia.com/v1",
        api_key="test-key",
        model="deepseek-ai/deepseek-v4-pro",
        project_root=tmp_path,
        provider="openai-sdk",
        config=_nvidia_config(),
    )
    agent.tool_executor.get_tool_schemas = lambda mode="reverie": []
    agent.messages.append({"role": "system", "content": "late system note"})

    stream = agent._process_streaming_openai_sdk()
    event = decode_stream_event(next(stream))

    assert event["event"] == "model_request"
    assert event["message"] == "Waiting for NVIDIA API response"
    assert event["detail"] == "deepseek-ai/deepseek-v4-pro | stream"
    assert event["meta"] == "timeout 23s"
    assert "create_kwargs" not in seen

    try:
        next(stream)
    except StopIteration:
        pass

    create_kwargs = seen["create_kwargs"]
    assert create_kwargs["timeout"] == 23
    assert create_kwargs["extra_body"] == {"reasoning_effort": "max"}
    assert create_kwargs["messages"][0]["role"] == "system"
    assert all(message["role"] != "system" for message in create_kwargs["messages"][1:])


def test_display_renders_model_request_stream_event():
    console = Console(record=True, force_terminal=False, width=120)
    display = DisplayComponents(console)

    handled = display.show_stream_event(
        {
            "event": "model_request",
            "category": "Model",
            "message": "Waiting for NVIDIA API response",
            "status": "working",
            "detail": "deepseek-ai/deepseek-v4-pro | stream",
            "meta": "timeout 23s",
        }
    )

    assert handled is True
    assert "Waiting for NVIDIA API response" in console.export_text()


def test_nvidia_help_matches_supported_commands():
    nvidia_help = HELP_TOPICS["nvidia"]
    subcommand_usages = [item["usage"] for item in nvidia_help["subcommands"]]

    assert "/nvidia fast on" not in subcommand_usages
    assert "/nvidia fast off" not in subcommand_usages
    assert "thinking" in nvidia_help["overview"]
