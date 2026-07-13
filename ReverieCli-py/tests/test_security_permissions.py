from pathlib import Path

from reverie.agent.tool_executor import ToolExecutor
from reverie.config import Config
from reverie.security_policy import normalize_permission_level
from reverie.tools.command_exec import CommandExecTool
from reverie.tools.delete_file import DeleteFileTool


class _Agent:
    mode = "reverie"

    def __init__(self, permission_level: str):
        self.config = Config(security={"permission_level": permission_level})


def _executor(tmp_path: Path, permission_level: str) -> ToolExecutor:
    executor = ToolExecutor(tmp_path)
    executor.update_context("agent", _Agent(permission_level))
    return executor


def test_permission_levels_default_invalid_values_to_workspace_write() -> None:
    assert normalize_permission_level(None) == "workspace_write"
    assert normalize_permission_level("unexpected") == "workspace_write"
    assert Config().to_dict()["security"]["permission_level"] == "workspace_write"


def test_workspace_write_hides_and_denies_shell(tmp_path: Path) -> None:
    executor = _executor(tmp_path, "workspace_write")
    assert "command_exec" not in executor.list_tools(mode="reverie")

    result = executor.execute("command_exec", {"command": "python -c \"print(1)\""})
    assert not result.success
    assert "requires 'developer'" in result.error


def test_read_only_denies_file_mutation(tmp_path: Path) -> None:
    executor = _executor(tmp_path, "read_only")
    result = executor.execute("create_file", {"path": "blocked.txt", "content": "no"})
    assert not result.success
    assert not (tmp_path / "blocked.txt").exists()


def test_developer_allows_shell_but_not_full_control_tools(tmp_path: Path) -> None:
    executor = _executor(tmp_path, "developer")
    assert "command_exec" in executor.list_tools(mode="reverie")
    assert "browser_controler" not in executor.list_tools(mode="reverie")


def test_catastrophic_commands_are_permanently_blocked(tmp_path: Path) -> None:
    tool = CommandExecTool({"project_root": tmp_path})
    for command in ("format C:", "diskpart /s wipe.txt", "shutdown /s /t 0", "dd if=x of=/dev/sda"):
        result = tool.execute(command=command)
        assert not result.success
        assert "disabled by software policy" in result.error


def test_delete_file_refuses_targets_over_one_gib(tmp_path: Path) -> None:
    target = tmp_path / "large.bin"
    with target.open("wb") as handle:
        handle.truncate(1024 ** 3 + 1)
    result = DeleteFileTool({"project_root": tmp_path}).execute(path=str(target), confirm_delete=True)

    assert not result.success
    assert "in-depth review" in result.error
    assert target.exists()
