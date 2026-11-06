from pathlib import Path
from unittest.mock import Mock

import pytest

from reverie.agent.tool_executor import ToolExecutor


@pytest.mark.parametrize("operation", ["list", "read", "exists", "info"])
def test_reading_file_ops_never_scans_workspace_for_write_checkpoints(tmp_path: Path, monkeypatch, operation):
    (tmp_path / "sample.txt").write_text("content", encoding="utf-8")
    executor = ToolExecutor(tmp_path)
    guard = executor.context["shadow_git_manager"]
    checkpoint = Mock(side_effect=AssertionError("Read operation tried to snapshot workspace"))
    monkeypatch.setattr(guard, "checkpoint", checkpoint)
    result = executor.execute("file_ops", {"operation": operation, "path": "." if operation == "list" else "sample.txt"})
    assert result.success, result.error
    checkpoint.assert_not_called()


def test_mkdir_keeps_before_and_after_checkpoints(tmp_path: Path, monkeypatch):
    executor = ToolExecutor(tmp_path)
    guard = executor.context["shadow_git_manager"]
    checkpoint = Mock(wraps=guard.checkpoint)
    monkeypatch.setattr(guard, "checkpoint", checkpoint)
    result = executor.execute("file_ops", {"operation": "mkdir", "path": "created"})
    assert result.success, result.error
    assert (tmp_path / "created").is_dir()
    assert checkpoint.call_count == 2


def test_editor_view_does_not_create_write_checkpoint(tmp_path: Path, monkeypatch):
    (tmp_path / "sample.txt").write_text("content", encoding="utf-8")
    executor = ToolExecutor(tmp_path)
    guard = executor.context["shadow_git_manager"]
    checkpoint = Mock(side_effect=AssertionError("View tried to snapshot workspace"))
    monkeypatch.setattr(guard, "checkpoint", checkpoint)
    result = executor.execute("str_replace_editor", {"command": "view", "path": "sample.txt"})
    assert result.success, result.error
    checkpoint.assert_not_called()


@pytest.mark.parametrize("field,operation", [
    ("action", "list"), ("action", "view"), ("action", "show"),
    ("operation", "view_tasklist"), ("action", "VIEW-TASKLIST"),
])
def test_task_list_never_scans_workspace(tmp_path: Path, monkeypatch, field, operation):
    artifacts = tmp_path / "artifacts"
    artifacts.mkdir()
    checklist = artifacts / "task.md"
    checklist.write_text("[ ] Inspect project\n[x] Verify tools", encoding="utf-8")
    executor = ToolExecutor(tmp_path)
    checkpoint = Mock(side_effect=AssertionError("List tried to snapshot workspace"))
    monkeypatch.setattr(executor.context["shadow_git_manager"], "checkpoint", checkpoint)
    before = checklist.stat().st_mtime_ns
    result = executor.execute("checklist", {field: operation})
    assert result.success, result.error
    assert len(result.data["tasks"]) == 2
    assert checklist.stat().st_mtime_ns == before
    checkpoint.assert_not_called()


def test_task_write_keeps_workspace_protection(tmp_path: Path, monkeypatch):
    executor = ToolExecutor(tmp_path)
    guard = executor.context["shadow_git_manager"]
    checkpoint = Mock(wraps=guard.checkpoint)
    monkeypatch.setattr(guard, "checkpoint", checkpoint)
    result = executor.execute("task_manager", {"action": "add", "tasks": ["Verify tools"]})
    assert result.success, result.error
    assert checkpoint.call_count == 2


def test_execute_builtin_does_not_refresh_dynamic_catalog(tmp_path: Path, monkeypatch):
    executor = ToolExecutor(tmp_path)
    sync = Mock(wraps=executor._sync_dynamic_tools)
    monkeypatch.setattr(executor, "_sync_dynamic_tools", sync)
    result = executor.execute("file_ops", {"operation": "exists", "path": "missing.txt"})
    assert result.success, result.error
    sync.assert_not_called()
