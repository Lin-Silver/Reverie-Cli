import copy

import pytest

from reverie.config import Config, ModelConfig
from reverie.custom_providers import default_custom_provider
from reverie.desktop_catalog import select_custom_provider_model
from reverie.session.runtime_config import capture_runtime_config, resolve_runtime_config


@pytest.mark.parametrize('proxy', ['http://test-user:old-private@proxy.invalid:8080', 'test-user:old-private@proxy.invalid:8080'])
def test_proxy_authentication_is_not_part_of_a_conversation_snapshot(proxy):
    config=Config(api_proxy=proxy)
    snapshot=capture_runtime_config(config)
    assert snapshot['settings']['api_proxy']=='http://proxy.invalid:8080'
    assert 'test-user' not in str(snapshot) and 'old-private' not in str(snapshot)


@pytest.mark.parametrize('shared_proxy,expected', [
    ('http://current-user:new-private@proxy.invalid:8080','http://current-user:new-private@proxy.invalid:8080'),
    ('http://proxy.invalid:8080','http://proxy.invalid:8080'),
    ('http://other-user:other-private@other.invalid:8080','http://proxy.invalid:8080'),
])
def test_proxy_credentials_are_resolved_from_the_current_matching_shared_endpoint(shared_proxy,expected):
    config=Config(api_proxy='http://test-user:old-private@proxy.invalid:8080')
    snapshot=capture_runtime_config(config)
    snapshot['settings']['api_proxy']='http://test-user:old-private@proxy.invalid:8080'
    config.api_proxy=shared_proxy
    assert resolve_runtime_config(config,snapshot).api_proxy==expected


def test_terminal_proxy_credentials_stay_shared_while_saved_configuration_and_exports_are_secret_free(tmp_path):
    from types import SimpleNamespace
    from reverie.session.sqlite_manager import SQLiteSessionManager
    from reverie.session.runtime_config import ConversationConfigView

    shared=Config()
    sessions=SQLiteSessionManager(tmp_path/'state')
    session=sessions.create_session('Proxy configuration')
    session.metadata['runtime_config']=capture_runtime_config(shared)
    sessions.save_session(session)
    def save(value):
        nonlocal shared
        shared=copy.deepcopy(value)
    view=ConversationConfigView(SimpleNamespace(load=lambda:copy.deepcopy(shared),save=save),sessions,lambda value:None)
    edited=view.load();edited.api_proxy='http://test-user:new-private@proxy.invalid:8080'
    view.save(edited)
    assert shared.api_proxy==edited.api_proxy
    assert view.load().api_proxy==edited.api_proxy
    assert 'new-private' not in str(sessions.configuration_history(session.id))
    for format_name in ('json','markdown'):
        target=tmp_path/f'proxy-export.{format_name}'
        sessions.export_current_session(target,format_name)
        assert 'new-private' not in target.read_text(encoding='utf-8')


def test_export_sanitizes_existing_proxy_snapshots_without_changing_saved_history(tmp_path):
    import json
    from reverie.session.sqlite_manager import SQLiteSessionManager

    sessions=SQLiteSessionManager(tmp_path/'state')
    session=sessions.create_session('Existing snapshot')
    snapshot=capture_runtime_config(Config())
    snapshot['settings']['api_proxy']='http://test-user:old-private@proxy.invalid:8080'
    session.metadata['runtime_config']=snapshot
    session.messages=[{'role':'user','content':'Keep the complete user message.'}]
    sessions.save_session(session)
    sessions.register_run(session.id,'existing-run',snapshot,session._storage_revision,str(tmp_path),request={'configuration':snapshot,'prompt':'Keep the complete user message.'})
    for format_name in ('json','markdown'):
        target=tmp_path/f'existing-export.{format_name}'
        sessions.export_current_session(target,format_name)
        assert 'old-private' not in target.read_text(encoding='utf-8')
    exported=json.loads((tmp_path/'existing-export.json').read_text(encoding='utf-8'))
    assert exported['messages']==session.messages
    assert sessions.load_session(session.id).metadata['runtime_config']==snapshot


def test_plain_conversation_proxy_does_not_overwrite_another_shared_authenticated_endpoint(tmp_path):
    from types import SimpleNamespace
    from reverie.session.sqlite_manager import SQLiteSessionManager
    from reverie.session.runtime_config import ConversationConfigView

    shared=Config(api_proxy='http://test-user:shared-private@proxy.invalid:8080')
    sessions=SQLiteSessionManager(tmp_path/'state');session=sessions.create_session('Independent proxy')
    session.metadata['runtime_config']=capture_runtime_config(shared);sessions.save_session(session)
    def save(value):
        nonlocal shared
        shared=copy.deepcopy(value)
    view=ConversationConfigView(SimpleNamespace(load=lambda:copy.deepcopy(shared),save=save),sessions,lambda value:None)
    edited=view.load();edited.api_proxy='http://other.invalid:8080';view.save(edited)
    assert shared.api_proxy=='http://test-user:shared-private@proxy.invalid:8080'
    assert view.load().api_proxy=='http://other.invalid:8080'


