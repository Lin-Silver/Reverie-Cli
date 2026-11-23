-- Compatible with the final Python 2.5.5 SQLiteSessionManager user_version=7.
-- Source: ReverieCli-py/reverie/session/sqlite_manager.py at 070fa25 (MIT).
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
CREATE TABLE IF NOT EXISTS conversation_read_states (
    session_id TEXT PRIMARY KEY REFERENCES conversations(id),unread INTEGER NOT NULL DEFAULT 0);
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
    result TEXT NOT NULL DEFAULT '{}',created_at TEXT NOT NULL,updated_at TEXT NOT NULL,
    request TEXT NOT NULL DEFAULT '{}');
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
PRAGMA user_version=7;
