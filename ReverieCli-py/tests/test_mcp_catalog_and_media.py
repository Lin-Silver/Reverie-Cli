import base64
from types import SimpleNamespace

from reverie.mcp import BaseMCPClient, format_mcp_call_result
from reverie.agent.agent import ReverieAgent, _tool_result_content, _build_anthropic_tool_result_block
from reverie.tools.base import ToolResult
from reverie.tools.mcp_dynamic import MCPDynamicTool


class PagedClient(BaseMCPClient):
    def __init__(self, repeated=False):
        super().__init__("fixture", {"type": "http", "httpUrl": "http://127.0.0.1"})
        self.calls = []
        self.repeated = repeated

    def request(self, method, params=None, **kwargs):
        self.calls.append((method, params))
        if method.endswith("/list"):
            key = method.split("/")[0]
            index = 2 if params.get("cursor") else 1
            return {key: [{"name": f"{key}-{index}"}], "nextCursor": "page-2" if index == 1 or self.repeated else None}
        return {}


def test_all_three_catalogs_follow_cursor_and_cache_complete_result():
    client = PagedClient()
    catalog = client.discover(timeout_ms=1000)
    assert catalog["error"] == ""
    for key in ("tools", "resources", "prompts"):
        assert [item["name"] for item in catalog[key]] == [f"{key}-1", f"{key}-2"]
        assert (f"{key}/list", {"cursor": "page-2"}) in client.calls
    count = len(client.calls)
    assert client.discover() == catalog
    assert len(client.calls) == count


def test_repeated_cursor_reports_failure_without_looping_forever():
    client = PagedClient(repeated=True)
    assert "repeated cursor" in client.discover(timeout_ms=1000)["error"]
    assert len(client.calls) == 8


def test_mixed_result_keeps_text_images_audio_resources_and_structured_data():
    data = base64.b64encode(b"fixture-media").decode()
    original = {"content": [
        {"type": "text", "text": "Measured result"},
        {"type": "image", "mimeType": "image/png", "data": data},
        {"type": "audio", "mimeType": "audio/wav", "data": data},
        {"type": "resource", "resource": {"uri": "fixture://document", "text": "Embedded text"}},
    ], "structuredContent": {"count": 2}}
    output, metadata, error = format_mcp_call_result(original)
    assert not error and data not in output
    assert "Embedded text" in output and "fixture://document" in output
    assert metadata["raw_result"] == original
    result = ToolResult.ok(output, data=metadata)
    parts = _tool_result_content(result)
    assert {part["type"] for part in parts} == {"text", "image_url", "input_audio"}
    anthropic = _build_anthropic_tool_result_block("call-1", result)
    assert any(part["type"] == "image" for part in anthropic["content"])
    assert any("does not accept audio" in part.get("text", "") for part in anthropic["content"])
    agent = ReverieAgent.__new__(ReverieAgent)
    agent.provider, agent.project_root = "openai-chat", "."
    converted = agent._resolve_messages_for_request([{"role": "tool", "tool_call_id": "call-1", "content": parts}])
    assert converted[0]["role"] == "tool" and isinstance(converted[0]["content"], str)
    assert converted[1]["role"] == "user" and converted[1]["content"][1]["type"] == "image_url"


def test_binary_payload_and_user_only_image_are_not_dumped_into_model_text():
    original = {"content": [
        {"type": "image", "mimeType": "image/png", "data": "invalid base64"},
        {"type": "image", "mimeType": "image/png", "data": "YQ==", "annotations": {"audience": ["user"]}},
    ]}
    output, metadata, _ = format_mcp_call_result(original)
    assert "invalid base64" not in output and "YQ==" not in output
    assert all(part["type"] == "text" for part in metadata["message_content"])


def test_mcp_error_keeps_typed_metadata_and_error_status():
    output, metadata, _ = format_mcp_call_result({"isError": True, "content": [{"type": "text", "text": "Failed"}]})
    runtime = SimpleNamespace(call_tool=lambda *args: {"success": False, "output": output, "data": metadata})
    result = MCPDynamicTool({"mcp_runtime": runtime}, {"name": "fixture", "server_name": "server", "tool_name": "tool"}).execute()
    assert not result.success and result.data == metadata
