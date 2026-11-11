from types import SimpleNamespace

import pytest

from reverie.agent import agent as module
from reverie.config import Config, ModelConfig
from reverie.context_engine import compressor, handoff
from reverie.session.aio_store import AiOStore
from reverie.session.sqlite_manager import SQLiteSessionManager
from reverie.session.runtime_config import capture_runtime_config


def conversation(tmp_path, *, provider="openai-chat", api_key="", endpoint="", assistant=False):
    base_url = "https://example.invalid/v1"
    if provider == "request":
        base_url += "/chat/completions"
    config = Config(models=[ModelConfig("local-fixture", "Local fixture", base_url, api_key=api_key, provider=provider, endpoint=endpoint)])
    manager = AiOStore(tmp_path / "data") if assistant else SQLiteSessionManager(tmp_path / "data", project_root=tmp_path)
    if assistant:
        manager.enable(capture_runtime_config(config))
    session = manager.load_session(manager.mainline_id) if assistant else manager.create_session("Long conversation")
    original = [
        {"role": "user" if index % 2 == 0 else "assistant", "content": f"Acknowledged original {index}"}
        for index in range(20)
    ]
    manager.update_messages(original)
    agent = module.ReverieAgent(
        base_url=base_url, api_key=api_key, model="local-fixture",
        provider=provider, endpoint=endpoint, project_root=tmp_path, config=config,
    )
    agent.system_prompt = "Preserve acknowledged original text."
    agent.messages = [dict(message) for message in original]
    agent.tool_executor.context["session_manager"] = manager
    return agent, manager, session, original


@pytest.mark.parametrize("provider,api_key", [("openai-chat", ""), ("request", "fixture-key")])
@pytest.mark.parametrize("assistant", [False, True])
def test_automatic_http_compaction_preserves_acknowledged_history(monkeypatch, tmp_path, provider, api_key, assistant):
    agent, manager, session, original = conversation(tmp_path, provider=provider, api_key=api_key, assistant=assistant)
    calls = []
    summary = "\n".join(f"{title}\nLOCAL_CONTEXT_SUMMARY" for title in compressor.COMPACTION_SECTION_TITLES)

    def respond(url, headers, payload):
        calls.append((url, headers, payload))
        assert headers.get("Authorization") == (f"Bearer {api_key}" if api_key else None)
        return SimpleNamespace(json=lambda: {"choices": [{"message": {"content": summary}}]})

    monkeypatch.setattr(compressor, "make_compression_request_with_retry", respond)
    agent._handle_context_compaction(40000, 50000, session_id=session.id)

    assert any("LOCAL_CONTEXT_SUMMARY" in str(message.get("content")) for message in agent.messages)
    assert calls[0][0] == "https://example.invalid/v1/chat/completions"
    assert calls[0][2]["model"] == "local-fixture"
    assert manager.get_page(session.id, limit=200)["messages"][:len(original)] == original
    assert manager.load_session(session.id).id == session.id
    assert all("context_replay" not in message and "segment_boundary" not in message for message in agent._build_messages(read_only=True))


@pytest.mark.parametrize("api_key,endpoint", [("", ""), ("fixture-key", "/custom-completions")])
def test_automatic_http_handoff_keeps_the_configured_route(monkeypatch, tmp_path, api_key, endpoint):
    agent, manager, session, original = conversation(tmp_path, api_key=api_key, endpoint=endpoint)
    calls = []

    def summarize(**kwargs):
        calls.append(kwargs)
        assert kwargs["provider"] == "request"
        assert kwargs["client"] is None
        return SimpleNamespace(carryover_text="LOCAL_HANDOFF_SUMMARY", to_dict=lambda: {"data": {"summary": "local"}})

    monkeypatch.setattr(module, "build_session_handoff_packet", summarize)
    agent._handle_session_rotation(45000, 50000, session_id=session.id)

    assert any("LOCAL_HANDOFF_SUMMARY" in str(message.get("content")) for message in agent.messages)
    assert calls[0]["base_url"] == "https://example.invalid/v1" + (endpoint or "/chat/completions")
    assert manager.get_page(session.id, limit=200)["messages"][:len(original)] == original
    assert manager.load_session(session.id).id == session.id


@pytest.mark.parametrize("api_key", ["", "fixture-key"])
def test_http_handoff_authentication_matches_the_configured_key(monkeypatch, api_key):
    calls = []

    def respond(url, headers, payload):
        calls.append(headers)
        return SimpleNamespace(json=lambda: {"choices": [{"message": {"content": "LOCAL_HANDOFF_SUMMARY"}}]})

    monkeypatch.setattr(handoff, "make_compression_request_with_retry", respond)
    text = handoff._request_handoff_summary_text(
        client=None, model="local-fixture", provider="request",
        base_url="https://example.invalid/v1/chat/completions", api_key=api_key,
        session_id="original", custom_headers={"X-Task-Identity": "original"},
        prompt_messages=[{"role": "user", "content": "Continue the original task."}],
    )

    assert text == "LOCAL_HANDOFF_SUMMARY"
    assert calls[0].get("Authorization") == (f"Bearer {api_key}" if api_key else None)
    assert calls[0]["X-Task-Identity"] == "original"
