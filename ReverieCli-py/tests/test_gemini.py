from __future__ import annotations

import base64
import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from types import SimpleNamespace

import pytest
from google.genai import types

from reverie.config import Config, ConfigManager, EXTERNAL_MODEL_SOURCES, ModelConfig, normalize_model_provider
from reverie.custom_providers import custom_provider_auth_headers, default_custom_provider, normalize_custom_provider_format
from reverie.gemini import default_gemini_config, gemini_http_options, gemini_request, iter_gemini_events


@pytest.fixture(autouse=True)
def clean_gemini_environment(monkeypatch):
    monkeypatch.delenv("GOOGLE_API_KEY", raising=False)
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)


def test_gemini_is_a_native_transport_and_builtin_source(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "gemini-test-key")
    config = Config.from_dict({"active_model_source": "gemini"})
    assert "gemini" in EXTERNAL_MODEL_SOURCES
    assert "webgemini" not in EXTERNAL_MODEL_SOURCES
    assert normalize_model_provider("gemini") == "gemini"
    assert config.active_model.provider == "gemini"
    assert config.active_model.api_key == "gemini-test-key"
    assert config.to_dict()["gemini"]["api_key"] == ""


def test_auto_environment_selection_uses_google_priority(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "gemini-test-key")
    monkeypatch.setenv("GOOGLE_API_KEY", "google-test-key")
    config = Config.from_dict({"active_model_source": "gemini"})
    assert config.gemini["api_key_env"] == "GOOGLE_API_KEY"
    assert config.active_model.api_key == "google-test-key"
    monkeypatch.setenv("GOOGLE_API_KEY", "rotated-test-key")
    assert config.active_model.api_key == "rotated-test-key"


def test_explicit_environment_name_and_literal_key_are_respected(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "gemini-test-key")
    monkeypatch.setenv("GOOGLE_API_KEY", "google-test-key")
    selected = Config.from_dict({"active_model_source": "gemini", "gemini": {"api_key_env": "GEMINI_API_KEY"}})
    assert selected.active_model.api_key == "gemini-test-key"
    literal = Config.from_dict({"active_model_source": "gemini", "gemini": {"api_key": "literal-test-key"}})
    assert literal.active_model.api_key == "literal-test-key"


@pytest.mark.parametrize("has_key", [True, False])
def test_legacy_source_is_removed_and_migrated_with_notice(tmp_path, monkeypatch, has_key):
    if has_key:
        monkeypatch.setenv("GEMINI_API_KEY", "gemini-test-key")
    app_root = tmp_path / "app"
    path = app_root / ".reverie" / "config.json"
    path.parent.mkdir(parents=True)
    path.write_text(json.dumps({"active_model_source": "webgemini", "webgemini": {"cookie": "legacy-private-cookie"},
        "models": [{"model": "manual", "model_display_name": "Manual", "provider": "openai-chat", "api_key": "manual-key", "base_url": "https://example.test/v1"},
                   {"model": "old-web", "provider": "webgemini"}]}), encoding="utf-8")
    monkeypatch.setattr("reverie.config.get_app_root", lambda: app_root)
    manager = ConfigManager(tmp_path / "workspace")
    config = manager.load()
    assert config.active_model_source == ("gemini" if has_key else "standard")
    assert [model.model for model in config.models] == ["manual"]
    saved = json.loads(path.read_text(encoding="utf-8"))
    assert "webgemini" not in saved
    notice = manager.consume_load_notice()
    assert notice and "WebGemini" in notice["detail"] and "Gemini" in notice["detail"]
    assert "legacy-private-cookie" not in str(notice)


def test_custom_gemini_format_has_native_authentication():
    record = default_custom_provider(name="Gateway", base_url="https://example.test/gemini/v1beta", api_key="test-key", provider_format="gemini")
    assert normalize_custom_provider_format("gemini") == "gemini"
    headers = custom_provider_auth_headers(record)
    assert headers["x-goog-api-key"] == "test-key"
    assert "Authorization" not in headers


def test_versioned_gateway_url_preserves_prefix():
    options = gemini_http_options("https://example.test/gemini/v1beta/", 9)
    assert options.base_url == "https://example.test/gemini"
    assert options.api_version == "v1beta"
    assert options.timeout == 9000


def test_native_history_preserves_markdown_images_and_function_signature():
    signature = base64.b64encode(b"opaque-signature").decode()
    request = gemini_request([
        {"role": "system", "content": "# Project rules\nKeep this Markdown."},
        {"role": "user", "content": [{"type": "text", "text": "Read image"}, {"type": "image_url", "image_url": {"url": "data:image/png;base64,eA=="}}]},
        {"role": "assistant", "content": None, "tool_calls": [{"id": "call-1", "type": "function", "thought_signature": signature, "function": {"name": "read_file", "arguments": '{"path":"a.md"}'}}]},
        {"role": "tool", "tool_call_id": "call-1", "content": "file contents"},
    ], [{"type": "function", "function": {"name": "read_file", "parameters": {"type": "object", "properties": {"path": {"type": "string"}}}}}])
    assert request["config"].system_instruction.startswith("# Project rules")
    assert request["contents"][0].parts[1].inline_data.data == b"x"
    assert request["contents"][1].parts[0].thought_signature == b"opaque-signature"
    response = request["contents"][2].parts[0].function_response
    assert response.name == "read_file" and response.id == "call-1"
    assert request["config"].automatic_function_calling.disable is True


