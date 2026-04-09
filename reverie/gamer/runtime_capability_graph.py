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
    if "third-person-template" in capabilities or "3d_third_person" in templates:
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
        quest_cutscene = "research_only"

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
