from __future__ import annotations

from pathlib import Path
from threading import Event
from types import SimpleNamespace
from typing import Any

import reverie.agent.subagents as subagents_module
from reverie.agent.subagents import SubagentManager, SubagentSpec
from reverie.agent.tool_executor import ToolExecutor
from reverie.config import Config, ModelConfig, normalize_subagent_config
from reverie.tools.subagent import SubagentTool


class _ConfigManager:
    def __init__(self, config: Config):
        self.config = Config.from_dict(config.to_dict())

    def load(self) -> Config:
        return Config.from_dict(self.config.to_dict())

    def save(self, config: Config | None = None) -> None:
        if config is not None:
            self.config = Config.from_dict(config.to_dict())


class _Interface:
    def __init__(self, project_root: Path, config: Config):
        self.project_root = project_root
        self.project_data_dir = project_root / ".test-reverie"
        self.config_manager = _ConfigManager(config)
        self.agent = None
        self.retriever = None
        self.indexer = None
        self.git_integration = None
        self.operation_history = object()
        self.rollback_manager = object()

    def _load_active_runtime_config(self) -> Config:
        return self.config_manager.load()

    def ensure_context_engine(self, announce: bool = False) -> bool:
        return True


def _config(*, mode: str = "reverie", source: str = "standard") -> Config:
    return Config(
        models=[
            ModelConfig(
                model="fake-model",
                model_display_name="Fake Model",
                base_url="http://127.0.0.1",
                api_key="test-key",
                provider="request",
            )
        ],
        mode=mode,
        active_model_source=source,
    )


def _create_worker(manager: SubagentManager, *, mode: str = "reverie") -> SubagentSpec:
    return manager.create_subagent(
        {
            "source": "standard",
            "index": 0,
            "model": "fake-model",
            "display_name": "Fake Model",
        },
        mode=mode,
    )


def test_subagents_are_visible_with_nvidia_in_supported_modes(tmp_path: Path) -> None:
    for mode in ("reverie", "computer-controller"):
        config = _config(mode=mode, source="nvidia")
        manager = SubagentManager(_Interface(tmp_path / mode, config))
        executor = ToolExecutor(tmp_path)
        executor.update_context("config", config)

        names = {schema["function"]["name"] for schema in executor.get_tool_schemas(mode=mode)}

        assert manager.is_available()
        assert "subagent" in names
        manager.shutdown()


def test_subagent_mode_defaults_and_round_trips() -> None:
    normalized = normalize_subagent_config(
        {"agents": [{"id": "default"}, {"id": "computer", "mode": "computer-controller"}]}
    )

    assert normalized["agents"][0]["mode"] == "reverie"
    assert SubagentSpec.from_dict(normalized["agents"][1]).mode == "reverie"
    assert SubagentSpec.from_dict(normalized["agents"][1]).to_dict()["mode"] == "reverie"


def test_child_does_not_share_parent_session_or_rollback_state(tmp_path: Path, monkeypatch) -> None:
    captured: dict[str, Any] = {}

    class _Child:
        def __init__(self, **kwargs):
            captured.update(kwargs)
            self.tool_executor = ToolExecutor(kwargs["project_root"])

    monkeypatch.setattr(subagents_module, "ReverieAgent", _Child)
    interface = _Interface(tmp_path, _config(mode="computer-controller"))
    parent_executor = ToolExecutor(tmp_path)
    parent_executor.update_context("session_manager", object())
    parent_executor.update_context("operation_history", object())
    parent_executor.update_context("rollback_manager", object())
    parent_executor.update_context("safe_runtime", "shared")
    interface.agent = SimpleNamespace(tool_executor=parent_executor)
    manager = SubagentManager(interface)
    spec = _create_worker(manager)

    child = manager._build_child_agent(spec, interface.config_manager.load().models[0], _config())

    assert captured["mode"] == "reverie"
    assert captured["operation_history"] is None
    assert captured["rollback_manager"] is None
    assert child.tool_executor.context["safe_runtime"] == "shared"
    assert "session_manager" not in child.tool_executor.context
    assert "operation_history" not in child.tool_executor.context
    assert "rollback_manager" not in child.tool_executor.context
    manager.shutdown()


