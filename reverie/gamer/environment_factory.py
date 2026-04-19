"""Environment kit generation for Reverie-Gamer."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict

from .system_generators.shared import project_name, target_runtime


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def build_environment_kits(
    game_request: Dict[str, Any],
    blueprint: Dict[str, Any],
    content_expansion: Dict[str, Any],
    asset_pipeline: Dict[str, Any],
    *,
    runtime_profile: Dict[str, Any] | None = None,
) -> Dict[str, Any]:
    """Build environment kit seeds for each planned region."""

    regions = list(content_expansion.get("region_seeds", []) or [])
    modeling_seed = list(asset_pipeline.get("modeling_seed", []) or [])
    return {
        "schema_version": "reverie.environment_kits/1",
        "project_name": project_name(game_request, blueprint),
        "generated_at": _utc_now(),
        "runtime": target_runtime(blueprint, runtime_profile),
        "region_kits": [
            {
                "id": str(region.get("id", "")),
                "biome": str(region.get("biome", "")),
                "landmark": str(region.get("signature_landmark", "")),
                "purpose": str(region.get("purpose", "")),
                "landmark_asset_ids": [
                    str(seed.get("id", ""))
                    for seed in modeling_seed
                    if str(seed.get("region_id", "")) == str(region.get("id", ""))
                ],
            }
            for region in regions
        ],
        "authoring_rules": [
            "Every region kit must ship one long-range landmark, one combat pocket, and one route-reading prop family.",
            "Environment kit ids should remain stable so region streaming, quest beats, and boss anchors can reference them safely.",
        ],
    }
