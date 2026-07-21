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
from typing import List, Dict, Optional, Set, Tuple, Any, Iterable
from dataclasses import dataclass, field
from concurrent.futures import ThreadPoolExecutor
import math
import os
import re
import shutil
import subprocess
import time
from collections import Counter, defaultdict

from ..diagnostics import report_suppressed_exception
from .symbol_table import Symbol, SymbolTable, SymbolKind
from .dependency_graph import DependencyGraph, DependencyType
from .fast_context import FastContextExplorer, FastContextResult
from .workspace import WorkspaceProfile, detect_workspace_profile


@dataclass
class RetrievedContextPackage:
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


# Compatibility alias for integrations written before the domain-specific name.
ContextPackage = RetrievedContextPackage


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
        'context': ['retrieval', 'retriever', 'index', 'indexer', 'symbol', 'semantic', 'workspace', 'search', 'recommend', 'recommendation', 'ranking', 'relevance'],
        'stream': ['streaming', 'sse', 'delta', 'chunk', 'messages', 'completion'],
        'model': ['llm', 'provider', 'source', 'sdk', 'client', 'api'],
        'compression': ['compress', 'compressed', 'compaction', 'compact', 'summary', 'summarize', 'memory'],
        'tooling': ['tool', 'tools', 'executor', 'registry', 'manifest', 'schema', 'function'],
        'ui': ['ux', 'interface', 'frontend', 'react', 'electron', 'desktop', 'gui'],
        'performance': ['speed', 'latency', 'slow', 'fast', 'optimize', 'optimization', 'improve', 'smooth', 'smoothness', 'throughput'],
        'startup': ['launch', 'boot', 'cold', 'warm', 'portable'],
    }

    TASK_QUERY_ALIASES = {
        '上下文': ('context', 'retrieval', 'retriever', 'index'),
        '检索': ('retrieval', 'retriever', 'search', 'index'),
        '推荐': ('retrieval', 'ranking', 'relevance', 'search'),
        '相关': ('relevance', 'ranking', 'retrieval'),
        '压缩': ('compression', 'compressor', 'compaction', 'memory'),
        '缓存': ('cache', 'caching', 'memory'),
        '工具': ('tooling', 'tool', 'executor', 'registry'),
        '调用': ('tooling', 'function', 'executor'),
        '界面': ('ui', 'interface', 'frontend', 'desktop'),
        '流畅': ('performance', 'latency', 'ui'),
        '性能': ('performance', 'latency', 'throughput'),
        '速度': ('performance', 'latency', 'fast'),
        '启动': ('startup', 'launch', 'boot'),
        '测试': ('test', 'testing', 'pytest', 'spec'),
        '配置': ('config', 'settings', 'configuration'),
        '错误': ('error', 'exception', 'failure'),
        '修复': ('fix', 'bug', 'error'),
    }

    TASK_QUERY_STOPWORDS = {
        'about', 'actual', 'additional', 'all', 'also', 'and', 'any', 'are', 'because', 'been',
        'being', 'behavior', 'behaviour', 'but', 'can', 'could', 'description', 'does', 'expected',
        'for', 'from', 'had', 'has', 'have', 'into', 'its', 'make', 'more', 'not', 'one', 'only',
        'doesn', 'don', 'false', 'file', 'files', 'isn', 'no', 'none', 'null', 'other', 'our',
        'please', 'problem', 'related', 'results', 'should', 'some', 'steps', 'such',
        'than', 'that', 'the', 'their', 'then', 'there', 'these', 'they', 'this', 'those', 'through',
        'true', 'using', 'was', 'were', 'what', 'when', 'where', 'which', 'while', 'will', 'with',
        'without', 'won', 'work', 'working', 'would', 'yes', 'you', 'your',
    }
    TASK_SHORT_TOKENS = {'ai', 'db', 'ui', 'ux'}
    TASK_TOKEN_PATTERN = re.compile(r"[A-Za-z_][A-Za-z0-9_]{1,}|[\u4e00-\u9fff]{2,}")
    TASK_CJK_PATTERN = re.compile(r"[\u4e00-\u9fff]+")
    TASK_CAMEL_BOUNDARY_PATTERN = re.compile(r"([a-z0-9])([A-Z])")
    TASK_FENCED_BLOCK_PATTERN = re.compile(r"(?:```|~~~)[^\r\n]*\r?\n.*?(?:```|~~~)", re.DOTALL)
    TASK_FILE_EXTENSIONS = {
        'c', 'cc', 'conf', 'cpp', 'cs', 'css', 'csv', 'cxx', 'gd', 'go', 'h', 'hh', 'hpp',
        'htm', 'html', 'ini', 'java', 'js', 'json', 'jsx', 'less', 'lua', 'md', 'mdx', 'mjs',
        'py', 'pyi', 'pyw', 'rb', 'rs', 'rst', 'sass', 'scss', 'sh', 'sql', 'toml', 'ts',
        'tsx', 'txt', 'xml', 'yaml', 'yml', 'zig',
    }
    TASK_CONTENT_EXTENSIONS = {f'.{extension}' for extension in TASK_FILE_EXTENSIONS}
    TASK_EXCLUDED_PATH_SEGMENTS = {
        '.git', '.kernel', '.pytest_cache', '.reverie', '.runtime', '.venv', '__pycache__',
        'build', 'dist', 'node_modules', 'release', 'target', 'venv',
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
        content_searcher: Any = None,
        chunk_searcher: Any = None,
        content_frequency: Any = None,
        content_total: Any = None,
    ):
        self.symbol_table = symbol_table
        self.dependency_graph = dependency_graph
        self.project_root = project_root
        self.file_info = file_info if file_info is not None else {}
        self.git_integration = git_integration
        self.memory_indexer = memory_indexer
        self.lsp_manager = lsp_manager
        self.content_searcher = content_searcher
        self.chunk_searcher = chunk_searcher
        # Derive the content document-frequency providers from the same
        # indexer that owns ``content_searcher`` when they are not supplied
        # explicitly, so every caller (CLI, desktop bridge, benchmark) gets
        # true content-level IDF without extra wiring.
        if content_frequency is None and content_searcher is not None:
            owner = getattr(content_searcher, "__self__", None)
            derived = getattr(owner, "content_document_frequencies", None)
            if callable(derived):
                content_frequency = derived
                if content_total is None:
                    owner_total = getattr(owner, "content_document_total", None)
                    if callable(owner_total):
                        content_total = owner_total
        self.content_frequency = content_frequency
        self.content_total = content_total
        self._content_idf_cache: Dict[str, float] = {}
        self._dependency_in_degree: Dict[str, int] = {}
        self._dependency_in_degree_revision: Optional[tuple[int, int]] = None
        self._activity_files: Dict[str, Dict[str, float]] = {}
        self._activity_symbols: Dict[str, Dict[str, float]] = {}
        self._task_cache: Dict[tuple[Any, ...], tuple[float, TaskContextResult]] = {}
        self._lexical_index_revision: Optional[tuple[int, int, int]] = None
        self._lexical_documents: Dict[str, Counter[str]] = {}
        self._lexical_document_lengths: Dict[str, int] = {}
        self._lexical_document_frequency: Counter[str] = Counter()
        self._test_source_index_revision: Optional[tuple[int, int, int]] = None
        self._test_source_index: Dict[str, List[Tuple[str, Set[str]]]] = {}
        self._content_cache: Dict[str, tuple[int, int, str]] = {}
        self._path_cache: Dict[str, str] = {}
        self._relative_path_cache: Dict[str, str] = {}
        self._generated_path_cache: Dict[str, bool] = {}

    def _normalize_file_path(self, file_path: str) -> str:
        """Normalize file paths so workset scoring is stable across callers."""
        raw_path = str(file_path or "")
        cached = self._path_cache.get(raw_path)
        if cached is not None:
            return cached
        try:
            normalized = os.path.normpath(
                raw_path if os.path.isabs(raw_path) else os.path.join(str(self.project_root), raw_path)
            )
        except Exception:
            normalized = raw_path
        if len(self._path_cache) >= 4096:
            self._path_cache.pop(next(iter(self._path_cache)))
        self._path_cache[raw_path] = normalized
        return normalized

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
        raw_tokens = self.TASK_TOKEN_PATTERN.findall(str(text or ""))
        tokens: List[str] = []
        seen: Set[str] = set()
        for raw in raw_tokens:
            if self.TASK_CJK_PATTERN.fullmatch(raw):
                cjk_terms = [raw]
                if len(raw) > 4:
                    cjk_terms.extend(raw[index:index + 2] for index in range(len(raw) - 1))
                for term in cjk_terms:
                    if term in seen:
                        continue
                    seen.add(term)
                    tokens.append(term)
                continue
            if raw.islower() and "_" not in raw:
                if (
                    (len(raw) >= 3 or raw in self.TASK_SHORT_TOKENS)
                    and raw not in self.TASK_QUERY_STOPWORDS
                    and raw not in seen
                ):
                    seen.add(raw)
                    tokens.append(raw)
                continue
            expanded_text = raw.replace("_", " ")
            if not raw.islower():
                expanded_text = self.TASK_CAMEL_BOUNDARY_PATTERN.sub(r"\1 \2", expanded_text)
            expanded = expanded_text.split()
            for part in expanded:
                token = part.lower().strip()
                if (
                    (len(token) < 3 and token not in self.TASK_SHORT_TOKENS)
                    or token in self.TASK_QUERY_STOPWORDS
                    or token in seen
                ):
                    continue
                seen.add(token)
                tokens.append(token)
        return tokens

    def _query_prose(self, query: str) -> str:
        """Keep issue prose while excluding verbose fenced examples and command output."""
        return self.TASK_FENCED_BLOCK_PATTERN.sub("\n", str(query or ""))

    def _extract_fenced_call_identifiers(self, query: str) -> List[str]:
        """Keep only call-shaped identifiers from fenced traces and code samples."""
        identifiers: List[str] = []
        seen: Set[str] = set()
        for block in self.TASK_FENCED_BLOCK_PATTERN.findall(str(query or "")):
            for raw in re.findall(r"\b([A-Za-z_][A-Za-z0-9_.]{1,79})\s*\(", block):
                for value in (raw, raw.rsplit(".", 1)[-1]):
                    normalized = value.lower()
                    if normalized in seen or normalized in self.TASK_QUERY_STOPWORDS:
                        continue
                    seen.add(normalized)
                    identifiers.append(value)
                    if len(identifiers) >= 12:
                        return identifiers
        return identifiers

    def _extract_query_compounds(self, text: str, *, limit: int = 16) -> List[str]:
        """Join adjacent prose terms to match compound filenames and identifiers."""
        compounds: List[str] = []
        seen: Set[str] = set()
        for line in str(text or "").splitlines():
            line_terms: List[str] = []
            for raw in self.TASK_TOKEN_PATTERN.findall(line):
                expanded = self._tokenize_query(raw)
                if not expanded:
                    line_terms.append("")
                    continue
                line_terms.extend(expanded)
            for left, right in zip(line_terms, line_terms[1:]):
                if (
                    not left
                    or not right
                    or left == right
                    or not re.fullmatch(r"[a-z0-9_]+", left)
                    or not re.fullmatch(r"[a-z0-9_]+", right)
                ):
                    continue
                compound = f"{left}{right}"
                if len(compound) < 6 or len(compound) > 64 or compound in seen:
                    continue
                seen.add(compound)
                compounds.append(compound)
                if len(compounds) >= max(1, int(limit or 16)):
                    return compounds
        return compounds

    def _filter_corpus_compounds(self, compounds: List[str]) -> List[str]:
        """Drop joined-word compounds that name nothing in the codebase.

        The compound heuristic joins adjacent prose words to recover names like
        ``autodetector`` that appear split in an issue ("auto detector"). But
        the same rule fabricates junk from ordinary prose ("undefined
        expression" -> ``undefinedexpression``). A compound is only worth
        keeping if it resolves to a real artifact: a body token (content df>0),
        or a substring of some symbol/file name. Everything else is pruned so it
        cannot soak up the rare-term IDF bonus and displace real signal. Falls
        back to the unfiltered list when no corpus signal is available.
        """
        if not compounds:
            return []
        candidates = list(dict.fromkeys(compounds))

        frequencies: Optional[Dict[str, int]] = None
        if callable(self.content_frequency):
            try:
                frequencies = self.content_frequency(candidates)
            except Exception:
                frequencies = None

        # Build a lazily-populated set of symbol/file name tokens only if we need
        # to resolve compounds that the content index did not vouch for.
        name_tokens: Optional[Set[str]] = None

        def _resolve_name_tokens() -> Set[str]:
            tokens: Set[str] = set()
            try:
                for symbol in self.symbol_table.iter_symbols():
                    name = str(getattr(symbol, "name", "") or "").lower()
                    if name:
                        tokens.add(name.replace("_", ""))
            except Exception:
                 report_suppressed_exception(
                    "resolve Context Engine compound name tokens"
                )
            for raw_path in (self.file_info or {}):
                stem = Path(str(raw_path)).stem.lower()
                if stem:
                    tokens.add(stem.replace("_", ""))
            return tokens

        kept: List[str] = []
        for compound in candidates:
            if frequencies is not None and int(frequencies.get(compound, 0) or 0) > 0:
                kept.append(compound)
                continue
            if frequencies is None:
                # No content index: cannot prove absence, so keep to preserve
                # metadata-only behavior.
                kept.append(compound)
                continue
            if name_tokens is None:
                name_tokens = _resolve_name_tokens()
            if any(compound in token for token in name_tokens):
                kept.append(compound)
        return kept

    def _build_task_term_weights(self, query: str) -> Dict[str, float]:
        """Expand the user request into weighted retrieval terms."""
        prose = self._query_prose(query)
        weights: Dict[str, float] = {}
        for token in self._tokenize_query(prose):
            base_weight = 0.35 if re.fullmatch(r"[\u4e00-\u9fff]+", token) else 1.0
            weights[token] = max(weights.get(token, 0.0), base_weight)
            for root, synonyms in self.TASK_QUERY_SYNONYMS.items():
                if token == root or token in synonyms:
                    weights[root] = max(weights.get(root, 0.0), 0.9 if token == root else 0.7)
                    for synonym in synonyms:
                        weights[synonym] = max(weights.get(synonym, 0.0), 0.55)
        query_lower = prose.lower()
        for alias, expanded_terms in self.TASK_QUERY_ALIASES.items():
            if alias not in query_lower:
                continue
            for index, term in enumerate(expanded_terms):
                weights[term] = max(weights.get(term, 0.0), 0.95 if index == 0 else 0.68)
                for root, synonyms in self.TASK_QUERY_SYNONYMS.items():
                    if term != root and term not in synonyms:
                        continue
                    weights[root] = max(weights.get(root, 0.0), 0.72)
                    for synonym in synonyms:
                        weights[synonym] = max(weights.get(synonym, 0.0), 0.42)

        title = next((line.strip() for line in str(query or "").splitlines() if line.strip()), "")
        for token in self._tokenize_query(title):
            weights[token] = max(weights.get(token, 0.0), 1.65)
        title_compounds = set(self._extract_query_compounds(title, limit=6))
        prose_compounds = self._extract_query_compounds(prose, limit=16)
        # A joined adjacent-word compound is only useful if it actually names
        # something in the corpus (a file, symbol, or body token). Adjacent
        # prose words otherwise fabricate non-existent identifiers
        # (e.g. "undefined expression" -> "undefinedexpression") that, having
        # zero content frequency, receive the rare-term IDF bonus and crowd out
        # the real query signal. Keep only compounds that resolve to something.
        for compound in self._filter_corpus_compounds(prose_compounds):
            weights[compound] = max(weights.get(compound, 0.0), 1.85 if compound in title_compounds else 1.15)
        prose_identifiers = self._extract_query_identifiers(prose)
        # Dotted fragments lifted from repro snippets (e.g. ``r.limit``,
        # ``e.subs``, ``publication.objects``) are frequently local-variable
        # method calls that name nothing stable in the codebase. When such a
        # compound dotted form resolves to no body token, keep only its suffix
        # (the method/attribute name, already emitted separately) rather than
        # letting the throwaway ``head.attr`` string claim a top identifier
        # weight and, being corpus-absent, collect the rare-term IDF bonus.
        dotted = [ident for ident in prose_identifiers if "." in ident]
        dotted_ok: Set[str] = set()
        if dotted and callable(self.content_frequency):
            try:
                dotted_freqs = self.content_frequency([ident.lower() for ident in dotted])
            except Exception:
                dotted_freqs = None
            if dotted_freqs is not None:
                dotted_ok = {
                    ident
                    for ident in dotted
                    if int(dotted_freqs.get(ident.lower(), 0) or 0) > 0
                }
            else:
                dotted_ok = set(dotted)
        else:
            dotted_ok = set(dotted)
        for identifier in prose_identifiers:
            normalized = identifier.lower()
            if "." in identifier and identifier not in dotted_ok:
                continue
            weights[normalized] = max(weights.get(normalized, 0.0), 2.2)
        prose_identifier_set = {identifier.lower() for identifier in prose_identifiers}
        for identifier in self._extract_fenced_call_identifiers(query):
            normalized = identifier.lower()
            if normalized in prose_identifier_set:
                continue
            weights[normalized] = max(weights.get(normalized, 0.0), 0.85)
        return weights

    def _extract_query_identifiers(self, query: str) -> List[str]:
        """Return code-shaped and explicitly quoted terms without splitting their spelling."""
        text = str(query or "")
        candidates = re.findall(
            r"`([^`\r\n]{2,80})`|'([^'\r\n]{2,80})'|\"([^\"\r\n]{2,80})\"",
            text,
        )
        values = [part for groups in candidates for part in groups if part]
        explicit_code_terms: Set[str] = set()
        for left, right in re.findall(
            r"\b([A-Za-z_][A-Za-z0-9_]*)\s*/\s*([A-Za-z_][A-Za-z0-9_]*)\b",
            text,
        ):
            values.extend((left, right))
            explicit_code_terms.update((left.lower(), right.lower()))
        for call_name in re.findall(r"\b([A-Za-z_][A-Za-z0-9_]*)\s*\(", text):
            values.append(call_name)
            explicit_code_terms.add(call_name.lower())
        values.extend(
            re.findall(
                r"\b(?:[A-Za-z_][A-Za-z0-9_]*_[A-Za-z0-9_]+|[A-Z][A-Z0-9_]{2,}|"
                r"[A-Z][a-z0-9]+(?:[A-Z][A-Za-z0-9]*)+|[A-Za-z_][A-Za-z0-9_]*\."
                r"[A-Za-z_][A-Za-z0-9_]*)\b",
                text,
            )
        )

        identifiers: List[str] = []
        seen: Set[str] = set()
        for raw in values:
            candidate = str(raw or "").strip("`'\".,;:()[]{} ")
            if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_.-]{1,79}", candidate):
                continue
            suffix = candidate.rsplit(".", 1)[-1].lower() if "." in candidate else ""
            if suffix in self.TASK_FILE_EXTENSIONS or re.fullmatch(r"\d+(?:\.\d+)+", candidate):
                continue
            for value in (candidate, candidate.rsplit(".", 1)[-1]):
                normalized = value.replace("-", "_").lower()
                if (
                    normalized in seen
                    or normalized in self.TASK_QUERY_STOPWORDS
                    and normalized not in explicit_code_terms
                ):
                    continue
                seen.add(normalized)
                identifiers.append(value.replace("-", "_"))
        return identifiers[:24]

    # Reference IDF for a term appearing in ~3% of files, used to normalize the
    # BM25 inverse-document-frequency into a stable multiplier that does not
    # depend on repository size. log((1 - f) / f + 1) with f = 0.03.
    _IDF_REFERENCE = math.log((1.0 - 0.03) / 0.03 + 1.0)

    # Relationship weights for file-level dependency-neighbor propagation.
    # Structural edges (inheritance, calls, instantiation) carry more signal
    # than a bare import, which is often incidental.
    _DEP_NEIGHBOR_WEIGHTS = {
        DependencyType.INHERITS: 0.42,
        DependencyType.IMPLEMENTS: 0.42,
        DependencyType.OVERRIDES: 0.40,
        DependencyType.INSTANTIATES: 0.34,
        DependencyType.CALLS: 0.30,
        DependencyType.USES: 0.20,
        DependencyType.TYPE_HINTS: 0.18,
        DependencyType.REFERENCES: 0.16,
        DependencyType.IMPORTS: 0.16,
    }
    # A target reached from a single seed must clear this propagated score to be
    # promoted; multi-seed agreement bypasses it.
    _DEP_NEIGHBOR_MIN_SINGLE = 1.6

    def _content_idf(self, terms: Iterable[str]) -> Dict[str, float]:
        """Return a size-independent IDF multiplier per term from the content index.

        Uses true content document frequency (same tokenizer as search) so that
        a term appearing in a handful of files (e.g. ``output_transaction``) is
        weighted well above one appearing in hundreds (e.g. ``begin``). Falls
        back to the metadata-derived frequency table when no content index is
        wired in. Results are memoized per index revision.
        """
        requested = []
        seen: Set[str] = set()
        for term in terms:
            token = str(term or "").strip().lower()
            if token and token not in seen:
                seen.add(token)
                requested.append(token)
        if not requested:
            return {}

        multipliers: Dict[str, float] = {}
        missing = [term for term in requested if term not in self._content_idf_cache]

        frequencies: Optional[Dict[str, int]] = None
        total_documents = 0
        if missing and callable(self.content_frequency):
            try:
                frequencies = self.content_frequency(missing)
            except Exception:
                frequencies = None
            if frequencies is not None and callable(self.content_total):
                try:
                    total_documents = int(self.content_total() or 0)
                except Exception:
                    total_documents = 0

        if frequencies is not None and total_documents > 0:
            for term in missing:
                frequency = int(frequencies.get(term, 0) or 0)
                if frequency <= 0:
                    # Term is absent from file bodies: it can still match a path
                    # or symbol name, so keep it mildly rare-favoring rather than
                    # trusting the unbounded idf of a zero-frequency term.
                    self._content_idf_cache[term] = 1.15
                    continue
                idf = math.log(
                    (total_documents - frequency + 0.5) / (frequency + 0.5) + 1.0
                )
                self._content_idf_cache[term] = min(
                    2.6, max(0.28, idf / self._IDF_REFERENCE)
                )
        else:
            # No content index available: reuse the metadata frequency table so
            # calibration still degrades gracefully in metadata-only setups.
            self._ensure_lexical_index()
            document_count = max(1, len(self._lexical_documents))
            for term in missing:
                frequency = self._lexical_document_frequency.get(term, 0)
                idf = math.log(1.0 + (document_count + 1.0) / (frequency + 1.0))
                self._content_idf_cache[term] = min(2.4, max(0.22, idf / 2.4))

        for term in requested:
            multipliers[term] = self._content_idf_cache.get(term, 1.0)
        return multipliers

    def _calibrate_task_term_weights(self, term_weights: Dict[str, float]) -> Dict[str, float]:
        """Down-weight common corpus language and reward discriminative query terms."""
        if not term_weights or not isinstance(self.file_info, dict) or not self.file_info:
            return term_weights
        idf_multipliers = self._content_idf(term_weights.keys())
        calibrated: Dict[str, float] = {}
        for term, weight in term_weights.items():
            multiplier = idf_multipliers.get(term.lower(), 1.0)
            calibrated[term] = float(weight) * multiplier
        ranked = sorted(calibrated.items(), key=lambda item: (-item[1], item[0]))[:36]
        return dict(ranked)

    def _extract_query_anchors(self, query: str) -> Dict[str, List[str]]:
        """Extract high-confidence file and symbol anchors from a free-form task."""
        text = str(query or "")
        file_like: List[str] = []
        symbol_like: List[str] = []
        seen_files: Set[str] = set()
        seen_symbols: Set[str] = set()

        extension_pattern = "|".join(sorted(self.TASK_FILE_EXTENSIONS, key=len, reverse=True))
        for raw in re.findall(
            rf"(?<![\w.])[\w./\\-]+\.(?:{extension_pattern})(?::\d+)?\b",
            text,
            flags=re.IGNORECASE,
        ):
            candidate = raw.strip("`'\".,;()[]{}")
            if not candidate:
                continue
            if ":" in candidate:
                candidate = candidate.split(":", 1)[0]
            key = candidate.lower().replace("\\", "/")
            if key not in seen_files:
                seen_files.add(key)
                file_like.append(candidate)

        title = next((line.strip() for line in text.splitlines() if line.strip()), "")
        symbol_text = title + " " + " ".join(re.findall(r"`([^`\r\n]{2,80})`", text))
        for raw in re.findall(r"\b[A-Za-z_][A-Za-z0-9_]*(?:\.[A-Za-z_][A-Za-z0-9_]*)+\b|\b[A-Z][A-Za-z0-9_]{2,}\b", symbol_text):
            candidate = raw.strip("`'\".,;()[]{}")
            suffix = candidate.rsplit(".", 1)[-1].lower() if "." in candidate else ""
            if not candidate or suffix in self.TASK_FILE_EXTENSIONS:
                continue
            if "." not in candidate:
                symbol_shape = (
                    "_" in candidate
                    or candidate.isupper()
                    or any(character.isupper() for character in candidate[1:])
                    or title.strip("`'\".,;()[]{} ") == candidate
                )
                if not symbol_shape:
                    continue
            key = candidate.lower()
            if key not in seen_symbols:
                seen_symbols.add(key)
                symbol_like.append(candidate)

        return {"files": file_like[:12], "symbols": symbol_like[:20]}

    @staticmethod
    def _path_matches_file_anchor(file_path: str, anchor: str) -> bool:
        path = str(file_path or "").lower().replace("\\", "/").strip("/")
        expected = str(anchor or "").lower().replace("\\", "/").strip("/")
        if not path or not expected:
            return False
        return path == expected or path.endswith(f"/{expected}") or (
            "/" not in expected and Path(path).name == expected
        )

    def _reliable_file_anchor_terms(self, anchors: Set[str]) -> Set[str]:
        """Resolve stack-trace paths to unique workspace suffixes and reject ambiguity."""
        if not anchors or not isinstance(self.file_info, dict):
            return set(anchors)
        indexed_paths = [
            self._workspace_relative_path(self._normalize_file_path(path)).lower().replace("\\", "/").strip("/")
            for path in self.file_info
        ]
        reliable: Set[str] = set()
        for anchor in anchors:
            normalized = str(anchor or "").lower().replace("\\", "/").strip("/")
            if not normalized:
                continue
            parts = [part for part in normalized.split("/") if part and part not in {".", ".."}]
            suffixes = [normalized]
            if len(parts) > 2:
                suffixes.extend("/".join(parts[index:]) for index in range(1, len(parts) - 1))
            for suffix in dict.fromkeys(suffixes):
                matches = [path for path in indexed_paths if self._path_matches_file_anchor(path, suffix)]
                if len(matches) == 1 or ("/" in suffix and 1 < len(matches) <= 3):
                    reliable.add(suffix)
                    break
        return reliable

    def _is_generated_task_path(self, file_path: str) -> bool:
        """Keep generated application bundles and dependency trees out of task recommendations."""
        cache_key = str(file_path or "")
        cached = self._generated_path_cache.get(cache_key)
        if cached is not None:
            return cached
        try:
            relative = Path(file_path).relative_to(self.project_root)
        except (OSError, ValueError):
            relative = Path(file_path)
        generated = any(part.lower() in self.TASK_EXCLUDED_PATH_SEGMENTS for part in relative.parts)
        self._generated_path_cache[cache_key] = generated
        return generated

    def _query_role_boost(self, file_path: str, tags: List[str], query: str) -> Tuple[float, List[str]]:
        """Bias files toward the role implied by the user's task."""
        query_lower = next(
            (line.strip().lower() for line in str(query or "").splitlines() if line.strip()),
            "",
        )
        path_lower = str(file_path or "").lower().replace("\\", "/")
        tag_set = set(tags or [])
        boost = 0.0
        reasons: List[str] = []

        role_rules = [
            ("test", ("test", "tests", "pytest", "spec", "coverage"), 1.6),
            ("docs", ("doc", "docs", "readme", "documentation", "guide"), 1.6),
            ("config", ("config", "settings", "toml", "yaml", "json", "env"), 1.6),
            ("cli", ("cli", "command", "commands", "terminal", "shell"), 1.6),
            ("api", ("api", "endpoint", "route", "handler"), 1.6),
            ("engine", ("engine", "context", "retrieval", "indexer", "retriever"), 1.6),
            ("ui", (" ui ", " ux ", "gui", "frontend", "interface", "smooth"), 3.0),
            ("agent", ("llm", "agent", "proactive", "tool call", "function call"), 2.6),
            ("tools", ("tool", "tools", "function call"), 2.2),
        ]
        padded_query = f" {query_lower} "
        for tag, terms, role_weight in role_rules:
            if not any(term in padded_query for term in terms):
                continue
            if tag in tag_set or f"/{tag}" in path_lower or tag in path_lower:
                boost += role_weight
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
            stats = path.stat()
            if not path.is_file() or stats.st_size > 256 * 1024:
                return 0.0, []
            cache_key = self._normalize_file_path(file_path)
            cached = self._content_cache.get(cache_key)
            revision = (int(stats.st_mtime_ns), int(stats.st_size))
            if cached and cached[:2] == revision:
                text = cached[2]
            else:
                text = path.read_text(encoding="utf-8", errors="ignore")[:120000].lower()
                self._content_cache[cache_key] = (revision[0], revision[1], text)
                if len(self._content_cache) > 128:
                    self._content_cache.pop(next(iter(self._content_cache)))
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

    def _rank_task_search_terms(
        self,
        query: str,
        term_weights: Dict[str, float],
        *,
        limit: int = 18,
    ) -> List[Tuple[str, float]]:
        """Keep literal query terms while prioritizing code-shaped anchors."""
        title = next((line.strip() for line in str(query or "").splitlines() if line.strip()), "")
        prose = self._query_prose(query)
        identifiers = {item.lower() for item in self._extract_query_identifiers(prose)}
        all_identifiers = identifiers | {
            item.lower() for item in self._extract_fenced_call_identifiers(query)
        }
        title_identifiers = {item.lower() for item in self._extract_query_identifiers(title)}
        literal_terms = set(self._tokenize_query(prose)) | set(self._extract_query_compounds(prose, limit=16))
        title_terms = set(self._tokenize_query(title)) | set(self._extract_query_compounds(title, limit=6))
        prioritized_terms: List[Tuple[int, str, float]] = []
        for term, weight in term_weights.items():
            normalized = str(term or "").lower()
            if len(normalized) < 3 or normalized not in literal_terms | all_identifiers:
                continue
            if normalized in title_identifiers:
                boost = 2.4
                priority = 0
            elif normalized in title_terms:
                boost = 1.55
                priority = 1
            elif normalized in identifiers:
                boost = 2.0
                priority = 2
            elif normalized in all_identifiers:
                boost = 0.85
                priority = 3
            else:
                boost = 1.0
                priority = 4
            prioritized_terms.append((priority, normalized, float(weight) * boost))
        prioritized_terms.sort(key=lambda item: (item[0], -item[2], item[1]))
        return [(term, weight) for _, term, weight in prioritized_terms[: max(1, int(limit or 18))]]

    def _run_chunk_search(
        self,
        query: str,
        term_weights: Dict[str, float],
        *,
        limit: int = 120,
    ) -> List[Dict[str, Any]]:
        """Search persistent symbol-sized chunks when the indexer provides them."""
        if not callable(self.chunk_searcher):
            return []
        ranked_terms = self._rank_task_search_terms(query, term_weights, limit=18)
        if not ranked_terms:
            return []
        try:
            hits = self.chunk_searcher(ranked_terms, limit=limit)
        except Exception:
            return []
        return list(hits or [])

    def _mine_pseudo_relevance_terms(
        self,
        seed_candidates: List[TaskContextFile],
        existing_terms: Dict[str, float],
        *,
        max_seed_files: int = 3,
        max_terms: int = 6,
    ) -> Dict[str, float]:
        """Mine discriminative expansion terms from the top-ranked files.

        Classic pseudo-relevance feedback: treat the current top files as
        provisionally relevant, then harvest terms that are both frequent among
        them and rare in the corpus (high content IDF). This closes the common
        gap where an issue describes behaviour in prose while the target file's
        distinguishing vocabulary lives in its symbol names and docstrings. Only
        symbols already held in memory are inspected, so the pass adds no file
        reads and stays cheap. Expansion terms are returned with deliberately
        modest weights so they refine, never override, the literal query.
        """
        if self.symbol_table is None:
            return {}
        seeds = [
            candidate
            for candidate in seed_candidates
            if candidate.score > 0.0 and not self._is_generated_task_path(candidate.file_path)
        ][: max(1, int(max_seed_files or 3))]
        if len(seeds) < 2:
            # With a single provisional file there is no agreement signal, so
            # feedback would just echo one file's vocabulary and add noise.
            return {}

        existing = {str(term or "").lower() for term in existing_terms}
        term_files: Dict[str, Set[str]] = defaultdict(set)
        term_occurrences: Counter[str] = Counter()
        for candidate in seeds:
            local_terms: Set[str] = set()
            for symbol in self.symbol_table.get_all_in_file(candidate.file_path)[:40]:
                text = " ".join(
                    part
                    for part in (
                        str(getattr(symbol, "name", "") or ""),
                        str(getattr(symbol, "qualified_name", "") or ""),
                        str(getattr(symbol, "signature", "") or "")[:240],
                        str(getattr(symbol, "docstring", "") or "")[:240],
                    )
                    if part
                )
                for token in self._tokenize_query(text):
                    if len(token) < 4 or token in existing or token in self.TASK_QUERY_STOPWORDS:
                        continue
                    local_terms.add(token)
                    term_occurrences[token] += 1
            for token in local_terms:
                term_files[token].add(candidate.file_path)

        # Only terms shared by at least two provisional files are trustworthy;
        # a term unique to one file cannot distinguish agreement from chance.
        shared_terms = [term for term, files in term_files.items() if len(files) >= 2]
        if not shared_terms:
            return {}

        idf_multipliers = self._content_idf(shared_terms)
        scored: List[Tuple[float, str]] = []
        for term in shared_terms:
            idf = idf_multipliers.get(term, 1.0)
            # Reward corpus-rare terms; ignore ones that pervade the codebase.
            if idf < 0.9:
                continue
            agreement = len(term_files[term])
            score = idf * (1.0 + 0.35 * (agreement - 1))
            scored.append((score, term))
        if not scored:
            return {}
        scored.sort(key=lambda item: (-item[0], item[1]))

        expansion: Dict[str, float] = {}
        for _, term in scored[: max(1, int(max_terms or 6))]:
            # Capped, sub-unit weight keeps expansion subordinate to the literal
            # query terms while still letting a strong match promote a file.
            expansion[term] = 0.7
        return expansion

    def _run_targeted_content_search(
        self,
        query: str,
        term_weights: Dict[str, float],
        *,
        limit: int = 80,
    ) -> List[Dict[str, Any]]:
        """Search indexed text files for a small set of high-signal issue terms."""
        title = next((line.strip() for line in str(query or "").splitlines() if line.strip()), "")
        ranked_terms = self._rank_task_search_terms(query, term_weights, limit=16)
        if not ranked_terms:
            return []
        if callable(self.content_searcher):
            try:
                indexed_hits = self.content_searcher(ranked_terms, limit=limit)
            except Exception:
                indexed_hits = None
            if indexed_hits is not None:
                return list(indexed_hits)
        encoded_terms = [(term, term.encode("utf-8"), weight) for term, weight in ranked_terms]

        title_lower = title.lower()
        wants_docs = any(term in title_lower for term in ("doc", "readme", "guide"))
        wants_tests = any(term in title_lower for term in ("test", "pytest", "coverage", "spec"))
        candidates: List[Tuple[int, int, Path, str]] = []
        byte_budget = 48 * 1024 * 1024
        for raw_path, info in (self.file_info or {}).items():
            file_path = self._normalize_file_path(raw_path)
            path = Path(file_path)
            if self._is_generated_task_path(file_path) or path.suffix.lower() not in self.TASK_CONTENT_EXTENSIONS:
                continue
            try:
                size = int(self._get_file_meta(info, "size", 0) or 0)
            except (TypeError, ValueError):
                continue
            if size <= 0 or size > 1024 * 1024:
                continue
            normalized = file_path.lower().replace("\\", "/")
            is_docs = path.suffix.lower() in {".md", ".mdx", ".rst", ".txt"} or "/docs/" in f"/{normalized}"
            is_test = "/tests/" in f"/{normalized}" or path.name.lower().startswith("test_") or ".test." in path.name.lower()
            role = 0 if (not is_docs and not is_test) else 1 if (is_docs and wants_docs) or (is_test and wants_tests) else 2
            candidates.append((role, size, path, file_path))
        candidates.sort(key=lambda item: (item[0], item[1], item[3].lower()))

        selected: List[Tuple[Path, str]] = []
        selected_bytes = 0
        for _, size, path, file_path in candidates:
            if len(selected) >= 1200 or selected_bytes + size > byte_budget:
                break
            selected.append((path, file_path))
            selected_bytes += size
        if not selected:
            return []

        def score_path(item: Tuple[Path, str]) -> Optional[Dict[str, Any]]:
            path, file_path = item
            try:
                content = path.read_bytes().lower()
            except OSError:
                return None
            normalized_path = file_path.lower().replace("\\", "/")
            path_stem = path.stem.lower()
            contributions: List[float] = []
            matched: List[str] = []
            for term, encoded_term, weight in encoded_terms:
                count = content.count(encoded_term)
                path_match = weight >= 4.0 and (
                    term == path_stem or term in Path(normalized_path).name.lower()
                )
                if count <= 0 and not path_match:
                    continue
                contribution = weight * (1.0 + min(2.0, math.log2(count + 1.0))) if count > 0 else 0.0
                if path_match and term == path_stem:
                    contribution += weight * 10.0
                elif path_match:
                    contribution += weight * 3.0
                contributions.append(contribution)
                matched.append(term)
            if not matched:
                return None
            contributions.sort(reverse=True)
            score = sum(
                contribution * (1.0 if index == 0 else 0.72 if index == 1 else 0.45 if index < 5 else 0.18)
                for index, contribution in enumerate(contributions)
            )
            if len(matched) > 1:
                score += min(3.5, (len(matched) - 1) * 0.7)
            return {
                "file_path": file_path,
                "score": round(score, 4),
                "terms": matched[:6],
            }

        workers = min(8, max(1, os.cpu_count() or 1), len(selected))

        def score_batch(batch: List[Tuple[Path, str]]) -> List[Dict[str, Any]]:
            return [hit for item in batch if (hit := score_path(item)) is not None]

        batches = [selected[index::workers] for index in range(workers)]
        with ThreadPoolExecutor(max_workers=workers) as executor:
            hits = [hit for batch in executor.map(score_batch, batches) for hit in batch]
        hits.sort(key=lambda item: (-float(item["score"]), str(item["file_path"]).lower()))
        return hits[: max(1, int(limit or 80))]

    @staticmethod
    def _task_file_role_multiplier(file_path: str, tags: List[str], query: str) -> float:
        """Prefer implementation files unless the issue title explicitly asks for another role."""
        title = next((line.strip().lower() for line in str(query or "").splitlines() if line.strip()), "")
        normalized = str(file_path or "").lower().replace("\\", "/")
        name = Path(normalized).name
        tag_set = set(tags or [])
        is_docs = "docs" in tag_set or "/docs/" in f"/{normalized}" or Path(name).suffix in {".md", ".mdx", ".rst", ".txt"}
        is_test = "test" in tag_set or "/tests/" in f"/{normalized}" or name.startswith("test_") or ".test." in name
        if is_docs and not any(term in title for term in ("doc", "readme", "guide")):
            return 0.72
        if is_test and not any(term in title for term in ("test", "pytest", "coverage", "spec")):
            return 0.82
        if any(part in normalized for part in ("/.github/issue_template/", "/examples/", "/example/")):
            return 0.80
        return 1.0

    def _workspace_relative_path(self, file_path: str) -> str:
        raw_path = str(file_path or "")
        cached = self._relative_path_cache.get(raw_path)
        if cached is not None:
            return cached
        try:
            normalized = self._normalize_file_path(raw_path)
            relative = os.path.relpath(normalized, str(self.project_root))
            if relative == os.pardir or relative.startswith(os.pardir + os.sep):
                relative = raw_path
        except Exception:
            relative = raw_path
        if len(self._relative_path_cache) >= 8192:
            self._relative_path_cache.pop(next(iter(self._relative_path_cache)))
        self._relative_path_cache[raw_path] = relative
        return relative

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

    def _collect_preselection_graph_hits(
        self,
        seed_scores: Dict[str, float],
        *,
        max_seeds: int = 12,
        max_hits: int = 120,
    ) -> List[Dict[str, Any]]:
        """Propagate confident symbol hits to related files before file cutoff."""
        relationship_weights = {
            DependencyType.CALLS: 0.90,
            DependencyType.OVERRIDES: 0.85,
            DependencyType.IMPLEMENTS: 0.80,
            DependencyType.INHERITS: 0.78,
            DependencyType.INSTANTIATES: 0.72,
            DependencyType.CONTAINS: 0.68,
            DependencyType.USES: 0.62,
            DependencyType.REFERENCES: 0.58,
            DependencyType.DECORATES: 0.56,
            DependencyType.TYPE_HINTS: 0.50,
            DependencyType.IMPORTS: 0.42,
        }
        ranked_seeds = [
            (qualified_name, score)
            for qualified_name, score in sorted(seed_scores.items(), key=lambda item: (-item[1], item[0]))
            if score > 0.0 and self.symbol_table.get_symbol(qualified_name) is not None
        ][: max(1, int(max_seeds or 12))]
        best_hits: Dict[Tuple[str, str, str], Dict[str, Any]] = {}
        for seed_rank, (qualified_name, raw_seed_score) in enumerate(ranked_seeds, start=1):
            seed_symbol = self.symbol_table.get_symbol(qualified_name)
            if seed_symbol is None:
                continue
            seed_strength = (8.0 / math.sqrt(seed_rank)) * (
                1.0 + min(0.45, math.log1p(raw_seed_score) / 10.0)
            )
            seed_file = self._normalize_file_path(seed_symbol.file_path) if seed_symbol.file_path else ""
            related = self.dependency_graph.get_related_symbols(
                qualified_name,
                max_distance=2,
                max_results=64,
            )
            for related_name, distance, dep_type in related:
                related_symbol = self.symbol_table.get_symbol(related_name)
                if related_symbol is None or not related_symbol.file_path:
                    continue
                file_path = self._normalize_file_path(related_symbol.file_path)
                relationship_weight = relationship_weights.get(dep_type, 0.45)
                score = seed_strength * relationship_weight / (max(1, distance) ** 1.35)
                if file_path == seed_file:
                    score *= 0.55
                if score <= 0.0:
                    continue
                dep_name = str(getattr(dep_type, "name", dep_type)).lower()
                key = (file_path, related_name, dep_name)
                hit = {
                    "file_path": file_path,
                    "symbol": related_name,
                    "from_symbol": qualified_name,
                    "dependency_type": dep_name,
                    "distance": int(distance),
                    "score": round(score, 4),
                    "start_line": max(1, int(related_symbol.start_line or 1)),
                    "end_line": max(1, int(related_symbol.end_line or related_symbol.start_line or 1)),
                }
                previous = best_hits.get(key)
                if previous is None or score > float(previous.get("score", 0.0)):
                    best_hits[key] = hit
        return sorted(
            best_hits.values(),
            key=lambda item: (-float(item["score"]), str(item["file_path"]).lower(), str(item["symbol"])),
        )[: max(1, int(max_hits or 120))]

    def _file_dependency_in_degrees(self) -> Dict[str, int]:
        """Return, per file, how many distinct other files depend on it.

        Cached per index revision. This is the structural analogue of document
        frequency: a file imported by many others across the repository (a hub
        such as ``utils`` or a package ``base``) carries little targeting signal,
        while a file pulled in by a small focused cluster is discriminative.
        """
        revision = (
            len(self.file_info) if isinstance(self.file_info, dict) else 0,
            len(self.symbol_table),
        )
        if self._dependency_in_degree_revision == revision and self._dependency_in_degree:
            return self._dependency_in_degree

        importers: Dict[str, Set[str]] = defaultdict(set)
        incoming = getattr(self.dependency_graph, "_incoming", None)
        if isinstance(incoming, dict):
            for target_symbol, dependencies in incoming.items():
                target = self.symbol_table.get_symbol(target_symbol)
                if target is None or not target.file_path:
                    continue
                target_file = self._normalize_file_path(target.file_path)
                for dep in dependencies:
                    source_file = str(getattr(dep, "file_path", "") or "")
                    if not source_file:
                        continue
                    normalized_source = self._normalize_file_path(source_file)
                    if normalized_source and normalized_source != target_file:
                        importers[target_file].add(normalized_source)

        in_degrees = {file_path: len(sources) for file_path, sources in importers.items()}
        self._dependency_in_degree = in_degrees
        self._dependency_in_degree_revision = revision
        return in_degrees

    def _collect_dependency_neighbor_hits(
        self,
        file_candidates: List[TaskContextFile],
        *,
        max_seeds: int = 12,
        max_hits: int = 48,
    ) -> List[Dict[str, Any]]:
        """Propagate relevance from strong files to their local dependency targets.

        Many issues touch a shared base class or helper module that itself has
        weak lexical overlap with the issue text, while several of its importers
        score highly (they mention the API in prose). This pass follows the
        resolved outgoing dependencies of the top-scoring files and awards a
        fraction of the seed score to each in-repository target file, so a base
        module reachable from several strong importers surfaces on its own. This
        is generic structural expansion, not tuned to any specific repository.
        """
        if not file_candidates or self.symbol_table is None:
            return []
        ranked = sorted(file_candidates, key=lambda item: (-item.score, item.file_path.lower()))
        seeds = [candidate for candidate in ranked if candidate.score > 0.0][: max(1, int(max_seeds or 12))]
        if not seeds:
            return []

        # Resolve each target symbol to its defining file once.
        aggregated: Dict[str, Dict[str, Any]] = {}
        target_file_cache: Dict[str, Optional[str]] = {}

        def target_file(symbol_name: str) -> Optional[str]:
            if symbol_name in target_file_cache:
                return target_file_cache[symbol_name]
            symbol = self.symbol_table.get_symbol(symbol_name)
            resolved = self._normalize_file_path(symbol.file_path) if symbol and symbol.file_path else None
            target_file_cache[symbol_name] = resolved
            return resolved

        seed_count = len(seeds)
        for seed_rank, seed in enumerate(seeds, start=1):
            seed_file = seed.file_path
            # Diminishing seed strength keeps a single strong importer from
            # dominating; agreement across seeds is what should win.
            seed_strength = float(seed.score) / (1.0 + math.log1p(seed_rank))
            if seed_strength <= 0.0:
                continue
            counted_targets: Set[str] = set()
            for symbol in self.symbol_table.get_all_in_file(seed_file)[:64]:
                dependencies = self.dependency_graph.get_dependencies(symbol.qualified_name, depth=1)
                for dep in dependencies:
                    dep_type = getattr(dep, "dep_type", None)
                    weight = self._DEP_NEIGHBOR_WEIGHTS.get(dep_type, 0.0)
                    if weight <= 0.0:
                        continue
                    file_path = target_file(str(dep.to_symbol or ""))
                    if not file_path or file_path == seed_file:
                        continue
                    # Count each target file at most once per seed to avoid
                    # rewarding files merely because they are large.
                    dedup_key = (file_path, dep_type)
                    if dedup_key in counted_targets:
                        continue
                    counted_targets.add(dedup_key)
                    contribution = seed_strength * weight
                    record = aggregated.get(file_path)
                    if record is None:
                        aggregated[file_path] = {
                            "file_path": file_path,
                            "score": contribution,
                            "seeds": {seed_file},
                            "dependency_type": getattr(dep_type, "name", "related"),
                            "from_file": seed_file,
                        }
                    else:
                        record["score"] += contribution
                        record["seeds"].add(seed_file)

        in_degrees = self._file_dependency_in_degrees()
        hits: List[Dict[str, Any]] = []
        for file_path, record in aggregated.items():
            distinct_seeds = len(record["seeds"])
            # Reward agreement: a file pulled in by several strong importers is a
            # far better bet than one reached from a single seed.
            agreement = 1.0 + min(0.9, (distinct_seeds - 1) * 0.35)
            # Structural IDF: discount hub files that half the repo depends on.
            # A target imported by many distinct files carries little targeting
            # signal; one reached from a focused set is discriminative.
            in_degree = int(in_degrees.get(file_path, 0))
            hub_penalty = 1.0 / (1.0 + math.log1p(max(0, in_degree)))
            score = record["score"] * agreement * hub_penalty
            if distinct_seeds < 2 and score < self._DEP_NEIGHBOR_MIN_SINGLE:
                # A single weak structural link is too noisy to promote on its own.
                continue
            hits.append(
                {
                    "file_path": file_path,
                    "score": round(score, 4),
                    "seeds": distinct_seeds,
                    "in_degree": in_degree,
                    "dependency_type": str(record["dependency_type"]).lower(),
                    "from_file": record["from_file"],
                }
            )
        hits.sort(key=lambda item: (-float(item["score"]), str(item["file_path"]).lower()))
        return hits[: max(1, int(max_hits or 48))]

    @staticmethod
    def _test_source_stem(file_path: str) -> Optional[str]:
        """Return the implementation stem encoded by a conventional test path."""
        normalized = str(file_path or "").lower().replace("\\", "/")
        name = Path(normalized).stem
        parts = {part for part in normalized.split("/") if part}
        looks_like_test = (
            bool(parts & {"test", "tests", "testing", "spec", "specs", "__tests__"})
            or name.startswith("test_")
            or name.endswith("_test")
            or name.endswith(".test")
            or name.endswith(".spec")
        )
        if not looks_like_test:
            return None
        for prefix in ("test_", "tests_"):
            if name.startswith(prefix):
                name = name[len(prefix):]
                break
        for suffix in ("_test", "_tests", ".test", ".spec"):
            if name.endswith(suffix):
                name = name[:-len(suffix)]
                break
        return name if len(name) >= 3 and name not in {"conftest", "setup", "index"} else None

    def _collect_test_source_hits(
        self,
        candidates: List[TaskContextFile],
        *,
        max_seeds: int = 24,
        max_hits: int = 48,
    ) -> List[Dict[str, Any]]:
        """Bridge high-ranked conventional test modules back to likely implementation files."""
        source_by_stem = self._ensure_test_source_index()
        if not source_by_stem:
            return []

        hits: Dict[str, Dict[str, Any]] = {}
        ranked_seeds = sorted(candidates, key=lambda item: (-item.score, item.file_path.lower()))[:max_seeds]
        for rank, seed in enumerate(ranked_seeds, start=1):
            relative_seed = self._workspace_relative_path(seed.file_path).lower().replace("\\", "/")
            source_stem = self._test_source_stem(relative_seed)
            matches = source_by_stem.get(source_stem or "", [])
            match_quality = 1.0
            if source_stem and not matches:
                source_parts = set(source_stem.split("_"))
                fuzzy_stems = [
                    stem
                    for stem in source_by_stem
                    if len(stem) >= 5
                    and (
                        stem in source_parts
                        or source_stem.startswith(stem + "_")
                        or source_stem.endswith("_" + stem)
                    )
                ]
                if fuzzy_stems:
                    longest = max(len(stem) for stem in fuzzy_stems)
                    matches = [
                        match
                        for stem in sorted(fuzzy_stems)
                        if len(stem) == longest
                        for match in source_by_stem[stem]
                    ]
                    match_quality = 0.72
            if not source_stem or not matches:
                continue
            seed_directory_terms = {
                part.lower() for part in Path(relative_seed).parent.parts
                if part.lower() not in {"test", "tests", "testing", "spec", "specs", "__tests__"}
                and len(part) >= 2
            }
            ordered_matches = sorted(
                matches,
                key=lambda item: (
                    -len(seed_directory_terms & item[1]),
                    abs(len(seed_directory_terms) - len(item[1])),
                    item[0].lower(),
                ),
            )[:3]
            ambiguity = math.sqrt(max(1, len(matches)))
            for match_rank, (file_path, directory_terms) in enumerate(ordered_matches, start=1):
                overlap = len(seed_directory_terms & directory_terms)
                score = (10.0 / math.sqrt(rank)) * (1.0 + min(0.35, overlap * 0.08))
                score = score * match_quality / (ambiguity * math.sqrt(match_rank))
                hit = {
                    "file_path": file_path,
                    "score": round(score, 4),
                    "reason": f"test-source:{Path(relative_seed).name}->{Path(file_path).name}",
                    "seed_file": seed.file_path,
                }
                previous = hits.get(file_path)
                if previous is None or score > float(previous.get("score", 0.0)):
                    hits[file_path] = hit
        return sorted(
            hits.values(),
            key=lambda item: (-float(item["score"]), str(item["file_path"]).lower()),
        )[: max(1, int(max_hits or 48))]

    def _ensure_test_source_index(self) -> Dict[str, List[Tuple[str, Set[str]]]]:
        """Cache conventional implementation stems for repeated task queries."""
        revision = (
            len(self.file_info),
            sum(int(float(self._get_file_meta(info, "mtime", 0.0) or 0.0) * 1000) for info in self.file_info.values()),
            sum(int(self._get_file_meta(info, "size", 0) or 0) for info in self.file_info.values()),
        )
        if revision == self._test_source_index_revision:
            return self._test_source_index

        source_by_stem: Dict[str, List[Tuple[str, Set[str]]]] = defaultdict(list)
        code_extensions = {
            ".c", ".cc", ".cpp", ".cs", ".go", ".h", ".hpp", ".java", ".js", ".jsx",
            ".lua", ".py", ".pyi", ".pyw", ".rs", ".ts", ".tsx", ".zig",
        }
        excluded_parts = {"test", "tests", "testing", "spec", "specs", "__tests__"}
        for raw_path in self.file_info or {}:
            file_path = self._normalize_file_path(raw_path)
            relative = self._workspace_relative_path(file_path).lower().replace("\\", "/")
            path = Path(relative)
            if path.suffix.lower() not in code_extensions or self._test_source_stem(relative):
                continue
            stem = path.stem.lower()
            if len(stem) < 3 or stem in {"__init__", "index", "main", "setup"}:
                continue
            directory_terms = {
                part for part in path.parent.parts
                if part.lower() not in excluded_parts and len(part) >= 2
            }
            source_by_stem[stem].append((file_path, {part.lower() for part in directory_terms}))
        self._test_source_index_revision = revision
        self._test_source_index = dict(source_by_stem)
        return self._test_source_index

    def _run_ripgrep_for_task(self, query: str, term_weights: Dict[str, float], limit: int = 40) -> List[Dict[str, Any]]:
        """Use ripgrep as a fast lexical signal when it is installed."""
        rg = shutil.which("rg")
        if not rg or not term_weights:
            return []
        terms = [
            re.escape(term)
            for term, _ in sorted(term_weights.items(), key=lambda item: (-item[1], item[0]))
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
        """Rank cached metadata through a reusable BM25-style lexical index."""
        if not term_weights or not isinstance(self.file_info, dict) or not self.file_info:
            return []
        terms = [term for term, _ in sorted(term_weights.items(), key=lambda item: (-item[1], item[0])) if len(term) >= 3][:10]
        if not terms:
            return []
        self._ensure_lexical_index()
        document_count = len(self._lexical_documents)
        if not document_count:
            return []
        average_length = sum(self._lexical_document_lengths.values()) / max(document_count, 1)
        ranked: List[tuple[float, str]] = []
        for file_path, frequencies in self._lexical_documents.items():
            score = 0.0
            document_length = max(1, self._lexical_document_lengths.get(file_path, 1))
            for term in terms:
                frequency = frequencies.get(term, 0)
                if frequency <= 0:
                    continue
                document_frequency = self._lexical_document_frequency.get(term, 0)
                inverse_frequency = math.log(
                    1.0 + (document_count - document_frequency + 0.5) / (document_frequency + 0.5)
                )
                normalization = frequency + 1.2 * (0.25 + 0.75 * document_length / max(average_length, 1.0))
                score += inverse_frequency * ((frequency * 2.2) / normalization) * term_weights.get(term, 1.0)
            if score > 0.0:
                ranked.append((score, file_path))
        ranked.sort(key=lambda item: (-item[0], item[1].lower()))
        return [
            {"file_path": file_path, "score": round(score, 4)}
            for score, file_path in ranked[: max(1, int(limit or 40))]
        ]

    def _ensure_lexical_index(self) -> None:
        """Rebuild lexical metadata only when the indexed file set changes."""
        revision = (
            len(self.file_info),
            sum(int(float(self._get_file_meta(info, "mtime", 0.0) or 0.0) * 1000) for info in self.file_info.values()),
            sum(int(self._get_file_meta(info, "size", 0) or 0) for info in self.file_info.values()),
        )
        if revision == self._lexical_index_revision:
            return

        documents: Dict[str, Counter[str]] = {}
        document_lengths: Dict[str, int] = {}
        document_frequency: Counter[str] = Counter()
        for raw_path, info in self.file_info.items():
            file_path = self._normalize_file_path(raw_path)
            if self._is_generated_task_path(file_path):
                continue
            document_terms: Set[str] = set()
            for field in ("keywords", "tags"):
                for value in self._get_file_meta(info, field, []) or []:
                    token = str(value or "").lower().strip()
                    if token and token not in self.TASK_QUERY_STOPWORDS:
                        document_terms.add(token)
            for value in (
                str(raw_path),
                str(self._get_file_meta(info, "summary", "") or ""),
                *(str(value) for value in self._get_file_meta(info, "symbol_names", []) or []),
            ):
                document_terms.update(self._tokenize_query(value))
            frequencies = Counter({term: 1 for term in document_terms})
            if not frequencies:
                continue
            documents[file_path] = frequencies
            document_lengths[file_path] = sum(frequencies.values())
            document_frequency.update(frequencies.keys())

        self._lexical_index_revision = revision
        self._lexical_documents = documents
        self._lexical_document_lengths = document_lengths
        self._lexical_document_frequency = document_frequency

    def _collect_lsp_task_evidence(self, query: str, term_weights: Dict[str, float], limit: int = 20) -> List[Dict[str, Any]]:
        """Collect optional LSP workspace-symbol evidence without requiring LSP availability."""
        manager = getattr(self, "lsp_manager", None)
        if manager is None:
            manager = getattr(self, "lsp", None)
        if manager is None:
            return []
        hits: List[Dict[str, Any]] = []
        terms = [term for term, _ in sorted(term_weights.items(), key=lambda item: (-item[1], item[0])) if len(term) >= 3][:5]
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
                    report_suppressed_exception("make retrieval candidate project-relative")
            else:
                project_path = self.project_root / path
                add_candidate(str(project_path))
                add_candidate(str(project_path.resolve()))
        except Exception:
            report_suppressed_exception("resolve retrieval candidate path")

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
    ) -> RetrievedContextPackage:
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
            RetrievedContextPackage ready for model consumption
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
        
        for score, sym in sorted(scored_symbols, key=lambda item: (-item[0], item[1].qualified_name)):
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

        return RetrievedContextPackage(
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
        fast: bool = False,
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
        term_weights = self._calibrate_task_term_weights(self._build_task_term_weights(query_text))
        anchors = self._extract_query_anchors(query_text)
        anchor_file_terms = self._reliable_file_anchor_terms({
            item.lower().replace("\\", "/") for item in anchors.get("files", [])
        })
        anchors = {
            **anchors,
            "files": [
                item
                for item in anchors.get("files", [])
                if item.lower().replace("\\", "/").strip("/") in anchor_file_terms
            ],
        }
        anchor_symbol_terms = {item.lower() for item in anchors.get("symbols", [])}

        cache_key = (
            query_text.lower(),
            max_tokens,
            max_files,
            max_symbols,
            bool(include_history),
            bool(include_memory),
            bool(fast),
            tuple(sorted(str(path or "").strip() for path in (active_files or []) if str(path or "").strip())),
            tuple(sorted(str(path or "").strip() for path in (changed_files or []) if str(path or "").strip())),
            len(self.file_info) if isinstance(self.file_info, dict) else 0,
            len(self.symbol_table),
            tuple(sorted(anchor_file_terms)),
            tuple(sorted(anchor_symbol_terms)),
        )
        cached_entry = self._task_cache.get(cache_key)
        now = time.time()
        cache_ttl = 60.0 if fast else 20.0
        if cached_entry and (now - cached_entry[0]) <= cache_ttl:
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

        symbol_scores: Dict[str, float] = defaultdict(float)
        symbol_reasons: Dict[str, Set[str]] = defaultdict(set)
        symbol_file_boosts: Dict[str, float] = defaultdict(float)
        symbol_file_reasons: Dict[str, List[str]] = defaultdict(list)
        for anchor in anchor_symbol_terms:
            matches = self.symbol_table.search(anchor, limit=max(24, max_symbols * 8))
            ambiguity = math.sqrt(max(1.0, len(matches) / 3.0))
            for symbol in matches:
                name = str(symbol.name or "").lower()
                if name == anchor:
                    boost = 42.0
                elif name.startswith(anchor):
                    boost = 30.0
                elif anchor in name:
                    boost = 16.0
                else:
                    boost = 8.0
                boost /= ambiguity
                symbol_scores[symbol.qualified_name] += boost
                symbol_reasons[symbol.qualified_name].add(f"anchor-symbol:{anchor}")
                if symbol.file_path:
                    file_path = self._normalize_file_path(symbol.file_path)
                    symbol_file_boosts[file_path] += boost
                    symbol_file_reasons[file_path].append(f"anchor-symbol:{anchor}")
                    self._merge_file_evidence(
                        evidence_by_file,
                        file_path,
                        source="symbol",
                        reason=f"anchor-symbol:{anchor}",
                        score=boost,
                    )

        chunk_started = time.perf_counter()
        chunk_hits = self._run_chunk_search(
            query_text,
            term_weights,
            limit=max(48, max_files * 16),
        )
        chunk_search_ms = (time.perf_counter() - chunk_started) * 1000.0
        chunk_file_boosts: Dict[str, float] = {}
        for rank, hit in enumerate(chunk_hits, start=1):
            file_path = self._normalize_file_path(hit.get("file_path", ""))
            if not file_path:
                continue
            raw_score = max(0.0, float(hit.get("score", 0.0) or 0.0))
            matched_terms = [str(term) for term in hit.get("terms", []) if str(term)]
            rank_score = 9.0 / math.sqrt(rank)
            agreement = 1.0 + min(0.36, max(0, len(matched_terms) - 1) * 0.09)
            score = rank_score * agreement + min(2.0, math.log1p(raw_score))
            symbol_name = str(hit.get("symbol", "") or "").strip()
            reason = "chunk:" + (symbol_name or Path(file_path).name)
            if matched_terms:
                reason += ":" + ",".join(matched_terms[:3])
            self._merge_file_evidence(
                evidence_by_file,
                file_path,
                source="chunk",
                reason=reason,
                score=score,
                line=hit.get("start_line"),
                line_end=hit.get("end_line"),
            )
            previous_file_score = chunk_file_boosts.get(file_path, 0.0)
            chunk_file_boosts[file_path] = min(
                18.0,
                max(previous_file_score, score) + (min(1.0, score * 0.15) if previous_file_score else 0.0),
            )
            symbol = self.symbol_table.get_symbol(symbol_name) if symbol_name else None
            if symbol is not None:
                symbol_scores[symbol.qualified_name] += score
                symbol_reasons[symbol.qualified_name].add(reason)

        for file_path, score in chunk_file_boosts.items():
            symbol_file_boosts[file_path] += score
            symbol_file_reasons[file_path].append("chunk-match")

        graph_hits = self._collect_preselection_graph_hits(
            symbol_scores,
            max_seeds=max(8, min(16, max_symbols)),
            max_hits=max(48, max_files * 16),
        )
        graph_file_boosts: Dict[str, float] = {}
        for hit in graph_hits:
            file_path = self._normalize_file_path(hit.get("file_path", ""))
            related_name = str(hit.get("symbol", "") or "")
            if not file_path or not related_name:
                continue
            score = max(0.0, float(hit.get("score", 0.0) or 0.0))
            dep_name = str(hit.get("dependency_type", "related") or "related")
            from_symbol = str(hit.get("from_symbol", "") or "")
            reason = f"graph:{dep_name}:{from_symbol}->{related_name}"
            self._merge_file_evidence(
                evidence_by_file,
                file_path,
                source="graph",
                reason=reason,
                score=score,
                line=hit.get("start_line"),
                line_end=hit.get("end_line"),
            )
            previous_file_score = graph_file_boosts.get(file_path, 0.0)
            graph_file_boosts[file_path] = min(
                14.0,
                max(previous_file_score, score) + (min(0.75, score * 0.12) if previous_file_score else 0.0),
            )
            symbol_scores[related_name] = max(symbol_scores.get(related_name, 0.0), score)
            symbol_reasons[related_name].add(f"graph:{dep_name}")

        for file_path, score in graph_file_boosts.items():
            symbol_file_boosts[file_path] += score
            symbol_file_reasons[file_path].append("graph-related")

        file_candidates: List[TaskContextFile] = []
        seen_file_candidates: Set[str] = set()
        for raw_path, info in list((self.file_info or {}).items()):
            file_path = self._normalize_file_path(raw_path)
            normalized_path = file_path.lower().replace("\\", "/")
            if self._is_generated_task_path(file_path) and not any(
                self._path_matches_file_anchor(normalized_path, anchor) for anchor in anchor_file_terms
            ):
                continue
            candidate = self._score_file_for_task(
                file_path=file_path,
                info=info,
                term_weights=term_weights,
                active_files=normalized_active_files,
                changed_files=normalized_changed_files,
                base_score=symbol_file_boosts.get(file_path, 0.0),
                reason_override=(symbol_file_reasons.get(file_path) or [None])[0],
                query_text=query_text,
                anchor_file_terms=anchor_file_terms,
                score_content=False,
            )
            if candidate and file_path not in seen_file_candidates:
                for reason in candidate.reasons:
                    evidence_source = "anchor" if reason.startswith("anchor-file:") else "index"
                    self._merge_file_evidence(
                        evidence_by_file,
                        file_path,
                        source=evidence_source,
                        reason=reason,
                        score=candidate.score,
                    )
                file_candidates.append(candidate)
                seen_file_candidates.add(file_path)

        for anchor in anchor_file_terms:
            for raw_path, info in list((self.file_info or {}).items()):
                file_path = self._normalize_file_path(raw_path)
                normalized = file_path.lower().replace("\\", "/")
                if not self._path_matches_file_anchor(normalized, anchor):
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
                    score_content=False,
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
                score_content=False,
            )
            if candidate:
                file_candidates.append(candidate)
                seen_file_candidates.add(file_path)

        targeted_started = time.perf_counter()
        targeted_content_hits = self._run_targeted_content_search(
            query_text,
            term_weights,
            limit=max(40, max_files * 8),
        )
        targeted_content_ms = (time.perf_counter() - targeted_started) * 1000.0
        for hit in targeted_content_hits:
            file_path = self._normalize_file_path(hit.get("file_path", ""))
            if not file_path:
                continue
            score = float(hit.get("score", 0.0) or 0.0)
            matched_terms = [str(term) for term in hit.get("terms", []) if str(term)]
            reason = "targeted-content:" + ",".join(matched_terms[:3])
            self._merge_file_evidence(
                evidence_by_file,
                file_path,
                source="targeted-content",
                reason=reason,
                score=score,
            )
            existing = next((candidate for candidate in file_candidates if candidate.file_path == file_path), None)
            if existing is not None:
                existing.score += score
                existing.reasons = list(dict.fromkeys([reason] + existing.reasons))[:8]
                continue
            info = self._get_file_info_record(file_path)
            candidate = self._score_file_for_task(
                file_path=file_path,
                info=info,
                term_weights=term_weights,
                active_files=normalized_active_files,
                changed_files=normalized_changed_files,
                base_score=score,
                reason_override=reason,
                query_text=query_text,
                anchor_file_terms=anchor_file_terms,
                score_content=False,
            )
            if candidate:
                file_candidates.append(candidate)
                seen_file_candidates.add(file_path)

        fast_context_skipped = bool(fast and len(file_candidates) >= min(max_files, 8))
        if not fast_context_skipped:
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
                score_content=False,
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

        lsp_hits = [] if fast else self._collect_lsp_task_evidence(query_text, term_weights, limit=max_files * 4)
        for hit in lsp_hits:
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
                score_content=False,
            )
            if candidate:
                file_candidates.append(candidate)
                seen_file_candidates.add(file_path)

        test_source_hits = self._collect_test_source_hits(
            file_candidates,
            max_seeds=max(16, max_files * 3),
            max_hits=max(24, max_files * 4),
        )
        candidate_by_path = {candidate.file_path: candidate for candidate in file_candidates}
        for hit in test_source_hits:
            file_path = self._normalize_file_path(hit.get("file_path", ""))
            if not file_path:
                continue
            score = max(0.0, float(hit.get("score", 0.0) or 0.0))
            reason = str(hit.get("reason", "test-source") or "test-source")
            self._merge_file_evidence(
                evidence_by_file,
                file_path,
                source="neighborhood",
                reason=reason,
                score=score,
            )
            existing = candidate_by_path.get(file_path)
            if existing is not None:
                existing.score += min(4.0, score * 0.35)
                existing.reasons = list(dict.fromkeys([reason] + existing.reasons))[:8]
                continue
            info = self._get_file_info_record(file_path)
            candidate = self._score_file_for_task(
                file_path=file_path,
                info=info,
                term_weights=term_weights,
                active_files=normalized_active_files,
                changed_files=normalized_changed_files,
                base_score=score,
                reason_override=reason,
                query_text=query_text,
                anchor_file_terms=anchor_file_terms,
                score_content=False,
            )
            if candidate:
                file_candidates.append(candidate)
                candidate_by_path[file_path] = candidate
                seen_file_candidates.add(file_path)

        dependency_hits = self._collect_dependency_neighbor_hits(
            file_candidates,
            max_seeds=max(8, max_files * 2),
            max_hits=max(16, max_files * 3),
        )
        for hit in dependency_hits:
            file_path = self._normalize_file_path(hit.get("file_path", ""))
            if not file_path:
                continue
            score = max(0.0, float(hit.get("score", 0.0) or 0.0))
            if score <= 0.0:
                continue
            dep_type = str(hit.get("dependency_type", "related") or "related")
            reason = f"dependency:{dep_type}:{Path(hit.get('from_file', '') or '').name}"
            self._merge_file_evidence(
                evidence_by_file,
                file_path,
                source="dependency",
                reason=reason,
                score=score,
            )
            existing = candidate_by_path.get(file_path)
            if existing is not None:
                existing.score += min(6.0, score * 0.5)
                existing.reasons = list(dict.fromkeys([reason] + existing.reasons))[:8]
                continue
            info = self._get_file_info_record(file_path)
            candidate = self._score_file_for_task(
                file_path=file_path,
                info=info,
                term_weights=term_weights,
                active_files=normalized_active_files,
                changed_files=normalized_changed_files,
                base_score=score,
                reason_override=reason,
                query_text=query_text,
                anchor_file_terms=anchor_file_terms,
                score_content=False,
            )
            if candidate:
                file_candidates.append(candidate)
                candidate_by_path[file_path] = candidate
                seen_file_candidates.add(file_path)

        file_candidates.sort(key=lambda item: (-item.score, item.file_path.lower()))
        content_candidate_limit = 0 if fast_context_skipped else min(32, max(12, max_files * 2))
        for candidate in file_candidates[:content_candidate_limit]:
            content_boost, content_reasons = self._score_file_content_for_task(candidate.file_path, term_weights)
            if not content_boost:
                continue
            candidate.score += content_boost
            candidate.reasons = list(dict.fromkeys(candidate.reasons + content_reasons))[:8]
            self._merge_file_evidence(
                evidence_by_file,
                candidate.file_path,
                source="content",
                reason=content_reasons[0] if content_reasons else "content_match",
                score=content_boost,
            )

        # Pseudo-relevance feedback: mine discriminative vocabulary from the
        # provisional top files and run one extra chunk search. This bridges the
        # gap where an issue is phrased in prose but the target file's defining
        # terms live in its symbols/docstrings. Skipped when a strong anchor is
        # already present (nothing to gain) to keep the extra search off the
        # common path.
        expansion_terms: Dict[str, float] = {}
        if not anchor_file_terms:
            provisional_ranked = sorted(
                file_candidates, key=lambda item: (-item.score, item.file_path.lower())
            )
            expansion_terms = self._mine_pseudo_relevance_terms(
                provisional_ranked,
                term_weights,
                max_seed_files=3,
                max_terms=6,
            )
        if expansion_terms:
            prf_hits = self._run_chunk_search(
                query_text,
                expansion_terms,
                limit=max(24, max_files * 6),
            )
            prf_file_scores: Dict[str, float] = {}
            for rank, hit in enumerate(prf_hits, start=1):
                file_path = self._normalize_file_path(hit.get("file_path", ""))
                if not file_path:
                    continue
                matched_terms = [str(term) for term in hit.get("terms", []) if str(term)]
                # Feedback evidence is deliberately weaker than direct query
                # matches: reciprocal-rank shaped, capped, and requiring term
                # agreement to contribute meaningfully.
                rank_score = 4.0 / math.sqrt(rank)
                agreement = 1.0 + min(0.3, max(0, len(matched_terms) - 1) * 0.1)
                prf_file_scores[file_path] = max(
                    prf_file_scores.get(file_path, 0.0), rank_score * agreement
                )
            for file_path, score in prf_file_scores.items():
                reason = "prf:" + "+".join(sorted(expansion_terms)[:3])
                self._merge_file_evidence(
                    evidence_by_file,
                    file_path,
                    source="prf",
                    reason=reason,
                    score=score,
                )
                existing = candidate_by_path.get(file_path)
                if existing is not None:
                    existing.score += min(3.0, score * 0.4)
                    existing.reasons = list(dict.fromkeys([reason] + existing.reasons))[:8]
                    continue
                info = self._get_file_info_record(file_path)
                candidate = self._score_file_for_task(
                    file_path=file_path,
                    info=info,
                    term_weights=term_weights,
                    active_files=normalized_active_files,
                    changed_files=normalized_changed_files,
                    base_score=score,
                    reason_override=reason,
                    query_text=query_text,
                    anchor_file_terms=anchor_file_terms,
                    score_content=False,
                )
                if candidate:
                    file_candidates.append(candidate)
                    candidate_by_path[file_path] = candidate
                    seen_file_candidates.add(file_path)

        for candidate in file_candidates:
            self._fuse_task_file_evidence(candidate, evidence_by_file.get(candidate.file_path, []))
        self._rerank_task_file_candidates(file_candidates, evidence_by_file)
        for candidate in file_candidates:
            candidate.score *= self._task_file_role_multiplier(
                candidate.file_path,
                candidate.tags,
                query_text,
            )
        file_candidates.sort(key=lambda item: (-item.score, item.file_path.lower()))
        selected_file_candidates = self._select_task_file_candidates(
            file_candidates,
            term_weights=term_weights,
            limit=max_files,
            query_text=query_text,
        )
        selected_files: Dict[str, TaskContextFile] = {
            item.file_path: item for item in selected_file_candidates
        }

        symbol_search_terms = [] if fast else sorted(
            (
                (term, weight)
                for term, weight in term_weights.items()
                if re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]{2,}", term)
            ),
            key=lambda item: (-item[1], item[0]),
        )[:8]
        for term, weight in symbol_search_terms:
            for symbol in self.symbol_table.search(term, limit=max_symbols * 6):
                symbol_scores[symbol.qualified_name] += self._score_symbol_for_task(symbol, term, weight)
                symbol_reasons[symbol.qualified_name].add(f"term:{term}")

        for file_candidate in file_candidates[: max_files * 2]:
            file_symbols = self.symbol_table.get_all_in_file(file_candidate.file_path)
            for symbol in file_symbols[:8]:
                boost = max(0.4, file_candidate.score * 0.22)
                if any(term in symbol.qualified_name.lower() or term in symbol.name.lower() for term in term_weights):
                    boost += 0.8
                symbol_scores[symbol.qualified_name] += boost
                symbol_reasons[symbol.qualified_name].add("matched-file")

        ranked_symbols = sorted(symbol_scores.items(), key=lambda item: (-item[1], item[0]))
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
        for qualified_name, _ in sorted(expanded_symbols.items(), key=lambda item: (-item[1], item[0])):
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
                    score_content=False,
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

        selected_file_list = list(selected_files.values())[:max_files]
        workspace_profile = None if fast else detect_workspace_profile(
            self.project_root,
            focus_files=[item.file_path for item in selected_file_list],
        )
        for item in selected_file_list:
            item.evidence = sorted(
                evidence_by_file.get(item.file_path, []),
                key=lambda evidence: (
                    -float(evidence.get("score", 0.0)),
                    str(evidence.get("source", "")),
                    str(evidence.get("reason", "")),
                    int(evidence.get("line", 0) or 0),
                ),
            )[:8]
            if not fast:
                file_symbols = [
                    symbol
                    for symbol in selected_symbols
                    if symbol.file_path and self._normalize_file_path(symbol.file_path) == item.file_path
                ][:3]
                item.excerpt = self._build_file_excerpt(
                    item.file_path,
                    file_symbols,
                    term_weights=term_weights,
                    evidence=item.evidence,
                )

        memory_fragments: List[Dict[str, str]] = []
        if not fast and include_memory and self.memory_indexer:
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
        if not fast and include_history and self.git_integration and getattr(self.git_integration, "is_available", False):
            seen_commits: Set[str] = set()
            commit_candidates: List[Any] = []
            try:
                commit_candidates.extend(self.git_integration.search_commits(query_text, limit=3))
            except Exception:
                report_suppressed_exception("search Git commit context")
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

        if fast:
            context_string, token_estimate = "", 0
        else:
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
                "fast": bool(fast),
                "workspace": workspace_profile.to_dict() if workspace_profile else {},
                "evidence_sources": sorted(
                    {
                        str(evidence.get("source"))
                        for item in selected_file_list
                        for evidence in item.evidence
                        if evidence.get("source")
                    }
                ),
                "fast_context": fast_context_result.to_dict() if fast_context_result else {},
                "fast_context_skipped": fast_context_skipped,
                "targeted_content_hits": len(targeted_content_hits),
                "targeted_content_ms": round(targeted_content_ms, 3),
                "chunk_hits": len(chunk_hits),
                "chunk_search_ms": round(chunk_search_ms, 3),
                "graph_hits": len(graph_hits),
                "graph_files": len(graph_file_boosts),
                "test_source_hits": len(test_source_hits),
            },
        )
        self._task_cache[cache_key] = (time.time(), result)
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
        score_content: bool = True,
    ) -> Optional[TaskContextFile]:
        """Score a cached file record for a task-oriented retrieval request."""
        if info is None:
            return None

        summary = str(self._get_file_meta(info, "summary", "") or "")
        keywords = {str(value).lower() for value in self._get_file_meta(info, "keywords", [])}
        tag_values = [str(value).lower() for value in self._get_file_meta(info, "tags", [])]
        tags = set(tag_values)
        symbol_names = tuple(str(value).lower() for value in self._get_file_meta(info, "symbol_names", []))
        imports = self._get_file_meta(info, "imports", []) or []
        import_names = []
        for item in imports:
            if isinstance(item, dict):
                import_names.append(str(item.get("module") or item.get("name") or item.get("path") or "").lower())
        symbol_text = " ".join(symbol_names)
        import_text = " ".join(import_names)
        tag_text = " ".join(tags)
        path_lower = self._workspace_relative_path(file_path).lower().replace("\\", "/").strip("/")
        path_parts = [part for part in path_lower.split("/") if part]
        path_tokens = set(self._tokenize_query(" ".join(path_parts)))
        summary_lower = summary.lower()
        anchor_file_terms = anchor_file_terms or set()

        score = float(base_score)
        reasons: List[str] = [reason_override] if reason_override else []
        matched_terms: Set[str] = set()
        matched_path_terms: Set[str] = set()
        for anchor in anchor_file_terms:
            anchor_lower = str(anchor or "").lower().replace("\\", "/")
            if not anchor_lower:
                continue
            if self._path_matches_file_anchor(path_lower, anchor_lower):
                score += 8.0
                reasons.append(f"anchor-file:{anchor_lower}")
        for term, weight in term_weights.items():
            term_lower = term.lower()
            if (
                len(term_lower) < 3
                and term_lower not in self.TASK_SHORT_TOKENS
            ) or not re.fullmatch(r"[a-z0-9_\u4e00-\u9fff]+", term_lower):
                continue
            if term_lower in keywords:
                score += 2.6 * weight
                reasons.append(f"keyword:{term_lower}")
                matched_terms.add(term_lower)
            path_match = term_lower in path_tokens or (
                len(term_lower) >= 4 and term_lower in path_lower
            )
            if path_match:
                score += 2.2 * weight
                reasons.append(f"path:{term_lower}")
                matched_terms.add(term_lower)
                matched_path_terms.add(term_lower)
            if term_lower in summary_lower:
                score += 1.8 * weight
                reasons.append(f"summary:{term_lower}")
                matched_terms.add(term_lower)
            if term_lower in symbol_text:
                score += 1.7 * weight
                reasons.append(f"symbol:{term_lower}")
                matched_terms.add(term_lower)
            if term_lower in import_text:
                score += 1.2 * weight
                reasons.append(f"import:{term_lower}")
                matched_terms.add(term_lower)
            if term_lower in tags or term_lower in tag_text:
                score += 1.1 * weight
                reasons.append(f"tag:{term_lower}")
                matched_terms.add(term_lower)

        if len(matched_terms) > 1:
            coverage_boost = min(4.0, 0.45 * (len(matched_terms) - 1))
            score += coverage_boost
            reasons.append(f"term-coverage:{len(matched_terms)}")
        if len(matched_path_terms) > 1:
            path_coverage_boost = min(2.5, 0.65 * (len(matched_path_terms) - 1))
            score += path_coverage_boost
            reasons.append(f"path-coverage:{len(matched_path_terms)}")

        role_boost, role_reasons = self._query_role_boost(file_path, tags, query_text)
        if role_boost:
            score += role_boost
            reasons.extend(role_reasons)

        if score_content:
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
            tags=tag_values[:6],
        )

    @staticmethod
    def _fuse_task_file_evidence(candidate: TaskContextFile, evidence: List[Dict[str, Any]]) -> None:
        """Reward agreement between independent retrieval signals without score inflation."""
        source_weights = {"fts": 0.65, "fastcontext": 0.85, "lsp": 0.75}
        source_caps = {"fts": 3.5, "fastcontext": 4.5, "lsp": 3.0}
        best_by_source: Dict[str, float] = {}
        for item in evidence:
            raw_source = str(item.get("source", "") or "").strip().lower()
            source = raw_source.split(":", 1)[0]
            if source not in source_weights:
                continue
            best_by_source[source] = max(best_by_source.get(source, 0.0), float(item.get("score", 0.0) or 0.0))
        if not best_by_source:
            return

        extra_score = sum(
            min(source_caps[source], score) * source_weights[source]
            for source, score in best_by_source.items()
        )
        if len(best_by_source) > 1:
            extra_score += min(1.2, (len(best_by_source) - 1) * 0.55)
        candidate.score += extra_score
        reason_prefix = "consensus" if len(best_by_source) > 1 else "signal"
        consensus_reason = reason_prefix + ":" + "+".join(sorted(best_by_source))
        candidate.reasons = list(dict.fromkeys([consensus_reason] + candidate.reasons))[:8]

    @staticmethod
    def _rerank_task_file_candidates(
        candidates: List[TaskContextFile],
        evidence_by_file: Dict[str, List[Dict[str, Any]]],
    ) -> None:
        """Fuse source-local rankings so incomparable raw score scales stay balanced."""
        if not candidates:
            return
        source_weights = {
            "anchor": 3.00,
            "symbol": 2.80,
            "chunk": 2.35,
            "activity": 2.20,
            "graph": 1.85,
            "dependency": 2.05,
            "neighborhood": 2.20,
            "git": 1.75,
            "lsp": 1.55,
            "targeted-content": 1.45,
            "fastcontext": 1.20,
            "prf": 1.15,
            "content": 1.00,
            "fts": 0.95,
            "index": 0.35,
        }
        candidate_by_path = {candidate.file_path: candidate for candidate in candidates}
        base_order = sorted(candidates, key=lambda item: (-item.score, item.file_path.lower()))
        base_rank = {candidate.file_path: rank for rank, candidate in enumerate(base_order, start=1)}

        source_scores: Dict[str, Dict[str, float]] = defaultdict(dict)
        for file_path in candidate_by_path:
            for item in evidence_by_file.get(file_path, []):
                raw_source = str(item.get("source", "") or "").strip().lower()
                source = raw_source.split(":", 1)[0]
                if source not in source_weights:
                    continue
                score = float(item.get("score", 0.0) or 0.0)
                source_scores[source][file_path] = max(source_scores[source].get(file_path, 0.0), score)

        ranks_by_source: Dict[str, Dict[str, int]] = {}
        for source, scores in source_scores.items():
            ordered = sorted(scores.items(), key=lambda item: (-item[1], item[0].lower()))
            ranks_by_source[source] = {
                file_path: rank for rank, (file_path, _) in enumerate(ordered, start=1)
            }

        rrf_k = 24.0
        for candidate in candidates:
            fused_score = rrf_k / (rrf_k + base_rank[candidate.file_path])
            active_sources: List[str] = []
            for source, weight in source_weights.items():
                source_rank = ranks_by_source.get(source, {}).get(candidate.file_path)
                if source_rank is None:
                    continue
                fused_score += weight * rrf_k / (rrf_k + source_rank)
                if source != "index":
                    active_sources.append(source)
            independent_sources = len(set(active_sources))
            if independent_sources > 1:
                fused_score += min(0.55, (independent_sources - 1) * 0.11)
            candidate.score = fused_score
            reason = "rank-fusion:" + ("+".join(sorted(set(active_sources))) if active_sources else "base")
            candidate.reasons = list(dict.fromkeys([reason] + candidate.reasons))[:8]

    def _select_task_file_candidates(
        self,
        candidates: List[TaskContextFile],
        *,
        term_weights: Dict[str, float],
        limit: int,
        query_text: str = "",
    ) -> List[TaskContextFile]:
        """Preserve top relevance while covering distinct intents in compound tasks."""
        target = max(1, int(limit or 1))
        if len(candidates) <= target:
            return list(candidates)

        facet_terms = (
            ("retrieval", {"retrieval", "retriever", "recommend", "recommendation", "ranking", "relevance"}, 1),
            ("compression", {"compression", "compressor", "compaction"}, 1),
            ("tools", {"tool", "tooling", "function"}, 1),
            ("agent", {"agent", "llm", "proactive", "proactively"}, 2),
            ("ui", {"ui", "ux", "frontend", "gui"}, 2),
            ("startup", {"startup", "launch", "boot", "portable"}, 1),
            ("test", {"test", "tests", "testing", "pytest"}, 1),
            ("docs", {"docs", "documentation", "readme", "guide"}, 1),
            ("config", {"config", "configuration", "settings"}, 1),
        )
        facet_weights = term_weights
        if query_text:
            title = next((line.strip() for line in query_text.splitlines() if line.strip()), "")
            facet_weights = self._build_task_term_weights(title)
        active_facets = [
            (facet, quota)
            for facet, terms, quota in facet_terms
            if any(facet_weights.get(term, 0.0) >= 0.85 for term in terms)
        ]
        if not active_facets:
            return list(candidates[:target])

        selected: List[TaskContextFile] = [candidates[0]]
        selected_paths = {candidates[0].file_path}
        candidate_facets = {
            candidate.file_path: self._task_file_facets(candidate)
            for candidate in candidates
        }
        for facet, quota in active_facets:
            matched = [candidate for candidate in candidates if facet in candidate_facets[candidate.file_path]]
            matched.sort(
                key=lambda candidate: (
                    self._task_facet_priority(candidate, facet),
                    -candidate.score,
                    candidate.file_path.lower(),
                )
            )
            added = 0
            for candidate in matched:
                if candidate.file_path in selected_paths:
                    continue
                candidate.reasons = list(dict.fromkeys([f"coverage:{facet}"] + candidate.reasons))[:8]
                selected.append(candidate)
                selected_paths.add(candidate.file_path)
                added += 1
                if added >= quota or len(selected) >= target:
                    break
            if len(selected) >= target:
                return selected

        for candidate in candidates:
            if candidate.file_path in selected_paths:
                continue
            selected.append(candidate)
            selected_paths.add(candidate.file_path)
            if len(selected) >= target:
                break
        return selected

    def _task_file_facets(self, candidate: TaskContextFile) -> Set[str]:
        path = candidate.file_path.lower().replace("\\", "/")
        name = Path(path).name
        tags = set(candidate.tags)
        facets: Set[str] = set()
        if any(term in path for term in ("retriev", "recommend", "ranking", "relevance")):
            facets.add("retrieval")
        if "compress" in path or "compaction" in path:
            facets.add("compression")
        if "/tools/" in path or "tools" in tags or "tool_manifest" in name:
            facets.add("tools")
        suffix = Path(path).suffix
        if "/agent/" in path and suffix in {".py", ".ts", ".tsx"}:
            facets.add("agent")
        if "reveriecli-ui/" in path or (
            "ui" in tags and suffix in {".css", ".html", ".js", ".jsx", ".scss", ".ts", ".tsx"}
        ):
            facets.add("ui")
        if any(term in path for term in ("/electron/", "portable", "kernel-resolver", "/__main__.py")):
            facets.add("startup")
        if "/tests/" in path or name.startswith("test_") or ".test." in name:
            facets.add("test")
        if "/docs/" in path or name.startswith("readme"):
            facets.add("docs")
        if any(term in name for term in ("config", "settings")) or Path(path).suffix in {".toml", ".yaml", ".yml"}:
            facets.add("config")
        return facets

    @staticmethod
    def _task_facet_priority(candidate: TaskContextFile, facet: str) -> int:
        """Prefer canonical implementation entrypoints within a covered task facet."""
        name = Path(candidate.file_path).name.lower()
        if facet == "agent":
            if name == "agent.py":
                return 0
            if name.startswith("system_prompt"):
                return 1
        if facet == "ui":
            if name.startswith("app."):
                return 0
            if name.startswith("styles."):
                return 1
        return 2

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
        evidence: Optional[List[Dict[str, Any]]] = None,
    ) -> str:
        """Build bounded symbol context plus precise evidence-centered line windows."""
        parts: List[str] = []
        if symbols:
            for index, symbol in enumerate(symbols[:2]):
                include_source = index == 0
                parts.append(symbol.get_context_string(include_source=include_source, max_lines=72))

        raw_evidence_windows: List[Tuple[int, int]] = []
        for item in (evidence or [])[:2]:
            try:
                line = int(item.get("line") or 0)
                line_end = int(item.get("line_end") or line)
            except (TypeError, ValueError):
                continue
            if line <= 0:
                continue
            start = max(0, line - 5)
            end = max(line, line_end) + 4
            if end - start > 32:
                end = start + 32
            raw_evidence_windows.append((start, end))

        evidence_windows: List[Tuple[int, int]] = []
        for start, end in sorted(raw_evidence_windows):
            if evidence_windows and start <= evidence_windows[-1][1] + 2:
                evidence_windows[-1] = (evidence_windows[-1][0], max(evidence_windows[-1][1], end))
            else:
                evidence_windows.append((start, end))
            if len(evidence_windows) >= 2:
                break

        try:
            with open(file_path, 'r', encoding='utf-8', errors='ignore') as handle:
                lines = handle.readlines()
        except Exception:
            return "\n\n".join(part for part in parts if part).strip()

        if evidence_windows:
            rendered_windows: List[str] = []
            for start, end in evidence_windows:
                end = min(len(lines), end)
                if start >= end:
                    continue
                window_lines = [f"# Evidence lines {start + 1}-{end}"]
                window_lines.extend(
                    f"{line_no:4d} | {lines[line_no - 1].rstrip()}"
                    for line_no in range(start + 1, end + 1)
                )
                rendered_windows.append("\n".join(window_lines))
            if rendered_windows:
                parts.append("\n\n".join(rendered_windows))

        if parts:
            return "\n\n".join(part for part in parts if part).strip()

        terms = [
            term.lower()
            for term, _ in sorted((term_weights or {}).items(), key=lambda item: (-item[1], item[0]))
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

    @staticmethod
    def _trim_structured_excerpt(excerpt: str, max_chars: int) -> str:
        """Trim a focused excerpt while retaining its opening and closing evidence."""
        text = str(excerpt or "").strip()
        budget = max(0, int(max_chars or 0))
        if len(text) <= budget:
            return text
        if budget < 120:
            return text[:budget].rstrip()
        marker = "\n# ... excerpt truncated to token budget ...\n"
        usable = max(0, budget - len(marker))
        head_budget = usable * 2 // 3
        tail_budget = usable - head_budget
        head = text[:head_budget]
        if "\n" in head:
            head = head.rsplit("\n", 1)[0]
        tail = text[-tail_budget:] if tail_budget else ""
        if "\n" in tail:
            tail = tail.split("\n", 1)[-1]
        return (head.rstrip() + marker + tail.lstrip())[:budget].rstrip()

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
            display_path = self._workspace_relative_path(item.file_path)
            reason_text = ", ".join(item.reasons[:6]) if item.reasons else "relevance"
            summary = " ".join(str(item.summary or "").split())
            summary = summary[:260] + ("..." if len(summary) > 260 else "")
            parts.append(
                f"- {display_path} [score={item.score:.2f}] ({item.language}) :: {summary} :: reasons={reason_text}"
            )
            for evidence in item.evidence[:4]:
                compact_reason = " ".join(str(evidence.get("reason", "") or "").split())
                compact_reason = compact_reason[:240] + ("..." if len(compact_reason) > 240 else "")
                line = f"  evidence: {evidence.get('source')}:{compact_reason}"
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
                symbol_path = self._workspace_relative_path(symbol.file_path)
                parts.append(f"- {symbol.kind.name}: {symbol.qualified_name} ({symbol_path}:{symbol.start_line})")

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

        if relevant_files:
            parts.append("")
            parts.append("--- CURATED EXCERPTS ---")
        current_text = "\n".join(parts)
        current_tokens = int(len(current_text) * self.TOKENS_PER_CHAR)

        for index, item in enumerate(relevant_files):
            display_path = self._workspace_relative_path(item.file_path)
            section_lines = [f"### {display_path}"]
            if item.tags:
                section_lines.append(f"Tags: {', '.join(item.tags)}")
            if item.summary:
                compact_summary = " ".join(str(item.summary).split())
                section_lines.append(f"Summary: {compact_summary[:300]}")
            metadata_section = "\n".join(section_lines)
            metadata_tokens = int(len(metadata_section) * self.TOKENS_PER_CHAR)
            if current_tokens + metadata_tokens > max_tokens:
                break

            remaining_files = len(relevant_files) - index - 1
            remaining_tokens = max(0, max_tokens - current_tokens - metadata_tokens)
            reserved_tokens = min(remaining_tokens, remaining_files * 180)
            excerpt_tokens = max(0, remaining_tokens - reserved_tokens)
            if item.excerpt and excerpt_tokens >= 40:
                language = item.language or ""
                fence_overhead = len(language) + 9
                excerpt_chars = max(0, int(excerpt_tokens / self.TOKENS_PER_CHAR) - fence_overhead)
                excerpt = self._trim_structured_excerpt(item.excerpt, excerpt_chars)
                if excerpt:
                    section_lines.append(f"```{language}\n{excerpt}\n```")

            section = "\n".join(section_lines)
            section_tokens = int(len(section) * self.TOKENS_PER_CHAR)
            if current_tokens + section_tokens > max_tokens:
                section = metadata_section
                section_tokens = metadata_tokens
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
            report_suppressed_exception("collect project-tree retrieval context")
        
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
        scored_symbols.sort(key=lambda item: (-item[0], item[1].qualified_name))
        
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
