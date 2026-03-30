"""OpenAI Codex-style skill discovery and prompt helpers for Reverie."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, Optional
import json
import re
import time

import yaml


_FRONTMATTER_RE = re.compile(r"\A---\s*\r?\n(.*?)\r?\n---\s*(?:\r?\n|$)", re.DOTALL)
_EXPLICIT_SKILL_RE = re.compile(r"(?<![A-Za-z0-9_.-])\$([A-Za-z0-9][A-Za-z0-9._-]*)")
_TOKEN_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9._+-]{1,}")
_SKILL_STOPWORDS = {
    "the", "and", "for", "with", "that", "this", "from", "into", "your", "when", "use", "using",
    "user", "wants", "want", "anything", "files", "file", "skill", "guide", "whenever", "does",
    "what", "about", "into", "their", "them", "through", "where", "have", "has", "will", "should",
    "been", "more", "make", "creates", "create", "need", "needs", "work", "works", "working",
    "help", "please", "build", "app", "apps", "project", "projects", "task", "tasks",
}


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
            "workspace": "Workspace",
            "app": "App",
            "user": "User",
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

    def __init__(self, project_root: Path, app_root: Path) -> None:
        self.project_root = Path(project_root).resolve()
        self.app_root = Path(app_root).resolve()
        self.home_root = Path.home().resolve()
        self._snapshot: Optional[SkillsSnapshot] = None
        self._generation = 0
        self._signature = ""

    def _build_root_candidates(self) -> tuple[SkillRoot, ...]:
        candidates = [
            SkillRoot("workspace", ".reverie/Skills", self.project_root / ".reverie" / "Skills", 0),
            SkillRoot("workspace", ".reverie/skills", self.project_root / ".reverie" / "skills", 1),
            SkillRoot("workspace", ".codex/skills", self.project_root / ".codex" / "skills", 2),
            SkillRoot("app", ".reverie/Skills", self.app_root / ".reverie" / "Skills", 3),
            SkillRoot("app", ".reverie/skills", self.app_root / ".reverie" / "skills", 4),
            SkillRoot("user", "~/.reverie/Skills", self.home_root / ".reverie" / "Skills", 5),
            SkillRoot("user", "~/.reverie/skills", self.home_root / ".reverie" / "skills", 6),
            SkillRoot("user", "~/.codex/skills", self.home_root / ".codex" / "skills", 7),
        ]

        deduped: list[SkillRoot] = []
        seen_paths: set[str] = set()
        for root in candidates:
            normalized = str(root.path.resolve(strict=False)).lower()
            if normalized in seen_paths:
                continue
            seen_paths.add(normalized)
            deduped.append(root)
        return tuple(deduped)

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
        seen_skill_paths: set[str] = set()

        for root in roots:
            if not root.path.is_dir():
                continue
            for skill_md in self._iter_skill_files(root.path):
                normalized_path = str(skill_md.resolve(strict=False)).lower()
                if normalized_path in seen_skill_paths:
                    continue
                seen_skill_paths.add(normalized_path)
                record, error = self._load_skill(skill_md, root)
                if record is not None:
                    records.append(record)
                if error is not None:
                    errors.append(error)

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

    def _iter_skill_files(self, root_path: Path) -> list[Path]:
        """Return candidate SKILL.md files from direct and nested `skills/` layouts."""
        skill_files: list[Path] = []
        seen: set[str] = set()

        patterns = (
            "*/SKILL.md",
            "skills/*/SKILL.md",
            "*/skills/*/SKILL.md",
            "*/*/skills/*/SKILL.md",
        )
        for pattern in patterns:
            for candidate in root_path.glob(pattern):
                if not candidate.is_file():
                    continue
                normalized = str(candidate.resolve(strict=False)).lower()
                if normalized in seen:
                    continue
                seen.add(normalized)
                skill_files.append(candidate)

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
        wanted_path = str(Path(wanted).resolve(strict=False)).lower() if ("SKILL.md" in wanted or "\\" in wanted or "/" in wanted) else ""

        for record in snapshot.records:
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
        """Infer relevant skills from the user request without explicit `$skill` markers."""
        snapshot = self.get_snapshot(force_refresh=force_refresh)
        if not snapshot.records:
            return []

        raw_text = str(text or "")
        lowered = raw_text.lower()
        query_tokens = _extract_tokens(raw_text)
        extension_tokens = {
            token.lower()
            for token in re.findall(r"\.([A-Za-z0-9]{2,8})\b", raw_text)
        }
        scored: list[tuple[int, SkillRecord]] = []

        for record in snapshot.records:
            score = 0
            if record.lookup_key and record.lookup_key in lowered:
                score += 12

            name_parts = [part for part in re.split(r"[-._/\\]+", record.lookup_key) if part]
            for part in name_parts:
                normalized_part = _normalize_token(part)
                if not normalized_part:
                    continue
                if normalized_part in query_tokens:
                    score += 4 if len(normalized_part) >= 4 else 6
                if normalized_part in extension_tokens:
                    score += 8

            overlap = len(record.match_tokens & query_tokens)
            if overlap >= 4:
                score += min(overlap * 2, 10)
            elif overlap >= 2:
                score += overlap

            if score >= 6:
                scored.append((score, record))

        scored.sort(key=lambda item: (-item[0], item[1].root.priority, item[1].name.lower()))
        return [record for _score, record in scored[:max(1, top_n)]]

    def build_explicit_skill_injection(self, records: Iterable[SkillRecord]) -> str:
        """Render active-skill context in a Codex-style skill wrapper block."""
        normalized_records = [record for record in records if isinstance(record, SkillRecord)]
        if not normalized_records:
            return ""

        blocks = [
            "[SKILL SYSTEM]",
            "The following skills are active for this turn.",
            "Treat them as high-priority instructions and follow their guidance before making changes.",
            "Skills may be activated explicitly with `$skill-name` or selected automatically when they clearly match the request.",
            "",
        ]
        for record in normalized_records:
            body = record.body.strip() or record.description.strip()
            blocks.extend(
                [
                    "<skill>",
                    f"<name>{record.name}</name>",
                    f"<path>{record.path_to_skill_md}</path>",
                    body,
                    "</skill>",
                    "",
                ]
            )
        return "\n".join(blocks).strip()

    def describe_for_prompt(self, *, force_refresh: bool = False, max_items: int = 10) -> str:
        """Return a compact prompt block describing available skills."""
        snapshot = self.get_snapshot(force_refresh=force_refresh)
        lines = [
            "## Skills",
            "- Reverie supports Codex/Claude-style skills: directories that contain a `SKILL.md` entrypoint.",
            "- Scan roots include `.reverie/Skills`, `.reverie/skills`, and compatibility paths such as `.codex/skills`.",
            "- Nested marketplace or repository layouts like `<root>/<repo>/skills/<skill>/SKILL.md` are supported.",
            "- If a listed skill clearly matches the user's request, inspect that skill's `SKILL.md` before implementing the task.",
            "- Users can explicitly activate a skill for the current turn by writing `$skill-name` in their message.",
            "- Use `/skills` to inspect available skills, rescan roots, and view exact `SKILL.md` paths.",
        ]

        if not snapshot.records:
            lines.append("- No valid skills are currently detected.")
        else:
            lines.append("- Available skills:")
            for record in snapshot.records[:max_items]:
                lines.append(
                    f"  - `{record.name}` ({record.scope_label}, {record.root_label}): {record.summary} (file: {record.path_to_skill_md})"
                )
            if len(snapshot.records) > max_items:
                lines.append(f"  - Additional skills not shown: {len(snapshot.records) - max_items}")

        if snapshot.errors:
            lines.append(f"- Invalid skills skipped during scan: {len(snapshot.errors)}")

        return "\n".join(lines)
