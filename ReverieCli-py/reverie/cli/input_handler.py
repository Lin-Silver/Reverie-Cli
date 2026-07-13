r"""
Input Handler - Advanced input with multiline support and command completion

Features:
- Multiline input (use \ at end of line or triple quotes)
- Command auto-completion
- Command history
- Syntax highlighting for commands
- Dreamscape themed prompts
"""

from typing import Dict, List, Optional, Tuple, Callable, Any
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
from ..diagnostics import report_suppressed_exception


class InputHandler:
    """
    Advanced input handler with multiline support and command completion.
    Features Dreamscape themed prompts and visual feedback.
    """
    
    def __init__(
        self,
        console: Console,
        attachment_selector: Optional[Callable[[str], Optional[str]]] = None,
        command_provider: Optional[Callable[[], Dict[str, str]]] = None,
    ):
        self.console = console
        self.history: List[str] = []
        self.history_index = 0
        self.theme = THEME
        self.deco = DECO
        self.attachment_selector = attachment_selector
        self.command_provider = command_provider

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

    @staticmethod
    def _move_word_left(buffer: str, cursor: int) -> int:
        cursor = max(0, min(cursor, len(buffer)))
        while cursor > 0 and buffer[cursor - 1].isspace():
            cursor -= 1
        while cursor > 0 and not buffer[cursor - 1].isspace():
            cursor -= 1
        return cursor

    @staticmethod
    def _move_word_right(buffer: str, cursor: int) -> int:
        cursor = max(0, min(cursor, len(buffer)))
        while cursor < len(buffer) and not buffer[cursor].isspace():
            cursor += 1
        while cursor < len(buffer) and buffer[cursor].isspace():
            cursor += 1
        return cursor

    @classmethod
    def _delete_word_backward(cls, buffer: str, cursor: int) -> tuple[str, int]:
        start = cls._move_word_left(buffer, cursor)
        return f"{buffer[:start]}{buffer[cursor:]}", start

    def _completion_candidates(self, buffer: str) -> List[Tuple[str, str]]:
        text = str(buffer or "")
        if "\n" in text or not text.startswith("/"):
            return []
        return self.get_command_completions(text.rstrip())

    def _inline_completion_text(self, buffer: str, selected: int = 0) -> str:
        completions = self._completion_candidates(buffer)
        if not completions:
            return ""
        selected = selected % len(completions)
        window_size = 6
        start = max(0, min(selected - window_size // 2, max(0, len(completions) - window_size)))
        visible = completions[start:start + window_size]
        labels = []
        for index, (command, description) in enumerate(visible, start=start):
            marker = ">" if index == selected else " "
            labels.append(f"{marker} {command:<24} {description[:70]}")
        labels.append(f"  {selected + 1}/{len(completions)} · Tab complete · Up/Down scroll")
        return "\n".join(labels)

    def _line_visual_rows(self, prompt_width: int, line: str) -> int:
        terminal_width = max(self._console_width(), 1)
        cells = prompt_width + self._display_width(line)
        return max(1, (cells + terminal_width - 1) // terminal_width)

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

        text_rows = 0
        cursor_row = 0
        cursor_col = 0
        for index, line in enumerate(lines):
            prompt_width = self._display_width(
                self._plain_prompt_text(prompt_text, is_continuation=index > 0)
            )
            if index < cursor_line:
                text_rows += self._line_visual_rows(prompt_width, line)
                continue
            if index == cursor_line:
                cursor_cells = prompt_width + self._display_width(cursor_line_prefix)
                cursor_row = text_rows + (cursor_cells // terminal_width)
                cursor_col = cursor_cells % terminal_width
            text_rows += self._line_visual_rows(prompt_width, line)

        text_rows = max(text_rows, 1)
        needs_trailing_cursor_row = cursor_row >= text_rows
        return {
            "text_rows": text_rows,
            "total_rows": max(text_rows, cursor_row + 1),
            "cursor_row": max(cursor_row, 0),
            "cursor_col": max(cursor_col, 0),
            "needs_trailing_cursor_row": needs_trailing_cursor_row,
        }

    def _update_cursor_position(self, render_state: dict, metrics: dict) -> None:
        last_row = metrics["total_rows"] - 1
        row_delta = last_row - metrics["cursor_row"]
        if row_delta > 0:
            self._write_terminal(f"\033[{row_delta}A")
        elif row_delta < 0:
            self._write_terminal(f"\033[{-row_delta}B")
        self._write_terminal("\r")
        if metrics["cursor_col"] > 0:
            self._write_terminal(f"\033[{metrics['cursor_col']}C")

    def _redraw_windows_input(
        self,
        prompt_text: str,
        buffer: str,
        cursor: int,
        render_state: dict,
        completion_index: int = 0,
    ) -> None:
        self._clear_rendered_windows_input(render_state)

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
        if metrics.get("needs_trailing_cursor_row"):
            self._write_terminal("\n")
        completion_text = self._inline_completion_text(buffer, completion_index)
        if completion_text:
            self._write_terminal(f"\n\033[2m{completion_text}\033[0m")
            metrics["total_rows"] += sum(self._line_visual_rows(0, line) for line in completion_text.splitlines())
        self._update_cursor_position(render_state, metrics)

        render_state.update(metrics)
        render_state["terminal_width"] = self._console_width()
        render_state["rendered_rows"] = metrics["total_rows"]
        render_state["rendered"] = True

    def _clear_rendered_windows_input(self, render_state: dict) -> None:
        if not render_state.get("rendered"):
            return

        previous_cursor_row = int(render_state.get("cursor_row", 0) or 0)
        if previous_cursor_row > 0:
            self._write_terminal(f"\033[{previous_cursor_row}A")

        previous_rows = max(
            1,
            int(render_state.get("rendered_rows", 0) or 0),
            int(render_state.get("total_rows", 0) or 0),
            previous_cursor_row + 1,
        )
        for row in range(previous_rows):
            self._write_terminal("\r\033[2K")
            if row < previous_rows - 1:
                self._write_terminal("\033[1B")
        if previous_rows > 1:
            self._write_terminal(f"\033[{previous_rows - 1}A")
        self._write_terminal("\r")
        render_state["rendered"] = False
    
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

    def _any_buffered_input(self, msvcrt_module: Any) -> bool:
        try:
            return bool(msvcrt_module.kbhit())
        except OSError:
            return False

    def _collect_buffered_printable_input(
        self,
        msvcrt_module: Any,
        first_key: str,
        pending_keys: List[str],
    ) -> str:
        text = [first_key]
        while self._any_buffered_input(msvcrt_module):
            try:
                key = msvcrt_module.getwch()
            except OSError:
                break
            if key.isprintable():
                text.append(key)
                continue
            pending_keys.append(key)
            break
        return "".join(text)

    def _read_buffered_input(self) -> str:
        rest = []
        while True:
            try:
                fragment = input("")
            except (EOFError, KeyboardInterrupt):
                break
            rest.append(fragment)
        return "\n".join(rest)

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
        pending_keys: List[str] = []
        completion_index = 0
        completion_selection_active = False
        history_draft = buffer
        history_search_matches: List[str] = []
        history_search_index = -1
        self.history_index = len(self.history)
        self._redraw_windows_input(prompt_text, buffer, cursor, render_state, completion_index)

        while True:
            try:
                key = pending_keys.pop(0) if pending_keys else msvcrt.getwch()
            except OSError:
                continue
            if int(render_state.get("terminal_width", self._console_width())) != self._console_width():
                self._redraw_windows_input(prompt_text, buffer, cursor, render_state, completion_index)
            if skip_next_lf and key != "\n":
                skip_next_lf = False

            if key in ("\x00", "\xe0"):
                before = (buffer, cursor)
                selection_changed = False
                try:
                    key_code = pending_keys.pop(0) if pending_keys else msvcrt.getwch()
                except OSError:
                    continue
                if key_code == "K":
                    cursor = self._move_cursor_left(buffer, cursor)
                elif key_code == "M":
                    cursor = self._move_cursor_right(buffer, cursor)
                elif key_code == "s":
                    cursor = self._move_word_left(buffer, cursor)
                elif key_code in {"t", "T"}:
                    cursor = self._move_word_right(buffer, cursor)
                elif key_code == "H":
                    completions = self._completion_candidates(buffer)
                    if completions:
                        completion_index = (completion_index - 1) % len(completions)
                        completion_selection_active = True
                        selection_changed = True
                    elif self.history:
                        if self.history_index == len(self.history):
                            history_draft = buffer
                        self.history_index = max(0, self.history_index - 1)
                        buffer = self.history[self.history_index]
                        cursor = len(buffer)
                elif key_code == "P":
                    completions = self._completion_candidates(buffer)
                    if completions:
                        completion_index = (completion_index + 1) % len(completions)
                        completion_selection_active = True
                        selection_changed = True
                    elif self.history_index < len(self.history):
                        self.history_index += 1
                        buffer = history_draft if self.history_index == len(self.history) else self.history[self.history_index]
                        cursor = len(buffer)
                elif key_code == "G":
                    cursor = buffer.rfind("\n", 0, cursor) + 1
                elif key_code == "O":
                    next_newline = buffer.find("\n", cursor)
                    cursor = len(buffer) if next_newline < 0 else next_newline
                elif key_code == "S":
                    buffer, cursor = self._delete_forward(buffer, cursor)
                if selection_changed or (buffer, cursor) != before:
                    self._redraw_windows_input(prompt_text, buffer, cursor, render_state, completion_index)
                continue
            if key == "\r":
                if self._enter_should_insert_newline():
                    buffer, cursor = self._insert_text(buffer, cursor, "\n")
                    self._redraw_windows_input(prompt_text, buffer, cursor, render_state, completion_index)
                    continue
                if self._has_buffered_keyboard_input(msvcrt):
                    buffer, cursor = self._insert_text(buffer, cursor, "\n")
                    skip_next_lf = True
                    self._redraw_windows_input(prompt_text, buffer, cursor, render_state, completion_index)
                    continue
                completions = self._completion_candidates(buffer)
                if completion_selection_active and completions:
                    buffer = completions[completion_index % len(completions)][0]
                    cursor = len(buffer)
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
                self._redraw_windows_input(prompt_text, buffer, cursor, render_state, completion_index)
                continue
            if key == "\x03":
                self._clear_rendered_windows_input(render_state)
                self._write_terminal("\n")
                return None
            if key == "\x08":
                before = (buffer, cursor)
                buffer, cursor = self._delete_backward(buffer, cursor)
                if (buffer, cursor) != before:
                    completion_index = 0
                    self._redraw_windows_input(prompt_text, buffer, cursor, render_state, completion_index)
                continue
            if key == "\t":
                completions = self._completion_candidates(buffer)
                if completions:
                    selected = completions[completion_index % len(completions)][0]
                    buffer, cursor = selected, len(selected)
                    completion_selection_active = False
                    self._redraw_windows_input(prompt_text, buffer, cursor, render_state, completion_index)
                continue
            if key == "\x15":  # Ctrl+U: delete to line start
                line_start = buffer.rfind("\n", 0, cursor) + 1
                buffer, cursor = f"{buffer[:line_start]}{buffer[cursor:]}", line_start
                self._redraw_windows_input(prompt_text, buffer, cursor, render_state, completion_index)
                continue
            if key == "\x0b":  # Ctrl+K: delete to line end
                line_end = buffer.find("\n", cursor)
                line_end = len(buffer) if line_end < 0 else line_end
                buffer = f"{buffer[:cursor]}{buffer[line_end:]}"
                self._redraw_windows_input(prompt_text, buffer, cursor, render_state, completion_index)
                continue
            if key == "\x17":  # Ctrl+W: delete previous word
                buffer, cursor = self._delete_word_backward(buffer, cursor)
                self._redraw_windows_input(prompt_text, buffer, cursor, render_state, completion_index)
                continue
            if key == "\x12":  # Ctrl+R: cycle reverse matches for the current draft
                if not history_search_matches:
                    needle = buffer.lower()
                    history_search_matches = [item for item in reversed(self.history) if needle in item.lower()]
                if history_search_matches:
                    history_search_index = (history_search_index + 1) % len(history_search_matches)
                    buffer = history_search_matches[history_search_index]
                    cursor = len(buffer)
                    self._redraw_windows_input(prompt_text, buffer, cursor, render_state, completion_index)
                continue
            if key == "@" and self._should_open_attachment_selector(buffer[:cursor]):
                self._write_terminal("\n")
                insertion = self._attachment_insertion_text()
                buffer, cursor = self._insert_text(buffer, cursor, insertion)
                render_state = {"rendered": False, "cursor_row": 0, "total_rows": 1}
                self._redraw_windows_input(prompt_text, buffer, cursor, render_state, completion_index)
                continue
            if key.isprintable():
                text = self._collect_buffered_printable_input(msvcrt, key, pending_keys)
                buffer, cursor = self._insert_text(buffer, cursor, text)
                completion_index = 0
                completion_selection_active = False
                history_search_matches = []
                history_search_index = -1
                self._redraw_windows_input(prompt_text, buffer, cursor, render_state, completion_index)

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

        try:
            return self._get_cross_platform_input(prompt_text, str(initial_text or ""))
        except ImportError:
            pass

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

    def _get_cross_platform_input(self, prompt_text: str, initial_text: str = "") -> Optional[str]:
        """Use prompt_toolkit for resize-aware editing on Linux and macOS."""
        from prompt_toolkit import PromptSession
        from prompt_toolkit.completion import Completer, Completion
        from prompt_toolkit.document import Document
        from prompt_toolkit.history import InMemoryHistory
        from prompt_toolkit.key_binding import KeyBindings

        owner = self

        class SlashCompleter(Completer):
            def get_completions(self, document, complete_event):
                text = document.text_before_cursor
                if not text.startswith("/") or "\n" in text:
                    return
                for command, description in owner.get_command_completions(text.rstrip()):
                    yield Completion(command, start_position=-len(text), display_meta=description)

        history = InMemoryHistory()
        for item in self.history:
            history.append_string(item)
        bindings = KeyBindings()

        @bindings.add("escape", "enter")
        def _submit(event):
            event.current_buffer.validate_and_handle()

        @bindings.add("c-j")
        def _newline(event):
            event.current_buffer.insert_text("\n")

        @bindings.add("@")
        def _mention(event):
            before = event.current_buffer.document.text_before_cursor
            if owner._should_open_attachment_selector(before):
                insertion = owner._attachment_insertion_text()
                event.current_buffer.insert_text(insertion)
            else:
                event.current_buffer.insert_text("@")

        session = PromptSession(
            history=history,
            completer=SlashCompleter(),
            complete_while_typing=True,
            enable_history_search=True,
            key_bindings=bindings,
            multiline=True,
            bottom_toolbar=lambda: "Esc+Enter send · Ctrl+J newline · Ctrl+R history · @ files",
        )
        try:
            result = session.prompt(
                self._plain_prompt_text(prompt_text),
                default=initial_text,
            )
        except (EOFError, KeyboardInterrupt):
            return None
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
        
        commands = build_command_completion_map()
        if callable(self.command_provider):
            try:
                commands.update(self.command_provider() or {})
            except Exception:
                report_suppressed_exception("load dynamic command completions")
        for cmd, desc in commands.items():
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
