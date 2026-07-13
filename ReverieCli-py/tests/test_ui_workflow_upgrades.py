from pathlib import Path

from rich.console import Console

from reverie.agent.tool_executor import ToolExecutor
from reverie.cli.input_handler import InputHandler
from reverie.cli.interface import ReverieInterface
from reverie.config import Config
from reverie.session.manager import SessionManager


class _Agent:
    mode = "reverie"

    def __init__(self, level: str = "workspace_write"):
        self.config = Config(security={"permission_level": level})


def test_dynamic_command_provider_updates_without_recreating_handler(tmp_path: Path) -> None:
    commands = {"/runtime-one": "one"}
    handler = InputHandler(Console(), command_provider=lambda: dict(commands))
    assert handler.get_command_completions("/runtime-")[0][0] == "/runtime-one"

    commands["/runtime-two"] = "two"
    assert {item[0] for item in handler.get_command_completions("/runtime-")} == {"/runtime-one", "/runtime-two"}


def test_approval_handler_supports_once_and_session(tmp_path: Path) -> None:
    executor = ToolExecutor(tmp_path)
    executor.update_context("agent", _Agent())
    decisions = iter(["once", "session"])
    calls = []
    executor.update_context("tool_approval_handler", lambda tool, args, denial: calls.append(tool.name) or next(decisions))

    first = executor.execute("command_exec", {"command": "python -c \"print('one')\""})
    second = executor.execute("command_exec", {"command": "python -c \"print('two')\""})
    third = executor.execute("command_exec", {"command": "python -c \"print('three')\""})

    assert first.success and second.success and third.success
    assert calls == ["command_exec", "command_exec"]


def test_approval_handler_keeps_deny_as_default(tmp_path: Path) -> None:
    executor = ToolExecutor(tmp_path)
    executor.update_context("agent", _Agent())
    executor.update_context("tool_approval_handler", lambda *args: "deny")
    result = executor.execute("command_exec", {"command": "python -c \"print('blocked')\""})
    assert not result.success


def test_dynamic_catalog_binding_can_defer_external_discovery(tmp_path: Path) -> None:
    class _Runtime:
        def __init__(self) -> None:
            self.calls = 0

        def get_tool_definitions(self, force_refresh: bool = False):
            self.calls += 1
            return []

        def get_generation(self) -> int:
            return 0

    runtime = _Runtime()
    executor = ToolExecutor(tmp_path)
    executor.update_context("mcp_runtime", runtime, sync_dynamic=False)

    assert runtime.calls == 0
    executor.list_tools()
    assert runtime.calls == 1


def test_session_export_search_fork_and_rewind(tmp_path: Path) -> None:
    manager = SessionManager(tmp_path / "state", project_root=tmp_path)
    source = manager.create_session("Source")
    source.messages = [
        {"role": "user", "content": "alpha question"},
        {"role": "assistant", "content": "beta answer"},
        {"role": "user", "content": "gamma question"},
    ]
    manager.save_session(source)

    assert manager.search_sessions("beta")[0]["message_index"] == 1
    exported = manager.export_current_session(tmp_path / "session.md")
    assert "## Assistant" in exported.read_text(encoding="utf-8")

    forked = manager.fork_current_session(2)
    assert len(forked.messages) == 2
    assert forked.metadata["forked_from"] == source.id
    manager.rewind_current_session(1)
    assert len(manager.get_current_session().messages) == 1


def test_workspace_mention_candidates_include_non_visual_files(tmp_path: Path) -> None:
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "feature.py").write_text("print('ok')", encoding="utf-8")
    interface = object.__new__(ReverieInterface)
    interface.project_root = tmp_path

    candidates = interface._collect_workspace_mention_candidates("feature")
    assert [item["path"] for item in candidates] == ["src/feature.py"]
