import pytest
from reverie.config import Config,ModelConfig
from reverie.session.runtime_config import capture_runtime_config
from reverie.session.aio_store import AiOStore


def enabled(tmp_path):
    store=AiOStore(tmp_path/'aio')
    snapshot=capture_runtime_config(Config(models=[ModelConfig('test','Test','http://127.0.0.1:9/v1')]))
    store.enable(snapshot)
    return store,snapshot


def test_mainline_and_outbox_are_durable_and_idempotent(tmp_path):
    store,snapshot=enabled(tmp_path)
    store.append('proactive',{'text':'完整主动发言'},event_id='message',visible=True,outbox=True)
    store.append('proactive',{'text':'完整主动发言'},event_id='message',visible=True,outbox=True)
    restored=AiOStore(tmp_path/'aio')
    restored.enable(snapshot)
    assert restored.get_page(restored.mainline_id)['total']==1
    assert restored.claim_message('message')
    assert not restored.claim_message('message')
    assert AiOStore(tmp_path/'aio').pending_messages()==[]
    with pytest.raises(ValueError,match='identity'):
        store.append('proactive',{'text':'different'},event_id='message')


def test_runtime_decision_has_a_separate_identity_from_its_saved_reply(tmp_path,monkeypatch):
    import json
    from types import SimpleNamespace
    from reverie.aio import AiORuntime
    from reverie.agent.agent import ReverieAgent
    config = Config(models=[ModelConfig('test','Test','http://127.0.0.1:9/v1')])
    runtime = AiORuntime(tmp_path)
    runtime.enable(config)
    runtime.store.append('proactive',{'text':'Question'},event_id='question',visible=True,outbox=True)
    runtime.store.reply('question','User answer','saved-reply')
    calls = []
    def decide(_agent,**kwargs):
        calls.append(kwargs)
        return json.dumps({'speech':'Received','tasks':[],'memories':[]})
    monkeypatch.setattr(ReverieAgent,'_process_non_streaming',decide)
    interface = SimpleNamespace(project_root=tmp_path,config_manager=SimpleNamespace(load=lambda:config))
    signal = runtime.store.pending_signals()[0]
    first = runtime.decide(interface,signal,[str(tmp_path)],urgent=True)
    assert first['message_id'] == 'decision:saved-reply-speech'
    runtime.decide(interface,signal,[str(tmp_path)],urgent=True)
    assert len(calls) == 1
    with runtime.store.connect() as db:
        assert db.execute("SELECT kind FROM aio_events WHERE id='saved-reply'").fetchone()[0] == 'user'
        assert db.execute("SELECT kind FROM aio_events WHERE id='decision:saved-reply'").fetchone()[0] == 'decision'


@pytest.mark.parametrize('changes,urgent', [({'proactive':False},False),({'paused':True},True),({'enabled':False},True)])
def test_control_change_during_model_request_prevents_late_dispatch(tmp_path,monkeypatch,changes,urgent):
    import json
    from types import SimpleNamespace
    from reverie.aio import AiORuntime
    from reverie.agent.agent import ReverieAgent
    config=Config(models=[ModelConfig('test','Test','http://127.0.0.1:9/v1')])
    runtime=AiORuntime(tmp_path)
    runtime.enable(config)
    def decide(_agent,**_kwargs):
        runtime.store.control(changes)
        return json.dumps({'speech':'Late speech','tasks':[{'workspace':str(tmp_path),'mode':'reverie','prompt':'Late task','acceptance':'Verified'}],'memories':[]})
    monkeypatch.setattr(ReverieAgent,'_process_non_streaming',decide)
    interface=SimpleNamespace(project_root=tmp_path,config_manager=SimpleNamespace(load=lambda:config))
    assert runtime.decide(interface,{'source':'qualification'},[str(tmp_path)],urgent=urgent)=={'speech':'','tasks':[]}
    assert runtime.store.pending_tasks()==[]
    assert runtime.store.pending_messages()==[]
    assert runtime.store.get_page(runtime.store.mainline_id)['total']==0


