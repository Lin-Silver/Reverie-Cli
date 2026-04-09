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
    deferred = [
        str(item).strip()
        for item in production.get("deferred_features", [])
        if str(item).strip()
    ]

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
        "creative_direction": {
            "pillars": _pillars(blueprint),
            "tone": creative.get("tone", "heroic, kinetic, and exploratory"),
            "art_direction": dict(creative.get("art_direction", {}) or {}),
            "references": reference_titles,
        },
        "experience_contract": {
            "dimension": experience.get("dimension", "3D"),
            "camera_model": experience.get("camera_model", "third_person"),
            "movement_model": experience.get("movement_model", "third_person_action"),
            "combat_model": experience.get("combat_model", "ability_action"),
            "core_loop": list(experience.get("core_loop", []) or []),
            "meta_loop": list(experience.get("meta_loop", []) or []),
            "player_verbs": list(experience.get("player_verbs", []) or []),
        },
        "world_direction": {
            "world_model": "multi_region_open_world" if "open_world" in genre_tags else "hub_and_frontier_regions",
            "delivery_target": content_scale.get("delivery_target", "single_region_vertical_slice"),
            "requested_scale": content_scale.get("requested_scale", "single_slice"),
            "slice_spaces": int(content_scale.get("slice_spaces", 1) or 1),
            "enemy_families": int(content_scale.get("enemy_families", 1) or 1),
            "boss_encounters": int(content_scale.get("boss_encounters", 0) or 0),
            "quest_count": int(content_scale.get("quest_count", 1) or 1),
        },
        "production_contract": {
            "requested_scope": production.get("requested_scope", "vertical_slice"),
            "delivery_scope": production.get("delivery_scope", "vertical_slice"),
            "complexity_score": int(production.get("complexity_score", 0) or 0),
            "required_systems": required_systems,
            "deferred_features": deferred,
            "known_risks": list(production.get("known_risks", []) or []),
            "slice_targets": list(production.get("slice_targets", []) or []),
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
