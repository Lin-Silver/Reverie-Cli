"""Runtime registry and selection helpers for Reverie-Gamer."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List

from .reference_intelligence import build_reference_intelligence
from .runtime_adapters import (
    BaseRuntimeAdapter,
    ReverieEngineRuntimeAdapter,
)


LEGACY_RUNTIME_SOURCES = {"godot", "o3de", "renpy"}


def _adapter_table() -> list[BaseRuntimeAdapter]:
    return [ReverieEngineRuntimeAdapter()]


def infer_existing_runtime(project_root: Path) -> str:
    root = Path(project_root)
    if (root / "data" / "config" / "engine.yaml").exists():
        return "reverie_engine"
    if (root / "engine" / "godot" / "project.godot").exists() or (root / "project.godot").exists():
        return "reverie_engine"
    if (root / "engine" / "o3de").exists():
        return "reverie_engine"
    if any(root.rglob("*.rpy")):
        return "reverie_engine"
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

    raw_existing = str(existing_runtime or "").strip().lower()
    inferred_existing = str(raw_existing or infer_existing_runtime(root)).strip().lower()
    runtime_preferences = dict(game_request.get("runtime_preferences", {}))
    explicit_requested = str(requested_runtime or runtime_preferences.get("requested_runtime") or "").strip().lower()
    preferred_runtime = str(runtime_preferences.get("preferred_runtime") or "").strip().lower()
    chosen_id = "reverie_engine"
    reason = "Selected the unified built-in Reverie Engine runtime."
    fallback_reason = ""
    legacy_source = next(
        (
            value
            for value in (
                str(runtime_preferences.get("legacy_source") or "").strip().lower(),
                explicit_requested,
                preferred_runtime,
                raw_existing,
            )
            if value in LEGACY_RUNTIME_SOURCES
        ),
        "",
    )
    if legacy_source:
        reason = (
            f"Mapped the requested {legacy_source} source into the unified Reverie Engine; "
            "the legacy engine remains reference or migration input only."
        )
    elif inferred_existing == "reverie_engine":
        reason = "Preserved the repository's canonical Reverie Engine runtime."
    elif explicit_requested and explicit_requested != "reverie_engine":
        fallback_reason = f"Runtime '{explicit_requested}' is not a built-in runtime; using Reverie Engine."

    chosen_profile = profiles[chosen_id]

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
        "legacy_source": legacy_source,
        "unified_runtime": True,
    }
