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
    specialized = [
        str(item).strip()
        for item in game_request.get("systems", {}).get("specialized", []) or []
        if str(item).strip()
    ]
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
                "priority": "p0" if system_name in {"combat", "movement", "camera", "quest"} else "p1",
                "delivery_track": "runtime_and_systems" if system_name in {"combat", "movement", "camera", "save_load"} else "world_and_progression",
            }
        )
    for feature in specialized:
        rows.append(
            {
                "id": feature,
                "kind": "specialized_system",
                "packet_id": "",
                "phase": "vertical_slice" if feature in {"character_swap", "elemental_reaction", "open_world_exploration"} else "launch_growth",
                "status": "in_scope",
                "priority": "p1",
                "delivery_track": "large_scale_expression",
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
                "priority": "p2",
                "delivery_track": "post_slice_growth",
            }
        )

    return {
        "schema_version": "reverie.feature_matrix/1",
        "project_name": project_name(game_request, blueprint),
        "generated_at": _utc_now(),
        "runtime": target_runtime(blueprint, runtime_profile),
        "rows": rows,
        "phase_summary": {
            "foundation": len([row for row in rows if row["phase"] == "foundation"]),
            "vertical_slice": len([row for row in rows if row["phase"] == "vertical_slice"]),
            "launch_growth": len([row for row in rows if row["phase"] == "launch_growth"]),
            "post_slice": len([row for row in rows if row["phase"] == "post_slice"]),
        },
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
    live_service_enabled = bool(game_request.get("production", {}).get("live_service_profile", {}).get("enabled", False))
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
                "id": "experience_design",
                "title": "Experience Design",
                "goal": "Lock the player personas, onboarding, difficulty, feedback, balance, and accessibility defaults early.",
                "exit_criteria": ["design_intelligence exists"],
            },
            {
                "id": "large_scale_direction",
                "title": "Large-Scale Direction",
                "goal": "Lock the campaign, roster, live-ops, and production operating model before scope fans out.",
                "exit_criteria": [
                    "campaign_program exists",
                    "roster_strategy exists",
                    "live_ops_plan exists",
                    "production_operating_model exists",
                ],
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
        "release_train": [
            {
                "id": "verified_slice",
                "window": "now",
                "goal": "Ship the first credible playable 3D slice with continuity artifacts attached.",
            },
            {
                "id": "launch_readiness",
                "window": "next_major_phase",
                "goal": "Lock enough regions, roster depth, and quest continuity to support a public-facing launch baseline.",
            },
            {
                "id": "service_growth" if live_service_enabled else "expansion_growth",
                "window": "post_launch",
                "goal": (
                    "Promote the project into a repeatable version cadence with event and roster governance."
                    if live_service_enabled
                    else "Promote the project into campaign expansions and new-region beats without restarting the production memory."
                ),
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
    quality = dict(game_request.get("quality_targets", {}) or {})
    runtime = str(target_runtime(blueprint, runtime_profile))
    live_service_enabled = bool(game_request.get("production", {}).get("live_service_profile", {}).get("enabled", False))
    target_platforms = [str(item).strip() for item in quality.get("target_platforms", []) or [] if str(item).strip()]
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
    if live_service_enabled:
        risks.append(
            {
                "id": "service_cadence_burn",
                "severity": "high",
                "area": "live_ops",
                "summary": "Roster, event, and region cadence can outpace validated combat and content quality.",
                "mitigation": "Tie every release wave to slice score, quality gates, and the operating-model workstreams before promotion.",
            }
        )
        risks.append(
            {
                "id": "economy_trust_drift",
                "severity": "medium",
                "area": "product",
                "summary": "Live-service rewards or monetization can erode trust if they outpace content and combat quality.",
                "mitigation": "Keep monetization guardrails, free progression viability, and version-quality evidence visible in the same planning loop.",
            }
        )
    if str(blueprint.get("meta", {}).get("dimension", "3D")) == "3D":
        risks.append(
            {
                "id": "readability_accessibility_drift",
                "severity": "medium",
                "area": "experience_design",
                "summary": "Combat readability, onboarding, and accessibility can drift as effects, enemies, and content density increase.",
                "mitigation": "Keep design_intelligence and quality gates current, and re-run balance probes before scaling content density.",
            }
        )
    if len(target_platforms) >= 3:
        risks.append(
            {
                "id": "cross_platform_certification",
                "severity": "high" if str(production.get("target_quality", "aa")).lower() == "aaa" else "medium",
                "area": "platform",
                "summary": "Cross-platform delivery multiplies runtime, UX, and performance certification pressure.",
                "mitigation": "Treat input profiles, load-time budgets, and platform-specific validation as first-class milestones before launch expansion.",
            }
        )
    return {
        "schema_version": "reverie.risk_register/1",
        "project_name": project_name(game_request, blueprint),
        "generated_at": _utc_now(),
        "runtime": runtime,
        "risks": risks,
    }
