import json

import pytest

from reverie.agent.agent import ReverieAgent, _StreamingTurnState


def _writer_agent():
    agent = object.__new__(ReverieAgent)
    agent.mode = "writer"
    agent._writer_native_tool_choice = lambda: None
    agent._writer_active_project_state = lambda: {
        "novel_id": "water-station",
        "active_chapter": 1,
        "active_chapter_has_control_card": True,
    }
    agent._writer_latest_turn_serial_novel_action = lambda: "prepare_chapter"
    return agent


@pytest.mark.parametrize("nested_data", [False, True])
def test_provider_key_value_wrapper_preserves_only_the_actual_prose(nested_data):
    agent = _writer_agent()
    prose = "\n\n".join(
        f"她核对第{index:03d}页记录，写下这一页的水位、日期和经办人，另纸说明疑点，没有改动玻璃柜中的原件。"
        for index in range(140)
    ) + "\n\n讲义上印着<function=not_a_call>，她只将它当作标签抄在便签。"
    assert sum(not char.isspace() for char in prose) > 5000
    payload = {"data": json.dumps({"content": prose, "summary": "核对记录。"}, ensure_ascii=False)} if nested_data else {"content": prose, "summary": "核对记录。"}
    arguments = {"action": "commit_chapter", "novel_id": "water-station", "chapter": "1", **payload}
    state = _StreamingTurnState()
    state.collected_content = "I will draft the chapter.\n<tool_call>serial_novel" + "".join(
        f"<arg_key>{key}</arg_key><arg_value>{value}</arg_value>" for key, value in arguments.items()
    ) + "</tool_call>"

    assert agent._promote_writer_json_tool_call(state)
    call = state.tool_calls[0]["function"]
    parsed = json.loads(call["arguments"])
    assert call["name"] == "serial_novel" and parsed["chapter"] == 1
    assert parsed.get("data", parsed)["content"] == prose
    assert parsed.get("data", parsed)["summary"] == "核对记录。"
    assert agent._writer_commit_call_has_prose(parsed)
    assert state.collected_content == ""


@pytest.mark.parametrize("wrapper", [
    "<tool_call>serial_novel<arg_key>content</arg_key><arg_value>",
    "<tool_call><function=serial_novel><parameter=content>",
    "<tool_call>other_tool<arg_key>content</arg_key><arg_value>",
])
def test_unparsed_wrappers_never_become_direct_chapter_prose(wrapper):
    agent = _writer_agent()
    state = _StreamingTurnState()
    state.collected_content = wrapper + "未执行的工具参数。" * 800
    original = state.collected_content

    assert not agent._promote_writer_direct_prose_commit(state)
    assert state.tool_calls == [] and state.collected_content == original
    instruction = agent._writer_retry_instruction_for_short_direct_prose(original)
    assert "tool-call wrapper" in instruction and "plain" in instruction
