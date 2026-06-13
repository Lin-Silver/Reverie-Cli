from __future__ import annotations

from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from threading import Thread
from typing import Any
import json

from reverie.agent.subagents import SubagentManager
from reverie.agent.tool_executor import ToolExecutor
from reverie.config import Config, ModelConfig, normalize_subagent_config
from reverie.nvidia import default_nvidia_config


class _FakeConfigManager:
    def __init__(self, config: Config):
        self.config = Config.from_dict(config.to_dict())

    def load(self) -> Config:
        return Config.from_dict(self.config.to_dict())

    def save(self, config: Config | None = None) -> None:
        if config is not None:
            self.config = Config.from_dict(config.to_dict())

    def get_active_model(self):
        return self.config.active_model


class _FakeRulesManager:
    def get_rules_text(self) -> str:
        return ""


class _FakeInterface:
    def __init__(self, project_root: Path, config: Config):
        self.project_root = project_root
        self.project_data_dir = project_root / ".test-reverie"
        self.project_data_dir.mkdir(parents=True, exist_ok=True)
        self.config_manager = _FakeConfigManager(config)
        self.rules_manager = _FakeRulesManager()
        self.agent = None
        self.retriever = None
        self.indexer = None
        self.git_integration = None
        self.lsp_manager = None
        self.operation_history = None
        self.rollback_manager = None
        self.mcp_config_manager = None
        self.mcp_runtime = None
        self.runtime_plugin_manager = None
        self.skills_manager = None
        self.session_manager = None
        self.memory_indexer = None
        self.workspace_stats_manager = None
        self.console = None
        self.ui_events = []

    def _load_active_runtime_config(self) -> Config:
        return self.config_manager.load()

    def ensure_context_engine(self, announce: bool = False) -> bool:
        return True

    def _handle_agent_ui_event(self, event: dict) -> None:
        self.ui_events.append(dict(event))


class _SubagentFakeHandler(BaseHTTPRequestHandler):
    call_count = 0

    def log_message(self, format: str, *args: Any) -> None:
        return

    def do_POST(self) -> None:
        content_length = int(self.headers.get("Content-Length", "0") or "0")
        _ = self.rfile.read(content_length)
        type(self).call_count += 1
        payload = {
            "choices": [
                {
                    "message": {
                        "role": "assistant",
                        "content": "Evidence summary: inspected requested scope and found the relevant boundary. //END//",
                    }
                }
            ],
            "usage": {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2},
        }

        body = json.dumps(payload).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


def _start_fake_server() -> tuple[HTTPServer, Thread, str]:
    _SubagentFakeHandler.call_count = 0
    server = HTTPServer(("127.0.0.1", 0), _SubagentFakeHandler)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    host, port = server.server_address
    return server, thread, f"http://{host}:{port}/chat/completions"


def test_subagent_config_normalizes_and_round_trips() -> None:
    normalized = normalize_subagent_config(
        {
            "agents": [
                {
                    "id": "worker one",
                    "model_ref": {"source": "unknown", "index": "3", "model": "m"},
                }
            ]
        }
    )

    assert normalized["enabled"] is True
    assert normalized["agents"][0]["model_ref"]["source"] == "standard"
    assert normalized["agents"][0]["model_ref"]["index"] == 3
    assert normalized["agents"][0]["color"].startswith("#")

    config = Config.from_dict({"models": [], "subagents": normalized})
    serialized = config.to_dict()
    assert serialized["subagents"]["agents"][0]["id"] == "worker one"


def test_subagent_tool_is_only_visible_in_base_reverie(tmp_path: Path) -> None:
    executor = ToolExecutor(tmp_path)
    reverie_names = {
        schema["function"]["name"]
        for schema in executor.get_tool_schemas(mode="reverie")
    }
    gamer_names = {
        schema["function"]["name"]
        for schema in executor.get_tool_schemas(mode="reverie-gamer")
    }

    assert "subagent" in reverie_names
    assert "subagent" not in gamer_names


