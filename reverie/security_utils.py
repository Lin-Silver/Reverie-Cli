"""Security-focused helpers for secret handling and sensitive file writes."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Iterable
import json
import os
import stat
import tempfile


def read_first_env(names: Iterable[str]) -> str:
    """Return the first non-empty environment variable from the provided names."""
    for name in names:
        key = str(name or "").strip()
        if not key:
            continue
        value = os.environ.get(key)
        if value and value.strip():
            return value.strip()
    return ""


def apply_restrictive_permissions(path: Path) -> None:
    """Best-effort restrictive permissions for files containing secrets."""
    target = Path(path)
    try:
        if os.name == "nt":
            os.chmod(target, stat.S_IREAD | stat.S_IWRITE)
        else:
            os.chmod(target, 0o600)
    except Exception:
        pass


def write_json_secure(path: Path, data: Any) -> None:
    """Atomically write JSON and tighten file permissions when possible."""
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    temp_name = ""

    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            dir=str(target.parent),
            prefix=f".{target.name}.tmp-",
            suffix=".json",
            delete=False,
        ) as temp_file:
            json.dump(data, temp_file, indent=2, ensure_ascii=False)
            temp_file.flush()
            try:
                os.fsync(temp_file.fileno())
            except OSError:
                pass
            temp_name = temp_file.name

        temp_path = Path(temp_name)
        apply_restrictive_permissions(temp_path)
        os.replace(temp_name, target)
        apply_restrictive_permissions(target)
    finally:
        if temp_name:
            leftover = Path(temp_name)
            if leftover.exists():
                try:
                    leftover.unlink()
                except Exception:
                    pass
