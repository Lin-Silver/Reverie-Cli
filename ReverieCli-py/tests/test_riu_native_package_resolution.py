import importlib.util
from pathlib import Path
import plistlib

import pytest


@pytest.fixture
def verifier(monkeypatch):
    path = Path(__file__).resolve().parents[2] / "scripts/verification/riu_package_native.py"
    spec = importlib.util.spec_from_file_location("riu_package_native", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    monkeypatch.setattr(module.sys, "platform", "darwin")
    return module


def test_native_macos_package_uses_actual_bundle_and_executable_name(tmp_path, verifier):
    bundle = tmp_path / "ReverieUI.app"
    (bundle / "Contents/MacOS").mkdir(parents=True)
    with (bundle / "Contents/Info.plist").open("wb") as stream:
        plistlib.dump({"CFBundleExecutable": "ReverieUI"}, stream)
    expected = bundle / "Contents/MacOS/ReverieUI"
    assert verifier.package_executable(tmp_path) == expected
    assert verifier.package_executable(bundle) == expected


def test_native_macos_package_rejects_missing_or_ambiguous_bundles(tmp_path, verifier):
    with pytest.raises(ValueError, match="found 0"):
        verifier.package_executable(tmp_path)
    (tmp_path / "First.app").mkdir()
    (tmp_path / "Second.app").mkdir()
    with pytest.raises(ValueError, match="found 2"):
        verifier.package_executable(tmp_path)
