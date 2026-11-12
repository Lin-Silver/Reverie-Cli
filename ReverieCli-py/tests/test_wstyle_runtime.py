import json
from pathlib import Path

import pytest

from reverie.config import Config, normalize_writer_mode_config
from reverie.session.manager import SessionManager
from reverie.tools.serial_novel import SerialNovelTool
from reverie.writer.style_runtime import WStyleRuntime
from reverie.writer.wstyles import WStyleError

from test_wstyles import write_card


def make_runtime(tmp_path, **kwargs):
    workspace = tmp_path / "workspace"
    workspace.mkdir(exist_ok=True)
    runtime = WStyleRuntime(workspace, app_root=tmp_path / "app", **kwargs)
    write_card(runtime.repository, "a", "具体动作承载情绪。")
    write_card(runtime.repository, "b", "短句推进场景选择。", layer="narrative")
    return runtime


def bootstrap(runtime, novel_id):
    tool = SerialNovelTool({"project_root": runtime.project_root})
    assert tool.execute(action="bootstrap", novel_id=novel_id, title=novel_id,
                        brief="A small original workflow proof", target_chars=1000, chapter_target_chars=500).success
    return runtime.project_root / "novels" / novel_id


def test_config_defaults_migrate_single_id_and_preserve_other_writer_settings():
    assert normalize_writer_mode_config({})["active_wstyles"] == []
    normalized = normalize_writer_mode_config({"active_wstyles": "a", "memory_system_enabled": False})
    assert normalized["active_wstyles"] == ["a"]
    assert normalized["memory_system_enabled"] is False
    assert Config.from_dict({"writer_mode": {"active_wstyles": ["b", "a", "b"]}}).writer_mode["active_wstyles"] == ["b", "a"]


def test_global_selection_is_atomic_and_recovers_order_without_overwriting_config(tmp_path):
    runtime = make_runtime(tmp_path)
    config_path = runtime.global_config_path
    config_path.parent.mkdir(parents=True, exist_ok=True)
    config_path.write_text(json.dumps({"mode": "writer", "unrelated": {"keep": True}}), encoding="utf-8")
    runtime.set_selection(["b", "a", "b"], global_scope=True)
    saved = json.loads(config_path.read_text(encoding="utf-8"))
    assert saved["writer_mode"]["active_wstyles"] == ["b", "a"]
    assert saved["unrelated"] == {"keep": True}
    restarted = WStyleRuntime(runtime.project_root, app_root=runtime.app_root)
    assert restarted.composition().active_ids == ["b", "a"]
    assert restarted.snapshot()["scope"] == "global"


def test_novel_override_and_explicit_off_preserve_manuscript(tmp_path):
    runtime = make_runtime(tmp_path)
    runtime.set_selection(["a"], global_scope=True)
    project_dir = bootstrap(runtime, "first")
    runtime.bind_project("first", project_dir)
    state_path = project_dir / "tracking" / "state.json"
    prior_state = json.loads(state_path.read_text(encoding="utf-8"))
    assert runtime.composition().active_ids == ["a"]
    runtime.set_selection(["b"])
    saved = json.loads(state_path.read_text(encoding="utf-8"))
    assert saved["active_wstyles"] == ["b"]
    assert saved["chapters"] == prior_state["chapters"]
    assert runtime.snapshot()["scope"] == "novel:first"
    runtime.set_selection([])
    assert runtime.composition().active_ids == []
    assert json.loads(runtime.global_config_path.read_text(encoding="utf-8"))["writer_mode"]["active_wstyles"] == ["a"]
    runtime.inherit_defaults()
    assert runtime.composition().active_ids == ["a"]
    assert "active_wstyles" not in json.loads(state_path.read_text(encoding="utf-8"))


