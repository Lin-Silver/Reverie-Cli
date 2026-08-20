"""Shared vocabulary for the experimental Thinking Tool.

The tool implementation, the terminal renderer, and the GUI bridge all need the
same tool names and the same "what text do we actually show" rule.  Keeping them
in a dependency-free leaf module lets the CLI display layer use them without
importing the whole ``reverie.tools`` package at startup.
"""

from __future__ import annotations

from typing import Any, Dict, Optional


#: Primary tool name advertised to the model.
THINK_TOOL_NAME = "deep_think"

#: Aliases the model may use for the same call.
THINK_TOOL_ALIASES: tuple[str, ...] = ("think", "think_tool", "deep_thinking")

#: Tag the terminal renders this content under.
THINK_TOOL_TAG = "think_tool"

#: Every accepted spelling, lowercased, for cheap membership tests.
THINK_TOOL_NAMES = frozenset(
    {THINK_TOOL_NAME.lower()} | {alias.lower() for alias in THINK_TOOL_ALIASES}
)


def is_think_tool(tool_name: Any) -> bool:
    """Whether a tool name refers to the Thinking Tool scratchpad."""
    return str(tool_name or "").strip().lower() in THINK_TOOL_NAMES


def clean_think_argument(value: Any) -> str:
    """Normalize an argument a model may send as any JSON scalar or list."""
    if value is None:
        return ""
    if isinstance(value, (list, tuple)):
        value = "\n".join(str(item) for item in value if str(item or "").strip())
    elif not isinstance(value, str):
        value = str(value)
    return value.strip()


def extract_think_tool_text(arguments: Optional[Dict[str, Any]]) -> str:
    """Return the renderable thinking text from a ``deep_think`` call's arguments.

    Shared by the terminal renderer and the GUI bridge so both show the same
    body, including for partially-streamed or malformed argument payloads.
    """
    if not isinstance(arguments, dict):
        return ""

    thought = clean_think_argument(arguments.get("thought"))
    topic = clean_think_argument(arguments.get("topic"))
    next_step = clean_think_argument(arguments.get("next_step"))

    sections: list[str] = []
    if topic:
        sections.append(f"**{topic}**")
    if thought:
        sections.append(thought)
    if next_step:
        sections.append(f"Next: {next_step}")
    return "\n\n".join(sections).strip()


__all__ = [
    "THINK_TOOL_ALIASES",
    "THINK_TOOL_NAME",
    "THINK_TOOL_NAMES",
    "THINK_TOOL_TAG",
    "clean_think_argument",
    "extract_think_tool_text",
    "is_think_tool",
]
