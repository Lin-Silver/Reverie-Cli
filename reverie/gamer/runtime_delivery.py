"""Runtime delivery planning for Reverie-Gamer."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict

from .system_generators.shared import project_name


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def build_runtime_delivery_plan(
    game_request: Dict[str, Any],
    blueprint: Dict[str, Any],
    runtime_selection: Dict[str, Any],
    capability_graph: Dict[str, Any],
    *,
    system_bundle: Dict[str, Any] | None = None,
) -> Dict[str, Any]:
    """Build a runtime delivery plan from the capability graph."""

    selected = dict(capability_graph.get("selected_summary", {}) or {})
    packet_ids = list((system_bundle or {}).get("expansion_order", []) or [])
    blockers = list(selected.get("blockers", []) or [])
    runtime_root = str(selected.get("runtime_root", "."))
    validation_mode = "runtime_validation" if runtime_selection.get("profile", {}).get("can_validate") else "artifact_review"
    reference_intelligence = dict(runtime_selection.get("reference_intelligence", {}) or {})
    selected_runtime = str(runtime_selection.get("selected_runtime", "reverie_engine"))
    selected_alignment = next(
        (
            dict(item)
            for item in reference_intelligence.get("runtime_alignment", [])
            if str(item.get("runtime_id", "")).strip() == selected_runtime
        ),
        {},
    )
    alternate_scale_reference = next(
        (
            dict(item)
            for item in sorted(
                reference_intelligence.get("runtime_alignment", []),
                key=lambda entry: int(entry.get("reference_fit_score", 0)),
                reverse=True,
            )
            if str(item.get("runtime_id", "")).strip() != selected_runtime
        ),
        {},
    )
    live_service_enabled = bool(game_request.get("production", {}).get("live_service_profile", {}).get("enabled", False))
    large_scale_profile = dict(game_request.get("production", {}).get("large_scale_profile", {}) or {})
    runtime_contract_ids = [
        str(item).strip()
        for item in large_scale_profile.get("runtime_contracts", []) or []
        if str(item).strip()
    ]
    runtime_data_contracts = []
    if runtime_contract_ids:
        runtime_root_hint = "engine/godot/data" if selected_runtime == "godot" else "data/content"
        for contract_id in runtime_contract_ids:
            file_stem = contract_id
            extension = ".json" if selected_runtime == "godot" else ".yaml"
            runtime_data_contracts.append(
                {
                    "id": contract_id,
                    "runtime_path": f"{runtime_root_hint}/{file_stem}{extension}",
                    "purpose": {
                        "party_roster": "keep starter roster, active slots, and party-role coverage durable across sessions",
                        "elemental_matrix": "record elemental or affinity reactions for combat routing and future hero design",
                        "world_streaming": "stage region cells, streaming budgets, and landmark activation rules",
                        "commission_board": "keep short-session commissions or district objectives tied to the same project memory",
                        "regional_objectives": "preserve regional goals and objective handoffs as runtime-visible contracts",
                    }.get(contract_id, "preserve large-scale runtime state as a first-class artifact"),
                }
            )
    toolchain_matrix = list(reference_intelligence.get("toolchain_matrix", []) or [])
    adoption_plan = list(reference_intelligence.get("adoption_plan", []) or [])

    return {
        "schema_version": "reverie.runtime_delivery_plan/1",
        "project_name": project_name(game_request, blueprint),
        "generated_at": _utc_now(),
        "runtime": selected_runtime,
        "runtime_root": runtime_root,
        "delivery_phases": [
            {
                "id": "runtime_bootstrap",
                "goal": "Materialize the chosen runtime foundation and entry point.",
                "outputs": ["project root", "boot scene", "save/load entry path"],
            },
            {
                "id": "system_integration",
                "goal": "Map generated system packets into the runtime without losing data contracts.",
                "outputs": packet_ids,
            },
            {
                "id": "validation",
                "goal": "Prove smoke path, content loading, and project health at the selected runtime root.",
                "outputs": [validation_mode, "quality_gates", "slice_score"],
            },
            {
                "id": "expansion_base",
                "goal": "Leave the runtime ready for region expansion and asset replacement waves.",
                "outputs": ["runtime_delivery_plan", "continuation_recommendations"],
            },
        ],
        "capability_snapshot": selected,
        "toolchain_requirements": list(selected.get("toolchain_requirements", []) or []),
        "blockers": blockers,
        "reference_inputs": {
            "selected_runtime_alignment": selected_alignment,
            "recommended_stack": list(reference_intelligence.get("recommended_reference_stack", []) or []),
            "adoption_plan": adoption_plan,
            "toolchain_matrix": toolchain_matrix,
            "legal_guardrails": list(reference_intelligence.get("legal_guardrails", []) or []),
        },
        "delivery_lanes": [
            {
                "id": "runtime_bootstrap",
                "focus": "boot path, save path, and data-contract loading",
            },
            {
                "id": "content_runtime_binding",
                "focus": "map region, quest, boss, and roster artifacts into runtime-visible data",
            },
            {
                "id": "performance_and_validation",
                "focus": "stabilize streaming, combat responsiveness, and asset-import health before widening scope",
            },
        ],
        "scale_up_stages": [
            {
                "id": "verified_slice",
                "runtime": selected_runtime,
                "goal": "Ship a runnable, measurable, and high-signal first vertical slice.",
                "reference_support": list(selected_alignment.get("supporting_references", []) or []),
            },
            {
                "id": "multi_region_growth",
                "runtime": selected_runtime,
                "goal": "Expand regions, questlines, and reusable systems without breaking the runtime contract.",
                "reference_support": list(selected_alignment.get("supporting_references", []) or []),
            },
            {
                "id": "service_scale" if live_service_enabled else "post_launch_expansion",
                "runtime": selected_runtime,
                "goal": (
                    "Promote the project into a versioned content cadence with stronger release governance."
                    if live_service_enabled
                    else "Promote the verified slice into premium-style expansion packs and campaign chapters."
                ),
                "reference_support": list(alternate_scale_reference.get("supporting_references", []) or [])
                or list(selected_alignment.get("supporting_references", []) or []),
            },
        ],
        "future_runtime_references": {
            "selected_runtime": selected_runtime,
            "alternate_scale_reference": alternate_scale_reference,
        },
        "delivery_tracks": {
            "runtime_readiness": "scaffold_ready" if runtime_selection.get("profile", {}).get("can_scaffold") else "planning_only",
            "world_scale_track": str(large_scale_profile.get("world_cell_strategy", "single_slice_lane")),
            "launch_region_target": int(large_scale_profile.get("launch_region_target", 1) or 1),
            "starter_party_size": int(large_scale_profile.get("starter_party_size", 1) or 1),
            "content_cadence": str(
                large_scale_profile.get(
                    "content_cadence",
                    "major_expansion_packs" if not live_service_enabled else "six_week_content_cycles",
                )
            ),
        },
        "runtime_data_contracts": runtime_data_contracts,
        "optimization_backlog": [
            "profile region transitions and tighten loaded-cell counts before widening the active region budget",
            "keep combat VFX, projectile counts, and AI density inside one shared frame budget",
            "promote only validated assets into runtime import lanes so placeholder swaps do not regress load times",
        ],
        "asset_contract": {
            "runtime_root": runtime_root,
            "import_path": str(selected.get("asset_import_path", "project_level_registry")),
            "notes": [
                "Keep project-level artifacts authoritative even when runtime-native assets are mirrored elsewhere.",
                "Promote authored assets through validation rather than bypassing the registry and budget lanes.",
            ],
        },
    }
