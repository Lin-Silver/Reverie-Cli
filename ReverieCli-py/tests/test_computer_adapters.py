"""Desktop media and uncertain results across model transport adapters."""
import base64
import json
from types import SimpleNamespace

import pytest
from PIL import Image

from reverie.agent.agent import (
    ReverieAgent, _build_anthropic_tool_result_block, _tool_result_content, _tool_result_history_content,
)
from reverie.codex import build_codex_request_payload
from reverie.tools.computer import as_result, runtime_for
from reverie.agent.tool_executor import ToolExecutor
from reverie.tools.computer import COMPUTER_TOOL_CLASSES
from reverie.context_engine.compressor import (
    _build_deterministic_compression_summary, _format_compression_message,
    _truncate_for_memory, build_memory_digest,
)
from reverie.context_engine.handoff import _render_handoff_source
from reverie.config import Config, ModelConfig


def _screenshot(tmp_path, identity="image"):
    path = tmp_path / (identity + ".png")
    Image.new("RGB", (3, 2), "white").save(path)
    return {"version": "2.6", "ok": True, "command": "screenshot", "data": {
        "path": str(path), "image_id": identity, "width": 3, "height": 2,
    }}


def test_text_model_gets_saved_screenshot_without_image_payload(tmp_path):
    result = as_result(_screenshot(tmp_path), vision=False)
    assert isinstance(_tool_result_content(result), str)
    assert "base64" not in _tool_result_content(result)
    assert result.data["file_path"].endswith("image.png")


@pytest.mark.parametrize("second_image", [False, True])
def test_chat_media_follows_all_pending_tool_results(tmp_path, second_image):
    first = as_result(_screenshot(tmp_path), vision=True)
    second = as_result(_screenshot(tmp_path, "second"), vision=True) if second_image else as_result(
        {"version": "2.6", "ok": True, "command": "get", "data": {"value": "saved"}})
    calls = [{"id": identity, "type": "function", "function": {"name": "computer_screenshot", "arguments": "{}"}} for identity in ("a", "b")]
    messages = [{"role": "assistant", "content": None, "tool_calls": calls},
                {"role": "tool", "tool_call_id": "a", "content": _tool_result_content(first)},
                {"role": "tool", "tool_call_id": "b", "content": _tool_result_content(second)}]
    agent = SimpleNamespace(provider="openai", project_root=tmp_path)

    prepared = ReverieAgent._resolve_messages_for_request(agent, messages)

    assert [m["role"] for m in prepared] == ["assistant", "tool", "tool", "user"]
    assert all(isinstance(m["content"], str) for m in prepared[1:3])
    images = [part for part in prepared[-1]["content"] if part["type"] == "image_url"]
    assert len(images) == 1 + second_image
    response_payload = build_codex_request_payload("gpt-5", prepared)
    assert sum(item["type"] == "function_call_output" for item in response_payload["input"]) == 2
    assert sum(part["type"] == "input_image" for item in response_payload["input"] for part in item.get("content", [])) == 1 + second_image


def test_anthropic_screenshot_keeps_png_in_tool_result(tmp_path):
    result = as_result(_screenshot(tmp_path), vision=True)
    block = _build_anthropic_tool_result_block("a", result)
    image = next(part for part in block["content"] if part["type"] == "image")

    assert block["tool_use_id"] == "a"
    assert not block["is_error"]
    assert image["source"]["media_type"] == "image/png"
    assert base64.b64decode(image["source"]["data"]).startswith(b"\x89PNG")


def test_uncertain_error_survives_anthropic_and_responses_conversion(tmp_path):
    envelope = {"version": "2.6", "ok": False, "command": "click", "error": {
        "code": "TIMEOUT", "message": "Verification expired after input",
        "disposition": {"delivery": "delivered_unverified", "retry": "unsafe"},
    }}
    result = as_result(envelope)
    anthropic = _build_anthropic_tool_result_block("a", result)
    assert anthropic["is_error"]
    assert "delivered_unverified" in str(anthropic["content"])
    payload = build_codex_request_payload("gpt-5", [{"role": "tool", "tool_call_id": "a", "content": _tool_result_content(result)}])
    assert "delivered_unverified" in payload["input"][0]["output"]
    assert "unsafe" in payload["input"][0]["output"]


