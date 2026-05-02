"""Harness audit and reporting helpers for Reverie CLI."""

from __future__ import annotations

from collections import Counter
from datetime import datetime
import json
import re
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

from .config import get_project_data_dir
from .modes import normalize_mode
from .security_utils import PROJECT_CACHE_AUDIT_REL_PATH
from .tools.registry import get_tool_classes_for_mode


_TASK_LINE_RE = re.compile(r"^(?P<indent>\s*)\[(?P<state> |/|x|-)\]\s+(?P<name>.+?)\s*$")
_TASK_STATE_NAMES = {
    " ": "NOT_STARTED",
    "/": "IN_PROGRESS",
    "x": "COMPLETED",
    "-": "CANCELLED",
}
_TASK_STATE_MARKERS = {
    "NOT_STARTED": "[ ]",
    "IN_PROGRESS": "[/]",
    "COMPLETED": "[x]",
    "CANCELLED": "[-]",
}
_LOCAL_TZ = datetime.now().astimezone().tzinfo
_HARNESS_RUN_HISTORY_REL_PATH = Path("harness") / "prompt_runs.jsonl"
_MAX_HARNESS_RUN_HISTORY = 200
_VERIFICATION_HINTS = {
    "test": [
        "pytest",
        "unittest",
        "nose",
        "vitest",
        "jest",
        "ava",
        "mocha",
        "go test",
        "cargo test",
        "dotnet test",
        "mvn test",
        "gradle test",
        "./gradlew test",
        "ctest",
        "phpunit",
        "rspec",
        "bun test",
    ],
    "e2e": [
        "playwright",
        "cypress",
        "selenium",
        "puppeteer",
    ],
    "lint": [
        "ruff",
        "flake8",
        "pylint",
        "eslint",
        "shellcheck",
        "golangci-lint",
        "cargo clippy",
        "npm run lint",
        "pnpm lint",
        "yarn lint",
    ],
    "typecheck": [
        "mypy",
        "pyright",
        "tsc --noemit",
        "tsc --noEmit",
        "npm run typecheck",
        "pnpm typecheck",
        "yarn typecheck",
    ],
    "build": [
        "npm run build",
        "pnpm build",
        "yarn build",
        "cargo build",
        "dotnet build",
        "mvn package",
        "mvn verify",
        "gradle build",
        "./gradlew build",
        "cmake --build",
        "python -m build",
        "make build",
    ],
}
_TOOL_FAILURE_HINTS = {
    "schema_mismatch": [
        "parameter validation failed",
        "missing required parameter",
        "must be a string",
        "must be an integer",
        "must be a boolean",
        "must be an array",
        "unknown action",
        "unknown operation",
        "unknown query type",
        "unknown lsp_action",
        "unknown command",
        "unsupported action",
        "action is required",
        "query is required",
        "path is required",
        "prompt is required",
        "tool_name is required",
    ],
    "workspace_boundary": [
        "outside the active workspace",
        "permission denied",
        "blocked ",
        "working directory not found",
        "working directory is not a directory",
    ],
    "missing_dependency": [
        "not available",
        "missing dependencies",
        "disabled in config",
        "command executable not found",
        "tool not found",
        "symbol '",
        "file not found",
    ],
    "timeout": [
        "timed out",
        "timeout",
    ],
}
_PLAYBOOK_SEVERITY_ORDER = {
    "critical": 0,
    "high": 1,
    "medium": 2,
    "low": 3,
}


def _task_paths(project_root: Path) -> tuple[Path, Path]:
    artifacts_dir = Path(project_root) / "artifacts"
    return artifacts_dir / "task_list.json", artifacts_dir / "Tasks.md"


def _coerce_datetime(value: Any) -> Optional[datetime]:
    text = str(value or "").strip()
    if not text:
        return None
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return None
    if parsed.tzinfo is None and _LOCAL_TZ is not None:
        return parsed.replace(tzinfo=_LOCAL_TZ)
    return parsed


def _safe_json_load(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None


def _safe_json_lines(path: Path) -> List[Dict[str, Any]]:
    entries: List[Dict[str, Any]] = []
    if not path.exists():
        return entries

    try:
        for raw_line in path.read_text(encoding="utf-8").splitlines():
            raw_line = raw_line.strip()
            if not raw_line:
                continue
            try:
                payload = json.loads(raw_line)
            except Exception:
                continue
            if isinstance(payload, dict):
                entries.append(payload)
    except Exception:
        return []
    return entries


def _normalize_command_text(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "").strip()).lower()


def _compact_text(value: Any, limit: int = 180) -> str:
    text = re.sub(r"\s+", " ", str(value or "").strip())
    if len(text) <= limit:
        return text
    return f"{text[: max(limit - 3, 1)].rstrip()}..."


def _classify_verification_command(command_name: Any) -> List[str]:
    normalized = _normalize_command_text(command_name)
    if not normalized:
        return []

    matches: List[str] = []
    for category, hints in _VERIFICATION_HINTS.items():
        if any(hint in normalized for hint in hints):
            matches.append(category)
    return matches


def _harness_run_history_path(project_data_dir: Path) -> Path:
    return Path(project_data_dir).resolve() / _HARNESS_RUN_HISTORY_REL_PATH


def _float_or_zero(value: Any) -> float:
    try:
        return float(value or 0.0)
    except Exception:
        return 0.0


def _int_or_zero(value: Any) -> int:
    try:
        return int(value or 0)
    except Exception:
        return 0


def _compact_history_entry(entry: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "timestamp": str(entry.get("timestamp", "") or ""),
        "mode": str(entry.get("mode", "") or ""),
        "success": bool(entry.get("success")),
        "duration_seconds": round(_float_or_zero(entry.get("duration_seconds")), 3),
        "overall_score": _int_or_zero(entry.get("overall_score")),
        "verification_commands": _int_or_zero(entry.get("verification_commands")),
        "verification_categories": list(entry.get("verification_categories", []) or []),
        "task_active": str(entry.get("task_active", "") or ""),
        "auto_followup_count": _int_or_zero(entry.get("auto_followup_count")),
        "completion_gate_status": str(entry.get("completion_gate_status", "") or ""),
        "completion_gate_label": str(entry.get("completion_gate_label", "") or ""),
        "recovery_playbooks": _int_or_zero(entry.get("recovery_playbooks")),
    }


def _parse_task_entries(project_root: Path) -> Dict[str, Any]:
    json_path, markdown_path = _task_paths(project_root)
    counts = Counter()
    entries: List[Dict[str, Any]] = []
    source = "missing"

    payload = _safe_json_load(json_path) if json_path.exists() else None
    if isinstance(payload, dict):
        source = "json"
        for item in payload.get("tasks", []) or []:
            if not isinstance(item, dict):
                continue
            state = str(item.get("state", "NOT_STARTED") or "NOT_STARTED").upper()
            if state not in {"NOT_STARTED", "IN_PROGRESS", "COMPLETED", "CANCELLED"}:
                state = "NOT_STARTED"
            entry = {
                "id": str(item.get("id", "") or "").strip(),
                "name": str(item.get("name", "") or "").strip(),
                "state": state,
                "phase": str(item.get("phase", "") or "").strip(),
            }
            entries.append(entry)
            counts[state] += 1

    if not entries and markdown_path.exists():
        source = "markdown"
        try:
            for raw_line in markdown_path.read_text(encoding="utf-8").splitlines():
                match = _TASK_LINE_RE.match(raw_line)
                if not match:
                    continue
                state = _TASK_STATE_NAMES.get(match.group("state"), "NOT_STARTED")
                entry = {
                    "id": "",
                    "name": match.group("name").strip(),
                    "state": state,
                    "phase": "",
                }
                entries.append(entry)
                counts[state] += 1
        except Exception:
            entries = []

    return {
        "source": source,
        "json_path": str(json_path),
        "markdown_path": str(markdown_path),
        "exists": bool(entries) or json_path.exists() or markdown_path.exists(),
        "total": len(entries),
        "not_started": counts.get("NOT_STARTED", 0),
        "in_progress": counts.get("IN_PROGRESS", 0),
        "completed": counts.get("COMPLETED", 0),
        "cancelled": counts.get("CANCELLED", 0),
        "entries": entries[:10],
    }


