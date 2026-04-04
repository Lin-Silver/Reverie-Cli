"""Runtime registry and selection helpers for Reverie-Gamer."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List

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
    elif dimension == "3D" and profiles["godot"].can_scaffold:
        chosen_id = "godot"
        reason = "Selected Godot as the strongest extensible 3D slice foundation."
    else:
        chosen_id = "reverie_engine"
        reason = "Selected Reverie Engine for the fastest prompt-to-playable slice."

    chosen_profile = profiles[chosen_id]
    if not chosen_profile.available and chosen_id != "reverie_engine":
        fallback_reason = f"{chosen_profile.display_name} is not currently available; falling back to Reverie Engine."
        chosen_id = "reverie_engine"
        chosen_profile = profiles[chosen_id]

    adapter = adapters[chosen_id]
    return {
        "selected_runtime": chosen_id,
        "reason": reason,
        "fallback_reason": fallback_reason,
        "profile": chosen_profile.to_dict(),
        "profiles": [profile.to_dict() for profile in profiles.values()],
        "adapter": adapter,
    }
