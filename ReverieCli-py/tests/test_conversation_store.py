import json
from concurrent.futures import ThreadPoolExecutor

import pytest

from reverie.session.sqlite_manager import SQLiteSessionManager


def test_background_save_does_not_change_navigation(tmp_path):
    foreground = SQLiteSessionManager(tmp_path, project_root=tmp_path)
    first = foreground.create_session("first")
    second = foreground.create_session("second")
    worker = SQLiteSessionManager(tmp_path, project_root=tmp_path, navigation=False)
    session = worker.load_session(first.id)
    session.messages.append({"role": "assistant", "content": "completed in background"})
    worker.save_session(session)
    restored = SQLiteSessionManager(tmp_path, project_root=tmp_path)
    assert restored.restore_last_session().id == second.id
    assert restored.load_session(first.id).messages[-1]["content"] == "completed in background"


def test_stale_background_append_preserves_updated_configuration(tmp_path):
    first = SQLiteSessionManager(tmp_path, project_root=tmp_path)
    session = first.create_session("task")
    worker = SQLiteSessionManager(tmp_path, project_root=tmp_path, navigation=False)
    stale = worker.load_session(session.id)
    session.metadata["runtime_config"] = {"model": "second"}
    first.save_session(session)
    stale.messages.append({"role": "assistant", "content": "result"})
    worker.save_session(stale)
    saved = first.load_session(session.id)
    assert saved.metadata["runtime_config"] == {"model": "second"}
    assert saved.messages[-1]["content"] == "result"


def test_conflicting_history_replacement_is_rejected(tmp_path):
    first = SQLiteSessionManager(tmp_path, project_root=tmp_path)
    session = first.create_session()
    session.messages.append({"role": "user", "content": "original"})
    first.save_session(session)
    second = SQLiteSessionManager(tmp_path, project_root=tmp_path, navigation=False)
    stale = second.load_session(session.id)
    session.messages[0]["content"] = "new version"
    first.save_session(session)
    stale.messages[0]["content"] = "stale overwrite"
    with pytest.raises(ValueError, match="revision|conflict"):
        second.save_session(stale)
    assert first.load_session(session.id).messages[0]["content"] == "new version"


def test_agent_surfaces_a_transactional_history_conflict(tmp_path):
    from types import SimpleNamespace
    from reverie.agent.agent import ReverieAgent
    store = SQLiteSessionManager(tmp_path)
    session = store.create_session()
    session.messages = [{'role':'user','content':'original'}]
    store.save_session(session)
    worker = SQLiteSessionManager(tmp_path, navigation=False)
    worker.load_session(session.id)
    session.messages[0]['content'] = 'newer user history'
    store.save_session(session)
    agent = object.__new__(ReverieAgent)
    agent.tool_executor = SimpleNamespace(context={'session_manager':worker})
    agent.messages = [{'role':'user','content':'stale worker replacement'}]
    with pytest.raises(ValueError, match='revision conflict'):
        agent._persist_history_to_session()
    assert store.load_session(session.id).messages[0]['content'] == 'newer user history'


def test_context_segmentation_keeps_identity_configuration_and_lossless_history(tmp_path):
    store = SQLiteSessionManager(tmp_path)
    session = store.create_session('Long task')
    session.messages = [{'role':'user','content':f'Original {index}'} for index in range(100)]
    session.metadata['runtime_config'] = {'model_ref':{'source':'fixture','model':'chosen'}}
    store.save_session(session)
    config_versions = store.configuration_history(session.id)
    segmented = store.rotate_session('Stage summary', handoff_packet={'data':{'pending':'continue'}})
    assert segmented.id == session.id
    assert store.selected_session_id() == session.id
    assert len(segmented.messages) == 1
    assert segmented.metadata['runtime_config']['model_ref']['model'] == 'chosen'
    segmented.messages.append({'role':'assistant','content':'Result'})
    store.save_session(segmented)
    restored = SQLiteSessionManager(tmp_path)
    active = restored.load_session(session.id)
    assert len(active.messages) == 2
    assert restored.get_page(session.id)['total'] == 102
    assert restored.get_page(session.id,before=100,limit=100)['messages'][0]['content'] == 'Original 0'
    assert restored.configuration_history(session.id) == config_versions
    active.messages[0]['content'] = 'Corrected stage summary'
    restored.save_session(active)
    assert restored.get_page(session.id)['total'] == 102
    target = restored.export_current_session(tmp_path/'export.json','json')
    exported = json.loads(target.read_text(encoding='utf-8'))
    assert len(exported['messages']) == 102
    assert exported['messages'][0]['content'] == 'Original 0'
    fork = restored.fork_current_session(message_count=20)
    assert len(fork.messages) == 20
    assert fork.metadata['runtime_config'] == active.metadata['runtime_config']
    restored.load_session(session.id)
    rewound = restored.rewind_current_session(50)
    assert len(rewound.messages) == 50
    assert restored.get_page(session.id)['total'] == 50
    assert rewound.metadata['runtime_config'] == active.metadata['runtime_config']


