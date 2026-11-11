"""Transactional conversation persistence; JSON files remain migration inputs."""

from __future__ import annotations

from datetime import datetime
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Dict, Optional
import hashlib
import json
import logging
import sqlite3
import re
import threading
import time
import uuid

from .manager import Session, SessionInfo, SessionManager
from .roles import from_stored_messages, to_stored_messages

_INITIALIZE_LOCK = threading.Lock()


def _json(value):
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"), sort_keys=True)


def _digest(value):
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


class SQLiteSessionManager(SessionManager):
    """One database per owner workspace, independent of executor checkout."""

    def __init__(self, base_dir, project_root=None, memory_indexer=None,
                 always_new_session=False, refresh_memory_index_on_save=False,
                 navigation=True):
        self.navigation = navigation
        super().__init__(base_dir, project_root, memory_indexer, always_new_session,
                         refresh_memory_index_on_save)
        self.database_path = self.base_dir / "conversations.sqlite3"
        self._initialize_database()

    @contextmanager
    def connect(self):
        connection = sqlite3.connect(self.database_path, timeout=10)
        connection.row_factory = sqlite3.Row
        started = time.monotonic()
        try:
            connection.execute("PRAGMA foreign_keys=ON")
            connection.execute("PRAGMA synchronous=FULL")
            with connection:
                yield connection
        except sqlite3.Error as error:
            logging.getLogger(__name__).exception(
                "Conversation database operation failed: database=%s elapsed_seconds=%.3f sqlite_errorcode=%s sqlite_errorname=%s",
                self.database_path, time.monotonic() - started,
                getattr(error, 'sqlite_errorcode', None), getattr(error, 'sqlite_errorname', None),
            )
            raise
        finally:
            connection.close()

    def _initialize_database(self):
        with _INITIALIZE_LOCK, self.connect() as db:
            for attempt in range(20):
                try:
                    if db.execute("PRAGMA journal_mode").fetchone()[0] != "wal":
                        db.execute("PRAGMA journal_mode=WAL")
                    break
                except sqlite3.OperationalError as error:
                    if "locked" not in str(error) or attempt == 19:
                        raise
                    time.sleep(0.05)
            version = db.execute("PRAGMA user_version").fetchone()[0]
            if version > 7:
                raise RuntimeError("Conversation database requires a newer Reverie version.")
            if version == 7:
                return
            if version:
                # Online backup preserves a consistent WAL snapshot before upgrades.
                self.backup(self.base_dir / f"conversations.before-v{version + 1}.sqlite3")
            db.executescript("""
                CREATE TABLE IF NOT EXISTS conversations (
                    id TEXT PRIMARY KEY, name TEXT NOT NULL, created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL, metadata TEXT NOT NULL,
                    revision INTEGER NOT NULL DEFAULT 1, message_count INTEGER NOT NULL DEFAULT 0,
                    deleted INTEGER NOT NULL DEFAULT 0);
                CREATE TABLE IF NOT EXISTS messages (
                    session_id TEXT NOT NULL REFERENCES conversations(id), sequence INTEGER NOT NULL,
                    id TEXT NOT NULL UNIQUE, payload TEXT NOT NULL, digest TEXT NOT NULL,
                    PRIMARY KEY(session_id,sequence));
                CREATE TABLE IF NOT EXISTS history_versions (
                    session_id TEXT NOT NULL, revision INTEGER NOT NULL, payload TEXT NOT NULL,
                    PRIMARY KEY(session_id,revision));
                CREATE TABLE IF NOT EXISTS navigation (key TEXT PRIMARY KEY,value TEXT);
                CREATE TABLE IF NOT EXISTS conversation_read_states (session_id TEXT PRIMARY KEY REFERENCES conversations(id),unread INTEGER NOT NULL DEFAULT 0);
                CREATE TABLE IF NOT EXISTS migrations (id TEXT PRIMARY KEY,digest TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS stream_fragments (
                    session_id TEXT NOT NULL, run_id TEXT NOT NULL, kind TEXT NOT NULL,
                    content TEXT NOT NULL, updated_at TEXT NOT NULL,
                    PRIMARY KEY(session_id,run_id,kind));
                CREATE TABLE IF NOT EXISTS stream_chunks (
                    sequence INTEGER PRIMARY KEY AUTOINCREMENT,session_id TEXT NOT NULL,
                    run_id TEXT NOT NULL,kind TEXT NOT NULL,content TEXT NOT NULL,updated_at TEXT NOT NULL);
                CREATE INDEX IF NOT EXISTS stream_owner ON stream_chunks(session_id,run_id,sequence);
                CREATE TABLE IF NOT EXISTS conversation_events (
                    id TEXT PRIMARY KEY,session_id TEXT NOT NULL REFERENCES conversations(id),digest TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS task_runs (
                    id TEXT PRIMARY KEY,session_id TEXT NOT NULL REFERENCES conversations(id),
                    configuration_revision INTEGER NOT NULL,configuration TEXT NOT NULL,
                    execution_root TEXT NOT NULL,state TEXT NOT NULL,revision INTEGER NOT NULL DEFAULT 1,
                    result TEXT NOT NULL DEFAULT '{}',created_at TEXT NOT NULL,updated_at TEXT NOT NULL);
                CREATE INDEX IF NOT EXISTS task_session ON task_runs(session_id,created_at DESC);
                CREATE TABLE IF NOT EXISTS configuration_versions (
                    session_id TEXT NOT NULL, revision INTEGER NOT NULL,
                    payload TEXT NOT NULL, created_at TEXT NOT NULL,
                    PRIMARY KEY(session_id,revision));
                CREATE INDEX IF NOT EXISTS conversation_updated ON conversations(deleted,updated_at DESC);
                CREATE VIRTUAL TABLE IF NOT EXISTS message_search USING fts5(payload,content='messages',content_rowid='rowid',tokenize='trigram');
                CREATE TRIGGER IF NOT EXISTS message_search_insert AFTER INSERT ON messages BEGIN
                    INSERT INTO message_search(rowid,payload) VALUES (new.rowid,new.payload);
                END;
                CREATE TRIGGER IF NOT EXISTS message_search_delete AFTER DELETE ON messages BEGIN
                    INSERT INTO message_search(message_search,rowid,payload) VALUES ('delete',old.rowid,old.payload);
                END;
                CREATE TRIGGER IF NOT EXISTS message_search_update AFTER UPDATE ON messages BEGIN
                    INSERT INTO message_search(message_search,rowid,payload) VALUES ('delete',old.rowid,old.payload);
                    INSERT INTO message_search(rowid,payload) VALUES (new.rowid,new.payload);
                END;
                INSERT INTO message_search(message_search) VALUES ('rebuild');
                INSERT INTO stream_chunks(session_id,run_id,kind,content,updated_at)
                    SELECT session_id,run_id,kind,content,updated_at FROM stream_fragments;
                DELETE FROM stream_fragments;
            """)
            if 'request' not in {row[1] for row in db.execute('PRAGMA table_info(task_runs)')}:
                db.execute("ALTER TABLE task_runs ADD COLUMN request TEXT NOT NULL DEFAULT '{}' ")
            db.execute('PRAGMA user_version=7')

    def migrate_legacy(self, session_id=None, limit=50):
        if session_id is not None and not re.fullmatch(r"[A-Za-z0-9_-]{1,128}", str(session_id)):
            raise ValueError("Invalid conversation identifier.")
        paths = [self.sessions_dir / f"{session_id}.json"] if session_id else self.sessions_dir.glob("*.json")
        imported = 0
        with self.connect() as db:
            known = {row[0] for row in db.execute('SELECT id FROM conversations')}
        for path in paths:
            if path.stem in known:
                continue
            if not path.is_file():
                continue
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
                if not isinstance(data,dict):
                    raise TypeError('Legacy conversation must be a JSON object.')
            except (json.JSONDecodeError,UnicodeDecodeError,TypeError) as error:
                logging.getLogger(__name__).warning('Legacy conversation could not be migrated: path=%s error=%s',path,error)
                if session_id is not None:
                    raise ValueError(f'Legacy conversation could not be migrated: {path}') from error
                continue
            if not self._belongs_to_workspace(data):
                continue
            session = Session.from_dict(data)
            session.metadata = self._merge_scope_metadata(session.metadata)
            session.metadata.setdefault("configuration_origin", "legacy-workspace-default")
            with self.connect() as db:
                db.execute("BEGIN IMMEDIATE")
                if db.execute("SELECT 1 FROM conversations WHERE id=?", (session.id,)).fetchone():
                    continue
                payloads = [_json(item) for item in to_stored_messages(session.messages)]
                db.execute("INSERT INTO conversations VALUES (?,?,?,?,?,1,?,0)",
                           (session.id, session.name, session.created_at, session.updated_at, _json(session.metadata), len(payloads)))
                db.executemany("INSERT INTO messages VALUES (?,?,?,?,?)", [
                    (session.id, index, uuid.uuid4().hex, item, _digest(item)) for index, item in enumerate(payloads)])
                db.execute("INSERT OR IGNORE INTO migrations VALUES (?,?)", (path.stem, _digest(_json(data))))
            imported += 1
            if imported >= limit:
                break
        return imported

    def _generate_session_id(self):
        return uuid.uuid4().hex

    def refresh_generated_session_names(self):
        # Migrated inputs are immutable. New titles update the authoritative store.
        return 0

    def _remember_base(self, session, revision, payloads, offset=0):
        session._storage_revision = revision
        session._storage_base = {
            "name": session.name, "metadata": json.loads(_json(session.metadata)),
            "messages": [_digest(item) for item in payloads], "offset":offset,
        }

    def _write_session(self, session, *, touch_updated_at=True):
        session.metadata = self._merge_scope_metadata(session.metadata)
        payloads = [_json(item) for item in to_stored_messages(session.messages)]
        original_payloads = payloads
        digests = [_digest(item) for item in payloads]
        base = getattr(session, "_storage_base", None)
        expected = getattr(session, "_storage_revision", 0)
        now = datetime.now().isoformat() if touch_updated_at else session.updated_at
        reconcile = False
        with self.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute("SELECT * FROM conversations WHERE id=?", (session.id,)).fetchone()
            if row and row["deleted"]:
                raise RuntimeError("Conversation was deleted; a stale executor cannot restore it.")
            if row is None:
                revision = 1
                db.execute("INSERT INTO conversations VALUES (?,?,?,?,?,?,?,0)",
                           (session.id, session.name, session.created_at, now, _json(session.metadata), revision, len(payloads)))
                start = 0
            else:
                if base is None:
                    raise RuntimeError("Conversation revision is missing; reload before saving.")
                stored_meta = json.loads(row["metadata"])
                for key in base["metadata"].keys() | session.metadata.keys():
                    before = base["metadata"].get(key)
                    after = session.metadata.get(key)
                    if before == after:
                        continue
                    if row["revision"] != expected and stored_meta.get(key) not in (before, after):
                        raise RuntimeError(f"Conversation metadata revision conflict: {key}")
                    if key in session.metadata:
                        stored_meta[key] = after
                    else:
                        stored_meta.pop(key, None)
                name = session.name if session.name != base["name"] else row["name"]
                prefix = base["messages"]
                append = len(digests) >= len(prefix) and digests[:len(prefix)] == prefix
                if append:
                    additions = payloads[len(prefix):]
                    if not additions and stored_meta == json.loads(row["metadata"]) and name == row["name"] and row["revision"] == expected:
                        session.metadata = stored_meta
                        session.name = name
                        return session.to_dict()
                    start = row["message_count"]
                    reconcile = start != base.get('offset',0) + len(prefix)
                    payloads = additions
                else:
                    if row["revision"] != expected:
                        raise ValueError("Conversation history revision conflict; reload before replacing history.")
                    old = [json.loads(item[0]) for item in db.execute("SELECT payload FROM messages WHERE session_id=? ORDER BY sequence", (session.id,))]
                    db.execute("INSERT OR IGNORE INTO history_versions VALUES (?,?,?)", (session.id, row["revision"], _json(old)))
                    start = base.get('offset',0)
                    db.execute("DELETE FROM messages WHERE session_id=? AND sequence>=?", (session.id,start))
                revision = row["revision"] + 1
                session.metadata = stored_meta
                session.name = name
                db.execute("UPDATE conversations SET name=?,metadata=?,updated_at=?,revision=?,message_count=? WHERE id=?",
                           (name, _json(stored_meta), now, revision, start + len(payloads), session.id))
            entries = [(session.id,start + index,uuid.uuid4().hex,item,_digest(item)) for index,item in enumerate(payloads)]
            db.executemany("INSERT INTO messages VALUES (?,?,?,?,?)",entries)
            self._record_appended_messages(db,entries)
            snapshot = session.metadata.get("runtime_config")
            if snapshot is not None and (base is None or snapshot != base["metadata"].get("runtime_config")):
                db.execute("INSERT INTO configuration_versions VALUES (?,?,?,?)",
                           (session.id, revision, _json(snapshot), now))
        # Reconcile concurrent appends before retaining the next save baseline.
        if reconcile:
            loaded = self._read_session(session.id,active_only=bool(base.get('offset',0)))
            session.messages = loaded.messages
            session.metadata = loaded.metadata
            session.name = loaded.name
            session.updated_at = loaded.updated_at
            session._storage_revision = loaded._storage_revision
            session._storage_base = loaded._storage_base
        else:
            session.updated_at = now
            self._remember_base(session, revision, original_payloads,base.get('offset',0) if base else 0)
        self._session_index[session.id] = self._session_index_entry(session)
        return session.to_dict()

    def _record_appended_messages(self, db, entries):
        pass

    def _read_session(self, session_id, *, active_only=False):
        with self.connect() as db:
            db.execute("BEGIN")
            row = db.execute("SELECT * FROM conversations WHERE id=? AND deleted=0", (session_id,)).fetchone()
            if row is None:
                return None
            metadata = json.loads(row['metadata'])
            offset = int(metadata.get('active_context_start',0)) if active_only else 0
            payloads = [item[0] for item in db.execute("SELECT payload FROM messages WHERE session_id=? AND sequence>=? ORDER BY sequence", (session_id,offset))]
            session = Session(row["id"], row["name"], row["created_at"], row["updated_at"],
                              from_stored_messages([json.loads(item) for item in payloads]), metadata)
            self._remember_base(session, row["revision"], payloads,offset)
            return session

    def load_session(self, session_id):
        self.migrate_legacy(session_id)
        session = self._read_session(str(session_id),active_only=True)
        if session is not None:
            self._current_session = session
            self._save_state(session.id)
        return session

    def _save_state(self, session_id):
        if not self.navigation:
            return
        with self.connect() as db:
            db.execute("INSERT OR REPLACE INTO navigation VALUES ('selected',?)", (session_id,))

    def _load_state(self):
        with self.connect() as db:
            row = db.execute("SELECT value FROM navigation WHERE key='selected'").fetchone()
        return {"current_session_id": row[0]} if row else super()._load_state()

    def _save_session_index(self, *, force=True):
        self._session_index_dirty = False

    def flush_session_index(self):
        self._session_index_dirty = False

    def _stamp_session_file_mtime(self, session_id):
        return getattr(self._current_session, "_storage_revision", 0)

    def list_sessions(self):
        self.migrate_legacy(limit=50)
        with self.connect() as db:
            rows = db.execute("SELECT id,name,created_at,updated_at,message_count FROM conversations WHERE deleted=0 ORDER BY updated_at DESC").fetchall()
            known = {item[0] for item in db.execute("SELECT id FROM conversations")}
        result = [SessionInfo(*row) for row in rows]
        # Existing compact index allows unmigrated conversations to remain visible.
        result.extend(SessionInfo(entry["id"],entry["name"],entry["created_at"],entry["updated_at"],entry["message_count"])
                      for entry in self._session_index.values() if entry["id"] not in known)
        result.sort(key=lambda item: item.updated_at, reverse=True)
        return result

    def delete_session(self, session_id):
        self.migrate_legacy(session_id)
        with self.connect() as db:
            result = db.execute("UPDATE conversations SET deleted=1,revision=revision+1 WHERE id=? AND deleted=0", (session_id,)).rowcount
        self._session_index.pop(session_id, None)
        with self.connect() as db:
            db.execute("DELETE FROM navigation WHERE key='selected' AND value=?",(session_id,))
        if self._current_session and self._current_session.id == session_id:
            self._current_session = None
            self._save_state(None)
        return bool(result)

    def selected_session_id(self):
        return str(self._load_state().get("current_session_id") or "")

    def select_session(self, session_id):
        # Called only by navigation, independently of the loaded executor history.
        with self.connect() as db:
            if not db.execute("SELECT 1 FROM conversations WHERE id=? AND deleted=0", (session_id,)).fetchone():
                raise ValueError("Conversation not found.")
            db.execute("INSERT OR REPLACE INTO navigation VALUES ('selected',?)", (session_id,))
            db.execute('UPDATE conversation_read_states SET unread=0 WHERE session_id=?',(session_id,))

    def mark_read(self,session_id):
        with self.connect() as db:
            db.execute('UPDATE conversation_read_states SET unread=0 WHERE session_id=?',(session_id,))

    def unread_session_ids(self):
        with self.connect() as db:
            return [row[0] for row in db.execute('SELECT r.session_id FROM conversation_read_states r JOIN conversations c ON c.id=r.session_id WHERE r.unread=1 AND c.deleted=0')]

    def save_session(self, session=None):
        session = session or self._current_session
        if session is not None:
            payload = self._write_session(session)
            self._refresh_memory_index_for_session(session.id, payload)

    def update_messages(self, messages):
        # Context carryover repeats a pending request for the model, not a new user event.
        return super().update_messages([message for message in messages if not message.get('context_replay')])

    def update_metadata(self, session_id, changes, *, expected_revision):
        """Update a header without reading or overwriting its transcript."""
        with self.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute("SELECT metadata,revision FROM conversations WHERE id=? AND deleted=0", (session_id,)).fetchone()
            if row is None:
                raise ValueError("Conversation not found.")
            if row["revision"] != expected_revision:
                raise ValueError("Conversation revision conflict; reload before changing configuration.")
            metadata = json.loads(row["metadata"])
            metadata.update(changes)
            revision = row["revision"] + 1
            now = datetime.now().isoformat()
            db.execute("UPDATE conversations SET metadata=?,revision=?,updated_at=? WHERE id=?", (_json(metadata),revision,now,session_id))
            if "runtime_config" in changes:
                db.execute("INSERT INTO configuration_versions VALUES (?,?,?,?)", (session_id,revision,_json(changes["runtime_config"]),now))
            return revision

    def archive_states(self):
        with self.connect() as db:
            return {row[0]: bool(row[1]) for row in db.execute("SELECT id,json_extract(metadata,'$.archived') FROM conversations WHERE deleted=0 AND json_type(metadata,'$.archived') IS NOT NULL")}

    def conversation_owners(self):
        with self.connect() as db:
            return {row[0]:{key:value for key,value in (('assistant_id',row[1]),('workspace',row[2])) if value}
                    for row in db.execute("SELECT id,json_extract(metadata,'$.assistant_id'),json_extract(metadata,'$.workspace_path') FROM conversations WHERE deleted=0")}

    def import_legacy_archives(self, session_ids):
        with self.connect() as db:
            if db.execute("SELECT 1 FROM navigation WHERE key='legacy_archive_import_v1'").fetchone():
                return
        for session_id in set(session_ids):
            self.migrate_legacy(session_id)
        with self.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            if db.execute("SELECT 1 FROM navigation WHERE key='legacy_archive_import_v1'").fetchone():
                return
            for session_id in set(session_ids):
                row = db.execute('SELECT metadata FROM conversations WHERE id=? AND deleted=0', (session_id,)).fetchone()
                if row:
                    metadata = json.loads(row[0])
                    if 'archived' not in metadata:
                        metadata['archived'] = True
                        db.execute('UPDATE conversations SET metadata=?,revision=revision+1 WHERE id=?', (_json(metadata),session_id))
            db.execute("INSERT INTO navigation VALUES ('legacy_archive_import_v1','done')")

    def configuration_history(self, session_id):
        from .runtime_config import _without_secrets
        with self.connect() as db:
            return [{"revision":row[0],"config":_without_secrets(json.loads(row[1])),"created_at":row[2]} for row in db.execute(
                "SELECT revision,payload,created_at FROM configuration_versions WHERE session_id=? ORDER BY revision", (session_id,))]

    def append_messages(self, session_id, messages, *, event_id, expected_revision=None):
        """An idempotent append transaction that never replaces a loaded history."""
        payloads = [_json(item) for item in to_stored_messages(messages)]
        digest = _digest(_json(payloads))
        with self.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            row = db.execute('SELECT revision,message_count FROM conversations WHERE id=? AND deleted=0',(session_id,)).fetchone()
            if row is None:
                raise ValueError('Conversation not found.')
            existing = db.execute('SELECT session_id,digest FROM conversation_events WHERE id=?',(event_id,)).fetchone()
            if existing:
                if tuple(existing) != (session_id,digest):
                    raise ValueError('Conversation event identity was reused with different content.')
                return row['revision']
            if expected_revision is not None and expected_revision != row['revision']:
                raise ValueError('Conversation revision conflict.')
            db.execute('INSERT INTO conversation_events VALUES (?,?,?)',(event_id,session_id,digest))
            entries = [(session_id,row['message_count']+index,uuid.uuid5(uuid.NAMESPACE_URL,f'{session_id}:{event_id}:{index}').hex,payload,_digest(payload)) for index,payload in enumerate(payloads)]
            db.executemany('INSERT INTO messages VALUES (?,?,?,?,?)',entries)
            self._record_appended_messages(db,entries)
            db.execute('UPDATE conversations SET revision=revision+1,message_count=message_count+?,updated_at=? WHERE id=?',(len(payloads),datetime.now().isoformat(),session_id))
            return row['revision'] + 1

    def register_run(self, session_id, run_id, configuration, configuration_revision, execution_root, request=None):
        with self.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            existing = db.execute('SELECT session_id,configuration,revision FROM task_runs WHERE id=?',(run_id,)).fetchone()
            if existing:
                if existing['session_id'] != session_id or json.loads(existing['configuration']) != configuration:
                    raise ValueError('Task identity was reused with a different conversation or configuration.')
                return existing['revision']
            if not db.execute('SELECT 1 FROM conversations WHERE id=? AND deleted=0',(session_id,)).fetchone():
                raise ValueError('Conversation not found.')
            # JSON transports serialize integral floats as integers. Compare the
            # saved values rather than their formatting, within the queued version.
            saved = next((row for row in db.execute('SELECT revision,payload FROM configuration_versions WHERE session_id=? AND revision<=? ORDER BY revision DESC',(session_id,configuration_revision)) if json.loads(row['payload'])==configuration),None)
            if saved is None:
                raise ValueError('Task configuration has no saved conversation version.')
            configuration_revision = saved[0]
            now = datetime.now().isoformat()
            db.execute("INSERT INTO task_runs VALUES (?,?,?,?,?,'queued',1,'{}',?,?,?)",(run_id,session_id,configuration_revision,_json(configuration),execution_root,now,now,_json(request or {})))
            return 1

    def update_run(self, session_id, run_id, state, *, expected_revision, execution_root=None, result=None):
        allowed={'queued','running','stopping','waiting_pause','paused','waiting_user','verifying','waiting_incorporation','completed','cancelled','failed','interrupted'}
        if state not in allowed:
            raise ValueError('Invalid task state.')
        with self.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            row = db.execute('SELECT * FROM task_runs WHERE id=? AND session_id=?',(run_id,session_id)).fetchone()
            if row is None or row['revision'] != expected_revision:
                raise ValueError('Task revision or conversation identity conflict.')
            if row['state'] in {'completed','cancelled','failed'} and state != row['state']:
                raise ValueError('A finalized task cannot return to execution.')
            db.execute('UPDATE task_runs SET state=?,revision=revision+1,execution_root=?,result=?,updated_at=? WHERE id=?',(state,execution_root or row['execution_root'],_json(result) if result is not None else row['result'],datetime.now().isoformat(),run_id))
            if state in {'completed','failed','waiting_user','waiting_incorporation'}:
                db.execute('INSERT INTO conversation_read_states VALUES (?,1) ON CONFLICT(session_id) DO UPDATE SET unread=1',(session_id,))
            return expected_revision + 1

    def list_runs(self, session_id, *, limit=60):
        with self.connect() as db:
            return [{**dict(row),'configuration':json.loads(row['configuration']),'result':json.loads(row['result']),'request':json.loads(row['request'])} for row in db.execute('SELECT * FROM task_runs WHERE session_id=? ORDER BY created_at DESC LIMIT ?',(session_id,max(1,min(200,limit))))]

    def recover_runs(self):
        """Resume only work that was durably queued and had no execution effects."""
        with self.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            db.execute("UPDATE task_runs SET state='interrupted',revision=revision+1,updated_at=? WHERE state IN ('running','stopping','waiting_pause','paused','verifying')",(datetime.now().isoformat(),))
            return [{**dict(row),'configuration':json.loads(row['configuration']),'request':json.loads(row['request'])} for row in db.execute("SELECT t.* FROM task_runs t JOIN conversations c ON c.id=t.session_id WHERE t.state='queued' AND c.deleted=0 ORDER BY t.created_at")]

    def export_current_session(self, output_path, format_name='markdown'):
        from .runtime_config import _without_secrets
        session = self._current_session
        if session is None:
            raise ValueError('No active session to export.')
        full = SQLiteSessionManager._read_session(self,session.id)
        payload = full.to_dict()
        if 'runtime_config' in payload['metadata']:
            payload['metadata'] = {**payload['metadata'],'runtime_config':_without_secrets(payload['metadata']['runtime_config'])}
        payload['configuration_versions'] = self.configuration_history(session.id)
        with self.connect() as db:
            payload['tasks'] = []
            for row in db.execute('SELECT * FROM task_runs WHERE session_id=? ORDER BY created_at',(session.id,)):
                task = {**dict(row),'configuration':_without_secrets(json.loads(row['configuration'])),'result':json.loads(row['result'])}
                request = json.loads(task['request'])
                if 'configuration' in request:
                    request['configuration'] = _without_secrets(request['configuration'])
                    task['request'] = _json(request)
                payload['tasks'].append(task)
            payload['history_versions'] = [{'revision':row[0],'messages':json.loads(row[1])} for row in db.execute('SELECT revision,payload FROM history_versions WHERE session_id=? ORDER BY revision',(session.id,))]
        if hasattr(self, 'export_assistant_records'):
            payload['assistant_records'] = self.export_assistant_records(session.id, output_path)
        if format_name.lower() == 'json':
            target = Path(output_path)
            target.parent.mkdir(parents=True,exist_ok=True)
            target.write_text(json.dumps(payload,ensure_ascii=False,indent=2),encoding='utf-8')
            return target
        self._current_session = full
        try:
            target = super().export_current_session(output_path,format_name)
        finally:
            self._current_session = session
        with target.open('a',encoding='utf-8') as output:
            output.write('\n\n## Configuration and task history\n\n```json\n'+json.dumps({key:payload[key] for key in ('configuration_versions','tasks','history_versions','assistant_records') if key in payload},ensure_ascii=False,indent=2)+'\n```\n')
        return target

    def fork_current_session(self, message_count=None, name=None):
        from copy import deepcopy
        source = self._current_session
        if source is not None:
            source = SQLiteSessionManager._read_session(self,source.id)
            self._current_session = source
        forked = super().fork_current_session(message_count, name)
        if "runtime_config" in source.metadata:
            forked.metadata["runtime_config"] = deepcopy(source.metadata["runtime_config"])
            self.save_session(forked)
        return forked

    def rewind_current_session(self, message_count):
        if self._current_session is not None:
            self._current_session = SQLiteSessionManager._read_session(self,self._current_session.id)
            self._current_session.metadata.pop('active_context_start',None)
        return super().rewind_current_session(message_count)

    def rotate_session(self, working_memory, reason='Context threshold reached', handoff_packet=None):
        session = self._current_session
        if session is None:
            raise ValueError('No active conversation to segment.')
        self.save_session(session)
        text = '[WORKING MEMORY - Previous Session Context]\n' + working_memory + '\n[END WORKING MEMORY]'
        if handoff_packet:
            text += '\nStructured handoff memory:\n' + _json(handoff_packet.get('data') or {})
        message = {'role':'system','content':text,'segment_boundary':True}
        payload = _json(to_stored_messages([message])[0])
        with self.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            row = db.execute('SELECT revision,message_count,metadata FROM conversations WHERE id=? AND deleted=0',(session.id,)).fetchone()
            if row is None or row['revision'] != session._storage_revision:
                raise ValueError('Conversation context revision conflict; reload before segmentation.')
            metadata = json.loads(row['metadata'])
            metadata.update(active_context_start=row['message_count'],rotation_reason=reason,has_working_memory=bool(working_memory))
            entry = (session.id,row['message_count'],uuid.uuid4().hex,payload,_digest(payload))
            db.execute('INSERT INTO messages VALUES (?,?,?,?,?)',entry)
            self._record_appended_messages(db,[entry])
            db.execute('UPDATE conversations SET metadata=?,revision=revision+1,message_count=message_count+1,updated_at=? WHERE id=?',(_json(metadata),datetime.now().isoformat(),session.id))
        session.metadata = metadata
        session.messages = [message]
        self._remember_base(session,row['revision']+1,[payload],row['message_count'])
        return session

    def get_page(self, session_id, *, before=None, limit=60):
        self.migrate_legacy(session_id)
        limit = max(1, min(200, int(limit)))
        with self.connect() as db:
            db.execute("BEGIN")
            row = db.execute("SELECT * FROM conversations WHERE id=? AND deleted=0", (session_id,)).fetchone()
            if row is None:
                raise ValueError("Conversation not found.")
            end = row["message_count"] if before is None else min(row["message_count"], max(0, int(before)))
            start = max(0, end-limit)
            messages = [json.loads(item[0]) for item in db.execute("SELECT payload FROM messages WHERE session_id=? AND sequence>=? AND sequence<? ORDER BY sequence", (session_id,start,end))]
            return {"id":row["id"], "name":row["name"], "created_at":row["created_at"], "updated_at":row["updated_at"],
                    "metadata":json.loads(row["metadata"]), "revision":row["revision"],
                    "messages":from_stored_messages(messages), "total":row["message_count"], "before":start if start else None}

    def read_streams(self, session_id):
        with self.connect() as db:
            rows = db.execute('SELECT session_id,run_id,kind,content,updated_at FROM stream_chunks WHERE session_id=? ORDER BY sequence',(session_id,)).fetchall()
        streams = {}
        for row in rows:
            stream = streams.setdefault((row['run_id'],row['kind']),{**dict(row),'content':[],'interrupted':True})
            stream['content'].append(row['content'])
            stream['updated_at'] = row['updated_at']
        return [{**stream,'content':''.join(stream['content'])} for stream in streams.values()]

    def write_stream(self, session_id, run_id, kind, fragment):
        with self.connect() as db:
            db.execute("INSERT INTO stream_chunks(session_id,run_id,kind,content,updated_at) VALUES (?,?,?,?,?)",
                       (session_id,run_id,kind,fragment,datetime.now().isoformat()))

    def clear_stream(self, session_id, run_id):
        with self.connect() as db:
            db.execute("DELETE FROM stream_chunks WHERE session_id=? AND run_id=?", (session_id,run_id))

    def search_sessions(self, query, limit=50, *, offset=0):
        self.migrate_legacy(limit=1000)
        query = str(query).strip()
        if not query:
            return []
        limit = max(1,min(200,int(limit)))
        offset = max(0,int(offset))
        with self.connect() as db:
            if len(query) >= 3:
                rows = db.execute('SELECT c.id,c.name,m.sequence,m.payload FROM message_search f JOIN messages m ON m.rowid=f.rowid JOIN conversations c ON c.id=m.session_id WHERE c.deleted=0 AND message_search MATCH ? ORDER BY c.updated_at DESC,m.sequence DESC LIMIT ? OFFSET ?',('"'+query.replace('"','""')+'"',limit,offset)).fetchall()
            else:
                escaped = query.replace('\\','\\\\').replace('%','\\%').replace('_','\\_')
                rows = db.execute("SELECT c.id,c.name,m.sequence,m.payload FROM messages m JOIN conversations c ON c.id=m.session_id WHERE c.deleted=0 AND m.payload LIKE ? ESCAPE '\\' ORDER BY c.updated_at DESC,m.sequence DESC LIMIT ? OFFSET ?",('%'+escaped+'%',limit,offset)).fetchall()
        return [{"session_id":row[0],"session_name":row[1],"message_index":row[2],"preview":str(json.loads(row[3]).get("content", ""))[:300]} for row in rows]

    def backup(self, target: Path):
        target.parent.mkdir(parents=True, exist_ok=True)
        with self.connect() as source, sqlite3.connect(target) as destination:
            source.backup(destination)