def test_task_reply_remains_bound_after_segmentation(tmp_path):
    store,snapshot=enabled(tmp_path)
    task=store.create_task(str(tmp_path),snapshot,'Test the project','All checks pass',task_id='task')
    assert store.create_task(str(tmp_path),snapshot,'Test the project','All checks pass',task_id='task')==task
    store.append('report',{'text':'需要确认'},event_id='question',branch=task['branch'],visible=True,outbox=True)
    store.segment_summary('Current project task is waiting for the user.')
    store.reply('question','继续','reply')
    assert store.get_page(task['branch'])['messages'][-1]['content']=='继续'
    assert store.get_page(store.mainline_id)['total']==0
    assert store.context()['summaries']==['Current project task is waiting for the user.']


def test_mainline_fork_has_independent_workspace_messages_and_configuration(tmp_path):
    store,snapshot=enabled(tmp_path)
    store.append('user',{'text':'Original user input'},event_id='first',visible=True)
    store.append('conversation',{'text':'Original reply'},event_id='second',visible=True)
    source=store.load_session(store.mainline_id)
    before=store.get_page(source.id)
    workspace=tmp_path/'workspace'
    workspace.mkdir()
    forked=store.fork_current_session(workspace=workspace)
    assert forked.id!=source.id
    assert forked.metadata['assistant_id']=='aio'
    assert forked.metadata['workspace_path']==str(workspace.resolve())
    assert forked.metadata['forked_from']==source.id
    assert forked.messages==source.messages
    changed={**snapshot,'rules':'Fork rules'}
    store.update_metadata(forked.id,{'runtime_config':changed},expected_revision=forked._storage_revision)
    store.append_messages(forked.id,[{'role':'user','content':'Fork input'}],event_id='fork-input')
    assert store.get_page(source.id)==before
    restored=AiOStore(store.base_dir)
    assert restored.get_page(forked.id)['metadata']['runtime_config']['rules']=='Fork rules'
    assert restored.get_page(forked.id)['total']==before['total']+1
    assert restored.configuration_history(forked.id)[0]['config']==snapshot


def test_task_fork_preserves_task_workspace_without_reusing_task_identity(tmp_path):
    store,snapshot=enabled(tmp_path)
    original=tmp_path/'original'
    task=store.create_task(str(original),snapshot,'Original work','Verified',task_id='original-task')
    store.load_session(task['branch'])
    forked=store.fork_current_session(workspace=tmp_path/'other')
    assert forked.metadata['workspace_path']==str(original.resolve())
    assert forked.metadata['forked_task_id']=='original-task'
    assert 'task_id' not in forked.metadata
    assert store.pending_tasks()[0]['branch']==task['branch']


def test_mainline_cannot_be_deleted_but_its_fork_can(tmp_path):
    store,snapshot=enabled(tmp_path)
    store.load_session(store.mainline_id)
    forked=store.fork_current_session(workspace=tmp_path)
    with pytest.raises(ValueError,match='mainline cannot be deleted'):
        store.delete_session(store.mainline_id)
    assert store.get_page(store.mainline_id)['metadata']['runtime_config']==snapshot
    assert store.delete_session(forked.id)
    with pytest.raises(ValueError,match='not found'):
        store.get_page(forked.id)


def test_mainline_archive_is_durable_and_follows_assistant_identity(tmp_path):
    store,_=enabled(tmp_path)
    page=store.get_page(store.mainline_id)
    store.update_metadata(store.mainline_id,{'archived':True},expected_revision=page['revision'])
    restored=AiOStore(store.base_dir)
    assert restored.archive_states()=={store.mainline_id:True}
    assert restored.get_page(store.mainline_id)['metadata']['archived']
    restored.segment_summary('Keep the stable mainline')
    assert restored.archive_states()[store.mainline_id]


def test_legacy_archive_import_cannot_reverse_user_unarchive(tmp_path):
    store,_=enabled(tmp_path)
    store.import_legacy_archives([store.mainline_id])
    page=store.get_page(store.mainline_id)
    store.update_metadata(store.mainline_id,{'archived':False},expected_revision=page['revision'])
    restored=AiOStore(store.base_dir)
    restored.import_legacy_archives([store.mainline_id])
    assert restored.archive_states()=={store.mainline_id:False}


