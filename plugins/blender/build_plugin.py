"""Build the portable Blender plugin with its text-only Skill resources."""

from pathlib import Path
import argparse
import os
import subprocess
import sys


def main() -> int:
    root = Path(__file__).resolve().parent
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--archive", type=Path, default=root / "blender-5.1.1-windows-x64.zip")
    args = parser.parse_args()
    command = [sys.executable, "-m", "PyInstaller", "--noconfirm", "--clean", "--onefile",
               "--name", "reverie-blender", "--specpath", "build"]
    if args.archive.is_file():
        command.extend(["--add-data", f"{args.archive.resolve()}{os.pathsep}."])
    elif sys.platform == "win32":
        parser.error(f"Blender portable archive not found: {args.archive}")
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
