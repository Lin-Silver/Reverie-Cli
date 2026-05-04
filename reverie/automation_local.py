"""Local file-backed automations for Reverie UI."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional
import json
import os
import re
import subprocess
import sys
import uuid

from .security_utils import write_json_secure


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _sanitize_id(value: Any) -> str:
    text = str(value or "").strip().lower()
    text = re.sub(r"[^a-z0-9_-]+", "-", text)
    text = re.sub(r"-+", "-", text).strip("-")
    return text or f"automation-{uuid.uuid4().hex[:12]}"


def _ps_single_quote(value: Any) -> str:
    return "'" + str(value or "").replace("'", "''") + "'"


@dataclass
class AutomationPaths:
    root: Path
    tasks_path: Path
    prompts_dir: Path
    runners_dir: Path
    logs_dir: Path
    reports_dir: Path


class LocalAutomationManager:
    """Manage local Reverie prompt automations and optional Windows schedules."""

    SCHEMA = "reverie.local_automations.v1"

    def __init__(self, app_root: Path, *, reverie_executable: Optional[Path] = None) -> None:
        self.app_root = Path(app_root).resolve()
        self.reverie_executable = Path(reverie_executable or sys.executable).resolve()
        self.use_python_module = self.reverie_executable.name.lower().startswith("python")
        root = self.app_root / ".reverie" / "automations"
        self.paths = AutomationPaths(
            root=root,
            tasks_path=root / "tasks.json",
            prompts_dir=root / "prompts",
            runners_dir=root / "runners",
            logs_dir=root / "logs",
            reports_dir=root / "reports",
        )
        self.ensure_dirs()

    def ensure_dirs(self) -> None:
        for path in (
            self.paths.root,
            self.paths.prompts_dir,
            self.paths.runners_dir,
            self.paths.logs_dir,
            self.paths.reports_dir,
        ):
            path.mkdir(parents=True, exist_ok=True)

    def _load_payload(self) -> Dict[str, Any]:
        if not self.paths.tasks_path.exists():
            return {"schema": self.SCHEMA, "automations": []}
        try:
            data = json.loads(self.paths.tasks_path.read_text(encoding="utf-8-sig"))
        except Exception:
            return {"schema": self.SCHEMA, "automations": []}
        if not isinstance(data, dict):
            return {"schema": self.SCHEMA, "automations": []}
        items = data.get("automations", [])
        if not isinstance(items, list):
            items = []
        return {"schema": self.SCHEMA, "automations": [item for item in items if isinstance(item, dict)]}

    def _save_payload(self, payload: Dict[str, Any]) -> None:
        self.ensure_dirs()
        normalized = {
            "schema": self.SCHEMA,
            "updated_at": _utc_now(),
            "automations": payload.get("automations", []) if isinstance(payload.get("automations"), list) else [],
        }
        write_json_secure(self.paths.tasks_path, normalized)

    def list_automations(self) -> Dict[str, Any]:
        payload = self._load_payload()
        items = []
        for item in payload.get("automations", []):
            normalized = self._normalize_record(item)
            normalized["runtime"] = self._runtime_summary(normalized)
            items.append(normalized)
        items.sort(key=lambda item: str(item.get("updated_at") or ""), reverse=True)
        return {
            "schema": self.SCHEMA,
            "root": self.paths.root,
            "scheduler": "windows-task-scheduler" if os.name == "nt" else "file-only",
            "reverie_executable": self.reverie_executable,
            "automations": items,
        }

    def get_automation(self, automation_id: str) -> Optional[Dict[str, Any]]:
        target = _sanitize_id(automation_id)
        for item in self._load_payload().get("automations", []):
            if _sanitize_id(item.get("id")) == target:
                return self._normalize_record(item)
        return None

    def save_automation(self, data: Dict[str, Any]) -> Dict[str, Any]:
        payload = self._load_payload()
        now = _utc_now()
        automation_id = _sanitize_id(data.get("id") or f"automation-{uuid.uuid4().hex[:12]}")
        existing = None
        for item in payload.get("automations", []):
            if _sanitize_id(item.get("id")) == automation_id:
                existing = item
                break

        record = self._normalize_record(existing or {})
        record.update(
            {
                "id": automation_id,
                "name": str(data.get("name") or record.get("name") or "Reverie automation").strip(),
                "prompt": str(data.get("prompt") or record.get("prompt") or "").strip(),
                "workspace": str(data.get("workspace") or record.get("workspace") or "").strip(),
                "enabled": bool(data.get("enabled", record.get("enabled", True))),
                "schedule": self._normalize_schedule(data.get("schedule") or record.get("schedule") or {}),
                "updated_at": now,
            }
        )
        if not record.get("created_at"):
            record["created_at"] = now

        if not record["prompt"]:
            return {"success": False, "error": "Automation prompt is required.", "automation": record}
        if not record["workspace"]:
            record["workspace"] = str(Path.cwd())

        replaced = False
        for index, item in enumerate(payload.get("automations", [])):
            if _sanitize_id(item.get("id")) == automation_id:
                payload["automations"][index] = record
                replaced = True
                break
        if not replaced:
            payload.setdefault("automations", []).append(record)

        self._write_runner(record)
        scheduler = self._sync_scheduler(record)
        record["scheduler_status"] = scheduler
        self._save_payload(payload)
        return {"success": bool(scheduler.get("success", True)), "error": scheduler.get("error", ""), "automation": record}

    def delete_automation(self, automation_id: str) -> Dict[str, Any]:
        target = _sanitize_id(automation_id)
        payload = self._load_payload()
        before = len(payload.get("automations", []))
        payload["automations"] = [item for item in payload.get("automations", []) if _sanitize_id(item.get("id")) != target]
        scheduler = self._delete_scheduled_task(target)
        for path in (
            self._prompt_path(target),
            self._runner_path(target),
            self._log_path(target),
            self._report_path(target),
        ):
            try:
                path.unlink(missing_ok=True)
            except Exception:
                pass
        self._save_payload(payload)
        return {"success": len(payload["automations"]) < before, "scheduler_status": scheduler}

    def toggle_automation(self, automation_id: str, enabled: bool) -> Dict[str, Any]:
        record = self.get_automation(automation_id)
        if record is None:
            return {"success": False, "error": "Automation not found."}
        record["enabled"] = bool(enabled)
        return self.save_automation(record)

    def run_automation(self, automation_id: str) -> Dict[str, Any]:
        record = self.get_automation(automation_id)
        if record is None:
            return {"success": False, "error": "Automation not found."}
        self._write_runner(record)
        runner = self._runner_path(record["id"])
        try:
            completed = subprocess.run(
                [
                    "powershell.exe" if os.name == "nt" else "pwsh",
                    "-NoProfile",
                    "-ExecutionPolicy",
                    "Bypass",
                    "-File",
                    str(runner),
                ],
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=60 * 60,
                check=False,
            )
            return {
                "success": completed.returncode == 0,
                "returncode": completed.returncode,
                "stdout": completed.stdout[-4000:],
                "stderr": completed.stderr[-4000:],
                "automation": self.get_automation(automation_id),
            }
        except Exception as exc:
            return {"success": False, "error": str(exc)}

    def _normalize_record(self, item: Dict[str, Any]) -> Dict[str, Any]:
        automation_id = _sanitize_id(item.get("id") or f"automation-{uuid.uuid4().hex[:12]}")
        return {
            "id": automation_id,
            "name": str(item.get("name") or "Reverie automation").strip(),
            "prompt": str(item.get("prompt") or "").strip(),
            "workspace": str(item.get("workspace") or "").strip(),
            "enabled": bool(item.get("enabled", True)),
            "schedule": self._normalize_schedule(item.get("schedule") or {}),
            "created_at": str(item.get("created_at") or ""),
            "updated_at": str(item.get("updated_at") or ""),
            "scheduler_status": item.get("scheduler_status") if isinstance(item.get("scheduler_status"), dict) else {},
        }

    def _normalize_schedule(self, schedule: Dict[str, Any]) -> Dict[str, Any]:
        if not isinstance(schedule, dict):
            schedule = {}
        try:
            interval = int(schedule.get("interval_minutes") or 60)
        except (TypeError, ValueError):
            interval = 60
        interval = max(1, min(interval, 10080))
        return {
            "type": "interval",
            "interval_minutes": interval,
        }

    def _runtime_summary(self, record: Dict[str, Any]) -> Dict[str, Any]:
        log_path = self._log_path(record["id"])
        report_path = self._report_path(record["id"])
        summary: Dict[str, Any] = {
            "task_name": self._task_name(record["id"]),
            "runner_path": self._runner_path(record["id"]),
            "prompt_path": self._prompt_path(record["id"]),
            "log_path": log_path,
            "report_path": report_path,
            "last_log": "",
            "last_run_at": "",
        }
        if log_path.exists():
            try:
                summary["last_log"] = log_path.read_text(encoding="utf-8", errors="replace")[-4000:]
                summary["last_run_at"] = datetime.fromtimestamp(log_path.stat().st_mtime).isoformat()
            except Exception:
                pass
        if report_path.exists():
            summary["has_report"] = True
        return summary

    def _prompt_path(self, automation_id: str) -> Path:
        return self.paths.prompts_dir / f"{_sanitize_id(automation_id)}.md"

    def _runner_path(self, automation_id: str) -> Path:
        return self.paths.runners_dir / f"{_sanitize_id(automation_id)}.ps1"

    def _log_path(self, automation_id: str) -> Path:
        return self.paths.logs_dir / f"{_sanitize_id(automation_id)}.log"

    def _report_path(self, automation_id: str) -> Path:
        return self.paths.reports_dir / f"{_sanitize_id(automation_id)}.json"

    def _task_name(self, automation_id: str) -> str:
        return rf"\Reverie UI\{_sanitize_id(automation_id)}"

    def _write_runner(self, record: Dict[str, Any]) -> None:
        automation_id = _sanitize_id(record["id"])
        prompt_path = self._prompt_path(automation_id)
        runner_path = self._runner_path(automation_id)
        log_path = self._log_path(automation_id)
        report_path = self._report_path(automation_id)
        workspace = Path(str(record.get("workspace") or Path.cwd())).expanduser()
        prompt_path.write_text(str(record.get("prompt") or ""), encoding="utf-8")
        script = "\n".join(
            [
                "$ErrorActionPreference = 'Continue'",
                f"Set-Location -LiteralPath {_ps_single_quote(workspace)}",
                f"$reverie = {_ps_single_quote(self.reverie_executable)}",
                f"$workspace = {_ps_single_quote(workspace)}",
                f"$prompt = {_ps_single_quote(prompt_path)}",
                f"$report = {_ps_single_quote(report_path)}",
                f"$log = {_ps_single_quote(log_path)}",
                "New-Item -ItemType Directory -Force -Path (Split-Path -Parent $log) | Out-Null",
                "& $reverie " + ("-m reverie " if self.use_python_module else "") + "$workspace --prompt-file $prompt --report-file $report *> $log",
                "exit $LASTEXITCODE",
                "",
            ]
        )
        runner_path.write_text(script, encoding="utf-8")

    def _sync_scheduler(self, record: Dict[str, Any]) -> Dict[str, Any]:
        if os.name != "nt":
            return {"success": True, "kind": "file-only", "message": "Scheduler integration is only enabled on Windows."}
        automation_id = _sanitize_id(record["id"])
        if not record.get("enabled", True):
            return self._delete_scheduled_task(automation_id)
        schedule = self._normalize_schedule(record.get("schedule") or {})
        runner = self._runner_path(automation_id)
        task_name = self._task_name(automation_id)
        command = f'powershell.exe -NoProfile -ExecutionPolicy Bypass -File "{runner}"'
        try:
            completed = subprocess.run(
                [
                    "schtasks.exe",
                    "/Create",
                    "/F",
                    "/TN",
                    task_name,
                    "/SC",
                    "MINUTE",
                    "/MO",
                    str(schedule["interval_minutes"]),
                    "/TR",
                    command,
                ],
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=20,
                check=False,
            )
            return {
                "success": completed.returncode == 0,
                "kind": "windows-task-scheduler",
                "task_name": task_name,
                "stdout": completed.stdout.strip(),
                "stderr": completed.stderr.strip(),
                "error": "" if completed.returncode == 0 else (completed.stderr or completed.stdout).strip(),
            }
        except Exception as exc:
            return {"success": False, "kind": "windows-task-scheduler", "task_name": task_name, "error": str(exc)}

    def _delete_scheduled_task(self, automation_id: str) -> Dict[str, Any]:
        if os.name != "nt":
            return {"success": True, "kind": "file-only"}
        task_name = self._task_name(automation_id)
        try:
            completed = subprocess.run(
                ["schtasks.exe", "/Delete", "/F", "/TN", task_name],
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=20,
                check=False,
            )
            ok = completed.returncode == 0 or "cannot find" in (completed.stderr + completed.stdout).lower()
            return {
                "success": ok,
                "kind": "windows-task-scheduler",
                "task_name": task_name,
                "stdout": completed.stdout.strip(),
                "stderr": completed.stderr.strip(),
                "error": "" if ok else (completed.stderr or completed.stdout).strip(),
            }
        except Exception as exc:
            return {"success": False, "kind": "windows-task-scheduler", "task_name": task_name, "error": str(exc)}
