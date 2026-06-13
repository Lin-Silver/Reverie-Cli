"""Registry for Agnes text-to-image API profiles."""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from . import agnes_image_20_flash, agnes_image_21_flash


_PROFILES = {
    agnes_image_20_flash.MODEL_ID: agnes_image_20_flash,
    agnes_image_21_flash.MODEL_ID: agnes_image_21_flash,
}


def get_agnes_tti_model_catalog() -> List[Dict[str, Any]]:
    """Return supported Agnes image-output models."""
    return [profile.metadata() for profile in _PROFILES.values()]


def get_agnes_tti_profile(model_id: Any):
    """Return the Python profile module for an Agnes TTI model."""
    model_key = str(model_id or "").strip().lower()
    return _PROFILES.get(model_key)


def resolve_agnes_tti_model(model_id_or_name: Any) -> Optional[Dict[str, Any]]:
    """Resolve model metadata by id or display name."""
    wanted = str(model_id_or_name or "").strip().lower()
    if not wanted:
        return get_agnes_tti_model_catalog()[0]
    for item in get_agnes_tti_model_catalog():
        if wanted in {str(item.get("id", "")).lower(), str(item.get("display_name", "")).lower()}:
            return item
    for item in get_agnes_tti_model_catalog():
        if wanted in str(item.get("id", "")).lower() or wanted in str(item.get("display_name", "")).lower():
            return item
    return None
