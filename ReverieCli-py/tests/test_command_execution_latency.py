from pathlib import Path
import sys

from reverie.tools.command_exec import CommandExecTool


def test_batch_command_does_not_wait_for_bridge_input(tmp_path: Path) -> None:
    script = tmp_path / "read_input.py"
    script.write_text("import sys\nprint('input=' + repr(sys.stdin.read()))\n", encoding="utf-8")
    tool = CommandExecTool({"project_root": tmp_path})
    result = tool.execute(command=f'"{sys.executable}" read_input.py', timeout=5)
    assert result.success, result.error
    assert "input=''" in result.output


def test_shell_chains_are_rejected_without_starting_a_process(tmp_path: Path, monkeypatch) -> None:
    from unittest.mock import Mock
    import subprocess

    spawn = Mock()
    monkeypatch.setattr(subprocess, "Popen", spawn)
    tool = CommandExecTool({"project_root": tmp_path})
    result = tool.execute(command="python -m compileall . && python -m unittest")
    assert not result.success
    assert "Run each command separately" in result.error
    spawn.assert_not_called()


def test_operator_text_inside_an_argument_is_preserved(tmp_path: Path) -> None:
    script = tmp_path / "arguments.py"
    script.write_text("import sys\nprint(sys.argv[1])\n", encoding="utf-8")
    tool = CommandExecTool({"project_root": tmp_path})
    for value in ["literal && text", "&&"]:
        result = tool.execute(command=f'"{sys.executable}" arguments.py "{value}"', timeout=5)
        assert result.success, result.error
        assert value in result.output
