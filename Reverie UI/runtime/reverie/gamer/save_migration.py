"""Save migration planning for long-running Reverie-Gamer projects."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict

from .system_generators.shared import project_name, target_runtime


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def build_save_migration_plan(
    game_request: Dict[str, Any],
    blueprint: Dict[str, Any],
    system_bundle: Dict[str, Any],
    content_expansion: Dict[str, Any],
    *,
    runtime_profile: Dict[str, Any] | None = None,
) -> Dict[str, Any]:
    """Build a save-schema migration plan for future region growth."""

    save_packet = dict(system_bundle.get("packets", {}).get("save_load", {}) or {})
    fields = list(save_packet.get("save_schema", {}).get("fields", []) or [])
    return {
        "schema_version": "reverie.save_migration_plan/1",
        "project_name": project_name(game_request, blueprint),
        "generated_at": _utc_now(),
        "runtime": target_runtime(blueprint, runtime_profile),
        "current_fields": fields,
        "future_additions": [
            "region_unlocks",
            "quest_arc_states",
            "faction_standings",
            "world_events",
        ],
        "migration_rules": [
            "default missing future fields to empty collections or safe zero values",
            "never delete current critical-path objective state during migration",
            "record schema version alongside region and quest progression snapshots",
        ],
        "planned_region_count": len(content_expansion.get("region_seeds", []) or []),
    }
