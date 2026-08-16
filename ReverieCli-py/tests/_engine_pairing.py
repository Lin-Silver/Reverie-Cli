"""Locate the paired Reverie Engine editor binary for real RTP pairing tests.

Reverie-Cli and Reverie Engine are separate local repositories, so the tests that
exercise a genuine RTP session need the Engine executable. Gating those tests
behind an environment variable alone made them skip silently on every ordinary
run, which let an Engine tool-contract change (synchronous to bounded async cell
streaming, `reverie.world-streaming/1` to `/2`) drift undetected for a whole
development cycle.

Discovery therefore falls back to the sibling Engine worktree: an explicit
`REVERIE_RATS_ENGINE_BIN` still wins for out-of-tree builds, but a normal
checkout runs the pairing tests by default so contract drift turns the suite red.
"""

from __future__ import annotations

import os
from pathlib import Path

ENGINE_BIN_ENV = "REVERIE_RATS_ENGINE_BIN"

# The provider executable RATS validates. The `.console.exe` wrapper launches it
# but is not itself the process the descriptor identifies.
ENGINE_BINARY_NAME = "reverie.windows.editor.x86_64.exe"
_CONSOLE_SUFFIX = ".console.exe"

# Checked under each ancestor of this repository, nearest first.
_SIBLING_BIN_DIRS = (
    Path("Reverie Engine") / "Reverie Engine" / "bin",
    Path("Reverie Engine") / "bin",
)


def _provider_binary(binary: Path) -> Path:
    """Map a console wrapper onto the provider executable beside it."""
    if binary.name.lower().endswith(_CONSOLE_SUFFIX):
        provider = binary.with_name(binary.name[: -len(_CONSOLE_SUFFIX)] + ".exe")
        if provider.is_file():
            return provider
    return binary


def discover_engine_binary() -> Path | None:
    """Return the Engine editor binary to pair with, or None when unavailable."""
    override = str(os.environ.get(ENGINE_BIN_ENV, "")).strip()
    if override:
        return _provider_binary(Path(override).expanduser().resolve())
    for ancestor in Path(__file__).resolve().parents:
        for relative in _SIBLING_BIN_DIRS:
            candidate = ancestor / relative / ENGINE_BINARY_NAME
            if candidate.is_file():
                return candidate
    return None


def engine_pairing_skip_reason() -> str:
    """Explain how to supply an Engine binary when discovery found none."""
    return (
        "No Reverie Engine editor binary was discovered beside this repository; "
        f"build one or set {ENGINE_BIN_ENV} to run the real Engine/Cli RTP pairing."
    )