def _filter_entries_by_window(
    entries: Iterable[Dict[str, Any]],
    *,
    started_at: Optional[str] = None,
    ended_at: Optional[str] = None,
) -> List[Dict[str, Any]]:
    start_dt = _coerce_datetime(started_at)
    end_dt = _coerce_datetime(ended_at)
    if start_dt is None and end_dt is None:
        return [dict(item) for item in entries if isinstance(item, dict)]

    filtered: List[Dict[str, Any]] = []
    for item in entries:
        if not isinstance(item, dict):
            continue
        item_dt = _coerce_datetime(item.get("timestamp"))
        if item_dt is None:
            continue
        if start_dt is not None and item_dt < start_dt:
            continue
        if end_dt is not None and item_dt > end_dt:
            continue
        filtered.append(dict(item))
    return filtered


def summarize_command_audit(
    project_root: Path,
    *,
    project_data_dir: Optional[Path] = None,
    started_at: Optional[str] = None,
    ended_at: Optional[str] = None,
) -> Dict[str, Any]:
    audit_root = Path(project_data_dir).resolve() if project_data_dir is not None else get_project_data_dir(Path(project_root))
    audit_path = audit_root / PROJECT_CACHE_AUDIT_REL_PATH
    entries = _safe_json_lines(audit_path)
    entries = _filter_entries_by_window(entries, started_at=started_at, ended_at=ended_at)

    counts = Counter()
    commands = Counter()
    blocked_reasons = Counter()
    verification_categories = Counter()
    verification_examples: List[str] = []
    latest_successful_check = ""
    explicit_verification_commands = 0
    for item in entries:
        event_name = str(item.get("event", "") or "unknown").strip().lower() or "unknown"
        counts[event_name] += 1
        command_name = str(
            item.get("normalized_command")
            or item.get("command")
            or item.get("tool")
            or ""
        ).strip()
        if command_name:
            commands[command_name] += 1
            matched_categories = _classify_verification_command(command_name)
            if matched_categories:
                explicit_verification_commands += 1
            if matched_categories and command_name not in verification_examples and len(verification_examples) < 5:
                verification_examples.append(command_name)
            for category in matched_categories:
                verification_categories[category] += 1
        if event_name == "command_blocked":
            reason = str(item.get("reason", "") or "").strip()
            if reason:
                blocked_reasons[reason] += 1

    successful_commands = 0
    failed_commands = 0
    successful_verification_commands = 0
    failed_verification_commands = 0
    for item in entries:
        if str(item.get("event", "") or "").strip().lower() != "command_result":
            continue
        exit_code = item.get("exit_code")
        command_name = str(
            item.get("normalized_command")
            or item.get("command")
            or item.get("tool")
            or ""
        ).strip()
        matched_categories = _classify_verification_command(command_name)
        if exit_code == 0:
            successful_commands += 1
            if matched_categories:
                successful_verification_commands += 1
                latest_successful_check = str(item.get("timestamp", "") or latest_successful_check)
        else:
            failed_commands += 1
            if matched_categories:
                failed_verification_commands += 1

    top_commands = [
        {"command": name, "count": count}
        for name, count in commands.most_common(5)
    ]
    top_blockers = [
        {"reason": reason, "count": count}
        for reason, count in blocked_reasons.most_common(3)
    ]

    return {
        "path": str(audit_path),
        "exists": audit_path.exists(),
        "entries": len(entries),
        "successful_commands": successful_commands,
        "failed_commands": failed_commands,
        "blocked_commands": counts.get("command_blocked", 0),
        "timed_out_commands": counts.get("command_timeout", 0),
        "events_by_type": dict(sorted(counts.items())),
        "verification": {
            "explicit_commands": explicit_verification_commands,
            "successful_commands": successful_verification_commands,
            "failed_commands": failed_verification_commands,
            "categories": dict(sorted(verification_categories.items())),
            "examples": verification_examples,
            "latest_successful_check": latest_successful_check,
            "has_runtime_validation": bool(
                verification_categories.get("test", 0) or verification_categories.get("e2e", 0)
            ),
            "has_static_validation": bool(
                verification_categories.get("lint", 0)
                or verification_categories.get("typecheck", 0)
                or verification_categories.get("build", 0)
            ),
        },
        "top_commands": top_commands,
        "top_blockers": top_blockers,
    }


def _classify_tool_failure(error_text: Any, result_text: Any = "") -> str:
    normalized = _normalize_command_text(f"{error_text or ''} {result_text or ''}")
    if not normalized:
        return "other"

    for category, hints in _TOOL_FAILURE_HINTS.items():
        if any(hint in normalized for hint in hints):
            return category
    return "other"


def summarize_operation_history(operation_history: Any) -> Dict[str, Any]:
    operations = list(getattr(operation_history, "operations", []) or [])
    by_type = Counter()
    tools = Counter()
    tool_failures = 0
    tool_failures_by_class = Counter()
    file_operations = Counter()
    touched_files: List[str] = []
    recent_failures: List[Dict[str, Any]] = []

    for operation in operations:
        operation_type = getattr(getattr(operation, "operation_type", None), "value", "")
        if operation_type:
            by_type[str(operation_type)] += 1
        tool_call = getattr(operation, "tool_call", None)
        tool_name = str(getattr(tool_call, "tool_name", "") or "").strip()
        if tool_name:
            tools[tool_name] += 1
            tool_error = str(getattr(tool_call, "error", "") or "").strip()
            tool_result = str(getattr(tool_call, "result", "") or "").strip()
            tool_success = bool(getattr(tool_call, "success", False))
            if (not tool_success) or tool_error:
                tool_failures += 1
                failure_class = _classify_tool_failure(tool_error, tool_result)
                tool_failures_by_class[failure_class] += 1

        file_operation = getattr(operation, "file_operation", None)
        file_path = str(getattr(file_operation, "file_path", "") or "").strip()
        file_kind = str(getattr(file_operation, "operation", "") or "").strip().lower()
        if file_kind:
            file_operations[file_kind] += 1
        if file_path and file_path not in touched_files:
            touched_files.append(file_path)

    for operation in reversed(operations):
        tool_call = getattr(operation, "tool_call", None)
        if tool_call is None:
            continue
        tool_name = str(getattr(tool_call, "tool_name", "") or "").strip()
        tool_error = str(getattr(tool_call, "error", "") or "").strip()
        tool_result = str(getattr(tool_call, "result", "") or "").strip()
        tool_success = bool(getattr(tool_call, "success", False))
        if tool_success and not tool_error:
            continue
        recent_failures.append(
            {
                "tool": tool_name,
                "classification": _classify_tool_failure(tool_error, tool_result),
                "error": _compact_text(tool_error or tool_result, limit=220),
                "timestamp": str(getattr(operation, "timestamp", "") or ""),
            }
        )
        if len(recent_failures) >= 5:
            break

    return {
        "operations": len(operations),
        "by_type": dict(sorted(by_type.items())),
        "tool_calls": sum(tools.values()),
        "tool_failures": tool_failures,
        "tool_failures_by_class": dict(sorted(tool_failures_by_class.items())),
        "file_operations": sum(file_operations.values()),
        "file_operations_by_kind": dict(sorted(file_operations.items())),
        "files_touched": len(touched_files),
        "touched_files": touched_files[:8],
        "recent_failures": recent_failures,
        "top_tools": [
            {"tool": name, "count": count}
            for name, count in tools.most_common(5)
        ],
    }


