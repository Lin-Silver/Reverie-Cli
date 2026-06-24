import json
from urllib.parse import parse_qs

import pytest

from reverie.agent.agent import ReverieAgent, decode_stream_event
from reverie.config import Config, EXTERNAL_MODEL_SOURCES
from reverie.provider_smoke import BUILTIN_PROVIDER_NAMES
from reverie.webgemini import (
    _build_stream_generate_request,
    build_webgemini_runtime_model_data,
    extract_webgemini_response_text,
    get_webgemini_model_catalog,
    messages_to_webgemini_prompt,
    normalize_webgemini_config,
    parse_webgemini_tool_calls,
)


def _fake_stream_generate_raw(text: str) -> str:
    inner = [None] * 5
    inner[4] = [[None, [text + (" " * 220)]]]
    line = json.dumps([["wrb.fr", None, json.dumps(inner)]])
    return ")]}'\n\n" + line + "\n"


def test_webgemini_catalog_contains_all_web_modes() -> None:
    ids = {item["id"] for item in get_webgemini_model_catalog()}

    assert {
        "gemini-3.5-flash",
        "gemini-3.5-flash-thinking",
        "gemini-3.5-flash-thinking-lite",
        "gemini-3.1-pro",
        "gemini-auto",
        "gemini-flash-lite",
    } <= ids
    assert "webgemini" in EXTERNAL_MODEL_SOURCES
    assert "webgemini" in BUILTIN_PROVIDER_NAMES


def test_webgemini_runtime_model_data_needs_no_api_key() -> None:
    runtime = build_webgemini_runtime_model_data(
        {"selected_model_id": "gemini-auto", "timeout": 30}
    )

    assert runtime is not None
    assert runtime["model"] == "gemini-auto"
    assert runtime["provider"] == "webgemini"
    assert runtime["api_key"] == ""
    assert runtime["base_url"] == "https://gemini.google.com"


def test_config_active_model_resolves_webgemini() -> None:
    config = Config(
        active_model_source="webgemini",
        webgemini=normalize_webgemini_config({"selected_model_id": "gemini-flash-lite"}),
    )

    active = config.active_model

    assert active is not None
    assert active.model == "gemini-flash-lite"
    assert active.model_display_name == "Gemini Flash Lite"
    assert active.provider == "webgemini"


def test_webgemini_prompt_includes_tools_as_tool_call_contract() -> None:
    prompt = messages_to_webgemini_prompt(
        [
            {"role": "system", "content": "Be brief."},
            {"role": "user", "content": "Create a file."},
        ],
        tools=[
            {
                "type": "function",
                "function": {
                    "name": "create_file",
                    "description": "Create a file",
                    "parameters": {"type": "object"},
                },
            }
        ],
    )

    assert "[System instruction]: Be brief." in prompt
    assert "```tool_call" in prompt
    assert '"name": "create_file"' in prompt
    assert "Create a file." in prompt


def test_webgemini_tool_call_blocks_parse_to_openai_shape() -> None:
    text, tool_calls = parse_webgemini_tool_calls(
        'Done.\n```tool_call\n{"name":"create_file","arguments":{"path":"note.txt","content":"hi"}}\n```'
    )

    assert text == "Done."
    assert tool_calls[0]["type"] == "function"
    assert tool_calls[0]["function"]["name"] == "create_file"
    assert json.loads(tool_calls[0]["function"]["arguments"]) == {
        "path": "note.txt",
        "content": "hi",
    }


def test_webgemini_stream_generate_text_parser_extracts_final_text() -> None:
    raw = _fake_stream_generate_raw("Hello WebGemini")

    assert extract_webgemini_response_text(raw) == "Hello WebGemini"


def test_webgemini_parser_accepts_short_text_payload() -> None:
    inner = [None] * 5
    inner[4] = [[None, ["OK"]]]
    line = json.dumps([["wrb.fr", None, json.dumps(inner)]])

    assert extract_webgemini_response_text(")]}'\n" + line + "\n") == "OK"


def test_webgemini_stream_generate_payload_matches_reference_shape() -> None:
    url, headers, body = _build_stream_generate_request(
        "hello",
        2,
        0,
        normalize_webgemini_config({"gemini_bl": "boq_assistant-bard-web-server_test"}),
    )
    params = parse_qs(body)
    outer = json.loads(params["f.req"][0])
    inner = json.loads(outer[1])

    assert "assistant.lamda.BardFrontendService/StreamGenerate" in url
    assert headers["Origin"] == "https://gemini.google.com"
    assert len(inner) == 102
    assert inner[0][0] == "hello"
    assert inner[17] == [[0]]
    assert inner[79] == 2


def test_webgemini_streaming_empty_response_falls_back_to_full_response(tmp_path, monkeypatch) -> None:
    def fake_deltas(**kwargs):
        if False:
            yield ""

    def fake_generate(**kwargs):
        return "OK", []

    monkeypatch.setattr("reverie.agent.agent.iter_webgemini_text_deltas", fake_deltas)
    monkeypatch.setattr("reverie.agent.agent.generate_webgemini_message", fake_generate)

    config = Config(
        active_model_source="webgemini",
        webgemini=normalize_webgemini_config({"selected_model_id": "gemini-3.5-flash-thinking"}),
    )
    agent = ReverieAgent(
        base_url="https://gemini.google.com",
        api_key="",
        model="gemini-3.5-flash-thinking",
        model_display_name="Gemini 3.5 Flash Thinking",
        provider="webgemini",
        project_root=tmp_path,
        config=config,
    )
    agent.get_visible_tool_schemas = lambda: []
    agent.messages.append({"role": "user", "content": "hello"})

    chunks = [
        chunk
        for chunk in agent._process_streaming_webgemini(session_id="test")
        if decode_stream_event(chunk) is None
    ]

    assert "".join(chunks) == "OK"
    assert agent.messages[-1]["content"] == "OK"


def test_webgemini_tool_branch_empty_response_raises(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr("reverie.agent.agent.generate_webgemini_message", lambda **kwargs: ("", []))

    config = Config(
        active_model_source="webgemini",
        webgemini=normalize_webgemini_config({"selected_model_id": "gemini-3.5-flash-thinking"}),
    )
    agent = ReverieAgent(
        base_url="https://gemini.google.com",
        api_key="",
        model="gemini-3.5-flash-thinking",
        model_display_name="Gemini 3.5 Flash Thinking",
        provider="webgemini",
        project_root=tmp_path,
        config=config,
    )
    agent.get_visible_tool_schemas = lambda: [
        {"type": "function", "function": {"name": "create_file", "parameters": {"type": "object"}}}
    ]
    agent.messages.append({"role": "user", "content": "hello"})

    with pytest.raises(ValueError, match="WebGemini returned an empty response"):
        list(agent._process_streaming_webgemini(session_id="test"))
