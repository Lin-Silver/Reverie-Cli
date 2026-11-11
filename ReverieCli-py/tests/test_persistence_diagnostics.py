import io
import json
import logging
import sqlite3
from types import SimpleNamespace

import pytest

from reverie import sdk_bridge
from reverie.session.sqlite_manager import SQLiteSessionManager


def test_sqlite_failure_logs_database_and_traceback_while_rolling_back(tmp_path, caplog):
    store = SQLiteSessionManager(tmp_path)
    session = store.create_session('Saved conversation')
    private_content = 'private-message-that-must-not-be-logged'
    with caplog.at_level(logging.ERROR):
        with pytest.raises(sqlite3.OperationalError, match='no such table') as failure:
            with store.connect() as database:
                database.execute('BEGIN IMMEDIATE')
                database.execute('UPDATE conversations SET name=? WHERE id=?', (private_content, session.id))
                database.execute('SELECT * FROM missing_diagnostic_table')
    assert store.load_session(session.id).name == 'Saved conversation'
    assert str(store.database_path) in caplog.text
    assert private_content not in caplog.text
    assert any(record.exc_info and record.exc_info[1] is failure.value for record in caplog.records)


def test_desktop_sqlite_error_keeps_jsonl_protocol_and_omits_request_content(monkeypatch, caplog):
    private_content = 'private-prompt-and-credential-that-must-not-be-logged'

    class Bridge:
        def __init__(self, **_kwargs):
            self.rats_runtime = SimpleNamespace(shutdown=lambda: None)

        def dispatch(self, message):
            if message['action'] == 'listSessions':
                raise sqlite3.OperationalError('database is locked')
            return {'id': message['id'], 'type': 'shutdown'}

    incoming = [
        {'id': 'diagnostic-request', 'action': 'listSessions',
         'payload': {'prompt': private_content, 'configuration': {'api_key': private_content}}},
        {'id': 'shutdown-request', 'action': 'shutdown'},
    ]
    output = io.StringIO()
    monkeypatch.setattr(sdk_bridge, 'ReverieSdkBridge', Bridge)
    monkeypatch.setattr(sdk_bridge.sys, 'stdin', io.StringIO('\n'.join(map(json.dumps, incoming)) + '\n'))
    monkeypatch.setattr(sdk_bridge.sys, 'stdout', output)
    monkeypatch.setattr(sdk_bridge, '_configure_utf8_stdio', lambda: None)
    with caplog.at_level(logging.ERROR):
        assert sdk_bridge.main() == 0
    assert [json.loads(line) for line in output.getvalue().splitlines()] == [
        {'type': 'ready', 'protocol_version': 1},
        {'id': 'diagnostic-request', 'type': 'error', 'error': 'database is locked'},
        {'id': 'shutdown-request', 'type': 'shutdown'},
    ]
    assert 'listSessions' in caplog.text and 'diagnostic-request' in caplog.text
    assert 'database is locked' in caplog.text
    assert private_content not in output.getvalue() + caplog.text
    assert any(record.exc_info and isinstance(record.exc_info[1], sqlite3.Error) for record in caplog.records)
