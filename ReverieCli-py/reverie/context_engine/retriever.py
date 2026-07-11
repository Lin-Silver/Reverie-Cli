"""
Context Retriever - The brain of the Context Engine

This is the most critical component for reducing model hallucinations.
It provides intelligent context retrieval with the "minimal but complete" strategy.

The retriever:
1. Understands what context is needed for a task
2. Retrieves the minimum necessary symbols and their dependencies
3. Formats context in a way optimized for LLM consumption
4. Respects token limits while maximizing information density
"""

from pathlib import Path
from typing import List, Dict, Optional, Set, Tuple, Any
from dataclasses import dataclass, field
import re
import shutil
import sqlite3
import subprocess
import time
from collections import defaultdict

from .symbol_table import Symbol, SymbolTable, SymbolKind
from .dependency_graph import DependencyGraph, DependencyType
from .fast_context import FastContextExplorer, FastContextResult
from .workspace import WorkspaceProfile, detect_workspace_profile


@dataclass
class ContextPackage:
    """
    A package of context ready to be sent to the model.
    
    This represents the "minimal but complete" context for a task.
    """
    symbols: List[Symbol]
    dependencies: List[Tuple[str, str, str]]  # (from, to, type)
    file_contents: Dict[str, str]  # file_path -> relevant content
    imports: List[Dict]
    context_string: str  # Formatted context for model consumption
    token_estimate: int
    metadata: Dict = field(default_factory=dict)
    
    @property
    def symbol_count(self) -> int:
        return len(self.symbols)
    
    @property
    def file_count(self) -> int:
        return len(self.file_contents)


@dataclass
class SymbolContext:
    """Context for a single symbol with its related symbols"""
    symbol: Symbol
    parent: Optional[Symbol]
    children: List[Symbol]
    dependencies: List[Symbol]  # What it depends on
    dependents: List[Symbol]    # What depends on it
    call_chain: List[str]       # Symbols in the call chain
    context_string: str


@dataclass
class EditContext:
    """Context prepared specifically for code editing"""
    target_file: str
    target_lines: Tuple[int, int]
    target_content: str
    symbols_in_range: List[Symbol]
    related_symbols: List[Symbol]
    imports: List[Dict]
    context_string: str


@dataclass
class TaskContextFile:
    """A ranked file candidate for an intent-driven retrieval request."""
    file_path: str
    language: str
    score: float
    summary: str
    reasons: List[str]
    top_symbols: List[str] = field(default_factory=list)
    tags: List[str] = field(default_factory=list)
    excerpt: str = ""
    evidence: List[Dict[str, Any]] = field(default_factory=list)


@dataclass
class TaskContextResult:
    """Curated multi-source context for a task or user request."""
    query: str
    relevant_symbols: List[Symbol]
    relevant_files: List[TaskContextFile]
    memory_fragments: List[Dict[str, str]]
    commit_context: List[Dict[str, Any]]
    context_string: str
    token_estimate: int
    metadata: Dict = field(default_factory=dict)
    workspace_profile: Optional[WorkspaceProfile] = None


