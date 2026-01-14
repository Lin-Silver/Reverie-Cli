"""
Clarification Tool - Allows the AI to proactively ask the user for clarification
"""

from typing import Dict, Any, Optional, List
from .base import BaseTool, ToolResult


class ClarificationTool(BaseTool):
    """
    Allows the AI to proactively ask the user for clarification or more details
    about a task.
    """
    
    name = "ask_clarification"
    description = (
        "Ask the user for clarification or specific details about the current task. "
        "Use this when requirements are vague, you need to make a choice between options, "
        "or you need more context to proceed effectively."
    )
    
    parameters = {
        "type": "object",
        "properties": {
            "question": {
                "type": "string",
                "description": "The specific question to ask the user."
            },
            "options": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Optional list of suggesting options for the user to choose from."
            },
            "context": {
                "type": "string",
                "description": "Brief context about why this clarification is needed."
            }
        },
        "required": ["question"]
    }
    
    def execute(self, question: str, options: Optional[List[str]] = None, context: Optional[str] = None) -> ToolResult:
        """
        In the CLI, we return a status that pauses the AI.
        The UI framework will handle the actual interaction.
        """
        msg = f"Clarification requested: '{question}'"
        if options:
            msg += f"\nOptions: {', '.join(options)}"
        if context:
            msg += f"\nContext: {context}"
            
        return ToolResult.ok(
            f"{msg}\n\n"
            "The system is now waiting for user input. "
            "Do not continue until you receive a response."
        )

    def get_execution_message(self, **kwargs) -> str:
        """
        Overridden to display the actual question in the execution log.
        """
        question = kwargs.get('question', '...')
        return f"Requesting clarification: \"{question}\""
