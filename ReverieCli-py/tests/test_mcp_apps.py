"""The P3 privacy, discovery and resource boundaries (no live credentials)."""
import json
from types import SimpleNamespace

import pytest

from reverie.mcp import BaseMCPClient, MCPConfigManager, MCPRuntime, format_mcp_call_result
from reverie.tools.mcp_dynamic import MCPDynamicTool


SECRET = "PRIVATE_META_MUST_NEVER_REACH_MODEL"
URI = "ui://fixture/app.html"


class AppClient(BaseMCPClient):
    def request(self, method, params=None, **kwargs):
        if method == "initialize":
            self.capabilities = params["capabilities"]
            return {"protocolVersion": "2025-06-18"}
        if method == "tools/list":
            return {"tools": [
                {"name": "show", "_meta": {"ui": {"resourceUri": URI}}},
                {"name": "hidden", "description": SECRET, "_meta": {"ui": {"visibility": ["app"]}}},
                {"name": "model-only", "_meta": {"ui": {"visibility": ["model"]}}},
                {"name": "alias", "_meta": {"openai/outputTemplate": URI}},
                {"name": "invalid", "_meta": {"ui": {"visibility": "app"}}},
            ]}
        if method == "tools/call":
            return {"content": [{"type": "text", "text": "Useful text"}], "structuredContent": {"value": 7}, "_meta": {"secret": SECRET}}
        if method == "resources/read":
            return {"contents": [{"uri": URI, "mimeType": "text/html;profile=mcp-app", "text": "<h1>App</h1>", "_meta": {"ui": {"csp": {"connectDomains": []}}}}]}
        return {}


def app_runtime(tmp_path, monkeypatch):
    manager = MCPConfigManager(tmp_path / "app-root")
    manager.save({"mcpServers": {"fixture": {"type": "http", "httpUrl": "http://127.0.0.1:9999/mcp"}}})
    runtime = MCPRuntime(manager, project_root=tmp_path)
    monkeypatch.setattr(runtime, "_create_client_locked", lambda name, cfg: AppClient(name, cfg))
    runtime.get_tool_definitions(force_refresh=True)
    return runtime


@pytest.mark.parametrize("result", [
    {"_meta": {"secret": SECRET}},
    {"content": [], "_meta": {"secret": SECRET}},
    {"isError": True, "_meta": {"secret": SECRET}},
    {"content": [{"type": "text", "text": "Visible", "_meta": {"secret": SECRET}}], "_meta": {"secret": SECRET}},
])
def test_private_meta_never_enters_formatter_or_model_payload(result):
    output, metadata, _ = format_mcp_call_result(result)
    assert output
    assert SECRET not in json.dumps([output, metadata])


def test_catalog_keeps_ui_metadata_but_app_only_is_not_discoverable(tmp_path, monkeypatch):
    runtime = app_runtime(tmp_path, monkeypatch)
    definitions = runtime.get_tool_definitions()
    assert SECRET not in json.dumps(definitions)
    assert {x["tool_name"] for x in definitions} == {"show", "model-only", "alias"}
    show = next(x for x in definitions if x["tool_name"] == "show")
    assert show["_meta"]["ui"]["resourceUri"] == URI
    assert {x["tool_name"] for x in runtime.get_app_tool_definitions()} == {"show", "hidden", "alias"}
    alias = next(x for x in definitions if x["tool_name"] == "alias")
    assert alias["ui"]["resourceUri"] == URI
    client = runtime._clients["fixture"]
    assert client.capabilities["extensions"]["io.modelcontextprotocol/ui"]["mimeTypes"] == ["text/html;profile=mcp-app"]


def test_app_only_requires_live_server_binding_and_model_visibility_is_not_a_grant(tmp_path, monkeypatch):
    runtime = app_runtime(tmp_path, monkeypatch)
    with pytest.raises(Exception, match="visibility"):
        runtime.call_tool("fixture", "hidden", {})
    binding = runtime.app_identity("fixture")
    response = runtime.call_tool("fixture", "hidden", {}, app_binding=binding)
    assert SECRET not in json.dumps(response["data"])
    assert response["result"]["_meta"]["secret"] == SECRET
    with pytest.raises(Exception, match="visibility"):
        runtime.call_tool("fixture", "model-only", {}, app_binding=binding)
    runtime.close()
    with pytest.raises(Exception, match="connection|expired|discovery"):
        runtime.call_tool("fixture", "hidden", {}, app_binding=binding)


