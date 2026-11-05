"""SenseNova runtime exercises the real Messages SDK and HTTP tool round trip."""

from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import threading

import httpx
import pytest

from reverie.agent.agent import ReverieAgent
from reverie.config import Config
from reverie.sensenova import build_sensenova_anthropic_options
from reverie import sensenova


@contextmanager
def messages_gateway():
    requests = []
    thinking = {"type": "thinking", "thinking": "Read the fixture.", "signature": "fixture-signature"}
    tool = {"type": "tool_use", "id": "toolu_fixture", "name": "file_ops", "input": {"operation": "read", "path": "fixture.txt"}}
    turns = [[thinking, tool], [{"type": "text", "text": "Fixture verified."}]]

    class Handler(BaseHTTPRequestHandler):
        def do_POST(self):
            body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
            requests.append({"path": self.path, "body": body, "authorization": self.headers.get("Authorization"), "version": self.headers.get("anthropic-version")})
            content = turns[min(len(requests) - 1, 1)]
            message = {"id": "msg_fixture", "type": "message", "role": "assistant", "model": body["model"], "content": content,
                       "stop_reason": "tool_use" if len(requests) == 1 else "end_turn", "stop_sequence": None,
                       "usage": {"input_tokens": 10, "output_tokens": 10}}
            if body.get("stream"):
                # SenseNova's real SSE message_start currently sends content=null.
                events = [("message_start", {"type": "message_start", "message": {**message, "content": None, "stop_reason": None}})]
                for index, block in enumerate(content):
                    start = {**block}
                    if block["type"] == "tool_use":
                        start["input"] = {}
                    elif block["type"] == "text":
                        start["text"] = ""
                    events.append(("content_block_start", {"type": "content_block_start", "index": index, "content_block": start}))
                    if block["type"] in {"tool_use", "text"}:
                        delta = {"type": "input_json_delta", "partial_json": json.dumps(block["input"])} if block["type"] == "tool_use" else {"type": "text_delta", "text": block["text"]}
                        events.append(("content_block_delta", {"type": "content_block_delta", "index": index, "delta": delta}))
                    events.append(("content_block_stop", {"type": "content_block_stop", "index": index}))
                events.extend([("message_delta", {"type": "message_delta", "delta": {"stop_reason": message["stop_reason"], "stop_sequence": None}, "usage": {"output_tokens": 10}}), ("message_stop", {"type": "message_stop"})])
                data = "".join(f"event: {name}\ndata: {json.dumps(event)}\n\n" for name, event in events).encode()
                content_type = "text/event-stream"
            else:
                data = json.dumps(message).encode()
                content_type = "application/json"
            self.send_response(200)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def log_message(self, *args):
            pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_port}/v1/chat/completions", requests
    finally:
        server.shutdown()
        server.server_close()
        thread.join()


@pytest.mark.parametrize("streaming", [False, True])
@pytest.mark.parametrize("effort", ["none", "high"])
def test_runtime_uses_native_messages_and_preserves_tool_continuation(tmp_path, monkeypatch, streaming, effort):
    monkeypatch.setenv("REVERIE_APP_ROOT", str(tmp_path / "app"))
    monkeypatch.setattr(sensenova, "_MODEL_CACHE", {})
    monkeypatch.setattr(ReverieAgent, "_build_proxied_http_client", lambda self: httpx.Client(trust_env=False))
    (tmp_path / "fixture.txt").write_text("catalog fixture content", encoding="utf-8")
    with messages_gateway() as (url, requests):
        config = Config(active_model_source="sensenova", sensenova={"api_url": url, "api_key": "fixture-key", "reasoning_effort": effort})
        model = config.active_model
        agent = ReverieAgent(base_url=model.base_url, api_key=model.api_key, model=model.model,
                             provider=model.provider, thinking_mode=model.thinking_mode,
                             project_root=tmp_path, config=config)
        agent._check_and_compress_context = lambda **kwargs: None
        agent.messages = [{"role": "user", "content": "Read fixture.txt and confirm."}]
        agent.get_visible_tool_schemas = lambda: [agent.tool_executor.get_tool("file_ops").get_schema()]
        try:
            result = "".join(agent._process_streaming_anthropic()) if streaming else agent._process_non_streaming_anthropic()
            assert "Fixture verified." in result
            assert len(requests) == 2
            for request in requests:
                assert request["path"] == "/v1/messages"
                assert request["authorization"] == "Bearer fixture-key"
                assert request["version"] == "2023-06-01"
                body = request["body"]
                assert body["stream"] is streaming
                assert body["thinking"] == {"type": "disabled" if effort == "none" else "adaptive"}
                assert body["max_tokens"] == 65536
                assert "reasoning_effort" not in body and "top_p" not in body
                assert (body.get("output_config") == {"effort": "high"}) if effort == "high" else "output_config" not in body
            followup = requests[1]["body"]["messages"]
            assistant = next(item for item in followup if item["role"] == "assistant")
            assert assistant["content"][0]["signature"] == "fixture-signature"
            tool_result = followup[-1]["content"][0]
            assert tool_result["type"] == "tool_result"
            assert tool_result["tool_use_id"] == "toolu_fixture"
            assert "catalog fixture content" in tool_result["content"]
        finally:
            if agent._client:
                agent._client.close()


def test_explicit_non_reasoning_catalog_does_not_receive_thinking_options(monkeypatch):
    model = sensenova._sensenova_model("plain-model", "Plain Model", "Fixture", thinking=False)
    monkeypatch.setattr(sensenova, "resolve_sensenova_selected_model", lambda *args, **kwargs: model)
    options = build_sensenova_anthropic_options({"reasoning_effort": "high"})
    assert "thinking" not in options and "extra_body" not in options


def test_kimi_k3_uses_the_only_allowed_temperature(monkeypatch):
    monkeypatch.setattr(sensenova, "_MODEL_CACHE", {})
    cfg = sensenova.normalize_sensenova_config({"selected_model_id": "kimi-k3", "temperature": 0.6})
    assert cfg["temperature"] == 1.0
    assert build_sensenova_anthropic_options(cfg)["temperature"] == 1.0


def test_glm53_keeps_provider_thinking_when_disable_is_rejected(monkeypatch):
    monkeypatch.setattr(sensenova, "_MODEL_CACHE", {})
    options = build_sensenova_anthropic_options({"selected_model_id": "glm-5.3", "reasoning_effort": "none"})
    assert options["temperature"] == 0.6
    assert "thinking" not in options and "extra_body" not in options