def test_sdk_events_match_agent_protocol_and_include_signatures():
    response = types.GenerateContentResponse(candidates=[types.Candidate(content=types.Content(role="model", parts=[
        types.Part(text="reasoning", thought=True), types.Part(text="answer"),
        types.Part(function_call=types.FunctionCall(name="read_file", args={"path": "a.md"}), thought_signature=b"signature"),
    ]), finish_reason="STOP")], usage_metadata=types.GenerateContentResponseUsageMetadata(prompt_token_count=12, candidates_token_count=6, thoughts_token_count=3, cached_content_token_count=4, total_token_count=21))
    def stream(**kwargs):
        yield response
    events = list(iter_gemini_events(SimpleNamespace(models=SimpleNamespace(generate_content_stream=stream)), "model", {"contents": [], "config": {}}))
    assert [event["type"] for event in events] == ["usage", "reasoning", "content", "tool_call", "finish"]
    assert events[3]["name"] == "read_file"
    assert base64.b64decode(events[3]["thought_signature"]) == b"signature"
    assert events[-1]["reason"] == "tool_calls"


@pytest.fixture
def gemini_endpoint():
    requests = []
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def do_GET(self):
            requests.append((self.path, dict(self.headers), None))
            body = json.dumps({"models": [
                {"name": "models/gemini-test", "displayName": "Test Gemini", "inputTokenLimit": 32768, "outputTokenLimit": 4096, "supportedGenerationMethods": ["generateContent"]},
                {"name": "models/embedding-test", "supportedGenerationMethods": ["embedContent"]},
            ]}).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def do_POST(self):
            payload = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
            requests.append((self.path, dict(self.headers), payload))
            has_result = any(part.get("functionResponse") for content in payload.get("contents", []) for part in content.get("parts", []))
            part = {"text": "Verified file contents."} if has_result else {"functionCall": {"name": "file_ops", "args": {"operation": "read", "path": "proof.txt"}}, "thoughtSignature": base64.b64encode(b"sdk-signature").decode()}
            event = {"candidates": [{"content": {"role": "model", "parts": [part]}, "finishReason": "STOP"}],
                     "usageMetadata": {"promptTokenCount": 120, "candidatesTokenCount": 10, "thoughtsTokenCount": 5, "cachedContentTokenCount": 40, "totalTokenCount": 135}}
            body = ("data: " + json.dumps(event) + "\n\n").encode()
            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    worker = threading.Thread(target=server.serve_forever, daemon=True)
    worker.start()
    try:
        yield f"http://127.0.0.1:{server.server_port}/gateway/v1beta", requests
    finally:
        server.shutdown()
        server.server_close()
        worker.join(2)


def test_real_sdk_catalog_uses_versioned_gateway_and_native_key(gemini_endpoint):
    from reverie.custom_providers import fetch_custom_provider_models
    base_url, requests = gemini_endpoint
    provider = default_custom_provider(name="Gateway", base_url=base_url, api_key="loopback-test-key", provider_format="gemini")
    models = fetch_custom_provider_models(provider, force_refresh=True)
    assert [model["id"] for model in models] == ["gemini-test"]
    assert models[0]["context_length"] == 32768
    assert requests[0][0].split("?")[0] == "/gateway/v1beta/models"
    assert next(value for key, value in requests[0][1].items() if key.lower() == "x-goog-api-key") == "loopback-test-key"


@pytest.mark.parametrize("streaming", [True, False])
def test_real_sdk_agent_executes_file_tool_and_returns_signature(tmp_path, gemini_endpoint, streaming):
    from reverie.agent.agent import ReverieAgent, decode_stream_event
    from reverie.tools.file_ops import FileOpsTool
    base_url, requests = gemini_endpoint
    (tmp_path / "proof.txt").write_text("actual file proof", encoding="utf-8")
    config = Config(active_model_source="gemini", gemini={**default_gemini_config(), "api_key": "loopback-test-key", "api_url": base_url})
    agent = ReverieAgent(base_url, "loopback-test-key", "gemini-test", project_root=tmp_path, provider="gemini", config=config)
    agent.get_visible_tool_schemas = lambda: [FileOpsTool().get_schema()]
    agent.messages = [{"role": "user", "content": "Read proof.txt and describe its contents."}]
    try:
        if streaming:
            output = list(agent._process_streaming(session_id="sdk-test"))
            answer = "".join(chunk for chunk in output if decode_stream_event(chunk) is None)
        else:
            answer = agent._process_non_streaming(session_id="sdk-test")
    finally:
        if agent._client is not None:
            agent._client.close()
    assert "Verified file contents." in answer
    assert len(requests) == 2
    assert all(path.split("?")[0] == "/gateway/v1beta/models/gemini-test:streamGenerateContent" for path, _, _ in requests)
    parts = [part for content in requests[1][2]["contents"] for part in content.get("parts", [])]
    assert any(part.get("thoughtSignature") == base64.b64encode(b"sdk-signature").decode() for part in parts)
    response = next(part["functionResponse"] for part in parts if "functionResponse" in part)
    assert "actual file proof" in str(response)
