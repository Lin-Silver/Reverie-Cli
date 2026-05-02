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
    design_intelligence: Dict[str, Any] | None = None,
) -> Dict[str, Any]:
    """Build a quality gate report from planning and verification artifacts."""

    verification = dict(verification or {})
    slice_score = dict(slice_score or {})
    asset_pipeline = dict(asset_pipeline or {})
    design_intelligence = dict(design_intelligence or {})
    packet_ids = list(system_bundle.get("packets", {}).keys())
    queue = list(asset_pipeline.get("production_queue", []) or [])
    personas = list(design_intelligence.get("player_personas", []) or [])
    onboarding_ladder = list(design_intelligence.get("onboarding_ladder", []) or [])
    accessibility_features = list(design_intelligence.get("accessibility_baseline", {}).get("required_features", []) or [])
    balance_probes = list(design_intelligence.get("balance_lab", {}).get("doubling_halving_probes", []) or [])
    scalability_patterns = list(design_intelligence.get("runtime_guardrails", {}).get("scalability_patterns", []) or [])
    large_scale_profile = dict(game_request.get("production", {}).get("large_scale_profile", {}) or {})
    runtime_contracts = list(large_scale_profile.get("runtime_contracts", []) or [])
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
            "id": "design_intelligence",
            "status": _status(len(personas) >= 2 and len(onboarding_ladder) >= 4, review=bool(personas) or bool(onboarding_ladder)),
            "summary": "Default player personas, onboarding beats, and design intelligence exist for the slice.",
            "evidence": {
                "persona_count": len(personas),
                "onboarding_beat_count": len(onboarding_ladder),
            },
        },
        {
            "id": "accessibility_baseline",
            "status": _status(len(accessibility_features) >= 6, review=len(accessibility_features) >= 3),
            "summary": "Accessibility defaults are planned before content scale increases.",
            "evidence": {"required_feature_count": len(accessibility_features)},
        },
        {
            "id": "balance_probe_coverage",
            "status": _status(len(balance_probes) >= 3, review=len(balance_probes) >= 2),
            "summary": "The slice has concrete balance probes for fast tuning passes.",
            "evidence": {"balance_probe_count": len(balance_probes)},
        },
        {
            "id": "runtime_scalability",
            "status": _status(len(scalability_patterns) >= 3, review=bool(scalability_patterns)),
            "summary": "Large-scene scalability guardrails are attached to the project.",
            "evidence": {"scalability_pattern_count": len(scalability_patterns)},
        },
        {
            "id": "large_scale_contracts",
            "status": _status(len(runtime_contracts) >= 3, review=bool(runtime_contracts)),
            "summary": "Large-scale runtime contracts are explicit for party, region, and continuation growth.",
            "evidence": {
                "contract_ids": runtime_contracts,
                "project_shape": str(large_scale_profile.get("project_shape", "regional_action_rpg")),
            },
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
