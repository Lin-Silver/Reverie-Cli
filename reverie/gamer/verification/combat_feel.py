"""Combat-feel scoring for Reverie-Gamer."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def build_combat_feel_report(
    game_request: Dict[str, Any],
    blueprint: Dict[str, Any],
    system_bundle: Dict[str, Any],
    *,
    slice_score: Dict[str, Any] | None = None,
) -> Dict[str, Any]:
    """Build a combat-feel report from the current slice packets."""

    slice_score = dict(slice_score or {})
    combat_packet = dict(system_bundle.get("packets", {}).get("combat", {}) or {})
    enemy_count = len(combat_packet.get("enemy_archetypes", []) or [])
    tests = len(combat_packet.get("tests", []) or [])
    readability = 82 if enemy_count >= 3 else 68
    expression = 78 if "lock_on" in game_request.get("systems", {}).get("required", []) else 70
    feedback = 80 if tests >= 4 else 66
    pacing = 76 if int(slice_score.get("score", 0) or 0) >= 70 else 64
    overall = int(round((readability + expression + feedback + pacing) / 4.0))
    return {
        "schema_version": "reverie.combat_feel_report/1",
        "project_name": blueprint.get("meta", {}).get("project_name", "Untitled Reverie Slice"),
        "generated_at": _utc_now(),
        "overall_score": overall,
        "subscores": {
            "readability": readability,
            "expression": expression,
            "feedback": feedback,
            "pacing": pacing,
        },
        "recommendations": [
            "tighten attack-confirm, dodge, and reaction timing before widening move lists",
            "preserve readable telegraphs for elites and bosses as content grows",
        ],
    }
