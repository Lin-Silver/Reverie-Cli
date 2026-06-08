import json

from reverie.config import Config, EXTERNAL_MODEL_SOURCES
from reverie.provider_smoke import BUILTIN_PROVIDER_NAMES
from reverie.webgemini import (
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
