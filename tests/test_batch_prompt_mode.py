from pathlib import Path

from reverie.agent.agent import THINKING_END_MARKER, THINKING_START_MARKER
from reverie.cli.interface import ReverieInterface, _sanitize_prompt_output_text
from reverie.config import Config, ModelConfig


class _FakeToolExecutor:
    def __init__(self) -> None:
        self.context = {}

    def update_context(self, key, value) -> None:
        self.context[key] = value


class _FakeAgent:
    def __init__(self) -> None:
        self.tool_executor = _FakeToolExecutor()
        self.model_display_name = "Fake Model"
        self.messages = []
        self.additional_rules = ""
        self.mode = "reverie"
        self.ant_phase = "PLANNING"

    def set_history(self, messages) -> None:
        self.messages = list(messages)

    def get_history(self):
        return list(self.messages)

    def process_message(self, user_message, stream=True, session_id="default", user_display_text=None):
        self.messages.append({"role": "user", "content": user_message})
        handler = self.tool_executor.context.get("ui_event_handler")
        if handler:
            handler({"kind": "tool_progress", "tool_name": "command_exec", "message": "running"})
        yield "Hello "
        yield THINKING_START_MARKER
        yield "plan first"
        yield THINKING_END_MARKER
        yield "world //END//"
        self.messages.append({"role": "assistant", "content": "Hello world //END//"})


class _SpecAutoContinueAgent(_FakeAgent):
    def __init__(self, project_root: Path) -> None:
        super().__init__()
        self.project_root = Path(project_root)
        self.mode = "spec-driven"
        self.turn = 0

    def process_message(self, user_message, stream=True, session_id="default", user_display_text=None):
        self.messages.append({"role": "user", "content": user_message})
        spec_dir = self.project_root / "artifacts" / "specs" / "sample-feature"
        spec_dir.mkdir(parents=True, exist_ok=True)
        if self.turn == 0:
            (spec_dir / "requirements.md").write_text("# Requirements\n", encoding="utf-8")
            self.turn += 1
            yield "I created requirements.md. Please approve before I continue."
        else:
            (spec_dir / "design.md").write_text("# Design\n", encoding="utf-8")
            (spec_dir / "tasks.md").write_text("[ ] Implement feature\n", encoding="utf-8")
            self.turn += 1
            yield "Created design.md and tasks.md //END//"
        self.messages.append({"role": "assistant", "content": "completed"})


class _WriterAutoContinueAgent(_FakeAgent):
    def __init__(self, project_root: Path) -> None:
        super().__init__()
        self.project_root = Path(project_root)
        self.mode = "writer"
        self.turn = 0

    def process_message(self, user_message, stream=True, session_id="default", user_display_text=None):
        self.messages.append({"role": "user", "content": user_message})
        if self.turn == 0:
            self.turn += 1
            yield "I've created the outline. Should I proceed to write Chapter 1?"
        else:
            (self.project_root / "outline.md").write_text("# Outline\n", encoding="utf-8")
            (self.project_root / "chapter1.md").write_text("x" * 1600, encoding="utf-8")
            (self.project_root / "continuity_note.md").write_text("# Continuity\n", encoding="utf-8")
            self.turn += 1
            yield "Created outline.md, chapter1.md, and continuity_note.md //END//"
        self.messages.append({"role": "assistant", "content": "completed"})


def test_run_prompt_once_collects_output_and_events(tmp_path, monkeypatch):
    interface = ReverieInterface(tmp_path, headless=True)
    config = Config(
        models=[
            ModelConfig(
                model="fake-model",
                model_display_name="Fake Model",
                base_url="https://example.com/v1",
                api_key="test-key",
            )
        ],
        active_model_index=0,
    )

    monkeypatch.setattr(interface.config_manager, "load", lambda: config)
    monkeypatch.setattr(interface, "ensure_context_engine", lambda announce=False: True)
    monkeypatch.setattr(interface, "_sync_workspace_memory_message", lambda session: None)
    monkeypatch.setattr(interface.workspace_stats_manager, "update_session_snapshot", lambda *args, **kwargs: None)
    monkeypatch.setattr(interface.workspace_stats_manager, "flush", lambda: None)

    def _fake_init_agent(config_override=None, persist_config_changes=True):
        interface.agent = _FakeAgent()

    monkeypatch.setattr(interface, "_init_agent", _fake_init_agent)

    result = interface.run_prompt_once(
        "say hello",
        mode_override="writer",
        no_index=True,
    )

    assert result.success is True
    assert result.mode == "writer"
    assert result.output_text == "Hello world //END//"
    assert result.thinking_text == "plan first"
    assert result.context_engine_initialized is True
    assert result.session_id
    assert result.ui_events
    assert result.ui_events[0]["kind"] == "tool_progress"