def test_segmented_concurrent_appends_keep_the_prefix_and_active_context(tmp_path):
    store = SQLiteSessionManager(tmp_path)
    session = store.create_session()
    session.messages = [{'role':'user','content':'Original request'}]
    store.save_session(session)
    store.rotate_session('Summary')
    other = SQLiteSessionManager(tmp_path,navigation=False)
    stale = other.load_session(session.id)
    store.append_messages(session.id,[{'role':'user','content':'New user reply'}],event_id='reply')
    stale.messages.append({'role':'assistant','content':'Background result'})
    other.save_session(stale)
    assert len(stale.messages) == 3
    assert [message['content'] for message in store.get_page(session.id)['messages']] == ['Original request',stale.messages[0]['content'],'New user reply','Background result']


def test_pending_context_replay_is_not_saved_as_a_second_user_message(tmp_path):
    store = SQLiteSessionManager(tmp_path)
    session = store.create_session()
    session.messages = [{'role':'user','content':'Original request'}]
    store.save_session(session)
    store.rotate_session('Summary of the pending request')
    store.update_messages([*session.messages,{'role':'user','content':'Original request','context_replay':True},{'role':'assistant','content':'Verified result'}])
    history = store.get_page(session.id)['messages']
    assert len(history) == 3
    assert [message['content'] for message in history if message['role']=='user'] == ['Original request']


def test_four_managers_append_without_losing_conversations(tmp_path):
    def work(index):
        manager = SQLiteSessionManager(tmp_path, project_root=tmp_path, navigation=False)
        session = manager.create_session(str(index))
        for turn in range(15):
            session.messages.append({"role": "assistant", "content": f"{index}:{turn}"})
            manager.save_session(session)
        return session.id
    with ThreadPoolExecutor(max_workers=4) as pool:
        ids = list(pool.map(work, range(4)))
    manager = SQLiteSessionManager(tmp_path, project_root=tmp_path)
    assert {item.id for item in manager.list_sessions()} == set(ids)
    for session_id in ids:
        assert len(manager.load_session(session_id).messages) == 15


def test_legacy_migration_is_repeatable_and_keeps_original_bytes(tmp_path):
    directory = tmp_path / "sessions"
    directory.mkdir()
    original = {"id": "old", "name": "legacy", "created_at": "2026-01-01", "updated_at": "2026-01-02", "messages": [{"role": "Reverie", "content": "原文"}], "metadata": {"custom": "keep"}}
    path = directory / "old.json"
    path.write_text(json.dumps(original), encoding="utf-8")
    before = path.read_bytes()
    for _ in range(2):
        manager = SQLiteSessionManager(tmp_path, project_root=tmp_path)
        assert manager.load_session("old").messages[0]["role"] == "assistant"
        assert manager.load_session("old").metadata["custom"] == "keep"
        assert len(manager.list_sessions()) == 1
    assert path.read_bytes() == before


def test_paging_does_not_load_entire_transcript(tmp_path):
    manager = SQLiteSessionManager(tmp_path, project_root=tmp_path)
    session = manager.create_session()
    session.messages = [{"role": "user", "content": str(i)} for i in range(10000)]
    manager.save_session(session)
    page = manager.get_page(session.id, limit=60)
    assert len(page["messages"]) == 60
    assert page["messages"][0]["content"] == "9940"
    assert page["total"] == 10000
    assert page["before"] == 9940


def test_incremental_events_deduplicate_and_reject_cross_conversation_replay(tmp_path):
    manager = SQLiteSessionManager(tmp_path)
    first = manager.create_session()
    second = manager.create_session()
    messages = [{'role':'user','content':'同一个事件'}]
    manager.append_messages(first.id,messages,event_id='event')
    manager.append_messages(first.id,messages,event_id='event')
    assert manager.get_page(first.id)['total'] == 1
    with pytest.raises(ValueError,match='identity'):
        manager.append_messages(second.id,messages,event_id='event')
    with pytest.raises(ValueError,match='identity'):
        manager.append_messages(first.id,[{'role':'user','content':'changed'}],event_id='event')
    assert manager.get_page(second.id)['total'] == 0


