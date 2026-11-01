import hashlib
import importlib.util
import json
import os
from pathlib import Path
import sys

import pytest


path = Path(__file__).resolve().parents[2] / "scripts/verification/riu_full_benchmark.py"
spec = importlib.util.spec_from_file_location("riu_full_benchmark", path)
benchmark = importlib.util.module_from_spec(spec)
spec.loader.exec_module(benchmark)


def test_streamed_digest_matches_sha256(tmp_path):
    data = b"native acceptance\x00" * 100000
    target = tmp_path / "binary"
    target.write_bytes(data)
    assert benchmark.digest(target) == hashlib.sha256(data).hexdigest()


def test_tools_are_suppressed_only_for_self_contained_static_requests(tmp_path):
    target = tmp_path / "request.json"
    for prompt, expected in [
        ("请展示给定统计卡：计划中7、开发中5，以及表格 Alpha / 开发中 / 核心助手。本题不需调查仓库。", 0),
        ("调查仓库并更新项目文件，然后展示当前项目状态。", 27),
        ("创建一个可以编辑、筛选和排序的表格。", 27),
    ]:
        for count in [0, 27]:
            target.write_text(json.dumps({"messages": [{"role": "user", "content": prompt}],
                "tools": [{}] * count}, ensure_ascii=False), encoding="utf-8")
            assert benchmark.request_tool_scope_matches({"request": str(target), "tools": count}) == (count == expected)
            assert not benchmark.request_tool_scope_matches({"request": str(target), "tools": 99})


def test_native_null_tools_is_absent_only_for_self_contained_static_answers(tmp_path):
    target = tmp_path / 'nullable-tools.json'
    for prompt, expected in [('展示给定统计卡：计划中7，以及表格 Alpha / 开发中 / 核心助手。', True),
                             ('创建一个可以编辑、筛选和排序的表格。', False)]:
        target.write_text(json.dumps({'messages': [{'role': 'user', 'content': prompt}], 'tools': None}), encoding='utf-8')
        assert benchmark.request_tool_scope_matches({'request': str(target), 'tools': 0}) is expected


def test_static_correction_scope_depends_on_retained_data_and_no_tool_calls(tmp_path):
    target = tmp_path / "correction.json"
    supplied = {"role": "user", "content": "展示给定统计卡：计划中7、开发中5，以及表格 Alpha / 开发中 / 核心助手。"}
    reply = {"role": "assistant", "content": "之前的回答"}
    correction = {"role": "user", "content": "把计划中改为0，其余统计卡保持不变。"}
    for messages, expected in [([supplied, reply, correction], 0),
                                ([correction], 27),
                                ([supplied, {**reply, "tool_calls": [{"id": "call"}]}, correction], 27)]:
        for count in [0, 27]:
            target.write_text(json.dumps({"messages": messages, "tools": [{}] * count}, ensure_ascii=False), encoding="utf-8")
            assert benchmark.request_tool_scope_matches({"request": str(target), "tools": count}) == (count == expected)


