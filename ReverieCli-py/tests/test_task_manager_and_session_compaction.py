import json
from pathlib import Path

from rich.console import Console

from reverie.cli.display import DisplayComponents
from reverie.session.manager import SessionManager
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