def test_failed_append_rolls_back_event_identity_and_history(tmp_path):
    import sqlite3
    manager = SQLiteSessionManager(tmp_path)
    session = manager.create_session()
    with manager.connect() as db:
        db.execute("CREATE TRIGGER fail_write BEFORE INSERT ON messages BEGIN SELECT RAISE(ABORT,'disk write failed'); END")
    with pytest.raises(sqlite3.IntegrityError,match='disk write failed'):
        manager.append_messages(session.id,[{'role':'user','content':'retry'}],event_id='retry')
    assert manager.get_page(session.id)['total'] == 0
    with manager.connect() as db:
        assert db.execute('SELECT count(*) FROM conversation_events').fetchone()[0] == 0
        db.execute('DROP TRIGGER fail_write')
    manager.append_messages(session.id,[{'role':'user','content':'retry'}],event_id='retry')
    assert manager.get_page(session.id)['total'] == 1


def test_stream_chunks_survive_restart_without_rewriting_previous_chunks(tmp_path):
    manager = SQLiteSessionManager(tmp_path)
    session = manager.create_session()
    for fragment in ['first',' second',' third']:
        manager.write_stream(session.id,'run','assistant',fragment)
    with manager.connect() as db:
        assert db.execute('SELECT count(*) FROM stream_chunks').fetchone()[0] == 3
    recovered = SQLiteSessionManager(tmp_path).read_streams(session.id)
    assert recovered[0]['content'] == 'first second third'
    assert recovered[0]['interrupted'] is True


def test_queued_task_retains_its_configuration_version_and_terminal_state(tmp_path):
    manager = SQLiteSessionManager(tmp_path)
    session = manager.create_session()
    first = {'version':1,'model_ref':{'source':'standard','model':'first'}}
    manager.update_metadata(session.id,{'runtime_config':first},expected_revision=1)
    manager.register_run(session.id,'run',first,2,str(tmp_path))
    manager.update_metadata(session.id,{'runtime_config':{'version':1,'model_ref':{'source':'standard','model':'second'}}},expected_revision=2)
    assert manager.list_runs(session.id)[0]['configuration'] == first
    assert manager.list_runs(session.id)[0]['configuration_revision'] == 2
    assert manager.update_run(session.id,'run','running',expected_revision=1) == 2
    with pytest.raises(ValueError,match='revision'):
        manager.update_run(session.id,'run','completed',expected_revision=1)
    manager.update_run(session.id,'run','completed',expected_revision=2,result={'verified':True})
    with pytest.raises(ValueError,match='finalized'):
        manager.update_run(session.id,'run','running',expected_revision=3)
    restored = SQLiteSessionManager(tmp_path).list_runs(session.id)[0]
    assert restored['state'] == 'completed'
    assert restored['result'] == {'verified':True}


def test_full_text_search_pages_and_tracks_replacement_without_stale_results(tmp_path):
    manager=SQLiteSessionManager(tmp_path)
    session=manager.create_session()
    manager.append_messages(session.id,[{'role':'user','content':'这是长期主线的原文 '+str(i)} for i in range(5)],event_id='search')
    assert len(manager.search_sessions('长期主线',limit=2))==2
    assert manager.search_sessions('长期主线',limit=2,offset=2)[0]['message_index']==2
    session=manager.load_session(session.id)
    session.messages=[{'role':'user','content':'replacement'}]
    manager.save_session(session)
    assert manager.search_sessions('长期主线')==[]
    assert len(manager.search_sessions('replacement'))==1
    manager.delete_session(session.id)
    assert manager.search_sessions('replacement')==[]


def test_restart_recovers_only_queued_tasks_with_fixed_input(tmp_path):
    manager=SQLiteSessionManager(tmp_path)
    session=manager.create_session()
    config={'model_ref':{'model':'fixed'}}
    manager.update_metadata(session.id,{'runtime_config':config},expected_revision=1)
    for task in ['queued','active']:
        manager.register_run(session.id,task,config,2,str(tmp_path),request={'prompt':task,'runType':'prompt'})
    manager.update_run(session.id,'active','running',expected_revision=1)
    restored=SQLiteSessionManager(tmp_path)
    pending=restored.recover_runs()
    assert [run['id'] for run in pending]==['queued']
    assert pending[0]['request']['prompt']=='queued'
    assert {run['id']:run['state'] for run in restored.list_runs(session.id)}=={'queued':'queued','active':'interrupted'}


