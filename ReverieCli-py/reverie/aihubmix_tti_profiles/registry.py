"""Registry for AIhubMix text-to-image API profiles."""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from . import gemini_31_flash_image_preview_free, gpt_image_2_free


_PROFILES = {
    gpt_image_2_free.MODEL_ID: gpt_image_2_free,
    gemini_31_flash_image_preview_free.MODEL_ID: gemini_31_flash_image_preview_free,
}


def get_aihubmix_tti_model_catalog() -> List[Dict[str, Any]]:
    """Return supported AIhubMix TTI models."""
    return [profile.metadata() for profile in _PROFILES.values()]


def get_aihubmix_tti_profile(model_id: Any):
    """Return the Python profile module for an AIhubMix TTI model."""
    model_key = str(model_id or "").strip().lower()
    return _PROFILES.get(model_key)


def resolve_aihubmix_tti_model(model_id_or_name: Any) -> Optional[Dict[str, Any]]:
    """Resolve model metadata by id or display name."""
    wanted = str(model_id_or_name or "").strip().lower()
    if not wanted:
        return get_aihubmix_tti_model_catalog()[0]
    for item in get_aihubmix_tti_model_catalog():
        if wanted in {str(item.get("id", "")).lower(), str(item.get("display_name", "")).lower()}:
            return item
    for item in get_aihubmix_tti_model_catalog():
        if wanted in str(item.get("id", "")).lower() or wanted in str(item.get("display_name", "")).lower():
            return item
    return None
