"""Rebuildable per-workspace transcript search cache."""

import json
import sqlite3
from pathlib import Path
from typing import Any

from .roles import from_stored_role


class SessionSearchIndex:
    def __init__(self, path: Path):
        self.path = path
        db = self.connect()
        try:
            with db:
                db.execute("CREATE TABLE IF NOT EXISTS sessions (id TEXT PRIMARY KEY, mtime INTEGER, updated_at TEXT)")
                db.execute("CREATE TABLE IF NOT EXISTS messages (session_id TEXT, message_index INTEGER, role TEXT, preview TEXT, body TEXT)")
                db.execute("CREATE INDEX IF NOT EXISTS messages_session ON messages(session_id)")
                if db.execute("PRAGMA user_version").fetchone()[0] != 1:
                    db.execute("DROP TABLE IF EXISTS text_search")
                    db.execute("DELETE FROM messages")
                    db.execute("DELETE FROM sessions")
                    db.execute("PRAGMA user_version=1")
                try:
                    db.execute("CREATE VIRTUAL TABLE IF NOT EXISTS text_search USING fts5(body, tokenize='trigram', detail=none, columnsize=0)")
                    self.fts = True
                except sqlite3.OperationalError:
                    self.fts = False
        finally:
            db.close()

    def connect(self):
        # Each operation owns its connection; SDK requests can run on different threads.
        return sqlite3.connect(self.path, timeout=10)

    def stamps(self) -> dict[str, int]:
        db = self.connect()
        try:
            return dict(db.execute("SELECT id, mtime FROM sessions"))
        finally:
            db.close()

    def update(self, session_id: str, data: dict[str, Any] | None, mtime: int = 0):
        self.update_many([(session_id, data, mtime)])

    def update_many(self, changes):
        db = self.connect()
        try:
            with db:
                for session_id, data, mtime in changes:
                    if self.fts:
                        db.execute("DELETE FROM text_search WHERE rowid IN (SELECT rowid FROM messages WHERE session_id=?)", (session_id,))
                    db.execute("DELETE FROM messages WHERE session_id=?", (session_id,))
                    db.execute("DELETE FROM sessions WHERE id=?", (session_id,))
                    if data is None:
                        continue
                    db.execute("INSERT INTO sessions VALUES (?, ?, ?)", (session_id, mtime, str(data.get("updated_at") or "")))
                    name = str(data.get("name") or session_id)
                    rows = [(-1, "session", name, name)]
                    for index, message in enumerate(data.get("messages", []) or []):
                        if not isinstance(message, dict):
                            continue
                        content = message.get("content", "")
                        text = content if isinstance(content, str) else json.dumps(content, ensure_ascii=False)
                        reasoning = str(message.get("reasoning_content") or "")
                        calls = " ".join(str((call.get("function") or {}).get("name") or "")
                                         for call in message.get("tool_calls", []) or [] if isinstance(call, dict))
                        rows.append((index, from_stored_role(message.get("role", "")), (text or reasoning or calls)[:500],
                                     "\n".join(part for part in (text, reasoning, calls) if part)))
                    for index, role, preview, body in rows:
                        cursor = db.execute("INSERT INTO messages VALUES (?, ?, ?, ?, ?)", (session_id, index, role, preview, body.lower()))
                        if self.fts:
                            db.execute("INSERT INTO text_search(rowid, body) VALUES (?, ?)", (cursor.lastrowid, body.lower()))
        finally:
            db.close()

    def search(self, needle: str, limit: int) -> list[dict[str, Any]]:
        db = self.connect()
        try:
            indexed = self.fts and len(needle) >= 3
            candidate = "m.rowid IN (SELECT rowid FROM text_search WHERE text_search MATCH ?) AND " if indexed else ""
            # Compact postings filter candidates; instr below checks the full literal.
            grams = dict.fromkeys([needle[:3], needle[-3:]])
            params = [' AND '.join('"' + gram.replace('"', '""') + '"' for gram in grams)] if indexed else []
            params.extend([needle, limit])
            rows = db.execute(
                f"SELECT m.session_id, m.message_index, m.role, m.preview, title.preview FROM messages m "
                "JOIN sessions s ON s.id=m.session_id JOIN messages title ON title.session_id=m.session_id AND title.message_index=-1 "
                f"WHERE {candidate}instr(m.body, ?) > 0 ORDER BY s.updated_at DESC, m.message_index LIMIT ?", params)
            return [{"session_id": sid, "session_name": name, "message_index": index, "role": role, "text": preview}
                    for sid, index, role, preview, name in rows]
        finally:
            db.close()
