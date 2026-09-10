"""Bounded, read-only previews of file edits recorded by the agent."""

from difflib import unified_diff
from itertools import islice
from pathlib import Path


MAX_SNAPSHOT_BYTES = 256 * 1024


def read_edit_snapshot(path: Path) -> str | None:
    try:
        if not path.exists():
            return ""
        with path.open("rb") as stream:
            data = stream.read(MAX_SNAPSHOT_BYTES + 1)
        if len(data) > MAX_SNAPSHOT_BYTES or b"\x00" in data:
            return None
        return data.decode("utf-8")
    except (OSError, UnicodeError):
        return None


def file_changes_payload(history, session_id: str) -> list[dict]:
    # History belongs to the runtime workspace; file records carry session IDs
    # so switching conversations never attributes another session's edits here.
    grouped = {}
    for operation in list(history.operations):
        edit = operation.file_operation
        if edit is None or edit.session_id != session_id:
            continue
        previous = grouped.get(edit.file_path)
        grouped[edit.file_path] = {
            "path": edit.file_path,
            "operation": (previous or {}).get("operation", edit.operation),
            "old": previous["old"] if previous else edit.old_content,
            "new": edit.new_content,
            "last_operation": edit.operation,
            "timestamp": operation.timestamp,
        }
    result = []
    for item in list(grouped.values())[-100:]:
        old, new = item.pop("old"), item.pop("new")
        last_operation = item.pop("last_operation")
        existed_before = item["operation"] != "create"
        exists_after = last_operation != "delete"
        if not existed_before and not exists_after:
            continue
        if existed_before == exists_after and old is not None and new is not None and old == new:
            continue
        item["operation"] = "modify" if existed_before and exists_after else "delete" if existed_before else "create"
        unavailable = old is None or new is None
        lines = [] if unavailable else list(islice(unified_diff(
            old.splitlines(keepends=True), new.splitlines(keepends=True),
            fromfile="a/" + item["path"], tofile="b/" + item["path"],
        ), 2001))
        display_lines = []
        for line in lines:
            display_lines.append(line.rstrip("\r\n"))
            if not line.endswith(("\n", "\r")):
                display_lines.append("\\ No newline at end of file")
        preview = "\n".join(display_lines[:2000])
        truncated = len(display_lines) > 2000 or len(preview) > 60000
        preview = preview[:60000]
        # Only the first two lines are file headers. Content can itself begin
        # with ++/--, and counts must describe the preview the user can see.
        content_lines = preview.splitlines()[2:]
        item.update(
            diff=preview,
            additions=sum(line.startswith("+") for line in content_lines),
            deletions=sum(line.startswith("-") for line in content_lines),
            truncated=truncated, unavailable=unavailable,
        )
        result.append(item)
    return result
