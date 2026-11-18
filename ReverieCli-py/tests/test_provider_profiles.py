import json
from pathlib import Path

import pytest

from reverie.config import Config, ConfigManager, ModelConfig
from reverie.custom_providers import default_custom_provider


@pytest.fixture
def manager(tmp_path, monkeypatch):
    monkeypatch.setenv('REVERIE_APP_ROOT', str(tmp_path / 'app'))
    project = tmp_path / 'project'
    project.mkdir()
    return ConfigManager(project)


def catalog_config(size=2000, name='Kilo'):
    provider = default_custom_provider(provider_id='kilo', name=name, base_url='https://profiles.invalid/v1', api_key='stored-key')
    provider.update(models=[{'id': f'model-{i}', 'display_name': f'Model {i}', 'reasoning': True, 'context_length': 128000} for i in range(size)],
                    selected_model_id='model-4', model_context_limits={'model-4': 96000})
    return Config(active_model_source='custom', custom_providers={'active_provider_id': 'kilo', 'providers': [provider]})


def test_catalog_saved_once_in_named_profile_and_round_trips(manager):
    config = catalog_config()
    manager.save(config)
    raw = json.loads(manager.config_path.read_text(encoding='utf-8'))
    record = raw['custom_providers']['providers'][0]
    assert record == {'id': 'kilo', 'profile': 'Kilo.json'}
    assert 'stored-key' not in manager.config_path.read_text(encoding='utf-8')
    profile = manager.config_path.parent / 'Providers' / 'Kilo.json'
    inventory = json.loads(profile.read_text(encoding='utf-8'))
    assert len(inventory['models']) == 2000
    assert inventory['api_key'] == 'stored-key'
    manager._config = None
    loaded = manager.load().custom_providers['providers'][0]
    assert len(loaded['models']) == 2000
    assert loaded['selected_model_id'] == 'model-4'
    assert loaded['max_context_tokens'] == 96000
    before = profile.stat().st_mtime_ns
    manager.save(manager.load())
    assert profile.stat().st_mtime_ns == before


def test_legacy_inline_catalog_migrates_without_losing_selection(manager):
    manager.config_path.parent.mkdir(parents=True, exist_ok=True)
    manager.config_path.write_text(json.dumps(catalog_config(10).to_dict()), encoding='utf-8')
    loaded = manager.load()
    assert loaded.custom_providers['providers'][0]['selected_model_id'] == 'model-4'
    raw = json.loads(manager.config_path.read_text(encoding='utf-8'))
    assert raw['custom_providers']['providers'][0]['profile'] == 'Kilo.json'
    backup = manager.config_path.with_name('config.pre-providers.json.bak')
    assert len(json.loads(backup.read_text(encoding='utf-8'))['custom_providers']['providers'][0]['models']) == 10


def test_profile_changes_reload_without_main_config_edit(manager):
    manager.save(catalog_config(10))
    profile = manager.config_path.parent / 'Providers' / 'Kilo.json'
    payload = json.loads(profile.read_text(encoding='utf-8'))
    payload['models'].append({'id': 'new-model', 'display_name': 'New Model'})
    profile.write_text(json.dumps(payload), encoding='utf-8')
    assert len(manager.load().custom_providers['providers'][0]['models']) == 11


def test_saving_an_in_memory_inventory_edit_updates_the_profile(manager):
    config = catalog_config(10)
    manager.save(config)
    config.custom_providers['providers'][0]['models'].append({'id': 'added', 'display_name': 'Added'})
    manager.save(config)
    manager._config = None
    assert len(manager.load().custom_providers['providers'][0]['models']) == 11


def test_missing_profile_is_reported_without_replacing_the_configuration(manager):
    from reverie.provider_profiles import ProviderProfileError
    manager.save(catalog_config(10))
    saved = manager.config_path.read_bytes()
    (manager.config_path.parent / 'Providers' / 'Kilo.json').unlink()
    with pytest.raises(ProviderProfileError, match='Cannot load provider profile'):
        manager.load()
    assert manager.config_path.read_bytes() == saved


def test_workspace_provider_files_are_independent_of_global_provider_files(manager):
    manager.save(catalog_config(10))
    assert manager.copy_config_to_workspace()
    global_profile = manager.global_config_path.parent / 'Providers' / 'Kilo.json'
    workspace_profile = manager.workspace_config_path.parent / 'Providers' / 'Kilo.json'
    assert global_profile.is_file()
    assert workspace_profile.is_file()
    local = manager.load()
    local.custom_providers['providers'][0]['api_key'] = 'workspace-key'
    manager.save(local)
    assert json.loads(global_profile.read_text(encoding='utf-8'))['api_key'] == 'stored-key'
    assert ConfigManager(manager.project_root).load().custom_providers['providers'][0]['api_key'] == 'workspace-key'
    assert manager.copy_config_to_global()
    assert len(manager.load().custom_providers['providers'][0]['models']) == 10
    assert json.loads(global_profile.read_text(encoding='utf-8'))['api_key'] == 'workspace-key'


