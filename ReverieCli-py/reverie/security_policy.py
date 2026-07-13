"""Hard, software-enforced capability policy for AI tool execution."""

from __future__ import annotations

from typing import Any, Optional


PERMISSION_LEVELS = ("read_only", "workspace_write", "developer", "full_control")
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
    normalized = str(value or "workspace_write").strip().lower().replace(" ", "_")
    normalized = _LEVEL_ALIASES.get(normalized, normalized)
    return normalized if normalized in PERMISSION_LEVELS else "workspace_write"


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
