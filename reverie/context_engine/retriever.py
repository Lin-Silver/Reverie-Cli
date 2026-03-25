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
import time
from collections import defaultdict

from .symbol_table import Symbol, SymbolTable, SymbolKind
from .dependency_graph import DependencyGraph, DependencyType


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
    ):
        self.symbol_table = symbol_table
        self.dependency_graph = dependency_graph
        self.project_root = project_root
        self.file_info = file_info if file_info is not None else {}
        self.git_integration = git_integration
        self.memory_indexer = memory_indexer
        self._activity_files: Dict[str, Dict[str, float]] = {}
        self._activity_symbols: Dict[str, Dict[str, float]] = {}

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

    def _get_file_meta(self, info: Any, key: str, default: Any = None) -> Any:
        if isinstance(info, dict):
            return info.get(key, default)
        return getattr(info, key, default)
    
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
        
        # Get imports from file
        # This would need to be tracked during parsing
        imports = []  # TODO: Get from parse results
        
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
        
        return ContextPackage(
            symbols=included_symbols,
            dependencies=dependencies,
            file_contents=file_contents,
            imports=[],
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
            )
            if candidate and file_path not in seen_file_candidates:
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
        for item in selected_file_list:
            file_symbols = [symbol for symbol in selected_symbols if symbol.file_path == item.file_path][:3]
            item.excerpt = self._build_file_excerpt(item.file_path, file_symbols)

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
                })
                if len(commit_context) >= 5:
                    break

        context_string, token_estimate = self._format_task_context(
            query_text,
            selected_file_list,
            selected_symbols,
            memory_fragments,
            commit_context,
            max_tokens=max_tokens,
        )

        for file_candidate in selected_file_list[:4]:
            self.mark_file_activity(file_candidate.file_path, weight=1.0, reason="task")
        for symbol in selected_symbols[:8]:
            self.mark_symbol_activity(symbol.qualified_name, weight=0.8)

        return TaskContextResult(
            query=query_text,
            relevant_symbols=selected_symbols,
            relevant_files=selected_file_list,
            memory_fragments=memory_fragments,
            commit_context=commit_context,
            context_string=context_string,
            token_estimate=token_estimate,
            metadata={
                "term_weights": term_weights,
                "active_files": sorted(normalized_active_files),
                "changed_files": sorted(normalized_changed_files),
                "selected_file_count": len(selected_file_list),
                "selected_symbol_count": len(selected_symbols),
            },
        )

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

        score = float(base_score)
        reasons: List[str] = [reason_override] if reason_override else []
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

    def _build_file_excerpt(self, file_path: str, symbols: List[Symbol]) -> str:
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
            "--- FILE PRIORITIES ---",
        ]
        for item in relevant_files:
            reason_text = ", ".join(item.reasons) if item.reasons else "relevance"
            parts.append(
                f"- {item.file_path} [score={item.score:.2f}] ({item.language}) :: {item.summary} :: reasons={reason_text}"
            )

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

            # Boost if in the same file or package as reference symbols (heuristics)
            # This requires 'boost' map to contain 'reference_file' or similar metadata
            # For now, we rely on the specific boost list passed in.
            
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
