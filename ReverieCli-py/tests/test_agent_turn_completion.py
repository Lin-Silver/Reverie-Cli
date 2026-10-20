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
import pytest
from types import SimpleNamespace
from reverie.skills_manager import SkillsManager

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


def _tool_call_delta(call_id: str, name: str, arguments: str, index: int = 0) -> SimpleNamespace:
    return SimpleNamespace(
        index=index,
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


def test_reasoning_only_retries_remain_in_history_without_empty_api_messages(monkeypatch, tmp_path) -> None:
    first = "The system prompt says to use tools. This is the raw failed attempt."
    second = "Still considering the same inputs."
    turns = [
        [_chunk(_delta(reasoning=first), "length")],
        [_chunk(_delta(reasoning=second), "stop")],
        [_chunk(_delta(content="Done. //END//"), "stop")],
    ]
    captured = []
    _install_scripted_openai(monkeypatch, turns, captured)
    agent = _agent(tmp_path)
    agent.messages = [{"role": "user", "content": "Create the requested view."}]
    list(agent._process_streaming_openai_sdk(session_id="t"))

    assert [message.get("reasoning_content") for message in agent.messages if message.get("reasoning_content")] == [first, second]
    assert all(message.get("content") or message.get("tool_calls") for call in captured for message in call["messages"] if message.get("role") == "assistant")
    # Request projection must not mutate the persisted, user-visible transcript.
    assert len([message for message in agent.messages if message.get("content") is None]) == 2


@pytest.mark.parametrize("partial_tool", (False, True))
def test_failed_stream_preserves_raw_reasoning_without_replaying_partial_tools(monkeypatch, tmp_path, partial_tool):
    raw = "  The system prompt repeats here. These are the actual interrupted bytes."

    class BrokenStream:
        def __iter__(self):
            yield _chunk(_delta(reasoning=raw), None)
            if partial_tool:
                yield _chunk(_delta(tool_calls=[_tool_call_delta("unfinished", "create_file", '{"path":')]), None)
            raise RuntimeError("upstream fatal error")

    captured = []
    _install_scripted_openai(monkeypatch, [BrokenStream()], captured)
    agent = _agent(tmp_path)
    agent.provider = "openai-chat"
    agent._check_and_compress_context = lambda **kwargs: None
    persisted = []
    agent._persist_history_to_session = lambda: persisted.append(list(agent.messages))
    chunks = list(agent.process_message("Create the view", session_id="failed"))
    traces = [message for message in agent.messages if message.get("reasoning_content")]
    assert [message["reasoning_content"] for message in traces] == [raw]
    assert not any(message.get("tool_calls") for message in agent.messages)
    assert persisted and persisted[-1][-1]["reasoning_content"] == raw
    assert "upstream fatal error" in _visible_text(chunks)


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


def test_buffered_turn_honors_stop_received_while_waiting_for_the_reply(tmp_path) -> None:
    from reverie.desktop_control import RunControl

    agent = _agent(tmp_path, mode="reverie")
    events = []
    agent.desktop_control = RunControl(events.append)

    def buffered_reply(session_id="default"):
        agent.desktop_control.stop()
        agent.messages.append({"role": "assistant", "content": "Reply that arrived after Stop."})
        return "Reply that arrived after Stop."

    agent._process_non_streaming = buffered_reply
    chunks = list(agent.process_message("Wait for the reply", stream=False, session_id="t"))

    assert events[-1] == {"type": "run.control", "state": "stopping"}
    assert "Run stopped by user;" in _visible_text(chunks)
    assert "Reply that arrived after Stop." not in _visible_text(chunks)


def test_buffered_turn_without_stop_publishes_the_complete_reply(tmp_path) -> None:
    from reverie.desktop_control import RunControl

    agent = _agent(tmp_path, mode="reverie")
    agent.desktop_control = RunControl(lambda event: None)
    def buffered_reply(session_id="default"):
        agent.messages.append({"role": "assistant", "content": "Complete reply."})
        return "Complete reply."

    agent._process_non_streaming = buffered_reply

    assert _visible_text(list(agent.process_message("Wait for the reply", stream=False, session_id="t"))) == "Complete reply."


def test_one_provider_response_executes_both_requested_tools_before_followup(monkeypatch, tmp_path) -> None:
    turns = [
        [
            _chunk(_delta(tool_calls=[_tool_call_delta("call_1", "first_tool", "{}", 0)]), None),
            _chunk(_delta(tool_calls=[_tool_call_delta("call_2", "second_tool", "{}", 1)]), "tool_calls"),
        ],
        [_chunk(_delta(content="Both checks complete. //END//"), "stop")],
    ]
    captured: list = []
    _install_scripted_openai(monkeypatch, turns, captured)
    agent = _agent(tmp_path, mode="reverie")
    executed: list[str] = []

    def execute_call(call, _messages, session_id="default"):
        executed.append(call["function"]["name"])
        agent.messages.append({"role": "tool", "tool_call_id": call["id"], "content": "ok"})
        yield ""

    agent._stream_execute_tool_call = execute_call
    chunks = list(agent.process_message("Run both checks", stream=True, session_id="t"))

    assert executed == ["first_tool", "second_tool"]
    assert len(captured) == 2
    assert {message["tool_call_id"] for message in captured[1]["messages"] if message["role"] == "tool"} == {"call_1", "call_2"}
    assert "Both checks complete." in _visible_text(chunks)


def test_resume_uses_existing_user_turn_and_records_uncertain_tool_result(tmp_path) -> None:
    agent = _agent(tmp_path, mode="reverie")
    agent.messages = [
        {"role": "user", "content": "Build the site"},
        {"role": "assistant", "content": None, "tool_calls": [
            {"id": "done", "type": "function", "function": {"name": "read_file", "arguments": "{}"}},
            {"id": "pending", "type": "function", "function": {"name": "command_exec", "arguments": "{}"}},
        ]},
        {"role": "tool", "tool_call_id": "done", "content": "file contents"},
    ]
    requests = []

    def resumed_stream(session_id="default"):
        requests.append(agent.get_history())
        agent.messages.append({"role": "assistant", "content": "Done."})
        yield "Done."

    agent._process_streaming = resumed_stream
    list(agent.process_message("", stream=True, session_id="t", resume=True))

    assert [message["content"] for message in agent.messages if message["role"] == "user"] == ["Build the site"]
    assert len([message for message in requests[0] if message["role"] == "tool" and message["tool_call_id"] == "pending"]) == 1
    assert "result is unknown" in requests[0][-1]["content"]


def test_reasoning_prompt_echo_is_preserved_in_stream_and_history(monkeypatch, tmp_path) -> None:
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

    assert thinking == f"{prompt}\n\nWe need to control the computer."
    stored = [message for message in agent.messages if message["role"] == "assistant"]
    assert stored[-1]["reasoning_content"] == thinking


def test_reasoning_echo_split_across_chunks_is_preserved(monkeypatch, tmp_path) -> None:
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

    assert thinking == f"{prompt}\n\nFirst, list the running apps."


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


def test_repeated_prompt_is_emitted_immediately_without_prefix_buffering(tmp_path) -> None:
    agent = _agent(tmp_path)
    agent.messages = [{"role": "user", "content": "hi"}]

    state = agent._new_turn_state()
    assert state.add_reasoning("hi") == [THINKING_START_MARKER, "hi"]
    assert state.collected_thinking == "hi"


def test_non_streaming_sdk_preserves_repeated_native_reasoning(monkeypatch, tmp_path):
    prompt = "请计算并保留真实的模型输出。"
    reasoning = f"  {prompt}\n\n先检查输入。"
    response = SimpleNamespace(choices=[SimpleNamespace(
        message=SimpleNamespace(content="结果为 7。", reasoning_content=reasoning, tool_calls=[]),
        finish_reason="stop",
    )])
    agent = _agent(tmp_path)
    agent.messages = [{"role": "user", "content": prompt}]
    monkeypatch.setattr(agent, "_ensure_client", lambda: SimpleNamespace(chat=SimpleNamespace(
        completions=SimpleNamespace(create=lambda **kwargs: response),
    )))
    assert agent._process_non_streaming_openai_sdk(session_id="test") == "结果为 7。"
    assert agent.messages[-1]["reasoning_content"] == reasoning


def test_required_skills_are_loaded_in_full_on_each_turn_and_goal_stays_out_of_history(monkeypatch, tmp_path):
    skill_dir = tmp_path / ".agents" / "skills" / "required"
    skill_dir.mkdir(parents=True)
    skill_md = skill_dir / "SKILL.md"
    body = "Required instructions.\n" * 2500 + "FINAL_REQUIRED_INSTRUCTION"
    skill_md.write_text(f"---\nname: required\ndescription: Test workflow.\n---\n{body}", encoding="utf-8")
    manager = SkillsManager(project_root=tmp_path, app_root=tmp_path / "app")
    manager.pin_skill("required")
    captured = []
    _install_scripted_openai(monkeypatch, [[_chunk(_delta(content="Completed. //END//"), "stop")]], captured)
    agent = _agent(tmp_path, mode="reverie")
    agent.tool_executor.context["skills_manager"] = manager
    agent.goal_context = "Acceptance conditions: All target tests pass."
    list(agent.process_message("Perform the task."))
    system = captured[0]["messages"][0]["content"]
    assert body in system
    assert agent.goal_context in system
    # Compaction consumes the core request messages, before provider adapters merge system notes.
    history = agent._history_from_request_messages(agent._build_messages(read_only=True))
    assert not any(message.get("role") == "system" for message in history)
    assert body not in str(agent.messages)
    assert agent.goal_context not in str(agent.messages)
    skill_md.write_text("---\nname: required\ndescription: Test workflow.\n---\nUPDATED_REQUIRED_INSTRUCTION", encoding="utf-8")
    list(agent.process_message("Next task."))
    assert "UPDATED_REQUIRED_INSTRUCTION" in captured[-1]["messages"][0]["content"]
    assert "FINAL_REQUIRED_INSTRUCTION" not in captured[-1]["messages"][0]["content"]


def test_missing_required_skill_blocks_before_model_and_history_changes(tmp_path):
    manager = SkillsManager(project_root=tmp_path, app_root=tmp_path / "app")
    manager.restore_pinned_skills(["missing-required"])
    agent = _agent(tmp_path, mode="reverie")
    agent.tool_executor.context["skills_manager"] = manager
    with pytest.raises(ValueError, match="Required Skill is unavailable"):
        list(agent.process_message("Do the work."))
    assert agent.messages == []
