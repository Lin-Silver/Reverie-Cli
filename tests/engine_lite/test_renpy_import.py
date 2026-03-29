from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory
import json

import pytest
import yaml

from reverie.engine_lite.app import EngineLiteApp, RuntimeProfile, load_project_scene
from reverie.engine_lite.project import create_project_skeleton
from reverie.engine_lite.renpy_import import compile_renpy_script, import_renpy_script, parse_renpy_script


def test_compile_renpy_script_builds_dialogue_graph_with_menu_and_jump() -> None:
    sample = """
define e = Character("Eileen")
define l = Character("Lucy")

label start:
    e "Hello there."
    menu:
        "Where do we go?"
        "Library":
            jump library
        "Stay":
            l "Then we stay."
    "After menu."
    return

label library:
    "Books everywhere."
"""

    parsed = parse_renpy_script(sample, conversation_id="Test Route")
    compiled = compile_renpy_script(parsed)
    conversation = compiled["conversation"]
    nodes = conversation["nodes"]

    assert parsed.entry_label == "start"
    assert conversation["start"]
    assert conversation["cast"]["Eileen"]["renpy_alias"] == "e"
    assert conversation["cast"]["Lucy"]["renpy_alias"] == "l"

    start_node = nodes[conversation["start"]]
    assert start_node["speaker"] == "Eileen"
    assert start_node["text"] == "Hello there."

    menu_node = nodes[start_node["next"]]
    assert menu_node["text"] == "Where do we go?"
    assert [choice["text"] for choice in menu_node["choices"]] == ["Library", "Stay"]

    library_choice = next(choice for choice in menu_node["choices"] if choice["text"] == "Library")
    stay_choice = next(choice for choice in menu_node["choices"] if choice["text"] == "Stay")
    assert nodes[library_choice["next"]]["text"] == "Books everywhere."
    assert nodes[stay_choice["next"]]["speaker"] == "Lucy"
    assert compiled["warnings"] == []


def test_compile_renpy_script_maps_conditions_and_stage_commands() -> None:
    sample = """
label start:
    $ menu_var = 0
    scene bg beach
    show eileen happy at left
    play music "theme.ogg"
    menu:
        "Increment":
            $ menu_var += 1
            jump start
        "Done" if menu_var >= 2:
            "Ready."
            return
"""

    parsed = parse_renpy_script(sample, conversation_id="Condition Route")
    compiled = compile_renpy_script(parsed)
    conversation = compiled["conversation"]
    start_node = conversation["nodes"][conversation["start"]]
    second_node = conversation["nodes"][start_node["next"]]
    third_node = conversation["nodes"][second_node["next"]]
    fourth_node = conversation["nodes"][third_node["next"]]
    menu_node = conversation["nodes"][fourth_node["next"]]
    done_choice = next(choice for choice in menu_node["choices"] if choice["text"] == "Done")

    assert start_node["auto_advance"] is True
    assert start_node["effects_on_enter"]["set_notes"]["menu_var"] == 0
    assert second_node["effects_on_enter"]["renpy_commands"][0]["kind"] == "scene"
    assert third_node["effects_on_enter"]["renpy_commands"][0]["kind"] == "show"
    assert fourth_node["effects_on_enter"]["renpy_commands"][0]["kind"] == "play"
    assert done_choice["conditions"]["requires_notes_min"]["menu_var"] == 2
    assert done_choice["renpy_condition"] == "menu_var >= 2"


def test_import_renpy_script_updates_dialogue_and_autostart_scene() -> None:
    sample = """
define a = Character("Ariel")

label start:
    a "Welcome to Reverie."
    menu:
        "Choose a route"
        "Sunrise":
            jump sunrise
        "Stay":
            "We stay here."
    return

label sunrise:
    "Morning route unlocked."
"""

    with TemporaryDirectory() as temp_dir:
        project_root = Path(temp_dir) / "galgame_project"
        create_project_skeleton(
            project_root,
            project_name="RenPy Import Test",
            dimension="2D",
            sample_name="galgame_live2d",
            genre="galgame",
            overwrite=True,
        )

        script_path = project_root / "imports" / "route.rpy"
        script_path.parent.mkdir(parents=True, exist_ok=True)
        script_path.write_text(sample.strip(), encoding="utf-8")

        result = import_renpy_script(
            project_root,
            script_path,
            conversation_id="route_alpha",
            entry_label="start",
            autostart=True,
        )

        assert result["conversation_id"] == "route_alpha"
        assert result["node_count"] >= 3
        assert result["autostart_updated"] is True
        assert result["stage_scene_updated"] is True

        dialogue_payload = yaml.safe_load((project_root / "data/content/dialogue.yaml").read_text(encoding="utf-8"))
        conversation = dialogue_payload["conversations"]["route_alpha"]
        assert conversation["start"] == result["start_node"]
        assert conversation["nodes"][result["start_node"]]["speaker"] == "Ariel"

        scene_payload = json.loads((project_root / "data/scenes/main.relscene.json").read_text(encoding="utf-8"))
        assert scene_payload["metadata"]["autostart_conversation"] == "route_alpha"
        scene_child_names = [child["name"] for child in scene_payload["children"]]
        assert "RenPyBackground" in scene_child_names
        assert "RenPyCharacterLeft" in scene_child_names