def test_missing_ui_does_not_lose_text_or_leak_meta():
    raw = {"content": [{"type": "text", "text": "Text still works"}], "_meta": {"secret": SECRET}}
    output, data, _ = format_mcp_call_result(raw)
    runtime = SimpleNamespace(call_tool=lambda *args: {"output": output, "data": data, "result": raw})
    tool = MCPDynamicTool({"mcp_runtime": runtime}, {"name": "fixture", "server_name": "server", "tool_name": "show", "ui": {"resourceUri": URI}})
    result = tool.execute()
    assert result.success and "Text still works" in result.output
    assert SECRET not in json.dumps(result.__dict__, default=str)


def test_resource_identity_and_private_payload_are_outside_served_directory(tmp_path, monkeypatch):
    from reverie.views import ViewIdentity, ViewStore
    runtime = app_runtime(tmp_path, monkeypatch)
    binding = runtime.app_identity("fixture")
    resource = runtime.read_ui_resource("fixture", URI, binding)
    assert resource["source"]["resource_uri"] == URI
    assert resource["source"]["connection_generation"] == binding["connection_generation"]
    assert resource["source"]["cache_key"]
    store = ViewStore(tmp_path / "views")
    raw = runtime.call_tool("fixture", "show", {})["result"]
    manifest = store.register_mcp_app(resource=resource, identity=ViewIdentity("session", "turn", "call"), title="Fixture", summary="Useful text", arguments={}, result=raw, callable_tools=["mcp_fixture_show"])
    app = store.read_mcp_app("session", manifest.view_id, 1)
    assert app["toolResult"]["_meta"]["secret"] == SECRET
    served = store.view_directory("session", manifest.view_id, 1)
    assert store.resolve_entry("session", manifest.view_id, 1)[0] == served / "index.html"
    assert all(SECRET not in p.read_text(encoding="utf-8") for p in served.iterdir())
    assert SECRET not in json.dumps(manifest.model_reference())
    store.fork_session("session", "fork", [(manifest.view_id, 1)])
    assert store.read_mcp_app("fork", manifest.view_id, 1) == app


@pytest.mark.parametrize("change", [
    {"uri": "file:///etc/passwd"},
    {"mimeType": "text/html"},
    {"mimeType": "text/html+skybridge"},
    {"text": "x" * (2 * 1024 * 1024 + 1)},
    {"_meta": {"ui": {"csp": {"connectDomains": ["https://evil.example"]}}}},
    {"_meta": {"ui": {"csp": {"resourceDomains": ["https://cdn.example"]}}}},
    {"_meta": {"ui": {"csp": {"frameDomains": ["https://evil.example"]}}}},
    {"_meta": {"ui": {"permissions": {"camera": {}}}}},
    {"_meta": {"ui": {"csp": "unsafe"}}},
])
def test_bad_resources_fail_closed(tmp_path, monkeypatch, change):
    runtime = app_runtime(tmp_path, monkeypatch)
    client = runtime._clients["fixture"]
    original = client.read_resource
    def read(uri):
        result = original(uri)
        result["contents"][0].update(change)
        return result
    monkeypatch.setattr(client, "read_resource", read)
    with pytest.raises(ValueError):
        runtime.read_ui_resource("fixture", URI, runtime.app_identity("fixture"))


def test_reconnect_changes_cache_and_refuses_old_binding(tmp_path, monkeypatch):
    runtime = app_runtime(tmp_path, monkeypatch)
    binding = runtime.app_identity("fixture")
    first = runtime.read_ui_resource("fixture", URI, binding)
    client = runtime._clients["fixture"]
    client._initialized = False
    client.initialize()
    with pytest.raises(Exception, match="connection|expired"):
        runtime.read_ui_resource("fixture", URI, binding)
    second = runtime.read_ui_resource("fixture", URI, runtime.app_identity("fixture"))
    assert first["source"]["cache_key"] != second["source"]["cache_key"]


def test_model_schemas_search_and_guessed_calls_do_not_reveal_app_only(tmp_path, monkeypatch):
    from reverie.agent.tool_executor import ToolExecutor
    runtime = app_runtime(tmp_path, monkeypatch)
    executor = ToolExecutor(project_root=tmp_path)
    executor.update_context("mcp_runtime", runtime)
    assert SECRET not in json.dumps(executor.get_tool_schemas())
    assert SECRET not in json.dumps(executor.get_tool_records(), default=str)
    assert "mcp_fixture_hidden" not in executor.list_tools()
    result = executor.execute("mcp_fixture_hidden", {})
    assert not result.success and "visibility" in result.error


