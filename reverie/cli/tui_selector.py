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

from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich.text import Text
from rich.align import Align
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
    
    def run(self) -> SelectorResult:
        """
        Run the selector and return the result.
        
        This method blocks until the user makes a selection or cancels.
        """
        import msvcrt
        import sys
        import time
        from rich.live import Live
        from rich.align import Align
        
        # Initial render
        content = self._build_content()
        
        with Live(content, console=self.console, refresh_per_second=30) as live:
            while True:
                # Wait for key press
                if msvcrt.kbhit():
                    key = msvcrt.getch()
                    
                    # Handle special keys
                    if key == b'\x00' or key == b'\xe0':  # Function key
                        key = msvcrt.getch()
                        
                        if key == b'H':  # Up arrow
                            self._navigate_up()
                        elif key == b'P':  # Down arrow
                            self._navigate_down()
                        elif key == b'I':  # Page Up
                            self._page_up()
                        elif key == b'Q':  # Page Down
                            self._page_down()
                        elif key == b'G':  # Home
                            self._go_home()
                        elif key == b'O':  # End
                            self._go_end()
                        else:
                            # Unknown function key, skip
                            continue
                    
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
                    
                    elif key == b'/':  # Slash to start search
                        if self.allow_search and not self.is_searching:
                            self.is_searching = True
                            self.search_query = ""
                    
                    elif self.is_searching:
                        # Handle search input
                        if key == b'\x08':  # Backspace
                            self.search_query = self.search_query[:-1]
                            self._apply_search()
                        elif 32 <= key[0] <= 126:  # Printable characters
                            self.search_query += key.decode('ascii')
                            self._apply_search()
                    
                    else:
                        # Other keys, skip
                        continue
                    
                    # Update the live display
                    live.update(self._build_content())
                
                # Small sleep to prevent CPU spinning
                time.sleep(0.01)
    
    def _navigate_up(self) -> None:
        """Navigate up in the list"""
        if self.selected_index > 0:
            self.selected_index -= 1
            if self.selected_index < self.scroll_offset:
                self.scroll_offset = self.selected_index
    
    def _navigate_down(self) -> None:
        """Navigate down in the list"""
        if self.selected_index < len(self.filtered_items) - 1:
            self.selected_index += 1
            if self.selected_index >= self.scroll_offset + self.max_visible:
                self.scroll_offset = self.selected_index - self.max_visible + 1
    
    def _page_up(self) -> None:
        """Page up"""
        page_size = self.max_visible - 1
        self.selected_index = max(0, self.selected_index - page_size)
        self.scroll_offset = max(0, self.scroll_offset - page_size)
    
    def _page_down(self) -> None:
        """Page down"""
        page_size = self.max_visible - 1
        self.selected_index = min(
            len(self.filtered_items) - 1,
            self.selected_index + page_size
        )
        self.scroll_offset = min(
            len(self.filtered_items) - self.max_visible,
            self.scroll_offset + page_size
        )
    
    def _go_home(self) -> None:
        """Go to first item"""
        self.selected_index = 0
        self.scroll_offset = 0
    
    def _go_end(self) -> None:
        """Go to last item"""
        self.selected_index = len(self.filtered_items) - 1
        self.scroll_offset = max(
            0,
            len(self.filtered_items) - self.max_visible
        )
    
    def _apply_search(self) -> None:
        """Apply search filter"""
        if not self.search_query:
            self.filtered_items = self.items.copy()
        else:
            query = self.search_query.lower()
            self.filtered_items = [
                item for item in self.items
                if query in item.title.lower() or
                   query in item.description.lower()
            ]
        
        self.selected_index = 0
        self.scroll_offset = 0
    
    def _build_content(self) -> Align:
        """Build the complete content for display"""
        from rich.console import Group
        
        # Create title panel
        title_text = Text()
        title_text.append(f"{self.deco.SPARKLE} ", style=self.theme.PINK_SOFT)
        title_text.append(self.title, style=f"bold {self.theme.PURPLE_SOFT}")
        
        title_panel = Panel(
            title_text,
            border_style=self.theme.BORDER_PRIMARY,
            padding=(0, 2),
            box=box.ROUNDED
        )
        
        # Create items table
        table = Table(
            show_header=False,
            box=box.ROUNDED,
            border_style=self.theme.BORDER_SECONDARY,
            padding=(0, 1),
            show_lines=False
        )
        
        table.add_column("indicator", width=3)
        table.add_column("title", style=self.theme.TEXT_PRIMARY)
        
        if self.show_descriptions:
            table.add_column("description", style=self.theme.TEXT_SECONDARY)
        
        # Calculate visible items
        end_index = min(
            self.scroll_offset + self.max_visible,
            len(self.filtered_items)
        )
        
        visible_items = self.filtered_items[self.scroll_offset:end_index]
        
        # Add items to table
        for i, item in enumerate(visible_items):
            actual_index = self.scroll_offset + i
            is_selected = actual_index == self.selected_index
            
            # Indicator
            if is_selected:
                indicator = Text(f"{self.deco.CHEVRON_RIGHT}", style=f"bold {self.theme.PINK_SOFT}")
            else:
                indicator = Text("  ")
            
            # Title with enhanced visual feedback
            if is_selected:
                # Selected item: bold with background highlight
                title_style = f"bold {self.theme.BLUE_SOFT} on {self.theme.PURPLE_DEEP}"
            else:
                title_style = self.theme.TEXT_PRIMARY
            
            title_text = Text(item.title, style=title_style)
            
            # Description
            if self.show_descriptions:
                desc_text = Text(item.description, style=self.theme.TEXT_DIM)
                table.add_row(indicator, title_text, desc_text)
            else:
                table.add_row(indicator, title_text)
        
        # Build content group
        content_parts = [title_panel, "", table, "", self._get_help_text()]
        
        # Add search bar if searching
        if self.is_searching:
            search_text = Text()
            search_text.append(f"{self.deco.SEARCH} Search: ", style=f"bold {self.theme.PURPLE_SOFT}")
            search_text.append(self.search_query, style=f"bold {self.theme.TEXT_PRIMARY}")
            search_text.append("_", style=f"bold {self.theme.PINK_SOFT}")  # Blinking cursor effect
            
            search_panel = Panel(
                search_text,
                border_style=self.theme.PINK_SOFT,
                padding=(0, 1),
                box=box.ROUNDED
            )
            content_parts.append(search_panel)
        
        # Add scroll indicator if needed
        if len(self.filtered_items) > self.max_visible:
            scroll_info = Text()
            scroll_info.append(f"Showing {self.scroll_offset + 1}-{min(self.scroll_offset + self.max_visible, len(self.filtered_items))} of {len(self.filtered_items)}", 
                             style=self.theme.TEXT_DIM)
            content_parts.append(scroll_info)
        
        return Align(Group(*content_parts), vertical="top")
    
    def _render(self) -> None:
        """Render the selector UI (deprecated, use _build_content with Live)"""
        # This method is kept for backward compatibility but should not be used
        # Use _build_content() with Live context instead
        content = self._build_content()
        self.console.print(content)
    
    def _get_help_text(self) -> Text:
        """Get help text for navigation"""
        help_text = Text()
        
        # Navigation label
        help_text.append("Navigation: ", style=self.theme.TEXT_DIM)
        
        # Navigate
        help_text.append("↑↓", style=self.theme.BLUE_SOFT)
        help_text.append(" Navigate ", style=self.theme.TEXT_DIM)
        
        # Select
        help_text.append("Enter", style=self.theme.BLUE_SOFT)
        help_text.append(" Select ", style=self.theme.TEXT_DIM)
        
        # Cancel
        if self.allow_cancel:
            help_text.append("Esc", style=self.theme.BLUE_SOFT)
            help_text.append(" Cancel ", style=self.theme.TEXT_DIM)
        
        # Search
        if self.allow_search:
            help_text.append("/", style=self.theme.BLUE_SOFT)
            help_text.append(" Search ", style=self.theme.TEXT_DIM)
        
        # Page
        help_text.append("PgUp/PgDn", style=self.theme.BLUE_SOFT)
        help_text.append(" Page", style=self.theme.TEXT_DIM)
        
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
        for session in sessions:
            created_at = session.get('created_at', '')
            message_count = session.get('message_count', 0)
            
            description = f"{created_at} • {message_count} messages"
            
            items.append(SelectorItem(
                id=session['id'],
                title=session['name'],
                description=description,
                metadata=session
            ))
        
        # Set current session as selected
        if current_session:
            for i, item in enumerate(items):
                if item.id == current_session:
                    self.selected_index = i
                    break
        
        super().__init__(
            console=console,
            title="Select Session",
            items=items,
            allow_search=True,
            allow_cancel=True,
            show_descriptions=True
        )


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
