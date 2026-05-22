"""TLS certificate bundle hygiene for packaged and embedded runtimes."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Dict


CA_BUNDLE_ENV_VARS = ("REQUESTS_CA_BUNDLE", "SSL_CERT_FILE", "CURL_CA_BUNDLE")


def _existing_file(path_value: str) -> bool:
    text = str(path_value or "").strip().strip('"')
    if not text:
        return False
    try:
        return Path(os.path.expandvars(os.path.expanduser(text))).is_file()
    except (OSError, ValueError):
        return False


def configure_tls_ca_bundle() -> Dict[str, str]:
    """Remove stale CA bundle paths that would break requests/httpx TLS setup.

    PyInstaller one-file apps extract dependencies under a temporary ``_MEI*``
    directory. If a host process leaks that path through CA bundle environment
    variables after the temp directory is removed, later Python HTTP clients fail
    before they can fall back to certifi. Valid user-provided bundle paths are
    preserved.
    """

    removed: Dict[str, str] = {}
    for name in CA_BUNDLE_ENV_VARS:
        value = os.environ.get(name)
        if value and not _existing_file(value):
            removed[name] = value
            os.environ.pop(name, None)

    return removed
