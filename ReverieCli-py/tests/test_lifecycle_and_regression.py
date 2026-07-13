from pathlib import Path

from reverie.agent.tool_executor import ToolExecutor
from reverie.agent_regression import AgentRegressionHarness
from reverie.lifecycle import LifecycleManager


def test_lifecycle_hooks_audit_and_deny_terminal_delete(tmp_path: Path) -> None:
    project_root = tmp_path / "workspace"
    project_data_dir = tmp_path / "cache"
    project_root.mkdir()
    (project_root / "keep.txt").write_text("safe", encoding="utf-8")

    lifecycle = LifecycleManager(project_data_dir, project_root=project_root)
    executor = ToolExecutor(project_root=project_root)
    executor.update_context("security", {"permission_level": "developer"})
    executor.update_context("project_data_dir", project_data_dir)
    executor.update_context("lifecycle_manager", lifecycle)

    read_result = executor.execute("file_ops", {"operation": "read", "path": "keep.txt"}, tool_call_id="test-read")
    assert read_result.success

    denied = executor.execute("command_exec", {"command": "Remove-Item keep.txt"}, tool_call_id="test-deny")
    assert not denied.success
    assert "Lifecycle hook denied" in (denied.error or "")
    assert (project_root / "keep.txt").exists()

    summary = lifecycle.summary()
    assert summary["events"] >= 3
    assert summary["denied"] >= 1
    assert any(item.get("tool") == "file_ops" for item in summary["recent"])


def test_agent_regression_harness_runs_stable_baseline(tmp_path: Path) -> None:
    project_root = tmp_path / "project"
    project_data_dir = tmp_path / "cache"
    project_root.mkdir()

    harness = AgentRegressionHarness(project_data_dir, project_root=project_root)
    summary = harness.run()

    assert summary["schema"] == "reverie.agent.regression.v1"
    assert summary["passed"] is True
    assert summary["total"] >= 4
    assert summary["score"] == 100
    assert harness.latest_summary()["passed"] is True
