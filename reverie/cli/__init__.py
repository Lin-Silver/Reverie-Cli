"""
Reverie CLI Package

Rich command-line interface components with Dreamscape Theme:
- ReverieInterface: Main interactive interface
- CommandHandler: Process CLI commands
- DisplayComponents: Rich UI elements
- InputHandler: Multiline input and command completion
- SessionUI: Session management UI
- Theme: Dreamscape color palette and decorators
"""

from .interface import ReverieInterface
from .commands import CommandHandler
from .display import DisplayComponents
from .input_handler import InputHandler
from .session_ui import SessionUI
from .theme import THEME, DECO, DREAM, DreamscapeTheme, DreamDecorators, DreamText

__all__ = [
    'ReverieInterface',
    'CommandHandler',
    'DisplayComponents',
    'InputHandler',
    'SessionUI',
    'THEME',
    'DECO',
    'DREAM',
    'DreamscapeTheme',
    'DreamDecorators',
    'DreamText',
]
