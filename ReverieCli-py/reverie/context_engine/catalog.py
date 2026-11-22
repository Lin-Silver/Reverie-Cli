"""In-process Python catalog with transactional manifest, FTS and revision checks."""

from contextlib import contextmanager
from pathlib import Path, PurePosixPath, PureWindowsPath
import sqlite3
from threading import RLock

from . import catalog_search
from .text_analysis import expand_identifier_text, subword_expansion
from .indexer import CodebaseIndexer
from .storage_errors import ContextStorageError
from .storage_paths import database_argument, readonly_uri


class Catalog:
    APPLICATION_ID = 0x52565059  # RVPY; distinct from the historical Rust RVCE database.
    SCHEMA_VERSION = CodebaseIndexer._CONTENT_INDEX_SCHEMA_VERSION

    def __init__(self, database):
        self.database = Path(database).resolve()
        self._writer = None
        self._reader = None
        self._lock = RLock()
        self._closed = False

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()

    def _open(self):
        if self._closed:
            raise ContextStorageError("Context Engine catalog has been closed")
        if self._writer is not None:
            return
        self.database.parent.mkdir(parents=True, exist_ok=True)
        writer = sqlite3.connect(database_argument(self.database), timeout=30,
                                 isolation_level=None, check_same_thread=False)
        try:
            identity = writer.execute("PRAGMA application_id").fetchone()[0]
            version = writer.execute("PRAGMA user_version").fetchone()[0]
            if identity == 0:
                writer.execute("BEGIN IMMEDIATE")
                identity = writer.execute("PRAGMA application_id").fetchone()[0]
                version = writer.execute("PRAGMA user_version").fetchone()[0]
                if identity == 0:
                    if version or writer.execute("SELECT COUNT(*) FROM sqlite_schema WHERE type='table'").fetchone()[0]:
                        raise ContextStorageError("Refusing to overwrite an unrelated SQLite database")
                    CodebaseIndexer._initialize_content_index(writer)
                    writer.execute("CREATE TABLE state (id INTEGER PRIMARY KEY CHECK(id=1), "
                                   "root TEXT NOT NULL,revision INTEGER NOT NULL)")
                    writer.execute("INSERT INTO state VALUES(1,'',0)")
                    writer.execute("CREATE TABLE files (path TEXT PRIMARY KEY,size INTEGER NOT NULL CHECK(size>=0), "
                                   "modified_ns INTEGER NOT NULL,indexed INTEGER NOT NULL)")
                    writer.execute("CREATE INDEX file_path_nocase ON files(path COLLATE NOCASE)")
                    writer.execute(f"PRAGMA application_id={self.APPLICATION_ID}")
                    identity, version = self.APPLICATION_ID, self.SCHEMA_VERSION
                writer.commit()
            if identity != self.APPLICATION_ID or version != self.SCHEMA_VERSION:
                raise ContextStorageError("Incompatible Context Engine database; back up and rebuild its derived index")
            if writer.execute("PRAGMA journal_mode").fetchone()[0].lower() != "wal":
                writer.execute("PRAGMA journal_mode=WAL")
            writer.execute("PRAGMA foreign_keys=ON")
            writer.execute("PRAGMA synchronous=NORMAL")
            reader = sqlite3.connect(readonly_uri(self.database), uri=True, timeout=10,
                                     isolation_level=None, check_same_thread=False)
        except Exception:
            writer.close()
            raise
        self._writer, self._reader = writer, reader

    @staticmethod
    def _state(connection):
        root, revision = connection.execute("SELECT root,revision FROM state WHERE id=1").fetchone()
        return {"root": root, "revision": revision}

    @contextmanager
    def _read(self, expected_revision=None):
        reader = self._reader
        reader.execute("BEGIN")
        try:
            if expected_revision is not None and self._state(reader)["revision"] != expected_revision:
                raise ContextStorageError("Context index changed since it was loaded")
            yield reader
        finally:
            reader.rollback()

    @staticmethod
    def _relative(path):
        if not isinstance(path, str) or not path or "\\" in path or PureWindowsPath(path).drive:
            raise ValueError("Invalid workspace-relative path")
        pieces = PurePosixPath(path).parts
        if not pieces or any(piece in {"/", ".", ".."} for piece in pieces) or "/".join(pieces) != path:
            raise ValueError("Invalid workspace-relative path")
        return path

    def _begin(self, root, replace, expected_revision):
        if self._writer.in_transaction:
            raise ContextStorageError("Context index update already started")
        self._writer.execute("BEGIN IMMEDIATE")
        state = self._state(self._writer)
        if state["revision"] != expected_revision:
            raise ContextStorageError("Context index changed while preparing an update")
        if state["root"] and state["root"] != root:
            raise ContextStorageError("Context index is bound to a different workspace")
        if replace:
            for table in ("chunk_search", "content_search"):
                self._writer.execute(f"INSERT INTO {table}({table}) VALUES('delete-all')")
            for table in ("chunk_documents", "content_documents", "fts_delete_payloads", "files"):
                self._writer.execute(f"DELETE FROM {table}")
        if not state["root"]:
            self._writer.execute("UPDATE state SET root=? WHERE id=1", (root,))

    def _remove(self, path):
        path = self._relative(path)
        CodebaseIndexer._delete_fts_rows(self._writer, "content_documents", "content_search",
                                         ("body", "subwords"), path)
        CodebaseIndexer._delete_fts_rows(self._writer, "chunk_documents", "chunk_search",
                                         ("name", "signature", "documentation", "body", "subwords"), path)
        self._writer.execute("DELETE FROM files WHERE path=?", (path,))

    def _insert_search(self, table, rowid, fields):
        names = ("body", "subwords") if table == "content_search" else (
            "name", "signature", "documentation", "body", "subwords")
        placeholders = ",".join("?" for _ in range(len(fields) + 1))
        self._writer.execute(f"INSERT INTO {table}(rowid,{','.join(names)}) VALUES({placeholders})",
                             (rowid, *fields))
        self._writer.execute("INSERT INTO fts_delete_payloads VALUES(?,?,?)",
                             (table, rowid, CodebaseIndexer._pack_fts_delete_payload(tuple(fields))))

    def _insert(self, document):
        path = self._relative(document["path"])
        self._remove(path)
        body = document.get("body")
        self._writer.execute("INSERT INTO files VALUES(?,?,?,?)",
                             (path, document["size"], document["modified_ns"], int(body is not None)))
        if body is None:
            return
        rowid = self._writer.execute("INSERT INTO content_documents(path) VALUES(?)", (path,)).lastrowid
        self._insert_search("content_search", rowid, (body, subword_expansion(body, limit=768)))
        for chunk in document.get("chunks", []):
            rowid = self._writer.execute(
                "INSERT INTO chunk_documents(path,symbol,kind,start_line,end_line) VALUES(?,?,?,?,?)",
                (path, chunk["symbol"], chunk["kind"], chunk["start_line"], chunk["end_line"]),
            ).lastrowid
            name = " ".join((chunk["symbol"], expand_identifier_text(chunk["name"]), chunk["kind"].lower()))
            signature = str(chunk.get("signature", "") or "")[:4096]
            documentation = str(chunk.get("documentation", "") or "")[:8192]
            body = str(chunk.get("body", "") or "")
            if len(body) > 49152:
                body = body[:36864] + "\n...\n" + body[-8192:]
            self._insert_search("chunk_search", rowid, (
                name, signature, documentation, body,
                subword_expansion(chunk["symbol"], signature, body, limit=192)))

    def _respond(self, operation, fields):
        if operation == "hello":
            from .. import __version__
            return {"protocol": 1, "version": __version__, "backend": "python"}
        if operation == "begin":
            return self._begin(fields["root"], fields["replace"], fields["expected_revision"])
        if operation == "rollback":
            return self._writer.rollback()
        if operation in {"apply", "commit"}:
            if not self._writer.in_transaction:
                raise ContextStorageError("Context index update has not started")
            if operation == "apply":
                for path in fields["removed"]:
                    self._remove(path)
                for document in fields["documents"]:
                    self._insert(document)
                return None
            self._writer.execute("UPDATE state SET revision=revision+1 WHERE id=1")
            state = self._state(self._writer)
            self._writer.commit()
            return state
        with self._read(fields.get("expected_revision")) as reader:
            if operation == "state":
                return self._state(reader)
            if operation == "files":
                rows = reader.execute("SELECT path,size,modified_ns FROM files ORDER BY path")
                return [dict(zip(("path", "size", "modified_ns"), row)) for row in rows]
            if operation == "search":
                return catalog_search.ranked(reader, fields["weights"], fields["limit"], fields["chunks"])
            if operation == "frequencies":
                return {"total": catalog_search.total(reader),
                        "terms": catalog_search.frequencies(reader, fields["terms"])}
            if operation == "total":
                return catalog_search.total(reader)
            if operation == "paths":
                return catalog_search.paths(reader, fields["prefix"], fields["limit"])
            raise ValueError(f"Unknown Context Engine operation: {operation}")

    def request(self, operation, **fields):
        with self._lock:
            try:
                self._open()
                return self._respond(operation, fields)
            except (ContextStorageError, sqlite3.Error, OSError, ValueError, KeyError, TypeError) as error:
                if self._writer is not None and operation in {"begin", "apply", "commit"}:
                    self._writer.rollback()
                if isinstance(error, ContextStorageError):
                    raise
                raise ContextStorageError(str(error)) from error

    def close(self):
        with self._lock:
            self._closed = True
            for connection in (self._reader, self._writer):
                if connection is not None:
                    connection.close()
            self._reader = self._writer = None
