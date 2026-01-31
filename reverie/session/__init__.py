"""
Reverie Session Package

Session management for conversation persistence:
- SessionManager: Create, save, load sessions
- Session: A conversation session
- CheckpointManager: Create/restore checkpoints with file-level support
- ArchiveManager: Long-term storage
- OperationHistory: Track all operations for rollback support
- RollbackManager: Advanced rollback functionality
"""

from .manager import SessionManager, Session, SessionInfo
from .checkpoint import CheckpointManager, Checkpoint, FileCheckpoint
from .archive import ArchiveManager, Archive
from .operation_history import OperationHistory, Operation, OperationType
from .rollback_manager import RollbackManager, RollbackResult

__all__ = [
    'SessionManager',
    'Session',
    'SessionInfo',
    'CheckpointManager',
    'Checkpoint',
    'FileCheckpoint',
    'ArchiveManager',
    'Archive',
    'OperationHistory',
    'Operation',
    'OperationType',
    'RollbackManager',
    'RollbackResult',
]
