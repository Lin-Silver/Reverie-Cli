"""
Checkpoint Manager - Create and restore checkpoints

Checkpoints are automatic snapshots created before major operations.
Supports file-level checkpoints with TUI interaction for rollback.
"""

from pathlib import Path
from typing import List, Dict, Optional
from dataclasses import dataclass
from datetime import datetime
import json
import shutil
import hashlib


@dataclass
class FileCheckpoint:
    """A checkpoint for a single file"""
    file_path: str
    checkpoint_id: str
    content: str
    created_at: str
    description: str = ""
    
    def to_dict(self) -> dict:
        return {
            'file_path': self.file_path,
            'checkpoint_id': self.checkpoint_id,
            'content': self.content,
            'created_at': self.created_at,
            'description': self.description
        }
    
    @classmethod
    def from_dict(cls, data: dict) -> 'FileCheckpoint':
        return cls(
            file_path=data['file_path'],
            checkpoint_id=data['checkpoint_id'],
            content=data['content'],
            created_at=data['created_at'],
            description=data.get('description', '')
        )


@dataclass
class Checkpoint:
    """A checkpoint snapshot"""
    id: str
    session_id: str
    description: str
    created_at: str
    message_count: int
    file_checkpoints: List[str] = None  # List of file checkpoint IDs
    
    def __post_init__(self):
        if self.file_checkpoints is None:
            self.file_checkpoints = []
    
    def to_dict(self) -> dict:
        return {
            'id': self.id,
            'session_id': self.session_id,
            'description': self.description,
            'created_at': self.created_at,
            'message_count': self.message_count,
            'file_checkpoints': self.file_checkpoints
        }


