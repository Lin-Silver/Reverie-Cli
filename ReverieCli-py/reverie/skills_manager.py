"""OpenAI Codex-style skill discovery and prompt helpers for Reverie."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, Optional
import json
import os
import re
import time

import yaml

from .modes import normalize_mode
from .builtin_skills import BUILTIN_SKILL_MODES


_FRONTMATTER_RE = re.compile(r"\A---\s*\r?\n(.*?)\r?\n---\s*(?:\r?\n|$)", re.DOTALL)
_EXPLICIT_SKILL_RE = re.compile(r"(?<![A-Za-z0-9_.-])\$([A-Za-z0-9][A-Za-z0-9._-]*)")
_TOKEN_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9._+-]{1,}")
_SKILL_SCAN_SKIP_DIRS = {".git", ".hg", ".svn", "__pycache__", "node_modules", ".venv", "venv"}
_SKILL_METADATA_RELATIVE_PATH = Path("agents") / "openai.yaml"
_DEFAULT_SKILL_METADATA_CHAR_BUDGET = 8_000
_SKILL_STOPWORDS = {
    "the", "and", "for", "with", "that", "this", "from", "into", "your", "when", "use", "using",
    "user", "wants", "want", "anything", "files", "file", "skill", "guide", "whenever", "does",
    "what", "about", "into", "their", "them", "through", "where", "have", "has", "will", "should",
    "been", "more", "make", "creates", "create", "need", "needs", "work", "works", "working",
    "help", "please", "build", "app", "apps", "project", "projects", "task", "tasks",
}


def _same_path(left: Path, right: Path) -> bool:
    """Compare paths without assuming that the host filesystem is case-sensitive."""
    try:
        if left.exists() and right.exists():
            return left.samefile(right)
    except OSError:
        pass
    return os.path.normcase(str(left.resolve(strict=False))) == os.path.normcase(
        str(right.resolve(strict=False))
    )


def _stable_json_signature(payload: Any) -> str:
    """Return a stable signature string for change detection."""
    try:
        return json.dumps(payload, ensure_ascii=False, sort_keys=True, default=str)
    except Exception:
        return repr(payload)


def _normalize_skill_key(value: Any) -> str:
    """Normalize skill names for lookups and explicit mentions."""
    text = str(value or "").strip().lower()
    return re.sub(r"[^a-z0-9._-]+", "-", text).strip("-._")


def _trim_text(value: Any, limit: int = 240) -> str:
    """Return a one-line summary clipped to a predictable width."""
    text = re.sub(r"\s+", " ", str(value or "").strip())
    if len(text) <= limit:
        return text
    return f"{text[: max(limit - 3, 1)].rstrip()}..."


def _normalize_token(value: str) -> str:
    """Normalize a loose token for matching."""
    text = str(value or "").strip().lower()
    text = re.sub(r"^[^a-z0-9]+|[^a-z0-9]+$", "", text)
    if len(text) > 4 and text.endswith("ies"):
        text = f"{text[:-3]}y"
    elif len(text) > 3 and text.endswith("s") and not text.endswith("ss"):
        text = text[:-1]
    return text


def _extract_tokens(value: Any) -> set[str]:
    """Extract normalized matching tokens from free text."""
    raw_tokens = {_normalize_token(match.group(0)) for match in _TOKEN_RE.finditer(str(value or ""))}
    return {token for token in raw_tokens if token and token not in _SKILL_STOPWORDS}


def _extract_frontmatter(raw_text: str) -> tuple[dict[str, Any], str, Optional[str]]:
    """Return parsed YAML frontmatter, body text, and an optional parse error."""
    text = str(raw_text or "")
    match = _FRONTMATTER_RE.match(text)
    if not match:
        return {}, text, None

    frontmatter_text = match.group(1)
    body = text[match.end():]
    try:
        parsed = yaml.safe_load(frontmatter_text) or {}
    except Exception as exc:
        return {}, body, str(exc)
    if not isinstance(parsed, dict):
        return {}, body, "frontmatter must deserialize to a mapping"
    return parsed, body, None


def _load_optional_skill_metadata(path: Path) -> dict[str, Any]:
    """Load optional OpenAI Skill metadata without blocking a valid Skill."""
    if not path.is_file():
        return {}
    try:
        parsed = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except Exception:
        return {}
    return parsed if isinstance(parsed, dict) else {}


def _skill_allows_implicit_invocation(metadata: dict[str, Any]) -> bool:
    """Return the standard `agents/openai.yaml` implicit-invocation policy."""
    policy = metadata.get("policy") if isinstance(metadata, dict) else None
    if not isinstance(policy, dict):
        return True
    value = policy.get("allow_implicit_invocation")
    return value is not False and not (isinstance(value, str) and value.strip().lower() == "false")


def _extract_fallback_description(body_text: str) -> str:
    """Build a fallback description from the first meaningful prose paragraph."""
    lines = [line.strip() for line in str(body_text or "").splitlines()]
    paragraph_parts: list[str] = []
    for line in lines:
        if not line:
            if paragraph_parts:
                break
            continue
        if line.startswith(("---", "```", "~~~")):
            continue
        if line.startswith("#"):
            cleaned = line.lstrip("#").strip()
            if cleaned and not paragraph_parts:
                paragraph_parts.append(cleaned)
            continue
        if line.startswith(("-", "*", ">")) and not paragraph_parts:
            continue
        paragraph_parts.append(line)
    return _trim_text(" ".join(paragraph_parts), limit=240)


@dataclass(frozen=True)
class SkillRoot:
    """One configured discovery root for SKILL.md directories."""

    scope: str
    label: str
    path: Path
    priority: int

    @property
    def scope_label(self) -> str:
        labels = {
            "builtin": "Built-in",
            "workspace": "Workspace",
            "app": "App",
            "user": "User",
            "plugin": "Plugin",
        }
        return labels.get(self.scope, self.scope.title())


@dataclass(frozen=True)
class SkillError:
    """One invalid or unreadable skill discovered during scan."""

    path: Path
    root: SkillRoot
    message: str


@dataclass(frozen=True)
class SkillRecord:
    """One discovered skill directory."""

    name: str
    description: str
    path_to_skill_md: Path
    skill_dir: Path
    root: SkillRoot
    body: str
    metadata: dict[str, Any]
    lookup_key: str
    match_tokens: frozenset[str]
    allow_implicit_invocation: bool = True
    metadata_path: Optional[Path] = None
    source_uri: str = ""
    plugin_id: str = ""

    @property
    def scope_label(self) -> str:
        return self.root.scope_label

    @property
    def root_label(self) -> str:
        return self.root.label

    @property
    def display_path(self) -> str:
        return str(self.path_to_skill_md)

    @property
    def summary(self) -> str:
        return _trim_text(self.description, limit=180)


@dataclass(frozen=True)
class SkillsSnapshot:
    """Cached skill scan state."""

    roots: tuple[SkillRoot, ...]
    scanned_at: float
    records: tuple[SkillRecord, ...]
    errors: tuple[SkillError, ...]

    @property
    def skill_count(self) -> int:
        return len(self.records)

    @property
    def error_count(self) -> int:
        return len(self.errors)

    def summary_label(self) -> str:
        return f"{self.skill_count} skills | {self.error_count} invalid"

    def names(self, limit: int = 4) -> str:
        names = [record.name for record in self.records]
        if not names:
            return ""
        visible = names[:limit]
        if len(names) > limit:
            visible.append(f"+{len(names) - limit} more")
        return ", ".join(visible)


class SkillsManager:
    """Discover SKILL.md directories and render Codex-style prompt guidance."""

    def __init__(self, project_root: Path, app_root: Path, runtime_plugin_manager: Any = None) -> None:
        self.project_root = Path(project_root).resolve()
        self.app_root = Path(app_root).resolve()
        self.runtime_plugin_manager = runtime_plugin_manager
        self.active_mode = "reverie"
        self._snapshot: Optional[SkillsSnapshot] = None
        self._generation = 0
        self._signature = ""

    def _build_root_candidates(self) -> tuple[SkillRoot, ...]:
        package_root = Path(__file__).resolve().parent
        candidates = [
            SkillRoot("builtin", "builtin_skills", package_root / "builtin_skills", -10),
            SkillRoot("user", "~/.agents/skills", Path.home() / ".agents" / "skills", -2),
            SkillRoot("app", ".reverie/Skills (legacy)", self.app_root / ".reverie" / "Skills", 0),
            SkillRoot("app", ".reverie/skills (legacy)", self.app_root / ".reverie" / "skills", 1),
        ]
        candidates.extend(self._repo_skill_root_candidates())

        deduped: list[SkillRoot] = []
        seen_paths: list[Path] = []
        for root in candidates:
            if any(_same_path(root.path, seen) for seen in seen_paths):
                continue
            seen_paths.append(root.path)
            deduped.append(root)
        return tuple(deduped)

    def _repo_skill_root_candidates(self) -> list[SkillRoot]:
        """Discover `.agents/skills` from the project root through the working directory."""
        ancestors = [self.project_root, *self.project_root.parents]
        repo_boundary = next((path for path in ancestors if (path / ".git").exists()), None)
        if repo_boundary is not None:
            ancestors = ancestors[: ancestors.index(repo_boundary) + 1]
        candidates: list[SkillRoot] = []
        for priority, directory in enumerate(reversed(ancestors), start=2):
            candidates.append(
                SkillRoot("workspace", ".agents/skills", directory / ".agents" / "skills", priority)
            )
        return candidates

    def set_runtime_plugin_manager(self, manager: Any) -> None:
        self.runtime_plugin_manager = manager
        self._snapshot = None

    def set_active_mode(self, mode: Any) -> None:
        normalized = normalize_mode(mode)
        if normalized != self.active_mode:
            self.active_mode = normalized
            self._snapshot = None

    def get_generation(self) -> int:
        """Return the current snapshot generation counter."""
        return int(self._generation)

    def get_snapshot(self, *, force_refresh: bool = False) -> SkillsSnapshot:
        """Return the current cached snapshot, rescanning when requested."""
        if force_refresh or self._snapshot is None:
            return self.scan()
        return self._snapshot

    def scan(self) -> SkillsSnapshot:
        """Scan supported roots for Codex-style skill directories."""
        roots = self._build_root_candidates()
        records: list[SkillRecord] = []
        errors: list[SkillError] = []
        seen_skill_paths: list[Path] = []

        for root in roots:
            if not root.path.is_dir():
                continue
            for skill_md in self._iter_skill_files(root.path):
                if any(_same_path(skill_md, seen) for seen in seen_skill_paths):
                    continue
                seen_skill_paths.append(skill_md)
                record, error = self._load_skill(skill_md, root)
                if record is not None and self._skill_visible_in_active_mode(record):
                    records.append(record)
                if error is not None:
                    errors.append(error)

        records.extend(self._load_plugin_skills())

        records.sort(key=lambda item: (item.root.priority, item.name.lower(), str(item.path_to_skill_md).lower()))
        errors.sort(key=lambda item: (item.root.priority, str(item.path).lower()))

        snapshot = SkillsSnapshot(
            roots=roots,
            scanned_at=time.time(),
            records=tuple(records),
            errors=tuple(errors),
        )

        signature_payload = {
            "records": [
                {
                    "name": record.name,
                    "description": record.description,
                    "path": str(record.path_to_skill_md),
                    "scope": record.root.scope,
                    "label": record.root.label,
                    "body": record.body,
                    "source_uri": record.source_uri,
                }
                for record in snapshot.records
            ],
            "errors": [
                {
                    "path": str(error.path),
                    "scope": error.root.scope,
                    "label": error.root.label,
                    "message": error.message,
                }
                for error in snapshot.errors
            ],
        }
        signature = _stable_json_signature(signature_payload)
        if signature != self._signature:
            self._signature = signature
            self._generation += 1
        self._snapshot = snapshot
        return snapshot

    def _skill_visible_in_active_mode(self, record: SkillRecord) -> bool:
        """Apply package-owned mode gates to built-in skills."""
        if record.root.scope != "builtin":
            return True
        include_modes = {
            normalize_mode(mode)
            for mode in BUILTIN_SKILL_MODES.get(record.lookup_key, ())
            if str(mode or "").strip()
        }
        return not include_modes or self.active_mode in include_modes

    def _load_plugin_skills(self) -> list[SkillRecord]:
        manager = self.runtime_plugin_manager
        if manager is None or not hasattr(manager, "get_skill_definitions"):
            return []
        try:
            definitions = manager.get_skill_definitions(force_refresh=False)
        except Exception:
            return []

        records: list[SkillRecord] = []
        for definition in definitions:
            if not isinstance(definition, dict):
                continue
            include_modes = {
                normalize_mode(mode)
                for mode in (definition.get("include_modes", []) or [])
                if str(mode or "").strip()
            }
            exclude_modes = {
                normalize_mode(mode)
                for mode in (definition.get("exclude_modes", []) or [])
                if str(mode or "").strip()
            }
            if include_modes and self.active_mode not in include_modes:
                continue
            if self.active_mode in exclude_modes:
                continue

            plugin_id = str(definition.get("plugin_id") or "").strip()
            name = str(definition.get("name") or "").strip()
            body = str(definition.get("body") or "").strip()
            if not plugin_id or not name or not body:
                continue
            description = str(definition.get("description") or "").strip() or f"Instructions supplied by plugin {plugin_id}."
            install_dir = Path(str(definition.get("install_dir") or self.app_root / ".reverie" / "plugins" / plugin_id))
            virtual_path = install_dir / "__plugin_skills__" / _normalize_skill_key(name) / "SKILL.md"
            source_uri = f"plugin://{plugin_id}/skills/{_normalize_skill_key(name)}"
            metadata = definition.get("metadata")
            normalized_name = _normalize_skill_key(name)
            root = SkillRoot("plugin", f"plugin:{plugin_id}", install_dir, -5)
            records.append(
                SkillRecord(
                    name=name,
                    description=description,
                    path_to_skill_md=virtual_path,
                    skill_dir=virtual_path.parent,
                    root=root,
                    body=body,
                    metadata=dict(metadata) if isinstance(metadata, dict) else {},
                    lookup_key=normalized_name,
                    match_tokens=frozenset(
                        {
                            token
                            for token in re.split(r"[-._/\\]+", normalized_name)
                            if token
                        }
                        | _extract_tokens(description)
                    ),
                    allow_implicit_invocation=_skill_allows_implicit_invocation(metadata),
                    source_uri=source_uri,
                    plugin_id=plugin_id,
                )
            )
        return records

    def _iter_skill_files(self, root_path: Path) -> list[Path]:
        """Return candidate SKILL.md files from one root, recursively."""
        skill_files: list[Path] = []
        seen: list[Path] = []

        for dirpath, dirnames, filenames in os.walk(root_path):
            dirnames[:] = [name for name in dirnames if name not in _SKILL_SCAN_SKIP_DIRS]
            if "SKILL.md" not in filenames:
                continue
            candidate = Path(dirpath) / "SKILL.md"
            if not candidate.is_file():
                continue
            if any(_same_path(candidate, discovered) for discovered in seen):
                continue
            seen.append(candidate)
            skill_files.append(candidate)
            # A discovered Skill directory is a package boundary. Its nested
            # references must not become separate Skills during discovery.
            dirnames[:] = []

        skill_files.sort(key=lambda path: str(path).lower())
        return skill_files

    def _load_skill(self, skill_md: Path, root: SkillRoot) -> tuple[Optional[SkillRecord], Optional[SkillError]]:
        try:
            raw_text = skill_md.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            try:
                raw_text = skill_md.read_text(encoding="utf-8-sig")
            except Exception as exc:
                return None, SkillError(skill_md, root, f"failed to read SKILL.md: {exc}")
        except Exception as exc:
            return None, SkillError(skill_md, root, f"failed to read SKILL.md: {exc}")

        metadata, body_text, parse_error = _extract_frontmatter(raw_text)
        if parse_error:
            return None, SkillError(skill_md, root, f"invalid frontmatter: {parse_error}")

        metadata_path = skill_md.parent / _SKILL_METADATA_RELATIVE_PATH
        metadata_file = _load_optional_skill_metadata(metadata_path)

        name = str(metadata.get("name") or skill_md.parent.name).strip() or skill_md.parent.name
        description = str(metadata.get("description") or "").strip()
        if not description:
            metadata_block = metadata.get("metadata")
            if isinstance(metadata_block, dict):
                description = str(
                    metadata_block.get("short-description")
                    or metadata_block.get("short_description")
                    or ""
                ).strip()
        if not description:
            description = _extract_fallback_description(body_text) or "No skill description provided."

        normalized_name = _normalize_skill_key(name) or _normalize_skill_key(skill_md.parent.name) or skill_md.parent.name.lower()
        name_tokens = {
            token
            for token in re.split(r"[-._/\\]+", normalized_name)
            if token
        }
        description_tokens = _extract_tokens(description)
        match_tokens = frozenset(name_tokens | description_tokens)
        record = SkillRecord(
            name=name,
            description=description,
            path_to_skill_md=skill_md.resolve(strict=False),
            skill_dir=skill_md.parent.resolve(strict=False),
            root=root,
            body=str(body_text or "").strip(),
            metadata=metadata,
            lookup_key=normalized_name,
            match_tokens=match_tokens,
            allow_implicit_invocation=_skill_allows_implicit_invocation(metadata_file),
            metadata_path=metadata_path if metadata_path.is_file() else None,
        )
        return record, None

    def get_status_summary(self, *, force_refresh: bool = False) -> dict[str, Any]:
        """Return a compact summary for status views and command panels."""
        snapshot = self.get_snapshot(force_refresh=force_refresh)
        root_values = [str(root.path) for root in snapshot.roots]
        return {
            "root_paths": root_values,
            "summary_label": snapshot.summary_label(),
            "skill_count": snapshot.skill_count,
            "error_count": snapshot.error_count,
            "skill_names": snapshot.names(),
        }

    def list_display_rows(self, *, force_refresh: bool = False) -> list[dict[str, str]]:
        """Return normalized rows for terminal tables."""
        snapshot = self.get_snapshot(force_refresh=force_refresh)
        return [
            {
                "name": record.name,
                "scope": record.scope_label,
                "root": record.root_label,
                "description": record.summary,
                "path": record.display_path,
            }
            for record in snapshot.records
        ]

    def list_error_rows(self, *, force_refresh: bool = False) -> list[dict[str, str]]:
        """Return invalid-skill rows for inspection UIs."""
        snapshot = self.get_snapshot(force_refresh=force_refresh)
        return [
            {
                "scope": error.root.scope_label,
                "root": error.root.label,
                "path": str(error.path),
                "message": error.message,
            }
            for error in snapshot.errors
        ]

    def get_record(self, identifier: str, *, force_refresh: bool = False) -> Optional[SkillRecord]:
        """Resolve one skill by explicit name, directory name, or SKILL.md path."""
        snapshot = self.get_snapshot(force_refresh=force_refresh)
        wanted = str(identifier or "").strip()
        if not wanted:
            return None

        wanted_key = _normalize_skill_key(wanted)
        wanted_path = (
            str(Path(wanted).resolve(strict=False)).lower()
            if ("SKILL.md" in wanted or "\\" in wanted or "/" in wanted) and not wanted.startswith("plugin://")
            else ""
        )

        for record in snapshot.records:
            if record.source_uri and record.source_uri.lower() == wanted.lower():
                return record
            if wanted_path and str(record.path_to_skill_md).lower() == wanted_path:
                return record
            if record.lookup_key == wanted_key:
                return record
            if _normalize_skill_key(record.skill_dir.name) == wanted_key:
                return record
        return None

    def resolve_explicit_mentions(self, text: str, *, force_refresh: bool = False) -> dict[str, Any]:
        """Resolve `$skill-name` mentions from one user turn."""
        snapshot = self.get_snapshot(force_refresh=force_refresh)
        if not snapshot.records:
            return {"names": [], "records": [], "missing": []}

        ordered_names: list[str] = []
        seen_names: set[str] = set()
        for match in _EXPLICIT_SKILL_RE.finditer(str(text or "")):
            raw_name = str(match.group(1) or "").strip()
            key = _normalize_skill_key(raw_name)
            if not key or key in seen_names:
                continue
            seen_names.add(key)
            ordered_names.append(raw_name)

        records: list[SkillRecord] = []
        missing: list[str] = []
        for raw_name in ordered_names:
            record = self.get_record(raw_name, force_refresh=False)
            if record is None:
                missing.append(raw_name)
            else:
                records.append(record)

        return {
            "names": ordered_names,
            "records": records,
            "missing": missing,
        }

    def resolve_automatic_matches(
        self,
        text: str,
        *,
        force_refresh: bool = False,
        top_n: int = 2,
    ) -> list[SkillRecord]:
        """Deprecated local matcher kept for compatibility; selection belongs to the model."""
        del text, force_refresh, top_n
        return []

    def build_explicit_skill_injection(self, records: Iterable[SkillRecord]) -> str:
        """Render explicit Skill names without copying untrusted bodies into user content."""
        normalized_records = [record for record in records if isinstance(record, SkillRecord)]
        if not normalized_records:
            return ""

        blocks = [
            "[SKILL REQUEST]",
            "The user explicitly requested the following Skill(s). Call skill_lookup(operation='inspect') for each before taking task actions.",
        ]
        for record in normalized_records:
            blocks.extend(
                [
                    f"- {record.name} (file: {record.source_uri or record.path_to_skill_md})",
                ]
            )
        return "\n".join(blocks).strip()

    def describe_for_prompt(
        self,
        *,
        force_refresh: bool = False,
        max_chars: int = _DEFAULT_SKILL_METADATA_CHAR_BUDGET,
    ) -> str:
        """Render a budgeted Codex-style metadata list for model-side Skill selection."""
        snapshot = self.get_snapshot(force_refresh=force_refresh)
        budget = max(512, int(max_chars or _DEFAULT_SKILL_METADATA_CHAR_BUDGET))
        lines = [
            "## Skills",
            "A skill is a reusable workflow stored in a `SKILL.md` file. The list below contains only name, description, and path.",
            "If the user names a skill or the task clearly matches its description, call `skill_lookup` with `operation=inspect` before acting. Read every returned body chunk before using that skill.",
            "Use `$skill-name` for an explicit request. Do not load a skill body merely because its description shares generic words with the task.",
            "### Available skills",
        ]
        used = sum(len(line) + 1 for line in lines)
        omitted = 0
        implicit_records = [record for record in snapshot.records if record.allow_implicit_invocation]
        for record in implicit_records:
            description = _trim_text(record.description, limit=1024)
            line = f"- {record.name}: {description} (file: {record.source_uri or record.path_to_skill_md})"
            if used + len(line) + 1 > budget:
                omitted += 1
                continue
            lines.append(line)
            used += len(line) + 1

        if not implicit_records:
            lines.append("- No valid skills are currently detected.")
        elif omitted:
            lines.append(f"- {omitted} additional Skill descriptions were omitted to fit the metadata budget.")

        if snapshot.errors:
            lines.append(f"- Invalid skills skipped during scan: {len(snapshot.errors)}")

        return "\n".join(lines)
