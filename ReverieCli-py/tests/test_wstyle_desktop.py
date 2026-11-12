import json
import threading
from types import SimpleNamespace

import pytest
from rich.console import Console

from reverie.cli.input_handler import InputHandler
from reverie.config import Config
from reverie.sdk_bridge import ReverieSdkBridge
from reverie.session.sqlite_manager import SQLiteSessionManager
from reverie.tools.serial_novel import SerialNovelTool
from reverie.writer.style_runtime import WStyleRuntime
from test_wstyles import write_card


def desktop_fixture(root):
    manager = SQLiteSessionManager(root / "sessions", project_root=root)
    first = manager.create_session("First")
    second = manager.create_session("Second")
    runtime = WStyleRuntime(root, app_root=root / "app")
    write_card(runtime.repository, "a", "具体动作")
    write_card(runtime.repository, "b", "主动选择", layer="narrative")
    for session, novel in ((first, "first"), (second, "second")):
        tool = SerialNovelTool({"project_root": root})
        assert tool.execute(action="bootstrap", novel_id=novel, title=novel, brief="Original proof", target_chars=1000).success
        page = manager.get_page(session.id, limit=1)
        manager.update_metadata(session.id, {"writer_project": {"novel_id": novel, "project_dir": "novels/" + novel}}, expected_revision=page["revision"])
    manager.load_session(first.id)
    manager.select_session(second.id)
    interface = SimpleNamespace(project_root=root, config_manager=SimpleNamespace(app_root=root / "app", load=lambda: Config(mode="writer")),
                                session_manager=manager)
    bridge = ReverieSdkBridge.__new__(ReverieSdkBridge)
    bridge.project_root = root
    bridge._run_lock = threading.Lock()
    bridge.ensure_interface = lambda *args: interface
    return bridge, manager, first, second


def test_desktop_command_targets_requested_session_without_changing_loaded_session(tmp_path):
    bridge, manager, first, second = desktop_fixture(tmp_path)
    result = bridge.dispatch({"action": "wstyleCommand", "payload": {"args": "use b", "sessionId": second.id}})
    assert result["type"] == "wstyle.result" and result["success"]
    assert result["data"]["state"]["scope"] == "novel:second"
    assert json.loads((tmp_path / "novels/second/tracking/state.json").read_text(encoding="utf-8"))["active_wstyles"] == ["b"]
    assert "active_wstyles" not in json.loads((tmp_path / "novels/first/tracking/state.json").read_text(encoding="utf-8"))
    assert manager.get_current_session().id == first.id


def test_desktop_uses_saved_mode_and_rejects_colliding_run(tmp_path):
    bridge, manager, _, second = desktop_fixture(tmp_path)
    page = manager.get_page(second.id, limit=1)
    manager.update_metadata(second.id, {"runtime_config": {"settings": {"mode": "reverie"}}}, expected_revision=page["revision"])
    result = bridge.dispatch({"action": "wstyleCommand", "payload": {"args": "off", "sessionId": second.id}})
    assert not result["success"] and "Writer" in result["error"]
    bridge._run_lock.acquire()
    with pytest.raises(ValueError, match="active run"):
        bridge.dispatch({"action": "wstyleCommand", "payload": {"args": "use a", "sessionId": second.id}})
    bridge._run_lock.release()


def test_terminal_completion_handles_multiple_cards_and_keeps_selected_order():
    handler = InputHandler(Console(), command_provider=lambda: {"/wstyle use a": "A", "/wstyle use b": "B", "/wstyle use 双女主": "双女主"})
    assert ("/wstyle use a b", "B") in handler.get_command_completions("/wstyle use a ")
    assert ("/wstyle use a a", "A") not in handler.get_command_completions("/wstyle use a ")
    assert handler.get_command_completions("/wstyle use b 双") == [("/wstyle use b 双女主", "双女主")]
