"""Faction-graph builders for long-running Reverie-Gamer projects."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict

from .system_generators.shared import project_name, target_runtime


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def build_faction_graph(
    game_request: Dict[str, Any],
    blueprint: Dict[str, Any],
    content_expansion: Dict[str, Any],
    *,
    runtime_profile: Dict[str, Any] | None = None,
) -> Dict[str, Any]:
    """Build a deterministic faction graph from content seeds."""

    regions = [str(region.get("id", "")) for region in content_expansion.get("region_seeds", []) if str(region.get("id", ""))]
    factions = [
        {
            "id": "keepers_of_the_shrine",
            "role": "allied",
            "regions": regions[:2] or ["starter_ruins"],
            "fantasy": "protect the old routes and stabilize relic systems",
        },
        {
            "id": "frontier_legion",
            "role": "contested",
            "regions": regions[1:3] or regions[:1],
            "fantasy": "secure new territory through force and logistics",
        },
        {
            "id": "resonance_cabal",
            "role": "enemy",
            "regions": regions[1:] or regions[:1],
            "fantasy": "weaponize the world's unstable signal network",
        },
    ]
    return {
        "schema_version": "reverie.faction_graph/1",
        "project_name": project_name(game_request, blueprint),
        "generated_at": _utc_now(),
        "runtime": target_runtime(blueprint, runtime_profile),
        "factions": factions,
        "relationships": [
            {"from": "keepers_of_the_shrine", "to": "frontier_legion", "type": "uneasy_alliance"},
            {"from": "frontier_legion", "to": "resonance_cabal", "type": "open_conflict"},
            {"from": "resonance_cabal", "to": "keepers_of_the_shrine", "type": "hostile_corruption"},
        ],
    }


def build_enemy_faction_packet(faction_id: str, faction_graph: Dict[str, Any]) -> Dict[str, Any]:
    """Build a focused faction packet for enemy or region production."""

    faction = next(
        (
            dict(item)
            for item in faction_graph.get("factions", [])
            if str(item.get("id", "")).strip() == str(faction_id).strip()
        ),
        {},
    )
    return {
        "schema_version": "reverie.enemy_faction/1",
        "generated_at": _utc_now(),
        "faction": faction,
        "deployment_rules": [
            "anchor every enemy faction appearance to a region purpose and landmark sightline",
            "escalate faction pressure through patrols, elites, and bosses rather than raw enemy count",
        ],
    }
