"""Content-lattice builders for large Reverie-Gamer projects."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List

from .system_generators.shared import project_name, target_runtime


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _region_release_plan(
    regions: List[Dict[str, Any]],
    *,
    launch_region_target: int,
    live_service_enabled: bool,
) -> List[Dict[str, Any]]:
    plan: List[Dict[str, Any]] = []
    for index, region in enumerate(regions, start=1):
        region_id = str(region.get("id", f"region_{index}")).strip() or f"region_{index}"
        release_window = "launch" if index <= launch_region_target else f"version_1_{index - launch_region_target}"
        if not live_service_enabled and index > launch_region_target:
            release_window = f"expansion_pack_{index - launch_region_target}"
        plan.append(
            {
                "region_id": region_id,
                "release_window": release_window,
                "goal": str(region.get("purpose", "") or "expand the combat and exploration grammar"),
                "signature_landmark": str(region.get("signature_landmark", "")),
            }
        )
    return plan


def _content_wave_templates(
    *,
    live_service_enabled: bool,
    party_model: str,
) -> List[Dict[str, Any]]:
    templates = [
        {
            "id": "region_drop",
            "focus": "landmark routes, local quest hooks, and one signature encounter ladder",
        },
        {
            "id": "boss_and_elite_refresh",
            "focus": "new punish windows, rematch variants, and clearer mastery checks",
        },
    ]
    if party_model != "single_hero_focus":
        templates.append(
            {
                "id": "roster_wave",
                "focus": "one new role or affinity addition that changes route and boss planning",
            }
        )
    if live_service_enabled:
        templates.append(
            {
                "id": "event_story",
                "focus": "short-session reentry beats tied to the same world memory and reward economy",
            }
        )
    return templates


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
    quality = dict(game_request.get("quality_targets", {}) or {})
    large_scale_profile = dict(production.get("large_scale_profile", {}) or {})
    live_service_enabled = bool(production.get("live_service_profile", {}).get("enabled", False))
    playable_roster = list(asset_pipeline.get("content_sets", {}).get("playable_roster", []) or [])
    party_model = str(game_request.get("experience", {}).get("party_model", "single_hero_focus"))
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
                "character_drop_ids": [
                    str(item.get("id", ""))
                    for item in playable_roster
                    if region_id and region_id in str(item.get("home_region", ""))
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
            "roster release discipline",
            "event surface reuse",
        ],
        "region_release_plan": _region_release_plan(
            regions,
            launch_region_target=int(large_scale_profile.get("launch_region_target", max(len(entries), 1)) or max(len(entries), 1)),
            live_service_enabled=live_service_enabled,
        ),
        "content_wave_templates": _content_wave_templates(
            live_service_enabled=live_service_enabled,
            party_model=party_model,
        ),
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
            "target_quality": str(production.get("target_quality", "aa")),
            "target_platforms": list(quality.get("target_platforms", []) or []),
            "target_world_size": str(quality.get("world_size", "")),
            "target_content_hours": str(quality.get("content_hours", "")),
        },
    }
