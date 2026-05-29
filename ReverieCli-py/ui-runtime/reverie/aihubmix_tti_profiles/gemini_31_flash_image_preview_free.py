"""AIhubMix Gemini 3.1 Flash image preview profile."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List

from .common import get_field, normalize_choice, save_base64_image


MODEL_ID = "gemini-3.1-flash-image-preview-free"
DISPLAY_NAME = "Gemini 3.1 Flash Image Preview Free"
DESCRIPTION = "AIhubMix multimodal chat-completions image generation model."
SUPPORTED_ASPECT_RATIOS = {"1:1", "2:3", "3:2", "3:4", "4:3", "4:5", "5:4", "9:16", "16:9", "21:9"}


def metadata() -> Dict[str, Any]:
    return {
        "id": MODEL_ID,
        "display_name": DISPLAY_NAME,
        "description": DESCRIPTION,
        "api": "chat.completions.create",
        "supports_n": False,
        "supported_aspect_ratios": sorted(SUPPORTED_ASPECT_RATIOS),
    }


def _message_parts(response: Any) -> List[Any]:
    choices = get_field(response, "choices", []) or []
    if not choices:
        return []
    message = get_field(choices[0], "message", None)
    parts = get_field(message, "multi_mod_content", None)
    if parts is None:
        parts = get_field(message, "content", None)
    return parts if isinstance(parts, list) else []


def generate_image(
    client: Any,
    *,
    prompt: str,
    output_path: Path,
    aspect_ratio: Any = "1:1",
    **_: Any,
) -> Dict[str, Any]:
    normalized_aspect_ratio = normalize_choice(aspect_ratio, SUPPORTED_ASPECT_RATIOS, "1:1")
    response = client.chat.completions.create(
        model=MODEL_ID,
        messages=[
            {"role": "system", "content": f"aspect_ratio={normalized_aspect_ratio}"},
            {"role": "user", "content": [{"type": "text", "text": prompt}]},
        ],
        modalities=["text", "image"],
    )

    parts = _message_parts(response)
    saved_images: List[str] = []
    text_parts: List[str] = []
    total_images = sum(1 for part in parts if get_field(part, "inline_data", None))
    image_index = 0
    for part in parts:
        text = get_field(part, "text", "")
        if text:
            text_parts.append(str(text))
        inline_data = get_field(part, "inline_data", None)
        if not inline_data:
            continue
        image_index += 1
        saved_images.append(
            save_base64_image(
                get_field(inline_data, "data", ""),
                output_path,
                stem=f"aihubmix_gemini_image_{normalized_aspect_ratio.replace(':', '-')}",
                index=image_index,
                total=max(1, total_images),
                mime_type=get_field(inline_data, "mime_type", "image/png"),
            )
        )

    return {
        "model": MODEL_ID,
        "display_name": DISPLAY_NAME,
        "saved_images": saved_images,
        "text_parts": text_parts,
        "request": {"aspect_ratio": normalized_aspect_ratio},
    }
