"""RIU ownership follows SQLite navigation without loading executor history."""

from pathlib import Path
from types import SimpleNamespace

import pytest

from reverie.sdk_bridge import ReverieSdkBridge
from reverie.session import SQLiteSessionManager
from reverie.views import ViewIdentity, ViewStore


@pytest.fixture(params=[False, True], ids=["restarted", "other-history-loaded"])
def selected_view(tmp_path, request):
    base = tmp_path / "state"
    manager = SQLiteSessionManager(base, project_root=tmp_path, navigation=False)
    selected = manager.create_session("Selected conversation")
    other = manager.create_session("Other conversation")
    store = ViewStore(base / "views")
    artifact = tmp_path / "chart.html"
    artifact.write_text("<!doctype html><title>chart</title>", encoding="utf-8")
    views = [store.register(
        artifact_path=str(artifact),
        identity=ViewIdentity(session_id=session.id, turn_id="turn", tool_call_id="chart"),
        title="Chart", summary="Selected chart", workspace_root=tmp_path,
        source_kind="generated",
    ) for session in (selected, other)]
    store.write_state(selected.id, views[0].view_id, state={"filter": "restored"})
    selected.messages = [{"role": "tool", "tool_call_id": "chart",
                          "content": f"Interactive view registered (view_id={views[0].view_id}, revision=1)."}]
    manager.save_session(selected)

    manager = SQLiteSessionManager(base, project_root=tmp_path, navigation=False)
    if request.param:
        manager.load_session(other.id)
    loaded = manager.get_current_session()
    interface = SimpleNamespace(session_manager=manager, agent=None)
    bridge = ReverieSdkBridge.__new__(ReverieSdkBridge)
    bridge.project_root = tmp_path
    bridge.ensure_interface = lambda *args, **kwargs: interface
    bridge._view_store = lambda: store
    bridge.sessions_payload = lambda: {}
    response = bridge.dispatch({"action": "getSession", "payload": {"sessionId": selected.id}})
    assert response["session"]["id"] == selected.id
    assert manager.selected_session_id() == selected.id
    assert manager.get_current_session() is loaded
    return SimpleNamespace(bridge=bridge, interface=interface, manager=manager, loaded=loaded, store=store,
                           selected=selected, other=other, view=views[0], other_view=views[1])


@pytest.mark.parametrize("action", ["getView", "setViewState", "updateViewModelContext"])
def test_selected_view_survives_lazy_session_loading(selected_view, action):
    env = selected_view
    payload = {"sessionId": env.selected.id, "viewId": env.view.view_id, "revision": 1,
               "state": {"filter": "updated"}, "baseRevision": 1, "summary": "Selected row"}
    response = env.bridge.dispatch({"action": action, "payload": payload})
    if action == "getView":
        assert response["view"]["sessionId"] == env.selected.id
        assert response["view"]["state"]["state"] == {"filter": "restored"}
        assert Path(response["resolved"]["directory"]).is_relative_to(env.store.views_root / env.selected.id)
    elif action == "setViewState":
        assert response["revision"] == 2
        assert env.store.read_state(env.selected.id, env.view.view_id)["state"] == {"filter": "updated"}
    else:
        assert response["status"] == "stored"
        assert env.store.read_model_context(env.selected.id, env.view.view_id)["summary"] == "Selected row"
    assert env.manager.get_current_session() is env.loaded
    assert env.manager.selected_session_id() == env.selected.id


@pytest.mark.parametrize("action", ["getView", "setViewState", "updateViewModelContext"])
@pytest.mark.parametrize("wrong_owner", ["session", "view"])
def test_selected_view_rejects_another_conversation(selected_view, action, wrong_owner):
    env = selected_view
    payload = {"sessionId": env.selected.id, "viewId": env.view.view_id, "revision": 1,
               "state": {"filter": "forged"}, "baseRevision": 1, "summary": "Forged row"}
    if wrong_owner == "session":
        payload["sessionId"] = env.other.id
        error = "different session"
    else:
        payload["viewId"] = env.other_view.view_id
        error = "not stored"
    with pytest.raises(ValueError, match=error):
        env.bridge.dispatch({"action": action, "payload": payload})
    assert env.store.read_state(env.selected.id, env.view.view_id)["state"] == {"filter": "restored"}
    assert env.store.read_model_context(env.selected.id, env.view.view_id) is None
    assert env.manager.get_current_session() is env.loaded


