"""Registry for Agnes text-to-video API profiles."""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from . import agnes_video_v2


_PROFILES = {
    agnes_video_v2.MODEL_ID: agnes_video_v2,
}


def get_agnes_ttv_model_catalog() -> List[Dict[str, Any]]:
    """Return supported Agnes text-to-video models."""
    return [profile.metadata() for profile in _PROFILES.values()]


def get_agnes_ttv_profile(model_id: Any):
    """Return the Python profile module for an Agnes TTV model."""
    model_key = str(model_id or "").strip().lower()
    return _PROFILES.get(model_key)


def resolve_agnes_ttv_model(model_id_or_name: Any) -> Optional[Dict[str, Any]]:
    """Resolve model metadata by id or display name."""
    wanted = str(model_id_or_name or "").strip().lower()
    catalog = get_agnes_ttv_model_catalog()
    if not wanted:
        return catalog[0] if catalog else None
    for item in catalog:
        if wanted in {str(item.get("id", "")).lower(), str(item.get("display_name", "")).lower()}:
            return item
    for item in catalog:
        if wanted in str(item.get("id", "")).lower() or wanted in str(item.get("display_name", "")).lower():
            return item
    return None

