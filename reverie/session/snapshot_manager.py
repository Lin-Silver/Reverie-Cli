"""
Snapshot Manager - Repository-grade project snapshots

Provides:
- Full project file tree snapshots (like Git commits)
- Automatic snapshot creation before each user question
- Snapshot restoration (one-click recovery)
- Automatic cleanup (keep max 10 snapshots)
"""

from pathlib import Path
from typing import List, Dict, Optional
from dataclasses import dataclass
from datetime import datetime
import json
import shutil
import hashlib
import logging


logger = logging.getLogger(__name__)


@dataclass
class SnapshotInfo:
    """Information about a project snapshot"""
    id: str
    created_at: str
    description: str
    file_count: int
    total_size_bytes: int
    manifest_hash: str = ""
    reused: bool = False
    
    def to_dict(self) -> dict:
        return {
            'id': self.id,
            'created_at': self.created_at,
            'description': self.description,
            'file_count': self.file_count,
            'total_size_bytes': self.total_size_bytes,
            'manifest_hash': self.manifest_hash,
        }
    
    @classmethod
    def from_dict(cls, data: dict) -> 'SnapshotInfo':
        return cls(
            id=data['id'],
            created_at=data['created_at'],
            description=data['description'],
            file_count=data['file_count'],
            total_size_bytes=data['total_size_bytes'],
            manifest_hash=data.get('manifest_hash', ''),
        )


