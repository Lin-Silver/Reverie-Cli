from __future__ import annotations

from pathlib import Path
import base64
import json
from types import SimpleNamespace

from rich.console import Console

from reverie.agent.tool_executor import ToolExecutor
from reverie.cli.commands import CommandHandler
from reverie.cli.help_catalog import normalize_help_topic
from reverie.config import ConfigManager
from reverie.harness import (
    build_harness_capability_report,
    build_harness_prompt_guidance,
    summarize_prompt_harness_history,
)
from reverie.skills_manager import SkillsManager
from reverie.tools import browser_controler as browser_controler_module
from reverie.tools.mcp_resource_tools import ListMcpResourcesTool, ReadMcpResourceTool
from reverie.tools.mode_switch import ModeSwitchTool
from reverie.tools.browser_controler import BrowserControlerTool
from reverie.tools.skill_lookup import SkillLookupTool
from reverie.tools.tool_catalog import ToolCatalogTool


class DummyTool:
    def __init__(
        self,
        name: str,
        description: str,
        parameters: dict | None = None,
        *,
        aliases: list[str] | None = None,
        search_hint: str = "",
        category: str = "general",
        tags: list[str] | None = None,
        read_only: bool = False,
        concurrency_safe: bool = False,
        destructive: bool = False,
        supported_modes: list[str] | None = None,
    ):
        self.name = name
        self.description = description
        self.parameters = parameters or {"type": "object", "properties": {}, "required": []}
        self.aliases = aliases or []
        self.search_hint = search_hint
        self.tool_category = category
        self.tool_tags = tags or []
        self.read_only = read_only
        self.concurrency_safe = concurrency_safe
        self.destructive = destructive
        self.supported_modes = supported_modes or []

    def get_schema(self) -> dict:
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": self.parameters,
            },
        }

    def get_metadata(self) -> dict:
        return {
            "name": self.name,
            "aliases": list(self.aliases),
            "search_hint": self.search_hint,
            "category": self.tool_category,
            "tags": list(self.tool_tags),
            "read_only": self.read_only,
            "concurrency_safe": self.concurrency_safe,
            "destructive": self.destructive,
            "should_defer": False,
            "always_load": False,
            "max_result_chars": 50_000,
        }

    def get_aliases(self) -> list[str]:
        return list(self.aliases)


class DummyToolExecutor:
    def __init__(self, tools: list[DummyTool]):
        self._tools = {tool.name: tool for tool in tools}

    def get_tool_schemas(self, mode: str = "reverie") -> list[dict]:
        return [tool.get_schema() for tool in self._tools.values()]

    def get_tool(self, name: str):
        if name in self._tools:
            return self._tools.get(name)
        lowered = str(name).lower()
        for tool in self._tools.values():
            if lowered == tool.name.lower() or lowered in {alias.lower() for alias in tool.get_aliases()}:
                return tool
        return None

    def get_tool_records(self, mode: str = "reverie") -> list[dict]:
        records = []
        for tool in self._tools.values():
            schema = tool.get_schema()
            function = schema["function"]
            properties = function["parameters"].get("properties", {})
            records.append(
                {
                    "name": tool.name,
                    "tool": tool,
                    "schema": schema,
                    "description": tool.description,
                    "required": list(function["parameters"].get("required", [])),
                    "properties": list(properties.keys()),
                    "property_schemas": dict(properties),
                    "metadata": tool.get_metadata(),
                    "supported_modes": list(tool.supported_modes),
                }
            )
        return records


class DummyAgent:
    def __init__(self, tools: list[DummyTool], mode: str = "reverie"):
        self.mode = mode
        self.tool_executor = DummyToolExecutor(tools)

    def update_mode(self, mode: str) -> None:
        self.mode = mode


class DummyRuntime:
    def __init__(self):
        self.resources = [
            {
                "server": "filesystem",
                "uri": "file:///workspace/README.md",
                "name": "Workspace README",
                "description": "Project overview",
                "mimeType": "text/markdown",
            }
        ]

    def list_resources(self, server_name: str = "", force_refresh: bool = False):
        if server_name:
            return [item for item in self.resources if item["server"] == server_name]
        return list(self.resources)

    def read_resource(self, server_name: str, uri: str):
        assert server_name == "filesystem"
        assert uri == "file:///workspace/README.md"
        return {
            "contents": [
                {
                    "uri": uri,
                    "mimeType": "text/markdown",
                    "text": "# Title\n\nBody",
                },
                {
                    "uri": "mcp://assets/logo",
                    "mimeType": "application/octet-stream",
                    "blob": base64.b64encode(b"hello").decode("ascii"),
                },
            ]
        }


def test_tool_catalog_search_and_inspect(tmp_path: Path) -> None:
    tools = [
        DummyTool(
            "command_exec",
            "Run audited workspace commands inside the active workspace.",
            {
                "type": "object",
                "properties": {
                    "command": {"type": "string", "description": "Command line to execute"},
                    "timeout": {"type": "integer", "description": "Timeout in seconds"},
                },
                "required": ["command"],
            },
            aliases=["shell"],
            search_hint="run builds tests git and workspace commands",
            category="workspace",
            tags=["shell", "command", "test"],
            supported_modes=["reverie", "reverie-atlas", "reverie-gamer", "reverie-ant", "spec-driven", "spec-vibe", "writer"],
        ),
        DummyTool(
            "read_mcp_resource",
            "Read a specific MCP resource by server name and URI.",
            {
                "type": "object",
                "properties": {
                    "server": {"type": "string", "description": "MCP server name"},
                    "uri": {"type": "string", "description": "Resource URI"},
                },
                "required": ["server", "uri"],
            },
            aliases=["open_mcp_resource"],
            search_hint="read one mcp resource by uri",
            category="mcp-resource",
            tags=["mcp", "resource", "read"],
            read_only=True,
            concurrency_safe=True,
            supported_modes=["reverie", "reverie-atlas", "reverie-gamer", "reverie-ant", "spec-driven", "spec-vibe", "writer"],
        ),
    ]
    agent = DummyAgent(tools)
    tool = ToolCatalogTool({"agent": agent, "project_root": tmp_path})

    search_result = tool.execute(operation="search", query="mcp resource")
    assert search_result.success is True
    assert "read_mcp_resource" in search_result.output

    inspect_result = tool.execute(operation="inspect", tool_name="command_exec")
    assert inspect_result.success is True
    assert "Required parameters: command" in inspect_result.output
    assert "timeout" in inspect_result.output
    assert "Aliases: shell" in inspect_result.output
    assert "Supported modes:" in inspect_result.output

    recommend_result = tool.execute(operation="recommend", query="read mcp docs")
    assert recommend_result.success is True
    assert "read_mcp_resource" in recommend_result.output

    inferred_recommend = tool.execute(query="read mcp docs")
    assert inferred_recommend.success is True
    assert "read_mcp_resource" in inferred_recommend.output

    inferred_inspect = tool.execute(tool_name="command_exec")
    assert inferred_inspect.success is True
    assert "Tool: command_exec" in inferred_inspect.output

    groups_result = tool.execute(operation="groups")
    assert groups_result.success is True
    assert "mcp-resource" in groups_result.output


