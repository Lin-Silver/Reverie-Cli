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
    
    def __init__(
        self,
        symbol_table: SymbolTable,
        dependency_graph: DependencyGraph,
        project_root: Path
    ):
        self.symbol_table = symbol_table
        self.dependency_graph = dependency_graph
        self.project_root = project_root
    
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
        relevance_boost: Optional[Dict[str, float]] = None
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
                'tokens_used': current_tokens
            }
        )
    
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
