r"""
Input Handler - Advanced input with multiline support and command completion

Features:
- Multiline input (use \ at end of line or triple quotes)
- Command auto-completion
- Command history
- Syntax highlighting for commands
- Dreamscape themed prompts
"""

from typing import List, Optional, Tuple, Callable, Any
import sys
import time
import unicodedata

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
    
    def __init__(
        self,
        console: Console,
        attachment_selector: Optional[Callable[[str], Optional[str]]] = None,
    ):
        self.console = console
        self.history: List[str] = []
        self.history_index = 0
        self.theme = THEME
        self.deco = DECO
        self.attachment_selector = attachment_selector

    def _console_width(self) -> int:
        """Best-effort terminal width."""
        try:
            width = int(getattr(self.console.size, "width", 0) or self.console.width or 0)
        except Exception:
            width = 0
        return max(width, 60)

    def _output_stream(self) -> Any:
        return getattr(self.console, "file", None) or sys.stdout

    def _write_terminal(self, value: str) -> None:
        stream = self._output_stream()
        stream.write(value)
        stream.flush()

    def _plain_prompt_text(self, prompt_text: str, is_continuation: bool = False) -> str:
        if is_continuation:
            return ""
        return (
            f"{self.deco.DIAMOND_FILLED} "
            f"{prompt_text.rstrip('> ')} "
            f"{self.deco.DOT_MEDIUM} "
            f"{self.deco.CHEVRON_RIGHT} "
        )

    @staticmethod
    def _char_cell_width(char: str) -> int:
        if not char or char in "\r\n":
            return 0
        if unicodedata.combining(char):
            return 0
        if unicodedata.category(char) in {"Cc", "Cf"}:
            return 0
        return 2 if unicodedata.east_asian_width(char) in {"F", "W"} else 1

    @classmethod
    def _display_width(cls, text: str) -> int:
        return sum(cls._char_cell_width(char) for char in str(text or ""))

    @staticmethod
    def _insert_text(buffer: str, cursor: int, value: str) -> tuple[str, int]:
        cursor = max(0, min(cursor, len(buffer)))
        updated = f"{buffer[:cursor]}{value}{buffer[cursor:]}"
        return updated, cursor + len(value)

    @staticmethod
    def _delete_backward(buffer: str, cursor: int) -> tuple[str, int]:
        cursor = max(0, min(cursor, len(buffer)))
        if cursor <= 0:
            return buffer, cursor
        return f"{buffer[:cursor - 1]}{buffer[cursor:]}", cursor - 1

    @staticmethod
    def _delete_forward(buffer: str, cursor: int) -> tuple[str, int]:
        cursor = max(0, min(cursor, len(buffer)))
        if cursor >= len(buffer):
            return buffer, cursor
        return f"{buffer[:cursor]}{buffer[cursor + 1:]}", cursor

    @staticmethod
    def _move_cursor_left(buffer: str, cursor: int) -> int:
        return max(0, min(cursor, len(buffer)) - 1)

    @staticmethod
    def _move_cursor_right(buffer: str, cursor: int) -> int:
        return min(len(buffer), max(0, cursor) + 1)

    def _line_visual_rows(self, prompt_width: int, line: str) -> int:
        terminal_width = max(self._console_width(), 1)
        cells = prompt_width + self._display_width(line)
        return max(1, cells // terminal_width + 1)

    def _input_visual_metrics(
        self,
        prompt_text: str,
        buffer: str,
        cursor: int,
    ) -> dict:
        terminal_width = max(self._console_width(), 1)
        buffer = str(buffer or "")
        cursor = max(0, min(cursor, len(buffer)))
        lines = buffer.split("\n")
        prefix = buffer[:cursor]
        cursor_line = prefix.count("\n")
        cursor_line_start = prefix.rfind("\n") + 1
        cursor_line_prefix = prefix[cursor_line_start:]

        total_rows = 0
        cursor_row = 0
        cursor_col = 0
        for index, line in enumerate(lines):
            prompt_width = self._display_width(
                self._plain_prompt_text(prompt_text, is_continuation=index > 0)
            )
            if index < cursor_line:
                total_rows += self._line_visual_rows(prompt_width, line)
                continue
            if index == cursor_line:
                cursor_cells = prompt_width + self._display_width(cursor_line_prefix)
                cursor_row = total_rows + (cursor_cells // terminal_width)
                cursor_col = cursor_cells % terminal_width
            total_rows += self._line_visual_rows(prompt_width, line)

        return {
            "total_rows": max(total_rows, 1),
            "cursor_row": max(cursor_row, 0),
            "cursor_col": max(cursor_col, 0),
        }

    def _redraw_windows_input(
        self,
        prompt_text: str,
        buffer: str,
        cursor: int,
        render_state: dict,
    ) -> None:
        if render_state.get("rendered"):
            previous_cursor_row = int(render_state.get("cursor_row", 0) or 0)
            if previous_cursor_row > 0:
                self._write_terminal(f"\033[{previous_cursor_row}A")
            self._write_terminal("\r\033[J")

        lines = str(buffer or "").split("\n")
        for index, line in enumerate(lines):
            if index:
                self._write_terminal("\n")
            if index > 0:
                self._write_terminal(line)
            else:
                self._render_prompt(prompt_text, is_continuation=False)
                if line:
                    self._write_terminal(line)

        metrics = self._input_visual_metrics(prompt_text, buffer, cursor)
        rows_below_cursor = metrics["total_rows"] - metrics["cursor_row"] - 1
        if rows_below_cursor > 0:
            self._write_terminal(f"\033[{rows_below_cursor}A")
        self._write_terminal("\r")
        if metrics["cursor_col"] > 0:
            self._write_terminal(f"\033[{metrics['cursor_col']}C")

        render_state.update(metrics)
        render_state["rendered"] = True
    
    def _render_prompt(self, prompt_text: str, is_continuation: bool = False) -> None:
        """Render the dreamy themed prompt"""
        if is_continuation:
            return
        else:
            prompt_parts = Text()
            prompt_parts.append(f"{self.deco.DIAMOND_FILLED} ", style=self.theme.BLUE_SOFT)
            prompt_parts.append(prompt_text.rstrip("> "), style=f"bold {self.theme.PURPLE_SOFT}")
            prompt_parts.append(f" {self.deco.DOT_MEDIUM} ", style=self.theme.TEXT_DIM)
            prompt_parts.append(f"{self.deco.CHEVRON_RIGHT} ", style=self.theme.BLUE_SOFT)
            self.console.print(prompt_parts, end="")

    def _should_open_attachment_selector(self, text_before_cursor: str) -> bool:
        """Open the image picker only when `@` starts a mention token."""
        if self.attachment_selector is None:
            return False
        if not text_before_cursor:
            return True
        return bool(text_before_cursor[-1].isspace())

    def _attachment_insertion_text(self) -> str:
        """Run the attachment selector and return the text to insert."""
        selector = self.attachment_selector
        if selector is None:
            return "@"

        mention = selector("")
        if mention:
            insertion = str(mention).strip()
            if insertion:
                return f"{insertion} "
        return "@"

    def _has_buffered_keyboard_input(self, msvcrt_module: Any) -> bool:
        time.sleep(0.02)
        try:
            return bool(msvcrt_module.kbhit())
        except OSError:
            return False

    @staticmethod
    def _windows_virtual_key_pressed(*virtual_keys: int) -> bool:
        if sys.platform != "win32":
            return False
        try:
            import ctypes

            user32 = ctypes.windll.user32
            return any(bool(user32.GetAsyncKeyState(key) & 0x8000) for key in virtual_keys)
        except Exception:
            return False

    def _enter_should_insert_newline(self) -> bool:
        # VK_SHIFT = 0x10, VK_CONTROL = 0x11.
        return self._windows_virtual_key_pressed(0x10, 0x11)

    def _get_seeded_single_line_input(
        self,
        prompt_text: str,
        initial_text: str,
        *,
        record_history: bool = True,
    ) -> Optional[str]:
        """Capture editable Windows input while preserving an existing draft buffer."""
        try:
            import msvcrt
        except ImportError:
            self._render_prompt(prompt_text, is_continuation=False)
            line = Prompt.ask("", default=initial_text, show_default=False)
            return line

        buffer = str(initial_text or "")
        cursor = len(buffer)
        render_state = {"rendered": False, "cursor_row": 0, "total_rows": 1}
        skip_next_lf = False
        self._redraw_windows_input(prompt_text, buffer, cursor, render_state)

        while True:
            try:
                key = msvcrt.getwch()
            except OSError:
                continue
            if skip_next_lf and key != "\n":
                skip_next_lf = False

            if key in ("\x00", "\xe0"):
                try:
                    key_code = msvcrt.getwch()
                except OSError:
                    continue
                if key_code == "K":  # Left
                    cursor = self._move_cursor_left(buffer, cursor)
                elif key_code == "M":  # Right
                    cursor = self._move_cursor_right(buffer, cursor)
                elif key_code == "G":  # Home
                    cursor = buffer.rfind("\n", 0, cursor) + 1
                elif key_code == "O":  # End
                    next_newline = buffer.find("\n", cursor)
                    cursor = len(buffer) if next_newline < 0 else next_newline
                elif key_code == "S":  # Delete
                    buffer, cursor = self._delete_forward(buffer, cursor)
                self._redraw_windows_input(prompt_text, buffer, cursor, render_state)
                continue
            if key == "\r":
                if self._enter_should_insert_newline():
                    buffer, cursor = self._insert_text(buffer, cursor, "\n")
                    self._redraw_windows_input(prompt_text, buffer, cursor, render_state)
                    continue
                if self._has_buffered_keyboard_input(msvcrt):
                    buffer, cursor = self._insert_text(buffer, cursor, "\n")
                    skip_next_lf = True
                    self._redraw_windows_input(prompt_text, buffer, cursor, render_state)
                    continue
                self._write_terminal("\n")
                if record_history and buffer.strip():
                    self.history.append(buffer)
                    self.history_index = len(self.history)
                return buffer
            if key == "\n":
                if skip_next_lf:
                    skip_next_lf = False
                    continue
                buffer, cursor = self._insert_text(buffer, cursor, "\n")
                self._redraw_windows_input(prompt_text, buffer, cursor, render_state)
                continue
            if key == "\x03":
                self._write_terminal("\n")
                return None
            if key == "\x08":
                buffer, cursor = self._delete_backward(buffer, cursor)
                self._redraw_windows_input(prompt_text, buffer, cursor, render_state)
                continue
            if key == "@" and self._should_open_attachment_selector(buffer[:cursor]):
                self._write_terminal("\n")
                insertion = self._attachment_insertion_text()
                buffer, cursor = self._insert_text(buffer, cursor, insertion)
                render_state = {"rendered": False, "cursor_row": 0, "total_rows": 1}
                self._redraw_windows_input(prompt_text, buffer, cursor, render_state)
                continue
            if key.isprintable():
                buffer, cursor = self._insert_text(buffer, cursor, key)
                self._redraw_windows_input(prompt_text, buffer, cursor, render_state)

    def get_input(self, prompt_text: str = "Reverie> ", initial_text: str = "") -> Optional[str]:
        """
        Get input from user with multiline support.
        
        Multiline modes:
        - Windows prompt editor: Shift+Enter/Ctrl+Enter or Ctrl+J inserts a newline; pasted newlines are preserved
        - Paste detection: Rapidly entered lines are preserved as one message
        - End line with \\ to continue on next line
        - Use triple quotes for block input
        
        Returns None if user wants to exit (Ctrl+C twice)
        """
        try:
            import msvcrt
        except ImportError:
            msvcrt = None

        if msvcrt is not None:
            return self._get_seeded_single_line_input(prompt_text, str(initial_text or ""))

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
                
                # Paste detection: Check if more input is immediately available in buffer.
                # Preserve pasted newlines so long specs, logs, and code blocks remain intact.
                if not in_multiline and msvcrt is not None and msvcrt.kbhit():
                    # Small delay to let the buffer fill if it's a real paste
                    import time
                    time.sleep(0.05)
                    
                    # Collect all buffered lines as a single multi-line paste
                    pasted_lines = [line]
                    while msvcrt.kbhit():
                        try:
                            pasted_lines.append(input(""))
                        except (EOFError, KeyboardInterrupt):
                            break
                    
                    combined_input = "\n".join(pasted_lines)
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
