"""
Reverie Session Package

Session management for conversation persistence:
- SessionManager: Create, save, load sessions
- Session: A conversation session
- CheckpointManager: Create/restore checkpoints with file-level support
- ArchiveManager: Long-term storage
"""

from .manager import SessionManager, Session, SessionInfo
from .checkpoint import CheckpointManager, Checkpoint, FileCheckpoint
from .archive import ArchiveManager, Archive

__all__ = [
    'SessionManager',
    'Session',
    'SessionInfo',
    'CheckpointManager',
    'Checkpoint',
    'FileCheckpoint',
    'ArchiveManager',
    'Archive',
]