@pytest.mark.parametrize('source', ['standard', 'custom', 'sensenova'])
@pytest.mark.parametrize('model_count', [1, 2])
def test_frozen_child_preserves_provider_without_sending_saved_keys_to_default_host(tmp_path, monkeypatch, source, model_count):
    monkeypatch.setattr(benchmark, 'ROOT', tmp_path)
    (tmp_path / '.runtime').mkdir()
    scripts = tmp_path / 'scripts/verification'
    (scripts / 'fixtures').mkdir(parents=True)
    for name in ['riu_quality_benchmark.py', 'riu_rich_answer_benchmark.py', 'desktop_process.py',
                 'fixtures/riu-natural-tasks.json', 'fixtures/riu-rich-answer-tasks.json']:
        (scripts / name).write_text('{}', encoding='utf-8')
    package = tmp_path / 'package'
    exe = package / ('MacOS/ReverieUI' if sys.platform == 'darwin' else 'ReverieUI.exe')
    core = package / ('reverie.exe' if os.name == 'nt' else 'reverie')
    archive = package / ('Resources' if sys.platform == 'darwin' else 'resources') / 'app.asar'
    for path in [exe, core, archive]:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b'fixture')
    files = {'regression.json': {'source_unchanged': True, 'stages': [{'exit_code': 0}]},
             'acceptance.json': {'passed': True, 'build': {'id': 'fixture'}}, 'sources.json': {}}
    for name, value in files.items():
        (tmp_path / name).write_text(json.dumps(value), encoding='utf-8')
    output = tmp_path / '.runtime/frozen'
    argv = ['benchmark', '--output', str(output), '--exe', str(exe), '--models', *['model-one', 'model-two'][:model_count],
            '--regression', str(tmp_path / 'regression.json'), '--acceptance', str(tmp_path / 'acceptance.json'),
            '--source-manifest', str(tmp_path / 'sources.json'), '--source', source, '--formal', '--attempts', '3']
    if source == 'custom':
        argv += ['--provider-id', 'xkiro']
    monkeypatch.setattr(sys, 'argv', argv)
    monkeypatch.setattr(benchmark, 'settings_digest', lambda provider='standard', provider_id=None: provider + '-digest')
    commands = []

    def stop_before_model(command, **kwargs):
        commands.append(command)
        raise RuntimeError('stop-before-model-launch')

    monkeypatch.setattr(benchmark.subprocess, 'Popen', stop_before_model)
    with pytest.raises(RuntimeError, match='stop-before-model-launch'):
        benchmark.main()
    manifest = json.loads((output / 'manifest.json').read_text())
    assert manifest['source'] == source
    assert len(manifest['models']) == model_count and manifest['attempts'] == 3
    assert len(manifest['tasks']) == 10
    assert len(manifest['fixed_manual_review_ids']) == 9 * model_count
    assert manifest['verification_settings_sha256'] == source + '-digest'
    command, = commands
    assert command[command.index('--source') + 1] == source
    if source == 'custom':
        assert manifest['api_url'] is None and '--api-url' not in command
        assert manifest['provider_id'] == 'xkiro'
        assert command[command.index('--provider-id') + 1] == 'xkiro'
    elif source == 'standard':
        assert command[command.index('--api-url') + 1] == 'https://oai.endpoints.kepler.ai.cloud.ovh.net/v1'
    else:
        assert manifest['api_url'] is None and '--api-url' not in command and '--provider-id' not in command


def test_sensenova_account_and_endpoint_are_frozen_with_the_round(monkeypatch):
    from types import SimpleNamespace
    from reverie.config import ConfigManager
    cfg = SimpleNamespace(security={}, api_proxy='', api_max_retries=2, api_initial_backoff=1,
                          sensenova={'api_key': 'fixture-key', 'api_url': 'https://provider.invalid/v1'})
    monkeypatch.setattr(ConfigManager, 'load', lambda self: cfg)
    original = benchmark.settings_digest('sensenova')
    cfg.sensenova['api_key'] = 'fixture-rotated-key'
    assert benchmark.settings_digest('sensenova') != original
    rotated = benchmark.settings_digest('sensenova')
    cfg.sensenova['api_url'] = 'https://other.invalid/v1'
    assert benchmark.settings_digest('sensenova') != rotated


@pytest.mark.parametrize('variable', ['SENSENOVA_API_KEY', 'SENSE_API_KEY'])
def test_sensenova_environment_account_is_frozen_with_the_round(monkeypatch, variable):
    from types import SimpleNamespace
    from reverie.config import ConfigManager
    cfg = SimpleNamespace(security={}, api_proxy='', api_max_retries=2, api_initial_backoff=1,
                          sensenova={'api_key': ''})
    monkeypatch.setattr(ConfigManager, 'load', lambda self: cfg)
    monkeypatch.delenv('SENSENOVA_API_KEY', raising=False)
    monkeypatch.delenv('SENSE_API_KEY', raising=False)
    monkeypatch.setenv(variable, 'fixture-key')
    original = benchmark.settings_digest('sensenova')
    monkeypatch.setenv(variable, 'fixture-rotated-key')
    assert benchmark.settings_digest('sensenova') != original
