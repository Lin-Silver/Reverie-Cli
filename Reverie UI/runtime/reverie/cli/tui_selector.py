"""
TUI Selector - Interactive menu selection with keyboard navigation

Provides a modern, commercial-feeling TUI interface for:
- Model selection
- Settings configuration
- Session management
- Checkpoint management
- Any list-based selection

Features:
- Arrow key navigation (up/down)
- Enter to confirm
- Escape to cancel
- Visual highlighting of selected item
- Smooth scrolling
- Search/filter support
"""

from typing import List, Dict, Optional, Callable, Any
from dataclasses import dataclass
from enum import Enum, auto

from rich.console import Console, Group
from rich.table import Table
from rich.panel import Panel
from rich.text import Text
from rich.align import Align
from rich.columns import Columns
from rich import box

from .theme import THEME, DECO


class SelectorAction(Enum):
    """Actions that can be performed in the selector"""
    SELECT = auto()
    CANCEL = auto()
    NAVIGATE_UP = auto()
    NAVIGATE_DOWN = auto()
    SEARCH = auto()
    PAGE_UP = auto()
    PAGE_DOWN = auto()
    HOME = auto()
    END = auto()


@dataclass
class SelectorItem:
    """An item in the selector"""
    id: str
    title: str
    description: str = ""
    metadata: Dict = None
    
    def __post_init__(self):
        if self.metadata is None:
            self.metadata = {}


@dataclass
class SelectorResult:
    """Result of selector interaction"""
    action: SelectorAction
    selected_item: Optional[SelectorItem] = None
    search_query: str = ""


