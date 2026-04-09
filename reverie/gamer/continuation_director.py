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
) -> Dict[str, Any]:
    """Build recommendations for the next autonomous project iteration."""

    slice_score = dict(slice_score or {})
    quality_gates = dict(quality_gates or {})
    world_program = dict(world_program or {})
    reference_intelligence = dict(reference_intelligence or {})
    recommended_focus = str(expansion_backlog.get("recommended_focus", "stabilize_current_slice"))
    next_prompts: List[str] = [
        f"continue the project by focusing on {recommended_focus}",
        "expand the next region using the existing world and faction artifacts",
        "upgrade combat feel while preserving the verified slice loop",
    ]
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
        "reference_stack": list(reference_intelligence.get("recommended_reference_stack", []) or []),
        "legal_guardrails": list(reference_intelligence.get("legal_guardrails", []) or []),
        "next_prompt_pack": next_prompts,
        "instructions": [
            "reopen the durable artifacts before changing scope",
            "stabilize current blockers before broadening region or boss content",
            "prefer one coherent next milestone instead of parallel feature sprawl",
            "consult the local reference stack before introducing new runtime conventions or asset-pipeline branches",
        ],
    }


def continuation_recommendations_markdown(plan: Dict[str, Any]) -> str:
    """Render continuation recommendations as markdown."""

    lines = [f"# Continuation Recommendations: {plan.get('project_name', 'Untitled Reverie Slice')}", ""]
    lines.append(f"Recommended Focus: {plan.get('recommended_focus', 'stabilize_current_slice')}")
    lines.append(f"Quality Status: {plan.get('quality_status', 'review')}")
    lines.append(f"Slice Verdict: {plan.get('slice_verdict', 'planning_only')}")
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
    lines.append("## Next Prompt Pack")
    for item in plan.get("next_prompt_pack", []):
        lines.append(f"- {item}")
    lines.append("")
    lines.append("## Instructions")
    for item in plan.get("instructions", []):
        lines.append(f"- {item}")
    lines.append("")
    return "\n".join(lines)
