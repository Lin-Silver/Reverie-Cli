"""Shared diagnostics for recoverable runtime failures."""

from __future__ import annotations

import logging
from typing import Optional


def report_suppressed_exception(
    operation: str,
    *,
    logger: Optional[logging.Logger] = None,
    level: int = logging.DEBUG,
) -> None:
    """Record the active exception when a best-effort operation must continue."""
    target = logger or logging.getLogger("reverie.recovery")
    target.log(level, "Recoverable operation failed: %s", operation, exc_info=True)
