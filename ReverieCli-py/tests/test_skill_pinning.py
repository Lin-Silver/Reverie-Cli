"""Pinned skills: session-scoped enforcement across the manager, tool, bridge, and prompt."""

import io
from pathlib import Path
from types import SimpleNamespace

from rich.console import Console

from reverie.cli.input_handler import InputHandler
from reverie.cli.theme import DECO, THEME
from reverie.sdk_bridge import ReverieSdkBridge
from reverie.skills_manager import SkillsManager
from reverie.tools.skill_lookup import SkillLookupTool


def _write_skill(root: Path, name: str, description: str, body: str = "") -> Path:
    skill_dir = root / name
    skill_dir.mkdir(parents=True, exist_ok=True)
    (skill_dir / "SKILL.md").write_text(
        f"---\nname: {name}\ndescription: {description}\n---\n\n{body or f'{name} workflow body.'}\n",
        encoding="utf-8",
    )
    return skill_dir


def _manager(tmp_path: Path, *skills: tuple[str, str]) -> SkillsManager:
    app_root = tmp_path / "app"
    project_root = tmp_path / "project"
    project_root.mkdir(parents=True, exist_ok=True)
    skills_root = project_root / ".agents" / "skills"
    for name, description in skills:
        _write_skill(skills_root, name, description)
    manager = SkillsManager(project_root=project_root, app_root=app_root)
    manager.scan()
    return manager


def test_pinning_promotes_one_skill_into_a_mandatory_prompt_block(tmp_path: Path) -> None:
    manager = _manager(
        tmp_path,
        ("mesh-drafting", "Rebuild a photographed subject as Three.js code."),
        ("release-notes", "Draft release notes from the commit log."),
    )

    assert manager.has_pinned_skills is False
    assert manager.describe_pinned_for_prompt() == ""

    outcome = manager.pin_skill("mesh-drafting")

    assert outcome["status"] == "pinned"
    assert outcome["name"] == "mesh-drafting"
    assert manager.has_pinned_skills is True
    assert manager.pinned_names() == ["mesh-drafting"]

    block = manager.describe_pinned_for_prompt()
    assert "### Pinned skills (mandatory)" in block
    assert "mesh-drafting: Rebuild a photographed subject as Three.js code." in block
    assert "skill_lookup" in block
    # A pin must not drag the other skills' bodies into the prompt.
    assert "release-notes" not in block

    catalog = manager.describe_for_prompt()
    assert "### Pinned skills (mandatory)" in catalog
    assert "- mesh-drafting [PINNED]:" in catalog
    assert "- release-notes:" in catalog


def test_pinning_is_idempotent_capped_and_releasable(tmp_path: Path) -> None:
    manager = _manager(tmp_path, *[(f"skill-{index}", f"Skill {index}.") for index in range(6)])

    assert manager.max_pinned_skills == 4
    assert manager.pin_skill("skill-0")["status"] == "pinned"
    assert manager.pin_skill("skill-0")["status"] == "already"
    assert manager.pinned_names() == ["skill-0"]

    for index in range(1, 4):
        assert manager.pin_skill(f"skill-{index}")["status"] == "pinned"

    full = manager.pin_skill("skill-4")
    assert full["status"] == "full"
    assert manager.pinned_names() == ["skill-0", "skill-1", "skill-2", "skill-3"]

    assert manager.pin_skill("nope")["status"] == "missing"
    assert manager.unpin_skill("nope")["status"] == "missing"
    assert manager.unpin_skill("skill-1") == {"status": "unpinned", "name": "skill-1"}
    assert manager.pinned_names() == ["skill-0", "skill-2", "skill-3"]

    released = manager.clear_pinned_skills()
    assert released == ["skill-0", "skill-2", "skill-3"]
    assert manager.has_pinned_skills is False
    assert manager.describe_pinned_for_prompt() == ""


def test_pinning_outranks_a_skill_that_disables_implicit_invocation(tmp_path: Path) -> None:
    app_root = tmp_path / "app"
    project_root = tmp_path / "project"
    skill_dir = _write_skill(project_root / ".agents" / "skills", "manual-only", "Only run when asked.")
    (skill_dir / "agents").mkdir()
    (skill_dir / "agents" / "openai.yaml").write_text(
        "policy:\n  allow_implicit_invocation: false\n",
        encoding="utf-8",
    )

    manager = SkillsManager(project_root=project_root, app_root=app_root)
    assert "manual-only" not in manager.describe_for_prompt(force_refresh=True)

    assert manager.pin_skill("manual-only")["status"] == "pinned"
    catalog = manager.describe_for_prompt()

    # An explicit pin is a user instruction, so it outranks the skill's own policy.
    assert "- manual-only [PINNED]:" in catalog
    assert "### Pinned skills (mandatory)" in catalog


