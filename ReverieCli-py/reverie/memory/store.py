"""Immediate, durable project-memory persistence backed by SQLite FTS5."""

from __future__ import annotations

import json
import re
import sqlite3
import threading
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

from .models import MemoryItem, new_id, normalize_memory_type, normalize_scope, utc_now
from .safety import redact_memory_text


_WORD_RE = re.compile(r"[A-Za-z_][A-Za-z0-9_]{1,}|\d+|[\u4e00-\u9fff]{2,}")


def _search_terms(value: str) -> List[str]:
    terms: List[str] = []
    for token in _WORD_RE.findall(str(value or "").lower()):
        terms.append(token)
        if re.fullmatch(r"[\u4e00-\u9fff]{2,}", token):
            terms.extend(token[index : index + 2] for index in range(len(token) - 1))
        else:
            terms.extend(part for part in re.split(r"[_\-.]+", token) if len(part) >= 2)
    return list(dict.fromkeys(terms))


class MemoryStore:
    """Project-isolated memory database with transactional immediate search."""

    SCHEMA_VERSION = 2

    def __init__(self, project_data_dir: Path):
        self.project_data_dir = Path(project_data_dir)
        self.memory_dir = self.project_data_dir / "memory"
        self.database_path = self.memory_dir / "memory.sqlite3"
        self.items_path = self.memory_dir / "memory_items.json"
        self._lock = threading.RLock()
        self._fts_available = False
        self.memory_dir.mkdir(parents=True, exist_ok=True)
        self._initialize()
        self._migrate_legacy_json()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(str(self.database_path), timeout=10.0)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA busy_timeout=10000")
        connection.execute("PRAGMA foreign_keys=ON")
        return connection

    def _initialize(self) -> None:
        with self._lock, self._connect() as connection:
            connection.execute("PRAGMA journal_mode=WAL")
            connection.execute("PRAGMA synchronous=NORMAL")
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS memory_meta (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS memories (
                    id TEXT PRIMARY KEY,
                    fingerprint TEXT NOT NULL,
                    scope TEXT NOT NULL,
                    memory_type TEXT NOT NULL,
                    status TEXT NOT NULL,
                    content TEXT NOT NULL,
                    tags TEXT NOT NULL,
                    confidence REAL NOT NULL,
                    updated_at TEXT NOT NULL,
                    payload TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_memories_status_updated
                    ON memories(status, updated_at DESC);
                CREATE INDEX IF NOT EXISTS idx_memories_type_scope
                    ON memories(memory_type, scope);
                CREATE INDEX IF NOT EXISTS idx_memories_fingerprint
                    ON memories(fingerprint);
                """
            )
            connection.execute(
                "INSERT OR IGNORE INTO memory_meta(key, value) VALUES('schema_version', ?)",
                (str(self.SCHEMA_VERSION),),
            )
            connection.execute("INSERT OR IGNORE INTO memory_meta(key, value) VALUES('revision', '0')")
            try:
                connection.execute(
                    "CREATE VIRTUAL TABLE IF NOT EXISTS memory_fts USING fts5(id UNINDEXED, search_text, tokenize='unicode61')"
                )
                self._fts_available = True
            except sqlite3.OperationalError:
                self._fts_available = False

    def _migrate_legacy_json(self) -> None:
        if not self.items_path.is_file():
            return
        with self._connect() as connection:
            existing = int(connection.execute("SELECT COUNT(*) FROM memories").fetchone()[0])
        if existing:
            return
        try:
            payload = json.loads(self.items_path.read_text(encoding="utf-8"))
            raw_items = payload.get("items", []) if isinstance(payload, dict) else []
            items = [MemoryItem.from_dict(item) for item in raw_items if isinstance(item, dict)]
        except Exception:
            return
        if items:
            self.save_items(items)

    @property
    def revision(self) -> int:
        try:
            with self._connect() as connection:
                row = connection.execute("SELECT value FROM memory_meta WHERE key='revision'").fetchone()
            return int(row[0]) if row else 0
        except (OSError, sqlite3.Error, TypeError, ValueError):
            return 0

    def _increment_revision(self, connection: sqlite3.Connection) -> None:
        connection.execute(
            "UPDATE memory_meta SET value=CAST(CAST(value AS INTEGER) + 1 AS TEXT) WHERE key='revision'"
        )

    @staticmethod
    def _decode(row: sqlite3.Row) -> MemoryItem:
        try:
            payload = json.loads(str(row["payload"] or "{}"))
        except (TypeError, json.JSONDecodeError):
            payload = {}
        return MemoryItem.from_dict(payload if isinstance(payload, dict) else {})

    @staticmethod
    def _search_text(item: MemoryItem) -> str:
        topic = str((item.metadata or {}).get("topic") or "")
        raw = " ".join([item.content, " ".join(item.tags or []), topic])
        return raw + " " + " ".join(_search_terms(raw))

    def _write_item(self, connection: sqlite3.Connection, item: MemoryItem) -> None:
        item.content = redact_memory_text(item.content).strip()
        payload = item.to_dict()
        connection.execute(
            """
            INSERT INTO memories(id, fingerprint, scope, memory_type, status, content, tags, confidence, updated_at, payload)
            VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
                fingerprint=excluded.fingerprint,
                scope=excluded.scope,
                memory_type=excluded.memory_type,
                status=excluded.status,
                content=excluded.content,
                tags=excluded.tags,
                confidence=excluded.confidence,
                updated_at=excluded.updated_at,
                payload=excluded.payload
            """,
            (
                item.id,
                item.fingerprint(),
                normalize_scope(item.scope),
                normalize_memory_type(item.memory_type),
                str(item.status or "active"),
                item.content,
                json.dumps(item.tags or [], ensure_ascii=False),
                max(0.0, min(1.0, float(item.confidence or 0.0))),
                item.updated_at or utc_now(),
                json.dumps(payload, ensure_ascii=False, separators=(",", ":")),
            ),
        )
        if self._fts_available:
            connection.execute("DELETE FROM memory_fts WHERE id=?", (item.id,))
            if item.status == "active":
                connection.execute(
                    "INSERT INTO memory_fts(id, search_text) VALUES(?, ?)",
                    (item.id, self._search_text(item)),
                )

    def load_items(self, *, include_deleted: bool = False) -> List[MemoryItem]:
        where = "" if include_deleted else "WHERE status='active'"
        try:
            with self._connect() as connection:
                rows = connection.execute(
                    f"SELECT payload FROM memories {where} ORDER BY updated_at DESC, id ASC"
                ).fetchall()
        except sqlite3.Error:
            return []
        return [self._decode(row) for row in rows]

    def save_items(self, items: Iterable[MemoryItem]) -> None:
        materialized = list(items)
        with self._lock, self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            connection.execute("DELETE FROM memories")
            if self._fts_available:
                connection.execute("DELETE FROM memory_fts")
            for item in materialized:
                self._write_item(connection, item)
            self._increment_revision(connection)
            connection.commit()

    def upsert(self, item: MemoryItem) -> MemoryItem:
        with self._lock, self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute(
                "SELECT payload FROM memories WHERE fingerprint=? ORDER BY updated_at DESC LIMIT 1",
                (item.fingerprint(),),
            ).fetchone()
            if row is not None:
                existing = self._decode(row)
                merged_evidence = list(existing.evidence or [])
                evidence_ids = {
                    str(evidence.get("event_id", ""))
                    for evidence in merged_evidence
                    if isinstance(evidence, dict)
                }
                for evidence in item.evidence or []:
                    event_id = str(evidence.get("event_id", "")) if isinstance(evidence, dict) else ""
                    if event_id and event_id in evidence_ids:
                        continue
                    merged_evidence.append(evidence)
                    if event_id:
                        evidence_ids.add(event_id)
                item = MemoryItem.from_dict(
                    {
                        **existing.to_dict(),
                        **item.to_dict(),
                        "id": existing.id,
                        "created_at": existing.created_at,
                        "updated_at": utc_now(),
                        "evidence": merged_evidence[-20:],
                        "source_event_ids": list(
                            dict.fromkeys((existing.source_event_ids or []) + (item.source_event_ids or []))
                        )[-40:],
                        "tags": list(dict.fromkeys((existing.tags or []) + (item.tags or [])))[:16],
                        "confidence": max(float(existing.confidence or 0.0), float(item.confidence or 0.0)),
                        "access_count": max(existing.access_count, item.access_count),
                    }
                )
            self._write_item(connection, item)
            self._increment_revision(connection)
            connection.commit()
            return item

    def get(self, memory_id: str, *, include_deleted: bool = False) -> Optional[MemoryItem]:
        wanted = str(memory_id or "").strip()
        if not wanted:
            return None
        where = "id=?" if include_deleted else "id=? AND status='active'"
        with self._connect() as connection:
            row = connection.execute(f"SELECT payload FROM memories WHERE {where}", (wanted,)).fetchone()
        return self._decode(row) if row is not None else None

    def correct(self, memory_id: str, content: str, *, tags: Optional[List[str]] = None) -> Optional[MemoryItem]:
        existing = self.get(memory_id, include_deleted=True)
        if existing is None:
            return None
        replacement = MemoryItem.from_dict(
            {
                **existing.to_dict(),
                "id": new_id("mem"),
                "content": str(content or "").strip() or existing.content,
                "created_at": utc_now(),
                "updated_at": utc_now(),
                "confidence": max(float(existing.confidence or 0.0), 0.9),
                "tags": list(dict.fromkeys((existing.tags or []) + (tags or []) + ["corrected"]))[:16],
                "status": "active",
                "provenance": "explicit_correction",
                "version": max(1, int(existing.version or 1)) + 1,
                "supersedes": list(dict.fromkeys((existing.supersedes or []) + [existing.id])),
                "superseded_by": "",
                "metadata": {**(existing.metadata or {}), "corrected": True},
            }
        )
        existing.status = "superseded"
        existing.superseded_by = replacement.id
        existing.updated_at = utc_now()
        existing.valid_to = existing.updated_at
        with self._lock, self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            self._write_item(connection, existing)
            self._write_item(connection, replacement)
            self._increment_revision(connection)
            connection.commit()
        return replacement

    def supersede(self, memory_ids: Iterable[str], replacement: MemoryItem) -> MemoryItem:
        wanted = {str(item or "").strip() for item in memory_ids if str(item or "").strip()}
        if not wanted:
            return self.upsert(replacement)
        with self._lock, self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            versions = [max(1, replacement.version)]
            supersedes = list(replacement.supersedes or [])
            for memory_id in sorted(wanted):
                row = connection.execute("SELECT payload FROM memories WHERE id=?", (memory_id,)).fetchone()
                if row is None:
                    continue
                existing = self._decode(row)
                versions.append(max(1, existing.version))
                supersedes.append(existing.id)
                existing.status = "superseded"
                existing.superseded_by = replacement.id
                existing.updated_at = utc_now()
                existing.valid_to = existing.updated_at
                self._write_item(connection, existing)
            replacement.supersedes = list(dict.fromkeys(supersedes))
            replacement.version = max(versions) + 1
            self._write_item(connection, replacement)
            self._increment_revision(connection)
            connection.commit()
        return replacement

    def delete(self, memory_id: str, *, hard: bool = False) -> bool:
        wanted = str(memory_id or "").strip()
        if not wanted:
            return False
        with self._lock, self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute("SELECT payload FROM memories WHERE id=?", (wanted,)).fetchone()
            if row is None:
                connection.rollback()
                return False
            if hard:
                connection.execute("DELETE FROM memories WHERE id=?", (wanted,))
                if self._fts_available:
                    connection.execute("DELETE FROM memory_fts WHERE id=?", (wanted,))
            else:
                item = self._decode(row)
                item.status = "deleted"
                item.updated_at = utc_now()
                self._write_item(connection, item)
            self._increment_revision(connection)
            connection.commit()
        return True

    def search_fts(self, query: str, *, limit: int = 80) -> List[str]:
        if not self._fts_available:
            return []
        terms = _search_terms(query)
        if not terms:
            return []
        expression = " OR ".join('"' + term.replace('"', '""') + '"' for term in terms[:32])
        try:
            with self._connect() as connection:
                rows = connection.execute(
                    "SELECT id FROM memory_fts WHERE memory_fts MATCH ? ORDER BY bm25(memory_fts) LIMIT ?",
                    (expression, max(1, min(int(limit or 1), 500))),
                ).fetchall()
        except sqlite3.Error:
            return []
        return [str(row["id"]) for row in rows]

    def touch_access(self, memory_ids: Iterable[str]) -> None:
        wanted = list(dict.fromkeys(str(item or "").strip() for item in memory_ids if str(item or "").strip()))
        if not wanted:
            return
        with self._lock, self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            for memory_id in wanted:
                row = connection.execute("SELECT payload FROM memories WHERE id=?", (memory_id,)).fetchone()
                if row is None:
                    continue
                item = self._decode(row)
                item.last_accessed_at = utc_now()
                item.access_count = max(0, int(item.access_count or 0)) + 1
                self._write_item(connection, item)
            connection.commit()

    def status(self) -> Dict[str, Any]:
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT status, COUNT(*) AS count FROM memories GROUP BY status ORDER BY status"
            ).fetchall()
        return {
            "database_path": str(self.database_path),
            "schema_version": self.SCHEMA_VERSION,
            "revision": self.revision,
            "fts5": self._fts_available,
            "counts": {str(row["status"]): int(row["count"]) for row in rows},
            "immediate_search": True,
        }


__all__ = ["MemoryStore"]
