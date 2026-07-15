"""Workspace-scoped mutation checkpoints backed by an internal shadow Git repo."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import shutil
import subprocess
import threading
from typing import Iterable, Optional


class WorkspaceGuardError(RuntimeError):
    """Raised when workspace mutation safety cannot be established."""


@dataclass(frozen=True)
class WorkspaceCheckpoint:
    commit: str
    changed: bool


class ShadowGitManager:
    """Track workspace state without touching the user's repository or branch."""

    GENERATED_PATH_GLOBS = (
        "**/.git/**",
        "**/.reverie/**",
        "**/__pycache__/**",
        "**/.pytest_cache/**",
        "**/.mypy_cache/**",
        "**/.tox/**",
        "**/.nox/**",
        "**/node_modules/**",
        "**/venv/**",
        "**/.venv/**",
        "**/env/**",
        "**/build/**",
        "**/dist/**",
        "**/dist-staging/**",
        "**/target/**",
        "**/references/**",
        "**/*.zip",
        "**/*.7z",
        "**/*.tar",
        "**/*.gz",
    )

    def __init__(self, project_root: Path, project_data_dir: Path):
        self.project_root = Path(project_root).expanduser().resolve()
        self.project_data_dir = Path(project_data_dir).expanduser().resolve()
        self.git_dir = self.project_data_dir / "git-checkpoints"
        self.deleted_files_dir = self.project_data_dir / "deleted-files"
        self.audit_path = self.project_data_dir / "security" / "workspace_mutations.jsonl"
        self._lock = threading.RLock()
        self._ready = False

    def ensure_workspace_path(self, value: Path | str, *, purpose: str = "modify file") -> Path:
        candidate = Path(value).expanduser()
        if not candidate.is_absolute():
            candidate = self.project_root / candidate
        resolved = candidate.resolve(strict=False)
        if resolved != self.project_root and self.project_root not in resolved.parents:
            raise WorkspaceGuardError(
                f"Refused to {purpose} outside the active workspace: {resolved}"
            )
        return resolved

    def _git(self, *args: str, check: bool = True) -> subprocess.CompletedProcess[str]:
        env = os.environ.copy()
        env.update(
            {
                "GIT_DIR": str(self.git_dir),
                "GIT_WORK_TREE": str(self.project_root),
                "GIT_AUTHOR_NAME": "Reverie Checkpoint",
                "GIT_AUTHOR_EMAIL": "checkpoint@reverie.local",
                "GIT_COMMITTER_NAME": "Reverie Checkpoint",
                "GIT_COMMITTER_EMAIL": "checkpoint@reverie.local",
            }
        )
        completed = subprocess.run(
            ["git", *args],
            cwd=str(self.project_root),
            env=env,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            check=False,
        )
        if check and completed.returncode != 0:
            raise WorkspaceGuardError(completed.stderr.strip() or completed.stdout.strip() or "Git checkpoint failed")
        return completed

    def ensure_initialized(self) -> None:
        with self._lock:
            if self._ready:
                return
            if shutil.which("git") is None:
                raise WorkspaceGuardError("Git is required for automatic workspace checkpoints but was not found.")
            self.git_dir.parent.mkdir(parents=True, exist_ok=True)
            if not (self.git_dir / "HEAD").is_file():
                completed = subprocess.run(
                    ["git", "init", "--bare", str(self.git_dir)],
                    capture_output=True,
                    text=True,
                    encoding="utf-8",
                    errors="replace",
                    check=False,
                )
                if completed.returncode != 0:
                    raise WorkspaceGuardError(completed.stderr.strip() or "Could not initialize shadow Git repository")
            self._git("config", "core.autocrlf", "false")
            self._git("config", "core.filemode", "false")
            exclude = self.git_dir / "info" / "exclude"
            exclude.parent.mkdir(parents=True, exist_ok=True)
            exclude.write_text(".git/\n.reverie/\ndist-staging/\n", encoding="utf-8")
            self._ready = True

    def checkpoint(
        self,
        description: str,
        *,
        force_paths: Iterable[Path | str] = (),
    ) -> WorkspaceCheckpoint:
        """Commit current non-ignored workspace state when it changed."""
        with self._lock:
            self.ensure_initialized()
            exclusions = [f":(exclude,glob){pattern}" for pattern in self.GENERATED_PATH_GLOBS]
            # The shadow index intentionally ignores the user's .gitignore so
            # ignored source/config files are protected too. Generated and
            # dependency trees stay out unless a path-aware tool targets one.
            self._git("add", "-A", "-f", "--", ".", *exclusions)
            for raw_path in force_paths:
                candidate = self.ensure_workspace_path(raw_path, purpose="checkpoint file")
                if candidate.exists() and candidate.is_file():
                    relative = candidate.relative_to(self.project_root).as_posix()
                    self._git("add", "-f", "--", relative)
            head = self._git("rev-parse", "--verify", "HEAD", check=False)
            has_head = head.returncode == 0
            diff = self._git("diff", "--cached", "--quiet", check=False) if has_head else None
            changed = not has_head or diff is None or diff.returncode != 0
            if changed:
                stamp = datetime.now(timezone.utc).isoformat(timespec="seconds")
                commit_args = ["commit", "--no-gpg-sign"]
                if not has_head:
                    commit_args.append("--allow-empty")
                self._git(*commit_args, "-m", f"{description} [{stamp}]")
            commit = self._git("rev-parse", "HEAD").stdout.strip()
            return WorkspaceCheckpoint(commit=commit, changed=changed)

    def deleted_paths_since(self, commit: str) -> list[str]:
        with self._lock:
            self.ensure_initialized()
            result = self._git("diff", "--name-status", "--diff-filter=D", commit, "--", ".")
            return [line.split("\t", 1)[1] for line in result.stdout.splitlines() if "\t" in line]

    def restore_paths(self, commit: str, paths: Iterable[str]) -> list[str]:
        restored: list[str] = []
        with self._lock:
            self.ensure_initialized()
            for raw_path in paths:
                relative = str(raw_path or "").replace("\\", "/").lstrip("/")
                if not relative:
                    continue
                target = self.ensure_workspace_path(relative, purpose="restore file")
                target.parent.mkdir(parents=True, exist_ok=True)
                blob = subprocess.run(
                    ["git", f"--git-dir={self.git_dir}", "show", f"{commit}:{relative}"],
                    capture_output=True,
                    check=False,
                )
                if blob.returncode == 0:
                    target.write_bytes(blob.stdout)
                    restored.append(relative)
            if restored:
                self.checkpoint("Restore deletion blocked by workspace policy")
        return restored

    def archive_for_delete(self, path: Path) -> Path:
        """Copy a workspace file into portable project storage before deletion."""
        source = self.ensure_workspace_path(path, purpose="delete file")
        if not source.is_file():
            raise WorkspaceGuardError(f"Only regular workspace files can be archived for deletion: {source}")
        relative = source.relative_to(self.project_root)
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S.%fZ")
        target = self.deleted_files_dir / stamp / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)
        self._audit(
            {
                "event": "delete_archive_created",
                "source": str(source),
                "archive": str(target),
                "size": source.stat().st_size,
            }
        )
        return target

    def _audit(self, payload: dict) -> None:
        self.audit_path.parent.mkdir(parents=True, exist_ok=True)
        record = {"timestamp": datetime.now(timezone.utc).isoformat(), **payload}
        with self.audit_path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(record, ensure_ascii=False) + "\n")
