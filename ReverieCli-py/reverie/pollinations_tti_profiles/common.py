"""Shared helpers for Pollinations image generation profiles."""

from __future__ import annotations

import base64
from pathlib import Path
from typing import Any, Dict, List, Optional
from urllib.request import Request, urlopen

import requests

from ..aihubmix_tti_profiles.common import clamp_int, get_field, normalize_choice, resolve_output_file


POLLINATIONS_DEFAULT_BASE_URL = "https://gen.pollinations.ai/v1"
SUPPORTED_SIZES = {"1024x1024", "1024x1536", "1536x1024", "auto"}
SUPPORTED_QUALITIES = {"high", "medium", "low", "auto"}
SUPPORTED_RESPONSE_FORMATS = {"b64_json", "url"}


def normalize_pollinations_base_url(base_url: Any) -> str:
    raw = str(base_url or POLLINATIONS_DEFAULT_BASE_URL).strip() or POLLINATIONS_DEFAULT_BASE_URL
    raw = raw.rstrip("/")
    if raw.endswith("/images/generations"):
        raw = raw[: -len("/images/generations")]
    if not raw.endswith("/v1"):
        raw = f"{raw}/v1"
    return raw


def build_images_url(base_url: Any) -> str:
    return f"{normalize_pollinations_base_url(base_url)}/images/generations"


def extension_for_mime(mime_type: Any) -> str:
    mime = str(mime_type or "").strip().lower().split(";")[0]
    if mime in {"image/jpeg", "image/jpg"}:
        return ".jpg"
    if mime == "image/webp":
        return ".webp"
    return ".png"


def _save_base64_image(data: Any, output_path: Path, *, stem: str, index: int, total: int) -> str:
    encoded = str(data or "").strip()
    if not encoded:
        raise ValueError("image response did not include base64 data")
    image_bytes = base64.b64decode(encoded)
    target = resolve_output_file(output_path, stem=stem, index=index, total=total, suffix=".png")
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(image_bytes)
    return str(target)


def _save_url_image(url: Any, output_path: Path, *, stem: str, index: int, total: int) -> str:
    image_url = str(url or "").strip()
    if not image_url:
        raise ValueError("image response did not include an image URL")
    request = Request(image_url, headers={"User-Agent": "ReverieCLI-Pollinations-TTI/1.0"})
    with urlopen(request, timeout=120) as response:
        content_type = response.headers.get("Content-Type", "image/png")
        image_bytes = response.read()
    target = resolve_output_file(
        output_path,
        stem=stem,
        index=index,
        total=total,
        suffix=extension_for_mime(content_type),
    )
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(image_bytes)
    return str(target)


def _optional_bool(value: Any) -> Optional[bool]:
    if value is None:
        return None
    if isinstance(value, bool):
        return value
    raw = str(value).strip().lower()
    if not raw:
        return None
    if raw in {"1", "true", "yes", "y", "on"}:
        return True
    if raw in {"0", "false", "no", "n", "off"}:
        return False
    return None


def build_metadata(
    *,
    model_id: str,
    display_name: str,
    description: str,
    input_modalities: List[str],
) -> Dict[str, Any]:
    return {
        "id": model_id,
        "display_name": display_name,
        "description": description,
        "api": "v1.images.generations",
        "free": True,
        "paid_only": False,
        "input_modalities": input_modalities,
        "output_modalities": ["image"],
        "requires_api_key": True,
        "supports_n": False,
        "supported_sizes": sorted(SUPPORTED_SIZES),
        "supported_qualities": sorted(SUPPORTED_QUALITIES),
        "supported_response_formats": sorted(SUPPORTED_RESPONSE_FORMATS),
    }


def generate_openai_compatible_image(
    *,
    model_id: str,
    display_name: str,
    prompt: str,
    output_path: Path,
    base_url: Any = POLLINATIONS_DEFAULT_BASE_URL,
    api_key: Any = "",
    timeout: Any = 300,
    n: Any = 1,
    size: Any = "1024x1024",
    quality: Any = "medium",
    response_format: Any = "b64_json",
    safe: Any = "",
    **_: Any,
) -> Dict[str, Any]:
    image_count = clamp_int(n, default=1, minimum=1, maximum=1)
    normalized_size = normalize_choice(size, SUPPORTED_SIZES, "1024x1024")
    normalized_quality = normalize_choice(quality, SUPPORTED_QUALITIES, "medium")
    normalized_response_format = normalize_choice(response_format, SUPPORTED_RESPONSE_FORMATS, "b64_json")
    try:
        timeout_seconds = max(1, int(timeout or 300))
    except (TypeError, ValueError):
        timeout_seconds = 300

    payload: Dict[str, Any] = {
        "model": model_id,
        "prompt": prompt,
        "n": image_count,
        "size": normalized_size,
        "quality": normalized_quality,
        "response_format": normalized_response_format,
    }
    safe_value = _optional_bool(safe)
    if safe_value is not None:
        payload["safe"] = safe_value

    headers = {"Content-Type": "application/json"}
    token = str(api_key or "").strip()
    if token:
        headers["Authorization"] = f"Bearer {token}"

    response = requests.post(
        build_images_url(base_url),
        headers=headers,
        json=payload,
        timeout=timeout_seconds,
    )
    response.raise_for_status()
    response_json = response.json()
    data_items = get_field(response_json, "data", []) or []
    if not isinstance(data_items, list):
        data_items = []

    saved_images: List[str] = []
    for index, item in enumerate(data_items, start=1):
        b64_json = get_field(item, "b64_json", "")
        if b64_json:
            saved_images.append(
                _save_base64_image(
                    b64_json,
                    Path(output_path),
                    stem=f"pollinations_{model_id.replace('-', '_')}",
                    index=index,
                    total=len(data_items),
                )
            )
            continue
        image_url = get_field(item, "url", "")
        if image_url:
            saved_images.append(
                _save_url_image(
                    image_url,
                    Path(output_path),
                    stem=f"pollinations_{model_id.replace('-', '_')}",
                    index=index,
                    total=len(data_items),
                )
            )

    return {
        "model": model_id,
        "display_name": display_name,
        "saved_images": saved_images,
        "text_parts": [],
        "request": {
            "n": image_count,
            "size": normalized_size,
            "quality": normalized_quality,
            "response_format": normalized_response_format,
            "safe": safe_value,
        },
    }