@pytest.mark.parametrize('edited_proxy,expected_shared', [
    ('http://test-user:new-private@proxy.invalid:8080','http://test-user:new-private@proxy.invalid:8080'),
    ('http://proxy.invalid:8080','http://proxy.invalid:8080'),
    ('http://other.invalid:8080','http://test-user:old-private@proxy.invalid:8080'),
])
def test_desktop_proxy_edit_survives_fresh_worker_without_saving_credentials_in_history(tmp_path,monkeypatch,edited_proxy,expected_shared):
    from types import SimpleNamespace
    from reverie.config import ConfigManager
    from reverie.sdk_bridge import ReverieSdkBridge
    from reverie.session.sqlite_manager import SQLiteSessionManager

    manager=ConfigManager(tmp_path)
    shared=Config(api_proxy='http://test-user:old-private@proxy.invalid:8080')
    manager.save(shared)
    sessions=SQLiteSessionManager(tmp_path/'state')
    session=sessions.create_session('Desktop proxy')
    session.metadata['runtime_config']=capture_runtime_config(shared)
    sessions.save_session(session)
    interface=SimpleNamespace(config_manager=manager,session_manager=sessions,rules_manager=None,runtime_plugin_manager=None,agent=None)
    bridge=ReverieSdkBridge()
    monkeypatch.setattr(bridge,'ensure_interface',lambda:interface)
    for name in ('settings_payload','model_sources_payload','workspace_payload'):
        monkeypatch.setattr(bridge,name,lambda:{})
    monkeypatch.setattr(bridge,'_refresh_plugin_dependents',lambda:None)
    response=bridge.dispatch({'action':'setSetting','payload':{'sessionId':session.id,'key':'api_proxy','value':edited_proxy}})
    assert response['success']
    fresh_defaults=ConfigManager(tmp_path).load()
    fresh_session=SQLiteSessionManager(tmp_path/'state').load_session(session.id)
    assert fresh_defaults.api_proxy==expected_shared
    assert resolve_runtime_config(fresh_defaults,fresh_session.metadata['runtime_config']).api_proxy==edited_proxy
    assert 'private' not in str(sessions.configuration_history(session.id))


def test_model_reference_survives_catalog_reordering_and_excludes_credentials():
    config = Config(models=[ModelConfig("a", "A", "https://example.com/v1", api_key="private-key"), ModelConfig("b", "B", "https://other.example/v1")])
    snapshot = capture_runtime_config(config)
    assert "private-key" not in str(snapshot)
    reordered = copy.deepcopy(config)
    reordered.models.reverse()
    assert resolve_runtime_config(reordered, snapshot).active_model.model == "a"


def test_missing_model_does_not_fall_back():
    config = Config(models=[ModelConfig("a", "A", "https://example.com/v1")])
    snapshot = capture_runtime_config(config)
    config.models = [ModelConfig("b", "B", "https://example.com/v1")]
    with pytest.raises(ValueError, match="model|profile"):
        resolve_runtime_config(config, snapshot)


def test_runtime_parameters_are_independent_and_permissions_cannot_expand():
    config = Config(models=[ModelConfig("a", "A", "https://example.com/v1")])
    config.security["permission_level"] = "full_control"
    snapshot = capture_runtime_config(config)
    snapshot["settings"]["api_timeout"] = 180
    config.api_timeout = 30
    config.security["permission_level"] = "read_only"
    runtime = resolve_runtime_config(config, snapshot)
    assert runtime.api_timeout == 180
    assert runtime.permission_level == "read_only"
    assert config.api_timeout == 30


def test_old_review_preferences_cannot_restore_revoked_permissions():
    config=Config(models=[ModelConfig('a','A','https://example.com')])
    config.security.update({'strict_allow_read_only':True,'review':{'fail_open':True,'approve_risk_at':'critical','review_read_only':False}})
    snapshot=capture_runtime_config(config)
    config.security.update({'strict_allow_read_only':False,'review':{'fail_open':False,'approve_risk_at':'low','review_read_only':True}})
    runtime=resolve_runtime_config(config,snapshot)
    assert runtime.security['strict_allow_read_only'] is False
    assert runtime.security['review']['fail_open'] is False
    assert runtime.security['review']['approve_risk_at']=='low'
    assert runtime.security['review']['review_read_only'] is True