def test_copy_legacy_provider_without_explicit_id_to_workspace(manager):
    legacy = catalog_config(10).to_dict()
    legacy['customProviders'] = legacy.pop('custom_providers')
    legacy['customProviders']['providers'][0].pop('id')
    manager.global_config_path.parent.mkdir(parents=True, exist_ok=True)
    manager.global_config_path.write_text(json.dumps(legacy), encoding='utf-8')

    assert manager.copy_config_to_workspace()
    loaded = ConfigManager(manager.project_root).load()
    assert loaded.active_model.model == 'model-4'
    assert loaded.custom_providers['providers'][0]['api_key'] == 'stored-key'


def test_loading_retries_after_a_concurrent_provider_rename(manager, monkeypatch):
    manager.save(catalog_config(10))
    reader = ConfigManager(manager.project_root)
    original = reader._load_json_payload

    def read_then_rename(path, **options):
        data = original(path, **options)
        if data['custom_providers']['providers'][0]['profile'] == 'Kilo.json':
            config = manager.load()
            config.custom_providers['providers'][0]['name'] = 'Kilo Renamed'
            manager.save(config)
        return data

    monkeypatch.setattr(reader, '_load_json_payload', read_then_rename)
    loaded = reader.load()
    assert loaded.active_model.model == 'model-4'
    assert loaded.custom_providers['providers'][0]['name'] == 'Kilo Renamed'


def test_provider_name_collision_does_not_overwrite_another_inventory(manager):
    config = catalog_config(10, 'Kilo/Relay')
    another = catalog_config(5, 'Kilo:Relay').custom_providers['providers'][0]
    another['id'] = 'other'
    config.custom_providers['providers'].append(another)
    manager.save(config)
    raw = json.loads(manager.config_path.read_text(encoding='utf-8'))
    profiles = [p['profile'] for p in raw['custom_providers']['providers']]
    assert len(set(profiles)) == 2
    assert all(Path(p).name == p for p in profiles)
    manager._config = None
    assert [len(p['models']) for p in manager.load().custom_providers['providers']] == [10, 5]


def test_migrates_legacy_inventory_files_and_preserves_builtin_settings(manager):
    from reverie.model_catalog_cache import model_catalog_key

    config = catalog_config(10)
    config.models = [ModelConfig('manual', 'Manual', 'https://manual.invalid', api_key='manual-key')]
    config.agnes['api_key'] = 'agnes-key'
    config.text_to_image['agnes']['default_model'] = 'my-image-model'
    legacy = config.to_dict()
    provider = legacy['custom_providers']['providers'][0]
    models = provider.pop('models')
    key = model_catalog_key('https://profiles.invalid/v1/models', 'stored-key', 'openai-chat')
    provider['catalog_profile'] = 'Kilo.json'
    legacy_root = manager.global_config_path.parent / 'profiles'
    legacy_root.mkdir(parents=True)
    (legacy_root / 'Kilo.json').write_text(json.dumps({
        'provider_id': 'kilo', 'models': models, 'connection_key': key,
        'model_context_limits': provider.pop('model_context_limits'),
    }), encoding='utf-8')
    manager.global_config_path.write_text(json.dumps(legacy), encoding='utf-8')

    manager.load()
    loaded = ConfigManager(manager.project_root).load()
    assert loaded.active_model.model == 'model-4'
    assert loaded.active_model.max_context_tokens == 96000
    assert loaded.models[0].api_key == 'manual-key'
    assert loaded.agnes['api_key'] == 'agnes-key'
    assert loaded.text_to_image['agnes']['default_model'] == 'my-image-model'
    root = manager.global_config_path.parent / 'Providers'
    stored = json.loads((root / 'Kilo.json').read_text(encoding='utf-8'))
    assert len(stored['models']) == 10
    assert stored['model_catalog'] == {'connection_key': key}
    assert (legacy_root / 'Kilo.json').is_file()


def test_model_selection_touches_only_the_selected_provider(manager, monkeypatch):
    from reverie.desktop_catalog import select_custom_provider_model

    manager.save(catalog_config(100))
    config = manager.load().copy_with_shared_catalogs()
    select_custom_provider_model(config, 'kilo', 'model-99', 192000, describe_provider=False)
    root = manager.config_path.parent / 'Providers'
    before = {path.name: path.stat().st_mtime_ns for path in root.glob('*.json')}
    monkeypatch.setattr(config, 'to_dict', lambda: pytest.fail('Model selection serialized the full config'))

    manager.save_model_selection(config)

    assert {path.name for path in root.glob('*.json') if path.stat().st_mtime_ns != before[path.name]} == {'Kilo.json'}
    restored = ConfigManager(manager.project_root).load()
    assert restored.active_model.model == 'model-99'
    assert restored.active_model.max_context_tokens == 192000


def test_removing_a_provider_removes_only_its_current_credential_file(manager):
    manager.save(catalog_config(10))
    root = manager.config_path.parent / 'Providers'
    (root / 'other.json').write_text('{}', encoding='utf-8')
    config = manager.load()
    config.custom_providers['providers'] = []
    manager.save(config)
    assert (root / 'other.json').is_file()
    assert not (root / 'Kilo.json').exists()
