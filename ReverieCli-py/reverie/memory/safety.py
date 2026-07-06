"""Safety helpers for durable project memory."""

from __future__ import annotations

import re
from typing import Any


_SECRET_PATTERNS = (
    re.compile(r"(?i)\b(sk-[A-Za-z0-9_\-]{16,})\b"),
    re.compile(r"(?i)\b(ms-[A-Za-z0-9_\-]{16,})\b"),
    re.compile(r"(?i)\b(nvapi-[A-Za-z0-9_\-]{16,})\b"),
    re.compile(r"(?i)\b(gh[pousr]_[A-Za-z0-9_]{20,})\b"),
    re.compile(r"(?i)\b(bearer\s+)[A-Za-z0-9._\-]{12,}"),
    re.compile(r"(?i)\b(api[_-]?key|access[_-]?token|token|secret|password)\s*[:=]\s*['\"]?[^'\"\s,;]{8,}"),
)


def redact_memory_text(value: Any) -> str:
    """Remove common credentials and user-home identifiers before persistence."""
    safe = str(value or "")
    for pattern in _SECRET_PATTERNS:
        safe = pattern.sub(_replacement, safe)
    safe = re.sub(r"(?i)\b([A-Z]:\\Users\\)[^\\\s]+", r"\1[USER]", safe)
    safe = re.sub(r"(?i)\b(/home/)[^/\s]+", r"\1[USER]", safe)
    safe = re.sub(r"(?i)\b(/Users/)[^/\s]+", r"\1[USER]", safe)
    return safe


def _replacement(match: re.Match[str]) -> str:
    text = match.group(0)
    lowered = text.lower()
    if lowered.startswith("bearer "):
        return text[:7] + "[REDACTED]"
    if re.match(r"(?i)^(api[_-]?key|access[_-]?token|token|secret|password)", text):
        key = text.split("=", 1)[0].split(":", 1)[0]
        separator = "=" if "=" in text else ":"
        return f"{key}{separator}[REDACTED]"
    return "[REDACTED_SECRET]"


__all__ = ["redact_memory_text"]