class TUISelector:
    """
    Interactive TUI selector with keyboard navigation.
    
    Provides a modern, commercial-feeling interface for selecting
    items from a list using arrow keys and enter.
    """
    
    def __init__(
        self,
        console: Console,
        title: str,
        items: List[SelectorItem],
        allow_search: bool = True,
        allow_cancel: bool = True,
        show_descriptions: bool = True,
        max_visible: int = 8
    ):
        self.console = console
        self.title = title
        self.items = items
        self.allow_search = allow_search
        self.allow_cancel = allow_cancel
        self.show_descriptions = show_descriptions
        self.max_visible = max_visible
        
        self.theme = THEME
        self.deco = DECO
        
        # State
        self.selected_index = 0
        self.scroll_offset = 0
        self.search_query = ""
        self.is_searching = False
        self.filtered_items = items.copy()
        self._search_index = [self._build_search_blob(item) for item in self.items]
        self._render_cache_key = None
        self._render_cache = None

    def _console_width(self) -> int:
        """Best-effort terminal width."""
        try:
            width = int(getattr(self.console.size, "width", 0) or self.console.width or 0)
        except Exception:
            width = 0
        return max(width, 60)

    def _console_height(self) -> int:
        """Best-effort terminal height."""
        try:
            height = int(getattr(self.console.size, "height", 0) or 0)
        except Exception:
            height = 0
        return max(height, 20)

    def _truncate(self, value: str, max_length: int) -> str:
        """Trim long selector fields for narrow terminals."""
        text = str(value or "").strip()
        if len(text) <= max_length:
            return text
        if max_length <= 3:
            return text[:max_length]
        return f"{text[:max_length - 3]}..."

    def _build_search_blob(self, item: SelectorItem) -> str:
        parts = [item.id, item.title, item.description]
        metadata = item.metadata or {}
        for key, value in metadata.items():
            if isinstance(value, dict):
                parts.extend(str(inner) for inner in value.values() if inner not in (None, ""))
            elif isinstance(value, list):
                parts.extend(str(inner) for inner in value if inner not in (None, ""))
            elif value not in (None, ""):
                parts.append(str(value))
            if key not in ("id", "title", "description"):
                parts.append(str(key))
        return " ".join(part.lower() for part in parts if str(part).strip())

    def _visible_rows(self) -> int:
        reserve = 15 if self._console_width() >= 110 else 18
        return max(6, min(18, self._console_height() - reserve))

    def _selected_item(self) -> Optional[SelectorItem]:
        if not self.filtered_items:
            return None
        if self.selected_index < 0:
            self.selected_index = 0
        if self.selected_index >= len(self.filtered_items):
            self.selected_index = len(self.filtered_items) - 1
        return self.filtered_items[self.selected_index]

    def _selected_detail_lines(self, item: Optional[SelectorItem]) -> List[Text]:
        if item is None:
            return [Text("No item selected.", style=self.theme.TEXT_DIM)]

        lines = [Text(item.title, style=f"bold {self.theme.PURPLE_SOFT}")]
        description = str(item.description or "").strip()
        if description:
            lines.append(Text(description, style=self.theme.TEXT_SECONDARY))

        metadata = item.metadata or {}
        detail_rows: List[tuple[str, str]] = []
        model_info = metadata.get("model")
        if isinstance(model_info, dict):
            model_id = str(model_info.get("id", "") or "").strip()
            if model_id:
                detail_rows.append(("ID", model_id))
            context_length = model_info.get("context_length")
            if context_length not in (None, ""):
                try:
                    detail_rows.append(("Context", f"{int(context_length):,}"))
                except (TypeError, ValueError):
                    detail_rows.append(("Context", str(context_length)))
            visibility = str(model_info.get("visibility", "") or "").strip()
            if visibility:
                detail_rows.append(("Visibility", visibility))
        elif item.id:
            detail_rows.append(("ID", item.id))

        for label, value in detail_rows[:3]:
            line = Text()
            line.append(f"{label}: ", style=self.theme.TEXT_DIM)
            line.append(self._truncate(value, 64), style=self.theme.TEXT_PRIMARY)
            lines.append(line)

        if not detail_rows and not description:
            lines.append(Text("Press Enter to confirm this selection.", style=self.theme.TEXT_DIM))
        return lines

    def _build_detail_panel(self, item: Optional[SelectorItem], *, compact: bool) -> Panel:
        return Panel(
            Group(*self._selected_detail_lines(item)),
            title=f"[bold {self.theme.BLUE_SOFT}]Focused Item[/bold {self.theme.BLUE_SOFT}]",
            border_style=self.theme.BORDER_SUBTLE,
            box=box.ROUNDED,
            padding=(0, 1 if compact else 2),
        )
    
    def run(self) -> SelectorResult:
        """
        Run the selector and return the result.
        
        This method blocks until the user makes a selection or cancels.
        """
        import msvcrt
        import time
        from rich.live import Live
        
        # Initial render
        content = self._build_content()
        use_alt_screen = bool(getattr(self.console, "is_terminal", False))
        
        with Live(
            content,
            console=self.console,
            auto_refresh=False,
            screen=use_alt_screen,
            transient=use_alt_screen,
            vertical_overflow="crop",
        ) as live:
            last_size = (self._console_width(), self._console_height())
            while True:
                # Wait for key press
                if msvcrt.kbhit():
                    key = msvcrt.getch()
                    state_changed = False
                    
                    # Handle special keys
                    if key == b'\x00' or key == b'\xe0':  # Function key
                        key = msvcrt.getch()
                        
                        if key == b'H':  # Up arrow
                            self._navigate_up()
                            state_changed = True
                        elif key == b'P':  # Down arrow
                            self._navigate_down()
                            state_changed = True
                        elif key == b'I':  # Page Up
                            self._page_up()
                            state_changed = True
                        elif key == b'Q':  # Page Down
                            self._page_down()
                            state_changed = True
                        elif key == b'G':  # Home
                            self._go_home()
                            state_changed = True
                        elif key == b'O':  # End
                            self._go_end()
                            state_changed = True
                    
                    elif key == b'\r':  # Enter
                        if self.filtered_items:
                            return SelectorResult(
                                action=SelectorAction.SELECT,
                                selected_item=self.filtered_items[self.selected_index],
                                search_query=self.search_query
                            )
                    
                    elif key == b'\x1b':  # Escape
                        if self.allow_cancel:
                            return SelectorResult(action=SelectorAction.CANCEL)
                        else:
                            # Clear search if searching
                            if self.is_searching:
                                self.is_searching = False
                                self.search_query = ""
                                self.filtered_items = self.items.copy()
                                self.selected_index = 0
                                self.scroll_offset = 0
                                state_changed = True
                    
                    elif key == b'/':  # Slash to start search
                        if self.allow_search and not self.is_searching:
                            self.is_searching = True
                            self.search_query = ""
                            state_changed = True
                    
                    elif self.is_searching:
                        # Handle search input
                        if key == b'\x08':  # Backspace
                            if self.search_query:
                                self.search_query = self.search_query[:-1]
                                self._apply_search()
                                state_changed = True
                            else:
                                self.is_searching = False
                                state_changed = True
                        elif 32 <= key[0] <= 126:  # Printable characters
                            self.search_query += key.decode('ascii')
                            self._apply_search()
                            state_changed = True
                    
                    elif key in (b'k', b'K'):
                        self._navigate_up()
                        state_changed = True
                    elif key in (b'j', b'J'):
                        self._navigate_down()
                        state_changed = True
                    elif key in (b'g',):
                        self._go_home()
                        state_changed = True
                    elif key in (b'G',):
                        self._go_end()
                        state_changed = True
                    
                    current_size = (self._console_width(), self._console_height())
                    if current_size != last_size:
                        last_size = current_size
                        state_changed = True
                    
                    # Update only when state changes so the terminal keeps normal scroll behavior.
                    if state_changed:
                        live.update(self._build_content(), refresh=True)

                current_size = (self._console_width(), self._console_height())
                if current_size != last_size:
                    last_size = current_size
                    live.update(self._build_content(), refresh=True)

                # Small sleep to prevent CPU spinning
                time.sleep(0.025)
    
    def _navigate_up(self) -> None:
        """Navigate up in the list"""
        if not self.filtered_items:
            return
        if self.selected_index > 0:
            self.selected_index -= 1
            if self.selected_index < self.scroll_offset:
                self.scroll_offset = self.selected_index
    
    def _navigate_down(self) -> None:
        """Navigate down in the list"""
        if not self.filtered_items:
            return
        visible_rows = self._visible_rows()
        if self.selected_index < len(self.filtered_items) - 1:
            self.selected_index += 1
            if self.selected_index >= self.scroll_offset + visible_rows:
                self.scroll_offset = self.selected_index - visible_rows + 1
    
    def _page_up(self) -> None:
        """Page up"""
        if not self.filtered_items:
            return
        page_size = max(1, self._visible_rows() - 1)
        self.selected_index = max(0, self.selected_index - page_size)
        self.scroll_offset = max(0, self.scroll_offset - page_size)
    
    def _page_down(self) -> None:
        """Page down"""
        if not self.filtered_items:
            return
        visible_rows = self._visible_rows()
        page_size = max(1, visible_rows - 1)
        self.selected_index = min(
            len(self.filtered_items) - 1,
            self.selected_index + page_size
        )
        self.scroll_offset = min(
            max(0, len(self.filtered_items) - visible_rows),
            self.scroll_offset + page_size
        )
    
    def _go_home(self) -> None:
        """Go to first item"""
        if not self.filtered_items:
            return
        self.selected_index = 0
        self.scroll_offset = 0
    
    def _go_end(self) -> None:
        """Go to last item"""
        if not self.filtered_items:
            return
        self.selected_index = len(self.filtered_items) - 1
        visible_rows = self._visible_rows()
        self.scroll_offset = max(
            0,
            len(self.filtered_items) - visible_rows
        )
    
    def _apply_search(self) -> None:
        """Apply search filter"""
        if not self.search_query:
            self.filtered_items = self.items.copy()
        else:
            query = self.search_query.lower()
            self.filtered_items = [
                item for item, search_blob in zip(self.items, self._search_index)
                if query in search_blob
            ]
        
        self.selected_index = 0
        self.scroll_offset = 0
        self._render_cache_key = None
        self._render_cache = None
    
    def _build_content(self) -> Align:
        """Build the complete content for display."""
        width = self._console_width()
        height = self._console_height()
        compact = width < 96
        wide = width >= 116
        show_description = self.show_descriptions and width >= 92
        self.max_visible = self._visible_rows()
        selected_item = self._selected_item()
        cache_key = (
            width,
            height,
            self.selected_index,
            self.scroll_offset,
            self.search_query,
            self.is_searching,
            len(self.filtered_items),
            self.max_visible,
            selected_item.id if selected_item else "",
        )
        if cache_key == self._render_cache_key and self._render_cache is not None:
            return self._render_cache

        title_grid = Table.grid(expand=True)
        title_grid.add_column(ratio=1)
        title_grid.add_column(justify="right", no_wrap=True)
        title_grid.add_row(
            Text.assemble(
                (f"{self.deco.SPARKLE} ", self.theme.PINK_SOFT),
                (self.title, f"bold {self.theme.PURPLE_SOFT}"),
            ),
            Text(
                f"{len(self.filtered_items)} items" + (" filtered" if self.search_query else ""),
                style=self.theme.TEXT_DIM,
            ),
        )
        if selected_item is not None:
            subtitle = Text()
            subtitle.append("Focused ", style=self.theme.TEXT_DIM)
            subtitle.append(self._truncate(selected_item.title, 72 if wide else 48), style=self.theme.TEXT_PRIMARY)
            title_panel = Panel(
                Group(title_grid, subtitle),
                border_style=self.theme.BORDER_PRIMARY,
                padding=(0, 1),
                box=box.ROUNDED,
            )
        else:
            title_panel = Panel(
                title_grid,
                border_style=self.theme.BORDER_PRIMARY,
                padding=(0, 1),
                box=box.ROUNDED,
            )

        table = Table(
            show_header=False,
            box=box.SIMPLE_HEAVY,
            border_style=self.theme.BORDER_SECONDARY,
            padding=(0, 1),
            show_lines=False,
            expand=True,
        )
        table.add_column("indicator", width=3, no_wrap=True)
        table.add_column("index", width=4, style=self.theme.TEXT_DIM, justify="right", no_wrap=True)
        table.add_column("title", style=self.theme.TEXT_PRIMARY)
        if show_description:
            table.add_column("description", style=self.theme.TEXT_SECONDARY)

        end_index = min(self.scroll_offset + self.max_visible, len(self.filtered_items))
        visible_items = self.filtered_items[self.scroll_offset:end_index]

        for i, item in enumerate(visible_items):
            actual_index = self.scroll_offset + i
            is_selected = actual_index == self.selected_index
            indicator = Text(f"{self.deco.CHEVRON_RIGHT}", style=f"bold {self.theme.PINK_SOFT}") if is_selected else Text("  ")
            title_style = f"bold {self.theme.BLUE_SOFT} on {self.theme.PURPLE_DEEP}" if is_selected else self.theme.TEXT_PRIMARY
            title_text = Text(self._truncate(item.title, 30 if compact else 48), style=title_style)
            row_index = Text(f"{actual_index + 1}.", style=self.theme.TEXT_DIM)

            if show_description:
                desc_style = self.theme.TEXT_SECONDARY if is_selected else self.theme.TEXT_DIM
                desc_text = Text(self._truncate(item.description, 34 if compact else 62), style=desc_style)
                table.add_row(indicator, row_index, title_text, desc_text)
            else:
                table.add_row(indicator, row_index, title_text)

        content_parts = [title_panel]
        if visible_items:
            list_panel = Panel(
                table,
                title=f"[bold {self.theme.BLUE_SOFT}]Options[/bold {self.theme.BLUE_SOFT}]",
                subtitle=f"[{self.theme.TEXT_DIM}]Visible {self.scroll_offset + 1}-{end_index} / {len(self.filtered_items)}[/{self.theme.TEXT_DIM}]",
                border_style=self.theme.BORDER_SUBTLE,
                box=box.ROUNDED,
                padding=(0, 1),
            )
            detail_panel = self._build_detail_panel(selected_item, compact=compact)
            body = Columns([list_panel, detail_panel], expand=True, equal=False) if wide else Group(list_panel, detail_panel)
            content_parts.extend(["", body])
        else:
            content_parts.extend([
                "",
                Panel(
                    Text("No matching items. Refine the search or press Esc to cancel.", style=self.theme.TEXT_DIM),
                    border_style=self.theme.BORDER_SUBTLE,
                    box=box.ROUNDED,
                    padding=(0, 1),
                ),
            ])

        if self.is_searching:
            search_text = Text()
            search_text.append(f"{self.deco.SEARCH} Search: ", style=f"bold {self.theme.PURPLE_SOFT}")
            search_text.append(self.search_query, style=f"bold {self.theme.TEXT_PRIMARY}")
            search_text.append("_", style=f"bold {self.theme.PINK_SOFT}")
            search_panel = Panel(
                search_text,
                border_style=self.theme.PINK_SOFT,
                padding=(0, 1),
                box=box.ROUNDED,
            )
            content_parts.extend(["", search_panel])

        visible_end = self.scroll_offset + len(visible_items)
        footer_grid = Table.grid(expand=True)
        footer_grid.add_column(ratio=1)
        footer_grid.add_column(justify="right", no_wrap=True)
        footer_grid.add_row(
            self._get_help_text(compact=compact),
            Text(
                (f"{self.scroll_offset + 1}-{visible_end} / {len(self.filtered_items)}" if visible_items else f"0 / {len(self.filtered_items)}"),
                style=self.theme.TEXT_DIM,
            ),
        )
        content_parts.extend([
            "",
            Panel(footer_grid, border_style=self.theme.BORDER_SUBTLE, box=box.ROUNDED, padding=(0, 1)),
        ])

        renderable = Align(Group(*content_parts), vertical="top")
        self._render_cache_key = cache_key
        self._render_cache = renderable
        return renderable

    def _render(self) -> None:
        """Render the selector UI (deprecated, use _build_content with Live)"""
        # This method is kept for backward compatibility but should not be used
        # Use _build_content() with Live context instead
        content = self._build_content()
        self.console.print(content)
    
    def _get_help_text(self, compact: bool = False) -> Text:
        """Get help text for navigation."""
        help_text = Text()
        help_text.append("Navigation: ", style=self.theme.TEXT_DIM)
        help_text.append("Up/Down or j/k", style=self.theme.BLUE_SOFT)
        help_text.append(" Navigate ", style=self.theme.TEXT_DIM)
        help_text.append("Enter", style=self.theme.BLUE_SOFT)
        help_text.append(" Select ", style=self.theme.TEXT_DIM)
        if self.allow_cancel:
            help_text.append("Esc", style=self.theme.BLUE_SOFT)
            help_text.append(" Cancel ", style=self.theme.TEXT_DIM)
        if self.allow_search and not compact:
            help_text.append("/", style=self.theme.BLUE_SOFT)
            help_text.append(" Search ", style=self.theme.TEXT_DIM)
        if not compact:
            help_text.append("PgUp/PgDn", style=self.theme.BLUE_SOFT)
            help_text.append(" Page ", style=self.theme.TEXT_DIM)
            help_text.append("Home/End", style=self.theme.BLUE_SOFT)
        return help_text


