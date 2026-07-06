from __future__ import annotations

from pathlib import Path
import json
import yaml

from reverie.engine import assess_project_scope, inspect_legacy_project, migrate_legacy_project, run_project_smoke
from reverie.gamer.prompt_compiler import compile_game_prompt
from reverie.gamer.runtime_adapters import ReverieEngineRuntimeAdapter
from reverie.gamer.runtime_registry import discover_runtime_profiles, select_runtime_profile


def test_closed_commercial_runtime_requests_fall_back_to_unified_engine(tmp_path: Path) -> None:
    request = compile_game_prompt(
        "Use Unity for a third-person 3D action RPG slice.",
        project_name="Unified Runtime Slice",
        requested_runtime="unity",
    )
    selection = select_runtime_profile(request, project_root=tmp_path, requested_runtime="unity")

    assert request["runtime_preferences"]["requested_runtime"] == ""
    assert request["runtime_preferences"]["unsupported_requested_runtime"] == "unity"
    assert selection["selected_runtime"] == "reverie_engine"
    assert selection["unified_runtime"] is True


def test_discovered_profiles_expose_only_reverie_engine(tmp_path: Path) -> None:
    profiles = discover_runtime_profiles(tmp_path)

    assert [item["id"] for item in profiles] == ["reverie_engine"]
    assert profiles[0]["external"] is False
    assert "godot-migration" in profiles[0]["capabilities"]
    assert "o3de-migration" in profiles[0]["capabilities"]


def test_legacy_runtime_request_is_recorded_as_migration_source(tmp_path: Path) -> None:
    request = compile_game_prompt(
        "Use Godot patterns for a focused third-person game.",
        project_name="Unified Slice",
        requested_runtime="godot",
    )
    selection = select_runtime_profile(request, project_root=tmp_path, requested_runtime="godot")

    assert request["runtime_preferences"]["preferred_runtime"] == "reverie_engine"
    assert request["runtime_preferences"]["legacy_source"] == "godot"
    assert selection["selected_runtime"] == "reverie_engine"
    assert selection["legacy_source"] == "godot"


def test_godot_project_migrates_portable_assets_into_reverie_engine(tmp_path: Path) -> None:
    source = tmp_path / "godot-source"
    source.mkdir()
    (source / "project.godot").write_text("config_version=5\n", encoding="utf-8")
    (source / "main.tscn").write_text("[gd_scene format=3]\n", encoding="utf-8")
    (source / "player.gd").write_text("extends CharacterBody3D\n", encoding="utf-8")
    (source / "hero.glb").write_bytes(b"glTF")
    target = tmp_path / "reverie-target"

    inspection = inspect_legacy_project(source)
    result = migrate_legacy_project(source, target, project_name="Migrated Hero")

    assert inspection["source_engine"] == "godot"
    assert inspection["details"]["scene_count"] == 1
    assert result["target_engine"] == "reverie_engine"
    assert (target / "data" / "config" / "engine.yaml").exists()
    assert (target / "assets" / "imported" / "godot" / "hero.glb").exists()
    assert not (target / "engine" / "godot").exists()


def test_godot_scene_and_script_contracts_become_runnable_reverie_content(tmp_path: Path) -> None:
    source = tmp_path / "godot-source"
    source.mkdir()
    (source / "project.godot").write_text(
        """config_version=5

[application]
config/name="Godot Heritage"
run/main_scene="res://main.tscn"

[input]
move_left={"deadzone": 0.5}
""",
        encoding="utf-8",
    )
    (source / "player.gd").write_text(
        """extends CharacterBody3D
class_name HeritagePlayer
signal health_changed(value)
@export var speed = 6.0
func _physics_process(delta):
    pass
""",
        encoding="utf-8",
    )
    (source / "main.tscn").write_text(
        """[gd_scene load_steps=2 format=3]

[ext_resource type="Script" path="res://player.gd" id="1"]

[node name="Main" type="Node3D"]

[node name="Player" type="CharacterBody3D" parent="." groups=["player"]]
position = Vector3(1, 2, 3)
script = ExtResource("1")

[node name="Camera" type="Camera3D" parent="Player"]
fov = 68.0
""",
        encoding="utf-8",
    )
    target = tmp_path / "reverie-target"

    result = migrate_legacy_project(source, target, project_name="Converted Godot")

    imported_scene = target / "data" / "scenes" / "imported_godot_main.relscene.json"
    script_contract = target / "data" / "migration" / "godot_scripts.json"
    project_contract = target / "data" / "migration" / "godot_project.json"
    assert imported_scene.exists()
    assert script_contract.exists()
    assert project_contract.exists()
    scene = json.loads(imported_scene.read_text(encoding="utf-8"))
    player = next(item for item in scene["children"] if item["name"] == "Player")
    component_types = {item["type"] for item in player["components"]}
    assert {"Transform", "KinematicBody", "Collider", "ScriptBehaviour"} <= component_types
    assert player["groups"] == ["player"]
    scripts = json.loads(script_contract.read_text(encoding="utf-8"))
    assert scripts["scripts"][0]["class_name"] == "HeritagePlayer"
    assert scripts["scripts"][0]["functions"] == ["_physics_process"]
    assert scripts["scripts"][0]["signals"] == ["health_changed"]
    smoke = run_project_smoke(target, scene_path=imported_scene)
    assert smoke["success"] is True
    assert any(item["kind"] == "godot_scene" for item in result["converted_content"])


