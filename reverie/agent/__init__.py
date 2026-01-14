"""
Reverie Agent Package

The AI Agent that orchestrates tool usage and conversation:
- ReverieAgent: Main agent class with streaming support
- build_system_prompt: Generate the instruction prompt
- ToolExecutor: Execute tool calls
- THINKING_START_MARKER, THINKING_END_MARKER: Markers for thinking content
"""

from .agent import ReverieAgent, THINKING_START_MARKER, THINKING_END_MARKER
from .system_prompt import build_system_prompt, get_tool_definitions
from .tool_executor import ToolExecutor

__all__ = [
    'ReverieAgent',
    'THINKING_START_MARKER',
    'THINKING_END_MARKER',
    'build_system_prompt',
    'get_tool_definitions',
    'ToolExecutor',
]
