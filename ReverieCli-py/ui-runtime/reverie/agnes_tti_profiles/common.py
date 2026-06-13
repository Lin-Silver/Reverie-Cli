"""Shared helpers for Agnes image generation profiles."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Optional

import requests

from ..agnes import AGNES_DEFAULT_API_URL, resolve_agnes_sdk_base_url
from ..aihubmix_tti_profiles.common import clamp_int, get_field, normalize_choice, save_base64_image, save_url_image


SUPPORTED_QUALITIES = {"high", "medium", "low", "auto"}
SUPPORTED_RESPONSE_FORMATS = {"b64_json", "url"}
DEFAULT_SIZE = "1024x1024"


def normalize_agnes_image_base_url(base_url: Any) -> str:
    """Normalize Agnes base URL for /v1/images/generations."""
    return resolve_agnes_sdk_base_url(base_url or AGNES_DEFAULT_API_URL)


def build_images_url(base_url: Any) -> str:
    return f"{normalize_agnes_image_base_url(base_url)}/images/generations"


def normalize_size(value: Any, default: str = DEFAULT_SIZE) -> str:
    candidate = str(value or "").strip().lower()
    if not candidate:
        return default
    if candidate == "auto":
        return candidate
    parts = candidate.split("x", 1)
    if len(parts) == 2 and all(part.isdigit() and int(part) > 0 for part in parts):
        return candidate
    return default


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
        "source": "agnes",
        "input_modalities": input_modalities,
        "output_modalities": ["image"],
        "requires_api_key": True,
        "supports_n": True,
        "supported_qualities": sorted(SUPPORTED_QUALITIES),
        "supported_response_formats": sorted(SUPPORTED_RESPONSE_FORMATS),
        "default_size": DEFAULT_SIZE,
    }


def _collect_response_items(response_json: Any) -> List[Any]:
    if isinstance(response_json, dict):
        data = response_json.get("data")
        if isinstance(data, list):
            return data
        for key in ("images", "results", "output"):
            value = response_json.get(key)
            if isinstance(value, list):
                return value
            if isinstance(value, dict):
                return [value]
        return [response_json]
    if isinstance(response_json, list):
        return response_json
    return []


def _extract_b64(item: Any) -> str:
    for key in ("b64_json", "base64", "image_base64", "data"):
        value = get_field(item, key, "")
        if value:
            return str(value)
    return ""


def _extract_url(item: Any) -> str:
    for key in ("url", "image_url", "output_url"):
        value = get_field(item, key, "")
        if value:
            return str(value)
    nested = get_field(item, "image", None)
    if isinstance(nested, dict):
        return _extract_url(nested)
    return ""


def generate_agnes_image(
    *,
    model_id: str,
    display_name: str,
    prompt: str,
    output_path: Path,
    base_url: Any = AGNES_DEFAULT_API_URL,
    api_key: Any = "",
    timeout: Any = 300,
    n: Any = 1,
    size: Any = DEFAULT_SIZE,
    quality: Any = "auto",
    response_format: Any = "b64_json",
    seed: Any = None,
    extra_body: Optional[Dict[str, Any]] = None,
    **_: Any,
) -> Dict[str, Any]:
    image_count = clamp_int(n, default=1, minimum=1, maximum=10)
    normalized_size = normalize_size(size, DEFAULT_SIZE)
    normalized_quality = normalize_choice(quality, SUPPORTED_QUALITIES, "auto")
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
        "extra_body": {"response_format": normalized_response_format},
    }
    if isinstance(extra_body, dict):
        payload["extra_body"].update({k: v for k, v in extra_body.items() if v is not None})
    if seed is not None:
        try:
            payload["seed"] = int(seed)
        except (TypeError, ValueError):
            pass

    token = str(api_key or "").strip()
    headers = {
        "Content-Type": "application/json",
        "Accept": "application/json",
        "User-Agent": "ReverieCLI-Agnes-TTI/1.0",
    }
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
    data_items = _collect_response_items(response_json)

    saved_images: List[str] = []
    stem = f"agnes_{model_id.replace('-', '_')}"
    total = max(1, len(data_items))
    for index, item in enumerate(data_items, start=1):
        b64_json = _extract_b64(item)
        if b64_json:
            saved_images.append(
                save_base64_image(
                    b64_json,
                    Path(output_path),
                    stem=stem,
                    index=index,
                    total=total,
                )
            )
            continue
        image_url = _extract_url(item)
        if image_url:
            saved_images.append(
                save_url_image(
                    image_url,
                    Path(output_path),
                    stem=stem,
                    index=index,
                    total=total,
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
            "seed": payload.get("seed"),
        },
    }
