"""Agnes Video V2.0 text-to-video profile."""

from __future__ import annotations

from typing import Any, Dict

from .common import build_metadata


MODEL_ID = "agnes-video-v2.0"
DISPLAY_NAME = "Agnes Video V2.0"
DESCRIPTION = "Agnes asynchronous text-to-video model with optional image, multi-image, and keyframe inputs."
INPUT_MODALITIES = ["text", "image"]


def metadata() -> Dict[str, Any]:
    return build_metadata(
        model_id=MODEL_ID,
        display_name=DISPLAY_NAME,
        description=DESCRIPTION,
        input_modalities=INPUT_MODALITIES,
    )

