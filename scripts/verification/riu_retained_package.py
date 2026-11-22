"""Validate retained macOS packages before diagnostic execution; never publish them."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import re


def retained_artifact(source: dict, arch: str) -> str:
    if source.get("status") != "completed" or arch not in {"arm64", "x64"}:
        raise ValueError("A completed native macOS run and supported architecture are required")
    sha = source.get("head_sha", "")
    if not re.fullmatch(r"[0-9a-f]{40}", sha):
        raise ValueError("Invalid source commit")
    if source.get("path") == ".github/workflows/verify-riu-packages.yml":
        return f"riu-validation-macos-{arch}-{sha}"
    if source.get("path") == ".github/workflows/build-core-release.yml":
        return f"failed-native-package-macos-{arch}-{sha}"
    raise ValueError("Unsupported retained-package workflow")


def file_digest(path: Path) -> str:
    checksum = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            checksum.update(chunk)
    return checksum.hexdigest()


def verify_retained_assets(root: Path, source: dict, arch: str) -> Path:
    retained_artifact(source, arch)
    core_release = source["path"] == ".github/workflows/build-core-release.yml"
    assets = root / "release-assets" if core_release else root
    manifest = json.loads((assets / f"reverie-kernel-macos-{arch}.json").read_text(encoding="utf-8"))
    if manifest.get("schema") != "reverie.kernel.release.v1" or manifest.get("commit") != source["head_sha"]:
        raise ValueError("Retained kernel manifest does not match its source")
    name = manifest["asset_name"]
    if Path(name).name != name or "\\" in name or not name:
        raise ValueError("Invalid retained kernel asset path")
    core = assets / name
    images = list(assets.glob("*.dmg"))
    if len(images) != 1:
        raise ValueError("Expected exactly one retained DMG")
    for path in (core, images[0]):
        if path.is_symlink() or path.resolve().parent != assets.resolve():
            raise ValueError("Retained asset escaped its directory")
    if core.stat().st_size != manifest["size"] or file_digest(core) != manifest["sha256"]:
        raise ValueError("Retained kernel content does not match its manifest")
    if manifest["kernel"].get("platform") != "darwin" or manifest["kernel"].get("arch") != arch:
        raise ValueError("Retained kernel platform or architecture does not match")
    if core_release:
        proof = json.loads((root / ".runtime/release-native-provenance.json").read_text(encoding="utf-8"))
        files = list(assets.iterdir())
        if proof.get("commit") != source["head_sha"] or any(not path.is_file() or path.is_symlink() for path in files):
            raise ValueError("Invalid retained release provenance")
        if {path.name: file_digest(path) for path in files} != proof["assets"]:
            raise ValueError("Retained release content does not match its provenance")
    return assets.resolve()
