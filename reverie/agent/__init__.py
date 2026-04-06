"""
Reverie Agent Package

The AI Agent that orchestrates tool usage and conversation:
- ReverieAgent: Main agent class with streaming support
- build_system_prompt: Generate the instruction prompt
- ToolExecutor: Execute tool calls
- THINKING_START_MARKER, THINKING_END_MARKER: Markers for thinking content
"""

from .agent import (
    ReverieAgent,
    HIDDEN_STREAM_TOKEN,
    THINKING_START_MARKER,
    THINKING_END_MARKER,
    STREAM_EVENT_MARKER,
    encode_stream_event,
    decode_stream_event,
)
from .system_prompt import build_system_prompt, get_tool_definitions
from .tool_executor import ToolExecutor

__all__ = [
    'ReverieAgent',
    'HIDDEN_STREAM_TOKEN',
    'THINKING_START_MARKER',
    'THINKING_END_MARKER',
    'STREAM_EVENT_MARKER',
    'encode_stream_event',
    'decode_stream_event',
    'build_system_prompt',
    'get_tool_definitions',
    'ToolExecutor',
]
