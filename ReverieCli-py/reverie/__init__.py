"""
Reverie Cli - World-Class Context Engine Coding Assistant

Reverie is an agentic coding tool that uses a sophisticated
Context Engine to understand large codebases and reduce
AI model hallucinations.
"""

# Keep package import lightweight.  Config imports every built-in provider, so
# load the convenience exports only when callers actually request them.
from importlib import import_module

from .version import __version__

__author__ = "Raiden"
__description__ = "World-Class Context Engine Coding Assistant"

__all__ = [
    '__version__',
    '__author__',
    '__description__',
    'Config',
    'ConfigManager',
    'ModelConfig',
]

_LAZY_EXPORTS = {
    'Config': ('.config', 'Config'),
    'ConfigManager': ('.config', 'ConfigManager'),
    'ModelConfig': ('.config', 'ModelConfig'),
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
