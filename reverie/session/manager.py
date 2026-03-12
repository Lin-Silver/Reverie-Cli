"""
Session Manager - Handle conversation sessions

Provides:
- Session creation and persistence
- Session listing and selection
- History management
"""

from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
from dataclasses import dataclass, field
from datetime import datetime
import hashlib
import json


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

    def __init__(
        self,
        base_dir: Path,
        project_root: Optional[Path] = None,
        snapshot_manager=None,
        memory_indexer=None
    ):
        self.base_dir = Path(base_dir).resolve()
        self.project_root = Path(project_root).resolve() if project_root else None
        self.sessions_dir = self.base_dir / 'sessions'
        self.archives_dir = self.base_dir / 'archives'
        self.checkpoints_dir = self.base_dir / 'checkpoints'
        self.state_path = self.base_dir / 'session_state.json'

        scope_source = self.project_root or self.base_dir
        self.workspace_path = str(scope_source)
        self.workspace_id = self._build_workspace_id(scope_source)

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

    def _normalize_path(self, path_value: Any) -> str:
        raw = str(path_value or '').strip()
        if not raw:
            return ''

        try:
            normalized = str(Path(raw).resolve())
        except Exception:
            normalized = raw

        return normalized.replace('\\', '/').rstrip('/').lower()

    def _build_workspace_id(self, path_value: Any) -> str:
        normalized = self._normalize_path(path_value)
        if not normalized:
            return ''
        return hashlib.sha1(normalized.encode('utf-8')).hexdigest()[:16]

    def _scope_metadata(self) -> Dict[str, str]:
        metadata: Dict[str, str] = {}
        if self.workspace_id:
            metadata['workspace_id'] = self.workspace_id
        if self.workspace_path:
            metadata['workspace_path'] = self.workspace_path
        return metadata

    def _merge_scope_metadata(self, metadata: Optional[Dict]) -> Dict:
        merged = dict(metadata or {})
        merged.update(self._scope_metadata())
        return merged

    def _belongs_to_workspace(self, data: Dict) -> bool:
        metadata = data.get('metadata') or {}

        session_workspace_id = str(metadata.get('workspace_id') or '').strip()
        if session_workspace_id:
            return session_workspace_id == self.workspace_id

        session_workspace_path = str(metadata.get('workspace_path') or '').strip()
        if session_workspace_path:
            return self._normalize_path(session_workspace_path) == self._normalize_path(self.workspace_path)

        return True

    def _write_json_atomic(self, target_path: Path, payload: Dict) -> None:
        temp_path = target_path.with_name(f"{target_path.name}.tmp")
        with open(temp_path, 'w', encoding='utf-8') as f:
            json.dump(payload, f, indent=2, ensure_ascii=False)
        temp_path.replace(target_path)

    def _write_session(self, session: Session, *, touch_updated_at: bool = True) -> None:
        if touch_updated_at:
            session.updated_at = datetime.now().isoformat()

        session.metadata = self._merge_scope_metadata(session.metadata)
        session_path = self.sessions_dir / f"{session.id}.json"
        self._write_json_atomic(session_path, session.to_dict())

    def _save_state(self, session_id: Optional[str]) -> None:
        if not session_id:
            if self.state_path.exists():
                self.state_path.unlink()
            return

        state = {
            'current_session_id': session_id,
            'workspace_id': self.workspace_id,
            'workspace_path': self.workspace_path,
            'updated_at': datetime.now().isoformat()
        }
        self._write_json_atomic(self.state_path, state)

    def _load_state(self) -> Dict[str, Any]:
        if not self.state_path.exists():
            return {}

        try:
            with open(self.state_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
        except Exception:
            return {}

        if not isinstance(data, dict):
            return {}

        state_workspace_id = str(data.get('workspace_id') or '').strip()
        if state_workspace_id and state_workspace_id != self.workspace_id:
            return {}

        state_workspace_path = str(data.get('workspace_path') or '').strip()
        if state_workspace_path and self._normalize_path(state_workspace_path) != self._normalize_path(self.workspace_path):
            return {}

        return data

    def _generate_session_id(self) -> str:
        while True:
            session_id = datetime.now().strftime('%Y%m%d_%H%M%S_%f')
            if not (self.sessions_dir / f"{session_id}.json").exists():
                return session_id

    def create_session(self, name: Optional[str] = None) -> Session:
        """Create a new session"""
        if self._current_session:
            self.save_session(self._current_session)

        now = datetime.now()
        session_id = self._generate_session_id()
        iso_time = now.isoformat()

        if name is None:
            name = f"Session {now.strftime('%Y-%m-%d %H:%M:%S')}"

        session = Session(
            id=session_id,
            name=name,
            created_at=iso_time,
            updated_at=iso_time,
            metadata=self._scope_metadata()
        )

        self._current_session = session
        self._write_session(session, touch_updated_at=False)
        self._save_state(session.id)
        return session

    def save_session(self, session: Optional[Session] = None) -> None:
        """Save session to file"""
        session = session or self._current_session
        if session is None:
            return

        self._write_session(session, touch_updated_at=True)

        if self._current_session and self._current_session.id == session.id:
            self._save_state(session.id)

    def load_session(self, session_id: str) -> Optional[Session]:
        """Load a session by ID"""
        session_path = self.sessions_dir / f"{session_id}.json"

        if not session_path.exists():
            return None

        try:
            with open(session_path, 'r', encoding='utf-8') as f:
                data = json.load(f)

            if not isinstance(data, dict) or not self._belongs_to_workspace(data):
                return None

            session = Session.from_dict(data)
            original_metadata = dict(session.metadata or {})
            session.metadata = self._merge_scope_metadata(session.metadata)

            self._current_session = session
            self._save_state(session.id)

            if session.metadata != original_metadata:
                self._write_session(session, touch_updated_at=False)

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
                self._save_state(None)

            return True
        return False

    def list_sessions(self) -> List[SessionInfo]:
        """List sessions for the current workspace"""
        sessions: List[SessionInfo] = []

        for session_file in self.sessions_dir.glob('*.json'):
            try:
                with open(session_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)

                if not isinstance(data, dict) or not self._belongs_to_workspace(data):
                    continue

                sessions.append(SessionInfo(
                    id=data['id'],
                    name=data['name'],
                    created_at=data['created_at'],
                    updated_at=data['updated_at'],
                    message_count=len(data.get('messages', []))
                ))
            except Exception:
                continue

        sessions.sort(key=lambda s: s.updated_at, reverse=True)
        return sessions

    def restore_last_session(self) -> Optional[Session]:
        """Restore the last active session for the current workspace."""
        if self._current_session:
            return self._current_session

        state = self._load_state()
        session_id = str(state.get('current_session_id') or '').strip()
        if session_id:
            session = self.load_session(session_id)
            if session:
                return session

        sessions = self.list_sessions()
        if sessions:
            return self.load_session(sessions[0].id)

        return None

    def ensure_session(self, name: Optional[str] = None) -> Tuple[Session, bool]:
        """Restore the last active session or create a new one."""
        session = self.restore_last_session()
        if session:
            return session, True
        return self.create_session(name), False

    def get_current_session(self) -> Optional[Session]:
        """Get the current session"""
        return self._current_session

    def set_current_session(self, session: Session) -> None:
        """Set the current session"""
        session.metadata = self._merge_scope_metadata(session.metadata)
        self._current_session = session
        self._save_state(session.id)

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
        if self._current_session:
            self.save_session()

            if self.memory_indexer:
                self.memory_indexer.index_session(self._current_session.id)

        now = datetime.now()
        session_id = self._generate_session_id()
        iso_time = now.isoformat()

        new_session = Session(
            id=session_id,
            name=f"Session {now.strftime('%Y-%m-%d %H:%M:%S')}",
            created_at=iso_time,
            updated_at=iso_time,
            metadata=self._merge_scope_metadata({
                'rotated_from': self._current_session.id if self._current_session else None,
                'rotation_reason': reason,
                'has_working_memory': bool(working_memory)
            })
        )

        if working_memory:
            new_session.messages.append({
                'role': 'system',
                'content': f"[WORKING MEMORY - Previous Session Context]\n{working_memory}\n[END WORKING MEMORY]"
            })

        self._current_session = new_session
        self._write_session(new_session, touch_updated_at=False)
        self._save_state(new_session.id)
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
        from ..context_engine.compressor import build_memory_digest

        return build_memory_digest(self._current_session.messages)