class CheckpointManager:
    """Manages checkpoints for sessions with file-level support"""
    
    def __init__(self, reverie_dir: Path):
        self.reverie_dir = reverie_dir
        self.checkpoints_dir = reverie_dir / 'checkpoints'
        self.file_checkpoints_dir = reverie_dir / 'file_checkpoints'
        self.checkpoints_dir.mkdir(parents=True, exist_ok=True)
        self.file_checkpoints_dir.mkdir(parents=True, exist_ok=True)
    
    def create_checkpoint(
        self,
        session_id: str,
        messages: List[Dict],
        description: str = ""
    ) -> Checkpoint:
        """Create a checkpoint for a session"""
        import uuid
        
        checkpoint_id = str(uuid.uuid4())[:8]
        now = datetime.now().isoformat()
        
        checkpoint = Checkpoint(
            id=checkpoint_id,
            session_id=session_id,
            description=description or f"Checkpoint at {datetime.now().strftime('%H:%M:%S')}",
            created_at=now,
            message_count=len(messages)
        )
        
        # Save checkpoint data
        checkpoint_dir = self.checkpoints_dir / checkpoint_id
        checkpoint_dir.mkdir(exist_ok=True)
        
        # Save metadata
        with open(checkpoint_dir / 'meta.json', 'w', encoding='utf-8') as f:
            json.dump(checkpoint.to_dict(), f, indent=2)
        
        # Save messages
        with open(checkpoint_dir / 'messages.json', 'w', encoding='utf-8') as f:
            json.dump(messages, f, indent=2)
        
        return checkpoint
    
    def create_file_checkpoint(
        self,
        file_path: str,
        content: str,
        description: str = ""
    ) -> FileCheckpoint:
        """
        Create a checkpoint for a single file.
        
        This is called automatically before any file modification.
        """
        import uuid
        
        # Generate checkpoint ID based on file path and content hash
        content_hash = hashlib.md5(content.encode()).hexdigest()[:8]
        checkpoint_id = f"{Path(file_path).name}_{content_hash}_{str(uuid.uuid4())[:4]}"
        
        now = datetime.now().isoformat()
        
        file_checkpoint = FileCheckpoint(
            file_path=file_path,
            checkpoint_id=checkpoint_id,
            content=content,
            created_at=now,
            description=description or f"File checkpoint for {file_path}"
        )
        
        # Save file checkpoint
        checkpoint_file = self.file_checkpoints_dir / f"{checkpoint_id}.json"
        with open(checkpoint_file, 'w', encoding='utf-8') as f:
            json.dump(file_checkpoint.to_dict(), f, indent=2)
        
        return file_checkpoint
    
    def restore_file_checkpoint(
        self,
        checkpoint_id: str,
        target_path: Optional[Path] = None
    ) -> Optional[str]:
        """
        Restore a file from its checkpoint.
        
        Args:
            checkpoint_id: The file checkpoint ID
            target_path: Where to restore the file (default: original location)
        
        Returns:
            The restored content, or None if checkpoint not found
        """
        checkpoint_file = self.file_checkpoints_dir / f"{checkpoint_id}.json"
        
        if not checkpoint_file.exists():
            return None
        
        try:
            with open(checkpoint_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            file_checkpoint = FileCheckpoint.from_dict(data)
            
            # If target_path is specified, restore there
            if target_path:
                with open(target_path, 'w', encoding='utf-8') as f:
                    f.write(file_checkpoint.content)
            else:
                # Restore to original location
                original_path = Path(file_checkpoint.file_path)
                original_path.parent.mkdir(parents=True, exist_ok=True)
                with open(original_path, 'w', encoding='utf-8') as f:
                    f.write(file_checkpoint.content)
            
            return file_checkpoint.content
        
        except Exception as e:
            print(f"Error restoring file checkpoint: {e}")
            return None
    
    def list_file_checkpoints(
        self,
        file_path: Optional[str] = None
    ) -> List[FileCheckpoint]:
        """
        List file checkpoints.
        
        Args:
            file_path: Filter by specific file path (optional)
        
        Returns:
            List of file checkpoints, sorted by creation time (newest first)
        """
        checkpoints = []
        
        for checkpoint_file in self.file_checkpoints_dir.glob('*.json'):
            try:
                with open(checkpoint_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                
                file_checkpoint = FileCheckpoint.from_dict(data)
                
                # Filter by file path if specified
                if file_path and file_checkpoint.file_path != file_path:
                    continue
                
                checkpoints.append(file_checkpoint)
            
            except Exception:
                continue
        
        # Sort by creation time (newest first)
        checkpoints.sort(key=lambda c: c.created_at, reverse=True)
        
        return checkpoints
    
    def list_checkpoints(self, session_id: Optional[str] = None) -> List[Checkpoint]:
        """List checkpoints, optionally filtered by session"""
        checkpoints = []
        
        for cp_dir in self.checkpoints_dir.iterdir():
            if not cp_dir.is_dir():
                continue
            
            meta_path = cp_dir / 'meta.json'
            if not meta_path.exists():
                continue
            
            try:
                with open(meta_path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                
                if session_id and data.get('session_id') != session_id:
                    continue
                
                checkpoints.append(Checkpoint(
                    id=data['id'],
                    session_id=data['session_id'],
                    description=data['description'],
                    created_at=data['created_at'],
                    message_count=data['message_count'],
                    file_checkpoints=data.get('file_checkpoints', [])
                ))
            except Exception:
                continue
        
        checkpoints.sort(key=lambda c: c.created_at, reverse=True)
        return checkpoints
    
    def restore_checkpoint(self, checkpoint_id: str) -> Optional[List[Dict]]:
        """Restore messages from a checkpoint"""
        checkpoint_dir = self.checkpoints_dir / checkpoint_id
        messages_path = checkpoint_dir / 'messages.json'
        
        if not messages_path.exists():
            return None
        
        try:
            with open(messages_path, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception:
            return None
    
    def delete_checkpoint(self, checkpoint_id: str) -> bool:
        """Delete a checkpoint"""
        checkpoint_dir = self.checkpoints_dir / checkpoint_id
        
        if checkpoint_dir.exists():
            shutil.rmtree(checkpoint_dir)
            return True
        return False
    
    def delete_file_checkpoint(self, checkpoint_id: str) -> bool:
        """Delete a file checkpoint"""
        checkpoint_file = self.file_checkpoints_dir / f"{checkpoint_id}.json"
        
        if checkpoint_file.exists():
            checkpoint_file.unlink()
            return True
        return False
    
    def cleanup_old_checkpoints(self, days_old: int = 7) -> int:
        """Clean up checkpoints older than specified days"""
        import time
        cutoff_time = datetime.now().timestamp() - (days_old * 24 * 3600)
        removed = 0
        
        # Clean up session checkpoints
        for cp_dir in self.checkpoints_dir.iterdir():
            if not cp_dir.is_dir():
                continue
            
            meta_path = cp_dir / 'meta.json'
            if not meta_path.exists():
                continue
            
            try:
                with open(meta_path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                
                created_at = datetime.fromisoformat(data['created_at']).timestamp()
                
                if created_at < cutoff_time:
                    shutil.rmtree(cp_dir)
                    removed += 1
            
            except Exception:
                continue
        
        # Clean up file checkpoints
        for checkpoint_file in self.file_checkpoints_dir.glob('*.json'):
            try:
                with open(checkpoint_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                
                created_at = datetime.fromisoformat(data['created_at']).timestamp()
                
                if created_at < cutoff_time:
                    checkpoint_file.unlink()
                    removed += 1
            
            except Exception:
                continue
        
        return removed
