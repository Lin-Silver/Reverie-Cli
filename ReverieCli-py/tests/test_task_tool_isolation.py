from concurrent.futures import ThreadPoolExecutor, TimeoutError
import json
from threading import Event
from unittest.mock import Mock

import pytest

from reverie.agent.tool_executor import ToolExecutor
from reverie.tools.task_manager import TaskManagerTool, cleanup_completed_task_artifacts


def test_builtin_task_lookup_does_not_wait_for_dynamic_catalog(tmp_path, monkeypatch):
    executor = ToolExecutor(tmp_path)
    sync = Mock(side_effect=AssertionError("Built-in lookup entered plugin discovery"))
    monkeypatch.setattr(executor, "_sync_dynamic_tools", sync)
    result = executor.execute("checklist", {"action": "list"})
    assert result.success, result.error
    sync.assert_not_called()


def test_task_tools_keep_projects_separate(tmp_path):
    first = TaskManagerTool({"project_root": tmp_path / "first"})
    first.execute(action="add", tasks=["First project"])
    second = TaskManagerTool({"project_root": tmp_path / "second"})
    second.execute(action="add", tasks=["Second project"])
    assert first.execute(action="list").output == "[ ] First project"
    first.execute(action="update", target="First project", status="done")
    assert second.execute(action="list").output == "[ ] Second project"
    assert (tmp_path / "first/artifacts/task.md").read_text(encoding="utf-8") == "[x] First project"


def test_task_tool_sees_external_edits_without_rewriting_checklist(tmp_path):
    tool = TaskManagerTool({"project_root": tmp_path})
    tool.execute(action="add", tasks=["Original"])
    checklist = tmp_path / "artifacts/task.md"
    checklist.write_text("[/] Edited outside the tool\n[x] Verified", encoding="utf-8")
    before = checklist.stat().st_mtime_ns
    result = tool.execute(action="list")
    assert result.output == "[/] Edited outside the tool\n[x] Verified"
    assert checklist.stat().st_mtime_ns == before
    assert tool.execute(action="update", target="Edited outside the tool", status="done").success


def test_task_tool_does_not_resurrect_cleaned_up_tasks(tmp_path):
    tool = TaskManagerTool({"project_root": tmp_path})
    tool.execute(action="add", tasks=["Completed"])
    tool.execute(action="update", target="Completed", status="done")
    assert cleanup_completed_task_artifacts(tmp_path) == [tmp_path / "artifacts/task.md"]
    assert tool.execute(action="list").data["tasks"] == []
    tool.execute(action="add", tasks=["Next task"])
    assert tool.execute(action="list").output == "[ ] Next task"


def test_task_tools_in_same_workspace_observe_each_others_updates(tmp_path):
    first = TaskManagerTool({"project_root": tmp_path})
    second = TaskManagerTool({"project_root": tmp_path})
    first.execute(action="add", tasks=["Shared task"])
    assert second.execute(action="list").output == "[ ] Shared task"
    second.execute(action="update", target="Shared task", status="doing")
    assert first.execute(action="list").output == "[/] Shared task"


def test_same_workspace_instances_preserve_ids_and_metadata(tmp_path):
    first = TaskManagerTool({"project_root": tmp_path})
    second = TaskManagerTool({"project_root": tmp_path})
    dependency = first.execute(action="add", tasks=[{"name": "Dependency"}]).data["added_tasks"][0]
    result = second.execute(action="add", tasks=[{
        "name": "Main task",
        "description": "Keep this description",
        "priority": "high",
        "tags": ["review"],
        "dependencies": [dependency["id"]],
    }])
    assert result.success, result.error
    main = result.data["added_tasks"][0]
    updated = first.execute(action="update", target=dependency["id"], status="done")
    assert updated.success, updated.error
    for tool in (first, second):
        tasks = {task["name"]: task for task in tool.execute(action="list").data["tasks"]}
        assert tasks["Dependency"]["id"] == dependency["id"]
        assert tasks["Main task"]["id"] == main["id"]
        assert tasks["Main task"]["description"] == "Keep this description"
        assert tasks["Main task"]["priority"] == "high"
        assert tasks["Main task"]["tags"] == ["review"]
        assert tasks["Main task"]["dependencies"] == [dependency["id"]]


def test_concurrent_same_workspace_adds_preserve_both_tasks(tmp_path, monkeypatch):
    first = TaskManagerTool({"project_root": tmp_path})
    second = TaskManagerTool({"project_root": tmp_path})
    saving = Event()
    release = Event()
    original_save = first._task_store.save

    def pause_first_save():
        if not saving.is_set():
            saving.set()
            assert release.wait(5), "First save was not released"
        return original_save()

    monkeypatch.setattr(first._task_store, "save", pause_first_save)
    with ThreadPoolExecutor(max_workers=2) as pool:
        first_result = pool.submit(first.execute, action="add", tasks=["First"])
        try:
            assert saving.wait(5), "First task did not reach save"
            second_result = pool.submit(second.execute, action="add", tasks=["Second"])
            try:
                second_result.result(timeout=0.5)
            except TimeoutError:
                pass  # The second operation may correctly be waiting on the workspace lock.
        finally:
            release.set()
        assert first_result.result(timeout=5).success
        assert second_result.result(timeout=5).success
    assert set(first.execute(action="list").output.splitlines()) == {"[ ] First", "[ ] Second"}


@pytest.mark.parametrize("filename,content", [
    ("Tasks.md", "[ ] Legacy task"),
    ("task_list.json", json.dumps({
        "tasks": [{"id": "legacy-id", "name": "Legacy task", "state": "NOT_STARTED"}],
        "root_tasks": ["legacy-id"],
    })),
])
def test_list_reads_new_legacy_artifact_without_writing(tmp_path, filename, content):
    tool = TaskManagerTool({"project_root": tmp_path})
    artifacts = tmp_path / "artifacts"
    artifacts.mkdir()
    legacy = artifacts / filename
    legacy.write_text(content, encoding="utf-8")
    before = {path.name: path.read_bytes() for path in artifacts.iterdir()}
    result = tool.execute(action="list")
    assert result.success, result.error
    assert result.output == "[ ] Legacy task"
    assert {path.name: path.read_bytes() for path in artifacts.iterdir()} == before
