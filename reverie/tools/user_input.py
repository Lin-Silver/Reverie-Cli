"""
User Input Tool - Allows the AI to explicitly request feedback or approval
"""

from typing import Dict, Any, Optional
from .base import BaseTool, ToolResult


class UserInputTool(BaseTool):
    """
    Allows the AI to explicitly request feedback or approval from the user.
    """
    
    name = "userInput"
    description = (
        "Ask the user for specific input, feedback, or approval. "
        "Use this when you need a clear 'yes' or detailed feedback before proceeding. "
        "The reason parameter helps the system track the purpose of the request."
    )
    
    parameters = {
        "type": "object",
        "properties": {
            "question": {
                "type": "string",
                "description": "The question or request for the user."
            },
            "reason": {
                "type": "string",
                "description": "The specific reason for the request (e.g., 'spec-requirements-review')."
            }
        },
        "required": ["question", "reason"]
    }
    
    def execute(self, question: str, reason: str) -> ToolResult:
        """
        In the CLI, we just return a status to the AI.
        The UI will display the question as part of the normal streaming output.
        """
        return ToolResult.ok(
            f"Question asked: '{question}' for reason '{reason}'. "
            "The system is now waiting for the user to respond in the chat. "
            "Do not continue with further tool calls until you receive a user message."
        )

    def get_execution_message(self, **kwargs) -> str:
        """
        Overridden to display the actual question in the execution log.
        """
        question = kwargs.get('question', '...')
        reason = kwargs.get('reason', 'user input')
        return f"Asking user ({reason}): \"{question}\""
