"""
Checkpoint Manager - Create and restore checkpoints

Checkpoints are automatic snapshots created before major operations.
"""

from pathlib import Path
from typing import List, Dict, Optional
from dataclasses import dataclass
from datetime import datetime
import json
import shutil


@dataclass
class Checkpoint:
    """A checkpoint snapshot"""
    id: str
    session_id: str
    description: str
    created_at: str
    message_count: int
    
    def to_dict(self) -> dict:
        return {
            'id': self.id,
            'session_id': self.session_id,
            'description': self.description,
            'created_at': self.created_at,
            'message_count': self.message_count
        }


class CheckpointManager:
    """Manages checkpoints for sessions"""
    
    def __init__(self, reverie_dir: Path):
        self.reverie_dir = reverie_dir
        self.checkpoints_dir = reverie_dir / 'checkpoints'
        self.checkpoints_dir.mkdir(parents=True, exist_ok=True)
    
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
                    message_count=data['message_count']
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