def test_sdk_mainline_fork_and_delete_protection(tmp_path,monkeypatch):
    from types import SimpleNamespace
    from reverie.sdk_bridge import ReverieSdkBridge
    store,_=enabled(tmp_path)
    store.append('user',{'text':'Kept mainline'},event_id='input',visible=True)
    interface=SimpleNamespace(session_manager=store,project_root=tmp_path,agent=None,_assistant_owner=True)
    bridge=ReverieSdkBridge()
    monkeypatch.setattr(bridge,'ensure_interface',lambda *_:interface)
    monkeypatch.setattr(bridge,'sessions_payload',lambda:{})
    monkeypatch.setattr(bridge,'_fork_view_artifacts',lambda *_:None)
    response=bridge.dispatch({'action':'forkSession','payload':{'assistantId':'aio','sessionId':store.mainline_id}})
    fork=response['session']
    assert fork['id']!=store.mainline_id
    assert fork['metadata']['workspace_path']==str(tmp_path.resolve())
    with pytest.raises(ValueError,match='cannot be deleted'):
        bridge.dispatch({'action':'deleteSessions','payload':{'assistantId':'aio','confirmed':True,'sessionIds':[fork['id'],store.mainline_id]}})
    assert store.get_page(fork['id'])['total']==1


def test_cli_mainline_fork_copies_history_before_active_segment(tmp_path):
    from reverie.cli.commands import CommandHandler
    from rich.console import Console
    store,_=enabled(tmp_path)
    for index in range(70):
        store.append('user',{'text':str(index)},event_id=f'input-{index}',visible=True)
    store.segment_summary('Earlier conversation')
    store.load_session(store.mainline_id)
    handler=CommandHandler(Console(),{'session_manager':store,'project_root':tmp_path})
    assert handler.cmd_fork('')
    fork=store.get_current_session()
    assert fork.id!=store.mainline_id
    assert len(fork.messages)==70


def test_mainline_export_contains_segments_task_receipts_and_original_events(tmp_path):
    import json
    store,snapshot=enabled(tmp_path)
    task=store.create_task(str(tmp_path),snapshot,'Original task','Exact bytes',task_id='task')
    store.append('report',{'text':'Original result'},event_id='report',branch=task['branch'],visible=True)
    store.segment_summary('Retained summary')
    store.load_session(store.mainline_id)
    target=store.export_current_session(tmp_path/'mainline.json','json')
    records=json.loads(target.read_text(encoding='utf-8'))['assistant_records']
    assert records['tasks'][0]['branch']==task['branch']
    assert records['tasks'][0]['configuration']==snapshot
    assert records['tasks'][0]['acceptance']=='Exact bytes'
    assert records['segments'][0]['summary']=='Retained summary'
    events=[json.loads(line) for line in target.with_name(records['events_file']).read_text(encoding='utf-8').splitlines()]
    assert any(event['id']=='report' and event['payload']['text']=='Original result' for event in events)
    store.export_current_session(tmp_path/'mainline.md','markdown')
    assert 'assistant_records' in (tmp_path/'mainline.md').read_text(encoding='utf-8')


@pytest.mark.parametrize('format_name',['json','markdown'])
def test_export_sanitizes_legacy_task_and_event_configuration_only(tmp_path,format_name):
    import json
    store,snapshot=enabled(tmp_path)
    snapshot['settings']['api_proxy']='http://test-user:old-private@proxy.invalid:8080'
    task=store.create_task(str(tmp_path),snapshot,'Original task','Exact bytes',task_id='legacy-proxy')
    text='Keep literal api_proxy and password in this ordinary event.'
    store.append('report',{'text':text},event_id='original-report',branch=task['branch'],visible=True)
    with store.connect() as db:
        before_tasks=[tuple(row) for row in db.execute('SELECT * FROM aio_tasks')]
        before_events=[tuple(row) for row in db.execute('SELECT * FROM aio_events')]
    store.load_session(store.mainline_id)
    target=store.export_current_session(tmp_path/f'mainline.{format_name}',format_name)
    body=target.read_text(encoding='utf-8')
    companion=target.with_name(target.name+'.aio-events.jsonl')
    events_text=companion.read_text(encoding='utf-8')
    assert 'old-private' not in body and 'old-private' not in events_text
    events=[json.loads(line) for line in events_text.splitlines()]
    created=next(event for event in events if event['kind']=='task.created')
    assert created['payload']['configuration']['settings']['api_proxy']=='http://proxy.invalid:8080'
    assert next(event for event in events if event['id']=='original-report')['payload']['text']==text
    if format_name=='json':
        records=json.loads(body)['assistant_records']
        assert records['tasks'][0]['configuration']['settings']['api_proxy']=='http://proxy.invalid:8080'
        assert records['tasks'][0]['acceptance']=='Exact bytes'
    with store.connect() as db:
        assert [tuple(row) for row in db.execute('SELECT * FROM aio_tasks')]==before_tasks
        assert [tuple(row) for row in db.execute('SELECT * FROM aio_events')]==before_events


