"""Project scaffolding helpers for Reverie Engine."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict
import json
import zipfile

import yaml

from .config import ENGINE_BRAND, ENGINE_NAME, build_engine_config as build_engine_profile, load_engine_config
from .live2d import Live2DManager
from .localization import LocalizationManager
from .modeling import inspect_modeling_workspace, materialize_modeling_workspace
from .samples import get_sample_definition, list_samples
from .schemas import (
    ENGINE_CONFIG_SCHEMA,
    GAMEPLAY_MANIFEST_SCHEMA,
    validate_engine_config_schema,
    validate_gameplay_manifest_schema,
)
from .serialization import validate_scene_document


DEFAULT_STRUCTURE = [
    "assets/animations",
    "assets/audio",
    "assets/live2d",
    "assets/models",
    "assets/models/source",
    "assets/models/runtime",
    "assets/shaders",
    "assets/textures",
    "assets/ui",
    "data/config",
    "data/content",
    "data/live2d",
    "data/models",
    "data/localization",
    "data/prefabs",
    "data/scenes",
    "docs",
    "playtest/logs",
    "playtest/renders/models",
    "save_data",
    "src/game",
    "src/game/behaviours",
    "src/game/scripts",
    "telemetry",
    "tests/integration",
    "tests/smoke",
    "tests/unit",
    "web",
]


def _safe_write(path: Path, content: str, overwrite: bool) -> bool:
    if path.exists() and not overwrite:
        return False
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    return True


def _safe_write_json(path: Path, payload: Dict[str, Any], overwrite: bool) -> bool:
    return _safe_write(path, json.dumps(payload, indent=2, ensure_ascii=False), overwrite)


def _safe_write_yaml(path: Path, payload: Dict[str, Any], overwrite: bool) -> bool:
    return _safe_write(path, yaml.safe_dump(payload, sort_keys=False, allow_unicode=True), overwrite)


def _safe_write_payload(path: Path, payload: Any, overwrite: bool) -> bool:
    if isinstance(payload, dict):
        if path.suffix.lower() == ".json":
            return _safe_write_json(path, payload, overwrite)
        return _safe_write_yaml(path, payload, overwrite)
    return _safe_write(path, str(payload), overwrite)


def build_bootstrap() -> str:
    return (
        "from pathlib import Path\n"
        "from reverie.engine import run_project\n\n\n"
        "def run_game(headless: bool = False) -> dict:\n"
        "    project_root = Path(__file__).resolve().parents[2]\n"
        "    return run_project(project_root, headless=headless)\n\n\n"
        "if __name__ == '__main__':\n"
        "    run_game()\n"
    )


def build_engine_config(project_name: str, dimension: str, sample_name: str | None = None, genre: str | None = None) -> Dict[str, Any]:
    profile = build_engine_profile(project_name, dimension, sample_name=sample_name, genre=genre)
    profile["content"] = {
        "scene_format": ".relscene.json",
        "prefab_format": ".relprefab.json",
        "config_format": ".yaml",
        "data_driven": True,
        "content_bundle_paths": [
            "data/content",
            "data/live2d",
            "data/models",
        ],
    }
    return profile


def build_gameplay_manifest(project_name: str, dimension: str, genre: str) -> Dict[str, Any]:
    return {
        "project": project_name,
        "dimension": dimension,
        "genre": genre,
        "systems": {
            "dialogue": genre in {"adventure", "action_rpg", "galgame"},
            "quests": genre in {"adventure", "action_rpg", "galgame", "platformer"},
            "tower_defense": genre == "tower_defense",
            "live2d": genre == "galgame",
        },
        "economy": {
            "starting_resources": {
                "gold": 150 if genre == "tower_defense" else 0,
                "lives": 20 if genre == "tower_defense" else 3,
            }
        },
    }


GENRE_PRIMARY_ACTIONS: Dict[str, tuple[str, str, Dict[str, Any]]] = {
    "sandbox": ("explore", "sandbox_explored", {"add_counters": {"exploration": 1}}),
    "platformer": ("jump", "platformer_jump", {"add_counters": {"jumps": 1}}),
    "adventure": ("investigate", "adventure_investigated", {"set_flags": ["clue:first"]}),
    "action_rpg": ("attack", "action_rpg_attack", {"add_counters": {"attacks": 1}}),
    "galgame": ("advance_story", "story_advanced", {"add_counters": {"story_beats": 1}}),
    "tower_defense": ("plan_defense", "defense_planned", {"add_counters": {"defense_plans": 1}}),
    "arena": ("arena_attack", "arena_attack", {"add_counters": {"attacks": 1}}),
    "card_game": ("draw_card", "card_drawn", {"add_inventory": {"starter_card": 1}}),
    "fighting": ("strike", "fighter_strike", {"add_counters": {"combo_hits": 1}}),
    "horror": ("inspect_clue", "horror_clue_inspected", {"set_flags": ["clue:inspected"]}),
    "idle": ("collect_income", "idle_income_collected", {"add_resources": {"gold": 1}}),
    "management": ("assign_worker", "worker_assigned", {"add_counters": {"assigned_workers": 1}}),
    "metroidvania": ("unlock_ability", "ability_unlocked", {"set_flags": ["ability:starter"]}),
    "puzzle": ("solve_step", "puzzle_step_solved", {"add_counters": {"puzzle_steps": 1}}),
    "racing": ("reach_checkpoint", "racing_checkpoint", {"add_counters": {"checkpoints": 1}}),
    "rhythm": ("rhythm_hit", "rhythm_note_hit", {"add_counters": {"rhythm_combo": 1}}),
    "roguelike": ("descend_floor", "roguelike_floor_entered", {"add_counters": {"floor": 1}}),
    "shooter": ("fire_weapon", "weapon_fired", {"add_counters": {"shots": 1}}),
    "simulation": ("simulate_tick", "simulation_tick", {"add_counters": {"simulation_ticks": 1}}),
    "sports": ("score_point", "sports_point_scored", {"add_counters": {"score": 1}}),
    "strategy": ("issue_order", "strategy_order_issued", {"add_counters": {"orders": 1}}),
    "survival": ("craft_item", "survival_item_crafted", {"add_inventory": {"crafted_item": 1}}),
    "tactics": ("end_turn", "tactics_turn_ended", {"add_counters": {"turn": 1}}),
}


GENRE_CHALLENGE_ACTIONS: Dict[str, tuple[str, str, str]] = {
    "sandbox": ("collect_resource", "resource_collected", "finish_expedition"),
    "platformer": ("land_jump", "platformer_landed", "reach_goal"),
    "adventure": ("solve_clue", "mystery_solved", "complete_chapter"),
    "action_rpg": ("defeat_enemy", "enemy_defeated", "claim_bounty"),
    "galgame": ("make_choice", "story_choice_made", "complete_route"),
    "tower_defense": ("complete_wave", "wave_completed", "secure_base"),
    "arena": ("defeat_opponent", "opponent_defeated", "win_match"),
    "fighting": ("finish_combo", "combo_completed", "win_round"),
    "horror": ("escape_threat", "threat_escaped", "reach_safety"),
    "idle": ("buy_upgrade", "idle_upgrade_bought", "complete_cycle"),
    "management": ("complete_order", "management_order_completed", "close_day"),
    "metroidvania": ("cross_ability_gate", "ability_gate_crossed", "reach_checkpoint"),
    "puzzle": ("solve_puzzle", "puzzle_solved", "open_exit"),
    "racing": ("finish_lap", "lap_completed", "claim_podium"),
    "rhythm": ("finish_song", "song_completed", "record_score"),
    "roguelike": ("clear_floor", "floor_cleared", "choose_reward"),
    "shooter": ("defeat_target", "target_defeated", "complete_mission"),
    "simulation": ("reach_stable_state", "simulation_stabilized", "complete_scenario"),
    "sports": ("finish_match", "sports_match_completed", "record_result"),
    "strategy": ("capture_objective", "objective_captured", "win_battle"),
    "survival": ("survive_night", "night_survived", "secure_shelter"),
    "tactics": ("complete_objective", "tactical_objective_completed", "win_encounter"),
}


def build_genre_rules(genre: str) -> Dict[str, Any]:
    genre_key = str(genre or "sandbox").strip().lower()
    action_id, event_name, effects = GENRE_PRIMARY_ACTIONS.get(genre_key, GENRE_PRIMARY_ACTIONS["sandbox"])
    primary_effects = {
        key: dict(value) if isinstance(value, dict) else list(value) if isinstance(value, list) else value
        for key, value in effects.items()
    }
    primary_effects["activate_quests"] = ["slice_objective"]
    primary_effects.setdefault("add_counters", {})["challenge_progress"] = 1
    challenge_action, challenge_event, completion_action = GENRE_CHALLENGE_ACTIONS.get(
        genre_key,
        GENRE_CHALLENGE_ACTIONS["sandbox"],
    )
    payload = {
        "schema_version": "reverie.game_rules/1",
        "genre": genre_key,
        "initial_state": {
            "resources": {"energy": 10},
            "counters": {"turn": 0},
            "notes": {"rules_profile": genre_key},
        },
        "primary_action": action_id,
        "smoke_actions": [action_id, challenge_action, completion_action],
        "rules": {
            action_id: {
                "event": event_name,
                "effects": primary_effects,
            },
            challenge_action: {
                "event": challenge_event,
                "conditions": {"requires_counters_min": {"challenge_progress": 1}},
                "effects": {
                    "complete_quests": ["slice_objective"],
                    "grant_rewards": {"slice_reward": 1},
                    "add_counters": {"challenge_resolved": 1},
                },
            },
            completion_action: {
                "event": "slice_completed",
                "conditions": {"requires_inventory": {"slice_reward": 1}},
                "effects": {
                    "set_flags": ["slice:completed"],
                    "add_counters": {"completed_slices": 1},
                },
            },
        },
    }
    if genre_key == "card_game":
        payload["initial_state"]["inventory"] = {"draw_pile": 5, "hand_card": 0}
        payload["initial_state"]["counters"]["victory_progress"] = 0
        payload["rules"] = {
            "draw_card": {
                "event": "card_drawn",
                "conditions": {"requires_inventory": {"draw_pile": 1}},
                "effects": {
                    "add_inventory": {"draw_pile": -1, "hand_card": 1},
                    "add_counters": {"cards_drawn": 1},
                    "activate_quests": ["slice_objective"],
                },
            },
            "play_card": {
                "event": "card_played",
                "conditions": {"requires_inventory": {"hand_card": 1}},
                "costs": {"energy": 1},
                "effects": {
                    "add_inventory": {"hand_card": -1},
                    "add_counters": {"cards_played": 1, "damage_dealt": 6, "victory_progress": 1},
                },
            },
            "claim_victory": {
                "event": "card_battle_won",
                "conditions": {"requires_counters_min": {"victory_progress": 1}},
                "effects": {
                    "set_flags": ["victory:first_battle"],
                    "complete_quests": ["slice_objective"],
                    "grant_rewards": {"slice_reward": 1},
                },
            },
            "complete_slice": {
                "event": "slice_completed",
                "conditions": {"requires_inventory": {"slice_reward": 1}},
                "effects": {
                    "set_flags": ["slice:completed"],
                    "add_counters": {"completed_slices": 1},
                },
            },
        }
        payload["smoke_actions"] = ["draw_card", "play_card", "claim_victory", "complete_slice"]
    return payload


def build_live2d_manifest(enabled: bool) -> Dict[str, Any]:
    return {
        "enabled": enabled,
        "renderer": "web",
        "sdk_candidates": [
            "vendor/live2d/live2dcubismcore.min.js",
            "web/vendor/live2d/live2dcubismcore.min.js",
        ],
        "models": {},
    }


def build_smoke_test() -> str:
    return (
        "from pathlib import Path\n"
        "from reverie.engine import run_project_smoke\n\n\n"
        "def test_project_smoke() -> None:\n"
        "    project_root = Path(__file__).resolve().parents[2]\n"
        "    result = run_project_smoke(project_root)\n"
        "    assert result['success'] is True\n"
        "    assert result['summary']['event_count'] >= 2\n"
    )


def create_project_skeleton(
    output_dir: Path,
    *,
    project_name: str,
    dimension: str = "2D",
    sample_name: str | None = None,
    genre: str | None = None,
    overwrite: bool = False,
) -> Dict[str, Any]:
    output_dir = Path(output_dir)
    engine_config = build_engine_config(project_name, dimension, sample_name=sample_name, genre=genre)
    genre_name = str(engine_config.get("project", {}).get("genre") or "sandbox")
    live2d_enabled = bool(engine_config.get("live2d", {}).get("enabled", False))
    created_directories: list[str] = []
    written_files: list[str] = []
    for relative in DEFAULT_STRUCTURE:
        target = output_dir / relative
        target.mkdir(parents=True, exist_ok=True)
        created_directories.append(str(target))

    if _safe_write(output_dir / "src/game/bootstrap.py", build_bootstrap(), overwrite):
        written_files.append(str(output_dir / "src/game/bootstrap.py"))
    if _safe_write(
        output_dir / "src/game/scripts/__init__.py",
        '"""Reverie Engine built-in script hooks and project-local behaviours."""\n',
        overwrite,
    ):
        written_files.append(str(output_dir / "src/game/scripts/__init__.py"))
    if _safe_write_yaml(output_dir / "data/config/engine.yaml", engine_config, overwrite):
        written_files.append(str(output_dir / "data/config/engine.yaml"))
    if _safe_write(
        output_dir / "docs/reverie_engine_quickstart.md",
        "# Reverie Engine Quickstart\n\nUse `/engine run`, `/engine smoke`, `/engine test`, and `/playtest telemetry` to iterate quickly.\n",
        overwrite,
    ):
        written_files.append(str(output_dir / "docs/reverie_engine_quickstart.md"))
    if _safe_write(output_dir / "tests/smoke/test_engine_smoke.py", build_smoke_test(), overwrite):
        written_files.append(str(output_dir / "tests/smoke/test_engine_smoke.py"))
    if _safe_write_yaml(
        output_dir / "data/content/gameplay_manifest.yaml",
        build_gameplay_manifest(project_name, dimension, genre_name),
        overwrite,
    ):
        written_files.append(str(output_dir / "data/content/gameplay_manifest.yaml"))
    genre_rules = build_genre_rules(genre_name)
    if _safe_write_yaml(output_dir / "data/content/rules.yaml", genre_rules, overwrite):
        written_files.append(str(output_dir / "data/content/rules.yaml"))
    if _safe_write_yaml(output_dir / "data/live2d/models.yaml", build_live2d_manifest(live2d_enabled), overwrite):
        written_files.append(str(output_dir / "data/live2d/models.yaml"))
    if _safe_write(
        output_dir / "assets/live2d/README.md",
        "# Live2D Assets\n\nPlace `.model3.json`, textures, motions, and expressions here. Reverie bundles `live2dcubismcore.min.js` in the CLI runtime and mirrors it into `web/vendor/live2d/` when building the browser bridge.\n",
        overwrite,
    ):
        written_files.append(str(output_dir / "assets/live2d/README.md"))

    live2d_bridge = Live2DManager(output_dir)
    bridge_path = output_dir / "web/live2d_bridge.html"
    if overwrite or not bridge_path.exists():
        live2d_bridge.build_web_bridge(bridge_path)
        written_files.append(str(bridge_path))

    scene_seed = {
        "name": "Main",
        "type": "Scene",
        "scene_id": "main",
        "metadata": {
            "dimension": dimension,
            "engine": ENGINE_NAME,
            "brand": ENGINE_BRAND,
            "genre": genre_name,
        },
        "components": [{"type": "Transform", "position": [0, 0, 0]}],
        "children": [
            {
                "name": "Player",
                "type": "Actor",
                "tags": ["player"],
                "components": [
                    {"type": "Transform", "position": [0, 0, 0]},
                    {"type": "Collider", "size": [1, 2, 1], "layer": "player"},
                    {"type": "KinematicBody", "speed": 4.0},
                    {"type": "Health", "max_health": 10, "current_health": 10, "faction": "player"},
                    {"type": "ScriptBehaviour", "script": "player_avatar"},
                ],
                "children": [],
            }
        ],
    }
    if _safe_write_json(output_dir / "data/scenes/main.relscene.json", scene_seed, overwrite):
        written_files.append(str(output_dir / "data/scenes/main.relscene.json"))

    prefab_seed = {
        "name": "Player",
        "type": "Actor",
        "tags": ["player"],
        "components": [
            {"type": "Transform", "position": [0, 0, 0]},
            {"type": "Collider", "size": [1, 2, 1], "layer": "player"},
            {"type": "KinematicBody", "speed": 4.0},
            {"type": "Health", "max_health": 10, "current_health": 10, "faction": "player"},
        ],
        "children": [],
    }
    if _safe_write_json(output_dir / "data/prefabs/player.relprefab.json", prefab_seed, overwrite):
        written_files.append(str(output_dir / "data/prefabs/player.relprefab.json"))

    if _safe_write_yaml(
        output_dir / "data/content/progression.yaml",
        {"tracks": [{"id": "starter", "levels": [1, 2, 3], "perks": ["mobility", "power", "clarity"]}]},
        overwrite,
    ):
        written_files.append(str(output_dir / "data/content/progression.yaml"))
    if not sample_name and _safe_write_json(
        output_dir / "playtest/logs/input_script.json",
        {
            "inputs": [
                {"frame": index + 1, "action": action_id}
                for index, action_id in enumerate(genre_rules.get("smoke_actions") or [genre_rules["primary_action"]])
            ]
        },
        overwrite,
    ):
        written_files.append(str(output_dir / "playtest/logs/input_script.json"))
    if _safe_write_yaml(output_dir / "data/content/dialogue.yaml", {"conversations": {}}, overwrite):
        written_files.append(str(output_dir / "data/content/dialogue.yaml"))
    if _safe_write_yaml(output_dir / "data/content/tower_defense.yaml", {"paths": {}, "waves": {}, "towers": {}}, overwrite):
        written_files.append(str(output_dir / "data/content/tower_defense.yaml"))
    if _safe_write_yaml(output_dir / "data/content/quests.yaml", {"quests": {}}, overwrite):
        written_files.append(str(output_dir / "data/content/quests.yaml"))
    if _safe_write_yaml(
        output_dir / "data/localization/en.yaml",
        {
            "locale": "en",
            "strings": {
                "ui.gold": "Gold",
                "ui.lives": "Lives",
                "ui.build_towers": "Build Towers",
            },
        },
        overwrite,
    ):
        written_files.append(str(output_dir / "data/localization/en.yaml"))

    modeling_seed = None
    if bool(engine_config.get("modeling", {}).get("enabled", False)):
        modeling_seed = materialize_modeling_workspace(output_dir, overwrite=overwrite)
        written_files.extend(modeling_seed["files"])

    materialized_sample = None
    if sample_name:
        materialized = materialize_sample(output_dir, sample_name, overwrite=overwrite)
        materialized_sample = materialized["sample_name"]
        written_files.extend(materialized["files"])

    return {
        "directories": created_directories,
        "files": sorted(set(written_files)),
        "sample_name": materialized_sample,
        "genre": genre_name,
        "live2d_enabled": live2d_enabled,
        "modeling_enabled": bool(engine_config.get("modeling", {}).get("enabled", False)),
        "modeling": modeling_seed or {},
    }


def materialize_sample(output_dir: Path, sample_name: str, *, overwrite: bool = False) -> Dict[str, Any]:
    output_dir = Path(output_dir)
    sample = get_sample_definition(sample_name)
    files: list[str] = []

    if _safe_write_yaml(
        output_dir / "data/config/engine.yaml",
        build_engine_config(sample["project_name"], sample["dimension"], sample_name=sample_name, genre=sample.get("genre")),
        overwrite,
    ):
        files.append(str(output_dir / "data/config/engine.yaml"))

    if _safe_write_json(output_dir / "data/scenes/main.relscene.json", sample["scene"], overwrite):
        files.append(str(output_dir / "data/scenes/main.relscene.json"))

    for file_name, payload in sample.get("prefabs", {}).items():
        target = output_dir / "data/prefabs" / file_name
        if _safe_write_payload(target, payload, overwrite):
            files.append(str(target))

    for file_name, payload in sample.get("content", {}).items():
        target = output_dir / "data/content" / file_name
        changed = _safe_write_payload(target, payload, overwrite)
        if changed:
            files.append(str(target))

    for relative_path, payload in sample.get("files", {}).items():
        target = output_dir / relative_path
        if _safe_write_payload(target, payload, overwrite):
            files.append(str(target))

    if _safe_write_json(output_dir / "playtest/logs/input_script.json", {"inputs": sample.get("input_script", [])}, overwrite):
        files.append(str(output_dir / "playtest/logs/input_script.json"))

    if _safe_write(
        output_dir / "docs/sample_profile.md",
        f"# {sample['project_name']}\n\n- Sample: {sample_name}\n- Dimension: {sample['dimension']}\n- Description: {sample['description']}\n",
        overwrite,
    ):
        files.append(str(output_dir / "docs/sample_profile.md"))

    return {"sample_name": sample_name, "files": files, "expected_events": sample.get("expected_events", [])}


def inspect_project(project_root: Path) -> Dict[str, Any]:
    project_root = Path(project_root)
    config = load_engine_config(project_root)
    live2d = Live2DManager(project_root)
    localization = LocalizationManager(project_root)
    scene_files = sorted(project_root.glob("data/scenes/*.relscene.json"))
    prefab_files = sorted(project_root.glob("data/prefabs/*.relprefab.json"))
    content_files = sorted(project_root.glob("data/content/*"))
    modeling = inspect_modeling_workspace(project_root)
    return {
        "project_root": str(project_root.resolve()),
        "scene_count": len(scene_files),
        "prefab_count": len(prefab_files),
        "content_count": len(content_files),
        "available_samples": list_samples(),
        "has_bootstrap": (project_root / "src/game/bootstrap.py").exists(),
        "entry_scene": str((project_root / "data/scenes/main.relscene.json").resolve()),
        "dimension": config.dimension,
        "genre": config.genre,
        "modules": list(config.modules),
        "config": config.to_dict(),
        "live2d": live2d.summary(),
        "localization": localization.summary(),
        "modeling": modeling,
    }


def validate_project(project_root: Path) -> Dict[str, Any]:
    project_root = Path(project_root)
    required_paths = [
        "src/game/bootstrap.py",
        "data/config/engine.yaml",
        "data/content/gameplay_manifest.yaml",
        "data/scenes/main.relscene.json",
        "data/prefabs",
        "data/content",
        "data/live2d",
    ]
    errors: list[str] = []
    warnings: list[str] = []
    for relative in required_paths:
        if not (project_root / relative).exists():
            errors.append(f"missing required path: {relative}")
    config = load_engine_config(project_root)
    scene_path = project_root / "data/scenes/main.relscene.json"
    if scene_path.exists():
        payload = json.loads(scene_path.read_text(encoding="utf-8"))
        scene_errors = validate_scene_document(payload)
        errors.extend(scene_errors)
    else:
        errors.append("missing required path: data/scenes/main.relscene.json")

    engine_config_path = project_root / "data/config/engine.yaml"
    if engine_config_path.exists():
        engine_payload = yaml.safe_load(engine_config_path.read_text(encoding="utf-8")) or {}
        errors.extend(validate_engine_config_schema(engine_payload))

    gameplay_manifest_path = project_root / "data/content/gameplay_manifest.yaml"
    if gameplay_manifest_path.exists():
        gameplay_payload = yaml.safe_load(gameplay_manifest_path.read_text(encoding="utf-8")) or {}
        errors.extend(validate_gameplay_manifest_schema(gameplay_payload))

    live2d = Live2DManager(project_root)
    live2d_errors = live2d.validate()
    if config.live2d.enabled:
        errors.extend(live2d_errors)
    elif live2d_errors:
        warnings.extend(live2d_errors)

    modeling = inspect_modeling_workspace(project_root)
    if config.modeling.enabled:
        if not modeling.get("pipeline_exists", False):
            warnings.append("missing modeling pipeline manifest: data/models/pipeline.yaml")
        if not modeling.get("registry_exists", False):
            warnings.append("missing model registry: data/models/model_registry.yaml")
        if not modeling.get("stack", {}).get("blockbench", {}).get("installed", False):
            warnings.append("Blockbench desktop was not detected. Install Blockbench for built-in model authoring workflows.")
        if not modeling.get("stack", {}).get("ashfox", {}).get("reachable", False):
            warnings.append("Ashfox MCP endpoint is not reachable. Launch Blockbench with the Ashfox plugin enabled.")
    return {
        "valid": not errors,
        "errors": errors,
        "warnings": warnings,
        "required_paths": required_paths,
        "dimension": config.dimension,
        "genre": config.genre,
        "modules": list(config.modules),
        "schemas": {
            "engine": ENGINE_CONFIG_SCHEMA,
            "gameplay_manifest": GAMEPLAY_MANIFEST_SCHEMA,
        },
    }


def build_project_health_report(project_root: Path, *, include_smoke: bool = False) -> Dict[str, Any]:
    from .app import run_project_smoke

    project_root = Path(project_root)
    info = inspect_project(project_root)
    validation = validate_project(project_root)
    capabilities = info.get("config", {}).get("capabilities", {})
    recommendations: list[str] = []
    score = 100

    if validation["errors"]:
        score -= min(60, len(validation["errors"]) * 12)
        recommendations.extend(f"fix: {item}" for item in validation["errors"][:8])
    if validation["warnings"]:
        score -= min(20, len(validation["warnings"]) * 4)
        recommendations.extend(f"review: {item}" for item in validation["warnings"][:8])
    if not info["scene_count"]:
        score -= 10
        recommendations.append("add at least one scene under data/scenes")
    if not info["prefab_count"]:
        score -= 8
        recommendations.append("add reusable prefabs under data/prefabs")
    if capabilities.get("supports_live2d") and not info.get("live2d", {}).get("model_count", 0):
        score -= 6
        recommendations.append("register at least one Live2D model in data/live2d/models.yaml")
    if capabilities.get("supports_ui") and not info["content_count"]:
        score -= 4
        recommendations.append("add gameplay/content data for UI-facing systems")
    if capabilities.get("supports_model_pipeline"):
        modeling = info.get("modeling", {})
        if not modeling.get("stack", {}).get("blockbench", {}).get("installed", False):
            score -= 3
            recommendations.append("install Blockbench desktop for the built-in modeling workflow")
        if not modeling.get("stack", {}).get("ashfox", {}).get("reachable", False):
            score -= 5
            recommendations.append("launch Blockbench with the Ashfox plugin so Reverie-Gamer can discover live Ashfox MCP tools")
        if info.get("dimension") in {"2.5D", "3D"} and not modeling.get("runtime_model_count", 0):
            score -= 6
            recommendations.append("import at least one runtime model into assets/models/runtime for the built-in modeling flow")

    smoke: Dict[str, Any] = {"executed": False}
    if include_smoke and validation["valid"]:
        smoke = run_project_smoke(project_root)
        smoke["executed"] = True
        if not smoke.get("success", False):
            score -= 15
            recommendations.append("smoke run failed; inspect playtest/logs/engine_smoke.json")

    score = max(0, min(100, score))
    status = "healthy" if score >= 85 and validation["valid"] else ("warning" if score >= 60 else "critical")
    return {
        "project_root": str(project_root.resolve()),
        "score": score,
        "status": status,
        "validation": validation,
        "inspection": info,
        "smoke": smoke,
        "recommendations": recommendations[:12],
    }


def package_project(
    project_root: Path,
    *,
    output_path: str | Path | None = None,
    include_smoke: bool = True,
) -> Dict[str, Any]:
    from .app import run_project_smoke

    project_root = Path(project_root)
    validation = validate_project(project_root)
    if not validation["valid"]:
        return {
            "success": False,
            "project_root": str(project_root.resolve()),
            "validation": validation,
            "error": "project validation failed",
        }

    smoke = run_project_smoke(project_root) if include_smoke else {"success": True, "summary": {}}
    if include_smoke and not smoke.get("success", False):
        return {
            "success": False,
            "project_root": str(project_root.resolve()),
            "validation": validation,
            "smoke": smoke,
            "error": "smoke validation failed",
        }

    output_dir = project_root / "dist"
    output_dir.mkdir(parents=True, exist_ok=True)
    package_file = Path(output_path) if output_path else output_dir / f"{project_root.name}_reverie_engine_package.zip"
    if not package_file.is_absolute():
        package_file = (project_root / package_file).resolve()
    package_file.parent.mkdir(parents=True, exist_ok=True)

    included_roots = [
        "assets",
        "data",
        "docs",
        "src/game",
        "tests/smoke",
        "playtest/logs",
        "save_data",
        "web",
    ]
    packaged_files: list[str] = []
    with zipfile.ZipFile(package_file, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        manifest = {
            "engine": ENGINE_NAME,
            "brand": ENGINE_BRAND,
            "project_root": str(project_root.resolve()),
            "validation": validation,
            "smoke": smoke if include_smoke else {},
            "included_roots": included_roots,
        }
        archive.writestr("package_manifest.json", json.dumps(manifest, indent=2, ensure_ascii=False))
        packaged_files.append("package_manifest.json")
        for relative_root in included_roots:
            source_root = project_root / relative_root
            if not source_root.exists():
                continue
            for file_path in sorted(path for path in source_root.rglob("*") if path.is_file()):
                relative_name = file_path.relative_to(project_root).as_posix()
                archive.write(file_path, arcname=relative_name)
                packaged_files.append(relative_name)

    return {
        "success": True,
        "project_root": str(project_root.resolve()),
        "package_path": str(package_file),
        "file_count": len(packaged_files),
        "files": packaged_files,
        "validation": validation,
        "smoke": smoke,
    }
