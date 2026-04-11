"""Game-program compilation for large-scale Reverie-Gamer production."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List

from .system_generators.shared import project_name, target_runtime


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _references(game_request: Dict[str, Any]) -> List[str]:
    return [
        str(item).strip()
        for item in game_request.get("creative_target", {}).get("references", [])
        if str(item).strip()
    ]


def _pillars(blueprint: Dict[str, Any]) -> List[str]:
    values = [
        str(item).strip()
        for item in blueprint.get("creative_direction", {}).get("pillars", [])
        if str(item).strip()
    ]
    return values or [
        "deliver a strong player fantasy inside the first playable hour",
        "keep combat, traversal, and objectives readable under pressure",
        "grow the project through reusable world, system, and asset contracts",
    ]


def _high_concept(game_request: Dict[str, Any], blueprint: Dict[str, Any]) -> str:
    creative = game_request.get("creative_target", {})
    experience = game_request.get("experience", {})
    references = _references(game_request)
    reference_text = f" with reference energy from {', '.join(references)}" if references else ""
    return (
        f"{experience.get('dimension', '3D')} {creative.get('primary_genre', 'action_rpg')} project"
        f" centered on {experience.get('movement_model', 'exploration')} and"
        f" {experience.get('combat_model', 'ability_action')}{reference_text}."
    )


def _design_operating_system(game_request: Dict[str, Any]) -> Dict[str, Any]:
    experience = dict(game_request.get("experience", {}) or {})
    production = dict(game_request.get("production", {}) or {})
    world_structure = str(experience.get("world_structure", "regional_action_slice"))
    party_model = str(experience.get("party_model", "single_hero_focus"))
    live_service_profile = dict(production.get("live_service_profile", {}) or {})
    aesthetics = ["fantasy", "challenge", "discovery"]
    if party_model != "single_hero_focus":
        aesthetics.append("expression")
    if world_structure == "hub_and_districts":
        aesthetics.append("fellowship")
    aesthetics.append("narrative")
    return {
        "default_capabilities": list(production.get("default_design_capabilities", []) or []),
        "primary_aesthetics": aesthetics,
        "difficulty_model": "flow_ramp_with_dynamic_support",
        "feedback_model": "telegraph_confirm_payoff",
        "accessibility_bar": "subtitles_remapping_toggle_hold_audio_visual_redundancy",
        "service_model": "live_service" if live_service_profile.get("enabled") else "slice_first_campaign_growth",
    }


def _signature_systems(game_request: Dict[str, Any]) -> List[str]:
    production = dict(game_request.get("production", {}) or {})
    profile = dict(production.get("large_scale_profile", {}) or {})
    if profile.get("signature_systems"):
        return [str(item).strip() for item in profile.get("signature_systems", []) if str(item).strip()]
    systems = [
        str(item).strip()
        for item in game_request.get("systems", {}).get("specialized", []) or []
        if str(item).strip()
    ]
    systems.extend(
        str(item).strip()
        for item in game_request.get("systems", {}).get("required", []) or []
        if str(item).strip() in {"combat", "movement", "quest", "progression", "world_slice"}
    )
    return list(dict.fromkeys(systems))


def build_game_program(
    game_request: Dict[str, Any],
    blueprint: Dict[str, Any],
    *,
    runtime_profile: Dict[str, Any] | None = None,
) -> Dict[str, Any]:
    """Compile a durable project program from the request and blueprint."""

    creative = dict(game_request.get("creative_target", {}) or {})
    experience = dict(game_request.get("experience", {}) or {})
    production = dict(game_request.get("production", {}) or {})
    quality = dict(game_request.get("quality_targets", {}) or {})
    content_scale = dict(production.get("content_scale", {}) or {})
    genre_tags = {str(item).strip() for item in creative.get("genre_tags", []) if str(item).strip()}
    reference_titles = _references(game_request)
    lowered_reference_titles = {item.lower() for item in reference_titles}
    large_scale_signal = "open_world" in genre_tags or bool(lowered_reference_titles & {"genshin impact", "wuthering waves", "zenless zone zero"})
    target_class = "large_scale_3d_action_rpg_base" if large_scale_signal else "regional_action_rpg_base"
    required_systems = [
        str(item).strip()
        for item in game_request.get("systems", {}).get("required", [])
        if str(item).strip()
    ]
    specialized_systems = [
        str(item).strip()
        for item in game_request.get("systems", {}).get("specialized", [])
        if str(item).strip()
    ]
    deferred = [
        str(item).strip()
        for item in production.get("deferred_features", [])
        if str(item).strip()
    ]
    live_service_profile = dict(production.get("live_service_profile", {}) or {})
    large_scale_profile = dict(production.get("large_scale_profile", {}) or {})
    launch_region_target = int(large_scale_profile.get("launch_region_target", 1) or 1)
    starter_party_size = int(large_scale_profile.get("starter_party_size", 1) or 1)
    runtime_contracts = [
        str(item).strip()
        for item in large_scale_profile.get("runtime_contracts", []) or []
        if str(item).strip()
    ]
    signature_systems = _signature_systems(game_request)

    return {
        "schema_version": "reverie.game_program/1",
        "project_name": project_name(game_request, blueprint),
        "generated_at": _utc_now(),
        "runtime": target_runtime(blueprint, runtime_profile),
        "source_prompt": game_request.get("source_prompt", ""),
        "high_concept": _high_concept(game_request, blueprint),
        "target_class": target_class,
        "program_thesis": (
            "Build a prompt-born 3D production base that can ship one verified slice quickly"
            " and continue into region-by-region growth without losing continuity."
        ),
        "signature_systems": signature_systems,
        "creative_direction": {
            "pillars": _pillars(blueprint),
            "tone": creative.get("tone", "heroic, kinetic, and exploratory"),
            "art_direction": dict(creative.get("art_direction", {}) or {}),
            "references": reference_titles,
            "reference_profile": dict(creative.get("reference_profile", {}) or {}),
        },
        "experience_contract": {
            "dimension": experience.get("dimension", "3D"),
            "camera_model": experience.get("camera_model", "third_person"),
            "movement_model": experience.get("movement_model", "third_person_action"),
            "combat_model": experience.get("combat_model", "ability_action"),
            "world_structure": experience.get("world_structure", "regional_action_slice"),
            "party_model": experience.get("party_model", "single_hero_focus"),
            "progression_model": experience.get("progression_model", "ability_unlocks_and_rewards"),
            "combat_pacing": experience.get("combat_pacing", "readable_action_rpg"),
            "core_loop": list(experience.get("core_loop", []) or []),
            "meta_loop": list(experience.get("meta_loop", []) or []),
            "player_verbs": list(experience.get("player_verbs", []) or []),
        },
        "world_direction": {
            "world_model": "multi_region_open_world" if "open_world" in genre_tags else "hub_and_frontier_regions",
            "world_structure": experience.get("world_structure", "regional_action_slice"),
            "delivery_target": content_scale.get("delivery_target", "single_region_vertical_slice"),
            "requested_scale": content_scale.get("requested_scale", "single_slice"),
            "slice_spaces": int(content_scale.get("slice_spaces", 1) or 1),
            "enemy_families": int(content_scale.get("enemy_families", 1) or 1),
            "boss_encounters": int(content_scale.get("boss_encounters", 0) or 0),
            "quest_count": int(content_scale.get("quest_count", 1) or 1),
        },
        "vertical_slice_contract": {
            "slice_role": "large_scale_proof_slice" if large_scale_signal else "regional_foundation_slice",
            "one_prompt_pipeline": str(
                production.get(
                    "one_prompt_goal",
                    "prompt -> game program -> runtime foundation -> verified 3d slice -> continuity pack",
                )
            ),
            "proves": [
                "runtime-aware project foundation",
                "repeatable combat and traversal loop",
                "region and quest continuity memory",
                "scale-up contracts for future regions, party growth, and live cadence" if large_scale_signal else "expansion-ready continuity",
            ],
            "runtime_contracts": runtime_contracts,
        },
        "large_scale_blueprint": {
            "project_shape": str(large_scale_profile.get("project_shape", "regional_action_rpg")),
            "world_cell_strategy": str(large_scale_profile.get("world_cell_strategy", "single_slice_lane")),
            "launch_region_target": launch_region_target,
            "post_launch_region_target": int(large_scale_profile.get("post_launch_region_target", max(launch_region_target, 2)) or max(launch_region_target, 2)),
            "starter_party_size": starter_party_size,
            "content_cadence": str(
                large_scale_profile.get(
                    "content_cadence",
                    live_service_profile.get("cadence", "major_expansion_packs"),
                )
            ),
            "presentation_goal": str(
                large_scale_profile.get(
                    "presentation_goal",
                    "Large-scale 3D action foundation with readable production lanes.",
                )
            ),
        },
        "design_operating_system": _design_operating_system(game_request),
        "scale_tracks": {
            "campaign_track": "multi_region_chapter_growth" if large_scale_signal else "single_slice_to_frontier_growth",
            "roster_track": (
                "swap_party_collection_program"
                if experience.get("party_model", "single_hero_focus") != "single_hero_focus"
                else "hero_mastery_program"
            ),
            "live_ops_track": (
                str(live_service_profile.get("cadence", "six_week_content_cycles"))
                if live_service_profile.get("enabled")
                else "premium_expansion_packs"
            ),
            "operating_model": "slice_first_production_os",
            "director_artifacts": [
                "artifacts/campaign_program.json",
                "artifacts/roster_strategy.json",
                "artifacts/live_ops_plan.json",
                "artifacts/production_operating_model.json",
            ],
        },
        "production_contract": {
            "requested_scope": production.get("requested_scope", "vertical_slice"),
            "delivery_scope": production.get("delivery_scope", "vertical_slice"),
            "complexity_score": int(production.get("complexity_score", 0) or 0),
            "required_systems": required_systems,
            "specialized_systems": specialized_systems,
            "deferred_features": deferred,
            "known_risks": list(production.get("known_risks", []) or []),
            "slice_targets": list(production.get("slice_targets", []) or []),
            "live_service_profile": live_service_profile,
            "one_prompt_goal": str(
                production.get("one_prompt_goal", "prompt -> game program -> runtime foundation -> verified 3d slice -> continuity pack")
            ),
        },
        "success_criteria": {
            "target_fps": int(quality.get("target_fps", 60) or 60),
            "target_load_time_seconds": int(quality.get("target_load_time_seconds", 12) or 12),
            "slice_playable_minutes": int(quality.get("slice_playable_minutes", 20) or 20),
            "must_have": list(quality.get("must_have", []) or []),
        },
    }


def game_bible_markdown(program: Dict[str, Any]) -> str:
    """Render a readable game bible from the game program."""

    lines = [f"# Game Bible: {program.get('project_name', 'Untitled Reverie Project')}", ""]
    lines.append(f"Runtime: {program.get('runtime', 'reverie_engine')}")
    lines.append(f"Target Class: {program.get('target_class', 'regional_action_rpg_base')}")
    lines.append("")
    lines.append("## High Concept")
    lines.append(str(program.get("high_concept", "")))
    lines.append("")
    lines.append("## Program Thesis")
    lines.append(str(program.get("program_thesis", "")))
    lines.append("")
    lines.append("## Pillars")
    for item in program.get("creative_direction", {}).get("pillars", []):
        lines.append(f"- {item}")
    lines.append("")
    lines.append("## Experience Contract")
    for key, value in program.get("experience_contract", {}).items():
        if isinstance(value, list):
            lines.append(f"- {key}:")
            for item in value:
                lines.append(f"  - {item}")
        else:
            lines.append(f"- {key}: {value}")
    lines.append("")
    lines.append("## World Direction")
    for key, value in program.get("world_direction", {}).items():
        lines.append(f"- {key}: {value}")
    lines.append("")
    lines.append("## Design Operating System")
    for key, value in program.get("design_operating_system", {}).items():
        if isinstance(value, list):
            lines.append(f"- {key}:")
            for item in value:
                lines.append(f"  - {item}")
        else:
            lines.append(f"- {key}: {value}")
    lines.append("")
    lines.append("## Scale Tracks")
    for key, value in program.get("scale_tracks", {}).items():
        if isinstance(value, list):
            lines.append(f"- {key}:")
            for item in value:
                lines.append(f"  - {item}")
        else:
            lines.append(f"- {key}: {value}")
    lines.append("")
    lines.append("## Production Contract")
    for key, value in program.get("production_contract", {}).items():
        if isinstance(value, list):
            lines.append(f"- {key}:")
            for item in value:
                lines.append(f"  - {item}")
        else:
            lines.append(f"- {key}: {value}")
    lines.append("")
    lines.append("## Success Criteria")
    for key, value in program.get("success_criteria", {}).items():
        if isinstance(value, list):
            lines.append(f"- {key}:")
            for item in value:
                lines.append(f"  - {item}")
        else:
            lines.append(f"- {key}: {value}")
    lines.append("")
    return "\n".join(lines)
