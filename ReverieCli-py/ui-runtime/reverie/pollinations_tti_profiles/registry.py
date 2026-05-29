"""Registry for Pollinations text-to-image API profiles."""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from . import flux, gptimage, gptimage_large, klein, kontext, nova_canvas, qwen_image, wan_image, zimage


_PROFILES = {
    flux.MODEL_ID: flux,
    gptimage.MODEL_ID: gptimage,
    gptimage_large.MODEL_ID: gptimage_large,
    kontext.MODEL_ID: kontext,
    zimage.MODEL_ID: zimage,
    wan_image.MODEL_ID: wan_image,
    qwen_image.MODEL_ID: qwen_image,
    klein.MODEL_ID: klein,
    nova_canvas.MODEL_ID: nova_canvas,
}


def get_pollinations_tti_model_catalog() -> List[Dict[str, Any]]:
    """Return supported free Pollinations image-output models."""
    return [profile.metadata() for profile in _PROFILES.values()]


def get_pollinations_tti_profile(model_id: Any):
    """Return the Python profile module for a Pollinations TTI model."""
    model_key = str(model_id or "").strip().lower()
    return _PROFILES.get(model_key)


def resolve_pollinations_tti_model(model_id_or_name: Any) -> Optional[Dict[str, Any]]:
    """Resolve model metadata by id or display name."""
    wanted = str(model_id_or_name or "").strip().lower()
    if not wanted:
        return get_pollinations_tti_model_catalog()[0]
    for item in get_pollinations_tti_model_catalog():
        if wanted in {str(item.get("id", "")).lower(), str(item.get("display_name", "")).lower()}:
            return item
    for item in get_pollinations_tti_model_catalog():
        if wanted in str(item.get("id", "")).lower() or wanted in str(item.get("display_name", "")).lower():
            return item
    return None
