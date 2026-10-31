"""Completion decisions must follow observed work, rather than command intent."""
from types import SimpleNamespace

import pytest

from reverie import harness


def gate(audit=None, tasks=None):
    tasks = tasks or {}
    audit = audit or {}
    return harness.build_completion_gate(
        task_summary=tasks,
        task_snapshot=harness.summarize_task_snapshot(tasks),
        audit_summary=audit,
        verification_summary=audit.get("verification", {}),
        operation_summary={},
        git_workspace={},
    )


def test_pending_tasks_prevent_completion_even_without_active_lane():
    decision = gate(tasks={"total": 2, "completed": 1, "not_started": 1})
    assert decision["status"] == "continue"
    assert "1" in " ".join(decision["reasons"])


def test_active_task_outside_preview_prevents_completion():
    # Large task ledgers expose only ten preview entries, but counts cover all tasks.
    decision = gate(tasks={"total": 12, "completed": 11, "in_progress": 1,
                           "entries": [{"state": "COMPLETED", "name": str(i)} for i in range(10)]})
    assert decision["status"] == "continue"


@pytest.mark.parametrize("event", ["command_start", "command_blocked"])
def test_verification_intent_is_not_success(monkeypatch, tmp_path, event):
    monkeypatch.setattr(harness, "_safe_json_lines", lambda path: [
        {"event": event, "command": "pytest -q", "cwd": str(tmp_path)}
    ])
    audit = harness.summarize_command_audit(tmp_path, project_data_dir=tmp_path)
    assert audit["verification"]["successful_commands"] == 0
    assert gate(audit)["status"] != "ready"


def test_only_a_completed_verification_satisfies_the_gate(monkeypatch, tmp_path):
    entries = [
        {"event": "command_start", "command": "pytest -q", "cwd": str(tmp_path)},
        {"event": "command_result", "command": "pytest -q", "cwd": str(tmp_path), "exit_code": 0},
    ]
    monkeypatch.setattr(harness, "_safe_json_lines", lambda path: entries)
    audit = harness.summarize_command_audit(tmp_path, project_data_dir=tmp_path)
    assert audit["verification"]["explicit_commands"] == 1
    assert gate(audit)["status"] == "ready"


def test_timeout_after_success_does_not_reuse_old_success(monkeypatch, tmp_path):
    entries = [
        {"event": "command_result", "command": "pytest -q", "cwd": str(tmp_path), "exit_code": 0},
        {"event": "command_timeout", "command": "pytest -q", "cwd": str(tmp_path)},
    ]
    monkeypatch.setattr(harness, "_safe_json_lines", lambda path: entries)
    audit = harness.summarize_command_audit(tmp_path, project_data_dir=tmp_path)
    assert audit["timed_out_commands"] == 1
    assert audit["unresolved_failed_commands"] == 1
    assert gate(audit)["status"] == "blocked"


def test_prompt_failure_cannot_inherit_workspace_readiness(monkeypatch, tmp_path):
    monkeypatch.setattr(harness, "build_harness_capability_report", lambda *a, **kw: {
        "completion_gate": {"status": "ready", "label": "Ready to close"},
        "git_workspace": {},
    })
    result = SimpleNamespace(success=False, error="Provider unavailable", mode="reverie",
                             activity_events=[], ui_events=[])
    report = harness.build_prompt_harness_report(tmp_path, project_data_dir=tmp_path, prompt_result=result)
    assert report["completion_gate"]["status"] == "blocked"


def test_prompt_gate_uses_its_own_command_window(monkeypatch, tmp_path):
    monkeypatch.setattr(harness, "build_harness_capability_report", lambda *a, **kw: {
        "completion_gate": {"status": "ready", "label": "Ready to close"},
        "git_workspace": {"is_dirty": True},
    })
    monkeypatch.setattr(harness, "summarize_command_audit", lambda *a, **kw: {
        "entries": 1, "verification": {"explicit_commands": 0, "successful_commands": 0}
    })
    result = SimpleNamespace(success=True, error="", mode="reverie", activity_events=[], ui_events=[])
    report = harness.build_prompt_harness_report(tmp_path, project_data_dir=tmp_path, prompt_result=result)
    assert report["completion_gate"]["status"] == "continue"


