import json
from pathlib import Path

import pytest

from reverie.config import Config, ConfigManager
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
    assert record['catalog_profile'] == 'Kilo.json'
    assert 'models' not in record and 'model_catalog' not in record
    profile = manager.app_root / '.reverie' / 'profiles' / 'Kilo.json'
    inventory = json.loads(profile.read_text(encoding='utf-8'))
    assert len(inventory['models']) == 2000
    assert 'api_key' not in inventory
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
    assert raw['custom_providers']['providers'][0]['catalog_profile'] == 'Kilo.json'


def test_profile_changes_reload_without_main_config_edit(manager):
    manager.save(catalog_config(10))
    profile = manager.app_root / '.reverie' / 'profiles' / 'Kilo.json'
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
    (manager.app_root / '.reverie' / 'profiles' / 'Kilo.json').unlink()
    with pytest.raises(ProviderProfileError, match='Cannot load provider profile'):
        manager.load()
    assert manager.config_path.read_bytes() == saved


def test_workspace_and_global_configs_use_profiles_under_the_executable_root(manager):
    manager.save(catalog_config(10))
    assert manager.copy_config_to_workspace()
    global_profile = manager.global_config_path.parent / 'profiles' / 'Kilo.json'
    assert global_profile.is_file()
    assert not (manager.workspace_config_path.parent / 'profiles').exists()
    assert len(manager.load().custom_providers['providers'][0]['models']) == 10
    assert manager.copy_config_to_global()
    assert len(manager.load().custom_providers['providers'][0]['models']) == 10


def test_provider_name_collision_does_not_overwrite_another_inventory(manager):
    config = catalog_config(10, 'Kilo/Relay')
    another = catalog_config(5, 'Kilo:Relay').custom_providers['providers'][0]
    another['id'] = 'other'
    config.custom_providers['providers'].append(another)
    manager.save(config)
    raw = json.loads(manager.config_path.read_text(encoding='utf-8'))
    profiles = [p['catalog_profile'] for p in raw['custom_providers']['providers']]
    assert len(set(profiles)) == 2
    assert all(Path(p).name == p for p in profiles)
    manager._config = None
    assert [len(p['models']) for p in manager.load().custom_providers['providers']] == [10, 5]
