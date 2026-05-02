"""Continuation planning for long-running Reverie-Gamer projects."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def build_continuation_recommendations(
    game_request: Dict[str, Any],
    blueprint: Dict[str, Any],
    production_plan: Dict[str, Any],
    task_graph: Dict[str, Any],
    expansion_backlog: Dict[str, Any],
    resume_state: Dict[str, Any],
    *,
    slice_score: Dict[str, Any] | None = None,
    quality_gates: Dict[str, Any] | None = None,
    world_program: Dict[str, Any] | None = None,
    reference_intelligence: Dict[str, Any] | None = None,
    production_directive: Dict[str, Any] | None = None,
    campaign_program: Dict[str, Any] | None = None,
    roster_strategy: Dict[str, Any] | None = None,
    live_ops_plan: Dict[str, Any] | None = None,
    production_operating_model: Dict[str, Any] | None = None,
    design_intelligence: Dict[str, Any] | None = None,
) -> Dict[str, Any]:
    """Build recommendations for the next autonomous project iteration."""

    slice_score = dict(slice_score or {})
    quality_gates = dict(quality_gates or {})
    world_program = dict(world_program or {})
    reference_intelligence = dict(reference_intelligence or {})
    production_directive = dict(production_directive or {})
    campaign_program = dict(campaign_program or {})
    roster_strategy = dict(roster_strategy or {})
    live_ops_plan = dict(live_ops_plan or {})
    production_operating_model = dict(production_operating_model or {})
    design_intelligence = dict(design_intelligence or {})
    recommended_focus = str(expansion_backlog.get("recommended_focus", "stabilize_current_slice"))
    operations = list(production_directive.get("operations", []) or [])
    active_region_id = str(world_program.get("active_region_id", "")).strip()
    chapter_order = list(campaign_program.get("chapter_order", []) or [])
    roster_waves = list(roster_strategy.get("launch_roster_waves", []) or [])
    service_model = str(live_ops_plan.get("service_model", "boxed_release_plus_expansions")).strip()
    design_probes = list(design_intelligence.get("balance_lab", {}).get("doubling_halving_probes", []) or [])
    accessibility_features = list(design_intelligence.get("accessibility_baseline", {}).get("required_features", []) or [])
    next_prompts: List[str] = [
        f"continue the project by focusing on {recommended_focus}",
        f"expand the next region using the existing world and faction artifacts{' for ' + active_region_id if active_region_id else ''}",
        "upgrade combat feel while preserving the verified slice loop",
    ]
    if "plan_boss_arc" in operations:
        next_prompts.insert(1, f"build the first multi-phase boss encounter for {active_region_id or 'the active frontier'}")
    if "upgrade_gameplay_factory" in operations:
        next_prompts.append("tighten traversal, camera, and combo routing without widening scope too early")
    if len(roster_waves) > 1:
        next_prompts.append("expand the next recruitable character wave while preserving the current role matrix and boss counterplay")
    if service_model == "live_service":
        next_prompts.append("plan the next version update with one event beat, one roster beat, and one region-pressure objective")
    if len(chapter_order) > 1:
        next_prompts.append("prepare the next campaign chapter by reusing the current region, faction, and questline memory")
    if design_probes:
        next_prompts.append("run the next doubling-halving balance probe pass before adding enemy or boss breadth")
    if accessibility_features:
        next_prompts.append("tighten onboarding, accessibility, and return-session clarity without shrinking the mastery ceiling")
    return {
        "schema_version": "reverie.continuation_recommendations/1",
        "project_name": blueprint.get("meta", {}).get("project_name", "Untitled Reverie Slice"),
        "generated_at": _utc_now(),
        "recommended_focus": recommended_focus,
        "resume_artifacts": list(resume_state.get("artifacts_to_open_first", []) or []),
        "critical_path": list(task_graph.get("critical_path", []) or []),
        "quality_status": str(quality_gates.get("overall_status", "review")),
        "slice_verdict": str(slice_score.get("verdict", "planning_only")),
        "candidate_region_ids": list(world_program.get("region_order", []) or []),
        "latest_operations": operations,
        "campaign_chapter_ids": [str(item.get("id", "")).strip() for item in chapter_order if str(item.get("id", "")).strip()],
        "roster_wave_ids": [str(item.get("id", "")).strip() for item in roster_waves if str(item.get("id", "")).strip()],
        "service_model": service_model,
        "design_probe_ids": [str(item.get("id", "")).strip() for item in design_probes if str(item.get("id", "")).strip()],
        "accessibility_focus_count": len(accessibility_features),
        "reference_stack": list(reference_intelligence.get("recommended_reference_stack", []) or []),
        "legal_guardrails": list(reference_intelligence.get("legal_guardrails", []) or []),
        "next_prompt_pack": next_prompts,
        "instructions": [
            "reopen the durable artifacts before changing scope",
            "stabilize current blockers before broadening region or boss content",
            "keep campaign, roster, live-ops, and operating-model artifacts in sync with the next backlog item",
            "run the design-intelligence balance and accessibility checks before widening encounter density or content cadence",
            "prefer one coherent next milestone instead of parallel feature sprawl",
            "consult the local reference stack before introducing new runtime conventions or asset-pipeline branches",
            "use the operating model to decide which workstream owns the next region, boss, roster, or release beat",
        ],
        "operating_model_workstreams": [
            str(item.get("id", "")).strip()
            for item in production_operating_model.get("workstreams", []) or []
            if str(item.get("id", "")).strip()
        ],
    }


def continuation_recommendations_markdown(plan: Dict[str, Any]) -> str:
    """Render continuation recommendations as markdown."""

    lines = [f"# Continuation Recommendations: {plan.get('project_name', 'Untitled Reverie Slice')}", ""]
    lines.append(f"Recommended Focus: {plan.get('recommended_focus', 'stabilize_current_slice')}")
    lines.append(f"Quality Status: {plan.get('quality_status', 'review')}")
    lines.append(f"Slice Verdict: {plan.get('slice_verdict', 'planning_only')}")
    lines.append(f"Service Model: {plan.get('service_model', 'boxed_release_plus_expansions')}")
    lines.append(f"Accessibility Focus Count: {plan.get('accessibility_focus_count', 0)}")
    lines.append("")
    lines.append("## Resume Artifacts")
    for item in plan.get("resume_artifacts", []):
        lines.append(f"- {item}")
    lines.append("")
    if plan.get("reference_stack"):
        lines.append("## Reference Stack")
        for item in plan.get("reference_stack", []):
            lines.append(f"- {item.get('reference_id', 'reference')}: {item.get('role', '')}")
        lines.append("")
    if plan.get("legal_guardrails"):
        lines.append("## Guardrails")
        for item in plan.get("legal_guardrails", []):
            lines.append(f"- {item.get('note', '')}")
        lines.append("")
    if plan.get("campaign_chapter_ids"):
        lines.append("## Campaign Chapters")
        for item in plan.get("campaign_chapter_ids", []):
            lines.append(f"- {item}")
        lines.append("")
    if plan.get("roster_wave_ids"):
        lines.append("## Roster Waves")
        for item in plan.get("roster_wave_ids", []):
            lines.append(f"- {item}")
        lines.append("")
    if plan.get("design_probe_ids"):
        lines.append("## Design Probes")
        for item in plan.get("design_probe_ids", []):
            lines.append(f"- {item}")
        lines.append("")
    lines.append("## Next Prompt Pack")
    for item in plan.get("next_prompt_pack", []):
        lines.append(f"- {item}")
    lines.append("")
    if plan.get("operating_model_workstreams"):
        lines.append("## Operating Model Workstreams")
        for item in plan.get("operating_model_workstreams", []):
            lines.append(f"- {item}")
        lines.append("")
    lines.append("## Instructions")
    for item in plan.get("instructions", []):
        lines.append(f"- {item}")
    lines.append("")
    return "\n".join(lines)