def summarize_checkpoints(rollback_manager: Any, *, session_id: str = "") -> Dict[str, Any]:
    checkpoint_manager = getattr(rollback_manager, "checkpoint_manager", None)
    if checkpoint_manager is None:
        return {"available": False, "count": 0, "latest": ""}

    try:
        checkpoints = checkpoint_manager.list_checkpoints(session_id=session_id or None)
    except Exception:
        checkpoints = []

    latest = ""
    if checkpoints:
        latest = str(getattr(checkpoints[0], "created_at", "") or "")

    return {
        "available": True,
        "count": len(checkpoints),
        "latest": latest,
    }


def summarize_sessions(session_manager: Any) -> Dict[str, Any]:
    if session_manager is None:
        return {"available": False, "count": 0, "current_session_id": "", "current_session_name": ""}

    try:
        sessions = session_manager.list_sessions()
    except Exception:
        sessions = []
    current_session = None
    try:
        current_session = session_manager.get_current_session()
    except Exception:
        current_session = None

    return {
        "available": True,
        "count": len(sessions),
        "current_session_id": str(getattr(current_session, "id", "") or ""),
        "current_session_name": str(getattr(current_session, "name", "") or ""),
    }


def summarize_git_workspace(git_integration: Any) -> Dict[str, Any]:
    if git_integration is None or not bool(getattr(git_integration, "is_available", False)):
        return {
            "available": False,
            "branch": "",
            "is_dirty": False,
            "dirty_files": 0,
            "modified": 0,
            "added": 0,
            "deleted": 0,
            "untracked": 0,
            "sample_paths": [],
        }

    try:
        changes = dict(git_integration.get_uncommitted_changes() or {})
    except Exception:
        changes = {}

    modified = list(changes.get("modified", []) or [])
    added = list(changes.get("added", []) or [])
    deleted = list(changes.get("deleted", []) or [])
    untracked = list(changes.get("untracked", []) or [])
    seen: set[str] = set()
    sample_paths: List[str] = []
    for path in modified + added + deleted + untracked:
        text = str(path or "").strip()
        if not text or text in seen:
            continue
        sample_paths.append(text)
        seen.add(text)
        if len(sample_paths) >= 6:
            break

    return {
        "available": True,
        "branch": str(getattr(git_integration, "get_current_branch", lambda: "")() or ""),
        "is_dirty": bool(modified or added or deleted or untracked),
        "dirty_files": len(set(modified + added + deleted + untracked)),
        "modified": len(modified),
        "added": len(added),
        "deleted": len(deleted),
        "untracked": len(untracked),
        "sample_paths": sample_paths,
    }


def summarize_activity_events(events: Iterable[Dict[str, Any]]) -> Dict[str, Any]:
    by_category = Counter()
    by_status = Counter()
    recent: List[Dict[str, Any]] = []

    for event in events or []:
        if not isinstance(event, dict):
            continue
        category = str(event.get("category", "") or "Activity").strip() or "Activity"
        status = str(event.get("status", "") or "info").strip().lower() or "info"
        by_category[category] += 1
        by_status[status] += 1
        if len(recent) < 5:
            recent.append(
                {
                    "category": category,
                    "status": status,
                    "message": str(event.get("message", "") or "").strip(),
                }
            )

    return {
        "count": sum(by_category.values()),
        "by_category": dict(sorted(by_category.items())),
        "by_status": dict(sorted(by_status.items())),
        "recent": recent,
    }


def summarize_ui_events(events: Iterable[Dict[str, Any]]) -> Dict[str, Any]:
    by_kind = Counter()
    tool_progress_by_tool = Counter()

    for event in events or []:
        if not isinstance(event, dict):
            continue
        kind = str(event.get("kind") or event.get("event") or "unknown").strip().lower() or "unknown"
        by_kind[kind] += 1
        if kind == "tool_progress":
            tool_name = str(event.get("tool_name", "") or "").strip()
            if tool_name:
                tool_progress_by_tool[tool_name] += 1

    return {
        "count": sum(by_kind.values()),
        "by_kind": dict(sorted(by_kind.items())),
        "tool_progress": [
            {"tool": name, "count": count}
            for name, count in tool_progress_by_tool.most_common(5)
        ],
    }


def persist_prompt_harness_run(
    project_data_dir: Path,
    *,
    prompt_result: Any,
    harness_report: Dict[str, Any],
) -> Dict[str, Any]:
    history_path = _harness_run_history_path(Path(project_data_dir))
    history_path.parent.mkdir(parents=True, exist_ok=True)

    workspace_audit = dict(harness_report.get("workspace_audit", {}) or {})
    command_window = dict(harness_report.get("command_window", {}) or {})
    verification = dict(command_window.get("verification", {}) or {})
    summary = dict(workspace_audit.get("summary", {}) or {})
    task_snapshot = dict(workspace_audit.get("task_snapshot", {}) or {})
    checkpoints = dict(harness_report.get("checkpoints", {}) or {})
    operation_history = dict(harness_report.get("operation_history", {}) or {})
    completion_gate = dict(workspace_audit.get("completion_gate", {}) or harness_report.get("completion_gate", {}) or {})
    recovery_playbooks = list(workspace_audit.get("recovery_playbooks", []) or harness_report.get("recovery_playbooks", []) or [])

    entry = {
        "timestamp": str(getattr(prompt_result, "ended_at", "") or ""),
        "started_at": str(getattr(prompt_result, "started_at", "") or ""),
        "ended_at": str(getattr(prompt_result, "ended_at", "") or ""),
        "mode": str(getattr(prompt_result, "mode", "") or ""),
        "success": bool(getattr(prompt_result, "success", False)),
        "duration_seconds": round(_float_or_zero(getattr(prompt_result, "duration_seconds", 0.0)), 3),
        "auto_followup_count": _int_or_zero(getattr(prompt_result, "auto_followup_count", 0)),
        "overall_score": _int_or_zero(workspace_audit.get("overall_score")),
        "visible_tools": _int_or_zero(summary.get("visible_tools")),
        "audit_events": _int_or_zero(command_window.get("entries")),
        "checkpoint_count": _int_or_zero(checkpoints.get("count")),
        "operation_count": _int_or_zero(operation_history.get("operations")),
        "verification_commands": _int_or_zero(verification.get("explicit_commands")),
        "verification_categories": list((verification.get("categories", {}) or {}).keys()),
        "task_active": str(task_snapshot.get("active", "") or ""),
        "task_next": str(task_snapshot.get("next", "") or ""),
        "completion_gate_status": str(completion_gate.get("status", "") or ""),
        "completion_gate_label": str(completion_gate.get("label", "") or ""),
        "recovery_playbooks": len(recovery_playbooks),
        "recovery_playbook_ids": [
            str(item.get("id", "") or "")
            for item in recovery_playbooks
            if str(item.get("id", "") or "").strip()
        ][:6],
        "session_id": str(getattr(prompt_result, "session_id", "") or ""),
        "session_name": str(getattr(prompt_result, "session_name", "") or ""),
        "error": str(getattr(prompt_result, "error", "") or ""),
    }

    entries = _safe_json_lines(history_path)
    entries.append(entry)
    entries = entries[-_MAX_HARNESS_RUN_HISTORY:]
    history_path.write_text(
        "\n".join(json.dumps(item, ensure_ascii=False) for item in entries) + "\n",
        encoding="utf-8",
    )

    history_summary = summarize_prompt_harness_history(project_data_dir, limit=8)
    history_summary["path"] = str(history_path)
    return history_summary


