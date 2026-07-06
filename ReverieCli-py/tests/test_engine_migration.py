import importlib

import pytest

from reverie.skills_manager import SkillsManager
from reverie.tools.registry import get_registered_tool_classes
from reverie.tools.reverie_engine import ReverieEngineTool


def test_reverie_engine_is_canonical_and_legacy_package_removed():
    engine = importlib.import_module("reverie.engine")

    assert engine.ENGINE_NAME == "reverie_engine"
    with pytest.raises(ModuleNotFoundError):
        importlib.import_module("reverie." + "engine" + "_lite")


def test_legacy_engine_tool_is_not_registered():
    names = {tool.name for tool in get_registered_tool_classes(include_hidden=True)}

    assert "reverie_engine" in names
    assert "reverie_engine" + "_lite" not in names


def test_reverie_engine_skill_is_gamer_only(tmp_path) -> None:
    manager = SkillsManager(project_root=tmp_path, app_root=tmp_path)

    assert manager.get_record("reverie-engine", force_refresh=True) is None
    manager.set_active_mode("reverie-gamer")
    record = manager.get_record("reverie-engine", force_refresh=True)

    assert record is not None
    assert "unified built-in Reverie Engine" in record.description
    assert record.skill_dir.name == "reverie-engine"
    assert (record.skill_dir / "references" / "tool-actions.md").is_file()


def test_reverie_engine_tool_exposes_scope_and_builtin_renpy_actions(tmp_path) -> None:
    script = tmp_path / "game" / "script.rpy"
    script.parent.mkdir()
    script.write_text(
        'define e = Character("Eileen")\n\nlabel start:\n    e "Hello."\n    return\n',
        encoding="utf-8",
    )
    tool = ReverieEngineTool({"project_root": tmp_path})

    scope = tool.execute(
        action="assess_scope",
        dimension="3D",
        genre="action_rpg",
        quality_tier="AA",
        world_structure="open_world",
    )
    outline = tool.execute(action="outline_renpy", script_path=str(script))

    assert scope.success is True
    assert scope.data["supported"] is False
    assert outline.success is True
    assert outline.data["counts"]["labels"] == 1
    assert outline.data["counts"]["characters"] == 1


def test_reverie_engine_tool_accepts_nested_scope_and_infers_card_project(tmp_path) -> None:
    tool = ReverieEngineTool({"project_root": tmp_path})

    scope = tool.execute(
        action="assess_scope",
        data={"dimension": "2D", "genre": "card_battle", "quality_tier": "indie"},
    )
    created = tool.execute(
        action="create_project",
        output_dir="CardBattle",
        project_name="CardBattle",
        overwrite=True,
    )

    assert scope.success is True
    assert scope.data["genre"] == "card_game"
    assert created.success is True
    assert created.data["genre"] == "card_game"

    smoke = tool.execute(action="run_smoke", output_path=str(tmp_path / "CardBattle"))
    validate = tool.execute(action="validate_project", project_dir=str(tmp_path / "CardBattle"))

    assert smoke.success is True
    assert smoke.data["success"] is True
    assert validate.success is True
    assert validate.data["validation"]["valid"] is True
