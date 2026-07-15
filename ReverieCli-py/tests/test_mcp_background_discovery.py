from __future__ import annotations

from pathlib import Path
import threading
import time
from types import SimpleNamespace

from reverie.agent.system_prompt import build_system_prompt
from reverie.agent.tool_executor import ToolExecutor
from reverie.cli import interface as interface_module
from reverie.cli.interface import ReverieInterface
from reverie.mcp import BaseMCPClient, MCPConfigManager, MCPRuntime


class ControlledMCPClient(BaseMCPClient):
    def __init__(
        self,
        server_name: str,
        server_config: dict,
        *,
        result: dict,
        started: threading.Event | None = None,
        release: threading.Event | None = None,
    ) -> None:
        super().__init__(server_name, server_config)
        self.result = result
        self.started = started
        self.release = release

    def discover(self, force: bool = False, timeout_ms: int | None = None) -> dict:
        if self.started is not None:
            self.started.set()
        if self.release is not None:
            assert self.release.wait(timeout=2.0), "test did not release MCP discovery"
        self._catalog_dirty = False
        self._discovery_cache = {**self.result, "fetched_at": time.time()}
        return dict(self._discovery_cache)


def _runtime(tmp_path: Path, monkeypatch, results: dict[str, dict], **controls) -> MCPRuntime:
    app_root = tmp_path / "app"
    manager = MCPConfigManager(app_root)
    manager.save(
        {
            "mcp": {"enabled": True, "discovery_timeout_ms": 1000},
            "mcpServers": {
                name: {
                    "enabled": True,
                    "type": "http",
                    "httpUrl": f"http://127.0.0.1/{name}",
                }
                for name in results
            },
        }
    )
    runtime = MCPRuntime(manager, project_root=tmp_path)

    def create_client(server_name: str, server_config: dict) -> ControlledMCPClient:
        return ControlledMCPClient(
            server_name,
            server_config,
            result=results[server_name],
            started=controls.get("started"),
            release=controls.get("release"),
        )

    monkeypatch.setattr(runtime, "_create_client_locked", create_client)
    return runtime


def _join_discovery(runtime: MCPRuntime) -> None:
    thread = runtime._background_discovery_thread
    assert thread is not None
    thread.join(timeout=3.0)
    assert not thread.is_alive()


def test_automatic_discovery_is_non_blocking_and_status_uses_pending_snapshot(tmp_path: Path, monkeypatch) -> None:
    started = threading.Event()
    release = threading.Event()
    runtime = _runtime(
        tmp_path,
        monkeypatch,
        {
            "slow": {
                "tools": [{"name": "lookup", "description": "SLOW_TOOL", "inputSchema": {"type": "object"}}],
                "resources": [],
                "prompts": [],
                "error": "",
            }
        },
        started=started,
        release=release,
    )

    before = time.perf_counter()
    assert runtime.get_tool_definitions() == []
    assert time.perf_counter() - before < 0.1
    assert started.wait(timeout=1.0)

    before = time.perf_counter()
    rows = runtime.list_server_status()
    assert time.perf_counter() - before < 0.1
    assert rows[0]["health"] == "pending"
    assert runtime.describe_for_prompt() == ""

    release.set()
    _join_discovery(runtime)
    assert runtime.get_tool_definitions()[0]["description"] == "SLOW_TOOL"
    assert runtime.list_server_status()[0]["tools"] == 1


def test_failed_server_tools_and_prompt_content_are_not_injected(tmp_path: Path, monkeypatch) -> None:
    runtime = _runtime(
        tmp_path,
        monkeypatch,
        {
            "good": {
                "tools": [{"name": "lookup", "description": "HEALTHY_MCP_MARKER", "inputSchema": {"type": "object"}}],
                "resources": [{"uri": "mcp://good/readme"}],
                "prompts": [{"name": "good_prompt"}],
                "error": "",
            },
            "bad": {
                "tools": [{"name": "unsafe", "description": "FAILED_MCP_MARKER", "inputSchema": {"type": "object"}}],
                "resources": [],
                "prompts": [{"name": "FAILED_PROMPT_MARKER"}],
                "error": "offline",
            },
        },
    )

    assert runtime.start_background_discovery()
    _join_discovery(runtime)

    definitions = runtime.get_tool_definitions()
    serialized = repr(definitions)
    assert "HEALTHY_MCP_MARKER" in serialized
    assert "FAILED_MCP_MARKER" not in serialized
    assert all(item["server_name"] == "good" for item in definitions)

    guidance = runtime.describe_for_prompt()
    prompt = build_system_prompt(additional_rules=guidance)
    assert "good" in guidance
    assert "bad" not in guidance
    assert "FAILED_MCP_MARKER" not in prompt
    assert "FAILED_PROMPT_MARKER" not in prompt

    executor = ToolExecutor(tmp_path)
    executor.update_context("mcp_runtime", runtime, sync_dynamic=False)
    schemas = executor.get_tool_schemas(mode="reverie")
    schema_text = repr(schemas)
    assert "HEALTHY_MCP_MARKER" in schema_text
    assert "FAILED_MCP_MARKER" not in schema_text
    schema_names = {item["function"]["name"] for item in schemas}
    assert "list_mcp_resources" in schema_names
    assert "read_mcp_resource" in schema_names


