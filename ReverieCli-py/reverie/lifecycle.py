"""Lifecycle hooks and audit trail for Reverie agent tool activity."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional
from uuid import uuid4


AUDIT_SCHEMA_VERSION = "reverie.lifecycle.audit.v1"
HOOK_CONFIG_VERSION = "reverie.lifecycle.hooks.v1"


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _safe_json(value: Any) -> Any:
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, dict):
        return {str(key): _safe_json(item) for key, item in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [_safe_json(item) for item in value]
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    return str(value)


def _compact(value: Any, max_chars: int = 800) -> Any:
    text = json.dumps(_safe_json(value), ensure_ascii=False, sort_keys=True)
    if len(text) <= max_chars:
        try:
            return json.loads(text)
        except Exception:
            return text
    return text[: max_chars - 1] + "..."


@dataclass
class LifecycleDecision:
    allowed: bool = True
    action: str = "allow"
    reason: str = ""
    rule_id: str = ""


@dataclass
class LifecycleHookRule:
    id: str
    phase: str = "*"
    tool: str = "*"
    action: str = "audit"
    enabled: bool = True
    args_contains: str = ""
    message: str = ""
    priority: int = 100
    source: str = "workspace"

    @classmethod
    def from_dict(cls, payload: Dict[str, Any]) -> "LifecycleHookRule":
        return cls(
            id=str(payload.get("id") or f"rule-{uuid4().hex[:8]}"),
            phase=str(payload.get("phase") or "*"),
            tool=str(payload.get("tool") or "*"),
            action=str(payload.get("action") or "audit").lower(),
            enabled=bool(payload.get("enabled", True)),
            args_contains=str(payload.get("args_contains") or ""),
            message=str(payload.get("message") or ""),
            priority=int(payload.get("priority", 100) or 100),
            source=str(payload.get("source") or "workspace"),
        )

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "phase": self.phase,
            "tool": self.tool,
            "action": self.action,
            "enabled": self.enabled,
            "args_contains": self.args_contains,
            "message": self.message,
            "priority": self.priority,
            "source": self.source,
        }

    def matches(self, phase: str, tool: str, arguments: Dict[str, Any]) -> bool:
        if not self.enabled:
            return False
        if self.phase not in {"*", phase}:
            return False
        if self.tool not in {"*", tool}:
            return False
        needle = self.args_contains.strip().lower()
        if needle:
            haystack = json.dumps(_safe_json(arguments), ensure_ascii=False).lower()
            if needle not in haystack:
                return False
        return True


@dataclass
class LifecycleEvent:
    phase: str
    tool: str = ""
    action: str = "audit"
    allowed: bool = True
    success: Optional[bool] = None
    reason: str = ""
    rule_id: str = ""
    duration_ms: Optional[int] = None
    arguments: Any = field(default_factory=dict)
    result: Any = field(default_factory=dict)
    context: Dict[str, Any] = field(default_factory=dict)
    timestamp: str = field(default_factory=_utc_now)

    def to_record(self) -> Dict[str, Any]:
        return {
            "schema": AUDIT_SCHEMA_VERSION,
            "timestamp": self.timestamp,
            "phase": self.phase,
            "tool": self.tool,
            "action": self.action,
            "allowed": self.allowed,
            "success": self.success,
            "reason": self.reason,
            "rule_id": self.rule_id,
            "duration_ms": self.duration_ms,
            "arguments": _compact(self.arguments),
            "result": _compact(self.result),
            "context": _compact(self.context, max_chars=1000),
        }


class LifecycleAuditStore:
    """Append-only JSONL audit store with small summary helpers."""

    def __init__(self, project_data_dir: Path):
        self.root = Path(project_data_dir) / "lifecycle"
        self.audit_path = self.root / "audit.jsonl"
        self.config_path = self.root / "hooks.json"

    def append(self, event: LifecycleEvent) -> None:
        self.root.mkdir(parents=True, exist_ok=True)
        with self.audit_path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(event.to_record(), ensure_ascii=False, sort_keys=True) + "\n")

    def read_recent(self, limit: int = 50) -> List[Dict[str, Any]]:
        if not self.audit_path.exists():
            return []
        lines = self.audit_path.read_text(encoding="utf-8", errors="replace").splitlines()
        records: List[Dict[str, Any]] = []
        for line in lines[-max(limit, 1):]:
            try:
                item = json.loads(line)
            except Exception:
                continue
            if isinstance(item, dict):
                records.append(item)
        return records

    def summarize(self, limit: int = 500) -> Dict[str, Any]:
        records = self.read_recent(limit)
        denied = sum(1 for item in records if item.get("allowed") is False)
        failures = sum(1 for item in records if item.get("success") is False)
        by_tool: Dict[str, int] = {}
        by_phase: Dict[str, int] = {}
        for item in records:
            tool = str(item.get("tool") or "runtime")
            phase = str(item.get("phase") or "unknown")
            by_tool[tool] = by_tool.get(tool, 0) + 1
            by_phase[phase] = by_phase.get(phase, 0) + 1
        return {
            "audit_path": str(self.audit_path),
            "config_path": str(self.config_path),
            "events": len(records),
            "denied": denied,
            "failures": failures,
            "by_tool": by_tool,
            "by_phase": by_phase,
            "recent": records[-20:],
        }


class LifecycleManager:
    """Rule-driven lifecycle hook manager for the active workspace."""

    def __init__(self, project_data_dir: Path, project_root: Optional[Path] = None):
        self.project_data_dir = Path(project_data_dir)
        self.project_root = Path(project_root).resolve() if project_root else None
        self.store = LifecycleAuditStore(self.project_data_dir)
        self.rules = self._load_rules()
        if not self.store.config_path.exists():
            try:
                self.save_rules()
            except Exception:
                pass

    def _default_rules(self) -> List[LifecycleHookRule]:
        return [
            LifecycleHookRule(
                id="audit-all-tools",
                phase="*",
                tool="*",
                action="audit",
                priority=1000,
                source="builtin",
                message="Record every lifecycle transition.",
            ),
            LifecycleHookRule(
                id="deny-shell-delete",
                phase="pre_tool_use",
                tool="command_exec",
                action="deny",
                args_contains="Remove-Item",
                priority=10,
                source="builtin",
                message="Terminal deletion must use the dedicated delete_file tool.",
            ),
            LifecycleHookRule(
                id="warn-write-tools",
                phase="pre_tool_use",
                tool="str_replace_editor",
                action="warn",
                priority=100,
                source="builtin",
                message="Write-capable edit tool invoked.",
            ),
        ]

    def _load_rules(self) -> List[LifecycleHookRule]:
        defaults = self._default_rules()
        path = self.store.config_path
        if not path.exists():
            return defaults
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            return defaults
        raw_rules = payload.get("rules") if isinstance(payload, dict) else None
        if not isinstance(raw_rules, list):
            return defaults
        custom = [LifecycleHookRule.from_dict(item) for item in raw_rules if isinstance(item, dict)]
        return sorted(custom or defaults, key=lambda item: item.priority)

    def save_rules(self) -> None:
        self.store.root.mkdir(parents=True, exist_ok=True)
        payload = {
            "schema": HOOK_CONFIG_VERSION,
            "updated_at": _utc_now(),
            "rules": [rule.to_dict() for rule in sorted(self.rules, key=lambda item: item.priority)],
        }
        self.store.config_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    def evaluate(self, phase: str, tool: str, arguments: Dict[str, Any]) -> LifecycleDecision:
        matched = [
            rule
            for rule in sorted(self.rules, key=lambda item: item.priority)
            if rule.matches(phase, tool, arguments)
        ]
        for rule in matched:
            if rule.action == "deny":
                return LifecycleDecision(False, "deny", rule.message or "Lifecycle hook denied the action.", rule.id)
            if rule.action == "warn":
                return LifecycleDecision(True, "warn", rule.message, rule.id)
        if matched:
            rule = matched[0]
            return LifecycleDecision(True, rule.action or "audit", rule.message, rule.id)
        return LifecycleDecision(True, "allow", "", "")

    def emit(self, event: LifecycleEvent) -> None:
        self.store.append(event)

    def before_tool(self, tool: str, arguments: Dict[str, Any], context: Dict[str, Any]) -> LifecycleDecision:
        decision = self.evaluate("pre_tool_use", tool, arguments)
        self.emit(
            LifecycleEvent(
                phase="pre_tool_use",
                tool=tool,
                action=decision.action,
                allowed=decision.allowed,
                reason=decision.reason,
                rule_id=decision.rule_id,
                arguments=arguments,
                context=self._context_summary(context),
            )
        )
        return decision

    def after_tool(
        self,
        tool: str,
        arguments: Dict[str, Any],
        result: Any,
        duration_ms: int,
        context: Dict[str, Any],
    ) -> None:
        success = bool(getattr(result, "success", False))
        payload = {
            "success": success,
            "output": getattr(result, "output", ""),
            "error": getattr(result, "error", ""),
            "data": getattr(result, "data", {}),
        }
        self.emit(
            LifecycleEvent(
                phase="post_tool_use",
                tool=tool,
                action="audit",
                allowed=True,
                success=success,
                duration_ms=duration_ms,
                arguments=arguments,
                result=payload,
                context=self._context_summary(context),
            )
        )

    def _context_summary(self, context: Dict[str, Any]) -> Dict[str, Any]:
        project_root = context.get("project_root")
        session_id = ""
        session_manager = context.get("session_manager")
        if session_manager is not None and hasattr(session_manager, "get_current_session"):
            try:
                current_session = session_manager.get_current_session()
                session_id = str(getattr(current_session, "id", "") or "")
            except Exception:
                session_id = ""
        return {
            "project_root": str(project_root) if project_root else "",
            "tool_call_id": str(context.get("active_tool_call_id") or ""),
            "subagent_id": str(context.get("subagent_id") or "main"),
            "is_subagent": bool(context.get("is_subagent", False)),
            "session_id": session_id,
        }

    def summary(self) -> Dict[str, Any]:
        data = self.store.summarize()
        data["rules"] = [rule.to_dict() for rule in sorted(self.rules, key=lambda item: item.priority)]
        data["enabled"] = True
        return data

    def recent(self, limit: int = 50) -> List[Dict[str, Any]]:
        return self.store.read_recent(limit)


def summarize_lifecycle(project_data_dir: Path, project_root: Optional[Path] = None) -> Dict[str, Any]:
    return LifecycleManager(project_data_dir, project_root=project_root).summary()


def read_recent_lifecycle_events(project_data_dir: Path, limit: int = 50) -> List[Dict[str, Any]]:
    return LifecycleAuditStore(Path(project_data_dir)).read_recent(limit)