def summarize_prompt_harness_history(
    project_data_dir: Path,
    *,
    limit: int = 8,
) -> Dict[str, Any]:
    history_path = _harness_run_history_path(Path(project_data_dir))
    entries = _safe_json_lines(history_path)
    total_runs = len(entries)
    if total_runs == 0:
        return {
            "path": str(history_path),
            "exists": history_path.exists(),
            "total_runs": 0,
            "recent_runs": [],
            "recent_success_rate": 0,
            "recent_verification_coverage": 0,
            "average_score": 0,
            "average_duration_seconds": 0.0,
            "score_delta": 0,
            "score_trend": "no_baseline",
            "score_trend_label": "No history yet",
            "latest_run": {},
        }

    recent = entries[-max(limit, 1):]
    latest = recent[-1]
    previous = recent[-2] if len(recent) > 1 else None
    success_count = sum(1 for item in recent if bool(item.get("success")))
    verification_count = sum(1 for item in recent if _int_or_zero(item.get("verification_commands")) > 0)
    average_score = int(round(
        sum(_int_or_zero(item.get("overall_score")) for item in recent) / max(len(recent), 1)
    ))
    average_duration = round(
        sum(_float_or_zero(item.get("duration_seconds")) for item in recent) / max(len(recent), 1),
        3,
    )
    score_delta = 0
    if previous is not None:
        score_delta = _int_or_zero(latest.get("overall_score")) - _int_or_zero(previous.get("overall_score"))
    if previous is None:
        score_trend = "no_baseline"
        score_trend_label = "Need more than one run"
    elif score_delta >= 5:
        score_trend = "improving"
        score_trend_label = f"Improving (+{score_delta})"
    elif score_delta <= -5:
        score_trend = "falling"
        score_trend_label = f"Falling ({score_delta})"
    else:
        score_trend = "stable"
        score_trend_label = f"Stable ({score_delta:+d})"

    return {
        "path": str(history_path),
        "exists": history_path.exists(),
        "total_runs": total_runs,
        "recent_runs": [_compact_history_entry(item) for item in reversed(recent)],
        "recent_success_rate": int(round((success_count / max(len(recent), 1)) * 100)),
        "recent_verification_coverage": int(round((verification_count / max(len(recent), 1)) * 100)),
        "average_score": average_score,
        "average_duration_seconds": average_duration,
        "score_delta": score_delta,
        "score_trend": score_trend,
        "score_trend_label": score_trend_label,
        "latest_run": _compact_history_entry(latest),
    }


def _tool_name_set(tool_surface: Dict[str, Any]) -> set[str]:
    return {
        str(name or "").strip()
        for name in tool_surface.get("names", []) or []
        if str(name or "").strip()
    }


def _limited_names(names: Iterable[Any], limit: int = 6) -> List[str]:
    visible: List[str] = []
    seen: set[str] = set()
    for item in names:
        text = str(item or "").strip()
        if not text or text in seen:
            continue
        visible.append(text)
        seen.add(text)
        if len(visible) >= limit:
            break
    return visible


def summarize_task_snapshot(task_summary: Dict[str, Any], limit: int = 5) -> Dict[str, Any]:
    entries = [
        dict(item)
        for item in task_summary.get("entries", []) or []
        if isinstance(item, dict)
    ]
    active = ""
    next_up = ""
    sample_lines: List[str] = []

    for item in entries:
        state = str(item.get("state", "NOT_STARTED") or "NOT_STARTED").upper()
        name = str(item.get("name", "") or "").strip()
        phase = str(item.get("phase", "") or "").strip()
        if not name:
            continue
        if not active and state == "IN_PROGRESS":
            active = name
        if not next_up and state == "NOT_STARTED":
            next_up = name

        marker = _TASK_STATE_MARKERS.get(state, "[ ]")
        suffix = f" ({phase})" if phase else ""
        if len(sample_lines) < limit:
            sample_lines.append(f"{marker} {name}{suffix}")

    return {
        "active": active,
        "next": next_up,
        "multiple_in_progress": task_summary.get("in_progress", 0) > 1,
        "sample_lines": sample_lines,
    }


def _build_playbook(
    *,
    playbook_id: str,
    title: str,
    severity: str,
    why: str,
    evidence: Iterable[Any],
    actions: Iterable[Any],
) -> Dict[str, Any]:
    return {
        "id": str(playbook_id or "").strip(),
        "title": str(title or "").strip(),
        "severity": str(severity or "medium").strip().lower() or "medium",
        "why": _compact_text(why, limit=220),
        "evidence": [
            _compact_text(item, limit=200)
            for item in evidence
            if _compact_text(item, limit=200)
        ][:4],
        "actions": [
            _compact_text(item, limit=220)
            for item in actions
            if _compact_text(item, limit=220)
        ][:4],
    }


def build_recovery_playbooks(
    *,
    task_summary: Dict[str, Any],
    task_snapshot: Dict[str, Any],
    audit_summary: Dict[str, Any],
    verification_summary: Dict[str, Any],
    operation_summary: Dict[str, Any],
    checkpoint_summary: Dict[str, Any],
    history_summary: Dict[str, Any],
    git_workspace: Dict[str, Any],
) -> List[Dict[str, Any]]:
    playbooks: List[Dict[str, Any]] = []

    if audit_summary.get("failed_commands", 0) > 0 or verification_summary.get("failed_commands", 0) > 0:
        playbooks.append(
            _build_playbook(
                playbook_id="failed_checks",
                title="Stabilize failing verification before closing",
                severity="critical" if verification_summary.get("failed_commands", 0) > 0 else "high",
                why="The harness is still seeing failing command results, so the execution loop has not converged yet.",
                evidence=[
                    f"{audit_summary.get('failed_commands', 0)} failed command(s) in the audit trail.",
                    f"{verification_summary.get('failed_commands', 0)} failed verification command(s).",
                    f"Recent verification categories: {', '.join((verification_summary.get('categories', {}) or {}).keys()) or '(none)'}",
                ],
                actions=[
                    "Re-run the exact failing command first and fix the first broken assertion, compile error, or runtime failure it reports.",
                    "Do not widen scope until the same targeted check is green again.",
                    "Only mark the active task complete after the previously failing command passes or a real blocker is recorded.",
                ],
            )
        )

    if int((operation_summary.get("tool_failures_by_class", {}) or {}).get("schema_mismatch", 0) or 0) > 0:
        recent_schema_failures = [
            item.get("error", "")
            for item in operation_summary.get("recent_failures", []) or []
            if str(item.get("classification", "") or "") == "schema_mismatch"
        ]
        playbooks.append(
            _build_playbook(
                playbook_id="tool_schema_mismatch",
                title="Recover from tool-schema mismatch",
                severity="medium",
                why="Recent tool failures look like parameter-shape or required-field mistakes rather than real product defects.",
                evidence=[
                    f"{int((operation_summary.get('tool_failures_by_class', {}) or {}).get('schema_mismatch', 0) or 0)} schema-related tool failure(s).",
                    *recent_schema_failures[:2],
                ],
                actions=[
                    "Inspect the live tool schema with tool_catalog before retrying.",
                    "Use exact field names and required parameters instead of near-miss aliases or guessed payload shapes.",
                    "Retry once with a validated payload instead of brute-forcing repeated invalid calls.",
                ],
            )
        )

    if task_snapshot.get("multiple_in_progress"):
        playbooks.append(
            _build_playbook(
                playbook_id="lane_conflict",
                title="Collapse to one active execution lane",
                severity="medium",
                why="More than one task is currently marked IN_PROGRESS, which makes the harness more likely to thrash instead of converge.",
                evidence=[
                    f"{task_summary.get('in_progress', 0)} tasks are currently IN_PROGRESS.",
                    f"Active task: {task_snapshot.get('active', '(none)')}",
                    f"Next task: {task_snapshot.get('next', '(none)')}",
                ],
                actions=[
                    "Pick the single task that owns the next concrete step and move all others back to NOT_STARTED or BLOCKED.",
                    "Use one batch task_manager update so the ledger reflects one clear lane.",
                    "Run verification for the active lane before switching to the next one.",
                ],
            )
        )

    needs_verification_recovery = (
        verification_summary.get("explicit_commands", 0) == 0
        and (
            bool(task_snapshot.get("active"))
            or bool(git_workspace.get("is_dirty"))
            or audit_summary.get("entries", 0) > 0
        )
    )
    if needs_verification_recovery:
        playbooks.append(
            _build_playbook(
                playbook_id="verification_gap",
                title="Close the verification gap",
                severity="high" if task_snapshot.get("active") else "medium",
                why="The current lane has execution evidence, but no explicit test/build/lint/browser verification has been recorded yet.",
                evidence=[
                    f"{audit_summary.get('entries', 0)} audited command event(s) and {verification_summary.get('explicit_commands', 0)} explicit verification command(s).",
                    f"Dirty git paths: {git_workspace.get('dirty_files', 0)}" if git_workspace.get("available") else "",
                    f"Active task: {task_snapshot.get('active', '(none)')}",
                ],
                actions=[
                    "Run the smallest meaningful test, build, lint, or browser check that proves the active change path.",
                    "Prefer command_exec-backed checks so the harness keeps auditable evidence.",
                    "If verification is impossible right now, record the exact blocker instead of implying completion.",
                ],
            )
        )

    if checkpoint_summary.get("count", 0) == 0 and (
        bool(task_snapshot.get("active"))
        or audit_summary.get("entries", 0) > 0
    ):
        playbooks.append(
            _build_playbook(
                playbook_id="checkpoint_gap",
                title="Add a recovery anchor before the next risky step",
                severity="low",
                why="The session has started doing real work without leaving behind a rollback anchor.",
                evidence=[
                    f"{checkpoint_summary.get('count', 0)} checkpoints recorded.",
                    f"{audit_summary.get('entries', 0)} audited command event(s).",
                ],
                actions=[
                    "Create a checkpoint before the next risky refactor, migration, or broad command.",
                    "Use rollback as a deliberate recovery rail rather than waiting for a bad state to accumulate.",
                ],
            )
        )

    if history_summary.get("score_trend") == "falling" or history_summary.get("recent_success_rate", 100) < 50:
        playbooks.append(
            _build_playbook(
                playbook_id="run_regression",
                title="Investigate recent harness regression",
                severity="medium",
                why="Recent prompt-mode runs show lower stability than the previous baseline.",
                evidence=[
                    f"Trend: {history_summary.get('score_trend_label', 'n/a')}",
                    f"Recent success rate: {history_summary.get('recent_success_rate', 0)}%",
                    f"Recent verification coverage: {history_summary.get('recent_verification_coverage', 0)}%",
                ],
                actions=[
                    "Compare the latest runs and identify which layer regressed: goals, context, tools, execution, memory, evaluation, or recovery.",
                    "Tighten the first regressed layer before widening scope again.",
                ],
            )
        )

    playbooks.sort(
        key=lambda item: (
            _PLAYBOOK_SEVERITY_ORDER.get(str(item.get("severity", "medium") or "medium"), 99),
            str(item.get("title", "")).lower(),
        )
    )
    return playbooks


