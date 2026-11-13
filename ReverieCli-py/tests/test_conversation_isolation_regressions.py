"""Persistence reproductions for independent background conversations."""

import copy
import json
from types import SimpleNamespace

import pytest

from reverie.config import Config, ModelConfig
from reverie.sdk_bridge import ReverieSdkBridge
from reverie.session import SQLiteSessionManager as SessionManager


@pytest.mark.parametrize('legacy_note',[False,True])
def test_workspace_memory_refresh_keeps_message_ids_and_sequences(tmp_path,legacy_note):
    from reverie.cli.interface import ReverieInterface
    manager=SessionManager(tmp_path/'state',project_root=tmp_path)
    session=manager.create_session('Stable history')
    session.messages=[{'role':'user','content':'Keep my work.'},{'role':'assistant','content':'Confirmed.'}]
    if legacy_note:
        session.messages.insert(0,{'role':'system','content':'[WORKSPACE GLOBAL MEMORY]\nold saved note'})
    manager.save_session(session)
    with manager.connect() as db:
        original=[tuple(row) for row in db.execute('SELECT sequence,id,payload FROM messages WHERE session_id=? ORDER BY sequence',(session.id,))]
    interface=SimpleNamespace(session_manager=manager,_runtime_scope='workspace',agent=SimpleNamespace(workspace_memory_context='stale'),
        memory_indexer=SimpleNamespace(refresh_session=lambda _id:None,build_workspace_memory_summary=lambda **_: 'Current project facts.'))
    ReverieInterface._sync_workspace_memory_message(interface,session)
    ReverieInterface._sync_workspace_memory_message(interface,session)
    with manager.connect() as db:
        assert [tuple(row) for row in db.execute('SELECT sequence,id,payload FROM messages WHERE session_id=? ORDER BY sequence',(session.id,))]==original
    assert 'Current project facts.' in interface.agent.workspace_memory_context
    interface._runtime_scope='aio'
    ReverieInterface._sync_workspace_memory_message(interface,session)
    assert interface.agent.workspace_memory_context==''


def test_model_uses_fresh_workspace_memory_without_replaying_legacy_notes(tmp_path,monkeypatch):
    from reverie.agent.agent import ReverieAgent
    monkeypatch.setenv('REVERIE_APP_ROOT',str(tmp_path/'app-root'))
    agent=ReverieAgent(base_url='http://127.0.0.1:9/v1',api_key='fixture',model='fixture',project_root=tmp_path,config=Config(auto_index=False))
    monkeypatch.setattr(agent,'_memory_context_package_message',lambda:None)
    history=[{'role':'system','content':'[WORKSPACE GLOBAL MEMORY]\nobsolete saved facts'}, {'role':'user','content':'Use current facts.'}]
    agent.set_history(copy.deepcopy(history))
    agent.workspace_memory_context='[WORKSPACE GLOBAL MEMORY]\ncorrected project facts'
    request=agent._build_messages()
    assert any(message.get('content')==agent.workspace_memory_context for message in request)
    assert not any(message.get('content')==history[0]['content'] for message in request)
    assert agent.get_history()==history


def test_deleting_background_session_preserves_navigation_selection(tmp_path,monkeypatch):
    manager=SessionManager(tmp_path/'state',project_root=tmp_path)
    background=manager.create_session('Background')
    viewed=manager.create_session('Viewed')
    manager.select_session(viewed.id)
    interface=SimpleNamespace(session_manager=manager,agent=None,_view_session_id=viewed.id)
    bridge=ReverieSdkBridge()
    monkeypatch.setattr(bridge,'ensure_interface',lambda *_:interface)
    monkeypatch.setattr(bridge,'sessions_payload',lambda:{})
    monkeypatch.setattr(bridge,'_drop_view_artifacts',lambda *_:None)
    manager.load_session(background.id)
    response=bridge.dispatch({'action':'deleteSession','payload':{'sessionId':background.id,'confirmed':True}})
    assert response['session']['id']==viewed.id
    assert manager.selected_session_id()==viewed.id


def test_legacy_archives_migrate_from_host_settings_with_separate_core_storage(tmp_path,monkeypatch):
    manager=SessionManager(tmp_path/'core-state',project_root=tmp_path)
    archived=manager.create_session('Archived')
    settings=tmp_path/'host-settings.json'
    settings.write_text(json.dumps({'ui':{'archivedSessions':{str(tmp_path):[archived.id]}}}),encoding='utf-8')
    monkeypatch.setenv('REVERIE_DESKTOP_SETTINGS',str(settings))
    interface=SimpleNamespace(session_manager=manager,agent=None)
    bridge=ReverieSdkBridge()
    bridge.project_root=tmp_path
    monkeypatch.setattr(bridge,'ensure_interface',lambda *_:interface)
    assert bridge.sessions_payload()['archive_states']=={archived.id:True}


