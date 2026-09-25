"""Shared helpers for SenseNova image generation and editing profiles.

SenseNova's image API is OpenAI-shaped but carries fields the OpenAI SDK cannot
express (``watermark``, ``prompt_extend``) and a distinct editing endpoint that
takes reference images inline as ``images: [{"image_url": ...}]`` rather than the
SDK's multipart upload. Both reasons make a small raw-HTTP client the right tool,
so every SenseNova image profile funnels through the two functions below.

Confirmed contract:

* Text-to-image: ``POST {base}/images/generations`` with
  ``{model, prompt, n, size, output_format, response_format, watermark, prompt_extend}``.
* Image editing: ``POST {base}/images/edits`` with
  ``{model, prompt, images: [{image_url}], n, size, response_format, watermark, prompt_extend}``.
* Auth: ``Authorization: Bearer {api_key}``; JSON in, JSON out.
* Response: ``data[0].b64_json`` (or ``data[0].url``).
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Optional

import requests

from ..aihubmix_tti_profiles.common import (
    get_field,
    save_base64_image,
    save_url_image,
)


SUPPORTED_RESPONSE_FORMATS = {"b64_json", "url"}
SUPPORTED_OUTPUT_FORMATS = {"png", "jpeg", "webp"}
DEFAULT_OUTPUT_FORMAT = "png"
DEFAULT_RESPONSE_FORMAT = "url"


def build_metadata(
    *,
    model_id: str,
    display_name: str,
    description: str,
    supported_sizes: List[str],
    supports_edit: bool,
    default_size: str,
) -> Dict[str, Any]:
    input_modalities = ["text", "image"] if supports_edit else ["text"]
    return {
        "id": model_id,
        "display_name": display_name,
        "description": description,
        "api": "v1.images.generations",
        "source": "sensenova",
        "input_modalities": input_modalities,
        "output_modalities": ["image"],
        "requires_api_key": True,
        "supports_n": False,
        "supports_edit": bool(supports_edit),
        "supported_sizes": sorted(supported_sizes),
        "supported_output_formats": sorted(SUPPORTED_OUTPUT_FORMATS),
        "supported_response_formats": sorted(SUPPORTED_RESPONSE_FORMATS),
        "default_size": default_size,
    }


def normalize_size(
    value: Any,
    *,
    supported: Optional[set[str]] = None,
    default: str,
    permissive: bool = False,
) -> str:
    """Resolve a requested size against a profile's capabilities.

    ``auto`` passes through so SenseNova chooses the output dimensions. Permissive
    profiles accept any ``WIDTHxHEIGHT`` string; restricted
    ones only accept sizes they advertise and otherwise fall back to ``default``.
    """
    candidate = str(value or "").strip().lower()
    if not candidate:
        return default
    if candidate == "auto":
        return "auto"
    parts = candidate.split("x", 1)
    is_dimensions = len(parts) == 2 and all(part.isdigit() and int(part) > 0 for part in parts)
    if not is_dimensions:
        return default
    if permissive:
        return candidate
    if supported and candidate in {str(item).lower() for item in supported}:
        return candidate
    return default


def _normalize_choice(value: Any, allowed: set[str], default: str) -> str:
    candidate = str(value or "").strip().lower()
    return candidate if candidate in allowed else default


def _as_bool(value: Any, default: bool) -> bool:
    if isinstance(value, bool):
        return value
    if value is None:
        return default
    text = str(value).strip().lower()
    if text in {"true", "1", "yes", "on"}:
        return True
    if text in {"false", "0", "no", "off"}:
        return False
    return default


def _collect_response_items(response_json: Any) -> List[Any]:
    if isinstance(response_json, dict):
        data = response_json.get("data")
        if isinstance(data, list):
            return data
        if isinstance(data, dict):
            return [data]
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
    for key in ("b64_json", "base64", "image_base64"):
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


def _headers(api_key: Any) -> Dict[str, str]:
    headers = {
        "Content-Type": "application/json",
        "Accept": "application/json",
        "User-Agent": "ReverieCLI-SenseNova-TTI/1.0",
    }
    token = str(api_key or "").strip()
    if token:
        headers["Authorization"] = f"Bearer {token}"
    return headers


def _build_images_url(base_url: Any, endpoint: str) -> str:
    base = str(base_url or "").strip().rstrip("/")
    return f"{base}/{endpoint.lstrip('/')}"


def run_sensenova_image(
    *,
    model_id: str,
    display_name: str,
    prompt: str,
    output_path: Path,
    base_url: Any,
    api_key: Any = "",
    timeout: Any = 300,
    size: Any = "",
    supported_sizes: Optional[set[str]] = None,
    default_size: str,
    permissive_size: bool = False,
    supports_edit: bool = False,
    reference_images: Optional[List[str]] = None,
    n: Any = 1,
    output_format: Any = DEFAULT_OUTPUT_FORMAT,
    response_format: Any = DEFAULT_RESPONSE_FORMAT,
    watermark: Any = False,
    prompt_extend: Any = True,
    **_: Any,
) -> Dict[str, Any]:
    """Generate or edit an image against SenseNova's HTTP image API.

    When ``reference_images`` are supplied the request routes to the editing
    endpoint (which requires an edit-capable model); otherwise it is a plain
    text-to-image generation.
    """
    references = [str(url).strip() for url in (reference_images or []) if str(url).strip()]
    is_edit = bool(references)
    if is_edit and not supports_edit:
        raise ValueError(
            f"SenseNova model '{model_id}' does not support image editing; "
            "use sensenova-u1.5-lite or omit reference images."
        )

    normalized_output_format = _normalize_choice(output_format, SUPPORTED_OUTPUT_FORMATS, DEFAULT_OUTPUT_FORMAT)
    normalized_response_format = _normalize_choice(response_format, SUPPORTED_RESPONSE_FORMATS, DEFAULT_RESPONSE_FORMAT)
    # Let the provider choose edit dimensions unless the caller overrides them.
    effective_default = "auto" if is_edit else default_size
    normalized_size = normalize_size(
        size,
        supported=supported_sizes,
        default=effective_default,
        permissive=permissive_size or is_edit,
    )
    try:
        timeout_seconds = max(1, int(timeout or 300))
    except (TypeError, ValueError):
        timeout_seconds = 300

    payload: Dict[str, Any] = {
        "model": model_id,
        "prompt": prompt,
        "n": 1,
        "size": normalized_size,
        "response_format": normalized_response_format,
        "watermark": _as_bool(watermark, False),
        "prompt_extend": _as_bool(prompt_extend, True),
    }
    if is_edit:
        payload["images"] = [{"image_url": url} for url in references]
        endpoint = "images/edits"
    else:
        payload["output_format"] = normalized_output_format
        endpoint = "images/generations"

    response = requests.post(
        _build_images_url(base_url, endpoint),
        headers=_headers(api_key),
        json=payload,
        timeout=timeout_seconds,
    )
    response.raise_for_status()
    response_json = response.json()
    data_items = _collect_response_items(response_json)

    mime_type = f"image/{'jpeg' if normalized_output_format == 'jpeg' else normalized_output_format}"
    stem = f"sensenova_{model_id.replace('-', '_').replace('.', '_')}"
    if is_edit:
        stem += "_edit"
    saved_images: List[str] = []
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
                    mime_type=mime_type,
                )
            )
            continue
        image_url = _extract_url(item)
        if image_url:
            saved_images.append(
                save_url_image(image_url, Path(output_path), stem=stem, index=index, total=total)
            )

    return {
        "model": model_id,
        "display_name": display_name,
        "saved_images": saved_images,
        "text_parts": [],
        "request": {
            "mode": "edit" if is_edit else "generate",
            "n": 1,
            "size": normalized_size,
            "output_format": normalized_output_format,
            "response_format": normalized_response_format,
            "watermark": payload["watermark"],
            "prompt_extend": payload["prompt_extend"],
            "reference_count": len(references),
        },
    }
