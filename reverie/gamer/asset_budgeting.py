"""Asset budget planning for Reverie-Gamer."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict

from .system_generators.shared import project_name, target_runtime


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def build_asset_budget(
    game_request: Dict[str, Any],
    blueprint: Dict[str, Any],
    asset_pipeline: Dict[str, Any],
    content_expansion: Dict[str, Any],
    *,
    runtime_profile: Dict[str, Any] | None = None,
) -> Dict[str, Any]:
    """Build a high-level asset budget for the current slice and next region wave."""

    budget_profile = dict(asset_pipeline.get("budget_profile", {}) or {})
    slice_targets = dict(budget_profile.get("slice_targets", {}) or {})
    expansion_targets = dict(budget_profile.get("expansion_targets", {}) or {})
    region_count = len(content_expansion.get("region_seeds", []) or [])
    return {
        "schema_version": "reverie.asset_budget/1",
        "project_name": project_name(game_request, blueprint),
        "generated_at": _utc_now(),
        "runtime": target_runtime(blueprint, runtime_profile),
        "slice_targets": slice_targets,
        "expansion_targets": expansion_targets,
        "budget_pressure": {
            "planned_regions": region_count,
            "production_queue_count": len(asset_pipeline.get("production_queue", []) or []),
            "needs_strict_budgeting": region_count >= 3 or len(asset_pipeline.get("production_queue", []) or []) >= 8,
        },
        "rules": list(budget_profile.get("budget_rules", []) or []),
    }
