"""Delegate bounded work to configured Reverie subagents."""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from .base import BaseTool, ToolResult


class SubagentTool(BaseTool):
    """Tool for the main Reverie agent to delegate work to configured subagents."""

    name = "subagent"
    aliases = ("delegate_to_subagent", "subagents")
    search_hint = "delegate independent development tasks to configured Reverie subagents"
    tool_category = "orchestration"
    tool_tags = ("delegate", "subagent", "parallel", "development")
    concurrency_safe = False
    description = """Delegate bounded development work to a configured Reverie Subagent.
Subagents are available only in base Reverie mode. Each configured Subagent uses
the same Reverie prompt/tool/plugin/skill surface as the main agent, but runs
with the model selected by the user and the task assigned by the main agent.
Use action=list first when you need available subagent IDs, then action=delegate
with a clear, self-contained task.
"""
    parameters = {
        "type": "object",
        "properties": {
            "action": {
                "type": "string",
                "enum": ["list", "delegate", "status"],
                "description": "Operation to perform.",
            },
            "subagent_id": {
                "type": "string",
                "description": "Configured subagent ID, for example subagent-001.",
            },
            "task": {
                "type": "string",
                "description": "Self-contained task assignment for the subagent.",
            },
            "expected_output": {
                "type": "string",
                "description": "Optional expected output or acceptance criteria.",
            },
            "read_scope": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Optional files or areas the subagent should inspect.",
            },
            "write_scope": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Optional files or areas the subagent may modify.",
            },
            "run_id": {
                "type": "string",
                "description": "Run ID for action=status.",
            },
        },
        "required": ["action"],
    }

    def get_execution_message(self, **kwargs) -> str:
        action = str(kwargs.get("action") or "delegate").strip().lower()
        subagent_id = str(kwargs.get("subagent_id") or "").strip()
        if action == "list":
            return "Listing configured Subagents"
        if action == "status":
            return "Checking Subagent run status"
        return f"Delegating task to {subagent_id or 'Subagent'}"

    def _manager(self):
        return self.context.get("subagent_manager")

    def _coerce_string_list(self, value: Any) -> Optional[List[str]]:
        if value is None:
            return None
        if not isinstance(value, list):
            return None
        return [str(item).strip() for item in value if str(item or "").strip()]

    def execute(self, **kwargs) -> ToolResult:
        if self.context.get("is_subagent"):
            return ToolResult.fail("Nested subagent delegation is disabled.")

        manager = self._manager()
        if manager is None:
            return ToolResult.fail("Subagent manager is not available in this runtime.")

        try:
            if not manager.is_available():
                return ToolResult.fail("Subagents are only available in base Reverie mode.")
        except Exception as exc:
            return ToolResult.fail(str(exc))

        action = str(kwargs.get("action") or "").strip().lower()
        if action == "list":
            specs = manager.list_specs()
            if not specs:
                return ToolResult.ok("No Subagents are configured. Use /subagent create in base Reverie mode.")
            lines = ["Configured Subagents:"]
            for spec in specs:
                ref = dict(spec.model_ref or {})
                source = str(ref.get("source") or "standard")
                display = str(ref.get("display_name") or ref.get("model") or "(unresolved)")
                state = "enabled" if spec.enabled else "disabled"
                lines.append(f"- {spec.id} [{state}] {display} ({source}) color={spec.color}")
            return ToolResult.ok("\n".join(lines), data={"subagents": [spec.to_dict() for spec in specs]})

        if action == "status":
            run_id = str(kwargs.get("run_id") or "").strip()
            if run_id:
                run = manager.get_run(run_id)
                if run is None:
                    return ToolResult.fail(f"Unknown Subagent run: {run_id}")
                return ToolResult.ok(run.summary or run.error or run.status, data={"run": run.to_dict()})
            runs = manager.list_recent_runs()
            if not runs:
                return ToolResult.ok("No Subagent runs have been recorded in this session.")
            lines = ["Recent Subagent runs:"]
            for run in runs[:8]:
                lines.append(f"- {run.run_id}: {run.status} ({run.subagent_id})")
            return ToolResult.ok("\n".join(lines), data={"runs": [run.to_dict() for run in runs[:8]]})

        if action != "delegate":
            return ToolResult.fail("Unsupported subagent action. Use list, delegate, or status.")

        subagent_id = str(kwargs.get("subagent_id") or "").strip()
        task = str(kwargs.get("task") or "").strip()
        if not subagent_id:
            return ToolResult.fail("subagent_id is required for delegation.")
        if not task:
            return ToolResult.fail("task is required for delegation.")

        try:
            run = manager.run_task(
                subagent_id,
                task,
                expected_output=str(kwargs.get("expected_output") or "").strip(),
                read_scope=self._coerce_string_list(kwargs.get("read_scope")),
                write_scope=self._coerce_string_list(kwargs.get("write_scope")),
                stream=False,
            )
        except Exception as exc:
            return ToolResult.fail(str(exc))

        if run.status == "completed":
            output = (
                f"Subagent {run.subagent_id} completed run {run.run_id}.\n"
                f"Log: {run.log_path}\n\n"
                f"{run.summary}".strip()
            )
            return ToolResult.ok(output, data={"run": run.to_dict()})

        return ToolResult.fail(
            f"Subagent {run.subagent_id} failed run {run.run_id}: {run.error or run.status}"
        )