class SnapshotManager:
    """
    Manages repository-grade project snapshots.
    
    Snapshots capture the entire project file tree at a specific point in time,
    similar to Git commits. They can be restored to recover the project state.
    """
    
    # Directories and files to exclude from snapshots
    EXCLUDE_PATTERNS = [
        '.git',
        '__pycache__',
        '.reverie',
        'node_modules',
        'venv',
        'env',
        '.venv',
        '.env',
        '*.pyc',
        '*.pyo',
        '*.pyd',
        '.DS_Store',
        'Thumbs.db',
        '*.log',
        '.pytest_cache',
        '.mypy_cache',
        '.tox',
        'dist',
        'build',
        '*.egg-info'
    ]
    
    MAX_SNAPSHOTS = 10  # Maximum number of snapshots to keep
    
    def __init__(self, project_root: Path, snapshots_dir: Path):
        self.project_root = project_root
        self.snapshots_dir = snapshots_dir
        self.snapshots_dir.mkdir(parents=True, exist_ok=True)
    
    def _should_exclude(self, path: Path) -> bool:
        """Check if a path should be excluded from snapshot"""
        path_str = str(path)
        
        # Check directory names
        for part in path.parts:
            if part in ['.git', '__pycache__', '.reverie', 'node_modules', 'venv', 'env', '.venv']:
                return True
        
        # Check file extensions
        if path.is_file():
            if path.suffix in ['.pyc', '.pyo', '.pyd', '.log']:
                return True
            if path.name in ['.DS_Store', 'Thumbs.db']:
                return True
        
        return False
    
    def _collect_files(self) -> List[Path]:
        """Collect all files to include in snapshot"""
        files = []
        
        try:
            for item in self.project_root.rglob('*'):
                if item.is_file() and not self._should_exclude(item):
                    files.append(item)
        except Exception as e:
            logger.warning("Error collecting snapshot files: %s", e)

        files.sort(key=lambda item: str(item.relative_to(self.project_root)).replace("\\", "/"))
        return files

    def _build_manifest_hash(self, files: List[Path]) -> str:
        """Fingerprint the current workspace snapshot contents cheaply from stat metadata."""
        digest = hashlib.sha1()
        for file_path in files:
            try:
                rel_path = str(file_path.relative_to(self.project_root)).replace("\\", "/")
                stat = file_path.stat()
            except Exception:
                continue
            digest.update(rel_path.encode("utf-8", errors="ignore"))
            digest.update(b"\0")
            digest.update(str(int(stat.st_size)).encode("ascii", errors="ignore"))
            digest.update(b"\0")
            digest.update(str(int(getattr(stat, "st_mtime_ns", int(stat.st_mtime * 1_000_000_000)))).encode("ascii", errors="ignore"))
            digest.update(b"\n")
        return digest.hexdigest()

    def _latest_snapshot(self) -> Optional[SnapshotInfo]:
        snapshots = self.list_snapshots()
        return snapshots[0] if snapshots else None

    def create_snapshot(self, description: str = "") -> Optional[SnapshotInfo]:
        """
        Create a new project snapshot.
        
        Args:
            description: Optional description for the snapshot
        
        Returns:
            SnapshotInfo if successful, None otherwise
        """
        try:
            # Collect files
            files = self._collect_files()
            
            if not files:
                logger.info("No files matched the snapshot scope")
                return None

            manifest_hash = self._build_manifest_hash(files)
            latest_snapshot = self._latest_snapshot()
            if latest_snapshot and latest_snapshot.manifest_hash and latest_snapshot.manifest_hash == manifest_hash:
                latest_snapshot.reused = True
                return latest_snapshot

            # Generate snapshot ID (timestamp-based with microseconds to avoid collisions)
            now = datetime.now()
            snapshot_id = f"snap_{now.strftime('%Y%m%d_%H%M%S_%f')}"

            # Create snapshot directory
            snapshot_dir = self.snapshots_dir / snapshot_id
            snapshot_dir.mkdir(exist_ok=True)
            
            # Copy files to snapshot directory
            total_size = 0
            for file_path in files:
                try:
                    # Calculate relative path
                    rel_path = file_path.relative_to(self.project_root)
                    
                    # Create target path
                    target_path = snapshot_dir / rel_path
                    target_path.parent.mkdir(parents=True, exist_ok=True)
                    
                    # Copy file
                    shutil.copy2(file_path, target_path)
                    total_size += file_path.stat().st_size
                
                except Exception as e:
                    logger.warning("Failed to copy %s into snapshot: %s", file_path, e)
                    continue
            
            # Create snapshot metadata
            snapshot_info = SnapshotInfo(
                id=snapshot_id,
                created_at=now.isoformat(),
                description=description or f"Snapshot at {now.strftime('%Y-%m-%d %H:%M:%S')}",
                file_count=len(files),
                total_size_bytes=total_size,
                manifest_hash=manifest_hash,
            )
            
            # Save metadata
            meta_path = snapshot_dir / 'snapshot_meta.json'
            with open(meta_path, 'w', encoding='utf-8') as f:
                json.dump(snapshot_info.to_dict(), f, indent=2, ensure_ascii=False)
            
            # Cleanup old snapshots
            self._cleanup_old_snapshots()
            
            return snapshot_info
        
        except Exception as e:
            logger.error("Error creating snapshot: %s", e)
            return None
    
    def list_snapshots(self) -> List[SnapshotInfo]:
        """List all available snapshots"""
        snapshots = []
        
        for snapshot_dir in self.snapshots_dir.iterdir():
            if not snapshot_dir.is_dir():
                continue
            
            meta_path = snapshot_dir / 'snapshot_meta.json'
            if not meta_path.exists():
                continue
            
            try:
                with open(meta_path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                snapshots.append(SnapshotInfo.from_dict(data))
            except Exception:
                continue
        
        # Sort by creation time (newest first)
        snapshots.sort(key=lambda s: s.created_at, reverse=True)
        
        return snapshots
    
    def restore_snapshot(self, snapshot_id: str, backup_current: bool = True) -> bool:
        """
        Restore a snapshot to the project directory.
        
        Args:
            snapshot_id: ID of the snapshot to restore
            backup_current: If True, create a backup of current state before restoring
        
        Returns:
            True if successful, False otherwise
        """
        snapshot_dir = self.snapshots_dir / snapshot_id
        
        if not snapshot_dir.exists():
            logger.warning("Snapshot %s not found", snapshot_id)
            return False
        
        try:
            # Create backup of current state if requested
            if backup_current:
                backup_info = self.create_snapshot("Pre-restore backup")
                if backup_info:
                    logger.info("Created pre-restore backup snapshot %s", backup_info.id)
            
            # Clear current project files (except excluded directories)
            for item in self.project_root.iterdir():
                if self._should_exclude(item):
                    continue
                
                try:
                    if item.is_file():
                        item.unlink()
                    elif item.is_dir():
                        shutil.rmtree(item)
                except Exception as e:
                    logger.warning("Failed to remove %s during snapshot restore: %s", item, e)
            
            # Restore files from snapshot
            for item in snapshot_dir.rglob('*'):
                if item.name == 'snapshot_meta.json':
                    continue
                
                if item.is_file():
                    # Calculate relative path
                    rel_path = item.relative_to(snapshot_dir)
                    
                    # Create target path
                    target_path = self.project_root / rel_path
                    target_path.parent.mkdir(parents=True, exist_ok=True)
                    
                    # Copy file
                    shutil.copy2(item, target_path)
            
            logger.info("Successfully restored snapshot %s", snapshot_id)
            return True
        
        except Exception as e:
            logger.error("Error restoring snapshot %s: %s", snapshot_id, e)
            return False
    
    def delete_snapshot(self, snapshot_id: str) -> bool:
        """Delete a specific snapshot"""
        snapshot_dir = self.snapshots_dir / snapshot_id
        
        if not snapshot_dir.exists():
            return False
        
        try:
            shutil.rmtree(snapshot_dir)
            return True
        except Exception as e:
            logger.error("Error deleting snapshot %s: %s", snapshot_id, e)
            return False
    
    def _cleanup_old_snapshots(self) -> int:
        """
        Clean up old snapshots, keeping only the most recent MAX_SNAPSHOTS.
        
        Returns:
            Number of snapshots deleted
        """
        snapshots = self.list_snapshots()
        
        if len(snapshots) <= self.MAX_SNAPSHOTS:
            return 0
        
        # Delete oldest snapshots
        to_delete = snapshots[self.MAX_SNAPSHOTS:]
        deleted_count = 0
        
        for snapshot in to_delete:
            if self.delete_snapshot(snapshot.id):
                deleted_count += 1
        
        return deleted_count
    
    def get_snapshot_info(self, snapshot_id: str) -> Optional[SnapshotInfo]:
        """Get information about a specific snapshot"""
        snapshot_dir = self.snapshots_dir / snapshot_id
        meta_path = snapshot_dir / 'snapshot_meta.json'
        
        if not meta_path.exists():
            return None
        
        try:
            with open(meta_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            return SnapshotInfo.from_dict(data)
        except Exception:
            return None
