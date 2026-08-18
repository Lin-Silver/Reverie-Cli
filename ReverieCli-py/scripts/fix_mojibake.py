#!/usr/bin/env python3
"""Detect (and optionally repair) cp1252 mojibake in tracked source files.

Mojibake happens when UTF-8 bytes are decoded as cp1252/latin-1 and then
re-saved as UTF-8.  U+2022 BULLET turns into the three-character run
U+00E2 U+20AC U+00A2, and U+00B7 MIDDLE DOT turns into U+00C2 U+00B7.
Editors and terminals both render the damaged form faithfully, so the only
reliable repair is to re-encode the damaged run back to cp1252 bytes and
decode them as UTF-8 again.

Codepoints are named rather than shown above on purpose: spelling the damaged
runs out literally would make this file flag (and rewrite) itself.

Usage::

    python scripts/fix_mojibake.py            # report only, exit 1 if damaged
    python scripts/fix_mojibake.py --write    # rewrite the damaged files
"""

from __future__ import annotations

import argparse
import os
import re
import sys
from typing import Iterable, List, Tuple

# Roots that hold hand-written source. Vendored/generated trees are skipped.
DEFAULT_ROOTS = (
    "ReverieCli-py/reverie",
    "ReverieCli-py/tests",
    "ReverieCli-py/scripts",
    "ReverieCli-py/docs",
    "ReverieCli-ui/src",
    "ReverieCli-ui/electron",
    "ReverieCli-ui/scripts",
    "docs",
    "plugins",
)

SKIP_DIRS = {
    "__pycache__",
    "node_modules",
    "dist",
    "dist-electron",
    "build",
    "release",
    "venv",
    ".venv",
    ".git",
    ".pytest_cache",
}

EXTENSIONS = {
    ".py",
    ".ts",
    ".tsx",
    ".js",
    ".jsx",
    ".json",
    ".md",
    ".ps1",
    ".bat",
    ".sh",
    ".html",
    ".css",
}


def _sloppy_cp1252_table() -> dict:
    """Map every byte 0x00-0xFF to the character a sloppy cp1252 decode yields.

    Real cp1252 leaves 0x81, 0x8D, 0x8F, 0x90 and 0x9D undefined.  The tools
    that produced the damage in this repo passed those bytes through as latin-1
    instead of failing, so a strict cp1252 round-trip can only repair part of
    each run.  Mirroring that behaviour is what makes the repair complete.
    """
    table = {}
    for byte in range(0x100):
        try:
            char = bytes([byte]).decode("cp1252")
        except UnicodeDecodeError:
            char = chr(byte)  # latin-1 passthrough for the undefined slots
        table[char] = byte
    return table


_ENCODE_TABLE = _sloppy_cp1252_table()
# Only bytes >= 0x80 can be part of a mis-decoded multi-byte UTF-8 sequence.
_ALPHABET = "".join(sorted(char for char, byte in _ENCODE_TABLE.items() if byte >= 0x80))
_RUN_RE = re.compile(f"[{re.escape(_ALPHABET)}]+")


def _encode_sloppy(run: str) -> bytes | None:
    try:
        return bytes(_ENCODE_TABLE[char] for char in run)
    except KeyError:
        return None


def _decode_once(run: str) -> str | None:
    """Undo one cp1252-mojibake layer, or return None when ``run`` is clean."""
    raw = _encode_sloppy(run)
    if raw is None:
        return None
    try:
        fixed = raw.decode("utf-8")
    except UnicodeDecodeError:
        return None
    return fixed if fixed != run else None


def repair_run(run: str) -> str:
    """Repeatedly undo mojibake layers until the run stops changing."""
    current = run
    for _ in range(4):  # double/triple encoding happens; 4 is a safe ceiling
        nxt = _decode_once(current)
        if nxt is None:
            break
        current = nxt
    return current


def repair_text(text: str) -> Tuple[str, List[Tuple[str, str]]]:
    """Return ``(repaired_text, [(damaged, fixed), ...])``."""
    replacements: List[Tuple[str, str]] = []

    def substitute(match: re.Match[str]) -> str:
        run = match.group(0)
        fixed = repair_run(run)
        if fixed == run:
            return run
        replacements.append((run, fixed))
        return fixed

    return _RUN_RE.sub(substitute, text), replacements


def iter_source_files(roots: Iterable[str]) -> Iterable[str]:
    for root in roots:
        if not os.path.isdir(root):
            continue
        for dirpath, dirnames, filenames in os.walk(root):
            dirnames[:] = sorted(d for d in dirnames if d not in SKIP_DIRS)
            for filename in sorted(filenames):
                if os.path.splitext(filename)[1].lower() not in EXTENSIONS:
                    continue
                yield os.path.join(dirpath, filename).replace("\\", "/")


def main(argv: List[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--write", action="store_true", help="rewrite damaged files in place")
    parser.add_argument("roots", nargs="*", default=None, help="directories to scan")
    args = parser.parse_args(argv)

    roots = args.roots or list(DEFAULT_ROOTS)
    damaged_files = 0
    damaged_runs = 0

    for path in iter_source_files(roots):
        try:
            raw = open(path, "rb").read()
        except OSError:
            continue
        try:
            text = raw.decode("utf-8")
        except UnicodeDecodeError:
            print(f"{path}: not valid UTF-8 (skipped)")
            continue

        repaired, replacements = repair_text(text)
        if not replacements:
            continue

        damaged_files += 1
        damaged_runs += len(replacements)
        print(f"{path}: {len(replacements)} damaged run(s)")
        seen = set()
        for bad, good in replacements:
            if bad in seen:
                continue
            seen.add(bad)
            # ascii() keeps the report readable on consoles that are not UTF-8.
            print(f"    {ascii(bad)} -> {ascii(good)}")

        if args.write:
            with open(path, "wb") as handle:
                handle.write(repaired.encode("utf-8"))

    verb = "repaired" if args.write else "found"
    print(f"\n{verb} {damaged_runs} damaged run(s) across {damaged_files} file(s)")
    return 1 if damaged_files and not args.write else 0


if __name__ == "__main__":
    sys.exit(main())
