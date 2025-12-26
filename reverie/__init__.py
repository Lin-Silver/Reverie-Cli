"""
Reverie Cli - World-Class Context Engine Coding Assistant

Reverie is an agentic coding tool that uses a sophisticated
Context Engine to understand large codebases and reduce
AI model hallucinations.
"""

__version__ = "1.2.5"
__author__ = "Raiden"
__description__ = "World-Class Context Engine Coding Assistant"

# Convenient imports
from .config import Config, ConfigManager, ModelConfig

__all__ = [
    '__version__',
    '__author__',
    '__description__',
    'Config',
    'ConfigManager',
    'ModelConfig',
]
