"""Agnes Image 2.1 Flash image generation profile."""

from __future__ import annotations

from typing import Any, Dict

from .common import build_metadata, generate_agnes_image


MODEL_ID = "agnes-image-2.1-flash"
DISPLAY_NAME = "Agnes Image 2.1 Flash"
DESCRIPTION = "Agnes image model optimized for high-density text-to-image and image editing prompts."
INPUT_MODALITIES = ["text", "image"]


def metadata() -> Dict[str, Any]:
    return build_metadata(
        model_id=MODEL_ID,
        display_name=DISPLAY_NAME,
        description=DESCRIPTION,
        input_modalities=INPUT_MODALITIES,
    )


def generate_image(**kwargs: Any) -> Dict[str, Any]:
    if str(kwargs.get("response_format") or "b64_json").strip().lower() == "b64_json":
        extra_body = dict(kwargs.get("extra_body") or {})
        extra_body.setdefault("response_format", "b64_json")
        kwargs["extra_body"] = extra_body
    return generate_agnes_image(model_id=MODEL_ID, display_name=DISPLAY_NAME, **kwargs)
