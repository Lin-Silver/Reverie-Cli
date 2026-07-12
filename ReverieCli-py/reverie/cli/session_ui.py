"""
Session UI - Interactive session management
"""

from dataclasses import asdict
from typing import Optional
from rich.console import Console

from .tui_selector import SelectorAction, SessionSelector


class SessionUI:
    """Interactive session selection and management"""
    
    def __init__(self, console: Console, session_manager):
        self.console = console
        self.session_manager = session_manager
    
    def show_selector(self) -> Optional[str]:
        """Show interactive session selector, returns selected session ID"""
        sessions = list(self.session_manager.list_sessions())
        if not sessions:
            self.console.print("[dim]No saved sessions are available for this workspace.[/dim]")
            return None

        current = self.session_manager.get_current_session()
        selector = SessionSelector(
            self.console,
            [asdict(session) for session in sessions],
            current_session=current.id if current else None,
        )
        result = selector.run()
        if result.action != SelectorAction.SELECT or result.selected_item is None:
            return None
        return result.selected_item.id
