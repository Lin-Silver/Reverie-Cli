"""
Workspace-level persistent usage and runtime statistics.

This module tracks:
- cumulative CLI runtime and active work time per workspace
- model usage totals (input/output tokens, calls)
- session-level usage rollups for dashboards such as /total
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional
import hashlib
import json
import os
import time


WORKSPACE_STATS_SCHEMA_VERSION = 1
WORKSPACE_STATS_FILENAME = "workspace_stats.json"


def _now_iso() -> str:
    return datetime.now().replace(microsecond=0).isoformat()


def _normalize_path(path_value: Any) -> str:
    raw = str(path_value or "").strip()
    if not raw:
        return ""
    try:
        normalized = str(Path(raw).resolve())
    except Exception:
        normalized = raw
    return normalized.replace("\\", "/")


def _workspace_id_for_path(path_value: Any) -> str:
    normalized = _normalize_path(path_value)
    if not normalized:
        return ""
    return hashlib.sha1(normalized.lower().encode("utf-8")).hexdigest()[:16]


def _coerce_nonnegative_float(value: Any) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return 0.0
    return max(0.0, number)


def _coerce_nonnegative_int(value: Any) -> int:
    try:
        number = int(value)
    except (TypeError, ValueError):
        return 0
    return max(0, number)


def _clean_text(value: Any) -> str:
    return str(value or "").strip()


def _clean_bool(value: Any, default: bool = False) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    if isinstance(value, str):
        lowered = value.strip().lower()
        if lowered in {"1", "true", "yes", "on"}:
            return True
        if lowered in {"0", "false", "no", "off"}:
            return False
    return default


@dataclass
class SessionUsageSummary:
    session_id: str
    session_name: str = ""
    calls: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
    message_count: int = 0
    updated_at: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "session_id": self.session_id,
            "session_name": self.session_name,
            "calls": self.calls,
            "input_tokens": self.input_tokens,
            "output_tokens": self.output_tokens,
            "message_count": self.message_count,
            "updated_at": self.updated_at,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "SessionUsageSummary":
        return cls(
            session_id=_clean_text(data.get("session_id")),
            session_name=_clean_text(data.get("session_name")),
            calls=_coerce_nonnegative_int(data.get("calls")),
            input_tokens=_coerce_nonnegative_int(data.get("input_tokens")),
            output_tokens=_coerce_nonnegative_int(data.get("output_tokens")),
            message_count=_coerce_nonnegative_int(data.get("message_count")),
            updated_at=_clean_text(data.get("updated_at")),
        )


@dataclass
class ModelUsageSummary:
    usage_key: str
    provider: str
    source: str
    model: str
    model_display_name: str
    calls: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
    last_used_at: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "usage_key": self.usage_key,
            "provider": self.provider,
            "source": self.source,
            "model": self.model,
            "model_display_name": self.model_display_name,
            "calls": self.calls,
            "input_tokens": self.input_tokens,
            "output_tokens": self.output_tokens,
            "last_used_at": self.last_used_at,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ModelUsageSummary":
        return cls(
            usage_key=_clean_text(data.get("usage_key")),
            provider=_clean_text(data.get("provider")) or "unknown",
            source=_clean_text(data.get("source")) or "standard",
            model=_clean_text(data.get("model")),
            model_display_name=_clean_text(data.get("model_display_name")),
            calls=_coerce_nonnegative_int(data.get("calls")),
            input_tokens=_coerce_nonnegative_int(data.get("input_tokens")),
            output_tokens=_coerce_nonnegative_int(data.get("output_tokens")),
            last_used_at=_clean_text(data.get("last_used_at")),
        )


@dataclass
class WorkspaceStatsState:
    schema_version: int = WORKSPACE_STATS_SCHEMA_VERSION
    workspace_id: str = ""
    workspace_path: str = ""
    workspace_name: str = ""
    created_at: str = ""
    updated_at: str = ""
    total_runtime_seconds: float = 0.0
    total_active_seconds: float = 0.0
    model_usage: Dict[str, ModelUsageSummary] = field(default_factory=dict)
    session_usage: Dict[str, SessionUsageSummary] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "workspace_id": self.workspace_id,
            "workspace_path": self.workspace_path,
            "workspace_name": self.workspace_name,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "total_runtime_seconds": self.total_runtime_seconds,
            "total_active_seconds": self.total_active_seconds,
            "model_usage": {key: item.to_dict() for key, item in self.model_usage.items()},
            "session_usage": {key: item.to_dict() for key, item in self.session_usage.items()},
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "WorkspaceStatsState":
        model_usage_raw = data.get("model_usage") or {}
        session_usage_raw = data.get("session_usage") or {}
        return cls(
            schema_version=_coerce_nonnegative_int(data.get("schema_version")) or WORKSPACE_STATS_SCHEMA_VERSION,
            workspace_id=_clean_text(data.get("workspace_id")),
            workspace_path=_normalize_path(data.get("workspace_path")),
            workspace_name=_clean_text(data.get("workspace_name")),
            created_at=_clean_text(data.get("created_at")),
            updated_at=_clean_text(data.get("updated_at")),
            total_runtime_seconds=_coerce_nonnegative_float(data.get("total_runtime_seconds")),
            total_active_seconds=_coerce_nonnegative_float(data.get("total_active_seconds")),
            model_usage={
                str(key): ModelUsageSummary.from_dict(value)
                for key, value in model_usage_raw.items()
                if isinstance(value, dict)
            },
            session_usage={
                str(key): SessionUsageSummary.from_dict(value)
                for key, value in session_usage_raw.items()
                if isinstance(value, dict)
            },
        )


class WorkspaceStatsManager:
    """Persist and query workspace-level runtime and token statistics."""

    _encoding = None
    _encoding_checked = False
    _save_interval_seconds = 1.25
    _max_deferred_save_seconds = 8.0

    def __init__(self, project_data_dir: Path, project_root: Optional[Path] = None):
        self.project_data_dir = Path(project_data_dir).resolve()
        self.project_root = Path(project_root).resolve() if project_root else None
        self.stats_path = self.project_data_dir / WORKSPACE_STATS_FILENAME
        self._dirty = False
        self._last_save_monotonic = 0.0
        self._pending_since_monotonic = 0.0

        workspace_path = _normalize_path(self.project_root or self.project_data_dir)
        workspace_name = (
            Path(workspace_path).name
            if workspace_path
            else self.project_data_dir.name
        )
        self._default_state = WorkspaceStatsState(
            workspace_id=_workspace_id_for_path(workspace_path or self.project_data_dir),
            workspace_path=workspace_path or _normalize_path(self.project_data_dir),
            workspace_name=workspace_name,
            created_at=_now_iso(),
            updated_at=_now_iso(),
        )
        self.state = self._load_state()
        self._merge_identity()

    @classmethod
    def _get_encoding(cls):
        if cls._encoding_checked:
            return cls._encoding
        cls._encoding_checked = True
        try:
            import tiktoken

            cls._encoding = tiktoken.get_encoding("cl100k_base")
        except Exception:
            cls._encoding = None
        return cls._encoding

    @classmethod
    def count_text_tokens(cls, text: Any) -> int:
        raw_text = str(text or "")
        if not raw_text:
            return 0
        encoding = cls._get_encoding()
        if encoding is not None:
            try:
                return len(encoding.encode(raw_text))
            except Exception:
                pass
        return max(1, len(raw_text) // 4)

    @classmethod
    def count_messages_tokens(cls, messages: List[Dict[str, Any]]) -> int:
        total = 0
        for message in messages or []:
            if not isinstance(message, dict):
                continue
            total += 4
            content = message.get("content")
            total += cls._count_value_tokens(content)
            tool_calls = message.get("tool_calls")
            if isinstance(tool_calls, list):
                for tool_call in tool_calls:
                    if isinstance(tool_call, dict):
                        total += cls._count_value_tokens(
                            {
                                key: value
                                for key, value in tool_call.items()
                                if key not in {"thought_signature", "gemini_thought_signature"}
                            }
                        )
            tool_call_id = message.get("tool_call_id")
            if tool_call_id:
                total += cls.count_text_tokens(tool_call_id)
            name = message.get("name")
            if name:
                total += cls.count_text_tokens(name)
                total -= 1
        return total + 2

    @classmethod
    def _count_value_tokens(cls, value: Any) -> int:
        if value is None:
            return 0
        if isinstance(value, str):
            return cls.count_text_tokens(value)
        if isinstance(value, (int, float, bool)):
            return cls.count_text_tokens(str(value))
        if isinstance(value, list):
            return sum(cls._count_value_tokens(item) for item in value)
        if isinstance(value, dict):
            total = 0
            for key, item in value.items():
                if str(key) in {"reasoning_content", "thought_signature", "gemini_thought_signature"}:
                    continue
                total += cls._count_value_tokens(item)
            return total
        return cls.count_text_tokens(str(value))

    @staticmethod
    def _usage_dict(usage: Any) -> Dict[str, int]:
        if usage is None:
            return {}
        if isinstance(usage, dict):
            get_value = usage.get
        else:
            get_value = lambda key, default=None: getattr(usage, key, default)
        input_tokens = get_value("prompt_tokens")
        if input_tokens is None:
            input_tokens = get_value("input_tokens")
        output_tokens = get_value("completion_tokens")
        if output_tokens is None:
            output_tokens = get_value("output_tokens")
        total_tokens = get_value("total_tokens")
        result: Dict[str, int] = {}
        if input_tokens is not None:
            result["input_tokens"] = _coerce_nonnegative_int(input_tokens)
        if output_tokens is not None:
            result["output_tokens"] = _coerce_nonnegative_int(output_tokens)
        if total_tokens is not None:
            result["total_tokens"] = _coerce_nonnegative_int(total_tokens)
        return result

    @staticmethod
    def _usage_key(provider: str, source: str, model: str, model_display_name: str) -> str:
        provider_text = _clean_text(provider) or "unknown"
        source_text = _clean_text(source) or "standard"
        model_text = _clean_text(model) or _clean_text(model_display_name) or "unknown-model"
        return f"{provider_text}::{source_text}::{model_text}"

    def _merge_identity(self) -> None:
        if not self.state.workspace_id:
            self.state.workspace_id = self._default_state.workspace_id
        if not self.state.workspace_path:
            self.state.workspace_path = self._default_state.workspace_path
        if not self.state.workspace_name:
            self.state.workspace_name = self._default_state.workspace_name
        if not self.state.created_at:
            self.state.created_at = self._default_state.created_at
        self.state.updated_at = _now_iso()

    def _load_state(self) -> WorkspaceStatsState:
        if not self.stats_path.exists():
            return self._default_state
        try:
            payload = json.loads(self.stats_path.read_text(encoding="utf-8"))
        except Exception:
            return self._default_state
        if not isinstance(payload, dict):
            return self._default_state
        return WorkspaceStatsState.from_dict(payload)

    def save(self, *, force: bool = False) -> None:
        now = time.monotonic()
        if not force:
            self._dirty = True
            if self._pending_since_monotonic <= 0:
                self._pending_since_monotonic = now
            if self._last_save_monotonic > 0:
                elapsed_since_last = now - self._last_save_monotonic
                elapsed_pending = now - self._pending_since_monotonic
                if (
                    elapsed_since_last < self._save_interval_seconds
                    and elapsed_pending < self._max_deferred_save_seconds
                ):
                    return
        self.project_data_dir.mkdir(parents=True, exist_ok=True)
        self.state.updated_at = _now_iso()
        temp_path = self.stats_path.with_name(f"{self.stats_path.name}.tmp")
        temp_path.write_text(
            json.dumps(self.state.to_dict(), indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
        temp_path.replace(self.stats_path)
        self._dirty = False
        self._last_save_monotonic = now
        self._pending_since_monotonic = 0.0

    def flush(self) -> None:
        """Persist any deferred stats updates immediately."""
        self.save(force=True)

    def get_total_runtime_seconds(self) -> float:
        return float(self.state.total_runtime_seconds)

    def get_total_active_seconds(self) -> float:
        return float(self.state.total_active_seconds)

    def record_runtime(self, seconds: float, *, force: bool = False) -> None:
        duration = _coerce_nonnegative_float(seconds)
        if duration <= 0:
            return
        self.state.total_runtime_seconds += duration
        self.save(force=force)

    def record_active_time(self, seconds: float, *, force: bool = False) -> None:
        duration = _coerce_nonnegative_float(seconds)
        if duration <= 0:
            return
        self.state.total_active_seconds += duration
        self.save(force=force)

    def update_session_snapshot(
        self,
        session_id: str,
        *,
        session_name: str = "",
        message_count: Optional[int] = None,
        force: bool = False,
    ) -> None:
        cleaned_id = _clean_text(session_id)
        if not cleaned_id:
            return
        summary = self.state.session_usage.get(cleaned_id) or SessionUsageSummary(session_id=cleaned_id)
        if session_name:
            summary.session_name = _clean_text(session_name)
        if message_count is not None:
            summary.message_count = _coerce_nonnegative_int(message_count)
        summary.updated_at = _now_iso()
        self.state.session_usage[cleaned_id] = summary
        self.save(force=force)

    def record_model_usage(
        self,
        *,
        provider: str,
        source: str,
        model: str,
        model_display_name: str,
        request_messages: List[Dict[str, Any]],
        assistant_text: str = "",
        reasoning_text: str = "",
        tool_calls: Optional[List[Dict[str, Any]]] = None,
        usage: Any = None,
        session_id: str = "",
        session_name: str = "",
        interaction_type: str = "chat",
        force: bool = False,
    ) -> None:
        usage_payload = self._usage_dict(usage)
        input_tokens = usage_payload.get("input_tokens")
        output_tokens = usage_payload.get("output_tokens")

        if input_tokens is None:
            input_tokens = self.count_messages_tokens(request_messages)
        if output_tokens is None:
            output_tokens = self.count_text_tokens(assistant_text) + self.count_text_tokens(reasoning_text)
            if tool_calls:
                try:
                    output_tokens += self.count_text_tokens(
                        json.dumps(
                            [
                                {
                                    key: value
                                    for key, value in tool_call.items()
                                    if key not in {"thought_signature", "gemini_thought_signature"}
                                }
                                for tool_call in tool_calls
                                if isinstance(tool_call, dict)
                            ],
                            ensure_ascii=False,
                            separators=(",", ":"),
                        )
                    )
                except Exception:
                    output_tokens += self.count_text_tokens(str(tool_calls))

        usage_key = self._usage_key(provider, source, model, model_display_name)
        summary = self.state.model_usage.get(usage_key)
        if summary is None:
            summary = ModelUsageSummary(
                usage_key=usage_key,
                provider=_clean_text(provider) or "unknown",
                source=_clean_text(source) or "standard",
                model=_clean_text(model),
                model_display_name=_clean_text(model_display_name) or _clean_text(model),
            )
        summary.calls += 1
        summary.input_tokens += _coerce_nonnegative_int(input_tokens)
        summary.output_tokens += _coerce_nonnegative_int(output_tokens)
        summary.last_used_at = _now_iso()
        self.state.model_usage[usage_key] = summary

        cleaned_session_id = _clean_text(session_id)
        if cleaned_session_id:
            session_summary = self.state.session_usage.get(cleaned_session_id)
            if session_summary is None:
                session_summary = SessionUsageSummary(session_id=cleaned_session_id)
            if session_name:
                session_summary.session_name = _clean_text(session_name)
            session_summary.calls += 1
            session_summary.input_tokens += _coerce_nonnegative_int(input_tokens)
            session_summary.output_tokens += _coerce_nonnegative_int(output_tokens)
            session_summary.updated_at = _now_iso()
            self.state.session_usage[cleaned_session_id] = session_summary

        self.save(force=force)

    def build_dashboard_data(self) -> Dict[str, Any]:
        model_rows = sorted(
            (
                summary.to_dict()
                for summary in self.state.model_usage.values()
            ),
            key=lambda item: (
                -_coerce_nonnegative_int(item.get("input_tokens")),
                -_coerce_nonnegative_int(item.get("output_tokens")),
                item.get("model_display_name", ""),
            ),
        )
        session_rows = sorted(
            (
                summary.to_dict()
                for summary in self.state.session_usage.values()
            ),
            key=lambda item: item.get("updated_at", ""),
            reverse=True,
        )
        total_input = sum(_coerce_nonnegative_int(item.get("input_tokens")) for item in model_rows)
        total_output = sum(_coerce_nonnegative_int(item.get("output_tokens")) for item in model_rows)
        total_calls = sum(_coerce_nonnegative_int(item.get("calls")) for item in model_rows)
        source_aggregate: Dict[str, Dict[str, Any]] = {}
        for row in model_rows:
            source_key = _clean_text(row.get("source")) or "standard"
            bucket = source_aggregate.setdefault(
                source_key,
                {
                    "source": source_key,
                    "calls": 0,
                    "input_tokens": 0,
                    "output_tokens": 0,
                    "models": set(),
                    "providers": set(),
                },
            )
            bucket["calls"] += _coerce_nonnegative_int(row.get("calls"))
            bucket["input_tokens"] += _coerce_nonnegative_int(row.get("input_tokens"))
            bucket["output_tokens"] += _coerce_nonnegative_int(row.get("output_tokens"))
            model_name = _clean_text(row.get("model_display_name")) or _clean_text(row.get("model"))
            provider_name = _clean_text(row.get("provider")) or "unknown"
            if model_name:
                bucket["models"].add(model_name)
            if provider_name:
                bucket["providers"].add(provider_name)

        source_rows = sorted(
            (
                {
                    "source": key,
                    "calls": value["calls"],
                    "input_tokens": value["input_tokens"],
                    "output_tokens": value["output_tokens"],
                    "model_count": len(value["models"]),
                    "provider_count": len(value["providers"]),
                    "models": sorted(value["models"]),
                    "providers": sorted(value["providers"]),
                }
                for key, value in source_aggregate.items()
            ),
            key=lambda item: (
                -_coerce_nonnegative_int(item.get("input_tokens")),
                -_coerce_nonnegative_int(item.get("output_tokens")),
                item.get("source", ""),
            ),
        )
        return {
            "workspace_id": self.state.workspace_id,
            "workspace_path": self.state.workspace_path,
            "workspace_name": self.state.workspace_name,
            "created_at": self.state.created_at,
            "updated_at": self.state.updated_at,
            "total_runtime_seconds": self.state.total_runtime_seconds,
            "total_active_seconds": self.state.total_active_seconds,
            "total_input_tokens": total_input,
            "total_output_tokens": total_output,
            "total_calls": total_calls,
            "model_usage": model_rows,
            "source_usage": source_rows,
            "session_usage": session_rows,
        }

    @classmethod
    def from_cache_dir(cls, cache_dir: Path) -> "WorkspaceStatsManager":
        workspace_path = ""
        state_path = Path(cache_dir) / "session_state.json"
        if state_path.exists():
            try:
                payload = json.loads(state_path.read_text(encoding="utf-8"))
                if isinstance(payload, dict):
                    workspace_path = _normalize_path(payload.get("workspace_path"))
            except Exception:
                workspace_path = ""
        project_root = Path(workspace_path) if workspace_path else None
        return cls(Path(cache_dir), project_root=project_root)

    @classmethod
    def discover_workspaces(cls, app_root: Optional[Path] = None) -> List[Dict[str, Any]]:
        root = Path(app_root or Path.cwd())
        projects_dir = root / ".reverie" / "project_caches"
        if not projects_dir.exists():
            return []

        discovered: List[Dict[str, Any]] = []
        for cache_dir in sorted(projects_dir.iterdir(), key=lambda item: item.name.lower()):
            if not cache_dir.is_dir():
                continue
            manager = cls.from_cache_dir(cache_dir)
            dashboard = manager.build_dashboard_data()
            sessions_count = len(list((cache_dir / "sessions").glob("*.json")))
            discovered.append(
                {
                    "cache_dir": str(cache_dir),
                    "workspace_id": dashboard["workspace_id"],
                    "workspace_path": dashboard["workspace_path"],
                    "workspace_name": dashboard["workspace_name"] or cache_dir.name,
                    "updated_at": dashboard["updated_at"],
                    "total_runtime_seconds": dashboard["total_runtime_seconds"],
                    "total_active_seconds": dashboard["total_active_seconds"],
                    "total_input_tokens": dashboard["total_input_tokens"],
                    "total_output_tokens": dashboard["total_output_tokens"],
                    "total_calls": dashboard["total_calls"],
                    "session_count": sessions_count,
                    "model_count": len(dashboard["model_usage"]),
                }
            )
        discovered.sort(key=lambda item: item.get("updated_at", ""), reverse=True)
        return discovered

    @staticmethod
    def list_session_files(cache_dir: Path) -> List[Dict[str, Any]]:
        sessions_dir = Path(cache_dir) / "sessions"
        session_index_path = Path(cache_dir) / "session_index.json"
        rows: List[Dict[str, Any]] = []
        if session_index_path.exists():
            try:
                payload = json.loads(session_index_path.read_text(encoding="utf-8"))
            except Exception:
                payload = {}
            raw_sessions = payload.get("sessions") if isinstance(payload, dict) else {}
            if isinstance(raw_sessions, dict) and raw_sessions:
                for session_id, entry in raw_sessions.items():
                    if not isinstance(entry, dict):
                        continue
                    rows.append(
                        {
                            "id": _clean_text(entry.get("id")) or str(session_id),
                            "name": _clean_text(entry.get("name")) or str(session_id),
                            "created_at": _clean_text(entry.get("created_at")),
                            "updated_at": _clean_text(entry.get("updated_at")),
                            "message_count": _coerce_nonnegative_int(entry.get("message_count")),
                            "path": str(sessions_dir / f"{_clean_text(entry.get('id')) or str(session_id)}.json"),
                        }
                    )
                rows.sort(key=lambda item: item.get("updated_at", ""), reverse=True)
                return rows

        for session_file in sessions_dir.glob("*.json"):
            try:
                payload = json.loads(session_file.read_text(encoding="utf-8"))
            except Exception:
                continue
            if not isinstance(payload, dict):
                continue
            rows.append(
                {
                    "id": _clean_text(payload.get("id")) or session_file.stem,
                    "name": _clean_text(payload.get("name")) or session_file.stem,
                    "created_at": _clean_text(payload.get("created_at")),
                    "updated_at": _clean_text(payload.get("updated_at")),
                    "message_count": len(payload.get("messages", []) or []),
                    "path": str(session_file),
                }
            )
        rows.sort(key=lambda item: item.get("updated_at", ""), reverse=True)
        return rows

    @staticmethod
    def load_session_payload(cache_dir: Path, session_id: str) -> Dict[str, Any]:
        target = Path(cache_dir) / "sessions" / f"{_clean_text(session_id)}.json"
        if not target.exists():
            return {}
        try:
            payload = json.loads(target.read_text(encoding="utf-8"))
        except Exception:
            return {}
        return payload if isinstance(payload, dict) else {}


def get_known_workspaces(app_root: Path) -> List[Dict[str, Any]]:
    """Helper used by the CLI to populate the /total workspace selector."""
    return WorkspaceStatsManager.discover_workspaces(app_root=app_root)
