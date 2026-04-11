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
    design_intelligence: Dict[str, Any] | None = None,
) -> Dict[str, Any]:
    """Build a combat-feel report from the current slice packets."""

    slice_score = dict(slice_score or {})
    design_intelligence = dict(design_intelligence or {})
    combat_packet = dict(system_bundle.get("packets", {}).get("combat", {}) or {})
    enemy_count = len(combat_packet.get("enemy_archetypes", []) or [])
    tests = len(combat_packet.get("tests", []) or [])
    feedback_contract = list(design_intelligence.get("reinforcement_model", {}).get("feedback_contract", []) or [])
    balance_probes = list(design_intelligence.get("balance_lab", {}).get("doubling_halving_probes", []) or [])
    readability = 82 if enemy_count >= 3 else 68
    expression = 78 if "lock_on" in game_request.get("systems", {}).get("required", []) else 70
    feedback = 82 if tests >= 4 and len(feedback_contract) >= 3 else 74 if tests >= 4 else 66
    pacing = 78 if int(slice_score.get("score", 0) or 0) >= 70 and len(balance_probes) >= 3 else 64
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
            "run one doubling-halving balance pass on boss punish windows and sustain if combat pacing drifts",
            "keep audio and visual hit confirms aligned with the feedback contract for timing-critical actions",
        ],
    }
