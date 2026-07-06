"""SenseNova U1 Fast image generation profile."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List

from ..aihubmix_tti_profiles.common import get_field, iter_response_data, normalize_choice, save_base64_image, save_url_image


MODEL_ID = "sensenova-u1-fast"
DISPLAY_NAME = "SenseNova U1 Fast"
DESCRIPTION = "SenseNova model dedicated to 2K infographic generation."
SUPPORTED_SIZES = {
    "1664x2496", "2496x1664", "1760x2368", "2368x1760", "1824x2272",
    "2272x1824", "2048x2048", "2752x1536", "1536x2752", "3072x1376", "1344x3136",
}


def metadata() -> Dict[str, Any]:
    return {
        "id": MODEL_ID,
        "display_name": DISPLAY_NAME,
        "description": DESCRIPTION,
        "api": "images.generate",
        "input_modalities": ["text"],
        "output_modalities": ["image"],
        "supports_n": False,
        "supported_sizes": sorted(SUPPORTED_SIZES),
    }


def generate_image(client: Any, *, prompt: str, output_path: Path, size: Any = "2752x1536", **_: Any) -> Dict[str, Any]:
    normalized_size = normalize_choice(size, SUPPORTED_SIZES, "2752x1536")
    response = client.images.generate(model=MODEL_ID, prompt=prompt, size=normalized_size, n=1)
    data_items = list(iter_response_data(response))
    saved_images: List[str] = []
    for index, item in enumerate(data_items, start=1):
        b64_json = get_field(item, "b64_json", "")
        if b64_json:
            saved_images.append(save_base64_image(b64_json, output_path, stem="sensenova_u1_fast", index=index, total=len(data_items)))
            continue
        image_url = get_field(item, "url", "")
        if image_url:
            saved_images.append(save_url_image(image_url, output_path, stem="sensenova_u1_fast", index=index, total=len(data_items)))
    return {
        "model": MODEL_ID,
        "display_name": DISPLAY_NAME,
        "saved_images": saved_images,
        "text_parts": [],
        "request": {"n": 1, "size": normalized_size},
    }