def test_deleting_queued_task_cancels_dispatch_and_pending_popup(tmp_path):
    store,snapshot=enabled(tmp_path)
    task=store.create_task(str(tmp_path),snapshot,'Queued task','Verified',task_id='queued')
    store.append('report',{'text':'Queued speech'},event_id='speech',branch=task['branch'],visible=True,outbox=True)
    assert store.delete_session(task['branch'])
    assert not store.pending_tasks()
    assert not store.pending_messages()


@pytest.mark.parametrize('fork',[False,True])
def test_sdk_rejects_task_and_fork_execution_from_another_workspace(tmp_path,monkeypatch,fork):
    from types import SimpleNamespace
    from reverie.sdk_bridge import ReverieSdkBridge
    store,snapshot=enabled(tmp_path)
    owner=tmp_path/'owner'
    owner.mkdir()
    if fork:
        store.load_session(store.mainline_id)
        session_id=store.fork_current_session(workspace=owner).id
    else:
        session_id=store.create_task(str(owner),snapshot,'Owned task','Verified')['branch']
    other=tmp_path/'other'
    other.mkdir()
    interface=SimpleNamespace(session_manager=store,project_root=other,_assistant_owner=True)
    bridge=ReverieSdkBridge()
    monkeypatch.setattr(bridge,'ensure_interface',lambda *_:interface)
    with pytest.raises(ValueError,match='original workspace'):
        bridge._dispatch_prompt('wrong-owner','runPrompt',{'projectRoot':str(other),'assistantId':'aio','sessionId':session_id,'prompt':'Continue'})
    with pytest.raises(ValueError,match='original workspace'):
        bridge.dispatch({'id':'wrong-owner-read','action':'getSession','payload':{'projectRoot':str(other),'assistantId':'aio','sessionId':session_id}})
    assert store.conversation_owners()[session_id]=={'assistant_id':'aio','workspace':str(owner.resolve())}


def test_terminal_refuses_foreign_branch_before_model_or_file_access(tmp_path):
    from reverie.cli.interface import ReverieInterface
    from unittest.mock import Mock
    store,snapshot=enabled(tmp_path)
    owner=tmp_path/'owner'
    task=store.create_task(str(owner),snapshot,'Owned task','Verified')
    store.load_session(task['branch'])
    interface=ReverieInterface.__new__(ReverieInterface)
    interface.session_manager=store
    interface.project_root=tmp_path/'other'
    interface._show_activity_event=Mock()
    assert interface._process_message('Continue')
    assert 'original workspace' in interface._show_activity_event.call_args.args[1]
    with pytest.raises(ValueError,match='original workspace'):
        interface.run_prompt_once('Continue',fresh_session=False)


@pytest.mark.parametrize('fork',[False,True])
def test_sdk_accepts_owned_branch_in_an_isolated_execution_directory(tmp_path,monkeypatch,fork):
    from types import SimpleNamespace
    from reverie.sdk_bridge import ReverieSdkBridge
    store,snapshot=enabled(tmp_path)
    owner=tmp_path/'owner'
    execution=tmp_path/'isolated-checkout'
    owner.mkdir();execution.mkdir()
    if fork:
        store.load_session(store.mainline_id)
        session_id=store.fork_current_session(workspace=owner).id
    else:
        session_id=store.create_task(str(owner),snapshot,'Owned task','Verified')['branch']
    interface=SimpleNamespace(session_manager=store,workspace_root=owner,project_root=execution,_assistant_owner=True,
                              run_prompt_once=lambda *_args,**_kwargs:SimpleNamespace(to_dict=lambda:{'success':True}))
    bridge=ReverieSdkBridge()
    bridge.project_root=owner
    monkeypatch.setattr(bridge,'ensure_interface',lambda *_args:interface)
    monkeypatch.setattr(bridge,'_sync_skill_pins',lambda _interface:None)
    monkeypatch.setattr(bridge,'sessions_payload',lambda:{})
    monkeypatch.setattr(bridge,'recovery_payload',lambda:{})
    response=bridge.dispatch({'id':'owned-read','action':'getSession','payload':{'projectRoot':str(owner),'assistantId':'aio','sessionId':session_id,'select':False}})
    assert response['session']['id']==session_id
    response=bridge._dispatch_prompt('owned-run','runPrompt',{'projectRoot':str(owner),'assistantId':'aio','sessionId':session_id,'prompt':'Continue'})
    assert response['result']['success']
    assert interface.project_root==execution
    assert store.conversation_owners()[session_id]['workspace']==str(owner.resolve())


