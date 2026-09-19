"""Stable request identification for Reverie-owned model API traffic."""

from __future__ import annotations

from typing import Dict, Mapping, Optional

from .version import __version__


REVERIE_CLIENT_HEADER = "X-Reverie-Client"
REVERIE_CLIENT_IDENTITY = f"Reverie-Cli/{__version__}"


def apply_reverie_client_identity(
    headers: Optional[Mapping[str, object]] = None,
    *,
    include_identity: bool = True,
) -> Dict[str, str]:
    """Return request headers carrying Reverie's non-overridable client identity.

    Set ``include_identity=False`` to strip Reverie's own client header instead of
    stamping it. That path exists only for the built-in OpenCode source, whose
    reverse proxy expects requests to look like the official OpenCode client;
    leaking ``X-Reverie-Client`` there would defeat the client-identity spoofing.
    Every other provider keeps Reverie's real identity.
    """
    normalized: Dict[str, str] = {}
    for key, value in (headers or {}).items():
        name = str(key or "").strip()
        text = str(value or "").strip()
        if name and text and name.lower() != REVERIE_CLIENT_HEADER.lower():
            normalized[name] = text
    if include_identity:
        normalized[REVERIE_CLIENT_HEADER] = REVERIE_CLIENT_IDENTITY
    return normalized
