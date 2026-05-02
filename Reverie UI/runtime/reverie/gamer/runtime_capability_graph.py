"""Runtime capability graph for Reverie-Gamer production planning."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _runtime_root(runtime_id: str) -> str:
    if runtime_id == "godot":
        return "engine/godot"
    if runtime_id == "o3de":
        return "engine/o3de"
    return "."


def _capability_summary(profile: Dict[str, Any]) -> Dict[str, Any]:
    runtime_id = str(profile.get("id", "reverie_engine"))
    capabilities = {str(item).strip() for item in profile.get("capabilities", []) if str(item).strip()}
    templates = {str(item).strip() for item in profile.get("template_support", []) if str(item).strip()}
    blockers: List[str] = []
    if not profile.get("can_scaffold", False):
        blockers.append("runtime does not currently expose repository-native scaffolding")
    if not profile.get("can_validate", False):
        blockers.append("runtime validation still depends on external tooling or later integration")

    combat_profile = "action_slice_ready"
    if "third-person-template" in capabilities or "third_person_action" in templates or "3d_third_person" in templates:
        combat_profile = "third_person_action_base"
    elif "large-scale-3d" in capabilities:
        combat_profile = "future_large_scale_combat_base"

    world_streaming = "single_region_slice"
    if "streaming" in capabilities or "large-scale-3d" in capabilities:
        world_streaming = "regional_streaming_ready"

    quest_cutscene = "data_driven_quest_flow"
    if runtime_id == "godot":
        quest_cutscene = "scene_driven_quest_flow"
    elif runtime_id == "o3de":
        quest_cutscene = "component_entity_flow"

    asset_import = "project_level_registry"
    if "gltf" in capabilities:
        asset_import = "gltf_scene_pipeline"
    elif runtime_id == "o3de":
        asset_import = "asset_processor_pipeline"

    performance_budget = "slice_friendly"
    if "large-scale-3d" in capabilities:
        performance_budget = "future_large_world_budget"

    return {
        "runtime_id": runtime_id,
        "display_name": str(profile.get("display_name", runtime_id)),
        "available": bool(profile.get("available", False)),
        "health": str(profile.get("health", "unknown")),
        "runtime_root": _runtime_root(runtime_id),
        "combat_capability_profile": combat_profile,
        "world_streaming_capability": world_streaming,
        "quest_cutscene_capability": quest_cutscene,
        "asset_import_path": asset_import,
        "performance_budget_profile": performance_budget,
        "toolchain_requirements": [
            "repository scaffold",
            "runtime validation" if profile.get("can_validate", False) else "runtime bootstrap review",
            "asset import contract",
        ],
        "blockers": blockers,
        "capabilities": sorted(capabilities),
        "template_support": sorted(templates),
    }


def _scale_fit(summary: Dict[str, Any], game_request: Dict[str, Any]) -> Dict[str, Any]:
    production = dict(game_request.get("production", {}) or {})
    large_scale_profile = dict(production.get("large_scale_profile", {}) or {})
    live_service_enabled = bool(production.get("live_service_profile", {}).get("enabled", False))
    runtime_contract_count = len(large_scale_profile.get("runtime_contracts", []) or [])
    reference_fit_score = int(summary.get("reference_fit_score", 0) or 0)
    score = 45 + min(reference_fit_score // 4, 20)
    if summary.get("world_streaming_capability") == "regional_streaming_ready":
        score += 15
    if summary.get("combat_capability_profile") in {"third_person_action_base", "future_large_scale_combat_base"}:
        score += 10
    if runtime_contract_count >= 4:
        score += 5
    if live_service_enabled:
        score += 5
    score = max(0, min(100, score))
    verdict = "slice_first_large_scale_candidate" if score >= 70 else "credible_slice_runtime" if score >= 55 else "prototype_bias"
    return {
        "score": score,
        "verdict": verdict,
        "notes": [
            "Prefer runtimes that can scaffold a verified slice now while preserving future region and roster contracts.",
            "Reference fit can raise planning confidence, but scaffold readiness still decides whether the runtime can ship the first slice here.",
        ],
    }


def build_runtime_capability_graph(
    game_request: Dict[str, Any],
    runtime_selection: Dict[str, Any],
) -> Dict[str, Any]:
    """Build a capability graph from runtime selection data."""

    profiles = [dict(item) for item in runtime_selection.get("profiles", [])]
    summaries = [_capability_summary(profile) for profile in profiles]
    selected_runtime = str(runtime_selection.get("selected_runtime", "reverie_engine"))
    reference_intelligence = dict(runtime_selection.get("reference_intelligence", {}) or {})
    reference_alignment = {
        str(item.get("runtime_id", "")).strip(): dict(item)
        for item in reference_intelligence.get("runtime_alignment", [])
        if str(item.get("runtime_id", "")).strip()
    }
    for summary in summaries:
        alignment = reference_alignment.get(summary["runtime_id"], {})
        summary["reference_fit_score"] = int(alignment.get("reference_fit_score", 0))
        summary["reference_fit"] = str(alignment.get("fit", "unknown"))
        summary["reference_execution_readiness"] = str(alignment.get("execution_readiness", "unknown"))
        summary["reference_support"] = list(alignment.get("supporting_references", []) or [])
        summary["scale_fit"] = _scale_fit(summary, game_request)
    selected_summary = next(
        (summary for summary in summaries if summary["runtime_id"] == selected_runtime),
        _capability_summary(dict(runtime_selection.get("profile", {}) or {"id": selected_runtime})),
    )
    return {
        "schema_version": "reverie.runtime_capability_graph/1",
        "project_name": str(game_request.get("meta", {}).get("project_name", "Untitled Reverie Slice")),
        "generated_at": _utc_now(),
        "selected_runtime": selected_runtime,
        "decision_reason": str(runtime_selection.get("reason", "")),
        "fallback_reason": str(runtime_selection.get("fallback_reason", "")),
        "nodes": summaries,
        "edges": [
            {
                "from": "request",
                "to": summary["runtime_id"],
                "relationship": "candidate_runtime",
            }
            for summary in summaries
        ]
        + [
            {
                "from": ref_id,
                "to": runtime_id,
                "relationship": "reference_supports_runtime",
            }
            for runtime_id, alignment in reference_alignment.items()
            for ref_id in alignment.get("supporting_references", []) or []
        ],
        "selected_summary": selected_summary,
        "risk_nodes": [
            {
                "id": f"{summary['runtime_id']}_validation_risk",
                "runtime_id": summary["runtime_id"],
                "severity": "medium" if summary.get("reference_execution_readiness") == "scaffold_ready" else "high",
                "summary": "Runtime validation and scale-up discipline must stay attached to the same project memory.",
            }
            for summary in summaries
        ],
        "reference_sources": [
            {
                "id": item.get("id", ""),
                "engine": item.get("engine", ""),
                "category": item.get("category", ""),
                "signals": list(item.get("signals", []) or [])[:8],
            }
            for item in reference_intelligence.get("detected_repositories", [])
        ],
    }
