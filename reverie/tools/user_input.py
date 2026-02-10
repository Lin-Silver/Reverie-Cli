"""
User Input Tool - Allows the AI to explicitly request feedback or approval
"""

from typing import Dict, Any, Optional
from .base import BaseTool, ToolResult


class UserInputTool(BaseTool):
    """
    Allows the AI to explicitly request feedback or approval from the user.
    
    Enhanced with:
    - Proper pause behavior (program waits for user input)
    - Input validation (checks for empty input)
    - Multi-line input support
    - Cancel operation support
    - Optimized TUI rendering
    
    **Validates: Requirements 8.1-8.10**
    """
    
    name = "userInput"
    description = (
        "Ask the user for specific input, feedback, or approval. "
        "Use this when you need a clear 'yes' or detailed feedback before proceeding. "
        "The reason parameter helps the system track the purpose of the request. "
        "Supports multi-line input and cancel operations."
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
            },
            "multiline": {
                "type": "boolean",
                "description": "Whether to accept multi-line input (default: false).",
                "default": False
            },
            "default_value": {
                "type": "string",
                "description": "Optional default value if user provides empty input."
            },
            "allow_cancel": {
                "type": "boolean",
                "description": "Whether to allow user to cancel the operation (default: true).",
                "default": True
            }
        },
        "required": ["question", "reason"]
    }
    
    def execute(
        self,
        question: str,
        reason: str,
        multiline: bool = False,
        default_value: Optional[str] = None,
        allow_cancel: bool = True
    ) -> ToolResult:
        """
        Execute the user input tool with proper pause behavior.
        
        Args:
            question: The question to ask the user
            reason: The reason for the request
            multiline: Whether to accept multi-line input
            default_value: Optional default value for empty input
            allow_cancel: Whether to allow cancellation
        
        Returns:
            ToolResult with user's input or cancellation status
        
        **Validates: Requirements 8.1-8.10**
        """
        from rich.console import Console
        from rich.panel import Panel
        from rich import box
        from ..cli.theme import THEME, DECO
        
        # Use force_terminal=True to ensure proper input handling on Windows
        # Try to get console from context if available (for shared instance)
        console = self.context.get('console') if self.context else None
        if not console:
            console = Console(width=None, force_terminal=True)
        
        # Stop status line live display if it's running (to prevent input being overwritten)
        get_status_live = self.context.get('get_status_live') if self.context else None
        status_live = get_status_live() if get_status_live else None
        if status_live:
            status_live.stop()
        
        # Display the question in a prominent panel (Requirement 8.2)
        question_panel = Panel(
            f"[bold {THEME.BLUE_SOFT}]{question}[/bold {THEME.BLUE_SOFT}]",
            title=f"[{THEME.PINK_SOFT}]{DECO.RHOMBUS} User Input Required[/{THEME.PINK_SOFT}]",
            subtitle=f"[{THEME.TEXT_DIM}]Reason: {reason}[/{THEME.TEXT_DIM}]",
            border_style=THEME.BORDER_PRIMARY,
            box=box.ROUNDED,
            padding=(0, 1)
        )
        console.print(question_panel)
        
        # Show input instructions
        if multiline:
            console.print(
                f"[{THEME.TEXT_DIM}]{DECO.DOT_MEDIUM} Multi-line input mode. "
                f"Press Ctrl+D (Unix) or Ctrl+Z (Windows) when done.[/{THEME.TEXT_DIM}]"
            )
        if allow_cancel:
            console.print(
                f"[{THEME.TEXT_DIM}]{DECO.DOT_MEDIUM} Press Ctrl+C to cancel.[/{THEME.TEXT_DIM}]"
            )
        if default_value:
            console.print(
                f"[{THEME.TEXT_DIM}]{DECO.DOT_MEDIUM} Default: {default_value}[/{THEME.TEXT_DIM}]"
            )
        
        console.print()  # Add spacing
        
        try:
            if multiline:
                # Multi-line input mode (Requirement 8.6)
                user_input = self._get_multiline_input(console)
            else:
                # Single-line input mode with proper pause (Requirements 8.1, 8.3)
                # Use console.input() directly for reliable input handling on all platforms
                prompt_text = f"[{THEME.PURPLE_SOFT}]{DECO.CHEVRON_RIGHT}[/{THEME.PURPLE_SOFT}] "
                if default_value:
                    prompt_text += f"[{THEME.TEXT_DIM}](default: {default_value})[/{THEME.TEXT_DIM}] "
                prompt_text += f"[bold {THEME.TEXT_PRIMARY}]›[bold {THEME.TEXT_PRIMARY}] "
                
                console.print(prompt_text, end="")
                user_input = console.input("")
                
                # Handle default value for empty input
                if not user_input.strip() and default_value:
                    user_input = default_value
                    console.print(
                        f"[{THEME.TEXT_DIM}]{DECO.DOT_MEDIUM} Using default value: {default_value}[/{THEME.TEXT_DIM}]"
                    )
            
            # Input validation (Requirement 8.5)
            if not user_input or user_input.strip() == "":
                # Empty input without default - ask again
                console.print(
                    f"[{THEME.AMBER_GLOW}]! Empty input provided. Please provide a response.[/{THEME.AMBER_GLOW}]"
                )
                # Restart status live before recursive call
                if status_live:
                    status_live.start()
                return self.execute(question, reason, multiline, default_value, allow_cancel)
            
            # Success message (Requirement 8.4)
            console.print(
                f"[{THEME.MINT_SOFT}]{DECO.CHECK_FANCY} Input received[/{THEME.MINT_SOFT}]"
            )
            console.print()  # Add spacing for clean rendering (Requirement 8.9)
            
            # Restart status live after successful input
            if status_live:
                status_live.start()
            
            return ToolResult.ok(
                f"User response: {user_input}",
                data={"user_input": user_input, "reason": reason}
            )
        
        except KeyboardInterrupt:
            # Handle cancellation (Requirements 8.7, 8.8)
            # Restart status live before handling cancellation
            if status_live:
                status_live.start()
            
            if allow_cancel:
                console.print(
                    f"\n[{THEME.CORAL_SOFT}]{DECO.CROSS_FANCY} Input cancelled by user[/{THEME.CORAL_SOFT}]"
                )
                console.print()  # Add spacing
                return ToolResult.ok(
                    "User cancelled the input operation.",
                    data={"cancelled": True, "reason": reason}
                )
            else:
                console.print(
                    f"\n[{THEME.AMBER_GLOW}]! Cancellation not allowed. Please provide input.[/{THEME.AMBER_GLOW}]"
                )
                # Restart status live before recursive call
                if status_live:
                    status_live.start()
                return self.execute(question, reason, multiline, default_value, allow_cancel)
        
        except Exception as e:
            # Handle unexpected errors gracefully (Requirement 8.8)
            # Restart status live before returning
            if status_live:
                status_live.start()
            
            console.print(
                f"[{THEME.CORAL_VIBRANT}]{DECO.CROSS_FANCY} Error getting input: {str(e)}[/{THEME.CORAL_VIBRANT}]"
            )
            return ToolResult.fail(
                f"Failed to get user input: {str(e)}"
            )
    
    def _get_multiline_input(self, console) -> str:
        """
        Get multi-line input from user.
        
        **Validates: Requirement 8.6**
        """
        import sys
        from ..cli.theme import THEME, DECO
        
        console.print(
            f"[{THEME.PURPLE_SOFT}]{DECO.CHEVRON_RIGHT} Enter your response (multi-line):[/{THEME.PURPLE_SOFT}]"
        )
        
        lines = []
        try:
            while True:
                # Use console.input() for proper terminal handling on Windows
                # This ensures the input is properly captured in all terminal environments
                try:
                    if sys.platform == 'win32':
                        # On Windows, use sys.stdout.flush() to ensure prompt is displayed
                        sys.stdout.flush()
                    line = console.input("")
                    lines.append(line)
                except EOFError:
                    # Ctrl+D (Unix) or Ctrl+Z (Windows) pressed
                    break
        except KeyboardInterrupt:
            # Allow Ctrl+C to cancel multi-line input
            pass
        
        return "\n".join(lines)

    def get_execution_message(self, **kwargs) -> str:
        """
        Overridden to display the actual question in the execution log.
        """
        question = kwargs.get('question', '...')
        reason = kwargs.get('reason', 'user input')
        multiline = kwargs.get('multiline', False)
        mode = "multi-line" if multiline else "single-line"
        return f"Asking user ({reason}, {mode}): \"{question}\""
