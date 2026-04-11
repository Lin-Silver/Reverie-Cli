"""World-program builders for persistent Reverie-Gamer projects."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict

from .system_generators.shared import project_name, target_runtime


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


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
        "region_order": [str(region.get("id", "")) for region in regions if str(region.get("id", ""))],
        "active_region_id": str(content_expansion.get("active_region_id", "")).strip(),
        "boss_priority_region_id": str(content_expansion.get("boss_priority_region_id", "")).strip(),
        "regional_rules": [
            "Each region should teach or stress one new traversal, combat, or quest idea.",
            "Every region needs a signature landmark, one critical-path route, and one optional detour reward.",
            "Quest arcs should overlap regions instead of resetting from scratch.",
        ],
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
        "rules": [
            "Every quest arc must advance world knowledge, region access, or player strength.",
            "Quest-state ids should remain stable across future region additions.",
        ],
    }
