"""Hard, software-enforced capability policy for AI tool execution."""

from __future__ import annotations

from typing import Any, Dict, Optional


PERMISSION_LEVELS = ("read_only", "workspace_write", "developer", "full_control")
DEFAULT_PERMISSION_LEVEL = "full_control"

# Approval modes layered on top of the hard permission level.
#   default    - software-only checker (historic behavior)
#   auto_check - one extra model call reviews each response's tool calls
#   strict     - every tool call waits for an explicit user decision
PERMISSION_MODES = ("default", "auto_check", "strict")
DEFAULT_PERMISSION_MODE = "default"
_MODE_ALIASES = {
    "auto": "auto_check",
    "autocheck": "auto_check",
    "auto-check": "auto_check",
    "check": "auto_check",
    "approve_for_me": "auto_check",
    "manual": "strict",
    "always_ask": "strict",
    "ask": "strict",
    "off": "default",
    "none": "default",
    "builtin": "default",
}

RISK_LEVELS = ("none", "low", "medium", "high", "critical")
DEFAULT_RISK_THRESHOLD = "medium"
_RISK_ALIASES = {
    "safe": "none",
    "no": "none",
    "minimal": "low",
    "moderate": "medium",
    "med": "medium",
    "elevated": "high",
    "severe": "critical",
    "danger": "critical",
    "dangerous": "critical",
}
_LEVEL_ALIASES = {
    "readonly": "read_only",
    "read-only": "read_only",
    "workspace": "workspace_write",
    "write": "workspace_write",
    "shell": "developer",
    "full": "full_control",
}

_WRITE_TOOLS = {
    "str_replace_editor", "create_file", "delete_file", "file_ops",
    "memory_manager", "task_manager", "evolution_feedback",
}
_DEVELOPER_TOOLS = {
    "command_exec", "web_search", "web_fetch", "text_to_image", "text_to_video",
    "media_generation_capabilities",
}
_FULL_CONTROL_TOOLS = {"browser_controler", "subagent"}
_COMPUTER_USE_PREFIXES = ("computer_", "open_computer", "click", "drag", "scroll", "type_text", "key_press")


def normalize_permission_level(value: Any) -> str:
    normalized = str(value or DEFAULT_PERMISSION_LEVEL).strip().lower().replace(" ", "_")
    normalized = _LEVEL_ALIASES.get(normalized, normalized)
    return normalized if normalized in PERMISSION_LEVELS else DEFAULT_PERMISSION_LEVEL


def normalize_permission_mode(value: Any) -> str:
    """Normalize the persisted approval mode selector."""
    normalized = str(value or DEFAULT_PERMISSION_MODE).strip().lower().replace(" ", "_").replace("-", "_")
    normalized = _MODE_ALIASES.get(normalized, normalized)
    return normalized if normalized in PERMISSION_MODES else DEFAULT_PERMISSION_MODE


def normalize_risk_level(value: Any, default: str = DEFAULT_RISK_THRESHOLD) -> str:
    """Normalize a reviewer-reported or configured risk level."""
    normalized = str(value or "").strip().lower().replace(" ", "_").replace("-", "_")
    normalized = _RISK_ALIASES.get(normalized, normalized)
    if normalized in RISK_LEVELS:
        return normalized
    fallback = str(default or DEFAULT_RISK_THRESHOLD).strip().lower()
    return fallback if fallback in RISK_LEVELS else DEFAULT_RISK_THRESHOLD


def risk_requires_approval(risk: Any, threshold: Any = DEFAULT_RISK_THRESHOLD) -> bool:
    """Return whether a reviewed risk level must be escalated to the user."""
    level = normalize_risk_level(risk, "medium")
    gate = normalize_risk_level(threshold, DEFAULT_RISK_THRESHOLD)
    return RISK_LEVELS.index(level) >= RISK_LEVELS.index(gate)


def permission_mode_label(value: Any) -> str:
    """Human-facing label for one approval mode."""
    return {
        "default": "Default",
        "auto_check": "Auto Check",
        "strict": "Strict",
    }[normalize_permission_mode(value)]


def permission_mode_description(value: Any) -> str:
    """One-line explanation of one approval mode."""
    return {
        "default": "Built-in software checker only. Tool calls run unless hard policy blocks them.",
        "auto_check": "One extra model call reviews every response's tool calls; only risky calls pause for you.",
        "strict": "Every tool call waits for your explicit approval.",
    }[normalize_permission_mode(value)]


def required_permission_for_tool(tool: Any) -> str:
    name = str(getattr(tool, "name", tool) or "").strip().lower()
    metadata = getattr(tool, "metadata", {})
    if isinstance(metadata, dict) and metadata.get("plugin_id"):
        return "full_control"
    if name in _FULL_CONTROL_TOOLS or name.startswith(_COMPUTER_USE_PREFIXES):
        return "full_control"
    if name in _DEVELOPER_TOOLS:
        return "developer"
    if name in _WRITE_TOOLS or bool(getattr(tool, "destructive", False)):
        return "workspace_write"
    return "read_only"


def permission_denial(tool: Any, configured_level: Any) -> Optional[str]:
    level = normalize_permission_level(configured_level)
    required = required_permission_for_tool(tool)
    if PERMISSION_LEVELS.index(level) >= PERMISSION_LEVELS.index(required):
        return None
    name = str(getattr(tool, "name", tool) or "tool")
    return (
        f"Tool '{name}' is disabled by the '{level}' permission level. "
        f"It requires '{required}'. Change security.permission_level only after reviewing the requested capability."
    )


