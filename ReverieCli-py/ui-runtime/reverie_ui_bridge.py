"""Compatibility launcher for the Reverie JSONL SDK bridge."""

from __future__ import annotations

import sys
from pathlib import Path


RUNTIME_ROOT = Path(__file__).resolve().parent
if str(RUNTIME_ROOT) not in sys.path:
    sys.path.insert(0, str(RUNTIME_ROOT))

from reverie.sdk_bridge import main


if __name__ == "__main__":
    raise SystemExit(main())
