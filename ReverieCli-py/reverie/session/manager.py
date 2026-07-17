"""
Session Manager - Handle conversation sessions

Provides:
- Session creation and persistence
- Session listing and selection
- History management
"""

from datetime import datetime
import hashlib
import json
import os
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from ..diagnostics import report_suppressed_exception

SESSION_INDEX_FILENAME = 'session_index.json'
GENERATED_SESSION_NAME_PREFIXES = ('Session ', 'Prompt Run ', 'New Conversation')


def session_title_from_prompt(prompt: Any, max_length: int = 64) -> str:
    """Build a compact history title from the first meaningful prompt line."""
    text = ' '.join(str(prompt or '').split()).strip()
    if not text:
        return ''
    limit = max(12, int(max_length or 64))
    return text if len(text) <= limit else f"{text[: limit - 1].rstrip()}…"


def is_generated_session_name(name: Any) -> bool:
    candidate = str(name or '').strip()
    return not candidate or candidate.startswith(GENERATED_SESSION_NAME_PREFIXES)


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
    - Integration with persistent memory systems
    """

    def __init__(
        self,
        base_dir: Path,
        project_root: Optional[Path] = None,
        memory_indexer=None,
        always_new_session: bool = False,
        refresh_memory_index_on_save: bool = False,
    ):
        self.base_dir = Path(base_dir).resolve()
        self.project_root = Path(project_root).resolve() if project_root else None
        self.sessions_dir = self.base_dir / 'sessions'
        self.archives_dir = self.base_dir / 'archives'
        self.checkpoints_dir = self.base_dir / 'checkpoints'
        self.transcripts_dir = self.base_dir / 'full_transcripts'
        self.handoffs_dir = self.base_dir / 'session_handoffs'
        self.state_path = self.base_dir / 'session_state.json'
        self.session_index_path = self.base_dir / SESSION_INDEX_FILENAME

        scope_source = self.project_root or self.base_dir
        self.workspace_path = str(scope_source)
        self.workspace_id = self._build_workspace_id(scope_source)

        self._ensure_dirs()
        self._current_session: Optional[Session] = None
        self._session_index: Dict[str, Dict[str, Any]] = self._load_session_index()

        # Enhanced features
        self.memory_indexer = memory_indexer
        self.always_new_session = bool(always_new_session)
        self.refresh_memory_index_on_save = bool(refresh_memory_index_on_save)
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
        self.transcripts_dir.mkdir(parents=True, exist_ok=True)
        self.handoffs_dir.mkdir(parents=True, exist_ok=True)

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
        target_path = Path(target_path)
        target_path.parent.mkdir(parents=True, exist_ok=True)

        temp_path: Optional[Path] = None
        try:
            with tempfile.NamedTemporaryFile(
                mode='w',
                encoding='utf-8',
                dir=str(target_path.parent),
                prefix=f".{target_path.name}.",
                suffix=".tmp",
                delete=False,
            ) as f:
                temp_path = Path(f.name)
                json.dump(payload, f, indent=2, ensure_ascii=False)
                f.flush()
                os.fsync(f.fileno())

            temp_path.replace(target_path)

            # Best-effort directory sync so the rename is durable on POSIX filesystems.
            try:
                dir_fd = os.open(str(target_path.parent), os.O_RDONLY)
            except OSError:
                return
            try:
                os.fsync(dir_fd)
            finally:
                os.close(dir_fd)
        except Exception:
            if temp_path is not None:
                try:
                    temp_path.unlink(missing_ok=True)
                except OSError:
                    report_suppressed_exception("remove failed session-write temporary file")
            raise

    def _load_session_index(self) -> Dict[str, Dict[str, Any]]:
        if not self.session_index_path.exists():
            return {}

        try:
            with open(self.session_index_path, 'r', encoding='utf-8') as f:
                payload = json.load(f)
        except Exception:
            return {}

        raw_sessions = payload.get('sessions') if isinstance(payload, dict) else {}
        if not isinstance(raw_sessions, dict):
            return {}

        index: Dict[str, Dict[str, Any]] = {}
        for session_id, entry in raw_sessions.items():
            if not isinstance(entry, dict):
                continue
            session_entry = {
                'id': str(entry.get('id') or session_id),
                'name': str(entry.get('name') or session_id),
                'created_at': str(entry.get('created_at') or ''),
                'updated_at': str(entry.get('updated_at') or ''),
                'message_count': int(entry.get('message_count') or 0),
                'workspace_id': str(entry.get('workspace_id') or ''),
                'workspace_path': str(entry.get('workspace_path') or ''),
            }
            if self._belongs_to_workspace({'metadata': session_entry}):
                index[str(session_entry['id'])] = session_entry
        return index

    def _save_session_index(self) -> None:
        payload = {
            'workspace_id': self.workspace_id,
            'workspace_path': self.workspace_path,
            'updated_at': datetime.now().isoformat(),
            'sessions': self._session_index,
        }
        self._write_json_atomic(self.session_index_path, payload)

    def _session_index_entry(self, session: Session) -> Dict[str, Any]:
        metadata = self._merge_scope_metadata(session.metadata)
        return {
            'id': session.id,
            'name': session.name,
            'created_at': session.created_at,
            'updated_at': session.updated_at,
            'message_count': len(session.messages or []),
            'workspace_id': str(metadata.get('workspace_id') or ''),
            'workspace_path': str(metadata.get('workspace_path') or ''),
        }

    def _rebuild_session_index(self) -> None:
        rebuilt: Dict[str, Dict[str, Any]] = {}
        for session_file in self.sessions_dir.glob('*.json'):
            try:
                with open(session_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
            except Exception:
                continue

            if not isinstance(data, dict) or not self._belongs_to_workspace(data):
                continue

            session_id = str(data.get('id') or session_file.stem)
            rebuilt[session_id] = {
                'id': session_id,
                'name': str(data.get('name') or session_id),
                'created_at': str(data.get('created_at') or ''),
                'updated_at': str(data.get('updated_at') or ''),
                'message_count': len(data.get('messages', []) or []),
                'workspace_id': str((data.get('metadata') or {}).get('workspace_id') or self.workspace_id),
                'workspace_path': str((data.get('metadata') or {}).get('workspace_path') or self.workspace_path),
            }

        self._session_index = rebuilt
        self._save_session_index()

    def _ensure_session_index(self) -> None:
        expected_count = sum(1 for _ in self.sessions_dir.glob('*.json'))
        if self._session_index and len(self._session_index) == expected_count:
            return
        if not self.session_index_path.exists() and expected_count == 0:
            self._session_index = {}
            return
        self._rebuild_session_index()

    def refresh_generated_session_names(self) -> int:
        """Upgrade timestamp-only legacy names from their first user prompt."""
        self._ensure_session_index()
        changed = 0
        for session_id, entry in list(self._session_index.items()):
            if not is_generated_session_name(entry.get('name')):
                continue
            session_path = self.sessions_dir / f"{session_id}.json"
            try:
                data = json.loads(session_path.read_text(encoding='utf-8'))
            except Exception:
                continue
            if not isinstance(data, dict) or not self._belongs_to_workspace(data):
                continue
            first_prompt = next(
                (
                    message.get('content')
                    for message in (data.get('messages', []) or [])
                    if isinstance(message, dict)
                    and str(message.get('role') or '').lower() == 'user'
                    and isinstance(message.get('content'), str)
                    and str(message.get('content') or '').strip()
                ),
                '',
            )
            title = session_title_from_prompt(first_prompt)
            if not title or title == str(data.get('name') or ''):
                continue
            data['name'] = title
            self._write_json_atomic(session_path, data)
            entry['name'] = title
            changed += 1
            if self._current_session and self._current_session.id == session_id:
                self._current_session.name = title
        if changed:
            self._save_session_index()
        return changed

    def _write_session(self, session: Session, *, touch_updated_at: bool = True) -> None:
        if touch_updated_at:
            session.updated_at = datetime.now().isoformat()

        session.metadata = self._merge_scope_metadata(session.metadata)
        session_path = self.sessions_dir / f"{session.id}.json"
        self._write_json_atomic(session_path, session.to_dict())
        self._session_index[session.id] = self._session_index_entry(session)
        self._save_session_index()

    def _archive_current_transcript_before_compaction(
        self,
        *,
        replacement_messages: List[Dict],
        reason: str = "message history compaction",
    ) -> str:
        """Preserve the full session transcript before replacing it with a shorter history."""
        session = self._current_session
        if not session:
            return ""

        current_messages = list(session.messages or [])
        if not current_messages:
            return ""
        if len(replacement_messages or []) >= len(current_messages):
            return ""

        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S_%f')
        target_path = self.transcripts_dir / f"full_transcript_{session.id}_{timestamp}.json"
        payload = {
            'id': session.id,
            'name': session.name,
            'created_at': session.created_at,
            'updated_at': session.updated_at,
            'archived_at': datetime.now().isoformat(),
            'reason': reason,
            'workspace_id': self.workspace_id,
            'workspace_path': self.workspace_path,
            'original_message_count': len(current_messages),
            'replacement_message_count': len(replacement_messages or []),
            'metadata': dict(session.metadata or {}),
            'messages': current_messages,
        }

        try:
            self._write_json_atomic(target_path, payload)
        except Exception:
            return ""

        archives = list((session.metadata or {}).get('full_transcript_archives', []) or [])
        archives.append(
            {
                'path': str(target_path),
                'archived_at': payload['archived_at'],
                'reason': reason,
                'message_count': len(current_messages),
            }
        )
        session.metadata['full_transcript_archives'] = archives[-20:]
        return str(target_path)

    def _refresh_memory_index_for_session(self, session_id: str) -> None:
        """Refresh the memory index for one session when the mode opts into live indexing."""
        if not self.refresh_memory_index_on_save or not self.memory_indexer:
            return
        try:
            self.memory_indexer.refresh_session(session_id)
        except Exception:
            report_suppressed_exception("refresh session memory index")

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
        self._refresh_memory_index_for_session(session.id)
        return session

    def save_session(self, session: Optional[Session] = None) -> None:
        """Save session to file"""
        session = session or self._current_session
        if session is None:
            return

        self._write_session(session, touch_updated_at=True)
        self._refresh_memory_index_for_session(session.id)

        if self._current_session and self._current_session.id == session.id:
            self._save_state(session.id)

    def rename_current_session_from_prompt(self, prompt: Any) -> bool:
        """Name a newly-created/default session after its first user prompt."""
        session = self._current_session
        if session is None or not is_generated_session_name(session.name):
            return False
        title = session_title_from_prompt(prompt)
        if not title:
            return False
        session.name = title
        self.save_session(session)
        return True

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
            refreshed_index_entry = self._session_index_entry(session)

            self._current_session = session
            self._save_state(session.id)
            if self._session_index.get(session.id) != refreshed_index_entry:
                self._session_index[session.id] = refreshed_index_entry
                self._save_session_index()

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
            self._session_index.pop(session_id, None)
            self._save_session_index()
            self._refresh_memory_index_for_session(session_id)

            if self._current_session and self._current_session.id == session_id:
                self._current_session = None
                self._save_state(None)

            return True
        return False

    def list_sessions(self) -> List[SessionInfo]:
        """List sessions for the current workspace"""
        self._ensure_session_index()
        sessions: List[SessionInfo] = []
        for entry in self._session_index.values():
            sessions.append(SessionInfo(
                id=str(entry.get('id') or ''),
                name=str(entry.get('name') or ''),
                created_at=str(entry.get('created_at') or ''),
                updated_at=str(entry.get('updated_at') or ''),
                message_count=int(entry.get('message_count') or 0),
            ))

        sessions.sort(key=lambda s: s.updated_at, reverse=True)
        return sessions

    def restore_last_session(self) -> Optional[Session]:
        """Restore the last active session for the current workspace."""
        if self._current_session:
            return self._current_session

        if self.always_new_session:
            return None

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
        if self._current_session:
            return self._current_session, True

        if self.always_new_session:
            return self.create_session(name), False

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
            self._archive_current_transcript_before_compaction(
                replacement_messages=messages,
            )
            self._current_session.messages = messages
            self.save_session()

    def add_message(self, message: Dict) -> None:
        """Add a message to current session"""
        if self._current_session:
            self._current_session.messages.append(message)
            self.save_session()

    def fork_current_session(self, message_count: Optional[int] = None, name: Optional[str] = None) -> Session:
        """Create a new session from a prefix of the current transcript."""
        source = self._current_session
        if source is None:
            raise ValueError("No active session to fork")
        messages = list(source.messages or [])
        if message_count is not None:
            messages = messages[:max(0, min(int(message_count), len(messages)))]
        forked = self.create_session(name or f"{source.name} (fork)")
        forked.messages = messages
        forked.metadata.update({"forked_from": source.id, "forked_message_count": len(messages)})
        self.save_session(forked)
        return forked

    def rewind_current_session(self, message_count: int) -> Session:
        """Truncate the active transcript to an explicit message boundary."""
        session = self._current_session
        if session is None:
            raise ValueError("No active session to rewind")
        count = max(0, min(int(message_count), len(session.messages or [])))
        self._archive_current_transcript_before_compaction(replacement_messages=list(session.messages[:count]), reason="user rewind")
        session.messages = list(session.messages[:count])
        session.metadata["rewound_at"] = datetime.now().isoformat()
        self.save_session(session)
        return session

    def search_sessions(self, query: str, limit: int = 50) -> List[Dict[str, Any]]:
        """Search message text across workspace sessions."""
        needle = str(query or "").strip().lower()
        if not needle:
            return []
        results: List[Dict[str, Any]] = []
        for info in self.list_sessions():
            if needle in info.name.lower():
                results.append({
                    "session_id": info.id,
                    "session_name": info.name,
                    "message_index": -1,
                    "role": "session",
                    "text": info.name,
                })
                if len(results) >= limit:
                    return results
            path = self.sessions_dir / f"{info.id}.json"
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
            except Exception:
                continue
            for index, message in enumerate(data.get("messages", []) or []):
                if not isinstance(message, dict):
                    continue
                content = message.get("content", "")
                content_text = content if isinstance(content, str) else json.dumps(content, ensure_ascii=False)
                reasoning_text = str(message.get("reasoning_content") or "")
                call_names = " ".join(
                    str((call.get("function") or {}).get("name") or "")
                    for call in (message.get("tool_calls") or [])
                    if isinstance(call, dict)
                )
                searchable = "\n".join(part for part in (content_text, reasoning_text, call_names) if part)
                if needle in searchable.lower():
                    preview = content_text or reasoning_text or call_names
                    results.append({"session_id": info.id, "session_name": info.name, "message_index": index, "role": message.get("role", ""), "text": preview[:500]})
                    if len(results) >= limit:
                        return results
        return results

    def export_current_session(self, output_path: Path, format_name: str = "markdown") -> Path:
        """Export the active session to Markdown or JSON."""
        session = self._current_session
        if session is None:
            raise ValueError("No active session to export")
        target = Path(output_path)
        target.parent.mkdir(parents=True, exist_ok=True)
        if format_name.lower() == "json":
            target.write_text(json.dumps(session.to_dict(), ensure_ascii=False, indent=2), encoding="utf-8")
        else:
            lines = [f"# {session.name}", ""]
            for message in session.messages:
                role = str(message.get("role", "message")).title()
                content = message.get("content", "")
                text = content if isinstance(content, str) else json.dumps(content, ensure_ascii=False, indent=2)
                lines.extend([f"## {role}", "", text, ""])
            target.write_text("\n".join(lines), encoding="utf-8")
        return target

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
        reason: str = "Token threshold reached",
        handoff_packet: Optional[Dict[str, Any]] = None,
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
            handoff_data = {}
            if isinstance(handoff_packet, dict):
                maybe_data = handoff_packet.get('data')
                if isinstance(maybe_data, dict):
                    handoff_data = maybe_data
            working_memory_body = working_memory
            if handoff_data:
                serialized_handoff = json.dumps(handoff_data, ensure_ascii=False, separators=(',', ':'))
                working_memory_body = (
                    f"{working_memory}\n\n"
                    f"Structured handoff memory:\n{serialized_handoff}"
                )
            new_session.messages.append({
                'role': 'system',
                'content': f"[WORKING MEMORY - Previous Session Context]\n{working_memory_body}\n[END WORKING MEMORY]"
            })

        if handoff_packet:
            handoff_path = self._persist_handoff_packet(
                previous_session_id=self._current_session.id if self._current_session else None,
                new_session_id=session_id,
                handoff_packet=handoff_packet,
            )
            if handoff_path:
                new_session.metadata['handoff_path'] = handoff_path

        self._current_session = new_session
        self._write_session(new_session, touch_updated_at=False)
        self._save_state(new_session.id)
        self._refresh_memory_index_for_session(new_session.id)
        return new_session

    def _persist_handoff_packet(
        self,
        *,
        previous_session_id: Optional[str],
        new_session_id: str,
        handoff_packet: Dict[str, Any],
    ) -> str:
        """Persist an automatic session handoff packet under project cache state."""
        payload = dict(handoff_packet or {})
        payload.update(
            {
                'previous_session_id': previous_session_id,
                'new_session_id': new_session_id,
                'workspace_id': self.workspace_id,
                'workspace_path': self.workspace_path,
                'persisted_at': datetime.now().isoformat(),
            }
        )

        target_path = self.handoffs_dir / f"handoff_{new_session_id}.json"
        try:
            self._write_json_atomic(target_path, payload)
        except Exception:
            return ""
        return str(target_path)

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
