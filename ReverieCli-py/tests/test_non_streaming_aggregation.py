import json
from types import SimpleNamespace

import pytest

from reverie.agent.agent import ReverieAgent
from reverie.config import Config
from reverie.stream_protocol import (
    THINKING_END_MARKER,
    THINKING_START_MARKER,
    encode_stream_event,
)


@pytest.fixture(params=["codex", "webgemini"])
def buffered_agent(request):
    agent = ReverieAgent.__new__(ReverieAgent)
    agent.provider = request.param
    events = []
    agent.tool_executor = SimpleNamespace(context={"ui_event_handler": events.append})
    return agent, events


def install_stream(monkeypatch, agent, generate):
    if agent.provider == "codex":
        monkeypatch.setattr(agent, "_process_streaming_native_provider", lambda **kwargs: generate())
    else:
        monkeypatch.setattr(agent, "_process_streaming_webgemini", lambda **kwargs: generate())


def test_buffered_output_keeps_reasoning_and_tool_events_out_of_answer(buffered_agent, monkeypatch):
    agent, events = buffered_agent

    def generate():
        yield THINKING_START_MARKER
        yield "Check the file first."
        yield THINKING_END_MARKER
        yield "I checked "
        yield encode_stream_event("tool_start", tool_name="file_ops", tool_call_id="call-1")
        assert events == [{"kind": "stream_event", "event": "tool_start", "tool_name": "file_ops", "tool_call_id": "call-1"}]
        yield encode_stream_event("tool_result", tool_name="file_ops", tool_call_id="call-1", output="中文内容", success=True)
        yield THINKING_START_MARKER
        yield "The file confirms the result."
        yield THINKING_END_MARKER
        yield "the file."

    install_stream(monkeypatch, agent, generate)

    assert agent._process_non_streaming(session_id="test") == "I checked the file."
    assert [event["event"] for event in events] == ["tool_start", "tool_result"]
    assert events[-1]["output"] == "中文内容"


def test_buffered_output_does_not_render_reasoning_only_response(buffered_agent, monkeypatch):
    agent, events = buffered_agent
    install_stream(monkeypatch, agent, lambda: iter([THINKING_START_MARKER, "Still thinking", THINKING_END_MARKER]))

    assert agent._process_non_streaming(session_id="test") == ""
    assert events == []


def test_buffered_output_preserves_tool_event_before_provider_failure(buffered_agent, monkeypatch):
    agent, events = buffered_agent

    def generate():
        yield encode_stream_event("tool_start", tool_name="file_ops", tool_call_id="call-1")
        raise RuntimeError("provider disconnected")

    install_stream(monkeypatch, agent, generate)

    with pytest.raises(RuntimeError, match="provider disconnected"):
        agent._process_non_streaming(session_id="test")
    assert events == [{"kind": "stream_event", "event": "tool_start", "tool_name": "file_ops", "tool_call_id": "call-1"}]


def test_buffered_output_preserves_reasoning_in_saved_history(buffered_agent, monkeypatch):
    agent, _ = buffered_agent
    agent.messages = []
    agent._record_model_usage = lambda **kwargs: None
    agent._promote_writer_json_tool_call = lambda state: None
    agent._promote_writer_direct_prose_commit = lambda state: None
    agent._writer_retry_instruction_for_invalid_commit_tool_call = lambda calls: None
    agent._writer_retry_instruction_for_short_direct_prose = lambda content: None

    def generate():
        state = agent._new_turn_state()
        yield from state.add_reasoning("独立的思考内容")
        yield from state.add_content("最终答复")
        yield from state.flush()
        agent._commit_stream_state(state=state, request_messages=[], messages=[], session_id="test")

    install_stream(monkeypatch, agent, generate)

    assert agent._process_non_streaming(session_id="test") == "最终答复"
    assert agent.messages == [{"role": "assistant", "content": "最终答复", "reasoning_content": "独立的思考内容"}]


def test_codex_non_streaming_decodes_sse_and_preserves_reasoning_history(tmp_path, monkeypatch):
    frames = [
        {"type": "response.reasoning_summary_text.delta", "delta": "独立的思考内容"},
        {"type": "response.output_text.delta", "delta": "最终答复"},
        {"type": "response.completed", "response": {"status": "completed", "usage": {"input_tokens": 20, "output_tokens": 4}}},
    ]
    requests = []
    closed = []

    class Response:
        def iter_lines(self, **kwargs):
            for frame in frames:
                yield ("data: " + json.dumps(frame)).encode()
                yield b""

        def close(self):
            closed.append(True)

    def respond(**kwargs):
        requests.append(kwargs)
        return Response()

    monkeypatch.setattr("reverie.agent.agent.make_api_request_with_retry", respond)
    monkeypatch.setattr("reverie.codex.resolve_codex_credentials", lambda *args, **kwargs: {"found": True, "api_key": "test", "auth_mode": "api_key"})
    agent = ReverieAgent(base_url="https://example.test/v1", api_key="test", model="test-model", provider="codex", project_root=tmp_path, config=Config())
    agent.get_visible_tool_schemas = lambda: []
    agent.messages = [{"role": "user", "content": "请回答"}]

    assert agent._process_non_streaming(session_id="test") == "最终答复"
    assert requests[0]["stream"] is True  # This provider only exposes SSE transport.
    assert closed == [True]
    assert agent.messages[-1]["content"] == "最终答复"
    assert agent.messages[-1]["reasoning_content"] == "独立的思考内容"


def test_webgemini_non_streaming_preserves_model_activity_and_reasoning_history(tmp_path, monkeypatch):
    monkeypatch.setattr("reverie.agent.agent.iter_webgemini_text_deltas", lambda **kwargs: iter(["<think>独立的", "思考内容</think>", "最终答复"]))
    agent = ReverieAgent(base_url="https://example.test", api_key="", model="test-model", provider="webgemini", project_root=tmp_path, config=Config())
    agent.get_visible_tool_schemas = lambda: []
    agent.messages = [{"role": "user", "content": "请回答"}]
    events = []
    agent.tool_executor.context["ui_event_handler"] = events.append

    assert agent._process_non_streaming(session_id="test") == "最终答复"
    assert events[0]["event"] == "model_request"
    assert agent.messages[-1]["content"] == "最终答复"
    assert agent.messages[-1]["reasoning_content"] == "独立的思考内容"
