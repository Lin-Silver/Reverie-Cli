"""
Memory Indexer - Project database indexing for persistent memory

Provides:
- Session history indexing
- Keyword and entity extraction
- Semantic search over historical conversations
- Dynamic memory injection for context retrieval
"""

from pathlib import Path
from typing import Any, List, Dict, Optional, Set, Tuple
from dataclasses import dataclass, field
from datetime import datetime
import hashlib
import json
import re
import logging
from collections import defaultdict

from ..diagnostics import report_suppressed_exception

from ..context_engine.fragments import ContextFragment, make_context_fragment, truncate_to_token_cap


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


@dataclass
class AutoMemoryItem:
    """A compact learned memory distilled from prior sessions."""
    id: str
    content: str
    score: float
    source_session_id: str
    updated_at: str
    keywords: List[str] = field(default_factory=list)
    entities: List[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            'id': self.id,
            'content': self.content,
            'score': self.score,
            'source_session_id': self.source_session_id,
            'updated_at': self.updated_at,
            'keywords': self.keywords,
            'entities': self.entities,
        }

    @classmethod
    def from_dict(cls, data: dict) -> 'AutoMemoryItem':
        return cls(
            id=str(data.get('id') or ''),
            content=str(data.get('content') or ''),
            score=float(data.get('score') or 0.0),
            source_session_id=str(data.get('source_session_id') or ''),
            updated_at=str(data.get('updated_at') or ''),
            keywords=list(data.get('keywords') or []),
            entities=list(data.get('entities') or []),
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
        self.auto_memory_path = self.indexes_dir / 'auto_memory.json'
        
        self.index: Optional[ProjectIndex] = None
        self.fragments: Dict[str, MemoryFragment] = {}
        self.auto_memory: List[AutoMemoryItem] = []
        self._auto_memory_loaded = False

    def get_scope_label(self) -> str:
        """Return a human-readable label for the current memory archive."""
        scope_name = str(self.project_data_dir.name or "").strip().lower()
        if scope_name in {"computer-controller", "computer_controller"}:
            return "Computer Controller History"
        return "Workspace Global Memory"

    def _redact_memory_text(self, text: str) -> str:
        """Remove secrets and highly personal path segments before persistence."""
        safe = str(text or "")
        if not safe:
            return ""

        secret_patterns = [
            r"(?i)\b(sk-[A-Za-z0-9_\-]{16,})\b",
            r"(?i)\b(ms-[A-Za-z0-9_\-]{16,})\b",
            r"(?i)\b(nvapi-[A-Za-z0-9_\-]{16,})\b",
            r"(?i)\b(gh[pousr]_[A-Za-z0-9_]{20,})\b",
            r"(?i)\b(api[_-]?key|token|secret|password)\s*[:=]\s*['\"]?[^'\"\s,;]{8,}",
        ]
        for pattern in secret_patterns:
            safe = re.sub(pattern, lambda match: self._redacted_secret_replacement(match), safe)

        safe = re.sub(r"(?i)\b([A-Z]:\\Users\\)[^\\\s]+", r"\1[USER]", safe)
        safe = re.sub(r"(?i)\b(/home/)[^/\s]+", r"\1[USER]", safe)
        safe = re.sub(r"(?i)\b(/Users/)[^/\s]+", r"\1[USER]", safe)
        return safe

    @staticmethod
    def _redacted_secret_replacement(match: re.Match) -> str:
        text = match.group(0)
        if re.match(r"(?i)^(api[_-]?key|token|secret|password)", text):
            key = text.split("=", 1)[0].split(":", 1)[0]
            separator = "=" if "=" in text else ":"
            return f"{key}{separator}[REDACTED]"
        return "[REDACTED_SECRET]"
    
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

                safe_content = self._redact_memory_text(str(content))
                
                # Create fragment
                fragment_id = self._create_fragment_id(session_id, idx)
                
                fragment = MemoryFragment(
                    session_id=session_id,
                    message_index=idx,
                    role=role,
                    content=safe_content[:1000],  # Limit content length
                    timestamp=session_data.get('updated_at', ''),
                    keywords=self._extract_keywords(safe_content),
                    entities=self._extract_entities(safe_content),
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

    def _load_auto_memory(self) -> List[AutoMemoryItem]:
        """Load distilled automatic memories from disk."""
        if self._auto_memory_loaded:
            return self.auto_memory
        self._auto_memory_loaded = True
        self.auto_memory = []
        if not self.auto_memory_path.exists():
            return self.auto_memory
        try:
            payload = json.loads(self.auto_memory_path.read_text(encoding='utf-8'))
            items = payload.get('items', []) if isinstance(payload, dict) else []
            self.auto_memory = [
                item
                for item in (AutoMemoryItem.from_dict(raw) for raw in items if isinstance(raw, dict))
                if item.id and item.content
            ]
        except Exception as exc:
            logger.warning("Error loading auto memory: %s", exc)
            self.auto_memory = []
        return self.auto_memory

    def _save_auto_memory(self) -> None:
        """Persist distilled automatic memories."""
        payload = {
            'schema': 'reverie.auto_memory.v1',
            'updated_at': datetime.now().isoformat(),
            'items': [item.to_dict() for item in self.auto_memory],
        }
        self.indexes_dir.mkdir(parents=True, exist_ok=True)
        self.auto_memory_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding='utf-8')
        self._auto_memory_loaded = True

    @staticmethod
    def _normalize_memory_key(text: str) -> str:
        compact = re.sub(r'\s+', ' ', str(text or '').strip().lower())
        compact = re.sub(r'[^a-z0-9_\-./\\: ]+', '', compact)
        return compact[:800]

    def _auto_memory_id(self, text: str) -> str:
        digest = hashlib.sha256(self._normalize_memory_key(text).encode('utf-8', errors='replace')).hexdigest()
        return digest[:20]

    def _score_auto_memory_candidate(self, fragment: MemoryFragment, content: str) -> float:
        """Score whether a fragment is durable enough to become auto memory."""
        compact = str(content or '').strip()
        if len(compact) < 48:
            return 0.0
        score = 0.0
        if fragment.role == 'user':
            score += 0.5
        if fragment.tool_calls:
            score += 0.8
        score += min(1.0, len(fragment.entities) * 0.14)
        score += min(0.45, len(fragment.keywords) * 0.03)
        if re.search(r'(?i)\b(always|never|prefer|remember|default|must|should|fixed|implemented|changed|added|removed|migrat|config|workspace|context|memory|provider|api|stream|timeout|retry|test)\b', compact):
            score += 0.9
        if re.search(r'[\w./\\-]+\.(py|ts|tsx|js|jsx|cs|json|toml|yaml|yml|md)\b', compact, flags=re.I):
            score += 0.8
        if re.search(r'(需要|应该|默认|不要|修复|优化|迁移|工作区|上下文|记忆|模型|调用|测试)', compact):
            score += 0.9
        if len(compact) > 900:
            score -= 0.25
        return max(0.0, score)

    def auto_learn_from_sessions(
        self,
        *,
        max_items: int = 36,
        max_sessions: int = 40,
        min_score: float = 1.35,
    ) -> List[AutoMemoryItem]:
        """
        Distill durable cross-session facts from indexed sessions.

        This is a local, deterministic learning loop: it redacts secrets, de-dupes
        fragments, ranks durable facts/preferences/workspace decisions, and stores
        them for automatic prompt injection.
        """
        if not self.index:
            self.load_index()
        if not self.index and self.sessions_dir.exists():
            self.build_index()

        existing_by_id = {item.id: item for item in self._load_auto_memory()}
        candidates: Dict[str, AutoMemoryItem] = dict(existing_by_id)

        if self.index:
            for session_id, summary in list(self.index.session_summaries.items())[-max_sessions:]:
                safe_summary = truncate_to_token_cap(self._redact_memory_text(summary), 80).strip()
                if len(safe_summary) < 48:
                    continue
                item_id = self._auto_memory_id(safe_summary)
                item = AutoMemoryItem(
                    id=item_id,
                    content=safe_summary,
                    score=max(1.6, existing_by_id.get(item_id, AutoMemoryItem(item_id, '', 0.0, '', '')).score),
                    source_session_id=session_id,
                    updated_at=datetime.now().isoformat(),
                    keywords=self._extract_keywords(safe_summary),
                    entities=self._extract_entities(safe_summary),
                )
                if item.score >= candidates.get(item_id, item).score:
                    candidates[item_id] = item

        fragments = sorted(
            self.fragments.values(),
            key=lambda fragment: (fragment.timestamp, fragment.message_index),
            reverse=True,
        )[: max(1, max_sessions * 16)]

        for fragment in fragments:
            safe_content = truncate_to_token_cap(self._redact_memory_text(fragment.content), 120).strip()
            score = self._score_auto_memory_candidate(fragment, safe_content)
            if score < min_score:
                continue
            item_id = self._auto_memory_id(safe_content)
            current = candidates.get(item_id)
            if current and current.score > score:
                continue
            candidates[item_id] = AutoMemoryItem(
                id=item_id,
                content=safe_content,
                score=score,
                source_session_id=fragment.session_id,
                updated_at=fragment.timestamp or datetime.now().isoformat(),
                keywords=fragment.keywords,
                entities=fragment.entities,
            )

        ranked = sorted(
            candidates.values(),
            key=lambda item: (-float(item.score or 0.0), str(item.updated_at or ''), item.id),
        )
        self.auto_memory = ranked[: max(1, int(max_items or 36))]
        self._save_auto_memory()
        return self.auto_memory

    def search_auto_memory(
        self,
        query: str = "",
        *,
        max_items: int = 6,
        max_chars: int = 1200,
    ) -> List[AutoMemoryItem]:
        """Retrieve learned auto-memory items with query-aware scoring."""
        items = self._load_auto_memory()
        if not items and self.sessions_dir.exists():
            items = self.auto_learn_from_sessions(max_items=max(12, max_items))
        if not items:
            return []

        query_terms = set(self._extract_keywords(query)) | {entity.lower() for entity in self._extract_entities(query)}
        scored: List[Tuple[float, AutoMemoryItem]] = []
        for item in items:
            score = float(item.score or 0.0)
            item_terms = set(item.keywords or []) | {entity.lower() for entity in (item.entities or [])}
            if query_terms:
                score += len(query_terms & item_terms) * 0.75
                content_lower = item.content.lower()
                score += sum(0.35 for term in query_terms if term and term in content_lower)
            scored.append((score, item))

        total_chars = 0
        selected: List[AutoMemoryItem] = []
        for _, item in sorted(scored, key=lambda pair: (-pair[0], pair[1].id)):
            item_chars = len(item.content)
            if selected and total_chars + item_chars > max_chars:
                break
            selected.append(item)
            total_chars += item_chars
            if len(selected) >= max_items:
                break
        return selected

    def build_context_fragments(
        self,
        query: str = "",
        *,
        max_fragments: int = 8,
        max_chars: int = 3200,
    ) -> List[ContextFragment]:
        """Build typed bounded memory fragments for prompt assembly."""
        fragments: List[ContextFragment] = []
        auto_items = self.search_auto_memory(query, max_items=4, max_chars=max(600, max_chars // 3))
        for order, item in enumerate(auto_items):
            fragments.append(
                make_context_fragment(
                    "auto_memory",
                    f"auto:{item.source_session_id or item.id}",
                    item.content,
                    token_cap=160,
                    priority=3.0 + float(item.score or 0.0),
                    stable_order=order,
                    metadata={"memory_id": item.id, "updated_at": item.updated_at},
                )
            )

        memory_fragments = (
            self.search(query, max_results=max_fragments, max_tokens=max_chars // 4)
            if str(query or "").strip()
            else self.get_recent_fragments(limit=max_fragments)
        )
        for order, fragment in enumerate(memory_fragments, start=len(fragments)):
            fragments.append(
                make_context_fragment(
                    "session_memory",
                    f"{fragment.session_id}:{fragment.message_index}",
                    f"[{fragment.role}] {fragment.content}",
                    token_cap=120,
                    priority=1.0,
                    stable_order=order,
                    metadata={"timestamp": fragment.timestamp},
                )
            )
        return fragments
    
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
        
        query_terms = set(query_keywords) | {entity.lower() for entity in query_entities}

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

        # Content overlap and recency scoring catch useful fragments whose
        # extracted keyword/entity list was too sparse.
        now = datetime.now()
        for fragment_id, fragment in self.fragments.items():
            content_lower = str(fragment.content or "").lower()
            for term in query_terms:
                if term and term in content_lower:
                    scores[fragment_id] += 0.35
            try:
                fragment_time = datetime.fromisoformat(str(fragment.timestamp or ""))
                age_days = max(0.0, (now - fragment_time).total_seconds() / 86400.0)
                scores[fragment_id] += max(0.0, 0.35 * (1.0 - min(age_days / 30.0, 1.0)))
            except Exception:
                report_suppressed_exception("score session-memory recency", logger=logger)
        
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

        auto_items = self.search_auto_memory(query, max_items=5, max_chars=max(800, max_chars // 3))
        if auto_items:
            lines.append("- Auto memory:")
            for item in auto_items:
                compact = " ".join(str(item.content or "").split())
                compact = compact[:260] + ("..." if len(compact) > 260 else "")
                lines.append(f"  - {compact}")

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
