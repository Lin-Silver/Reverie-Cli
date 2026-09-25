"""SenseNova U1.5 Lite image generation and editing profile."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict

from .common import build_metadata, run_sensenova_image


MODEL_ID = "sensenova-u1.5-lite"
DISPLAY_NAME = "SenseNova U1.5 Lite"
DESCRIPTION = "SenseNova unified image generation and editing model (text-to-image and image editing)."
SUPPORTS_EDIT = True
DEFAULT_SIZE = "2048x2048"
# U1.5 Lite accepts arbitrary sizes up to 4K plus ``auto``; the set below is a
# convenience list for the picker, but any WIDTHxHEIGHT is passed through.
SUPPORTED_SIZES = {
    "1024x1024", "2048x2048", "2752x1536", "1536x2752",
    "2496x1664", "1664x2496", "4096x4096",
}


def metadata() -> Dict[str, Any]:
    return build_metadata(
        model_id=MODEL_ID,
        display_name=DISPLAY_NAME,
        description=DESCRIPTION,
        supported_sizes=sorted(SUPPORTED_SIZES),
        supports_edit=SUPPORTS_EDIT,
        default_size=DEFAULT_SIZE,
    )


def generate_image(*, prompt: str, output_path: Path, **kwargs: Any) -> Dict[str, Any]:
    return run_sensenova_image(
        model_id=MODEL_ID,
        display_name=DISPLAY_NAME,
        prompt=prompt,
        output_path=output_path,
        supported_sizes=SUPPORTED_SIZES,
        default_size=DEFAULT_SIZE,
        permissive_size=True,
        supports_edit=SUPPORTS_EDIT,
        **kwargs,
    )