def test_stream_buffer_bounds_large_unicode_fragments_without_losing_bytes(tmp_path):
    from reverie.session.streams import StreamBuffer
    manager=SQLiteSessionManager(tmp_path)
    session=manager.create_session()
    buffer=StreamBuffer(manager,session.id,'large')
    text='前缀'+('中文🙂'*20000)
    buffer.append('assistant',text)
    buffer.flush()
    with manager.connect() as db:
        chunks=[row[0] for row in db.execute('SELECT content FROM stream_chunks ORDER BY sequence')]
    assert all(len(chunk.encode('utf-8'))<=16*1024 for chunk in chunks)
    assert ''.join(chunks)==text


def test_sqlite_full_error_rolls_back_event_and_message(tmp_path,monkeypatch):
    from contextlib import contextmanager
    import sqlite3
    manager=SQLiteSessionManager(tmp_path)
    session=manager.create_session()
    manager.append_messages(session.id,[{'role':'user','content':'Confirmed saved'}],event_id='saved')
    connect=manager.connect
    @contextmanager
    def full_database():
        with connect() as db:
            pages=db.execute('PRAGMA page_count').fetchone()[0]
            db.execute(f'PRAGMA max_page_count={pages}')
            yield db
    monkeypatch.setattr(manager,'connect',full_database)
    with pytest.raises(sqlite3.OperationalError,match='full'):
        manager.append_messages(session.id,[{'role':'assistant','content':'Unconfirmed '*100000}],event_id='failed')
    monkeypatch.setattr(manager,'connect',connect)
    assert manager.get_page(session.id)['messages'][0]['content']=='Confirmed saved'
    assert manager.get_page(session.id)['total']==1
    with manager.connect() as db:
        assert db.execute("SELECT count(*) FROM conversation_events WHERE id='failed'").fetchone()[0]==0


def test_queued_configuration_matches_numeric_json_roundtrip(tmp_path):
    manager=SQLiteSessionManager(tmp_path)
    session=manager.create_session()
    configuration={'version':1,'settings':{'temperature':1.0,'timeout':60.0}}
    revision=manager.update_metadata(session.id,{'runtime_config':configuration},expected_revision=1)
    transmitted={'version':1,'settings':{'temperature':1,'timeout':60}}
    assert manager.register_run(session.id,'transport',configuration,revision,str(tmp_path))==1
    assert manager.register_run(session.id,'transport',transmitted,revision,str(tmp_path))==1
    assert manager.list_runs(session.id)[0]['configuration_revision']==revision


def test_unread_completion_survives_restart_without_changing_navigation(tmp_path):
    manager=SQLiteSessionManager(tmp_path)
    first=manager.create_session('First');second=manager.create_session('Second')
    manager.select_session(second.id)
    configuration={'version':1}
    revision=manager.update_metadata(first.id,{'runtime_config':configuration},expected_revision=1)
    manager.register_run(first.id,'background',configuration,revision,str(tmp_path))
    manager.update_run(first.id,'background','completed',expected_revision=1)
    restored=SQLiteSessionManager(tmp_path)
    assert restored.unread_session_ids()==[first.id]
    assert restored.selected_session_id()==second.id
    restored.mark_read(first.id)
    assert restored.selected_session_id()==second.id
    assert SQLiteSessionManager(tmp_path).unread_session_ids()==[]
@pytest.mark.parametrize('original',[b'{"id":"broken","messages":[',b'[]',b'\xff\xfe'])
def test_malformed_legacy_file_does_not_block_healthy_listing_and_is_reported(tmp_path,caplog,original):
    import logging
    manager=SQLiteSessionManager(tmp_path)
    healthy=manager.create_session('Healthy SQLite conversation')
    broken=manager.sessions_dir/'broken.json'
    broken.write_bytes(original)
    legacy=healthy.to_dict();legacy['id']='legacy-healthy';legacy['name']='Healthy legacy conversation'
    legacy_path=manager.sessions_dir/'legacy-healthy.json'
    legacy_bytes=json.dumps(legacy).encode('utf-8');legacy_path.write_bytes(legacy_bytes)
    with caplog.at_level(logging.WARNING):
        listed=manager.list_sessions()
    assert healthy.id in {item.id for item in listed}
    assert 'legacy-healthy' in {item.id for item in listed}
    assert str(broken) in caplog.text
    assert broken.read_bytes()==original
    assert legacy_path.read_bytes()==legacy_bytes
    with pytest.raises(ValueError,match='broken.json'):
        manager.load_session('broken')