def test_large_tree_budget_retains_identity_and_incomplete_observation(tmp_path):
    executor = ToolExecutor(tmp_path)
    tool = next(cls for cls in COMPUTER_TOOL_CLASSES if cls.name == "computer_snapshot")()
    envelope = {"version": "2.6", "ok": True, "command": "snapshot", "data": {
        "tree": {"name": "many controls " * 6000}, "snapshot_id": "s1",
        "complete": True, "truncated": False, "identity_unproven": True,
    }}

    result = executor._apply_result_budget(tool, as_result(envelope))
    visible = json.loads(_tool_result_content(result))

    assert visible["data"]["snapshot_id"] == "s1"
    assert visible["data"]["complete"] is False
    assert visible["data"]["truncated"] is True
    assert visible["data"]["identity_unproven"] is True
    assert "tree" not in visible["data"]
    assert len(result.output) < 5000


def _large_error():
    return {"version": "2.6", "ok": False, "command": "click", "error": {
        "code": "TIMEOUT", "message": "Verification timeout",
        "details": {"tree": "long diagnostic " * 5000},
        "target": {"window_id": "w1", "ref": "@s1:e4"},
        "disposition": {"delivery": "delivered_unverified", "retry": "unsafe"},
        "verification_scope": "value_readback", "identity_unproven": True,
    }}


def test_large_error_budget_preserves_delivery_target_and_scope(tmp_path):
    executor = ToolExecutor(tmp_path)
    tool = next(cls for cls in COMPUTER_TOOL_CLASSES if cls.name == "computer_click")()
    result = executor._apply_result_budget(tool, as_result(_large_error()))
    visible = json.loads(result.error)

    assert not result.success
    assert visible["error"]["code"] == "TIMEOUT"
    assert visible["error"]["disposition"] == {"delivery": "delivered_unverified", "retry": "unsafe"}
    assert visible["error"]["target"] == {"window_id": "w1", "ref": "@s1:e4"}
    assert visible["error"]["verification_scope"] == "value_readback"
    assert len(result.error) < 5000


@pytest.mark.parametrize("render", [
    lambda messages: build_memory_digest(messages),
    lambda messages: _build_deterministic_compression_summary(messages, []),
    lambda messages: _format_compression_message(messages[0]),
    lambda messages: _render_handoff_source(messages),
])
def test_memory_and_handoff_keep_unsafe_delivery_after_large_details(render):
    message = {"role": "tool", "tool_name": "computer_click", "content": "Error: " + json.dumps(_large_error())}

    summary = render([message])

    for value in ("delivered_unverified", "unsafe", "TIMEOUT", "@s1:e4", "value_readback", "identity_unproven"):
        assert value in summary
    assert "long diagnostic" not in summary


def test_long_native_error_message_cannot_defeat_memory_budget():
    envelope = _large_error()
    envelope["error"]["message"] = "native diagnostic " * 10000

    summary = _truncate_for_memory(json.dumps(envelope), limit=1000)

    assert len(summary) < 8000
    assert "delivered_unverified" in summary
    assert "unsafe" in summary


@pytest.mark.parametrize("tool_name", ["computer_screenshot", "computer_clipboard_get"])
def test_responses_model_receives_screenshot_on_the_next_request(tmp_path, monkeypatch, tool_name):
    requests = []
    config = Config(models=[ModelConfig("demo", "Demo", "https://example.invalid/v1", api_key="test", supports_vision=True)])
    agent = ReverieAgent(base_url="https://example.invalid/v1", api_key="test", model="demo",
                         project_root=tmp_path, provider="openai-responses", config=config)
    agent.messages.append({"role": "user", "content": "Observe this window."})
    envelope = _screenshot(tmp_path)
    runtime = runtime_for(agent.tool_executor.context)
    if tool_name == "computer_screenshot":
        runtime.images[envelope["data"]["image_id"]] = {"kind": "window", "path": envelope["data"]["path"], "model_visible": False}
    else:
        envelope["command"] = "clipboard-get"
        envelope["data"].pop("image_id")
        envelope["data"]["type"] = "image"
    screenshot = as_result(envelope, vision=True, runtime=runtime)
    monkeypatch.setattr(agent.tool_executor, "execute", lambda *args, **kwargs: screenshot)
    monkeypatch.setattr(agent, "_check_and_compress_context", lambda **kwargs: None)
    monkeypatch.setattr(agent, "_prepare_tool_call_review", lambda calls: None)
    def respond(payload):
        requests.append(payload)
        if len(requests) == 1:
            return {"output": [{"type": "function_call", "call_id": "shot", "name": tool_name, "arguments": "{}"}]}
        return {"output": [{"type": "message", "content": [{"type": "output_text", "text": "Observed."}]}]}
    monkeypatch.setattr(agent, "_create_openai_response", respond)

    assert agent._process_non_streaming_openai_responses() == "Observed."

    assert len(requests) == 2
    images = [part for item in requests[1]["input"] for part in item.get("content", []) if part["type"] == "input_image"]
    assert len(images) == 1
    assert images[0]["image_url"].startswith("data:image/png;base64,")
    assert "base64" not in json.dumps(agent.get_history())
    payload = screenshot.data["computer_use"]["data"]
    assert runtime.images[payload.get("image_id") or payload["reverie_media_id"]]["model_visible"]


