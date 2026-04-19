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


def _platform_strategy(game_request: Dict[str, Any], runtime_profile: Dict[str, Any] | None) -> Dict[str, Any]:
    quality = dict(game_request.get("quality_targets", {}) or {})
    experience = dict(game_request.get("experience", {}) or {})
    production = dict(game_request.get("production", {}) or {})
    large_scale_profile = dict(production.get("large_scale_profile", {}) or {})
    explicit_targets = [
        str(item).strip()
        for item in quality.get("target_platforms", []) or []
        if str(item).strip()
    ]
    if not explicit_targets:
        explicit_targets = ["PC"]
        if str(experience.get("dimension", "3D")).upper() == "3D":
            explicit_targets.append("Console")
        if production.get("live_service_profile", {}).get("enabled"):
            explicit_targets.append("Mobile")
    runtime_id = str((runtime_profile or {}).get("id", "") or game_request.get("runtime_preferences", {}).get("preferred_runtime", "reverie_engine"))
    return {
        "target_platforms": explicit_targets,
        "primary_runtime": runtime_id,
        "rendering_priority": (
            "stylized_high_readability_3d"
            if str(experience.get("dimension", "3D")).upper() == "3D"
            else "fast_iteration_readability"
        ),
        "input_profiles": ["controller", "keyboard_mouse"] + (["touch_fallback"] if "Mobile" in explicit_targets else []),
        "optimization_bias": (
            "cross_platform_streaming_and_vfx_discipline"
            if int(large_scale_profile.get("launch_region_target", 1) or 1) >= 3
            else "slice_boot_speed_and_combat_feel"
        ),
    }


def _production_scale(
    game_request: Dict[str, Any],
    *,
    large_scale_signal: bool,
) -> Dict[str, Any]:
    production = dict(game_request.get("production", {}) or {})
    large_scale_profile = dict(production.get("large_scale_profile", {}) or {})
    live_service_profile = dict(production.get("live_service_profile", {}) or {})
    return {
        "project_scale": "large_scale" if large_scale_signal else "regional",
        "launch_region_target": int(large_scale_profile.get("launch_region_target", 1) or 1),
        "post_launch_region_target": int(large_scale_profile.get("post_launch_region_target", 2) or 2),
        "starter_party_size": int(large_scale_profile.get("starter_party_size", 1) or 1),
        "world_cell_strategy": str(large_scale_profile.get("world_cell_strategy", "single_slice_lane")),
        "content_cadence": str(
            large_scale_profile.get(
                "content_cadence",
                live_service_profile.get("cadence", "major_expansion_packs"),
            )
        ),
        "delivery_mode": "slice_first_then_live_growth" if live_service_profile.get("enabled") else "slice_first_then_campaign_growth",
    }


def _content_operating_model(game_request: Dict[str, Any]) -> Dict[str, Any]:
    production = dict(game_request.get("production", {}) or {})
    experience = dict(game_request.get("experience", {}) or {})
    live_service_profile = dict(production.get("live_service_profile", {}) or {})
    party_model = str(experience.get("party_model", "single_hero_focus"))
    tracks = [
        "main_chapter_delivery",
        "regional_route_and_landmark_kits",
        "boss_and_elite_progression",
        "questline_and_commission_refresh",
        "combat_balance_and_telegraph_polish",
    ]
    if party_model != "single_hero_focus":
        tracks.append("roster_wave_and_team_synergy_delivery")
    if live_service_profile.get("enabled"):
        tracks.append("event_and_version_cadence")
    return {
        "delivery_tracks": tracks,
        "authoring_lanes": [
            "design_program_and_risk",
            "runtime_and_systems",
            "world_and_quest",
            "character_and_roster",
            "environment_and_landmarks",
            "playtest_and_optimization",
        ],
        "release_train": {
            "launch": ["verified_slice", "starter_region_pack", "first_boss_arc"],
            "post_launch": (
                ["region_update", "character_wave", "event_story"]
                if live_service_profile.get("enabled")
                else ["campaign_expansion", "new_region", "boss_rematch_pack"]
            ),
        },
    }


def _technical_guardrails(
    game_request: Dict[str, Any],
    reference_intelligence: Dict[str, Any] | None,
    runtime_capability_graph: Dict[str, Any] | None,
) -> Dict[str, Any]:
    production = dict(game_request.get("production", {}) or {})
    quality = dict(game_request.get("quality_targets", {}) or {})
    large_scale_profile = dict(production.get("large_scale_profile", {}) or {})
    selected_summary = dict((runtime_capability_graph or {}).get("selected_summary", {}) or {})
    adoption_plan = list((reference_intelligence or {}).get("adoption_plan", []) or [])
    return {
        "runtime_contracts": [
            str(item).strip()
            for item in large_scale_profile.get("runtime_contracts", []) or []
            if str(item).strip()
        ],
        "selected_runtime_root": str(selected_summary.get("runtime_root", ".")),
        "performance_target": {
            "target_fps": int(quality.get("target_fps", 60) or 60),
            "target_load_time_seconds": int(quality.get("target_load_time_seconds", 12) or 12),
        },
        "authoring_rules": [
            "Protect readable silhouettes, encounter telegraphs, and landmark clarity before raw content breadth.",
            "Treat streaming, VFX density, AI density, and party size as one shared performance problem.",
            "Do not widen region count until the current slice keeps validation, combat feel, and asset import health stable together.",
        ],
        "reference_adoption": [str(item.get("id", "")).strip() for item in adoption_plan if str(item.get("id", "")).strip()],
    }


