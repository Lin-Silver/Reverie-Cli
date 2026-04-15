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


def summarize_operation_history(operation_history: Any) -> Dict[str, Any]:
    operations = list(getattr(operation_history, "operations", []) or [])
    by_type = Counter()
    tools = Counter()
    for operation in operations:
        operation_type = getattr(getattr(operation, "operation_type", None), "value", "")
        if operation_type:
            by_type[str(operation_type)] += 1
        tool_call = getattr(operation, "tool_call", None)
        tool_name = str(getattr(tool_call, "tool_name", "") or "").strip()
        if tool_name:
            tools[tool_name] += 1

    return {
        "operations": len(operations),
        "by_type": dict(sorted(by_type.items())),
        "tool_calls": sum(tools.values()),
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
        },
        "categories": categories,
        "task_snapshot": task_snapshot,
        "runtime": runtime,
        "artifacts": {
            "tasks": task_summary,
            "command_audit": audit_summary,
            "verification": verification_summary,
            "operation_history": operation_summary,
            "checkpoints": checkpoint_summary,
            "sessions": sessions_summary,
            "prompt_runs": history_summary,
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
    audit = (report.get("artifacts", {}) or {}).get("command_audit", {})
    verification = (report.get("artifacts", {}) or {}).get("verification", {})
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

    continuity_parts: List[str] = []
    if runtime.get("workspace_memory_available"):
        continuity_parts.append("workspace memory")
    if runtime.get("session_continuity_available"):
        continuity_parts.append("session continuity")
    if runtime.get("automatic_checkpoints"):
        continuity_parts.append("automatic checkpoints before user turns and tool calls")
    if runtime.get("rollback_available"):
        continuity_parts.append("rollback recovery")
    if continuity_parts:
        lines.append(f"- Continuity and recovery: {', '.join(continuity_parts)} are available.")

    lines.append(
        f"- External capability surface: {integrations.get('mcp_tools', 0)} MCP tools, "
        f"{int((integrations.get('runtime_plugins', {}) or {}).get('tool_count', 0) or 0)} runtime-plugin tools, "
        f"{int((integrations.get('skills', {}) or {}).get('skill_count', 0) or 0)} skills."
    )
    lines.append("- Keep the loop explicit: understand -> gather missing context -> act -> verify -> update task state -> continue or recover.")
    lines.append("- If checks fail or tool results conflict with the plan, treat that as a recovery step rather than a finish state.")

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
    }