REVIEW_MODEL_MODES = ("follow", "custom")
DEFAULT_REVIEW_TIMEOUT_SECONDS = 45
DEFAULT_REVIEW_MAX_TOKENS = 900


def default_review_config() -> Dict[str, Any]:
    """Default configuration for the Auto Check reviewer call."""
    return {
        "model_mode": "follow",
        "source": "",
        "model": "",
        "model_index": 0,
        "timeout": DEFAULT_REVIEW_TIMEOUT_SECONDS,
        "max_tokens": DEFAULT_REVIEW_MAX_TOKENS,
        "approve_risk_at": DEFAULT_RISK_THRESHOLD,
        "fail_open": False,
        "review_read_only": False,
    }


def normalize_review_config(value: Any) -> Dict[str, Any]:
    """Normalize the persisted Auto Check reviewer configuration."""
    raw = value if isinstance(value, dict) else {}
    defaults = default_review_config()

    model_mode = str(raw.get("model_mode") or "").strip().lower()
    if model_mode not in REVIEW_MODEL_MODES:
        model_mode = "custom" if str(raw.get("model") or raw.get("source") or "").strip() else "follow"

    def _int(key: str, minimum: int, maximum: int) -> int:
        try:
            number = int(raw.get(key, defaults[key]))
        except (TypeError, ValueError):
            number = int(defaults[key])
        return max(minimum, min(maximum, number))

    def _bool(key: str) -> bool:
        candidate = raw.get(key, defaults[key])
        if isinstance(candidate, bool):
            return candidate
        return str(candidate or "").strip().lower() in {"1", "true", "yes", "on"}

    return {
        "model_mode": model_mode,
        "source": str(raw.get("source") or "").strip().lower(),
        "model": str(raw.get("model") or "").strip(),
        "model_index": _int("model_index", 0, 999),
        "timeout": _int("timeout", 5, 600),
        "max_tokens": _int("max_tokens", 200, 8192),
        "approve_risk_at": normalize_risk_level(raw.get("approve_risk_at"), DEFAULT_RISK_THRESHOLD),
        "fail_open": _bool("fail_open"),
        "review_read_only": _bool("review_read_only"),
    }


def default_security_config() -> Dict[str, Any]:
    """Default persisted security block."""
    return {
        "permission_level": DEFAULT_PERMISSION_LEVEL,
        "permission_mode": DEFAULT_PERMISSION_MODE,
        "strict_allow_read_only": False,
        "review": default_review_config(),
    }


def normalize_security_config(value: Any) -> Dict[str, Any]:
    """Normalize the persisted security block while preserving unknown keys."""
    raw = dict(value) if isinstance(value, dict) else {}
    strict_allow_read_only = raw.get("strict_allow_read_only", False)
    if not isinstance(strict_allow_read_only, bool):
        strict_allow_read_only = str(strict_allow_read_only or "").strip().lower() in {"1", "true", "yes", "on"}
    raw.update(
        {
            "permission_level": normalize_permission_level(raw.get("permission_level")),
            "permission_mode": normalize_permission_mode(raw.get("permission_mode")),
            "strict_allow_read_only": strict_allow_read_only,
            "review": normalize_review_config(raw.get("review")),
        }
    )
    return raw


def _security_block(source: Any) -> Dict[str, Any]:
    security = getattr(source, "security", source)
    return security if isinstance(security, dict) else {}


def resolve_permission_mode(source: Any) -> str:
    """Read the approval mode from a Config or a raw security mapping."""
    return normalize_permission_mode(_security_block(source).get("permission_mode"))


def resolve_review_config(source: Any) -> Dict[str, Any]:
    """Read the reviewer configuration from a Config or a raw security mapping."""
    return normalize_review_config(_security_block(source).get("review"))


def strict_allows_read_only(source: Any) -> bool:
    """Whether Strict mode may auto-allow provably read-only tools."""
    return bool(_security_block(source).get("strict_allow_read_only", False))


# Heuristic priors handed to the reviewer as context and used to bias fail-closed
# behavior. These never replace the reviewer verdict; they only seed it.
_HIGH_RISK_TOOLS = {"delete_file", "command_exec", "computer_control", "open_computer_use"}
_MEDIUM_RISK_TOOLS = {
    "str_replace_editor", "create_file", "file_ops", "browser_controler",
    "subagent", "text_to_image", "text_to_video", "memory_manager",
}


def heuristic_risk_prior(tool: Any, arguments: Optional[Dict[str, Any]] = None) -> str:
    """Cheap static risk prior for one tool call."""
    name = str(getattr(tool, "name", tool) or "").strip().lower()
    if bool(getattr(tool, "read_only", False)):
        return "none"
    if name in _HIGH_RISK_TOOLS or name.startswith(_COMPUTER_USE_PREFIXES):
        return "high"
    metadata = getattr(tool, "metadata", {})
    if isinstance(metadata, dict) and metadata.get("plugin_id"):
        return "medium"
    if name in _MEDIUM_RISK_TOOLS or bool(getattr(tool, "destructive", False)):
        return "medium"
    return "low"
