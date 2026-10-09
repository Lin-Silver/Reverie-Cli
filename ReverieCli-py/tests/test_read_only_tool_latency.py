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
