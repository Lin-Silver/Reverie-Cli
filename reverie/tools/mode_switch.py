"""
Mode switch tool.

Lets the active agent move between supported non-desktop-control modes when the
task would benefit from a different workflow or tool surface.
"""

from __future__ import annotations

from typing import Dict, Optional

from .base import BaseTool, ToolResult
from ..modes import get_mode_description, list_modes, normalize_mode


class ModeSwitchTool(BaseTool):
    """Switch the current Reverie mode without leaving the session."""

    aliases = ("switch_mode",)
    search_hint = "switch into a better specialized workflow mode"
    tool_category = "coordination"
    tool_tags = ("mode", "switch", "workflow", "specialist")
    name = "switch_mode"
    description = (
        "Switch Reverie into a different task mode when another workflow is a better fit. "
        "Available targets exclude Computer Controller mode."
    )
    parameters = {
        "type": "object",
        "properties": {
            "mode": {
                "type": "string",
                "enum": list_modes(include_computer=False, switchable_only=True),
                "description": "Target mode to activate.",
            },
            "reason": {
                "type": "string",
                "description": "Short reason for the mode transition.",
            },
        },
        "required": ["mode"],
    }

    def execute(self, mode: str, reason: str = "") -> ToolResult:
        normalized_mode = normalize_mode(mode)
        if normalized_mode not in list_modes(include_computer=False, switchable_only=True):
            return ToolResult.fail(
                "Unsupported mode target. Available modes: "
                + ", ".join(list_modes(include_computer=False, switchable_only=True))
            )

        agent = self.context.get("agent")
        config_manager = self.context.get("config_manager")
        session_manager = self.context.get("session_manager")

        if not agent:
            return ToolResult.fail("Agent context is unavailable; cannot switch mode")

        previous_mode = normalize_mode(getattr(agent, "mode", "reverie"))
        if previous_mode == normalized_mode:
            return ToolResult.ok(
                f"Mode already set to {normalized_mode}.",
                data={"mode": normalized_mode, "previous_mode": previous_mode},
            )

        agent.update_mode(normalized_mode)

        if config_manager:
            config = config_manager.load()
            config.mode = normalized_mode
            config_manager.save(config)

        if session_manager and session_manager.get_current_session():
            session = session_manager.get_current_session()
            metadata = dict(getattr(session, "metadata", {}) or {})
            metadata["mode"] = normalized_mode
            session.metadata = metadata
            session_manager.save_session(session)

        reason_text = f" Reason: {reason.strip()}" if str(reason or "").strip() else ""
        return ToolResult.ok(
            f"Switched mode from {previous_mode} to {normalized_mode}.{reason_text}\n"
            f"New workflow: {get_mode_description(normalized_mode)}",
            data={
                "mode": normalized_mode,
                "previous_mode": previous_mode,
                "reason": str(reason or "").strip(),
            },
        )

    def get_execution_message(self, mode: str, reason: str = "") -> str:
        normalized_mode = normalize_mode(mode)
        if reason:
            return f"Switching mode to {normalized_mode} ({reason})"
        return f"Switching mode to {normalized_mode}"

