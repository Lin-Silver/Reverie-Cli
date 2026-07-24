"""Stable request identification for Reverie-owned model API traffic."""

from __future__ import annotations

from typing import Dict, Mapping, Optional

from .version import __version__


REVERIE_CLIENT_HEADER = "X-Reverie-Client"
REVERIE_CLIENT_IDENTITY = f"Reverie-Cli/{__version__}"


def apply_reverie_client_identity(headers: Optional[Mapping[str, object]] = None) -> Dict[str, str]:
    """Return request headers carrying Reverie's non-overridable client identity."""
    normalized: Dict[str, str] = {}
    for key, value in (headers or {}).items():
        name = str(key or "").strip()
        text = str(value or "").strip()
        if name and text and name.lower() != REVERIE_CLIENT_HEADER.lower():
            normalized[name] = text
    normalized[REVERIE_CLIENT_HEADER] = REVERIE_CLIENT_IDENTITY
    return normalized
