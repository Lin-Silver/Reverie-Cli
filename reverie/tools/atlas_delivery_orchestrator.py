"""
Atlas Delivery Orchestrator Tool.

This tool is purpose-built for Reverie-Atlas. It turns Atlas's
document-driven workflow into durable project artifacts under
`artifacts/atlas/` so the mode can resume, continue, and close work based on
real delivery state rather than conversational momentum alone.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
import json
import re
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

from .base import BaseTool, ToolResult


ATLAS_ARTIFACTS_DIR = "artifacts/atlas"
DEFAULT_MASTER_DOCUMENT_PATH = "artifacts/Master Document.md"
DEFAULT_TASK_PATH = "artifacts/task.md"
DEFAULT_STATE_PATH = f"{ATLAS_ARTIFACTS_DIR}/atlas_state.json"
DEFAULT_CHARTER_PATH = f"{ATLAS_ARTIFACTS_DIR}/delivery_charter.md"
DEFAULT_TRACKER_PATH = f"{ATLAS_ARTIFACTS_DIR}/delivery_tracker.md"
DEFAULT_DOCUMENT_MANIFEST_JSON_PATH = f"{ATLAS_ARTIFACTS_DIR}/document_manifest.json"
DEFAULT_DOCUMENT_MANIFEST_MD_PATH = f"{ATLAS_ARTIFACTS_DIR}/document_manifest.md"
DEFAULT_RESUME_INDEX_PATH = f"{ATLAS_ARTIFACTS_DIR}/resume_index.md"
DEFAULT_HANDOFF_PATH = f"{ATLAS_ARTIFACTS_DIR}/handoff_summary.md"
DEFAULT_FINAL_REPORT_PATH = f"{ATLAS_ARTIFACTS_DIR}/final_delivery_report.md"

HEADING_RE = re.compile(r"^(?P<level>#{1,6})\s+(?P<title>.+?)\s*$")
NON_ALNUM_RE = re.compile(r"[^a-z0-9]+")
WHITESPACE_RE = re.compile(r"\s+")

SLICE_STATUSES = {"planned", "in_progress", "completed", "blocked", "cancelled"}
BLOCKER_STATUSES = {"open", "resolved"}
BLOCKER_SEVERITIES = {"low", "medium", "high", "critical"}
COMPLEXITY_TIERS = {"tier1", "tier2", "tier3", "tier4"}
DELIVERY_MODES = {
    "research_only",
    "documentation_only",
    "full_delivery",
    "session_continuation",
}


def _now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _clean_text(value: Any) -> str:
    return str(value or "").strip()


def _clean_multiline_text(value: Any) -> str:
    text = str(value or "").replace("\r\n", "\n").replace("\r", "\n").strip()
    lines = [line.rstrip() for line in text.splitlines()]
    while lines and not lines[0]:
        lines.pop(0)
    while lines and not lines[-1]:
        lines.pop()
    return "\n".join(lines)


def _normalize_bool(value: Any, default: bool = False) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    if isinstance(value, str):
        lowered = value.strip().lower()
        if lowered in {"1", "true", "yes", "on"}:
            return True
        if lowered in {"0", "false", "no", "off"}:
            return False
    return default


def _normalize_list(value: Any) -> List[str]:
    if value is None:
        return []
    if isinstance(value, (list, tuple, set)):
        return [_clean_multiline_text(item) for item in value if _clean_multiline_text(item)]
    if isinstance(value, str):
        text = value.strip()
        if not text:
            return []
        if text.startswith("[") and text.endswith("]"):
            try:
                parsed = json.loads(text)
            except Exception:
                parsed = None
            if isinstance(parsed, list):
                return [_clean_multiline_text(item) for item in parsed if _clean_multiline_text(item)]
        if "\n" in text:
            return [_clean_multiline_text(part) for part in text.splitlines() if _clean_multiline_text(part)]
        return [_clean_multiline_text(part) for part in text.split(",") if _clean_multiline_text(part)]
    return [_clean_multiline_text(value)] if _clean_multiline_text(value) else []


def _normalize_unique_list(value: Any) -> List[str]:
    seen: set[str] = set()
    ordered: List[str] = []
    for item in _normalize_list(value):
        lowered = item.casefold()
        if lowered in seen:
            continue
        seen.add(lowered)
        ordered.append(item)
    return ordered


def _slugify(value: str, fallback: str = "item") -> str:
    lowered = value.strip().lower()
    slug = NON_ALNUM_RE.sub("-", lowered).strip("-")
    return slug or fallback


def _anchorify(value: str) -> str:
    slug = _slugify(value, fallback="section")
    return f"#{slug}"


def _word_count(text: str) -> int:
    if not text.strip():
        return 0
    return len(WHITESPACE_RE.split(text.strip()))


def _truncate(text: str, limit: int = 180) -> str:
    cleaned = " ".join(str(text or "").split())
    if len(cleaned) <= limit:
        return cleaned
    return cleaned[: max(0, limit - 3)].rstrip() + "..."


def _ensure_parent(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)


def _safe_json_dump(payload: Dict[str, Any], path: Path) -> None:
    _ensure_parent(path)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")


def _status_icon(status: str) -> str:
    return {
        "planned": "[ ]",
        "in_progress": "[/]",
        "completed": "[x]",
        "blocked": "[!]",
        "cancelled": "[-]",
    }.get(status, "[ ]")


def _blocker_icon(status: str) -> str:
    return {"open": "[!]", "resolved": "[x]"}.get(status, "[!]")


def _format_bullets(items: Iterable[str]) -> str:
    items = [item for item in items if _clean_multiline_text(item)]
    if not items:
        return "- None"
    return "\n".join(f"- {item}" for item in items)


def _maybe_relativize(path: Path, root: Path) -> str:
    try:
        return str(path.relative_to(root))
    except ValueError:
        return str(path)


def _stable_sort_strings(items: Iterable[str]) -> List[str]:
    return sorted((_clean_multiline_text(item) for item in items if _clean_multiline_text(item)), key=str.casefold)


def _normalize_status(status: Any, *, default: str, allowed: set[str]) -> str:
    value = str(status or "").strip().lower()
    return value if value in allowed else default


def _normalize_path_strings(values: Any) -> List[str]:
    return [_clean_text(item) for item in _normalize_unique_list(values) if _clean_text(item)]


def _default_success_criteria() -> List[str]:
    return [
        "Confirmed document baseline exists and is synchronized with the delivered code.",
        "Implementation slices are completed or explicitly cancelled with justification.",
        "Verification evidence exists for the delivered behavior.",
    ]


def _default_constraints() -> List[str]:
    return [
        "Keep all Atlas delivery artifacts under artifacts/atlas.",
        "Do not treat intermediate progress summaries as completion.",
        "Only emit a final delivery report after completion gates pass or a real blocker is recorded.",
    ]


def _default_master_document_sections() -> List[str]:
    return [
        "Goal and Problem Definition",
        "Current Evidence Summary",
        "Target Architecture",
        "Subsystem Breakdown",
        "Implementation Sequence",
        "Quality Gates and Verification Matrix",
        "Appendix Index",
    ]


def _default_appendix_sections() -> List[str]:
    return [
        "Scope",
        "Current Behavior and Evidence",
        "Target Design",
        "Interfaces and Data Contracts",
        "Failure Modes and Edge Cases",
        "Implementation Notes",
        "Verification Notes",
    ]


@dataclass
class AtlasSectionSnapshot:
    level: int
    title: str
    anchor: str
    line_number: int
    word_count: int
    excerpt: str

    def to_dict(self) -> Dict[str, Any]:
        return {
            "level": self.level,
            "title": self.title,
            "anchor": self.anchor,
            "line_number": self.line_number,
            "word_count": self.word_count,
            "excerpt": self.excerpt,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "AtlasSectionSnapshot":
        return cls(
            level=int(data.get("level", 1) or 1),
            title=_clean_text(data.get("title")),
            anchor=_clean_text(data.get("anchor")) or "#section",
            line_number=int(data.get("line_number", 1) or 1),
            word_count=int(data.get("word_count", 0) or 0),
            excerpt=_clean_multiline_text(data.get("excerpt")),
        )


@dataclass
class AtlasDocumentSnapshot:
    path: str
    role: str
    exists: bool
    word_count: int = 0
    line_count: int = 0
    section_count: int = 0
    last_synced_at: str = ""
    last_modified_at: str = ""
    summary: str = ""
    sections: List[AtlasSectionSnapshot] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "path": self.path,
            "role": self.role,
            "exists": self.exists,
            "word_count": self.word_count,
            "line_count": self.line_count,
            "section_count": self.section_count,
            "last_synced_at": self.last_synced_at,
            "last_modified_at": self.last_modified_at,
            "summary": self.summary,
            "sections": [section.to_dict() for section in self.sections],
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "AtlasDocumentSnapshot":
        return cls(
            path=_clean_text(data.get("path")),
            role=_clean_text(data.get("role")) or "appendix",
            exists=bool(data.get("exists", False)),
            word_count=int(data.get("word_count", 0) or 0),
            line_count=int(data.get("line_count", 0) or 0),
            section_count=int(data.get("section_count", 0) or 0),
            last_synced_at=_clean_text(data.get("last_synced_at")),
            last_modified_at=_clean_text(data.get("last_modified_at")),
            summary=_clean_multiline_text(data.get("summary")),
            sections=[
                AtlasSectionSnapshot.from_dict(item)
                for item in data.get("sections", []) or []
                if isinstance(item, dict)
            ],
        )


@dataclass
class AtlasSliceRecord:
    slice_id: str
    title: str
    status: str = "planned"
    document_anchor: str = ""
    document_paths: List[str] = field(default_factory=list)
    success_criteria: List[str] = field(default_factory=list)
    implementation_targets: List[str] = field(default_factory=list)
    verification_plan: List[str] = field(default_factory=list)
    verification_results: List[str] = field(default_factory=list)
    delivered_changes: List[str] = field(default_factory=list)
    open_questions: List[str] = field(default_factory=list)
    dependencies: List[str] = field(default_factory=list)
    notes: str = ""
    created_at: str = ""
    started_at: str = ""
    updated_at: str = ""
    completed_at: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "slice_id": self.slice_id,
            "title": self.title,
            "status": self.status,
            "document_anchor": self.document_anchor,
            "document_paths": self.document_paths,
            "success_criteria": self.success_criteria,
            "implementation_targets": self.implementation_targets,
            "verification_plan": self.verification_plan,
            "verification_results": self.verification_results,
            "delivered_changes": self.delivered_changes,
            "open_questions": self.open_questions,
            "dependencies": self.dependencies,
            "notes": self.notes,
            "created_at": self.created_at,
            "started_at": self.started_at,
            "updated_at": self.updated_at,
            "completed_at": self.completed_at,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "AtlasSliceRecord":
        return cls(
            slice_id=_clean_text(data.get("slice_id")),
            title=_clean_text(data.get("title")),
            status=_normalize_status(data.get("status"), default="planned", allowed=SLICE_STATUSES),
            document_anchor=_clean_text(data.get("document_anchor")),
            document_paths=_normalize_path_strings(data.get("document_paths")),
            success_criteria=_normalize_unique_list(data.get("success_criteria")),
            implementation_targets=_normalize_unique_list(data.get("implementation_targets")),
            verification_plan=_normalize_unique_list(data.get("verification_plan")),
            verification_results=_normalize_unique_list(data.get("verification_results")),
            delivered_changes=_normalize_unique_list(data.get("delivered_changes")),
            open_questions=_normalize_unique_list(data.get("open_questions")),
            dependencies=_normalize_unique_list(data.get("dependencies")),
            notes=_clean_multiline_text(data.get("notes")),
            created_at=_clean_text(data.get("created_at")),
            started_at=_clean_text(data.get("started_at")),
            updated_at=_clean_text(data.get("updated_at")),
            completed_at=_clean_text(data.get("completed_at")),
        )


@dataclass
class AtlasVerificationRecord:
    verification_id: str
    slice_id: str
    kind: str
    passed: bool
    summary: str
    command: str = ""
    evidence_paths: List[str] = field(default_factory=list)
    recorded_at: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "verification_id": self.verification_id,
            "slice_id": self.slice_id,
            "kind": self.kind,
            "passed": self.passed,
            "summary": self.summary,
            "command": self.command,
            "evidence_paths": self.evidence_paths,
            "recorded_at": self.recorded_at,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "AtlasVerificationRecord":
        return cls(
            verification_id=_clean_text(data.get("verification_id")),
            slice_id=_clean_text(data.get("slice_id")),
            kind=_clean_text(data.get("kind")) or "verification",
            passed=bool(data.get("passed", False)),
            summary=_clean_multiline_text(data.get("summary")),
            command=_clean_multiline_text(data.get("command")),
            evidence_paths=_normalize_path_strings(data.get("evidence_paths")),
            recorded_at=_clean_text(data.get("recorded_at")),
        )


@dataclass
class AtlasBlockerRecord:
    blocker_id: str
    title: str
    detail: str
    severity: str = "medium"
    status: str = "open"
    impacted_slices: List[str] = field(default_factory=list)
    unblockers: List[str] = field(default_factory=list)
    opened_at: str = ""
    resolved_at: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "blocker_id": self.blocker_id,
            "title": self.title,
            "detail": self.detail,
            "severity": self.severity,
            "status": self.status,
            "impacted_slices": self.impacted_slices,
            "unblockers": self.unblockers,
            "opened_at": self.opened_at,
            "resolved_at": self.resolved_at,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "AtlasBlockerRecord":
        return cls(
            blocker_id=_clean_text(data.get("blocker_id")),
            title=_clean_text(data.get("title")),
            detail=_clean_multiline_text(data.get("detail")),
            severity=_normalize_status(data.get("severity"), default="medium", allowed=BLOCKER_SEVERITIES),
            status=_normalize_status(data.get("status"), default="open", allowed=BLOCKER_STATUSES),
            impacted_slices=_normalize_unique_list(data.get("impacted_slices")),
            unblockers=_normalize_unique_list(data.get("unblockers")),
            opened_at=_clean_text(data.get("opened_at")),
            resolved_at=_clean_text(data.get("resolved_at")),
        )


@dataclass
class AtlasCheckpointRecord:
    checkpoint_id: str
    focus: str
    summary: str
    next_action: str
    open_risks: List[str] = field(default_factory=list)
    open_blockers: List[str] = field(default_factory=list)
    updated_docs: List[str] = field(default_factory=list)
    recorded_at: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "checkpoint_id": self.checkpoint_id,
            "focus": self.focus,
            "summary": self.summary,
            "next_action": self.next_action,
            "open_risks": self.open_risks,
            "open_blockers": self.open_blockers,
            "updated_docs": self.updated_docs,
            "recorded_at": self.recorded_at,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "AtlasCheckpointRecord":
        return cls(
            checkpoint_id=_clean_text(data.get("checkpoint_id")),
            focus=_clean_multiline_text(data.get("focus")),
            summary=_clean_multiline_text(data.get("summary")),
            next_action=_clean_multiline_text(data.get("next_action")),
            open_risks=_normalize_unique_list(data.get("open_risks")),
            open_blockers=_normalize_unique_list(data.get("open_blockers")),
            updated_docs=_normalize_path_strings(data.get("updated_docs")),
            recorded_at=_clean_text(data.get("recorded_at")),
        )


@dataclass
class AtlasDeliveryState:
    objective: str = ""
    delivery_mode: str = "full_delivery"
    complexity_tier: str = "tier3"
    contract_summary: str = ""
    user_requested_implementation: bool = True
    contract_confirmed: bool = False
    confirmation_notes: str = ""
    master_document_path: str = DEFAULT_MASTER_DOCUMENT_PATH
    appendix_paths: List[str] = field(default_factory=list)
    success_criteria: List[str] = field(default_factory=_default_success_criteria)
    constraints: List[str] = field(default_factory=_default_constraints)
    document_manifest: List[AtlasDocumentSnapshot] = field(default_factory=list)
    slices: List[AtlasSliceRecord] = field(default_factory=list)
    verifications: List[AtlasVerificationRecord] = field(default_factory=list)
    blockers: List[AtlasBlockerRecord] = field(default_factory=list)
    checkpoints: List[AtlasCheckpointRecord] = field(default_factory=list)
    created_at: str = ""
    updated_at: str = ""
    last_action: str = ""
    final_report_path: str = DEFAULT_FINAL_REPORT_PATH

    def to_dict(self) -> Dict[str, Any]:
        return {
            "objective": self.objective,
            "delivery_mode": self.delivery_mode,
            "complexity_tier": self.complexity_tier,
            "contract_summary": self.contract_summary,
            "user_requested_implementation": self.user_requested_implementation,
            "contract_confirmed": self.contract_confirmed,
            "confirmation_notes": self.confirmation_notes,
            "master_document_path": self.master_document_path,
            "appendix_paths": self.appendix_paths,
            "success_criteria": self.success_criteria,
            "constraints": self.constraints,
            "document_manifest": [doc.to_dict() for doc in self.document_manifest],
            "slices": [item.to_dict() for item in self.slices],
            "verifications": [item.to_dict() for item in self.verifications],
            "blockers": [item.to_dict() for item in self.blockers],
            "checkpoints": [item.to_dict() for item in self.checkpoints],
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "last_action": self.last_action,
            "final_report_path": self.final_report_path,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "AtlasDeliveryState":
        return cls(
            objective=_clean_multiline_text(data.get("objective")),
            delivery_mode=_normalize_status(data.get("delivery_mode"), default="full_delivery", allowed=DELIVERY_MODES),
            complexity_tier=_normalize_status(data.get("complexity_tier"), default="tier3", allowed=COMPLEXITY_TIERS),
            contract_summary=_clean_multiline_text(data.get("contract_summary")),
            user_requested_implementation=bool(data.get("user_requested_implementation", True)),
            contract_confirmed=bool(data.get("contract_confirmed", False)),
            confirmation_notes=_clean_multiline_text(data.get("confirmation_notes")),
            master_document_path=_clean_text(data.get("master_document_path")) or DEFAULT_MASTER_DOCUMENT_PATH,
            appendix_paths=_normalize_path_strings(data.get("appendix_paths")),
            success_criteria=_normalize_unique_list(data.get("success_criteria")) or _default_success_criteria(),
            constraints=_normalize_unique_list(data.get("constraints")) or _default_constraints(),
            document_manifest=[
                AtlasDocumentSnapshot.from_dict(item)
                for item in data.get("document_manifest", []) or []
                if isinstance(item, dict)
            ],
            slices=[
                AtlasSliceRecord.from_dict(item)
                for item in data.get("slices", []) or []
                if isinstance(item, dict)
            ],
            verifications=[
                AtlasVerificationRecord.from_dict(item)
                for item in data.get("verifications", []) or []
                if isinstance(item, dict)
            ],
            blockers=[
                AtlasBlockerRecord.from_dict(item)
                for item in data.get("blockers", []) or []
                if isinstance(item, dict)
            ],
            checkpoints=[
                AtlasCheckpointRecord.from_dict(item)
                for item in data.get("checkpoints", []) or []
                if isinstance(item, dict)
            ],
            created_at=_clean_text(data.get("created_at")),
            updated_at=_clean_text(data.get("updated_at")),
            last_action=_clean_text(data.get("last_action")),
            final_report_path=_clean_text(data.get("final_report_path")) or DEFAULT_FINAL_REPORT_PATH,
        )


class AtlasDeliveryOrchestratorTool(BaseTool):
    aliases = ("atlas_delivery", "atlas_orchestrator")
    search_hint = "manage atlas contracts slices blockers and handoffs"
    tool_category = "atlas"
    tool_tags = ("atlas", "delivery", "slice", "blocker", "handoff", "tracker", "document")
    name = "atlas_delivery_orchestrator"
    description = (
        "Track Atlas document contracts, implementation slices, verification "
        "evidence, blockers, checkpoints, and completion gates using durable "
        "artifacts under artifacts/atlas."
    )

    parameters = {
        "type": "object",
        "properties": {
            "action": {
                "type": "string",
                "enum": [
                    "bootstrap_delivery",
                    "register_contract",
                    "plan_slices",
                    "record_slice",
                    "record_verification",
                    "record_blocker",
                    "resolve_blocker",
                    "sync_documents",
                    "checkpoint_delivery",
                    "assess_completion",
                    "prepare_final_report",
                ],
                "description": "Atlas delivery orchestration action.",
            },
            "objective": {"type": "string", "description": "High-level delivery objective."},
            "contract_summary": {"type": "string", "description": "Summary of the engineering contract."},
            "delivery_mode": {"type": "string", "description": "Delivery mode."},
            "complexity_tier": {"type": "string", "description": "Complexity tier."},
            "master_document_path": {"type": "string", "description": "Master document path."},
            "appendix_paths": {"type": "array", "items": {"type": "string"}, "description": "Appendix document paths."},
            "appendix_titles": {"type": "array", "items": {"type": "string"}, "description": "Appendix titles used for default files."},
            "success_criteria": {"type": "array", "items": {"type": "string"}, "description": "Success criteria."},
            "constraints": {"type": "array", "items": {"type": "string"}, "description": "Delivery constraints."},
            "contract_confirmed": {"type": "boolean", "description": "Whether the user confirmed the document baseline."},
            "confirmation_notes": {"type": "string", "description": "Notes captured during confirmation."},
            "user_requested_implementation": {"type": "boolean", "description": "Whether the user asked for implementation."},
            "create_placeholders": {"type": "boolean", "description": "Create placeholder master and appendix documents if missing."},
            "replace_existing_slices": {"type": "boolean", "description": "Replace existing slice plan."},
            "slice_titles": {"type": "array", "items": {"type": "string"}, "description": "Slice titles to plan."},
            "slice_id": {"type": "string", "description": "Existing slice id."},
            "title": {"type": "string", "description": "Slice title or blocker title."},
            "status": {"type": "string", "description": "Slice or blocker status."},
            "document_anchor": {"type": "string", "description": "Document anchor tied to a slice."},
            "document_paths": {"type": "array", "items": {"type": "string"}, "description": "Document paths attached to a slice."},
            "implementation_targets": {"type": "array", "items": {"type": "string"}, "description": "Code or subsystem targets for a slice."},
            "verification_plan": {"type": "array", "items": {"type": "string"}, "description": "Verification plan items for a slice."},
            "verification_results": {"type": "array", "items": {"type": "string"}, "description": "Verification result notes for a slice."},
            "delivered_changes": {"type": "array", "items": {"type": "string"}, "description": "Delivered changes for a slice."},
            "open_questions": {"type": "array", "items": {"type": "string"}, "description": "Open questions related to a slice."},
            "dependencies": {"type": "array", "items": {"type": "string"}, "description": "Slice dependencies."},
            "notes": {"type": "string", "description": "Free-form notes."},
            "kind": {"type": "string", "description": "Verification kind."},
            "passed": {"type": "boolean", "description": "Whether a verification passed."},
            "summary": {"type": "string", "description": "Summary text for checkpoints or verification."},
            "command": {"type": "string", "description": "Command associated with verification evidence."},
            "evidence_paths": {"type": "array", "items": {"type": "string"}, "description": "Evidence paths for verification."},
            "blocker_id": {"type": "string", "description": "Existing blocker id."},
            "detail": {"type": "string", "description": "Blocker detail."},
            "severity": {"type": "string", "description": "Blocker severity."},
            "impacted_slices": {"type": "array", "items": {"type": "string"}, "description": "Slice ids impacted by a blocker."},
            "unblockers": {"type": "array", "items": {"type": "string"}, "description": "Actions required to unblock work."},
            "focus": {"type": "string", "description": "Current focus for a handoff checkpoint."},
            "next_action": {"type": "string", "description": "Next intended action after a checkpoint."},
            "open_risks": {"type": "array", "items": {"type": "string"}, "description": "Open risks to preserve in a checkpoint."},
            "updated_docs": {"type": "array", "items": {"type": "string"}, "description": "Recently updated documents for a checkpoint."},
            "report_path": {"type": "string", "description": "Optional output path for the final report."},
            "strict": {"type": "boolean", "description": "If true, final report generation fails until completion gates pass."},
        },
        "required": ["action"],
    }

    def __init__(self, context: Optional[Dict[str, Any]] = None):
        super().__init__(context)
        self.project_root = self.get_project_root()

    def get_execution_message(self, **kwargs) -> str:
        action = _clean_text(kwargs.get("action")) or "run"
        return f"Updating Atlas delivery state with {action}"

    def execute(self, **kwargs) -> ToolResult:
        action = _clean_text(kwargs.get("action"))
        if not action:
            return ToolResult.fail("action is required")

        try:
            state = self._load_state()
            if action == "bootstrap_delivery":
                return self._bootstrap_delivery(state, kwargs)
            if action == "register_contract":
                return self._register_contract(state, kwargs)
            if action == "plan_slices":
                return self._plan_slices(state, kwargs)
            if action == "record_slice":
                return self._record_slice(state, kwargs)
            if action == "record_verification":
                return self._record_verification(state, kwargs)
            if action == "record_blocker":
                return self._record_blocker(state, kwargs)
            if action == "resolve_blocker":
                return self._resolve_blocker(state, kwargs)
            if action == "sync_documents":
                return self._sync_documents(state, kwargs)
            if action == "checkpoint_delivery":
                return self._checkpoint_delivery(state, kwargs)
            if action == "assess_completion":
                return self._assess_completion(state, kwargs)
            if action == "prepare_final_report":
                return self._prepare_final_report(state, kwargs)
            return ToolResult.fail(f"Unknown action: {action}")
        except Exception as exc:
            return ToolResult.fail(f"Error executing {action}: {exc}")

    def _bootstrap_delivery(self, state: AtlasDeliveryState, kwargs: Dict[str, Any]) -> ToolResult:
        objective = _clean_multiline_text(kwargs.get("objective")) or state.objective
        if not objective:
            return ToolResult.fail("objective is required for bootstrap_delivery")

        state.objective = objective
        state.delivery_mode = _normalize_status(
            kwargs.get("delivery_mode") or state.delivery_mode,
            default=state.delivery_mode or "full_delivery",
            allowed=DELIVERY_MODES,
        )
        state.complexity_tier = _normalize_status(
            kwargs.get("complexity_tier") or state.complexity_tier,
            default=state.complexity_tier or "tier3",
            allowed=COMPLEXITY_TIERS,
        )
        state.contract_summary = (
            _clean_multiline_text(kwargs.get("contract_summary")) or state.contract_summary or objective
        )
        state.user_requested_implementation = _normalize_bool(
            kwargs.get("user_requested_implementation"),
            state.user_requested_implementation,
        )
        state.master_document_path = self._normalize_document_path(
            kwargs.get("master_document_path") or state.master_document_path or DEFAULT_MASTER_DOCUMENT_PATH
        )

        appendix_paths = _normalize_path_strings(kwargs.get("appendix_paths"))
        appendix_titles = _normalize_unique_list(kwargs.get("appendix_titles"))
        if appendix_titles and not appendix_paths:
            appendix_paths = self._build_default_appendix_paths(appendix_titles)
        if appendix_paths:
            state.appendix_paths = appendix_paths

        success_criteria = _normalize_unique_list(kwargs.get("success_criteria"))
        if success_criteria:
            state.success_criteria = success_criteria

        constraints = _normalize_unique_list(kwargs.get("constraints"))
        if constraints:
            state.constraints = constraints

        if kwargs.get("contract_confirmed") is not None:
            state.contract_confirmed = _normalize_bool(kwargs.get("contract_confirmed"), state.contract_confirmed)
        confirmation_notes = _clean_multiline_text(kwargs.get("confirmation_notes"))
        if confirmation_notes:
            state.confirmation_notes = confirmation_notes

        now = _now_iso()
        if not state.created_at:
            state.created_at = now
        state.updated_at = now
        state.last_action = "bootstrap_delivery"

        if _normalize_bool(kwargs.get("create_placeholders"), False):
            self._ensure_default_documents_exist(state)

        self._persist_state_bundle(state)
        summary = (
            f"Bootstrapped Atlas delivery under {ATLAS_ARTIFACTS_DIR}\n"
            f"Objective: {state.objective}\n"
            f"Master document: {state.master_document_path}\n"
            f"Appendices: {len(state.appendix_paths)}\n"
            f"Success criteria: {len(state.success_criteria)}"
        )
        return ToolResult.ok(
            summary,
            {
                "state_path": DEFAULT_STATE_PATH,
                "charter_path": DEFAULT_CHARTER_PATH,
                "tracker_path": DEFAULT_TRACKER_PATH,
                "task_path": DEFAULT_TASK_PATH,
                "resume_index_path": DEFAULT_RESUME_INDEX_PATH,
                "master_document_path": state.master_document_path,
                "appendix_paths": state.appendix_paths,
            },
        )

    def _register_contract(self, state: AtlasDeliveryState, kwargs: Dict[str, Any]) -> ToolResult:
        if _clean_multiline_text(kwargs.get("objective")):
            state.objective = _clean_multiline_text(kwargs.get("objective"))
        if _clean_multiline_text(kwargs.get("contract_summary")):
            state.contract_summary = _clean_multiline_text(kwargs.get("contract_summary"))
        if kwargs.get("delivery_mode") is not None:
            state.delivery_mode = _normalize_status(
                kwargs.get("delivery_mode"),
                default=state.delivery_mode,
                allowed=DELIVERY_MODES,
            )
        if kwargs.get("complexity_tier") is not None:
            state.complexity_tier = _normalize_status(
                kwargs.get("complexity_tier"),
                default=state.complexity_tier,
                allowed=COMPLEXITY_TIERS,
            )
        if kwargs.get("user_requested_implementation") is not None:
            state.user_requested_implementation = _normalize_bool(
                kwargs.get("user_requested_implementation"),
                state.user_requested_implementation,
            )
        if kwargs.get("contract_confirmed") is not None:
            state.contract_confirmed = _normalize_bool(kwargs.get("contract_confirmed"), state.contract_confirmed)
        if _clean_multiline_text(kwargs.get("confirmation_notes")):
            state.confirmation_notes = _clean_multiline_text(kwargs.get("confirmation_notes"))
        if kwargs.get("master_document_path") is not None:
            state.master_document_path = self._normalize_document_path(kwargs.get("master_document_path"))
        appendix_paths = _normalize_path_strings(kwargs.get("appendix_paths"))
        if appendix_paths:
            state.appendix_paths = appendix_paths
        success_criteria = _normalize_unique_list(kwargs.get("success_criteria"))
        if success_criteria:
            state.success_criteria = success_criteria
        constraints = _normalize_unique_list(kwargs.get("constraints"))
        if constraints:
            state.constraints = constraints

        if not state.created_at:
            state.created_at = _now_iso()
        state.updated_at = _now_iso()
        state.last_action = "register_contract"
        self._persist_state_bundle(state)

        return ToolResult.ok(
            (
                "Registered Atlas delivery contract\n"
                f"Confirmed: {'yes' if state.contract_confirmed else 'no'}\n"
                f"Mode: {state.delivery_mode}\n"
                f"Tier: {state.complexity_tier}\n"
                f"Success criteria: {len(state.success_criteria)}\n"
                f"Constraints: {len(state.constraints)}"
            ),
            {
                "contract_confirmed": state.contract_confirmed,
                "delivery_mode": state.delivery_mode,
                "complexity_tier": state.complexity_tier,
                "success_criteria": state.success_criteria,
                "constraints": state.constraints,
            },
        )

    def _plan_slices(self, state: AtlasDeliveryState, kwargs: Dict[str, Any]) -> ToolResult:
        titles = _normalize_unique_list(kwargs.get("slice_titles"))
        replace_existing = _normalize_bool(kwargs.get("replace_existing_slices"), False)

        if not titles:
            titles = self._derive_slice_titles_from_state(state)
        if not titles:
            titles = [
                "Document contract alignment",
                "Primary implementation delivery",
                "Verification and closure",
            ]

        planned_slices = self._build_slice_records_from_titles(state, titles)
        if replace_existing:
            state.slices = planned_slices
        else:
            existing_map = {item.slice_id: item for item in state.slices}
            for record in planned_slices:
                if record.slice_id not in existing_map and not any(
                    item.title.casefold() == record.title.casefold() for item in state.slices
                ):
                    state.slices.append(record)
            state.slices = self._sort_slices(state.slices)

        if not state.created_at:
            state.created_at = _now_iso()
        state.updated_at = _now_iso()
        state.last_action = "plan_slices"
        self._persist_state_bundle(state)

        return ToolResult.ok(
            (
                f"Planned Atlas implementation slices: {len(state.slices)} total\n"
                f"Generated now: {len(planned_slices)}\n"
                f"Replace existing: {'yes' if replace_existing else 'no'}"
            ),
            {
                "slice_ids": [item.slice_id for item in state.slices],
                "slice_titles": [item.title for item in state.slices],
            },
        )

    def _record_slice(self, state: AtlasDeliveryState, kwargs: Dict[str, Any]) -> ToolResult:
        title = _clean_multiline_text(kwargs.get("title"))
        slice_id = _clean_text(kwargs.get("slice_id"))
        record = self._find_slice(state, slice_id=slice_id, title=title)
        if record is None:
            if not title:
                return ToolResult.fail("slice_id or title is required for record_slice")
            record = self._create_slice_record(state, title)
            state.slices.append(record)

        status = _normalize_status(kwargs.get("status"), default=record.status, allowed=SLICE_STATUSES)
        record.status = status
        if _clean_text(kwargs.get("document_anchor")):
            record.document_anchor = _clean_text(kwargs.get("document_anchor"))
        if kwargs.get("document_paths") is not None:
            record.document_paths = _normalize_path_strings(kwargs.get("document_paths"))
        if kwargs.get("implementation_targets") is not None:
            record.implementation_targets = _normalize_unique_list(kwargs.get("implementation_targets"))
        if kwargs.get("verification_plan") is not None:
            record.verification_plan = _normalize_unique_list(kwargs.get("verification_plan"))
        if kwargs.get("verification_results") is not None:
            record.verification_results = _normalize_unique_list(kwargs.get("verification_results"))
        if kwargs.get("delivered_changes") is not None:
            record.delivered_changes = _normalize_unique_list(kwargs.get("delivered_changes"))
        if kwargs.get("open_questions") is not None:
            record.open_questions = _normalize_unique_list(kwargs.get("open_questions"))
        if kwargs.get("dependencies") is not None:
            record.dependencies = _normalize_unique_list(kwargs.get("dependencies"))
        if kwargs.get("success_criteria") is not None:
            record.success_criteria = _normalize_unique_list(kwargs.get("success_criteria"))
        if _clean_multiline_text(kwargs.get("notes")):
            record.notes = _clean_multiline_text(kwargs.get("notes"))

        now = _now_iso()
        if not record.created_at:
            record.created_at = now
        if status == "in_progress" and not record.started_at:
            record.started_at = now
        if status == "completed":
            if not record.started_at:
                record.started_at = now
            record.completed_at = now
        if status in {"planned", "blocked", "cancelled"} and record.completed_at and status != "completed":
            record.completed_at = ""
        record.updated_at = now

        state.slices = self._sort_slices(state.slices)
        if not state.created_at:
            state.created_at = now
        state.updated_at = now
        state.last_action = "record_slice"
        self._persist_state_bundle(state)

        return ToolResult.ok(
            (
                f"Recorded slice {record.slice_id}\n"
                f"Title: {record.title}\n"
                f"Status: {record.status}\n"
                f"Targets: {len(record.implementation_targets)}\n"
                f"Verification results: {len(record.verification_results)}"
            ),
            {"slice": record.to_dict()},
        )

    def _record_verification(self, state: AtlasDeliveryState, kwargs: Dict[str, Any]) -> ToolResult:
        slice_id = _clean_text(kwargs.get("slice_id"))
        title = _clean_multiline_text(kwargs.get("title"))
        record = self._find_slice(state, slice_id=slice_id, title=title)
        if record is None:
            return ToolResult.fail("record_verification requires an existing slice_id or matching title")

        summary = _clean_multiline_text(kwargs.get("summary"))
        if not summary:
            return ToolResult.fail("summary is required for record_verification")

        verification = AtlasVerificationRecord(
            verification_id=self._unique_verification_id(state, record.slice_id, kwargs.get("kind")),
            slice_id=record.slice_id,
            kind=_clean_text(kwargs.get("kind")) or "verification",
            passed=_normalize_bool(kwargs.get("passed"), False),
            summary=summary,
            command=_clean_multiline_text(kwargs.get("command")),
            evidence_paths=_normalize_path_strings(kwargs.get("evidence_paths")),
            recorded_at=_now_iso(),
        )
        state.verifications.append(verification)

        result_line = summary
        if verification.command:
            result_line = f"{summary} (command: {verification.command})"
        if verification.evidence_paths:
            result_line += f" [evidence: {', '.join(verification.evidence_paths)}]"
        if result_line not in record.verification_results:
            record.verification_results.append(result_line)
        if verification.passed and record.status == "planned":
            record.status = "in_progress"
        record.updated_at = _now_iso()

        if not state.created_at:
            state.created_at = _now_iso()
        state.updated_at = _now_iso()
        state.last_action = "record_verification"
        self._persist_state_bundle(state)

        return ToolResult.ok(
            (
                f"Recorded verification {verification.verification_id}\n"
                f"Slice: {record.slice_id}\n"
                f"Kind: {verification.kind}\n"
                f"Passed: {'yes' if verification.passed else 'no'}"
            ),
            {"verification": verification.to_dict()},
        )

    def _record_blocker(self, state: AtlasDeliveryState, kwargs: Dict[str, Any]) -> ToolResult:
        title = _clean_multiline_text(kwargs.get("title"))
        detail = _clean_multiline_text(kwargs.get("detail"))
        if not title or not detail:
            return ToolResult.fail("title and detail are required for record_blocker")

        blocker_id = _clean_text(kwargs.get("blocker_id")) or self._unique_blocker_id(state, title)
        existing = self._find_blocker(state, blocker_id=blocker_id, title=title)
        now = _now_iso()
        if existing is None:
            existing = AtlasBlockerRecord(
                blocker_id=blocker_id,
                title=title,
                detail=detail,
                severity=_normalize_status(kwargs.get("severity"), default="medium", allowed=BLOCKER_SEVERITIES),
                status="open",
                impacted_slices=_normalize_unique_list(kwargs.get("impacted_slices")),
                unblockers=_normalize_unique_list(kwargs.get("unblockers")),
                opened_at=now,
            )
            state.blockers.append(existing)
        else:
            existing.title = title
            existing.detail = detail
            existing.severity = _normalize_status(
                kwargs.get("severity"),
                default=existing.severity,
                allowed=BLOCKER_SEVERITIES,
            )
            existing.status = "open"
            if kwargs.get("impacted_slices") is not None:
                existing.impacted_slices = _normalize_unique_list(kwargs.get("impacted_slices"))
            if kwargs.get("unblockers") is not None:
                existing.unblockers = _normalize_unique_list(kwargs.get("unblockers"))
            if not existing.opened_at:
                existing.opened_at = now
            existing.resolved_at = ""

        for slice_name in existing.impacted_slices:
            target = self._find_slice(state, slice_id=slice_name, title=slice_name)
            if target is not None and target.status != "completed":
                target.status = "blocked"
                target.updated_at = now

        if not state.created_at:
            state.created_at = now
        state.updated_at = now
        state.last_action = "record_blocker"
        self._persist_state_bundle(state)

        return ToolResult.ok(
            (
                f"Recorded blocker {existing.blocker_id}\n"
                f"Severity: {existing.severity}\n"
                f"Impacted slices: {len(existing.impacted_slices)}\n"
                f"Unblockers: {len(existing.unblockers)}"
            ),
            {"blocker": existing.to_dict()},
        )

    def _resolve_blocker(self, state: AtlasDeliveryState, kwargs: Dict[str, Any]) -> ToolResult:
        blocker_id = _clean_text(kwargs.get("blocker_id"))
        title = _clean_multiline_text(kwargs.get("title"))
        blocker = self._find_blocker(state, blocker_id=blocker_id, title=title)
        if blocker is None:
            return ToolResult.fail("resolve_blocker requires an existing blocker_id or matching title")

        blocker.status = "resolved"
        blocker.resolved_at = _now_iso()
        if _clean_multiline_text(kwargs.get("detail")):
            blocker.detail = _clean_multiline_text(kwargs.get("detail"))
        if kwargs.get("unblockers") is not None:
            blocker.unblockers = _normalize_unique_list(kwargs.get("unblockers"))

        for slice_name in blocker.impacted_slices:
            target = self._find_slice(state, slice_id=slice_name, title=slice_name)
            if target is not None and target.status == "blocked":
                target.status = "planned"
                target.updated_at = _now_iso()

        if not state.created_at:
            state.created_at = _now_iso()
        state.updated_at = _now_iso()
        state.last_action = "resolve_blocker"
        self._persist_state_bundle(state)

        return ToolResult.ok(
            (
                f"Resolved blocker {blocker.blocker_id}\n"
                f"Title: {blocker.title}\n"
                f"Resolved at: {blocker.resolved_at}"
            ),
            {"blocker": blocker.to_dict()},
        )

    def _sync_documents(self, state: AtlasDeliveryState, kwargs: Dict[str, Any]) -> ToolResult:
        if kwargs.get("master_document_path") is not None:
            state.master_document_path = self._normalize_document_path(kwargs.get("master_document_path"))
        appendix_paths = _normalize_path_strings(kwargs.get("appendix_paths"))
        if appendix_paths:
            state.appendix_paths = appendix_paths

        manifest = self._scan_documents(state)
        state.document_manifest = manifest
        if not state.created_at:
            state.created_at = _now_iso()
        state.updated_at = _now_iso()
        state.last_action = "sync_documents"
        self._persist_state_bundle(state)

        existing_count = len([item for item in manifest if item.exists])
        missing_count = len(manifest) - existing_count
        return ToolResult.ok(
            (
                f"Synchronized Atlas document manifest\n"
                f"Tracked documents: {len(manifest)}\n"
                f"Existing: {existing_count}\n"
                f"Missing: {missing_count}"
            ),
            {
                "document_manifest": [item.to_dict() for item in manifest],
                "existing_count": existing_count,
                "missing_count": missing_count,
            },
        )

    def _checkpoint_delivery(self, state: AtlasDeliveryState, kwargs: Dict[str, Any]) -> ToolResult:
        focus = _clean_multiline_text(kwargs.get("focus")) or self._default_focus(state)
        summary = _clean_multiline_text(kwargs.get("summary")) or self._default_checkpoint_summary(state)
        next_action = _clean_multiline_text(kwargs.get("next_action")) or self._recommend_next_action(state)

        checkpoint = AtlasCheckpointRecord(
            checkpoint_id=self._unique_checkpoint_id(state),
            focus=focus,
            summary=summary,
            next_action=next_action,
            open_risks=_normalize_unique_list(kwargs.get("open_risks")),
            open_blockers=[item.blocker_id for item in state.blockers if item.status == "open"],
            updated_docs=_normalize_path_strings(kwargs.get("updated_docs")),
            recorded_at=_now_iso(),
        )
        state.checkpoints.append(checkpoint)
        if not state.created_at:
            state.created_at = checkpoint.recorded_at
        state.updated_at = checkpoint.recorded_at
        state.last_action = "checkpoint_delivery"
        self._persist_state_bundle(state)

        return ToolResult.ok(
            (
                f"Captured Atlas checkpoint {checkpoint.checkpoint_id}\n"
                f"Focus: {checkpoint.focus}\n"
                f"Next action: {checkpoint.next_action}\n"
                f"Open blockers: {len(checkpoint.open_blockers)}"
            ),
            {"checkpoint": checkpoint.to_dict(), "handoff_path": DEFAULT_HANDOFF_PATH},
        )

    def _assess_completion(self, state: AtlasDeliveryState, kwargs: Dict[str, Any]) -> ToolResult:
        assessment = self._completion_assessment(state)
        strict = _normalize_bool(kwargs.get("strict"), True)
        output_lines = [
            "Atlas completion assessment",
            "",
            f"Ready for final report: {'yes' if assessment['ready'] else 'no'}",
            f"Strict mode: {'yes' if strict else 'no'}",
            f"Open slices: {len(assessment['open_slices'])}",
            f"Open blockers: {len(assessment['open_blockers'])}",
            f"Verification failures: {len(assessment['failed_verifications'])}",
            f"Missing conditions: {len(assessment['missing_conditions'])}",
        ]
        if assessment["missing_conditions"]:
            output_lines.append("")
            output_lines.append("Missing conditions:")
            output_lines.extend(f"- {item}" for item in assessment["missing_conditions"])
        if assessment["recommendations"]:
            output_lines.append("")
            output_lines.append("Recommended next actions:")
            output_lines.extend(f"- {item}" for item in assessment["recommendations"])

        if not state.created_at:
            state.created_at = _now_iso()
        state.updated_at = _now_iso()
        state.last_action = "assess_completion"
        self._persist_state_bundle(state)

        if assessment["ready"]:
            return ToolResult.ok("\n".join(output_lines), assessment)
        return ToolResult.partial("\n".join(output_lines), "Atlas delivery is not ready for closure yet.")

    def _prepare_final_report(self, state: AtlasDeliveryState, kwargs: Dict[str, Any]) -> ToolResult:
        strict = _normalize_bool(kwargs.get("strict"), True)
        assessment = self._completion_assessment(state)
        report_path = self._normalize_document_path(
            kwargs.get("report_path") or state.final_report_path or DEFAULT_FINAL_REPORT_PATH
        )
        state.final_report_path = report_path

        if strict and not assessment["ready"]:
            self._persist_state_bundle(state)
            return ToolResult.fail(
                "Completion gates are not satisfied yet. "
                "Run assess_completion or finish the missing slices and verifications first."
            )

        report_markdown = self._render_final_report(state, assessment)
        report_file = self.resolve_workspace_path(report_path, purpose="write final report")
        _ensure_parent(report_file)
        report_file.write_text(report_markdown, encoding="utf-8")

        if not state.created_at:
            state.created_at = _now_iso()
        state.updated_at = _now_iso()
        state.last_action = "prepare_final_report"
        self._persist_state_bundle(state)

        if assessment["ready"]:
            return ToolResult.ok(
                f"Prepared final Atlas delivery report at {report_path}",
                {
                    "report_path": report_path,
                    "ready": True,
                    "assessment": assessment,
                },
            )
        return ToolResult.partial(
            f"Prepared partial Atlas delivery report at {report_path}",
            "Completion gates are still missing items.",
        )

    def _load_state(self) -> AtlasDeliveryState:
        state_path = self.resolve_workspace_path(DEFAULT_STATE_PATH, purpose="load state")
        if not state_path.exists():
            return AtlasDeliveryState(created_at=_now_iso(), updated_at=_now_iso())
        try:
            payload = json.loads(state_path.read_text(encoding="utf-8"))
        except Exception:
            return AtlasDeliveryState(created_at=_now_iso(), updated_at=_now_iso())
        return AtlasDeliveryState.from_dict(payload if isinstance(payload, dict) else {})

    def _persist_state_bundle(self, state: AtlasDeliveryState) -> None:
        state.updated_at = _now_iso()
        if not state.created_at:
            state.created_at = state.updated_at
        self._write_state(state)
        self._write_charter(state)
        self._write_tracker(state)
        self._write_task_file(state)
        self._write_resume_index_file(state)
        self._write_document_manifest_files(state)
        self._write_handoff_file(state)

    def _write_state(self, state: AtlasDeliveryState) -> None:
        state_path = self.resolve_workspace_path(DEFAULT_STATE_PATH, purpose="write state")
        _safe_json_dump(state.to_dict(), state_path)

    def _write_charter(self, state: AtlasDeliveryState) -> None:
        charter_path = self.resolve_workspace_path(DEFAULT_CHARTER_PATH, purpose="write charter")
        _ensure_parent(charter_path)
        charter_path.write_text(self._render_charter(state), encoding="utf-8")

    def _write_tracker(self, state: AtlasDeliveryState) -> None:
        tracker_path = self.resolve_workspace_path(DEFAULT_TRACKER_PATH, purpose="write tracker")
        _ensure_parent(tracker_path)
        tracker_path.write_text(self._render_tracker(state), encoding="utf-8")

    def _write_task_file(self, state: AtlasDeliveryState) -> None:
        task_path = self.resolve_workspace_path(DEFAULT_TASK_PATH, purpose="write atlas task file")
        _ensure_parent(task_path)
        task_path.write_text(self._render_task_file(state), encoding="utf-8")

    def _write_resume_index_file(self, state: AtlasDeliveryState) -> None:
        resume_index_path = self.resolve_workspace_path(DEFAULT_RESUME_INDEX_PATH, purpose="write atlas resume index")
        _ensure_parent(resume_index_path)
        resume_index_path.write_text(self._render_resume_index(state), encoding="utf-8")

    def _write_document_manifest_files(self, state: AtlasDeliveryState) -> None:
        manifest_json_path = self.resolve_workspace_path(
            DEFAULT_DOCUMENT_MANIFEST_JSON_PATH,
            purpose="write document manifest json",
        )
        manifest_md_path = self.resolve_workspace_path(
            DEFAULT_DOCUMENT_MANIFEST_MD_PATH,
            purpose="write document manifest markdown",
        )
        payload = {
            "master_document_path": state.master_document_path,
            "appendix_paths": state.appendix_paths,
            "document_manifest": [item.to_dict() for item in state.document_manifest],
            "updated_at": state.updated_at,
        }
        _safe_json_dump(payload, manifest_json_path)
        _ensure_parent(manifest_md_path)
        manifest_md_path.write_text(self._render_document_manifest(state), encoding="utf-8")

    def _write_handoff_file(self, state: AtlasDeliveryState) -> None:
        handoff_path = self.resolve_workspace_path(DEFAULT_HANDOFF_PATH, purpose="write handoff")
        _ensure_parent(handoff_path)
        handoff_path.write_text(self._render_handoff_summary(state), encoding="utf-8")

    def _normalize_document_path(self, raw_path: Any) -> str:
        candidate = _clean_text(raw_path) or DEFAULT_MASTER_DOCUMENT_PATH
        resolved = self.resolve_workspace_path(candidate, purpose="resolve document path")
        return _maybe_relativize(resolved, self.project_root)

    def _build_default_appendix_paths(self, titles: List[str]) -> List[str]:
        paths: List[str] = []
        for index, title in enumerate(titles, start=1):
            label = chr(64 + index) if index <= 26 else str(index)
            safe_title = title.replace("/", " ").replace("\\", " ").strip()
            filename = f"Appendix {label} - {safe_title}.md"
            paths.append(f"artifacts/{filename}")
        return paths

    def _ensure_default_documents_exist(self, state: AtlasDeliveryState) -> None:
        master_path = self.resolve_workspace_path(state.master_document_path, purpose="write master document")
        if not master_path.exists():
            _ensure_parent(master_path)
            master_path.write_text(self._render_master_document_template(state), encoding="utf-8")

        for appendix_path in state.appendix_paths:
            appendix_file = self.resolve_workspace_path(appendix_path, purpose="write appendix")
            if appendix_file.exists():
                continue
            _ensure_parent(appendix_file)
            appendix_file.write_text(
                self._render_appendix_template(state, appendix_file.stem),
                encoding="utf-8",
            )

    def _scan_documents(self, state: AtlasDeliveryState) -> List[AtlasDocumentSnapshot]:
        manifest: List[AtlasDocumentSnapshot] = []
        document_specs: List[Tuple[str, str]] = [("master", state.master_document_path)]
        document_specs.append(("task", DEFAULT_TASK_PATH))
        document_specs.append(("resume", DEFAULT_RESUME_INDEX_PATH))
        document_specs.extend(("appendix", path) for path in state.appendix_paths)
        for role, path_text in document_specs:
            normalized = self._normalize_document_path(path_text)
            absolute = self.resolve_workspace_path(normalized, purpose="scan document")
            manifest.append(self._snapshot_document(absolute, role=role))
        return manifest

    def _snapshot_document(self, path: Path, *, role: str) -> AtlasDocumentSnapshot:
        exists = path.exists()
        if not exists:
            return AtlasDocumentSnapshot(
                path=_maybe_relativize(path, self.project_root),
                role=role,
                exists=False,
                last_synced_at=_now_iso(),
            )

        text = path.read_text(encoding="utf-8")
        lines = text.splitlines()
        sections = self._extract_sections(text)
        modified_at = datetime.fromtimestamp(path.stat().st_mtime, tz=timezone.utc).replace(microsecond=0).isoformat()
        return AtlasDocumentSnapshot(
            path=_maybe_relativize(path, self.project_root),
            role=role,
            exists=True,
            word_count=_word_count(text),
            line_count=len(lines),
            section_count=len(sections),
            last_synced_at=_now_iso(),
            last_modified_at=modified_at,
            summary=_truncate(text, 220),
            sections=sections,
        )

    def _extract_sections(self, text: str) -> List[AtlasSectionSnapshot]:
        lines = text.splitlines()
        matches: List[Tuple[int, re.Match[str]]] = []
        for index, line in enumerate(lines, start=1):
            match = HEADING_RE.match(line)
            if match:
                matches.append((index, match))

        if not matches:
            return []

        sections: List[AtlasSectionSnapshot] = []
        for idx, (line_number, match) in enumerate(matches):
            title = match.group("title").strip()
            next_line = matches[idx + 1][0] if idx + 1 < len(matches) else len(lines) + 1
            body = "\n".join(lines[line_number: max(line_number, next_line - 1)])
            sections.append(
                AtlasSectionSnapshot(
                    level=len(match.group("level")),
                    title=title,
                    anchor=_anchorify(title),
                    line_number=line_number,
                    word_count=_word_count(body),
                    excerpt=_truncate(body, 140),
                )
            )
        return sections

    def _derive_slice_titles_from_state(self, state: AtlasDeliveryState) -> List[str]:
        titles: List[str] = []
        manifest = state.document_manifest or self._scan_documents(state)
        for document in manifest:
            if not document.exists:
                continue
            if document.role == "master":
                for section in document.sections:
                    lowered = section.title.casefold()
                    if any(keyword in lowered for keyword in ["implementation", "verification", "sequence", "phase"]):
                        titles.append(section.title)
            else:
                if document.sections:
                    titles.append(f"{Path(document.path).stem}: {document.sections[0].title}")
                else:
                    titles.append(Path(document.path).stem)

        if not titles:
            titles.extend(state.success_criteria)
        if not titles and state.objective:
            titles.extend(self._derive_titles_from_objective(state.objective))

        unique_titles: List[str] = []
        seen: set[str] = set()
        for title in titles:
            cleaned = _clean_multiline_text(title)
            if not cleaned:
                continue
            lowered = cleaned.casefold()
            if lowered in seen:
                continue
            seen.add(lowered)
            unique_titles.append(cleaned)
        return unique_titles

    def _derive_titles_from_objective(self, objective: str) -> List[str]:
        fragments = re.split(r"[.;:\n]+", objective)
        titles = [_clean_multiline_text(fragment) for fragment in fragments if _clean_multiline_text(fragment)]
        if titles:
            return titles
        return [objective]

    def _build_slice_records_from_titles(
        self,
        state: AtlasDeliveryState,
        titles: List[str],
    ) -> List[AtlasSliceRecord]:
        records: List[AtlasSliceRecord] = []
        for index, title in enumerate(titles, start=1):
            record = self._create_slice_record(state, title, index=index)
            record.document_anchor = self._suggest_anchor_for_title(state, title)
            record.document_paths = self._suggest_document_paths_for_title(state, title)
            record.success_criteria = self._suggest_slice_success_criteria(state, title)
            record.implementation_targets = self._suggest_slice_targets(title)
            record.verification_plan = self._suggest_verification_plan(title, state)
            records.append(record)
        return self._sort_slices(records)

    def _suggest_anchor_for_title(self, state: AtlasDeliveryState, title: str) -> str:
        lowered = title.casefold()
        for document in state.document_manifest or self._scan_documents(state):
            for section in document.sections:
                section_lower = section.title.casefold()
                if section_lower == lowered or lowered in section_lower or section_lower in lowered:
                    return section.anchor
        return _anchorify(title)

    def _suggest_document_paths_for_title(self, state: AtlasDeliveryState, title: str) -> List[str]:
        lowered = title.casefold()
        matches: List[str] = []
        for document in state.document_manifest or self._scan_documents(state):
            if any(lowered in section.title.casefold() for section in document.sections):
                matches.append(document.path)
                continue
            stem = Path(document.path).stem.casefold()
            if stem in lowered or lowered in stem:
                matches.append(document.path)
        if matches:
            return _stable_sort_strings(matches)
        base_paths = [state.master_document_path]
        if state.appendix_paths:
            base_paths.extend(state.appendix_paths[:1])
        return _stable_sort_strings(base_paths)

    def _suggest_slice_success_criteria(self, state: AtlasDeliveryState, title: str) -> List[str]:
        lowered = title.casefold()
        matched = [criterion for criterion in state.success_criteria if any(word in criterion.casefold() for word in lowered.split())]
        if matched:
            return matched
        if state.success_criteria:
            return [state.success_criteria[0]]
        return []

    def _suggest_slice_targets(self, title: str) -> List[str]:
        lowered = title.casefold()
        targets: List[str] = []
        if "document" in lowered or "contract" in lowered:
            targets.append("artifacts and document bundle")
        if "verification" in lowered or "quality" in lowered:
            targets.append("tests, build, and runtime validation")
        if "implementation" in lowered or "deliver" in lowered:
            targets.append("production code path")
        if not targets:
            targets.append("affected subsystem to be determined from retrieval")
        return targets

    def _suggest_verification_plan(self, title: str, state: AtlasDeliveryState) -> List[str]:
        lowered = title.casefold()
        plan: List[str] = []
        if state.user_requested_implementation:
            plan.append("Run targeted tests or build validation for the slice.")
        if "document" in lowered or "contract" in lowered:
            plan.append("Confirm the document set stays aligned with delivered behavior.")
        if "verification" in lowered:
            plan.append("Record passed and failed verification evidence explicitly.")
        if not plan:
            plan.append("Verify integration behavior before moving to the next slice.")
        return plan

    def _sort_slices(self, slices: List[AtlasSliceRecord]) -> List[AtlasSliceRecord]:
        order = {
            "in_progress": 0,
            "blocked": 1,
            "planned": 2,
            "completed": 3,
            "cancelled": 4,
        }
        return sorted(
            slices,
            key=lambda item: (
                order.get(item.status, 9),
                item.created_at or "",
                item.slice_id,
            ),
        )

    def _create_slice_record(
        self,
        state: AtlasDeliveryState,
        title: str,
        *,
        index: Optional[int] = None,
    ) -> AtlasSliceRecord:
        slice_id = self._unique_slice_id(state, title, index=index)
        now = _now_iso()
        return AtlasSliceRecord(
            slice_id=slice_id,
            title=title,
            status="planned",
            created_at=now,
            updated_at=now,
        )

    def _find_slice(
        self,
        state: AtlasDeliveryState,
        *,
        slice_id: str = "",
        title: str = "",
    ) -> Optional[AtlasSliceRecord]:
        cleaned_slice_id = _clean_text(slice_id)
        cleaned_title = _clean_multiline_text(title)
        if cleaned_slice_id:
            for item in state.slices:
                if item.slice_id == cleaned_slice_id:
                    return item
        if cleaned_title:
            lowered = cleaned_title.casefold()
            for item in state.slices:
                if item.title.casefold() == lowered:
                    return item
        return None

    def _find_blocker(
        self,
        state: AtlasDeliveryState,
        *,
        blocker_id: str = "",
        title: str = "",
    ) -> Optional[AtlasBlockerRecord]:
        cleaned_id = _clean_text(blocker_id)
        cleaned_title = _clean_multiline_text(title)
        if cleaned_id:
            for item in state.blockers:
                if item.blocker_id == cleaned_id:
                    return item
        if cleaned_title:
            lowered = cleaned_title.casefold()
            for item in state.blockers:
                if item.title.casefold() == lowered:
                    return item
        return None

    def _unique_slice_id(
        self,
        state: AtlasDeliveryState,
        title: str,
        *,
        index: Optional[int] = None,
    ) -> str:
        base = _slugify(title, fallback="slice")
        if index is not None:
            base = f"{index:02d}-{base}"
        existing = {item.slice_id for item in state.slices}
        candidate = base
        counter = 2
        while candidate in existing:
            candidate = f"{base}-{counter}"
            counter += 1
        return candidate

    def _unique_verification_id(self, state: AtlasDeliveryState, slice_id: str, kind: Any) -> str:
        base = _slugify(f"{slice_id}-{_clean_text(kind) or 'verification'}", fallback="verification")
        existing = {item.verification_id for item in state.verifications}
        candidate = base
        counter = 2
        while candidate in existing:
            candidate = f"{base}-{counter}"
            counter += 1
        return candidate

    def _unique_blocker_id(self, state: AtlasDeliveryState, title: str) -> str:
        base = _slugify(title, fallback="blocker")
        existing = {item.blocker_id for item in state.blockers}
        candidate = base
        counter = 2
        while candidate in existing:
            candidate = f"{base}-{counter}"
            counter += 1
        return candidate

    def _unique_checkpoint_id(self, state: AtlasDeliveryState) -> str:
        base = datetime.now().strftime("cp-%Y%m%d-%H%M%S")
        existing = {item.checkpoint_id for item in state.checkpoints}
        candidate = base
        counter = 2
        while candidate in existing:
            candidate = f"{base}-{counter}"
            counter += 1
        return candidate

    def _default_focus(self, state: AtlasDeliveryState) -> str:
        active = self._active_slice(state)
        if active is not None:
            return f"Continue slice {active.slice_id}: {active.title}"
        if state.objective:
            return state.objective
        return "Atlas delivery continuation"

    def _default_checkpoint_summary(self, state: AtlasDeliveryState) -> str:
        completed = len([item for item in state.slices if item.status == "completed"])
        total = len(state.slices)
        blockers = len([item for item in state.blockers if item.status == "open"])
        verifications = len(state.verifications)
        return (
            f"{completed}/{total} slices completed, "
            f"{blockers} open blockers, "
            f"{verifications} verifications recorded."
        )

    def _recommend_next_action(self, state: AtlasDeliveryState) -> str:
        assessment = self._completion_assessment(state)
        if assessment["recommendations"]:
            return assessment["recommendations"][0]
        active = self._active_slice(state)
        if active is not None:
            return f"Continue implementation and verification for slice {active.slice_id}."
        return "Review the document contract and generate the next implementation slice."

    def _active_slice(self, state: AtlasDeliveryState) -> Optional[AtlasSliceRecord]:
        for item in state.slices:
            if item.status == "in_progress":
                return item
        for item in state.slices:
            if item.status == "blocked":
                return item
        for item in state.slices:
            if item.status == "planned":
                return item
        return None

    def _completion_assessment(self, state: AtlasDeliveryState) -> Dict[str, Any]:
        manifest = state.document_manifest or self._scan_documents(state)
        open_blockers = [item for item in state.blockers if item.status == "open"]
        open_slices = [item for item in state.slices if item.status in {"planned", "in_progress", "blocked"}]
        completed_slices = [item for item in state.slices if item.status == "completed"]
        failed_verifications = [item for item in state.verifications if not item.passed]

        missing_conditions: List[str] = []
        recommendations: List[str] = []

        if not state.objective:
            missing_conditions.append("Atlas objective is missing.")
            recommendations.append("Register the delivery objective before continuing.")

        if state.delivery_mode == "full_delivery" and state.user_requested_implementation and not state.contract_confirmed:
            missing_conditions.append("The document baseline has not been confirmed yet.")
            recommendations.append("Explain the document set to the user and confirm the baseline before broad implementation.")

        if not manifest:
            missing_conditions.append("No document manifest is available.")
            recommendations.append("Run sync_documents to capture the current master and appendix files.")
        else:
            master_doc = next((item for item in manifest if item.role == "master"), None)
            if master_doc is None or not master_doc.exists:
                missing_conditions.append("The master document is missing.")
                recommendations.append("Create or restore the master document and sync the document manifest.")
            for appendix in [item for item in manifest if item.role == "appendix" and not item.exists]:
                missing_conditions.append(f"Appendix document missing: {appendix.path}")
                recommendations.append(f"Create or restore appendix document {appendix.path}.")

        if state.user_requested_implementation:
            if not state.slices:
                missing_conditions.append("No implementation slices are planned.")
                recommendations.append("Plan delivery slices from the document contract.")
            if open_slices:
                missing_conditions.append("There are unfinished implementation slices.")
                active = self._active_slice(state)
                if active is not None:
                    recommendations.append(
                        f"Continue slice {active.slice_id}: {active.title} instead of summarizing progress."
                    )
            if not completed_slices:
                missing_conditions.append("No implementation slice is marked completed.")
                recommendations.append("Complete at least one meaningful implementation slice and record it.")
            if not state.verifications:
                missing_conditions.append("No verification evidence has been recorded.")
                recommendations.append("Record build, test, runtime, or manual verification evidence.")

        if open_blockers:
            for blocker in open_blockers:
                missing_conditions.append(f"Open blocker: {blocker.blocker_id} - {blocker.title}")
            recommendations.append("Resolve or explicitly escalate open blockers before final closure.")

        if failed_verifications:
            missing_conditions.append("There are failed verification records.")
            recommendations.append("Fix the failing verification issues or document them as explicit remaining gaps.")

        if not state.success_criteria:
            missing_conditions.append("Success criteria are missing.")
            recommendations.append("Register success criteria for the delivery contract.")

        coverage = self._success_criteria_coverage(state)
        uncovered = [item for item in coverage if not item["covered"]]
        if uncovered:
            for item in uncovered:
                missing_conditions.append(f"Success criterion not covered: {item['criterion']}")
            recommendations.append("Complete or document coverage for every success criterion.")

        ready = not missing_conditions
        return {
            "ready": ready,
            "objective": state.objective,
            "delivery_mode": state.delivery_mode,
            "complexity_tier": state.complexity_tier,
            "open_slices": [item.to_dict() for item in open_slices],
            "completed_slices": [item.to_dict() for item in completed_slices],
            "open_blockers": [item.to_dict() for item in open_blockers],
            "failed_verifications": [item.to_dict() for item in failed_verifications],
            "missing_conditions": missing_conditions,
            "recommendations": self._dedupe_recommendations(recommendations),
            "criteria_coverage": coverage,
        }

    def _success_criteria_coverage(self, state: AtlasDeliveryState) -> List[Dict[str, Any]]:
        completed_text = " ".join(
            [
                state.objective,
                state.contract_summary,
                " ".join(item.title for item in state.slices if item.status == "completed"),
                " ".join(change for item in state.slices for change in item.delivered_changes),
                " ".join(item.summary for item in state.verifications),
            ]
        ).casefold()
        coverage: List[Dict[str, Any]] = []
        for criterion in state.success_criteria:
            words = [word for word in NON_ALNUM_RE.split(criterion.casefold()) if len(word) > 3]
            matched_words = [word for word in words if word in completed_text]
            covered = bool(matched_words) or criterion.casefold() in completed_text
            coverage.append(
                {
                    "criterion": criterion,
                    "covered": covered,
                    "matched_words": matched_words,
                }
            )
        return coverage

    def _dedupe_recommendations(self, recommendations: List[str]) -> List[str]:
        ordered: List[str] = []
        seen: set[str] = set()
        for item in recommendations:
            cleaned = _clean_multiline_text(item)
            if not cleaned:
                continue
            lowered = cleaned.casefold()
            if lowered in seen:
                continue
            seen.add(lowered)
            ordered.append(cleaned)
        return ordered

    def _render_master_document_template(self, state: AtlasDeliveryState) -> str:
        body = [
            f"# {Path(state.master_document_path).stem}",
            "",
            "## Delivery Objective",
            state.objective or "Describe the delivery objective here.",
            "",
            "## Contract Summary",
            state.contract_summary or "Capture the agreed engineering contract here.",
            "",
            "## Success Criteria",
            _format_bullets(state.success_criteria),
            "",
            "## Constraints",
            _format_bullets(state.constraints),
            "",
        ]
        for section in _default_master_document_sections():
            body.extend([f"## {section}", "Pending research and delivery details.", ""])
        return "\n".join(body).rstrip() + "\n"

    def _render_appendix_template(self, state: AtlasDeliveryState, title: str) -> str:
        body = [f"# {title}", "", f"Linked objective: {state.objective or 'Pending'}", ""]
        for section in _default_appendix_sections():
            body.extend([f"## {section}", "Pending appendix details.", ""])
        return "\n".join(body).rstrip() + "\n"

    def _task_items_for_slice(self, item: AtlasSliceRecord) -> List[tuple[bool, str]]:
        items: List[tuple[bool, str]] = []

        for path in item.document_paths:
            items.append((item.status == "completed", f"同步相关文档：{path}"))
        for target in item.implementation_targets:
            items.append((item.status == "completed", f"实现目标：{target}"))
        for criterion in item.success_criteria:
            items.append((item.status == "completed", f"达成标准：{criterion}"))
        for plan in item.verification_plan:
            is_done = item.status == "completed" and bool(item.verification_results)
            items.append((is_done, f"验证项：{plan}"))
        for change in item.delivered_changes:
            items.append((True, f"已交付：{change}"))
        for result in item.verification_results:
            items.append((True, f"已验证：{result}"))
        for question in item.open_questions:
            items.append((False, f"待确认：{question}"))
        if item.notes:
            items.append((item.status == "completed", f"备注：{item.notes}"))

        if not items:
            fallback_text = item.notes or "推进该分目标并同步实现、验证、文档状态"
            items.append((item.status == "completed", fallback_text))

        deduped: List[tuple[bool, str]] = []
        seen: set[str] = set()
        for done, text in items:
            cleaned = _clean_multiline_text(text)
            key = cleaned.casefold()
            if not cleaned or key in seen:
                continue
            seen.add(key)
            deduped.append((done, cleaned))
        return deduped

    def _render_task_file(self, state: AtlasDeliveryState) -> str:
        lines = [
            "主任务目标",
            state.objective or "待补充主任务目标",
            "",
        ]

        if not state.slices:
            lines.extend(
                [
                    "分目标1：建立 Atlas 文档系统与执行切片",
                    "[ ]梳理主任务目标、主文档、附录文档和交付切片",
                    "[ ]补充 artifacts/task.md、artifacts/atlas/ 以及文档清单",
                ]
            )
        else:
            for index, item in enumerate(self._sort_slices(state.slices), start=1):
                lines.append(f"分目标{index}：{item.title}")
                for done, text in self._task_items_for_slice(item):
                    checkbox = "[x]" if done else "[ ]"
                    lines.append(f"{checkbox}{text}")
                lines.append("")

        open_blockers = [item for item in state.blockers if item.status == "open"]
        if open_blockers:
            lines.append(f"分目标{len(state.slices) + 1}：处理阻塞与风险")
            for blocker in open_blockers:
                lines.append(f"[ ]阻塞：{blocker.title} - {blocker.detail}")
            lines.append("")

        return "\n".join(lines).rstrip() + "\n"

    def _render_resume_index(self, state: AtlasDeliveryState) -> str:
        active = self._active_slice(state)
        open_blockers = [item for item in state.blockers if item.status == "open"]
        latest_checkpoint = state.checkpoints[-1] if state.checkpoints else None
        lines = [
            "# Atlas Resume Index",
            "",
            "Read this file first when a new Atlas conversation starts or resumes.",
            "",
            "## Resume Order",
            f"1. `{DEFAULT_RESUME_INDEX_PATH}`",
            f"2. `{DEFAULT_TASK_PATH}`",
            f"3. `{state.master_document_path}`",
            f"4. `{DEFAULT_TRACKER_PATH}`",
            f"5. `{DEFAULT_HANDOFF_PATH}`",
        ]
        if state.appendix_paths:
            lines.append("6. Relevant appendix documents for the active slice:")
            lines.extend(f"   - `{path}`" for path in state.appendix_paths[:8])

        lines.extend(
            [
                "",
                "## Current Objective",
                state.objective or "Pending objective.",
                "",
                "## Current State",
                f"- Delivery mode: `{state.delivery_mode}`",
                f"- Complexity tier: `{state.complexity_tier}`",
                f"- Contract confirmed: {'yes' if state.contract_confirmed else 'no'}",
                f"- Active slice: `{active.slice_id}` {active.title}" if active else "- Active slice: None",
                f"- Open blockers: {len(open_blockers)}",
                f"- Last action: `{state.last_action or 'none'}`",
                f"- Updated at: `{state.updated_at or state.created_at}`",
                "",
                "## Immediate Next Step",
                f"- {latest_checkpoint.next_action}" if latest_checkpoint and latest_checkpoint.next_action else f"- {self._recommend_next_action(state)}",
                "",
                "## Fast Resume Checklist",
                "- Reconcile the current repository state with the document system before editing.",
                f"- Open `{DEFAULT_TASK_PATH}` and continue the next unfinished item instead of writing a status recap.",
                "- If the active slice changed materially, refresh the Atlas tracker and task tree before broad implementation.",
                "- If context is tight, prefer document-grounded continuation over replaying old conversation details.",
            ]
        )
        return "\n".join(lines).rstrip() + "\n"

    def _render_charter(self, state: AtlasDeliveryState) -> str:
        active = self._active_slice(state)
        lines = [
            "# Atlas Delivery Charter",
            "",
            "## Objective",
            state.objective or "Pending objective.",
            "",
            "## Contract Summary",
            state.contract_summary or "Pending contract summary.",
            "",
            "## Delivery Profile",
            f"- Delivery mode: `{state.delivery_mode}`",
            f"- Complexity tier: `{state.complexity_tier}`",
            f"- User requested implementation: {'yes' if state.user_requested_implementation else 'no'}",
            f"- Contract confirmed: {'yes' if state.contract_confirmed else 'no'}",
            "",
            "## Document Set",
            f"- Master document: `{state.master_document_path}`",
            f"- Task tree: `{DEFAULT_TASK_PATH}`",
            f"- Resume index: `{DEFAULT_RESUME_INDEX_PATH}`",
            f"- Appendices tracked: {len(state.appendix_paths)}",
        ]
        if state.appendix_paths:
            lines.extend(f"  - `{path}`" for path in state.appendix_paths)
        lines.extend(
            [
                "",
                "## Success Criteria",
                _format_bullets(state.success_criteria),
                "",
                "## Constraints",
                _format_bullets(state.constraints),
                "",
                "## Current Execution Posture",
                f"- Active slice: `{active.slice_id}` {active.title}" if active else "- Active slice: None",
                f"- Last action: `{state.last_action or 'none'}`",
                f"- Updated at: `{state.updated_at or state.created_at}`",
            ]
        )
        if state.confirmation_notes:
            lines.extend(["", "## Confirmation Notes", state.confirmation_notes])
        return "\n".join(lines).rstrip() + "\n"

    def _render_tracker(self, state: AtlasDeliveryState) -> str:
        completed_count = len([item for item in state.slices if item.status == "completed"])
        open_blockers = [item for item in state.blockers if item.status == "open"]
        lines = [
            "# Atlas Delivery Tracker",
            "",
            "## Snapshot",
            f"- Objective: {state.objective or 'Pending objective'}",
            f"- Completed slices: {completed_count}/{len(state.slices)}",
            f"- Open blockers: {len(open_blockers)}",
            f"- Verifications: {len(state.verifications)}",
            "",
            "## Slice Ledger",
        ]
        if not state.slices:
            lines.append("- No slices planned yet.")
        else:
            for item in self._sort_slices(state.slices):
                lines.extend(
                    [
                        f"- {_status_icon(item.status)} `{item.slice_id}` {item.title}",
                        f"  - Anchor: `{item.document_anchor or 'n/a'}`",
                        f"  - Docs: {', '.join(f'`{path}`' for path in item.document_paths) if item.document_paths else 'n/a'}",
                        f"  - Targets: {', '.join(item.implementation_targets) if item.implementation_targets else 'n/a'}",
                        f"  - Verification plan: {', '.join(item.verification_plan) if item.verification_plan else 'n/a'}",
                        f"  - Delivered changes: {', '.join(item.delivered_changes) if item.delivered_changes else 'n/a'}",
                        f"  - Open questions: {', '.join(item.open_questions) if item.open_questions else 'n/a'}",
                    ]
                )
                if item.notes:
                    lines.append(f"  - Notes: {item.notes}")
        lines.extend(["", "## Verification Ledger"])
        if not state.verifications:
            lines.append("- No verification records yet.")
        else:
            for item in state.verifications:
                lines.append(
                    f"- [{'x' if item.passed else ' '}] `{item.verification_id}` "
                    f"`{item.slice_id}` {item.kind}: {item.summary}"
                )
                if item.command:
                    lines.append(f"  - Command: `{item.command}`")
                if item.evidence_paths:
                    lines.append(
                        f"  - Evidence: {', '.join(f'`{path}`' for path in item.evidence_paths)}"
                    )
        lines.extend(["", "## Blockers"])
        if not state.blockers:
            lines.append("- No blockers recorded.")
        else:
            for item in state.blockers:
                lines.extend(
                    [
                        f"- {_blocker_icon(item.status)} `{item.blocker_id}` [{item.severity}] {item.title}",
                        f"  - Detail: {item.detail}",
                        f"  - Impacted slices: {', '.join(item.impacted_slices) if item.impacted_slices else 'n/a'}",
                        f"  - Unblockers: {', '.join(item.unblockers) if item.unblockers else 'n/a'}",
                    ]
                )
        lines.extend(["", "## Latest Checkpoint"])
        if not state.checkpoints:
            lines.append("- No checkpoints yet.")
        else:
            latest = state.checkpoints[-1]
            lines.extend(
                [
                    f"- Checkpoint: `{latest.checkpoint_id}`",
                    f"- Focus: {latest.focus}",
                    f"- Summary: {latest.summary}",
                    f"- Next action: {latest.next_action}",
                ]
            )
        return "\n".join(lines).rstrip() + "\n"

    def _render_document_manifest(self, state: AtlasDeliveryState) -> str:
        lines = [
            "# Atlas Document Manifest",
            "",
            f"- Updated at: `{state.updated_at or _now_iso()}`",
            f"- Master document: `{state.master_document_path}`",
            f"- Task tree: `{DEFAULT_TASK_PATH}`",
            f"- Resume index: `{DEFAULT_RESUME_INDEX_PATH}`",
            f"- Appendices tracked: {len(state.appendix_paths)}",
            "",
        ]
        if not state.document_manifest:
            lines.append("No document manifest captured yet.")
            return "\n".join(lines).rstrip() + "\n"

        for document in state.document_manifest:
            lines.extend(
                [
                    f"## {Path(document.path).name}",
                    f"- Role: `{document.role}`",
                    f"- Exists: {'yes' if document.exists else 'no'}",
                    f"- Words: {document.word_count}",
                    f"- Lines: {document.line_count}",
                    f"- Sections: {document.section_count}",
                    f"- Last modified: `{document.last_modified_at or 'n/a'}`",
                    f"- Last synced: `{document.last_synced_at or 'n/a'}`",
                    f"- Summary: {document.summary or 'n/a'}",
                ]
            )
            if document.sections:
                lines.append("- Headings:")
                for section in document.sections:
                    lines.append(
                        f"  - H{section.level} {section.title} "
                        f"({section.anchor}, line {section.line_number}, words {section.word_count})"
                    )
            lines.append("")
        return "\n".join(lines).rstrip() + "\n"

    def _render_handoff_summary(self, state: AtlasDeliveryState) -> str:
        assessment = self._completion_assessment(state)
        latest = state.checkpoints[-1] if state.checkpoints else None
        active = self._active_slice(state)
        lines = [
            "# Atlas Handoff Summary",
            "",
            f"- Objective: {state.objective or 'Pending objective'}",
            f"- Delivery mode: `{state.delivery_mode}`",
            f"- Complexity tier: `{state.complexity_tier}`",
            f"- Contract confirmed: {'yes' if state.contract_confirmed else 'no'}",
            f"- Active slice: `{active.slice_id}` {active.title}" if active else "- Active slice: None",
            f"- Ready for final report: {'yes' if assessment['ready'] else 'no'}",
            "",
            "## Documents",
            f"- Master document: `{state.master_document_path}`",
            f"- Task tree: `{DEFAULT_TASK_PATH}`",
            f"- Resume index: `{DEFAULT_RESUME_INDEX_PATH}`",
        ]
        if state.appendix_paths:
            lines.extend(f"- Appendix: `{path}`" for path in state.appendix_paths)
        else:
            lines.append("- Appendix: None recorded")

        lines.extend(["", "## Progress"])
        if not state.slices:
            lines.append("- No slices planned yet.")
        else:
            for item in self._sort_slices(state.slices):
                lines.append(f"- {_status_icon(item.status)} `{item.slice_id}` {item.title}")

        lines.extend(["", "## Risks and Blockers"])
        open_blockers = [item for item in state.blockers if item.status == "open"]
        if open_blockers:
            for blocker in open_blockers:
                lines.append(f"- `{blocker.blocker_id}` [{blocker.severity}] {blocker.title}: {blocker.detail}")
        else:
            lines.append("- No open blockers recorded.")

        lines.extend(["", "## Verification"])
        if state.verifications:
            for verification in state.verifications[-5:]:
                lines.append(
                    f"- [{'x' if verification.passed else ' '}] `{verification.verification_id}` "
                    f"{verification.summary}"
                )
        else:
            lines.append("- No verification records yet.")

        lines.extend(["", "## Next Action"])
        if latest is not None and latest.next_action:
            lines.append(f"- {latest.next_action}")
        else:
            lines.append(f"- {self._recommend_next_action(state)}")
        return "\n".join(lines).rstrip() + "\n"

    def _render_final_report(self, state: AtlasDeliveryState, assessment: Dict[str, Any]) -> str:
        completed_slices = [AtlasSliceRecord.from_dict(item) for item in assessment.get("completed_slices", [])]
        open_slices = [AtlasSliceRecord.from_dict(item) for item in assessment.get("open_slices", [])]
        open_blockers = [AtlasBlockerRecord.from_dict(item) for item in assessment.get("open_blockers", [])]
        failed_verifications = [
            AtlasVerificationRecord.from_dict(item)
            for item in assessment.get("failed_verifications", [])
        ]

        lines = [
            "# Atlas Final Delivery Report",
            "",
            "## Objective",
            state.objective or "Pending objective.",
            "",
            "## Contract Summary",
            state.contract_summary or "Pending contract summary.",
            "",
            "## Completion Gate Result",
            f"- Ready for final report: {'yes' if assessment.get('ready') else 'no'}",
            f"- Delivery mode: `{state.delivery_mode}`",
            f"- Complexity tier: `{state.complexity_tier}`",
            f"- Contract confirmed: {'yes' if state.contract_confirmed else 'no'}",
            "",
            "## Delivered Slices",
        ]
        if completed_slices:
            for item in completed_slices:
                lines.extend(
                    [
                        f"- `{item.slice_id}` {item.title}",
                        f"  - Delivered changes: {', '.join(item.delivered_changes) if item.delivered_changes else 'n/a'}",
                        f"  - Verification results: {', '.join(item.verification_results) if item.verification_results else 'n/a'}",
                    ]
                )
        else:
            lines.append("- No completed slices recorded.")

        lines.extend(["", "## Verification Summary"])
        if state.verifications:
            for item in state.verifications:
                lines.append(
                    f"- [{'x' if item.passed else ' '}] `{item.verification_id}` `{item.slice_id}` "
                    f"{item.kind}: {item.summary}"
                )
        else:
            lines.append("- No verification records recorded.")

        lines.extend(["", "## Document Set"])
        if state.document_manifest:
            for document in state.document_manifest:
                lines.append(
                    f"- `{document.path}` ({document.role}, "
                    f"{'exists' if document.exists else 'missing'}, "
                    f"{document.section_count} sections)"
                )
        else:
            lines.append("- No document manifest recorded.")

        lines.extend(["", "## Remaining Gaps"])
        if assessment.get("missing_conditions"):
            lines.extend(f"- {item}" for item in assessment["missing_conditions"])
        else:
            lines.append("- No remaining gaps recorded.")

        lines.extend(["", "## Open Slices"])
        if open_slices:
            for item in open_slices:
                lines.append(f"- `{item.slice_id}` [{item.status}] {item.title}")
        else:
            lines.append("- No open slices.")

        lines.extend(["", "## Open Blockers"])
        if open_blockers:
            for item in open_blockers:
                lines.append(f"- `{item.blocker_id}` [{item.severity}] {item.title}: {item.detail}")
        else:
            lines.append("- No open blockers.")

        lines.extend(["", "## Failed Verification Records"])
        if failed_verifications:
            for item in failed_verifications:
                lines.append(f"- `{item.verification_id}` `{item.slice_id}` {item.summary}")
        else:
            lines.append("- No failed verification records.")

        lines.extend(["", "## Recommended Next Actions"])
        if assessment.get("recommendations"):
            lines.extend(f"- {item}" for item in assessment["recommendations"])
        else:
            lines.append("- No additional actions required.")
        return "\n".join(lines).rstrip() + "\n"
