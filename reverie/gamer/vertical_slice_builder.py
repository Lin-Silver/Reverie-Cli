"""Vertical-slice project builder for Reverie-Gamer."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict
import json

import yaml

from ..engine import (
    create_model_stub,
    create_primitive_model,
    materialize_modeling_workspace,
    sync_model_registry,
)
from .asset_pipeline import build_asset_pipeline_plan, asset_pipeline_markdown
from .asset_budgeting import build_asset_budget
from .animation_pipeline import build_animation_plan
from .character_factory import build_character_kits
from .content_lattice import build_content_matrix
from .continuation_director import (
    build_continuation_recommendations,
    continuation_recommendations_markdown,
)
from .design_intelligence import build_design_intelligence, design_playbook_markdown
from .environment_factory import build_environment_kits
from .project_director import (
    build_or_update_blueprint,
    build_or_update_game_request,
    evolve_boss_arc,
    evolve_content_expansion,
    evolve_gameplay_factory,
    evolve_world_program,
    load_existing_artifacts,
)
from .production_plan import (
    build_production_plan,
    production_plan_markdown,
    vertical_slice_markdown,
)
from .faction_graph import build_faction_graph
from .gameplay_factory import build_boss_arc, build_gameplay_factory
from .large_scale_director import (
    build_campaign_program,
    build_live_ops_plan,
    build_production_operating_model,
    build_roster_strategy,
)
from .milestone_planner import build_feature_matrix, build_milestone_board, build_risk_register
from .program_compiler import build_game_program, game_bible_markdown
from .region_expander import build_region_kits
from .runtime_capability_graph import build_runtime_capability_graph
from .runtime_delivery import build_runtime_delivery_plan
from .runtime_registry import select_runtime_profile
from .save_migration import build_save_migration_plan
from .expansion_planner import (
    build_content_expansion_plan,
    build_expansion_backlog,
    build_resume_state,
    content_expansion_markdown,
    expansion_backlog_markdown,
    resume_state_markdown,
)
from .system_generators import (
    build_system_packet_bundle,
    build_task_graph,
    system_packet_markdown,
    task_graph_markdown,
)
from .verification import (
    build_combat_feel_report,
    build_performance_budget,
    build_quality_gate_report,
    evaluate_slice_score,
    slice_score_markdown,
)
from .world_program import build_questline_program, build_world_program


def _write_json(path: Path, payload: Dict[str, Any], overwrite: bool) -> bool:
    if path.exists() and not overwrite:
        return False
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    return True


def _write_text(path: Path, content: str, overwrite: bool) -> bool:
    if path.exists() and not overwrite:
        return False
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    return True


def _write_yaml(path: Path, payload: Dict[str, Any], overwrite: bool) -> bool:
    if path.exists() and not overwrite:
        return False
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(yaml.safe_dump(payload, sort_keys=False, allow_unicode=True), encoding="utf-8")
    return True


def _seed_modeling_workspace(
    output_dir: Path,
    asset_pipeline: Dict[str, Any],
    *,
    overwrite: bool,
) -> Dict[str, Any]:
    workspace = materialize_modeling_workspace(output_dir, overwrite=overwrite)
    written_files = list(workspace.get("files", []))
    for seed in asset_pipeline.get("modeling_seed", []):
        asset_id = str(seed.get("id", "")).strip()
        if not asset_id:
            continue
        source_stub = str(seed.get("source_stub", "")).strip()
        if source_stub:
            try:
                stub_path = create_model_stub(
                    output_dir,
                    str(seed.get("label", asset_id)),
                    relative_path=source_stub,
                    overwrite=overwrite,
                )
                written_files.append(str(stub_path))
            except FileExistsError:
                pass

        dims = dict(seed.get("dimensions", {}) or {})
        try:
            generated = create_primitive_model(
                output_dir,
                asset_id,
                primitive=str(seed.get("primitive", "box") or "box"),
                size=max(
                    float(dims.get("width", 1.0) or 1.0),
                    float(dims.get("height", 1.0) or 1.0),
                    float(dims.get("depth", 1.0) or 1.0),
                    float(dims.get("radius", 0.5) or 0.5) * 2.0,
                ),
                width=float(dims.get("width", 1.0) or 1.0),
                height=float(dims.get("height", 1.0) or 1.0),
                depth=float(dims.get("depth", 1.0) or 1.0),
                radius=float(dims.get("radius", 0.5) or 0.5),
                segments=int(dims.get("segments", 16) or 16),
                overwrite=overwrite,
                create_preview=True,
            )
            written_files.append(str(generated.get("runtime_path", "")))
            if generated.get("preview_path"):
                written_files.append(str(generated["preview_path"]))
        except FileExistsError:
            pass

    registry = sync_model_registry(output_dir, overwrite=True)
    written_files.append(str(registry.get("registry_path", "")))
    return {
        "workspace": workspace,
        "registry": registry.get("registry", {}),
        "files": sorted({item for item in written_files if str(item).strip()}),
    }


def _playtest_plan_markdown(game_request: Dict[str, Any], blueprint: Dict[str, Any]) -> str:
    meta = blueprint.get("meta", {})
    lines = [
        f"# Playtest Plan: {meta.get('project_name', 'Untitled Reverie Slice')}",
        "",
        f"- Runtime: {meta.get('target_engine', 'reverie_engine')}",
        f"- Scope: {meta.get('scope', 'vertical_slice')}",
        "- Session Length: 20 minutes",
        "",
        "## Objectives",
        "- Verify that the player understands the core movement and objective within the first five minutes.",
        "- Confirm that combat or interaction reads clearly under camera and movement pressure.",
        "- Check that the reward and completion state motivate the next run or the next production increment.",
        "",
        "## Observer Focus",
        "- Time to first engagement",
        "- Time to first damage taken",
        "- Time to first objective completion",
        "- Confusion points around route guidance, combat readability, or shrine activation",
        "",
        "## Prompt Summary",
        f"- {game_request.get('source_prompt', '').strip()}",
        "",
    ]
    return "\n".join(lines)


def _telemetry_schema(game_request: Dict[str, Any], blueprint: Dict[str, Any]) -> Dict[str, Any]:
    systems = blueprint.get("gameplay_blueprint", {}).get("systems", {})
    events = [
        {"name": "session_start", "fields": ["build_id", "entry_point", "runtime"]},
        {"name": "session_end", "fields": ["duration_seconds", "result", "quit_reason"]},
        {"name": "damage_taken", "fields": ["source", "amount", "health_after"]},
        {"name": "reward_claimed", "fields": ["reward_type", "amount", "source"]},
        {"name": "slice_completed", "fields": ["objective_id", "elapsed_seconds", "runtime"]},
    ]
    for name in systems.keys():
        events.append({"name": f"{name}_state", "fields": ["state", "outcome", "difficulty"]})
    return {
        "project": blueprint.get("meta", {}).get("project_name", "Untitled Reverie Slice"),
        "runtime": blueprint.get("meta", {}).get("target_engine", "reverie_engine"),
        "events": events,
    }


def _quality_gates(
    game_request: Dict[str, Any],
    blueprint: Dict[str, Any],
    system_bundle: Dict[str, Any],
) -> Dict[str, Any]:
    quality = game_request.get("quality_targets", {})
    packets = system_bundle.get("packets", {})
    world_packet = packets.get("world_structure", {})
    return {
        "prototype": [
            "core controls respond consistently",
            "one complete objective path exists",
            "hard crashes are absent in the main path",
        ],
        "first_playable": [
            "reward and completion states fire correctly",
            "telemetry captures session start, damage, reward, and completion",
            "save/load schema exists even if content breadth is still narrow",
        ],
        "vertical_slice": quality.get("must_have", []) + [
            "camera, movement, and combat readability reinforce each other",
            "the slice is strong enough to guide further authored content production",
        ],
        "system_gate": {
            packet_id: packet.get("tests", [])[:2]
            for packet_id, packet in packets.items()
        },
        "content_gate": [
            "the world route uses readable landmarks and a clear finish state",
            "one combat or challenge pocket sits on the critical path",
            "quest, reward, and completion beats happen in one clean run",
        ],
        "performance_gate": [
            f"target_fps >= {quality.get('target_fps', 60)}",
            f"load_time_seconds <= {quality.get('target_load_time_seconds', 12)}",
            "asset import rules stay aligned with the runtime output",
        ],
        "asset_gate": world_packet.get("asset_contracts", {}),
    }


def _augment_reverie_engine_slice(
    output_dir: Path,
    game_request: Dict[str, Any],
    blueprint: Dict[str, Any],
    system_bundle: Dict[str, Any],
    content_expansion: Dict[str, Any],
    asset_pipeline: Dict[str, Any],
    *,
    overwrite: bool,
) -> list[str]:
    files: list[str] = []
    content_root = Path(output_dir) / "data" / "content"
    packets = system_bundle.get("packets", {})
    combat_packet = packets.get("combat", {})
    quest_packet = packets.get("quest", {})
    progression_packet = packets.get("progression", {})
    world_packet = packets.get("world_structure", {})
    save_packet = packets.get("save_load", {})
    region_seeds = list(content_expansion.get("region_seeds", []))
    starter_region_id = str(region_seeds[0].get("id", "starter_ruins")) if region_seeds else "starter_ruins"
    npc_roster = list(content_expansion.get("npc_roster", []))
    quest_arcs = list(content_expansion.get("quest_arcs", []))
    region_routes = []
    for index, region in enumerate(region_seeds[1:4], start=1):
        region_routes.append(
            {
                "id": f"route_{index}",
                "from": starter_region_id,
                "to": region.get("id", f"region_{index}"),
                "gate": region.get("progression_gate", "complete the current slice"),
            }
        )
    region_layouts = [
        {
            "id": "starter_ruins",
            "display_name": "Starter Ruins",
            "summary": "The onboarding shrine district with the first combat route and purification finale.",
            "spawn_point": [0.0, 1.1, 8.0],
            "center": [0.0, 0.0, 0.0],
            "landmarks": ["entry_arch", "combat_pocket", "purification_shrine"],
            "region_objective_id": "",
        },
        {
            "id": "cloudstep_basin",
            "display_name": "Cloudstep Basin",
            "summary": "A wider traversal basin that previews vertical routing and ranged pressure.",
            "spawn_point": [72.0, 1.1, 8.0],
            "center": [72.0, 0.0, 0.0],
            "landmarks": ["basin_watchtower", "reed_bridge", "survey_relay"],
            "region_objective_id": "cloudstep_relay",
        },
        {
            "id": "echo_watch",
            "display_name": "Echo Watch",
            "summary": "A frontier observatory region for elite pressure and stronger story escalation.",
            "spawn_point": [-72.0, 1.1, 8.0],
            "center": [-72.0, 0.0, 0.0],
            "landmarks": ["echo_spire", "relay_stairs", "signal_plaza"],
            "region_objective_id": "echo_spire",
        },
    ]
    region_objectives = [
        {
            "id": "cloudstep_relay",
            "region_id": "cloudstep_basin",
            "label": "Stabilize the Survey Relay",
            "summary": "Activate the basin relay and secure a cleaner route for future expansion passes.",
            "reward_id": "basin_insight",
        },
        {
            "id": "echo_spire",
            "region_id": "echo_watch",
            "label": "Calibrate the Echo Spire",
            "summary": "Re-tune the observatory spire to reveal stronger frontier signals.",
            "reward_id": "watch_resonance",
        },
    ]
    patrol_routes = [
        {
            "id": "starter_watch_loop",
            "region_id": "starter_ruins",
            "label": "Starter Watch Loop",
            "assigned_enemy_ids": ["sentinel_melee", "sentinel_ranged"],
            "loop": True,
            "wait_seconds": 0.85,
            "path_points": [[-4.0, 0.0, -1.5], [1.5, 0.0, -5.5], [6.0, 0.0, -8.5]],
            "purpose": "keep the shrine approach under light pressure",
        },
        {
            "id": "cloudstep_relay_arc",
            "region_id": "cloudstep_basin",
            "label": "Cloudstep Relay Arc",
            "assigned_enemy_ids": ["cloudstep_basin_sentinel_melee", "cloudstep_basin_sentinel_ranged"],
            "loop": True,
            "wait_seconds": 0.9,
            "path_points": [[73.5, 0.0, -4.5], [78.0, 0.0, -9.5], [82.0, 0.0, -13.0]],
            "purpose": "sweep the basin approach before the relay objective",
        },
        {
            "id": "echo_spire_sweep",
            "region_id": "echo_watch",
            "label": "Echo Spire Sweep",
            "assigned_enemy_ids": ["echo_watch_sentinel_ranged", "echo_watch_sentinel_elite"],
            "loop": True,
            "wait_seconds": 1.0,
            "path_points": [[-68.0, 0.0, -4.0], [-72.5, 0.0, -8.5], [-76.0, 0.0, -12.0]],
            "purpose": "hold the observatory lane before the spire can be reclaimed",
        },
    ]
    alert_networks = [
        {
            "id": "starter_intro_alert",
            "region_id": "starter_ruins",
            "label": "Starter Intro Alert",
            "assigned_enemy_ids": ["sentinel_melee", "sentinel_ranged"],
            "duration_seconds": 4.5,
            "search_duration_seconds": 3.0,
            "response_radius": 12.0,
            "anchor_point": [1.0, 0.0, -5.0],
            "purpose": "let shrine sentinels reinforce each other during the first route push",
        },
        {
            "id": "cloudstep_relay_alert",
            "region_id": "cloudstep_basin",
            "label": "Cloudstep Relay Alert",
            "assigned_enemy_ids": ["cloudstep_basin_sentinel_melee", "cloudstep_basin_sentinel_ranged"],
            "duration_seconds": 5.0,
            "search_duration_seconds": 3.4,
            "response_radius": 14.0,
            "anchor_point": [79.0, 0.0, -10.0],
            "purpose": "let relay defenders collapse toward the basin alert lane",
        },
        {
            "id": "echo_spire_alert",
            "region_id": "echo_watch",
            "label": "Echo Spire Alert",
            "assigned_enemy_ids": ["echo_watch_sentinel_ranged", "echo_watch_sentinel_elite"],
            "duration_seconds": 5.5,
            "search_duration_seconds": 3.8,
            "response_radius": 14.0,
            "anchor_point": [-73.0, 0.0, -9.5],
            "purpose": "let observatory defenders reinforce the spire approach",
        },
    ]
    world_graph = {
        "nodes": [
            {
                "id": layout["id"],
                "display_name": layout["display_name"],
                "summary": layout["summary"],
                "region_objective_id": layout.get("region_objective_id", ""),
            }
            for layout in region_layouts
        ],
        "routes": region_routes
        + [
            {"id": "route_return_cloudstep", "from": "cloudstep_basin", "to": "starter_ruins", "gate": "always_available"},
            {"id": "route_return_echo_watch", "from": "echo_watch", "to": "starter_ruins", "gate": "always_available"},
        ],
        "regional_goals": region_objectives,
        "patrol_lanes": [
            {
                "region_id": route["region_id"],
                "route_id": route["id"],
                "assigned_enemy_ids": route["assigned_enemy_ids"],
            }
            for route in patrol_routes
        ],
        "guard_networks": [
            {
                "region_id": network["region_id"],
                "network_id": network["id"],
                "assigned_enemy_ids": network["assigned_enemy_ids"],
                "search_duration_seconds": network["search_duration_seconds"],
                "anchor_point": network["anchor_point"],
            }
            for network in alert_networks
        ],
    }
    reward_nodes = progression_packet.get("reward_track", {}).get("nodes", [])
    encounter_payload = {
        "encounters": [
            {
                "id": "ruin_gate_intro",
                "enemies": [enemy.get("id", "sentinel_alpha") for enemy in combat_packet.get("enemy_archetypes", [])]
                or ["sentinel_alpha", "sentinel_beta"],
                "goal": "clear_camp",
                "reward": {"type": "power", "amount": 1, "unlock": reward_nodes[0]["id"] if reward_nodes else "wind_step"},
            }
        ]
    }
    quest_payload = {
        "quests": [
            {
                "id": "activate_shrine",
                "title": "Purify the Forgotten Shrine",
                "steps": [step.get("id", "objective") for step in quest_packet.get("slice_objectives", [])]
                or ["reach_ruins", "defeat_sentinels", "activate_shrine"],
                "rewards": quest_packet.get("reward_contract", {}).get("completion_rewards", ["perk:wind_step", "currency:50"]),
            }
        ]
    }
    progression_payload = {
        "tracks": [
            {
                "id": "slice_core",
                "levels": list(range(1, len(reward_nodes) + 1)) or [1, 2, 3],
                "perks": [node.get("id", "perk") for node in reward_nodes] or ["wind_step", "focus_strike", "resonant_guard"],
            }
        ]
    }
    world_slice_payload = {
        "slice_id": "forgotten_shrine",
        "biome": "windswept_ruins",
        "landmarks": world_packet.get("landmarks", ["entry_arch", "combat_pocket", "purification_shrine"]),
        "spaces": [space.get("space_id", "space") for space in world_packet.get("zone_layout", [])],
        "completion_gate": "activate_shrine",
        "patrol_route_ids": [route["id"] for route in patrol_routes],
        "alert_network_ids": [network["id"] for network in alert_networks],
    }
    save_schema_payload = save_packet.get("save_schema", {"schema_version": 1, "fields": ["objective_state", "rewards"]})
    asset_contract_payload = world_packet.get("asset_contracts", {})
    asset_registry_payload = {
        "runtime": asset_pipeline.get("runtime", "reverie_engine"),
        "modeling_workspace": asset_pipeline.get("modeling_workspace", {}),
        "content_sets": asset_pipeline.get("content_sets", {}),
        "modeling_seed": asset_pipeline.get("modeling_seed", []),
    }
    asset_import_profile_payload = {
        "runtime_delivery": asset_pipeline.get("runtime_delivery", {}),
        "import_profile": asset_pipeline.get("import_profile", {}),
        "validation_rules": asset_pipeline.get("validation_rules", {}),
        "budget_profile": asset_pipeline.get("budget_profile", {}),
    }
    payloads = {
        content_root / "encounters.yaml": encounter_payload,
        content_root / "quests.yaml": quest_payload,
        content_root / "progression.yaml": progression_payload,
        content_root / "world_slice.yaml": world_slice_payload,
        content_root / "save_schema.yaml": save_schema_payload,
        content_root / "asset_contracts.yaml": asset_contract_payload,
        content_root / "asset_registry.yaml": asset_registry_payload,
        content_root / "asset_import_profile.yaml": asset_import_profile_payload,
        content_root / "region_seeds.yaml": {"regions": region_seeds},
        content_root / "npc_roster.yaml": {"npcs": npc_roster},
        content_root / "quest_arcs.yaml": {"quest_arcs": quest_arcs},
        content_root / "region_routes.yaml": {"routes": region_routes},
        content_root / "region_layouts.yaml": {"regions": region_layouts},
        content_root / "region_objectives.yaml": {"objectives": region_objectives},
        content_root / "patrol_routes.yaml": {"routes": patrol_routes},
        content_root / "alert_networks.yaml": {"networks": alert_networks},
        content_root / "world_graph.yaml": world_graph,
    }
    for path, payload in payloads.items():
        if _write_yaml(path, payload, overwrite):
            files.append(str(path))
    return files


def _augment_godot_slice(
    output_dir: Path,
    game_request: Dict[str, Any],
    system_bundle: Dict[str, Any],
    content_expansion: Dict[str, Any],
    asset_pipeline: Dict[str, Any],
    *,
    roster_strategy: Dict[str, Any] | None = None,
    live_ops_plan: Dict[str, Any] | None = None,
    runtime_delivery_plan: Dict[str, Any] | None = None,
    overwrite: bool,
) -> list[str]:
    files: list[str] = []
    packets = system_bundle.get("packets", {})
    combat_packet = packets.get("combat", {})
    runtime_root = Path(output_dir) / "engine" / "godot"
    quest_packet = packets.get("quest", {})
    progression_packet = packets.get("progression", {})
    world_packet = packets.get("world_structure", {})
    save_packet = packets.get("save_load", {})
    region_seeds = list(content_expansion.get("region_seeds", []))
    npc_roster = list(content_expansion.get("npc_roster", []))
    quest_arcs = list(content_expansion.get("quest_arcs", []))
    roster_strategy = dict(roster_strategy or {})
    live_ops_plan = dict(live_ops_plan or {})
    runtime_delivery_plan = dict(runtime_delivery_plan or {})
    party_model = str(game_request.get("experience", {}).get("party_model", "single_hero_focus")).strip() or "single_hero_focus"
    specialized = {
        str(item).strip()
        for item in game_request.get("systems", {}).get("specialized", []) or []
        if str(item).strip()
    }
    large_scale_profile = dict(game_request.get("production", {}).get("large_scale_profile", {}) or {})
    starter_region_id = str(region_seeds[0].get("id", "starter_ruins")) if region_seeds else "starter_ruins"
    second_region_id = str(region_seeds[1].get("id", "cloudstep_basin")) if len(region_seeds) > 1 else "cloudstep_basin"
    third_region_id = str(region_seeds[2].get("id", "echo_watch")) if len(region_seeds) > 2 else "echo_watch"
    region_layouts = [
        {
            "id": starter_region_id,
            "display_name": starter_region_id.replace("_", " ").title(),
            "summary": str(region_seeds[0].get("purpose", "Onboard traversal and shrine combat")) if region_seeds else "Onboard traversal and shrine combat",
            "spawn_point": [0.0, 1.1, 8.0],
            "center": [0.0, 0.0, 0.0],
            "sky_tint": [0.78, 0.89, 1.0],
            "region_objective_id": "",
            "preview_landmarks": [],
        },
        {
            "id": second_region_id,
            "display_name": second_region_id.replace("_", " ").title(),
            "summary": str(region_seeds[1].get("purpose", "Teach vertical routing and ranged pressure")) if len(region_seeds) > 1 else "Teach vertical routing and ranged pressure",
            "spawn_point": [72.0, 1.1, 8.0],
            "center": [72.0, 0.0, 0.0],
            "sky_tint": [0.70, 0.90, 0.92],
            "region_objective_id": "cloudstep_relay",
            "preview_landmarks": [
                {"id": f"{second_region_id}_watchtower", "position": [68.0, 1.3, -10.0], "size": [3.0, 3.0, 3.0], "color": [0.42, 0.55, 0.44]},
                {"id": f"{second_region_id}_relay", "position": [81.0, 1.1, -14.0], "size": [2.4, 2.2, 2.4], "color": [0.32, 0.62, 0.58]},
            ],
        },
        {
            "id": third_region_id,
            "display_name": third_region_id.replace("_", " ").title(),
            "summary": str(region_seeds[2].get("purpose", "Seed elite encounters and stronger story beats")) if len(region_seeds) > 2 else "Seed elite encounters and stronger story beats",
            "spawn_point": [-72.0, 1.1, 8.0],
            "center": [-72.0, 0.0, 0.0],
            "sky_tint": [0.84, 0.80, 1.0],
            "region_objective_id": "echo_spire",
            "preview_landmarks": [
                {"id": f"{third_region_id}_spire", "position": [-76.0, 1.4, -11.0], "size": [3.4, 3.6, 3.4], "color": [0.44, 0.42, 0.62]},
                {"id": f"{third_region_id}_signal", "position": [-63.0, 1.0, -13.0], "size": [2.6, 2.1, 2.6], "color": [0.58, 0.44, 0.66]},
            ],
        },
    ]
    region_objectives = [
        {
            "id": "cloudstep_relay",
            "region_id": second_region_id,
            "label": "Stabilize the Survey Relay",
            "summary": "Activate the basin relay and secure a cleaner route for future expansion passes.",
            "reward_id": "basin_insight",
            "encounter_id": "cloudstep_relay_push",
            "position": [81.0, 0.0, -14.0],
            "color": [0.44, 0.86, 0.78],
            "travel_hint": "Head toward the basin relay and stabilize the route.",
        },
        {
            "id": "echo_spire",
            "region_id": third_region_id,
            "label": "Calibrate the Echo Spire",
            "summary": "Re-tune the observatory spire to reveal stronger frontier signals.",
            "reward_id": "watch_resonance",
            "encounter_id": "echo_spire_hold",
            "position": [-76.0, 0.0, -11.0],
            "color": [0.86, 0.74, 1.0],
            "travel_hint": "Climb to the spire and restore the observatory signal.",
        },
    ]
    region_spawn_map = {layout["id"]: layout["spawn_point"] for layout in region_layouts}
    region_gateway_specs = [
        {
            "id": f"{second_region_id}_gateway",
            "region_id": starter_region_id,
            "target_region": second_region_id,
            "target_spawn": region_spawn_map.get(second_region_id, [72.0, 1.1, 8.0]),
            "biome": str(region_seeds[1].get("biome", "frontier")) if len(region_seeds) > 1 else "frontier",
            "summary": str(region_seeds[1].get("purpose", "expand the next authored region")) if len(region_seeds) > 1 else "expand the next authored region",
            "position": [-12.0, 0.0, -17.0],
            "color": [0.55, 0.88, 1.0],
            "requires_primed": True,
        },
        {
            "id": f"{third_region_id}_gateway",
            "region_id": starter_region_id,
            "target_region": third_region_id,
            "target_spawn": region_spawn_map.get(third_region_id, [-72.0, 1.1, 8.0]),
            "biome": str(region_seeds[2].get("biome", "frontier")) if len(region_seeds) > 2 else "frontier",
            "summary": str(region_seeds[2].get("purpose", "expand the next authored region")) if len(region_seeds) > 2 else "expand the next authored region",
            "position": [12.0, 0.0, -17.0],
            "color": [0.98, 0.66, 0.32],
            "requires_primed": True,
        },
        {
            "id": f"return_to_{starter_region_id}_from_{second_region_id}",
            "region_id": second_region_id,
            "target_region": starter_region_id,
            "target_spawn": region_spawn_map.get(starter_region_id, [0.0, 1.1, 8.0]),
            "biome": "return route",
            "summary": "Return to the shrine district and continue the main arc.",
            "position": [60.0, 0.0, -17.0],
            "color": [0.74, 0.92, 0.96],
            "requires_primed": False,
        },
        {
            "id": f"return_to_{starter_region_id}_from_{third_region_id}",
            "region_id": third_region_id,
            "target_region": starter_region_id,
            "target_spawn": region_spawn_map.get(starter_region_id, [0.0, 1.1, 8.0]),
            "biome": "return route",
            "summary": "Return to the shrine district and continue the main arc.",
            "position": [-60.0, 0.0, -17.0],
            "color": [0.92, 0.82, 1.0],
            "requires_primed": False,
        },
    ]
    npc_beacon_specs = []
    npc_positions = {
        starter_region_id: [-10.0, 0.0, 6.0],
        second_region_id: [72.0, 0.0, 10.0],
        third_region_id: [-72.0, 0.0, 6.0],
    }
    npc_colors = (
        [0.98, 0.92, 0.54],
        [0.60, 0.98, 0.74],
        [0.92, 0.78, 1.0],
    )
    for index, npc in enumerate(npc_roster[:3]):
        home_region = npc.get("home_region", starter_region_id)
        npc_beacon_specs.append(
            {
                "id": npc.get("id", f"npc_{index}"),
                "name": str(npc.get("id", f"npc_{index}")).replace("_", " ").title(),
                "role": npc.get("role", "guide"),
                "function": npc.get("function", "supports the next quest branch"),
                "home_region": home_region,
                "region_id": home_region,
                "position": npc_positions.get(home_region, [0.0, 0.0, 0.0]),
                "color": npc_colors[index],
            }
        )
    active_arc = quest_arcs[0] if quest_arcs else {
        "id": "purification_path",
        "title": "Purification Path",
        "beat_count": 4,
    }
    enemy_archetypes = combat_packet.get("enemy_archetypes", [])
    enemy_defaults = []
    for enemy in enemy_archetypes:
        role = str(enemy.get("role", "close pressure")).lower()
        enemy_id = str(enemy.get("id", "sentinel"))
        if "guardian" in role or "boss" in role or "warden" in enemy_id:
            enemy_defaults.append(
                {
                    "id": enemy_id,
                    "pattern_profile_id": "shrine_guardian",
                    "combat_role": "boss",
                    "combat_tier": "boss",
                    "desired_range": 5.0,
                    "projectile_speed": 11.5,
                    "projectile_damage": 9,
                    "projectile_cooldown": 2.6,
                    "projectile_lifetime": 3.2,
                    "burst_projectile_count": 8,
                    "burst_projectile_speed": 8.5,
                    "burst_projectile_damage": 5,
                    "burst_cooldown": 4.4,
                    "phase_thresholds": [0.66, 0.33],
                    "max_poise": 8.0,
                    "poise_recovery_per_second": 1.1,
                    "stagger_duration": 0.40,
                }
            )
        elif "elite" in role or "detour" in role:
            enemy_defaults.append(
                {
                    "id": enemy_id,
                    "pattern_profile_id": "elite_vanguard",
                    "combat_role": "elite",
                    "combat_tier": "elite",
                    "desired_range": 2.7,
                    "projectile_speed": 0.0,
                    "projectile_damage": 0,
                    "projectile_cooldown": 0.0,
                    "projectile_lifetime": 0.0,
                    "burst_projectile_count": 0,
                    "burst_projectile_speed": 0.0,
                    "burst_projectile_damage": 0,
                    "burst_cooldown": 0.0,
                    "phase_thresholds": [0.5],
                    "max_poise": 5.4,
                    "poise_recovery_per_second": 1.2,
                    "stagger_duration": 0.36,
                }
            )
        elif "space" in role or "ranged" in role:
            enemy_defaults.append(
                {
                    "id": enemy_id,
                    "pattern_profile_id": "sentinel_volley",
                    "combat_role": "ranged",
                    "combat_tier": "standard",
                    "desired_range": 7.5,
                    "projectile_speed": 13.0,
                    "projectile_damage": 6,
                    "projectile_cooldown": 2.0,
                    "projectile_lifetime": 3.0,
                    "burst_projectile_count": 0,
                    "burst_projectile_speed": 0.0,
                    "burst_projectile_damage": 0,
                    "burst_cooldown": 0.0,
                    "phase_thresholds": [],
                    "max_poise": 2.6,
                    "poise_recovery_per_second": 1.6,
                    "stagger_duration": 0.28,
                }
            )
        else:
            enemy_defaults.append(
                {
                    "id": enemy_id,
                    "pattern_profile_id": "sentinel_duelist",
                    "combat_role": "melee",
                    "combat_tier": "standard",
                    "desired_range": 1.9,
                    "projectile_speed": 0.0,
                    "projectile_damage": 0,
                    "projectile_cooldown": 0.0,
                    "projectile_lifetime": 0.0,
                    "burst_projectile_count": 0,
                    "burst_projectile_speed": 0.0,
                    "burst_projectile_damage": 0,
                    "burst_cooldown": 0.0,
                    "phase_thresholds": [],
                    "max_poise": 3.0,
                    "poise_recovery_per_second": 1.4,
                    "stagger_duration": 0.32,
                }
            )
    melee_enemy_id = str(enemy_archetypes[0].get("id", "sentinel_melee")) if enemy_archetypes else "sentinel_melee"
    ranged_enemy_id = str(enemy_archetypes[1].get("id", "sentinel_ranged")) if len(enemy_archetypes) > 1 else "sentinel_ranged"
    elite_enemy_id = str(enemy_archetypes[2].get("id", "sentinel_elite")) if len(enemy_archetypes) > 2 else "sentinel_elite"
    boss_enemy_id = (
        str(enemy_archetypes[3].get("id", "shrine_warden"))
        if len(enemy_archetypes) > 3
        else str(enemy_archetypes[2].get("id", "shrine_warden")) if len(enemy_archetypes) > 2 else "shrine_warden"
    )
    basin_melee_enemy_id = f"{second_region_id}_sentinel_melee"
    basin_ranged_enemy_id = f"{second_region_id}_sentinel_ranged"
    watch_ranged_enemy_id = f"{third_region_id}_sentinel_ranged"
    watch_elite_enemy_id = f"{third_region_id}_sentinel_elite"
    patrol_routes = [
        {
            "id": "starter_watch_loop",
            "region_id": starter_region_id,
            "label": "Starter Watch Loop",
            "assigned_enemy_ids": [melee_enemy_id, ranged_enemy_id],
            "loop": True,
            "wait_seconds": 0.85,
            "path_points": [[-4.0, 0.0, -1.5], [1.5, 0.0, -5.5], [6.0, 0.0, -8.5]],
            "purpose": "keep the shrine approach under light pressure",
        },
        {
            "id": "cloudstep_relay_arc",
            "region_id": second_region_id,
            "label": "Cloudstep Relay Arc",
            "assigned_enemy_ids": [basin_melee_enemy_id, basin_ranged_enemy_id],
            "loop": True,
            "wait_seconds": 0.9,
            "path_points": [[73.5, 0.0, -4.5], [78.0, 0.0, -9.5], [82.0, 0.0, -13.0]],
            "purpose": "sweep the basin approach before the relay objective",
        },
        {
            "id": "echo_spire_sweep",
            "region_id": third_region_id,
            "label": "Echo Spire Sweep",
            "assigned_enemy_ids": [watch_ranged_enemy_id, watch_elite_enemy_id],
            "loop": True,
            "wait_seconds": 1.0,
            "path_points": [[-68.0, 0.0, -4.0], [-72.5, 0.0, -8.5], [-76.0, 0.0, -12.0]],
            "purpose": "hold the observatory lane before the spire can be reclaimed",
        },
    ]
    alert_networks = [
        {
            "id": "starter_intro_alert",
            "region_id": starter_region_id,
            "label": "Starter Intro Alert",
            "assigned_enemy_ids": [melee_enemy_id, ranged_enemy_id],
            "duration_seconds": 4.5,
            "search_duration_seconds": 3.0,
            "response_radius": 12.0,
            "anchor_point": [1.0, 0.0, -5.0],
            "purpose": "let shrine sentinels reinforce each other during the first route push",
        },
        {
            "id": "cloudstep_relay_alert",
            "region_id": second_region_id,
            "label": "Cloudstep Relay Alert",
            "assigned_enemy_ids": [basin_melee_enemy_id, basin_ranged_enemy_id],
            "duration_seconds": 5.0,
            "search_duration_seconds": 3.4,
            "response_radius": 14.0,
            "anchor_point": [79.0, 0.0, -10.0],
            "purpose": "let relay defenders collapse toward the basin alert lane",
        },
        {
            "id": "echo_spire_alert",
            "region_id": third_region_id,
            "label": "Echo Spire Alert",
            "assigned_enemy_ids": [watch_ranged_enemy_id, watch_elite_enemy_id],
            "duration_seconds": 5.5,
            "search_duration_seconds": 3.8,
            "response_radius": 14.0,
            "anchor_point": [-73.0, 0.0, -9.5],
            "purpose": "let observatory defenders reinforce the spire approach",
        },
    ]
    slice_manifest = {
        "spawn_point": [0.0, 1.1, 8.0],
        "shrine_position": [0.0, 0.0, -12.0],
        "landmarks": [
            {
                "id": "entry_arch",
                "region_id": starter_region_id,
                "position": [-8.0, 1.0, -9.0],
                "size": [2.5, 2.0, 2.5],
                "color": [0.35, 0.36, 0.41],
            },
            {
                "id": "combat_pocket",
                "region_id": starter_region_id,
                "position": [8.5, 1.25, -9.5],
                "size": [2.0, 2.5, 2.0],
                "color": [0.45, 0.34, 0.28],
            },
            {
                "id": "purification_shrine",
                "region_id": starter_region_id,
                "position": [0.0, 0.75, -18.0],
                "size": [6.0, 1.5, 2.5],
                "color": [0.30, 0.32, 0.37],
            },
        ],
        "enemies": [
            {
                "id": melee_enemy_id,
                "name": "Sentinel Alpha",
                "pattern_profile_id": "sentinel_duelist",
                "position": [-3.0, 1.0, -3.0],
                "color": [0.96, 0.35, 0.35],
                "max_health": 3,
                "contact_damage": 7,
                "move_speed": 3.8,
                "combat_role": "melee",
                "combat_tier": "standard",
                "squad_role": "vanguard",
                "region_id": starter_region_id,
                "critical_path": True,
                "max_poise": 3.0,
                "poise_recovery_per_second": 1.4,
                "stagger_duration": 0.32,
            },
            {
                "id": ranged_enemy_id,
                "name": "Sentinel Beta",
                "pattern_profile_id": "sentinel_volley",
                "position": [3.5, 1.0, -6.0],
                "color": [0.35, 0.80, 1.0],
                "max_health": 4,
                "contact_damage": 8,
                "move_speed": 3.2,
                "combat_role": "ranged",
                "combat_tier": "standard",
                "squad_role": "suppressor",
                "region_id": starter_region_id,
                "critical_path": True,
                "desired_range": 7.5,
                "projectile_speed": 13.0,
                "projectile_damage": 6,
                "projectile_cooldown": 2.0,
                "projectile_lifetime": 3.0,
                "max_poise": 2.6,
                "poise_recovery_per_second": 1.6,
                "stagger_duration": 0.28,
            },
            {
                "id": elite_enemy_id,
                "name": "Sentinel Vanguard",
                "pattern_profile_id": "elite_vanguard",
                "position": [10.5, 1.0, -8.5],
                "color": [0.88, 0.40, 0.88],
                "max_health": 7,
                "contact_damage": 10,
                "move_speed": 4.1,
                "combat_role": "elite",
                "combat_tier": "elite",
                "squad_role": "anchor",
                "region_id": starter_region_id,
                "critical_path": False,
                "desired_range": 2.7,
                "max_poise": 5.4,
                "poise_recovery_per_second": 1.2,
                "stagger_duration": 0.36,
                "phase_thresholds": [0.5],
            },
            {
                "id": boss_enemy_id,
                "name": "Shrine Warden",
                "pattern_profile_id": "shrine_guardian",
                "position": [0.0, 1.0, -13.5],
                "color": [0.92, 0.62, 0.24],
                "max_health": 10,
                "contact_damage": 12,
                "move_speed": 3.1,
                "combat_role": "boss",
                "combat_tier": "boss",
                "squad_role": "boss_anchor",
                "region_id": starter_region_id,
                "critical_path": True,
                "desired_range": 5.0,
                "projectile_speed": 11.5,
                "projectile_damage": 9,
                "projectile_cooldown": 2.6,
                "projectile_lifetime": 3.2,
                "burst_projectile_count": 8,
                "burst_projectile_speed": 8.5,
                "burst_projectile_damage": 5,
                "burst_cooldown": 4.4,
                "phase_thresholds": [0.66, 0.33],
                "max_poise": 8.0,
                "poise_recovery_per_second": 1.1,
                "stagger_duration": 0.40,
            },
            {
                "id": basin_melee_enemy_id,
                "archetype_id": melee_enemy_id,
                "name": "Cloudstep Reaver",
                "pattern_profile_id": "sentinel_duelist",
                "position": [76.5, 1.0, -9.0],
                "color": [0.62, 0.88, 0.70],
                "max_health": 4,
                "contact_damage": 8,
                "move_speed": 4.0,
                "combat_role": "melee",
                "combat_tier": "standard",
                "squad_role": "vanguard",
                "region_id": second_region_id,
                "critical_path": True,
                "max_poise": 3.4,
                "poise_recovery_per_second": 1.5,
                "stagger_duration": 0.30,
            },
            {
                "id": basin_ranged_enemy_id,
                "archetype_id": ranged_enemy_id,
                "name": "Cloudstep Spotter",
                "pattern_profile_id": "sentinel_volley",
                "position": [82.5, 1.0, -9.5],
                "color": [0.42, 0.90, 0.92],
                "max_health": 4,
                "contact_damage": 7,
                "move_speed": 3.4,
                "combat_role": "ranged",
                "combat_tier": "standard",
                "squad_role": "suppressor",
                "region_id": second_region_id,
                "critical_path": True,
                "desired_range": 8.0,
                "projectile_speed": 13.8,
                "projectile_damage": 6,
                "projectile_cooldown": 1.9,
                "projectile_lifetime": 3.2,
                "max_poise": 2.8,
                "poise_recovery_per_second": 1.7,
                "stagger_duration": 0.28,
            },
            {
                "id": watch_ranged_enemy_id,
                "archetype_id": ranged_enemy_id,
                "name": "Echo Watch Sniper",
                "pattern_profile_id": "sentinel_volley",
                "position": [-69.0, 1.0, -8.5],
                "color": [0.70, 0.76, 1.0],
                "max_health": 5,
                "contact_damage": 8,
                "move_speed": 3.5,
                "combat_role": "ranged",
                "combat_tier": "standard",
                "squad_role": "suppressor",
                "region_id": third_region_id,
                "critical_path": True,
                "desired_range": 8.4,
                "projectile_speed": 14.4,
                "projectile_damage": 7,
                "projectile_cooldown": 1.8,
                "projectile_lifetime": 3.3,
                "max_poise": 2.8,
                "poise_recovery_per_second": 1.7,
                "stagger_duration": 0.28,
            },
            {
                "id": watch_elite_enemy_id,
                "archetype_id": elite_enemy_id,
                "name": "Echo Watch Vanguard",
                "pattern_profile_id": "elite_vanguard",
                "position": [-77.0, 1.0, -8.0],
                "color": [0.92, 0.58, 1.0],
                "max_health": 8,
                "contact_damage": 11,
                "move_speed": 4.2,
                "combat_role": "elite",
                "combat_tier": "elite",
                "squad_role": "anchor",
                "region_id": third_region_id,
                "critical_path": True,
                "desired_range": 2.8,
                "max_poise": 5.8,
                "poise_recovery_per_second": 1.3,
                "stagger_duration": 0.36,
                "phase_thresholds": [0.55],
            },
        ],
        "npc_beacons": npc_beacon_specs,
        "region_gateways": region_gateway_specs,
        "reward_sites": [
            {
                "id": "overlook_cache",
                "label": "Overlook Cache",
                "reward_id": "route_sigil",
                "summary": "Optional elite cache that improves guard timing and stamina recovery.",
                "encounter_id": "overlook_elite_detour",
                "region_id": starter_region_id,
                "position": [13.0, 0.0, -12.5],
                "color": [0.96, 0.80, 0.38],
            }
        ],
        "active_arc": active_arc,
        "active_region_id": starter_region_id,
        "region_layouts": region_layouts,
        "region_objectives": region_objectives,
        "patrol_routes": patrol_routes,
        "alert_networks": alert_networks,
        "world_graph": {
            "nodes": [
                {
                    "id": layout["id"],
                    "display_name": layout["display_name"],
                    "summary": layout["summary"],
                    "region_objective_id": layout.get("region_objective_id", ""),
                }
                for layout in region_layouts
            ],
            "routes": [
                {
                    "id": gateway["id"],
                    "from_region": gateway["region_id"],
                    "to_region": gateway["target_region"],
                    "requires_primed": gateway.get("requires_primed", True),
                }
                for gateway in region_gateway_specs
            ],
            "regional_goals": [
                {
                    "region_id": objective["region_id"],
                    "objective_id": objective["id"],
                    "reward_id": objective["reward_id"],
                }
                for objective in region_objectives
            ],
            "patrol_lanes": [
                {
                    "region_id": route["region_id"],
                    "route_id": route["id"],
                    "assigned_enemy_ids": route["assigned_enemy_ids"],
                }
                for route in patrol_routes
            ],
            "guard_networks": [
                {
                    "region_id": network["region_id"],
                    "network_id": network["id"],
                    "assigned_enemy_ids": network["assigned_enemy_ids"],
                    "search_duration_seconds": network["search_duration_seconds"],
                    "anchor_point": network["anchor_point"],
                }
                for network in alert_networks
            ],
        },
        "encounters": [
            {
                "id": "ruin_intro_skirmish",
                "label": "Intro Skirmish",
                "region_id": starter_region_id,
                "enemy_ids": [
                    melee_enemy_id,
                    ranged_enemy_id,
                ],
                "start_position": [0.0, 1.0, -1.5],
                "activation_radius": 8.5,
                "hint": "Lock on, weave around the ranged line, and finish the escort cleanly.",
                "boss_enemy_id": "",
            },
            {
                "id": "overlook_elite_detour",
                "label": "Overlook Elite Detour",
                "region_id": starter_region_id,
                "enemy_ids": [
                    elite_enemy_id,
                ],
                "start_position": [9.5, 1.0, -7.5],
                "activation_radius": 6.8,
                "hint": "The side route hides an elite and a cache. Break the vanguard to earn the bonus reward.",
                "boss_enemy_id": "",
                "reward_site_id": "overlook_cache",
            },
            {
                "id": "shrine_guardian_finale",
                "label": "Shrine Guardian Finale",
                "region_id": starter_region_id,
                "enemy_ids": [
                    boss_enemy_id,
                ],
                "start_position": [0.0, 1.0, -11.0],
                "activation_radius": 7.5,
                "hint": "Read the telegraph, guard the burst opener, and punish the stagger window.",
                "boss_enemy_id": boss_enemy_id,
            },
            {
                "id": "cloudstep_relay_push",
                "label": "Cloudstep Relay Push",
                "region_id": second_region_id,
                "enemy_ids": [
                    basin_melee_enemy_id,
                    basin_ranged_enemy_id,
                ],
                "start_position": [79.5, 1.0, -10.5],
                "activation_radius": 7.2,
                "hint": "Break the basin defenders and stabilize the relay.",
                "boss_enemy_id": "",
            },
            {
                "id": "echo_spire_hold",
                "label": "Echo Spire Hold",
                "region_id": third_region_id,
                "enemy_ids": [
                    watch_ranged_enemy_id,
                    watch_elite_enemy_id,
                ],
                "start_position": [-73.5, 1.0, -9.0],
                "activation_radius": 7.0,
                "hint": "Clear the observatory defenders before calibrating the spire.",
                "boss_enemy_id": "",
            },
        ],
    }
    playable_roster = list(asset_pipeline.get("content_sets", {}).get("playable_roster", []) or [])
    starter_team = list(roster_strategy.get("starter_team", []) or [])
    starter_party_size = max(int(large_scale_profile.get("starter_party_size", len(starter_team) or len(playable_roster) or 1) or 1), 1)
    party_slots = []
    for index, hero in enumerate(starter_team, start=1):
        slot_id = f"slot_{index:02d}"
        fallback_seed = next(
            (
                dict(seed)
                for seed in playable_roster
                if str(seed.get("combat_role", "")).strip() == str(hero.get("combat_role", "")).strip()
            ),
            dict(playable_roster[index - 1]) if len(playable_roster) >= index else {},
        )
        hero_id = str(fallback_seed.get("id", hero.get("id", f"starter_hero_{index}"))).strip() or f"starter_hero_{index}"
        party_slots.append(
            {
                "slot_id": slot_id,
                "hero_id": hero_id,
                "display_name": str(fallback_seed.get("label", hero_id.replace("_", " ").title())),
                "combat_role": str(hero.get("combat_role", fallback_seed.get("combat_role", "vanguard"))),
                "combat_affinity": str(hero.get("combat_affinity", fallback_seed.get("combat_affinity", "steel"))),
                "release_window": str(hero.get("release_window", "launch")),
                "signature_job": str(hero.get("signature_job", "cover the core fantasy cleanly")),
            }
        )
    if not party_slots:
        for index, hero in enumerate(playable_roster[:starter_party_size], start=1):
            party_slots.append(
                {
                    "slot_id": f"slot_{index:02d}",
                    "hero_id": str(hero.get("id", f"starter_hero_{index}")),
                    "display_name": str(hero.get("label", f"Starter Hero {index}")),
                    "combat_role": str(hero.get("combat_role", "vanguard")),
                    "combat_affinity": str(hero.get("combat_affinity", "steel")),
                    "release_window": "launch",
                    "signature_job": "cover the core fantasy cleanly",
                }
            )
    active_party_slot_ids = [slot["slot_id"] for slot in party_slots[:starter_party_size]]
    active_affinities = []
    for slot in party_slots:
        affinity = str(slot.get("combat_affinity", "")).strip()
        if affinity and affinity not in active_affinities:
            active_affinities.append(affinity)

    if "elemental_reaction" in specialized:
        reaction_rules = [
            {"input": ["flare", "tide"], "result": "steam_burst", "combat_use": "widen stagger windows and splash pressure"},
            {"input": ["volt", "tide"], "result": "chain_current", "combat_use": "spread crowd control across grouped enemies"},
            {"input": ["gale", "flare"], "result": "wildfire_lift", "combat_use": "launch clustered enemies into aerial follow-ups"},
            {"input": ["frost", "terra"], "result": "crystal_lock", "combat_use": "pin elite targets before burst conversion"},
        ]
    else:
        reaction_rules = [
            {"input": ["steel", "guard"], "result": "break_guard", "combat_use": "open a short punish window on armored targets"},
            {"input": ["rush", "arc"], "result": "tempo_surge", "combat_use": "reward aggressive routing with faster cooldown cycling"},
        ]
    party_roster_payload = {
        "party_model": party_model,
        "swap_style": "fast_swap_combo_chain" if party_model != "single_hero_focus" else "single_hero_mastery",
        "swap_cooldown_seconds": 1.2 if party_model != "single_hero_focus" else 0.0,
        "starter_party_size": starter_party_size,
        "active_party_slot_ids": active_party_slot_ids,
        "party_slots": party_slots,
        "signature_roles": [str(slot.get("combat_role", "")) for slot in party_slots if str(slot.get("combat_role", "")).strip()],
    }
    elemental_matrix_payload = {
        "system_enabled": "elemental_reaction" in specialized,
        "affinity_order": active_affinities or list(roster_strategy.get("combat_affinities", []) or ["steel", "arc", "guard", "rush"]),
        "starter_affinities": active_affinities or ["steel"],
        "reaction_rules": reaction_rules,
    }
    world_streaming_payload = {
        "strategy": str(large_scale_profile.get("world_cell_strategy", "single_slice_lane")),
        "launch_region_target": int(large_scale_profile.get("launch_region_target", max(len(region_layouts), 1)) or max(len(region_layouts), 1)),
        "active_region_id": starter_region_id,
        "loaded_region_ids": [starter_region_id],
        "stream_cells": [
            {
                "cell_id": f"{layout.get('id', 'region')}_cell",
                "region_id": layout.get("id", "starter_ruins"),
                "load_priority": "critical" if index == 0 else "frontier",
                "stream_budget_class": "slice_core" if index == 0 else "preview_frontier",
                "entry_gateway_ids": [
                    str(gateway.get("id", ""))
                    for gateway in region_gateway_specs
                    if str(gateway.get("target_region", "")) == str(layout.get("id", ""))
                ],
            }
            for index, layout in enumerate(region_layouts)
        ],
        "transition_budget_seconds": 4.0 if party_model != "single_hero_focus" else 3.0,
        "runtime_delivery_track": dict(runtime_delivery_plan.get("delivery_tracks", {}) or {}),
    }
    commission_board_payload = {
        "service_model": str(live_ops_plan.get("service_model", "boxed_release_plus_expansions")),
        "content_cadence": str(
            live_ops_plan.get(
                "cadence",
                large_scale_profile.get("content_cadence", "major_expansion_packs"),
            )
        ),
        "active_commission_ids": ["starter_route_clear", "cloudstep_relay_support"],
        "commission_slots": [
            {
                "id": "starter_route_clear",
                "region_id": starter_region_id,
                "title": "Clear the Starter Route",
                "goal": "Re-run the shrine route and stabilize the onboarding lane.",
                "reward_type": "upgrade_materials",
            },
            {
                "id": "cloudstep_relay_support",
                "region_id": second_region_id,
                "title": "Support the Cloudstep Relay",
                "goal": "Stabilize the basin relay and keep the first frontier route open.",
                "reward_type": "region_progress",
            },
            {
                "id": "echo_watch_signal",
                "region_id": third_region_id,
                "title": "Restore the Echo Signal",
                "goal": "Hold the observatory lane and recalibrate the signal spire.",
                "reward_type": "boss_material",
            },
        ],
        "rotation_rules": [
            "Always keep one starter-route commission available for short re-entry sessions.",
            "Promote one frontier commission per newly active region before widening the pool.",
            "Map every commission back to the same region, party, and milestone memory artifacts.",
        ],
    }
    slice_manifest["party_roster"] = {
        "party_model": party_roster_payload["party_model"],
        "active_party_slot_ids": party_roster_payload["active_party_slot_ids"],
        "starter_party_size": party_roster_payload["starter_party_size"],
    }
    slice_manifest["elemental_matrix"] = {
        "system_enabled": elemental_matrix_payload["system_enabled"],
        "starter_affinities": elemental_matrix_payload["starter_affinities"],
    }
    slice_manifest["world_streaming"] = {
        "strategy": world_streaming_payload["strategy"],
        "active_region_id": world_streaming_payload["active_region_id"],
        "loaded_region_ids": world_streaming_payload["loaded_region_ids"],
    }
    slice_manifest["commission_board"] = {
        "service_model": commission_board_payload["service_model"],
        "active_commission_ids": commission_board_payload["active_commission_ids"],
    }
    payloads = {
        runtime_root / "data" / "system_specs.json": system_bundle,
        runtime_root / "data" / "combat.json": {
            "combat_loop": combat_packet.get("combat_loop", []),
            "enemy_archetypes": enemy_archetypes,
            "enemy_defaults": enemy_defaults,
            "encounter_templates": [
                {
                    "id": "ruin_intro_skirmish",
                    "label": "Intro Skirmish",
                    "enemies": [melee_enemy_id, ranged_enemy_id],
                    "goal": "teach movement, lock-on, and projectile pressure",
                    "director": {
                        "activation_radius": 8.5,
                        "start_position": [0.0, 1.0, -1.5],
                        "hint": "Lock on, pressure the ranged unit, and rotate around the melee bodyguard.",
                    },
                },
                {
                    "id": "overlook_elite_detour",
                    "label": "Overlook Elite Detour",
                    "enemies": [elite_enemy_id],
                    "goal": "teach side-route value with an optional elite and a reward cache",
                    "director": {
                        "activation_radius": 6.8,
                        "start_position": [9.5, 1.0, -7.5],
                        "hint": "Push off the main route, break the vanguard, and claim the detour cache.",
                        "reward_site_id": "overlook_cache",
                    },
                },
                {
                    "id": "shrine_guardian_finale",
                    "label": "Shrine Guardian Finale",
                    "enemies": [boss_enemy_id],
                    "goal": "close the slice with a boss-style telegraph and burst attack check",
                    "director": {
                        "activation_radius": 7.5,
                        "start_position": [0.0, 1.0, -11.0],
                        "boss_enemy_id": boss_enemy_id,
                        "hint": "Guard or dash the opener, break poise, and finish the guardian cleanly.",
                    },
                },
                {
                    "id": "cloudstep_relay_push",
                    "label": "Cloudstep Relay Push",
                    "enemies": [basin_melee_enemy_id, basin_ranged_enemy_id],
                    "goal": "secure the basin relay so the first frontier region becomes a real expansion beat",
                    "director": {
                        "activation_radius": 7.2,
                        "start_position": [79.5, 1.0, -10.5],
                        "hint": "Collapse the defenders, then stabilize the survey relay.",
                        "objective_id": "cloudstep_relay",
                    },
                },
                {
                    "id": "echo_spire_hold",
                    "label": "Echo Spire Hold",
                    "enemies": [watch_ranged_enemy_id, watch_elite_enemy_id],
                    "goal": "hold the observatory approach long enough to reclaim the spire",
                    "director": {
                        "activation_radius": 7.0,
                        "start_position": [-73.5, 1.0, -9.0],
                        "hint": "Crack the elite anchor, then finish the sniper to reclaim the spire.",
                        "objective_id": "echo_spire",
                    },
                },
            ],
            "pattern_library": {
                "sentinel_duelist": {
                    "id": "sentinel_duelist",
                    "label": "Sentinel Duelist",
                    "behavior_mode": "duelist",
                    "phase_profiles": [
                        {
                            "phase": 1,
                            "label": "Pressure Advance",
                            "attack_windup_seconds": 0.40,
                            "attack_cooldown": 1.05,
                            "lunge_speed": 0.0,
                            "lunge_distance_threshold": 0.0,
                            "move_speed_bonus": 0.0,
                            "contact_bonus": 0,
                            "hint": "The melee sentinel wants to pin you while the ranged unit covers space.",
                        }
                    ],
                },
                "sentinel_volley": {
                    "id": "sentinel_volley",
                    "label": "Sentinel Volley",
                    "behavior_mode": "kite_and_volley",
                    "phase_profiles": [
                        {
                            "phase": 1,
                            "label": "Volley Spacing",
                            "attack_windup_seconds": 0.0,
                            "attack_cooldown": 1.85,
                            "projectile_cooldown": 1.9,
                            "desired_range": 7.8,
                            "move_speed_bonus": 0.0,
                            "contact_bonus": 0,
                            "hint": "The ranged sentinel retreats to keep pressure on the lane.",
                        }
                    ],
                },
                "elite_vanguard": {
                    "id": "elite_vanguard",
                    "label": "Elite Vanguard",
                    "behavior_mode": "elite_brutalizer",
                    "phase_profiles": [
                        {
                            "phase": 1,
                            "label": "Detour Keeper",
                            "attack_windup_seconds": 0.46,
                            "attack_cooldown": 1.18,
                            "desired_range": 2.7,
                            "move_speed_bonus": 0.15,
                            "contact_bonus": 1,
                            "lunge_speed": 9.0,
                            "lunge_distance_threshold": 4.2,
                            "hint": "The vanguard guards the cache route with heavier melee pressure.",
                        },
                        {
                            "phase": 2,
                            "label": "Cache Breaker",
                            "attack_windup_seconds": 0.36,
                            "attack_cooldown": 0.96,
                            "desired_range": 2.4,
                            "move_speed_bonus": 0.38,
                            "contact_bonus": 3,
                            "lunge_speed": 10.4,
                            "lunge_distance_threshold": 4.8,
                            "hint": "Cache Breaker rushes harder once wounded. Guard cleanly or stagger it first.",
                        },
                    ],
                },
                "shrine_guardian": {
                    "id": "shrine_guardian",
                    "label": "Shrine Guardian",
                    "behavior_mode": "boss_pattern",
                    "phase_profiles": [
                        {
                            "phase": 1,
                            "label": "Survey Burst",
                            "attack_windup_seconds": 0.54,
                            "attack_cooldown": 1.55,
                            "projectile_cooldown": 2.5,
                            "burst_cooldown": 4.2,
                            "desired_range": 5.2,
                            "move_speed_bonus": 0.0,
                            "contact_bonus": 0,
                            "lunge_speed": 8.5,
                            "lunge_distance_threshold": 4.8,
                            "hint": "Survey Burst opens with measured pressure and tests your first defensive read.",
                        },
                        {
                            "phase": 2,
                            "label": "Resonant Chase",
                            "attack_windup_seconds": 0.46,
                            "attack_cooldown": 1.25,
                            "projectile_cooldown": 2.0,
                            "burst_cooldown": 3.3,
                            "desired_range": 4.5,
                            "move_speed_bonus": 0.35,
                            "contact_bonus": 2,
                            "lunge_speed": 10.0,
                            "lunge_distance_threshold": 5.4,
                            "hint": "Resonant Chase speeds up the guardian and compresses your punish windows.",
                        },
                        {
                            "phase": 3,
                            "label": "Final Breaker",
                            "attack_windup_seconds": 0.36,
                            "attack_cooldown": 0.95,
                            "projectile_cooldown": 1.65,
                            "burst_cooldown": 2.6,
                            "desired_range": 4.0,
                            "move_speed_bonus": 0.7,
                            "contact_bonus": 4,
                            "lunge_speed": 11.5,
                            "lunge_distance_threshold": 6.0,
                            "hint": "Final Breaker demands guard timing, stagger breaks, and disciplined stamina use.",
                        },
                    ],
                },
            },
            "player_actions": {
                "lock_on_enabled": True,
                "basic_attack_damage": 1,
                "combo_chain": [
                    {
                        "id": "light_slash_1",
                        "damage": 1,
                        "cooldown": 0.42,
                        "stamina_cost": 0.0,
                        "hit_range": 3.2,
                        "combo_window_seconds": 0.68,
                        "hit_reaction_seconds": 0.16,
                        "poise_damage": 1.0,
                    },
                    {
                        "id": "light_slash_2",
                        "damage": 2,
                        "cooldown": 0.38,
                        "stamina_cost": 6.0,
                        "hit_range": 3.35,
                        "combo_window_seconds": 0.62,
                        "hit_reaction_seconds": 0.20,
                        "poise_damage": 1.4,
                    },
                    {
                        "id": "light_slash_finisher",
                        "damage": 3,
                        "cooldown": 0.58,
                        "stamina_cost": 10.0,
                        "hit_range": 3.8,
                        "combo_window_seconds": 0.0,
                        "hit_reaction_seconds": 0.28,
                        "poise_damage": 2.6,
                    },
                ],
                "skill_loadout": {
                    "primary": {
                        "id": "focus_burst",
                        "name": "focus_burst",
                        "damage": 3,
                        "range": 5.6,
                        "stamina_cost": 32.0,
                        "cooldown": 2.2,
                        "hit_reaction_seconds": 0.34,
                        "poise_damage": 3.2,
                    },
                    "heavy": {
                        "id": "skybreak",
                        "name": "skybreak",
                        "damage": 5,
                        "range": 4.8,
                        "stamina_cost": 40.0,
                        "cooldown": 4.8,
                        "hit_reaction_seconds": 0.42,
                        "poise_damage": 4.8,
                    },
                },
                "skill_name": "focus_burst",
                "skill_damage": 3,
                "skill_range": 5.6,
                "skill_stamina_cost": 32.0,
                "skill_cooldown": 2.2,
                "guard": {
                    "enabled": True,
                    "stamina_drain_per_second": 12.0,
                    "damage_reduction": 0.72,
                    "perfect_guard_window_seconds": 0.18,
                    "counter_poise_damage": 3.6,
                },
                "player_hurt_reaction_seconds": 0.24,
                "dash_i_frames_seconds": 0.22,
            },
            "reward_hooks": combat_packet.get("reward_hooks", []),
            "encounter_budget": combat_packet.get("encounter_budget", {}),
        },
        runtime_root / "data" / "quest_flow.json": {
            "state_machine": quest_packet.get("state_machine", []),
            "objectives": quest_packet.get("slice_objectives", []),
            "rewards": quest_packet.get("reward_contract", {}),
            "active_arc": active_arc,
            "npc_briefings": [
                {
                    "npc_id": npc.get("id", ""),
                    "role": npc.get("role", "guide"),
                    "summary": npc.get("function", "supports the next quest branch"),
                }
                for npc in npc_roster
            ],
            "gateway_unlocks": [
                {
                    "gateway_id": gateway.get("id", ""),
                    "from_region": gateway.get("region_id", starter_region_id),
                    "target_region": gateway.get("target_region", ""),
                    "unlock_condition": "complete_current_slice" if gateway.get("requires_primed", True) else "always_available",
                }
                for gateway in region_gateway_specs
            ],
            "region_handoffs": [
                {
                    "region_id": objective["region_id"],
                    "objective_id": objective["id"],
                    "travel_hint": objective["travel_hint"],
                    "encounter_id": objective.get("encounter_id", ""),
                }
                for objective in region_objectives
            ],
        },
        runtime_root / "data" / "progression.json": progression_packet.get("reward_track", {}),
        runtime_root / "data" / "world_slice.json": {
            "zone_layout": world_packet.get("zone_layout", []),
            "landmarks": world_packet.get("landmarks", []),
            "asset_contracts": world_packet.get("asset_contracts", {}),
            "region_seed_ids": [region.get("id", "") for region in region_seeds],
            "active_arc_id": active_arc.get("id", ""),
            "patrol_route_ids": [route["id"] for route in patrol_routes],
            "alert_network_ids": [network["id"] for network in alert_networks],
        },
        runtime_root / "data" / "save_schema.json": save_packet.get("save_schema", {}),
        runtime_root / "data" / "slice_manifest.json": slice_manifest,
        runtime_root / "data" / "asset_registry.json": {
            "runtime": asset_pipeline.get("runtime", "godot"),
            "modeling_workspace": asset_pipeline.get("modeling_workspace", {}),
            "content_sets": asset_pipeline.get("content_sets", {}),
            "modeling_seed": asset_pipeline.get("modeling_seed", []),
        },
        runtime_root / "data" / "asset_import_profile.json": {
            "runtime_delivery": asset_pipeline.get("runtime_delivery", {}),
            "import_profile": asset_pipeline.get("import_profile", {}),
            "validation_rules": asset_pipeline.get("validation_rules", {}),
            "budget_profile": asset_pipeline.get("budget_profile", {}),
        },
        runtime_root / "data" / "region_seeds.json": {"regions": region_seeds},
        runtime_root / "data" / "region_layouts.json": {"regions": region_layouts, "active_region_id": starter_region_id},
        runtime_root / "data" / "region_objectives.json": {"objectives": region_objectives},
        runtime_root / "data" / "patrol_routes.json": {"routes": patrol_routes},
        runtime_root / "data" / "alert_networks.json": {"networks": alert_networks},
        runtime_root / "data" / "world_graph.json": slice_manifest["world_graph"],
        runtime_root / "data" / "npc_roster.json": {"npcs": npc_roster},
        runtime_root / "data" / "quest_arcs.json": {"quest_arcs": quest_arcs},
        runtime_root / "data" / "party_roster.json": party_roster_payload,
        runtime_root / "data" / "elemental_matrix.json": elemental_matrix_payload,
        runtime_root / "data" / "world_streaming.json": world_streaming_payload,
        runtime_root / "data" / "commission_board.json": commission_board_payload,
    }
    for path, payload in payloads.items():
        if _write_json(path, payload, overwrite):
            files.append(str(path))

    next_steps = "\n".join(
        [
            "# Godot Runtime Expansion Notes",
            "",
            "Use the generated data contracts to replace primitive slice content with authored assets and richer scene logic.",
            "",
            "Next upgrades:",
            "- swap primitive enemies for authored rigs and animation state machines",
            "- move quest and reward state into data-driven runtime resources",
            "- wire save schema to a real persistence service",
            "- grow region_seeds, npc_roster, and quest_arcs into multi-region content",
            "- expand the world slice into multiple streamed combat spaces",
            "- promote party_roster, elemental_matrix, world_streaming, and commission_board into authored runtime systems",
            "",
        ]
    )
    notes_path = runtime_root / "docs" / "next_steps.md"
    if _write_text(notes_path, next_steps, overwrite):
        files.append(str(notes_path))
    return files


def build_vertical_slice_project(
    output_dir: Path,
    *,
    prompt: str = "",
    game_request: Dict[str, Any] | None = None,
    blueprint: Dict[str, Any] | None = None,
    project_name: str = "",
    requested_runtime: str = "",
    existing_runtime: str = "",
    overwrite: bool = False,
    app_root: Path | None = None,
) -> Dict[str, Any]:
    """Compile a prompt, pick a runtime, and materialize a vertical-slice project."""

    root = Path(output_dir)
    existing_artifacts = load_existing_artifacts(root)
    compiled_request, production_directive = build_or_update_game_request(
        prompt,
        project_name=project_name or root.name or "Untitled Reverie Slice",
        requested_runtime=requested_runtime,
        existing_runtime=existing_runtime,
        base_request=game_request or existing_artifacts.get("artifacts/game_request.json", {}),
        existing_artifacts=existing_artifacts,
    )
    selection = select_runtime_profile(
        compiled_request,
        project_root=root,
        app_root=app_root,
        requested_runtime=requested_runtime,
        existing_runtime=existing_runtime,
    )
    reference_intelligence = dict(selection.get("reference_intelligence", {}) or {})
    runtime_profile = selection["profile"]
    selected_runtime = selection["selected_runtime"]
    adapter = selection["adapter"]

    built_blueprint = build_or_update_blueprint(
        compiled_request,
        runtime_profile=runtime_profile,
        base_blueprint=blueprint or existing_artifacts.get("artifacts/game_blueprint.json", {}),
        production_directive=production_directive,
    )
    if reference_intelligence:
        built_blueprint.setdefault("technical_strategy", {})["reference_strategy"] = {
            "reference_root": reference_intelligence.get("reference_root", ""),
            "recommended_stack": list(reference_intelligence.get("recommended_reference_stack", []) or []),
            "legal_guardrails": list(reference_intelligence.get("legal_guardrails", []) or []),
        }
    production_plan = build_production_plan(
        compiled_request,
        built_blueprint,
        runtime_profile=runtime_profile,
    )
    slice_plan = production_plan["vertical_slice"]
    system_bundle = build_system_packet_bundle(
        compiled_request,
        built_blueprint,
        runtime_profile=runtime_profile,
    )
    task_graph = build_task_graph(
        compiled_request,
        built_blueprint,
        system_bundle,
        runtime_profile=runtime_profile,
        production_plan=production_plan,
    )
    content_expansion = build_content_expansion_plan(
        compiled_request,
        built_blueprint,
        runtime_profile=runtime_profile,
    )
    content_expansion = evolve_content_expansion(
        content_expansion,
        game_request=compiled_request,
        blueprint=built_blueprint,
        production_directive=production_directive,
        existing_plan=existing_artifacts.get("artifacts/content_expansion.json", {}),
    )
    asset_pipeline = build_asset_pipeline_plan(
        compiled_request,
        built_blueprint,
        system_bundle,
        content_expansion,
        runtime_profile=runtime_profile,
    )
    if reference_intelligence:
        asset_pipeline["reference_stack"] = list(reference_intelligence.get("recommended_reference_stack", []) or [])
        asset_pipeline["reference_guardrails"] = list(reference_intelligence.get("legal_guardrails", []) or [])
    feature_matrix = build_feature_matrix(
        compiled_request,
        built_blueprint,
        system_bundle,
        runtime_profile=runtime_profile,
    )
    content_matrix = build_content_matrix(
        compiled_request,
        built_blueprint,
        content_expansion,
        asset_pipeline,
        runtime_profile=runtime_profile,
    )
    milestone_board = build_milestone_board(
        compiled_request,
        built_blueprint,
        production_plan,
        runtime_profile=runtime_profile,
    )
    risk_register = build_risk_register(
        compiled_request,
        built_blueprint,
        runtime_profile=runtime_profile,
    )
    runtime_capability_graph = build_runtime_capability_graph(compiled_request, selection)
    runtime_delivery_plan = build_runtime_delivery_plan(
        compiled_request,
        built_blueprint,
        selection,
        runtime_capability_graph,
        system_bundle=system_bundle,
    )
    game_program = build_game_program(
        compiled_request,
        built_blueprint,
        runtime_profile=runtime_profile,
        reference_intelligence=reference_intelligence,
        runtime_capability_graph=runtime_capability_graph,
    )
    character_kits = build_character_kits(
        compiled_request,
        built_blueprint,
        content_expansion,
        asset_pipeline,
        runtime_profile=runtime_profile,
    )
    environment_kits = build_environment_kits(
        compiled_request,
        built_blueprint,
        content_expansion,
        asset_pipeline,
        runtime_profile=runtime_profile,
    )
    animation_plan = build_animation_plan(
        compiled_request,
        built_blueprint,
        system_bundle,
        runtime_profile=runtime_profile,
    )
    asset_budget = build_asset_budget(
        compiled_request,
        built_blueprint,
        asset_pipeline,
        content_expansion,
        runtime_profile=runtime_profile,
    )
    world_program = build_world_program(
        compiled_request,
        built_blueprint,
        content_expansion,
        runtime_profile=runtime_profile,
    )
    world_program = evolve_world_program(
        world_program,
        content_expansion=content_expansion,
        production_directive=production_directive,
        existing_program=existing_artifacts.get("artifacts/world_program.json", {}),
    )
    region_kits = build_region_kits(
        compiled_request,
        built_blueprint,
        content_expansion,
        world_program,
    )
    faction_graph = build_faction_graph(
        compiled_request,
        built_blueprint,
        content_expansion,
        runtime_profile=runtime_profile,
    )
    questline_program = build_questline_program(
        compiled_request,
        built_blueprint,
        content_expansion,
        runtime_profile=runtime_profile,
    )
    save_migration_plan = build_save_migration_plan(
        compiled_request,
        built_blueprint,
        system_bundle,
        content_expansion,
        runtime_profile=runtime_profile,
    )
    design_intelligence = build_design_intelligence(
        compiled_request,
        built_blueprint,
        system_bundle,
        content_expansion,
        runtime_delivery_plan,
        reference_intelligence=reference_intelligence,
        runtime_profile=runtime_profile,
    )
    gameplay_factory = build_gameplay_factory(
        compiled_request,
        built_blueprint,
        system_bundle,
        content_expansion,
        design_intelligence=design_intelligence,
        runtime_profile=runtime_profile,
    )
    gameplay_factory = evolve_gameplay_factory(
        gameplay_factory,
        production_directive=production_directive,
        game_request=compiled_request,
        blueprint=built_blueprint,
        content_expansion=content_expansion,
        existing_factory=existing_artifacts.get("artifacts/gameplay_factory.json", {}),
    )
    boss_arc = build_boss_arc(
        compiled_request,
        built_blueprint,
        system_bundle,
        content_expansion,
        design_intelligence=design_intelligence,
        runtime_profile=runtime_profile,
    )
    boss_arc = evolve_boss_arc(
        boss_arc,
        production_directive=production_directive,
        content_expansion=content_expansion,
        existing_arc=existing_artifacts.get("artifacts/boss_arc.json", {}),
    )
    campaign_program = build_campaign_program(
        compiled_request,
        built_blueprint,
        content_expansion,
        world_program,
        faction_graph,
        runtime_profile=runtime_profile,
    )
    roster_strategy = build_roster_strategy(
        compiled_request,
        built_blueprint,
        gameplay_factory,
        character_kits,
        runtime_profile=runtime_profile,
    )
    live_ops_plan = build_live_ops_plan(
        compiled_request,
        built_blueprint,
        campaign_program,
        roster_strategy,
        runtime_delivery_plan,
        runtime_profile=runtime_profile,
    )
    production_operating_model = build_production_operating_model(
        compiled_request,
        built_blueprint,
        selection,
        runtime_delivery_plan,
        asset_pipeline,
        reference_intelligence=reference_intelligence,
        runtime_profile=runtime_profile,
    )

    project_name = str(
        built_blueprint.get("meta", {}).get("project_name")
        or compiled_request.get("meta", {}).get("project_name")
        or root.name
        or "Untitled Reverie Slice"
    )

    runtime_result = adapter.create_project(
        root,
        project_name=project_name,
        game_request=compiled_request,
        blueprint=built_blueprint,
        overwrite=overwrite,
    )
    modeling_workspace = _seed_modeling_workspace(
        root,
        asset_pipeline,
        overwrite=overwrite,
    )

    written_artifacts: list[str] = []
    artifact_payloads = {
        root / "artifacts" / "production_directive.json": production_directive,
        root / "artifacts" / "game_request.json": compiled_request,
        root / "artifacts" / "game_blueprint.json": built_blueprint,
        root / "artifacts" / "runtime_registry.json": {
            "selected_runtime": selected_runtime,
            "reason": selection["reason"],
            "fallback_reason": selection["fallback_reason"],
            "profiles": selection["profiles"],
            "reference_alignment": selection.get("reference_alignment", {}),
        },
        root / "artifacts" / "reference_intelligence.json": reference_intelligence,
        root / "artifacts" / "production_plan.json": production_plan,
        root / "artifacts" / "system_specs.json": system_bundle,
        root / "artifacts" / "task_graph.json": task_graph,
        root / "artifacts" / "game_program.json": game_program,
        root / "artifacts" / "feature_matrix.json": feature_matrix,
        root / "artifacts" / "content_matrix.json": content_matrix,
        root / "artifacts" / "design_intelligence.json": design_intelligence,
        root / "artifacts" / "campaign_program.json": campaign_program,
        root / "artifacts" / "roster_strategy.json": roster_strategy,
        root / "artifacts" / "live_ops_plan.json": live_ops_plan,
        root / "artifacts" / "production_operating_model.json": production_operating_model,
        root / "artifacts" / "milestone_board.json": milestone_board,
        root / "artifacts" / "risk_register.json": risk_register,
        root / "artifacts" / "runtime_capability_graph.json": runtime_capability_graph,
        root / "artifacts" / "runtime_delivery_plan.json": runtime_delivery_plan,
        root / "artifacts" / "content_expansion.json": content_expansion,
        root / "artifacts" / "asset_pipeline.json": asset_pipeline,
        root / "artifacts" / "character_kits.json": character_kits,
        root / "artifacts" / "environment_kits.json": environment_kits,
        root / "artifacts" / "animation_plan.json": animation_plan,
        root / "artifacts" / "asset_budget.json": asset_budget,
        root / "artifacts" / "world_program.json": world_program,
        root / "artifacts" / "region_kits.json": region_kits,
        root / "artifacts" / "faction_graph.json": faction_graph,
        root / "artifacts" / "questline_program.json": questline_program,
        root / "artifacts" / "save_migration_plan.json": save_migration_plan,
        root / "artifacts" / "gameplay_factory.json": gameplay_factory,
        root / "artifacts" / "boss_arc.json": boss_arc,
        root / "artifacts" / "telemetry_schema.json": _telemetry_schema(compiled_request, built_blueprint),
    }
    for path, payload in artifact_payloads.items():
        if _write_json(path, payload, True):
            written_artifacts.append(str(path))

    artifact_texts = {
        root / "artifacts" / "vertical_slice_plan.md": vertical_slice_markdown(slice_plan),
        root / "artifacts" / "production_plan.md": production_plan_markdown(production_plan),
        root / "artifacts" / "system_specs.md": system_packet_markdown(system_bundle),
        root / "artifacts" / "task_graph.md": task_graph_markdown(task_graph),
        root / "artifacts" / "content_expansion.md": content_expansion_markdown(content_expansion),
        root / "artifacts" / "asset_pipeline.md": asset_pipeline_markdown(asset_pipeline),
        root / "artifacts" / "game_bible.md": game_bible_markdown(game_program),
        root / "artifacts" / "design_playbook.md": design_playbook_markdown(design_intelligence),
        root / "playtest" / "test_plan.md": _playtest_plan_markdown(compiled_request, built_blueprint),
    }
    for path, payload in artifact_texts.items():
        if _write_text(path, payload, True):
            written_artifacts.append(str(path))

    extra_runtime_files: list[str] = []
    if selected_runtime == "reverie_engine":
        extra_runtime_files.extend(
            _augment_reverie_engine_slice(
                root,
                compiled_request,
                built_blueprint,
                system_bundle,
                content_expansion,
                asset_pipeline,
                overwrite=overwrite,
            )
        )
    if selected_runtime == "godot":
        extra_runtime_files.extend(
            _augment_godot_slice(
                root,
                compiled_request,
                system_bundle,
                content_expansion,
                asset_pipeline,
                roster_strategy=roster_strategy,
                live_ops_plan=live_ops_plan,
                runtime_delivery_plan=runtime_delivery_plan,
                overwrite=overwrite,
            )
        )

    verification = adapter.validate_project(root)
    slice_score = evaluate_slice_score(
        compiled_request,
        built_blueprint,
        system_bundle,
        runtime_profile=runtime_profile,
        runtime_result=runtime_result,
        verification=verification,
    )
    expansion_backlog = build_expansion_backlog(
        compiled_request,
        built_blueprint,
        task_graph,
        content_expansion,
        slice_score=slice_score,
        production_directive=production_directive,
    )
    resume_state = build_resume_state(
        compiled_request,
        built_blueprint,
        production_plan,
        task_graph,
        content_expansion,
        expansion_backlog,
        runtime_profile=runtime_profile,
        verification=verification,
        slice_score=slice_score,
        production_directive=production_directive,
    )
    quality_gates = build_quality_gate_report(
        compiled_request,
        built_blueprint,
        system_bundle,
        runtime_profile=runtime_profile,
        verification=verification,
        slice_score=slice_score,
        asset_pipeline=asset_pipeline,
        design_intelligence=design_intelligence,
    )
    performance_budget = build_performance_budget(
        compiled_request,
        built_blueprint,
        asset_pipeline,
        design_intelligence=design_intelligence,
        runtime_profile=runtime_profile,
    )
    combat_feel_report = build_combat_feel_report(
        compiled_request,
        built_blueprint,
        system_bundle,
        slice_score=slice_score,
        design_intelligence=design_intelligence,
    )
    continuation_recommendations = build_continuation_recommendations(
        compiled_request,
        built_blueprint,
        production_plan,
        task_graph,
        expansion_backlog,
        resume_state,
        slice_score=slice_score,
        quality_gates=quality_gates,
        world_program=world_program,
        reference_intelligence=reference_intelligence,
        production_directive=production_directive,
        campaign_program=campaign_program,
        roster_strategy=roster_strategy,
        live_ops_plan=live_ops_plan,
        production_operating_model=production_operating_model,
        design_intelligence=design_intelligence,
    )
    score_payloads = {
        root / "playtest" / "quality_gates.json": quality_gates,
        root / "playtest" / "performance_budget.json": performance_budget,
        root / "playtest" / "combat_feel_report.json": combat_feel_report,
        root / "playtest" / "slice_score.json": slice_score,
        root / "artifacts" / "expansion_backlog.json": expansion_backlog,
        root / "artifacts" / "resume_state.json": resume_state,
    }
    for path, payload in score_payloads.items():
        if _write_json(path, payload, True):
            written_artifacts.append(str(path))

    score_texts = {
        root / "playtest" / "slice_score.md": slice_score_markdown(slice_score),
        root / "artifacts" / "expansion_backlog.md": expansion_backlog_markdown(expansion_backlog),
        root / "artifacts" / "resume_state.md": resume_state_markdown(resume_state),
        root / "playtest" / "continuation_recommendations.md": continuation_recommendations_markdown(continuation_recommendations),
    }
    for path, payload in score_texts.items():
        if _write_text(path, payload, True):
            written_artifacts.append(str(path))

    return {
        "project_root": str(root),
        "runtime": selected_runtime,
        "runtime_profile": runtime_profile,
        "runtime_result": runtime_result,
        "verification": verification,
        "production_directive": production_directive,
        "game_request": compiled_request,
        "blueprint": built_blueprint,
        "production_plan": production_plan,
        "system_bundle": system_bundle,
        "task_graph": task_graph,
        "content_expansion": content_expansion,
        "asset_pipeline": asset_pipeline,
        "game_program": game_program,
        "feature_matrix": feature_matrix,
        "content_matrix": content_matrix,
        "design_intelligence": design_intelligence,
        "campaign_program": campaign_program,
        "roster_strategy": roster_strategy,
        "live_ops_plan": live_ops_plan,
        "production_operating_model": production_operating_model,
        "milestone_board": milestone_board,
        "risk_register": risk_register,
        "reference_intelligence": reference_intelligence,
        "runtime_capability_graph": runtime_capability_graph,
        "runtime_delivery_plan": runtime_delivery_plan,
        "character_kits": character_kits,
        "environment_kits": environment_kits,
        "animation_plan": animation_plan,
        "asset_budget": asset_budget,
        "world_program": world_program,
        "region_kits": region_kits,
        "faction_graph": faction_graph,
        "questline_program": questline_program,
        "save_migration_plan": save_migration_plan,
        "gameplay_factory": gameplay_factory,
        "boss_arc": boss_arc,
        "expansion_backlog": expansion_backlog,
        "resume_state": resume_state,
        "quality_gates": quality_gates,
        "performance_budget": performance_budget,
        "combat_feel_report": combat_feel_report,
        "continuation_recommendations": continuation_recommendations,
        "slice_score": slice_score,
        "modeling_workspace": modeling_workspace,
        "written_artifacts": written_artifacts,
        "runtime_files": runtime_result.get("files", []) + extra_runtime_files + modeling_workspace.get("files", []),
    }
