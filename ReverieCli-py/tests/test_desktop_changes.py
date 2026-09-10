import pytest

from reverie.desktop_changes import MAX_SNAPSHOT_BYTES, file_changes_payload, read_edit_snapshot
from reverie.session.operation_history import OperationHistory


def test_changes_combine_edits_and_isolate_sessions():
    history = OperationHistory("workspace")
    history.add_file_operation("a.py", "modify", "before\n", "middle\n", session_id="one")
    history.add_file_operation("a.py", "modify", "middle\n", "after\n", session_id="one")
    history.add_file_operation("other.py", "create", "", "other", session_id="two")
    changes = file_changes_payload(history, "one")
    assert len(changes) == 1
    assert "-before" in changes[0]["diff"] and "+after" in changes[0]["diff"]
    assert "middle" not in changes[0]["diff"]
    assert (changes[0]["additions"], changes[0]["deletions"]) == (1, 1)
    restored = OperationHistory.from_dict(history.to_dict())
    assert file_changes_payload(restored, "one") == changes


def test_changes_creation_deletion_unknown_and_no_net_change():
    history = OperationHistory("workspace")
    history.add_file_operation("new", "create", "", "new\n", session_id="one")
    history.add_file_operation("gone", "delete", "gone\n", "", session_id="one")
    history.add_file_operation("binary", "modify", None, None, session_id="one")
    history.add_file_operation("same", "modify", "same", "same", session_id="one")
    changes = {item["path"]: item for item in file_changes_payload(history, "one")}
    assert set(changes) == {"new", "gone", "binary"}
    assert changes["new"]["additions"] == 1
    assert changes["gone"]["deletions"] == 1
    assert changes["binary"]["unavailable"]


def test_snapshot_bounds_and_binary(tmp_path):
    sample = tmp_path / "sample"
    assert read_edit_snapshot(sample) == ""
    sample.write_bytes("你好\n".encode("utf-8"))
    assert read_edit_snapshot(sample) == "你好\n"
    sample.write_bytes(b"a\x00b")
    assert read_edit_snapshot(sample) is None
    sample.write_bytes(b"a" * (MAX_SNAPSHOT_BYTES + 1))
    assert read_edit_snapshot(sample) is None


@pytest.mark.parametrize(
    "edits, expected",
    [
        ([("create", "", "")], "create"),
        ([("delete", "", "")], "delete"),
        ([("delete", "old\n", ""), ("create", "", "new\n")], "modify"),
        ([("delete", "same\n", ""), ("create", "", "same\n")], None),
        ([("create", "", "new\n"), ("modify", "new\n", "edited\n")], "create"),
        ([("create", None, None), ("delete", None, None)], None),
    ],
    ids=["empty-create", "empty-delete", "recreated", "restored", "edited-create", "binary-create-delete"],
)
def test_changes_preserve_file_existence_across_edits(edits, expected):
    history = OperationHistory("workspace")
    for operation, old, new in edits:
        history.add_file_operation("sample", operation, old, new, session_id="one")
    changes = file_changes_payload(history, "one")
    if expected is None:
        assert changes == []
    else:
        assert len(changes) == 1
        assert changes[0]["operation"] == expected


def test_diff_counts_include_content_that_looks_like_a_header():
    history = OperationHistory("workspace")
    history.add_file_operation("sample", "modify", "--old\n", "++new\n", session_id="one")
    change = file_changes_payload(history, "one")[0]
    assert (change["additions"], change["deletions"]) == (1, 1)


@pytest.mark.parametrize("content", ["line\n" * 3000, "a" * 61000 + "\nmore\n"], ids=["line-limit", "character-limit"])
def test_diff_counts_match_only_the_displayed_preview(content):
    history = OperationHistory("workspace")
    history.add_file_operation("sample", "create", "", content, session_id="one")
    change = file_changes_payload(history, "one")[0]
    assert change["truncated"]
    assert len(change["diff"]) <= 60000
    lines = change["diff"].splitlines()
    assert len(lines) <= 2000
    assert change["additions"] == sum(line.startswith("+") for line in lines[2:])


def test_diff_preserves_missing_final_newline_evidence():
    history = OperationHistory("workspace")
    history.add_file_operation("sample", "modify", "same", "same\n", session_id="one")
    change = file_changes_payload(history, "one")[0]
    assert "-same\n\\ No newline at end of file\n+same" in change["diff"]


def test_agent_edit_records_real_before_and_after_and_ignores_failures(tmp_path):
    import json
    from types import SimpleNamespace
    from reverie.agent.agent import ReverieAgent
    from reverie.tools.str_replace_editor import StrReplaceEditorTool

    target = tmp_path / "sample.py"
    target.write_bytes(b"value = 1\n")
    tool = StrReplaceEditorTool({"project_root": tmp_path})
    history = OperationHistory("workspace")
    agent = SimpleNamespace(
        tool_executor=SimpleNamespace(get_tool=lambda name: tool, execute=lambda name, args, **kwargs: tool.execute(**args)),
        _check_tool_side_effects=lambda *args: None,
        operation_history=history, rollback_manager=None, messages=[],
        agent_id="test", agent_color="blue",
    )
    for old in ("value = 1", "missing text"):
        call = {"id": "edit", "function": {"name": "str_replace_editor", "arguments": json.dumps({
            "command": "str_replace", "path": str(target), "old_str": old, "new_str": "value = 2",
        })}}
        list(ReverieAgent._stream_execute_tool_call(agent, call, [], session_id="test-session"))
    changes = file_changes_payload(history, "test-session")
    assert len(changes) == 1
    assert "-value = 1" in changes[0]["diff"]
    assert "+value = 2" in changes[0]["diff"]
    assert not file_changes_payload(history, "another-session")
