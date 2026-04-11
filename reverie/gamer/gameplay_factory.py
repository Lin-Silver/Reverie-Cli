"""Gameplay factory builders for large-scale Reverie-Gamer requests."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict

from .system_generators.shared import project_name, target_runtime


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def build_gameplay_factory(
    game_request: Dict[str, Any],
    blueprint: Dict[str, Any],
    system_bundle: Dict[str, Any],
    content_expansion: Dict[str, Any],
    *,
    design_intelligence: Dict[str, Any] | None = None,
    runtime_profile: Dict[str, Any] | None = None,
) -> Dict[str, Any]:
    """Build reusable gameplay factory outputs from system packets."""

    design_intelligence = dict(design_intelligence or {})
    experience = dict(game_request.get("experience", {}) or {})
    specialized = {str(item).strip() for item in game_request.get("systems", {}).get("specialized", []) if str(item).strip()}
    combat_packet = dict(system_bundle.get("packets", {}).get("combat", {}) or {})
    enemy_archetypes = list(combat_packet.get("enemy_archetypes", []) or [])
    onboarding_ladder = list(design_intelligence.get("onboarding_ladder", []) or [])
    balance_probes = list(design_intelligence.get("balance_lab", {}).get("doubling_halving_probes", []) or [])
    feedback_contract = list(design_intelligence.get("reinforcement_model", {}).get("feedback_contract", []) or [])
    session_hooks = list(design_intelligence.get("session_model", {}).get("session_hooks", []) or [])
    traversal_presets = [
        {"id": "default_field", "movement_model": experience.get("movement_model", "third_person_action")},
        {"id": "combat_engage", "movement_model": "combat_entry"},
    ]
    if {"aerial_combat", "glide", "climb"} & specialized:
        traversal_presets.append({"id": "vertical_assault", "movement_model": "aerial_combo_route"})

    camera_presets = [
        {"id": "exploration", "camera_model": experience.get("camera_model", "third_person")},
        {"id": "combat_lock_on", "camera_model": "third_person_lock_on"},
    ]
    if "aerial_combat" in specialized:
        camera_presets.append({"id": "air_route", "camera_model": "third_person_air_follow"})

    growth = ["guard", "air_followup", "resonance_burst"]
    if experience.get("party_model", "single_hero_focus") != "single_hero_focus":
        growth.append("swap_cancel")
    if "parry" in specialized:
        growth.append("perfect_guard_counter")
    encounter_grammar = [
        "safe tutorial beat",
        "approach pressure",
        "mixed melee and ranged wave",
        "elite detour",
        "boss finale",
    ]
    if experience.get("world_structure", "regional_action_slice") in {"open_world_regions", "hub_and_districts"}:
        encounter_grammar.insert(1, "landmark-driven route commit")
    if experience.get("party_model", "single_hero_focus") != "single_hero_focus":
        encounter_grammar.insert(3, "tag-synergy punish window")
    return {
        "schema_version": "reverie.gameplay_factory/1",
        "project_name": project_name(game_request, blueprint),
        "generated_at": _utc_now(),
        "runtime": target_runtime(blueprint, runtime_profile),
        "traversal_presets": traversal_presets,
        "camera_presets": camera_presets,
        "ability_graph": {
            "starter": ["light_attack", "dodge", "skill"],
            "growth": growth,
        },
        "enemy_families": enemy_archetypes,
        "encounter_grammar": encounter_grammar,
        "boss_phase_seeds": [
            "telegraphed opener",
            "mobility punish",
            "high-pressure finale",
        ],
        "experience_design": {
            "aesthetic_targets": list(design_intelligence.get("mda_map", {}).get("aesthetics", []) or []),
            "session_hooks": session_hooks,
            "onboarding_ladder": [str(item.get("id", "")).strip() for item in onboarding_ladder if str(item.get("id", "")).strip()],
            "feedback_contract": feedback_contract,
            "difficulty_director": dict(design_intelligence.get("difficulty_model", {}).get("dynamic_adjustment", {}) or {}),
            "balance_probe_ids": [str(item.get("id", "")).strip() for item in balance_probes if str(item.get("id", "")).strip()],
        },
        "quest_event_director": {
            "regions": [str(item.get("id", "")) for item in content_expansion.get("region_seeds", []) if str(item.get("id", ""))],
            "beats": ["arrival", "goal reveal", "challenge", "reward", "handoff"],
            "onboarding_beats": [str(item.get("id", "")).strip() for item in onboarding_ladder[:3] if str(item.get("id", "")).strip()],
        },
    }


def build_boss_arc(
    game_request: Dict[str, Any],
    blueprint: Dict[str, Any],
    system_bundle: Dict[str, Any],
    content_expansion: Dict[str, Any],
    *,
    design_intelligence: Dict[str, Any] | None = None,
    runtime_profile: Dict[str, Any] | None = None,
) -> Dict[str, Any]:
    """Build a boss-arc plan from combat and world seeds."""

    design_intelligence = dict(design_intelligence or {})
    combat_packet = dict(system_bundle.get("packets", {}).get("combat", {}) or {})
    feedback_contract = list(design_intelligence.get("reinforcement_model", {}).get("feedback_contract", []) or [])
    boss = next(
        (
            dict(item)
            for item in combat_packet.get("enemy_archetypes", [])
            if "boss" in str(item.get("role", "")).lower() or "warden" in str(item.get("id", "")).lower()
        ),
        {"id": "shrine_warden", "role": "guardian boss"},
    )
    final_region = next(
        (str(item.get("id", "")) for item in reversed(content_expansion.get("region_seeds", [])) if str(item.get("id", ""))),
        "starter_ruins",
    )
    return {
        "schema_version": "reverie.boss_arc/1",
        "project_name": project_name(game_request, blueprint),
        "generated_at": _utc_now(),
        "runtime": target_runtime(blueprint, runtime_profile),
        "boss": boss,
        "target_region": final_region,
        "phases": [
            "telegraphed opener",
            "pressure escalation with mobility checks",
            "finale burst with visible punish windows",
        ],
        "rewards": ["region unlock", "progression node", "continuation hook"],
        "learning_loops": [
            "teach one defensive read",
            "demand one route or spacing adjustment",
            "pay off mastery with a clear punish window",
        ],
        "telegraph_contract": feedback_contract[:3],
    }