def build_completion_gate(
    *,
    task_summary: Dict[str, Any],
    task_snapshot: Dict[str, Any],
    audit_summary: Dict[str, Any],
    verification_summary: Dict[str, Any],
    operation_summary: Dict[str, Any],
    git_workspace: Dict[str, Any],
) -> Dict[str, Any]:
    reasons: List[str] = []
    next_actions: List[str] = []
    status = "ready"
    label = "Ready to close"
    confidence = 85

    if audit_summary.get("failed_commands", 0) > 0:
        status = "blocked"
        label = "Blocked by failing checks"
        confidence = 92
        reasons.append(f"{audit_summary.get('failed_commands', 0)} audited command(s) are still failing.")
        next_actions.append("Fix the failing command path and rerun the same verification step.")

    schema_failures = int((operation_summary.get("tool_failures_by_class", {}) or {}).get("schema_mismatch", 0) or 0)
    if status != "blocked" and schema_failures > 0:
        status = "blocked"
        label = "Blocked by tool-call mismatch"
        confidence = 84
        reasons.append(f"{schema_failures} recent tool failure(s) look like schema or parameter mismatches.")
        next_actions.append("Inspect the tool schema and retry with an exact payload.")

    if status == "ready" and task_snapshot.get("multiple_in_progress"):
        status = "continue"
        label = "Continue implementation"
        confidence = 78
        reasons.append("Multiple tasks are in progress, so the active lane is still ambiguous.")
        next_actions.append("Collapse the task ledger to one active lane before closing.")

    if status == "ready" and task_snapshot.get("active"):
        status = "continue"
        label = "Continue implementation"
        confidence = 82
        reasons.append(f"Active task still open: {task_snapshot.get('active')}.")
        next_actions.append("Finish or explicitly block the active task before treating the run as done.")

    verification_gap = (
        verification_summary.get("explicit_commands", 0) == 0
        and (
            bool(task_snapshot.get("active"))
            or bool(git_workspace.get("is_dirty"))
            or audit_summary.get("entries", 0) > 0
        )
    )
    if status == "ready" and verification_gap:
        status = "continue"
        label = "Needs explicit verification"
        confidence = 74
        reasons.append("No explicit verification evidence is visible for the current execution lane.")
        next_actions.append("Run a focused test, build, lint, or browser check before closing.")

    if status == "ready" and task_summary.get("total", 0) == 0 and audit_summary.get("entries", 0) == 0:
        confidence = 60
        reasons.append("No active task ledger or command evidence is present, so this gate is informational rather than authoritative.")

    if status == "ready" and verification_summary.get("explicit_commands", 0) > 0:
        reasons.append(
            f"Explicit verification is present across {', '.join((verification_summary.get('categories', {}) or {}).keys()) or 'at least one category'}."
        )

    return {
        "status": status,
        "label": label,
        "confidence": confidence,
        "reasons": reasons[:4],
        "next_actions": next_actions[:3],
    }


def _resolve_tool_surface(agent: Any, mode: str) -> Dict[str, Any]:
    normalized_mode = normalize_mode(mode or "reverie")
    if agent is not None:
        tool_executor = getattr(agent, "tool_executor", None)
        if tool_executor is not None and hasattr(tool_executor, "get_tool_records"):
            try:
                records = tool_executor.get_tool_records(mode=normalized_mode)
            except Exception:
                records = []
            return {
                "count": len(records),
                "names": [str(item.get("name", "") or "").strip() for item in records if str(item.get("name", "") or "").strip()],
            }

    tool_classes = get_tool_classes_for_mode(normalized_mode, include_hidden=False)
    return {
        "count": len(tool_classes),
        "names": [
            str(getattr(tool_class, "name", "") or "").strip()
            for tool_class in tool_classes
            if str(getattr(tool_class, "name", "") or "").strip()
        ],
    }


def _score_from_signals(signals: Dict[str, bool]) -> int:
    values = [bool(value) for value in signals.values()]
    if not values:
        return 0
    passed = sum(1 for value in values if value)
    return int(round((passed / len(values)) * 100))


