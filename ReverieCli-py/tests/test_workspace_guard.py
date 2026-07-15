from pathlib import Path

from reverie.agent.tool_executor import ToolExecutor
from reverie.tools.base import BaseTool, ToolResult
from reverie.tools.command_exec import CommandExecTool
from reverie.tools.delete_file import DeleteFileTool
from reverie.workspace_guard import ShadowGitManager, WorkspaceGuardError


class _DeleteWithoutPermissionTool(BaseTool):
    name = "delete_without_permission"
    parameters = {
        "type": "object",
        "properties": {"path": {"type": "string"}},
        "required": ["path"],
    }

    def execute(self, **kwargs) -> ToolResult:
        Path(kwargs["path"]).unlink()
        return ToolResult.ok("deleted")


class _OutsideWriterTool(BaseTool):
    name = "outside_writer"
    parameters = {
        "type": "object",
        "properties": {"output_path": {"type": "string"}},
        "required": ["output_path"],
    }

    def execute(self, **kwargs) -> ToolResult:
        Path(kwargs["output_path"]).write_text("unsafe", encoding="utf-8")
        return ToolResult.ok("written")


def _guard(workspace: Path, state_root: Path) -> ShadowGitManager:
    return ShadowGitManager(workspace, state_root / "project-data")


def test_shadow_git_is_internal_and_restores_blocked_deletion(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    target = workspace / "keep.txt"
    target.write_text("keep", encoding="utf-8")
    guard = _guard(workspace, tmp_path / "state")

    checkpoint = guard.checkpoint("baseline")
    target.unlink()
    deleted = guard.deleted_paths_since(checkpoint.commit)
    restored = guard.restore_paths(checkpoint.commit, deleted)

    assert restored == ["keep.txt"]
    assert target.read_text(encoding="utf-8") == "keep"
    assert not (workspace / ".git").exists()
    assert guard.git_dir.is_dir()


def test_executor_restores_deletion_by_any_other_tool(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    target = workspace / "keep.txt"
    target.write_text("keep", encoding="utf-8")
    executor = ToolExecutor(workspace)
    executor.update_context("shadow_git_manager", _guard(workspace, tmp_path / "state"))
    executor._register_tool_instance(_DeleteWithoutPermissionTool(executor.context))
    executor._rebuild_tool_alias_lookup()

    result = executor.execute("delete_without_permission", {"path": str(target)})

    assert not result.success
    assert "only the delete_file tool" in result.error
    assert target.read_text(encoding="utf-8") == "keep"


def test_executor_restores_ignored_source_deleted_by_other_tool(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    (workspace / ".gitignore").write_text("private.cfg\n", encoding="utf-8")
    target = workspace / "private.cfg"
    target.write_text("protected", encoding="utf-8")
    executor = ToolExecutor(workspace)
    executor.update_context("shadow_git_manager", _guard(workspace, tmp_path / "state"))
    executor._register_tool_instance(_DeleteWithoutPermissionTool(executor.context))
    executor._rebuild_tool_alias_lookup()

    result = executor.execute("delete_without_permission", {"path": str(target)})

    assert not result.success
    assert target.read_text(encoding="utf-8") == "protected"


def test_delete_file_archives_ignored_file_before_removal(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    (workspace / "build").mkdir()
    (workspace / ".gitignore").write_text("build/\n", encoding="utf-8")
    target = workspace / "build" / "ignored.bin"
    target.write_bytes(b"binary\x00payload")
    guard = _guard(workspace, tmp_path / "state")
    tool = DeleteFileTool({"project_root": workspace, "shadow_git_manager": guard})

    result = tool.execute(path="build/ignored.bin", confirm_delete=True)

    assert result.success
    assert not target.exists()
    archive = Path(result.data["archive_path"])
    assert archive.read_bytes() == b"binary\x00payload"
    assert guard.deleted_files_dir in archive.parents


def test_delete_file_refreshes_context_after_checkpointed_removal(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    target = workspace / "remove.txt"
    target.write_text("remove", encoding="utf-8")
    executor = ToolExecutor(workspace)
    executor.update_context("shadow_git_manager", _guard(workspace, tmp_path / "state"))
    refreshes = []
    executor.update_context("refresh_context_after_mutation", lambda: refreshes.append(True))

    result = executor.execute("delete_file", {"path": "remove.txt", "confirm_delete": True})

    assert result.success
    assert not target.exists()
    assert refreshes == [True]


def test_mutating_tool_cannot_target_outside_workspace(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    outside = tmp_path / "outside.txt"
    executor = ToolExecutor(workspace)
    executor.update_context("shadow_git_manager", _guard(workspace, tmp_path / "state"))
    executor._register_tool_instance(_OutsideWriterTool(executor.context))
    executor._rebuild_tool_alias_lookup()

    result = executor.execute("outside_writer", {"output_path": str(outside)})

    assert not result.success
    assert "outside the active workspace" in result.error
    assert not outside.exists()


def test_guard_rejects_parent_traversal(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    guard = _guard(workspace, tmp_path / "state")

    try:
        guard.ensure_workspace_path("../outside.txt", purpose="write file")
    except WorkspaceGuardError as exc:
        assert "outside the active workspace" in str(exc)
    else:
        raise AssertionError("Parent traversal was accepted")


def test_command_exec_rejects_inline_interpreter_code(tmp_path: Path) -> None:
    tool = CommandExecTool({"project_root": tmp_path})

    result = tool.execute(command="python -c \"print('unsafe')\"")

    assert not result.success
    assert "inline interpreter" in result.error
