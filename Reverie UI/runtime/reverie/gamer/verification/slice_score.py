"""Slice scoring for Reverie-Gamer vertical slices."""

from __future__ import annotations

from typing import Any, Dict, List

from ..system_generators import CORE_PACKET_ORDER


def _gate(
    gate_id: str,
    name: str,
    *,
    points: int,
    max_points: int,
    passed: bool,
    summary: str,
    evidence: Dict[str, Any] | None = None,
) -> Dict[str, Any]:
    return {
        "id": gate_id,
        "name": name,
        "points": int(points),
        "max_points": int(max_points),
        "passed": bool(passed),
        "summary": summary,
        "evidence": dict(evidence or {}),
    }


def _ratio_points(hit_count: int, total_count: int, max_points: int) -> int:
    if total_count <= 0:
        return max_points
    ratio = max(0.0, min(1.0, float(hit_count) / float(total_count)))
    return int(round(ratio * max_points))


def _expected_packets(game_request: Dict[str, Any]) -> List[str]:
    experience = game_request.get("experience", {})
    creative = game_request.get("creative_target", {})
    required = set(game_request.get("systems", {}).get("required", []))
    expected = {"quest", "save_load", "progression", "world_structure"}
    if str(experience.get("dimension", "3D")) == "3D" or str(experience.get("camera_model", "")) == "third_person":
        expected.add("character_controller")
    if "combat" in required or str(creative.get("primary_genre", "action_rpg")) in {"action_rpg", "arena"}:
        expected.add("combat")
    return [packet_id for packet_id in CORE_PACKET_ORDER if packet_id in expected]


