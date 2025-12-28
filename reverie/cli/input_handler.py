r"""
Input Handler - Advanced input with multiline support and command completion

Features:
- Multiline input (use \ at end of line or triple quotes)
- Command auto-completion
- Command history
- Syntax highlighting for commands
- Dreamscape themed prompts
"""

from typing import List, Optional, Tuple, Callable
import sys

from rich.console import Console
from rich.text import Text
from rich.prompt import Prompt

from .theme import THEME, DECO


# Available commands with descriptions
COMMANDS = {
    '/help': 'Show available commands',
    '/model': 'List and select models',
    '/status': 'Show current status',
    '/search': 'Search the web (usage: /search <query>)',
    '/sessions': 'Manage sessions',
    '/history': 'View conversation history',
    '/clear': 'Clear the screen',
    '/index': 'Re-index the codebase',
    '/setting': 'Interactive settings menu',
    '/rules': 'Manage custom rules',
    '/tools': 'List available tools',
    '/exit': 'Exit Reverie',
    '/quit': 'Exit Reverie',
}


class InputHandler:
    """
    Advanced input handler with multiline support and command completion.
    Features Dreamscape themed prompts and visual feedback.
    """
    
    def __init__(self, console: Console):
        self.console = console
        self.history: List[str] = []
        self.history_index = 0
        self.theme = THEME
        self.deco = DECO
    
    def _render_prompt(self, prompt_text: str, is_continuation: bool = False) -> None:
        """Render the dreamy themed prompt"""
        if is_continuation:
            # Continuation prompt for multiline input
            self.console.print(
                f"[{self.theme.PURPLE_MEDIUM}]   {self.deco.LINE_VERTICAL}[/{self.theme.PURPLE_MEDIUM}] ",
                end=""
            )
        else:
            # Main prompt with sparkle effect
            prompt_parts = Text()
            
            # Decorative sparkle
            prompt_parts.append(f"{self.deco.SPARKLE_FILLED} ", style=self.theme.PINK_SOFT)
            
            # Main prompt text
            prompt_parts.append(prompt_text.rstrip("> "), style=f"bold {self.theme.PURPLE_SOFT}")
            
            # Chevron separator
            prompt_parts.append(f" {self.deco.CHEVRON_RIGHT} ", style=self.theme.BLUE_SOFT)
            
            self.console.print(prompt_parts, end="")
    
    def get_input(self, prompt_text: str = "Reverie> ") -> Optional[str]:
        """
        Get input from user with multiline support.
        
        Multiline modes:
        - End line with \ to continue on next line
        - Use triple quotes for block input
        
        Returns None if user wants to exit (Ctrl+C twice)
        """
        lines = []
        in_multiline = False
        multiline_quote = None
        
        while True:
            try:
                # Show appropriate prompt
                if in_multiline:
                    self._render_prompt(prompt_text, is_continuation=True)
                else:
                    self._render_prompt(prompt_text, is_continuation=False)
                
                line = input("")
                
                # Check for triple quotes to start/end multiline
                if '"""' in line or "'''" in line:
                    quote = '"""' if '"""' in line else "'''"
                    if not in_multiline:
                        # Starting multiline
                        in_multiline = True
                        multiline_quote = quote
                        # Remove the opening quote
                        line = line.replace(quote, '', 1)
                        if quote in line:
                            # Both open and close on same line
                            line = line.replace(quote, '', 1)
                            in_multiline = False
                            multiline_quote = None
                    else:
                        # Ending multiline
                        line = line.replace(quote, '', 1)
                        in_multiline = False
                        multiline_quote = None
                    lines.append(line)
                    if not in_multiline:
                        break
                    continue
                
                # Check for line continuation
                if line.endswith('\\'):
                    lines.append(line[:-1])  # Remove the backslash
                    in_multiline = True
                    continue
                
                lines.append(line)
                
                if not in_multiline:
                    break
                    
            except KeyboardInterrupt:
                if in_multiline:
                    # Cancel multiline input
                    self.console.print(
                        f"\n[{self.theme.TEXT_DIM}]{self.deco.CROSS} Multiline input cancelled[/{self.theme.TEXT_DIM}]"
                    )
                    return ""
                else:
                    self.console.print()
                    return None  # Signal interrupt
            except EOFError:
                return None
        
        result = '\n'.join(lines)
        
        # Add to history if not empty
        if result.strip():
            self.history.append(result)
            self.history_index = len(self.history)
        
        return result
    
    def get_command_completions(self, partial: str) -> List[Tuple[str, str]]:
        """
        Get command completions for partial input.
        
        Returns list of (command, description) tuples.
        """
        if not partial.startswith('/'):
            return []
        
        partial_lower = partial.lower()
        completions = []
        
        for cmd, desc in COMMANDS.items():
            if cmd.lower().startswith(partial_lower):
                completions.append((cmd, desc))
        
        return completions
    
    def show_completions(self, completions: List[Tuple[str, str]]) -> Optional[str]:
        """
        Display completions with dreamy styling and let user select one.
        
        Returns selected command or None.
        """
        if not completions:
            return None
        
        self.console.print(
            f"\n[{self.theme.PURPLE_SOFT}]{self.deco.SPARKLE} Available commands:[/{self.theme.PURPLE_SOFT}]"
        )
        
        for i, (cmd, desc) in enumerate(completions, 1):
            # Gradient-like color based on position
            colors = [self.theme.PINK_SOFT, self.theme.PURPLE_SOFT, self.theme.BLUE_SOFT]
            color = colors[i % len(colors)]
            
            self.console.print(
                f"  [{color}]{self.deco.CHEVRON_RIGHT}[/{color}] "
                f"[bold {self.theme.BLUE_SOFT}]{cmd}[/bold {self.theme.BLUE_SOFT}]  "
                f"[{self.theme.TEXT_DIM}]{desc}[/{self.theme.TEXT_DIM}]"
            )
        
        self.console.print()
        return None  # User needs to type the full command
    
    def interactive_input(self, prompt_text: str = "Reverie> ") -> Optional[str]:
        """
        Get input with interactive command completion.
        
        When user types / and pauses, show available commands.
        """
        result = self.get_input(prompt_text)
        
        if result is None:
            return None
        
        # Check if partial command - offer completions
        stripped = result.strip()
        if stripped.startswith('/') and ' ' not in stripped:
            completions = self.get_command_completions(stripped)
            if len(completions) == 1:
                # Exact match or single completion
                return completions[0][0]
            elif len(completions) > 1 and stripped != '/' and len(stripped) > 1:
                # Multiple matches - show them
                self.show_completions(completions)
                # Return original so user can refine
                return result
        
        return result


def create_prompt_text() -> str:
    """Create the interactive prompt text"""
    return "Reverie> "