def test_background_lifecycle_injects_selected_context_and_retains_summary(
    tmp_path: Path,
    monkeypatch,
) -> None:
    started = Event()
    release = Event()
    prompts: list[str] = []

    class _Child:
        def __init__(self, **kwargs):
            self.tool_executor = ToolExecutor(kwargs["project_root"])

        def process_message(self, prompt: str, **kwargs):
            prompts.append(prompt)
            started.set()
            release.wait(2)
            yield "background summary"

    monkeypatch.setattr(subagents_module, "ReverieAgent", _Child)
    manager = SubagentManager(_Interface(tmp_path, _config()))
    spec = _create_worker(manager)
    manager.remember_context(spec.id, "selected", "SELECTED-CONTEXT-VALUE")
    manager.remember_context(spec.id, "hidden", "HIDDEN-CONTEXT-VALUE")

    run = manager.start_task(
        spec.id,
        "Inspect the requested area.",
        context_keys=["selected"],
        retain_summary=True,
    )

    assert run.status in {"queued", "running"}
    assert started.wait(1)
    assert manager.get_run(run.run_id).status == "running"
    release.set()
    finished = manager.wait_task(run.run_id, timeout=2)

    assert finished is not None
    assert finished.status == "completed"
    assert finished.summary == "background summary"
    assert "SELECTED-CONTEXT-VALUE" in prompts[0]
    assert "HIDDEN-CONTEXT-VALUE" not in prompts[0]
    assert manager.load_context(spec.id)["last_summary"] == "background summary"
    assert (tmp_path / ".test-reverie" / "subagents" / spec.id / "context.json").is_file()

    synchronous = manager.run_task(spec.id, "Run through the compatible delegate path.")
    assert synchronous.status == "completed"
    assert synchronous.summary == "background summary"
    manager.shutdown(wait=True)


def test_background_cancel_transitions_to_cancelled(tmp_path: Path, monkeypatch) -> None:
    started = Event()
    release = Event()

    class _Child:
        def __init__(self, **kwargs):
            self.tool_executor = ToolExecutor(kwargs["project_root"])

        def process_message(self, prompt: str, **kwargs):
            started.set()
            release.wait(2)
            yield "must be discarded"

    monkeypatch.setattr(subagents_module, "ReverieAgent", _Child)
    manager = SubagentManager(_Interface(tmp_path, _config()))
    spec = _create_worker(manager)
    run = manager.start_task(spec.id, "Wait until cancelled.")

    assert started.wait(1)
    cancelling = manager.cancel_task(run.run_id)
    assert cancelling is not None
    assert cancelling.status in {"cancelling", "cancelled"}
    release.set()
    finished = manager.wait_task(run.run_id, timeout=2)

    assert finished is not None
    assert finished.status == "cancelled"
    assert finished.summary == ""
    manager.shutdown(wait=True)


def test_context_tool_actions_are_isolated_per_worker(tmp_path: Path) -> None:
    manager = SubagentManager(_Interface(tmp_path, _config()))
    first = _create_worker(manager)
    second = _create_worker(manager)
    tool = SubagentTool({"subagent_manager": manager})

    remembered = tool.execute(
        action="remember",
        subagent_id=first.id,
        context_key="decision",
        context_value={"value": 3},
    )
    inspected = tool.execute(action="context", subagent_id=first.id)
    forgotten = tool.execute(action="forget", subagent_id=first.id, context_key="decision")
    cleared = tool.execute(action="clear_context", subagent_id=first.id)

    assert remembered.success
    assert inspected.data["context"] == {"decision": {"value": 3}}
    assert forgotten.success
    assert cleared.success
    assert manager.load_context(first.id) == {}
    assert manager.load_context(second.id) == {}
    manager.shutdown()


def test_main_agent_can_create_and_delete_reverie_subagent(tmp_path: Path) -> None:
    manager = SubagentManager(_Interface(tmp_path, _config(mode="computer-controller", source="nvidia")))
    tool = SubagentTool({"subagent_manager": manager})

    created = tool.execute(action="create", subagent_id="coder", mode="reverie")
    listed = tool.execute(action="list")
    deleted = tool.execute(action="delete", subagent_id="coder")

    assert created.success
    assert created.data["subagent"]["mode"] == "reverie"
    assert "coder" in listed.output
    assert deleted.success
    manager.shutdown()


def test_query_code_retrieval_cannot_bypass_read_scope(tmp_path: Path) -> None:
    executor = ToolExecutor(tmp_path)
    executor.update_context("is_subagent", True)
    executor.update_context("subagent_read_scope", ["allowed"])
    tool = executor.get_tool("codebase-retrieval")
    assert tool is not None

    broad = executor._subagent_scope_denial(tool, {"query_type": "search", "query": "Secret"})
    disguised_broad = executor._subagent_scope_denial(
        tool,
        {"query_type": "search", "query": "Secret", "path": "allowed"},
    )
    outside = executor._subagent_scope_denial(
        tool,
        {"query_type": "file", "query": "outside/secret.py"},
    )
    inside = executor._subagent_scope_denial(
        tool,
        {"query_type": "file", "query": "allowed/module.py"},
    )

    assert broad and "cannot be safely proven" in broad
    assert disguised_broad and "cannot be safely proven" in disguised_broad
    assert outside and "cannot be safely proven" in outside
    assert inside is None