def test_terminal_branch_ownership_uses_workspace_not_execution_directory(tmp_path):
    from types import SimpleNamespace
    from unittest.mock import Mock
    from reverie.cli.interface import ReverieInterface
    store,snapshot=enabled(tmp_path)
    owner=tmp_path/'owner'
    task=store.create_task(str(owner),snapshot,'Owned task','Verified')
    store.load_session(task['branch'])
    interface=ReverieInterface.__new__(ReverieInterface)
    interface.session_manager=store
    interface.workspace_root=owner
    interface.project_root=tmp_path/'isolated-checkout'
    interface.agent=None
    interface._show_activity_event=Mock()
    class ReachedExecution(Exception):
        pass
    interface._init_agent=Mock(side_effect=ReachedExecution)
    interface.config_manager=SimpleNamespace(load=Mock(side_effect=ReachedExecution))
    with pytest.raises(ReachedExecution):
        interface._process_message('Continue')
    with pytest.raises(ReachedExecution):
        interface.run_prompt_once('Continue',fresh_session=False)


def test_deleted_or_corrected_inference_cannot_resurrect(tmp_path):
    store,_=enabled(tmp_path)
    memory=store.remember('用户可能喜欢深色主题',provenance='inferred',event_ids=['observation'])
    assert memory.provenance=='inferred'
    corrected=store.edit_memory(memory.id,'用户明确偏好浅色主题')
    assert corrected.provenance=='explicit_correction'
    assert store.remember('用户可能喜欢深色主题',event_ids=['observation']) is None
    store.edit_memory(corrected.id)
    assert store.remember('用户明确偏好浅色主题') is None
    assert AiOStore(tmp_path/'aio').context()['memories']==[]


def test_task_state_rejects_stale_updates(tmp_path):
    store,snapshot=enabled(tmp_path)
    task=store.create_task(str(tmp_path),snapshot,'Task','Validate')
    assert store.task_state(task['id'],'running',revision=1)==2
    with pytest.raises(ValueError,match='revision'):
        store.task_state(task['id'],'completed',revision=1)


def test_host_recovery_preserves_queued_work_and_never_replays_uncertain_actions(tmp_path):
    store,snapshot=enabled(tmp_path)
    queued=store.create_task(str(tmp_path),snapshot,'queued work','Validate',task_id='queued')
    active=store.create_task(str(tmp_path),snapshot,'active work','Validate',task_id='active')
    store.task_state(active['id'],'running',revision=1)
    store.append('proactive',{'text':'possibly shown'},event_id='uncertain',visible=True,outbox=True)
    assert store.claim_message('uncertain')
    store.append('proactive',{'text':'not shown'},event_id='queued-message',visible=True,outbox=True)
    recovered=store.recover_host()
    assert {task['id']:task['state'] for task in recovered['tasks']} == {'queued':'queued','active':'interrupted'}
    assert [task['id'] for task in store.pending_tasks()] == [queued['id']]
    assert [message['id'] for message in store.pending_messages()] == ['queued-message']
    assert store.get_page(store.mainline_id)['total'] == 2


def test_disabling_popups_returns_only_undisplayed_claims_to_queue(tmp_path):
    store,_=enabled(tmp_path)
    for event in ['waiting','readable']:
        store.append('proactive',{'text':event},event_id=event,visible=True,outbox=True)
        store.claim_message(event)
    store.acknowledge_message('readable')
    for event in ['waiting','readable']:
        store.release_message(event)
    assert [message['id'] for message in store.pending_messages()] == ['waiting']


