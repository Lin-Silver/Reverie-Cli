import json
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
import requests

from reverie.agent.agent import ReverieAgent, _StreamingTurnState, make_api_request_with_retry
from reverie.codex import parse_codex_sse_event
from reverie.session.workspace_stats import ModelUsageSummary, SessionUsageSummary, WorkspaceStatsManager
from reverie.cli.commands import CommandHandler
from rich.console import Console
from rich.text import Text


def record(manager, usage):
    manager.record_model_usage(
        provider="test", source="chat", model="model", model_display_name="Model",
        request_messages=[{"role": "user", "content": "中文 test"}],
        assistant_text="answer", reasoning_text="reasoning",
        tool_calls=[{"function": {"name": "read", "arguments": "{}"}}],
        usage=usage, session_id="session", force=True,
    )
    return manager.build_dashboard_data()


@pytest.mark.parametrize("usage,expected", [
    ({"prompt_tokens": 120, "completion_tokens": 7, "total_tokens": 127}, (120, 7, 127)),
    (SimpleNamespace(input_tokens=120, output_tokens=7), (120, 7, 127)),
    ({"input_tokens": 120, "total_tokens": 127}, (120, 7, 127)),
    ({"output_tokens": 7, "total_tokens": 127}, (120, 7, 127)),
    ({"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}, (0, 0, 0)),
    ({"total_tokens": 0}, (0, 0, 0)),
    ({"input_tokens": 12, "output_tokens": 7, "total_tokens": 25}, (12, 7, 25)),
    ({"input_tokens": 12, "cache_creation_input_tokens": 20, "cache_read_input_tokens": 30, "output_tokens": 7}, (62, 7, 69)),
    ({"prompt_tokens": 12, "prompt_tokens_details": {"cached_tokens": 10}, "completion_tokens": 7}, (12, 7, 19)),
])
def test_complete_api_usage_never_calls_local_tokenizer(tmp_path, monkeypatch, usage, expected):
    manager = WorkspaceStatsManager(tmp_path)
    monkeypatch.setattr(manager, "count_messages_tokens", Mock(side_effect=AssertionError("local input")))
    monkeypatch.setattr(manager, "count_text_tokens", Mock(side_effect=AssertionError("local output")))
    dashboard = record(manager, usage)
    assert tuple(dashboard[key] for key in ("total_input_tokens", "total_output_tokens", "total_tokens")) == expected
    for key in ("model_usage", "session_usage", "source_usage"):
        assert dashboard[key][0]["total_tokens"] == expected[2]
    assert WorkspaceStatsManager(tmp_path).build_dashboard_data()["total_tokens"] == expected[2]


@pytest.mark.parametrize("usage,expected,input_calls,output_calls", [
    (None, (100, 9, 109), 1, 3),
    ({"input_tokens": 12}, (12, 9, 21), 0, 3),
    ({"output_tokens": 7}, (100, 7, 107), 1, 0),
    ({"total_tokens": 150}, (100, 50, 150), 1, 0),
    ({"input_tokens": -1, "output_tokens": "invalid"}, (100, 9, 109), 1, 3),
    ({"input_tokens": False, "output_tokens": 1.5}, (100, 9, 109), 1, 3),
])
def test_local_fallback_only_counts_missing_fields(tmp_path, monkeypatch, usage, expected, input_calls, output_calls):
    manager = WorkspaceStatsManager(tmp_path)
    inbound, outbound = Mock(return_value=100), Mock(return_value=3)
    monkeypatch.setattr(manager, "count_messages_tokens", inbound)
    monkeypatch.setattr(manager, "count_text_tokens", outbound)
    dashboard = record(manager, usage)
    assert tuple(dashboard[key] for key in ("total_input_tokens", "total_output_tokens", "total_tokens")) == expected
    assert inbound.call_count == input_calls
    assert outbound.call_count == output_calls


def test_historical_totals_remain_readable():
    assert SessionUsageSummary.from_dict({"input_tokens": 12, "output_tokens": 7}).total_tokens == 19
    assert ModelUsageSummary.from_dict({"input_tokens": 12, "output_tokens": 7}).total_tokens == 19


@pytest.mark.parametrize("total", [0, 25])
def test_status_ledger_displays_authoritative_api_total(total):
    handler = CommandHandler(Console(), {})
    rendered = Text.from_markup(handler._format_token_ledger({"input_tokens": 12, "output_tokens": 7, "total_tokens": total, "calls": 1})).plain
    assert f"{total} total across 1 call(s)" in rendered


def test_top_model_uses_authoritative_api_total():
    handler = CommandHandler(Console(), {})
    table = Mock()
    handler._add_model_token_row(table, {"model_usage": [
        {"model": "api-total", "input_tokens": 12, "output_tokens": 7, "total_tokens": 25},
        {"model": "legacy", "input_tokens": 20, "output_tokens": 0},
    ]})
    detail = Text.from_markup(table.add_row.call_args.args[1]).plain
    assert "api-total" in detail and "25 tokens" in detail


@pytest.mark.parametrize("transport", ["sdk", "request", "responses"])
@pytest.mark.parametrize("content", ["answer", ""])
def test_stream_snapshots_count_once_including_usage_only_chunks(transport, content):
    agent = ReverieAgent.__new__(ReverieAgent)
    agent.messages = []
    agent._model_stream_connected_event = lambda: None
    agent._record_model_usage = Mock()
    agent._promote_writer_json_tool_call = lambda state: None
    agent._promote_writer_direct_prose_commit = lambda state: None
    agent._writer_retry_instruction_for_invalid_commit_tool_call = lambda calls: None
    agent._writer_retry_instruction_for_short_direct_prose = lambda text: None
    state = _StreamingTurnState(collected_content=content)
    if transport == "sdk":
        events = agent._iter_openai_sdk_stream_events([
            SimpleNamespace(choices=[], usage=SimpleNamespace(prompt_tokens=12, completion_tokens=2, total_tokens=14)),
            SimpleNamespace(choices=[], usage=SimpleNamespace(prompt_tokens=12, completion_tokens=7, total_tokens=19)),
        ])
    elif transport == "request":
        agent._iter_sse_data_strings = lambda response: iter([
            json.dumps({"choices": [], "usage": {"prompt_tokens": 12, "completion_tokens": 2, "total_tokens": 14}}),
            json.dumps({"choices": [], "usage": {"prompt_tokens": 12, "completion_tokens": 7, "total_tokens": 19}}),
        ])
        events = agent._iter_request_stream_events(None, "test")
    else:
        events, _ = parse_codex_sse_event(json.dumps({"type": "response.incomplete", "response": {"usage": {"input_tokens": 12, "output_tokens": 7, "total_tokens": 19}}}))
    for event in events:
        list(agent._apply_stream_event(state, event))
    outcome, _ = agent._commit_stream_state(state=state, request_messages=[], messages=[], session_id="session")
    assert outcome == ("content" if content else "empty")
    assert agent._record_model_usage.call_count == 1
    assert agent._record_model_usage.call_args.kwargs["usage"] == {"input_tokens": 12, "output_tokens": 7, "total_tokens": 19}


def test_sdk_requests_usage_and_only_drops_rejected_option():
    agent = ReverieAgent.__new__(ReverieAgent)
    agent.api_max_retries = 0
    agent._is_active_model_source = lambda source: False
    calls = []
    def create(kwargs):
        calls.append(dict(kwargs))
        if len(calls) == 1:
            raise TypeError("unexpected keyword argument 'stream_options'")
        return "response"
    agent._call_openai_chat_completion_once = create
    tools = [{"type": "function", "function": {"name": "read"}}]
    assert agent._create_openai_chat_completion(stream=True, messages=[], tools=tools) == "response"
    assert len(calls) == 2
    assert calls[0]["stream_options"] == {"include_usage": True}
    assert calls[-1]["tools"] == tools
    assert "stream_options" not in calls[-1]


def test_anthropic_empty_response_records_api_usage_once():
    agent = ReverieAgent.__new__(ReverieAgent)
    agent.api_max_retries = 0
    agent.model = "test"
    agent.messages = [{"role": "user", "content": "hello"}]
    agent._completion_continuation_limit = lambda: 1
    agent._check_and_compress_context = lambda **kwargs: None
    agent.get_visible_tool_schemas = lambda: []
    agent._build_messages = lambda: list(agent.messages)
    agent._resolve_messages_for_request = lambda messages: messages
    agent._resolve_anthropic_max_tokens = lambda: 100
    agent._apply_sensenova_anthropic_options = lambda kwargs: kwargs
    agent._apply_custom_provider_anthropic_options = lambda kwargs: kwargs
    agent._is_active_model_source = lambda source: False
    agent._new_turn_state = _StreamingTurnState
    agent._promote_writer_json_tool_call = lambda state: None
    agent._promote_writer_direct_prose_commit = lambda state: None
    agent._writer_retry_instruction_for_invalid_commit_tool_call = lambda calls: None
    agent._writer_retry_instruction_for_short_direct_prose = lambda text: None
    agent._recover_empty_model_turn = lambda messages, attempt: False
    agent._record_model_usage = Mock()
    usage = SimpleNamespace(input_tokens=120, output_tokens=0)

    class Stream:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            pass

        def __iter__(self):
            return iter(())

        def get_final_message(self):
            return SimpleNamespace(content=[], stop_reason="end_turn", usage=usage)

    agent._ensure_client = lambda: SimpleNamespace(messages=SimpleNamespace(stream=lambda **kwargs: Stream()))
    assert "without returning any text" in "".join(agent._process_streaming_anthropic())
    assert agent._record_model_usage.call_count == 1
    assert agent._record_model_usage.call_args.kwargs["usage"] is usage


def test_sdk_include_usage_is_default():
    agent = ReverieAgent.__new__(ReverieAgent)
    agent.api_max_retries = 0
    agent._is_active_model_source = lambda source: False
    agent._call_openai_chat_completion_once = Mock(return_value="response")
    agent._create_openai_chat_completion(stream=True, stream_options={"other": True}, messages=[])
    assert agent._call_openai_chat_completion_once.call_args.args[0]["stream_options"] == {"other": True, "include_usage": True}


def test_http_usage_option_rejection_preserves_tools(monkeypatch):
    rejected = requests.Response()
    rejected.status_code = 400
    rejected._content = b'{"error":{"message":"Unknown parameter stream_options"}}'
    accepted = requests.Response()
    accepted.status_code = 200
    post = Mock(side_effect=[rejected, accepted])
    monkeypatch.setattr("reverie.agent.agent.provider_post", post)
    payload = {"model": "test", "messages": [], "stream": True, "stream_options": {"include_usage": True}, "tools": [{"type": "function", "function": {"name": "read"}}]}
    result = make_api_request_with_retry("http://localhost/v1/chat/completions", {}, payload, max_retries=0, stream=True)
    assert result is accepted
    assert post.call_args_list[0].kwargs["json"]["stream_options"] == {"include_usage": True}
    assert "stream_options" not in post.call_args_list[1].kwargs["json"]
    assert post.call_args_list[1].kwargs["json"]["tools"] == payload["tools"]
