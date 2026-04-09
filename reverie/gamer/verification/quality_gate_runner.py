"""Quality gate execution for Reverie-Gamer."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _status(passed: bool, review: bool = False) -> str:
    if passed:
        return "pass"
    if review:
        return "review"
    return "fail"


def build_quality_gate_report(
    game_request: Dict[str, Any],
    blueprint: Dict[str, Any],
    system_bundle: Dict[str, Any],
    *,
    runtime_profile: Dict[str, Any] | None = None,
    verification: Dict[str, Any] | None = None,
    slice_score: Dict[str, Any] | None = None,
    asset_pipeline: Dict[str, Any] | None = None,
) -> Dict[str, Any]:
    """Build a quality gate report from planning and verification artifacts."""

    verification = dict(verification or {})
    slice_score = dict(slice_score or {})
    asset_pipeline = dict(asset_pipeline or {})
    packet_ids = list(system_bundle.get("packets", {}).keys())
    queue = list(asset_pipeline.get("production_queue", []) or [])
    gate_sets: List[Dict[str, Any]] = [
        {
            "id": "runtime_boot",
            "status": _status(bool(verification.get("valid", False)), review=bool(verification)),
            "summary": "Runtime validation and smoke path",
            "evidence": {"validation_checks": len(verification.get("checks", []) or [])},
        },
        {
            "id": "system_coverage",
            "status": _status(len(packet_ids) >= 4, review=len(packet_ids) >= 2),
            "summary": "Critical system packets exist for the slice",
            "evidence": {"packet_ids": packet_ids},
        },
        {
            "id": "scope_control",
            "status": _status(str(game_request.get("production", {}).get("delivery_scope", "")) in {"prototype", "first_playable", "vertical_slice"}),
            "summary": "Scope is reduced to a buildable slice tier",
            "evidence": {"delivery_scope": game_request.get("production", {}).get("delivery_scope", "vertical_slice")},
        },
        {
            "id": "asset_lane",
            "status": _status(bool(queue), review=True),
            "summary": "Asset queue and import rules are defined",
            "evidence": {"production_queue_count": len(queue)},
        },
        {
            "id": "slice_readiness",
            "status": _status(int(slice_score.get("score", 0) or 0) >= 70, review=int(slice_score.get("score", 0) or 0) >= 55),
            "summary": "Current slice score is strong enough for continued iteration",
            "evidence": {"slice_score": int(slice_score.get("score", 0) or 0)},
        },
    ]
    statuses = [gate["status"] for gate in gate_sets]
    overall = "pass" if all(status == "pass" for status in statuses) else "review" if "fail" not in statuses else "fail"
    return {
        "schema_version": "reverie.quality_gates/1",
        "project_name": blueprint.get("meta", {}).get("project_name", "Untitled Reverie Slice"),
        "generated_at": _utc_now(),
        "runtime": (runtime_profile or {}).get("id") or blueprint.get("meta", {}).get("target_engine", "reverie_engine"),
        "overall_status": overall,
        "gate_sets": gate_sets,
    }