def _recommendations_from_audit(
    *,
    task_summary: Dict[str, Any],
    task_snapshot: Dict[str, Any],
    audit_summary: Dict[str, Any],
    verification_summary: Dict[str, Any],
    checkpoint_summary: Dict[str, Any],
    sessions_summary: Dict[str, Any],
    operation_summary: Dict[str, Any],
    history_summary: Dict[str, Any],
    scores: Dict[str, int],
    tool_surface: Dict[str, Any],
    plugin_tools: int,
    mcp_tools: int,
    skill_count: int,
    skill_errors: int,
) -> List[str]:
    recommendations: List[str] = []

    if task_summary.get("total", 0) == 0:
        recommendations.append("No active task ledger is present. Use task_manager when work becomes multi-step, cross-file, or verification-heavy.")
    if task_snapshot.get("multiple_in_progress"):
        recommendations.append("Multiple tasks are marked IN_PROGRESS. Tighten the execution track so only one active task owns the current step.")
    if audit_summary.get("entries", 0) == 0:
        recommendations.append("No command audit evidence exists yet. Run command_exec-backed verification to leave an auditable trail.")
    if verification_summary.get("explicit_commands", 0) == 0:
        recommendations.append("No explicit verification commands were detected. Add test, lint, build, or browser checks before closing implementation work.")
    if checkpoint_summary.get("count", 0) == 0:
        recommendations.append("No checkpoints are recorded yet. Longer runs would benefit from more rollback anchors and clearer recovery cut points.")
    if sessions_summary.get("count", 0) <= 1:
        recommendations.append("Workspace session history is still shallow. Repeated use will improve continuity, recovery value, and memory quality.")
    if operation_summary.get("operations", 0) == 0:
        recommendations.append("Operation history is still empty. A richer execution trail will make rollback and forensics more trustworthy.")
    if history_summary.get("total_runs", 0) == 0:
        recommendations.append("No prompt-run harness history exists yet. Capturing repeated runs will make stability trends and regressions easier to spot.")
    elif history_summary.get("recent_verification_coverage", 0) < 50:
        recommendations.append("Recent runs rarely leave explicit verification evidence. Make test/build/lint checks part of the normal execution loop.")
    elif history_summary.get("score_trend") == "falling":
        recommendations.append("Recent harness scores are trending down. Review the latest run history to see which layers regressed.")
    if tool_surface.get("count", 0) < 6:
        recommendations.append("The visible tool surface is small for the active mode. Check provider setup or switch to a mode with a richer harness.")
    if mcp_tools == 0 and plugin_tools == 0:
        recommendations.append("No MCP or runtime-plugin tools are currently active. External capability expansion is available but unused.")
    if skill_count == 0:
        recommendations.append("No Codex-style skills are currently loaded. Reusable workflows could be captured as SKILL.md packs.")
    if skill_errors > 0:
        recommendations.append("Some skills failed validation. Fix the invalid skill roots so prompt injection stays trustworthy.")
    if scores.get("evaluation", 0) < 70:
        recommendations.append("Evaluation coverage is thin. Prefer explicit test/build/run evidence before closing implementation tasks.")
    if scores.get("recovery", 0) < 70:
        recommendations.append("Recovery infrastructure is present but underused. Lean on checkpoints, task ledgers, and session continuity more deliberately.")

    return recommendations[:6]


