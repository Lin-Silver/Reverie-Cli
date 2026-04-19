"""World-program builders for persistent Reverie-Gamer projects."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict

from .system_generators.shared import project_name, target_runtime


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _world_topology(regions: list[Dict[str, Any]]) -> Dict[str, Any]:
    nodes = []
    routes = []
    for index, region in enumerate(regions, start=1):
        region_id = str(region.get("id", f"region_{index}")).strip() or f"region_{index}"
        nodes.append(
            {
                "id": region_id,
                "biome": str(region.get("biome", "")),
                "signature_landmark": str(region.get("signature_landmark", "")),
                "purpose": str(region.get("purpose", "")),
            }
        )
        if index > 1:
            previous_id = str(regions[index - 2].get("id", f"region_{index - 1}")).strip() or f"region_{index - 1}"
            routes.append(
                {
                    "id": f"{previous_id}_to_{region_id}",
                    "from": previous_id,
                    "to": region_id,
                    "gate": str(region.get("progression_gate", "complete the current frontier milestone")),
                }
            )
    return {
        "nodes": nodes,
        "routes": routes,
    }


def _streaming_plan(game_request: Dict[str, Any], regions: list[Dict[str, Any]]) -> Dict[str, Any]:
    world_structure = str(game_request.get("experience", {}).get("world_structure", "regional_action_slice"))
    return {
        "streaming_model": (
            "region_cells_with_landmark_routes"
            if world_structure == "open_world_regions"
            else "hub_and_district_cells"
            if world_structure == "hub_and_districts"
            else "single_slice_lane"
        ),
        "active_region_budget": 2 if len(regions) >= 3 else 1,
        "preview_region_budget": 1 if len(regions) >= 2 else 0,
        "landmark_anchor_rule": "Every streamed region needs one landmark that can teach orientation from a distance.",
    }


def _live_ops_surfaces(game_request: Dict[str, Any], regions: list[Dict[str, Any]]) -> list[Dict[str, Any]]:
    live_service_enabled = bool(game_request.get("production", {}).get("live_service_profile", {}).get("enabled", False))
    surfaces = [
        {
            "id": "regional_objectives",
            "purpose": "Keep chapter and quest progression attached to durable region state.",
        },
        {
            "id": "boss_rematch_ladder",
            "purpose": "Turn boss anchors into repeatable mastery and reward surfaces.",
        },
    ]
    if live_service_enabled:
        surfaces.append(
            {
                "id": "commission_board",
                "purpose": "Support short-session reentry beats without losing chapter continuity.",
            }
        )
    if len(regions) >= 3:
        surfaces.append(
            {
                "id": "region_unlock_chain",
                "purpose": "Use cross-region unlocks and handoffs to make the world feel cumulative instead of episodic.",
            }
        )
    return surfaces


def build_world_program(
    game_request: Dict[str, Any],
    blueprint: Dict[str, Any],
    content_expansion: Dict[str, Any],
    *,
    runtime_profile: Dict[str, Any] | None = None,
) -> Dict[str, Any]:
    """Build the durable world program for multi-region growth."""

    regions = list(content_expansion.get("region_seeds", []) or [])
    return {
        "schema_version": "reverie.world_program/1",
        "project_name": project_name(game_request, blueprint),
        "generated_at": _utc_now(),
        "runtime": target_runtime(blueprint, runtime_profile),
        "world_model": content_expansion.get("target_scale", "regional_arpg_base"),
        "world_topology": _world_topology(regions),
        "streaming_plan": _streaming_plan(game_request, regions),
        "region_order": [str(region.get("id", "")) for region in regions if str(region.get("id", ""))],
        "active_region_id": str(content_expansion.get("active_region_id", "")).strip(),
        "boss_priority_region_id": str(content_expansion.get("boss_priority_region_id", "")).strip(),
        "regional_rules": [
            "Each region should teach or stress one new traversal, combat, or quest idea.",
            "Every region needs a signature landmark, one critical-path route, and one optional detour reward.",
            "Quest arcs should overlap regions instead of resetting from scratch.",
        ],
        "live_ops_surfaces": _live_ops_surfaces(game_request, regions),
        "regions": regions,
    }


def build_questline_program(
    game_request: Dict[str, Any],
    blueprint: Dict[str, Any],
    content_expansion: Dict[str, Any],
    *,
    runtime_profile: Dict[str, Any] | None = None,
) -> Dict[str, Any]:
    """Build a durable questline program from expansion seeds."""

    arcs = list(content_expansion.get("quest_arcs", []) or [])
    return {
        "schema_version": "reverie.questline_program/1",
        "project_name": project_name(game_request, blueprint),
        "generated_at": _utc_now(),
        "runtime": target_runtime(blueprint, runtime_profile),
        "quest_arcs": arcs,
        "quest_spine": [
            {
                "id": str(arc.get("id", "")).strip(),
                "regions": [str(item).strip() for item in arc.get("regions", []) or [] if str(item).strip()],
                "goal": str(arc.get("goal", "") or arc.get("summary", "") or "advance the frontier state"),
            }
            for arc in arcs
            if str(arc.get("id", "")).strip()
        ],
        "rules": [
            "Every quest arc must advance world knowledge, region access, or player strength.",
            "Quest-state ids should remain stable across future region additions.",
        ],
    }
