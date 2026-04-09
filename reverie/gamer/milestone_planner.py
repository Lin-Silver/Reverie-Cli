"""Milestone and feature planning for large Reverie-Gamer projects."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict

from .system_generators.shared import project_name, target_runtime


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def build_feature_matrix(
    game_request: Dict[str, Any],
    blueprint: Dict[str, Any],
    system_bundle: Dict[str, Any],
    *,
    runtime_profile: Dict[str, Any] | None = None,
) -> Dict[str, Any]:
    """Build a phase-aware feature matrix for the current production program."""

    required = [
        str(item).strip()
        for item in game_request.get("systems", {}).get("required", [])
        if str(item).strip()
    ]
    deferred = [
        str(item).strip()
        for item in game_request.get("production", {}).get("deferred_features", [])
        if str(item).strip()
    ]
    packets = dict(system_bundle.get("packets", {}) or {})
    rows = []
    for system_name in required:
        packet_id = str(system_bundle.get("coverage", {}).get(system_name, ""))
        rows.append(
            {
                "id": system_name,
                "kind": "required_system",
                "packet_id": packet_id,
                "phase": "vertical_slice" if packet_id in packets else "foundation",
                "status": "in_scope",
            }
        )
    for item in deferred:
        rows.append(
            {
                "id": item.replace(" ", "_"),
                "kind": "deferred_feature",
                "packet_id": "",
                "phase": "post_slice",
                "status": "deferred",
            }
        )

    return {
        "schema_version": "reverie.feature_matrix/1",
        "project_name": project_name(game_request, blueprint),
        "generated_at": _utc_now(),
        "runtime": target_runtime(blueprint, runtime_profile),
        "rows": rows,
    }


def build_milestone_board(
    game_request: Dict[str, Any],
    blueprint: Dict[str, Any],
    production_plan: Dict[str, Any],
    *,
    runtime_profile: Dict[str, Any] | None = None,
) -> Dict[str, Any]:
    """Build a durable milestone board for long-running production."""

    vertical_slice = dict(production_plan.get("vertical_slice", {}) or {})
    return {
        "schema_version": "reverie.milestone_board/1",
        "project_name": project_name(game_request, blueprint),
        "generated_at": _utc_now(),
        "runtime": target_runtime(blueprint, runtime_profile),
        "milestones": [
            {
                "id": "program_compilation",
                "title": "Program Compilation",
                "goal": "Lock the project program, pillars, risk register, and milestone lanes.",
                "exit_criteria": ["game_program exists", "milestone_board exists", "risk_register exists"],
            },
            {
                "id": "runtime_foundation",
                "title": "Runtime Foundation",
                "goal": "Choose the runtime, capability graph, and delivery plan for the production base.",
                "exit_criteria": ["runtime capability graph exists", "runtime delivery plan exists"],
            },
            {
                "id": "first_playable",
                "title": "First Playable",
                "goal": "Reach one complete route from entry to objective to reward.",
                "exit_criteria": ["boot path exists", "quest and reward loop exist"],
            },
            {
                "id": "vertical_slice",
                "title": "Vertical Slice",
                "goal": "Ship a readable, verified, and extensible slice baseline.",
                "exit_criteria": list(vertical_slice.get("quality_gates", []) or []),
            },
            {
                "id": "expansion_base",
                "title": "Expansion Base",
                "goal": "Promote the slice into a multi-region production program with continuity artifacts.",
                "exit_criteria": ["world program exists", "resume state exists", "continuation recommendations exist"],
            },
        ],
    }


def build_risk_register(
    game_request: Dict[str, Any],
    blueprint: Dict[str, Any],
    *,
    runtime_profile: Dict[str, Any] | None = None,
) -> Dict[str, Any]:
    """Build a structured risk register for large 3D project delivery."""

    production = dict(game_request.get("production", {}) or {})
    runtime = str(target_runtime(blueprint, runtime_profile))
    risks = [
        {
            "id": "scope_pressure",
            "severity": "high" if int(production.get("complexity_score", 0) or 0) >= 60 else "medium",
            "area": "production",
            "summary": "Ambition can outpace what one verified vertical slice can support.",
            "mitigation": "Defer breadth explicitly and score the current slice before expansion.",
        },
        {
            "id": "runtime_feel",
            "severity": "high" if str(blueprint.get("meta", {}).get("dimension", "3D")) == "3D" else "medium",
            "area": "gameplay",
            "summary": "3D feel work depends on camera, controller, encounter readability, and content density working together.",
            "mitigation": "Keep combat-feel and quality-gate artifacts current and iterate before widening scope.",
        },
        {
            "id": "asset_lane",
            "severity": "medium",
            "area": "asset_pipeline",
            "summary": "Authored assets can drift away from runtime validation, budgets, or naming contracts.",
            "mitigation": "Use asset budget, import profile, and queue validation before scene integration.",
        },
        {
            "id": "runtime_delivery",
            "severity": "medium" if runtime == "reverie_engine" else "high",
            "area": "runtime",
            "summary": "External runtime delivery can be gated by scaffold, validation, or toolchain availability.",
            "mitigation": "Record capability graph blockers and keep a fallback delivery path visible.",
        },
    ]
    return {
        "schema_version": "reverie.risk_register/1",
        "project_name": project_name(game_request, blueprint),
        "generated_at": _utc_now(),
        "runtime": runtime,
        "risks": risks,
    }
