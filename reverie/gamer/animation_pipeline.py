"""Animation planning for Reverie-Gamer."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List

from .system_generators.shared import project_name, target_runtime


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def build_animation_plan(
    game_request: Dict[str, Any],
    blueprint: Dict[str, Any],
    system_bundle: Dict[str, Any],
    *,
    runtime_profile: Dict[str, Any] | None = None,
) -> Dict[str, Any]:
    """Build an animation plan from the current slice systems."""

    movement_model = str(game_request.get("experience", {}).get("movement_model", "third_person_action"))
    combat_packet = dict(system_bundle.get("packets", {}).get("combat", {}) or {})
    enemy_ids = [str(item.get("id", "")) for item in combat_packet.get("enemy_archetypes", []) if str(item.get("id", ""))]
    clips: List[Dict[str, Any]] = [
        {"owner": "player_avatar", "clip": "idle"},
        {"owner": "player_avatar", "clip": "run"},
        {"owner": "player_avatar", "clip": "attack_light"},
        {"owner": "player_avatar", "clip": "dodge"},
        {"owner": "player_avatar", "clip": "hurt"},
    ]
    if "traversal" in movement_model or "exploration" in movement_model:
        clips.append({"owner": "player_avatar", "clip": "jump"})
    for enemy_id in enemy_ids:
        clips.extend(
            [
                {"owner": enemy_id, "clip": "idle"},
                {"owner": enemy_id, "clip": "attack"},
                {"owner": enemy_id, "clip": "hit_reaction"},
                {"owner": enemy_id, "clip": "defeat"},
            ]
        )
    return {
        "schema_version": "reverie.animation_plan/1",
        "project_name": project_name(game_request, blueprint),
        "generated_at": _utc_now(),
        "runtime": target_runtime(blueprint, runtime_profile),
        "clips": clips,
        "rules": [
            "Prioritize locomotion, combat readability, and hit reactions before cinematic polish.",
            "Share skeleton or timing rules across enemy families whenever possible.",
        ],
    }
