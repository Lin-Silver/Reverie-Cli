"""Build the portable Blender plugin with its text-only Skill resources."""

from pathlib import Path
import argparse
import hashlib
import os
import subprocess
import sys
import tempfile
from urllib.request import urlopen


ARCHIVE_NAME = "blender-5.1.1-windows-x64.zip"
ARCHIVE_URL = "https://download.blender.org/release/Blender5.1/" + ARCHIVE_NAME
ARCHIVE_SIZE = 414370237
ARCHIVE_SHA256 = "307123caa3bad0c1d04ec373a2f22f622c403eecb34b9c646ede104906b04ced"


def verify_archive(path: Path) -> None:
    if path.stat().st_size != ARCHIVE_SIZE:
        raise ValueError("Blender portable archive size mismatch")
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    if digest.hexdigest() != ARCHIVE_SHA256:
        raise ValueError("Blender portable archive SHA-256 mismatch")


def ensure_archive(path: Path) -> Path:
    path = path.resolve()
    if path.is_file():
        verify_archive(path)
        return path
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary = tempfile.mkstemp(prefix=ARCHIVE_NAME + ".", suffix=".part", dir=path.parent)
    os.close(descriptor)
    candidate = Path(temporary)
    try:
        received = 0
        with urlopen(ARCHIVE_URL, timeout=120) as response, candidate.open("wb") as destination:
            declared = response.headers.get("Content-Length")
            if declared is not None and int(declared) != ARCHIVE_SIZE:
                raise ValueError("Blender download Content-Length mismatch")
            while block := response.read(1024 * 1024):
                received += len(block)
                if received > ARCHIVE_SIZE:
                    raise ValueError("Blender download exceeds pinned size")
                destination.write(block)
        verify_archive(candidate)
        if path.exists():
            verify_archive(path)
        else:
            os.replace(candidate, path)
        return path
    finally:
        candidate.unlink(missing_ok=True)


def main() -> int:
    root = Path(__file__).resolve().parent
    parser = argparse.ArgumentParser(description=__doc__)
    default_archive = root / "build" / "sdk" / ARCHIVE_NAME
    parser.add_argument("--archive", type=Path, default=default_archive)
    args = parser.parse_args()
    command = [sys.executable, "-m", "PyInstaller", "--noconfirm", "--clean", "--onefile",
               "--name", "reverie-blender", "--specpath", "build"]
    if sys.platform == "win32" or args.archive.is_file():
        if not args.archive.is_file() and args.archive.resolve() != default_archive.resolve():
            parser.error(f"Blender portable archive not found: {args.archive}")
        try:
            archive = ensure_archive(args.archive)
        except (OSError, ValueError) as error:
            parser.error(str(error))
        command.extend(["--add-data", f"{archive}{os.pathsep}."])
    for resource in sorted((root / "skills").rglob("*")):
        relative = resource.relative_to(root)
        if {"__pycache__", "node_modules", ".git", ".cache"}.intersection(relative.parts):
            continue
        if not resource.is_file() or (resource.name != "LICENSE" and resource.suffix not in
                                      {".md", ".py", ".mjs", ".js", ".json", ".yaml", ".sh", ".html", ".css"}):
            continue
        command.extend(["--add-data", f"{resource}{os.pathsep}{relative.parent}"])
    command.append("plugin.py")
    return subprocess.call(command, cwd=root)


if __name__ == "__main__":
    raise SystemExit(main())