def test_a_pin_whose_skill_disappears_is_reported_as_stale(tmp_path: Path) -> None:
    manager = _manager(tmp_path, ("temporary", "A skill that will be deleted."))
    assert manager.pin_skill("temporary")["status"] == "pinned"

    skill_md = manager.get_record("temporary").path_to_skill_md
    skill_md.unlink()
    manager.scan()

    state = manager.pinned_state()
    assert state["names"] == []
    assert state["unresolved"] == ["temporary"]
    assert manager.pinned_names() == ["temporary"]

    block = manager.describe_pinned_for_prompt()
    assert "pinned but no longer present on disk" in block
    assert "temporary" in block

    assert manager.unpin_skill("temporary")["status"] == "unpinned"
    assert manager.describe_pinned_for_prompt() == ""


def test_skill_lookup_marks_pinned_skills_in_list_and_inspect(tmp_path: Path) -> None:
    manager = _manager(
        tmp_path,
        ("mesh-drafting", "Rebuild a photographed subject as Three.js code."),
        ("release-notes", "Draft release notes from the commit log."),
    )
    manager.pin_skill("mesh-drafting")
    tool = SkillLookupTool({"skills_manager": manager, "project_root": tmp_path / "project"})

    listing = tool.execute(operation="list")
    assert listing.success is True
    assert "mesh-drafting [PINNED]" in listing.output
    assert "release-notes [PINNED]" not in listing.output
    assert "Pinned skills are mandatory for every turn" in listing.output
    assert listing.data["pinned"] == ["mesh-drafting"]
    # Built-in skills share the listing, so assert on the two this test wrote.
    rows = {row["name"]: row["pinned"] for row in listing.data["items"]}
    assert rows["mesh-drafting"] is True
    assert rows["release-notes"] is False

    pinned = tool.execute(operation="inspect", skill_name="mesh-drafting")
    assert "Skill: mesh-drafting [PINNED]" in pinned.output
    assert "the user requires this skill on every turn" in pinned.output
    assert pinned.data["pinned"] is True

    other = tool.execute(operation="inspect", skill_name="release-notes")
    assert "Skill: release-notes\n" in other.output
    assert other.data["pinned"] is False


def test_bridge_reports_and_mutates_the_pin_set_for_the_desktop(tmp_path: Path) -> None:
    manager = _manager(
        tmp_path,
        ("mesh-drafting", "Rebuild a photographed subject as Three.js code."),
        ("release-notes", "Draft release notes from the commit log."),
    )
    bridge = ReverieSdkBridge()
    bridge.project_root = tmp_path.resolve()
    bridge.interface = SimpleNamespace(skills_manager=manager, agent=None)

    listing = bridge.dispatch({"id": "list", "action": "listSkills", "payload": {}})
    assert listing["type"] == "skills"
    assert listing["skills"]["count"] == len(listing["skills"]["records"])
    assert {"mesh-drafting", "release-notes"} <= {record["name"] for record in listing["skills"]["records"]}
    assert listing["skills"]["pinned"] == {"max": 4, "keys": [], "names": [], "unresolved": []}
    assert all(record["pinned"] is False for record in listing["skills"]["records"])

    # A `$name` mention is what the composer sends, so the leading sigil is stripped.
    pinned = bridge.dispatch({"id": "pin", "action": "pinSkill", "payload": {"skill": "$mesh-drafting"}})
    assert pinned["type"] == "skill.pinned"
    assert pinned["status"] == "pinned"
    assert pinned["name"] == "mesh-drafting"
    assert pinned["skills"]["pinned"]["names"] == ["mesh-drafting"]
    rows = {record["name"]: record["pinned"] for record in pinned["skills"]["records"]}
    assert rows["mesh-drafting"] is True
    assert rows["release-notes"] is False

    assert bridge.dispatch({"id": "again", "action": "pinSkill", "payload": {"skill": "mesh-drafting"}})["status"] == "already"
    assert bridge.dispatch({"id": "nope", "action": "pinSkill", "payload": {"name": "ghost"}})["status"] == "missing"

    detail = bridge.dispatch({"id": "inspect", "action": "inspectSkill", "payload": {"skill": "mesh-drafting"}})
    assert detail["type"] == "skill.inspect"
    assert detail["record"]["pinned"] is True
    assert "mesh-drafting workflow body." in detail["record"]["body"]
    assert detail["record"]["metadata"]["name"] == "mesh-drafting"
    assert bridge.dispatch({"id": "gone", "action": "inspectSkill", "payload": {"skill": "ghost"}})["record"] is None

    released = bridge.dispatch({"id": "clear", "action": "clearPinnedSkills", "payload": {}})
    assert released["status"] == "cleared"
    assert released["released"] == ["mesh-drafting"]
    assert released["skills"]["pinned"]["names"] == []


