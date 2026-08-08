"""
Reverie Session Package

Session management for conversation persistence:
- SessionManager: Create, save, load sessions with auto-rotation
- Session: A conversation session
- CheckpointManager: Create/restore checkpoints with file-level support
- ArchiveManager: Long-term storage
- OperationHistory: Track all operations for rollback support
- RollbackManager: Advanced rollback functionality
- MemoryIndexer: Project database indexing for persistent memory
"""

from .manager import SessionManager, Session, SessionInfo
from .roles import (
    STORED_ASSISTANT_ROLE,
    from_stored_messages,
    from_stored_role,
    to_stored_messages,
    to_stored_role,
)
from .checkpoint import CheckpointManager, Checkpoint, FileCheckpoint
from .archive import ArchiveManager, Archive
from .operation_history import OperationHistory, Operation, OperationType
from .rollback_manager import RollbackManager, RollbackResult
from .memory_indexer import MemoryIndexer, MemoryFragment, ProjectIndex
from .workspace_stats import WorkspaceStatsManager, get_known_workspaces

__all__ = [
    'SessionManager',
    'Session',
    'SessionInfo',
    'STORED_ASSISTANT_ROLE',
    'from_stored_messages',
    'from_stored_role',
    'to_stored_messages',
    'to_stored_role',
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
    'MemoryIndexer',
    'MemoryFragment',
    'ProjectIndex',
    'WorkspaceStatsManager',
    'get_known_workspaces',
]