def test_subagent_configuration_uses_the_saved_profile_after_reordering():
    from reverie.agent.subagents import SubagentManager, SubagentSpec
    config = Config(models=[ModelConfig('a','A','https://example.com'),ModelConfig('b','B','https://example.com')])
    config.subagents['agents']=[{'id':'worker','model_ref':{'source':'standard','index':0,'model':'a'}}]
    snapshot = capture_runtime_config(config)
    reference = snapshot['settings']['subagents']['agents'][0]['model_ref']
    assert 'index' not in reference
    assert reference['profile_id'] == config.models[0].profile_id
    config.models.reverse()
    manager = object.__new__(SubagentManager)
    spec = SubagentSpec.from_dict({'id':'worker','model_ref':reference})
    assert manager.resolve_model(spec,config).model=='a'
    config.models=[config.models[0]]
    assert manager.resolve_model(spec,config) is None


def test_terminal_configuration_changes_only_the_owning_conversation(tmp_path):
    from reverie.session.sqlite_manager import SQLiteSessionManager
    from reverie.session.runtime_config import ConversationConfigView
    from types import SimpleNamespace
    config=Config(models=[ModelConfig('a','A','https://example.com'),ModelConfig('b','B','https://example.com')])
    sessions=SQLiteSessionManager(tmp_path)
    first=sessions.create_session()
    first.metadata['runtime_config']=capture_runtime_config(config)
    sessions.save_session(first)
    second=sessions.create_session()
    second.metadata['runtime_config']=capture_runtime_config(config)
    sessions.save_session(second)
    manager=SimpleNamespace(load=lambda:copy.deepcopy(config),save=lambda value:None)
    view=ConversationConfigView(manager,sessions,lambda value:None)
    edited=view.load();edited.active_model_index=1;edited.api_timeout=120
    view.save(edited)
    assert view.load().active_model.model=='b'
    sessions.load_session(first.id)
    assert view.load().active_model.model=='a'
    assert view.load().api_timeout==60
    assert config.active_model_index==0


def test_custom_conversation_keeps_limits_across_providers_without_saving_catalogs():
    defaults = Config()
    for index in (1, 2):
        record = default_custom_provider(provider_id=f'fixture-{index}', base_url=f'https://fixture-{index}.invalid/v1', api_key='secret')
        record['models'] = [{'id': 'chat', 'context_length': 32000}]
        defaults.custom_providers['providers'].append(record)

    config = defaults.copy_with_shared_catalogs()
    select_custom_provider_model(config, 'fixture-1', 'chat', 96000, 'low', describe_provider=False)
    first = capture_runtime_config(config)
    assert set(first['provider_settings']).isdisjoint({'api_key', 'models', 'model_catalog', 'base_url'})
    config = resolve_runtime_config(defaults, first, share_catalogs=True)
    select_custom_provider_model(config, 'fixture-2', 'chat', 48000, describe_provider=False)
    second = capture_runtime_config(config, previous=first)
    config = resolve_runtime_config(defaults, second, share_catalogs=True)
    assert config.active_model.max_context_tokens == 48000
    select_custom_provider_model(config, 'fixture-1', 'chat', describe_provider=False)
    assert config.active_model.max_context_tokens == 96000
    assert defaults.custom_providers['providers'][0]['model_context_limits'] == {}


def test_legacy_conversation_uses_current_custom_provider_connection_and_inventory():
    record = default_custom_provider(provider_id='fixture', base_url='https://current.invalid/v1', api_key='shared-key')
    record['models'] = [{'id': 'chat', 'context_length': 48000}]
    defaults = Config(custom_providers={'providers': [record], 'active_provider_id': 'fixture'})
    snapshot = {'model_ref': {'source': 'custom', 'provider_id': 'fixture', 'model': 'chat'},
                'provider_settings': {'base_url': 'https://old.invalid/v1', 'api_key': 'old-key',
                                      'model_catalog': {'connection_key': 'old', 'models': []},
                                      'model_context_limits': {'chat': 96000}}}
    model = resolve_runtime_config(defaults, snapshot).active_model
    assert (model.base_url, model.api_key, model.max_context_tokens) == ('https://current.invalid/v1', 'shared-key', 96000)
    snapshot['model_ref']['model'] = 'deleted'
    with pytest.raises(ValueError, match='not in'):
        resolve_runtime_config(defaults, snapshot)
