"""Persistent long-form fiction project control for Writer mode."""

from __future__ import annotations

import ast
from datetime import datetime, timezone
import hashlib
import json
import math
from pathlib import Path
import re
from typing import Any, Dict, Iterable, Optional

from .base import BaseTool, ToolResult


STATE_SCHEMA = "reverie.writer.project.v1"
DEFAULT_OUTPUT_DIR = "novels"
READER_OUTPUT_DIR = "novel"
MAX_QUALITY_GATE_RETRY_ATTEMPTS = 3
STYLE_TICS = (
    "微微",
    "缓缓",
    "仿佛",
    "似乎",
    "不由自主",
    "一丝",
    "像是被什么",
    "说不出话",
    "空气中弥漫",
)


DATA_PAYLOAD_KEYS = (
    "world_bible",
    "cast_bible",
    "story_architecture",
    "style_guide",
    "roadmap",
    "content",
    "append_content",
    "summary",
    "outline",
    "target_chars",
    "scene_beats",
    "continuity_requirements",
    "relationship_progression",
    "opening_hook",
    "ending_hook",
    "key_events",
    "character_updates",
    "relationship_updates",
    "timeline_updates",
    "opened_threads",
    "advanced_threads",
    "resolved_threads",
    "foreshadowing_opened",
    "foreshadowing_resolved",
)

PENDING_RECOVERY_APPEND_ONLY = "append_only"
PENDING_RECOVERY_FULL_REWRITE = "full_rewrite"
PENDING_RECOVERY_REPREPARE = "reprepare"
NEGATIVE_REQUIREMENT_MARKERS = (
    "不得出现",
    "不要出现",
    "禁止出现",
    "避免出现",
    "不得使用",
    "不要使用",
    "禁止使用",
)
REQUIREMENT_TERM_SPLIT_RE = re.compile(r"[、,，/]")
MATCH_TEXT_STRIP_RE = re.compile(r"[\s\"'“”‘’`，,。；;：:、\-—_()（）《》<>【】\[\]]+")
MATCH_TEXT_NOISE_TRANSLATION = str.maketrans("", "", "的是在")
LONGFORM_BRIEF_MARKERS = ("小说", "连载", "长篇", "多章节", "chaptered", "serial", "novel")
SHORTFORM_BRIEF_MARKERS = ("短篇", "中篇", "单篇", "短文", "微小说", "one-shot", "oneshot", "novella")


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _safe_id(value: Any) -> str:
    candidate = re.sub(r"[^\w.-]+", "-", str(value or "").strip(), flags=re.UNICODE).strip("-._")
    if not candidate:
        raise ValueError("novel_id must contain at least one letter or number")
    return candidate[:80]


def _as_list(value: Any) -> list[Any]:
    if value is None:
        return []
    if isinstance(value, list):
        return value
    return [value]


def _text(value: Any) -> str:
    if isinstance(value, (dict, list)):
        return json.dumps(value, ensure_ascii=False, indent=2).strip()
    return str(value or "").strip()


def _decode_jsonish_escapes(value: str) -> str:
    """Decode common JSON-style escapes without requiring strict JSON."""
    if "\\" not in value:
        return value

    def _replace_unicode(match: re.Match[str]) -> str:
        try:
            return chr(int(match.group(1), 16))
        except Exception:
            return match.group(0)

    decoded = re.sub(r"\\u([0-9a-fA-F]{4})", _replace_unicode, value)
    replacements = {
        r"\\": "\\",
        r"\"": '"',
        r"\'": "'",
        r"\/": "/",
        r"\n": "\n",
        r"\r": "\r",
        r"\t": "\t",
        r"\b": "\b",
        r"\f": "\f",
    }
    return re.sub(
        r"\\[\\\"'\/nrtbf]",
        lambda match: replacements.get(match.group(0), match.group(0)),
        decoded,
    )


def _next_jsonish_key(raw: str, index: int) -> str:
    """Return the next quoted object property name after a comma."""
    match = re.match(r"\s*['\"]([^'\"]+)['\"]\s*:", raw[index:])
    return str(match.group(1) or "").strip() if match else ""


def _extract_jsonish_string_field(raw: str, key: str, next_keys: set[str]) -> str:
    """Recover a long string value from a malformed JSON-like object."""
    match = re.search(rf"(['\"]){re.escape(key)}\1\s*:\s*(['\"])", raw, re.DOTALL)
    if not match:
        return ""

    quote = match.group(2)
    pieces: list[str] = []
    escaped = False
    index = match.end()

    while index < len(raw):
        char = raw[index]
        if escaped:
            pieces.append("\\" + char)
            escaped = False
            index += 1
            continue
        if char == "\\":
            escaped = True
            index += 1
            continue
        if char == quote:
            lookahead = index + 1
            while lookahead < len(raw) and raw[lookahead].isspace():
                lookahead += 1
            if lookahead >= len(raw) or raw[lookahead] in {"}", "]"}:
                return _decode_jsonish_escapes("".join(pieces))
            if raw[lookahead] == ",":
                next_key = _next_jsonish_key(raw, lookahead + 1)
                if next_key and next_key in next_keys:
                    return _decode_jsonish_escapes("".join(pieces))
        pieces.append(char)
        index += 1

    if escaped:
        pieces.append("\\")
    return _decode_jsonish_escapes("".join(pieces))


def _extract_jsonish_integer_field(raw: str, key: str) -> Optional[int]:
    """Recover a simple integer field from a malformed JSON-like object."""
    match = re.search(rf"['\"]{re.escape(key)}['\"]\s*:\s*(-?\d+)", raw)
    if not match:
        return None
    try:
        return int(match.group(1))
    except ValueError:
        return None


def _extract_jsonish_array_field(raw: str, key: str) -> list[Any]:
    """Recover a JSON-like array field from a malformed nested payload."""
    match = re.search(rf"(['\"]){re.escape(key)}\1\s*:\s*\[", raw, re.DOTALL)
    if not match:
        return []

    start = raw.find("[", match.end() - 1)
    if start < 0:
        return []

    depth = 0
    quote = ""
    escaped = False
    for index in range(start, len(raw)):
        char = raw[index]
        if quote:
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == quote:
                quote = ""
            continue
        if char in {"'", '"'}:
            quote = char
            continue
        if char == "[":
            depth += 1
            continue
        if char != "]":
            continue
        depth -= 1
        if depth != 0:
            continue
        chunk = raw[start : index + 1]
        try:
            decoded = json.loads(chunk)
        except json.JSONDecodeError:
            try:
                decoded = ast.literal_eval(chunk)
            except (SyntaxError, ValueError):
                return []
        return decoded if isinstance(decoded, list) else []
    return []


def _salvage_jsonish_data_payload(raw: str) -> Dict[str, Any]:
    """Recover Writer payload fields when a provider emits malformed nested JSON."""
    next_keys = set(DATA_PAYLOAD_KEYS)
    payload: Dict[str, Any] = {}
    for key in (
        "world_bible",
        "cast_bible",
        "story_architecture",
        "style_guide",
        "roadmap",
        "content",
        "append_content",
        "summary",
        "outline",
        "opening_hook",
        "ending_hook",
    ):
        value = _extract_jsonish_string_field(raw, key, next_keys)
        if value:
            payload[key] = value

    target_chars = _extract_jsonish_integer_field(raw, "target_chars")
    if target_chars is not None:
        payload["target_chars"] = target_chars

    for key in (
        "scene_beats",
        "continuity_requirements",
        "relationship_progression",
        "key_events",
        "character_updates",
        "relationship_updates",
        "timeline_updates",
        "opened_threads",
        "advanced_threads",
        "resolved_threads",
        "foreshadowing_opened",
        "foreshadowing_resolved",
    ):
        values = _extract_jsonish_array_field(raw, key)
        if values:
            payload[key] = values
    return payload


def _normalize_requirement_term(value: Any) -> str:
    term = _text(value).strip().strip("\"'“”‘’")
    term = term.strip(" ,，、.;；:：()（）[]{}<>《》【】")
    if len(term) < 2 or len(term) > 80:
        return ""
    if term.startswith("等") or "表述" in term:
        return ""
    return term


def _normalize_match_text(value: Any) -> str:
    return MATCH_TEXT_STRIP_RE.sub("", _text(value)).translate(MATCH_TEXT_NOISE_TRANSLATION).lower()


def _extract_forbidden_terms(requirements: Iterable[Any]) -> list[str]:
    terms: list[str] = []
    seen: set[str] = set()

    def add(term: Any) -> None:
        cleaned = _normalize_requirement_term(term)
        normalized = _normalize_match_text(cleaned)
        if not cleaned or not normalized or normalized in seen:
            return
        seen.add(normalized)
        terms.append(cleaned)

    for requirement in requirements:
        text = _text(requirement)
        if not text:
            continue
        for marker in NEGATIVE_REQUIREMENT_MARKERS:
            if marker not in text:
                continue
            fragment = text.split(marker, 1)[1]
            fragment = re.split(r"(?:等(?:表述|词|句|意象|内容|情节)?|即可|就行|并且|并|但是|但|。|；|;)", fragment, maxsplit=1)[0]
            for quoted in re.findall(r"[\"“”](.{2,80}?)[\"“”]", fragment):
                add(quoted)
            for piece in REQUIREMENT_TERM_SPLIT_RE.split(fragment):
                add(piece)
            break
    return terms