def build_harness_capability_report(
    project_root: Path,
    *,
    project_data_dir: Optional[Path] = None,
    mode: str = "reverie",
    agent: Any = None,
    indexer: Any = None,
    ensure_context_engine: Any = None,
    git_integration: Any = None,
    ensure_git_integration: Any = None,
    lsp_manager: Any = None,
    ensure_lsp_manager: Any = None,
    session_manager: Any = None,
    memory_indexer: Any = None,
    operation_history: Any = None,
    rollback_manager: Any = None,
    runtime_plugin_manager: Any = None,
    skills_manager: Any = None,
    mcp_runtime: Any = None,
) -> Dict[str, Any]:
    workspace_root = Path(project_root).resolve()
    resolved_project_data_dir = (
        Path(project_data_dir).resolve()
        if project_data_dir is not None
        else get_project_data_dir(workspace_root)
    )
    normalized_mode = normalize_mode(mode or "reverie")
    task_summary = _parse_task_entries(workspace_root)
    task_snapshot = summarize_task_snapshot(task_summary)
    audit_summary = summarize_command_audit(workspace_root, project_data_dir=resolved_project_data_dir)
    verification_summary = dict(audit_summary.get("verification", {}) or {})
    operation_summary = summarize_operation_history(operation_history)
    checkpoint_summary = summarize_checkpoints(rollback_manager)
    sessions_summary = summarize_sessions(session_manager)
    history_summary = summarize_prompt_harness_history(resolved_project_data_dir)
    git_workspace = summarize_git_workspace(git_integration)
    tool_surface = _resolve_tool_surface(agent, normalized_mode)
    visible_tool_names = _tool_name_set(tool_surface)

    plugin_summary = (
        runtime_plugin_manager.get_status_summary(force_refresh=False)
        if runtime_plugin_manager is not None and hasattr(runtime_plugin_manager, "get_status_summary")
        else {}
    )
    skills_summary = (
        skills_manager.get_status_summary(force_refresh=False)
        if skills_manager is not None and hasattr(skills_manager, "get_status_summary")
        else {}
    )
    try:
        mcp_tools = len(mcp_runtime.get_tool_definitions(force_refresh=False)) if mcp_runtime is not None else 0
    except Exception:
        mcp_tools = 0

    goal_signals = {
        "task_manager_visible": "task_manager" in visible_tool_names,
        "task_artifact_present": bool(task_summary.get("exists")),
        "single_active_lane": task_summary.get("in_progress", 0) <= 1,
        "execution_history": operation_summary.get("operations", 0) > 0 or sessions_summary.get("count", 0) > 0,
    }
    context_signals = {
        "context_engine": bool(indexer is not None or callable(ensure_context_engine)),
        "git": bool(getattr(git_integration, "is_available", False) or callable(ensure_git_integration)),
        "lsp": bool(
            (lsp_manager is not None and bool((lsp_manager.build_status_report() or {}).get("available")))
            or callable(ensure_lsp_manager)
        ),
        "workspace_memory": memory_indexer is not None,
    }
    tool_signals = {
        "tool_surface": tool_surface.get("count", 0) >= 6,
        "command_exec_visible": "command_exec" in visible_tool_names,
        "mcp_or_plugins": (mcp_tools + int(plugin_summary.get("tool_count", 0) or 0)) > 0,
        "skills_loaded": int(skills_summary.get("skill_count", 0) or 0) > 0,
    }
    execution_signals = {
        "task_manager_visible": "task_manager" in visible_tool_names,
        "command_exec_visible": "command_exec" in visible_tool_names,
        "operation_history": operation_history is not None,
        "session_tracking": bool(sessions_summary.get("available")),
    }
    memory_signals = {
        "workspace_memory": memory_indexer is not None,
        "sessions": bool(sessions_summary.get("available")),
        "task_ledger": bool(task_summary.get("exists")),
        "checkpoint_layer": rollback_manager is not None,
    }
    evaluation_signals = {
        "command_exec_visible": "command_exec" in visible_tool_names,
        "audited_commands": audit_summary.get("entries", 0) > 0,
        "successful_verification_commands": audit_summary.get("successful_commands", 0) > 0,
        "explicit_verification": verification_summary.get("explicit_commands", 0) > 0,
        "task_closure": task_summary.get("completed", 0) > 0 or task_summary.get("total", 0) == 0,
    }
    recovery_signals = {
        "rollback": rollback_manager is not None,
        "checkpoints": checkpoint_summary.get("count", 0) > 0,
        "audit_log": bool(audit_summary.get("exists")),
        "session_history": bool(sessions_summary.get("available")),
        "operation_history": operation_history is not None,
        "run_history": history_summary.get("total_runs", 0) > 0,
    }
    completion_gate = build_completion_gate(
        task_summary=task_summary,
        task_snapshot=task_snapshot,
        audit_summary=audit_summary,
        verification_summary=verification_summary,
        operation_summary=operation_summary,
        git_workspace=git_workspace,
    )
    recovery_playbooks = build_recovery_playbooks(
        task_summary=task_summary,
        task_snapshot=task_snapshot,
        audit_summary=audit_summary,
        verification_summary=verification_summary,
        operation_summary=operation_summary,
        checkpoint_summary=checkpoint_summary,
        history_summary=history_summary,
        git_workspace=git_workspace,
    )

    categories = {
        "goals": {
            "score": _score_from_signals(goal_signals),
            "signals": goal_signals,
            "highlights": [
                "task ledger present" if task_summary.get("exists") else "no task ledger yet",
                f"{task_summary.get('in_progress', 0)} active tasks",
                f"{task_summary.get('total', 0)} tracked tasks",
            ],
        },
        "context": {
            "score": _score_from_signals(context_signals),
            "signals": context_signals,
            "highlights": [
                "context engine ready" if indexer is not None else "context engine lazy/on-demand",
                "git available" if getattr(git_integration, "is_available", False) else "git on demand or unavailable",
                "memory indexer enabled" if memory_indexer is not None else "memory indexer unavailable",
                f"{git_workspace.get('dirty_files', 0)} dirty git paths" if git_workspace.get("available") else "git workspace state unavailable",
            ],
        },
        "tools": {
            "score": _score_from_signals(tool_signals),
            "signals": tool_signals,
            "highlights": [
                f"{tool_surface.get('count', 0)} visible tools in {normalized_mode}",
                f"{mcp_tools} MCP tools",
                f"{int(plugin_summary.get('tool_count', 0) or 0)} runtime-plugin tools",
            ],
        },
        "execution": {
            "score": _score_from_signals(execution_signals),
            "signals": execution_signals,
            "highlights": [
                "operation history active" if operation_history is not None else "operation history unavailable",
                "task_manager visible" if "task_manager" in visible_tool_names else "task_manager hidden",
                f"{operation_summary.get('tool_calls', 0)} recorded tool calls",
                completion_gate.get("label", ""),
            ],
        },
        "memory": {
            "score": _score_from_signals(memory_signals),
            "signals": memory_signals,
            "highlights": [
                "workspace memory enabled" if memory_indexer is not None else "workspace memory unavailable",
                f"{sessions_summary.get('count', 0)} workspace sessions",
                f"{checkpoint_summary.get('count', 0)} checkpoints",
            ],
        },
        "evaluation": {
            "score": _score_from_signals(evaluation_signals),
            "signals": evaluation_signals,
            "highlights": [
                f"{verification_summary.get('explicit_commands', 0)} explicit checks",
                f"{audit_summary.get('successful_commands', 0)} successful commands",
                f"{audit_summary.get('failed_commands', 0)} failed commands",
                ", ".join((verification_summary.get("categories", {}) or {}).keys()) or "no verification categories yet",
            ],
        },
        "recovery": {
            "score": _score_from_signals(recovery_signals),
            "signals": recovery_signals,
            "highlights": [
                "rollback manager ready" if rollback_manager is not None else "rollback manager unavailable",
                f"{checkpoint_summary.get('count', 0)} checkpoints",
                f"{history_summary.get('total_runs', 0)} stored runs",
            ],
        },
    }
    scores = {name: int(payload["score"]) for name, payload in categories.items()}
    overall_score = int(round(sum(scores.values()) / max(len(scores), 1)))

    runtime = {
        "task_manager_visible": "task_manager" in visible_tool_names,
        "command_exec_visible": "command_exec" in visible_tool_names,
        "workspace_memory_available": memory_indexer is not None,
        "operation_history_available": operation_history is not None,
        "rollback_available": rollback_manager is not None,
        "automatic_checkpoints": rollback_manager is not None,
        "session_continuity_available": session_manager is not None,
        "git_workspace_available": git_workspace.get("available", False),
    }

    recommendations = _recommendations_from_audit(
        task_summary=task_summary,
        task_snapshot=task_snapshot,
        audit_summary=audit_summary,
        verification_summary=verification_summary,
        checkpoint_summary=checkpoint_summary,
        sessions_summary=sessions_summary,
        operation_summary=operation_summary,
        history_summary=history_summary,
        scores=scores,
        tool_surface=tool_surface,
        plugin_tools=int(plugin_summary.get("tool_count", 0) or 0),
        mcp_tools=mcp_tools,
        skill_count=int(skills_summary.get("skill_count", 0) or 0),
        skill_errors=int(skills_summary.get("error_count", 0) or 0),
    )

    return {
        "workspace_root": str(workspace_root),
        "project_data_dir": str(resolved_project_data_dir),
        "mode": normalized_mode,
        "overall_score": overall_score,
        "scores": scores,
        "summary": {
            "visible_tools": tool_surface.get("count", 0),
            "task_total": task_summary.get("total", 0),
            "task_in_progress": task_summary.get("in_progress", 0),
            "sessions": sessions_summary.get("count", 0),
            "operations": operation_summary.get("operations", 0),
            "checkpoints": checkpoint_summary.get("count", 0),
            "audit_events": audit_summary.get("entries", 0),
            "verification_commands": verification_summary.get("explicit_commands", 0),
            "mcp_tools": mcp_tools,
            "runtime_plugin_tools": int(plugin_summary.get("tool_count", 0) or 0),
            "skills": int(skills_summary.get("skill_count", 0) or 0),
            "prompt_runs": history_summary.get("total_runs", 0),
            "recent_success_rate": history_summary.get("recent_success_rate", 0),
            "recent_verification_coverage": history_summary.get("recent_verification_coverage", 0),
            "dirty_files": git_workspace.get("dirty_files", 0),
            "recovery_playbooks": len(recovery_playbooks),
            "completion_gate_status": completion_gate.get("status", ""),
        },
        "categories": categories,
        "task_snapshot": task_snapshot,
        "runtime": runtime,
        "completion_gate": completion_gate,
        "recovery_playbooks": recovery_playbooks,
        "artifacts": {
            "tasks": task_summary,
            "command_audit": audit_summary,
            "verification": verification_summary,
            "operation_history": operation_summary,
            "checkpoints": checkpoint_summary,
            "sessions": sessions_summary,
            "prompt_runs": history_summary,
            "git_workspace": git_workspace,
        },
        "integrations": {
            "skills": skills_summary,
            "runtime_plugins": plugin_summary,
            "mcp_tools": mcp_tools,
        },
        "history_summary": history_summary,
        "recommendations": recommendations,
    }


