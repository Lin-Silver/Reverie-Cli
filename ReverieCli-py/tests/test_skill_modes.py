"""Mode changes preserve the skill library while explaining execution limits."""

from pathlib import Path
from types import SimpleNamespace

import pytest

from reverie.sdk_bridge import ReverieSdkBridge
from reverie.skills_manager import SkillsManager
from reverie.tools.mode_switch import ModeSwitchTool
from reverie.tools.skill_lookup import SkillLookupTool


@pytest.mark.parametrize("mode", ["writer", "computer-controller"])
def test_restricted_modes_keep_discovery_pins_and_actionable_guidance(tmp_path, monkeypatch, mode):
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: tmp_path))
    manager = SkillsManager(tmp_path / "project", tmp_path / "app")
    manager.pin_skill("photo-to-3d")
    manager.set_active_mode(mode)
    record = manager.get_record("photo-to-3d")
    assert record is not None
    for text in (
        manager.describe_for_prompt(), manager.describe_pinned_for_prompt(),
        manager.build_explicit_skill_injection([record]), manager.get_status_summary()["mode_notice"],
    ):
        assert "switch_mode" in text and "/mode reverie" in text
    assert manager.pinned_names() == ["photo-to-3d"]
    bridge = ReverieSdkBridge()
    bridge.interface = SimpleNamespace(skills_manager=manager)
    assert bridge.skills_payload()["mode"] == mode
    assert bridge.skills_payload()["pinned"]["names"] == ["photo-to-3d"]
    if mode == "writer":
        assert "skill_lookup is unavailable" in manager.describe_for_prompt()
        assert 'Call `skill_lookup(operation="inspect")`' not in manager.describe_pinned_for_prompt()
    else:
        tool = SkillLookupTool({"skills_manager": manager})
        for operation in ("list", "search", "inspect"):
            result = tool.execute(operation=operation, query="photo-to-3d", skill_name="photo-to-3d")
            assert result.success and "switch_mode" in result.output


def test_agent_mode_switch_immediately_refreshes_skill_discovery_and_keeps_pins(tmp_path, monkeypatch):
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: tmp_path))
    manager = SkillsManager(tmp_path / "project", tmp_path / "app")
    manager.set_active_mode("writer")
    manager.pin_skill("photo-to-3d")
    assert manager.get_record("reverie-engine") is None
    agent = SimpleNamespace(mode="writer")
    agent.update_mode = lambda mode: setattr(agent, "mode", mode)
    tool = ModeSwitchTool({"agent": agent, "skills_manager": manager})
    assert tool.execute(mode="reverie-gamer").success
    assert manager.active_mode == "reverie-gamer"
    assert manager.get_record("reverie-engine") is not None
    assert manager.get_mode_notice() == ""
    assert manager.pinned_names() == ["photo-to-3d"]
