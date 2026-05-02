"""Runtime registry and selection helpers for Reverie-Gamer."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List

from .reference_intelligence import build_reference_intelligence
from .runtime_adapters import (
    BaseRuntimeAdapter,
    GodotRuntimeAdapter,
    O3DERuntimeAdapter,
    ReverieEngineRuntimeAdapter,
)


def _adapter_table() -> list[BaseRuntimeAdapter]:
    return [
        ReverieEngineRuntimeAdapter(),
        GodotRuntimeAdapter(),
        O3DERuntimeAdapter(),
    ]


def infer_existing_runtime(project_root: Path) -> str:
    root = Path(project_root)
    if (root / "data" / "config" / "engine.yaml").exists():
        return "reverie_engine"
    if (root / "engine" / "godot" / "project.godot").exists() or (root / "project.godot").exists():
        return "godot"
    if (root / "engine" / "o3de").exists():
        return "o3de"
    return ""


def discover_runtime_profiles(project_root: Path, *, app_root: Path | None = None) -> List[Dict[str, Any]]:
    """Return the discovered runtime profiles."""

    root = Path(project_root)
    app = Path(app_root or root)
    profiles = []
    for adapter in _adapter_table():
        profiles.append(adapter.detect(root, app).to_dict())
    return profiles


def select_runtime_profile(
    game_request: Dict[str, Any],
    *,
    project_root: Path,
    app_root: Path | None = None,
    requested_runtime: str = "",
    existing_runtime: str = "",
) -> Dict[str, Any]:
    """Choose the most appropriate runtime for the current slice request."""

    root = Path(project_root)
    app = Path(app_root or root)
    adapters = {adapter.runtime_id: adapter for adapter in _adapter_table()}
    profiles = {adapter.runtime_id: adapter.detect(root, app) for adapter in adapters.values()}
    reference_intelligence = build_reference_intelligence(
        game_request,
        project_root=root,
        app_root=app,
        runtime_profiles=[profile.to_dict() for profile in profiles.values()],
    )
    reference_alignment = {
        str(item.get("runtime_id", "")).strip(): dict(item)
        for item in reference_intelligence.get("runtime_alignment", [])
        if str(item.get("runtime_id", "")).strip()
    }

    inferred_existing = str(existing_runtime or infer_existing_runtime(root)).strip().lower()
    runtime_preferences = dict(game_request.get("runtime_preferences", {}))
    explicit_requested = str(requested_runtime or runtime_preferences.get("requested_runtime") or "").strip().lower()
    preferred_runtime = str(runtime_preferences.get("preferred_runtime") or "").strip().lower()
    dimension = str(game_request.get("experience", {}).get("dimension", "3D")).upper()

    chosen_id = ""
    reason = ""
    fallback_reason = ""

    if inferred_existing and inferred_existing in profiles:
        chosen_id = inferred_existing
        reason = "Preserved the runtime already present in the repository."
    elif explicit_requested and explicit_requested in profiles:
        chosen_id = explicit_requested
        reason = "Used the explicitly requested runtime."
    elif preferred_runtime and preferred_runtime in profiles:
        chosen_id = preferred_runtime
        reason = "Used the request compiler's preferred runtime."
    elif dimension == "3D":
        scaffold_ready_alignment = [
            item
            for item in reference_intelligence.get("runtime_alignment", [])
            if profiles.get(str(item.get("runtime_id", "")))
            and profiles[str(item.get("runtime_id", ""))].can_scaffold
            and "experimental" not in profiles[str(item.get("runtime_id", ""))].maturity
        ]
        scaffold_ready_alignment.sort(key=lambda item: int(item.get("reference_fit_score", 0)), reverse=True)
        strongest_runtime = ""
        strongest_score = 0
        if scaffold_ready_alignment:
            strongest = scaffold_ready_alignment[0]
            strongest_runtime = str(strongest.get("runtime_id", "")).strip()
            strongest_score = int(strongest.get("reference_fit_score", 0))
        if strongest_runtime in profiles and strongest_score >= 60:
            chosen_id = strongest_runtime
            reason = (
                "Selected the strongest execution-ready runtime backed by local reference projects: "
                f"{strongest_runtime}."
            )
        elif profiles["godot"].can_scaffold:
            chosen_id = "godot"
            reason = "Selected Godot as the strongest extensible 3D slice foundation."
        else:
            chosen_id = "reverie_engine"
            reason = "Selected Reverie Engine for the fastest prompt-to-playable slice."
    else:
        chosen_id = "reverie_engine"
        reason = "Selected Reverie Engine for the fastest prompt-to-playable slice."

    chosen_profile = profiles[chosen_id]
    if not chosen_profile.available and chosen_id != "reverie_engine":
        fallback_reason = f"{chosen_profile.display_name} is not currently available; falling back to Reverie Engine."
        chosen_id = "reverie_engine"
        chosen_profile = profiles[chosen_id]

    strongest_reference = max(
        reference_intelligence.get("runtime_alignment", []),
        key=lambda item: int(item.get("reference_fit_score", 0)),
        default={},
    )
    strongest_reference_runtime = str(strongest_reference.get("runtime_id", "")).strip()
    if (
        strongest_reference_runtime
        and strongest_reference_runtime != chosen_id
        and strongest_reference.get("execution_readiness") != "scaffold_ready"
        and int(strongest_reference.get("reference_fit_score", 0)) >= 60
        and not fallback_reason
    ):
        fallback_reason = (
            f"Local references most strongly match {strongest_reference_runtime}, but it is not scaffold-ready here; "
            f"selected {chosen_id} for executable slice delivery."
        )

    adapter = adapters[chosen_id]
    return {
        "selected_runtime": chosen_id,
        "reason": reason,
        "fallback_reason": fallback_reason,
        "profile": chosen_profile.to_dict(),
        "profiles": [profile.to_dict() for profile in profiles.values()],
        "adapter": adapter,
        "reference_alignment": reference_alignment,
        "reference_intelligence": reference_intelligence,
    }