def test_completed_and_cancelled_tasks_are_closed():
    assert gate(tasks={"total": 2, "completed": 1, "cancelled": 1})["status"] == "ready"


@pytest.mark.parametrize("command", [
    "echo pytest", "printf 'npm run build'", "cat pytest.log", "echo '&&' pytest",
    "env CI=1 echo '&&' pytest", "bash -lc 'echo \"&&\" pytest'",
    'python -c "print(\'pytest\')"', "python -m pytest --version",
    "pytest --collect-only", "npm run test -- --help", "npm run --if-present test",
    "npx playwright install", "tsc --showConfig", "dotnet --info test",
    "powershell -Command \"'pytest'\"", "cmd /c \"echo pytest\"", "vitest list",
    "pytest -q || true", "pytest -q | tee results.txt", "pytest -q; true", "pytest -q &",
])
def test_mentions_and_non_verifying_commands_do_not_close_the_gate(monkeypatch, tmp_path, command):
    monkeypatch.setattr(harness, "_safe_json_lines", lambda path: [
        {"event": "command_result", "command": command, "cwd": str(tmp_path), "exit_code": 0}
    ])
    audit = harness.summarize_command_audit(tmp_path, project_data_dir=tmp_path)
    assert audit["verification"]["successful_commands"] == 0
    assert gate(audit)["status"] == "continue"


@pytest.mark.parametrize(("command", "category"), [
    ("pytest -v tests/test_core.py", "test"), ("python3.12 -m pytest -q", "test"),
    ('"/a path/python" -m unittest discover', "test"), ("py -3.12 -m pytest", "test"),
    ("& 'C:\\Program Files\\Python\\python.exe' -m pytest", "test"),
    ("powershell -NoProfile -Command 'pytest -q'", "test"), ("cmd /c pytest -q", "test"),
    ("npm test", "test"), ("npm run test:unit -- --run", "test"), ("pnpm test", "test"),
    ("yarn lint", "lint"), ("bun test", "test"), ("npx playwright test", "e2e"),
    ("npx --yes vitest run", "test"), ("npm exec -- vitest run", "test"),
    ("uv run --no-sync python -m pytest", "test"), ("env CI=1 pytest -q", "test"),
    ("bash -lc 'pytest -q'", "test"), ("cd src && pytest -q", "test"),
    ("ruff check .", "lint"), ("ruff format --check .", "lint"),
    ("npm run typecheck", "typecheck"), ("tsc --noEmit", "typecheck"),
    ("npm run build", "build"), ("python -m build", "build"),
    ("go test ./...", "test"), ("cargo test", "test"), ("cargo clippy", "lint"),
    ("mvn -q test", "test"), ("./gradlew test", "test"), ("cmake --build build", "build"),
])
def test_real_check_entrypoints_remain_classified(command, category):
    assert category in harness._classify_verification_command(command)


def test_original_command_preserves_a_quoted_executable_path(monkeypatch, tmp_path):
    monkeypatch.setattr(harness, "_safe_json_lines", lambda path: [{
        "event": "command_result", "command": '"C:\\Program Files\\Python\\python.exe" -m pytest -q',
        "normalized_command": "C:\\Program Files\\Python\\python.exe -m pytest -q", "exit_code": 0,
    }])
    audit = harness.summarize_command_audit(tmp_path, project_data_dir=tmp_path)
    assert audit["verification"]["successful_commands"] == 1


def operation(timestamp, *, success):
    return SimpleNamespace(timestamp=timestamp, operation_type=SimpleNamespace(value="tool_call"),
                           tool_call=SimpleNamespace(tool_name="file_ops", success=success,
                               result="inventory" if success else "", error="" if success else "missing required parameter: path"))