class ModelSelector(TUISelector):
    """Specialized selector for model selection"""
    
    def __init__(
        self,
        console: Console,
        models: List[Dict[str, Any]],
        current_model: Optional[str] = None
    ):
        items = [
            SelectorItem(
                id=model['id'],
                title=model['name'],
                description=model.get('description', ''),
                metadata=model
            )
            for model in models
        ]

        current_index = 0
        if current_model:
            for i, item in enumerate(items):
                if item.id == current_model:
                    current_index = i
                    break
        
        super().__init__(
            console=console,
            title="Select Model",
            items=items,
            allow_search=True,
            allow_cancel=True,
            show_descriptions=True
        )
        self.selected_index = current_index
        self.scroll_offset = max(0, self.selected_index - self.max_visible + 1)


class SubagentSelector(TUISelector):
    """Specialized selector for configured Subagents."""

    def __init__(self, console: Console, subagents: List[Dict[str, Any]]):
        items = []
        for subagent in subagents:
            model_ref = subagent.get("model_ref", {}) if isinstance(subagent.get("model_ref"), dict) else {}
            display_name = str(model_ref.get("display_name") or model_ref.get("model") or "(unresolved)")
            source = str(model_ref.get("source") or "standard")
            status = "enabled" if subagent.get("enabled", True) else "disabled"
            items.append(
                SelectorItem(
                    id=str(subagent.get("id") or ""),
                    title=str(subagent.get("name") or subagent.get("id") or "Subagent"),
                    description=f"{display_name} ({source}) - {status}",
                    metadata=subagent,
                )
            )

        super().__init__(
            console=console,
            title="Subagents",
            items=items,
            allow_search=True,
            allow_cancel=True,
            show_descriptions=True,
        )


