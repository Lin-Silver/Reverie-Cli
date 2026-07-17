#!/usr/bin/env python3
"""Merge platform kernel records into one release verification manifest."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Iterable


PLATFORM_ORDER = {
    ("win32", "x64"): 0,
    ("linux", "x64"): 1,
    ("darwin", "arm64"): 2,
    ("darwin", "x64"): 3,
}


def merge_manifests(paths: Iterable[Path]) -> dict[str, Any]:
    records: list[dict[str, Any]] = []
    for path in paths:
        payload = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(payload, dict):
            raise ValueError(f"Invalid kernel release manifest: {path}")
        kernel = payload.get("kernel")
        if (
            payload.get("schema") != "reverie.kernel.release.v1"
            or not isinstance(kernel, dict)
            or kernel.get("schema") != "reverie.kernel.v1"
            or kernel.get("bridge_protocol") != "sdk-bridge.v1"
            or kernel.get("frozen") is not True
            or len(str(payload.get("sha256", ""))) != 64
        ):
            raise ValueError(f"Invalid kernel release manifest: {path}")
        records.append(payload)

    if len(records) != len(PLATFORM_ORDER):
        raise ValueError(f"Expected {len(PLATFORM_ORDER)} platform manifests, found {len(records)}")

    platforms = {(record["kernel"]["platform"], record["kernel"]["arch"]) for record in records}
    if platforms != set(PLATFORM_ORDER):
        raise ValueError(f"Unexpected platform set: {sorted(platforms)}")

    commits = {str(record.get("commit", "")) for record in records}
    versions = {str(record["kernel"].get("version", "")) for record in records}
    asset_names = {str(record.get("asset_name", "")) for record in records}
    if len(commits) != 1 or "" in commits:
        raise ValueError("Kernel manifests do not share one non-empty commit")
    if len(versions) != 1 or "" in versions:
        raise ValueError("Kernel manifests do not share one non-empty version")
    if len(asset_names) != len(records) or "" in asset_names:
        raise ValueError("Kernel manifest asset names must be non-empty and unique")

    records.sort(key=lambda record: PLATFORM_ORDER[(record["kernel"]["platform"], record["kernel"]["arch"])])
    return {
        "schema": "reverie.kernels.release.v1",
        "version": next(iter(versions)),
        "commit": next(iter(commits)),
        "assets": [
            {
                "asset_name": record["asset_name"],
                "sha256": record["sha256"],
                "size": record["size"],
                "kernel": record["kernel"],
            }
            for record in records
        ],
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("manifests", nargs="+")
    parser.add_argument("--output", required=True)
    args = parser.parse_args()

    output = Path(args.output).resolve()
    payload = merge_manifests(Path(value).resolve() for value in args.manifests)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
