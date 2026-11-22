#!/usr/bin/env python3
"""Bind the complete Python release set to its verified kernel records and digests."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re

from merge_kernel_manifests import merge_manifests


PLATFORMS = {
    "windows-x64": ("win32", "x64", "reverie.exe"),
    "linux-x64": ("linux", "x64", "reverie"),
    "macos-arm64": ("darwin", "arm64", "Reverie-CLI-macOS-Apple-Silicon"),
    "macos-x64": ("darwin", "x64", "Reverie-CLI-macOS-Intel"),
}


def digest(path: Path) -> str:
    checksum = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            checksum.update(block)
    return checksum.hexdigest()


def write_release_metadata(directory: Path, version: str, commit: str, tag: str) -> None:
    directory = directory.resolve()
    if not re.fullmatch(r"(?:0|[1-9][0-9]*)\.(?:0|[1-9][0-9]*)\.(?:0|[1-9][0-9]*)", version):
        raise ValueError("Invalid release version")
    if not re.fullmatch(r"[0-9a-f]{40}", commit) or tag not in {"latest", "v" + version}:
        raise ValueError("Invalid release source or tag")
    files = {
        "reverie.exe": "windows-x64",
        f"Reverie-Setup-{version}-x64.exe": "windows-x64",
        f"Reverie-Portable-{version}-x64.exe": "windows-x64",
        "reverie": "linux-x64",
        f"Reverie-{version}-linux-x64.AppImage": "linux-x64",
        f"Reverie-{version}-linux-x64.deb": "linux-x64",
        "Reverie-CLI-macOS-Apple-Silicon": "macos-arm64",
        f"Reverie-{version}-macOS-Apple-Silicon.dmg": "macos-arm64",
        "Reverie-CLI-macOS-Intel": "macos-x64",
        f"Reverie-{version}-macOS-Intel.dmg": "macos-x64",
        **{f"reverie-kernel-{platform}.json": platform for platform in PLATFORMS},
        "reverie-kernels.json": "all",
    }
    outputs = {"reverie-release-assets.json", "SHA256SUMS"}
    if any(path.name not in files.keys() | outputs for path in directory.iterdir()):
        raise ValueError("Unexpected release asset")
    for name in files.keys() | outputs:
        path = directory / name
        if path.is_symlink() or path.resolve().parent != directory:
            raise ValueError(f"Release asset escaped staging: {name}")
        if name in files and (not path.is_file() or path.stat().st_size <= 0):
            raise ValueError(f"Missing or empty release asset: {name}")
    checksums = {name: digest(directory / name) for name in sorted(files)}
    manifests = [directory / f"reverie-kernel-{platform}.json" for platform in PLATFORMS]
    merged = merge_manifests(manifests)
    if merged["commit"] != commit or merged["version"] != version:
        raise ValueError("Release kernel source or version mismatch")
    if json.loads((directory / "reverie-kernels.json").read_text(encoding="utf-8")) != merged:
        raise ValueError("Consolidated kernel manifest mismatch")
    for platform, (system, architecture, asset) in PLATFORMS.items():
        record = json.loads((directory / f"reverie-kernel-{platform}.json").read_text(encoding="utf-8"))
        kernel = record["kernel"]
        if record["asset_name"] != asset or (kernel["platform"], kernel["arch"]) != (system, architecture):
            raise ValueError(f"Kernel platform identity mismatch: {platform}")
        if type(record["size"]) is not int or record["size"] != (directory / asset).stat().st_size or record["sha256"] != checksums[asset]:
            raise ValueError(f"Kernel content integrity mismatch: {asset}")
        if kernel.get("context_engine") != {"backend": "python", "execution": "in-process"}:
            raise ValueError(f"Kernel does not declare the final Python Context Engine: {asset}")
    payload = {
        "schema": "reverie.release.assets.v1", "version": version, "tag": tag, "commit": commit,
        "checksum_algorithm": "SHA-256", "context_engine": {"backend": "python", "execution": "in-process"},
        "assets": [{"name": name, "platform": files[name], "bytes": (directory / name).stat().st_size,
                    "sha256": checksums[name]} for name in sorted(files)],
        "metadata_scope": "Ten programs, four platform kernel records and the consolidated record. SHA256SUMS also covers this manifest. Functional and DPI acceptance have separate source-bound evidence.",
    }
    manifest = directory / "reverie-release-assets.json"
    manifest.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    checksums[manifest.name] = digest(manifest)
    (directory / "SHA256SUMS").write_text("".join(checksums[name] + "  " + name + "\n" for name in sorted(checksums)), encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("directory", type=Path)
    parser.add_argument("--version", required=True)
    parser.add_argument("--commit", required=True)
    parser.add_argument("--tag", required=True)
    arguments = parser.parse_args()
    try:
        write_release_metadata(arguments.directory, arguments.version, arguments.commit, arguments.tag)
    except (OSError, ValueError, KeyError, TypeError) as error:
        parser.exit(1, f"Release metadata: {error}\n")
    print(json.dumps({"commit": arguments.commit, "version": arguments.version, "asset_count": 17}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
