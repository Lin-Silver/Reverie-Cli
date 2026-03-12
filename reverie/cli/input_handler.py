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
from rich.panel import Panel
from rich.table import Table
from rich.text import Text
from rich.prompt import Prompt
from rich import box

from .help_catalog import build_command_completion_map
from .theme import THEME, DECO


# Available commands with descriptions
COMMANDS = build_command_completion_map()


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

    def _console_width(self) -> int:
        """Best-effort terminal width."""
        try:
            width = int(getattr(self.console.size, "width", 0) or self.console.width or 0)
        except Exception:
            width = 0
        return max(width, 60)
    
    def _render_prompt(self, prompt_text: str, is_continuation: bool = False) -> None:
        """Render the dreamy themed prompt"""
        if is_continuation:
            self.console.print(
                f"[{self.theme.PURPLE_MEDIUM}]   {self.deco.LINE_VERTICAL}[/{self.theme.PURPLE_MEDIUM}] ",
                end=""
            )
        else:
            prompt_parts = Text()
            
            prompt_parts.append(f"{self.deco.SPARKLE_FILLED} ", style=self.theme.PINK_SOFT)
            
            prompt_parts.append(prompt_text.rstrip("> "), style=f"bold {self.theme.PURPLE_SOFT}")
            
            prompt_parts.append(f" {self.deco.CHEVRON_RIGHT} ", style=self.theme.BLUE_SOFT)
            
            self.console.print(prompt_parts, end="")

    def _get_seeded_single_line_input(self, prompt_text: str, initial_text: str) -> Optional[str]:
        """Capture a single line while preserving an existing draft buffer."""
        try:
            import msvcrt
        except ImportError:
            self._render_prompt(prompt_text, is_continuation=False)
            line = Prompt.ask("", default=initial_text, show_default=False)
            return line

        buffer = str(initial_text or "")
        self._render_prompt(prompt_text, is_continuation=False)
        if buffer:
            self.console.print(buffer, end="")

        while True:
            try:
                key = msvcrt.getwch()
            except OSError:
                continue

            if key in ("\x00", "\xe0"):
                try:
                    msvcrt.getwch()
                except OSError:
                    pass
                continue
            if key in ("\r", "\n"):
                self.console.print()
                if buffer.strip():
                    self.history.append(buffer)
                    self.history_index = len(self.history)
                return buffer
            if key == "\x03":
                self.console.print()
                return None
            if key == "\x08":
                if buffer:
                    buffer = buffer[:-1]
                    sys.stdout.write("\b \b")
                    sys.stdout.flush()
                continue
            if key.isprintable():
                buffer += key
                sys.stdout.write(key)
                sys.stdout.flush()

    def get_input(self, prompt_text: str = "Reverie> ", initial_text: str = "") -> Optional[str]:
        """
        Get input from user with multiline support.
        
        Multiline modes:
        - Paste detection: Rapidly entered lines are combined into one line
        - End line with \\ to continue on next line
        - Use triple quotes for block input
        
        Returns None if user wants to exit (Ctrl+C twice)
        """
        import msvcrt

        seeded_text = str(initial_text or "")
        if seeded_text:
            return self._get_seeded_single_line_input(prompt_text, seeded_text)
        
        lines = []
        in_multiline = False
        multiline_quote = None
        
        while True:
            try:
                if in_multiline:
                    self._render_prompt(prompt_text, is_continuation=True)
                else:
                    self._render_prompt(prompt_text, is_continuation=False)
                
                line = input("")
                
                # Paste detection: Check if more input is immediately available in buffer
                # This handles "convert to one line input" for pasted content
                # Only trigger if there's significant buffered content (more than just the enter key)
                if not in_multiline and msvcrt.kbhit():
                    # Small delay to let the buffer fill if it's a real paste
                    import time
                    time.sleep(0.05)
                    
                    # Only treat as paste if there's still content after the delay
                    if msvcrt.kbhit():
                        pasted_lines = [line]
                        while msvcrt.kbhit():
                            try:
                                # Read subsequent lines without prompting
                                pasted_lines.append(input(""))
                            except (EOFError, KeyboardInterrupt):
                                break
                        
                        # Combine pasted lines into one single line input
                        # Replace newlines with spaces as requested ("convert to one line")
                        combined_input = " ".join(pasted_lines)
                        
                        # If we detected a paste, we usually return immediately unless it ended with continuation char
                        if combined_input.strip():
                            self.history.append(combined_input)
                            self.history_index = len(self.history)
                            return combined_input
                        return combined_input
                
                if '"""' in line or "'''" in line:
                    quote = '"""' if '"""' in line else "'''"
                    if not in_multiline:
                        in_multiline = True
                        multiline_quote = quote
                        line = line.replace(quote, '', 1)
                        if quote in line:
                            line = line.replace(quote, '', 1)
                            in_multiline = False
                            multiline_quote = None
                    else:
                        line = line.replace(quote, '', 1)
                        in_multiline = False
                        multiline_quote = None
                    lines.append(line)
                    if not in_multiline:
                        break
                    continue
                
                if line.endswith('\\'):
                    lines.append(line[:-1])
                    in_multiline = True
                    continue
                
                lines.append(line)
                
                if not in_multiline:
                    break
                    
            except KeyboardInterrupt:
                if in_multiline:
                    self.console.print(
                        f"\n[{self.theme.TEXT_DIM}]{self.deco.CROSS} Multiline input cancelled[/{self.theme.TEXT_DIM}]"
                    )
                    return ""
                else:
                    self.console.print()
                    return None
            except EOFError:
                return None
        
        result = '\n'.join(lines)
        if not in_multiline and len(lines) <= 1:
            result = result.replace('\n', '')
        
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

        compact = self._console_width() < 96
        table = Table(
            show_header=False,
            box=box.SIMPLE_HEAVY if not compact else box.SIMPLE,
            border_style=self.theme.BORDER_SUBTLE,
            pad_edge=False,
            expand=True,
        )
        table.add_column(style=f"bold {self.theme.BLUE_SOFT}", no_wrap=True)
        if not compact:
            table.add_column(style=self.theme.TEXT_DIM)

        for cmd, desc in completions[:10]:
            if compact:
                table.add_row(cmd)
            else:
                table.add_row(cmd, desc)

        footer = f"[{self.theme.TEXT_DIM}]Keep typing to narrow the list.[/{self.theme.TEXT_DIM}]"
        if len(completions) > 10:
            footer += f"\n[{self.theme.TEXT_DIM}]Showing first 10 of {len(completions)} matches.[/{self.theme.TEXT_DIM}]"

        self.console.print()
        self.console.print(
            Panel(
                table,
                title=f"[bold {self.theme.PURPLE_SOFT}]{self.deco.SPARKLE} Command Matches[/bold {self.theme.PURPLE_SOFT}]",
                subtitle=footer,
                border_style=self.theme.BORDER_PRIMARY,
                box=box.ROUNDED,
                padding=(0, 1),
            )
        )
        self.console.print()
        return None
    
    def interactive_input(self, prompt_text: str = "Reverie> ", initial_text: str = "") -> Optional[str]:
        """
        Get input with interactive command completion.
        
        When user types / and pauses, show available commands.
        """
        result = self.get_input(prompt_text, initial_text=initial_text)
        
        if result is None:
            return None
        
        stripped = result.strip()
        if stripped.startswith('/') and ' ' not in stripped:
            completions = self.get_command_completions(stripped)
            if len(completions) == 1:
                return completions[0][0]
            elif len(completions) > 1 and stripped != '/' and len(stripped) > 1:
                self.show_completions(completions)
                return result
        
        return result


def create_prompt_text() -> str:
    """Create the interactive prompt text"""
    return "Reverie> "
