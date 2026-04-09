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
    runtime_profile: Dict[str, Any] | None = None,
) -> Dict[str, Any]:
    """Build reusable gameplay factory outputs from system packets."""

    experience = dict(game_request.get("experience", {}) or {})
    combat_packet = dict(system_bundle.get("packets", {}).get("combat", {}) or {})
    enemy_archetypes = list(combat_packet.get("enemy_archetypes", []) or [])
    return {
        "schema_version": "reverie.gameplay_factory/1",
        "project_name": project_name(game_request, blueprint),
        "generated_at": _utc_now(),
        "runtime": target_runtime(blueprint, runtime_profile),
        "traversal_presets": [
            {"id": "default_field", "movement_model": experience.get("movement_model", "third_person_action")},
            {"id": "combat_engage", "movement_model": "combat_entry"},
        ],
        "camera_presets": [
            {"id": "exploration", "camera_model": experience.get("camera_model", "third_person")},
            {"id": "combat_lock_on", "camera_model": "third_person_lock_on"},
        ],
        "ability_graph": {
            "starter": ["light_attack", "dodge", "skill"],
            "growth": ["guard", "air_followup", "resonance_burst"],
        },
        "enemy_families": enemy_archetypes,
        "encounter_grammar": [
            "approach pressure",
            "mixed melee and ranged wave",
            "elite detour",
            "boss finale",
        ],
        "boss_phase_seeds": [
            "telegraphed opener",
            "mobility punish",
            "high-pressure finale",
        ],
        "quest_event_director": {
            "regions": [str(item.get("id", "")) for item in content_expansion.get("region_seeds", []) if str(item.get("id", ""))],
            "beats": ["arrival", "goal reveal", "challenge", "reward", "handoff"],
        },
    }


def build_boss_arc(
    game_request: Dict[str, Any],
    blueprint: Dict[str, Any],
    system_bundle: Dict[str, Any],
    content_expansion: Dict[str, Any],
    *,
    runtime_profile: Dict[str, Any] | None = None,
) -> Dict[str, Any]:
    """Build a boss-arc plan from combat and world seeds."""

    combat_packet = dict(system_bundle.get("packets", {}).get("combat", {}) or {})
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
    }
