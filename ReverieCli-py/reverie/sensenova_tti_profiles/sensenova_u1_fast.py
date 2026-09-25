"""SenseNova U1 Fast image generation profile."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict

from .common import build_metadata, run_sensenova_image


MODEL_ID = "sensenova-u1-fast"
DISPLAY_NAME = "SenseNova U1 Fast"
DESCRIPTION = "SenseNova model dedicated to 2K infographic generation."
SUPPORTS_EDIT = False
DEFAULT_SIZE = "2752x1536"
SUPPORTED_SIZES = {
    "1664x2496", "2496x1664", "1760x2368", "2368x1760", "1824x2272",
    "2272x1824", "2048x2048", "2752x1536", "1536x2752", "3072x1376", "1344x3136",
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
        supports_edit=SUPPORTS_EDIT,
        **kwargs,
    )
