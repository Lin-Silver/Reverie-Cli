"""Localization table support for Reverie Engine."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, Optional
import json

import yaml


class _SafeDict(dict):
    def __missing__(self, key: str) -> str:
        return "{" + key + "}"


@dataclass
class LocalizationManager:
    project_root: Path
    current_locale: str = "en"
    fallback_locale: str = "en"
    tables: Dict[str, Dict[str, str]] = field(default_factory=dict)

    def __init__(self, project_root: Path, *, locale: str = "en", fallback_locale: str = "en") -> None:
        self.project_root = Path(project_root)
        self.current_locale = str(locale or "en").strip() or "en"
        self.fallback_locale = str(fallback_locale or "en").strip() or "en"
        self.tables = {}
        self.reload()

    def reload(self) -> None:
        self.tables.clear()
        directory = self.project_root / "data/localization"
        if not directory.exists():
            return
        for path in sorted(directory.glob("*")):
            if path.suffix.lower() not in {".yaml", ".yml", ".json"}:
                continue
            payload = self._load_file(path)
            self._merge_payload(payload, source_name=path.stem)

    def _load_file(self, path: Path) -> Dict[str, Any]:
        if path.suffix.lower() == ".json":
            return json.loads(path.read_text(encoding="utf-8"))
        return yaml.safe_load(path.read_text(encoding="utf-8")) or {}

    def _merge_payload(self, payload: Dict[str, Any], *, source_name: str) -> None:
        data = dict(payload or {})
        if "locale" in data and isinstance(data.get("strings"), dict):
            locale = str(data.get("locale") or source_name).strip()
            self.tables.setdefault(locale, {}).update({str(key): str(value) for key, value in dict(data["strings"]).items()})
            return
        for key, value in data.items():
            if isinstance(value, dict):
                locale = str(key).strip()
                self.tables.setdefault(locale, {}).update({str(inner_key): str(inner_value) for inner_key, inner_value in value.items()})

    def set_locale(self, locale: str) -> str:
        normalized = str(locale or "").strip() or self.current_locale
        self.current_locale = normalized
        return self.current_locale

    def available_locales(self) -> list[str]:
        return sorted(self.tables.keys())

    def translate(self, key: str, *, locale: Optional[str] = None, default: str = "", params: Optional[Dict[str, Any]] = None) -> str:
        lookup = str(key or "").strip()
        if not lookup:
            return str(default or "")
        locale_key = str(locale or self.current_locale or self.fallback_locale).strip()
        candidates = [locale_key]
        if self.fallback_locale not in candidates:
            candidates.append(self.fallback_locale)
        for candidate in candidates:
            table = self.tables.get(candidate) or {}
            if lookup in table:
                return self._format(table[lookup], params=params)
        if default:
            return self._format(str(default), params=params)
        return lookup

    def resolve_text(self, value: str, *, locale: Optional[str] = None, params: Optional[Dict[str, Any]] = None, default: str = "") -> str:
        text = str(value or "")
        if text.startswith("loc:"):
            return self.translate(text[4:], locale=locale, default=default, params=params)
        return self._format(text or default, params=params)

    def _format(self, text: str, *, params: Optional[Dict[str, Any]] = None) -> str:
        mapping = _SafeDict({str(key): value for key, value in dict(params or {}).items()})
        try:
            return str(text).format_map(mapping)
        except Exception:
            return str(text)

    def summary(self) -> Dict[str, Any]:
        return {
            "current_locale": self.current_locale,
            "fallback_locale": self.fallback_locale,
            "available_locales": self.available_locales(),
            "entry_count": sum(len(table) for table in self.tables.values()),
        }
