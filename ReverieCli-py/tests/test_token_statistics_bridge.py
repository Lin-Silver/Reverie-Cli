import csv
import io
from types import SimpleNamespace

from reverie.sdk_bridge import ReverieSdkBridge
from reverie.session.workspace_stats import WorkspaceStatsManager


def test_bridge_statistics_prices_and_csv_share_filtered_data(tmp_path, monkeypatch):
    manager = WorkspaceStatsManager(tmp_path / '.reverie/projects/one', project_root=tmp_path / 'One')
    manager.record_model_usage(provider='gemini', source='chat', model='model', model_display_name='Model', request_messages=[],
                               usage={'input_tokens': 1000000, 'cached_input_tokens': 300000, 'output_tokens': 500000}, session_id='s1')
    runtime = ReverieSdkBridge.__new__(ReverieSdkBridge)
    runtime.project_root = tmp_path / 'One'
    runtime._run_control = None
    monkeypatch.setattr(runtime, 'ensure_interface', lambda: SimpleNamespace(workspace_stats_manager=manager))
    monkeypatch.setattr('reverie.sdk_bridge.get_app_root', lambda: tmp_path)
    price = runtime.dispatch({'id': 'price', 'action': 'setTokenPrice', 'payload': {'modelKey': 'gemini::model', 'price': {'currency': 'USD', 'input': 2, 'cached_input': 0.5, 'output': 8}}})
    assert price['type'] == 'token.price' and price['price']['currency'] == 'USD'
    report = runtime.dispatch({'id': 'report', 'action': 'getTokenStatistics', 'payload': {'filters': {'session': 's1'}}})
    assert report['type'] == 'token.statistics'
    assert report['statistics']['totals']['calls'] == 1
    assert report['statistics']['totals']['costs']['USD'] == 5.55
    assert 'records' not in report['statistics']
    export = runtime.dispatch({'id': 'csv', 'action': 'exportTokenStatistics', 'payload': {'filters': {'session': 's1'}}})
    assert export['type'] == 'token.csv' and export['filename'].endswith('.csv')
    assert len(list(csv.DictReader(io.StringIO(export['content'])))) == 1
