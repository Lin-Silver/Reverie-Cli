"""Turn-completion contracts: a run may not end on a tool result.

The regression these pin down came from a computer-controller session that
called four tools and then stopped: the provider returned a turn whose entire
output was ``reasoning_content``, every provider loop treated "no tool call and
no visible text" as a natural end, and the saved transcript ended on a tool
result with no assistant summary at all.
"""

from __future__ import annotations

import sys
import types
from types import SimpleNamespace

from reverie.agent.agent import (
    THINKING_END_MARKER,
    THINKING_START_MARKER,
    ReverieAgent,
    decode_stream_event,
)


def _config() -> SimpleNamespace:
    return SimpleNamespace(
        api_max_retries=1,
        api_initial_backoff=0.01,
        api_timeout=17,
        api_enable_debug_logging=False,
        active_model_source="standard",
    )


def _delta(
    *,
    content: str | None = None,
    reasoning: str | None = None,
    tool_calls: list | None = None,
) -> SimpleNamespace:
    return SimpleNamespace(
        content=content,
        reasoning_content=reasoning,
        thinking=None,
        reasoning=None,
        tool_calls=tool_calls or [],
    )


def _tool_call_delta(call_id: str, name: str, arguments: str) -> SimpleNamespace:
    return SimpleNamespace(
        index=0,
        id=call_id,
        function=SimpleNamespace(name=name, arguments=arguments),
    )


def _chunk(delta: SimpleNamespace, finish_reason: str | None) -> SimpleNamespace:
    return SimpleNamespace(choices=[SimpleNamespace(delta=delta, finish_reason=finish_reason)])


def _install_scripted_openai(monkeypatch, turns: list, captured: list) -> None:
    """Install a fake ``openai`` module that replays one scripted turn per call."""

    class FakeCompletions:
        def create(self, **kwargs):
            captured.append(dict(kwargs))
            index = min(len(captured) - 1, len(turns) - 1)
            return iter(turns[index])

    class FakeOpenAI:
        def __init__(self, **kwargs):
            self.chat = SimpleNamespace(completions=FakeCompletions())

    fake_module = types.ModuleType("openai")
    fake_module.OpenAI = FakeOpenAI
    monkeypatch.setitem(sys.modules, "openai", fake_module)


def _agent(tmp_path, *, mode: str = "computer-controller") -> ReverieAgent:
    agent = ReverieAgent(
        base_url="https://example.test/v1",
        api_key="x",
        model="test-model",
        project_root=tmp_path,
        provider="openai-sdk",
        config=_config(),
        mode=mode,
    )
    agent.tool_executor.get_tool_schemas = lambda mode="reverie": []
    return agent


def _visible_text(chunks: list) -> str:
    """Join the chunks a user would actually read."""
    parts = []
    thinking = False
    for chunk in chunks:
        if chunk == THINKING_START_MARKER:
            thinking = True
            continue
        if chunk == THINKING_END_MARKER:
            thinking = False
            continue
        if thinking or decode_stream_event(chunk) is not None:
            continue
        parts.append(chunk)
    return "".join(parts)


def test_reasoning_only_turn_is_retried_instead_of_ending_the_run(monkeypatch, tmp_path) -> None:
    turns = [
        # A turn whose whole output landed in reasoning_content.
        [_chunk(_delta(reasoning="Click completed. Need to list apps again."), "stop")],
        [_chunk(_delta(content="Edge is open on youtube.com. //END//"), "stop")],
    ]
    captured: list = []
    _install_scripted_openai(monkeypatch, turns, captured)
    agent = _agent(tmp_path)
    agent.messages = [{"role": "user", "content": "Open Edge and type the YouTube URL"}]

    chunks = list(agent._process_streaming_openai_sdk(session_id="t"))

    assert len(captured) == 2, "the output-less turn must be retried, not treated as the end"
    recovery = [
        message
        for message in captured[1]["messages"]
        if message["role"] == "system" and "Recovery notice" in str(message["content"])
    ]
    assert recovery, "the retry must carry an explicit recovery reminder"
    assert "Recovery notice 1/6" in str(recovery[0]["content"])
    assert "Edge is open on youtube.com." in _visible_text(chunks)
    assert agent.messages[-1]["role"] == "assistant"
    assert agent.messages[-1]["content"].strip() == "Edge is open on youtube.com."


def test_exhausted_recovery_budget_still_records_a_closing_assistant_message(monkeypatch, tmp_path) -> None:
    turns = [[_chunk(_delta(reasoning="thinking in circles"), "stop")]]
    captured: list = []
    _install_scripted_openai(monkeypatch, turns, captured)
    agent = _agent(tmp_path, mode="reverie")
    agent.messages = [{"role": "user", "content": "Summarize the repository layout"}]

    chunks = list(agent._process_streaming_openai_sdk(session_id="t"))

    # 3 recovery attempts for a non-computer-controller mode, plus the initial turn.
    assert len(captured) == 4
    final_reminders = [
        str(message["content"])
        for message in captured[-1]["messages"]
        if message["role"] == "system" and "Recovery notice" in str(message["content"])
    ]
    assert any("Recovery notice 3/3" in text for text in final_reminders)
    assert any("Do not call another tool in this turn." in text for text in final_reminders)
    assert agent.messages[-1]["role"] == "assistant"
    assert "the request is not finished" in agent.messages[-1]["content"]
    assert "the request is not finished" in _visible_text(chunks)


