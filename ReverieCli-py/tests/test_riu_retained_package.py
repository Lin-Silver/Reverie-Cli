from __future__ import annotations

import hashlib
import importlib.util
import json
from pathlib import Path

import pytest


@pytest.fixture
def verifier():
    path = Path(__file__).resolve().parents[2] / "scripts/verification/riu_retained_package.py"
    spec = importlib.util.spec_from_file_location("riu_retained_package", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def retained(tmp_path):
    source = {"status": "completed", "head_sha": "a" * 40, "path": ".github/workflows/build-core-release.yml"}
    assets = tmp_path / "release-assets"
    assets.mkdir()
    core = assets / "Reverie-CLI-macOS-Intel"
    core.write_bytes(b"retained kernel fixture")
    (assets / "Reverie-2.5.5-macOS-Intel.dmg").write_bytes(b"retained disk image fixture")
    manifest = {
        "schema": "reverie.kernel.release.v1", "commit": source["head_sha"],
        "asset_name": core.name, "size": core.stat().st_size,
        "sha256": hashlib.sha256(core.read_bytes()).hexdigest(),
        "kernel": {"platform": "darwin", "arch": "x64"},
    }
    (assets / "reverie-kernel-macos-x64.json").write_text(json.dumps(manifest), encoding="utf-8")
    (tmp_path / ".runtime").mkdir()
    proof = {"commit": source["head_sha"], "assets": {path.name: hashlib.sha256(path.read_bytes()).hexdigest() for path in assets.iterdir()}}
    (tmp_path / ".runtime/release-native-provenance.json").write_text(json.dumps(proof), encoding="utf-8")
    return tmp_path, source, assets


def test_exact_failed_release_can_be_diagnosed_without_rebuilding(verifier, retained):
    root, source, assets = retained
    assert verifier.retained_artifact(source, "x64") == "failed-native-package-macos-x64-" + source["head_sha"]
    assert verifier.verify_retained_assets(root, source, "x64") == assets.resolve()


@pytest.mark.parametrize("asset", ["Reverie-CLI-macOS-Intel", "Reverie-2.5.5-macOS-Intel.dmg", "reverie-kernel-macos-x64.json"])
def test_changed_retained_content_is_rejected_before_execution(verifier, retained, asset):
    root, source, assets = retained
    path = assets / asset
    path.write_bytes(path.read_bytes() + b" ")
    with pytest.raises(ValueError, match="content"):
        verifier.verify_retained_assets(root, source, "x64")


@pytest.mark.parametrize("change", [{"head_sha": "b" * 40}, {"status": "in_progress"}, {"path": ".github/workflows/test.yml"}, {"head_sha": "invalid"}])
def test_wrong_or_incomplete_source_is_rejected(verifier, retained, change):
    root, source, _ = retained
    with pytest.raises(ValueError):
        verifier.verify_retained_assets(root, {**source, **change}, "x64")


def test_missing_release_provenance_cannot_be_bypassed(verifier, retained):
    root, source, _ = retained
    (root / ".runtime/release-native-provenance.json").unlink()
    with pytest.raises(FileNotFoundError):
        verifier.verify_retained_assets(root, source, "x64")


def test_traversing_kernel_path_is_rejected(verifier, retained):
    root, source, assets = retained
    path = assets / "reverie-kernel-macos-x64.json"
    manifest = json.loads(path.read_text(encoding="utf-8"))
    manifest["asset_name"] = "../Reverie-CLI-macOS-Intel"
    path.write_text(json.dumps(manifest), encoding="utf-8")
    with pytest.raises(ValueError, match="path"):
        verifier.verify_retained_assets(root, source, "x64")


def test_existing_native_validation_artifact_remains_supported(verifier, tmp_path):
    source = {"status": "completed", "head_sha": "a" * 40, "path": ".github/workflows/verify-riu-packages.yml"}
    assert verifier.retained_artifact(source, "arm64") == "riu-validation-macos-arm64-" + source["head_sha"]