def evaluate_slice_score(
    game_request: Dict[str, Any],
    blueprint: Dict[str, Any],
    system_bundle: Dict[str, Any],
    *,
    runtime_profile: Dict[str, Any] | None = None,
    runtime_result: Dict[str, Any] | None = None,
    verification: Dict[str, Any] | None = None,
) -> Dict[str, Any]:
    """Score slice readiness so expansion decisions are grounded in artifacts."""

    runtime_result = dict(runtime_result or {})
    verification = dict(verification or {})
    packets = dict(system_bundle.get("packets", {}) or {})
    expected_packets = _expected_packets(game_request)
    present_packets = [packet_id for packet_id in expected_packets if packet_id in packets]
    missing_packets = [packet_id for packet_id in expected_packets if packet_id not in packets]

    runtime_files = list(runtime_result.get("files", []) or [])
    runtime_checks = list(verification.get("checks", []) or verification.get("validation", {}).get("checks", []) or [])
    runtime_gate_points = 20 if verification.get("valid", False) else 12 if runtime_files else 0
    gates = [
        _gate(
            "runtime_bootstrap",
            "Runtime Bootstrap",
            points=runtime_gate_points,
            max_points=20,
            passed=bool(verification.get("valid", False)),
            summary="Foundation boots and validation passes." if verification.get("valid", False) else "Foundation exists but runtime verification still needs work.",
            evidence={
                "runtime": (runtime_profile or {}).get("id") or blueprint.get("meta", {}).get("target_engine", "reverie_engine"),
                "runtime_files": len(runtime_files),
                "check_count": len(runtime_checks),
            },
        )
    ]

    systems_points = _ratio_points(len(present_packets), len(expected_packets), 20)
    gates.append(
        _gate(
            "system_coverage",
            "System Coverage",
            points=systems_points,
            max_points=20,
            passed=not missing_packets,
            summary="Core slice packets exist." if not missing_packets else "Some required system packets are still missing.",
            evidence={"expected": expected_packets, "missing": missing_packets},
        )
    )

    core_loop = list(blueprint.get("gameplay_blueprint", {}).get("core_loop", []) or [])
    quest_steps = list(packets.get("quest", {}).get("slice_objectives", []) or [])
    reward_nodes = list(packets.get("progression", {}).get("reward_track", {}).get("nodes", []) or [])
    world_spaces = list(packets.get("world_structure", {}).get("zone_layout", []) or [])
    loop_hits = sum(
        (
            len(core_loop) >= 4,
            len(quest_steps) >= 3,
            len(reward_nodes) >= 3,
            len(world_spaces) >= 3,
        )
    )
    gates.append(
        _gate(
            "gameplay_loop",
            "Gameplay Loop Completeness",
            points=loop_hits * 5,
            max_points=20,
            passed=loop_hits >= 3,
            summary="Loop covers onboarding, encounter, reward, and finish state." if loop_hits >= 3 else "Loop still lacks one or more major slice beats.",
            evidence={
                "core_loop_steps": len(core_loop),
                "quest_steps": len(quest_steps),
                "reward_nodes": len(reward_nodes),
                "world_spaces": len(world_spaces),
            },
        )
    )

    quality = dict(game_request.get("quality_targets", {}) or {})
    instrumentation_hits = sum(
        (
            bool(packets.get("save_load", {}).get("save_schema", {}).get("fields")),
            bool(packets.get("quest", {}).get("telemetry")),
            len(quality.get("must_have", [])) >= 3,
            all(len(packet.get("tests", [])) >= 3 for packet in packets.values()),
        )
    )
    gates.append(
        _gate(
            "instrumentation",
            "Instrumentation and Validation",
            points=instrumentation_hits * 5,
            max_points=20,
            passed=instrumentation_hits >= 3,
            summary="Save schema, telemetry, and tests are defined for the slice." if instrumentation_hits >= 3 else "Verification contracts are still too thin for stable iteration.",
            evidence={
                "must_have_count": len(quality.get("must_have", [])),
                "save_fields": len(packets.get("save_load", {}).get("save_schema", {}).get("fields", [])),
                "packet_count": len(packets),
            },
        )
    )

    production = dict(game_request.get("production", {}) or {})
    scope_hits = sum(
        (
            str(production.get("delivery_scope", "vertical_slice")) in {"prototype", "first_playable", "vertical_slice"},
            bool(production.get("deferred_features", [])) or int(production.get("complexity_score", 0)) < 70,
            bool(production.get("content_scale", {}).get("delivery_target")),
        )
    )
    gates.append(
        _gate(
            "scope_control",
            "Scope Control",
            points=[0, 4, 7, 10][scope_hits],
            max_points=10,
            passed=scope_hits >= 2,
            summary="Ambition is reduced into a controllable slice." if scope_hits >= 2 else "Scope still looks too open-ended for reliable delivery.",
            evidence={
                "delivery_scope": production.get("delivery_scope", "vertical_slice"),
                "complexity_score": production.get("complexity_score", 0),
                "deferred_features": len(production.get("deferred_features", [])),
            },
        )
    )

    runtime_capabilities = list((runtime_profile or {}).get("capabilities", []) or [])
    asset_rules = list(packets.get("world_structure", {}).get("asset_contracts", {}).get("import_rules", []) or [])
    extensibility_hits = sum(
        (
            len(runtime_capabilities) >= 3,
            len(asset_rules) >= 3,
            len(packets.get("save_load", {}).get("migration_rules", [])) >= 2,
        )
    )
    gates.append(
        _gate(
            "extensibility",
            "Extensibility",
            points=[0, 4, 7, 10][extensibility_hits],
            max_points=10,
            passed=extensibility_hits >= 2,
            summary="Foundation is credible for continued content growth." if extensibility_hits >= 2 else "Runtime or content contracts are still too thin for expansion.",
            evidence={
                "runtime_capabilities": len(runtime_capabilities),
                "asset_rules": len(asset_rules),
                "migration_rules": len(packets.get("save_load", {}).get("migration_rules", [])),
            },
        )
    )

    score = sum(gate["points"] for gate in gates)
    blockers: List[str] = []
    recommendations: List[str] = []

    if not verification.get("valid", False):
        blockers.append("Runtime validation or smoke path is not yet passing.")
        recommendations.append("Stabilize the boot path and rerun validation before expanding content breadth.")
    if missing_packets:
        blockers.append("Missing critical system packets: " + ", ".join(missing_packets))
        recommendations.append("Generate and wire the missing system packets before adding more authored content.")
    if loop_hits < 3:
        blockers.append("Core slice loop does not yet prove onboarding, combat or challenge, reward, and completion in one run.")
        recommendations.append("Tighten the main route so objective, encounter, and reward beats happen in a single clean session.")
    if instrumentation_hits < 3:
        recommendations.append("Deepen save/load, telemetry, and test coverage so iteration produces comparable evidence.")
    if scope_hits < 2:
        recommendations.append("Push more large-scale aspirations into deferred features and keep the slice narrowly scoped.")
    if extensibility_hits < 2:
        recommendations.append("Strengthen asset contracts and migration rules before scaling the project beyond one slice.")

    if score >= 85 and not blockers:
        verdict = "strong_vertical_slice_base"
        release_recommendation = "expand_carefully"
    elif score >= 70:
        verdict = "credible_vertical_slice_base"
        release_recommendation = "iterate_then_expand"
    elif score >= 55:
        verdict = "first_playable_with_gaps"
        release_recommendation = "stabilize_before_expand"
    else:
        verdict = "prototype_only"
        release_recommendation = "refocus_on_core_loop"

    return {
        "schema_version": "reverie.slice_score/1",
        "project_name": blueprint.get("meta", {}).get("project_name", "Untitled Reverie Slice"),
        "runtime": (runtime_profile or {}).get("id") or blueprint.get("meta", {}).get("target_engine", "reverie_engine"),
        "score": score,
        "max_score": 100,
        "verdict": verdict,
        "release_recommendation": release_recommendation,
        "blockers": blockers,
        "recommendations": recommendations,
        "gates": gates,
    }


def slice_score_markdown(score: Dict[str, Any]) -> str:
    lines = [f"# Slice Score: {score.get('project_name', 'Untitled Reverie Slice')}", ""]
    lines.append(f"Runtime: {score.get('runtime', 'reverie_engine')}")
    lines.append(f"Score: {score.get('score', 0)}/{score.get('max_score', 100)}")
    lines.append(f"Verdict: {score.get('verdict', 'prototype_only')}")
    lines.append(f"Recommendation: {score.get('release_recommendation', 'stabilize_before_expand')}")
    lines.append("")
    lines.append("## Gates")
    for gate in score.get("gates", []):
        lines.append(
            f"- {gate.get('name', gate.get('id', 'gate'))}: {gate.get('points', 0)}/{gate.get('max_points', 0)} | {'pass' if gate.get('passed') else 'review'}"
        )
    lines.append("")
    lines.append("## Blockers")
    blockers = score.get("blockers", [])
    if blockers:
        for item in blockers:
            lines.append(f"- {item}")
    else:
        lines.append("- none")
    lines.append("")
    lines.append("## Recommendations")
    for item in score.get("recommendations", []) or ["keep iterating against the strongest failed gate"]:
        lines.append(f"- {item}")
    lines.append("")
    return "\n".join(lines)
