"""Workspace recognition and instruction loading for Context Engine."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional
import fnmatch
import os


INSTRUCTION_FILENAMES = (
    "AGENTS.md",
    "CLAUDE.md",
    "GEMINI.md",
    ".cursorrules",
    ".reverierules",
    "README.md",
)

PROJECT_MARKERS: Dict[str, str] = {
    "pyproject.toml": "python",
    "setup.py": "python",
    "requirements.txt": "python",
    "package.json": "node",
    "pnpm-lock.yaml": "node",
    "yarn.lock": "node",
    "Cargo.toml": "rust",
    "go.mod": "go",
    "pom.xml": "java",
    "build.gradle": "java",
    "build.gradle.kts": "java",
    "*.csproj": "dotnet",
    "*.sln": "dotnet",
    "*.slnx": "dotnet",
    "Godot.project": "godot",
    "project.godot": "godot",
}


@dataclass
class ProjectBoundary:
    """One detected project/module inside the workspace."""

    root: str
    kind: str
    markers: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {"root": self.root, "kind": self.kind, "markers": list(self.markers)}


@dataclass
class InstructionLayer:
    """A repository instruction document relevant to the current task."""

    path: str
    scope: str
    priority: int
    excerpt: str

    def to_dict(self) -> Dict[str, Any]:
        return {
            "path": self.path,
            "scope": self.scope,
            "priority": self.priority,
            "excerpt": self.excerpt,
        }


@dataclass
class WorkspaceProfile:
    """Detected workspace shape used to bound retrieval and edits."""

    root: str
    vcs_root: str = ""
    languages: List[str] = field(default_factory=list)
    project_boundaries: List[ProjectBoundary] = field(default_factory=list)
    instruction_layers: List[InstructionLayer] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "root": self.root,
            "vcs_root": self.vcs_root,
            "languages": list(self.languages),
            "project_boundaries": [item.to_dict() for item in self.project_boundaries],
            "instruction_layers": [item.to_dict() for item in self.instruction_layers],
        }


def _read_excerpt(path: Path, max_chars: int = 1800) -> str:
    try:
        text = path.read_text(encoding="utf-8", errors="ignore").strip()
    except Exception:
        return ""
    if len(text) <= max_chars:
        return text
    return text[:max_chars].rstrip() + "\n..."


def _relative_label(path: Path, root: Path) -> str:
    try:
        return str(path.relative_to(root))
    except Exception:
        return str(path)


def find_vcs_root(project_root: Path) -> Optional[Path]:
    """Return the nearest git root at or above project_root."""
    current = Path(project_root).resolve()
    for candidate in (current, *current.parents):
        if (candidate / ".git").exists():
            return candidate
    return None


def detect_workspace_profile(
    project_root: Path,
    *,
    focus_files: Optional[List[str]] = None,
    max_instruction_chars: int = 1800,
    max_scan_entries: int = 12000,
) -> WorkspaceProfile:
    """Detect project boundaries and layered instructions for a workspace."""
    root = Path(project_root).resolve()
    vcs_root = find_vcs_root(root)
    focus_paths = []
    for raw in focus_files or []:
        try:
            path = Path(raw)
            focus_paths.append(path.resolve() if path.is_absolute() else (root / path).resolve())
        except Exception:
            continue

    boundaries_by_root: Dict[Path, ProjectBoundary] = {}
    languages: set[str] = set()
    search_roots = [root]
    for focus_path in focus_paths:
        parents = [focus_path if focus_path.is_dir() else focus_path.parent, *focus_path.parents]
        for parent in parents:
            if root in (parent, *parent.parents):
                search_roots.append(parent)
                break

    for base in dict.fromkeys(search_roots):
        for marker, kind in PROJECT_MARKERS.items():
            matches = list(base.glob(marker)) if "*" in marker else ([base / marker] if (base / marker).exists() else [])
            if not matches:
                continue
            boundary_root = base
            item = boundaries_by_root.setdefault(
                boundary_root,
                ProjectBoundary(root=str(boundary_root), kind=kind, markers=[]),
            )
            for match in matches:
                item.markers.append(_relative_label(match, root))
            languages.add(kind)

    skipped_dirs = {".git", ".reverie", "node_modules", "__pycache__", "dist", "build", "target", ".venv", "venv"}
    scanned = 0
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [name for name in dirnames if name not in skipped_dirs]
        scanned += len(filenames)
        if scanned > max_scan_entries:
            break
        for filename in filenames:
            for marker, kind in PROJECT_MARKERS.items():
                if "*" not in marker and filename != marker:
                    continue
                if "*" in marker and not fnmatch.fnmatch(filename, marker):
                    continue
                match = Path(dirpath) / filename
                boundary_root = match.parent
                item = boundaries_by_root.setdefault(
                    boundary_root,
                    ProjectBoundary(root=str(boundary_root), kind=kind, markers=[]),
                )
                label = _relative_label(match, root)
                if label not in item.markers:
                    item.markers.append(label)
                languages.add(kind)

    instruction_candidates: Dict[Path, int] = {}
    roots_to_check = [root]
    if vcs_root and vcs_root != root:
        roots_to_check.insert(0, vcs_root)
    for focus_path in focus_paths:
        current = focus_path if focus_path.is_dir() else focus_path.parent
        while root in (current, *current.parents):
            roots_to_check.append(current)
            if current == root:
                break
            current = current.parent

    for priority, base in enumerate(dict.fromkeys(roots_to_check)):
        for filename in INSTRUCTION_FILENAMES:
            path = base / filename
            if path.exists() and path.is_file():
                instruction_candidates[path.resolve()] = priority

    instruction_layers = []
    for path, priority in sorted(instruction_candidates.items(), key=lambda item: (item[1], str(item[0]))):
        excerpt = _read_excerpt(path, max_chars=max_instruction_chars)
        if not excerpt:
            continue
        instruction_layers.append(
            InstructionLayer(
                path=str(path),
                scope=_relative_label(path.parent, root),
                priority=priority,
                excerpt=excerpt,
            )
        )

    return WorkspaceProfile(
        root=str(root),
        vcs_root=str(vcs_root) if vcs_root else "",
        languages=sorted(languages),
        project_boundaries=sorted(boundaries_by_root.values(), key=lambda item: item.root)[:40],
        instruction_layers=instruction_layers[:12],
    )
