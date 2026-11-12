import copy
import json

import pytest

from reverie.agent.text_completion import IncompleteTextResponse, _text_from_result
from reverie.writer.style_runtime import WStyleRuntime
from test_wstyle_requests import make_agent, model_server, system_text


@pytest.mark.parametrize("provider", ["request", "openai-chat", "openai-responses", "anthropic", "curl", "gemini"])
def test_auxiliary_calls_use_real_transport_without_history_tools_or_state_changes(tmp_path, provider):
    with model_server() as server:
        runtime = WStyleRuntime(tmp_path, app_root=tmp_path / "app")
        agent = make_agent(tmp_path, runtime, provider, server.server_port)
        agent.messages = [{"role": "user", "content": "PRIVATE_HISTORY"}]
        old_messages = copy.deepcopy(agent.messages)
        old_config = copy.deepcopy(agent.config)
        original_provider = (agent.provider, agent.base_url, agent.api_key)
        result = agent.complete_text_only("AUXILIARY_SYSTEM", "EXPLICIT_SAMPLE", max_tokens=2048)
        assert "练习完成" in result
        payload = server.payloads[-1]
        assert system_text(payload) == "AUXILIARY_SYSTEM"
        assert "EXPLICIT_SAMPLE" in json.dumps(payload)
        assert "PRIVATE_HISTORY" not in json.dumps(payload)
        assert not payload.get("tools") and not payload.get("tool_choice")
        assert payload.get("max_tokens", payload.get("max_output_tokens", payload.get("generationConfig", {}).get("maxOutputTokens"))) == 2048
        assert agent.messages == old_messages
        assert agent.config == old_config
        assert original_provider == (agent.provider, agent.base_url, agent.api_key)
        assert len(server.payloads) == 1


@pytest.mark.parametrize("data,flags", [
    ({"choices": [{"message": {"content": "ignore", "tool_calls": [{"id": "bad"}]}}]}, {}),
    ({"content": [{"type": "tool_use"}]}, {"anthropic": True}),
    ({"output": [{"type": "function_call"}]}, {"responses": True}),
    ({"choices": [{"message": {"content": "partial"}, "finish_reason": "length"}]}, {}),
    ({"output": [], "status": "incomplete"}, {"responses": True}),
])
def test_auxiliary_rejects_actions_and_incomplete_output(data, flags):
    with pytest.raises(ValueError):
        _text_from_result(None, data, **flags)


def test_incomplete_text_is_available_for_diagnostics_but_never_accepted_as_complete():
    with pytest.raises(IncompleteTextResponse) as raised:
        _text_from_result(None, {"content": [{"type": "text", "text": "未完成的正文"}], "stop_reason": "max_tokens"}, anthropic=True)
    assert raised.value.partial_text == "未完成的正文"


@pytest.mark.parametrize("text", ["<think>private plan</think>正文", "private plan</think>正文"])
def test_auxiliary_output_separates_inline_and_orphaned_reasoning_from_text(text):
    trace = {}
    result = _text_from_result(None, {"content": [{"type": "text", "text": text}], "stop_reason": "end_turn"},
                               anthropic=True, response_trace=trace)
    assert result == "正文"
    assert trace["raw_text"] == text and trace["separated_reasoning"] is True


def test_auxiliary_validates_budget_before_network(tmp_path):
    with model_server() as server:
        agent = make_agent(tmp_path, WStyleRuntime(tmp_path, app_root=tmp_path / "app"), "request", server.server_port)
        with pytest.raises(ValueError, match="budget"):
            agent.complete_text_only("system", "x" * 60_001)
        agent.config.max_context_tokens = 1024
        with pytest.raises(ValueError, match="context"):
            agent.complete_text_only("system", "text", max_tokens=1024)
        assert not server.payloads


def test_auxiliary_respects_advertised_active_model_context_before_network(tmp_path):
    from reverie.config import ModelConfig

    with model_server() as server:
        agent = make_agent(tmp_path, WStyleRuntime(tmp_path, app_root=tmp_path / "app"), "request", server.server_port)
        agent.config.models = [ModelConfig("proof", "Small", agent.base_url, max_context_tokens=1024)]
        with pytest.raises(ValueError, match="context"):
            agent.complete_text_only("system", "text", max_tokens=1024)
        assert not server.payloads


@pytest.mark.parametrize("provider", ["request", "openai-chat", "openai-responses", "anthropic", "curl"])
def test_explicit_long_form_calls_have_large_output_budget_without_changing_editorial_limits(tmp_path, provider):
    with model_server() as server:
        agent = make_agent(tmp_path, WStyleRuntime(tmp_path, app_root=tmp_path / "app"), provider, server.server_port)
        agent.config.api_timeout = 300
        agent.config.max_tokens = 65_536
        server.reply_text = "原创长章。" * 7_000
        with pytest.raises(ValueError, match="budget"):
            agent.complete_text_only("system", "write", max_tokens=32_768)
        assert not server.payloads
        output = agent.complete_text_only("LONG_FORM_SYSTEM", "EXPLICIT_LONG_CHAPTER", max_tokens=32_768, long_form=True)
        assert output == server.reply_text
        payload = server.payloads[-1]
        assert payload.get("max_tokens", payload.get("max_output_tokens")) == 32_768
        assert system_text(payload) == "LONG_FORM_SYSTEM"
        assert not payload.get("tools") and not payload.get("tool_choice")
        assert len(server.payloads) == 1


@pytest.mark.parametrize("provider", ["anthropic", "openai-responses"])
def test_desktop_review_and_extraction_reach_the_configured_transport_and_preserve_sources(tmp_path, provider):
    from reverie.config import Config, ModelConfig
    from test_wstyle_desktop import desktop_fixture
    from test_wstyle_models import valid_review, extracted_reply

    with model_server() as server:
        bridge, sessions, first, second = desktop_fixture(tmp_path)
        config = Config(mode="writer", models=[ModelConfig("proof", "Loopback", f"http://127.0.0.1:{server.server_port}/v1",
                                                        api_key="local-test-key", provider=provider)])
        interface = bridge.ensure_interface()
        interface.config_manager.load = lambda: config
        draft = tmp_path / "novels/second/drafts/chapter-0001.json"
        content = "她把伞放在门边。\n雨停了，她仍在等。\n她又说了一遍同样的话。"
        draft.write_text(json.dumps({"data": {"content": content}}, ensure_ascii=False), encoding="utf-8")
        before = draft.read_bytes()
        server.reply_text = valid_review()
        result = bridge.dispatch({"action": "wstyleCommand", "payload": {"args": "review --chapter 1", "sessionId": second.id}})
        assert result["success"], result["error"]
        assert draft.read_bytes() == before
        assert result["data"]["report"]["model_review"]["issues"][0]["line_start"] == 3
        sample = tmp_path / "sample.md"
        sample.write_text("窗外的水汽让她看不清那班车，但她认得鸣笛声。", encoding="utf-8")
        sample_before = sample.read_bytes()
        server.reply_text = extracted_reply()
        extracted = bridge.dispatch({"action": "wstyleCommand", "payload": {"args": "extract inferred --sample sample.md --source-note 自写练习", "sessionId": second.id}})
        assert extracted["success"], extracted["error"]
        assert sample.read_bytes() == sample_before
        assert extracted["data"]["card"]["id"] == "inferred"
        assert "active_wstyles" not in json.loads((tmp_path / "novels/second/tracking/state.json").read_text(encoding="utf-8"))
        assert sessions.get_current_session().id == first.id
        assert len(server.payloads) == 2
        assert all(not payload.get("tools") and not payload.get("tool_choice") for payload in server.payloads)