def test_fork_selects_the_returned_conversation_and_restores_its_view(selected_view):
    env = selected_view
    forked = env.bridge.dispatch({"action": "forkSession", "payload": {
        "sessionId": env.selected.id, "messageCount": 1,
    }})["session"]
    assert env.manager.selected_session_id() == forked["id"]
    assert env.interface._view_session_id == forked["id"]
    response = env.bridge.dispatch({"action": "getView", "payload": {
        "sessionId": forked["id"], "viewId": env.view.view_id, "revision": 1,
    }})
    assert response["view"]["state"]["state"] == {"filter": "restored"}
    assert response["view"]["toolCalls"] == []
    restored = env.bridge.dispatch({"action": "deleteSession", "payload": {
        "sessionId": forked["id"], "confirmed": True,
    }})["session"]
    assert restored["id"] == env.selected.id
    assert env.manager.selected_session_id() == restored["id"]
    assert env.interface._view_session_id == restored["id"]
    assert env.bridge.dispatch({"action": "getView", "payload": {
        "sessionId": restored["id"], "viewId": env.view.view_id,
    }})["view"]["sessionId"] == restored["id"]


def test_bulk_delete_selects_the_surviving_conversation(selected_view):
    env = selected_view
    survivor = env.bridge.dispatch({"action": "deleteSessions", "payload": {
        "sessionIds": [env.selected.id], "confirmed": True,
    }})["session"]
    assert survivor["id"] == env.other.id
    assert env.manager.selected_session_id() == survivor["id"]
    assert env.interface._view_session_id == survivor["id"]
    assert env.bridge.dispatch({"action": "getView", "payload": {
        "sessionId": survivor["id"], "viewId": env.other_view.view_id,
    }})["view"]["sessionId"] == survivor["id"]


def test_bulk_delete_all_conversations_returns_to_a_draft(selected_view):
    env = selected_view
    response = env.bridge.dispatch({"action": "deleteSessions", "payload": {
        "sessionIds": [env.selected.id, env.other.id], "confirmed": True,
    }})
    assert response["session"] is None
    assert env.manager.selected_session_id() == ""
    assert env.interface._view_session_id is None
    assert env.interface._view_draft is True


def test_renaming_a_background_conversation_preserves_view_selection(selected_view):
    env = selected_view
    response = env.bridge.dispatch({"action": "renameSession", "payload": {
        "sessionId": env.other.id, "name": "Renamed background",
    }})
    assert response["updated_session"]["id"] == env.other.id
    assert response["session"]["id"] == env.selected.id
    assert env.manager.selected_session_id() == env.selected.id
    assert env.interface._view_session_id == env.selected.id
    assert env.bridge.dispatch({"action": "getView", "payload": {
        "sessionId": env.selected.id, "viewId": env.view.view_id,
    }})["view"]["sessionId"] == env.selected.id


def test_rewind_selects_the_target_and_keeps_only_visible_views(selected_view):
    env = selected_view
    env.other.messages = [{"role": "tool", "tool_call_id": "other-chart",
                           "content": f"Interactive view registered (view_id={env.other_view.view_id}, revision=1)."}]
    env.manager.save_session(env.other)
    kept = env.bridge.dispatch({"action": "rewindSession", "payload": {
        "sessionId": env.other.id, "messageCount": 1, "confirmed": True,
    }})["session"]
    assert env.manager.selected_session_id() == kept["id"]
    assert env.interface._view_session_id == kept["id"]
    assert env.bridge.dispatch({"action": "getView", "payload": {
        "sessionId": kept["id"], "viewId": env.other_view.view_id,
    }})["view"]["sessionId"] == kept["id"]
    env.bridge.dispatch({"action": "rewindSession", "payload": {
        "sessionId": kept["id"], "messageCount": 0, "confirmed": True,
    }})
    with pytest.raises(ValueError, match="hidden by session rewind"):
        env.bridge.dispatch({"action": "getView", "payload": {
            "sessionId": kept["id"], "viewId": env.other_view.view_id,
        }})
