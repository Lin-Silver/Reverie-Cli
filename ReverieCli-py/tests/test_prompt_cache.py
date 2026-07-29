from __future__ import annotations

from types import SimpleNamespace

import pytest

from reverie.prompt_cache import (
    anthropic_stream_with_prompt_cache_fallback,
    apply_anthropic_prompt_cache,
    apply_openai_prompt_cache,
    build_prompt_cache_key,
    call_with_prompt_cache_fallback,
    without_prompt_cache,
)
from reverie.agent.agent import ReverieAgent
from reverie.context_engine.compressor import ContextCompressor
from reverie.context_engine.handoff import _request_handoff_summary_text


def _openai_payload(user_text: str) -> dict:
    return {
        "model": "gpt-5.6",
        "messages": [
            {"role": "system", "content": "stable system prompt"},
            {"role": "user", "content": user_text},
        ],
        "tools": [{"type": "function", "function": {"name": "inspect", "parameters": {}}}],
    }


def test_openai_cache_key_is_stable_across_dynamic_user_input() -> None:
    first = apply_openai_prompt_cache(_openai_payload("first"), namespace="chat")
    second = apply_openai_prompt_cache(_openai_payload("second"), namespace="chat")

    assert first["prompt_cache_key"] == second["prompt_cache_key"]
    assert first["prompt_cache_key"].startswith("reverie:chat:")
    assert "stable system prompt" not in first["prompt_cache_key"]


def test_cache_key_changes_with_model_or_stable_prefix() -> None:
    base = _openai_payload("question")
    other_model = {**base, "model": "gpt-5.5"}
    other_system = {
        **base,
        "messages": [
            {"role": "system", "content": "different system prompt"},
            {"role": "user", "content": "question"},
        ],
    }

    assert build_prompt_cache_key(base) != build_prompt_cache_key(other_model)
    assert build_prompt_cache_key(base) != build_prompt_cache_key(other_system)


def test_openai_cache_hints_preserve_provider_options_and_strip_surgically() -> None:
    payload = apply_openai_prompt_cache(
        {**_openai_payload("question"), "extra_body": {"thinking": {"type": "enabled"}}},
        include_legacy_cache_prompt=True,
    )

    assert payload["cache_prompt"] is True
    assert payload["extra_body"] == {"thinking": {"type": "enabled"}}
    fallback = without_prompt_cache(payload)
    assert "prompt_cache_key" not in fallback
    assert "cache_prompt" not in fallback
    assert fallback["extra_body"] == {"thinking": {"type": "enabled"}}


def test_openai_call_retries_once_without_cache_hint_on_400() -> None:
    calls = []

    def fake_call(**kwargs):
        calls.append(kwargs)
        if "prompt_cache_key" in kwargs:
            error = RuntimeError("unsupported prompt_cache_key")
            error.status_code = 400
            raise error
        return "ok"

    payload = apply_openai_prompt_cache(_openai_payload("question"))
    assert call_with_prompt_cache_fallback(fake_call, payload) == "ok"
    assert len(calls) == 2
    assert "prompt_cache_key" in calls[0]
    assert "prompt_cache_key" not in calls[1]


def test_non_cache_error_is_not_retried() -> None:
    calls = []

    def fake_call(**kwargs):
        calls.append(kwargs)
        error = RuntimeError("rate limited")
        error.status_code = 429
        raise error

    with pytest.raises(RuntimeError, match="rate limited"):
        call_with_prompt_cache_fallback(fake_call, apply_openai_prompt_cache(_openai_payload("question")))
    assert len(calls) == 1


def test_anthropic_automatic_cache_control_and_stream_fallback() -> None:
    payload = apply_anthropic_prompt_cache(
        {"model": "claude-opus-5", "messages": [{"role": "user", "content": "hello"}]}
    )
    calls = []

    class _Manager:
        def __init__(self, kwargs):
            self.kwargs = kwargs

        def __enter__(self):
            calls.append(self.kwargs)
            if "cache_control" in self.kwargs:
                error = RuntimeError("cache_control is not supported")
                error.status_code = 400
                raise error
            return SimpleNamespace(name="stream")

        def __exit__(self, *args):
            return False

    with anthropic_stream_with_prompt_cache_fallback(lambda **kwargs: _Manager(kwargs), payload) as stream:
        assert stream.name == "stream"

    assert payload["cache_control"] == {"type": "ephemeral"}
    assert len(calls) == 2
    assert "cache_control" in calls[0]
    assert "cache_control" not in calls[1]


def test_main_agent_applies_cache_hints_to_chat_responses_and_raw_requests(tmp_path) -> None:
    config = SimpleNamespace(active_model_source="standard")
    agent = ReverieAgent(
        base_url="https://example.test/v1",
        api_key="test",
        model="gpt-5.6",
        project_root=tmp_path,
        provider="openai-chat",
        config=config,
    )
    seen = {}

    def fake_chat_create(**kwargs):
        seen.update(kwargs)
        return "ok"

    agent._ensure_client = lambda: SimpleNamespace(
        chat=SimpleNamespace(completions=SimpleNamespace(create=fake_chat_create))
    )
    result = agent._create_openai_chat_completion(
        model="gpt-5.6",
        messages=_openai_payload("question")["messages"],
        stream=False,
    )

    assert result == "ok"
    assert seen["prompt_cache_key"].startswith("reverie:agent-chat:")

    agent.provider = "openai-responses"
    agent.messages = [{"role": "user", "content": "question"}]
    agent.get_visible_tool_schemas = lambda: []
    responses_payload = agent._build_openai_responses_payload(stream=False)
    assert responses_payload["prompt_cache_key"].startswith("reverie:agent-responses:")

    agent.provider = "request"
    raw_payload = agent._prepare_request_payload(_openai_payload("question"))
    assert raw_payload["prompt_cache_key"].startswith("reverie:agent-chat:")
    assert raw_payload["cache_prompt"] is True


def test_context_compression_and_handoff_apply_cache_keys(tmp_path) -> None:
    compression_calls = []

    class _Completions:
        @staticmethod
        def create(**kwargs):
            compression_calls.append(kwargs)
            return SimpleNamespace(
                choices=[SimpleNamespace(message=SimpleNamespace(content="Current Goal\n- Continue."))],
                usage=None,
            )

    client = SimpleNamespace(chat=SimpleNamespace(completions=_Completions()))
    messages = [{"role": "system", "content": "stable system"}]
    messages.extend(
        {"role": "user" if index % 2 == 0 else "assistant", "content": f"message {index}"}
        for index in range(12)
    )

    ContextCompressor(tmp_path).compress(
        messages,
        client=client,
        model="gpt-5.6",
        provider="openai-chat",
    )
    assert compression_calls[0]["prompt_cache_key"].startswith("reverie:context-compression:")

    handoff_calls = []

    def handoff_create(**kwargs):
        handoff_calls.append(kwargs)
        return SimpleNamespace(
            choices=[SimpleNamespace(message=SimpleNamespace(content='{"summary":"ready"}'))],
            usage=None,
        )

    handoff_client = SimpleNamespace(
        chat=SimpleNamespace(completions=SimpleNamespace(create=handoff_create))
    )
    result = _request_handoff_summary_text(
        client=handoff_client,
        model="gpt-5.6",
        provider="openai-chat",
        base_url="https://example.test/v1",
        api_key="test",
        session_id="session-1",
        custom_headers=None,
        prompt_messages=_openai_payload("handoff")["messages"],
    )

    assert result == '{"summary":"ready"}'
    assert handoff_calls[0]["prompt_cache_key"].startswith("reverie:session-handoff:")
