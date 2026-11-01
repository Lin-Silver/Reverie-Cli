"""Inject harness failures without starting a desktop or contacting a model."""
from contextlib import contextmanager
import importlib.util
import json
from pathlib import Path
import sys

import pytest


@pytest.mark.parametrize('script', ['riu_quality_benchmark', 'riu_rich_answer_benchmark'])
@pytest.mark.parametrize('failure', ['setup', 'close'])
def test_credentials_do_not_survive_setup_or_finalization_failure(tmp_path, monkeypatch, script, failure):
    from reverie.config import ConfigManager
    from reverie.session.manager import SessionManager
    import playwright.sync_api

    root = Path(__file__).resolve().parents[2]
    spec = importlib.util.spec_from_file_location(script + '_cleanup_test', root / 'scripts/verification' / (script + '.py'))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    recorder_owner = module.q if script == 'riu_rich_answer_benchmark' else module
    monkeypatch.setattr(module, 'ROOT', tmp_path)
    original = ConfigManager(tmp_path)
    cfg = original.load()
    secret = 'fixture-cleanup-key'
    cfg.custom_providers = {'active_provider_id': 'xkiro', 'providers': [{
        'id': 'xkiro', 'name': 'xkiro', 'enabled': True, 'format': 'openai-chat',
        'base_url': 'https://provider.invalid/v1', 'api_key': secret,
        'selected_model_id': 'fixture-model', 'models': [{'id': 'fixture-model'}],
    }]}
    original.ensure_dirs()
    original.save(cfg)
    original_bytes = original.global_config_path.read_bytes()
    task = 'rich-overview' if script == 'riu_rich_answer_benchmark' else 'calculator'
    fixture = tmp_path / 'tasks.json'
    fixture.write_text(json.dumps({'version': 'test', 'tasks': [{'id': task}]}), encoding='utf-8')
    output = tmp_path / '.runtime/sample'
    output.parent.mkdir()
    argv = ['benchmark', '--output', str(output), '--exe', str(tmp_path / 'unused.exe'),
            '--source', 'custom', '--provider-id', 'xkiro', '--model', 'fixture-model',
            '--task-file', str(fixture), '--tasks', task, '--attempts', '1']
    monkeypatch.setattr(sys, 'argv', argv)
    recorders = []
    recorder_class = recorder_owner.Recorder

    class CapturedRecorder(recorder_class):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, **kwargs)
            recorders.append(self)

        def close(self):
            super().close()
            if failure == 'close':
                raise RuntimeError('close-failure')

    monkeypatch.setattr(recorder_owner, 'Recorder', CapturedRecorder)
    if failure == 'setup':
        def fail_setup(*args, **kwargs):
            raise RuntimeError('setup-failure')
        monkeypatch.setattr(SessionManager, 'create_session', fail_setup)
    else:
        @contextmanager
        def fail_launch():
            raise RuntimeError('launch-failure')
            yield
        monkeypatch.setattr(playwright.sync_api, 'sync_playwright', fail_launch)
    try:
        with pytest.raises(RuntimeError, match=failure + '-failure'):
            module.main()
        for path in (output / 'app-root').rglob('*.json'):
            assert secret not in path.read_text(encoding='utf-8'), path
        assert original.global_config_path.read_bytes() == original_bytes
    finally:
        for recorder in recorders:
            recorder_class.close(recorder)
