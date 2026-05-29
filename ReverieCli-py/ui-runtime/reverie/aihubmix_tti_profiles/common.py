"""Shared helpers for AIhubMix image generation profiles."""

from __future__ import annotations

import base64
import time
from pathlib import Path
from typing import Any, Iterable, List
from urllib.request import Request, urlopen


def get_field(value: Any, key: str, default: Any = None) -> Any:
    """Read a dict key or object attribute."""
    if isinstance(value, dict):
        return value.get(key, default)
    return getattr(value, key, default)


def iter_response_data(response: Any) -> Iterable[Any]:
    data = get_field(response, "data", []) or []
    if isinstance(data, (list, tuple)):
        return data
    return []


def extension_for_mime(mime_type: Any) -> str:
    mime = str(mime_type or "").strip().lower()
    if mime in {"image/jpeg", "image/jpg"}:
        return ".jpg"
    if mime == "image/webp":
        return ".webp"
    return ".png"


def resolve_output_file(
    output_path: Path,
    *,
    stem: str,
    index: int,
    total: int,
    suffix: str = ".png",
) -> Path:
    output_path = Path(output_path)
    if output_path.suffix:
        if total <= 1:
            return output_path
        return output_path.with_name(f"{output_path.stem}_{index}{output_path.suffix}")
    timestamp = time.strftime("%Y%m%d_%H%M%S")
    filename = f"{stem}_{timestamp}{suffix}" if total <= 1 else f"{stem}_{timestamp}_{index}{suffix}"
    return output_path / filename


def save_base64_image(
    data: Any,
    output_path: Path,
    *,
    stem: str,
    index: int,
    total: int,
    mime_type: Any = "image/png",
) -> str:
    encoded = str(data or "").strip()
    if not encoded:
        raise ValueError("image response did not include base64 data")
    image_bytes = base64.b64decode(encoded)
    target = resolve_output_file(
        output_path,
        stem=stem,
        index=index,
        total=total,
        suffix=extension_for_mime(mime_type),
    )
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(image_bytes)
    return str(target)


def save_url_image(
    url: Any,
    output_path: Path,
    *,
    stem: str,
    index: int,
    total: int,
) -> str:
    image_url = str(url or "").strip()
    if not image_url:
        raise ValueError("image response did not include an image URL")
    request = Request(image_url, headers={"User-Agent": "ReverieCLI-AIhubMix-TTI/1.0"})
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


def first_non_empty_text(parts: Iterable[Any]) -> List[str]:
    texts: List[str] = []
    for part in parts:
        text = get_field(part, "text", "")
        if text:
            texts.append(str(text))
    return texts


def clamp_int(value: Any, *, default: int, minimum: int, maximum: int) -> int:
    try:
        number = int(value)
    except (TypeError, ValueError):
        number = default
    return max(minimum, min(maximum, number))


def normalize_choice(value: Any, allowed: set[str], default: str) -> str:
    candidate = str(value or "").strip().lower()
    return candidate if candidate in allowed else default
