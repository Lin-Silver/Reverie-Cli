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
    
    Enhanced with:
    - Automatic session rotation at 80% token threshold
    - Working memory injection for session continuity
    - Integration with snapshot and memory systems
    """
    
    def __init__(self, base_dir: Path, snapshot_manager=None, memory_indexer=None):
        self.base_dir = Path(base_dir)
        self.sessions_dir = self.base_dir / 'sessions'
        self.archives_dir = self.base_dir / 'archives'
        self.checkpoints_dir = self.base_dir / 'checkpoints'
        
        self._ensure_dirs()
        self._current_session: Optional[Session] = None
        
        # Enhanced features
        self.snapshot_manager = snapshot_manager
        self.memory_indexer = memory_indexer
        self.rotation_threshold = 0.8  # 80% token usage triggers rotation
    
    @property
    def current_session(self) -> Optional[Session]:
        """Get the current session"""
        return self._current_session
    
    def _ensure_dirs(self) -> None:
        """Create necessary directories"""
        self.sessions_dir.mkdir(parents=True, exist_ok=True)
        self.archives_dir.mkdir(parents=True, exist_ok=True)
        self.checkpoints_dir.mkdir(parents=True, exist_ok=True)
    
    def create_session(self, name: Optional[str] = None) -> Session:
        """Create a new session"""
        # Use timestamp as session ID (YYYYMMDD_HHMMSS format)
        now = datetime.now()
        session_id = now.strftime('%Y%m%d_%H%M%S')
        iso_time = now.isoformat()
        
        if name is None:
            name = f"Session {now.strftime('%Y-%m-%d %H:%M:%S')}"
        
        session = Session(
            id=session_id,
            name=name,
            created_at=iso_time,
            updated_at=iso_time
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
    
    def check_rotation_needed(
        self,
        current_tokens: int,
        max_tokens: int
    ) -> bool:
        """
        Check if session rotation is needed based on token usage.
        
        Args:
            current_tokens: Current token count
            max_tokens: Maximum context tokens for the model
        
        Returns:
            True if rotation is needed (>= 80% threshold)
        """
        if max_tokens <= 0:
            return False
        
        usage_ratio = current_tokens / max_tokens
        return usage_ratio >= self.rotation_threshold
    
    def rotate_session(
        self,
        working_memory: str,
        reason: str = "Token threshold reached"
    ) -> Session:
        """
        Rotate to a new session with working memory injection.
        
        Args:
            working_memory: Compressed summary from previous session
            reason: Reason for rotation
        
        Returns:
            New session object
        """
        # Save current session
        if self._current_session:
            self.save_session()
            
            # Index the completed session for persistent memory
            if self.memory_indexer:
                self.memory_indexer.index_session(self._current_session.id)
        
        # Create new session
        now = datetime.now()
        # Use microseconds to ensure uniqueness
        session_id = now.strftime('%Y%m%d_%H%M%S') + f"_{now.microsecond:06d}"
        iso_time = now.isoformat()
        
        new_session = Session(
            id=session_id,
            name=f"Session {now.strftime('%Y-%m-%d %H:%M:%S')}",
            created_at=iso_time,
            updated_at=iso_time,
            metadata={
                'rotated_from': self._current_session.id if self._current_session else None,
                'rotation_reason': reason,
                'has_working_memory': bool(working_memory)
            }
        )
        
        # Inject working memory as first system message
        if working_memory:
            new_session.messages.append({
                'role': 'system',
                'content': f"[WORKING MEMORY - Previous Session Context]\n{working_memory}\n[END WORKING MEMORY]"
            })
        
        self._current_session = new_session
        self.save_session(new_session)
        
        return new_session
    
    def get_working_memory_summary(self) -> str:
        """
        Get working memory summary from current session.
        
        This should be called before rotation to generate a compressed
        summary of the current session for injection into the new session.
        
        Returns:
            Compressed summary string
        """
        if not self._current_session or not self._current_session.messages:
            return ""
        
        # Simple summary: last few messages + key information
        messages = self._current_session.messages
        
        # Extract key information
        user_questions = [m for m in messages if m.get('role') == 'user']
        tool_calls = []
        
        for m in messages:
            if m.get('role') == 'assistant' and 'tool_calls' in m:
                for tc in m['tool_calls']:
                    if isinstance(tc, dict):
                        func = tc.get('function', {})
                        if isinstance(func, dict):
                            tool_calls.append(func.get('name', ''))
        
        # Build summary
        summary_parts = []
        
        if user_questions:
            summary_parts.append(f"Recent topics: {len(user_questions)} user questions")
            # Include last 2 questions
            for q in user_questions[-2:]:
                content = q.get('content', '')[:200]
                summary_parts.append(f"- {content}")
        
        if tool_calls:
            unique_tools = list(set(tool_calls))
            summary_parts.append(f"Tools used: {', '.join(unique_tools[:10])}")
        
        return '\n'.join(summary_parts)
