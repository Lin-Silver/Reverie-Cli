from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
import threading

import pytest

from reverie.agent.agent import ReverieAgent
from reverie.config import Config
from reverie.tools.serial_novel import SerialNovelTool
from reverie.writer.style_runtime import WStyleRuntime

from test_wstyles import write_card


@contextmanager
def model_server():
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def do_POST(self):
            payload = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
            self.server.payloads.append(payload)
            reply_text = getattr(self.server, "reply_text", "原创场景练习完成。")
            gemini = ":streamGenerateContent" in self.path
            if gemini:
                response = {"candidates": [{"content": {"role": "model", "parts": [{"text": reply_text}]},
                                            "finishReason": "STOP"}],
                            "usageMetadata": {"promptTokenCount": 10, "candidatesTokenCount": 10, "totalTokenCount": 20}}
            elif self.path.endswith("/messages"):
                response = {"id": "msg_proof", "type": "message", "role": "assistant", "model": "proof",
                            "content": [{"type": "text", "text": reply_text}], "stop_reason": "end_turn",
                            "usage": {"input_tokens": 10, "output_tokens": 10}}
            elif self.path.endswith("/responses"):
                response = {"id": "resp_proof", "object": "response", "created_at": 1, "status": "completed",
                            "model": "proof", "output": [{"type": "message", "id": "msg_proof", "role": "assistant",
                            "status": "completed", "content": [{"type": "output_text", "text": reply_text, "annotations": []}]}]}
            else:
                response = {"id": "chat_proof", "object": "chat.completion", "created": 1, "model": "proof",
                            "choices": [{"index": 0, "message": {"role": "assistant", "content": reply_text}, "finish_reason": "stop"}]}
            raw = json.dumps(response, ensure_ascii=False).encode("utf-8")
            if gemini:
                raw = b"data: " + raw + b"\n\n"
            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream" if gemini else "application/json")
            self.send_header("Content-Length", str(len(raw)))
            self.end_headers()
            self.wfile.write(raw)

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    server.daemon_threads = True
    server.payloads = []
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield server
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


def make_agent(root, runtime, provider, port):
    base = f"http://127.0.0.1:{port}/v1"
    if provider in {"request", "curl"}:
        base += "/chat/completions"
    agent = ReverieAgent(base, "local-test-key", "proof", project_root=root, mode="writer", provider=provider,
                          config=Config(mode="writer", api_max_retries=0))
    agent.wstyle_runtime = runtime
    return agent


def system_text(payload):
    if "systemInstruction" in payload:
        return "\n".join(part.get("text", "") for part in payload["systemInstruction"].get("parts", []))
    if "system" in payload:
        value = payload["system"]
        return value if isinstance(value, str) else "\n".join(block.get("text", "") for block in value)
    if "instructions" in payload:
        return payload["instructions"]
    if "input" in payload and isinstance(payload["input"], list):
        return "\n".join(
            item["content"] if isinstance(item.get("content"), str) else "".join(block.get("text", "") for block in item.get("content", []))
            for item in payload["input"] if item.get("role") in {"system", "developer"}
        )
    return "\n".join(message.get("content", "") for message in payload.get("messages", []) if message.get("role") == "system")


@pytest.mark.parametrize("provider", ["request", "openai-chat", "openai-responses", "anthropic", "curl", "gemini"])
def test_actual_http_requests_follow_switch_edit_off_and_restart(tmp_path, provider):
    runtime = WStyleRuntime(tmp_path, app_root=tmp_path / "app")
    write_card(runtime.repository, "a", "STYLE_A_细密的感官与潜台词")
    path_b = write_card(runtime.repository, "b", "STYLE_B_短句和主动选择", layer="narrative")
    with model_server() as server:
        agent = make_agent(tmp_path, runtime, provider, server.server_port)

        def request():
            result = "".join(agent.process_message("写一段原创场景练习。", stream=False))
            assert "练习完成" in result
            return system_text(server.payloads[-1])

        base = request()
        assert "STYLE_A" not in base and "STYLE_B" not in base
        runtime.set_selection(["a"], global_scope=True)
        first = request()
        assert "STYLE_A" in first and "STYLE_B" not in first
        runtime.set_selection(["b"], global_scope=True)
        second = request()
        assert "STYLE_B" in second and "STYLE_A" not in second
        runtime.set_selection(["a", "b"], global_scope=True)
        combined = request()
        assert combined.count("STYLE_A") == 1 and combined.count("STYLE_B") == 1
        path_b.write_text(path_b.read_text(encoding="utf-8").replace("STYLE_B_", "STYLE_EDITED_B_"), encoding="utf-8")
        edited = request()
        assert "STYLE_EDITED_B" in edited and "STYLE_B_" not in edited
        restored = WStyleRuntime(tmp_path, app_root=runtime.app_root)
        agent.wstyle_runtime = restored
        assert "STYLE_EDITED_B" in request()
        restored.set_selection([], global_scope=True)
        off = request()
        assert agent.system_prompt in off
        assert "STYLE_A" not in off and "STYLE_EDITED_B" not in off
        assert "Active WStyle creative guidance" not in off
        assert not any("Active WStyle creative guidance" in str(m.get("content", "")) for m in agent.messages)
        assert len(server.payloads) == 7


def test_old_system_snapshots_do_not_reappear_after_switch(tmp_path):
    runtime = WStyleRuntime(tmp_path, app_root=tmp_path / "app")
    write_card(runtime.repository, "a", "OLD_STYLE_A")
    write_card(runtime.repository, "b", "NEW_STYLE_B")
    runtime.set_selection(["a"], global_scope=True)
    agent = ReverieAgent("http://127.0.0.1/v1", "test", "proof", project_root=tmp_path, mode="writer", config=Config(mode="writer"))
    agent.wstyle_runtime = runtime
    old_request = agent._build_messages()
    runtime.set_selection(["b"], global_scope=True)
    agent.messages = [*old_request, {"role": "user", "content": "Continue the exercise."}]
    current = agent._build_messages()
    assert "OLD_STYLE_A" not in "\n".join(m.get("content", "") for m in current)
    assert sum(m.get("role") == "system" and "Active WStyle creative guidance" in m.get("content", "") for m in current) == 1
    assert "OLD_STYLE_A" not in str(agent._history_from_request_messages(old_request))


def test_non_writer_requests_never_include_styles_or_expand_tools(tmp_path):
    runtime = WStyleRuntime(tmp_path, app_root=tmp_path / "app")
    write_card(runtime.repository, "a", "ONLY_WRITER_STYLE")
    runtime.set_selection(["a"], global_scope=True)
    agent = ReverieAgent("http://127.0.0.1/v1", "test", "proof", project_root=tmp_path, mode="writer", config=Config(mode="writer"))
    agent.wstyle_runtime = runtime
    tools = agent.get_visible_tool_schemas()
    assert "ONLY_WRITER_STYLE" in agent._build_messages()[0]["content"]
    assert agent.get_visible_tool_schemas() == tools
    agent.update_mode("reverie")
    assert "ONLY_WRITER_STYLE" not in agent._build_messages()[0]["content"]
