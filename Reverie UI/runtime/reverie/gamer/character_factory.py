"""Character kit generation for Reverie-Gamer."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict

from .system_generators.shared import project_name, target_runtime


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def build_character_kits(
    game_request: Dict[str, Any],
    blueprint: Dict[str, Any],
    content_expansion: Dict[str, Any],
    asset_pipeline: Dict[str, Any],
    *,
    runtime_profile: Dict[str, Any] | None = None,
) -> Dict[str, Any]:
    """Build hero, NPC, and enemy kit seeds for authored content production."""

    npcs = list(content_expansion.get("npc_roster", []) or [])
    modeling_seed = list(asset_pipeline.get("modeling_seed", []) or [])
    enemy_kits = [
        {
            "id": str(seed.get("id", "")),
            "category": "enemy",
            "runtime_target": str(seed.get("runtime_target", "")),
            "source_stub": str(seed.get("source_stub", "")),
        }
        for seed in modeling_seed
        if str(seed.get("category", "")) == "enemy"
    ]
    hero_kits = [
        {
            "id": str(seed.get("id", "")),
            "movement_model": str(game_request.get("experience", {}).get("movement_model", "third_person_action")),
            "combat_model": str(game_request.get("experience", {}).get("combat_model", "ability_action")),
            "combat_role": str(seed.get("combat_role", "vanguard")),
            "combat_affinity": str(seed.get("combat_affinity", "steel")),
            "source_stub": str(seed.get("source_stub", "")),
            "runtime_target": str(seed.get("runtime_target", "")),
            "production_role": (
                "starter_party_core"
                if str(seed.get("combat_role", "vanguard")) == "vanguard"
                else "starter_party_extension"
            ),
        }
        for seed in modeling_seed
        if str(seed.get("category", "")) == "character" and bool(seed.get("playable", False))
    ]
    npc_kits = [
        {
            "id": str(npc.get("id", "")),
            "role": str(npc.get("role", "")),
            "home_region": str(npc.get("home_region", "")),
        }
        for npc in npcs
    ]
    return {
        "schema_version": "reverie.character_kits/1",
        "project_name": project_name(game_request, blueprint),
        "generated_at": _utc_now(),
        "runtime": target_runtime(blueprint, runtime_profile),
        "hero_kit": hero_kits[0]
        if hero_kits
        else {
            "id": "player_avatar",
            "movement_model": str(game_request.get("experience", {}).get("movement_model", "third_person_action")),
            "combat_model": str(game_request.get("experience", {}).get("combat_model", "ability_action")),
            "source_stub": "assets/models/source/player_avatar.bbmodel",
            "runtime_target": "assets/models/runtime/player_avatar.gltf",
        },
        "hero_kits": hero_kits,
        "npc_kits": npc_kits,
        "enemy_kits": enemy_kits,
        "roster_rules": [
            "Starter hero kits should cover route ownership, boss punish conversion, sustain, and spacing control before adding rarer variants.",
            "Hero kit ids and combat roles should stay stable so future region and boss waves can target them safely.",
        ],
    }