@pytest.mark.parametrize("tool_name", ["computer_screenshot", "computer_clipboard_get"])
def test_anthropic_model_receives_image_on_next_request(tmp_path, monkeypatch, tool_name):
    requests = []
    config = Config(models=[ModelConfig("demo", "Demo", "https://example.invalid/v1", api_key="test", supports_vision=True)])
    agent = ReverieAgent(base_url="https://example.invalid/v1", api_key="test", model="demo",
                         project_root=tmp_path, provider="anthropic", config=config)
    agent.messages.append({"role": "user", "content": "Observe the image."})
    envelope = _screenshot(tmp_path)
    runtime = runtime_for(agent.tool_executor.context)
    if tool_name == "computer_screenshot":
        runtime.images[envelope["data"]["image_id"]] = {"kind": "window", "path": envelope["data"]["path"], "model_visible": False}
    else:
        envelope["command"] = "clipboard-get"
        envelope["data"].pop("image_id")
        envelope["data"]["type"] = "image"
    result = as_result(envelope, vision=True, runtime=runtime)
    monkeypatch.setattr(agent.tool_executor, "execute", lambda *args, **kwargs: result)
    monkeypatch.setattr(agent, "_check_and_compress_context", lambda **kwargs: None)
    def create(**payload):
        requests.append(payload)
        if len(requests) == 1:
            return SimpleNamespace(content=[SimpleNamespace(type="tool_use", id="shot", name=tool_name, input={})], stop_reason="tool_use")
        return SimpleNamespace(content=[SimpleNamespace(type="text", text="Observed.")], stop_reason="end_turn")
    monkeypatch.setattr(agent, "_ensure_client", lambda: SimpleNamespace(messages=SimpleNamespace(create=create)))

    assert "Observed." in agent._process_non_streaming_anthropic()

    assert len(requests) == 2
    blocks = [part for message in requests[1]["messages"] if isinstance(message["content"], list) for part in message["content"]]
    results = [part for part in blocks if part.get("type") == "tool_result"]
    images = [part for result in results for part in result["content"] if part.get("type") == "image"]
    assert len(images) == 1
    assert images[0]["source"]["media_type"] == "image/png"
    assert "base64" not in json.dumps(agent.get_history())
    if tool_name == "computer_clipboard_get":
        from reverie.computer_use.images import point
        from reverie.computer_use.runtime import NativeDesktopError
        with pytest.raises(NativeDesktopError) as error:
            point(runtime, result.data["computer_use"]["data"]["reverie_media_id"], 0, 0, vision=True)
        assert error.value.envelope["error"]["code"] == "INVALID_ARGS"


@pytest.mark.parametrize("invalidator", ["evicted", "restored", "text_model"])
def test_historical_image_cannot_bypass_session_or_vision_gate(tmp_path, invalidator):
    config = Config(models=[ModelConfig("demo", "Demo", "https://example.invalid/v1", api_key="test", supports_vision=True)])
    agent = ReverieAgent(base_url="https://example.invalid/v1", api_key="test", model="demo",
                         project_root=tmp_path, provider="openai-responses", config=config)
    runtime = runtime_for(agent.tool_executor.context)
    envelope = _screenshot(tmp_path)
    image_id = envelope["data"]["image_id"]
    record = {"path": envelope["data"]["path"], "model_visible": False}
    runtime.images[image_id] = record
    result = as_result(envelope, vision=True, runtime=runtime)
    history = [{"role": "tool", "tool_call_id": "shot", "content": _tool_result_history_content(result)}]
    if invalidator == "evicted":
        runtime.images.clear()
    elif invalidator == "restored":
        agent.set_history(history)
    else:
        config.active_model.supports_vision = False

    prepared = agent._resolve_messages_for_request(history)

    assert "image_url" not in json.dumps(prepared)
    assert "base64" not in json.dumps(prepared)
    assert record["model_visible"] is False
