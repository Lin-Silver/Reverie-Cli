"""Exercise the real Anthropic SDK, HTTP request and local tool round trip."""

import json
import threading
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest
import anthropic
import httpx

from reverie.agent.agent import ReverieAgent
from reverie.config import Config
from reverie.session.manager import SessionManager


def message(content, stop_reason="end_turn"):
    return {"id": "msg_test", "type": "message", "role": "assistant", "model": "test-model", "content": content, "stop_reason": stop_reason, "stop_sequence": None, "usage": {"input_tokens": 10, "output_tokens": 12}}


@contextmanager
def gateway(turns):
    requests = []

    class Handler(BaseHTTPRequestHandler):
        def do_POST(self):
            requests.append({"path": self.path, "body": json.loads(self.rfile.read(int(self.headers["Content-Length"])))})
            payload = json.dumps(turns[min(len(requests) - 1, len(turns) - 1)], ensure_ascii=False).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)

        def log_message(self, *args):
            pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_port}", requests
    finally:
        server.shutdown()
        server.server_close()
        thread.join()


def agent_for(tmp_path, base_url, monkeypatch):
    monkeypatch.setenv("REVERIE_APP_ROOT", str(tmp_path / "app"))
    agent = ReverieAgent(base_url=base_url, api_key="test-key", model="test-model", provider="anthropic", project_root=tmp_path, config=Config())
    agent._client = anthropic.Anthropic(base_url=base_url, api_key="test-key", max_retries=0, http_client=httpx.Client(trust_env=False))
    agent._ensure_client = lambda: agent._client
    agent._check_and_compress_context = lambda **kwargs: None
    agent.messages = [{"role": "user", "content": "Read the file and reply."}]
    return agent


def test_non_streaming_tool_blocks_execute_despite_wrong_stop_reason_and_preserve_signatures(tmp_path, monkeypatch):
    (tmp_path / "中文 文件.txt").write_text("文件内容", encoding="utf-8")
    thinking = {"type": "thinking", "thinking": "Inspect the file.", "signature": "test-signed-thinking"}
    call = {"type": "tool_use", "id": "toolu_file", "name": "file_ops", "input": {"operation": "read", "path": "中文 文件.txt"}}
    with gateway([message([thinking, call]), message([{"type": "text", "text": "已读取"}])]) as (url, requests):
        agent = agent_for(tmp_path, url, monkeypatch)
        agent.get_visible_tool_schemas = lambda: [agent.tool_executor.get_tool("file_ops").get_schema()]
        sessions = SessionManager(tmp_path / "session-data")
        session = sessions.create_session()
        agent.tool_executor.context["session_manager"] = sessions
        assert "已读取" in agent._process_non_streaming_anthropic(session_id=session.id)
        assert len(requests) == 2
        first, followup = [item["body"] for item in requests]
        assert all(item["path"] == "/v1/messages" for item in requests)
        assert first["stream"] is False
        assert first["tools"][0]["name"] == "file_ops"
        assert "path" in first["tools"][0]["input_schema"]["properties"]
        assistant = next(item for item in followup["messages"] if item["role"] == "assistant")
        assert assistant["content"][0] == thinking
        assert assistant["content"][1] == call
        result = followup["messages"][-1]["content"][0]
        assert result["type"] == "tool_result" and result["tool_use_id"] == call["id"]
        assert "文件内容" in result["content"]
        saved = sessions.load_session(session.id).messages
        assert saved[1]["reasoning_content"] == thinking["thinking"]
        assert saved[1]["anthropic_thinking"] == [thinking]
        assert any(item["role"] == "tool" and "文件内容" in item["content"] for item in saved)
        agent._client.close()


def test_non_streaming_end_turn_finishes_once_and_keeps_reasoning(tmp_path, monkeypatch):
    with gateway([message([{"type": "thinking", "thinking": "Reasoning", "signature": "signed"}, {"type": "text", "text": "answer"}])]) as (url, requests):
        agent = agent_for(tmp_path, url, monkeypatch)
        agent.get_visible_tool_schemas = lambda: []
        assert agent._process_non_streaming_anthropic() == "answer"
        assert len(requests) == 1
        assert agent.messages[-1]["reasoning_content"] == "Reasoning"
        agent._client.close()


def test_custom_provider_empty_billed_response_does_not_repeat_requests(tmp_path, monkeypatch):
    with gateway([message([])]) as (url, requests):
        agent = agent_for(tmp_path, url, monkeypatch)
        agent.get_visible_tool_schemas = lambda: []
        agent._is_active_model_source = lambda name: name == "custom"
        with pytest.raises(RuntimeError, match="reported output tokens"):
            agent._process_non_streaming_anthropic()
        assert len(requests) == 1
        agent._client.close()


def test_non_streaming_respects_truncation_with_bounded_continuation(tmp_path, monkeypatch):
    with gateway([message([{"type": "text", "text": "partial"}], "max_tokens"), message([{"type": "text", "text": "completed"}])]) as (url, requests):
        agent = agent_for(tmp_path, url, monkeypatch)
        agent.get_visible_tool_schemas = lambda: []
        assert agent._process_non_streaming_anthropic() == "partial\ncompleted"
        assert len(requests) == 2
        agent._client.close()