def test_finalized_task_cannot_be_reopened_by_a_late_failure(tmp_path):
    store,snapshot=enabled(tmp_path)
    task=store.create_task(str(tmp_path),snapshot,'Task','Validate')
    revision=store.task_state(task['id'],'completed',revision=1,result={'evidence':'verified'})
    with pytest.raises(ValueError,match='finalized'):
        store.task_state(task['id'],'interrupted',revision=revision)


def test_desktop_branch_is_owned_by_the_main_agent(tmp_path):
    store,snapshot=enabled(tmp_path)
    snapshot['settings']['mode']='aio'
    task=store.create_task(str(tmp_path),snapshot,'Inspect owned desktop app','Read back its text')
    assert store.get_page(task['branch'])['metadata']['executor_role']=='main'


def test_other_memory_extraction_paths_cannot_replay_deleted_evidence(tmp_path):
    from reverie.memory.models import MemoryItem
    store,_=enabled(tmp_path)
    memory=store.remember('prefers dark theme',kind='preference',event_ids=['old-event'])
    store.edit_memory(memory.id)
    replay=MemoryItem(id='replay',scope='project',memory_type='preference',content='dark theme is preferred',source_event_ids=['old-event'])
    store.memory.upsert(replay)
    assert replay.status=='suppressed'
    assert store.memory.load_items()==[]
    fresh=store.remember('prefers dark theme again',kind='preference',event_ids=['new-statement'],provenance='explicit_statement')
    assert fresh is not None
    assert fresh.scope=='assistant'


def test_context_uses_bounded_excerpts_while_history_retains_large_messages(tmp_path):
    import json
    store,_=enabled(tmp_path)
    text='长期原文'*20000
    store.append('user',{'text':text},event_id='large',visible=True)
    context=store.context()
    assert len(json.dumps(context,ensure_ascii=False))<48000
    assert context['recent'][0]['context_excerpt'] is True
    assert store.get_page(store.mainline_id)['messages'][0]['content']==text


def test_task_decision_popup_and_reply_keep_the_task_owner(tmp_path):
    store,snapshot=enabled(tmp_path)
    task=store.create_task(str(tmp_path),snapshot,'Task','Verify',task_id='owned')
    decision={'speech':'Task needs your reply','tasks':[],'memories':[]}
    observation={'type':'task.result','branch':task['branch'],'task_id':task['id']}
    store.accept_decision('decision',decision,observation,[],show=True)
    assert store.pending_messages()[0]['branch']==task['branch']
    store.segment_summary('Task needs a user decision.')
    store.reply('decision-speech','Continue','reply')
    assert store.get_page(task['branch'])['messages'][-1]['content']=='Continue'
    assert store.pending_signals()[0]['branch']==task['branch']


def test_saved_replies_and_task_results_survive_before_judgment(tmp_path):
    store,snapshot=enabled(tmp_path)
    store.append('proactive',{'text':'Hello'},event_id='hello',visible=True,outbox=True)
    store.reply('hello','User reply','reply')
    store.reply('hello','User reply','reply')
    task=store.create_task(str(tmp_path),snapshot,'Task','Verify',task_id='signal')
    store.task_state(task['id'],'completed',revision=1,result={'success':True})
    restored=AiOStore(tmp_path/'aio')
    signals=restored.pending_signals()
    assert [signal['type'] for signal in signals]==['user.reply','task.result']
    assert len(signals)==2
    restored.acknowledge_signal(signals[0]['event_id'])
    assert len(AiOStore(tmp_path/'aio').pending_signals())==1


def test_task_panel_reads_the_persisted_verification_phase(tmp_path):
    store,snapshot=enabled(tmp_path)
    task=store.create_task(str(tmp_path),snapshot,'Task','Verify',task_id='phase')
    store.task_state(task['id'],'running',revision=1)
    store.register_run(task['branch'],'run',snapshot,1,str(tmp_path))
    store.update_run(task['branch'],'run','verifying',expected_revision=1)
    assert store.state()['tasks'][0]['state']=='verifying'
    assert store.state()['tasks'][0]['revision']==2
