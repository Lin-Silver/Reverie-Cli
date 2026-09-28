from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

from reverie.sdk_bridge import ReverieSdkBridge
from reverie.session.manager import SessionManager


def make_bridge(tmp_path: Path):
    manager = SessionManager(tmp_path / "state", project_root=tmp_path)
    session = manager.create_session("Active conversation")
    manager.update_messages([{"role": "user", "content": "hello"}])
    agent = SimpleNamespace(set_history=Mock(), describe_context_usage=Mock(return_value={"total_tokens": 10}))
    interface = SimpleNamespace(
        agent=agent, session_manager=manager, _sync_workspace_memory_message=Mock(),
        config_manager=SimpleNamespace(load=lambda: SimpleNamespace(active_model=None)), _init_agent=Mock(),
    )
    bridge = ReverieSdkBridge()
    bridge.project_root = tmp_path.resolve()
    bridge.interface = interface
    return bridge, interface, session


def test_context_budget_read_does_not_rewrite_or_index_history(tmp_path: Path):
    bridge, interface, session = make_bridge(tmp_path)
    paths = [interface.session_manager.sessions_dir / f"{session.id}.json", interface.session_manager.state_path]
    before = [(path.read_bytes(), path.stat().st_mtime_ns) for path in paths]
    result = bridge.dispatch({"action": "getContextUsage", "payload": {"sessionId": session.id}})
    assert result["usage"] == {"total_tokens": 10}
    assert [(path.read_bytes(), path.stat().st_mtime_ns) for path in paths] == before
    interface._sync_workspace_memory_message.assert_not_called()
    interface.agent.set_history.assert_called_once_with(session.messages)


def test_late_budget_request_does_not_reselect_the_previous_conversation(tmp_path: Path):
    bridge, interface, old = make_bridge(tmp_path)
    active = interface.session_manager.create_session("Selected afterward")
    result = bridge.dispatch({"action": "getContextUsage", "payload": {"sessionId": old.id}})
    assert result["usage"] is None
    assert interface.session_manager.get_current_session() is active
    interface.agent.describe_context_usage.assert_not_called()


def test_missing_model_does_not_initialize_runtime_for_advisory_statistics(tmp_path: Path):
    bridge, interface, session = make_bridge(tmp_path)
    interface.agent = None
    result = bridge.dispatch({"action": "getContextUsage", "payload": {"sessionId": session.id}})
    assert result["usage"] is None
    interface._init_agent.assert_not_called()


def test_transcript_revision_changes_when_the_saved_history_changes(tmp_path: Path):
    bridge, interface, session = make_bridge(tmp_path)
    request = {"action": "getSession", "payload": {"sessionId": session.id}}
    first = bridge.dispatch(request)["session"]["revision"]
    assert bridge.dispatch(request)["session"]["revision"] == first
    interface.session_manager.update_messages([{"role": "user", "content": "a different prompt"}])
    assert bridge.dispatch(request)["session"]["revision"] != first
