"""Validate explicit desktop inputs, recording the content version actually read."""
from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any
from .inline_images import SUPPORTED_INLINE_MEDIA_EXTENSIONS, build_user_message_content, parse_inline_media_mentions
from .security_utils import resolve_workspace_path


def prepare_desktop_input(interface: Any, config: Any, text: str, attachments: list[dict]) -> tuple[Any, list[dict]]:
    if not isinstance(attachments, list) or len(attachments) > 20:
        raise ValueError("Maximum 20 attachments per message.")
    records = []
    parts = []
    total = 0
    # Preserve the legacy inline visual syntax without duplicating explicit cards.
    legacy = parse_inline_media_mentions(text, interface.project_root, modalities=["image", "video"])
    if legacy.get("warnings"):
        raise ValueError("; ".join(legacy["warnings"]))
    visual = list(legacy.get("attachments") or [])
    clean_text = str(legacy.get("clean_text", text))
    ordered = build_user_message_content(clean_text, visual)
    ordered = ordered if isinstance(ordered, list) else ([{"type": "text", "text": ordered}] if ordered else [])
    seen = {str(item.get("file_path")) for item in visual}
    for item in attachments:
        if not isinstance(item, dict) or item.get("status", "ready") != "ready":
            raise ValueError("Resolve failed or unfinished attachments before sending.")
        requested = str(item.get("relativePath") or "")
        file = resolve_workspace_path(requested, interface.project_root, purpose="read desktop attachment")
        if not file.is_file():
            raise ValueError(f"Attachment is missing: {requested}")
        size = file.stat().st_size
        total += size
        if size > 50 * 1024 * 1024 or total > 200 * 1024 * 1024:
            raise ValueError("Attachment exceeds the 50 MiB file / 200 MiB total limit.")
        data = file.read_bytes()
        version = hashlib.sha256(data).hexdigest()
        if item.get("kind") == "copy" and item.get("version") and item["version"] != version:
            raise ValueError(f"Attachment copy changed; re-import it: {requested}")
        records.append({**item, "version": version, "size": size, "relativePath": str(file.relative_to(Path(interface.project_root).resolve()))})
        if file.suffix.lower() in SUPPORTED_INLINE_MEDIA_EXTENSIONS:
            if requested not in seen:
                parsed = parse_inline_media_mentions('@"' + requested + '"', interface.project_root, modalities=["image", "video"])
                visual.extend(parsed["attachments"])
                ordered.extend(build_user_message_content("", parsed["attachments"]))
                seen.add(requested)
        else:
            try:
                content = data.decode("utf-8-sig")
            except UnicodeDecodeError:
                raise ValueError(f"This binary format cannot be sent as text: {requested}. Use a supported image or a text file.")
            line = max(1, int(item.get("line") or 1))
            if item.get("line"):
                content = "\n".join(content.splitlines()[max(0, line - 4):line + 36])
            truncated = len(content) > 200_000
            parts.append(f"User attached: {requested} (SHA256 {version}, line {line})\n{content[:200_000]}" + ("\n[Content truncated at 200000 characters]" if truncated else ""))
            records[-1]["truncated"] = truncated
            ordered.append({"type": "text", "text": parts[-1]})
    if visual:
        allowed, reason = interface._can_attach_inline_images(config)
        if not allowed:
            raise ValueError(f"Visual input unavailable: {reason} Switch to a vision-capable model or remove the image.")
        modalities = interface._current_inline_media_modalities(config)
        if any(item.get("type") == "local_video" for item in visual) and "video" not in modalities:
            raise ValueError("The current model does not support video input.")
    combined = "\n\n".join([part for part in [clean_text, *parts] if part])
    return ordered if visual else combined, records
