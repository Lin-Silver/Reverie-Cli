"""Exercise packaging orchestration without compiling the application in unit tests."""

import json
import os
from pathlib import Path
import shutil
import subprocess
import sys

import pytest


REPOSITORY = Path(__file__).resolve().parents[2]
NODE = shutil.which("node")
pytestmark = pytest.mark.skipif(NODE is None, reason="Node.js is required")


@pytest.mark.parametrize("reuse_archives", [True, False])
def test_kernel_uses_python_module_and_reuses_resources(tmp_path, reuse_archives):
    # A moved checkout with spaces, no activation script and no PyInstaller launcher.
    root = tmp_path / "moved checkout"
    ui = root / "ReverieCli-ui"
    scripts = ui / "scripts"
    scripts.mkdir(parents=True)
    script = scripts / "build-kernel.mjs"
    shutil.copy2(REPOSITORY / "ReverieCli-ui/scripts/build-kernel.mjs", script)
    build = root / "ReverieCli-py/build"
    for name in ["venv/Scripts/python.exe", "../venv/bin/python",
                 "bundle_resources/comfy/generate_image.py",
                 "bundle_resources/browser/ms-playwright/chrome.exe"]:
        file = build / name
        file.parent.mkdir(parents=True, exist_ok=True)
        file.write_text("fixture")
    packed = build / "bundle_resources/packed"
    if reuse_archives:
        packed.mkdir()
        (packed / "browser.zip").write_bytes(b"browser archive")
        (packed / "ffmpeg.zip").write_bytes(b"ffmpeg archive")
    # Stub the expensive compiler subprocess, but execute all orchestration and
    # filesystem operations in the real script using Node's native module loader.
    preload = root / "compiler-stub.mjs"
    preload.write_text('''
import cp from "node:child_process";
import { syncBuiltinESMExports } from "node:module";
import { mkdirSync, writeFileSync } from "node:fs";
import path from "node:path";
const calls = [];
cp.spawnSync = (executable, args, options) => {
  calls.push({ executable, args });
  if (args[0] === "-m" && args[1] === "PyInstaller") {
    const output = path.join(args[args.indexOf("--distpath") + 1], "reverie");
    mkdirSync(path.join(output, "reverie-runtime"), { recursive: true });
    writeFileSync(path.join(output, process.platform === "win32" ? "reverie.exe" : "reverie"), "kernel");
  } else if (args[0].endsWith("pack_ui_resources.py")) {
    const output = args[args.indexOf("--output") + 1];
    mkdirSync(output, { recursive: true });
    writeFileSync(path.join(output, "browser.zip"), "fresh browser archive");
  } else {
    throw new Error("Unexpected subprocess: " + executable);
  }
  writeFileSync(new URL("./calls.json", import.meta.url), JSON.stringify(calls));
  return { status: 0 };
};
syncBuiltinESMExports();
''', encoding="utf-8")
    result = subprocess.run([NODE, "--import", preload.as_uri(), str(script)],
                            cwd=tmp_path, text=True, capture_output=True, timeout=30)
    assert result.returncode == 0, result.stderr
    calls = json.loads((root / "calls.json").read_text())
    assert Path(calls[0]["executable"]).name in {"python.exe", "python"}
    assert calls[0]["args"][:2] == ["-m", "PyInstaller"]
    resources = ui / ".kernel/reverie/reverie-runtime/reverie_resources"
    if reuse_archives:
        assert len(calls) == 1
        assert (resources / "browser.zip").read_bytes() == b"browser archive"
        assert (resources / "ffmpeg.zip").read_bytes() == b"ffmpeg archive"
        assert (packed / "browser.zip").exists()
    else:
        assert len(calls) == 2
        assert (resources / "browser.zip").read_text() == "fresh browser archive"
    assert (ui / "build/generated/reverie-trusted-kernels.json").is_file()


def test_staging_cleanup_preserves_deliverables_and_dependencies(tmp_path):
    ui = tmp_path / "ReverieCli-ui"
    scripts = ui / "scripts"
    scripts.mkdir(parents=True)
    script = scripts / "clean-build-staging.mjs"
    shutil.copy2(REPOSITORY / "ReverieCli-ui/scripts/clean-build-staging.mjs", script)
    disposable = ["ReverieCli-py/build/pyinstaller/cache", "ReverieCli-py/build/pyinstaller-dist/reverie.exe",
                  "ReverieCli-ui/.kernel/reverie/reverie.exe", "ReverieCli-ui/release/win-unpacked/ReverieUI.exe"]
    preserved = ["dist/reverie.exe", "dist/Reverie-Portable.exe", "dist/.reverie/session.json",
                 "ReverieCli-ui/release/Reverie-Setup.exe", "ReverieCli-ui/node_modules/dependency",
                 "ReverieCli-py/build/venv/Scripts/python.exe", "ReverieCli-py/build/bundle_resources/packed/browser.zip"]
    for name in disposable + preserved:
        file = tmp_path / name
        file.parent.mkdir(parents=True, exist_ok=True)
        file.write_text(name)
    subprocess.run([NODE, str(script)], check=True, cwd=tmp_path, timeout=30)
    assert all(not (tmp_path / name).exists() for name in disposable)
    assert all((tmp_path / name).read_text() == name for name in preserved)


@pytest.mark.skipif(os.name != "nt", reason="cmd.exe quoting is Windows-specific")
def test_dependency_fingerprint_uses_quoted_python_path(tmp_path):
    environment = tmp_path / "build environment"
    subprocess.run([sys.executable, "-m", "venv", "--without-pip", str(environment)],
                   check=True, timeout=30)
    source = (REPOSITORY / "ReverieCli-py/build.bat").read_text()
    start = source.index('"%PYTHON_EXE%" -c "import hashlib')
    end = source.index('if "%FORCE_DEPS%"', start)
    batch = tmp_path / "fingerprint.bat"
    batch.write_text(
        '@echo off\nset "PYTHON_EXE=' + str(environment / "Scripts/python.exe")
        + '"\nset "LOCAL_BUILD_ROOT=' + str(tmp_path) + '"\n'
        + source[start:end] + '\necho %CURRENT_DEPS_STAMP%\nexit /b 0\n'
        + ':finish\nexit /b 1\n', encoding="utf-8")
    result = subprocess.run(["cmd", "/c", str(batch)], cwd=tmp_path,
                            text=True, capture_output=True, timeout=30)
    assert result.returncode == 0, result.stderr
    assert len(result.stdout.strip()) == 64, result.stdout
