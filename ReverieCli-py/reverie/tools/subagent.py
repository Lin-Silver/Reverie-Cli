"""Delegate bounded Context Engine work to configured Reverie subagents."""

from __future__ import annotations

from typing import Any, Dict, List, Optional
import json

from .base import BaseTool, ToolResult


class SubagentTool(BaseTool):
    """Tool for the main Reverie agent to delegate bounded context work."""

    name = "subagent"
    aliases = ("delegate_to_subagent", "subagents")
    search_hint = "delegate read-only context engine investigation or validation work to scoped subagents"
    tool_category = "orchestration"
    tool_tags = ("delegate", "subagent", "parallel", "context", "validation")
    concurrency_safe = False
    description = """Delegate bounded Context Engine investigation or validation work to a configured Reverie Subagent.
Subagents are available in Reverie and computer-controller modes. Each configured Subagent uses
the same Reverie prompt/tool/plugin/skill surface as the main agent, but runs
with the model selected by the user and the task assigned by the main agent.
Subagents are read-only by default. They should locate files, inspect symbols,
validate assumptions, and return evidence for the main agent. Provide write_scope
only for rare bounded edits; otherwise subagent write tools are blocked.
Use action=list first when you need available subagent IDs. Use delegate for a
synchronous result or start/status/wait/cancel for background work. Each Subagent
also has isolated persistent context managed with remember/context/forget/clear_context.
"""
    parameters = {
        "type": "object",
        "properties": {
            "action": {
                "type": "string",
                "enum": [
                    "list",
                    "create",
                    "delete",
                    "set_model",
                    "delegate",
                    "start",
                    "status",
                    "cancel",
                    "wait",
                    "remember",
                    "context",
                    "forget",
                    "clear_context",
                ],
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
                "description": "Optional files or areas the subagent may modify. Omit for read-only context/validation workers.",
            },
            "mode": {
                "type": "string",
                "enum": ["reverie", "reverie-gamer", "reverie-atlas", "reverie-ant", "spec-driven", "spec-vibe", "writer"],
                "description": "Workflow mode for a newly created SubAgent. Defaults to reverie.",
            },
            "model_ref": {
                "type": "object",
                "description": "Model reference from list/available configuration. Omit on create to use the first configured model.",
            },
            "worker_role": {
                "type": "string",
                "enum": ["context_expert", "validator"],
                "description": "Whether this subagent should retrieve context or verify a bounded claim.",
                "default": "context_expert",
            },
            "run_id": {
                "type": "string",
                "description": "Run ID for status, cancel, or wait.",
            },
            "context_key": {
                "type": "string",
                "description": "Persistent context key for remember or forget.",
            },
            "context_value": {
                "description": "JSON-serializable value to remember.",
            },
            "context_keys": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Persistent context keys to inspect or inject into delegate/start.",
            },
            "retain_summary": {
                "type": "boolean",
                "description": "Store a completed run summary as last_summary in this Subagent's context.",
                "default": False,
            },
            "timeout": {
                "type": "number",
                "minimum": 0,
                "description": "Maximum seconds to wait for action=wait.",
            },
        },
        "required": ["action"],
    }

    def get_execution_message(self, **kwargs) -> str:
        action = str(kwargs.get("action") or "delegate").strip().lower()
        subagent_id = str(kwargs.get("subagent_id") or "").strip()
        if action == "list":
            return "Listing configured Subagents"
        if action in {"create", "delete", "set_model"}:
            return f"{action.replace('_', ' ').title()} SubAgent {subagent_id}".strip()
        if action == "status":
            return "Checking Subagent run status"
        if action == "start":
            return f"Starting background task for {subagent_id or 'Subagent'}"
        if action in {"cancel", "wait"}:
            return f"{action.title()}ing Subagent run"
        if action in {"remember", "context", "forget", "clear_context"}:
            return f"Managing context for {subagent_id or 'Subagent'}"
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
                return ToolResult.fail("Subagents are only available in Reverie and computer-controller modes.")
        except Exception as exc:
            return ToolResult.fail(str(exc))

        action = str(kwargs.get("action") or "").strip().lower()
        if action == "list":
            specs = manager.list_specs()
            if not specs:
                return ToolResult.ok("No Subagents are configured. Use subagent(action=\"create\") or /subagent create.")
            lines = ["Configured Subagents:"]
            for spec in specs:
                ref = dict(spec.model_ref or {})
                source = str(ref.get("source") or "standard")
                display = str(ref.get("display_name") or ref.get("model") or "(unresolved)")
                state = "enabled" if spec.enabled else "disabled"
                lines.append(f"- {spec.id} [{state}] {display} ({source}) mode={spec.mode} color={spec.color}")
            return ToolResult.ok("\n".join(lines), data={"subagents": [spec.to_dict() for spec in specs]})

        subagent_id = str(kwargs.get("subagent_id") or "").strip()
        if action in {"create", "delete", "set_model"}:
            try:
                if action == "delete":
                    if not subagent_id:
                        return ToolResult.fail("subagent_id is required for delete.")
                    deleted = manager.delete_subagent(subagent_id)
                    if not deleted:
                        return ToolResult.fail(f"Unknown Subagent: {subagent_id}")
                    return ToolResult.ok(f"Deleted Subagent {subagent_id}.")

                model_ref = kwargs.get("model_ref")
                if not isinstance(model_ref, dict) or not model_ref:
                    choices = manager.available_model_refs()
                    if not choices:
                        return ToolResult.fail("No configured model is available for a Subagent.")
                    model_ref = dict(choices[0].get("model_ref") or {})
                if action == "set_model":
                    if not subagent_id:
                        return ToolResult.fail("subagent_id is required for set_model.")
                    updated = manager.set_model(subagent_id, model_ref)
                    if updated is None:
                        return ToolResult.fail(f"Unknown Subagent: {subagent_id}")
                    return ToolResult.ok(
                        f"Updated model for Subagent {subagent_id}.",
                        data={"subagent": updated.to_dict()},
                    )

                created = manager.create_subagent(
                    model_ref,
                    subagent_id=subagent_id,
                    mode=str(kwargs.get("mode") or "reverie"),
                )
                return ToolResult.ok(
                    f"Created {created.mode} Subagent {created.id}.",
                    data={"subagent": created.to_dict()},
                )
            except Exception as exc:
                return ToolResult.fail(str(exc))

        if action in {"remember", "context", "forget", "clear_context"}:
            if not subagent_id:
                return ToolResult.fail("subagent_id is required for context actions.")
            if manager.get_spec(subagent_id) is None:
                return ToolResult.fail(f"Unknown subagent: {subagent_id}")
            try:
                if action == "remember":
                    context_key = str(kwargs.get("context_key") or "").strip()
                    if not context_key:
                        return ToolResult.fail("context_key is required for remember.")
                    if "context_value" not in kwargs:
                        return ToolResult.fail("context_value is required for remember.")
                    context = manager.remember_context(subagent_id, context_key, kwargs.get("context_value"))
                    return ToolResult.ok(
                        f"Remembered context key {context_key} for {subagent_id}.",
                        data={"context": context},
                    )
                if action == "context":
                    context = manager.load_context(subagent_id)
                    context_keys = self._coerce_string_list(kwargs.get("context_keys"))
                    if context_keys:
                        context = {key: context[key] for key in context_keys if key in context}
                    return ToolResult.ok(
                        json.dumps(context, indent=2, ensure_ascii=False),
                        data={"context": context},
                    )
                if action == "forget":
                    context_key = str(kwargs.get("context_key") or "").strip()
                    removed = manager.forget_context(subagent_id, context_key)
                    return ToolResult.ok(
                        f"{'Forgot' if removed else 'Did not find'} context key {context_key} for {subagent_id}."
                    )
                manager.clear_context(subagent_id)
                return ToolResult.ok(f"Cleared persistent context for {subagent_id}.", data={"context": {}})
            except Exception as exc:
                return ToolResult.fail(str(exc))

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

        if action in {"cancel", "wait"}:
            run_id = str(kwargs.get("run_id") or "").strip()
            if not run_id:
                return ToolResult.fail(f"run_id is required for {action}.")
            if action == "cancel":
                run = manager.cancel_task(run_id)
            else:
                try:
                    timeout = kwargs.get("timeout")
                    run = manager.wait_task(run_id, timeout=float(timeout) if timeout is not None else None)
                except (TypeError, ValueError) as exc:
                    return ToolResult.fail(f"Invalid wait timeout: {exc}")
            if run is None:
                return ToolResult.fail(f"Unknown Subagent run: {run_id}")
            return ToolResult.ok(run.summary or run.error or run.status, data={"run": run.to_dict()})

        if action not in {"delegate", "start"}:
            return ToolResult.fail(
                "Unsupported subagent action. Use lifecycle, configuration, delegation, or context actions."
            )

        task = str(kwargs.get("task") or "").strip()
        if not subagent_id:
            return ToolResult.fail("subagent_id is required for delegation.")
        if not task:
            return ToolResult.fail("task is required for delegation.")

        try:
            runner = manager.start_task if action == "start" else manager.run_task
            run = runner(
                subagent_id,
                task,
                expected_output=str(kwargs.get("expected_output") or "").strip(),
                read_scope=self._coerce_string_list(kwargs.get("read_scope")),
                write_scope=self._coerce_string_list(kwargs.get("write_scope")),
                worker_role=str(kwargs.get("worker_role") or "context_expert").strip(),
                stream=False,
                context_keys=self._coerce_string_list(kwargs.get("context_keys")),
                retain_summary=bool(kwargs.get("retain_summary", False)),
            )
        except Exception as exc:
            return ToolResult.fail(str(exc))

        if action == "start":
            return ToolResult.ok(
                f"Started Subagent {run.subagent_id} run {run.run_id} in the background.",
                data={"run": run.to_dict()},
            )

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