def test_subagent_is_disabled_with_nvidia_source(tmp_path: Path) -> None:
    nvidia_cfg = default_nvidia_config()
    nvidia_cfg["api_key"] = "nv-test-key"
    config = Config(
        models=[],
        mode="reverie",
        active_model_source="nvidia",
        nvidia=nvidia_cfg,
    )
    manager = SubagentManager(_FakeInterface(tmp_path, config))

    assert not manager.is_available()
    try:
        manager.ensure_available()
    except RuntimeError as exc:
        assert "NVIDIA source" in str(exc)
    else:
        raise AssertionError("NVIDIA source should disable Subagents")


def test_context_engine_remains_visible_when_source_string_pollutes_mode(tmp_path: Path) -> None:
    executor = ToolExecutor(tmp_path)
    names = {
        schema["function"]["name"]
        for schema in executor.get_tool_schemas(mode="nvidia")
    }

    assert "codebase-retrieval" in names


def test_nvidia_source_hides_subagent_schema_but_keeps_context_engine(tmp_path: Path) -> None:
    nvidia_cfg = default_nvidia_config()
    nvidia_cfg["api_key"] = "nv-test-key"
    config = Config(
        mode="reverie",
        active_model_source="nvidia",
        nvidia=nvidia_cfg,
    )
    executor = ToolExecutor(tmp_path)
    executor.update_context("config", config)

    names = {
        schema["function"]["name"]
        for schema in executor.get_tool_schemas(mode="reverie")
    }

    assert "subagent" not in names
    assert "codebase-retrieval" in names


def test_subagent_tool_executor_is_read_only_by_default(tmp_path: Path) -> None:
    executor = ToolExecutor(tmp_path)
    executor.update_context("is_subagent", True)
    result = executor.execute(
        "create_file",
        {
            "path": "artifacts/blocked.txt",
            "content": "should not be written\n",
            "overwrite": True,
        },
    )

    assert not result.success
    assert "read-only by default" in (result.error or "")
    assert not (tmp_path / "artifacts" / "blocked.txt").exists()


def test_subagent_write_scope_allows_bounded_paths(tmp_path: Path) -> None:
    executor = ToolExecutor(tmp_path)
    executor.update_context("is_subagent", True)
    executor.update_context("subagent_write_scope", ["artifacts"])

    allowed = executor.execute(
        "create_file",
        {"path": "artifacts/allowed.txt", "content": "ok\n", "overwrite": True},
    )
    denied = executor.execute(
        "create_file",
        {"path": "outside.txt", "content": "no\n", "overwrite": True},
    )

    assert allowed.success
    assert (tmp_path / "artifacts" / "allowed.txt").read_text(encoding="utf-8") == "ok\n"
    assert not denied.success
    assert "write_scope" in (denied.error or "")
    assert not (tmp_path / "outside.txt").exists()


def test_subagent_assignment_prompt_positions_worker_as_scoped_validator(tmp_path: Path) -> None:
    config = Config(
        models=[
            ModelConfig(
                model="fake-subagent-model",
                model_display_name="Fake Subagent Model",
                base_url="http://127.0.0.1",
                api_key="test-key",
                max_context_tokens=128000,
                provider="request",
            )
        ],
        active_model_index=0,
        mode="reverie",
    )
    interface = _FakeInterface(tmp_path, config)
    manager = SubagentManager(interface)
    spec = manager.create_subagent(
        {
            "source": "standard",
            "index": 0,
            "model": "fake-subagent-model",
            "display_name": "Fake Subagent Model",
        }
    )

    prompt = manager._build_assignment_prompt(
        spec=spec,
        assignment="Validate the selected Context Engine workset.",
        read_scope=["reverie/context_engine"],
        worker_role="validator",
    )

    assert "validator worker" in prompt
    assert "Default policy: read-only" in prompt
    assert "No write_scope was assigned" in prompt
    assert "- reverie/context_engine" in prompt
