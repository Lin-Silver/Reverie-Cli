"""Subagent orchestration for base Reverie mode."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional
import json
import re
import uuid

from ..config import (
    EXTERNAL_MODEL_SOURCES,
    Config,
    ModelConfig,
    _subagent_color_for_id,
    normalize_subagent_config,
)
from ..modes import normalize_mode
from .agent import ReverieAgent


def _utc_timestamp() -> str:
    return datetime.utcnow().replace(microsecond=0).isoformat() + "Z"


def _safe_subagent_id(value: str) -> str:
    candidate = re.sub(r"[^A-Za-z0-9._-]+", "-", str(value or "").strip()).strip("-._")
    return candidate or "subagent"


@dataclass(frozen=True)
class SubagentSpec:
    """Persisted subagent configuration."""

    id: str
    name: str
    model_ref: Dict[str, Any]
    color: str
    enabled: bool = True
    created_at: str = ""
    updated_at: str = ""

    @classmethod
    def from_dict(cls, raw: Dict[str, Any]) -> "SubagentSpec":
        normalized = normalize_subagent_config({"agents": [raw]}).get("agents", [])
        data = normalized[0] if normalized else {}
        return cls(
            id=str(data.get("id") or ""),
            name=str(data.get("name") or data.get("id") or ""),
            model_ref=dict(data.get("model_ref") or {}),
            color=str(data.get("color") or ""),
            enabled=bool(data.get("enabled", True)),
            created_at=str(data.get("created_at") or ""),
            updated_at=str(data.get("updated_at") or ""),
        )

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name or self.id,
            "enabled": self.enabled,
            "color": self.color or _subagent_color_for_id(self.id),
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "model_ref": dict(self.model_ref or {}),
        }


@dataclass
class SubagentRun:
    """Runtime record for one delegated subagent assignment."""

    run_id: str
    subagent_id: str
    task_id: str
    status: str
    started_at: str
    ended_at: str = ""
    summary: str = ""
    error: str = ""
    log_path: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "run_id": self.run_id,
            "subagent_id": self.subagent_id,
            "task_id": self.task_id,
            "status": self.status,
            "started_at": self.started_at,
            "ended_at": self.ended_at,
            "summary": self.summary,
            "error": self.error,
            "log_path": self.log_path,
        }


class SubagentManager:
    """Create and execute model-scoped Subagents for base Reverie mode."""

    def __init__(self, interface: Any):
        self.interface = interface
        self._runs: Dict[str, SubagentRun] = {}

    def _load_config(self) -> Config:
        loader = getattr(self.interface, "_load_active_runtime_config", None)
        if callable(loader):
            return loader()
        config_manager = getattr(self.interface, "config_manager", None)
        if config_manager is not None and hasattr(config_manager, "load"):
            return config_manager.load()
        return Config()

    def _save_config(self, config: Config) -> None:
        config_manager = getattr(self.interface, "config_manager", None)
        if config_manager is not None and hasattr(config_manager, "save"):
            config_manager.save(config)

    def is_available(self, config: Optional[Config] = None) -> bool:
        active_config = config or self._load_config()
        return normalize_mode(getattr(active_config, "mode", "reverie")) == "reverie"

    def ensure_available(self, config: Optional[Config] = None) -> None:
        if not self.is_available(config):
            raise RuntimeError("Subagents are only available in base Reverie mode.")

    def list_specs(self, config: Optional[Config] = None) -> List[SubagentSpec]:
        active_config = config or self._load_config()
        section = normalize_subagent_config(getattr(active_config, "subagents", {}))
        return [SubagentSpec.from_dict(item) for item in section.get("agents", [])]

    def get_spec(self, subagent_id: str, config: Optional[Config] = None) -> Optional[SubagentSpec]:
        wanted = str(subagent_id or "").strip()
        if not wanted:
            return None
        for spec in self.list_specs(config):
            if spec.id == wanted:
                return spec
        return None

    def available_model_refs(self, config: Optional[Config] = None) -> List[Dict[str, Any]]:
        active_config = config or self._load_config()
        choices: List[Dict[str, Any]] = []

        for index, model in enumerate(getattr(active_config, "models", []) or []):
            if not isinstance(model, ModelConfig):
                continue
            model_ref = {
                "source": "standard",
                "index": index,
                "model": model.model,
                "display_name": model.model_display_name or model.model,
            }
            choices.append(
                {
                    "id": f"standard:{index}",
                    "name": model_ref["display_name"],
                    "description": f"Standard model #{index}: {model.model}",
                    "model": {
                        "id": model.model,
                        "context_length": model.max_context_tokens or "",
                        "visibility": "standard",
                    },
                    "model_ref": model_ref,
                }
            )

        for source in EXTERNAL_MODEL_SOURCES:
            probe = Config.from_dict(active_config.to_dict())
            probe.mode = "reverie"
            probe.active_model_source = source
            model = probe.active_model
            if not model:
                continue
            model_ref = {
                "source": source,
                "index": 0,
                "model": model.model,
                "display_name": model.model_display_name or model.model,
            }
            choices.append(
                {
                    "id": f"{source}:active",
                    "name": f"{model_ref['display_name']} ({source})",
                    "description": f"Configured {source} runtime model: {model.model}",
                    "model": {
                        "id": model.model,
                        "context_length": model.max_context_tokens or "",
                        "visibility": source,
                    },
                    "model_ref": model_ref,
                }
            )

        return choices

    def resolve_model(self, spec: SubagentSpec, config: Optional[Config] = None) -> Optional[ModelConfig]:
        active_config = config or self._load_config()
        model_ref = dict(spec.model_ref or {})
        source = str(model_ref.get("source", "standard") or "standard").strip().lower()

        if source == "standard":
            models = list(getattr(active_config, "models", []) or [])
            try:
                index = int(model_ref.get("index", -1))
            except (TypeError, ValueError):
                index = -1
            if 0 <= index < len(models):
                return ModelConfig.from_dict(models[index].to_dict())

            wanted_model = str(model_ref.get("model") or "").strip()
            wanted_display = str(model_ref.get("display_name") or "").strip()
            for model in models:
                if model.model == wanted_model or model.model_display_name == wanted_display:
                    return ModelConfig.from_dict(model.to_dict())
            return None

        if source in EXTERNAL_MODEL_SOURCES:
            probe = Config.from_dict(active_config.to_dict())
            probe.mode = "reverie"
            probe.active_model_source = source
            model = probe.active_model
            return ModelConfig.from_dict(model.to_dict()) if model else None

        return None

    def _next_subagent_id(self, config: Config) -> str:
        existing = {spec.id for spec in self.list_specs(config)}
        index = 1
        while True:
            candidate = f"subagent-{index:03d}"
            if candidate not in existing:
                return candidate
            index += 1

    def create_subagent(self, model_ref: Dict[str, Any], *, subagent_id: str = "") -> SubagentSpec:
        config = self._load_config()
        self.ensure_available(config)
        section = normalize_subagent_config(getattr(config, "subagents", {}))
        new_id = _safe_subagent_id(subagent_id) if subagent_id else self._next_subagent_id(config)
        if any(str(item.get("id") or "") == new_id for item in section.get("agents", [])):
            raise ValueError(f"Subagent already exists: {new_id}")

        now = _utc_timestamp()
        spec = SubagentSpec.from_dict(
            {
                "id": new_id,
                "name": new_id,
                "enabled": True,
                "color": _subagent_color_for_id(new_id),
                "created_at": now,
                "updated_at": now,
                "model_ref": dict(model_ref or {}),
            }
        )
        section["agents"].append(spec.to_dict())
        config.subagents = normalize_subagent_config(section)
        self._save_config(config)
        return spec

    def delete_subagent(self, subagent_id: str) -> bool:
        config = self._load_config()
        self.ensure_available(config)
        section = normalize_subagent_config(getattr(config, "subagents", {}))
        before = len(section.get("agents", []))
        section["agents"] = [
            item
            for item in section.get("agents", [])
            if str(item.get("id") or "").strip() != str(subagent_id or "").strip()
        ]
        if len(section["agents"]) == before:
            return False
        config.subagents = normalize_subagent_config(section)
        self._save_config(config)
        return True

    def set_model(self, subagent_id: str, model_ref: Dict[str, Any]) -> Optional[SubagentSpec]:
        config = self._load_config()
        self.ensure_available(config)
        section = normalize_subagent_config(getattr(config, "subagents", {}))
        now = _utc_timestamp()
        updated: Optional[SubagentSpec] = None
        for item in section.get("agents", []):
            if str(item.get("id") or "").strip() != str(subagent_id or "").strip():
                continue
            item["model_ref"] = dict(model_ref or {})
            item["updated_at"] = now
            updated = SubagentSpec.from_dict(item)
            break
        if updated is None:
            return None
        config.subagents = normalize_subagent_config(section)
        self._save_config(config)
        return updated

    def _runs_dir(self, subagent_id: str) -> Path:
        project_data_dir = getattr(self.interface, "project_data_dir", None)
        if project_data_dir is None:
            project_data_dir = Path.cwd() / ".reverie"
        return Path(project_data_dir) / "subagents" / _safe_subagent_id(subagent_id) / "runs"

    def _build_assignment_prompt(
        self,
        *,
        spec: SubagentSpec,
        assignment: str,
        expected_output: str = "",
        read_scope: Optional[List[str]] = None,
        write_scope: Optional[List[str]] = None,
    ) -> str:
        lines = [
            "You are a Reverie Subagent created by the main agent.",
            f"Subagent ID: {spec.id}",
            "You share the current Reverie system prompt, tools, plugins, skills, MCP surface, and workspace context.",
            "Your goal is only the task assigned by the main agent. Do not ask the user for confirmation unless the assignment is blocked.",
            "When you use tools, operate only inside the active workspace and return a concise result for the main agent.",
            "",
            "## Assignment",
            str(assignment or "").strip(),
        ]
        if expected_output:
            lines.extend(["", "## Expected Output", str(expected_output).strip()])
        if read_scope:
            lines.extend(["", "## Read Scope", "\n".join(f"- {item}" for item in read_scope)])
        if write_scope:
            lines.extend(["", "## Write Scope", "\n".join(f"- {item}" for item in write_scope)])
        lines.extend(["", "Finish with a short summary and include any files changed."])
        return "\n".join(lines).strip()

    def _shared_context_from_interface(self) -> Dict[str, Any]:
        parent_agent = getattr(self.interface, "agent", None)
        if parent_agent is not None and getattr(parent_agent, "tool_executor", None) is not None:
            return dict(getattr(parent_agent.tool_executor, "context", {}) or {})

        context: Dict[str, Any] = {
            "config_manager": getattr(self.interface, "config_manager", None),
            "mcp_config_manager": getattr(self.interface, "mcp_config_manager", None),
            "mcp_runtime": getattr(self.interface, "mcp_runtime", None),
            "runtime_plugin_manager": getattr(self.interface, "runtime_plugin_manager", None),
            "skills_manager": getattr(self.interface, "skills_manager", None),
            "session_manager": getattr(self.interface, "session_manager", None),
            "project_data_dir": getattr(self.interface, "project_data_dir", None),
            "memory_indexer": getattr(self.interface, "memory_indexer", None),
            "workspace_stats_manager": getattr(self.interface, "workspace_stats_manager", None),
            "lsp_manager": getattr(self.interface, "lsp_manager", None),
            "git_integration": getattr(self.interface, "git_integration", None),
            "console": getattr(self.interface, "console", None),
            "ui_event_handler": getattr(self.interface, "_handle_agent_ui_event", None),
        }
        return {key: value for key, value in context.items() if value is not None}

    def _build_child_agent(self, spec: SubagentSpec, model: ModelConfig, config: Config) -> ReverieAgent:
        rules_builder = getattr(self.interface, "_build_additional_rules_with_tti", None)
        additional_rules = rules_builder(config) if callable(rules_builder) else ""
        child = ReverieAgent(
            base_url=model.base_url,
            api_key=model.api_key,
            model=model.model,
            model_display_name=model.model_display_name,
            project_root=getattr(self.interface, "project_root", Path.cwd()),
            retriever=getattr(self.interface, "retriever", None),
            indexer=getattr(self.interface, "indexer", None),
            git_integration=getattr(self.interface, "git_integration", None),
            additional_rules=additional_rules,
            mode="reverie",
            provider=getattr(model, "provider", "openai-sdk"),
            thinking_mode=getattr(model, "thinking_mode", None),
            endpoint=getattr(model, "endpoint", ""),
            custom_headers=getattr(model, "custom_headers", {}),
            operation_history=getattr(self.interface, "operation_history", None),
            rollback_manager=getattr(self.interface, "rollback_manager", None),
            config=config,
            agent_id=spec.id,
            agent_color=spec.color,
            parent_agent_id="main",
        )

        shared_context = self._shared_context_from_interface()
        for key, value in shared_context.items():
            if key in {"project_root", "retriever", "indexer"}:
                continue
            child.tool_executor.update_context(key, value)
        child.tool_executor.update_context("agent", child)
        child.tool_executor.update_context("is_subagent", True)
        child.tool_executor.update_context("subagent_id", spec.id)
        child.tool_executor.update_context("subagent_color", spec.color)
        child.tool_executor.update_context("subagent_manager", self)
        return child

    def run_task(
        self,
        subagent_id: str,
        assignment: str,
        *,
        expected_output: str = "",
        read_scope: Optional[List[str]] = None,
        write_scope: Optional[List[str]] = None,
        stream: bool = False,
    ) -> SubagentRun:
        config = self._load_config()
        self.ensure_available(config)
        spec = self.get_spec(subagent_id, config)
        if spec is None:
            raise ValueError(f"Unknown subagent: {subagent_id}")
        if not spec.enabled:
            raise ValueError(f"Subagent is disabled: {subagent_id}")
        model = self.resolve_model(spec, config)
        if model is None:
            raise ValueError(f"Subagent {subagent_id} does not resolve to a configured model")

        ensure_context_engine = getattr(self.interface, "ensure_context_engine", None)
        if callable(ensure_context_engine):
            try:
                ensure_context_engine(announce=False)
            except TypeError:
                ensure_context_engine()

        run_id = f"{spec.id}-{uuid.uuid4().hex[:10]}"
        started_at = _utc_timestamp()
        run = SubagentRun(
            run_id=run_id,
            subagent_id=spec.id,
            task_id=uuid.uuid4().hex[:12],
            status="running",
            started_at=started_at,
        )
        self._runs[run_id] = run

        child_config = Config.from_dict(config.to_dict())
        child_config.mode = "reverie"
        child_agent = self._build_child_agent(spec, model, child_config)
        prompt = self._build_assignment_prompt(
            spec=spec,
            assignment=assignment,
            expected_output=expected_output,
            read_scope=read_scope,
            write_scope=write_scope,
        )

        try:
            chunks = list(
                child_agent.process_message(
                    prompt,
                    stream=stream,
                    session_id=run_id,
                    user_display_text=str(assignment or "").strip(),
                )
            )
            summary = "".join(str(chunk) for chunk in chunks).strip()
            if summary.startswith("Error processing message:"):
                run.status = "failed"
                run.error = summary
            else:
                run.status = "completed"
                run.summary = summary
        except Exception as exc:
            run.status = "failed"
            run.error = str(exc)
        finally:
            run.ended_at = _utc_timestamp()
            self._persist_run_log(run, spec, model, assignment)
            self._runs[run_id] = run

        return run

    def _persist_run_log(
        self,
        run: SubagentRun,
        spec: SubagentSpec,
        model: ModelConfig,
        assignment: str,
    ) -> None:
        log_dir = self._runs_dir(spec.id)
        log_dir.mkdir(parents=True, exist_ok=True)
        log_path = log_dir / f"{run.run_id}.json"
        run.log_path = str(log_path)
        payload = {
            "run": run.to_dict(),
            "subagent": spec.to_dict(),
            "model": model.to_dict(),
            "assignment": str(assignment or ""),
        }
        log_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")

    def get_run(self, run_id: str) -> Optional[SubagentRun]:
        return self._runs.get(str(run_id or "").strip())

    def list_recent_runs(self) -> List[SubagentRun]:
        return sorted(self._runs.values(), key=lambda item: item.started_at, reverse=True)
