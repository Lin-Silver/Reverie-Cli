"""Build the same standalone Context Engine for CLI and desktop packages."""

import os
from pathlib import Path
import shutil
import subprocess


def prepare() -> Path:
    root = Path(__file__).resolve().parents[1]
    crate = root / "native" / "context-engine"
    target = root / "build" / "context-engine"
    cargo = shutil.which("cargo")
    if cargo is None:
        raise SystemExit("Cargo is required to package the Reverie Context Engine (Rust 1.89 or newer).")
    subprocess.run(
        [cargo, "build", "--release", "--locked", "--target-dir", str(target)],
        cwd=crate,
        check=True,
    )
    binary = target / "release" / ("reverie-context-engine.exe" if os.name == "nt" else "reverie-context-engine")
    if not binary.is_file():
        raise SystemExit(f"Context Engine build did not produce {binary}")
    return binary


if __name__ == "__main__":
    print(prepare())