class ContextRetriever:
    """
    Intelligent context retriever for the Context Engine.
    
    This class is responsible for understanding what context is needed
    and retrieving it efficiently while respecting token limits.
    
    Key strategies:
    1. Symbol-centric retrieval: Start with requested symbols
    2. Dependency expansion: Automatically include critical dependencies
    3. Relevance ranking: Prioritize most relevant context
    4. Token budgeting: Fit within model context limits
    """
    
    # Approximate tokens per character
    TOKENS_PER_CHAR = 0.25
    
    # Default token budget (increased for larger context window)
    DEFAULT_TOKEN_BUDGET = 50000

    TASK_QUERY_SYNONYMS = {
        'logging': ['log', 'logger', 'telemetry', 'observability', 'trace', 'tracing', 'metrics', 'audit'],
        'payment': ['billing', 'checkout', 'invoice', 'charge', 'stripe', 'subscription'],
        'auth': ['authentication', 'authorize', 'authorization', 'login', 'token', 'session', 'identity'],
        'test': ['tests', 'testing', 'spec', 'assert', 'fixture'],
        'config': ['configuration', 'settings', 'option', 'flag', 'env', 'environment'],
        'database': ['db', 'sql', 'query', 'migration', 'model', 'schema', 'repository'],
        'cache': ['caching', 'redis', 'memo', 'memoize'],
        'queue': ['job', 'worker', 'task', 'scheduler', 'background'],
        'error': ['errors', 'exception', 'failure', 'retry', 'fallback'],
        'docs': ['documentation', 'readme', 'guide', 'runbook', 'spec'],
        'cli': ['command', 'commands', 'terminal', 'shell', 'argparse', 'click', 'prompt'],
        'context': ['retrieval', 'retriever', 'index', 'indexer', 'symbol', 'semantic', 'workspace'],
        'stream': ['streaming', 'sse', 'delta', 'chunk', 'messages', 'completion'],
        'model': ['provider', 'source', 'sdk', 'client', 'api'],
    }
    
    # Game-related keywords for prioritization
    GAME_LOGIC_KEYWORDS = {
        # Core game loop
        'update', 'draw', 'render', 'tick', 'step', 'loop',
        # Entity/Component
        'entity', 'component', 'system', 'actor', 'object', 'sprite',
        # Game state
        'state', 'scene', 'level', 'world', 'game', 'play',
        # Input
        'input', 'control', 'keyboard', 'mouse', 'touch', 'button',
        # Physics
        'physics', 'collision', 'velocity', 'position', 'transform',
        # Animation
        'animation', 'animate', 'tween', 'frame',
        # Audio
        'audio', 'sound', 'music', 'sfx',
        # UI
        'ui', 'menu', 'hud', 'dialog', 'button', 'panel',
        # RPG specific
        'quest', 'npc', 'dialog', 'inventory', 'item', 'skill', 'stat',
        'character', 'player', 'enemy', 'battle', 'combat',
        # Love2D specific
        'love', 'conf', 'load', 'keypressed', 'mousepressed',
        # Godot specific
        '_ready', '_process', '_physics_process', '_input', 'node',
    }
    
    def __init__(
        self,
        symbol_table: SymbolTable,
        dependency_graph: DependencyGraph,
        project_root: Path,
        *,
        file_info: Optional[Dict[str, Any]] = None,
        git_integration: Any = None,
        memory_indexer: Any = None,
        lsp_manager: Any = None,
    ):
        self.symbol_table = symbol_table
        self.dependency_graph = dependency_graph
        self.project_root = project_root
        self.file_info = file_info if file_info is not None else {}
        self.git_integration = git_integration
        self.memory_indexer = memory_indexer
        self.lsp_manager = lsp_manager
        self._activity_files: Dict[str, Dict[str, float]] = {}
        self._activity_symbols: Dict[str, Dict[str, float]] = {}
        self._task_cache: Dict[tuple[Any, ...], tuple[float, TaskContextResult]] = {}

    def _normalize_file_path(self, file_path: str) -> str:
        """Normalize file paths so workset scoring is stable across callers."""
        try:
            candidate = Path(file_path)
            if not candidate.is_absolute():
                candidate = (self.project_root / candidate).resolve()
            else:
                candidate = candidate.resolve()
            return str(candidate)
        except Exception:
            return str(file_path)

    def _normalize_symbol_name(self, symbol_name: str) -> str:
        return str(symbol_name or "").strip()

    def mark_file_activity(self, file_path: str, *, weight: float = 1.0, reason: str = "access") -> None:
        """Remember files the user or agent touched recently."""
        key = self._normalize_file_path(file_path)
        now = time.time()
        state = self._activity_files.setdefault(key, {"score": 0.0, "timestamp": now})
        state["score"] = min(8.0, float(state.get("score", 0.0)) + max(0.1, weight))
        state["timestamp"] = now
        if reason == "edit":
            state["score"] = min(10.0, state["score"] + 0.75)

    def mark_symbol_activity(self, symbol_name: str, *, weight: float = 1.0) -> None:
        """Remember symbol-level activity and tie it back to the containing file."""
        key = self._normalize_symbol_name(symbol_name)
        if not key:
            return
        now = time.time()
        state = self._activity_symbols.setdefault(key, {"score": 0.0, "timestamp": now})
        state["score"] = min(8.0, float(state.get("score", 0.0)) + max(0.1, weight))
        state["timestamp"] = now
        symbol = self.symbol_table.get_symbol(key)
        if symbol and symbol.file_path:
            self.mark_file_activity(symbol.file_path, weight=weight * 0.7, reason="symbol")

    def _activity_boost(self, state: Optional[Dict[str, float]]) -> float:
        """Decay recency-based workset boosts over time."""
        if not state:
            return 0.0
        age_seconds = max(0.0, time.time() - float(state.get("timestamp", 0.0)))
        age_penalty = min(1.0, age_seconds / 1800.0)
        return max(0.0, float(state.get("score", 0.0)) * (1.0 - age_penalty))

    def _tokenize_query(self, text: str) -> List[str]:
        raw_tokens = re.findall(r"[A-Za-z_][A-Za-z0-9_]{2,}", str(text or ""))
        tokens: List[str] = []
        seen: Set[str] = set()
        for raw in raw_tokens:
            expanded = re.sub(r"([a-z0-9])([A-Z])", r"\1 \2", raw).replace("_", " ").split()
            for part in expanded:
                token = part.lower().strip()
                if len(token) < 3 or token in seen:
                    continue
                seen.add(token)
                tokens.append(token)
        return tokens

    def _build_task_term_weights(self, query: str) -> Dict[str, float]:
        """Expand the user request into weighted retrieval terms."""
        weights: Dict[str, float] = {}
        for token in self._tokenize_query(query):
            weights[token] = max(weights.get(token, 0.0), 1.0)
            for root, synonyms in self.TASK_QUERY_SYNONYMS.items():
                if token == root or token in synonyms:
                    weights[root] = max(weights.get(root, 0.0), 0.9 if token == root else 0.7)
                    for synonym in synonyms:
                        weights[synonym] = max(weights.get(synonym, 0.0), 0.55)
        return weights

    def _extract_query_anchors(self, query: str) -> Dict[str, List[str]]:
        """Extract high-confidence file and symbol anchors from a free-form task."""
        text = str(query or "")
        file_like: List[str] = []
        symbol_like: List[str] = []
        seen_files: Set[str] = set()
        seen_symbols: Set[str] = set()

        for raw in re.findall(r"[\w./\\-]+\.[A-Za-z0-9_]{1,8}(?::\d+)?", text):
            candidate = raw.strip("`'\".,;()[]{}")
            if not candidate:
                continue
            if ":" in candidate:
                candidate = candidate.split(":", 1)[0]
            key = candidate.lower().replace("\\", "/")
            if key not in seen_files:
                seen_files.add(key)
                file_like.append(candidate)

        for raw in re.findall(r"\b[A-Za-z_][A-Za-z0-9_]*(?:\.[A-Za-z_][A-Za-z0-9_]*)+\b|\b[A-Z][A-Za-z0-9_]{2,}\b", text):
            candidate = raw.strip("`'\".,;()[]{}")
            if not candidate or "." in candidate and candidate.lower().endswith((".py", ".ts", ".js", ".md")):
                continue
            key = candidate.lower()
            if key not in seen_symbols:
                seen_symbols.add(key)
                symbol_like.append(candidate)

        return {"files": file_like[:12], "symbols": symbol_like[:20]}

    def _query_role_boost(self, file_path: str, tags: List[str], query: str) -> Tuple[float, List[str]]:
        """Bias files toward the role implied by the user's task."""
        query_lower = str(query or "").lower()
        path_lower = str(file_path or "").lower().replace("\\", "/")
        tag_set = set(tags or [])
        boost = 0.0
        reasons: List[str] = []

        role_rules = [
            ("test", ("test", "tests", "pytest", "spec", "coverage", "assert")),
            ("docs", ("doc", "docs", "readme", "documentation", "guide")),
            ("config", ("config", "settings", "toml", "yaml", "json", "env")),
            ("cli", ("cli", "command", "commands", "terminal", "shell")),
            ("api", ("api", "endpoint", "route", "handler")),
            ("engine", ("engine", "context", "retrieval", "indexer", "retriever")),
        ]
        for tag, terms in role_rules:
            if not any(term in query_lower for term in terms):
                continue
            if tag in tag_set or f"/{tag}" in path_lower or tag in path_lower:
                boost += 1.6
                reasons.append(f"role:{tag}")

        if any(term in query_lower for term in ("fix", "bug", "error", "exception", "traceback")) and "test" not in tag_set:
            boost += 0.4
            reasons.append("implementation-focus")
        return boost, reasons

    def _score_file_content_for_task(self, file_path: str, term_weights: Dict[str, float]) -> Tuple[float, List[str]]:
        """Lightweight content scoring for files whose cached summaries are sparse."""
        if not term_weights:
            return 0.0, []
        try:
            path = Path(file_path)
            if not path.exists() or not path.is_file() or path.stat().st_size > 256 * 1024:
                return 0.0, []
            text = path.read_text(encoding="utf-8", errors="ignore")[:120000].lower()
        except Exception:
            return 0.0, []

        score = 0.0
        reasons: List[str] = []
        for term, weight in term_weights.items():
            term_lower = term.lower()
            if len(term_lower) < 3:
                continue
            count = text.count(term_lower)
            if count <= 0:
                continue
            score += min(2.4, 0.35 * count) * weight
            reasons.append(f"content:{term_lower}")
            if len(reasons) >= 4:
                break
        return score, reasons

    def _workspace_relative_path(self, file_path: str) -> str:
        try:
            return str(Path(file_path).resolve().relative_to(self.project_root))
        except Exception:
            return str(file_path)

    def _merge_file_evidence(
        self,
        evidence_by_file: Dict[str, List[Dict[str, Any]]],
        file_path: str,
        *,
        source: str,
        reason: str,
        score: float = 0.0,
        line: Optional[int] = None,
        line_end: Optional[int] = None,
        detail: str = "",
    ) -> None:
        normalized = self._normalize_file_path(file_path)
        item = {
            "source": source,
            "reason": reason,
            "score": round(float(score), 3),
        }
        if line is not None:
            item["line"] = int(line)
        if line_end is not None:
            item["line_end"] = int(line_end)
        if detail:
            item["detail"] = str(detail)[:300]
        bucket = evidence_by_file.setdefault(normalized, [])
        key = (item.get("source"), item.get("reason"), item.get("line"), item.get("detail"))
        if any((old.get("source"), old.get("reason"), old.get("line"), old.get("detail")) == key for old in bucket):
            return
        bucket.append(item)

    def _run_ripgrep_for_task(self, query: str, term_weights: Dict[str, float], limit: int = 40) -> List[Dict[str, Any]]:
        """Use ripgrep as a fast lexical signal when it is installed."""
        rg = shutil.which("rg")
        if not rg or not term_weights:
            return []
        terms = [
            re.escape(term)
            for term, _ in sorted(term_weights.items(), key=lambda item: item[1], reverse=True)
            if len(str(term or "")) >= 3
        ][:8]
        if not terms:
            return []
        pattern = "|".join(terms)
        try:
            completed = subprocess.run(
                [rg, "--json", "--ignore-case", "--line-number", "--max-count", "4", pattern, str(self.project_root)],
                cwd=str(self.project_root),
                text=True,
                encoding="utf-8",
                errors="replace",
                capture_output=True,
                timeout=5,
            )
        except Exception:
            return []
        hits: List[Dict[str, Any]] = []
        for raw_line in completed.stdout.splitlines():
            if len(hits) >= limit:
                break
            try:
                payload = __import__("json").loads(raw_line)
            except Exception:
                continue
            if payload.get("type") != "match":
                continue
            data = payload.get("data", {}) if isinstance(payload.get("data"), dict) else {}
            path_info = data.get("path", {}) if isinstance(data.get("path"), dict) else {}
            lines_info = data.get("lines", {}) if isinstance(data.get("lines"), dict) else {}
            path_text = str(path_info.get("text") or "").strip()
            if not path_text:
                continue
            line_text = str(lines_info.get("text") or "").strip()
            line_number = int(data.get("line_number") or 0)
            score = 0.6
            lower_line = line_text.lower()
            for term, weight in term_weights.items():
                if term.lower() in lower_line:
                    score += 0.35 * weight
            hits.append(
                {
                    "file_path": self._normalize_file_path(path_text),
                    "line": line_number,
                    "text": line_text,
                    "score": score,
                }
            )
        return hits

    def _run_fast_context_for_task(
        self,
        query: str,
        term_weights: Dict[str, float],
        anchors: Dict[str, List[str]],
        *,
        max_files: int,
    ) -> FastContextResult:
        """Run the FastContext read/glob/grep explorer for task retrieval."""
        explorer = FastContextExplorer(self.project_root, file_info=self.file_info)
        return explorer.explore(
            query,
            term_weights=term_weights,
            anchors=anchors,
            max_hits=max(24, max_files * 12),
            max_files=max(8, max_files * 3),
        )

    def explore_fast_context(self, query: str, *, max_hits: int = 80, max_files: int = 20) -> FastContextResult:
        """Expose FastContext exploration for the codebase-retrieval tool."""
        query_text = str(query or "").strip()
        return FastContextExplorer(self.project_root, file_info=self.file_info).explore(
            query_text,
            term_weights=self._build_task_term_weights(query_text),
            anchors=self._extract_query_anchors(query_text),
            max_hits=max_hits,
            max_files=max_files,
        )

    @staticmethod
    def _language_for_path(file_path: str) -> str:
        suffix = Path(str(file_path or "")).suffix.lower()
        return {
            ".py": "python",
            ".js": "javascript",
            ".jsx": "javascript",
            ".ts": "typescript",
            ".tsx": "typescript",
            ".rs": "rust",
            ".go": "go",
            ".java": "java",
            ".cs": "csharp",
            ".cpp": "cpp",
            ".c": "c",
            ".h": "c",
            ".hpp": "cpp",
            ".md": "markdown",
            ".json": "json",
            ".yaml": "yaml",
            ".yml": "yaml",
            ".toml": "toml",
        }.get(suffix, suffix.lstrip(".") or "text")

    def _run_fts_for_task(self, term_weights: Dict[str, float], limit: int = 40) -> List[Dict[str, Any]]:
        """Build a small in-memory FTS index from cached summaries and keywords."""
        if not term_weights or not isinstance(self.file_info, dict) or not self.file_info:
            return []
        terms = [term for term, _ in sorted(term_weights.items(), key=lambda item: item[1], reverse=True) if len(term) >= 3][:10]
        if not terms:
            return []
        try:
            conn = sqlite3.connect(":memory:")
            conn.execute("CREATE VIRTUAL TABLE docs USING fts5(path UNINDEXED, body)")
            rows = []
            for raw_path, info in self.file_info.items():
                body_parts = [
                    str(raw_path),
                    str(self._get_file_meta(info, "summary", "") or ""),
                    " ".join(str(value) for value in self._get_file_meta(info, "keywords", []) or []),
                    " ".join(str(value) for value in self._get_file_meta(info, "symbol_names", []) or []),
                    " ".join(str(value) for value in self._get_file_meta(info, "tags", []) or []),
                ]
                rows.append((self._normalize_file_path(raw_path), " ".join(body_parts)))
            conn.executemany("INSERT INTO docs(path, body) VALUES (?, ?)", rows)
            match_query = " OR ".join(terms)
            cursor = conn.execute(
                "SELECT path, bm25(docs) AS rank FROM docs WHERE docs MATCH ? ORDER BY rank LIMIT ?",
                (match_query, int(limit)),
            )
            results = [
                {"file_path": self._normalize_file_path(path), "score": max(0.2, 2.0 - float(rank))}
                for path, rank in cursor.fetchall()
            ]
            conn.close()
            return results
        except Exception:
            return []

    def _collect_lsp_task_evidence(self, query: str, term_weights: Dict[str, float], limit: int = 20) -> List[Dict[str, Any]]:
        """Collect optional LSP workspace-symbol evidence without requiring LSP availability."""
        manager = getattr(self, "lsp_manager", None)
        if manager is None:
            manager = getattr(self, "lsp", None)
        if manager is None:
            return []
        hits: List[Dict[str, Any]] = []
        terms = [term for term, _ in sorted(term_weights.items(), key=lambda item: item[1], reverse=True) if len(term) >= 3][:5]
        for term in terms or [query]:
            try:
                symbols = manager.workspace_symbols(term, limit=max(4, limit // 2))
            except Exception:
                continue
            for item in symbols:
                if not isinstance(item, dict):
                    continue
                location = item.get("location", {}) if isinstance(item.get("location"), dict) else {}
                uri = str(location.get("uri", "") or "")
                if uri.startswith("file:///"):
                    try:
                        path = Path(uri.replace("file:///", "", 1))
                    except Exception:
                        continue
                    hits.append(
                        {
                            "file_path": self._normalize_file_path(str(path)),
                            "symbol": str(item.get("name") or ""),
                            "score": 2.0,
                        }
                    )
                    if len(hits) >= limit:
                        return hits
        return hits

    def _get_file_meta(self, info: Any, key: str, default: Any = None) -> Any:
        if isinstance(info, dict):
            return info.get(key, default)
        return getattr(info, key, default)

    def _get_file_info_record(self, file_path: str) -> Any:
        """Look up cached file metadata using raw or normalized path forms."""
        if not isinstance(self.file_info, dict):
            return None

        raw_path = str(file_path or "").strip()
        if not raw_path:
            return None

        candidates: List[str] = []
        seen: Set[str] = set()

        def add_candidate(value: Any) -> None:
            text = str(value or "").strip()
            if not text or text in seen:
                return
            seen.add(text)
            candidates.append(text)

        add_candidate(raw_path)
        try:
            path = Path(raw_path)
            add_candidate(str(path))
            if path.is_absolute():
                resolved = path.resolve()
                add_candidate(str(resolved))
                try:
                    add_candidate(str(resolved.relative_to(self.project_root)))
                except Exception:
                    pass
            else:
                project_path = self.project_root / path
                add_candidate(str(project_path))
                add_candidate(str(project_path.resolve()))
        except Exception:
            pass

        for candidate in candidates:
            info = self.file_info.get(candidate)
            if info is not None:
                return info
        return None

    def _collect_imports_for_files(self, file_paths: List[str]) -> List[Dict[str, Any]]:
        """Collect parsed imports for a set of files from cached index metadata."""
        imports: List[Dict[str, Any]] = []
        seen: Set[Any] = set()

        def freeze(value: Any) -> Any:
            if isinstance(value, dict):
                return tuple(sorted((str(k), freeze(v)) for k, v in value.items()))
            if isinstance(value, (list, tuple, set)):
                return tuple(freeze(item) for item in value)
            return value

        for file_path in file_paths:
            info = self._get_file_info_record(file_path)
            if not info:
                continue
            for item in self._get_file_meta(info, "imports", []) or []:
                if not isinstance(item, dict):
                    continue
                key = tuple(sorted((str(k), freeze(v)) for k, v in item.items()))
                if key in seen:
                    continue
                seen.add(key)
                imports.append(dict(item))
                if len(imports) >= 32:
                    return imports

        return imports
    
    def retrieve_symbol(
        self,
        query: str,
        include_dependencies: bool = True,
        include_dependents: bool = False,
        max_depth: int = 2
    ) -> Optional[SymbolContext]:
        """
        Retrieve complete context for a symbol.
        
        Args:
            query: Symbol name or qualified name
            include_dependencies: Include what this symbol depends on
            include_dependents: Include what depends on this symbol
            max_depth: How deep to traverse dependencies
        
        Returns:
            SymbolContext with the symbol and all related information
        """
        # Find the symbol
        symbol = self.symbol_table.get_symbol(query)
        if not symbol:
            # Try fuzzy search
            matches = self.symbol_table.find_by_name(query)
            if not matches:
                matches = self.symbol_table.find_by_pattern(f'*{query}*', limit=999999)
            if matches:
                symbol = matches[0]
            else:
                return None
        
        # Get parent
        parent = None
        if symbol.parent:
            parent = self.symbol_table.get_symbol(symbol.parent)
        
        # Get children
        children = self.symbol_table.get_children(symbol.qualified_name)
        
        # Get dependencies
        dependencies = []
        if include_dependencies:
            deps = self.dependency_graph.get_dependencies(
                symbol.qualified_name, depth=max_depth
            )
            for dep in deps:
                dep_symbol = self.symbol_table.get_symbol(dep.to_symbol)
                if dep_symbol:
                    dependencies.append(dep_symbol)
        
        # Get dependents
        dependents = []
        if include_dependents:
            deps = self.dependency_graph.get_dependents(
                symbol.qualified_name, depth=1
            )
            for dep in deps:
                dep_symbol = self.symbol_table.get_symbol(dep.from_symbol)
                if dep_symbol:
                    dependents.append(dep_symbol)
        
        # Get call chain
        call_chains = self.dependency_graph.get_call_chain(
            symbol.qualified_name, direction="down", max_depth=3
        )
        call_chain = call_chains[0] if call_chains else [symbol.qualified_name]
        
        # Build context string
        context_string = self._build_symbol_context_string(
            symbol, parent, children, dependencies, dependents
        )
        self.mark_symbol_activity(symbol.qualified_name, weight=1.2)
        if symbol.file_path:
            self.mark_file_activity(symbol.file_path, weight=0.8, reason="symbol_lookup")
        
        return SymbolContext(
            symbol=symbol,
            parent=parent,
            children=children,
            dependencies=dependencies,
            dependents=dependents,
            call_chain=call_chain,
            context_string=context_string
        )
    
    def retrieve_for_edit(
        self,
        file_path: str,
        start_line: int,
        end_line: int,
        intent: Optional[str] = None
    ) -> EditContext:
        """
        Prepare context for editing a specific region of code.
        
        This is called before str_replace_editor to ensure the model
        has all necessary context to make accurate edits.
        
        Args:
            file_path: Path to the file being edited
            start_line: Start line of edit region
            end_line: End line of edit region
            intent: Optional description of the edit intent
        
        Returns:
            EditContext with all context needed for the edit
        """
        # Get symbols in the target range
        all_file_symbols = self.symbol_table.get_all_in_file(file_path)
        symbols_in_range = [
            s for s in all_file_symbols
            if (s.start_line <= end_line and s.end_line >= start_line)
        ]
        
        # Get related symbols (dependencies of symbols in range)
        related_symbols = []
        seen = set()
        
        for sym in symbols_in_range:
            # Get dependencies
            deps = self.dependency_graph.get_dependencies(sym.qualified_name, depth=1)
            for dep in deps:
                if dep.to_symbol not in seen:
                    seen.add(dep.to_symbol)
                    dep_sym = self.symbol_table.get_symbol(dep.to_symbol)
                    if dep_sym and dep_sym.file_path != file_path:
                        related_symbols.append(dep_sym)
            
            # If it's a method, also get the class
            if sym.parent:
                parent = self.symbol_table.get_symbol(sym.parent)
                if parent and parent.qualified_name not in seen:
                    seen.add(parent.qualified_name)
                    related_symbols.append(parent)
        
        # Get imports from the cached parse results for the target file.
        imports = self._collect_imports_for_files([file_path])
        
        # Read target content
        target_content = self._read_file_range(file_path, start_line, end_line)
        
        # Build context string
        context_string = self._build_edit_context_string(
            file_path, start_line, end_line, target_content,
            symbols_in_range, related_symbols, intent
        )
        self.mark_file_activity(file_path, weight=1.4, reason="edit")
        for symbol in symbols_in_range[:6]:
            self.mark_symbol_activity(symbol.qualified_name, weight=1.0)
        
        return EditContext(
            target_file=file_path,
            target_lines=(start_line, end_line),
            target_content=target_content,
            symbols_in_range=symbols_in_range,
            related_symbols=related_symbols,
            imports=imports,
            context_string=context_string
        )
    
    def build_context_package(
        self,
        symbols: List[str],
        max_tokens: int = None,
        include_source: bool = True,
        include_dependencies: bool = True,
        relevance_boost: Optional[Dict[str, float]] = None,
        prioritize_game_code: bool = True
    ) -> ContextPackage:
        """
        Build a "minimal but complete" context package.
        
        This is the core method that ensures the model gets exactly
        the context it needs - no more, no less.
        
        Args:
            symbols: List of symbol names/qualified names to include
            max_tokens: Maximum token budget
            include_source: Include source code
            include_dependencies: Auto-expand dependencies
            relevance_boost: Optional relevance scores for prioritization
            prioritize_game_code: Prioritize game logic symbols over utility code
        
        Returns:
            ContextPackage ready for model consumption
        """
        max_tokens = max_tokens or self.DEFAULT_TOKEN_BUDGET
        
        # Resolve all symbols
        resolved_symbols = []
        for sym_query in symbols:
            sym = self.symbol_table.get_symbol(sym_query)
            if not sym:
                matches = self.symbol_table.find_by_name(sym_query)
                if matches:
                    sym = matches[0]
            if sym:
                resolved_symbols.append(sym)
        
        # Expand dependencies
        if include_dependencies:
            expanded = set(s.qualified_name for s in resolved_symbols)
            for sym in list(resolved_symbols):
                deps = self.dependency_graph.get_dependencies(sym.qualified_name, depth=1)
                for dep in deps:  # No limit expansion
                    if dep.to_symbol not in expanded:
                        expanded.add(dep.to_symbol)
                        dep_sym = self.symbol_table.get_symbol(dep.to_symbol)
                        if dep_sym:
                            resolved_symbols.append(dep_sym)
        
        # Apply game code prioritization if enabled
        if prioritize_game_code:
            resolved_symbols = self.prioritize_game_symbols(resolved_symbols)
        
        # Score and rank symbols
        scored_symbols = self._score_symbols(resolved_symbols, relevance_boost)
        
        # Build context within token budget
        context_parts = []
        included_symbols = []
        current_tokens = 0
        
        for score, sym in sorted(scored_symbols, key=lambda x: -x[0]):
            sym_context = sym.get_context_string(include_source=include_source)
            sym_tokens = int(len(sym_context) * self.TOKENS_PER_CHAR)
            
            if current_tokens + sym_tokens > max_tokens:
                # Try without source
                sym_context = sym.get_context_string(include_source=False)
                sym_tokens = int(len(sym_context) * self.TOKENS_PER_CHAR)
                
                if current_tokens + sym_tokens > max_tokens:
                    continue
            
            context_parts.append(sym_context)
            included_symbols.append(sym)
            current_tokens += sym_tokens
        
        # Get file contents for included symbols
        file_contents = {}
        for sym in included_symbols:
            if sym.file_path not in file_contents:
                content = self._read_file(sym.file_path)
                if content:
                    file_contents[sym.file_path] = content
        
        # Get dependencies between included symbols
        included_names = {s.qualified_name for s in included_symbols}
        dependencies = []
        for sym in included_symbols:
            deps = self.dependency_graph.get_dependencies(sym.qualified_name, depth=1)
            for dep in deps:
                if dep.to_symbol in included_names:
                    dependencies.append((
                        dep.from_symbol,
                        dep.to_symbol,
                        dep.dep_type.name
                    ))
        
        # Build final context string
        context_string = self._format_context_package(
            included_symbols, dependencies, context_parts
        )
        
        imports = self._collect_imports_for_files(
            [sym.file_path for sym in included_symbols if sym.file_path]
        )

        return ContextPackage(
            symbols=included_symbols,
            dependencies=dependencies,
            file_contents=file_contents,
            imports=imports,
            context_string=context_string,
            token_estimate=current_tokens,
            metadata={
                'requested_symbols': symbols,
                'symbols_included': len(included_symbols),
                'token_budget': max_tokens,
                'tokens_used': current_tokens,
                'game_prioritization': prioritize_game_code
            }
        )

    def retrieve_for_task(
        self,
        query: str,
        *,
        max_tokens: int = 12000,
        max_files: int = 6,
        max_symbols: int = 12,
        include_history: bool = True,
        include_memory: bool = True,
        active_files: Optional[List[str]] = None,
        changed_files: Optional[List[str]] = None,
    ) -> TaskContextResult:
        """
        Build a task-oriented context bundle.

        This mimics a modern Context Engine workflow: combine lexical signals,
        file summaries, recent activity, dependency expansion, memory, and git
        history into a curated context package for the active request.
        """
        query_text = str(query or "").strip()
        max_tokens = max(1000, int(max_tokens or 12000))
        max_files = max(1, int(max_files or 6))
        max_symbols = max(1, int(max_symbols or 12))
        term_weights = self._build_task_term_weights(query_text)
        anchors = self._extract_query_anchors(query_text)
        anchor_file_terms = {item.lower().replace("\\", "/") for item in anchors.get("files", [])}
        anchor_symbol_terms = {item.lower() for item in anchors.get("symbols", [])}

        cache_key = (
            query_text.lower(),
            max_tokens,
            max_files,
            max_symbols,
            bool(include_history),
            bool(include_memory),
            tuple(sorted(str(path or "").strip() for path in (active_files or []) if str(path or "").strip())),
            tuple(sorted(str(path or "").strip() for path in (changed_files or []) if str(path or "").strip())),
            len(self.file_info) if isinstance(self.file_info, dict) else 0,
            len(self.symbol_table),
            tuple(sorted(anchor_file_terms)),
            tuple(sorted(anchor_symbol_terms)),
        )
        cached_entry = self._task_cache.get(cache_key)
        now = time.time()
        if cached_entry and (now - cached_entry[0]) <= 15.0:
            return cached_entry[1]

        normalized_active_files = {
            self._normalize_file_path(path)
            for path in (active_files or [])
            if str(path or "").strip()
        }
        normalized_changed_files = {
            self._normalize_file_path(path)
            for path in (changed_files or [])
            if str(path or "").strip()
        }
        if not normalized_changed_files and self.git_integration and getattr(self.git_integration, "is_available", False):
            try:
                dirty = self.git_integration.get_uncommitted_changes()
            except Exception:
                dirty = {}
            for group in ("modified", "added", "deleted", "untracked"):
                for path in dirty.get(group, []) or []:
                    normalized_changed_files.add(self._normalize_file_path(path))

        evidence_by_file: Dict[str, List[Dict[str, Any]]] = {}
        fast_context_result: Optional[FastContextResult] = None
        for path in normalized_active_files:
            self._merge_file_evidence(evidence_by_file, path, source="activity", reason="active_file", score=2.2)
        for path in normalized_changed_files:
            self._merge_file_evidence(evidence_by_file, path, source="git", reason="uncommitted_change", score=1.9)

        file_candidates: List[TaskContextFile] = []
        seen_file_candidates: Set[str] = set()
        for raw_path, info in list((self.file_info or {}).items()):
            file_path = self._normalize_file_path(raw_path)
            candidate = self._score_file_for_task(
                file_path=file_path,
                info=info,
                term_weights=term_weights,
                active_files=normalized_active_files,
                changed_files=normalized_changed_files,
                query_text=query_text,
                anchor_file_terms=anchor_file_terms,
            )
            if candidate and file_path not in seen_file_candidates:
                for reason in candidate.reasons:
                    self._merge_file_evidence(evidence_by_file, file_path, source="index", reason=reason, score=candidate.score)
                file_candidates.append(candidate)
                seen_file_candidates.add(file_path)

        for anchor in anchor_file_terms:
            for raw_path, info in list((self.file_info or {}).items()):
                file_path = self._normalize_file_path(raw_path)
                normalized = file_path.lower().replace("\\", "/")
                if anchor not in normalized and Path(normalized).name != anchor:
                    continue
                if file_path in seen_file_candidates:
                    continue
                candidate = self._score_file_for_task(
                    file_path=file_path,
                    info=info,
                    term_weights=term_weights,
                    active_files=normalized_active_files,
                    changed_files=normalized_changed_files,
                    base_score=6.0,
                    reason_override=f"anchor-file:{anchor}",
                    query_text=query_text,
                    anchor_file_terms=anchor_file_terms,
                )
                if candidate:
                    self._merge_file_evidence(evidence_by_file, file_path, source="anchor", reason=f"anchor-file:{anchor}", score=candidate.score)
                    file_candidates.append(candidate)
                    seen_file_candidates.add(file_path)

        for hit in self._run_fts_for_task(term_weights, limit=max_files * 8):
            file_path = self._normalize_file_path(hit.get("file_path", ""))
            if not file_path:
                continue
            self._merge_file_evidence(evidence_by_file, file_path, source="fts", reason="summary_keyword_match", score=float(hit.get("score", 0.0)))
            if file_path in seen_file_candidates:
                continue
            info = self._get_file_info_record(file_path)
            candidate = self._score_file_for_task(
                file_path=file_path,
                info=info,
                term_weights=term_weights,
                active_files=normalized_active_files,
                changed_files=normalized_changed_files,
                base_score=float(hit.get("score", 0.0)),
                reason_override="fts:summary_keyword_match",
                query_text=query_text,
                anchor_file_terms=anchor_file_terms,
            )
            if candidate:
                file_candidates.append(candidate)
                seen_file_candidates.add(file_path)

        try:
            fast_context_result = self._run_fast_context_for_task(
                query_text,
                term_weights,
                anchors,
                max_files=max_files,
            )
        except Exception:
            fast_context_result = None

        for hit in (fast_context_result.hits if fast_context_result else []):
            file_path = self._normalize_file_path(hit.file_path)
            if not file_path:
                continue
            self._merge_file_evidence(
                evidence_by_file,
                file_path,
                source=f"fastcontext:{hit.source}",
                reason=hit.reason,
                score=float(hit.score),
                line=hit.line_start or None,
                line_end=hit.line_end or None,
                detail=hit.snippet,
            )
            if file_path in seen_file_candidates:
                continue
            info = self._get_file_info_record(file_path)
            candidate = self._score_file_for_task(
                file_path=file_path,
                info=info,
                term_weights=term_weights,
                active_files=normalized_active_files,
                changed_files=normalized_changed_files,
                base_score=float(hit.score),
                reason_override=f"fastcontext:{hit.source}",
                query_text=query_text,
                anchor_file_terms=anchor_file_terms,
            )
            if candidate is None and Path(file_path).is_file():
                candidate = TaskContextFile(
                    file_path=file_path,
                    language=self._language_for_path(file_path),
                    score=max(0.3, float(hit.score)),
                    summary=f"FastContext {hit.source} evidence for {query_text[:80]}",
                    reasons=[f"fastcontext:{hit.source}", hit.reason],
                    top_symbols=[],
                    tags=["fastcontext"],
                )
            if candidate:
                file_candidates.append(candidate)
                seen_file_candidates.add(file_path)

        for hit in self._run_ripgrep_for_task(query_text, term_weights, limit=max_files * 10):
            file_path = self._normalize_file_path(hit.get("file_path", ""))
            if not file_path:
                continue
            self._merge_file_evidence(
                evidence_by_file,
                file_path,
                source="ripgrep",
                reason="line_match",
                score=float(hit.get("score", 0.0)),
                line=hit.get("line"),
                detail=str(hit.get("text", "")),
            )
            if file_path in seen_file_candidates:
                continue
            info = self._get_file_info_record(file_path)
            candidate = self._score_file_for_task(
                file_path=file_path,
                info=info,
                term_weights=term_weights,
                active_files=normalized_active_files,
                changed_files=normalized_changed_files,
                base_score=float(hit.get("score", 0.0)),
                reason_override="rg:line_match",
                query_text=query_text,
                anchor_file_terms=anchor_file_terms,
            )
            if candidate:
                file_candidates.append(candidate)
                seen_file_candidates.add(file_path)

        for hit in self._collect_lsp_task_evidence(query_text, term_weights, limit=max_files * 4):
            file_path = self._normalize_file_path(hit.get("file_path", ""))
            if not file_path:
                continue
            symbol_name = str(hit.get("symbol", "") or "").strip()
            reason = f"lsp:{symbol_name}" if symbol_name else "lsp:workspace_symbol"
            self._merge_file_evidence(evidence_by_file, file_path, source="lsp", reason=reason, score=float(hit.get("score", 0.0)))
            if file_path in seen_file_candidates:
                continue
            info = self._get_file_info_record(file_path)
            candidate = self._score_file_for_task(
                file_path=file_path,
                info=info,
                term_weights=term_weights,
                active_files=normalized_active_files,
                changed_files=normalized_changed_files,
                base_score=float(hit.get("score", 0.0)),
                reason_override=reason,
                query_text=query_text,
                anchor_file_terms=anchor_file_terms,
            )
            if candidate:
                file_candidates.append(candidate)
                seen_file_candidates.add(file_path)

        file_candidates.sort(key=lambda item: item.score, reverse=True)
        selected_files: Dict[str, TaskContextFile] = {
            item.file_path: item for item in file_candidates[:max_files]
        }

        symbol_scores: Dict[str, float] = defaultdict(float)
        symbol_reasons: Dict[str, Set[str]] = defaultdict(set)
        for term, weight in term_weights.items():
            for symbol in self.symbol_table.search(term, limit=max_symbols * 6):
                symbol_scores[symbol.qualified_name] += self._score_symbol_for_task(symbol, term, weight)
                symbol_reasons[symbol.qualified_name].add(f"term:{term}")
        for anchor in anchor_symbol_terms:
            for symbol in self.symbol_table.search(anchor, limit=max_symbols * 4):
                symbol_scores[symbol.qualified_name] += 7.5
                symbol_reasons[symbol.qualified_name].add(f"anchor-symbol:{anchor}")

        for file_candidate in file_candidates[: max_files * 2]:
            file_symbols = self.symbol_table.get_all_in_file(file_candidate.file_path)
            for symbol in file_symbols[:8]:
                boost = max(0.4, file_candidate.score * 0.22)
                if any(term in symbol.qualified_name.lower() or term in symbol.name.lower() for term in term_weights):
                    boost += 0.8
                symbol_scores[symbol.qualified_name] += boost
                symbol_reasons[symbol.qualified_name].add("matched-file")

        ranked_symbols = sorted(symbol_scores.items(), key=lambda item: item[1], reverse=True)
        expanded_symbols: Dict[str, float] = dict(symbol_scores)
        for qualified_name, base_score in ranked_symbols[: max(4, max_symbols // 2)]:
            for related_name, distance, dep_type in self.dependency_graph.get_related_symbols(
                qualified_name,
                max_distance=2,
                max_results=16,
            ):
                if related_name == qualified_name:
                    continue
                expanded_symbols[related_name] = max(
                    expanded_symbols.get(related_name, 0.0),
                    max(0.35, base_score * (0.55 / max(distance, 1))),
                )
                symbol_reasons[related_name].add(f"graph:{dep_type.name.lower()}")

        selected_symbols: List[Symbol] = []
        for qualified_name, _ in sorted(expanded_symbols.items(), key=lambda item: item[1], reverse=True):
            symbol = self.symbol_table.get_symbol(qualified_name)
            if not symbol:
                continue
            selected_symbols.append(symbol)
            normalized_symbol_file = self._normalize_file_path(symbol.file_path) if symbol.file_path else ""
            if normalized_symbol_file and normalized_symbol_file not in selected_files and len(selected_files) < max_files:
                info = (self.file_info or {}).get(symbol.file_path) or (self.file_info or {}).get(normalized_symbol_file)
                selected_files[normalized_symbol_file] = self._score_file_for_task(
                    file_path=normalized_symbol_file,
                    info=info,
                    term_weights=term_weights,
                    active_files=normalized_active_files,
                    changed_files=normalized_changed_files,
                    base_score=max(0.5, expanded_symbols.get(qualified_name, 0.0) * 0.5),
                    reason_override=f"symbol:{symbol.name}",
                    query_text=query_text,
                    anchor_file_terms=anchor_file_terms,
                ) or TaskContextFile(
                    file_path=normalized_symbol_file,
                    language=symbol.language,
                    score=max(0.5, expanded_symbols.get(qualified_name, 0.0)),
                    summary=f"Relevant symbol {symbol.qualified_name}",
                    reasons=[f"symbol:{symbol.name}"],
                    top_symbols=[symbol.qualified_name],
                    tags=[],
                )
            if len(selected_symbols) >= max_symbols:
                break

        selected_file_list = sorted(selected_files.values(), key=lambda item: item.score, reverse=True)[:max_files]
        workspace_profile = detect_workspace_profile(
            self.project_root,
            focus_files=[item.file_path for item in selected_file_list],
        )
        for item in selected_file_list:
            item.evidence = sorted(
                evidence_by_file.get(item.file_path, []),
                key=lambda evidence: float(evidence.get("score", 0.0)),
                reverse=True,
            )[:8]
            file_symbols = [symbol for symbol in selected_symbols if symbol.file_path == item.file_path][:3]
            item.excerpt = self._build_file_excerpt(item.file_path, file_symbols, term_weights=term_weights)

        memory_fragments: List[Dict[str, str]] = []
        if include_memory and self.memory_indexer:
            try:
                memory_hits = self.memory_indexer.search(query_text, max_results=4, max_tokens=max_tokens // 5)
            except Exception:
                memory_hits = []
            for fragment in memory_hits:
                memory_fragments.append({
                    "session_id": str(getattr(fragment, "session_id", "")),
                    "role": str(getattr(fragment, "role", "")),
                    "content": str(getattr(fragment, "content", "")),
                })

        commit_context: List[Dict[str, Any]] = []
        if include_history and self.git_integration and getattr(self.git_integration, "is_available", False):
            seen_commits: Set[str] = set()
            commit_candidates: List[Any] = []
            try:
                commit_candidates.extend(self.git_integration.search_commits(query_text, limit=3))
            except Exception:
                pass
            for file_candidate in selected_file_list[:3]:
                try:
                    commit_candidates.extend(self.git_integration.get_file_history(file_candidate.file_path, limit=2))
                except Exception:
                    continue
            for commit in sorted(
                commit_candidates,
                key=lambda item: getattr(item, "date", 0),
                reverse=True,
            ):
                commit_hash = str(getattr(commit, "hash", ""))
                if not commit_hash or commit_hash in seen_commits:
                    continue
                seen_commits.add(commit_hash)
                commit_context.append({
                    "hash": str(getattr(commit, "short_hash", commit_hash[:7])),
                    "date": getattr(getattr(commit, "date", None), "isoformat", lambda: "")(),
                    "message": str(getattr(commit, "message", "")),
                    "files_changed": list(getattr(commit, "files_changed", [])[:6]),
                    "source": "git_history",
                })
                if len(commit_context) >= 5:
                    break

        context_string, token_estimate = self._format_task_context(
            query_text,
            selected_file_list,
            selected_symbols,
            memory_fragments,
            commit_context,
            workspace_profile=workspace_profile,
            max_tokens=max_tokens,
        )

        for file_candidate in selected_file_list[:4]:
            self.mark_file_activity(file_candidate.file_path, weight=1.0, reason="task")
        for symbol in selected_symbols[:8]:
            self.mark_symbol_activity(symbol.qualified_name, weight=0.8)

        result = TaskContextResult(
            query=query_text,
            relevant_symbols=selected_symbols,
            relevant_files=selected_file_list,
            memory_fragments=memory_fragments,
            commit_context=commit_context,
            context_string=context_string,
            token_estimate=token_estimate,
            workspace_profile=workspace_profile,
            metadata={
                "term_weights": term_weights,
                "active_files": sorted(normalized_active_files),
                "changed_files": sorted(normalized_changed_files),
                "selected_file_count": len(selected_file_list),
                "selected_symbol_count": len(selected_symbols),
                "workspace": workspace_profile.to_dict(),
                "evidence_sources": sorted(
                    {
                        str(evidence.get("source"))
                        for item in selected_file_list
                        for evidence in item.evidence
                        if evidence.get("source")
                    }
                ),
                "fast_context": fast_context_result.to_dict() if fast_context_result else {},
            },
        )
        self._task_cache[cache_key] = (now, result)
        if len(self._task_cache) > 24:
            oldest_key = min(self._task_cache.items(), key=lambda item: item[1][0])[0]
            self._task_cache.pop(oldest_key, None)
        return result

    def _score_file_for_task(
        self,
        *,
        file_path: str,
        info: Any,
        term_weights: Dict[str, float],
        active_files: Set[str],
        changed_files: Set[str],
        base_score: float = 0.0,
        reason_override: Optional[str] = None,
        query_text: str = "",
        anchor_file_terms: Optional[Set[str]] = None,
    ) -> Optional[TaskContextFile]:
        """Score a cached file record for a task-oriented retrieval request."""
        if info is None:
            return None

        summary = str(self._get_file_meta(info, "summary", "") or "")
        keywords = [str(value).lower() for value in self._get_file_meta(info, "keywords", [])]
        tags = [str(value).lower() for value in self._get_file_meta(info, "tags", [])]
        symbol_names = [str(value).lower() for value in self._get_file_meta(info, "symbol_names", [])]
        imports = self._get_file_meta(info, "imports", []) or []
        import_names = []
        for item in imports:
            if isinstance(item, dict):
                import_names.append(str(item.get("module") or item.get("name") or item.get("path") or "").lower())
        path_lower = file_path.lower().replace("\\", "/")
        summary_lower = summary.lower()
        anchor_file_terms = anchor_file_terms or set()

        score = float(base_score)
        reasons: List[str] = [reason_override] if reason_override else []
        for anchor in anchor_file_terms:
            anchor_lower = str(anchor or "").lower().replace("\\", "/")
            if not anchor_lower:
                continue
            if anchor_lower in path_lower or Path(path_lower).name == anchor_lower:
                score += 8.0
                reasons.append(f"anchor-file:{anchor_lower}")
        for term, weight in term_weights.items():
            term_lower = term.lower()
            if term_lower in keywords:
                score += 2.6 * weight
                reasons.append(f"keyword:{term_lower}")
            if term_lower in path_lower:
                score += 2.2 * weight
                reasons.append(f"path:{term_lower}")
            if term_lower in summary_lower:
                score += 1.8 * weight
                reasons.append(f"summary:{term_lower}")
            if any(term_lower in name for name in symbol_names):
                score += 1.7 * weight
                reasons.append(f"symbol:{term_lower}")
            if any(term_lower in name for name in import_names):
                score += 1.2 * weight
                reasons.append(f"import:{term_lower}")
            if any(term_lower == tag or term_lower in tag for tag in tags):
                score += 1.1 * weight
                reasons.append(f"tag:{term_lower}")

        role_boost, role_reasons = self._query_role_boost(file_path, tags, query_text)
        if role_boost:
            score += role_boost
            reasons.extend(role_reasons)

        content_boost, content_reasons = self._score_file_content_for_task(file_path, term_weights)
        if content_boost:
            score += content_boost
            reasons.extend(content_reasons)

        activity = self._activity_boost(self._activity_files.get(file_path))
        if file_path in active_files:
            activity += 2.2
        if file_path in changed_files:
            activity += 1.9
        if activity > 0:
            score += activity
            reasons.append("active-workset")

        if score <= 0.0:
            return None

        unique_reasons: List[str] = []
        seen: Set[str] = set()
        for reason in reasons:
            text = str(reason or "").strip()
            if not text or text in seen:
                continue
            seen.add(text)
            unique_reasons.append(text)

        return TaskContextFile(
            file_path=file_path,
            language=str(self._get_file_meta(info, "language", "unknown")),
            score=score,
            summary=summary or f"Relevant file {Path(file_path).name}",
            reasons=unique_reasons[:6],
            top_symbols=list(self._get_file_meta(info, "top_level_symbols", [])[:6]),
            tags=tags[:6],
        )

    def _score_symbol_for_task(self, symbol: Symbol, term: str, weight: float) -> float:
        """Score a symbol match for task-level retrieval."""
        term_lower = term.lower()
        qname_lower = symbol.qualified_name.lower()
        name_lower = symbol.name.lower()
        score = 0.0
        if name_lower == term_lower:
            score += 5.0 * weight
        elif name_lower.startswith(term_lower):
            score += 3.6 * weight
        elif term_lower in name_lower:
            score += 2.8 * weight
        elif term_lower in qname_lower:
            score += 2.0 * weight
        file_boost = self._activity_boost(self._activity_files.get(self._normalize_file_path(symbol.file_path)))
        symbol_boost = self._activity_boost(self._activity_symbols.get(symbol.qualified_name))
        kind_boost = {
            SymbolKind.CLASS: 1.3,
            SymbolKind.FUNCTION: 1.2,
            SymbolKind.METHOD: 1.15,
            SymbolKind.MODULE: 1.1,
        }.get(symbol.kind, 1.0)
        return (score + file_boost + symbol_boost) * kind_boost

    def _build_file_excerpt(
        self,
        file_path: str,
        symbols: List[Symbol],
        *,
        term_weights: Optional[Dict[str, float]] = None,
    ) -> str:
        """Build a compact file excerpt focused on the most relevant symbols."""
        if symbols:
            parts: List[str] = []
            for index, symbol in enumerate(symbols[:2]):
                include_source = index == 0
                parts.append(symbol.get_context_string(include_source=include_source))
            return "\n\n".join(parts).strip()

        try:
            with open(file_path, 'r', encoding='utf-8', errors='ignore') as handle:
                lines = handle.readlines()
        except Exception:
            return ""

        terms = [
            term.lower()
            for term, _ in sorted((term_weights or {}).items(), key=lambda item: item[1], reverse=True)
            if len(str(term or "")) >= 3
        ][:8]
        if terms:
            windows: List[Tuple[int, int]] = []
            for index, line in enumerate(lines):
                lower_line = line.lower()
                if not any(term in lower_line for term in terms):
                    continue
                start = max(0, index - 4)
                end = min(len(lines), index + 8)
                if windows and start <= windows[-1][1] + 2:
                    windows[-1] = (windows[-1][0], max(windows[-1][1], end))
                else:
                    windows.append((start, end))
                if len(windows) >= 3:
                    break
            if windows:
                parts = []
                for start, end in windows:
                    parts.append(f"# lines {start + 1}-{end}")
                    parts.extend(f"{line_no:4d} | {lines[line_no - 1].rstrip()}" for line_no in range(start + 1, end + 1))
                return "\n".join(parts).strip()

        excerpt = "".join(lines[: min(len(lines), 40)]).strip()
        return excerpt

    def _format_task_context(
        self,
        query: str,
        relevant_files: List[TaskContextFile],
        relevant_symbols: List[Symbol],
        memory_fragments: List[Dict[str, str]],
        commit_context: List[Dict[str, Any]],
        *,
        workspace_profile: Optional[WorkspaceProfile] = None,
        max_tokens: int,
    ) -> Tuple[str, int]:
        """Render the final task context string while respecting a token budget."""
        parts: List[str] = [
            "=" * 60,
            "TASK CONTEXT",
            f"Request: {query}",
            f"Files selected: {len(relevant_files)}",
            f"Symbols selected: {len(relevant_symbols)}",
            "=" * 60,
            "",
        ]
        if workspace_profile:
            parts.extend(
                [
                    "--- WORKSPACE ---",
                    f"Root: {workspace_profile.root}",
                    f"VCS root: {workspace_profile.vcs_root or '(none detected)'}",
                    f"Languages: {', '.join(workspace_profile.languages) if workspace_profile.languages else 'unknown'}",
                ]
            )
            if workspace_profile.project_boundaries:
                parts.append("Project boundaries:")
                for boundary in workspace_profile.project_boundaries[:8]:
                    markers = ", ".join(boundary.markers[:4])
                    parts.append(f"- {boundary.kind}: {boundary.root} ({markers})")
            if workspace_profile.instruction_layers:
                parts.append("")
                parts.append("--- PROJECT INSTRUCTIONS ---")
                for layer in workspace_profile.instruction_layers[:6]:
                    compact = " ".join(layer.excerpt.split())
                    compact = compact[:420] + ("..." if len(compact) > 420 else "")
                    parts.append(f"- {layer.path} [scope={layer.scope or '.'}] {compact}")
        parts.append("")
        parts.append("--- FILE PRIORITIES ---")
        for item in relevant_files:
            reason_text = ", ".join(item.reasons) if item.reasons else "relevance"
            parts.append(
                f"- {item.file_path} [score={item.score:.2f}] ({item.language}) :: {item.summary} :: reasons={reason_text}"
            )
            for evidence in item.evidence[:4]:
                line = f"  evidence: {evidence.get('source')}:{evidence.get('reason')}"
                if evidence.get("line"):
                    line_end = evidence.get("line_end") or evidence.get("line")
                    if line_end and line_end != evidence.get("line"):
                        line += f":{evidence.get('line')}-{line_end}"
                    else:
                        line += f":{evidence.get('line')}"
                if evidence.get("detail"):
                    line += f" :: {evidence.get('detail')}"
                parts.append(line)

        if relevant_symbols:
            parts.append("")
            parts.append("--- SYMBOL PRIORITIES ---")
            for symbol in relevant_symbols[:12]:
                parts.append(f"- {symbol.kind.name}: {symbol.qualified_name} ({symbol.file_path}:{symbol.start_line})")

        if memory_fragments:
            parts.append("")
            parts.append("--- WORKSPACE MEMORY ---")
            for fragment in memory_fragments[:4]:
                compact = " ".join(str(fragment.get("content", "")).split())
                compact = compact[:260] + ("..." if len(compact) > 260 else "")
                parts.append(f"- [{fragment.get('role', '')}] {compact}")

        if commit_context:
            parts.append("")
            parts.append("--- RECENT HISTORY ---")
            for commit in commit_context[:5]:
                files_changed = ", ".join(commit.get("files_changed", [])[:4])
                detail = f" | files: {files_changed}" if files_changed else ""
                parts.append(f"- {commit.get('hash', '')} {commit.get('message', '')}{detail}")

        current_text = "\n".join(parts)
        current_tokens = int(len(current_text) * self.TOKENS_PER_CHAR)
        if relevant_files:
            parts.append("")
            parts.append("--- CURATED EXCERPTS ---")

        for item in relevant_files:
            section_lines = [f"### {item.file_path}"]
            if item.tags:
                section_lines.append(f"Tags: {', '.join(item.tags)}")
            if item.summary:
                section_lines.append(f"Summary: {item.summary}")
            if item.excerpt:
                language = item.language or ""
                section_lines.append(f"```{language}\n{item.excerpt}\n```")
            section = "\n".join(section_lines)
            section_tokens = int(len(section) * self.TOKENS_PER_CHAR)
            if current_tokens + section_tokens > max_tokens:
                trimmed = "\n".join(section_lines[:3])
                trimmed_tokens = int(len(trimmed) * self.TOKENS_PER_CHAR)
                if current_tokens + trimmed_tokens > max_tokens:
                    break
                parts.append(trimmed)
                current_tokens += trimmed_tokens
            else:
                parts.append(section)
                current_tokens += section_tokens

        final_text = "\n".join(parts).strip()
        return final_text, int(len(final_text) * self.TOKENS_PER_CHAR)
    
    def search(
        self,
        query: str,
        kinds: Optional[List[str]] = None,
        file_pattern: Optional[str] = None,
        limit: int = 999999
    ) -> List[Any]:
        """
        Search for symbols matching a query.
        
        Args:
            query: Search query (supports wildcards)
            kinds: Filter by symbol kinds
            file_pattern: Filter by file path pattern
            limit: Maximum results
        
        Returns:
            List of matching symbols
        """
        return self.symbol_table.search(query, kinds, file_pattern, limit)
    
    def get_file_outline(self, file_path: str) -> List[Symbol]:
        """Get outline of a file (all top-level symbols)"""
        self.mark_file_activity(file_path, weight=0.8, reason="outline")
        return self.symbol_table.get_all_in_file(file_path)
    
    def get_directory_structure(self, path: Optional[str] = None) -> Dict:
        """Get directory structure with file counts by type"""
        root = Path(path) if path else self.project_root
        
        structure = {
            'name': root.name,
            'path': str(root),
            'type': 'directory',
            'children': []
        }
        
        try:
            for item in sorted(root.iterdir()):
                if item.name.startswith('.'):
                    continue
                
                if item.is_dir():
                    structure['children'].append({
                        'name': item.name,
                        'path': str(item),
                        'type': 'directory'
                    })
                else:
                    symbols = self.symbol_table.get_all_in_file(str(item))
                    structure['children'].append({
                        'name': item.name,
                        'path': str(item),
                        'type': 'file',
                        'symbols': len(symbols)
                    })
        except Exception:
            pass
        
        return structure
    
    def _score_symbols(
        self,
        symbols: List[Symbol],
        boost: Optional[Dict[str, float]] = None
    ) -> List[Tuple[float, Symbol]]:
        """Score symbols by relevance"""
        scored = []
        
        for sym in symbols:
            score = 1.0
            
            # Kind-based scoring
            if sym.kind in (SymbolKind.CLASS, SymbolKind.INTERFACE):
                score *= 1.5
            elif sym.kind == SymbolKind.FUNCTION:
                score *= 1.3
            elif sym.kind == SymbolKind.METHOD:
                score *= 1.2
            
            # Boost if has docstring
            if sym.docstring:
                score *= 1.2
            
            # Boost if has type annotations
            if sym.type_annotation or sym.return_type:
                score *= 1.1

            # Apply custom boost
            if boost and sym.qualified_name in boost:
                score *= boost[sym.qualified_name]
            
            scored.append((score, sym))
        
        return scored
    
    def _is_game_logic_symbol(self, symbol: Symbol) -> bool:
        """Check if a symbol is related to game logic"""
        name_lower = symbol.name.lower()
        qname_lower = symbol.qualified_name.lower()
        
        # Check if name contains game logic keywords
        for keyword in self.GAME_LOGIC_KEYWORDS:
            if keyword in name_lower or keyword in qname_lower:
                return True
        
        # Check file path for game-related directories
        if symbol.file_path:
            path_lower = symbol.file_path.lower()
            game_dirs = ['game', 'gameplay', 'entities', 'components', 'systems', 
                        'scenes', 'levels', 'characters', 'enemies', 'items']
            for game_dir in game_dirs:
                if f'/{game_dir}/' in path_lower or f'\\{game_dir}\\' in path_lower:
                    return True
        
        # Check for game-specific languages
        if symbol.language in {'lua', 'gdscript'}:
            return True
        
        return False
    
    def _calculate_game_priority_score(self, symbol: Symbol) -> float:
        """Calculate priority score for game-related symbols (higher = more important)"""
        score = 1.0
        
        # Base boost for game logic symbols
        if self._is_game_logic_symbol(symbol):
            score *= 2.0
        
        # Extra boost for core game loop functions
        name_lower = symbol.name.lower()
        if name_lower in {'update', 'draw', 'render', '_process', '_physics_process', 'tick'}:
            score *= 3.0
        
        # Boost for entity/component systems
        if any(keyword in name_lower for keyword in ['entity', 'component', 'system']):
            score *= 2.5
        
        # Boost for player-related code
        if 'player' in name_lower:
            score *= 2.0
        
        # Boost for game state management
        if any(keyword in name_lower for keyword in ['state', 'scene', 'level']):
            score *= 1.8
        
        # Boost for RPG-specific code
        if any(keyword in name_lower for keyword in ['quest', 'npc', 'dialog', 'inventory', 'battle']):
            score *= 1.7
        
        # Boost for game-specific file types
        if symbol.language in {'lua', 'gdscript'}:
            score *= 1.5
        
        return score
    
    def prioritize_game_symbols(self, symbols: List[Symbol]) -> List[Symbol]:
        """
        Sort symbols by game logic priority.
        
        Game-related symbols are prioritized higher than utility/helper code.
        """
        scored_symbols = []
        
        for symbol in symbols:
            priority_score = self._calculate_game_priority_score(symbol)
            scored_symbols.append((priority_score, symbol))
        
        # Sort by score (descending)
        scored_symbols.sort(key=lambda x: x[0], reverse=True)
        
        return [sym for _, sym in scored_symbols]
    
    def _build_symbol_context_string(
        self,
        symbol: Symbol,
        parent: Optional[Symbol],
        children: List[Symbol],
        dependencies: List[Symbol],
        dependents: List[Symbol]
    ) -> str:
        """Build context string for a symbol"""
        parts = []
        
        parts.append("=" * 60)
        parts.append(f"SYMBOL: {symbol.qualified_name}")
        parts.append("=" * 60)
        
        # Main symbol
        parts.append(symbol.get_context_string())
        
        # Parent context
        if parent:
            parts.append("\n--- PARENT ---")
            parts.append(parent.get_context_string(include_source=False))
        
        # Children (methods, nested classes)
        if children:
            parts.append("\n--- CHILDREN ---")
            for child in children:
                parts.append(f"- {child.qualified_name} ({child.kind.name})")
                if child.signature:
                    parts.append(f"  {child.signature}")
        
        # Dependencies (what it uses)
        if dependencies:
            parts.append("\n--- DEPENDENCIES (what it uses) ---")
            for dep in dependencies:
                parts.append(dep.get_context_string(include_source=False, max_lines=10))
        
        # Dependents (what uses it)
        if dependents:
            parts.append("\n--- DEPENDENTS (what uses it) ---")
            for dep in dependents:
                parts.append(f"- {dep.qualified_name} ({dep.file_path}:{dep.start_line})")
        
        parts.append("=" * 60)
        
        return '\n'.join(parts)
    
    def _build_edit_context_string(
        self,
        file_path: str,
        start_line: int,
        end_line: int,
        target_content: str,
        symbols_in_range: List[Symbol],
        related_symbols: List[Symbol],
        intent: Optional[str]
    ) -> str:
        """Build context string for an edit operation"""
        parts = []
        
        parts.append("=" * 60)
        parts.append("EDIT CONTEXT")
        parts.append("=" * 60)
        
        if intent:
            parts.append(f"\nIntent: {intent}")
        
        parts.append(f"\nFile: {file_path}")
        parts.append(f"Lines: {start_line}-{end_line}")
        
        # Target content
        parts.append("\n--- TARGET CODE ---")
        for i, line in enumerate(target_content.split('\n'), start=start_line):
            parts.append(f"{i:4d} | {line}")
        
        # Symbols in range
        if symbols_in_range:
            parts.append("\n--- SYMBOLS IN RANGE ---")
            for sym in symbols_in_range:
                parts.append(f"- {sym.kind.name}: {sym.qualified_name}")
                if sym.signature:
                    parts.append(f"  {sym.signature}")
        
        # Related symbols (from other files)
        if related_symbols:
            parts.append("\n--- RELATED SYMBOLS (from other files) ---")
            for sym in related_symbols:
                parts.append(sym.get_context_string(include_source=True, max_lines=20))
        
        parts.append("=" * 60)
        
        return '\n'.join(parts)
    
    def _format_context_package(
        self,
        symbols: List[Symbol],
        dependencies: List[Tuple[str, str, str]],
        context_parts: List[str]
    ) -> str:
        """Format a context package for model consumption"""
        parts = []
        
        parts.append("=" * 60)
        parts.append("CODEBASE CONTEXT")
        parts.append(f"Symbols included: {len(symbols)}")
        parts.append("=" * 60)
        
        # Summary
        parts.append("\n--- SYMBOL SUMMARY ---")
        for sym in symbols:
            parts.append(f"- {sym.kind.name}: {sym.qualified_name} ({sym.file_path}:{sym.start_line})")
        
        # Dependency graph
        if dependencies:
            parts.append("\n--- DEPENDENCIES ---")
            for from_sym, to_sym, dep_type in dependencies:
                parts.append(f"- {from_sym} --[{dep_type}]--> {to_sym}")
        
        # Full context
        parts.append("\n--- DETAILED CONTEXT ---")
        parts.extend(context_parts)
        
        parts.append("\n" + "=" * 60)
        
        return '\n'.join(parts)
    
    def _read_file(self, file_path: str) -> Optional[str]:
        """Read entire file content"""
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                return f.read()
        except Exception:
            return None
    
    def _read_file_range(self, file_path: str, start: int, end: int) -> str:
        """Read specific lines from a file"""
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                lines = f.readlines()
                selected = lines[start-1:end]
                return ''.join(selected)
        except Exception:
            return ""
