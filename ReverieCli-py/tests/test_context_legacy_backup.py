"""Historical Rust data is backed up and retained when Python rebuilds its index."""

import hashlib
import json
from pathlib import Path
import shutil
import sqlite3

import pytest

from reverie.context_engine.factory import create_indexer
from reverie.context_engine.legacy_backup import backup_legacy_index, RUST_APPLICATION_ID
from reverie.context_engine.storage_errors import ContextStorageError


def _legacy(cache, root):
    cache.mkdir()
    database = cache / "native-search.sqlite3"
    with sqlite3.connect(database) as connection:
        connection.execute(f"PRAGMA application_id={RUST_APPLICATION_ID}")
        connection.execute("PRAGMA user_version=1")
        connection.execute("CREATE TABLE state(id INTEGER PRIMARY KEY,root TEXT,revision INTEGER)")
        connection.execute("INSERT INTO state VALUES(1,?,7)", (str(root),))
        connection.execute("CREATE TABLE retained(value TEXT)")
        connection.execute("INSERT INTO retained VALUES('old index')")
    snapshot = cache / "native-snapshots" / "7"
    snapshot.mkdir(parents=True)
    (snapshot / "files.json").write_text('{"retained":true}', encoding="utf-8")
    return database, snapshot


def test_backup_restore_and_python_continuation_preserve_original_data(tmp_path):
    root = tmp_path / "workspace"
    root.mkdir()
    (root / "invoice.py").write_text("def verifyInvoice(): return 'billing'\n", encoding="utf-8")
    cache = tmp_path / "cache"
    original, snapshot = _legacy(cache, root)
    original_bytes = original.read_bytes()
    snapshot_bytes = (snapshot / "files.json").read_bytes()
    indexer = create_indexer(root, cache)
    try:
        backups = list((cache / "context-engine-backups" / "mixed-2.5.5").glob("*/manifest.json"))
        assert len(backups) == 1
        backup = backups[0].parent
        manifest = json.loads(backups[0].read_text(encoding="utf-8"))
        assert manifest["revision"] == 7
        assert manifest["sha256"]["files.json"] == hashlib.sha256(snapshot_bytes).hexdigest()
        restored = tmp_path / "restored.sqlite3"
        shutil.copy2(backup / original.name, restored)
        with sqlite3.connect(restored) as connection:
            assert connection.execute("SELECT value FROM retained").fetchone()[0] == "old index"
            assert connection.execute("SELECT revision FROM state").fetchone()[0] == 7
        assert indexer.full_index(show_progress=False).success
        assert indexer.get_index_status()["backend"] == "python"
        assert indexer.search_code_chunks([("verifyInvoice", 1.0)])
        assert original.read_bytes() == original_bytes
        assert (snapshot / "files.json").read_bytes() == snapshot_bytes
    finally:
        indexer.close()


def test_damaged_backup_does_not_get_silently_overwritten(tmp_path):
    root = tmp_path / "workspace"
    root.mkdir()
    original, _ = _legacy(tmp_path / "cache", root)
    backup = backup_legacy_index(original.parent)
    (backup / original.name).write_bytes(b"damaged")
    with pytest.raises(ContextStorageError, match="damaged"):
        backup_legacy_index(original.parent)
    assert (backup / original.name).read_bytes() == b"damaged"
    with sqlite3.connect(original) as connection:
        assert connection.execute("SELECT revision FROM state").fetchone()[0] == 7