def test_invalid_selection_does_not_clear_saved_state_and_missing_card_is_visible(tmp_path):
    runtime = make_runtime(tmp_path)
    runtime.set_selection(["a"], global_scope=True)
    before = runtime.global_config_path.read_bytes()
    with pytest.raises(WStyleError):
        runtime.set_selection(["missing"], global_scope=True)
    assert runtime.global_config_path.read_bytes() == before
    (runtime.repository.root / "a.md").unlink()
    state = runtime.snapshot()
    assert state["saved_ids"] == ["a"]
    assert state["cards"] == []
    assert state["issues"]
    assert state["saved_matches_effective"] is False


def test_session_binding_recovers_correct_novel_and_never_escapes_workspace(tmp_path):
    runtime = make_runtime(tmp_path)
    sessions = SessionManager(runtime.project_root)
    session = sessions.create_session("Writer proof")
    runtime.session_manager = sessions
    first = bootstrap(runtime, "first")
    bootstrap(runtime, "second")
    runtime.bind_project("first", first)
    runtime.set_selection(["a"])
    restored = WStyleRuntime(runtime.project_root, app_root=runtime.app_root, session_manager=sessions)
    assert restored.snapshot()["scope"] == "novel:first"
    assert restored.composition().active_ids == ["a"]
    session.metadata["writer_project"] = {"novel_id": "escape", "project_dir": "../outside"}
    sessions.save_session(session)
    other = WStyleRuntime(runtime.project_root, app_root=runtime.app_root, session_manager=sessions)
    assert any("workspace" in item["message"].lower() for item in other.snapshot()["issues"])


def test_first_install_keeps_user_card_and_deleted_builtin_stays_deleted(tmp_path):
    runtime = make_runtime(tmp_path)
    bundled = tmp_path / "bundled"
    bundled.mkdir()
    from test_wstyles import card_text

    (bundled / "a.md").write_text(card_text("a", "内置版本"), encoding="utf-8")
    (bundled / "fresh.md").write_text(card_text("fresh", "新内置卡片"), encoding="utf-8")
    user_bytes = (runtime.repository.root / "a.md").read_bytes()
    runtime.install_bundled(bundled)
    assert (runtime.repository.root / "a.md").read_bytes() == user_bytes
    assert runtime.repository.get("fresh").body == "新内置卡片"
    (runtime.repository.root / "fresh.md").unlink()
    runtime.install_bundled(bundled)
    assert not (runtime.repository.root / "fresh.md").exists()


@pytest.mark.parametrize("saved", [[], "broken", {"writer_mode": []}])
def test_malformed_application_configuration_is_visible_without_crashing(tmp_path, saved):
    runtime = make_runtime(tmp_path)
    runtime.global_config_path.write_text(json.dumps(saved), encoding="utf-8")
    state = runtime.snapshot()
    assert state["cards"] == []
    assert state["issues"] and state["saved_matches_effective"] is False


def test_corrupt_installation_record_does_not_disable_existing_valid_cards(tmp_path):
    runtime = make_runtime(tmp_path)
    runtime.set_selection(["a"], global_scope=True)
    marker = runtime.repository.root / ".bundled.json"
    marker.write_text("[broken", encoding="utf-8")
    restored = WStyleRuntime(runtime.project_root, app_root=runtime.app_root)
    state = restored.snapshot()
    assert [card["id"] for card in state["cards"]] == ["a"]
    assert any(issue["id"] == "resources" for issue in state["issues"])
    assert marker.read_text(encoding="utf-8") == "[broken"


def test_style_allocation_honors_the_smaller_active_model_context(tmp_path):
    from reverie.config import ModelConfig

    runtime = make_runtime(tmp_path)
    runtime.config = Config(max_context_tokens=128_000, models=[ModelConfig("small", "Small", "http://127.0.0.1", max_context_tokens=1024)])
    with pytest.raises(WStyleError, match="token WStyle allocation"):
        runtime.set_selection(["a"], global_scope=True)
    assert not runtime.global_config_path.exists()
