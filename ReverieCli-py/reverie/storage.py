"""Portable-first project data storage resolution."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional


PROJECTS_DATA_DIRNAME = "projects"
PROJECT_METADATA_FILENAME = "project_metadata.json"
PROJECT_LAYOUT_FILENAME = "storage_layout.json"

PROJECT_STORAGE_LAYOUT: Dict[str, List[str]] = {
    "sessions": [
        "sessions",
        "archives",
        "checkpoints",
        "full_transcripts",
        "session_handoffs",
    ],
    "context": [
        "context",
        "context/cache",
        "context/index",
        "context/compression",
        "context/retrieval",
        "context_cache",
        "indexes",
    ],
    "memory": [
        "memory",
        "memory/events",
        "memory/items",
        "memory/workflows",
        "memory/procedures",
        "memory/evolution",
    ],
    "feedback": [
        "feedback",
        "feedback/evolution_proposals",
    ],
    "tools": [
        "tools",
        "tools/state",
        "tools/media",
        "tools/subagents",
        "subagents",
        "subagent_runs",
        "media",
    ],
    "runtime": [
        "logs",
        "harness",
        "security",
        "lifecycle",
        "browser",
        "specs",
        "steering",
    ],
}


class ProjectStorageError(RuntimeError):
    """Raised when Reverie cannot use the launcher-local portable store."""


def _resolve_path(path: Any) -> Path:
    return Path(path).expanduser().resolve()


def sanitize_project_name(project_path: Any) -> str:
    """Return a Windows-safe project folder name derived from the full path."""
    path = _resolve_path(project_path)
    raw = str(path).strip()
    safe = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", raw)
    safe = re.sub(r"\s+", " ", safe).strip()
    safe = re.sub(r"_+", "_", safe).strip(" ._")
    reserved = {
        "CON",
        "PRN",
        "AUX",
        "NUL",
        *(f"COM{index}" for index in range(1, 10)),
        *(f"LPT{index}" for index in range(1, 10)),
    }
    if not safe or safe.upper() in reserved:
        safe = "workspace"
    return safe[:120]


@dataclass(frozen=True)
class ProjectStorageResolver:
    """Resolve all project-level data under the launcher-local portable root."""

    launcher_root: Path
    project_root: Path

    @classmethod
    def for_project(cls, project_root: Any, *, launcher_root: Optional[Any] = None) -> "ProjectStorageResolver":
        if launcher_root is None:
            from .config import get_app_root

            launcher_root = get_app_root()
        return cls(_resolve_path(launcher_root), _resolve_path(project_root))

    @property
    def reverie_root(self) -> Path:
        return self.launcher_root / ".reverie"

    @property
    def projects_root(self) -> Path:
        return self.reverie_root / PROJECTS_DATA_DIRNAME

    @property
    def project_name(self) -> str:
        return sanitize_project_name(self.project_root)

    @property
    def project_dir(self) -> Path:
        return self.projects_root / self.project_name

    def ensure_writable(self) -> None:
        """Create and verify the launcher-local .reverie root is writable."""
        try:
            self.reverie_root.mkdir(parents=True, exist_ok=True)
            self.projects_root.mkdir(parents=True, exist_ok=True)
            probe = self.reverie_root / ".write-test"
            probe.write_text("ok", encoding="utf-8")
            probe.unlink(missing_ok=True)
        except Exception as exc:
            raise ProjectStorageError(
                "Reverie portable storage is not writable. "
                f"Expected project data under '{self.reverie_root}'. "
                "Move the Reverie executable/launcher folder to a writable directory "
                "and run Reverie again. Reverie will not silently fall back to C:, "
                "AppData, a temp directory, or the repository."
            ) from exc

    def ensure_project_dir(self) -> Path:
        self.ensure_writable()
        self.project_dir.mkdir(parents=True, exist_ok=True)
        self.write_metadata()
        self.ensure_layout_dirs()
        return self.project_dir

    def ensure_layout_dirs(self) -> None:
        for paths in PROJECT_STORAGE_LAYOUT.values():
            for relative_path in paths:
                (self.project_dir / relative_path).mkdir(parents=True, exist_ok=True)
        self.write_layout()

    def write_layout(self) -> None:
        payload = {
            "schema": "reverie.project_storage_layout.v1",
            "project_data_name": self.project_name,
            "root": str(self.project_dir),
            "layout": PROJECT_STORAGE_LAYOUT,
            "notes": {
                "sessions": "SessionManager-compatible top-level session, archive, checkpoint, transcript, and handoff data.",
                "context": "Context Engine caches, indexes, retrieval packs, and compression artifacts for bounded/infinite context.",
                "memory": "Memory OS event store, MemoryItem records, workflow memory, and procedural memory.",
                "feedback": "Observe-Extract-Propose-Evaluate-Apply learning proposals and feedback history.",
                "tools": "Tool state, generated media state, and subagent run state.",
                "runtime": "Logs, harness reports, security audits, lifecycle data, browser state, specs, and steering files.",
            },
            "updated_at": datetime.now().isoformat(timespec="seconds"),
        }
        target = self.project_dir / PROJECT_LAYOUT_FILENAME
        target.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    def write_metadata(self) -> None:
        payload = self.metadata()
        target = self.project_dir / PROJECT_METADATA_FILENAME
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    def metadata(self) -> Dict[str, Any]:
        return {
            "schema": "reverie.project_storage.v4",
            "project_path": str(self.project_root),
            "project_data_name": self.project_name,
            "portable_root": str(self.reverie_root),
            "projects_root": str(self.projects_root),
            "updated_at": datetime.now().isoformat(timespec="seconds"),
        }
