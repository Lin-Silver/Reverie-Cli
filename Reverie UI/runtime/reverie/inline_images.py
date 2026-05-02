"""Helpers for inline @image attachments in chat messages."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Callable, Dict, List, Tuple
import base64
import mimetypes
import re

from .security_utils import WorkspaceSecurityError, resolve_workspace_path


SUPPORTED_INLINE_IMAGE_EXTENSIONS = {
    ".png",
    ".jpg",
    ".jpeg",
    ".gif",
    ".bmp",
    ".webp",
    ".tiff",
    ".tif",
}
INLINE_IMAGE_TOKEN_ESTIMATE = 1024
INLINE_IMAGE_MENTION_PATTERN = re.compile(
    r'(?<!\S)@(?:"([^"]+)"|\'([^\']+)\'|([^\s]+))'
)


def _detect_image_mime_type(path: Path) -> str:
    mime_type, _ = mimetypes.guess_type(str(path))
    if mime_type:
        return mime_type
    suffix = path.suffix.lower()
    return {
        ".png": "image/png",
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
        ".gif": "image/gif",
        ".bmp": "image/bmp",
        ".webp": "image/webp",
        ".tiff": "image/tiff",
        ".tif": "image/tiff",
    }.get(suffix, "image/png")


def _is_supported_image_candidate(path_text: str) -> bool:
    return Path(str(path_text or "").strip()).suffix.lower() in SUPPORTED_INLINE_IMAGE_EXTENSIONS


def _estimate_inline_image_tokens(
    *,
    explicit_value: Any = None,
    size_bytes: Any = None,
) -> int:
    try:
        explicit = int(explicit_value)
    except (TypeError, ValueError):
        explicit = 0
    if explicit > 0:
        return explicit

    try:
        size_value = int(size_bytes)
    except (TypeError, ValueError):
        size_value = 0
    if size_value <= 0:
        return INLINE_IMAGE_TOKEN_ESTIMATE

    if size_value <= 256 * 1024:
        return INLINE_IMAGE_TOKEN_ESTIMATE
    if size_value <= 1024 * 1024:
        return 1536
    return 2048


def parse_inline_image_mentions(message_text: str, project_root: Path) -> Dict[str, Any]:
    """Extract valid `@image.ext` mentions from a user message."""
    raw_text = str(message_text or "")
    attachments: List[Dict[str, Any]] = []
    warnings: List[str] = []
    seen_paths = set()
    cursor = 0
    cleaned_parts: List[str] = []

    for match in INLINE_IMAGE_MENTION_PATTERN.finditer(raw_text):
        candidate = next((group for group in match.groups() if group), "")
        if not _is_supported_image_candidate(candidate):
            continue

        try:
            resolved = resolve_workspace_path(candidate, project_root, purpose="attach inline image")
        except WorkspaceSecurityError as exc:
            warnings.append(str(exc))
            continue

        if not resolved.exists():
            warnings.append(f"Inline image not found: {candidate}")
            continue
        if not resolved.is_file():
            warnings.append(f"Inline image path is not a file: {candidate}")
            continue
        if resolved.suffix.lower() not in SUPPORTED_INLINE_IMAGE_EXTENSIONS:
            warnings.append(f"Unsupported inline image format: {candidate}")
            continue

        cleaned_parts.append(raw_text[cursor:match.start()])
        cursor = match.end()

        normalized_key = str(resolved).lower()
        if normalized_key in seen_paths:
            continue
        seen_paths.add(normalized_key)

        attachments.append(
            {
                "type": "local_image",
                "file_path": str(resolved.relative_to(Path(project_root).resolve())),
                "file_name": resolved.name,
                "mime_type": _detect_image_mime_type(resolved),
                "file_size": resolved.stat().st_size,
                "token_estimate": _estimate_inline_image_tokens(size_bytes=resolved.stat().st_size),
            }
        )

    cleaned_parts.append(raw_text[cursor:])
    clean_text = "".join(cleaned_parts)
    clean_text = re.sub(r"[ \t]{2,}", " ", clean_text)
    clean_text = re.sub(r"[ \t]+\n", "\n", clean_text)
    clean_text = clean_text.strip()

    return {
        "clean_text": clean_text,
        "attachments": attachments,
        "warnings": warnings,
    }


def build_inline_image_notice(attachments: List[Dict[str, Any]]) -> str:
    """Build a compact text block describing attached local images."""
    if not attachments:
        return ""
    lines = ["Attached local image files:"]
    for item in attachments:
        file_name = str(item.get("file_name", "") or "").strip()
        file_path = str(item.get("file_path", "") or "").strip()
        label = file_name or file_path or "image"
        if file_path and file_path != label:
            lines.append(f"- {label} ({file_path})")
        else:
            lines.append(f"- {label}")
    return "\n".join(lines)


def build_user_message_content(clean_text: str, attachments: List[Dict[str, Any]]) -> Any:
    """Build chat content blocks that preserve inline image attachment metadata."""
    if not attachments:
        return str(clean_text or "")

    content: List[Dict[str, Any]] = []
    text_sections: List[str] = []
    stripped_text = str(clean_text or "").strip()
    if stripped_text:
        text_sections.append(stripped_text)
    notice = build_inline_image_notice(attachments)
    if notice:
        text_sections.append(notice)
    if text_sections:
        content.append({"type": "text", "text": "\n\n".join(text_sections).strip()})
    content.extend(dict(item) for item in attachments if isinstance(item, dict))
    return content


def resolve_inline_image_content_for_request(content: Any, project_root: Path) -> Any:
    """Resolve lightweight local-image markers into OpenAI-compatible image parts."""
    if not isinstance(content, list):
        return content

    resolved_parts: List[Dict[str, Any]] = []
    for part in content:
        if isinstance(part, str):
            if part:
                resolved_parts.append({"type": "text", "text": part})
            continue

        if not isinstance(part, dict):
            continue

        part_type = str(part.get("type", "") or "").strip().lower()
        if part_type in {"text", "input_text", "output_text"}:
            text_value = str(part.get("text", "") or "").strip()
            if text_value:
                resolved_parts.append({"type": "text", "text": text_value})
            continue

        if part_type != "local_image":
            resolved_parts.append(dict(part))
            continue

        file_path = part.get("file_path") or part.get("path") or ""
        resolved_path = resolve_workspace_path(file_path, project_root, purpose="attach inline image")
        image_bytes = resolved_path.read_bytes()
        mime_type = str(part.get("mime_type", "") or "").strip() or _detect_image_mime_type(resolved_path)
        base64_image = base64.b64encode(image_bytes).decode("utf-8")
        resolved_parts.append(
            {
                "type": "image_url",
                "image_url": {"url": f"data:{mime_type};base64,{base64_image}"},
            }
        )

    return resolved_parts


def count_multimodal_value_tokens(value: Any, count_text: Callable[[Any], int]) -> int:
    """Estimate tokens for multimodal values without exploding on base64 payloads."""
    if value is None:
        return 0
    if isinstance(value, str):
        return count_text(value)
    if isinstance(value, (int, float, bool)):
        return count_text(str(value))
    if isinstance(value, list):
        return sum(count_multimodal_value_tokens(item, count_text) for item in value)
    if isinstance(value, dict):
        part_type = str(value.get("type", "") or "").strip().lower()
        if part_type == "local_image":
            return _estimate_inline_image_tokens(
                explicit_value=value.get("token_estimate"),
                size_bytes=value.get("file_size"),
            )
        if part_type in {"image", "input_image"}:
            source = value.get("source") if isinstance(value.get("source"), dict) else {}
            data = str(source.get("data", "") or "").strip()
            return _estimate_inline_image_tokens(
                explicit_value=value.get("token_estimate"),
                size_bytes=max(0, int(len(data) * 3 / 4)) if data else value.get("file_size"),
            )
        if part_type == "image_url":
            image_payload = value.get("image_url")
            url = ""
            if isinstance(image_payload, dict):
                url = str(image_payload.get("url", "") or "").strip()
            elif image_payload is not None:
                url = str(image_payload).strip()
            if url.startswith("data:image/"):
                encoded = url.split(",", 1)[1] if "," in url else ""
                estimated_size = max(0, int(len(encoded) * 3 / 4)) if encoded else 0
                return _estimate_inline_image_tokens(size_bytes=estimated_size)
            return INLINE_IMAGE_TOKEN_ESTIMATE

        total = 0
        for key, item in value.items():
            if str(key) in {"reasoning_content", "thought_signature", "gemini_thought_signature"}:
                continue
            total += count_multimodal_value_tokens(item, count_text)
        return total
    return count_text(str(value))


def flatten_multimodal_content_for_display(value: Any) -> str:
    """Render multimodal history entries into readable transcript text."""
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    if isinstance(value, (int, float, bool)):
        return str(value)
    if isinstance(value, list):
        parts: List[str] = []
        for item in value:
            rendered = flatten_multimodal_content_for_display(item)
            if rendered:
                parts.append(rendered)
        return "\n".join(parts).strip()
    if isinstance(value, dict):
        part_type = str(value.get("type", "") or "").strip().lower()
        if part_type == "local_image":
            file_name = str(value.get("file_name", "") or "").strip()
            file_path = str(value.get("file_path", "") or "").strip()
            label = file_name or file_path or "image"
            if file_path and file_path != label:
                return f"[image] {label} ({file_path})"
            return f"[image] {label}"
        if part_type == "image_url":
            return "[image] inline image attachment"
        text_value = (
            value.get("text")
            or value.get("content")
            or value.get("output_text")
            or value.get("input_text")
            or value.get("value")
        )
        if text_value is not None:
            return flatten_multimodal_content_for_display(text_value)
        return ""
    return str(value)
