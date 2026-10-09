"""Exercise the opt-in text protocol through real SDKs, HTTP and CLI tools."""

import json
import threading
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

from reverie.agent.agent import ReverieAgent
from reverie.api_compatibility import build_compatibility_messages, parse_compatibility_reply
from reverie.config import Config, ConfigManager
from reverie.session.manager import SessionManager
from reverie.settings_catalog import apply_setting_value, get_setting_items, setting_section_for
from reverie.tools.file_ops import FileOpsTool


TOOLS = [FileOpsTool().get_schema()]
ACTION = {"tool_calls": [{"name": "file_ops", "arguments": {"operation": "read", "path": "probe.txt"}}]}


@contextmanager
def gateway(reply):
    requests = []

    class Handler(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"

        def do_POST(self):
            body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
            requests.append({"path": self.path, "body": body, "connection": self.client_address})
            response = reply(body, len(requests))
            encoded = json.dumps(response).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(encoded)))
            self.end_headers()
            self.wfile.write(encoded)

        def log_message(self, *args):
            pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_port}/v1", requests
    finally:
        server.shutdown()
        server.server_close()
        thread.join()


def response_for(provider, text, truncated=False):
    usage = {"input_tokens": 10, "output_tokens": 8}
    if provider == "anthropic":
        return {"id": "msg_test", "type": "message", "role": "assistant", "model": "test-model",
                "content": [{"type": "text", "text": text}], "stop_reason": "max_tokens" if truncated else "end_turn", "usage": usage}
    if provider in {"openai-responses", "curl-responses"}:
        return {"id": "resp_test", "object": "response", "model": "test-model", "status": "incomplete" if truncated else "completed",
                "output": [{"id": "msg_test", "type": "message", "role": "assistant", "status": "completed",
                            "content": [{"type": "output_text", "text": text, "annotations": []}]}], "usage": usage}
    return {"id": "chat_test", "object": "chat.completion", "model": "test-model", "created": 1,
            "choices": [{"index": 0, "message": {"role": "assistant", "content": text}, "finish_reason": "length" if truncated else "stop"}],
            "usage": {"prompt_tokens": 10, "completion_tokens": 8, "total_tokens": 18}}


def make_agent(tmp_path, url, provider="anthropic", compatibility=True, permission="full_control"):
    config = Config(api_compatibility=compatibility, auto_index=False, api_max_retries=0)
    config.permission_level = permission
    manager = ConfigManager(tmp_path)
    manager.save(config)
    actual_provider = "curl" if provider == "curl-responses" else provider
    base = url + "/chat/completions" if provider in {"request", "openai-full-endpoint"} else url
    if provider == "anthropic":
        base = url.removesuffix("/v1")
    agent = ReverieAgent(base_url=base, api_key="test-key", model="test-model", project_root=tmp_path,
                         provider="openai-chat" if provider == "openai-full-endpoint" else actual_provider, config=config,
                         endpoint="/responses" if provider == "curl-responses" else "")
    agent.tool_executor.update_context("config_manager", manager)
    agent._check_and_compress_context = lambda **kwargs: None
    agent.get_visible_tool_schemas = lambda: TOOLS
    agent.messages = [{"role": "user", "content": "Read probe.txt and give its exact contents."}]
    return agent


@pytest.mark.parametrize("provider", ["anthropic", "openai-chat", "openai-responses", "request", "curl", "curl-responses", "openai-full-endpoint"])
@pytest.mark.parametrize("stream", [False, True])
def test_real_tool_round_trip_is_non_streaming_and_preserves_history(tmp_path, provider, stream):
    marker = "actual local file contents"
    (tmp_path / "probe.txt").write_text(marker, encoding="utf-8")

    def reply(body, number):
        assert body["stream"] is False
        assert not {"tools", "tool_choice", "thinking", "reasoning", "system", "stream_options"}.intersection(body)
        content = (body.get("messages") or body["input"])[0]["content"]
        context = json.loads(content.split("Context:\n", 1)[1])
        assert context["tools"][0]["name"] == "file_ops"
        if number == 1:
            text = json.dumps(ACTION)
        else:
            assert any(row["role"] == "tool" and marker in row["content"] for row in context["conversation"])
            text = json.dumps({"answer": marker})
        return response_for("openai-chat" if provider == "openai-full-endpoint" else provider, text)

    with gateway(reply) as (url, requests):
        agent = make_agent(tmp_path, url, provider)
        sessions = SessionManager(tmp_path / "sessions")
        session = sessions.create_session()
        agent.tool_executor.update_context("session_manager", sessions)
        if stream:
            output = "".join(agent._process_streaming(session.id))
        else:
            output = agent._process_non_streaming(session.id)
        assert output.endswith(marker)
        assert len(requests) == 2
        expected_path = "/v1/messages" if provider == "anthropic" else "/v1/responses" if provider in {"openai-responses", "curl-responses"} else "/v1/chat/completions"
        assert all(record["path"] == expected_path for record in requests)
        if provider not in {"curl", "curl-responses"}:
            assert requests[0]["connection"] == requests[1]["connection"]
        assert agent.messages[1]["tool_calls"][0]["function"]["name"] == "file_ops"
        assert agent.messages[2]["role"] == "tool" and marker in agent.messages[2]["content"]
        assert any(row["role"] == "tool" for row in sessions.load_session(session.id).messages)
        if agent._client:
            agent._client.close()


