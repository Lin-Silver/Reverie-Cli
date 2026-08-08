import json
from pathlib import Path

from rich.console import Console

from reverie.__main__ import DIRECT_COMMANDS
from reverie.cli.commands import CommandHandler
from reverie.cli.display import DisplayComponents
from reverie.cli.help_catalog import HELP_TOPICS
from reverie.session.manager import SessionManager
from reverie.tools.base import ToolResult
from reverie.tools.context_management import ContextManagementTool
from reverie.tools.task_manager import TaskManagerTool


def test_task_manager_accepts_short_action_and_name_updates(tmp_path: Path) -> None:
    tool = TaskManagerTool({"project_root": tmp_path})

    added = tool.execute(action="add", tasks=["Analyze architecture", {"content": "Fix live output"}])
    assert added.success
    assert "[ ] Analyze architecture" in added.output
    assert "[ ] Fix live output" in added.output

    updated = tool.execute(action="update", name="Fix live output", status="done")
    assert updated.success
    assert "[x] Fix live output" in updated.output

    listed = tool.execute(action="list")
    assert listed.success
    assert "[x] Fix live output" in listed.output


def test_live_tool_panel_summarizes_large_arguments() -> None:
    console = Console(record=True, width=100)
    display = DisplayComponents(console)
    display.build_live_tool_panel(
        [
            {
                "tool_name": "create_file",
                "message": "Executing create_file...",
                "arguments": {
                    "path": "src/client.rs",
                    "content": "pub fn connect() {}\n" * 200,
                },
                "stdout": "",
                "stderr": "",
            }
        ]
    )
    console.print(
        display.build_live_tool_panel(
            [
                {
                    "tool_name": "create_file",
                    "message": "Executing create_file...",
                    "arguments": {
                        "path": "src/client.rs",
                        "content": "pub fn connect() {}\n" * 200,
                    },
                    "stdout": "",
                    "stderr": "",
                }
            ]
        )
    )
    exported = console.export_text()
    assert "content=<" in exported
    assert "pub fn connect" not in exported


def test_session_manager_archives_full_transcript_before_shorter_update(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    manager = SessionManager(tmp_path / ".reverie", project_root=workspace)
    session = manager.create_session("Compaction Test")
    original_messages = [
        {"role": "user", "content": f"message {idx}"}
        for idx in range(8)
    ]
    manager.update_messages(original_messages)

    manager.update_messages([{"role": "system", "content": "compressed"}, original_messages[-1]])

    archive_paths = session.metadata.get("full_transcript_archives", [])
    assert archive_paths
    archive_path = Path(archive_paths[-1]["path"])
    assert archive_path.exists()
    archived = json.loads(archive_path.read_text(encoding="utf-8"))
    assert archived["original_message_count"] == 8
    assert archived["replacement_message_count"] == 2
    assert archived["messages"] == original_messages


def test_compact_command_forwards_optional_focus_and_full_runtime_context(monkeypatch, tmp_path: Path) -> None:
    captured = {}

    class Agent:
        system_prompt = "system"
        messages = [{"role": "user", "content": "active request"}]

    session_manager = object()
    workspace_stats_manager = object()

    def fake_execute(self, **kwargs):
        captured["context"] = self.context
        captured["kwargs"] = kwargs
        return ToolResult.ok("Context compressed: 1,000 -> 400 tokens")

    monkeypatch.setattr(ContextManagementTool, "execute", fake_execute)
    console = Console(record=True, width=120)
    handler = CommandHandler(
        console,
        {
            "agent": Agent(),
            "project_root": tmp_path,
            "session_manager": session_manager,
            "workspace_stats_manager": workspace_stats_manager,
        },
    )

    assert handler.handle("/compact preserve exact provider failures") is True
    assert captured["kwargs"] == {
        "action": "compress",
        "keep_last_messages": 8,
        "focus": "preserve exact provider failures",
    }
    assert captured["context"]["session_manager"] is session_manager
    assert captured["context"]["workspace_stats_manager"] is workspace_stats_manager
    assert "Context compression completed" in console.export_text()
    assert "compact" in DIRECT_COMMANDS
    assert HELP_TOPICS["compact"]["command"] == "/compact"


def test_manual_context_compaction_persists_session_memory_and_provider_metadata(monkeypatch, tmp_path: Path) -> None:
    captured = {}
    original_history = [
        {"role": "user" if index % 2 == 0 else "assistant", "content": f"message {index}"}
        for index in range(12)
    ]
    compressed_history = [
        {
            "role": "system",
            "content": "[MEMORY CONSOLIDATION - Context Engine Cache]\nSummary:\n- state\n[END MEMORY]",
        },
        *original_history[-8:],
    ]

    class Agent:
        model = "test-model"
        model_display_name = "Test Model"
        provider = "request"
        base_url = "https://example.test/v1/chat/completions"
        api_key = "test-key"
        custom_headers = {"X-Test": "yes"}

        def __init__(self):
            self.history = list(original_history)
            self.recorded_memory = None

        def get_history(self):
            return list(self.history)

        def set_history(self, messages):
            self.history = list(messages)

        def get_token_estimate(self):
            return 1200 if self.history == original_history else 500

        def _record_compaction_memory(self, messages, session_id):
            self.recorded_memory = (messages, session_id)

    class Session:
        id = "session-compact"

    class SessionManager:
        def __init__(self):
            self.updated = None

        def get_current_session(self):
            return Session()

        def update_messages(self, messages):
            self.updated = list(messages)

    def fake_compress(self, **kwargs):
        captured.update(kwargs)
        return list(compressed_history)

    monkeypatch.setattr(
        "reverie.context_engine.compressor.ContextCompressor.compress",
        fake_compress,
    )
    agent = Agent()
    session_manager = SessionManager()
    workspace_stats_manager = object()
    tool = ContextManagementTool(
        {
            "agent": agent,
            "project_root": tmp_path,
            "session_manager": session_manager,
            "workspace_stats_manager": workspace_stats_manager,
        }
    )

    result = tool.execute(
        action="compress",
        keep_last_messages=8,
        focus="preserve the failing endpoint",
    )

    assert result.success is True
    assert result.output == "Context compressed: 1,200 -> 500 tokens"
    assert captured["custom_headers"] == {"X-Test": "yes"}
    assert captured["workspace_stats_manager"] is workspace_stats_manager
    assert captured["model_display_name"] == "Test Model"
    assert captured["keep_last_messages"] == 8
    assert captured["focus"] == "preserve the failing endpoint"
    assert session_manager.updated == compressed_history
    assert agent.recorded_memory == (compressed_history, "session-compact")
