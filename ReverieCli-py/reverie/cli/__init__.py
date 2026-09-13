"""
Reverie CLI Package

Rich command-line interface components with Dreamscape Theme:
- ReverieInterface: Main interactive interface
- CommandHandler: Process CLI commands
- DisplayComponents: Rich UI elements
- InputHandler: Multiline input and command completion
- SessionUI: Session management UI
- RollbackUI: Interactive rollback interface
- Theme: Dreamscape color palette and decorators
"""

from importlib import import_module

__all__ = [
    'ReverieInterface',
    'CommandHandler',
    'DisplayComponents',
    'InputHandler',
    'SessionUI',
    'RollbackUI',
    'THEME',
    'DECO',
    'DREAM',
    'DreamscapeTheme',
    'DreamDecorators',
    'DreamText',
]

_LAZY_EXPORTS = {
    'ReverieInterface': ('.interface', 'ReverieInterface'),
    'CommandHandler': ('.commands', 'CommandHandler'),
    'DisplayComponents': ('.display', 'DisplayComponents'),
    'InputHandler': ('.input_handler', 'InputHandler'),
    'SessionUI': ('.session_ui', 'SessionUI'),
    'RollbackUI': ('.rollback_ui', 'RollbackUI'),
    'THEME': ('.theme', 'THEME'),
    'DECO': ('.theme', 'DECO'),
    'DREAM': ('.theme', 'DREAM'),
    'DreamscapeTheme': ('.theme', 'DreamscapeTheme'),
    'DreamDecorators': ('.theme', 'DreamDecorators'),
    'DreamText': ('.theme', 'DreamText'),
}


def __getattr__(name: str):
    target = _LAZY_EXPORTS.get(name)
    if target is None:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    module_name, attribute_name = target
    value = getattr(import_module(module_name, __name__), attribute_name)
    globals()[name] = value
    return value


def __dir__() -> list[str]:
    return sorted(set(globals()) | set(__all__))
