"""Pack large UI-kernel resources for lazy extraction at first use."""

from __future__ import annotations

import argparse
import os
from pathlib import Path
import shutil
import zipfile


BROWSER_EXECUTABLE_NAMES = (
    "chrome.exe",
    "chrome",
    "Chromium",
    "Google Chrome for Testing",
)


def _write_tree(archive: zipfile.ZipFile, source: Path, prefix: str) -> None:
    for file_path in sorted(path for path in source.rglob("*") if path.is_file()):
        archive.write(file_path, Path(prefix) / file_path.relative_to(source))


def _resolve_ffmpeg(explicit: str) -> Path:
    candidates = [
        explicit,
        os.environ.get("REVERIE_FFMPEG_PATH", ""),
        shutil.which("ffmpeg") or "",
        "D:/Program Files/Environment/ffmpeg/bin/ffmpeg.exe",
        "C:/Program Files/ffmpeg/bin/ffmpeg.exe",
    ]
    for value in candidates:
        if value and Path(value).is_file():
            return Path(value).resolve()
    raise SystemExit("FFmpeg is required to build the complete Reverie UI kernel.")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--browser", required=True)
    parser.add_argument("--ffmpeg", default="")
    parser.add_argument("--output", required=True)
    args = parser.parse_args()

    browser_root = Path(args.browser).resolve()
    browser_executables = (
        candidate
        for name in BROWSER_EXECUTABLE_NAMES
        for candidate in browser_root.rglob(name)
    )
    if not browser_root.is_dir() or not any(candidate.is_file() for candidate in browser_executables):
        raise SystemExit(f"Bundled Chromium runtime is incomplete: {browser_root}")

    ffmpeg = _resolve_ffmpeg(args.ffmpeg)
    output_root = Path(args.output).resolve()
    output_root.mkdir(parents=True, exist_ok=True)
    browser_archive = output_root / "browser.zip"
    ffmpeg_archive = output_root / "ffmpeg.zip"

    with zipfile.ZipFile(browser_archive, "w", zipfile.ZIP_DEFLATED, compresslevel=6, allowZip64=True) as archive:
        _write_tree(archive, browser_root, "ms-playwright")
    with zipfile.ZipFile(ffmpeg_archive, "w", zipfile.ZIP_DEFLATED, compresslevel=6, allowZip64=True) as archive:
        archive.write(ffmpeg, "ffmpeg.exe" if os.name == "nt" else "ffmpeg")

    print(f"Browser archive: {browser_archive} ({browser_archive.stat().st_size} bytes)")
    print(f"FFmpeg archive: {ffmpeg_archive} ({ffmpeg_archive.stat().st_size} bytes)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
