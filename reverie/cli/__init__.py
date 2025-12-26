"""
Reverie CLI Package

Rich command-line interface components:
- ReverieInterface: Main interactive interface
- CommandHandler: Process CLI commands
- DisplayComponents: Rich UI elements
- InputHandler: Multiline input and command completion
- SessionUI: Session management UI
"""

from .interface import ReverieInterface
from .commands import CommandHandler
from .display import DisplayComponents
from .input_handler import InputHandler
from .session_ui import SessionUI

__all__ = [
    'ReverieInterface',
    'CommandHandler',
    'DisplayComponents',
    'InputHandler',
    'SessionUI',
]
