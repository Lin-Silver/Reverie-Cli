"""Process-wide diagnostic switches shared by the CLI, prompt mode, and bridge.

Debug mode only widens what Reverie is willing to print: raw stream markers,
unrecognized protocol frames, and other internals that are noise during normal
use but the first thing worth seeing when a provider misbehaves.  It never
changes what is sent to a provider or written to disk.
"""

from __future__ import annotations

import os
from typing import Optional


DEBUG_ENV_VAR = "REVERIE_DEBUG"

_TRUE_VALUES = {"1", "true", "yes", "on", "debug", "verbose"}
_FALSE_VALUES = {"0", "false", "no", "off", ""}

_debug_override: Optional[bool] = None


def set_debug_mode(enabled: Optional[bool]) -> None:
    """Turn debug output on or off for this process.

    Passing ``None`` clears the override so the environment decides again.
    """
    global _debug_override
    _debug_override = None if enabled is None else bool(enabled)


def debug_mode_enabled() -> bool:
    """Whether debug output is currently allowed.

    An explicit ``--debug``/``set_debug_mode`` call wins; otherwise the
    ``REVERIE_DEBUG`` environment variable decides.
    """
    if _debug_override is not None:
        return _debug_override
    value = str(os.getenv(DEBUG_ENV_VAR, "") or "").strip().lower()
    if value in _TRUE_VALUES:
        return True
    if value in _FALSE_VALUES:
        return False
    # Any other non-empty value is treated as opt-in, matching how shells are
    # commonly used (``REVERIE_DEBUG=stream reverie``).
    return True