def test_bridge_unpin_needs_a_name_and_reports_an_unknown_one(tmp_path: Path) -> None:
    manager = _manager(tmp_path, ("mesh-drafting", "Rebuild a photographed subject as Three.js code."))
    bridge = ReverieSdkBridge()
    bridge.project_root = tmp_path.resolve()
    bridge.interface = SimpleNamespace(skills_manager=manager, agent=None)

    bridge.dispatch({"id": "pin", "action": "pinSkill", "payload": {"skill": "mesh-drafting"}})

    try:
        bridge.dispatch({"id": "blank", "action": "unpinSkill", "payload": {"skill": "   "}})
    except ValueError as error:
        assert "required" in str(error)
    else:  # pragma: no cover - the guard above must fire
        raise AssertionError("An empty skill name must be rejected, not silently ignored.")

    assert bridge.dispatch({"id": "ghost", "action": "unpinSkill", "payload": {"skill": "ghost"}})["status"] == "missing"

    dropped = bridge.dispatch({"id": "drop", "action": "unpinSkill", "payload": {"skill": "mesh-drafting"}})
    assert dropped["status"] == "unpinned"
    assert dropped["skills"]["pinned"]["names"] == []


def test_bridge_pin_rebuilds_the_prompt_so_the_next_turn_carries_it(tmp_path: Path) -> None:
    manager = _manager(tmp_path, ("mesh-drafting", "Rebuild a photographed subject as Three.js code."))
    refreshes: list[str] = []
    bridge = ReverieSdkBridge()
    bridge.project_root = tmp_path.resolve()
    bridge.interface = SimpleNamespace(
        skills_manager=manager,
        agent=object(),
        _refresh_agent_prompt_guidance=lambda: refreshes.append("refreshed"),
    )

    bridge.dispatch({"id": "pin", "action": "pinSkill", "payload": {"skill": "mesh-drafting"}})
    bridge.dispatch({"id": "clear", "action": "clearPinnedSkills", "payload": {}})

    # Both mutations have to reach the live agent; a pin the model never sees is a no-op.
    assert refreshes == ["refreshed", "refreshed"]


def _handler() -> tuple[InputHandler, io.StringIO]:
    stream = io.StringIO()
    console = Console(file=stream, width=120, force_terminal=False, no_color=True, legacy_windows=False)
    return InputHandler(console), stream


def test_a_pinned_skill_is_drawn_as_a_tag_inside_the_input_prompt() -> None:
    handler, stream = _handler()
    handler.set_prompt_tags(["photo-to-3d"])

    chip = f"{DECO.TAG_OPEN}photo-to-3d{DECO.TAG_CLOSE}"
    assert handler._prompt_tag_labels() == [chip]
    assert chip in handler._plain_prompt_text("reverie> ")
    assert handler._plain_prompt_text("reverie> ", is_continuation=True) == ""

    handler._render_prompt("reverie> ")
    assert chip in stream.getvalue()

    # prompt_toolkit gets fragments rather than a string so the chip can carry a fill.
    fragments = handler._prompt_toolkit_message("reverie> ")
    assert isinstance(fragments, list)
    styles = {style for style, text in fragments if text == chip}
    assert styles == {f"bold fg:{THEME.TEXT_PRIMARY} bg:{THEME.PURPLE_DEEP}"}


def test_prompt_tags_are_deduped_trimmed_and_clearable() -> None:
    handler, _ = _handler()

    handler.set_prompt_tags(["photo-to-3d", " photo-to-3d ", "", None, "release-notes"])
    assert handler.prompt_tags == ["photo-to-3d", "release-notes"]
    assert handler._plain_prompt_text("reverie> ").count(DECO.TAG_OPEN) == 2

    handler.set_prompt_tags(None)
    assert handler.prompt_tags == []
    assert handler._prompt_tag_labels() == []
    # With nothing pinned the prompt stays a plain string, exactly as before the feature.
    assert handler._prompt_toolkit_message("reverie> ") == handler._plain_prompt_text("reverie> ")