def test_recovery_reminder_never_mutates_the_request_already_sent(monkeypatch, tmp_path) -> None:
    """The reminder belongs to the next request, not the one already in flight."""
    turns = [
        [_chunk(_delta(reasoning="thinking"), "stop")],
        [_chunk(_delta(content="Done. //END//"), "stop")],
    ]
    captured: list = []
    _install_scripted_openai(monkeypatch, turns, captured)
    agent = _agent(tmp_path)
    agent.messages = [{"role": "user", "content": "Open Edge"}]

    list(agent._process_streaming_openai_sdk(session_id="t"))

    assert len(captured) == 2
    # captured[0]["messages"] is the very list object handed to the SDK, so an
    # append after the call returns would be visible right here.
    assert not [
        message
        for message in captured[0]["messages"]
        if "Recovery notice" in str(message.get("content") or "")
    ]
    assert any(
        "Recovery notice" in str(message.get("content") or "") for message in captured[1]["messages"]
    )


def test_run_never_ends_on_a_tool_result(monkeypatch, tmp_path) -> None:
    """The turn-level safety net covers loop exits the per-loop retry cannot."""
    turns = [[_chunk(_delta(content="done"), "stop")]]
    captured: list = []
    _install_scripted_openai(monkeypatch, turns, captured)
    agent = _agent(tmp_path)

    def _stop_on_tool_result(session_id: str = "default"):
        agent.messages.append(
            {
                "role": "assistant",
                "content": None,
                "tool_calls": [
                    {
                        "id": "call_1",
                        "type": "function",
                        "function": {"name": "list_apps", "arguments": "{}"},
                    }
                ],
            }
        )
        agent.messages.append({"role": "tool", "tool_call_id": "call_1", "content": "explorer"})
        return
        yield  # pragma: no cover - generator marker

    agent._process_streaming = _stop_on_tool_result

    chunks = list(
        agent.process_message("Open Edge and type the YouTube URL", stream=True, session_id="t")
    )

    assert agent.messages[-1]["role"] == "assistant"
    assert "the request is not finished" in agent.messages[-1]["content"]
    assert "the request is not finished" in _visible_text(chunks)


def test_completed_turn_is_not_annotated_by_the_safety_net(monkeypatch, tmp_path) -> None:
    turns = [[_chunk(_delta(content="All set."), "stop")]]
    captured: list = []
    _install_scripted_openai(monkeypatch, turns, captured)
    agent = _agent(tmp_path)

    chunks = list(agent.process_message("Say hello", stream=True, session_id="t"))

    assert _visible_text(chunks) == "All set."
    assert agent.messages[-1]["content"].strip() == "All set."
    assert sum(1 for message in agent.messages if message["role"] == "assistant") == 1


def test_reasoning_prompt_echo_is_dropped_from_the_thinking_stream(monkeypatch, tmp_path) -> None:
    prompt = "控制我的电脑，帮我打开我电脑上的Edge浏览器，并输入Youtube的网址"
    turns = [
        [
            _chunk(_delta(reasoning=f"{prompt}\n\nWe need to control the computer."), None),
            _chunk(_delta(content="Working on it. //END//"), "stop"),
        ]
    ]
    captured: list = []
    _install_scripted_openai(monkeypatch, turns, captured)
    agent = _agent(tmp_path)
    agent.messages = [{"role": "user", "content": prompt}]

    chunks = list(agent._process_streaming_openai_sdk(session_id="t"))
    thinking = "".join(
        chunk
        for chunk in chunks[chunks.index(THINKING_START_MARKER) + 1 : chunks.index(THINKING_END_MARKER)]
    )

    assert thinking == "We need to control the computer."
    assert prompt not in thinking
    stored = [message for message in agent.messages if message["role"] == "assistant"]
    assert stored[-1]["reasoning_content"] == "We need to control the computer."


def test_reasoning_echo_split_across_chunks_is_still_dropped(monkeypatch, tmp_path) -> None:
    prompt = "Open Edge and type the YouTube URL"
    turns = [
        [
            _chunk(_delta(reasoning="Open Edge and "), None),
            _chunk(_delta(reasoning="type the YouTube URL"), None),
            _chunk(_delta(reasoning="\n\nFirst, list the running apps."), None),
            _chunk(_delta(content="Listing apps. //END//"), "stop"),
        ]
    ]
    captured: list = []
    _install_scripted_openai(monkeypatch, turns, captured)
    agent = _agent(tmp_path)
    agent.messages = [{"role": "user", "content": prompt}]

    chunks = list(agent._process_streaming_openai_sdk(session_id="t"))
    thinking = "".join(
        chunk
        for chunk in chunks[chunks.index(THINKING_START_MARKER) + 1 : chunks.index(THINKING_END_MARKER)]
    )

    assert thinking == "First, list the running apps."


def test_reasoning_that_merely_mentions_the_prompt_is_preserved(monkeypatch, tmp_path) -> None:
    prompt = "Open Edge and type the YouTube URL"
    reasoning = "The user asked me to: Open Edge and type the YouTube URL. Start with list_apps."
    turns = [
        [
            _chunk(_delta(reasoning=reasoning), None),
            _chunk(_delta(content="Listing apps. //END//"), "stop"),
        ]
    ]
    captured: list = []
    _install_scripted_openai(monkeypatch, turns, captured)
    agent = _agent(tmp_path)
    agent.messages = [{"role": "user", "content": prompt}]

    chunks = list(agent._process_streaming_openai_sdk(session_id="t"))
    thinking = "".join(
        chunk
        for chunk in chunks[chunks.index(THINKING_START_MARKER) + 1 : chunks.index(THINKING_END_MARKER)]
    )

    assert thinking == reasoning


def test_short_prompts_are_never_treated_as_a_reasoning_echo(tmp_path) -> None:
    agent = _agent(tmp_path)
    agent.messages = [{"role": "user", "content": "hi"}]

    assert agent._reasoning_echo_guard() == ""
    assert agent._strip_reasoning_prompt_echo("hi there") == "hi there"