def test_stale_background_save_does_not_discard_newer_conversation_configuration(tmp_path):
    viewer = SessionManager(tmp_path / "state", project_root=tmp_path)
    original = viewer.create_session("Independent conversation")
    original.messages = [{"role": "user", "content": "Investigate this project."}]
    viewer.save_session(original)
    worker = SessionManager(tmp_path / "state", project_root=tmp_path)
    stale = worker.load_session(original.id)

    original.metadata["runtime_config"] = {"model": "chosen-after-launch", "rules": "Use Chinese."}
    viewer.save_session(original)
    stale.messages.append({"role": "assistant", "content": "Investigation finished."})
    try:
        worker.save_session(stale)
    except RuntimeError:
        # A version conflict may reject the stale save instead of merging it.
        pass

    restored = SessionManager(tmp_path / "state", project_root=tmp_path).load_session(original.id)
    assert restored.metadata["runtime_config"] == {
        "model": "chosen-after-launch", "rules": "Use Chinese."
    }


def test_stale_background_save_does_not_discard_a_newer_user_message(tmp_path):
    viewer = SessionManager(tmp_path / "state", project_root=tmp_path)
    original = viewer.create_session("Conversation with new input")
    original.messages = [{"role": "user", "content": "Start the investigation."}]
    viewer.save_session(original)
    worker = SessionManager(tmp_path / "state", project_root=tmp_path)
    stale = worker.load_session(original.id)

    original.messages.append({"role": "user", "content": "Keep the existing files unchanged."})
    viewer.save_session(original)
    stale.messages.append({"role": "assistant", "content": "Investigation finished."})
    try:
        worker.save_session(stale)
    except RuntimeError:
        pass

    restored = SessionManager(tmp_path / "state", project_root=tmp_path).load_session(original.id)
    assert "Keep the existing files unchanged." in [m["content"] for m in restored.messages]


def test_background_prompt_loading_does_not_replace_the_last_viewed_conversation(tmp_path, monkeypatch):
    viewer = SessionManager(tmp_path / "state", project_root=tmp_path)
    background = viewer.create_session("Background task")
    selected = viewer.create_session("Conversation the user is viewing")
    worker = SessionManager(tmp_path / "state", project_root=tmp_path)
    interface = SimpleNamespace(
        session_manager=worker,
        run_prompt_once=lambda *_args, **_kwargs: SimpleNamespace(to_dict=lambda: {"success": True}),
    )
    bridge = ReverieSdkBridge()
    bridge.project_root = tmp_path
    monkeypatch.setattr(bridge, "ensure_interface", lambda *_args: interface)
    monkeypatch.setattr(bridge, "_sync_skill_pins", lambda _interface: None)
    monkeypatch.setattr(bridge, "sessions_payload", lambda: {})
    monkeypatch.setattr(bridge, "recovery_payload", lambda: {})

    bridge._dispatch_prompt("background-request", "runPrompt", {
        "sessionId": background.id, "projectRoot": str(tmp_path), "prompt": "Continue."
    })

    assert viewer.selected_session_id() == selected.id


def test_selecting_a_conversation_model_does_not_change_workspace_defaults(tmp_path, monkeypatch):
    sessions = SessionManager(tmp_path / "state", project_root=tmp_path)
    conversation = sessions.create_session("Uses a different model")
    conversation.messages = [{"role": "user", "content": "Existing transcript"}]
    sessions.save_session(conversation)
    selected = sessions.create_session("Still selected")
    defaults = Config(models=[
        ModelConfig("first", "First", "http://127.0.0.1:9/v1"),
        ModelConfig("second", "Second", "http://127.0.0.1:9/v1"),
    ], active_model_source="standard", active_model_index=0)
    persisted = {"config": defaults}

    def save(config):
        persisted["config"] = copy.deepcopy(config)

    interface = SimpleNamespace(
        session_manager=sessions,
        project_data_dir=tmp_path / "state",
        config_manager=SimpleNamespace(load=lambda: copy.deepcopy(persisted["config"]), save=save),
        agent=None,
    )
    bridge = ReverieSdkBridge()
    bridge.project_root = tmp_path
    monkeypatch.setattr(bridge, "ensure_interface", lambda *_args: interface)
    monkeypatch.setattr(bridge, "model_sources_payload", lambda **_kwargs: {})
    monkeypatch.setattr(bridge, "workspace_payload", lambda: {})

    def unexpected_history_io(*args, **kwargs):
        raise AssertionError("Changing models must only update conversation metadata")

    with monkeypatch.context() as metadata_only:
        metadata_only.setattr(sessions, "load_session", unexpected_history_io)
        metadata_only.setattr(sessions, "save_session", unexpected_history_io)
        response = bridge.dispatch({"action": "selectModel", "payload": {
            "sessionId": conversation.id, "source": "standard", "modelId": "1"
        }})

    assert response["selected"]["model"] == "second"
    assert persisted["config"].active_model.model == "first"
    assert sessions.selected_session_id() == selected.id
    page = sessions.get_page(conversation.id)
    assert page["metadata"]["runtime_config"]["model_ref"]["model"] == "second"
    assert page["messages"] == conversation.messages
