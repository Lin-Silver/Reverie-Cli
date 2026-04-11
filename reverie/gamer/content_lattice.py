"""Content-lattice builders for large Reverie-Gamer projects."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List

from .system_generators.shared import project_name, target_runtime


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def build_content_matrix(
    game_request: Dict[str, Any],
    blueprint: Dict[str, Any],
    content_expansion: Dict[str, Any],
    asset_pipeline: Dict[str, Any],
    *,
    runtime_profile: Dict[str, Any] | None = None,
) -> Dict[str, Any]:
    """Build a durable content matrix that maps world, quest, and asset growth."""

    regions = list(content_expansion.get("region_seeds", []) or [])
    npcs = list(content_expansion.get("npc_roster", []) or [])
    quest_arcs = list(content_expansion.get("quest_arcs", []) or [])
    queue = list(asset_pipeline.get("production_queue", []) or [])
    production = dict(game_request.get("production", {}) or {})
    large_scale_profile = dict(production.get("large_scale_profile", {}) or {})
    playable_roster = list(asset_pipeline.get("content_sets", {}).get("playable_roster", []) or [])
    entries: List[Dict[str, Any]] = []
    for region in regions:
        region_id = str(region.get("id", "region")).strip() or "region"
        entries.append(
            {
                "region_id": region_id,
                "biome": str(region.get("biome", "")),
                "purpose": str(region.get("purpose", "")),
                "signature_landmark": str(region.get("signature_landmark", "")),
                "npc_ids": [str(npc.get("id", "")) for npc in npcs if str(npc.get("home_region", "")) == region_id],
                "quest_arc_ids": [
                    str(arc.get("id", ""))
                    for arc in quest_arcs
                    if region_id in {str(item) for item in arc.get("regions", [])}
                ],
                "asset_queue_ids": [
                    str(item.get("id", ""))
                    for item in queue
                    if region_id and region_id in str(item.get("goal", ""))
                ],
            }
        )

    return {
        "schema_version": "reverie.content_matrix/1",
        "project_name": project_name(game_request, blueprint),
        "generated_at": _utc_now(),
        "runtime": target_runtime(blueprint, runtime_profile),
        "entries": entries,
        "production_queue": [
            {
                "id": str(item.get("id", "")),
                "priority": str(item.get("priority", "next")),
                "category": str(item.get("category", "world_kit")),
            }
            for item in queue
        ],
        "content_axes": [
            "region progression",
            "npc continuity",
            "quest arc continuity",
            "asset replacement cadence",
            "world landmark readability",
        ],
        "release_forecast": {
            "project_shape": str(large_scale_profile.get("project_shape", "regional_action_rpg")),
            "launch_region_count": int(large_scale_profile.get("launch_region_target", max(len(entries), 1)) or max(len(entries), 1)),
            "post_launch_region_count": int(
                large_scale_profile.get("post_launch_region_target", max(len(entries) + 1, 2)) or max(len(entries) + 1, 2)
            ),
            "starter_party_size": int(large_scale_profile.get("starter_party_size", max(len(playable_roster), 1)) or max(len(playable_roster), 1)),
            "active_region_count": len(entries),
            "quest_arc_count": len(quest_arcs),
            "npc_count": len(npcs),
            "asset_queue_count": len(queue),
        },
    }
