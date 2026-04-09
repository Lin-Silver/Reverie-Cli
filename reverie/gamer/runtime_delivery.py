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
            "legal_guardrails": list(reference_intelligence.get("legal_guardrails", []) or []),
        },
        "asset_contract": {
            "runtime_root": runtime_root,
            "import_path": str(selected.get("asset_import_path", "project_level_registry")),
            "notes": [
                "Keep project-level artifacts authoritative even when runtime-native assets are mirrored elsewhere.",
                "Promote authored assets through validation rather than bypassing the registry and budget lanes.",
            ],
        },
    }