@pytest.mark.parametrize("text", [
    'Example: {"tool_calls":[{"name":"file_ops","arguments":{}}]}',
    '{"tool_calls":[{"name":"file_ops","arguments":{}}],"answer":"done"}',
    '{"tool_calls":[{"name":"unknown","arguments":{}}]}',
    '{"tool_calls":[{"name":"file_ops","arguments":"{}"}]}',
    '{"tool_calls":[]}', '[]', '{"answer":4}', '{"tool_calls":[',
])
def test_malformed_or_unavailable_actions_never_become_tool_calls(text):
    with pytest.raises(ValueError):
        parse_compatibility_reply(text, TOOLS)


def test_fenced_reply_and_literal_tool_examples_in_answer():
    _, calls = parse_compatibility_reply("```json\n" + json.dumps(ACTION) + "\n```", TOOLS)
    assert calls[0]["function"]["name"] == "file_ops"
    literal = json.dumps(ACTION)
    assert parse_compatibility_reply(json.dumps({"answer": literal}), TOOLS) == (literal, [])


@pytest.mark.parametrize("provider", ["anthropic", "openai-chat", "openai-responses"])
def test_truncated_response_is_not_executed_or_retried(tmp_path, provider):
    with gateway(lambda body, number: response_for(provider, json.dumps(ACTION), truncated=True)) as (url, requests):
        agent = make_agent(tmp_path, url, provider)
        with pytest.raises(ValueError, match="truncated"):
            agent._process_non_streaming()
        assert len(requests) == 1 and len(agent.messages) == 1
        agent._client.close()


def test_normal_mode_does_not_promote_text_to_tools(tmp_path):
    with gateway(lambda body, number: response_for("anthropic", json.dumps(ACTION))) as (url, requests):
        agent = make_agent(tmp_path, url, compatibility=False)
        assert "tool_calls" in agent._process_non_streaming()
        assert requests[0]["body"]["tools"][0]["name"] == "file_ops"
        assert not any(row["role"] == "tool" for row in agent.messages)
        agent._client.close()


def test_permission_denial_uses_normal_executor_and_is_sent_back(tmp_path):
    action = {"tool_calls": [{"name": "str_replace_editor", "arguments": {"command": "create", "path": "blocked.txt", "file_text": "must not be written"}}]}
    def reply(body, number):
        if number == 2:
            context = json.loads(body["messages"][0]["content"].split("Context:\n", 1)[1])
            assert any(row["role"] == "tool" and "permission" in row["content"].lower() for row in context["conversation"])
        return response_for("anthropic", json.dumps(action if number == 1 else {"answer": "Permission denied."}))
    with gateway(reply) as (url, requests):
        agent = make_agent(tmp_path, url, permission="read_only")
        agent.get_visible_tool_schemas = lambda: [agent.tool_executor.get_tool("str_replace_editor").get_schema()]
        assert "Permission denied" in agent._process_non_streaming()
        assert not (tmp_path / "blocked.txt").exists()
        assert len(requests) == 2
        agent._client.close()


def test_non_text_payload_is_rejected_before_a_request():
    with pytest.raises(ValueError, match="text only"):
        build_compatibility_messages([{"role": "user", "content": [{"type": "image_url", "image_url": {"url": "data:image/png;base64,AAA="}}]}], TOOLS)


def test_compact_catalog_keeps_argument_schemas_and_removes_repeated_examples():
    message = build_compatibility_messages([{"role": "user", "content": "read probe.txt"}], TOOLS)[0]
    context = json.loads(message["content"].split("Context:\n", 1)[1])
    assert context["tools"][0]["parameters"] == TOOLS[0]["function"]["parameters"]
    assert context["tools"][0]["description"] == TOOLS[0]["function"]["description"].split("\n\n", 1)[0]
    assert len(json.dumps(context["tools"])) < len(json.dumps([tool["function"] for tool in TOOLS]))


def test_setting_defaults_off_persists_and_sits_beside_thinking_tool(tmp_path):
    manager = ConfigManager(tmp_path)
    config = Config()
    assert Config.from_dict({}).api_compatibility is False
    items = get_setting_items(config, manager, None)
    item = next(row for row in items if row["key"] == "api_compatibility")
    assert item["kind"] == "bool" and item["experimental"] and getattr(config, item["key"]) is False
    assert setting_section_for("api_compatibility") == setting_section_for("thinking_tool")
    success, _, reinit = apply_setting_value(config, manager, None, "api_compatibility", True)
    assert success and reinit
    manager.save(config)
    assert manager.load().api_compatibility is True
    assert Config.from_dict(config.to_dict()).api_compatibility is True
