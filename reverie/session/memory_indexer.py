"""
Memory Indexer - Project database indexing for persistent memory

Provides:
- Session history indexing
- Keyword and entity extraction
- Semantic search over historical conversations
- Dynamic memory injection for context retrieval
"""

from pathlib import Path
from typing import List, Dict, Optional, Set, Tuple
from dataclasses import dataclass, field
from datetime import datetime
import json
import re
import logging
from collections import defaultdict


logger = logging.getLogger(__name__)


@dataclass
class MemoryFragment:
    """A fragment of historical memory"""
    session_id: str
    message_index: int
    role: str
    content: str
    timestamp: str
    keywords: List[str] = field(default_factory=list)
    entities: List[str] = field(default_factory=list)
    tool_calls: List[str] = field(default_factory=list)
    
    def to_dict(self) -> dict:
        return {
            'session_id': self.session_id,
            'message_index': self.message_index,
            'role': self.role,
            'content': self.content,
            'timestamp': self.timestamp,
            'keywords': self.keywords,
            'entities': self.entities,
            'tool_calls': self.tool_calls
        }
    
    @classmethod
    def from_dict(cls, data: dict) -> 'MemoryFragment':
        return cls(
            session_id=data['session_id'],
            message_index=data['message_index'],
            role=data['role'],
            content=data['content'],
            timestamp=data['timestamp'],
            keywords=data.get('keywords', []),
            entities=data.get('entities', []),
            tool_calls=data.get('tool_calls', [])
        )


@dataclass
class ProjectIndex:
    """Project-wide memory index"""
    last_updated: str
    total_sessions: int
    total_messages: int
    keyword_index: Dict[str, List[str]] = field(default_factory=dict)  # keyword -> [fragment_ids]
    entity_index: Dict[str, List[str]] = field(default_factory=dict)  # entity -> [fragment_ids]
    tool_index: Dict[str, List[str]] = field(default_factory=dict)  # tool_name -> [fragment_ids]
    session_summaries: Dict[str, str] = field(default_factory=dict)  # session_id -> summary
    
    def to_dict(self) -> dict:
        return {
            'last_updated': self.last_updated,
            'total_sessions': self.total_sessions,
            'total_messages': self.total_messages,
            'keyword_index': self.keyword_index,
            'entity_index': self.entity_index,
            'tool_index': self.tool_index,
            'session_summaries': self.session_summaries
        }
    
    @classmethod
    def from_dict(cls, data: dict) -> 'ProjectIndex':
        return cls(
            last_updated=data.get('last_updated', ''),
            total_sessions=data.get('total_sessions', 0),
            total_messages=data.get('total_messages', 0),
            keyword_index=data.get('keyword_index', {}),
            entity_index=data.get('entity_index', {}),
            tool_index=data.get('tool_index', {}),
            session_summaries=data.get('session_summaries', {})
        )