def test_prompt_operations_use_the_same_window_without_erasing_workspace_history(monkeypatch, tmp_path):
    history = SimpleNamespace(operations=[
        operation("2001-01-01T00:00:00+00:00", success=False),
        operation("2026-10-28T12:00:01+00:00", success=True),
        operation("2026-10-28T12:00:03+00:00", success=False),
    ])
    monkeypatch.setattr(harness, "build_harness_capability_report", lambda *a, **kw: {
        "artifacts": {"operation_history": harness.summarize_operation_history(history)},
    })
    monkeypatch.setattr(harness, "summarize_command_audit", lambda *a, **kw: {
        "entries": 1, "verification": {"explicit_commands": 1, "successful_commands": 1}
    })
    result = SimpleNamespace(success=True, error="", mode="reverie", activity_events=[], ui_events=[],
                             started_at="2026-10-28T12:00:00+00:00", ended_at="2026-10-28T12:00:02+00:00")
    report = harness.build_prompt_harness_report(tmp_path, project_data_dir=tmp_path,
                                                prompt_result=result, operation_history=history)
    assert report["completion_gate"]["status"] == "ready"
    assert report["operation_history"]["operations"] == 1
    assert report["operation_history"]["tool_failures"] == 0
    assert report["workspace_audit"]["artifacts"]["operation_history"]["tool_failures"] == 2
    assert len(history.operations) == 3


def test_current_window_schema_failure_still_blocks_completion(monkeypatch, tmp_path):
    history = SimpleNamespace(operations=[operation("2026-10-28T12:00:01+00:00", success=False)])
    monkeypatch.setattr(harness, "build_harness_capability_report", lambda *a, **kw: {})
    result = SimpleNamespace(success=True, error="", mode="reverie", activity_events=[], ui_events=[],
                             started_at="2026-10-28T12:00:00+00:00", ended_at="2026-10-28T12:00:02+00:00")
    report = harness.build_prompt_harness_report(tmp_path, project_data_dir=tmp_path,
                                                prompt_result=result, operation_history=history)
    assert report["completion_gate"]["status"] == "blocked"
    assert report["operation_history"]["tool_failures_by_class"]["schema_mismatch"] == 1


@pytest.mark.parametrize(("success", "error", "expected"), [
    (False, "HTTP 429 throttling_error", "blocked"),
    (True, "", "continue"),
])
def test_persisted_run_keeps_current_gate_instead_of_workspace_readiness(monkeypatch, tmp_path, success, error, expected):
    import json

    workspace_gate = {"status": "ready", "label": "Ready to close"}
    monkeypatch.setattr(harness, "build_harness_capability_report", lambda *a, **kw: {
        "completion_gate": workspace_gate,
        "recovery_playbooks": [{"id": "historical_failure"}],
    })
    # A real current command without validation should continue; a provider
    # failure must be blocked. Neither can inherit the workspace's ready gate.
    monkeypatch.setattr(harness, "summarize_command_audit", lambda *a, **kw: {
        "entries": 1, "verification": {"explicit_commands": 0, "successful_commands": 0},
    })
    result = SimpleNamespace(success=success, error=error, mode="reverie", activity_events=[], ui_events=[],
                             started_at="2026-10-30T09:55:11", ended_at="2026-10-30T09:55:13")
    report = harness.build_prompt_harness_report(tmp_path, project_data_dir=tmp_path, prompt_result=result)
    assert report["completion_gate"]["status"] == expected
    report["recovery_playbooks"] = []
    history = harness.persist_prompt_harness_run(tmp_path, prompt_result=result, harness_report=report)
    stored = json.loads((tmp_path / "harness/prompt_runs.jsonl").read_text())
    assert history["latest_run"]["completion_gate_status"] == expected
    assert stored["completion_gate_status"] == expected
    assert stored["completion_gate_label"] == report["completion_gate"]["label"]
    assert stored["recovery_playbook_ids"] == []
    assert history["latest_run"]["recovery_playbooks"] == 0
    assert report["workspace_audit"]["completion_gate"] == workspace_gate


def test_legacy_harness_history_without_current_gate_uses_workspace_fallback(tmp_path):
    result = SimpleNamespace(success=True, error="", mode="reverie")
    report = {"workspace_audit": {"completion_gate": {"status": "ready", "label": "Legacy gate"},
                                  "recovery_playbooks": [{"id": "legacy_recovery"}]}}
    history = harness.persist_prompt_harness_run(tmp_path, prompt_result=result, harness_report=report)
    assert history["latest_run"]["completion_gate_status"] == "ready"
    assert history["latest_run"]["recovery_playbooks"] == 1
