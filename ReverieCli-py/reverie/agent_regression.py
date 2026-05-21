"""Deterministic end-to-end agent behavior regression checks."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import json
from pathlib import Path
import shutil
import time
from typing import Any, Callable, Dict, List, Optional

from .agent.tool_executor import ToolExecutor
from .lifecycle import LifecycleManager


REGRESSION_SCHEMA_VERSION = "reverie.agent.regression.v1"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass
class AgentRegressionResult:
    id: str
    title: str
    passed: bool
    duration_ms: int
    detail: str

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "title": self.title,
            "passed": self.passed,
            "duration_ms": self.duration_ms,
            "detail": self.detail,
        }


class AgentRegressionHarness:
    """Run stable tool-level behavior scenarios without external model calls."""

    def __init__(self, project_data_dir: Path, project_root: Optional[Path] = None):
        self.project_data_dir = Path(project_data_dir)
        self.project_root = Path(project_root).resolve() if project_root else None
        self.root = self.project_data_dir / "agent_regression"
        self.workspace = self.root / "workspace"
        self.results_path = self.root / "results.jsonl"
        self.summary_path = self.root / "summary.json"

    def run(self) -> Dict[str, Any]:
        self._reset_workspace()
        lifecycle = LifecycleManager(self.project_data_dir, project_root=self.workspace)
        executor = ToolExecutor(project_root=self.workspace)
        executor.update_context("project_data_dir", self.project_data_dir)
        executor.update_context("lifecycle_manager", lifecycle)

        scenarios: List[tuple[str, str, Callable[[ToolExecutor], str]]] = [
            ("workspace-read-roundtrip", "Read seeded workspace file through file_ops", self._scenario_read_file),
            ("workspace-mkdir-visible", "Create a directory and observe it through file_ops", self._scenario_mkdir),
            ("lifecycle-denies-terminal-delete", "Deny terminal deletion before command execution", self._scenario_deny_delete),
            ("tool-schema-core-surface", "Expose core tool schemas in reverie mode", self._scenario_tool_schema),
        ]

        results: List[AgentRegressionResult] = []
        for scenario_id, title, runner in scenarios:
            started = time.perf_counter()
            try:
                detail = runner(executor)
                passed = True
            except AssertionError as exc:
                detail = str(exc)
                passed = False
            except Exception as exc:
                detail = f"{type(exc).__name__}: {exc}"
                passed = False
            duration_ms = int((time.perf_counter() - started) * 1000)
            results.append(AgentRegressionResult(scenario_id, title, passed, duration_ms, detail))

        summary = self._build_summary(results)
        self._write_results(summary)
        lifecycle.emit(
            lifecycle_event(
                phase="regression_complete",
                success=summary["passed"],
                result={
                    "passed": summary["passed"],
                    "passed_count": summary["passed_count"],
                    "total": summary["total"],
                    "score": summary["score"],
                },
            )
        )
        return summary

    def latest_summary(self) -> Dict[str, Any]:
        if not self.summary_path.exists():
            return {
                "schema": REGRESSION_SCHEMA_VERSION,
                "generated_at": "",
                "passed": None,
                "passed_count": 0,
                "failed_count": 0,
                "total": 0,
                "score": 0,
                "results": [],
                "summary_path": str(self.summary_path),
            }
        try:
            payload = json.loads(self.summary_path.read_text(encoding="utf-8"))
        except Exception:
            return {
                "schema": REGRESSION_SCHEMA_VERSION,
                "generated_at": "",
                "passed": None,
                "passed_count": 0,
                "failed_count": 0,
                "total": 0,
                "score": 0,
                "results": [],
                "summary_path": str(self.summary_path),
            }
        if isinstance(payload, dict):
            payload.setdefault("summary_path", str(self.summary_path))
            return payload
        return {}

    def _reset_workspace(self) -> None:
        if self.workspace.exists():
            shutil.rmtree(self.workspace)
        self.workspace.mkdir(parents=True, exist_ok=True)
        (self.workspace / "README.md").write_text("# Regression Workspace\n\nstable-sentinel\n", encoding="utf-8")

    def _scenario_read_file(self, executor: ToolExecutor) -> str:
        result = executor.execute("file_ops", {"operation": "read", "path": "README.md"}, tool_call_id="reg-read")
        assert result.success, result.error or result.output
        assert "stable-sentinel" in result.output
        return "Seed file was read and content matched."

    def _scenario_mkdir(self, executor: ToolExecutor) -> str:
        result = executor.execute("file_ops", {"operation": "mkdir", "path": "artifacts"}, tool_call_id="reg-mkdir")
        assert result.success, result.error or result.output
        check = executor.execute("file_ops", {"operation": "exists", "path": "artifacts"}, tool_call_id="reg-exists")
        assert check.success, check.error or check.output
        assert bool((check.data or {}).get("exists")) is True
        return "Directory creation remained workspace-confined."

    def _scenario_deny_delete(self, executor: ToolExecutor) -> str:
        result = executor.execute(
            "command_exec",
            {"command": "Remove-Item -Recurse artifacts"},
            tool_call_id="reg-deny-delete",
        )
        assert not result.success, "Terminal deletion unexpectedly succeeded."
        assert "Lifecycle hook denied" in (result.error or "")
        assert (self.workspace / "artifacts").exists()
        return "Lifecycle pre-tool hook denied a destructive terminal command."

    def _scenario_tool_schema(self, executor: ToolExecutor) -> str:
        names = {schema.get("function", {}).get("name") for schema in executor.get_tool_schemas(mode="reverie")}
        required = {"file_ops", "command_exec", "str_replace_editor"}
        missing = sorted(required - names)
        assert not missing, f"Missing core tool schemas: {', '.join(missing)}"
        return "Core tool schemas are visible in reverie mode."

    def _build_summary(self, results: List[AgentRegressionResult]) -> Dict[str, Any]:
        passed_count = sum(1 for result in results if result.passed)
        total = len(results)
        score = int(round((passed_count / total) * 100)) if total else 0
        return {
            "schema": REGRESSION_SCHEMA_VERSION,
            "generated_at": _now(),
            "workspace_root": str(self.project_root or ""),
            "sandbox_workspace": str(self.workspace),
            "passed": passed_count == total,
            "passed_count": passed_count,
            "failed_count": total - passed_count,
            "total": total,
            "score": score,
            "results": [result.to_dict() for result in results],
            "summary_path": str(self.summary_path),
            "results_path": str(self.results_path),
        }

    def _write_results(self, summary: Dict[str, Any]) -> None:
        self.root.mkdir(parents=True, exist_ok=True)
        self.summary_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
        with self.results_path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(summary, ensure_ascii=False, sort_keys=True) + "\n")


def lifecycle_event(phase: str, success: Optional[bool] = None, result: Optional[Dict[str, Any]] = None):
    from .lifecycle import LifecycleEvent

    return LifecycleEvent(
        phase=phase,
        tool="agent_regression",
        action="audit",
        allowed=True,
        success=success,
        result=result or {},
    )


def run_agent_regression(project_data_dir: Path, project_root: Optional[Path] = None) -> Dict[str, Any]:
    return AgentRegressionHarness(project_data_dir, project_root=project_root).run()


def latest_agent_regression_summary(project_data_dir: Path, project_root: Optional[Path] = None) -> Dict[str, Any]:
    return AgentRegressionHarness(project_data_dir, project_root=project_root).latest_summary()
