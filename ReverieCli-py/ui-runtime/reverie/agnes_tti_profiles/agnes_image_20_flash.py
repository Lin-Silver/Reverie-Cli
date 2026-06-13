"""Agnes Image 2.0 Flash image generation profile."""

from __future__ import annotations

from typing import Any, Dict

from .common import build_metadata, generate_agnes_image


MODEL_ID = "agnes-image-2.0-flash"
DISPLAY_NAME = "Agnes Image 2.0 Flash"
DESCRIPTION = "Agnes image model for text-to-image, image-to-image, and multi-image composition workflows."
INPUT_MODALITIES = ["text", "image"]


def metadata() -> Dict[str, Any]:
    return build_metadata(
        model_id=MODEL_ID,
        display_name=DISPLAY_NAME,
        description=DESCRIPTION,
        input_modalities=INPUT_MODALITIES,
    )


def generate_image(**kwargs: Any) -> Dict[str, Any]:
    return generate_agnes_image(model_id=MODEL_ID, display_name=DISPLAY_NAME, **kwargs)