def test_mode_switch_lists_recommends_and_switches(tmp_path: Path) -> None:
    agent = DummyAgent([], mode="reverie")
    tool = ModeSwitchTool({"agent": agent, "project_root": tmp_path})

    list_result = tool.execute(operation="list")
    assert list_result.success is True
    assert "reverie-gamer" in list_result.output

    recommend_result = tool.execute(operation="recommend", query="build a godot 3d combat prototype")
    assert recommend_result.success is True
    assert recommend_result.data["recommended_mode"] == "reverie-gamer"

    switch_result = tool.execute(mode="writer", reason="story-heavy drafting")
    assert switch_result.success is True
    assert agent.mode == "writer"


def test_mode_switch_surfaces_target_mode_tools_for_active_agent(tmp_path: Path) -> None:
    class ModeAwareAgent:
        def __init__(self) -> None:
            self.mode = "reverie"
            self.tool_executor = ToolExecutor(project_root=tmp_path)

        def update_mode(self, mode: str) -> None:
            self.mode = mode

    agent = ModeAwareAgent()
    tool = ModeSwitchTool({"agent": agent, "project_root": tmp_path})

    list_result = tool.execute(operation="list")
    assert list_result.success is True
    reverie_item = next(item for item in list_result.data["items"] if item["mode"] == "reverie")
    assert "blender_modeling_workbench" in reverie_item["primary_tools"]

    modeling_recommendation = tool.execute(query="create a Blender GLB 3D model")
    assert modeling_recommendation.success is True
    assert modeling_recommendation.data["recommended_mode"] == "reverie"

    switch_result = tool.execute(mode="reverie-gamer", reason="playable game production workflow")
    assert switch_result.success is True
    assert agent.mode == "reverie-gamer"
    assert switch_result.data["tool_surface_changed"] is True
    assert "game_design_orchestrator" in switch_result.data["visible_tools"]
    assert "reverie_engine" in switch_result.data["visible_tools"]


def test_browser_controler_is_registered_and_summarizes_html(tmp_path: Path) -> None:
    executor = ToolExecutor(project_root=tmp_path)
    tool = executor.get_tool("browser_controller")

    assert tool is not None
    assert tool.name == "browser_controler"

    summary = BrowserControlerTool._summarize_html(
        "https://example.test",
        """
        <html>
          <head><title>Example</title><meta name="description" content="Demo page"></head>
          <body>
            <h1>Welcome</h1>
            <p>Hello browser control.</p>
            <a href="/docs">Docs</a>
            <form action="/upload"><input type="file" name="image"></form>
          </body>
        </html>
        """,
        include_links=True,
    )

    rendered = BrowserControlerTool._render_page_summary(summary, max_chars=200)

    assert summary["title"] == "Example"
    assert summary["meta_description"] == "Demo page"
    assert "Hello browser control." in summary["text"]
    assert summary["links"][0]["href"] == "/docs"
    assert summary["forms"][0]["inputs"][0]["type"] == "file"
    assert "Headings:" in rendered


def test_browser_controler_diagnoses_page_assets_without_network() -> None:
    html = """
    <html>
      <head>
        <script src="/app.js"></script>
        <link rel="stylesheet" href="/app.css">
      </head>
      <body><img src="images/logo.png"></body>
    </html>
    """

    assets = BrowserControlerTool._asset_urls_from_html("https://example.test/base/index.html", html)

    assert assets == [
        {"kind": "script", "url": "https://example.test/app.js"},
        {"kind": "stylesheet", "url": "https://example.test/app.css"},
        {"kind": "image", "url": "https://example.test/base/images/logo.png"},
    ]


def test_browser_controler_exposes_window_state_actions() -> None:
    actions = BrowserControlerTool.parameters["properties"]["action"]["enum"]

    assert "active_window" in actions
    assert "list_browser_windows" in actions
    assert "activate_browser" in actions
    assert BrowserControlerTool._is_browser_process("chrome.exe")
    assert BrowserControlerTool._is_browser_process("msedge.exe")
    assert not BrowserControlerTool._is_browser_process("vmware.exe")


def test_browser_controler_exposes_structured_devtools_actions() -> None:
    parameters = BrowserControlerTool.parameters["properties"]
    actions = parameters["action"]["enum"]

    assert "open_debug_page" in actions
    assert "browser_session_start" in actions
    assert "browser_session_cleanup" in actions
    assert "devtools_targets" in actions
    assert "devtools_snapshot" in actions
    assert "devtools_screenshot" in actions
    assert "devtools_eval" in actions
    assert "devtools_console" in actions
    assert "devtools_network" in actions
    assert "devtools_click" in actions
    assert "devtools_type" in actions
    assert "devtools_upload" in actions
    assert "devtools_wait_for" in actions
    assert "devtools_accessibility_snapshot" in actions
    assert "devtools_dom_outline" in actions
    assert "devtools_find" in actions
    assert "safety_policy" in actions
    assert "browser_profile_status" in actions
    assert "browser_profile_backup" in actions
    assert "browser_profile_backups" in actions
    assert "browser_profile_restore" in actions
    assert "browser_profile_import" in actions
    assert "browser_profile_export" in actions
    assert "browser_runtime_status" in actions
    assert "port" in parameters
    assert "expression" in parameters
    assert "include_bodies" in parameters
    assert "include_request_body" in parameters
    assert "export_har" in parameters
    assert "selector" in parameters
    assert "session_id" in parameters
    assert "background" in parameters
    assert "minimized" in parameters
    assert "activate" in parameters
    assert "profile" in parameters
    assert "include_cache" in parameters
    assert "backup_id" in parameters
    assert "confirm" in parameters
    assert "import_format" in parameters


def test_browser_controler_chromium_flags_support_minimized_background_launch() -> None:
    flags = BrowserControlerTool._browser_window_flags(
        Path("chrome.exe"),
        private=False,
        new_window=True,
        minimized=True,
    )

    assert "--new-window" in flags
    assert "--start-minimized" in flags


