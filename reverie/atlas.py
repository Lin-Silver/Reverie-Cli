"""
Reverie-Atlas mode configuration and prompt helpers.

Atlas is a research-first, document-driven engineering mode for complex
projects. This module centralizes the persisted configuration and the extra
rules injected into the system prompt so the mode behaves consistently.
"""

from __future__ import annotations

from typing import Any, Dict, List


ATLAS_DEFAULT_MASTER_DOCUMENT_FILENAME = "Master Document.md"
ATLAS_DEFAULT_APPENDIX_FILENAME_PATTERN = "附录 {label} — {topic}.md"

ATLAS_MASTER_DOCUMENT_SECTIONS = (
    "项目目标与问题定义",
    "代码库现状与证据摘要",
    "目标架构与系统边界",
    "关键子系统拆解",
    "数据流、控制流与依赖关系",
    "约束、风险与非目标",
    "分阶段实施策略",
    "质量门禁与验证矩阵",
    "附录索引",
)

ATLAS_APPENDIX_SECTIONS = (
    "范围与背景",
    "实现现状与证据",
    "目标设计",
    "接口/数据结构/协议",
    "边界条件与故障模式",
    "实施步骤",
    "验证方法",
)

ATLAS_CONFIRMATION_POINTS = (
    "文档中的目标、边界、约束和优先级是否准确",
    "主文档与附录的信息是否足够支撑后续实施",
    "是否允许按照文档中的阶段顺序开始逐步实施",
)

ATLAS_IMPLEMENTATION_RULES = (
    "以文档为执行基线，小步推进，不跳阶段",
    "每完成一批代码就重新检查集成点、影响面和测试",
    "优先保证设计完整性、可维护性和验证深度，而不是追求一次性快写",
    "如果发现文档需要修正，先更新文档再继续实施",
    "除非用户暂停，否则不要停留在文档阶段而不继续完成项目",
)


ATLAS_DEVELOPMENT_PROTOCOL = (
    "Research until subsystem boundaries, constraints, and unknowns are explicit",
    "Create or refresh the master document and appendix set before broad implementation",
    "Explain the document baseline to the user and confirm scope when the work is non-trivial",
    "Implement in document-backed slices: choose one slice, retrieve context again, wire it fully, verify it, then refresh the docs",
    "Keep a visible engineering chain: evidence -> document decision -> implementation slice -> verification result -> document refresh",
)

ATLAS_MEMORY_PROTOCOL = (
    "Before a likely automatic session rotation, create a checkpoint and emit a compact handoff summary into the conversation",
    "Each handoff summary should preserve confirmed scope, document files, finished slices, active slice, unresolved risks, and the next intended action",
    "After automatic rotation or resume, re-anchor on workspace memory plus the document baseline before making new architecture or implementation decisions",
    "Do not cross an unresolved architecture decision or half-applied code change without first recording the exact state",
    "Use workspace memory updates after major phases so long-running Atlas sessions can resume with durable project context",
)


def _coerce_bool(value: Any, default: bool) -> bool:
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


def _coerce_int(
    value: Any,
    default: int,
    minimum: int = 0,
    maximum: int | None = None,
) -> int:
    try:
        number = int(value)
    except (TypeError, ValueError):
        number = default
    if number < minimum:
        number = minimum
    if maximum is not None and number > maximum:
        number = maximum
    return number


def default_atlas_mode_config() -> Dict[str, Any]:
    """Return the default persisted configuration for Reverie-Atlas."""
    return {
        "research_first": True,
        "master_document_required": True,
        "appendix_documents_required": True,
        "minimum_appendix_count": 2,
        "master_document_filename": ATLAS_DEFAULT_MASTER_DOCUMENT_FILENAME,
        "appendix_filename_pattern": ATLAS_DEFAULT_APPENDIX_FILENAME_PATTERN,
        "require_document_confirmation": True,
        "implementation_after_confirmation": True,
        "slow_and_rigorous_execution": True,
        "implementation_review_required": True,
        "documentation_refresh_after_implementation": True,
        "use_context_engine_memory": True,
        "verification_depth": "deep",
    }


def normalize_atlas_mode_config(raw_config: Any) -> Dict[str, Any]:
    """Normalize Atlas configuration loaded from config.json."""
    cfg = default_atlas_mode_config()
    if isinstance(raw_config, dict):
        cfg.update(raw_config)

    cfg["research_first"] = _coerce_bool(cfg.get("research_first"), True)
    cfg["master_document_required"] = _coerce_bool(cfg.get("master_document_required"), True)
    cfg["appendix_documents_required"] = _coerce_bool(cfg.get("appendix_documents_required"), True)
    cfg["minimum_appendix_count"] = _coerce_int(cfg.get("minimum_appendix_count"), 2, minimum=0, maximum=26)
    cfg["require_document_confirmation"] = _coerce_bool(cfg.get("require_document_confirmation"), True)
    cfg["implementation_after_confirmation"] = _coerce_bool(cfg.get("implementation_after_confirmation"), True)
    cfg["slow_and_rigorous_execution"] = _coerce_bool(cfg.get("slow_and_rigorous_execution"), True)
    cfg["implementation_review_required"] = _coerce_bool(cfg.get("implementation_review_required"), True)
    cfg["documentation_refresh_after_implementation"] = _coerce_bool(
        cfg.get("documentation_refresh_after_implementation"),
        True,
    )
    cfg["use_context_engine_memory"] = _coerce_bool(cfg.get("use_context_engine_memory"), True)

    master_document_filename = str(cfg.get("master_document_filename", "") or "").strip()
    cfg["master_document_filename"] = master_document_filename or ATLAS_DEFAULT_MASTER_DOCUMENT_FILENAME

    appendix_filename_pattern = str(cfg.get("appendix_filename_pattern", "") or "").strip()
    cfg["appendix_filename_pattern"] = appendix_filename_pattern or ATLAS_DEFAULT_APPENDIX_FILENAME_PATTERN

    verification_depth = str(cfg.get("verification_depth", "deep") or "").strip().lower()
    if verification_depth not in {"standard", "deep"}:
        verification_depth = "deep"
    cfg["verification_depth"] = verification_depth

    return cfg