def build_harness_prompt_guidance(
    project_root: Path,
    *,
    project_data_dir: Optional[Path] = None,
    mode: str = "reverie",
    agent: Any = None,
    indexer: Any = None,
    ensure_context_engine: Any = None,
    git_integration: Any = None,
    ensure_git_integration: Any = None,
    lsp_manager: Any = None,
    ensure_lsp_manager: Any = None,
    session_manager: Any = None,
    memory_indexer: Any = None,
    operation_history: Any = None,
    rollback_manager: Any = None,
    runtime_plugin_manager: Any = None,
    skills_manager: Any = None,
    mcp_runtime: Any = None,
) -> str:
    report = build_harness_capability_report(
        project_root,
        project_data_dir=project_data_dir,
        mode=mode,
        agent=agent,
        indexer=indexer,
        ensure_context_engine=ensure_context_engine,
        git_integration=git_integration,
        ensure_git_integration=ensure_git_integration,
        lsp_manager=lsp_manager,
        ensure_lsp_manager=ensure_lsp_manager,
        session_manager=session_manager,
        memory_indexer=memory_indexer,
        operation_history=operation_history,
        rollback_manager=rollback_manager,
        runtime_plugin_manager=runtime_plugin_manager,
        skills_manager=skills_manager,
        mcp_runtime=mcp_runtime,
    )

    summary = report.get("summary", {})
    runtime = report.get("runtime", {})
    task_snapshot = report.get("task_snapshot", {})
    completion_gate = report.get("completion_gate", {}) or {}
    recovery_playbooks = report.get("recovery_playbooks", []) or []
    audit = (report.get("artifacts", {}) or {}).get("command_audit", {})
    verification = (report.get("artifacts", {}) or {}).get("verification", {})
    git_workspace = (report.get("artifacts", {}) or {}).get("git_workspace", {})
    history_summary = report.get("history_summary", {}) or {}
    integrations = report.get("integrations", {})
    tool_surface = _limited_names(_resolve_tool_surface(agent, normalize_mode(mode or "reverie")).get("names", []), limit=8)

    lines = [
        "## Harness Runtime",
        "- Harness framing: prompt engineering clarifies the ask, context engineering supplies the right evidence, and harness engineering keeps the full execution loop stable.",
        f"- Active mode: `{report.get('mode', normalize_mode(mode or 'reverie'))}` with {summary.get('visible_tools', 0)} visible tools.",
    ]

    if tool_surface:
        lines.append(f"- Visible tool roster: {', '.join(tool_surface)}.")

    if task_snapshot.get("sample_lines"):
        active_text = str(task_snapshot.get("active", "") or "").strip() or "(none)"
        next_text = str(task_snapshot.get("next", "") or "").strip() or "(none)"
        lines.append(
            f"- Task ledger: {summary.get('task_total', 0)} tracked items, active `{active_text}`, next `{next_text}`."
        )
        lines.append("- Task snapshot:")
        for item in task_snapshot.get("sample_lines", [])[:4]:
            lines.append(f"  {item}")
    else:
        lines.append("- Task ledger: no active checklist yet. Use `task_manager` when work becomes multi-step, cross-file, or verification-heavy.")

    lines.append(
        f"- Verification trail: {audit.get('entries', 0)} audited command event(s), "
        f"{audit.get('successful_commands', 0)} successful command(s), "
        f"{audit.get('failed_commands', 0)} failed command(s)."
    )
    verification_categories = ", ".join((verification.get("categories", {}) or {}).keys())
    if verification.get("explicit_commands", 0):
        lines.append(
            f"- Verification posture: {verification.get('explicit_commands', 0)} explicit verification command(s)"
            f"{f' across {verification_categories}' if verification_categories else ''}."
        )
    else:
        lines.append("- Verification posture: no explicit test/build/lint/browser evidence is visible yet in the current audit window.")

    if history_summary.get("total_runs", 0):
        lines.append(
            f"- Recent harness runs: {history_summary.get('total_runs', 0)} stored, "
            f"{history_summary.get('recent_success_rate', 0)}% recent success, "
            f"{history_summary.get('recent_verification_coverage', 0)}% with explicit verification, "
            f"trend {history_summary.get('score_trend_label', 'n/a')}."
        )
    else:
        lines.append("- Recent harness runs: no prompt-mode history has been recorded yet for this workspace.")

    if git_workspace.get("available"):
        branch = str(git_workspace.get("branch", "") or "").strip() or "(detached)"
        lines.append(
            f"- Git workspace: branch `{branch}`, {git_workspace.get('dirty_files', 0)} dirty path(s)."
        )

    lines.append(
        f"- Closure gate: {completion_gate.get('label', 'No gate yet')} "
        f"(status `{completion_gate.get('status', 'unknown')}`, confidence {completion_gate.get('confidence', 0)}%)."
    )

    continuity_parts: List[str] = []
    if runtime.get("workspace_memory_available"):
        continuity_parts.append("workspace memory")
    if runtime.get("session_continuity_available"):
        continuity_parts.append("session continuity")
    if runtime.get("automatic_checkpoints"):
        continuity_parts.append("automatic checkpoints before user turns and tool calls")
    if runtime.get("rollback_available"):
        continuity_parts.append("rollback recovery")
    if runtime.get("git_workspace_available"):
        continuity_parts.append("git workspace state")
    if continuity_parts:
        lines.append(f"- Continuity and recovery: {', '.join(continuity_parts)} are available.")

    lines.append(
        f"- External capability surface: {integrations.get('mcp_tools', 0)} MCP tools, "
        f"{int((integrations.get('runtime_plugins', {}) or {}).get('tool_count', 0) or 0)} runtime-plugin tools, "
        f"{int((integrations.get('skills', {}) or {}).get('skill_count', 0) or 0)} skills."
    )
    lines.append("- Keep the loop explicit: understand -> gather missing context -> act -> verify -> update task state -> continue or recover.")
    lines.append("- If checks fail or tool results conflict with the plan, treat that as a recovery step rather than a finish state.")

    if recovery_playbooks:
        lines.append("- Recovery playbooks:")
        for item in recovery_playbooks[:2]:
            lines.append(
                f"  - {item.get('title', '')}: {item.get('why', '')}"
            )

    recommendations = report.get("recommendations", []) or []
    if recommendations:
        lines.append("- Harness nudges:")
        for item in recommendations[:3]:
            lines.append(f"  - {item}")

    return "\n".join(lines)


def build_prompt_harness_report(
    project_root: Path,
    *,
    project_data_dir: Optional[Path] = None,
    prompt_result: Any,
    operation_history: Any = None,
    rollback_manager: Any = None,
    agent: Any = None,
    indexer: Any = None,
    ensure_context_engine: Any = None,
    git_integration: Any = None,
    ensure_git_integration: Any = None,
    lsp_manager: Any = None,
    ensure_lsp_manager: Any = None,
    session_manager: Any = None,
    memory_indexer: Any = None,
    runtime_plugin_manager: Any = None,
    skills_manager: Any = None,
    mcp_runtime: Any = None,
) -> Dict[str, Any]:
    task_summary = _parse_task_entries(Path(project_root))
    operation_summary = summarize_operation_history(operation_history)
    checkpoint_summary = summarize_checkpoints(
        rollback_manager,
        session_id=str(getattr(prompt_result, "session_id", "") or ""),
    )
    command_summary = summarize_command_audit(
        Path(project_root),
        project_data_dir=project_data_dir,
        started_at=str(getattr(prompt_result, "started_at", "") or ""),
        ended_at=str(getattr(prompt_result, "ended_at", "") or ""),
    )
    activity_summary = summarize_activity_events(getattr(prompt_result, "activity_events", []) or [])
    ui_summary = summarize_ui_events(getattr(prompt_result, "ui_events", []) or [])

    workspace_audit = build_harness_capability_report(
        Path(project_root),
        project_data_dir=project_data_dir,
        mode=str(getattr(prompt_result, "mode", "reverie") or "reverie"),
        agent=agent,
        indexer=indexer,
        ensure_context_engine=ensure_context_engine,
        git_integration=git_integration,
        ensure_git_integration=ensure_git_integration,
        lsp_manager=lsp_manager,
        ensure_lsp_manager=ensure_lsp_manager,
        session_manager=session_manager,
        memory_indexer=memory_indexer,
        operation_history=operation_history,
        rollback_manager=rollback_manager,
        runtime_plugin_manager=runtime_plugin_manager,
        skills_manager=skills_manager,
        mcp_runtime=mcp_runtime,
    )

    return {
        "mode": str(getattr(prompt_result, "mode", "reverie") or "reverie"),
        "duration_seconds": float(getattr(prompt_result, "duration_seconds", 0.0) or 0.0),
        "auto_followup_count": int(getattr(prompt_result, "auto_followup_count", 0) or 0),
        "task_artifacts": task_summary,
        "operation_history": operation_summary,
        "command_window": command_summary,
        "verification": dict(command_summary.get("verification", {}) or {}),
        "checkpoints": checkpoint_summary,
        "activity": activity_summary,
        "ui_events": ui_summary,
        "workspace_audit": workspace_audit,
        "completion_gate": dict(workspace_audit.get("completion_gate", {}) or {}),
        "recovery_playbooks": list(workspace_audit.get("recovery_playbooks", []) or []),
    }
