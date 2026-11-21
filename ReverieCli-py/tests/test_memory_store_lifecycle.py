"""Memory transactions must release SQLite handles without relying on GC."""

import sqlite3

import pytest

from reverie.memory.store import MemoryStore
from reverie.session.aio_store import AiOMemoryStore


@pytest.fixture(params=[MemoryStore, AiOMemoryStore])
def store_type(request):
    return request.param


@pytest.fixture
def connections(monkeypatch):
    opened = []
    original = sqlite3.connect

    def connect(*args, **kwargs):
        connection = original(*args, **kwargs)
        opened.append(connection)
        return connection

    monkeypatch.setattr(sqlite3, "connect", connect)
    yield opened
    for connection in opened:
        connection.close()


def assert_closed(connections):
    assert connections
    for connection in connections:
        with pytest.raises(sqlite3.ProgrammingError, match="closed"):
            connection.execute("SELECT 1")


def test_memory_store_commits_and_closes_connections(tmp_path, connections, store_type):
    store = store_type(tmp_path)
    with store._connect() as connection:
        if store_type is AiOMemoryStore:
            assert connection.execute("PRAGMA synchronous").fetchone()[0] == 2
        connection.execute("INSERT INTO memory_meta(key, value) VALUES('lifecycle', 'committed')")
    with store._connect() as connection:
        value = connection.execute("SELECT value FROM memory_meta WHERE key='lifecycle'").fetchone()[0]

    assert value == "committed"
    assert_closed(connections)


def test_memory_store_rolls_back_and_closes_on_error(tmp_path, connections, store_type):
    store = store_type(tmp_path)
    with pytest.raises(RuntimeError, match="failed write"):
        with store._connect() as connection:
            connection.execute("INSERT INTO memory_meta(key, value) VALUES('lifecycle', 'rolled back')")
            raise RuntimeError("failed write")
    with store._connect() as connection:
        row = connection.execute("SELECT value FROM memory_meta WHERE key='lifecycle'").fetchone()

    assert row is None
    assert_closed(connections)


def test_memory_store_releases_database_for_project_removal(tmp_path, connections, store_type):
    store = store_type(tmp_path)
    assert store.load_items() == []
    assert store.status()["revision"] == 0

    # The fixture retains every connection, preventing GC from hiding Windows locks.
    moved = store.database_path.with_suffix(".moved")
    store.database_path.rename(moved)
    assert moved.is_file()
    assert_closed(connections)
