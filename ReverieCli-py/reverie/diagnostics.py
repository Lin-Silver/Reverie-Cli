"""Shared diagnostics for recoverable runtime failures."""

from __future__ import annotations

from collections import OrderedDict
from dataclasses import asdict, dataclass
import logging
import sys
import threading
import time
from typing import Any, Dict, List, Optional


@dataclass
class RecoveryDiagnostic:
    """A bounded, de-duplicated record of a best-effort failure."""

    operation: str
    exception_type: str
    message: str
    first_seen: float
    last_seen: float
    count: int = 1

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


_MAX_RECOVERY_DIAGNOSTICS = 128
_recovery_diagnostics: "OrderedDict[str, RecoveryDiagnostic]" = OrderedDict()
_recovery_diagnostics_lock = threading.Lock()


def _record_recovery_diagnostic(operation: str) -> RecoveryDiagnostic:
    _exception_type, exception, _traceback = sys.exc_info()
    exception_name = type(exception).__name__ if exception is not None else "UnknownError"
    message = str(exception).strip() if exception is not None else "No active exception"
    message = message[:500]
    operation = str(operation or "recoverable operation").strip()[:240]
    key = f"{operation}\0{exception_name}\0{message}"
    now = time.time()

    with _recovery_diagnostics_lock:
        event = _recovery_diagnostics.pop(key, None)
        if event is None:
            event = RecoveryDiagnostic(
                operation=operation,
                exception_type=exception_name,
                message=message,
                first_seen=now,
                last_seen=now,
            )
        else:
            event.last_seen = now
            event.count += 1
        _recovery_diagnostics[key] = event
        while len(_recovery_diagnostics) > _MAX_RECOVERY_DIAGNOSTICS:
            _recovery_diagnostics.popitem(last=False)
        return RecoveryDiagnostic(**event.to_dict())


def get_recent_recovery_diagnostics(limit: int = 50) -> List[Dict[str, Any]]:
    """Return the most recently observed recoverable failures."""
    safe_limit = max(0, min(_MAX_RECOVERY_DIAGNOSTICS, int(limit or 0)))
    with _recovery_diagnostics_lock:
        events = list(_recovery_diagnostics.values())[-safe_limit:] if safe_limit else []
        return [event.to_dict() for event in reversed(events)]


def clear_recovery_diagnostics() -> None:
    """Clear the process-local recovery diagnostic buffer."""
    with _recovery_diagnostics_lock:
        _recovery_diagnostics.clear()


def report_suppressed_exception(
    operation: str,
    *,
    logger: Optional[logging.Logger] = None,
    level: int = logging.DEBUG,
) -> None:
    """Record and log the active exception while a best-effort operation continues."""
    event = _record_recovery_diagnostic(operation)
    target = logger or logging.getLogger("reverie.recovery")
    target.log(
        level,
        "Recoverable operation failed: %s (%s; occurrences=%d)",
        event.operation,
        event.exception_type,
        event.count,
        exc_info=True,
        extra={"reverie_recovery_diagnostic": event.to_dict()},
    )