class MemoryIndexer:
    """
    Indexes project database for persistent memory retrieval.
    
    This provides the foundation for cross-session memory by:
    - Extracting keywords and entities from conversations
    - Building inverted indexes for fast retrieval
    - Enabling semantic search over historical context
    """
    
    def __init__(self, project_data_dir: Path):
        self.project_data_dir = project_data_dir
        self.sessions_dir = project_data_dir / 'sessions'
        self.indexes_dir = project_data_dir / 'indexes'
        self.indexes_dir.mkdir(parents=True, exist_ok=True)
        
        self.index_path = project_data_dir / 'project_index.json'
        self.fragments_path = self.indexes_dir / 'memory_fragments.jsonl'
        
        self.index: Optional[ProjectIndex] = None
        self.fragments: Dict[str, MemoryFragment] = {}

    def get_scope_label(self) -> str:
        """Return a human-readable label for the current memory archive."""
        scope_name = str(self.project_data_dir.name or "").strip().lower()
        if scope_name in {"computer-controller", "computer_controller"}:
            return "Computer Controller History"
        return "Workspace Global Memory"
    
    def _extract_keywords(self, text: str) -> List[str]:
        """Extract keywords from text using simple heuristics"""
        # Remove common words
        stop_words = {
            'the', 'a', 'an', 'and', 'or', 'but', 'in', 'on', 'at', 'to', 'for',
            'of', 'with', 'by', 'from', 'as', 'is', 'was', 'are', 'were', 'be',
            'been', 'being', 'have', 'has', 'had', 'do', 'does', 'did', 'will',
            'would', 'should', 'could', 'may', 'might', 'must', 'can', 'this',
            'that', 'these', 'those', 'i', 'you', 'he', 'she', 'it', 'we', 'they'
        }
        
        # Extract words (alphanumeric + underscore)
        words = re.findall(r'\b[a-zA-Z_][a-zA-Z0-9_]{2,}\b', text.lower())
        
        # Filter stop words and deduplicate
        keywords = list(set(w for w in words if w not in stop_words))
        
        return keywords[:20]  # Limit to top 20 keywords
    
    def _extract_entities(self, text: str) -> List[str]:
        """Extract entities (file paths, class names, function names) from text"""
        entities = []
        
        # Extract file paths (more permissive pattern)
        file_patterns = [
            r'`([a-zA-Z0-9_/\\.-]+\.[a-zA-Z0-9]+)`',  # `path/to/file.py`
            r'"([a-zA-Z0-9_/\\.-]+\.[a-zA-Z0-9]+)"',  # "path/to/file.py"
            r"'([a-zA-Z0-9_/\\.-]+\.[a-zA-Z0-9]+)'",  # 'path/to/file.py'
            r'\b([a-zA-Z_][a-zA-Z0-9_]*\.[a-zA-Z]{2,4})\b',  # file.py (without quotes)
        ]
        
        for pattern in file_patterns:
            entities.extend(re.findall(pattern, text))
        
        # Extract class names (CamelCase)
        class_pattern = r'\b([A-Z][a-zA-Z0-9]*(?:[A-Z][a-zA-Z0-9]*)+)\b'
        entities.extend(re.findall(class_pattern, text))
        
        # Extract function names (snake_case with parentheses)
        func_pattern = r'\b([a-z_][a-z0-9_]{2,})\s*\('
        entities.extend(re.findall(func_pattern, text))
        
        # Extract simple identifiers that look like function/variable names
        identifier_pattern = r'\b([a-z_][a-z0-9_]{3,})\b'
        potential_entities = re.findall(identifier_pattern, text)
        # Filter out common words
        common_words = {'function', 'called', 'using', 'with', 'from', 'import', 'create', 'file'}
        entities.extend([e for e in potential_entities if e not in common_words])
        
        # Deduplicate and limit
        unique_entities = list(set(entities))
        return unique_entities[:15]  # Limit to top 15 entities
    
    def _extract_tool_calls(self, message: Dict) -> List[str]:
        """Extract tool call names from a message"""
        tool_calls = []
        
        if message.get('role') == 'assistant' and 'tool_calls' in message:
            for tool_call in message['tool_calls']:
                if isinstance(tool_call, dict):
                    function = tool_call.get('function', {})
                    if isinstance(function, dict):
                        tool_name = function.get('name')
                        if tool_name:
                            tool_calls.append(tool_name)
        
        return tool_calls
    
    def _create_fragment_id(self, session_id: str, message_index: int) -> str:
        """Create a unique fragment ID"""
        return f"{session_id}_{message_index}"

    def _rebuild_indexes_from_fragments(self) -> None:
        """Rebuild inverted indexes from the current in-memory fragments."""
        keyword_index = defaultdict(list)
        entity_index = defaultdict(list)
        tool_index = defaultdict(list)
        session_summaries = dict(self.index.session_summaries) if self.index else {}

        session_ids = set()
        for fragment_id, fragment in self.fragments.items():
            session_ids.add(fragment.session_id)
            for keyword in fragment.keywords:
                keyword_index[keyword].append(fragment_id)
            for entity in fragment.entities:
                entity_index[entity].append(fragment_id)
            for tool_name in fragment.tool_calls:
                tool_index[tool_name].append(fragment_id)

        self.index = ProjectIndex(
            last_updated=datetime.now().isoformat(),
            total_sessions=len(session_ids),
            total_messages=len(self.fragments),
            keyword_index=dict(keyword_index),
            entity_index=dict(entity_index),
            tool_index=dict(tool_index),
            session_summaries=session_summaries,
        )
    
    def index_session(self, session_id: str) -> int:
        """
        Index a single session file.
        
        Returns:
            Number of fragments indexed
        """
        session_path = self.sessions_dir / f"{session_id}.json"
        
        if not session_path.exists():
            return 0

        try:
            with open(session_path, 'r', encoding='utf-8') as f:
                session_data = json.load(f)
            
            messages = session_data.get('messages', [])
            indexed_count = 0
            
            for idx, message in enumerate(messages):
                role = message.get('role', '')
                content = message.get('content', '')
                
                if not content or role == 'system':
                    continue
                
                # Create fragment
                fragment_id = self._create_fragment_id(session_id, idx)
                
                fragment = MemoryFragment(
                    session_id=session_id,
                    message_index=idx,
                    role=role,
                    content=content[:1000],  # Limit content length
                    timestamp=session_data.get('updated_at', ''),
                    keywords=self._extract_keywords(content),
                    entities=self._extract_entities(content),
                    tool_calls=self._extract_tool_calls(message)
                )
                
                self.fragments[fragment_id] = fragment
                indexed_count += 1
            
            return indexed_count
        
        except Exception as e:
            logger.warning("Error indexing session %s: %s", session_id, e)
            return 0

    def refresh_session(self, session_id: str) -> int:
        """
        Re-index a single session and persist the refreshed project index.

        Returns:
            Number of fragments indexed for the session.
        """
        if not self.index:
            self.load_index()

        stale_fragment_ids = [
            fragment_id
            for fragment_id, fragment in self.fragments.items()
            if fragment.session_id == session_id
        ]
        for fragment_id in stale_fragment_ids:
            self.fragments.pop(fragment_id, None)

        indexed_count = self.index_session(session_id)
        self._rebuild_indexes_from_fragments()
        self._save_index()
        self._save_fragments()
        return indexed_count
    
    def build_index(self) -> ProjectIndex:
        """
        Build the complete project index from all sessions.
        
        Returns:
            ProjectIndex object
        """
        logger.info("[Memory Indexer] Building project index...")
        
        # Clear existing data
        self.fragments.clear()
        
        # Index all sessions
        session_files = list(self.sessions_dir.glob('*.json'))
        total_sessions = len(session_files)
        total_messages = 0
        
        for session_file in session_files:
            session_id = session_file.stem
            count = self.index_session(session_id)
            total_messages += int(count or 0)
        
        # Build inverted indexes
        keyword_index = defaultdict(list)
        entity_index = defaultdict(list)
        tool_index = defaultdict(list)
        
        for fragment_id, fragment in self.fragments.items():
            # Index keywords
            for keyword in fragment.keywords:
                keyword_index[keyword].append(fragment_id)
            
            # Index entities
            for entity in fragment.entities:
                entity_index[entity].append(fragment_id)
            
            # Index tool calls
            for tool_name in fragment.tool_calls:
                tool_index[tool_name].append(fragment_id)
        
        # Create index
        self.index = ProjectIndex(
            last_updated=datetime.now().isoformat(),
            total_sessions=total_sessions,
            total_messages=total_messages,
            keyword_index=dict(keyword_index),
            entity_index=dict(entity_index),
            tool_index=dict(tool_index)
        )
        
        # Save index
        self._save_index()
        self._save_fragments()
        
        logger.info(
            "[Memory Indexer] Indexed %s sessions, %s messages",
            total_sessions,
            total_messages,
        )
        
        return self.index
    
    def _save_index(self) -> None:
        """Save project index to disk"""
        if self.index:
            with open(self.index_path, 'w', encoding='utf-8') as f:
                json.dump(self.index.to_dict(), f, indent=2, ensure_ascii=False)
    
    def _save_fragments(self) -> None:
        """Save memory fragments to disk (JSONL format)"""
        with open(self.fragments_path, 'w', encoding='utf-8') as f:
            for fragment in self.fragments.values():
                f.write(json.dumps(fragment.to_dict(), ensure_ascii=False) + '\n')
    
    def load_index(self) -> bool:
        """Load project index from disk"""
        if not self.index_path.exists():
            return False
        
        try:
            with open(self.index_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            self.index = ProjectIndex.from_dict(data)
            
            # Load fragments
            if self.fragments_path.exists():
                with open(self.fragments_path, 'r', encoding='utf-8') as f:
                    for line in f:
                        fragment_data = json.loads(line)
                        fragment = MemoryFragment.from_dict(fragment_data)
                        fragment_id = self._create_fragment_id(
                            fragment.session_id,
                            fragment.message_index
                        )
                        self.fragments[fragment_id] = fragment
            
            return True
        
        except Exception as e:
            logger.warning("Error loading memory index: %s", e)
            return False
    
    def search(
        self,
        query: str,
        max_results: int = 10,
        max_tokens: int = 16000
    ) -> List[MemoryFragment]:
        """
        Search for relevant memory fragments.
        
        Args:
            query: Search query
            max_results: Maximum number of results
            max_tokens: Maximum total tokens in results
        
        Returns:
            List of relevant memory fragments
        """
        if not self.index:
            self.load_index()
        if not self.index and self.sessions_dir.exists():
            self.build_index()

        if not self.index:
            return []
        
        # Extract keywords from query
        query_keywords = self._extract_keywords(query)
        query_entities = self._extract_entities(query)
        
        # Score fragments
        scores: Dict[str, float] = defaultdict(float)
        
        # Keyword matching
        for keyword in query_keywords:
            fragment_ids = self.index.keyword_index.get(keyword, [])
            for fragment_id in fragment_ids:
                scores[fragment_id] += 1.0
        
        # Entity matching (higher weight)
        for entity in query_entities:
            fragment_ids = self.index.entity_index.get(entity, [])
            for fragment_id in fragment_ids:
                scores[fragment_id] += 2.0
        
        # Sort by score
        sorted_fragments = sorted(
            scores.items(),
            key=lambda x: x[1],
            reverse=True
        )[:max_results]
        
        # Retrieve fragments
        results = []
        total_tokens = 0
        
        for fragment_id, score in sorted_fragments:
            fragment = self.fragments.get(fragment_id)
            if fragment:
                # Estimate tokens (rough: 1 token ≈ 4 characters)
                fragment_tokens = len(fragment.content) // 4
                
                if total_tokens + fragment_tokens > max_tokens:
                    break
                
                results.append(fragment)
                total_tokens += fragment_tokens
        
        return results
    
    def get_session_summary(self, session_id: str) -> Optional[str]:
        """Get summary for a session (if available)"""
        if not self.index:
            self.load_index()
        
        if self.index:
            return self.index.session_summaries.get(session_id)
        
        return None
    
    def set_session_summary(self, session_id: str, summary: str) -> None:
        """Set summary for a session"""
        if not self.index:
            self.load_index()
        
        if not self.index:
            self.index = ProjectIndex(
                last_updated=datetime.now().isoformat(),
                total_sessions=0,
                total_messages=0
            )
        
        self.index.session_summaries[session_id] = summary
        self._save_index()

    def get_recent_fragments(self, limit: int = 8) -> List[MemoryFragment]:
        """Return the most recent indexed fragments across the workspace."""
        if not self.index:
            self.load_index()

        items = sorted(
            self.fragments.values(),
            key=lambda fragment: (fragment.timestamp, fragment.message_index),
            reverse=True,
        )
        return items[: max(1, int(limit or 8))]

    def build_memory_summary(
        self,
        query: str = "",
        max_fragments: int = 8,
        max_chars: int = 3200,
        *,
        title: Optional[str] = None,
    ) -> str:
        """Build a compact memory block for the current archive."""
        if not self.index:
            self.load_index()
        if not self.index and self.sessions_dir.exists():
            self.build_index()

        if not self.index:
            return ""

        lines: List[str] = [
            f"## {title or self.get_scope_label()}",
            f"- Indexed sessions: {self.index.total_sessions}",
            f"- Indexed message fragments: {self.index.total_messages}",
        ]

        top_entities = sorted(
            self.index.entity_index.items(),
            key=lambda item: len(item[1]),
            reverse=True,
        )[:6]
        if top_entities:
            entity_text = ", ".join(f"{name}({len(refs)})" for name, refs in top_entities)
            lines.append(f"- Frequent entities: {entity_text}")

        top_tools = sorted(
            self.index.tool_index.items(),
            key=lambda item: len(item[1]),
            reverse=True,
        )[:6]
        if top_tools:
            tool_text = ", ".join(f"{name}({len(refs)})" for name, refs in top_tools)
            lines.append(f"- Common tools: {tool_text}")

        summary_ids = sorted(self.index.session_summaries.keys(), reverse=True)[:4]
        if summary_ids:
            lines.append("- Recent session summaries:")
            for session_id in summary_ids:
                summary = str(self.index.session_summaries.get(session_id, "") or "").strip()
                if summary:
                    lines.append(f"  - {summary[:220]}")

        fragments = self.search(query, max_results=max_fragments, max_tokens=max_chars // 4) if str(query or "").strip() else self.get_recent_fragments(limit=max_fragments)
        if fragments:
            lines.append("- Relevant memory fragments:")
            for fragment in fragments:
                compact = " ".join(str(fragment.content or "").split())
                compact = compact[:260] + ("..." if len(compact) > 260 else "")
                lines.append(f"  - [{fragment.role}] {compact}")

        summary = "\n".join(lines).strip()
        if len(summary) > max_chars:
            summary = summary[: max_chars - 3].rstrip() + "..."
        return summary

    def build_workspace_memory_summary(
        self,
        query: str = "",
        max_fragments: int = 8,
        max_chars: int = 3200,
    ) -> str:
        """Backward-compatible wrapper for workspace-labeled summaries."""
        return self.build_memory_summary(query=query, max_fragments=max_fragments, max_chars=max_chars)
