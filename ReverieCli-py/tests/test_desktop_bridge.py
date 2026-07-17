import json
from pathlib import Path
import threading
from types import SimpleNamespace

from reverie.config import Config, ModelConfig
from reverie.desktop_catalog import (
    add_standard_model,
    apply_model_selection,
    build_model_sources_payload,
    delete_standard_model,
    update_standard_model,
)
from reverie.session.manager import SessionManager, session_title_from_prompt
from reverie.sdk_bridge import _desktop_tool_record


def test_kernel_info_contract(capsys) -> None:
    from reverie.__main__ import main

    assert main(["--kernel-info"]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["schema"] == "reverie.kernel.v1"
    assert payload["version"] == "2.5.0"
    assert payload["bridge_protocol"] == "sdk-bridge.v1"
    assert payload["platform"]
    assert payload["arch"]


def _source(payload: dict, source_id: str) -> dict:
    return next(item for item in payload["sources"] if item["id"] == source_id)


def test_desktop_catalog_uses_native_model_reasoning_metadata() -> None:
    config = Config()
    payload = build_model_sources_payload(config)

    assert {item["id"] for item in payload["sources"]} >= {
        "standard",
        "codex",
        "nvidia",
        "sensenova",
        "agnes",
    }

    standard = _source(payload, "standard")
    if not standard["models"]:
        assert standard["selected_reasoning"] == {"control": "none", "options": [], "value": ""}

    codex = _source(payload, "codex")
    assert codex["models"]
    assert codex["models"][0]["reasoning"]["control"] == "effort"
    assert {item["id"] for item in codex["models"][0]["reasoning"]["options"]} >= {
        "low",
        "medium",
        "high",
    }

    nvidia = _source(payload, "nvidia")
    toggle_model = next(item for item in nvidia["models"] if item["reasoning"]["control"] == "toggle")
    assert {item["id"] for item in toggle_model["reasoning"]["options"]} == {"true", "false"}

    agnes = _source(payload, "agnes")
    no_thinking = next(item for item in agnes["models"] if not item["thinking"])
    assert no_thinking["reasoning"] == {"control": "none", "options": [], "value": "none"}
    assert agnes["modalities"] == {"live": False, "llm": 2, "tti": 2, "ttv": 1}


def test_model_selection_updates_model_specific_reasoning() -> None:
    config = Config()
    selected = apply_model_selection(config, "codex", "gpt-5.6-sol", "high")
    assert selected["id"] == "gpt-5.6-sol"
    assert config.active_model_source == "codex"
    assert config.codex["reasoning_effort"] == "high"

    nvidia_payload = build_model_sources_payload(config)
    nvidia = _source(nvidia_payload, "nvidia")
    toggle_model = next(item for item in nvidia["models"] if item["reasoning"]["control"] == "toggle")
    apply_model_selection(config, "nvidia", toggle_model["id"], "false")
    assert config.nvidia["selected_model_id"] == toggle_model["id"]
    assert config.nvidia["enable_thinking"] is False


def test_standard_model_crud_preserves_secret_when_update_omits_it() -> None:
    config = Config()
    index = add_standard_model(
        config,
        {
            "model": "local-model",
            "model_display_name": "Local Model",
            "base_url": "http://127.0.0.1:8000/v1",
            "api_key": "secret-key",
            "provider": "openai-chat",
        },
    )
    assert index == 0
    update_standard_model(config, index, {"model_display_name": "Renamed Model", "api_key": ""})
    assert config.models[index].model_display_name == "Renamed Model"
    assert config.models[index].api_key == "secret-key"
    delete_standard_model(config, index)
    assert config.models == []


def test_prompt_cli_accepts_uppercase_p_and_runtime_model_overrides(monkeypatch, tmp_path: Path) -> None:
    from reverie import __main__ as entrypoint
    import reverie.cli.interface as interface_module

    captured = {}

    class _Result:
        success = True
        output_text = "ok"
        error = ""

    class _Interface:
        def __init__(self, project_root: Path, headless: bool = False):
            captured["project_root"] = project_root
            captured["headless"] = headless

        def run_prompt_once(self, prompt: str, **kwargs):
            captured["prompt"] = prompt
            captured.update(kwargs)
            return _Result()

    monkeypatch.setattr(interface_module, "ReverieInterface", _Interface)
    code = entrypoint.main(
        [
            str(tmp_path),
            "-P",
            "hello",
            "-source",
            "codex",
            "-model",
            "gpt-5.6-sol",
            "-reasoning",
            "high",
        ]
    )

    assert code == 0
    assert captured["prompt"] == "hello"
    assert captured["source_override"] == "codex"
    assert captured["model_override"] == "gpt-5.6-sol"
    assert captured["reasoning_override"] == "high"


def test_desktop_approval_request_can_be_resolved_while_prompt_waits() -> None:
    from reverie.sdk_bridge import ReverieSdkBridge

    published = threading.Event()
    events = []

    def write_event(message: dict) -> None:
        events.append(message)
        published.set()

    bridge = ReverieSdkBridge(event_writer=write_event)
    result = {}
    tool = type("Tool", (), {"name": "write_file"})()

    worker = threading.Thread(
        target=lambda: result.update(
            decision=bridge._request_tool_approval("prompt-1", tool, {"path": "note.txt"}, "Write access required")
        )
    )
    worker.start()
    assert published.wait(timeout=1)

    request = events[0]["event"]
    response = bridge.dispatch(
        {
            "id": "approval-1",
            "action": "resolveApproval",
            "payload": {"approvalId": request["approval_id"], "decision": "once"},
        }
    )
    worker.join(timeout=1)

    assert response["type"] == "approval.resolved"
    assert result["decision"] == "once"


def test_session_titles_are_compact_and_legacy_names_are_upgraded(tmp_path: Path) -> None:
    manager = SessionManager(tmp_path / "state", project_root=tmp_path)
    session = manager.create_session("Prompt Run 2026-07-15 10:00:00")
    session.messages = [
        {"role": "system", "content": "workspace memory"},
        {"role": "user", "content": "  Diagnose   the history interaction and fix it completely.  "},
    ]
    manager.save_session(session)

    assert manager.refresh_generated_session_names() == 1
    assert manager.list_sessions()[0].name == "Diagnose the history interaction and fix it completely."
    assert session_title_from_prompt("x" * 100, max_length=20) == f"{'x' * 19}…"


def test_desktop_session_actions_keep_a_valid_active_session(tmp_path: Path) -> None:
    from reverie.sdk_bridge import ReverieSdkBridge

    manager = SessionManager(tmp_path / "state", project_root=tmp_path)
    first = manager.create_session()
    first.messages = [
        {"role": "user", "content": "First request"},
        {"role": "assistant", "content": "First answer"},
    ]
    manager.save_session(first)
    second = manager.create_session("Pinned conversation")
    manager.save_session(second)
    manager.load_session(first.id)

    class _Agent:
        history = []

        def set_history(self, messages):
            self.history = list(messages)

    class _Interface:
        session_manager = manager
        agent = _Agent()

    bridge = ReverieSdkBridge()
    bridge.project_root = tmp_path.resolve()
    bridge.interface = _Interface()

    renamed = bridge.dispatch(
        {"id": "rename", "action": "renameSession", "payload": {"sessionId": first.id, "name": "Renamed"}}
    )
    assert renamed["session"]["name"] == "Renamed"

    forked = bridge.dispatch(
        {"id": "fork", "action": "forkSession", "payload": {"sessionId": first.id, "messageCount": 1}}
    )
    fork_id = forked["session"]["id"]
    assert len(forked["session"]["messages"]) == 1

    rewound = bridge.dispatch(
        {
            "id": "rewind",
            "action": "rewindSession",
            "payload": {"sessionId": fork_id, "messageCount": 0, "confirmed": True},
        }
    )
    assert rewound["session"]["messages"] == []

    deleted = bridge.dispatch(
        {"id": "delete", "action": "deleteSession", "payload": {"sessionId": fork_id, "confirmed": True}}
    )
    assert deleted["session"] is not None
    assert deleted["sessions"]["current_session_id"] == deleted["session"]["id"]
    assert {item["id"] for item in deleted["sessions"]["items"]} == {first.id, second.id}


def test_renaming_or_deleting_a_background_session_preserves_the_active_session(tmp_path: Path) -> None:
    from reverie.sdk_bridge import ReverieSdkBridge

    manager = SessionManager(tmp_path / "state", project_root=tmp_path)
    active = manager.create_session("Active")
    manager.save_session(active)
    background = manager.create_session("Background")
    manager.save_session(background)
    manager.load_session(active.id)

    class _Agent:
        history = []

        def set_history(self, messages):
            self.history = list(messages)

    class _Interface:
        session_manager = manager
        agent = _Agent()

    bridge = ReverieSdkBridge()
    bridge.project_root = tmp_path.resolve()
    bridge.interface = _Interface()

    renamed = bridge.dispatch(
        {"id": "rename-background", "action": "renameSession", "payload": {"sessionId": background.id, "name": "Renamed"}}
    )
    assert renamed["session"]["id"] == active.id
    assert renamed["updated_session"]["id"] == background.id
    assert renamed["updated_session"]["name"] == "Renamed"
    assert manager.get_current_session().id == active.id

    deleted = bridge.dispatch(
        {"id": "delete-background", "action": "deleteSession", "payload": {"sessionId": background.id, "confirmed": True}}
    )
    assert deleted["session"]["id"] == active.id
    assert manager.get_current_session().id == active.id
    assert {item["id"] for item in deleted["sessions"]["items"]} == {active.id}


def test_bulk_deleting_archived_sessions_preserves_an_unarchived_active_session(tmp_path: Path) -> None:
    from reverie.sdk_bridge import ReverieSdkBridge

    manager = SessionManager(tmp_path / "state", project_root=tmp_path)
    active = manager.create_session("Active")
    manager.save_session(active)
    archived_one = manager.create_session("Archived one")
    manager.save_session(archived_one)
    archived_two = manager.create_session("Archived two")
    manager.save_session(archived_two)
    manager.load_session(active.id)

    class _Agent:
        history = []

        def set_history(self, messages):
            self.history = list(messages)

    class _Interface:
        session_manager = manager
        agent = _Agent()

    bridge = ReverieSdkBridge()
    bridge.project_root = tmp_path.resolve()
    bridge.interface = _Interface()

    deleted = bridge.dispatch(
        {
            "id": "delete-archived",
            "action": "deleteSessions",
            "payload": {
                "sessionIds": [archived_one.id, archived_two.id, archived_one.id],
                "confirmed": True,
            },
        }
    )

    assert deleted["session"]["id"] == active.id
    assert deleted["deleted_session_ids"] == [archived_one.id, archived_two.id]
    assert {item["id"] for item in deleted["sessions"]["items"]} == {active.id}
    assert manager.load_session(archived_one.id) is None
    assert manager.load_session(archived_two.id) is None


def test_session_search_covers_titles_reasoning_and_tool_calls(tmp_path: Path) -> None:
    manager = SessionManager(tmp_path / "state", project_root=tmp_path)
    session = manager.create_session("Architecture review")
    session.messages = [
        {"role": "assistant", "content": None, "reasoning_content": "inspect the persistence boundary"},
        {
            "role": "assistant",
            "content": None,
            "tool_calls": [{"function": {"name": "read_session_index", "arguments": "{}"}}],
        },
    ]
    manager.save_session(session)

    assert manager.search_sessions("Architecture")[0]["message_index"] == -1
    assert manager.search_sessions("persistence")[0]["message_index"] == 0
    assert manager.search_sessions("read_session_index")[0]["message_index"] == 1


def test_sdk_bridge_forces_utf8_stdio_for_frozen_windows_build(monkeypatch) -> None:
    import reverie.sdk_bridge as sdk_bridge

    class _Stream:
        configured = None

        def reconfigure(self, **kwargs):
            self.configured = kwargs

    streams = [_Stream(), _Stream(), _Stream()]
    monkeypatch.setattr(sdk_bridge.sys, "stdin", streams[0])
    monkeypatch.setattr(sdk_bridge.sys, "stdout", streams[1])
    monkeypatch.setattr(sdk_bridge.sys, "stderr", streams[2])

    sdk_bridge._configure_utf8_stdio()

    assert [stream.configured for stream in streams] == [
        {"encoding": "utf-8", "errors": "strict"},
        {"encoding": "utf-8", "errors": "strict"},
        {"encoding": "utf-8", "errors": "strict"},
    ]


def test_desktop_tool_record_flattens_schema_metadata_for_the_gui() -> None:
    tool = type("ReadFileTool", (), {"__module__": "reverie.tools.read_file"})()
    payload = _desktop_tool_record(
        {
            "name": "read_file",
            "tool": tool,
            "description": "Read text from a workspace file.",
            "required": ["path"],
            "properties": ["path", "line_start"],
            "supported_modes": ["reverie", "writer"],
            "metadata": {
                "category": "filesystem",
                "aliases": ["cat_file"],
                "tags": ["read", "file"],
                "read_only": True,
                "concurrency_safe": True,
            },
        }
    )

    assert payload == {
        "name": "read_file",
        "description": "Read text from a workspace file.",
        "kind": "built-in",
        "category": "filesystem",
        "aliases": ["cat_file"],
        "tags": ["read", "file"],
        "traits": ["read-only", "parallel"],
        "required": ["path"],
        "properties": ["path", "line_start"],
        "supported_modes": ["reverie", "writer"],
    }


def test_sdk_bridge_switches_workspace_interfaces_without_replacing_the_bridge(monkeypatch, tmp_path: Path) -> None:
    from reverie.cli import interface as interface_module
    from reverie.sdk_bridge import ReverieSdkBridge

    first_root = tmp_path / "first"
    second_root = tmp_path / "second"
    first_root.mkdir()
    second_root.mkdir()

    class _OldInterface:
        closed = False

        def close(self):
            self.closed = True

    class _NewInterface:
        def __init__(self, project_root: Path, headless: bool = False):
            self.project_root = project_root
            self.headless = headless

    bridge = ReverieSdkBridge()
    old_interface = _OldInterface()
    bridge.project_root = first_root.resolve()
    bridge.interface = old_interface
    monkeypatch.setattr(interface_module, "ReverieInterface", _NewInterface)

    next_interface = bridge.ensure_interface(second_root)

    assert old_interface.closed is True
    assert bridge.project_root == second_root.resolve()
    assert next_interface.project_root == second_root.resolve()
    assert next_interface.headless is True


def test_delete_project_data_removes_reverie_records_but_preserves_project_files(monkeypatch, tmp_path: Path) -> None:
    from reverie.config import ConfigManager
    from reverie.sdk_bridge import ReverieSdkBridge

    project_root = tmp_path / "project"
    project_root.mkdir()
    source_file = project_root / "keep.py"
    source_file.write_text("print('keep')\n", encoding="utf-8")
    monkeypatch.setenv("REVERIE_APP_ROOT", str(tmp_path / "app"))
    config_manager = ConfigManager(project_root)
    config_manager.ensure_dirs()
    sessions_dir = config_manager.project_data_dir / "sessions"
    sessions_dir.mkdir(parents=True, exist_ok=True)
    (sessions_dir / "one.json").write_text("{}", encoding="utf-8")
    (sessions_dir / "two.json").write_text("{}", encoding="utf-8")
    workspace_config = config_manager.project_data_dir / "config.json"
    workspace_rules = config_manager.project_data_dir / "rules.txt"
    workspace_config.write_text('{"workspace": true}', encoding="utf-8")
    workspace_rules.write_text("Keep project conventions.\n", encoding="utf-8")
    context_cache = project_root / ".reverie" / "context_cache"
    context_cache.mkdir(parents=True)
    (context_cache / "index.json").write_text("{}", encoding="utf-8")

    response = ReverieSdkBridge().dispatch(
        {
            "id": "delete-project",
            "action": "deleteProjectData",
            "payload": {"projectRoot": str(project_root), "confirmed": True},
        }
    )

    assert response["deleted_sessions"] == 2
    assert not sessions_dir.exists()
    assert workspace_config.read_text(encoding="utf-8") == '{"workspace": true}'
    assert workspace_rules.read_text(encoding="utf-8") == "Keep project conventions.\n"
    assert not context_cache.exists()
    assert source_file.read_text(encoding="utf-8") == "print('keep')\n"


def test_workspace_mentions_prioritize_context_engine_recommendations(tmp_path: Path) -> None:
    from reverie.cli.interface import ReverieInterface

    target = tmp_path / "src" / "composer.tsx"
    target.parent.mkdir()
    target.write_text("export const Composer = () => null;\n", encoding="utf-8")

    class _SessionManager:
        @staticmethod
        def get_current_session():
            return SimpleNamespace(messages=[{"role": "user", "content": "fix the composer attachment picker"}])

    class _Retriever:
        @staticmethod
        def retrieve_for_task(*args, **kwargs):
            return SimpleNamespace(
                relevant_files=[
                    SimpleNamespace(
                        file_path=str(target),
                        score=17.0,
                        reasons=["task:composer"],
                        summary="Composer attachment controls",
                    )
                ],
                relevant_symbols=[],
            )

    fake_interface = SimpleNamespace(
        project_root=tmp_path,
        session_manager=_SessionManager(),
        retriever=_Retriever(),
        indexer=None,
        ensure_context_engine=lambda **kwargs: False,
        ensure_git_integration=lambda **kwargs: False,
    )

    candidates = ReverieInterface._collect_workspace_mention_candidates(fake_interface, "", limit=8)

    assert candidates[0]["path"] == "src/composer.tsx"
    assert candidates[0]["source"] == "context-engine"
    assert candidates[0]["reason"] == "task:composer"


def test_workspace_mentions_fall_back_to_partial_filename_matches(tmp_path: Path) -> None:
    from reverie.cli.interface import ReverieInterface

    target = tmp_path / "src" / "composer.tsx"
    target.parent.mkdir()
    target.write_text("export const Composer = () => null;\n", encoding="utf-8")
    (tmp_path / "README.md").write_text("Project notes.\n", encoding="utf-8")

    fake_interface = SimpleNamespace(
        project_root=tmp_path,
        session_manager=SimpleNamespace(get_current_session=lambda: None),
        retriever=None,
        indexer=None,
        ensure_context_engine=lambda **kwargs: False,
        ensure_git_integration=lambda **kwargs: False,
    )

    candidates = ReverieInterface._collect_workspace_mention_candidates(
        fake_interface,
        "composer attachment",
        limit=8,
    )

    assert [item["path"] for item in candidates] == ["src/composer.tsx"]
    assert candidates[0]["source"] == "workspace-scan"
