"""Region expansion helpers for Reverie-Gamer."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def build_region_kits(
    game_request: Dict[str, Any],
    blueprint: Dict[str, Any],
    content_expansion: Dict[str, Any],
    world_program: Dict[str, Any],
) -> Dict[str, Any]:
    """Build reusable region kits from the world program."""

    regions = list(content_expansion.get("region_seeds", []) or [])
    kits: List[Dict[str, Any]] = []
    for region in regions:
        region_id = str(region.get("id", "region")).strip() or "region"
        kits.append(
            {
                "id": region_id,
                "biome": str(region.get("biome", "")),
                "signature_landmark": str(region.get("signature_landmark", "")),
                "progression_gate": str(region.get("progression_gate", "")),
                "critical_path_template": [
                    "arrival",
                    "landmark sightline",
                    "encounter pocket",
                    "objective site",
                    "reward or unlock",
                ],
            }
        )
    return {
        "schema_version": "reverie.region_kits/1",
        "project_name": str(world_program.get("project_name", game_request.get("meta", {}).get("project_name", "Untitled"))),
        "generated_at": _utc_now(),
        "runtime": str(world_program.get("runtime", blueprint.get("meta", {}).get("target_engine", "reverie_engine"))),
        "region_kits": kits,
    }


def build_region_expansion_plan(
    region_id: str,
    region_kits: Dict[str, Any],
    world_program: Dict[str, Any],
) -> Dict[str, Any]:
    """Build a concrete region-expansion plan for one region id."""

    selected = next(
        (
            dict(item)
            for item in region_kits.get("region_kits", [])
            if str(item.get("id", "")).strip() == str(region_id).strip()
        ),
        {},
    )
    return {
        "schema_version": "reverie.region_expansion/1",
        "project_name": str(world_program.get("project_name", "Untitled Reverie Project")),
        "generated_at": _utc_now(),
        "region_id": str(region_id).strip(),
        "region": selected,
        "tasks": [
            "mirror the region kit into runtime data",
            "place one landmark, one critical-path encounter, and one objective site",
            "bind quest-state and reward ids before authored asset replacement begins",
        ],
    }