def _parse_explicit_length_request(value: Any) -> Optional[int]:
    text = _text(value).lower()
    if not text:
        return None
    for token, amount in (
        ("十万字", 100000),
        ("十万", 100000),
        ("100k", 100000),
    ):
        if token in text:
            return amount
    patterns = (
        (r"(\d+(?:\.\d+)?)\s*(?:万|w)\s*(?:字|字符|characters?)?", 10000),
        (r"(\d+(?:\.\d+)?)\s*k\s*(?:字|字符|characters?)?", 1000),
        (r"(\d{4,6})\s*(?:字|字符|characters?)", 1),
    )
    for pattern, multiplier in patterns:
        match = re.search(pattern, text)
        if not match:
            continue
        return int(float(match.group(1)) * multiplier)
    return None


class SerialNovelTool(BaseTool):
    """Create and maintain a resumable, auditable serialized-fiction project."""

    name = "serial_novel"
    aliases = ("novel_project", "story_project", "longform_writer")
    search_hint = "bootstrap plan write continue and audit a 100k character serialized novel"
    tool_category = "writer"
    tool_tags = (
        "novel",
        "serial",
        "chapter",
        "outline",
        "continuity",
        "foreshadowing",
        "long-form",
    )
    description = (
        "Writer-only control plane for persistent long-form fiction. Bootstrap a novel project, write its bibles, "
        "prepare chapter control cards, commit complete chapters, resume after interruption, and audit the actual "
        "files and character count. Use this before writing prose whenever the user asks for a novel or serial."
    )
    max_result_chars = 20_000
    parameters = {
        "type": "object",
        "properties": {
            "action": {
                "type": "string",
                "enum": [
                    "bootstrap",
                    "configure",
                    "prepare_chapter",
                    "commit_chapter",
                    "context",
                    "status",
                    "audit",
                    "complete",
                    "list_projects",
                ],
                "description": "Project lifecycle action.",
            },
            "novel_id": {
                "type": "string",
                "description": "Stable project id used across later prompts.",
            },
            "title": {"type": "string", "description": "Novel or chapter title, depending on action."},
            "brief": {"type": "string", "description": "The user's original story brief."},
            "chapter": {"type": "integer", "description": "One-based chapter number."},
            "target_chars": {
                "type": "integer",
                "description": "Minimum non-whitespace character target for the complete novel.",
                "default": 100000,
            },
            "chapter_target_chars": {
                "type": "integer",
                "description": "Default non-whitespace character target for each chapter.",
                "default": 4000,
            },
            "output_dir": {
                "type": "string",
                "description": "Workspace-relative parent directory. Defaults to novels/.",
                "default": DEFAULT_OUTPUT_DIR,
            },
            "data": {
                "type": "object",
                "description": (
                    "Action payload. configure accepts world_bible, cast_bible, story_architecture, style_guide, "
                    "and roadmap. prepare_chapter accepts outline, scene_beats, continuity_requirements, "
                    "relationship_progression, opening_hook, ending_hook, and target_chars. commit_chapter accepts "
                    "content, summary, key_events, character_updates, relationship_updates, timeline_updates, "
                    "opened_threads, advanced_threads, resolved_threads, foreshadowing_opened, and "
                    "foreshadowing_resolved."
                ),
                "properties": {
                    "world_bible": {
                        "type": "string",
                        "description": "For configure: world rules, locations, institutions, and grounding details.",
                    },
                    "cast_bible": {
                        "type": "string",
                        "description": "For configure: the major cast, desires, boundaries, habits, and conflicts.",
                    },
                    "story_architecture": {
                        "type": "string",
                        "description": "For configure: the structural plan, arcs, and delivery logic.",
                    },
                    "style_guide": {
                        "type": "string",
                        "description": "For configure: viewpoint, diction, imagery, rhythm, and prohibited habits.",
                    },
                    "roadmap": {
                        "type": "string",
                        "description": "For configure: chapter-by-chapter or phase-by-phase delivery plan.",
                    },
                    "content": {
                        "type": "string",
                        "description": (
                            "For commit_chapter: the full chapter prose. Before calling commit_chapter, ensure its "
                            "non-whitespace character count reaches recommended_draft_chars returned by "
                            "prepare_chapter/context. After a length-only rejection, do not resend the full draft; "
                            "send only new prose through append_content."
                        ),
                    },
                    "append_content": {
                        "type": "string",
                        "description": (
                            "For commit_chapter recovery after a length-only rejection: only the new continuation "
                            "prose. Start from the first unseen beat after the preserved draft tail, and do not "
                            "repeat or lightly paraphrase any preserved paragraph. The tool merges it with the "
                            "preserved rejected draft and re-runs every gate."
                        ),
                    },
                    "summary": {
                        "type": "string",
                        "description": (
                            "For commit_chapter: a concise factual chapter summary used for continuity. If omitted, "
                            "the tool stores a deterministic extractive fallback instead of rejecting full prose."
                        ),
                    },
                    "outline": {
                        "type": "string",
                        "description": "For prepare_chapter: the complete scene-level chapter plan.",
                    },
                    "target_chars": {
                        "type": "integer",
                        "description": "For prepare_chapter: desired non-whitespace chapter character count.",
                    },
                    "scene_beats": {"type": "array", "items": {"type": "string"}},
                    "continuity_requirements": {"type": "array", "items": {"type": "string"}},
                    "relationship_progression": {"type": "array", "items": {"type": "string"}},
                    "key_events": {"type": "array", "items": {"type": "string"}},
                    "character_updates": {"type": "array", "items": {"type": "string"}},
                    "relationship_updates": {"type": "array", "items": {"type": "string"}},
                    "timeline_updates": {"type": "array", "items": {"type": "string"}},
                    "opened_threads": {"type": "array", "items": {"type": "string"}},
                    "advanced_threads": {"type": "array", "items": {"type": "string"}},
                    "resolved_threads": {"type": "array", "items": {"type": "string"}},
                    "foreshadowing_opened": {"type": "array", "items": {"type": "string"}},
                    "foreshadowing_resolved": {"type": "array", "items": {"type": "string"}},
                },
            },
        },
        "required": ["action"],
    }

    def execute(self, **kwargs: Any) -> ToolResult:
        try:
            action = _text(kwargs.get("action")).lower()
            if action == "list_projects":
                return self._list_projects(kwargs)
            raw_novel_id = kwargs.get("novel_id")
            if not _text(raw_novel_id) and action == "status":
                raw_novel_id = self._infer_active_novel_id(kwargs, allow_idle=True, suppress_errors=True)
                if not raw_novel_id:
                    return self._status_overview(kwargs)
            elif not _text(raw_novel_id) and action != "bootstrap":
                raw_novel_id = self._infer_active_novel_id(kwargs)
            novel_id = _safe_id(raw_novel_id)
            handlers = {
                "bootstrap": self._bootstrap,
                "configure": self._configure,
                "prepare_chapter": self._prepare_chapter,
                "commit_chapter": self._commit_chapter,
                "context": self._context,
                "status": self._status,
                "audit": self._audit_result,
                "complete": self._complete,
            }
            handler = handlers.get(action)
            if handler is None:
                return ToolResult.fail(f"Unknown action: {action}")
            return handler(novel_id, kwargs)
        except (OSError, ValueError, TypeError, json.JSONDecodeError) as exc:
            return ToolResult.fail(f"serial_novel failed: {exc}")

    def _output_root(self, kwargs: Dict[str, Any]) -> Path:
        raw = _text(kwargs.get("output_dir")) or DEFAULT_OUTPUT_DIR
        return self.resolve_workspace_path(raw, purpose="manage novel projects")

    def _project_dir(self, novel_id: str, kwargs: Dict[str, Any]) -> Path:
        return self._output_root(kwargs) / novel_id

    def _reader_root(self) -> Path:
        return self.resolve_workspace_path(READER_OUTPUT_DIR, purpose="write readable novel exports")

    def _reader_project_dir(self, novel_id: str) -> Path:
        return self._reader_root() / novel_id

    def _reader_chapter_path(self, novel_id: str, chapter: int) -> Path:
        return self._reader_project_dir(novel_id) / f"chapter-{chapter:04d}.txt"

    def _reader_manuscript_path(self, novel_id: str) -> Path:
        return self._reader_project_dir(novel_id) / "manuscript.txt"

    def _infer_active_novel_id(
        self,
        kwargs: Dict[str, Any],
        *,
        allow_idle: bool = True,
        suppress_errors: bool = False,
    ) -> str:
        active_candidates = []
        idle_candidates = []
        root = self._output_root(kwargs)
        if root.is_dir():
            for state_path in root.glob("*/tracking/state.json"):
                try:
                    state = json.loads(state_path.read_text(encoding="utf-8"))
                except (OSError, json.JSONDecodeError):
                    continue
                if state.get("status") == "complete":
                    continue
                candidate = _text(state.get("novel_id"))
                if not candidate:
                    continue
                if state.get("active_chapter") is not None:
                    active_candidates.append(candidate)
                elif allow_idle and state.get("status") in {"planning", "writing"}:
                    idle_candidates.append(candidate)
        if len(active_candidates) == 1:
            return active_candidates[0]
        if len(active_candidates) > 1:
            if suppress_errors:
                return ""
            raise ValueError("novel_id is required because multiple Writer projects have active chapters")
        if len(idle_candidates) == 1:
            return idle_candidates[0]
        if len(idle_candidates) > 1:
            if suppress_errors:
                return ""
            raise ValueError("novel_id is required because multiple unfinished Writer projects are available")
        if suppress_errors:
            return ""
        raise ValueError("novel_id is required when no single unfinished Writer project can be inferred")

    def _state_path(self, project_dir: Path) -> Path:
        return project_dir / "tracking" / "state.json"

    @staticmethod
    def _atomic_write(path: Path, content: str) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_name(f".{path.name}.tmp")
        temporary.write_text(content, encoding="utf-8")
        temporary.replace(path)

    def _write_json(self, path: Path, value: Any) -> None:
        self._atomic_write(path, json.dumps(value, ensure_ascii=False, indent=2) + "\n")

    def _load_state(self, novel_id: str, kwargs: Dict[str, Any]) -> tuple[Path, Dict[str, Any]]:
        project_dir = self._project_dir(novel_id, kwargs)
        state_path = self._state_path(project_dir)
        if not state_path.is_file():
            raise ValueError(f"Novel project '{novel_id}' does not exist. Call action='bootstrap' first.")
        state = json.loads(state_path.read_text(encoding="utf-8"))
        if state.get("schema") != STATE_SCHEMA or state.get("novel_id") != novel_id:
            raise ValueError(f"Invalid state file for novel project '{novel_id}'")
        return project_dir, state

    def _save_state(self, project_dir: Path, state: Dict[str, Any]) -> None:
        state["updated_at"] = _now()
        self._write_json(self._state_path(project_dir), state)

    @staticmethod
    def _markdown_body(path: Path) -> str:
        if not path.is_file():
            return ""
        text = path.read_text(encoding="utf-8")
        return re.sub(r"^# [^\n]+\n+", "", text, count=1).strip()

    @classmethod
    def _data_payload(cls, kwargs: Dict[str, Any]) -> Dict[str, Any]:
        """Accept ordinary objects and provider-produced JSON-string objects."""
        raw = kwargs.get("data")
        payload: Dict[str, Any] = {}
        if isinstance(raw, dict):
            payload = dict(raw)
        elif isinstance(raw, str) and raw.strip():
            try:
                decoded = json.loads(raw)
            except json.JSONDecodeError:
                try:
                    decoded = ast.literal_eval(raw)
                except (SyntaxError, ValueError):
                    decoded = _salvage_jsonish_data_payload(raw)
            if isinstance(decoded, dict):
                payload = decoded

        for key in DATA_PAYLOAD_KEYS:
            if key in kwargs and key not in payload and kwargs.get(key) not in (None, "", []):
                payload[key] = kwargs.get(key)
        return payload

    def _bootstrap(self, novel_id: str, kwargs: Dict[str, Any]) -> ToolResult:
        title = _text(kwargs.get("title"))
        brief = _text(kwargs.get("brief"))
        if not title or not brief:
            return ToolResult.fail("title and brief are required for action='bootstrap'")

        target_chars = max(1000, int(kwargs.get("target_chars") or 100000))
        if self._should_enforce_longform_floor(title, brief) and _parse_explicit_length_request(f"{title}\n{brief}") is None:
            target_chars = max(target_chars, 100000)
        chapter_target = max(500, int(kwargs.get("chapter_target_chars") or 4000))
        project_dir = self._project_dir(novel_id, kwargs)
        state_path = self._state_path(project_dir)
        if state_path.exists():
            return ToolResult.fail(
                f"Novel project '{novel_id}' already exists. Use action='status' or action='context' to resume it."
            )

        planned_chapters = max(1, math.ceil(target_chars / chapter_target))
        created_at = _now()
        state: Dict[str, Any] = {
            "schema": STATE_SCHEMA,
            "novel_id": novel_id,
            "title": title,
            "brief": brief,
            "status": "planning",
            "configured": False,
            "target_chars": target_chars,
            "chapter_target_chars": chapter_target,
            "planned_chapters": planned_chapters,
            "total_chars": 0,
            "total_han_chars": 0,
            "completed_chapters": 0,
            "active_chapter": None,
            "open_threads": [],
            "resolved_threads": [],
            "chapters": {},
            "created_at": created_at,
            "updated_at": created_at,
        }

        for folder in ("chapters", "control-cards", "drafts", "tracking"):
            (project_dir / folder).mkdir(parents=True, exist_ok=True)
        self._reader_project_dir(novel_id).mkdir(parents=True, exist_ok=True)
        self._atomic_write(
            project_dir / "00-project-brief.md",
            f"# {title}\n\n## Original brief\n\n{brief}\n\n"
            f"## Delivery contract\n\n- Minimum characters: {target_chars}\n"
            f"- Planned chapters: {planned_chapters}\n- Default chapter target: {chapter_target}\n",
        )
        skeletons = {
            "01-world-bible.md": "World Bible",
            "02-cast-bible.md": "Cast Bible",
            "03-story-architecture.md": "Story Architecture",
            "04-style-guide.md": "Style Guide",
            "05-roadmap.md": "Chapter Roadmap",
            "tracking/continuity.md": "Continuity Ledger",
            "tracking/timeline.md": "Timeline Ledger",
            "tracking/foreshadowing.md": "Foreshadowing Ledger",
        }
        for relative_path, heading in skeletons.items():
            self._atomic_write(project_dir / relative_path, f"# {heading}\n\n")
        self._save_state(project_dir, state)

        return ToolResult.ok(
            f"Bootstrapped '{title}' at {project_dir}. Configure the five project bibles before preparing chapter 1.",
            data=self._public_state(project_dir, state),
        )

    def _configure(self, novel_id: str, kwargs: Dict[str, Any]) -> ToolResult:
        project_dir, state = self._load_state(novel_id, kwargs)
        data = self._data_payload(kwargs)
        documents = {
            "world_bible": ("01-world-bible.md", "World Bible"),
            "cast_bible": ("02-cast-bible.md", "Cast Bible"),
            "story_architecture": ("03-story-architecture.md", "Story Architecture"),
            "style_guide": ("04-style-guide.md", "Style Guide"),
            "roadmap": ("05-roadmap.md", "Chapter Roadmap"),
        }
        updated: list[str] = []
        for key, (relative_path, heading) in documents.items():
            value = _text(data.get(key))
            if not value:
                continue
            self._atomic_write(project_dir / relative_path, f"# {heading}\n\n{value}\n")
            updated.append(key)

        missing = [
            key
            for key, (relative_path, _) in documents.items()
            if not self._markdown_body(project_dir / relative_path)
        ]
        if missing:
            if not updated:
                return ToolResult.fail(
                    "configure requires project documents. Missing: " + ", ".join(missing)
                )
            state["configured"] = False
            state["status"] = "planning"
            self._save_state(project_dir, state)
            return ToolResult.ok(
                "Saved partial project bibles. Missing before drafting can begin: "
                + ", ".join(missing)
                + ". Call configure again with the remaining documents.",
                data={
                    **self._public_state(project_dir, state),
                    "saved_documents": updated,
                    "missing_documents": missing,
                },
            )

        state["configured"] = True
        state["status"] = "writing"
        self._save_state(project_dir, state)
        return ToolResult.ok(
            f"Configured all project bibles for '{state['title']}'. Prepare chapter 1 next.",
            data={
                **self._public_state(project_dir, state),
                "saved_documents": updated or list(documents),
                "missing_documents": [],
            },
        )

    def _prepare_chapter(self, novel_id: str, kwargs: Dict[str, Any]) -> ToolResult:
        project_dir, state = self._load_state(novel_id, kwargs)
        if not state.get("configured"):
            return ToolResult.fail("Configure the project bibles before preparing a chapter.")
        if (
            int(state.get("total_chars", 0)) >= int(state.get("target_chars", 0))
            and int(state.get("completed_chapters", 0)) >= int(state.get("planned_chapters", 0))
        ):
            return ToolResult.fail("The planned delivery target is already met. Call action='audit' instead of opening another chapter.")
        chapter = int(kwargs.get("chapter") or (state.get("completed_chapters", 0) + 1))
        if chapter < 1:
            return ToolResult.fail("chapter must be a positive integer")
        active_chapter = state.get("active_chapter")
        if active_chapter is not None:
            try:
                active_chapter_number = int(active_chapter)
            except (TypeError, ValueError):
                active_chapter_number = 0
            committed_numbers = {int(key) for key in state.get("chapters", {}).keys()}
            if (
                active_chapter_number > 0
                and active_chapter_number not in committed_numbers
                and chapter != active_chapter_number
            ):
                return ToolResult.fail(
                    f"Chapter {active_chapter_number} is prepared but not committed. "
                    f"Finish or materially re-prepare chapter {active_chapter_number} before preparing chapter {chapter}."
                )
        data = self._data_payload(kwargs)
        outline = _text(data.get("outline"))
        title = _text(kwargs.get("title") or data.get("title"))
        if not title and outline:
            title = self._derive_chapter_title(outline, chapter)
        if not outline or not title:
            return ToolResult.fail("title and data.outline are required for action='prepare_chapter'")

        baseline_target_chars = max(500, int(state.get("chapter_target_chars") or 0))
        target_chars = max(
            baseline_target_chars,
            int(data.get("target_chars") or baseline_target_chars),
        )
        delivery_minimum = self._delivery_minimum_chars(state)
        minimum_chars_to_commit = max(350, math.floor(target_chars * 0.7), delivery_minimum)
        card = {
            "chapter": chapter,
            "title": title,
            "outline": outline,
            "scene_beats": _as_list(data.get("scene_beats")),
            "continuity_requirements": _as_list(data.get("continuity_requirements")),
            "relationship_progression": _as_list(data.get("relationship_progression")),
            "opening_hook": _text(data.get("opening_hook")),
            "ending_hook": _text(data.get("ending_hook")),
            "target_chars": target_chars,
            "minimum_chars_to_commit": minimum_chars_to_commit,
            "recommended_draft_chars": max(
                minimum_chars_to_commit,
                math.ceil(minimum_chars_to_commit * 1.15),
            ),
            "prepared_at": _now(),
        }
        forbidden_terms = self._control_card_forbidden_terms(card)
        if forbidden_terms:
            return ToolResult.fail(
                "prepare_chapter control card violates its own continuity requirements. "
                "Remove these forbidden terms from the outline, hooks, and scene beats before preparing again: "
                + ", ".join(forbidden_terms)
            )
        card_path = project_dir / "control-cards" / f"chapter-{chapter:04d}.json"
        self._write_json(card_path, card)
        self._discard_pending_draft(project_dir, chapter)
        state["active_chapter"] = chapter
        state["status"] = "writing"
        self._save_state(project_dir, state)

        context = self._context_payload(project_dir, state, chapter=chapter, card=card)
        return ToolResult.ok(
            self._format_context(context),
            data=context,
        )

    def _commit_chapter(self, novel_id: str, kwargs: Dict[str, Any]) -> ToolResult:
        project_dir, state = self._load_state(novel_id, kwargs)
        if state.get("status") == "complete":
            return ToolResult.fail("This novel project is complete. Start a new project or explicitly revise its files instead of committing more chapters.")
        chapter = int(kwargs.get("chapter") or state.get("active_chapter") or 0)
        if chapter < 1:
            return ToolResult.fail("chapter is required for action='commit_chapter'")
        card_path = project_dir / "control-cards" / f"chapter-{chapter:04d}.json"
        if not card_path.is_file():
            return ToolResult.fail(f"Chapter {chapter} has no control card. Call action='prepare_chapter' first.")
        card = json.loads(card_path.read_text(encoding="utf-8"))
        data = self._data_payload(kwargs)
        pending_draft = self._load_pending_draft(project_dir, chapter)
        append_content = str(data.get("append_content") or "").strip()
        if pending_draft and pending_draft.get("requires_reprepare"):
            return ToolResult.fail(
                f"Chapter {chapter} already exhausted {MAX_QUALITY_GATE_RETRY_ATTEMPTS} quality-gate repair attempts. "
                "Call action='prepare_chapter' again with a materially revised outline/control card before another commit_chapter attempt."
            )
        if append_content:
            if not pending_draft:
                return ToolResult.fail(
                    f"Chapter {chapter} has no preserved rejected draft. Submit the full prose through data.content."
                )
            if str(pending_draft.get("recovery_mode") or "") != PENDING_RECOVERY_APPEND_ONLY:
                return ToolResult.fail(
                    f"Chapter {chapter} requires a full revised chapter through data.content. "
                    "data.append_content is only valid after a length-only rejection that preserved the short draft."
                )
            pending_data = dict(pending_draft.get("data") or {})
            prior_content = str(pending_data.get("content") or "").strip()
            append_content = self._trim_append_only_overlap(prior_content, append_content)
            if not append_content:
                return ToolResult.fail(
                    f"Chapter {chapter} append-only retry only repeated the preserved tail. "
                    "Continue from the first unseen beat after the preserved draft and send new prose through data.append_content."
                )
            pending_data.update(
                {
                    key: value
                    for key, value in data.items()
                    if key != "append_content" and value not in (None, "", [])
                }
            )
            pending_data["content"] = f"{prior_content}\n\n{append_content}".strip()
            data = pending_data
        elif pending_draft and str(pending_draft.get("recovery_mode") or "") == PENDING_RECOVERY_APPEND_ONLY:
            recommended_append_chars = max(1, int(pending_draft.get("recommended_append_chars") or 0))
            content_candidate = str(data.get("content") or "").strip()
            if not content_candidate:
                return ToolResult.fail(
                    f"Chapter {chapter} already has a preserved rejected draft from a length-only quality-gate failure. "
                    "Do not resend metadata alone and do not regenerate the full chapter. "
                    f"Call commit_chapter again with data.append_content containing at least "
                    f"{recommended_append_chars} new non-whitespace characters that continue from the first unseen beat "
                    "after the preserved tail."
                )
        content = str(data.get("content") or "").strip()
        title = _text(
            kwargs.get("title")
            or data.get("title")
            or (pending_draft or {}).get("title")
            or card.get("title")
        )
        content = self._normalize_leading_commit_heading(content, title, chapter)
        supplied_summary = _text(data.get("summary"))
        summary = supplied_summary or self._extractive_summary(content)
        if not content or not title:
            return ToolResult.fail("title and data.content are required to commit a chapter")

        delivery_minimum = self._delivery_minimum_chars(state)
        quality = self._quality_report(
            content,
            int(card.get("target_chars") or state["chapter_target_chars"]),
            delivery_minimum_chars=delivery_minimum,
            prior_content=self._committed_prose(project_dir, state),
        )
        if quality["blocking_issues"]:
            retry_count = int((pending_draft or {}).get("quality_retry_count") or 0) + 1
            exhausted = retry_count >= MAX_QUALITY_GATE_RETRY_ATTEMPTS
            shortage = max(0, int(quality["minimum_chars"]) - int(quality["chars"]))
            length_only = shortage > 0 and len(quality["blocking_issues"]) == 1
            if length_only:
                retry_buffer = max(120, math.ceil(int(quality["minimum_chars"]) * 0.1))
                recommended_append_chars = shortage + retry_buffer
                self._save_pending_draft(
                    project_dir,
                    chapter,
                    title=title,
                    data={**data, "content": content},
                    quality=quality,
                    recommended_append_chars=recommended_append_chars,
                    quality_retry_count=retry_count,
                    blocking_issues=quality["blocking_issues"],
                    recovery_mode=(
                        PENDING_RECOVERY_REPREPARE if exhausted else PENDING_RECOVERY_APPEND_ONLY
                    ),
                    requires_reprepare=exhausted,
                )
                if exhausted:
                    return ToolResult.fail(
                        f"Chapter {chapter} is still short after {retry_count} quality-gate repair attempts. "
                        f"It remains {shortage} non-whitespace characters below the minimum {quality['minimum_chars']}. "
                        "The latest rejected draft was preserved locally. Stop autonomous retries and call "
                        "action='prepare_chapter' again with a materially revised chapter plan before another commit_chapter attempt."
                    )
                return ToolResult.fail(
                    f"Chapter {chapter} is {shortage} non-whitespace characters short. "
                    f"The rejected draft was preserved locally; do not resend the full chapter. "
                    f"Call commit_chapter again with data.append_content containing at least "
                    f"{recommended_append_chars} new non-whitespace characters. "
                    "Continue from the first unseen beat after the preserved tail; do not repeat or lightly "
                    "paraphrase any preserved paragraph. The tool will merge the continuation and re-run every "
                    "quality gate."
                )
            self._save_pending_draft(
                project_dir,
                chapter,
                title=title,
                data={**data, "content": content},
                quality=quality,
                recommended_append_chars=0,
                quality_retry_count=retry_count,
                blocking_issues=quality["blocking_issues"],
                recovery_mode=(
                    PENDING_RECOVERY_REPREPARE if exhausted else PENDING_RECOVERY_FULL_REWRITE
                ),
                requires_reprepare=exhausted,
            )
            if exhausted:
                return ToolResult.fail(
                    f"Chapter {chapter} exhausted {MAX_QUALITY_GATE_RETRY_ATTEMPTS} deterministic quality-gate revision attempts: "
                    + "; ".join(quality["blocking_issues"])
                    + ". The latest rejected draft was preserved locally. Stop autonomous retries and call "
                    "action='prepare_chapter' again with a materially revised outline/control card before another commit_chapter attempt."
                )
            return ToolResult.fail(
                f"Chapter {chapter} failed the deterministic quality gate (attempt {retry_count}/{MAX_QUALITY_GATE_RETRY_ATTEMPTS}): "
                + "; ".join(quality["blocking_issues"])
                + (
                    f". Add at least {shortage} more non-whitespace characters and submit materially revised prose. "
                    "Do not use data.append_content because this was not a length-only rejection."
                    if shortage
                    else ". Correct the reported issue and submit materially revised prose."
                )
                + " The latest rejected draft was preserved locally."
            )

        chapter_path = project_dir / "chapters" / f"chapter-{chapter:04d}.md"
        chapter_text = f"# Chapter {chapter}: {title}\n\n{content}\n"
        self._atomic_write(chapter_path, chapter_text)
        content_hash = hashlib.sha256(chapter_text.encode("utf-8")).hexdigest()

        record = {
            "chapter": chapter,
            "title": title,
            "path": str(chapter_path.relative_to(project_dir)).replace("\\", "/"),
            "chars": quality["chars"],
            "han_chars": quality["han_chars"],
            "sha256": content_hash,
            "summary": summary,
            "summary_source": "model" if supplied_summary else "extractive_fallback",
            "key_events": _as_list(data.get("key_events")),
            "character_updates": _as_list(data.get("character_updates")),
            "relationship_updates": _as_list(data.get("relationship_updates")),
            "timeline_updates": _as_list(data.get("timeline_updates")),
            "opened_threads": _as_list(data.get("opened_threads")),
            "advanced_threads": _as_list(data.get("advanced_threads")),
            "resolved_threads": _as_list(data.get("resolved_threads")),
            "foreshadowing_opened": _as_list(data.get("foreshadowing_opened")),
            "foreshadowing_resolved": _as_list(data.get("foreshadowing_resolved")),
            "quality": quality,
            "committed_at": _now(),
        }
        state["chapters"][str(chapter)] = record
        self._refresh_state_totals(state)
        self._refresh_threads(state)
        state["active_chapter"] = None
        self._append_ledgers(project_dir, record)
        self._discard_pending_draft(project_dir, chapter)
        self._refresh_reader_exports(project_dir, state)
        self._save_state(project_dir, state)

        target_note = (
            " Target met; call action='audit' now."
            if state["total_chars"] >= state["target_chars"]
            else ""
        )
        return ToolResult.ok(
            f"Committed chapter {chapter} ({quality['chars']} chars). Project total: "
            f"{state['total_chars']}/{state['target_chars']} chars across {state['completed_chapters']} chapters."
            f"{target_note}",
            data={"chapter": record, "project": self._public_state(project_dir, state)},
        )

    def _context(self, novel_id: str, kwargs: Dict[str, Any]) -> ToolResult:
        project_dir, state = self._load_state(novel_id, kwargs)
        chapter = int(kwargs.get("chapter") or state.get("active_chapter") or (state["completed_chapters"] + 1))
        card_path = project_dir / "control-cards" / f"chapter-{chapter:04d}.json"
        card = json.loads(card_path.read_text(encoding="utf-8")) if card_path.is_file() else None
        payload = self._context_payload(project_dir, state, chapter=chapter, card=card)
        return ToolResult.ok(self._format_context(payload), data=payload)

    def _status(self, novel_id: str, kwargs: Dict[str, Any]) -> ToolResult:
        project_dir, state = self._load_state(novel_id, kwargs)
        public = self._public_state(project_dir, state)
        return ToolResult.ok(self._format_status(public), data=public)

    def _status_overview(self, kwargs: Dict[str, Any]) -> ToolResult:
        projects = self._project_summaries(self._output_root(kwargs))
        if not projects:
            return ToolResult.ok(
                "No Writer projects exist yet. Call action='bootstrap' to start a new novel project.",
                data={"projects": [], "active_project": None},
            )
        if len(projects) == 1:
            project_dir, state = self._load_state(_text(projects[0]["novel_id"]), kwargs)
            public = self._public_state(project_dir, state)
            return ToolResult.ok(self._format_status(public), data=public)
        lines = ["Multiple Writer projects are available. Pass novel_id to inspect one project:"]
        lines.extend(
            f"- {item['novel_id']}: {item['title']} ({item['status']}, {item['total_chars']}/{item['target_chars']} chars)"
            for item in projects
        )
        return ToolResult.ok("\n".join(lines), data={"projects": projects, "active_project": None})

    def _audit_result(self, novel_id: str, kwargs: Dict[str, Any]) -> ToolResult:
        project_dir, state = self._load_state(novel_id, kwargs)
        audit = self._audit(project_dir, state)
        return ToolResult.ok(self._format_audit(audit), data=audit)

    def _complete(self, novel_id: str, kwargs: Dict[str, Any]) -> ToolResult:
        project_dir, state = self._load_state(novel_id, kwargs)
        audit = self._audit(project_dir, state)
        if state.get("status") == "complete":
            audit["status"] = "complete"
            return ToolResult.ok(
                f"'{state['title']}' is already complete with {audit['disk_total_chars']} verified characters "
                f"across {audit['disk_chapter_count']} chapters. No files were changed.",
                data=audit,
            )
        if not audit["completion_ready"]:
            return ToolResult.fail("Project cannot be completed: " + "; ".join(audit["blocking_issues"]))
        state["status"] = "complete"
        state["active_chapter"] = None
        state["completed_at"] = _now()
        self._save_state(project_dir, state)
        audit["status"] = "complete"
        return ToolResult.ok(
            f"Completed '{state['title']}' with {audit['disk_total_chars']} verified characters "
            f"across {audit['disk_chapter_count']} chapters.",
            data=audit,
        )

    def _list_projects(self, kwargs: Dict[str, Any]) -> ToolResult:
        projects = self._project_summaries(self._output_root(kwargs))
        lines = ["Writer projects:"] + [
            f"- {item['novel_id']}: {item['title']} ({item['status']}, "
            f"{item['total_chars']}/{item['target_chars']} chars)"
            for item in projects
        ]
        if not projects:
            lines.append("- none")
        return ToolResult.ok("\n".join(lines), data={"projects": projects})

    def _project_summaries(self, root: Path) -> list[Dict[str, Any]]:
        projects = []
        if root.is_dir():
            for state_path in sorted(root.glob("*/tracking/state.json")):
                try:
                    state = json.loads(state_path.read_text(encoding="utf-8"))
                    projects.append(self._public_state(state_path.parent.parent, state))
                except (OSError, json.JSONDecodeError, ValueError):
                    continue
        return projects

    @staticmethod
    def _delivery_minimum_chars(state: Dict[str, Any]) -> int:
        remaining_chars = max(0, int(state["target_chars"]) - int(state["total_chars"]))
        remaining_planned_chapters = max(
            1,
            int(state["planned_chapters"]) - int(state["completed_chapters"]),
        )
        return math.ceil(remaining_chars / remaining_planned_chapters)

    @staticmethod
    def _title_from_outline(outline: str) -> str:
        match = re.search(
            r"第\s*[一二三四五六七八九十百〇零\d]+\s*章\s*[《「\"]([^》」\"]+)[》」\"]",
            str(outline or ""),
        )
        return _text(match.group(1)) if match else ""

    @classmethod
    def _derive_chapter_title(cls, outline: str, chapter: int) -> str:
        explicit = cls._title_from_outline(outline)
        if explicit:
            return explicit

        normalized = re.sub(r"\s+", " ", str(outline or "")).strip()
        if normalized:
            preview = normalized[:160]
            for pattern in (
                r"(?:标题|章名)\s*[:：]\s*([^\n。！？]{1,40})",
                r"(?:chapter|chap\.?)\s*\d+\s*[:：\-]\s*([^\n]{1,40})",
                r"^[《「『“\"]([^》」』”\"]{1,40})[》」』”\"]",
            ):
                match = re.search(pattern, preview, flags=re.IGNORECASE)
                if match:
                    return _text(match.group(1))

            candidate = re.split(r"[。！？；\n]", normalized, maxsplit=1)[0].strip()
            candidate = re.sub(
                r"^(?:第\s*[一二三四五六七八九十百〇零\d]+\s*[章节回卷集]|chapter\s*\d+)\s*[:：\-]?\s*",
                "",
                candidate,
                flags=re.IGNORECASE,
            ).strip()
            candidate = re.split(r"[，,、:：\-\(\)（）\[\]【】]", candidate, maxsplit=1)[0].strip()
            candidate = candidate.strip("《》「」『』“”\"'<>〈〉")
            compact = re.sub(r"\s+", "", candidate)
            if 2 <= len(compact) <= 20:
                return candidate

        return f"第{chapter}章"

    @staticmethod
    def _extractive_summary(content: str, limit: int = 320) -> str:
        normalized = re.sub(r"\s+", " ", str(content or "")).strip()
        if len(normalized) <= limit:
            return normalized
        excerpt = normalized[:limit].rstrip("，、；： ")
        sentence_end = max(excerpt.rfind("。"), excerpt.rfind("！"), excerpt.rfind("？"))
        if sentence_end >= max(80, limit // 2):
            excerpt = excerpt[: sentence_end + 1]
        return excerpt + ("" if excerpt.endswith(("。", "！", "？")) else "……")

    @staticmethod
    def _pending_draft_path(project_dir: Path, chapter: int) -> Path:
        return project_dir / "drafts" / f"chapter-{chapter:04d}.json"

    def _load_pending_draft(self, project_dir: Path, chapter: int) -> Optional[Dict[str, Any]]:
        path = self._pending_draft_path(project_dir, chapter)
        if not path.is_file():
            return None
        value = json.loads(path.read_text(encoding="utf-8"))
        return value if isinstance(value, dict) else None

    def _save_pending_draft(
        self,
        project_dir: Path,
        chapter: int,
        *,
        title: str,
        data: Dict[str, Any],
        quality: Dict[str, Any],
        recommended_append_chars: int,
        quality_retry_count: int,
        blocking_issues: list[str],
        recovery_mode: str,
        requires_reprepare: bool,
    ) -> None:
        self._write_json(
            self._pending_draft_path(project_dir, chapter),
            {
                "chapter": chapter,
                "title": title,
                "data": data,
                "quality": quality,
                "recommended_append_chars": int(recommended_append_chars),
                "quality_retry_count": max(1, int(quality_retry_count)),
                "max_quality_retry_attempts": MAX_QUALITY_GATE_RETRY_ATTEMPTS,
                "blocking_issues": [str(item).strip() for item in blocking_issues if str(item).strip()],
                "recovery_mode": str(recovery_mode or "").strip() or PENDING_RECOVERY_FULL_REWRITE,
                "requires_reprepare": bool(requires_reprepare),
                "saved_at": _now(),
            },
        )

    @staticmethod
    def _trim_append_only_overlap(prior_content: str, append_content: str) -> str:
        prior_paragraphs = [
            paragraph.strip()
            for paragraph in re.split(r"\n\s*\n+", str(prior_content or "").strip())
            if paragraph.strip()
        ]
        append_paragraphs = [
            paragraph.strip()
            for paragraph in re.split(r"\n\s*\n+", str(append_content or "").strip())
            if paragraph.strip()
        ]
        if not prior_paragraphs or not append_paragraphs:
            return str(append_content or "").strip()

        prior_normalized = [_normalize_match_text(paragraph) for paragraph in prior_paragraphs]
        append_normalized = [_normalize_match_text(paragraph) for paragraph in append_paragraphs]

        overlap = 0
        max_overlap = min(len(prior_normalized), len(append_normalized), 24)
        for candidate in range(max_overlap, 0, -1):
            if prior_normalized[-candidate:] == append_normalized[:candidate]:
                overlap = candidate
                break

        recent_paragraphs = {
            normalized
            for normalized in prior_normalized[-24:]
            if normalized
        }
        trimmed = list(append_paragraphs[overlap:])
        while trimmed and _normalize_match_text(trimmed[0]) in recent_paragraphs:
            trimmed.pop(0)
        return "\n\n".join(trimmed).strip()

    def _discard_pending_draft(self, project_dir: Path, chapter: int) -> None:
        path = self._pending_draft_path(project_dir, chapter)
        if path.is_file():
            path.unlink()

    @staticmethod
    def _normalize_leading_commit_heading(content: str, title: str, chapter: int) -> str:
        text = str(content or "").strip()
        if not text:
            return ""

        lines = text.splitlines()
        if not lines:
            return text

        first_line = re.sub(r"^#+\s*", "", lines[0]).strip()
        normalized_first = re.sub(r"\s+", "", first_line).strip("《》「」『』\"'<>【】[]()（）:：-—")
        normalized_title = re.sub(r"\s+", "", str(title or "")).strip("《》「」『』\"'<>【】[]()（）:：-—")
        if not normalized_title:
            return text

        matches_title = normalized_first == normalized_title
        chapter_title_match = re.match(
            r"^(?:第\s*[一二三四五六七八九十百零〇\d]+\s*[章节回卷集]|chapter\s*\d+)\s*[:：\-]?\s*(.+)$",
            first_line,
            flags=re.IGNORECASE,
        )
        matches_chapter_heading = False
        if chapter_title_match:
            normalized_heading_title = re.sub(r"\s+", "", str(chapter_title_match.group(1) or "")).strip(
                "《》「」『』\"'<>【】[]()（）:：-—"
            )
            matches_chapter_heading = normalized_heading_title == normalized_title

        if not matches_title and not matches_chapter_heading:
            return text

        remainder = "\n".join(lines[1:]).lstrip()
        return remainder.strip() if remainder else text

    @staticmethod
    def _chapter_prose_from_markdown(text: str) -> str:
        parts = str(text or "").split("\n", 2)
        if len(parts) == 3 and parts[0].startswith("#"):
            return parts[2].rstrip("\n")
        return str(text or "").rstrip("\n")

    @staticmethod
    def _render_reader_chapter_text(chapter: int, title: str, content: str) -> str:
        return f"Chapter {chapter}: {title}\n\n{str(content or '').rstrip()}\n"

    @staticmethod
    def _render_reader_manuscript(title: str, chapter_texts: list[str]) -> str:
        parts = [str(title or "").strip(), ""]
        parts.extend(text.rstrip() for text in chapter_texts if str(text or "").strip())
        return "\n\n".join(parts).rstrip() + "\n"

    def _refresh_reader_exports(self, project_dir: Path, state: Dict[str, Any]) -> None:
        novel_id = _text(state.get("novel_id"))
        reader_dir = self._reader_project_dir(novel_id)
        reader_dir.mkdir(parents=True, exist_ok=True)
        rendered_chapters = []
        for _, record in sorted(state.get("chapters", {}).items(), key=lambda item: int(item[0])):
            relative_path = str(record.get("path", "") or "").strip()
            if not relative_path:
                continue
            chapter_path = project_dir / relative_path
            if not chapter_path.is_file():
                continue
            prose = self._chapter_prose_from_markdown(chapter_path.read_text(encoding="utf-8"))
            chapter_text = self._render_reader_chapter_text(int(record["chapter"]), _text(record.get("title")), prose)
            self._atomic_write(self._reader_chapter_path(novel_id, int(record["chapter"])), chapter_text)
            rendered_chapters.append(chapter_text)
        if rendered_chapters:
            self._atomic_write(
                self._reader_manuscript_path(novel_id),
                self._render_reader_manuscript(_text(state.get("title")), rendered_chapters),
            )

    @staticmethod
    def _quality_report(
        content: str,
        target_chars: int,
        *,
        delivery_minimum_chars: int = 0,
        prior_content: str = "",
    ) -> Dict[str, Any]:
        chars = sum(1 for char in content if not char.isspace())
        han_chars = len(re.findall(r"[\u3400-\u4dbf\u4e00-\u9fff]", content))
        paragraphs = [line.strip() for line in content.splitlines() if len(line.strip()) >= 20]
        duplicate_count = max(0, len(paragraphs) - len(set(paragraphs)))
        duplicate_ratio = duplicate_count / max(1, len(paragraphs))
        placeholders = sorted(set(re.findall(r"(?i)\b(?:TODO|TBD|PLACEHOLDER)\b|\[(?:to be written|pending)\]|待补|省略", content)))
        tic_counts = {tic: content.count(tic) for tic in STYLE_TICS if content.count(tic)}
        tic_limit = max(2, math.ceil(chars / 1000) * 2)
        overused_tics = {tic: count for tic, count in tic_counts.items() if count > tic_limit}
        tic_density = sum(tic_counts.values()) / max(chars, 1) * 1000
        normalized_content = re.sub(r"\s+", "", content)
        normalized_prior = re.sub(r"\s+", "", prior_content)
        passage_size = 64
        duplicate_passage = ""
        if len(normalized_content) >= passage_size and len(normalized_prior) >= passage_size:
            prior_passages = {
                normalized_prior[index : index + passage_size]
                for index in range(len(normalized_prior) - passage_size + 1)
            }
            for index in range(len(normalized_content) - passage_size + 1):
                candidate = normalized_content[index : index + passage_size]
                if candidate in prior_passages:
                    duplicate_passage = candidate
                    break
        control_card_minimum = max(350, math.floor(target_chars * 0.7))
        minimum = max(control_card_minimum, int(delivery_minimum_chars or 0))
        issues = []
        if chars < minimum:
            issues.append(f"only {chars} characters; minimum required for the planned delivery is {minimum}")
        if duplicate_ratio > 0.12:
            issues.append(f"duplicate paragraph ratio is {duplicate_ratio:.1%}")
        if placeholders:
            issues.append("placeholder text remains: " + ", ".join(placeholders[:5]))
        if overused_tics:
            issues.append(
                "overused generated-prose tics: "
                + ", ".join(f"{tic}={count}" for tic, count in sorted(overused_tics.items()))
            )
        if tic_density > 10:
            issues.append(f"generated-prose tic density is {tic_density:.1f} per 1000 characters")
        if duplicate_passage:
            issues.append("reuses a 64-character passage from an earlier chapter")
        return {
            "chars": chars,
            "han_chars": han_chars,
            "target_chars": target_chars,
            "minimum_chars": minimum,
            "control_card_minimum_chars": control_card_minimum,
            "delivery_minimum_chars": int(delivery_minimum_chars or 0),
            "duplicate_paragraphs": duplicate_count,
            "duplicate_ratio": round(duplicate_ratio, 4),
            "placeholders": placeholders,
            "style_tic_counts": tic_counts,
            "style_tic_density_per_1000": round(tic_density, 2),
            "overused_style_tics": overused_tics,
            "cross_chapter_duplicate_passage": duplicate_passage,
            "blocking_issues": issues,
            "passed": not issues,
        }

    @staticmethod
    def _committed_prose(project_dir: Path, state: Dict[str, Any]) -> str:
        prose_parts = []
        for record in state.get("chapters", {}).values():
            relative_path = str(record.get("path", "") or "").strip()
            if not relative_path:
                continue
            path = project_dir / relative_path
            if not path.is_file():
                continue
            prose_parts.append(SerialNovelTool._chapter_prose_from_markdown(path.read_text(encoding="utf-8")))
        return "\n".join(prose_parts)

    @staticmethod
    def _refresh_state_totals(state: Dict[str, Any]) -> None:
        records = list(state.get("chapters", {}).values())
        state["total_chars"] = sum(int(item.get("chars", 0)) for item in records)
        state["total_han_chars"] = sum(int(item.get("han_chars", 0)) for item in records)
        state["completed_chapters"] = len(records)

    @staticmethod
    def _unique_text(values: Iterable[Any]) -> list[str]:
        result = []
        seen = set()
        for value in values:
            item = _text(value)
            if not item or item in seen:
                continue
            result.append(item)
            seen.add(item)
        return result

    def _refresh_threads(self, state: Dict[str, Any]) -> None:
        opened = []
        resolved = []
        for _, record in sorted(state.get("chapters", {}).items(), key=lambda item: int(item[0])):
            opened.extend(record.get("opened_threads", []))
            resolved.extend(record.get("resolved_threads", []))
        resolved_text = self._unique_text(resolved)
        state["resolved_threads"] = resolved_text
        state["open_threads"] = [item for item in self._unique_text(opened) if item not in set(resolved_text)]

    def _append_ledgers(self, project_dir: Path, record: Dict[str, Any]) -> None:
        chapter = record["chapter"]
        continuity = [f"## Chapter {chapter}: {record['title']}", "", record["summary"], ""]
        for label, key in (
            ("Key events", "key_events"),
            ("Character changes", "character_updates"),
            ("Relationship changes", "relationship_updates"),
        ):
            values = record.get(key, [])
            if values:
                continuity.extend([f"### {label}", *[f"- {_text(item)}" for item in values], ""])
        self._replace_chapter_section(project_dir / "tracking" / "continuity.md", chapter, continuity)

        timeline = [f"## Chapter {chapter}: {record['title']}", ""]
        timeline.extend([f"- {_text(item)}" for item in record.get("timeline_updates", [])] or ["- No explicit timeline update."])
        timeline.append("")
        self._replace_chapter_section(project_dir / "tracking" / "timeline.md", chapter, timeline)

        foreshadowing = [f"## Chapter {chapter}: {record['title']}", ""]
        foreshadowing.extend([f"- Opened: {_text(item)}" for item in record.get("foreshadowing_opened", [])])
        foreshadowing.extend([f"- Resolved: {_text(item)}" for item in record.get("foreshadowing_resolved", [])])
        if len(foreshadowing) == 2:
            foreshadowing.append("- No foreshadowing update.")
        foreshadowing.append("")
        self._replace_chapter_section(project_dir / "tracking" / "foreshadowing.md", chapter, foreshadowing)

    def _replace_chapter_section(self, path: Path, chapter: int, lines: list[str]) -> None:
        existing = path.read_text(encoding="utf-8") if path.is_file() else f"# {path.stem.title()}\n\n"
        marker = f"## Chapter {chapter}:"
        start = existing.find(marker)
        if start >= 0:
            next_start = existing.find("\n## Chapter ", start + len(marker))
            existing = existing[:start] + (existing[next_start + 1 :] if next_start >= 0 else "")
        section = "\n".join(lines).rstrip() + "\n"
        self._atomic_write(path, existing.rstrip() + "\n\n" + section)

    def _public_state(self, project_dir: Path, state: Dict[str, Any]) -> Dict[str, Any]:
        remaining = max(0, int(state["target_chars"]) - int(state["total_chars"]))
        next_chapter = max([int(value) for value in state.get("chapters", {})] or [0]) + 1
        reader_dir = self._reader_project_dir(state["novel_id"])
        reader_manuscript = self._reader_manuscript_path(state["novel_id"])
        return {
            "novel_id": state["novel_id"],
            "title": state["title"],
            "status": state["status"],
            "configured": bool(state.get("configured")),
            "project_dir": str(project_dir),
            "reader_project_dir": str(reader_dir),
            "reader_manuscript_path": str(reader_manuscript),
            "target_chars": int(state["target_chars"]),
            "total_chars": int(state["total_chars"]),
            "total_han_chars": int(state.get("total_han_chars", 0)),
            "remaining_chars": remaining,
            "planned_chapters": int(state["planned_chapters"]),
            "completed_chapters": int(state["completed_chapters"]),
            "active_chapter": state.get("active_chapter"),
            "next_chapter": next_chapter,
            "open_threads": list(state.get("open_threads", [])),
            "updated_at": state["updated_at"],
        }

    def _context_payload(
        self,
        project_dir: Path,
        state: Dict[str, Any],
        *,
        chapter: int,
        card: Optional[Dict[str, Any]],
    ) -> Dict[str, Any]:
        ordered = sorted(state.get("chapters", {}).values(), key=lambda item: int(item["chapter"]))
        recent = ordered[-3:]
        bibles = {}
        for name in ("01-world-bible.md", "02-cast-bible.md", "03-story-architecture.md", "04-style-guide.md"):
            path = project_dir / name
            text = path.read_text(encoding="utf-8") if path.is_file() else ""
            bibles[name] = text[:4000]
        minimum_chars_to_commit = max(
            int((card or {}).get("minimum_chars_to_commit") or 0),
            self._delivery_minimum_chars(state),
        )
        recommended_draft_chars = max(
            int((card or {}).get("recommended_draft_chars") or 0),
            math.ceil(minimum_chars_to_commit * 1.15),
        )
        pending_draft = self._load_pending_draft(project_dir, chapter)
        pending_content = str(((pending_draft or {}).get("data") or {}).get("content") or "")
        return {
            "project": self._public_state(project_dir, state),
            "chapter": chapter,
            "control_card": card,
            "minimum_chars_to_commit": minimum_chars_to_commit,
            "recommended_draft_chars": recommended_draft_chars,
            "pending_draft": (
                {
                    "chars": int((pending_draft.get("quality") or {}).get("chars") or 0),
                    "minimum_chars": int(
                        (pending_draft.get("quality") or {}).get("minimum_chars") or minimum_chars_to_commit
                    ),
                    "recommended_append_chars": int(pending_draft.get("recommended_append_chars") or 0),
                    "quality_retry_count": int(pending_draft.get("quality_retry_count") or 0),
                    "max_quality_retry_attempts": int(
                        pending_draft.get("max_quality_retry_attempts") or MAX_QUALITY_GATE_RETRY_ATTEMPTS
                    ),
                    "blocking_issues": [
                        str(item).strip()
                        for item in (pending_draft.get("blocking_issues") or [])
                        if str(item).strip()
                    ],
                    "recovery_mode": str(pending_draft.get("recovery_mode") or "").strip(),
                    "requires_reprepare": bool(pending_draft.get("requires_reprepare")),
                    "content_tail": pending_content[-1600:],
                }
                if pending_draft
                else None
            ),
            "recent_chapters": [
                {
                    "chapter": item["chapter"],
                    "title": item["title"],
                    "summary": item["summary"],
                    "key_events": item.get("key_events", []),
                    "relationship_updates": item.get("relationship_updates", []),
                }
                for item in recent
            ],
            "open_threads": list(state.get("open_threads", [])),
            "bibles": bibles,
        }

    @staticmethod
    def _control_card_forbidden_terms(card: Dict[str, Any]) -> list[str]:
        forbidden_terms = _extract_forbidden_terms(card.get("continuity_requirements") or [])
        if not forbidden_terms:
            return []
        card_text = "\n".join(
            [
                _text(card.get("title")),
                _text(card.get("outline")),
                _text(card.get("opening_hook")),
                _text(card.get("ending_hook")),
                *[_text(item) for item in _as_list(card.get("scene_beats"))],
                *[_text(item) for item in _as_list(card.get("relationship_progression"))],
            ]
        )
        normalized_card_text = _normalize_match_text(card_text)
        violations: list[str] = []
        for term in forbidden_terms:
            if _normalize_match_text(term) and _normalize_match_text(term) in normalized_card_text:
                violations.append(term)
        return violations

    @staticmethod
    def _should_enforce_longform_floor(title: str, brief: str) -> bool:
        combined = f"{title}\n{brief}".lower()
        if any(marker in combined for marker in SHORTFORM_BRIEF_MARKERS):
            return False
        return any(marker in combined for marker in LONGFORM_BRIEF_MARKERS)

    @staticmethod
    def _format_context(payload: Dict[str, Any]) -> str:
        project = payload["project"]
        lines = [
            f"Novel context: {project['title']} ({project['novel_id']})",
            f"Progress: {project['total_chars']}/{project['target_chars']} chars; next chapter {payload['chapter']}",
            f"Minimum to commit: {payload['minimum_chars_to_commit']} non-whitespace characters",
            f"Recommended draft size: {payload['recommended_draft_chars']} non-whitespace characters",
            f"Open threads: {', '.join(payload['open_threads']) or 'none'}",
        ]
        card = payload.get("control_card")
        if card:
            lines.extend(
                [
                    f"Control card: Chapter {card['chapter']} - {card['title']}",
                    f"Outline: {card['outline']}",
                    f"Scene beats: {'; '.join(_text(item) for item in card.get('scene_beats', [])) or 'not specified'}",
                    (
                        "Continuity requirements: "
                        + (" | ".join(_text(item) for item in card.get("continuity_requirements", [])) or "none")
                    ),
                    f"Target: {card['target_chars']} chars",
                    f"Ending hook: {card.get('ending_hook') or 'not specified'}",
                    (
                        "Commit rule: draft and count the complete chapter before commit_chapter; "
                        f"aim for at least {payload['recommended_draft_chars']} non-whitespace characters. "
                        "If a length-only rejection preserves the draft, send only data.append_content starting "
                        "after the preserved tail."
                    ),
                ]
            )
        pending = payload.get("pending_draft")
        if pending:
            if pending["requires_reprepare"]:
                lines.append(
                    f"Preserved rejected draft: {pending['chars']}/{pending['minimum_chars']} chars after "
                    f"{pending['quality_retry_count']}/{pending['max_quality_retry_attempts']} failed repair attempts. "
                    "Do not call commit_chapter again yet; call prepare_chapter with a materially revised outline/control card first."
                )
            elif pending["recovery_mode"] == PENDING_RECOVERY_APPEND_ONLY:
                lines.append(
                    f"Preserved rejected draft: {pending['chars']}/{pending['minimum_chars']} chars. "
                    f"Resume with data.append_content of at least {pending['recommended_append_chars']} new characters; "
                    "do not resend the full chapter, and do not repeat or lightly paraphrase any preserved paragraph."
                )
            else:
                lines.append(
                    f"Preserved rejected draft: {pending['chars']}/{pending['minimum_chars']} chars. "
                    f"Revise the full chapter and recommit it. Repair attempt "
                    f"{pending['quality_retry_count']}/{pending['max_quality_retry_attempts']} is already recorded."
                )
            if pending["blocking_issues"]:
                lines.append("Latest blocking issues:")
                lines.extend(f"- {item}" for item in pending["blocking_issues"])
            lines.extend(
                [
                    "Boundary excerpt from the preserved tail for continuity only; continue after it and do not copy it:",
                    pending["content_tail"][-240:],
                ]
            )
        if payload["recent_chapters"]:
            lines.append("Recent chapter summaries:")
            lines.extend(
                f"- {item['chapter']} {item['title']}: {item['summary']}" for item in payload["recent_chapters"]
            )
        lines.append("Full structured bibles and control card are available in this tool result's data.")
        return "\n".join(lines)

    @staticmethod
    def _format_status(state: Dict[str, Any]) -> str:
        return (
            f"{state['title']} [{state['status']}]\n"
            f"Project: {state['project_dir']}\n"
            f"Readable TXT: {state['reader_project_dir']}\n"
            f"Merged manuscript: {state['reader_manuscript_path']}\n"
            f"Progress: {state['total_chars']}/{state['target_chars']} chars "
            f"({state['completed_chapters']} chapters; {state['remaining_chars']} remaining)\n"
            f"Next chapter: {state['next_chapter']}\n"
            f"Open threads: {', '.join(state['open_threads']) or 'none'}"
        )

    def _audit(self, project_dir: Path, state: Dict[str, Any]) -> Dict[str, Any]:
        disk_records = []
        mismatches = []
        novel_id = _text(state.get("novel_id"))
        rendered_chapters = []
        for key, record in sorted(state.get("chapters", {}).items(), key=lambda item: int(item[0])):
            path = project_dir / record["path"]
            if not path.is_file():
                mismatches.append(f"chapter {key} file is missing")
                continue
            content = path.read_text(encoding="utf-8")
            digest = hashlib.sha256(content.encode("utf-8")).hexdigest()
            prose = self._chapter_prose_from_markdown(content)
            chars = sum(1 for char in prose if not char.isspace())
            if digest != record.get("sha256"):
                mismatches.append(f"chapter {key} changed after commit")
            if chars != int(record.get("chars", 0)):
                mismatches.append(f"chapter {key} character count differs from state")
            reader_chapter_path = self._reader_chapter_path(novel_id, int(key))
            expected_reader_text = self._render_reader_chapter_text(int(key), _text(record.get("title")), prose)
            if not reader_chapter_path.is_file():
                mismatches.append(f"reader export for chapter {key} is missing")
            elif reader_chapter_path.read_text(encoding="utf-8") != expected_reader_text:
                mismatches.append(f"reader export for chapter {key} differs from committed prose")
            rendered_chapters.append(expected_reader_text)
            disk_records.append((int(key), chars))

        numbers = [number for number, _ in disk_records]
        missing_sequence = [number for number in range(1, max(numbers, default=0) + 1) if number not in numbers]
        if missing_sequence:
            mismatches.append("missing chapter numbers: " + ", ".join(map(str, missing_sequence)))
        reader_manuscript_path = self._reader_manuscript_path(novel_id)
        if rendered_chapters:
            expected_manuscript = self._render_reader_manuscript(_text(state.get("title")), rendered_chapters)
            if not reader_manuscript_path.is_file():
                mismatches.append("merged reader manuscript is missing")
            elif reader_manuscript_path.read_text(encoding="utf-8") != expected_manuscript:
                mismatches.append("merged reader manuscript differs from committed prose")
        disk_total = sum(chars for _, chars in disk_records)
        blockers = list(mismatches)
        if not state.get("configured"):
            blockers.append("project bibles are not configured")
        if disk_total < int(state["target_chars"]):
            blockers.append(f"verified total is {disk_total}/{state['target_chars']} characters")
        active_chapter = state.get("active_chapter")
        overrun_control_card = (
            active_chapter is not None
            and disk_total >= int(state["target_chars"])
            and int(active_chapter) > max(numbers, default=0)
        )
        if active_chapter is not None and not overrun_control_card:
            blockers.append(f"chapter {state['active_chapter']} is prepared but not committed")
        return {
            "novel_id": state["novel_id"],
            "title": state["title"],
            "status": state["status"],
            "project_dir": str(project_dir),
            "reader_project_dir": str(self._reader_project_dir(novel_id)),
            "reader_manuscript_path": str(reader_manuscript_path),
            "target_chars": int(state["target_chars"]),
            "disk_total_chars": disk_total,
            "disk_chapter_count": len(disk_records),
            "state_total_chars": int(state["total_chars"]),
            "mismatches": mismatches,
            "blocking_issues": blockers,
            "ignored_overrun_control_card": int(active_chapter) if overrun_control_card else None,
            "completion_ready": not blockers,
        }

    @staticmethod
    def _format_audit(audit: Dict[str, Any]) -> str:
        lines = [
            f"Audit: {audit['title']}",
            f"Readable TXT: {audit['reader_project_dir']}",
            f"Verified files: {audit['disk_chapter_count']} chapters, "
            f"{audit['disk_total_chars']}/{audit['target_chars']} characters",
            f"Completion ready: {'yes' if audit['completion_ready'] else 'no'}",
        ]
        if audit["blocking_issues"]:
            lines.append("Blocking issues:")
            lines.extend(f"- {item}" for item in audit["blocking_issues"])
        return "\n".join(lines)

    def get_execution_message(self, action: str = "", novel_id: str = "", **_: Any) -> str:
        label = _text(novel_id) or "writer project"
        return f"Running serial novel action '{_text(action) or 'status'}' for {label}"
