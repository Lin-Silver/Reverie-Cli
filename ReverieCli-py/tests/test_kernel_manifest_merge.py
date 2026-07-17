from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys


def _record(platform: str, arch: str, asset_name: str) -> dict[str, object]:
    return {
        "schema": "reverie.kernel.release.v1",
        "asset_name": asset_name,
        "sha256": "a" * 64,
        "size": 42,
        "commit": "release-commit",
        "kernel": {
            "schema": "reverie.kernel.v1",
            "version": "2.5.0",
            "bridge_protocol": "sdk-bridge.v1",
            "interface_version": "1.0",
            "platform": platform,
            "arch": arch,
            "frozen": True,
        },
    }


def test_merge_kernel_manifests_writes_one_ordered_release_record(tmp_path: Path) -> None:
    repo_root = Path(__file__).resolve().parents[1]
    script = repo_root / "scripts" / "merge_kernel_manifests.py"
    inputs = []
    for index, record in enumerate(
        (
            _record("darwin", "x64", "Reverie-CLI-macOS-Intel"),
            _record("linux", "x64", "reverie"),
            _record("win32", "x64", "reverie.exe"),
            _record("darwin", "arm64", "Reverie-CLI-macOS-Apple-Silicon"),
        )
    ):
        path = tmp_path / f"kernel-{index}.json"
        path.write_text(json.dumps(record), encoding="utf-8")
        inputs.append(path)

    output = tmp_path / "reverie-kernels.json"
    subprocess.run(
        [sys.executable, str(script), *(str(path) for path in inputs), "--output", str(output)],
        check=True,
    )
    merged = json.loads(output.read_text(encoding="utf-8"))

    assert merged["schema"] == "reverie.kernels.release.v1"
    assert merged["version"] == "2.5.0"
    assert merged["commit"] == "release-commit"
    assert [item["asset_name"] for item in merged["assets"]] == [
        "reverie.exe",
        "reverie",
        "Reverie-CLI-macOS-Apple-Silicon",
        "Reverie-CLI-macOS-Intel",
    ]