def test_rediscovery_removes_stale_tools_until_health_is_known(tmp_path: Path, monkeypatch) -> None:
    runtime = _runtime(
        tmp_path,
        monkeypatch,
        {
            "server": {
                "tools": [{"name": "lookup", "description": "PREVIOUSLY_HEALTHY", "inputSchema": {"type": "object"}}],
                "resources": [],
                "prompts": [],
                "error": "",
            }
        },
    )
    completions: list[dict] = []
    runtime.set_discovery_listener(lambda health: completions.append(health))
    assert runtime.start_background_discovery()
    _join_discovery(runtime)
    assert runtime.get_tool_definitions()

    client = runtime._clients["server"]
    client.result = {
        "tools": [{"name": "lookup", "description": "STALE_DESCRIPTION", "inputSchema": {"type": "object"}}],
        "resources": [],
        "prompts": [],
        "error": "now offline",
    }
    assert runtime.start_background_discovery(force_refresh=True)
    assert runtime.get_tool_definitions() == []
    assert runtime.describe_for_prompt() == ""
    _join_discovery(runtime)

    assert runtime.get_tool_definitions() == []
    assert runtime.get_health_snapshot()["server"]["state"] == "failed"
    assert len(completions) == 2


def test_all_failed_servers_remove_mcp_prompt_and_resource_tools(tmp_path: Path, monkeypatch) -> None:
    runtime = _runtime(
        tmp_path,
        monkeypatch,
        {
            "bad": {
                "tools": [{"name": "unsafe", "description": "FAILED_ONLY_MARKER", "inputSchema": {"type": "object"}}],
                "resources": [],
                "prompts": [{"name": "FAILED_ONLY_PROMPT"}],
                "error": "connection refused",
            }
        },
    )

    assert runtime.start_background_discovery()
    _join_discovery(runtime)
    assert runtime.get_tool_definitions() == []
    assert runtime.describe_for_prompt() == ""
    assert "## MCP Integration" not in build_system_prompt(additional_rules=runtime.describe_for_prompt())

    executor = ToolExecutor(tmp_path)
    executor.update_context("mcp_runtime", runtime, sync_dynamic=False)
    schema_names = {item["function"]["name"] for item in executor.get_tool_schemas(mode="reverie")}
    assert "list_mcp_resources" not in schema_names
    assert "read_mcp_resource" not in schema_names


def test_first_paint_rules_skip_expensive_harness_enrichment(monkeypatch, tmp_path: Path) -> None:
    def unexpected_harness_call(*args, **kwargs):
        raise AssertionError("Harness enrichment must not run on the first-paint Agent path")

    monkeypatch.setattr(interface_module, "build_harness_prompt_guidance", unexpected_harness_call)
    skills = SimpleNamespace(
        set_active_mode=lambda mode: None,
        describe_for_prompt=lambda force_refresh=False: "## Skills\n- cached",
    )
    runtime_plugins = SimpleNamespace(describe_for_prompt=lambda mode: "## Plugins\n- cached")
    mcp_runtime = SimpleNamespace(describe_for_prompt=lambda: "")
    interface = SimpleNamespace(
        rules_manager=SimpleNamespace(get_rules_text=lambda: ""),
        skills_manager=skills,
        runtime_plugin_manager=runtime_plugins,
        mcp_runtime=mcp_runtime,
        memory_indexer=None,
        lsp_manager=None,
        project_root=tmp_path,
    )

    rules = ReverieInterface._build_additional_rules_with_tti(
        interface,
        SimpleNamespace(mode="writer"),
        include_harness_guidance=False,
    )
    assert "## Skills" in rules
    assert "## Plugins" in rules


def test_startup_discovery_warms_skills_for_active_mode() -> None:
    scanned_modes: list[str] = []

    class Skills:
        active_mode = "reverie"

        def set_active_mode(self, mode: str) -> None:
            self.active_mode = mode

        def scan(self):
            scanned_modes.append(self.active_mode)
            return SimpleNamespace(summary_label=lambda: "1 skill")

    interface = SimpleNamespace(
        _startup_discovery_ready=False,
        skills_manager=Skills(),
        runtime_plugin_manager=SimpleNamespace(scan=lambda: SimpleNamespace(summary_label=lambda: "1 plugin")),
        _load_active_runtime_config=lambda: SimpleNamespace(mode="reverie"),
        _show_activity_event=lambda *args, **kwargs: None,
    )

    ReverieInterface._warm_startup_discovery(interface, config=SimpleNamespace(mode="writer"))
    assert scanned_modes
    assert set(scanned_modes) == {"writer"}
