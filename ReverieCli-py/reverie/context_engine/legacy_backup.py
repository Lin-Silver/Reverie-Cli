"""Preserve a consistent historical Rust index before rebuilding Python derivatives."""

from contextlib import closing
import hashlib
import json
import os
from pathlib import Path
import shutil
import sqlite3
from tempfile import TemporaryDirectory

from .storage_errors import ContextStorageError
from .storage_paths import database_argument, readonly_uri


RUST_APPLICATION_ID = 0x52564345
_SNAPSHOT_FILES = ("index.json", "files.json", "symbols.json.gz", "dependencies.json.gz")


def _digest(path):
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def is_legacy_database(path):
    path = Path(path)
    if not path.is_file():
        return False
    with closing(sqlite3.connect(readonly_uri(path), uri=True)) as connection:
        return connection.execute("PRAGMA application_id").fetchone()[0] == RUST_APPLICATION_ID


def backup_legacy_index(cache_dir, *, database=None):
    cache_dir = Path(cache_dir).resolve()
    database = Path(database).resolve() if database else cache_dir / "native-search.sqlite3"
    if not database.is_file() or not is_legacy_database(database):
        return None
    backup_root = cache_dir / "context-engine-backups" / "mixed-2.5.5"
    backup_root.mkdir(parents=True, exist_ok=True)
    if backup_root.resolve() != backup_root:
        raise ContextStorageError("Historical backup directory is a link; original index retained")
    with TemporaryDirectory(prefix="candidate-", dir=backup_root) as temporary:
        candidate = Path(temporary)
        target = candidate / database.name
        with closing(sqlite3.connect(readonly_uri(database), uri=True, timeout=30)) as source:
            source.execute("BEGIN")
            state = source.execute("SELECT root,revision FROM state WHERE id=1").fetchone()
            if source.execute("PRAGMA user_version").fetchone()[0] != 1:
                raise ContextStorageError("Unknown historical Rust index schema; original index retained")
            with closing(sqlite3.connect(database_argument(target))) as destination:
                source.backup(destination)
                if destination.execute("SELECT root,revision FROM state WHERE id=1").fetchone() != state:
                    raise ContextStorageError("Historical index backup revision mismatch")
                if destination.execute("PRAGMA quick_check").fetchone()[0] != "ok":
                    raise ContextStorageError("Historical index backup integrity check failed")
            snapshot = cache_dir / "native-snapshots" / str(state[1])
            if snapshot.is_dir():
                if snapshot.resolve() != snapshot:
                    raise ContextStorageError("Historical snapshot is a link; original index retained")
                for name in _SNAPSHOT_FILES:
                    original = snapshot / name
                    if not original.is_file():
                        continue
                    if original.resolve() != original:
                        raise ContextStorageError("Historical snapshot file is a link")
                    before = _digest(original)
                    shutil.copy2(original, candidate / name)
                    if _digest(candidate / name) != before or _digest(original) != before:
                        raise ContextStorageError("Historical snapshot changed during backup")
            source.rollback()
        hashes = {path.name: _digest(path) for path in candidate.iterdir()}
        manifest = {"source": str(database), "application_id": RUST_APPLICATION_ID, "schema": 1,
                    "root": state[0], "revision": state[1], "sha256": hashes,
                    "continuation": "Original retained; Python rebuilds derived structural and lexical indexes"}
        (candidate / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
        final = backup_root / (database.name + f"-r{state[1]}-" + hashes[database.name][:16])
        if not final.exists():
            try:
                os.rename(candidate, final)
            except FileExistsError:
                pass
        if final.exists():
            existing = json.loads((final / "manifest.json").read_text(encoding="utf-8"))
            if existing != manifest or any(not (final / name).is_file() or _digest(final / name) != digest
                                           for name, digest in hashes.items()):
                raise ContextStorageError("Existing historical index backup is damaged; original index retained")
        return final


def resolve_database(path, *, rebuild=False):
    path = Path(path).resolve()
    if is_legacy_database(path):
        if rebuild:
            backup_legacy_index(path.parent, database=path)
        derivative = path.with_name(path.name + ".python.sqlite3")
        if not rebuild and not derivative.is_file():
            raise ContextStorageError("Historical Rust index retained; run index to build its Python replacement")
        return derivative
    return path