def test_real_executor_app_callback_preserves_private_result_only_on_ui_channel(tmp_path, monkeypatch):
    from test_riu_call_view_tool import _make_bridge
    from reverie.views import ViewIdentity
    runtime = app_runtime(tmp_path, monkeypatch)
    harness = _make_bridge(tmp_path)
    executor = harness.bridge.interface.agent.tool_executor
    executor.update_context("mcp_runtime", runtime)
    resource = runtime.read_ui_resource("fixture", URI, runtime.app_identity("fixture"))
    resource["source"]["tool_bindings"] = {"hidden": "mcp_fixture_hidden"}
    manifest = harness.store.register_mcp_app(resource=resource, identity=ViewIdentity("s-main", "t", "c"),
        title="App", summary="Useful text", arguments={}, result={"content": []}, callable_tools=["mcp_fixture_hidden"])
    approvals = []
    monkeypatch.setattr(harness.bridge, "_request_tool_approval", lambda *args: approvals.append(args) or {"decision": "once"})
    harness.bridge.interface.agent.mode = "writer"
    blocked = harness.bridge.dispatch({"id": 0, "action": "callViewTool", "payload": {"viewId": manifest.view_id, "revision": 1, "toolName": "hidden", "callId": "mode-denied", "arguments": {}}})
    assert blocked["status"] == "error" and "current mode" in blocked["error"] and not approvals
    harness.bridge.interface.agent.mode = "reverie"
    response = harness.bridge.dispatch({"id": 1, "action": "callViewTool", "payload": {"viewId": manifest.view_id, "revision": 1, "toolName": "hidden", "callId": "app-call", "arguments": {}}})
    assert response["status"] == "success" and len(approvals) == 1
    assert response["toolResult"]["_meta"]["secret"] == SECRET
    assert SECRET not in json.dumps(response["data"])
    assert SECRET not in json.dumps(harness.recorder.snapshot())
    assert executor.context.get("mcp_app_binding") is None
    again = harness.bridge.dispatch({"id": 2, "action": "callViewTool", "payload": {"viewId": manifest.view_id, "revision": 1, "toolName": "hidden", "callId": "app-call", "arguments": {}}})
    assert again["duplicate"] and len(approvals) == 1


def test_cache_key_covers_server_generation_uri_bytes_and_policy():
    from reverie.mcp_apps import validate_ui_resource
    first = {"contents": [{"uri": URI, "mimeType": "text/html;profile=mcp-app", "text": "<p>1</p>"}]}
    binding = {"server_name": "a", "server_id": "a", "connection_generation": "1"}
    keys = {validate_ui_resource(first, URI, binding)["source"]["cache_key"]}
    keys.add(validate_ui_resource(first, URI, {**binding, "server_id": "b"})["source"]["cache_key"])
    keys.add(validate_ui_resource(first, URI, {**binding, "connection_generation": "2"})["source"]["cache_key"])
    first["contents"][0]["text"] = "<p>2</p>"
    keys.add(validate_ui_resource(first, URI, binding)["source"]["cache_key"])
    first["contents"][0]["_meta"] = {"ui": {"prefersBorder": True}}
    keys.add(validate_ui_resource(first, URI, binding)["source"]["cache_key"])
    assert len(keys) == 5


def test_dead_stdio_connection_cannot_restart_an_app_write(tmp_path):
    import sys
    from pathlib import Path
    manager = MCPConfigManager(tmp_path / "app-root")
    fixture = Path(__file__).parent / "fixtures/riu_p3/server.py"
    manager.save({"mcpServers": {"fixture": {"command": sys.executable, "args": [str(fixture), "--state", str(tmp_path / "effects")]}}})
    runtime = MCPRuntime(manager, project_root=tmp_path)
    try:
        runtime.get_tool_definitions(force_refresh=True, timeout_ms=5000)
        binding = runtime.app_identity("fixture")
        process = runtime._clients["fixture"]._process
        process.kill(); process.wait(timeout=5)
        with pytest.raises(Exception, match="connection expired"):
            runtime.call_tool("fixture", "increment", {}, app_binding=binding)
        assert runtime._clients["fixture"]._process is process
        assert not (tmp_path / "effects/effects.json").exists()
    finally:
        runtime.close()
