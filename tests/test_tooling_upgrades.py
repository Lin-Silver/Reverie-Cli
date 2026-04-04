from __future__ import annotations

from pathlib import Path
import base64

from rich.console import Console

from reverie.agent.tool_executor import ToolExecutor
from reverie.cli.commands import CommandHandler
from reverie.cli.help_catalog import normalize_help_topic
from reverie.config import ConfigManager
from reverie.skills_manager import SkillsManager
from reverie.tools.mcp_resource_tools import ListMcpResourcesTool, ReadMcpResourceTool
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

    groups_result = tool.execute(operation="groups")
    assert groups_result.success is True
    assert "mcp-resource" in groups_result.output


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
            supported_modes=["reverie-gamer"],
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
    assert "Mode Quick Picks" in overview_text
    assert "game_design_orchestrator" in overview_text
    assert "Tool Browser Shortcuts" in overview_text

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


def test_help_topic_normalizes_settings_alias() -> None:
    assert normalize_help_topic("settings") == "setting"


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