def test_o3de_project_is_migration_input_not_runtime(tmp_path: Path) -> None:
    source = tmp_path / "o3de-source"
    source.mkdir()
    (source / "project.json").write_text(
        json.dumps({"project_name": "Legacy O3DE", "gem_names": ["GameplayGem"]}),
        encoding="utf-8",
    )
    (source / "Gems" / "GameplayGem").mkdir(parents=True)
    (source / "Gems" / "GameplayGem" / "gem.json").write_text("{}", encoding="utf-8")

    inspection = inspect_legacy_project(source)

    assert inspection["source_engine"] == "o3de"
    assert inspection["details"]["gems"] == ["GameplayGem"]
    assert inspection["target_engine"] == "reverie_engine"


def test_o3de_gems_registry_and_scripts_become_reverie_contracts(tmp_path: Path) -> None:
    source = tmp_path / "o3de-source"
    (source / "Gems" / "GameplayGem" / "Scripts").mkdir(parents=True)
    (source / "Registry").mkdir()
    (source / "project.json").write_text(
        json.dumps({"project_name": "Legacy O3DE", "project_id": "legacy.o3de", "gem_names": ["GameplayGem"]}),
        encoding="utf-8",
    )
    (source / "Gems" / "GameplayGem" / "gem.json").write_text(
        json.dumps({"gem_name": "GameplayGem", "version": "1.2.0"}),
        encoding="utf-8",
    )
    (source / "Registry" / "game.setreg").write_text(
        json.dumps({"Amazon": {"AzCore": {"Bootstrap": {"project_path": "Legacy O3DE"}}}}),
        encoding="utf-8",
    )
    (source / "Gems" / "GameplayGem" / "Scripts" / "player.lua").write_text(
        "function GameplayPlayer:OnActivate()\nend\nfunction GameplayPlayer:OnTick(delta)\nend\n",
        encoding="utf-8",
    )
    target = tmp_path / "reverie-target"

    result = migrate_legacy_project(source, target, project_name="Converted O3DE")

    contract_path = target / "data" / "migration" / "o3de_project_contract.json"
    scripts_path = target / "data" / "migration" / "o3de_scripts.json"
    archetype_path = target / "data" / "prefabs" / "o3de_gameplaygem.relarchetype.json"
    assert contract_path.exists()
    assert scripts_path.exists()
    assert archetype_path.exists()
    contract = json.loads(contract_path.read_text(encoding="utf-8"))
    assert contract["project"]["project_id"] == "legacy.o3de"
    assert contract["gems"][0]["gem_name"] == "GameplayGem"
    assert contract["registry"][0]["relative_path"] == "Registry/game.setreg"
    scripts = json.loads(scripts_path.read_text(encoding="utf-8"))
    assert scripts["scripts"][0]["functions"] == ["GameplayPlayer:OnActivate", "GameplayPlayer:OnTick"]
    archetype = json.loads(archetype_path.read_text(encoding="utf-8"))
    assert archetype["archetype_id"] == "o3de.GameplayGem"
    assert any(item["kind"] == "o3de_gem" for item in result["converted_content"])


def test_scope_gate_rejects_only_declared_large_production_classes() -> None:
    focused = assess_project_scope(dimension="3D", genre="shooter", quality_tier="aa", world_structure="hub")
    open_world = assess_project_scope(dimension="3D", genre="action_rpg", quality_tier="aa", world_structure="open_world")
    aaa = assess_project_scope(dimension="2D", genre="platformer", quality_tier="aaa", world_structure="focused")

    assert focused["supported"] is True
    assert open_world["supported"] is False
    assert aaa["supported"] is False


def test_unified_runtime_adapter_is_the_only_public_adapter() -> None:
    assert ReverieEngineRuntimeAdapter().runtime_id == "reverie_engine"


def test_gamer_runtime_adapter_preserves_non_sample_game_family(tmp_path: Path) -> None:
    adapter = ReverieEngineRuntimeAdapter()
    project = tmp_path / "card-game"
    request = {
        "experience": {"dimension": "2D"},
        "creative_target": {"primary_genre": "card_game"},
    }

    created = adapter.create_project(
        project,
        project_name="Card Game",
        game_request=request,
        blueprint={},
        overwrite=True,
    )
    config = yaml.safe_load((project / "data" / "config" / "engine.yaml").read_text(encoding="utf-8"))
    rules = yaml.safe_load((project / "data" / "content" / "rules.yaml").read_text(encoding="utf-8"))
    validation = adapter.validate_project(project)

    assert created["template"] == "card_game_foundation"
    assert config["project"]["genre"] == "card_game"
    assert rules["primary_action"] == "draw_card"
    assert validation["valid"] is True
