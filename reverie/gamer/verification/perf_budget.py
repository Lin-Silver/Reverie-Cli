"""Performance budget planning for Reverie-Gamer."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def build_performance_budget(
    game_request: Dict[str, Any],
    blueprint: Dict[str, Any],
    asset_pipeline: Dict[str, Any],
    *,
    runtime_profile: Dict[str, Any] | None = None,
) -> Dict[str, Any]:
    """Build a performance budget for the current slice."""

    dimension = str(game_request.get("experience", {}).get("dimension", "3D"))
    target_fps = int(game_request.get("quality_targets", {}).get("target_fps", 60) or 60)
    queue_count = len(asset_pipeline.get("production_queue", []) or [])
    return {
        "schema_version": "reverie.performance_budget/1",
        "project_name": blueprint.get("meta", {}).get("project_name", "Untitled Reverie Slice"),
        "generated_at": _utc_now(),
        "runtime": (runtime_profile or {}).get("id") or blueprint.get("meta", {}).get("target_engine", "reverie_engine"),
        "target_fps": target_fps,
        "budgets": {
            "cpu_frame_ms": 16.6 if target_fps >= 60 else 33.3,
            "gpu_frame_ms": 16.6 if target_fps >= 60 else 33.3,
            "streamed_regions": 2 if dimension == "3D" else 1,
            "active_ai_agents": 8 if dimension == "3D" else 16,
            "projectiles": 12 if dimension == "3D" else 24,
            "vfx_emitters": 24 if queue_count >= 8 else 12,
        },
        "checks": [
            "controller, camera, and combat should hold target fps on the critical path",
            "landmarks and NPC beacons should stay within the slice scene budget",
            "avoid widening region count until the current budget remains stable",
        ],
    }
