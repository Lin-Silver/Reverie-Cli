"""
Rollback UI - Interactive rollback interface with TUI

Provides a modern, commercial-feeling TUI interface for:
- Selecting rollback points
- Viewing operation history
- Managing checkpoints
- Undo/redo operations

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


class RollbackAction(Enum):
    """Actions that can be performed in the rollback UI"""
    ROLLBACK_TO_QUESTION = auto()
    ROLLBACK_TO_TOOL = auto()
    ROLLBACK_TO_CHECKPOINT = auto()
    UNDO = auto()
    REDO = auto()
    CANCEL = auto()
    VIEW_DETAILS = auto()


@dataclass
class RollbackPoint:
    """A rollback point in the history"""
    id: str
    type: str  # 'question', 'tool', 'checkpoint'
    description: str
    timestamp: str
    message_index: int = -1
    checkpoint_id: Optional[str] = None
    metadata: Dict = None
    
    def __post_init__(self):
        if self.metadata is None:
            self.metadata = {}


class RollbackUI:
    """
    Interactive TUI for rollback operations.
    
    Provides a modern, commercial-feeling interface for selecting
    rollback points and managing operations.
    """
    
    def __init__(
        self,
        console: Console,
        rollback_manager,
        operation_history
    ):
        self.console = console
        self.rollback_manager = rollback_manager
        self.operation_history = operation_history
        
        self.theme = THEME
        self.deco = DECO
    
    def show_main_menu(self) -> Optional[RollbackAction]:
        """
        Show the main rollback menu.
        
        Returns:
            The selected action, or None if cancelled
        """
        from .tui_selector import TUISelector, SelectorItem, SelectorAction
        
        items = [
            SelectorItem(
                id="rollback_question",
                title="Rollback to Previous Question",
                description="Restore state before the last user question",
                metadata={"action": RollbackAction.ROLLBACK_TO_QUESTION}
            ),
            SelectorItem(
                id="rollback_tool",
                title="Rollback to Previous Tool Call",
                description="Restore state before the last tool execution",
                metadata={"action": RollbackAction.ROLLBACK_TO_TOOL}
            ),
            SelectorItem(
                id="rollback_checkpoint",
                title="Rollback to Checkpoint",
                description="Select a specific checkpoint to restore",
                metadata={"action": RollbackAction.ROLLBACK_TO_CHECKPOINT}
            ),
            SelectorItem(
                id="undo",
                title="Undo Last Rollback",
                description="Undo the most recent rollback operation",
                metadata={"action": RollbackAction.UNDO}
            ),
            SelectorItem(
                id="redo",
                title="Redo Last Undo",
                description="Redo the most recently undone rollback",
                metadata={"action": RollbackAction.REDO}
            ),
        ]
        
        selector = TUISelector(
            console=self.console,
            title=f"[bold {self.theme.PINK_SOFT}]{self.deco.SPARKLE} Rollback Menu {self.deco.SPARKLE}[/bold {self.theme.PINK_SOFT}]",
            items=items,
            allow_search=False,
            allow_cancel=True,
            show_descriptions=True,
            max_visible=6
        )
        
        result = selector.run()
        
        if result.action == SelectorAction.CANCEL:
            return None
        
        if result.selected_item:
            return result.selected_item.metadata.get("action")
        
        return None
    
    def show_checkpoint_selector(self) -> Optional[str]:
        """
        Show a checkpoint selector.
        
        Returns:
            The selected checkpoint ID, or None if cancelled
        """
        from .tui_selector import CheckpointSelector, SelectorAction
        
        # Get checkpoints
        checkpoints = self.rollback_manager.checkpoint_manager.list_checkpoints()
        
        if not checkpoints:
            self.console.print()
            self.console.print(f"[{self.theme.TEXT_DIM}]No checkpoints available.[/{self.theme.TEXT_DIM}]")
            return None
        
        # Prepare checkpoint data for selector
        checkpoints_data = []
        for cp in checkpoints[:20]:  # Show last 20
            created_at = cp.created_at[:19].replace('T', ' ')
            description = f"{cp.description} • {cp.message_count} messages"
            
            checkpoints_data.append({
                'id': cp.id,
                'description': cp.description,
                'created_at': created_at,
                'message_count': cp.message_count,
                'checkpoint': cp
            })
        
        selector = CheckpointSelector(
            console=self.console,
            checkpoints=checkpoints_data
        )
        
        result = selector.run()
        
        if result.action == SelectorAction.CANCEL:
            return None
        
        if result.selected_item:
            return result.selected_item.id
        
        return None
    
    def show_operation_history(self, limit: int = 20) -> None:
        """
        Show operation history.
        
        Args:
            limit: Maximum number of operations to show
        """
        self.console.print()
        title_panel = Panel(
            f"[bold {self.theme.PINK_SOFT}]{self.deco.SPARKLE} Operation History {self.deco.SPARKLE}[/bold {self.theme.PINK_SOFT}]",
            border_style=self.theme.BORDER_PRIMARY,
            padding=(0, 2),
            box=box.ROUNDED
        )
        self.console.print(title_panel)
        self.console.print()
        
        # Get operations
        operations = self.operation_history.get_operations(limit=limit)
        
        if not operations:
            self.console.print(f"[{self.theme.TEXT_DIM}]No operations recorded yet.[/{self.theme.TEXT_DIM}]")
            return
        
        # Create table
        table = Table(
            box=box.ROUNDED,
            border_style=self.theme.BORDER_PRIMARY,
            show_lines=True
        )
        table.add_column("#", style=f"bold {self.theme.BLUE_SOFT}", width=4)
        table.add_column("Type", style=self.theme.TEXT_SECONDARY, width=12)
        table.add_column("Description", style=self.theme.TEXT_PRIMARY)
        table.add_column("Time", style=f"dim {self.theme.TEXT_DIM}", width=20)
        
        for i, op in enumerate(operations, 1):
            table.add_row(
                str(i),
                op.operation_type.value,
                op.description[:60],
                op.timestamp[:19].replace('T', ' ')
            )
        
        self.console.print(table)
        self.console.print()
        self.console.print(f"[{self.theme.TEXT_DIM}]Showing last {len(operations)} operations.[/{self.theme.TEXT_DIM}]")
    
    def show_rollback_summary(self, result) -> None:
        """
        Show a summary of the rollback operation.
        
        Args:
            result: RollbackResult from the rollback operation
        """
        self.console.print()
        
        if result.success:
            self.console.print(f"[{self.theme.MINT_VIBRANT}]{self.deco.CHECK_FANCY} {result.message}[/{self.theme.MINT_VIBRANT}]")
            
            if result.restored_files:
                self.console.print()
                self.console.print(f"[{self.theme.TEXT_DIM}]Restored files:[/{self.theme.TEXT_DIM}]")
                for file_path in result.restored_files:
                    self.console.print(f"  [{self.theme.MINT_SOFT}]✓[/{self.theme.MINT_SOFT}] {file_path}")
            
            if result.errors:
                self.console.print()
                self.console.print(f"[{self.theme.AMBER_GLOW}]{self.deco.DOT_MEDIUM} Errors:[/{self.theme.AMBER_GLOW}]")
                for error in result.errors:
                    self.console.print(f"  [{self.theme.CORAL_SOFT}]✗[/{self.theme.CORAL_SOFT}] {error}")
        else:
            self.console.print(f"[{self.theme.CORAL_SOFT}]{self.deco.CROSS} {result.message}[/{self.theme.CORAL_SOFT}]")
        
        self.console.print()
    
    def show_status_bar(self) -> None:
        """Show a status bar with rollback information"""
        if not self.rollback_manager:
            return
        
        summary = self.rollback_manager.get_operation_summary()
        
        status_text = Text()
        status_text.append(f"[{self.theme.PURPLE_MEDIUM}]{self.deco.LINE_HORIZONTAL * 2}[/{self.theme.PURPLE_MEDIUM}] ", style="")
        status_text.append(f"[{self.theme.PINK_SOFT}]{self.deco.SPARKLE}[/{self.theme.PINK_SOFT}] ", style="")
        
        # Show operation count
        status_text.append(f"[bold {self.theme.TEXT_PRIMARY}]{summary['total_operations']} ops[/bold {self.theme.TEXT_PRIMARY}] ", style="")
        status_text.append(f"[{self.theme.TEXT_DIM}]{self.deco.DOT_MEDIUM}[/{self.theme.TEXT_DIM}] ", style="")
        
        # Show modified files
        status_text.append(f"[{self.theme.PURPLE_SOFT}]{len(summary['modified_files'])} files[/{self.theme.PURPLE_SOFT}] ", style="")
        status_text.append(f"[{self.theme.TEXT_DIM}]{self.deco.DOT_MEDIUM}[/{self.theme.TEXT_DIM}] ", style="")
        
        # Show undo/redo status
        if summary['can_undo']:
            status_text.append(f"[bold {self.theme.MINT_SOFT}]Undo[/bold {self.theme.MINT_SOFT}] ", style="")
        else:
            status_text.append(f"[dim]Undo[/dim] ", style="")
        
        status_text.append(f"[{self.theme.TEXT_DIM}]{self.deco.DOT_MEDIUM}[/{self.theme.TEXT_DIM}] ", style="")
        
        if summary['can_redo']:
            status_text.append(f"[bold {self.theme.MINT_SOFT}]Redo[/bold {self.theme.MINT_SOFT}] ", style="")
        else:
            status_text.append(f"[dim]Redo[/dim] ", style="")
        
        status_text.append(f"[{self.theme.PINK_SOFT}]{self.deco.SPARKLE}[/{self.theme.PINK_SOFT}] ", style="")
        status_text.append(f"[{self.theme.PURPLE_MEDIUM}]{self.deco.LINE_HORIZONTAL * 2}[/{self.theme.PURPLE_MEDIUM}] ", style="")
        
        self.console.print(status_text)