def test_active_model_reuses_standard_nvidia_key_for_computer_controller():
    config = Config(
        models=[
            ModelConfig(
                model="stepfun-ai/step-3.5-flash",
                model_display_name="step-3.5-flash[NVIDIA]",
                base_url="https://integrate.api.nvidia.com/v1",
                api_key="nvapi-test",
            )
        ],
        active_model_index=0,
        mode="computer-controller",
        nvidia={
            "enabled": True,
            "api_key": "",
            "selected_model_id": "qwen/qwen3.5-397b-a17b",
        },
    )

    active_model = config.active_model

    assert active_model is not None
    assert active_model.api_key == "nvapi-test"


def test_sanitize_prompt_output_text_removes_leaked_thinking():
    output_text = (
        'The user wants me to print exactly "OK ".\n'
        'Let me output: OK \n'
        '</think>\n'
        'OK'
    )
    thinking_text = (
        'The user wants me to print exactly "OK //END//".\n'
        'Let me output: OK //END//'
    )

    cleaned = _sanitize_prompt_output_text(output_text, thinking_text)

    assert cleaned == "OK"


def test_run_prompt_once_auto_continues_spec_driven(tmp_path, monkeypatch):
    interface = ReverieInterface(tmp_path, headless=True)
    config = Config(
        models=[
            ModelConfig(
                model="fake-model",
                model_display_name="Fake Model",
                base_url="https://example.com/v1",
                api_key="test-key",
            )
        ],
        active_model_index=0,
        mode="spec-driven",
    )

    monkeypatch.setattr(interface.config_manager, "load", lambda: config)
    monkeypatch.setattr(interface, "ensure_context_engine", lambda announce=False: True)
    monkeypatch.setattr(interface, "_sync_workspace_memory_message", lambda session: None)
    monkeypatch.setattr(interface.workspace_stats_manager, "update_session_snapshot", lambda *args, **kwargs: None)
    monkeypatch.setattr(interface.workspace_stats_manager, "flush", lambda: None)

    def _fake_init_agent(config_override=None, persist_config_changes=True):
        interface.agent = _SpecAutoContinueAgent(tmp_path)

    monkeypatch.setattr(interface, "_init_agent", _fake_init_agent)

    result = interface.run_prompt_once(
        "Create requirements.md, design.md, and tasks.md for this feature.",
        mode_override="spec-driven",
        no_index=True,
    )

    assert result.success is True
    assert result.auto_followup_count == 1
    assert result.output_text == "Created design.md and tasks.md //END//"
    assert (tmp_path / "artifacts" / "specs" / "sample-feature" / "requirements.md").exists()
    assert (tmp_path / "artifacts" / "specs" / "sample-feature" / "design.md").exists()
    assert (tmp_path / "artifacts" / "specs" / "sample-feature" / "tasks.md").exists()


def test_run_prompt_once_auto_continues_writer_when_files_missing(tmp_path, monkeypatch):
    interface = ReverieInterface(tmp_path, headless=True)
    config = Config(
        models=[
            ModelConfig(
                model="fake-model",
                model_display_name="Fake Model",
                base_url="https://example.com/v1",
                api_key="test-key",
            )
        ],
        active_model_index=0,
        mode="writer",
    )

    monkeypatch.setattr(interface.config_manager, "load", lambda: config)
    monkeypatch.setattr(interface, "ensure_context_engine", lambda announce=False: True)
    monkeypatch.setattr(interface, "_sync_workspace_memory_message", lambda session: None)
    monkeypatch.setattr(interface.workspace_stats_manager, "update_session_snapshot", lambda *args, **kwargs: None)
    monkeypatch.setattr(interface.workspace_stats_manager, "flush", lambda: None)

    def _fake_init_agent(config_override=None, persist_config_changes=True):
        interface.agent = _WriterAutoContinueAgent(tmp_path)

    monkeypatch.setattr(interface, "_init_agent", _fake_init_agent)

    result = interface.run_prompt_once(
        "Create outline.md, chapter1.md, and continuity_note.md for this story.",
        mode_override="writer",
        no_index=True,
    )

    assert result.success is True
    assert result.auto_followup_count == 1
    assert result.output_text == "Created outline.md, chapter1.md, and continuity_note.md //END//"
    assert (tmp_path / "outline.md").exists()
    assert (tmp_path / "chapter1.md").exists()
    assert (tmp_path / "continuity_note.md").exists()
