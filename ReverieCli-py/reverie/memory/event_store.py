"""Append-only event store for lossless Reverie memory evidence."""

from __future__ import annotations

import json
import threading
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

from ..diagnostics import report_suppressed_exception
from .models import EventRecord, coerce_tags, new_id, utc_now


def _json_safe(value: Any) -> Any:
    """Convert common runtime objects to JSON-safe values without truncating text."""
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, dict):
        return {str(key): _json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [_json_safe(item) for item in value]
    if hasattr(value, "to_dict") and callable(value.to_dict):
        try:
            return _json_safe(value.to_dict())
        except Exception:
            report_suppressed_exception("serialize memory event payload")
    return str(value)


class EventStore:
    """Lossless local JSONL event store."""

    def __init__(self, project_data_dir: Path, *, workspace_id: str = ""):
        self.project_data_dir = Path(project_data_dir)
        self.memory_dir = self.project_data_dir / "memory"
        self.events_path = self.memory_dir / "events.jsonl"
        self.workspace_id = str(workspace_id or "")
        self._lock = threading.RLock()
        self.memory_dir.mkdir(parents=True, exist_ok=True)

    def append(
        self,
        event_type: str,
        payload: Optional[Dict[str, Any]] = None,
        *,
        actor: str = "",
        session_id: str = "",
        tags: Optional[Iterable[Any]] = None,
    ) -> EventRecord:
        event = EventRecord(
            id=new_id("evt"),
            timestamp=utc_now(),
            event_type=str(event_type or "event").strip().lower() or "event",
            actor=str(actor or ""),
            session_id=str(session_id or ""),
            workspace_id=self.workspace_id,
            tags=coerce_tags(tags),
            payload=_json_safe(dict(payload or {})),
        )
        line = json.dumps(event.to_dict(), ensure_ascii=False, separators=(",", ":"))
        with self._lock:
            self.memory_dir.mkdir(parents=True, exist_ok=True)
            with self.events_path.open("a", encoding="utf-8") as handle:
                handle.write(line + "\n")
        return event

    def iter_events(self) -> Iterable[EventRecord]:
        if not self.events_path.exists():
            return []

        def _iter() -> Iterable[EventRecord]:
            with self.events_path.open("r", encoding="utf-8") as handle:
                for raw_line in handle:
                    line = raw_line.strip()
                    if not line:
                        continue
                    try:
                        data = json.loads(line)
                    except Exception:
                        continue
                    if isinstance(data, dict):
                        yield EventRecord.from_dict(data)

        return _iter()

    def tail(self, limit: int = 100, *, event_type: str = "") -> List[EventRecord]:
        try:
            return self.query(event_type=event_type, limit=limit)
        except Exception:
            return []

    def _iter_recent_events(self) -> Iterable[EventRecord]:
        """Read complete UTF-8 records backwards without loading the log."""
        if not self.events_path.exists():
            return
        with self.events_path.open("rb") as handle:
            handle.seek(0, 2)
            position = handle.tell()
            pending = b""
            while position:
                size = min(position, 65536)
                position -= size
                handle.seek(position)
                lines = (handle.read(size) + pending).split(b"\n")
                pending = lines.pop(0)
                if position == 0:
                    lines.insert(0, pending)
                for line in reversed(lines):
                    if not line.strip():
                        continue
                    try:
                        data = json.loads(line.decode("utf-8"))
                    except (UnicodeDecodeError, json.JSONDecodeError):
                        continue
                    if isinstance(data, dict):
                        yield EventRecord.from_dict(data)

    def query(
        self,
        *,
        event_type: str = "",
        contains: str = "",
        limit: int = 100,
    ) -> List[EventRecord]:
        wanted_type = str(event_type or "").strip().lower()
        needle = str(contains or "").strip().lower()
        wanted_count = max(1, int(limit or 1))
        hits: List[EventRecord] = []
        for event in self._iter_recent_events():
            if wanted_type and event.event_type != wanted_type:
                continue
            if needle:
                haystack = json.dumps(event.to_dict(), ensure_ascii=False).lower()
                if needle not in haystack:
                    continue
            hits.append(event)
            if len(hits) >= wanted_count:
                break
        return list(reversed(hits))
