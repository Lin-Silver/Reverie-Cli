from types import SimpleNamespace
import threading
import time
import pytest
from reverie.desktop_control import RunControl
from reverie.desktop_input import prepare_desktop_input


def test_steer_waits_for_request_boundary_and_stop_is_cooperative():
    events = []
    control = RunControl(events.append)
    agent = SimpleNamespace(messages=[], tool_executor=SimpleNamespace(context={}))
    identity = control.steer("new constraint", "new constraint")
    control.safe_point(agent, receive=False)
    assert agent.messages == []
    assert events[-1]["status"] == "waiting"
    control.safe_point(agent)
    assert agent.messages == [{"role": "user", "content": "new constraint"}]
    assert events[-1]["message_id"] == identity
    assert events[-1]["status"] == "received"
    control.stop()
    with pytest.raises(RuntimeError, match="stopped"):
        control.safe_point(agent)


def test_pause_resumes_at_a_tool_boundary():
    events = []
    control = RunControl(events.append)
    control.pause(True)
    worker = threading.Thread(target=control.safe_point, args=(SimpleNamespace(messages=[]),))
    worker.start()
    time.sleep(0.03)
    assert worker.is_alive()
    assert events[-1]["state"] == "paused"
    control.pause(False)
    worker.join(timeout=1)
    assert not worker.is_alive()


def test_desktop_text_inputs_use_current_version_and_never_cross_workspace(tmp_path):
    file = tmp_path / "中文 file.txt"
    file.write_text("current content", encoding="utf-8")
    interface = SimpleNamespace(project_root=tmp_path)
    content, records = prepare_desktop_input(interface, None, "", [{"relativePath": file.name, "kind": "reference"}])
    assert "current content" in content
    assert len(records[0]["version"]) == 64
    with pytest.raises(Exception):
        prepare_desktop_input(interface, None, "", [{"relativePath": "../outside.txt"}])
    with pytest.raises(ValueError, match="copy changed"):
        prepare_desktop_input(interface, None, "", [{"relativePath": file.name, "kind": "copy", "version": "old"}])


def test_visual_input_is_never_silently_downgraded(tmp_path):
    (tmp_path / "image.png").write_bytes(b"png")
    interface = SimpleNamespace(project_root=tmp_path, _can_attach_inline_images=lambda config: (False, "unsupported"))
    with pytest.raises(ValueError, match="Visual input unavailable"):
        prepare_desktop_input(interface, None, "", [{"relativePath": "image.png"}])


def test_mixed_attachment_content_keeps_the_user_selected_order(tmp_path):
    from PIL import Image
    Image.new("RGB", (2, 2), "red").save(tmp_path / "image.png")
    (tmp_path / "after.txt").write_text("text after image", encoding="utf-8")
    interface = SimpleNamespace(project_root=tmp_path,
        _can_attach_inline_images=lambda config: (True, "supported"),
        _current_inline_media_modalities=lambda config: ["image"])
    content, records = prepare_desktop_input(interface, None, "request", [
        {"relativePath": "image.png"}, {"relativePath": "after.txt"}])
    image_index = next(index for index, part in enumerate(content) if part["type"] == "local_image")
    text_index = next(index for index, part in enumerate(content) if "text after image" in part.get("text", ""))
    assert image_index < text_index
    assert [record["relativePath"] for record in records] == ["image.png", "after.txt"]


def test_review_only_allows_audited_builtin_reads_and_preserves_real_files(tmp_path):
    from reverie.agent.tool_executor import ToolExecutor
    file = tmp_path / "read.txt"
    file.write_text("review content", encoding="utf-8")
    executor = ToolExecutor(tmp_path)
    executor.update_context("desktop_read_only_review", True)
    read = executor.execute("file_ops", {"operation": "read", "path": "read.txt"})
    assert read.success
    for name, arguments in [
        ("file_ops", {"operation": "write", "path": "read.txt", "content": "changed"}),
        ("create_file", {"path": "blocked.txt", "content": "no"}),
        ("command_exec", {"command": "echo should-not-run"}),
        ("str_replace_editor", {"command": "create", "path": "blocked.txt", "file_text": "no"}),
    ]:
        result = executor.execute(name, arguments)
        assert not result.success
        assert "Read-only review" in result.error
    assert file.read_text(encoding="utf-8") == "review content"
    assert not (tmp_path / "blocked.txt").exists()
