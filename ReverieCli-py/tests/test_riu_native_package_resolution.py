import importlib.util
import json
from pathlib import Path
import plistlib
import subprocess

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


@pytest.mark.parametrize("trace_input", [False, True])
@pytest.mark.parametrize("failed_input", [False, True])
def test_native_input_trace_only_profiles_original_p4_and_preserves_failure(tmp_path, verifier, monkeypatch, trace_input, failed_input):
    monkeypatch.setattr(verifier, "ROOT", tmp_path)
    exe = tmp_path / "ReverieUI"
    exe.write_bytes(b"fixture package locator only")
    monkeypatch.setattr(verifier, "package_executable", lambda package: exe)
    output = tmp_path / ".runtime/native"
    monkeypatch.setattr(verifier.sys, "argv", ["native", "--package", str(tmp_path), "--sdk-root", str(tmp_path), "--output", str(output), *(["--trace-input"] if trace_input else [])])
    calls = []

    def run(command, **kwargs):
        calls.append(command)
        if "--riu-isolation-probe" in command:
            (output / "isolation.json").write_text(json.dumps({"checks": [{"passed": True}]}))
        failed = failed_input and any(str(arg).endswith("riu_p4_electron.py") for arg in command)
        return subprocess.CompletedProcess(command, int(failed))

    monkeypatch.setattr(verifier.subprocess, "run", run)
    assert verifier.main() == (2 if failed_input else 0)
    p4, = [command for command in calls if any(str(arg).endswith("riu_p4_electron.py") for arg in command)]
    assert ("--trace-input" in p4) == trace_input
    assert not any("--trace-input" in command for command in calls if command is not p4)
    report = json.loads((output / "report.json").read_text())
    assert report["passed"] is not failed_input
    assert next(stage for stage in report["stages"] if stage["name"] == "p4")["exit_code"] == int(failed_input)
