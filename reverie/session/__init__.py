"""
Reverie Session Package

Session management for conversation persistence:
- SessionManager: Create, save, load sessions
- Session: A conversation session
- CheckpointManager: Create/restore checkpoints
- ArchiveManager: Long-term storage
"""

from .manager import SessionManager, Session, SessionInfo
from .checkpoint import CheckpointManager, Checkpoint
from .archive import ArchiveManager, Archive

__all__ = [
    'SessionManager',
    'Session',
    'SessionInfo',
    'CheckpointManager',
    'Checkpoint',
    'ArchiveManager',
    'Archive',
]
