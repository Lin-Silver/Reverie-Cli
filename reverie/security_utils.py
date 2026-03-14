"""Security-focused helpers for secret handling and workspace isolation."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, Iterable
from datetime import datetime, timezone
import json
import os
import stat
import tempfile


class WorkspaceSecurityError(ValueError):
    """Raised when a tool attempts to access a path outside the active workspace."""


WORKSPACE_AUDIT_REL_PATH = Path(".reverie") / "security" / "command_audit.jsonl"


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


def get_workspace_root(project_root: Any = None) -> Path:
    """Return the canonical workspace root used for all tool path checks."""
    source = project_root if project_root is not None else Path.cwd()
    return Path(source).resolve()


def is_path_within_workspace(path: Path, project_root: Any = None) -> bool:
    """Return True when the resolved path is inside the current workspace root."""
    workspace_root = get_workspace_root(project_root)
    resolved = Path(path).resolve(strict=False)
    return resolved == workspace_root or workspace_root in resolved.parents


def ensure_workspace_path(path: Any, project_root: Any = None, *, purpose: str = "access") -> Path:
    """Ensure an already-built path stays inside the workspace boundary."""
    workspace_root = get_workspace_root(project_root)
    resolved = Path(path).resolve(strict=False)
    if not is_path_within_workspace(resolved, workspace_root):
        raise WorkspaceSecurityError(
            f"Blocked {purpose}: '{resolved}' is outside the active workspace '{workspace_root}'."
        )
    return resolved


def resolve_workspace_path(raw_path: Any, project_root: Any = None, *, purpose: str = "access") -> Path:
    """Resolve user input against the workspace root and reject path escapes."""
    raw_text = str(raw_path or "").strip()
    if not raw_text:
        raise WorkspaceSecurityError(f"Blocked {purpose}: path is required.")

    normalized = os.path.expandvars(raw_text)
    candidate = Path(normalized).expanduser()
    workspace_root = get_workspace_root(project_root)
    if not candidate.is_absolute():
        candidate = workspace_root / candidate

    return ensure_workspace_path(candidate, workspace_root, purpose=purpose)


def workspace_relative_path(path: Any, project_root: Any = None) -> str:
    """Return a stable workspace-relative path string when possible."""
    workspace_root = get_workspace_root(project_root)
    resolved = Path(path).resolve(strict=False)
    try:
        return str(resolved.relative_to(workspace_root))
    except ValueError:
        return str(resolved)


def ensure_archive_member_path(member_name: str, target_dir: Path, project_root: Any = None) -> Path:
    """Resolve an archive member path and block zip-slip / traversal attacks."""
    destination_root = ensure_workspace_path(target_dir, project_root, purpose="use extraction directory")
    member_path = Path(str(member_name or ""))
    if member_path.is_absolute():
        raise WorkspaceSecurityError(
            f"Blocked archive extraction: member '{member_name}' uses an absolute path."
        )

    extracted_path = (destination_root / member_path).resolve(strict=False)
    if not is_path_within_workspace(extracted_path, destination_root):
        raise WorkspaceSecurityError(
            f"Blocked archive extraction: member '{member_name}' escapes the target directory."
        )
    ensure_workspace_path(extracted_path, project_root, purpose="extract archive member")
    return extracted_path


def append_command_audit(project_root: Any, event: Dict[str, Any]) -> None:
    """Append a command audit event inside the workspace-local .reverie directory."""
    workspace_root = get_workspace_root(project_root)
    audit_path = workspace_root / WORKSPACE_AUDIT_REL_PATH
    audit_path.parent.mkdir(parents=True, exist_ok=True)

    payload = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        **(event or {}),
    }
    with audit_path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(payload, ensure_ascii=False) + "\n")
    apply_restrictive_permissions(audit_path)
