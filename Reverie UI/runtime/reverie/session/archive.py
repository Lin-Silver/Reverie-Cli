"""
Archive Manager - Long-term session storage
"""

from pathlib import Path
from typing import List, Optional
from dataclasses import dataclass
from datetime import datetime
import json
import shutil


@dataclass
class Archive:
    """An archived session"""
    id: str
    original_session_id: str
    name: str
    archived_at: str
    message_count: int


class ArchiveManager:
    """Manages archived sessions"""
    
    def __init__(self, reverie_dir: Path):
        self.reverie_dir = reverie_dir
        self.archives_dir = reverie_dir / 'archives'
        self.archives_dir.mkdir(parents=True, exist_ok=True)
    
    def archive_session(self, session_path: Path, name: str) -> Optional[Archive]:
        """Archive a session"""
        import uuid
        
        if not session_path.exists():
            return None
        
        archive_id = str(uuid.uuid4())[:8]
        now = datetime.now().isoformat()
        
        # Copy session file to archives
        archive_path = self.archives_dir / f"{archive_id}.json"
        shutil.copy(session_path, archive_path)
        
        # Load and update with archive metadata
        with open(archive_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        data['archived_at'] = now
        data['archive_id'] = archive_id
        
        with open(archive_path, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2)
        
        return Archive(
            id=archive_id,
            original_session_id=data['id'],
            name=name or data.get('name', 'Unnamed'),
            archived_at=now,
            message_count=len(data.get('messages', []))
        )
    
    def list_archives(self) -> List[Archive]:
        """List all archives"""
        archives = []
        
        for archive_file in self.archives_dir.glob('*.json'):
            try:
                with open(archive_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                
                archives.append(Archive(
                    id=data.get('archive_id', archive_file.stem),
                    original_session_id=data.get('id', ''),
                    name=data.get('name', 'Unnamed'),
                    archived_at=data.get('archived_at', ''),
                    message_count=len(data.get('messages', []))
                ))
            except Exception:
                continue
        
        archives.sort(key=lambda a: a.archived_at, reverse=True)
        return archives
    
    def restore_archive(self, archive_id: str) -> Optional[dict]:
        """Restore an archived session"""
        archive_path = self.archives_dir / f"{archive_id}.json"
        
        if not archive_path.exists():
            return None
        
        try:
            with open(archive_path, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception:
            return None
    
    def delete_archive(self, archive_id: str) -> bool:
        """Delete an archive"""
        archive_path = self.archives_dir / f"{archive_id}.json"
        
        if archive_path.exists():
            archive_path.unlink()
            return True
        return False