def test_import_renpy_script_resolves_relative_paths_from_current_working_directory(monkeypatch: pytest.MonkeyPatch) -> None:
    sample = """
label start:
    "Imported from outside the project root."
"""

    with TemporaryDirectory() as temp_dir:
        temp_root = Path(temp_dir)
        project_root = temp_root / "game_project"
        external_root = temp_root / "shared_scripts"
        original_cwd = Path.cwd()
        create_project_skeleton(
            project_root,
            project_name="RenPy Relative Import Test",
            dimension="2D",
            sample_name="galgame_live2d",
            genre="galgame",
            overwrite=True,
        )

        script_path = external_root / "story.rpy"
        script_path.parent.mkdir(parents=True, exist_ok=True)
        script_path.write_text(sample.strip(), encoding="utf-8")

        monkeypatch.chdir(external_root)
        result = import_renpy_script(project_root, Path("story.rpy"), conversation_id="external_story")
        monkeypatch.chdir(original_cwd)

        dialogue_payload = yaml.safe_load((project_root / "data/content/dialogue.yaml").read_text(encoding="utf-8"))
        assert result["conversation_id"] == "external_story"
        assert dialogue_payload["conversations"]["external_story"]["start"] == result["start_node"]


def test_imported_renpy_conditions_and_stage_commands_run() -> None:
    sample = """
define e = Character("Eileen")

label start:
    $ menu_var = 0
    scene bg beach
    show eileen happy at left
    play music "opening_theme.ogg"
    jump loop

label loop:
    menu:
        "Value: [menu_var]":
            pass
        "Increment":
            $ menu_var += 1
            hide eileen
            scene bg room
            jump loop
        "Done" if menu_var >= 2:
            e "Ready."
            return
"""

    with TemporaryDirectory() as temp_dir:
        project_root = Path(temp_dir) / "runtime_renpy_project"
        create_project_skeleton(
            project_root,
            project_name="RenPy Runtime Test",
            dimension="2D",
            sample_name="galgame_live2d",
            genre="galgame",
            overwrite=True,
        )

        script_path = project_root / "imports" / "runtime_route.rpy"
        script_path.parent.mkdir(parents=True, exist_ok=True)
        script_path.write_text(sample.strip(), encoding="utf-8")

        import_renpy_script(
            project_root,
            script_path,
            conversation_id="runtime_route",
            entry_label="start",
            autostart=True,
        )

        scene_tree, _, config = load_project_scene(project_root)
        app = EngineLiteApp(scene_tree, profile=RuntimeProfile(headless=True), config=config)
        gameplay = app.gameplay

        assert gameplay is not None
        gameplay.bootstrap()

        background_node = scene_tree.find("RenPyBackground")
        left_node = scene_tree.find("RenPyCharacterLeft")
        assert background_node is not None
        assert left_node is not None

        view = gameplay.get_active_dialogue_view()
        assert [choice["text"] for choice in view["choices"]] == ["Value: 0", "Increment"]
        assert background_node.get_component("Image").texture == "bg beach"  # type: ignore[union-attr]
        assert left_node.get_component("Image").texture == "eileen happy"  # type: ignore[union-attr]
        assert any(event["event"] == "renpy_audio_play" for event in app.telemetry.events)

        gameplay.advance_dialogue(choice_index=1)
        view = gameplay.get_active_dialogue_view()
        assert [choice["text"] for choice in view["choices"]] == ["Value: 1", "Increment"]
        assert background_node.get_component("Image").texture == "bg room"  # type: ignore[union-attr]
        assert left_node.get_component("UIControl").visible is False  # type: ignore[union-attr]

        gameplay.advance_dialogue(choice_index=1)
        view = gameplay.get_active_dialogue_view()
        assert [choice["text"] for choice in view["choices"]] == ["Value: 2", "Increment", "Done"]
