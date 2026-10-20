"""Rebuildable per-workspace transcript search cache.

The cache is a projection of the session JSON files, never a second source of
truth: a schema change or a corrupt database is repaired by rebuilding from the
transcripts. It still has to be cheap to keep current, because an active agent
turn edits the transcript many times. Two rules keep it that way:

- A session whose rows are unchanged is not rewritten.
- A transcript that only grew is appended to, instead of deleting and
  re-inserting every message. Compaction, rewind and rename all change the row
  list in place, which fails the prefix check and falls back to a full rebuild.
"""

import hashlib
import json
import sqlite3
from pathlib import Path
from typing import Any

from .roles import from_stored_role

SCHEMA_VERSION = 2


class SessionSearchIndex:
    def __init__(self, path: Path):
        self.path = path
        db = self.connect()
        try:
            with db:
                db.execute(
                    "CREATE TABLE IF NOT EXISTS sessions ("
                    "id TEXT PRIMARY KEY, mtime INTEGER, updated_at TEXT, "
                    "rows_digest TEXT, row_count INTEGER)"
                )
                db.execute(
                    "CREATE TABLE IF NOT EXISTS messages ("
                    "session_id TEXT, message_index INTEGER, role TEXT, body TEXT)"
                )
                db.execute("CREATE INDEX IF NOT EXISTS messages_session ON messages(session_id)")
                if db.execute("PRAGMA user_version").fetchone()[0] != SCHEMA_VERSION:
                    db.execute("DROP TABLE IF EXISTS text_search")
                    db.execute("DELETE FROM messages")
                    db.execute("DELETE FROM sessions")
                    db.execute(f"PRAGMA user_version={SCHEMA_VERSION}")
                try:
                    db.execute(
                        "CREATE VIRTUAL TABLE IF NOT EXISTS text_search USING fts5("
                        "body, tokenize='trigram', detail=none, columnsize=0)"
                    )
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

    @staticmethod
    def _rows(session_id: str, data: dict[str, Any]) -> list[tuple[int, str, str]]:
        """Flatten a transcript payload into searchable rows.

        Index -1 holds the session title so a title hit resolves to the session
        itself. Bodies keep their original case: they are also the search preview
        shown to the user, and lowercasing is done at match time instead.
        """
        name = str(data.get("name") or session_id)
        rows = [(-1, "session", name)]
        for index, message in enumerate(data.get("messages", []) or []):
            if not isinstance(message, dict):
                continue
            content = message.get("content", "")
            text = content if isinstance(content, str) else json.dumps(content, ensure_ascii=False)
            reasoning = str(message.get("reasoning_content") or "")
            calls = " ".join(
                str((call.get("function") or {}).get("name") or "")
                for call in message.get("tool_calls", []) or []
                if isinstance(call, dict)
            )
            body = "\n".join(part for part in (text, reasoning, calls) if part)
            rows.append((index, from_stored_role(message.get("role", "")), body))
        return rows

    @staticmethod
    def _rows_digest(rows) -> str:
        digest = hashlib.sha1()
        for index, role, body in rows:
            digest.update(f"{index}\x1f{role}\x1f{body}\x1e".encode("utf-8", "surrogatepass"))
        return digest.hexdigest()

    def _drop(self, db, session_id: str) -> None:
        if self.fts:
            db.execute(
                "DELETE FROM text_search WHERE rowid IN "
                "(SELECT rowid FROM messages WHERE session_id=?)",
                (session_id,),
            )
        db.execute("DELETE FROM messages WHERE session_id=?", (session_id,))
        db.execute("DELETE FROM sessions WHERE id=?", (session_id,))

    def update_many(self, changes):
        db = self.connect()
        try:
            with db:
                for session_id, data, mtime in changes:
                    if data is None:
                        self._drop(db, session_id)
                        continue

                    rows = self._rows(session_id, data)
                    rows_digest = self._rows_digest(rows)
                    stored = db.execute(
                        "SELECT rows_digest, row_count FROM sessions WHERE id=?",
                        (session_id,),
                    ).fetchone()
                    if stored and stored[0] == rows_digest:
                        # Rows already indexed. Only the freshness stamp can
                        # have moved, and that is what `stamps()` reports.
                        db.execute(
                            "UPDATE sessions SET mtime=?, updated_at=? WHERE id=?",
                            (mtime, str(data.get("updated_at") or ""), session_id),
                        )
                        continue

                    start = 0
                    if stored and stored[1] and len(rows) >= int(stored[1]):
                        # Stored rows are a prefix of the new list exactly when
                        # their digest matches; anything edited in place fails.
                        if self._rows_digest(rows[: int(stored[1])]) == stored[0]:
                            start = int(stored[1])
                    if start == 0:
                        self._drop(db, session_id)
                        db.execute(
                            "INSERT INTO sessions VALUES (?, ?, ?, ?, ?)",
                            (session_id, mtime, str(data.get("updated_at") or ""), rows_digest, len(rows)),
                        )
                    else:
                        db.execute(
                            "UPDATE sessions SET mtime=?, updated_at=?, rows_digest=?, row_count=? WHERE id=?",
                            (mtime, str(data.get("updated_at") or ""), rows_digest, len(rows), session_id),
                        )

                    for index, role, body in rows[start:]:
                        cursor = db.execute(
                            "INSERT INTO messages VALUES (?, ?, ?, ?)",
                            (session_id, index, role, body),
                        )
                        if self.fts:
                            db.execute(
                                "INSERT INTO text_search(rowid, body) VALUES (?, ?)",
                                (cursor.lastrowid, body.lower()),
                            )
        finally:
            db.close()

    def search(self, needle: str, limit: int) -> list[dict[str, Any]]:
        db = self.connect()
        try:
            indexed = self.fts and len(needle) >= 3
            candidate = (
                "m.rowid IN (SELECT rowid FROM text_search WHERE text_search MATCH ?) AND "
                if indexed
                else ""
            )
            # Compact postings filter candidates; instr below checks the full literal.
            grams = dict.fromkeys([needle[:3], needle[-3:]])
            params = (
                [' AND '.join('"' + gram.replace('"', '""') + '"' for gram in grams)]
                if indexed
                else []
            )
            params.extend([needle, limit])
            rows = db.execute(
                "SELECT m.session_id, m.message_index, m.role, substr(m.body, 1, 500), title.body "
                "FROM messages m "
                "JOIN sessions s ON s.id=m.session_id "
                "JOIN messages title ON title.session_id=m.session_id AND title.message_index=-1 "
                f"WHERE {candidate}instr(lower(m.body), ?) > 0 "
                "ORDER BY s.updated_at DESC, m.message_index LIMIT ?",
                params,
            )
            return [
                {
                    "session_id": sid,
                    "session_name": name,
                    "message_index": index,
                    "role": role,
                    "text": preview,
                }
                for sid, index, role, preview, name in rows
            ]
        finally:
            db.close()
