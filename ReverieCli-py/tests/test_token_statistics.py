from __future__ import annotations

import csv
import io
import json

import pytest

from reverie.session.workspace_stats import WorkspaceStatsManager


@pytest.mark.parametrize(('raw', 'expected'), [
    ({'prompt_tokens': 100, 'completion_tokens': 20, 'total_tokens': 120, 'prompt_tokens_details': {'cached_tokens': 40}, 'completion_tokens_details': {'reasoning_tokens': 5}},
     {'input_tokens': 100, 'output_tokens': 20, 'total_tokens': 120, 'cached_input_tokens': 40, 'reasoning_tokens': 5}),
    ({'input_tokens': 20, 'cache_read_input_tokens': 50, 'cache_creation_input_tokens': 10, 'output_tokens': 12},
     {'input_tokens': 80, 'output_tokens': 12, 'cached_input_tokens': 50, 'cache_creation_tokens': 10}),
    ({'prompt_token_count': 120, 'candidates_token_count': 10, 'thoughts_token_count': 5, 'cached_content_token_count': 40, 'total_token_count': 135},
     {'input_tokens': 120, 'output_tokens': 15, 'reasoning_tokens': 5, 'cached_input_tokens': 40, 'total_tokens': 135}),
])
def test_provider_usage_and_cache_are_normalized_once(raw, expected):
    normalized = WorkspaceStatsManager._usage_dict(raw)
    assert normalized == expected
    assert WorkspaceStatsManager._usage_dict(normalized) == expected


def record(manager, usage=None, **kwargs):
    manager.record_model_usage(provider='gemini', source='chat', model='test-model', model_display_name='Test model',
                               request_messages=[{'role': 'user', 'content': 'Hello'}], assistant_text='Answer', usage=usage,
                               session_id=kwargs.pop('session_id', 's1'), **kwargs)


def test_api_zero_does_not_fall_back_and_records_are_durable(tmp_path, monkeypatch):
    manager = WorkspaceStatsManager(tmp_path)
    def fail(*args):
        raise AssertionError('No local counter is needed for API-reported zero')
    monkeypatch.setattr(manager, 'count_messages_tokens', fail)
    monkeypatch.setattr(manager, 'count_text_tokens', fail)
    record(manager, {'input_tokens': 0, 'output_tokens': 0, 'total_tokens': 0, 'cached_input_tokens': 0})
    rows = WorkspaceStatsManager(tmp_path).model_requests()
    assert len(rows) == 1
    assert rows[0]['total_tokens'] == 0 and rows[0]['usage_source'] == 'api'


def test_partial_api_usage_and_local_fallback_disclose_sources(tmp_path):
    manager = WorkspaceStatsManager(tmp_path)
    record(manager, {'total_tokens': 50})
    record(manager)
    rows = manager.model_requests()
    measured, local = rows
    assert measured['total_tokens'] == 50 and measured['total_source'] == 'api'
    assert measured['usage_source'] == 'mixed'
    assert local['usage_source'] == 'local' and local['total_tokens'] > 0
    assert local['cached_input_tokens'] is None


def test_legacy_rollups_import_once_without_inventing_dates_or_sessions(tmp_path):
    (tmp_path / 'workspace_stats.json').write_text(json.dumps({'model_usage': {
        'gemini::chat::test-model': {'usage_key': 'gemini::chat::test-model', 'provider': 'gemini', 'source': 'chat',
                                   'model': 'test-model', 'model_display_name': 'Test model', 'calls': 5,
                                   'input_tokens': 100, 'output_tokens': 20, 'total_tokens': 120, 'last_used_at': '2026-11-10T10:00:00'}
    }}), encoding='utf-8')
    manager = WorkspaceStatsManager(tmp_path)
    record(manager, {'input_tokens': 30, 'output_tokens': 4, 'total_tokens': 34})
    rows = WorkspaceStatsManager(tmp_path).model_requests()
    assert len(rows) == 2
    old = next(row for row in rows if row['usage_source'] == 'historical')
    assert old['calls'] == 5 and old['occurred_at'] is None and old['session_id'] == ''
    assert old['cached_input_tokens'] is None
    assert sum(row['total_tokens'] for row in rows) == 154


def test_statistics_filters_csv_and_per_model_currency_prices(tmp_path, monkeypatch):
    from reverie.usage_statistics import build_usage_report, set_model_token_price, usage_csv
    app_root = tmp_path / 'app'
    one = WorkspaceStatsManager(app_root / '.reverie/projects/one', project_root=tmp_path / 'One')
    two = WorkspaceStatsManager(app_root / '.reverie/projects/two', project_root=tmp_path / 'Two')
    monkeypatch.setattr('reverie.session.workspace_stats._now_utc_iso', lambda: '2026-11-10T12:00:00+00:00')
    record(one, {'input_tokens': 1000000, 'output_tokens': 500000, 'cached_input_tokens': 400000, 'total_tokens': 1500000})
    monkeypatch.setattr('reverie.session.workspace_stats._now_utc_iso', lambda: '2026-11-11T12:00:00+00:00')
    record(two, {'input_tokens': 200, 'output_tokens': 50, 'total_tokens': 250}, session_id='s2')
    set_model_token_price(app_root, 'gemini::test-model', {'currency': 'USD', 'input': 2, 'cached_input': 0.5, 'output': 8})
    report = build_usage_report(app_root, current=one, filters={'start': '2026-11-10', 'end': '2026-11-10', 'project': one.state.workspace_id, 'session': 's1', 'model': 'gemini::test-model'})
    assert report['totals']['calls'] == 1 and report['totals']['total_tokens'] == 1500000
    assert report['totals']['costs']['USD'] == pytest.approx(5.4)
    assert len(report['daily']) == 1 and report['daily'][0]['date'] == '2026-11-10'
    assert len(report['options']['projects']) == 2
    rows = list(csv.DictReader(io.StringIO(usage_csv(report))))
    assert len(rows) == 1 and rows[0]['currency'] == 'USD' and float(rows[0]['estimated_cost']) == pytest.approx(5.4)
    set_model_token_price(app_root, 'gemini::test-model', {'currency': 'CNY', 'input': 1, 'cached_input': 0, 'output': 2})
    refreshed = build_usage_report(app_root, current=one, filters={'project': one.state.workspace_id})
    assert refreshed['totals']['costs'] == {'CNY': pytest.approx(1.6)}


@pytest.mark.parametrize('price', [{'currency': 'EUR', 'input': 1, 'cached_input': 1, 'output': 1},
                                  {'currency': 'USD', 'input': -1, 'cached_input': 1, 'output': 1},
                                  {'currency': 'USD', 'input': float('nan'), 'cached_input': 1, 'output': 1}])
def test_invalid_prices_are_rejected(tmp_path, price):
    from reverie.usage_statistics import set_model_token_price
    with pytest.raises(ValueError):
        set_model_token_price(tmp_path, 'model', price)


def test_unknown_cache_and_unpriced_models_are_disclosed(tmp_path):
    from reverie.usage_statistics import build_usage_report
    manager = WorkspaceStatsManager(tmp_path / '.reverie/projects/one')
    record(manager, {'input_tokens': 100, 'output_tokens': 20})
    report = build_usage_report(tmp_path, current=manager)
    assert report['totals']['unpriced_calls'] == 1
    assert report['totals']['unknown_cache_calls'] == 1
    assert report['totals']['costs'] == {}
