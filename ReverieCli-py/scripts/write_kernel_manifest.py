#!/usr/bin/env python3
"""Write a verified SHA-256 release record for a compiled Reverie kernel."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--executable", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--asset-name", required=True)
    args = parser.parse_args()

    executable = Path(args.executable).resolve()
    if not executable.is_file():
        raise SystemExit(f"Kernel executable not found: {executable}")
    completed = subprocess.run(
        [str(executable), "--kernel-info"],
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=30,
    )
    info = json.loads(completed.stdout)
    if info.get("schema") != "reverie.kernel.v1" or info.get("bridge_protocol") != "sdk-bridge.v1":
        raise SystemExit("Compiled kernel returned an incompatible --kernel-info record")

    digest = hashlib.sha256()
    with executable.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)

    payload = {
        "schema": "reverie.kernel.release.v1",
        "asset_name": args.asset_name,
        "sha256": digest.hexdigest(),
        "size": executable.stat().st_size,
        "commit": os.environ.get("GITHUB_SHA", ""),
        "kernel": info,
    }
    output = Path(args.output).resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
