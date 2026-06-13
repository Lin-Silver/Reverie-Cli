"""Structured MemoryItem persistence."""

from __future__ import annotations

import json
import os
import tempfile
import threading
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

from .models import MemoryItem, normalize_memory_type, normalize_scope, utc_now


class MemoryStore:
    """Mutable structured memory store backed by a small JSON document."""

    def __init__(self, project_data_dir: Path):
        self.project_data_dir = Path(project_data_dir)
        self.memory_dir = self.project_data_dir / "memory"
        self.items_path = self.memory_dir / "memory_items.json"
        self._lock = threading.RLock()
        self.memory_dir.mkdir(parents=True, exist_ok=True)

    def _write_json_atomic(self, payload: Dict[str, Any]) -> None:
        self.memory_dir.mkdir(parents=True, exist_ok=True)
        temp_path: Optional[Path] = None
        try:
            with tempfile.NamedTemporaryFile(
                mode="w",
                encoding="utf-8",
                dir=str(self.memory_dir),
                prefix=f".{self.items_path.name}.",
                suffix=".tmp",
                delete=False,
            ) as handle:
                temp_path = Path(handle.name)
                json.dump(payload, handle, ensure_ascii=False, indent=2)
                handle.flush()
                os.fsync(handle.fileno())
            temp_path.replace(self.items_path)
        finally:
            if temp_path is not None and temp_path.exists():
                try:
                    temp_path.unlink()
                except OSError:
                    pass

    def load_items(self, *, include_deleted: bool = False) -> List[MemoryItem]:
        if not self.items_path.exists():
            return []
        try:
            payload = json.loads(self.items_path.read_text(encoding="utf-8"))
        except Exception:
            return []
        raw_items = payload.get("items") if isinstance(payload, dict) else []
        if not isinstance(raw_items, list):
            return []
        items = [
            MemoryItem.from_dict(item)
            for item in raw_items
            if isinstance(item, dict)
        ]
        if include_deleted:
            return items
        return [item for item in items if item.status == "active"]

    def save_items(self, items: Iterable[MemoryItem]) -> None:
        payload = {
            "updated_at": utc_now(),
            "items": [item.to_dict() for item in items],
        }
        with self._lock:
            self._write_json_atomic(payload)

    def upsert(self, item: MemoryItem) -> MemoryItem:
        with self._lock:
            items = self.load_items(include_deleted=True)
            incoming_fingerprint = item.fingerprint()
            for index, existing in enumerate(items):
                if existing.fingerprint() != incoming_fingerprint:
                    continue
                merged_evidence = list(existing.evidence or [])
                seen_evidence = {
                    str(evidence.get("event_id", "")) for evidence in merged_evidence if isinstance(evidence, dict)
                }
                for evidence in item.evidence or []:
                    event_id = str(evidence.get("event_id", "")) if isinstance(evidence, dict) else ""
                    if event_id and event_id in seen_evidence:
                        continue
                    merged_evidence.append(evidence)
                    if event_id:
                        seen_evidence.add(event_id)
                merged_sources = list(dict.fromkeys((existing.source_event_ids or []) + (item.source_event_ids or [])))
                merged_tags = list(dict.fromkeys((existing.tags or []) + (item.tags or [])))[:16]
                items[index] = MemoryItem(
                    id=existing.id,
                    scope=normalize_scope(item.scope, normalize_scope(existing.scope)),
                    memory_type=normalize_memory_type(item.memory_type, normalize_memory_type(existing.memory_type)),
                    content=item.content or existing.content,
                    evidence=merged_evidence[-12:],
                    confidence=max(float(existing.confidence or 0.0), float(item.confidence or 0.0)),
                    tags=merged_tags,
                    decay=float(item.decay if item.decay is not None else existing.decay),
                    created_at=existing.created_at,
                    updated_at=utc_now(),
                    source_event_ids=merged_sources[-20:],
                    status="active",
                    metadata={**(existing.metadata or {}), **(item.metadata or {})},
                )
                self.save_items(items)
                return items[index]
            items.append(item)
            self.save_items(items)
            return item

    def get(self, memory_id: str, *, include_deleted: bool = False) -> Optional[MemoryItem]:
        wanted = str(memory_id or "").strip()
        if not wanted:
            return None
        for item in self.load_items(include_deleted=include_deleted):
            if item.id == wanted:
                return item
        return None

    def correct(self, memory_id: str, content: str, *, tags: Optional[List[str]] = None) -> Optional[MemoryItem]:
        wanted = str(memory_id or "").strip()
        if not wanted:
            return None
        items = self.load_items(include_deleted=True)
        for index, item in enumerate(items):
            if item.id != wanted:
                continue
            item.content = str(content or "").strip() or item.content
            item.updated_at = utc_now()
            item.confidence = min(1.0, max(float(item.confidence or 0.0), 0.85))
            if tags:
                item.tags = list(dict.fromkeys((item.tags or []) + tags))[:16]
            item.metadata = {**(item.metadata or {}), "corrected": True}
            items[index] = item
            self.save_items(items)
            return item
        return None

    def delete(self, memory_id: str, *, hard: bool = False) -> bool:
        wanted = str(memory_id or "").strip()
        if not wanted:
            return False
        items = self.load_items(include_deleted=True)
        changed = False
        kept: List[MemoryItem] = []
        for item in items:
            if item.id != wanted:
                kept.append(item)
                continue
            changed = True
            if not hard:
                item.status = "deleted"
                item.updated_at = utc_now()
                kept.append(item)
        if changed:
            self.save_items(kept)
        return changed
