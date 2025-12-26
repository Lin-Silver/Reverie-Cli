"""
Session Manager - Handle conversation sessions

Provides:
- Session creation and persistence
- Session listing and selection
- History management
"""

from pathlib import Path
from typing import List, Dict, Optional
from dataclasses import dataclass, field
from datetime import datetime
import json
import uuid


@dataclass
class Session:
    """A conversation session"""
    id: str
    name: str
    created_at: str
    updated_at: str
    messages: List[Dict] = field(default_factory=list)
    metadata: Dict = field(default_factory=dict)
    
    def to_dict(self) -> dict:
        return {
            'id': self.id,
            'name': self.name,
            'created_at': self.created_at,
            'updated_at': self.updated_at,
            'messages': self.messages,
            'metadata': self.metadata
        }
    
    @classmethod
    def from_dict(cls, data: dict) -> 'Session':
        return cls(
            id=data['id'],
            name=data['name'],
            created_at=data['created_at'],
            updated_at=data['updated_at'],
            messages=data.get('messages', []),
            metadata=data.get('metadata', {})
        )


@dataclass
class SessionInfo:
    """Brief session info for listing"""
    id: str
    name: str
    created_at: str
    updated_at: str
    message_count: int


class SessionManager:
    """
    Manages conversation sessions, including persistence,
    archiving, and checkpointing.
    """
    
    def __init__(self, base_dir: Path):
        self.base_dir = Path(base_dir)
        self.sessions_dir = self.base_dir / 'sessions'
        self.archives_dir = self.base_dir / 'archives'
        self.checkpoints_dir = self.base_dir / 'checkpoints'
        
        self._ensure_dirs()
        self.current_session: Optional[Session] = None
    
    def _ensure_dirs(self) -> None:
        """Create necessary directories"""
        self.sessions_dir.mkdir(parents=True, exist_ok=True)
        self.archives_dir.mkdir(parents=True, exist_ok=True)
        self.checkpoints_dir.mkdir(parents=True, exist_ok=True)
    
    def create_session(self, name: Optional[str] = None) -> Session:
        """Create a new session"""
        session_id = str(uuid.uuid4())[:8]
        now = datetime.now().isoformat()
        
        if name is None:
            name = f"Session {datetime.now().strftime('%Y-%m-%d %H:%M')}"
        
        session = Session(
            id=session_id,
            name=name,
            created_at=now,
            updated_at=now
        )
        
        self._current_session = session
        self.save_session(session)
        
        return session
    
    def save_session(self, session: Optional[Session] = None) -> None:
        """Save session to file"""
        session = session or self._current_session
        if session is None:
            return
        
        session.updated_at = datetime.now().isoformat()
        
        session_path = self.sessions_dir / f"{session.id}.json"
        with open(session_path, 'w', encoding='utf-8') as f:
            json.dump(session.to_dict(), f, indent=2, ensure_ascii=False)
    
    def load_session(self, session_id: str) -> Optional[Session]:
        """Load a session by ID"""
        session_path = self.sessions_dir / f"{session_id}.json"
        
        if not session_path.exists():
            return None
        
        try:
            with open(session_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            session = Session.from_dict(data)
            self._current_session = session
            return session
        except Exception:
            return None
    
    def delete_session(self, session_id: str) -> bool:
        """Delete a session"""
        session_path = self.sessions_dir / f"{session_id}.json"
        
        if session_path.exists():
            session_path.unlink()
            
            if self._current_session and self._current_session.id == session_id:
                self._current_session = None
            
            return True
        return False
    
    def list_sessions(self) -> List[SessionInfo]:
        """List all sessions"""
        sessions = []
        
        for session_file in self.sessions_dir.glob('*.json'):
            try:
                with open(session_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                
                sessions.append(SessionInfo(
                    id=data['id'],
                    name=data['name'],
                    created_at=data['created_at'],
                    updated_at=data['updated_at'],
                    message_count=len(data.get('messages', []))
                ))
            except Exception:
                continue
        
        # Sort by updated_at descending
        sessions.sort(key=lambda s: s.updated_at, reverse=True)
        
        return sessions
    
    def get_current_session(self) -> Optional[Session]:
        """Get the current session"""
        return self._current_session
    
    def set_current_session(self, session: Session) -> None:
        """Set the current session"""
        self._current_session = session
    
    def update_messages(self, messages: List[Dict]) -> None:
        """Update messages in current session"""
        if self._current_session:
            self._current_session.messages = messages
            self.save_session()
    
    def add_message(self, message: Dict) -> None:
        """Add a message to current session"""
        if self._current_session:
            self._current_session.messages.append(message)
            self.save_session()