class SettingsSelector(TUISelector):
    """Specialized selector for settings configuration"""
    
    def __init__(
        self,
        console: Console,
        settings: List[Dict[str, Any]],
        current_values: Dict[str, Any]
    ):
        items = []
        for setting in settings:
            current_value = current_values.get(setting['key'], setting.get('default', ''))
            description = f"Current: {current_value}"
            
            items.append(SelectorItem(
                id=setting['key'],
                title=setting['name'],
                description=description,
                metadata=setting
            ))
        
        super().__init__(
            console=console,
            title="Settings",
            items=items,
            allow_search=True,
            allow_cancel=True,
            show_descriptions=True
        )


class SessionSelector(TUISelector):
    """Specialized selector for session selection"""
    
    def __init__(
        self,
        console: Console,
        sessions: List[Dict[str, Any]],
        current_session: Optional[str] = None
    ):
        items = []
        current_index = 0
        for session in sessions:
            created_at = session.get('created_at', '')
            message_count = session.get('message_count', 0)
            description = f"{created_at} | {message_count} messages"
            items.append(SelectorItem(
                id=session['id'],
                title=session['name'],
                description=description,
                metadata=session
            ))
            if current_session and session['id'] == current_session:
                current_index = len(items) - 1
        
        super().__init__(
            console=console,
            title="Select Session",
            items=items,
            allow_search=True,
            allow_cancel=True,
            show_descriptions=True
        )
        self.selected_index = current_index
        self.scroll_offset = max(0, self.selected_index - self.max_visible + 1)


class CheckpointSelector(TUISelector):
    """Specialized selector for checkpoint selection"""
    
    def __init__(
        self,
        console: Console,
        checkpoints: List[Dict[str, Any]],
        file_path: Optional[str] = None
    ):
        items = []
        for checkpoint in checkpoints:
            created_at = checkpoint.get('created_at', '')
            description = f"Created: {created_at}"
            
            if file_path:
                description += f" • File: {file_path}"
            
            items.append(SelectorItem(
                id=checkpoint['id'],
                title=checkpoint.get('description', 'Checkpoint'),
                description=description,
                metadata=checkpoint
            ))
        
        title = f"Select Checkpoint for {file_path}" if file_path else "Select Checkpoint"
        
        super().__init__(
            console=console,
            title=title,
            items=items,
            allow_search=True,
            allow_cancel=True,
            show_descriptions=True
        )
