"""
Reverie Session Package

Session management for conversation persistence:
- SessionManager: Create, save, load sessions with auto-rotation
- Session: A conversation session
- CheckpointManager: Create/restore checkpoints with file-level support
- ArchiveManager: Long-term storage
- OperationHistory: Track all operations for rollback support
- RollbackManager: Advanced rollback functionality
- SnapshotManager: Repository-grade project snapshots
- MemoryIndexer: Project database indexing for persistent memory
"""

from .manager import SessionManager, Session, SessionInfo
from .checkpoint import CheckpointManager, Checkpoint, FileCheckpoint
from .archive import ArchiveManager, Archive
from .operation_history import OperationHistory, Operation, OperationType
from .rollback_manager import RollbackManager, RollbackResult
from .snapshot_manager import SnapshotManager, SnapshotInfo
from .memory_indexer import MemoryIndexer, MemoryFragment, ProjectIndex
from .workspace_stats import WorkspaceStatsManager, get_known_workspaces

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
    'SnapshotManager',
    'SnapshotInfo',
    'MemoryIndexer',
    'MemoryFragment',
    'ProjectIndex',
    'WorkspaceStatsManager',
    'get_known_workspaces',
]
