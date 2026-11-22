from __future__ import annotations

import hashlib
import json
from pathlib import Path
import subprocess
import sys

import pytest


SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
SOURCE = "a" * 40


def _staging(directory: Path) -> None:
    programs = ["reverie.exe", "Reverie-Setup-2.5.5-x64.exe", "Reverie-Portable-2.5.5-x64.exe",
                "reverie", "Reverie-2.5.5-linux-x64.AppImage", "Reverie-2.5.5-linux-x64.deb",
                "Reverie-CLI-macOS-Apple-Silicon", "Reverie-2.5.5-macOS-Apple-Silicon.dmg",
                "Reverie-CLI-macOS-Intel", "Reverie-2.5.5-macOS-Intel.dmg"]
    for name in programs:
        (directory / name).write_bytes(("test payload " + name).encode())
    for suffix, system, architecture, asset in (
        ("windows-x64", "win32", "x64", "reverie.exe"),
        ("linux-x64", "linux", "x64", "reverie"),
        ("macos-arm64", "darwin", "arm64", "Reverie-CLI-macOS-Apple-Silicon"),
        ("macos-x64", "darwin", "x64", "Reverie-CLI-macOS-Intel"),
    ):
        data = (directory / asset).read_bytes()
        record = {"schema": "reverie.kernel.release.v1", "asset_name": asset, "commit": SOURCE,
                  "sha256": hashlib.sha256(data).hexdigest(), "size": len(data),
                  "kernel": {"schema": "reverie.kernel.v1", "bridge_protocol": "sdk-bridge.v1",
                             "version": "2.5.5", "platform": system, "arch": architecture, "frozen": True,
                             "context_engine": {"backend": "python", "execution": "in-process"}}}
        (directory / f"reverie-kernel-{suffix}.json").write_text(json.dumps(record), encoding="utf-8")
    _consolidate(directory)


def _consolidate(directory: Path) -> None:
    subprocess.run([sys.executable, str(SCRIPTS / "merge_kernel_manifests.py"),
                    *(str(path) for path in directory.glob("reverie-kernel-*.json")),
                    "--output", str(directory / "reverie-kernels.json")], check=True, capture_output=True)


def _write(directory: Path, *, commit=SOURCE, tag="v2.5.5") -> subprocess.CompletedProcess:
    return subprocess.run([sys.executable, str(SCRIPTS / "write_release_manifest.py"), str(directory),
                           "--version", "2.5.5", "--commit", commit, "--tag", tag],
                          capture_output=True, text=True, encoding="utf-8", timeout=20)


@pytest.mark.parametrize("tag", ["v2.5.5", "latest"])
def test_complete_release_metadata_matches_actual_bytes(tmp_path: Path, tag: str) -> None:
    _staging(tmp_path)
    result = _write(tmp_path, tag=tag)
    assert result.returncode == 0, result.stderr
    manifest = json.loads((tmp_path / "reverie-release-assets.json").read_text(encoding="utf-8"))
    assert manifest["commit"] == SOURCE and manifest["tag"] == tag
    assert manifest["context_engine"] == {"backend": "python", "execution": "in-process"}
    assert len(manifest["assets"]) == 15 and len(list(tmp_path.iterdir())) == 17
    for asset in manifest["assets"]:
        data = (tmp_path / asset["name"]).read_bytes()
        assert len(data) == asset["bytes"] and hashlib.sha256(data).hexdigest() == asset["sha256"]
    checksums = (tmp_path / "SHA256SUMS").read_text(encoding="utf-8").splitlines()
    assert len(checksums) == 16
    for line in checksums:
        expected, name = line.split("  ", 1)
        assert hashlib.sha256((tmp_path / name).read_bytes()).hexdigest() == expected


@pytest.mark.parametrize("failure", ["content", "missing", "extra", "source", "tag", "backend", "consolidated"])
def test_invalid_release_candidate_creates_no_public_metadata(tmp_path: Path, failure: str) -> None:
    _staging(tmp_path)
    if failure == "content":
        (tmp_path / "reverie.exe").write_bytes(b"replaced after kernel verification")
    elif failure == "missing":
        (tmp_path / "Reverie-Portable-2.5.5-x64.exe").unlink()
    elif failure == "extra":
        (tmp_path / "unexpected-program.exe").write_bytes(b"unverified")
    elif failure == "backend":
        path = tmp_path / "reverie-kernel-windows-x64.json"
        record = json.loads(path.read_text())
        record["kernel"]["context_engine"] = {"backend": "rust", "execution": "worker"}
        path.write_text(json.dumps(record), encoding="utf-8")
        _consolidate(tmp_path)
    elif failure == "consolidated":
        (tmp_path / "reverie-kernels.json").write_text("{}", encoding="utf-8")
    result = _write(tmp_path, commit="b" * 40 if failure == "source" else SOURCE,
                    tag="v3.0.0" if failure == "tag" else "v2.5.5")
    assert result.returncode == 1 and "Release metadata:" in result.stderr
    assert not (tmp_path / "reverie-release-assets.json").exists()
    assert not (tmp_path / "SHA256SUMS").exists()