def _continuation_contract(
    game_request: Dict[str, Any],
    reference_intelligence: Dict[str, Any] | None,
) -> Dict[str, Any]:
    production = dict(game_request.get("production", {}) or {})
    return {
        "continuation_ready": bool(production.get("continuation_ready", False)),
        "resume_priority": [
            "artifacts/game_program.json",
            "artifacts/runtime_delivery_plan.json",
            "artifacts/world_program.json",
            "artifacts/gameplay_factory.json",
            "playtest/slice_score.json",
        ],
        "next_turn_operations": [
            "expand_region",
            "plan_boss_arc",
            "upgrade_gameplay_factory",
            "run_quality_gates",
        ],
        "reference_reopen_order": [
            str(item.get("id", "")).strip()
            for item in (reference_intelligence or {}).get("adoption_plan", []) or []
            if str(item.get("id", "")).strip()
        ],
    }


def build_game_program(
    game_request: Dict[str, Any],
    blueprint: Dict[str, Any],
    *,
    runtime_profile: Dict[str, Any] | None = None,
    reference_intelligence: Dict[str, Any] | None = None,
    runtime_capability_graph: Dict[str, Any] | None = None,
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
    aaa_product_profile: Dict[str, Any] = {}
    if str(production.get("target_quality", "")).strip().lower() == "aaa" or large_scale_signal:
        try:
            from .aaa_game_compiler import build_aaa_product_profile

            aaa_product_profile = build_aaa_product_profile(game_request)
        except Exception:
            aaa_product_profile = {}

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
        "production_scale": _production_scale(game_request, large_scale_signal=large_scale_signal),
        "platform_strategy": _platform_strategy(game_request, runtime_profile),
        "product_strategy": {
            "target_quality": str(production.get("target_quality", "aa")),
            "vision_statement": str(aaa_product_profile.get("vision_statement", "")),
            "target_audience": dict(aaa_product_profile.get("target_audience", {}) or {}),
            "unique_selling_points": list(aaa_product_profile.get("unique_selling_points", []) or []),
            "monetization_strategy": dict(aaa_product_profile.get("monetization_strategy", {}) or {}),
            "live_service_plan": dict(aaa_product_profile.get("live_service_plan", {}) or {}),
        },
        "world_fantasy": {
            "world_design": dict(aaa_product_profile.get("world_design", {}) or {}),
            "narrative_framework": dict(aaa_product_profile.get("narrative_framework", {}) or {}),
            "content_targets": dict(aaa_product_profile.get("content_targets", {}) or {}),
        },
        "content_operating_model": _content_operating_model(game_request),
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
        "technical_guardrails": _technical_guardrails(
            game_request,
            reference_intelligence,
            runtime_capability_graph,
        ),
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
        "continuation_contract": _continuation_contract(game_request, reference_intelligence),
        "success_criteria": {
            "target_fps": int(quality.get("target_fps", 60) or 60),
            "target_load_time_seconds": int(quality.get("target_load_time_seconds", 12) or 12),
            "slice_playable_minutes": int(quality.get("slice_playable_minutes", 20) or 20),
            "must_have": list(quality.get("must_have", []) or []),
        },
        "aaa_product_profile": aaa_product_profile,
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
    lines.append("## Platform Strategy")
    for key, value in program.get("platform_strategy", {}).items():
        if isinstance(value, list):
            lines.append(f"- {key}:")
            for item in value:
                lines.append(f"  - {item}")
        elif isinstance(value, dict):
            lines.append(f"- {key}:")
            for item_key, item_value in value.items():
                lines.append(f"  - {item_key}: {item_value}")
        else:
            lines.append(f"- {key}: {value}")
    lines.append("")
    lines.append("## Product Strategy")
    for key, value in program.get("product_strategy", {}).items():
        if isinstance(value, list):
            lines.append(f"- {key}:")
            for item in value:
                lines.append(f"  - {item}")
        elif isinstance(value, dict):
            lines.append(f"- {key}:")
            for item_key, item_value in value.items():
                lines.append(f"  - {item_key}: {item_value}")
        else:
            lines.append(f"- {key}: {value}")
    lines.append("")
    lines.append("## World Fantasy")
    for key, value in program.get("world_fantasy", {}).items():
        if isinstance(value, list):
            lines.append(f"- {key}:")
            for item in value:
                lines.append(f"  - {item}")
        elif isinstance(value, dict):
            lines.append(f"- {key}:")
            for item_key, item_value in value.items():
                lines.append(f"  - {item_key}: {item_value}")
        else:
            lines.append(f"- {key}: {value}")
    lines.append("")
    lines.append("## Content Operating Model")
    for key, value in program.get("content_operating_model", {}).items():
        if isinstance(value, list):
            lines.append(f"- {key}:")
            for item in value:
                lines.append(f"  - {item}")
        elif isinstance(value, dict):
            lines.append(f"- {key}:")
            for item_key, item_value in value.items():
                lines.append(f"  - {item_key}: {item_value}")
        else:
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
    lines.append("## Technical Guardrails")
    for key, value in program.get("technical_guardrails", {}).items():
        if isinstance(value, list):
            lines.append(f"- {key}:")
            for item in value:
                lines.append(f"  - {item}")
        elif isinstance(value, dict):
            lines.append(f"- {key}:")
            for item_key, item_value in value.items():
                lines.append(f"  - {item_key}: {item_value}")
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
    lines.append("## Continuation Contract")
    for key, value in program.get("continuation_contract", {}).items():
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