def test_browser_controler_debug_profiles_stay_isolated(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("REVERIE_APP_ROOT", str(tmp_path / "app"))
    tool = BrowserControlerTool({"project_root": tmp_path})

    default_profile = tool._resolve_debug_profile_dir("", browser="chromium", port=45678)
    relative_profile = tool._resolve_debug_profile_dir("weather-smoke", browser="chromium", port=45679)

    assert default_profile == (tool.debug_profiles_dir / "chromium" / "port-45678").resolve()
    assert relative_profile == (tool.debug_profiles_dir / "weather-smoke").resolve()
    assert tool._is_safe_debug_profile_path(default_profile)
    assert tool._is_safe_debug_profile_path(relative_profile)
    assert not tool._is_safe_debug_profile_path(tmp_path)

    try:
        tool._resolve_debug_profile_dir(str(tmp_path / "external-profile"), browser="chromium", port=45680)
    except ValueError as exc:
        assert "absolute path" in str(exc)
    else:
        raise AssertionError("External browser profile path was not refused")


def test_browser_controler_keeps_downloads_under_embedded_browser_root(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("REVERIE_APP_ROOT", str(tmp_path / "app"))
    tool = BrowserControlerTool({"project_root": tmp_path})
    profile_dir = tool._embedded_browser_profile_dir("download-test")
    preferences_path = profile_dir / "Default" / "Preferences"
    preferences_path.parent.mkdir(parents=True)
    preferences_path.write_text(json.dumps({"theme": "dark"}), encoding="utf-8")

    download_dir = tool._prepare_embedded_profile("download-test", profile_dir)
    preferences = json.loads(preferences_path.read_text(encoding="utf-8"))

    assert download_dir == (tool.downloads_dir / "download-test").resolve()
    assert preferences["theme"] == "dark"
    assert preferences["download"]["default_directory"] == str(download_dir)
    assert preferences["download"]["prompt_for_download"] is False
    assert preferences["savefile"]["default_directory"] == str(download_dir)
    assert str(download_dir).startswith(str(tool.output_dir.resolve()))


def test_browser_session_cleanup_preserves_persistent_and_credential_profiles(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("REVERIE_APP_ROOT", str(tmp_path / "app"))
    tool = BrowserControlerTool({"project_root": tmp_path})
    disposable = tool._embedded_browser_profile_dir("session-disposable")
    credential_profile = tool._embedded_browser_profile_dir("session-credential")
    persistent = tool._embedded_browser_profile_dir("default")
    for profile_dir in (disposable, credential_profile, persistent):
        profile_dir.mkdir(parents=True)
        (profile_dir / "marker.txt").write_text("keep-or-remove", encoding="utf-8")
    credential_import = tool.imports_dir / "session-credential"
    credential_import.mkdir(parents=True)
    (credential_import / "latest-storage-state.json").write_text("{}", encoding="utf-8")
    tool._save_browser_sessions(
        {
            "disposable": {"port": 1, "profile_dir": str(disposable)},
            "credential": {"port": 1, "profile_dir": str(credential_profile)},
            "persistent": {"port": 1, "profile_dir": str(persistent)},
        }
    )

    result = tool.execute(action="browser_session_cleanup", cleanup_profiles=True)

    assert result.success is True
    assert not disposable.exists()
    assert credential_profile.exists()
    assert persistent.exists()
    assert str(disposable) in result.data["removed_profiles"]
    assert str(credential_profile) in result.data["preserved_profiles"]
    assert str(persistent) in result.data["preserved_profiles"]


def test_browser_session_termination_only_stops_verified_embedded_process(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("REVERIE_APP_ROOT", str(tmp_path / "app"))
    tool = BrowserControlerTool({"project_root": tmp_path})
    embedded = tool.runtime_dir / "ms-playwright" / "chromium-1208" / "chrome-win64" / "chrome.exe"
    embedded.parent.mkdir(parents=True)
    embedded.write_bytes(b"embedded")
    profile = tool._embedded_browser_profile_dir("session-test")
    profile.mkdir(parents=True)
    session = {"process_id": 123, "browser": str(embedded), "profile_dir": str(profile)}
    taskkill_calls = []

    monkeypatch.setattr(tool, "_process_path", lambda _pid: str(embedded))
    monkeypatch.setattr(tool, "_process_command_line", lambda _pid: f'"{embedded}" --user-data-dir="{profile}"')

    def fake_run(args, **_kwargs):
        taskkill_calls.append(args)
        return SimpleNamespace(returncode=0, stdout="stopped", stderr="")

    monkeypatch.setattr(browser_controler_module.subprocess, "run", fake_run)
    assert tool._is_browser_controler_process(123) is True
    terminated = tool._terminate_embedded_browser_session_process(session)

    assert terminated["terminated"] is True
    assert taskkill_calls == [["taskkill", "/PID", "123", "/T", "/F"]]

    external = tmp_path / "chrome.exe"
    external.write_bytes(b"real-browser")
    monkeypatch.setattr(tool, "_process_path", lambda _pid: str(external))
    assert tool._is_browser_controler_process(123) is False
    refused = tool._terminate_embedded_browser_session_process(session)

    assert refused["terminated"] is False
    assert "outside .reverie/browser/runtime" in refused["reason"]
    assert len(taskkill_calls) == 1


def test_browser_controler_resolves_only_embedded_chromium_runtime(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("REVERIE_APP_ROOT", str(tmp_path / "app"))
    tool = BrowserControlerTool({"project_root": tmp_path})
    embedded = tool.runtime_dir / "ms-playwright" / "chromium-1208" / "chrome-win64" / "chrome.exe"
    embedded.parent.mkdir(parents=True)
    embedded.write_bytes(b"embedded")
    external = tmp_path / "system-browser.exe"
    external.write_bytes(b"external")

    assert tool._resolve_browser_executable(browser="edge", browser_path="") == embedded.resolve()
    assert tool._resolve_browser_executable(browser="edge", browser_path=str(external)) is None
    assert tool._resolve_browser_executable(browser="edge", browser_path=str(embedded)) == embedded.resolve()


def test_browser_controler_profile_backup_and_status(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("REVERIE_APP_ROOT", str(tmp_path / "app"))

    tool = BrowserControlerTool({"project_root": tmp_path / "workspace"})
    profile_dir = tool._embedded_browser_profile_dir("default")
    (profile_dir / "Default").mkdir(parents=True)
    (profile_dir / "Default" / "Cookies").write_text("cookie-data", encoding="utf-8")
    (profile_dir / "Local State").write_text("{}", encoding="utf-8")
    backup = tool.execute(action="browser_profile_backup", profile="default", include_cache=False)

    assert backup.success is True
    backup_dir = Path(backup.data["backup_dir"])
    assert (backup_dir / "Default" / "Cookies").read_text(encoding="utf-8") == "cookie-data"
    assert (backup_dir / "browser-profile-backup.json").exists()
    assert backup.data["profile"] == "default"

    status = tool.execute(action="browser_profile_status", profile="default")
    backups = tool.execute(action="browser_profile_backups", profile="default")

    assert status.success is True
    assert str(tmp_path / "app" / ".reverie" / "browser") in status.output
    assert "Latest backup" in status.output
    assert backups.success is True
    assert backup.data["backup_id"] in backups.output


def test_browser_profile_import_accepts_storage_state(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("REVERIE_APP_ROOT", str(tmp_path / "app"))
    project_root = tmp_path / "project"
    project_root.mkdir()
    state_path = project_root / "auth-state.json"
    state_path.write_text(
        json.dumps(
            {
                "cookies": [
                    {
                        "name": "sid",
                        "value": "123",
                        "domain": ".example.test",
                        "path": "/",
                        "expires": -1,
                        "httpOnly": True,
                        "secure": True,
                        "sameSite": "Lax",
                    }
                ],
                "origins": [{"origin": "https://example.test", "localStorage": [{"name": "token", "value": "abc"}]}],
            }
        ),
        encoding="utf-8",
    )

    tool = BrowserControlerTool({"project_root": project_root})
    result = tool.execute(action="browser_profile_import", file_path="auth-state.json", profile="default")

    assert result.success is True
    latest = tool._latest_storage_state_path("default")
    assert latest.exists()
    imported = json.loads(latest.read_text(encoding="utf-8"))
    assert imported["cookies"][0]["name"] == "sid"
    assert imported["origins"][0]["localStorage"][0]["name"] == "token"


def test_browser_command_manages_embedded_profile_backups(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("REVERIE_APP_ROOT", str(tmp_path / "app"))
    project_root = tmp_path / "project"
    project_root.mkdir()
    monkeypatch.chdir(project_root)
    tool = BrowserControlerTool({"project_root": project_root})
    profile_dir = tool._embedded_browser_profile_dir("default")
    (profile_dir / "Default").mkdir(parents=True)
    (profile_dir / "Default" / "Preferences").write_text("{}", encoding="utf-8")

    console = Console(record=True, force_terminal=False, width=120)
    handler = CommandHandler(console, {"project_root": project_root})

    assert handler.handle("/browser backup default") is True
    assert handler.handle("/browser backups default") is True
    rendered = console.export_text()

    assert "Backed up embedded browser profile default" in rendered
    assert "Embedded browser profile backups for default" in rendered


def test_browser_controler_authorizes_only_recorded_isolated_cdp_ports(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("REVERIE_APP_ROOT", str(tmp_path / "app"))
    tool = BrowserControlerTool({"project_root": tmp_path})
    profile_dir = tool._resolve_debug_profile_dir("", browser="chromium", port=45678)
    embedded = tool.runtime_dir / "ms-playwright" / "chromium-1208" / "chrome-win64" / "chrome.exe"
    embedded.parent.mkdir(parents=True)
    embedded.write_bytes(b"embedded")

    assert tool._is_authorized_cdp_port(45678) is False
    assert tool._user_data_dir_from_command_line(f'chrome.exe --user-data-dir="{profile_dir}"') == profile_dir

    tool._record_browser_session(
        session_id="safe",
        port=45678,
        url="about:blank",
        profile="default",
        profile_dir=profile_dir,
        browser=str(embedded),
        process_id=123,
        background=True,
        minimized=True,
    )
    monkeypatch.setattr(tool, "_process_path", lambda _pid: str(embedded))
    monkeypatch.setattr(tool, "_process_command_line", lambda _pid: f'"{embedded}" --user-data-dir="{profile_dir}"')

    assert tool._is_authorized_cdp_port(45678) is True

    tool._save_browser_sessions(
        {
            "unsafe": {
                "session_id": "unsafe",
                "port": 45679,
                "profile_dir": str(profile_dir),
                "browser": str(tmp_path / "system-chrome.exe"),
            }
        }
    )
    assert tool._is_authorized_cdp_port(45679) is False


def test_browser_controler_prefers_real_page_devtools_targets() -> None:
    about_blank = {"type": "page", "url": "about:blank", "title": "", "webSocketDebuggerUrl": "ws://example/blank"}
    real_page = {"type": "page", "url": "http://127.0.0.1:3000/", "title": "App", "webSocketDebuggerUrl": "ws://example/app"}

    assert BrowserControlerTool._cdp_target_score(real_page) > BrowserControlerTool._cdp_target_score(about_blank)


def test_browser_controler_renders_devtools_console_and_network_events() -> None:
    console_events = [
        {
            "method": "Runtime.consoleAPICalled",
            "params": {
                "type": "log",
                "args": [
                    {"type": "string", "value": "probe"},
                    {"type": "number", "value": 42},
                ],
            },
        },
        {
            "method": "Runtime.exceptionThrown",
            "params": {"exceptionDetails": {"text": "boom", "lineNumber": 1, "columnNumber": 2}},
        },
    ]
    rendered_console = BrowserControlerTool._render_cdp_console_events(console_events)

    assert "console.log: probe 42" in rendered_console[0]
    assert "exception: boom at 1:2" in rendered_console[1]

    network_summary = BrowserControlerTool._summarize_cdp_network_events(
        [
            {
                "method": "Network.requestWillBeSent",
                "params": {
                    "requestId": "1",
                    "type": "XHR",
                    "request": {"url": "https://example.test/api", "method": "POST"},
                },
            },
            {
                "method": "Network.responseReceived",
                "params": {
                    "requestId": "1",
                    "type": "XHR",
                    "response": {"url": "https://example.test/api", "status": 201, "mimeType": "application/json"},
                },
            },
            {"method": "Network.loadingFinished", "params": {"requestId": "1"}},
        ]
    )
    rendered_network = BrowserControlerTool._render_cdp_network_summary(
        network_summary,
        target={"title": "Example", "url": "https://example.test"},
    )

    assert network_summary["request_count"] == 1
    assert network_summary["response_count"] == 1
    assert network_summary["responses"][0]["finished"] is True
    assert "201 POST https://example.test/api" in rendered_network


def test_browser_controler_filters_network_and_builds_har() -> None:
    network_summary = BrowserControlerTool._summarize_cdp_network_events(
        [
            {
                "method": "Network.requestWillBeSent",
                "params": {
                    "requestId": "1",
                    "type": "XHR",
                    "request": {
                        "url": "https://example.test/api/save",
                        "method": "POST",
                        "postData": "{\"ok\":true}",
                    },
                },
            },
            {
                "method": "Network.responseReceived",
                "params": {
                    "requestId": "1",
                    "type": "XHR",
                    "response": {"url": "https://example.test/api/save", "status": 500, "mimeType": "application/json"},
                },
            },
            {
                "method": "Network.requestWillBeSent",
                "params": {
                    "requestId": "2",
                    "type": "Document",
                    "request": {"url": "https://example.test/", "method": "GET"},
                },
            },
            {
                "method": "Network.responseReceived",
                "params": {
                    "requestId": "2",
                    "type": "Document",
                    "response": {"url": "https://example.test/", "status": 200, "mimeType": "text/html"},
                },
            },
            {"method": "Network.webSocketCreated", "params": {"requestId": "ws", "url": "wss://example.test/socket"}},
            {
                "method": "Network.webSocketFrameReceived",
                "params": {"requestId": "ws", "response": {"opcode": 1, "payloadData": "hello"}},
            },
        ],
        include_request_body=True,
        include_websockets=True,
        filter_url="/api/",
        filter_method="POST",
        filter_status="5xx",
    )
    har = BrowserControlerTool._build_simple_har(network_summary)

    assert network_summary["filtered_response_count"] == 1
    assert network_summary["responses"][0]["post_data_preview"] == "{\"ok\":true}"
    assert network_summary["websockets"][0]["frames"][0]["payload_preview"] == "hello"
    assert har["log"]["entries"][0]["request"]["method"] == "POST"


def test_browser_controler_renders_dom_outline() -> None:
    lines = BrowserControlerTool._render_dom_outline(
        {
            "title": "App",
            "url": "https://example.test",
            "headings": [{"selector": "h1", "text": "Dashboard"}],
            "controls": [{"selector": "button#save", "text": "Save", "role": "button"}],
        },
        max_events=5,
    )

    assert "DOM outline for App" in lines[0]
    assert any("Dashboard" in line for line in lines)
    assert any("Save" in line for line in lines)


def test_skill_lookup_lists_and_inspects_discovered_skills(tmp_path: Path) -> None:
    app_root = tmp_path / "app"
    project_root = tmp_path / "project"
    project_root.mkdir(parents=True, exist_ok=True)
    skill_dir = app_root / ".reverie" / "skills" / "openai-docs"
    skill_dir.mkdir(parents=True, exist_ok=True)
    (skill_dir / "SKILL.md").write_text(
        "---\n"
        "name: openai-docs\n"
        "description: Use official OpenAI docs for product and API guidance.\n"
        "---\n\n"
        "Always prefer official OpenAI documentation.\n"
        "Read only the specific reference files needed for the task.\n"
        "Keep context narrow, prefer official sources, and avoid loading unrelated references into the turn.\n"
        "When a workflow mentions models, APIs, migration guidance, or parameter changes, verify the exact details in the docs before coding.\n",
        encoding="utf-8",
    )

    manager = SkillsManager(project_root=project_root, app_root=app_root)
    manager.scan()
    tool = SkillLookupTool({"skills_manager": manager, "project_root": project_root})

    list_result = tool.execute(operation="list")
    assert list_result.success is True
    assert "openai-docs" in list_result.output

    inspect_result = tool.execute(operation="inspect", skill_name="openai-docs", max_body_chars=40)
    assert inspect_result.success is True
    assert "Skill: openai-docs" in inspect_result.output
    assert inspect_result.data["truncated"] is True


def test_skills_manager_discovers_builtin_browser_controler_skill(tmp_path: Path) -> None:
    app_root = tmp_path / "app"
    project_root = tmp_path / "project"
    project_root.mkdir(parents=True, exist_ok=True)

    manager = SkillsManager(project_root=project_root, app_root=app_root)
    record = manager.get_record("browser-controler", force_refresh=True)

    assert record is not None
    assert record.root.scope == "builtin"
    assert "browser_controler" in record.body
    assert "list_browser_windows" in record.body
    assert "activate_browser" in record.body
    assert "open_debug_page" in record.body
    assert "devtools_eval" in record.body
    assert "devtools_console" in record.body
    assert "devtools_network" in record.body
    assert "devtools_screenshot" in record.body
    assert "devtools_dom_outline" in record.body
    assert "devtools_click" in record.body
    assert "browser_session_start" in record.body
    assert "safety_policy" in record.body
    assert "embedded open-source Chromium runtime" in record.body
    assert ".reverie/browser" in record.body
    assert "/browser import" in record.body
    assert "storage-state.json" in record.body
    assert "must not read browser databases" in record.body
    assert "Do not control the user's existing logged-in browser" in record.body
    assert "external DevTools ports" in record.body
    assert "real Chrome/Edge/Firefox/Brave profile" in record.body
    assert "background=true" in record.body
    assert "minimized=true" in record.body
    assert "diagnose_page" in record.body
    assert "check_endpoint" in record.body


def test_browser_controler_manifest_mentions_embedded_browser_contract() -> None:
    repo_root = Path(__file__).resolve().parents[1]
    manifest = json.loads((repo_root / "reverie" / "agent" / "tool_manifest.json").read_text(encoding="utf-8"))
    browser_record = manifest["tools"]["browser_controler"]

    assert "browser_runtime_status" in browser_record["parameters"]["action"]
    assert "browser_profile_status/backup/backups/restore/import/export" in browser_record["parameters"]["action"]
    assert "external unrecorded ports are refused" in browser_record["parameters"]["port"]
    assert "embedded open-source Chromium runtime" in browser_record["purpose"]
    assert ".reverie/browser" in browser_record["purpose"]
    assert "profile" in browser_record["parameters"]
    assert "include_cache" in browser_record["parameters"]
    assert "backup_id" in browser_record["parameters"]
    assert "confirm" in browser_record["parameters"]
    assert "import_format" in browser_record["parameters"]
    assert any("browser_runtime_status" in example for example in browser_record["examples"])
    assert any("browser_profile_import" in example for example in browser_record["examples"])
    assert any("browser_profile_backup" in example for example in browser_record["examples"])


def test_github_action_schedules_latest_windows_exe_build() -> None:
    repo_root = Path(__file__).resolve().parents[2]
    workflow = (repo_root / ".github" / "workflows" / "build-windows-exe.yml").read_text(encoding="utf-8")

    assert "schedule:" in workflow
    assert "17 18 * * *" in workflow
    assert "actions/upload-artifact@v4" in workflow
    assert "gh release upload latest" in workflow
    assert "dist/reverie.exe" in workflow
    assert "Build Python exe" in workflow
    assert "python -m playwright install chromium" in workflow
    assert "python -m playwright install chromium --no-shell" in workflow
    assert "PLAYWRIGHT_BROWSERS_PATH" in workflow
    assert "embedded Chromium Browser Controler runtime" in workflow
    assert "reverie.exe: primary Windows CLI executable" in workflow
    assert "Reverie CLI for Windows (Python full build)" in workflow
    assert "Blender runtime plugin" in workflow
    assert "Official Blender runtime plugin" not in workflow
    assert "reverie-python.exe" not in workflow
    assert "reverie-rust-preview.exe" not in workflow


def test_local_build_scripts_bundle_embedded_chromium() -> None:
    repo_root = Path(__file__).resolve().parents[1]
    build_bat = (repo_root / "build.bat").read_text(encoding="utf-8", errors="replace")
    build_sh = (repo_root / "build.sh").read_text(encoding="utf-8")
    spec = (repo_root / "reverie.spec").read_text(encoding="utf-8")
    setup = (repo_root / "setup.py").read_text(encoding="utf-8")

    for script in (build_bat, build_sh):
        assert "playwright install chromium --no-shell" in script
        assert "PLAYWRIGHT_BROWSERS_PATH" in script
        assert "browser/ms-playwright" in script.replace("\\", "/")
    assert 'add_tree_if_exists(browser_src / "ms-playwright", "reverie_resources/browser/ms-playwright")' in spec
    assert '"playwright>=1.56.0"' in setup


def test_mcp_resource_tools_list_and_read(tmp_path: Path) -> None:
    runtime = DummyRuntime()
    context = {
        "mcp_runtime": runtime,
        "project_root": tmp_path,
        "project_data_dir": tmp_path / ".reverie-cache",
    }

    list_tool = ListMcpResourcesTool(context)
    list_result = list_tool.execute(server="filesystem")
    assert list_result.success is True
    assert "Workspace README" in list_result.output

    read_tool = ReadMcpResourceTool(context)
    read_result = read_tool.execute(
        server="filesystem",
        uri="file:///workspace/README.md",
        save_binary=True,
    )
    assert read_result.success is True
    assert "# Title" in read_result.output

    saved_to = read_result.data["contents"][1]["saved_to"]
    assert Path(saved_to).exists()


def test_tool_executor_alias_resolution_and_large_output_budget(tmp_path: Path) -> None:
    large_text = "A" * 60_500
    large_file = tmp_path / "large.txt"
    large_file.write_text(large_text, encoding="utf-8")

    executor = ToolExecutor(project_root=tmp_path)

    shell_tool = executor.get_tool("shell")
    assert shell_tool is not None
    assert shell_tool.name == "command_exec"

    result = executor.execute("file_ops", {"operation": "read", "path": "large.txt"})
    assert result.success is True
    assert result.data["tool_result_budget_applied"] is True
    assert Path(result.data["output_saved_to"]).exists()
    assert "Full output saved to:" in result.output

    create_result = executor.execute(
        "create_file",
        {"path": "alias-content.txt", "text": "hello via alias", "overwrite": "true"},
    )
    assert create_result.success is True
    assert (tmp_path / "alias-content.txt").read_text(encoding="utf-8") == "hello via alias"


def test_tool_catalog_recommendation_adapts_to_mode_profile(tmp_path: Path) -> None:
    tools = [
        DummyTool(
            "command_exec",
            "Run audited workspace commands inside the active workspace.",
            {
                "type": "object",
                "properties": {"command": {"type": "string"}},
                "required": ["command"],
            },
            aliases=["shell"],
            search_hint="run builds tests git and workspace commands",
            category="workspace",
            tags=["shell", "command", "test"],
            supported_modes=["reverie", "reverie-gamer"],
        ),
        DummyTool(
            "game_design_orchestrator",
            "Create structured game blueprints, expand gameplay systems, and plan vertical slices.",
            {
                "type": "object",
                "properties": {"action": {"type": "string"}},
                "required": ["action"],
            },
            aliases=["game_blueprint"],
            search_hint="create game blueprints and vertical slice plans",
            category="game-design",
            tags=["game", "blueprint", "design", "vertical-slice"],
            supported_modes=["reverie", "reverie-gamer"],
        ),
    ]
    agent = DummyAgent(tools, mode="reverie-gamer")
    tool = ToolCatalogTool({"agent": agent, "project_root": tmp_path})

    recommend_result = tool.execute(
        operation="recommend",
        query="plan game blueprint and vertical slice",
    )
    assert recommend_result.success is True
    assert recommend_result.data["items"][0]["name"] == "game_design_orchestrator"


def test_command_handler_tools_views_are_mode_aware(tmp_path: Path) -> None:
    tools = [
        DummyTool(
            "command_exec",
            "Run audited workspace commands inside the active workspace.",
            {
                "type": "object",
                "properties": {"command": {"type": "string", "description": "Command line to execute"}},
                "required": ["command"],
            },
            aliases=["shell"],
            search_hint="run builds tests git and workspace commands",
            category="workspace",
            tags=["shell", "command", "test"],
            supported_modes=["reverie", "reverie-gamer", "writer"],
        ),
        DummyTool(
            "game_design_orchestrator",
            "Create structured game blueprints, expand gameplay systems, and plan vertical slices.",
            {
                "type": "object",
                "properties": {"action": {"type": "string", "description": "Blueprint action"}},
                "required": ["action"],
            },
            aliases=["game_blueprint"],
            search_hint="create game blueprints and vertical slice plans",
            category="game-design",
            tags=["game", "blueprint", "design", "vertical-slice"],
            supported_modes=["reverie-gamer"],
        ),
        DummyTool(
            "novel_context_manager",
            "Manage novel content, memory, and context for long-form story writing.",
            {
                "type": "object",
                "properties": {"action": {"type": "string", "description": "Writer action"}},
                "required": ["action"],
            },
            aliases=["writer_memory"],
            search_hint="manage novel memory characters and chapter context",
            category="writer",
            tags=["novel", "story", "memory"],
            supported_modes=["writer"],
        ),
    ]
    agent = DummyAgent(tools, mode="writer")

    overview_console = Console(record=True, force_terminal=False, width=120)
    overview_handler = CommandHandler(overview_console, {"agent": agent, "project_root": tmp_path})
    assert overview_handler.handle("/tools --mode reverie-gamer") is True
    overview_text = overview_console.export_text()
    assert "Available Reverie CLI tools:" in overview_text
    assert "game_design_orchestrator" in overview_text
    assert "All tools:" in overview_text
    assert "Total:" in overview_text
    assert "Mode Quick Picks" not in overview_text

    search_console = Console(record=True, force_terminal=False, width=120)
    search_handler = CommandHandler(search_console, {"agent": agent, "project_root": tmp_path})
    assert search_handler.handle("/tools search vertical slice --mode reverie-gamer") is True
    search_text = search_console.export_text()
    assert "Tool Search" in search_text
    assert "game_design_orchestrator" in search_text

    inspect_console = Console(record=True, force_terminal=False, width=120)
    inspect_handler = CommandHandler(inspect_console, {"agent": agent, "project_root": tmp_path})
    assert inspect_handler.handle("/tools inspect shell") is True
    inspect_text = inspect_console.export_text()
    assert "Tool Inspection" in inspect_text
    assert "command_exec" in inspect_text
    assert "Supported Modes" in inspect_text

    all_console = Console(record=True, force_terminal=False, width=120)
    all_handler = CommandHandler(all_console, {"agent": agent, "project_root": tmp_path})
    assert all_handler.handle("/tools all") is True
    all_text = all_console.export_text()
    assert "All Tools" in all_text
    assert "game_design_orchestrator" in all_text
    assert "Parameters" in all_text

    details_console = Console(record=True, force_terminal=False, width=120)
    details_handler = CommandHandler(details_console, {"agent": agent, "project_root": tmp_path})
    assert details_handler.handle("/tools details --mode reverie") is True
    details_text = details_console.export_text()
    assert "Tool Details" in details_text
    assert "Required" in details_text


def test_setting_status_alias_renders_tool_output_section(tmp_path: Path, monkeypatch) -> None:
    app_root = tmp_path / "app"
    project_root = tmp_path / "project"
    project_root.mkdir(parents=True, exist_ok=True)

    monkeypatch.setattr("reverie.config.get_app_root", lambda: app_root)
    monkeypatch.setattr("reverie.config.get_launcher_root", lambda: app_root)

    config_manager = ConfigManager(project_root)
    console = Console(record=True, force_terminal=False, width=120)
    handler = CommandHandler(console, {"config_manager": config_manager, "project_root": project_root})

    assert handler.handle("/settings status") is True

    output = console.export_text()
    assert "Tool Output" in output
    assert "Thinking" in output
    assert "Compact" in output
    assert "Full" in output


def test_setting_tool_output_updates_config_and_applies_display_preferences(tmp_path: Path, monkeypatch) -> None:
    app_root = tmp_path / "app"
    project_root = tmp_path / "project"
    project_root.mkdir(parents=True, exist_ok=True)

    monkeypatch.setattr("reverie.config.get_app_root", lambda: app_root)
    monkeypatch.setattr("reverie.config.get_launcher_root", lambda: app_root)

    config_manager = ConfigManager(project_root)
    applied: list[str] = []
    console = Console(record=True, force_terminal=False, width=120)
    handler = CommandHandler(
        console,
        {
            "config_manager": config_manager,
            "project_root": project_root,
            "apply_display_preferences": lambda config: applied.append(config.tool_output_style),
        },
    )

    assert handler.handle("/setting tool-output condensed") is True

    reloaded = config_manager.load()
    assert reloaded.tool_output_style == "condensed"
    assert applied == ["condensed"]
    assert "Tool output style set to condensed." in console.export_text()


def test_setting_tool_output_rejects_invalid_values(tmp_path: Path, monkeypatch) -> None:
    app_root = tmp_path / "app"
    project_root = tmp_path / "project"
    project_root.mkdir(parents=True, exist_ok=True)

    monkeypatch.setattr("reverie.config.get_app_root", lambda: app_root)
    monkeypatch.setattr("reverie.config.get_launcher_root", lambda: app_root)

    config_manager = ConfigManager(project_root)
    original = config_manager.load()
    assert original.tool_output_style == "compact"

    console = Console(record=True, force_terminal=False, width=120)
    handler = CommandHandler(console, {"config_manager": config_manager, "project_root": project_root})

    assert handler.handle("/setting tool-output verbose") is True

    reloaded = config_manager.load()
    assert reloaded.tool_output_style == "compact"
    assert "Invalid tool output style" in console.export_text()


def test_setting_ui_drains_stale_keyboard_input_before_starting() -> None:
    class FakeMsvcrt:
        def __init__(self) -> None:
            self.keys = [b"\r", b"\x1b"]

        def kbhit(self) -> bool:
            return bool(self.keys)

        def getch(self) -> bytes:
            return self.keys.pop(0)

    fake_msvcrt = FakeMsvcrt()
    console = Console(record=True, force_terminal=False, width=120)
    handler = CommandHandler(console, {"project_root": Path.cwd()})

    assert handler._drain_msvcrt_keyboard_buffer(fake_msvcrt) == 2
    assert fake_msvcrt.keys == []


def test_help_topic_normalizes_settings_alias() -> None:
    assert normalize_help_topic("settings") == "setting"
    assert normalize_help_topic("harness") == "doctor"


def test_doctor_command_renders_harness_audit(tmp_path: Path, monkeypatch) -> None:
    app_root = tmp_path / "app"
    project_root = tmp_path / "project"
    project_root.mkdir(parents=True, exist_ok=True)
    (project_root / "artifacts").mkdir(parents=True, exist_ok=True)
    (project_root / "artifacts" / "Tasks.md").write_text("[/] Audit harness\n[x] Add report\n", encoding="utf-8")

    monkeypatch.setattr("reverie.config.get_app_root", lambda: app_root)
    monkeypatch.setattr("reverie.config.get_launcher_root", lambda: app_root)

    config_manager = ConfigManager(project_root)
    audit_dir = config_manager.project_data_dir / "security"
    audit_dir.mkdir(parents=True, exist_ok=True)
    (audit_dir / "command_audit.jsonl").write_text(
        '{"timestamp":"2026-04-13T10:00:00+00:00","event":"command_result","command":"pytest","normalized_command":"pytest -q","exit_code":0}\n',
        encoding="utf-8",
    )

    console = Console(record=True, force_terminal=False, width=120)
    handler = CommandHandler(console, {"config_manager": config_manager, "project_root": project_root})

    assert handler.handle("/doctor") is True

    output = console.export_text()
    assert "Harness Doctor" in output
    assert "Harness Layers" in output
    assert "Verification Posture" in output
    assert "Closure Gate" in output
    assert "Recovery Playbooks" in output
    assert "Recent Command Surface" in output
    assert "Recovery" in output


def test_doctor_command_json_alias_outputs_report(tmp_path: Path, monkeypatch) -> None:
    app_root = tmp_path / "app"
    project_root = tmp_path / "project"
    project_root.mkdir(parents=True, exist_ok=True)

    monkeypatch.setattr("reverie.config.get_app_root", lambda: app_root)
    monkeypatch.setattr("reverie.config.get_launcher_root", lambda: app_root)

    config_manager = ConfigManager(project_root)
    console = Console(record=True, force_terminal=False, width=120)
    handler = CommandHandler(console, {"config_manager": config_manager, "project_root": project_root})

    assert handler.handle("/harness json") is True

    output = console.export_text()
    assert '"overall_score"' in output
    assert '"workspace_root"' in output


def test_doctor_history_outputs_recent_runs(tmp_path: Path, monkeypatch) -> None:
    app_root = tmp_path / "app"
    project_root = tmp_path / "project"
    project_root.mkdir(parents=True, exist_ok=True)

    monkeypatch.setattr("reverie.config.get_app_root", lambda: app_root)
    monkeypatch.setattr("reverie.config.get_launcher_root", lambda: app_root)

    config_manager = ConfigManager(project_root)
    history_dir = config_manager.project_data_dir / "harness"
    history_dir.mkdir(parents=True, exist_ok=True)
    (history_dir / "prompt_runs.jsonl").write_text(
        "\n".join(
            [
                '{"timestamp":"2026-04-15T10:00:00","mode":"reverie","success":true,"duration_seconds":12.0,"overall_score":82,"verification_commands":1,"verification_categories":["test"],"task_active":"Audit harness","auto_followup_count":0}',
                '{"timestamp":"2026-04-15T10:05:00","mode":"reverie","success":false,"duration_seconds":7.0,"overall_score":76,"verification_commands":0,"verification_categories":[],"task_active":"Tighten recovery","auto_followup_count":1}',
            ]
        ) + "\n",
        encoding="utf-8",
    )

    console = Console(record=True, force_terminal=False, width=120)
    handler = CommandHandler(console, {"config_manager": config_manager, "project_root": project_root})

    assert handler.handle("/doctor history") is True

    output = console.export_text()
    assert "Recent Harness Runs" in output
    assert "Tighten recovery" in output
    assert "Audit harness" in output


def test_harness_capability_report_uses_goal_to_recovery_layers(tmp_path: Path, monkeypatch) -> None:
    app_root = tmp_path / "app"
    project_root = tmp_path / "project"
    project_root.mkdir(parents=True, exist_ok=True)
    artifacts_dir = project_root / "artifacts"
    artifacts_dir.mkdir(parents=True, exist_ok=True)
    (artifacts_dir / "Tasks.md").write_text("[/] Audit harness\n[x] Add report\n", encoding="utf-8")

    monkeypatch.setattr("reverie.config.get_app_root", lambda: app_root)
    monkeypatch.setattr("reverie.config.get_launcher_root", lambda: app_root)

    config_manager = ConfigManager(project_root)
    audit_dir = config_manager.project_data_dir / "security"
    audit_dir.mkdir(parents=True, exist_ok=True)
    (audit_dir / "command_audit.jsonl").write_text(
        '{"timestamp":"2026-04-13T10:00:00+00:00","event":"command_result","command":"pytest","normalized_command":"pytest -q","exit_code":0}\n',
        encoding="utf-8",
    )

    report = build_harness_capability_report(
        project_root,
        project_data_dir=config_manager.project_data_dir,
        mode="reverie",
        operation_history=object(),
        rollback_manager=object(),
    )

    assert set(report["categories"].keys()) == {
        "goals",
        "context",
        "tools",
        "execution",
        "memory",
        "evaluation",
        "recovery",
    }
    assert report["task_snapshot"]["active"] == "Audit harness"
    assert report["runtime"]["automatic_checkpoints"] is True
    assert report["artifacts"]["verification"]["explicit_commands"] == 1
    assert report["summary"]["verification_commands"] == 1
    assert report["completion_gate"]["status"] == "continue"
    assert report["recovery_playbooks"]


def test_harness_prompt_guidance_mentions_task_ledger_and_recovery(tmp_path: Path, monkeypatch) -> None:
    app_root = tmp_path / "app"
    project_root = tmp_path / "project"
    project_root.mkdir(parents=True, exist_ok=True)
    artifacts_dir = project_root / "artifacts"
    artifacts_dir.mkdir(parents=True, exist_ok=True)
    (artifacts_dir / "Tasks.md").write_text("[/] Audit harness\n[ ] Tighten recovery loop\n", encoding="utf-8")

    monkeypatch.setattr("reverie.config.get_app_root", lambda: app_root)
    monkeypatch.setattr("reverie.config.get_launcher_root", lambda: app_root)

    config_manager = ConfigManager(project_root)
    guidance = build_harness_prompt_guidance(
        project_root,
        project_data_dir=config_manager.project_data_dir,
        mode="reverie",
        operation_history=object(),
        rollback_manager=object(),
    )

    assert "Harness Runtime" in guidance
    assert "prompt engineering clarifies the ask" in guidance
    assert "Audit harness" in guidance
    assert "automatic checkpoints before user turns and tool calls" in guidance
    assert "Verification trail:" in guidance
    assert "Recent harness runs:" in guidance
    assert "Closure gate:" in guidance
    assert "Recovery playbooks:" in guidance


def test_harness_report_surfaces_schema_mismatch_playbook(tmp_path: Path, monkeypatch) -> None:
    app_root = tmp_path / "app"
    project_root = tmp_path / "project"
    project_root.mkdir(parents=True, exist_ok=True)

    monkeypatch.setattr("reverie.config.get_app_root", lambda: app_root)
    monkeypatch.setattr("reverie.config.get_launcher_root", lambda: app_root)

    config_manager = ConfigManager(project_root)
    operation_history = SimpleNamespace(
        operations=[
            SimpleNamespace(
                operation_type=SimpleNamespace(value="tool_call"),
                tool_call=SimpleNamespace(
                    tool_name="task_manager",
                    arguments={},
                    result="",
                    success=False,
                    error="Missing required parameter: operation",
                ),
                file_operation=None,
                timestamp="2026-04-15T10:00:00",
            )
        ]
    )

    report = build_harness_capability_report(
        project_root,
        project_data_dir=config_manager.project_data_dir,
        mode="reverie",
        operation_history=operation_history,
    )

    playbook_ids = {item["id"] for item in report["recovery_playbooks"]}
    assert "tool_schema_mismatch" in playbook_ids
    assert report["completion_gate"]["status"] == "blocked"


def test_summarize_prompt_harness_history_tracks_trend(tmp_path: Path, monkeypatch) -> None:
    app_root = tmp_path / "app"
    project_root = tmp_path / "project"
    project_root.mkdir(parents=True, exist_ok=True)

    monkeypatch.setattr("reverie.config.get_app_root", lambda: app_root)
    monkeypatch.setattr("reverie.config.get_launcher_root", lambda: app_root)

    config_manager = ConfigManager(project_root)
    history_dir = config_manager.project_data_dir / "harness"
    history_dir.mkdir(parents=True, exist_ok=True)
    (history_dir / "prompt_runs.jsonl").write_text(
        "\n".join(
            [
                '{"timestamp":"2026-04-15T10:00:00","mode":"reverie","success":true,"duration_seconds":12.0,"overall_score":72,"verification_commands":0,"verification_categories":[],"task_active":"Draft audit","auto_followup_count":0}',
                '{"timestamp":"2026-04-15T10:05:00","mode":"reverie","success":true,"duration_seconds":10.0,"overall_score":83,"verification_commands":2,"verification_categories":["test","lint"],"task_active":"Close gaps","auto_followup_count":0}',
            ]
        ) + "\n",
        encoding="utf-8",
    )

    summary = summarize_prompt_harness_history(config_manager.project_data_dir, limit=8)

    assert summary["total_runs"] == 2
    assert summary["recent_success_rate"] == 100
    assert summary["recent_verification_coverage"] == 50
    assert summary["score_trend"] == "improving"


def test_setting_thinking_output_updates_config_and_applies_display_preferences(tmp_path: Path, monkeypatch) -> None:
    app_root = tmp_path / "app"
    project_root = tmp_path / "project"
    project_root.mkdir(parents=True, exist_ok=True)

    monkeypatch.setattr("reverie.config.get_app_root", lambda: app_root)
    monkeypatch.setattr("reverie.config.get_launcher_root", lambda: app_root)

    config_manager = ConfigManager(project_root)
    applied: list[str] = []
    console = Console(record=True, force_terminal=False, width=120)
    handler = CommandHandler(
        console,
        {
            "config_manager": config_manager,
            "project_root": project_root,
            "apply_display_preferences": lambda config: applied.append(config.thinking_output_style),
        },
    )

    assert handler.handle("/setting thinking hidden") is True

    reloaded = config_manager.load()
    assert reloaded.thinking_output_style == "hidden"
    assert applied == ["hidden"]
    assert "Thinking output style set to hidden." in console.export_text()
