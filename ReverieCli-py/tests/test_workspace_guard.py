from pathlib import Path
import json
import subprocess

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


class _DesktopActionTool(BaseTool):
    name = "desktop_action"
    workspace_checkpoint = False

    def execute(self, **kwargs) -> ToolResult:
        return ToolResult.ok("desktop action completed")


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


def test_desktop_action_does_not_depend_on_workspace_checkpoint_repository(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    guard = _guard(workspace, tmp_path / "state")
    guard.git_dir.mkdir(parents=True)
    (guard.git_dir / "index.lock").write_text("stale", encoding="utf-8")
    executor = ToolExecutor(workspace)
    executor.update_context("shadow_git_manager", guard)
    executor._register_tool_instance(_DesktopActionTool(executor.context))
    executor._rebuild_tool_alias_lookup()

    result = executor.execute("desktop_action", {})

    assert result.success
    assert result.output == "desktop action completed"


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


def _vanished_add_failure() -> subprocess.CompletedProcess[str]:
    """What Git reports when a file disappears between the walk and the open."""
    return subprocess.CompletedProcess(
        args=["git", "add"],
        returncode=128,
        stdout="",
        stderr=(
            'error: open(".godot/global_script_class_cache.cfg14995211.tmp"): '
            "No such file or directory\n"
            'error: unable to index file ".godot/global_script_class_cache.cfg14995211.tmp"\n'
            "fatal: adding files failed\n"
        ),
    )


def _as_git_result(
    failure: subprocess.CompletedProcess[str], *, check: bool
) -> subprocess.CompletedProcess[str]:
    """Apply ``_git``'s own check contract, so a caller that demands success raises.

    Without this a fake would let the pre-fix code path look healthy: it called
    ``add`` with ``check=True`` and would have raised on this exact stderr.
    """
    if check:
        raise WorkspaceGuardError(failure.stderr.strip())
    return failure


def test_a_file_that_vanishes_mid_checkpoint_does_not_fail_the_operation(tmp_path: Path) -> None:
    """A checkpoint is a safety net; unrelated churn must not abort the real work."""
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    (workspace / "keep.txt").write_text("keep", encoding="utf-8")
    guard = _guard(workspace, tmp_path / "state")
    guard.ensure_initialized()

    real_git = guard._git
    attempts = {"count": 0}

    def flaky_git(*args: str, check: bool = True):
        if args[:2] == ("add", "-A"):
            attempts["count"] += 1
            if attempts["count"] == 1:
                # Stage for real, then report the vanished temp file as Git does.
                real_git(*args, check=False)
                return _as_git_result(_vanished_add_failure(), check=check)
        return real_git(*args, check=check)

    guard._git = flaky_git

    checkpoint = guard.checkpoint("baseline")

    assert attempts["count"] == 2, "the failed add must be retried"
    assert checkpoint.commit
    assert checkpoint.changed
    guard._git = real_git
    tracked = real_git("ls-tree", "--name-only", "HEAD").stdout.split()
    assert "keep.txt" in tracked


def test_persistent_churn_is_audited_instead_of_raising(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    (workspace / "keep.txt").write_text("keep", encoding="utf-8")
    guard = _guard(workspace, tmp_path / "state")
    guard.ensure_initialized()

    real_git = guard._git
    attempts = {"count": 0}

    def always_churning(*args: str, check: bool = True):
        if args[:2] == ("add", "-A"):
            attempts["count"] += 1
            real_git(*args, check=False)
            return _as_git_result(_vanished_add_failure(), check=check)
        return real_git(*args, check=check)

    guard._git = always_churning

    checkpoint = guard.checkpoint("baseline")

    assert attempts["count"] == ShadowGitManager.STAGE_RETRY_LIMIT
    assert checkpoint.commit
    records = [
        json.loads(line)
        for line in guard.audit_path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    churn = [record for record in records if record["event"] == "checkpoint_stage_churn"]
    assert churn, "a thin checkpoint must be explainable after the fact"
    assert any("global_script_class_cache" in path for path in churn[-1]["paths"])


def test_a_real_add_failure_still_fails_the_checkpoint(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    guard = _guard(workspace, tmp_path / "state")
    guard.ensure_initialized()

    real_git = guard._git

    def broken_git(*args: str, check: bool = True):
        if args[:2] == ("add", "-A"):
            return _as_git_result(
                subprocess.CompletedProcess(
                    args=["git", "add"],
                    returncode=128,
                    stdout="",
                    stderr="fatal: not a git repository\n",
                ),
                check=check,
            )
        return real_git(*args, check=check)

    guard._git = broken_git

    try:
        guard.checkpoint("baseline")
    except WorkspaceGuardError as exc:
        assert "not a git repository" in str(exc)
    else:
        raise AssertionError("A genuine Git failure was swallowed")
