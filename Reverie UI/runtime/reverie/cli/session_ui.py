"""
Session UI - Interactive session management
"""

from typing import Optional
from rich.console import Console


class SessionUI:
    """Interactive session selection and management"""
    
    def __init__(self, console: Console, session_manager):
        self.console = console
        self.session_manager = session_manager
    
    def show_selector(self) -> Optional[str]:
        """Show interactive session selector, returns selected session ID"""
        # This is handled by CommandHandler for now
        pass