def build_atlas_additional_rules(
    raw_config: Any,
    *,
    workspace_memory_available: bool = False,
    lsp_available: bool = False,
) -> str:
    """Render Atlas-specific guidance appended to the system prompt."""
    cfg = normalize_atlas_mode_config(raw_config)
    lines: List[str] = [
        "## Atlas Execution Profile",
        f"- Research-first workflow: {'enabled' if cfg['research_first'] else 'disabled'}",
        f"- Master document required: {'yes' if cfg['master_document_required'] else 'no'}",
        f"- Appendix bundle required: {'yes' if cfg['appendix_documents_required'] else 'no'}",
        f"- Minimum appendix count target: {cfg['minimum_appendix_count']}",
        f"- Master document filename: `{cfg['master_document_filename']}`",
        f"- Appendix filename pattern: `{cfg['appendix_filename_pattern']}`",
        f"- User confirmation after documents: {'required' if cfg['require_document_confirmation'] else 'optional'}",
        f"- Continue into implementation after confirmation: {'yes' if cfg['implementation_after_confirmation'] else 'no'}",
        f"- Slow, rigorous execution style: {'enabled' if cfg['slow_and_rigorous_execution'] else 'disabled'}",
        f"- Refresh docs after implementation: {'yes' if cfg['documentation_refresh_after_implementation'] else 'no'}",
        f"- Context Engine memory support: {'enabled' if cfg['use_context_engine_memory'] else 'disabled'}",
        f"- Workspace global memory currently: {'available' if workspace_memory_available else 'not yet indexed'}",
        f"- Optional LSP bridge currently: {'available' if lsp_available else 'unavailable'}",
        f"- Verification depth target: `{cfg['verification_depth']}`",
        "",
        "## Atlas Persistence Contract",
        "- Persist until the active task is handled end to end whenever feasible: do not stop at research, documentation, progress recaps, or partial implementation if the user asked for delivery.",
        "- Treat `continue`, `继续`, `开始`, `go on`, and `keep going` as explicit permission to resume the next unfinished implementation slice rather than summarizing the current status.",
        "- Use `atlas_delivery_orchestrator` to bootstrap the delivery ledger, plan slices, record blockers and verification evidence, checkpoint state, and check closure readiness before final summaries.",
        "",
        "## Atlas Document Blueprint",
        "- Master document should usually cover:",
    ]
    lines.extend(f"  - {section}" for section in ATLAS_MASTER_DOCUMENT_SECTIONS)
    lines.extend(
        [
            "- Each appendix should usually cover:",
        ]
    )
    lines.extend(f"  - {section}" for section in ATLAS_APPENDIX_SECTIONS)
    lines.extend(
        [
            "",
            "## Atlas Confirmation Gate",
            "- After the first complete document bundle, explain the doc set to the user in plain language.",
            "- Use `userInput` to confirm the document information before broad implementation whenever the project scope is non-trivial.",
            "- If the active document baseline has already been confirmed and the scope has not materially changed, continue implementation without reopening confirmation.",
            "- Re-confirm only when architecture, delivery scope, constraints, or implementation direction changes in a meaningful way.",
            "- The confirmation should explicitly cover:",
        ]
    )
    lines.extend(f"  - {item}" for item in ATLAS_CONFIRMATION_POINTS)
    lines.extend(
        [
            "",
            "## Atlas Implementation Contract",
            "- Once the user confirms the document set, continue from the documents into full implementation instead of stopping at documentation.",
            "- Keep the implementation deliberate, detailed, and quality-first.",
            "- Treat the document set as a living engineering contract and refresh it whenever the delivered code changes the validated design.",
            "- Before any final-style summary or handoff, run `atlas_delivery_orchestrator(action=\"assess_completion\")`; if it reports unfinished slices or blockers, continue working or surface the concrete blocker instead of wrapping up.",
            "- Implementation rules:",
        ]
    )
    lines.extend(f"  - {item}" for item in ATLAS_IMPLEMENTATION_RULES)
    lines.extend(
        [
            "- Use repository evidence, workspace memory, and verification feedback to keep the documents and code aligned.",
            "- Record stable findings, confirmed constraints, and unfinished implementation slices so Context Engine memory can support later Atlas sessions.",
            "",
            "## Atlas Development Protocol",
            "- Atlas should usually follow this sequence:",
        ]
    )
    lines.extend(f"  - {item}" for item in ATLAS_DEVELOPMENT_PROTOCOL)
    lines.extend(
        [
            "",
            "## Atlas Context Continuity Protocol",
            "- Atlas should treat automatic Context Engine rotation as a durable handoff process:",
        ]
    )
    lines.extend(f"  - {item}" for item in ATLAS_MEMORY_PROTOCOL)
    return "\n".join(lines)
