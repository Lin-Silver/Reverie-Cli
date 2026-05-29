"""Pollinations Z-Image profile."""

from __future__ import annotations

from typing import Any, Dict

from .common import build_metadata, generate_openai_compatible_image


MODEL_ID = "zimage"
DISPLAY_NAME = "Z-Image"
DESCRIPTION = "Pollinations free text-to-image model."
INPUT_MODALITIES = ["text"]


def metadata() -> Dict[str, Any]:
    return build_metadata(
        model_id=MODEL_ID,
        display_name=DISPLAY_NAME,
        description=DESCRIPTION,
        input_modalities=INPUT_MODALITIES,
    )


def generate_image(**kwargs: Any) -> Dict[str, Any]:
    return generate_openai_compatible_image(model_id=MODEL_ID, display_name=DISPLAY_NAME, **kwargs)
