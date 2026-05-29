"""AIhubMix gpt-image-2-free image generation profile."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List

from .common import clamp_int, get_field, iter_response_data, normalize_choice, save_base64_image, save_url_image


MODEL_ID = "gpt-image-2-free"
DISPLAY_NAME = "GPT Image 2 Free"
DESCRIPTION = "AIhubMix OpenAI images.generate model for text-to-image generation."
SUPPORTED_SIZES = {"1024x1024", "1024x1536", "1536x1024", "auto"}
SUPPORTED_QUALITIES = {"high", "medium", "low", "auto"}


def metadata() -> Dict[str, Any]:
    return {
        "id": MODEL_ID,
        "display_name": DISPLAY_NAME,
        "description": DESCRIPTION,
        "api": "images.generate",
        "supports_n": True,
        "supported_sizes": sorted(SUPPORTED_SIZES),
        "supported_qualities": sorted(SUPPORTED_QUALITIES),
    }


def generate_image(
    client: Any,
    *,
    prompt: str,
    output_path: Path,
    n: Any = 1,
    size: Any = "auto",
    quality: Any = "auto",
    **_: Any,
) -> Dict[str, Any]:
    image_count = clamp_int(n, default=1, minimum=1, maximum=10)
    normalized_size = normalize_choice(size, SUPPORTED_SIZES, "auto")
    normalized_quality = normalize_choice(quality, SUPPORTED_QUALITIES, "auto")

    response = client.images.generate(
        model=MODEL_ID,
        prompt=prompt,
        n=image_count,
        size=normalized_size,
        quality=normalized_quality,
    )

    data_items = list(iter_response_data(response))
    saved_images: List[str] = []
    for index, item in enumerate(data_items, start=1):
        b64_json = get_field(item, "b64_json", "")
        if b64_json:
            saved_images.append(
                save_base64_image(
                    b64_json,
                    output_path,
                    stem="aihubmix_gpt_image_2",
                    index=index,
                    total=len(data_items),
                )
            )
            continue
        image_url = get_field(item, "url", "")
        if image_url:
            saved_images.append(
                save_url_image(
                    image_url,
                    output_path,
                    stem="aihubmix_gpt_image_2",
                    index=index,
                    total=len(data_items),
                )
            )

    return {
        "model": MODEL_ID,
        "display_name": DISPLAY_NAME,
        "saved_images": saved_images,
        "text_parts": [],
        "request": {
            "n": image_count,
            "size": normalized_size,
            "quality": normalized_quality,
        },
    }
