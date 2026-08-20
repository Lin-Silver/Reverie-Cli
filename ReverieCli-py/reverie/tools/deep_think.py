"""Deep Think tool - an explicit scratchpad for models without a native thinking mode.

Some providers expose no reasoning channel at all (plain instruct models), and
some expose one that never actually emits anything the user can see.  Giving the
model a tool whose only job is to receive a long chunk of step-by-step reasoning
recovers deliberation for both cases: the reasoning arrives as ordinary tool-call
arguments, which every provider supports, and Reverie renders it as thinking
content instead of as a tool row.

The tool performs no work.  It exists so the argument text exists.
"""

from __future__ import annotations

from typing import Any

from ..thinking_tool import (
    THINK_TOOL_ALIASES,
    THINK_TOOL_NAME,
    THINK_TOOL_TAG,
    clean_think_argument,
    extract_think_tool_text,
)
from .base import BaseTool, ToolResult


# Anything shorter than this is a placeholder, not deliberation.  We still accept
# it (rejecting would waste a turn) but the acknowledgement nudges the model.
_MIN_USEFUL_THOUGHT_CHARS = 40


class DeepThinkTool(BaseTool):
    """Let the model write out a long chain of reasoning before acting."""

    name = THINK_TOOL_NAME
    aliases = THINK_TOOL_ALIASES
    search_hint = "reason step by step in private before acting"
    tool_category = "reasoning"
    tool_tags = ("thinking", "reasoning", "planning", "analysis")
    read_only = True
    concurrency_safe = True
    destructive = False
    workspace_checkpoint = False
    max_result_chars = 4_000
    description = (
        "Think step by step before acting, in the open. Write your full reasoning into "
        "the 'thought' argument: restate the problem, list what you know and what you "
        "still need, weigh the options, then commit to a concrete next step. Nothing is "
        "executed and nothing here is read as your answer -- this is your reasoning, "
        "shown to the user as thinking. Call it once at the start of every turn, before "
        "any other tool and before replying, and again whenever a result contradicts "
        "what you expected. Do not call it twice in a row without doing real work in "
        "between, and never use it to reply to the user."
    )

    parameters = {
        "type": "object",
        "properties": {
            "thought": {
                "type": "string",
                "description": (
                    "Your complete step-by-step reasoning. Be long and concrete: "
                    "state the goal, the evidence you already have, the alternatives "
                    "you considered and why you rejected them, and the single next "
                    "action you will take. Plain prose or numbered steps."
                ),
            },
            "topic": {
                "type": "string",
                "description": "Optional short label for what this reasoning is about (a few words).",
            },
            "next_step": {
                "type": "string",
                "description": (
                    "Optional one-line statement of the concrete action you will take "
                    "immediately after this call."
                ),
            },
        },
        "required": ["thought"],
    }

    def execute(
        self,
        thought: Any = "",
        topic: Any = None,
        next_step: Any = None,
        **_ignored: Any,
    ) -> ToolResult:
        """Record the reasoning and hand control straight back to the model."""
        text = clean_think_argument(thought)
        if not text:
            return ToolResult.fail(
                "No reasoning was supplied. Put your full step-by-step thinking in the "
                "'thought' argument, or skip this tool and act directly."
            )

        follow_up = clean_think_argument(next_step)
        payload = {
            "tag": THINK_TOOL_TAG,
            "thought": text,
            "topic": clean_think_argument(topic),
            "next_step": follow_up,
            "characters": len(text),
        }

        if len(text) < _MIN_USEFUL_THOUGHT_CHARS:
            return ToolResult.ok(
                "Thought recorded, but it was very short. Either think properly or act -- "
                "do not call deep_think again just to pad it out.",
                payload,
            )

        acknowledgement = "Thought recorded. Now act on it"
        if follow_up:
            acknowledgement += f": {follow_up}"
        else:
            acknowledgement += " -- call a real tool or answer the user."
        return ToolResult.ok(acknowledgement, payload)

    def get_execution_message(self, **kwargs) -> str:
        """Describe the call in one line for the tool timeline."""
        topic = clean_think_argument(kwargs.get("topic"))
        if topic:
            return f"Thinking through {topic}"
        return "Thinking it through"


__all__ = ["DeepThinkTool", "THINK_TOOL_TAG", "extract_think_tool_text"]
