import json
import multiprocessing
from concurrent.futures import ThreadPoolExecutor

import pytest

from reverie.session.workspace_stats import WorkspaceStatsManager
from reverie.storage import ProjectStorageResolver


def _record_stats(root, number, ready, start):
    manager = WorkspaceStatsManager(root)
    ready.put(number)
    start.wait(20)
    for _ in range(20):
        manager.record_runtime(1, force=True)
        manager.record_active_time(0.5, force=True)
        manager.record_model_usage(
            provider="test", source="standard", model="shared", model_display_name="Shared",
            request_messages=[], usage={"input_tokens": 3, "output_tokens": 2},
            session_id=f"session-{number}", force=True,
        )
        manager.record_operation(category="tool", name="read", duration_ms=7, force=True)
    manager.flush()


def test_four_processes_preserve_all_statistics(tmp_path):
    context = multiprocessing.get_context("spawn")
    ready, start = context.Queue(), context.Event()
    processes = [context.Process(target=_record_stats, args=(str(tmp_path), index, ready, start)) for index in range(4)]
    try:
        for process in processes:
            process.start()
        assert sorted(ready.get(timeout=30) for _ in processes) == list(range(4))
        start.set()
        for process in processes:
            process.join(30)
            assert process.exitcode == 0
    finally:
        for process in processes:
            if process.is_alive():
                process.terminate()
                process.join()
    state = WorkspaceStatsManager(tmp_path).state
    assert state.total_runtime_seconds == 80
    assert state.total_active_seconds == 40
    assert state.model_usage["test::standard::shared"].calls == 80
    assert state.model_usage["test::standard::shared"].total_tokens == 400
    assert [state.session_usage[f"session-{index}"].calls for index in range(4)] == [20] * 4
    assert state.operation_usage["tool::::read"].total_duration_ms == 560


def test_legacy_statistics_are_imported_once_and_retained(tmp_path):
    legacy = tmp_path / "workspace_stats.json"
    legacy.write_text(json.dumps({"total_runtime_seconds": 12}), encoding="utf-8")
    manager = WorkspaceStatsManager(tmp_path)
    manager.record_runtime(3, force=True)
    assert WorkspaceStatsManager(tmp_path).get_total_runtime_seconds() == 15
    assert json.loads(legacy.read_text(encoding="utf-8"))["total_runtime_seconds"] == 12


def test_statistics_commit_failure_preserves_pending_increment(tmp_path, monkeypatch):
    manager = WorkspaceStatsManager(tmp_path)
    connect = manager._connect
    monkeypatch.setattr(manager, "_connect", lambda: (_ for _ in ()).throw(OSError("disk full")))
    with pytest.raises(OSError, match="disk full"):
        manager.record_runtime(3, force=True)
    monkeypatch.setattr(manager, "_connect", connect)
    manager.flush()
    manager.flush()
    assert WorkspaceStatsManager(tmp_path).get_total_runtime_seconds() == 3


def test_parallel_storage_probes_do_not_delete_each_others_file(tmp_path):
    resolver = ProjectStorageResolver.for_project(tmp_path / "workspace", launcher_root=tmp_path / "app")
    with ThreadPoolExecutor(max_workers=4) as pool:
        list(pool.map(lambda _: resolver.ensure_writable(), range(100)))
    assert not list(resolver.reverie_root.glob(".write-test-*"))
