"""
Symbol Table - Core data structure for Context Engine

Stores comprehensive information about all symbols in the codebase:
- Functions, classes, methods, variables
- Type annotations, docstrings, signatures
- Parent-child relationships
- Cross-reference locations

Optimized for large codebases (>5MB source code).
"""

from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Optional, List, Dict, Set, Tuple
from pathlib import Path
import json
import hashlib


class SymbolKind(Enum):
    """Types of symbols that can be indexed"""
    MODULE = auto()
    CLASS = auto()
    FUNCTION = auto()
    METHOD = auto()
    PROPERTY = auto()
    VARIABLE = auto()
    CONSTANT = auto()
    PARAMETER = auto()
    IMPORT = auto()
    INTERFACE = auto()  # For TypeScript/Go
    STRUCT = auto()     # For Rust/Go/C
    ENUM = auto()
    TRAIT = auto()      # For Rust
    TYPE_ALIAS = auto()
    NAMESPACE = auto()  # For C++/C#
    MACRO = auto()      # For C/C++/Rust
    HTML_ELEMENT = auto()
    CSS_SELECTOR = auto()
    CSS_PROPERTY = auto()


@dataclass
class Reference:
    """A reference to a symbol from another location"""
    file_path: str
    line: int
    column: int
    context: str  # The line of code containing the reference
    ref_type: str = "usage"  # usage, call, import, inherit, implement


@dataclass
class Symbol:
    """
    Represents a code symbol with all its metadata.
    
    This is the core unit of the Context Engine's knowledge about the codebase.
    """
    name: str
    qualified_name: str  # Full path like module.Class.method
    kind: SymbolKind
    file_path: str
    start_line: int
    end_line: int
    start_column: int = 0
    end_column: int = 0
    signature: Optional[str] = None  # Function/method signature
    docstring: Optional[str] = None
    source_code: Optional[str] = None  # Actual source code (for context)
    parent: Optional[str] = None  # Parent's qualified_name
    children: List[str] = field(default_factory=list)
    references: List[Reference] = field(default_factory=list)
    type_annotation: Optional[str] = None
    return_type: Optional[str] = None
    parameters: List[Dict] = field(default_factory=list)  # [{name, type, default}]
    decorators: List[str] = field(default_factory=list)
    modifiers: List[str] = field(default_factory=list)  # public, private, static, async, etc.
    language: str = "unknown"
    
    # For optimization when handling large codebases
    content_hash: Optional[str] = None
    
    def to_dict(self) -> dict:
        """Serialize to dictionary for JSON storage"""
        return {
            'name': self.name,
            'qualified_name': self.qualified_name,
            'kind': self.kind.name,
            'file_path': self.file_path,
            'start_line': self.start_line,
            'end_line': self.end_line,
            'start_column': self.start_column,
            'end_column': self.end_column,
            'signature': self.signature,
            'docstring': self.docstring,
            'source_code': self.source_code,
            'parent': self.parent,
            'children': self.children,
            'references': [
                {
                    'file_path': r.file_path,
                    'line': r.line,
                    'column': r.column,
                    'context': r.context,
                    'ref_type': r.ref_type
                }
                for r in self.references
            ],
            'type_annotation': self.type_annotation,
            'return_type': self.return_type,
            'parameters': self.parameters,
            'decorators': self.decorators,
            'modifiers': self.modifiers,
            'language': self.language,
            'content_hash': self.content_hash
        }
    
    @classmethod
    def from_dict(cls, data: dict) -> 'Symbol':
        """Deserialize from dictionary"""
        references = [
            Reference(
                file_path=r['file_path'],
                line=r['line'],
                column=r['column'],
                context=r['context'],
                ref_type=r.get('ref_type', 'usage')
            )
            for r in data.get('references', [])
        ]
        
        return cls(
            name=data['name'],
            qualified_name=data['qualified_name'],
            kind=SymbolKind[data['kind']],
            file_path=data['file_path'],
            start_line=data['start_line'],
            end_line=data['end_line'],
            start_column=data.get('start_column', 0),
            end_column=data.get('end_column', 0),
            signature=data.get('signature'),
            docstring=data.get('docstring'),
            source_code=data.get('source_code'),
            parent=data.get('parent'),
            children=data.get('children', []),
            references=references,
            type_annotation=data.get('type_annotation'),
            return_type=data.get('return_type'),
            parameters=data.get('parameters', []),
            decorators=data.get('decorators', []),
            modifiers=data.get('modifiers', []),
            language=data.get('language', 'unknown'),
            content_hash=data.get('content_hash')
        )
    
    def get_context_string(self, include_source: bool = True, max_lines: int = 50) -> str:
        """
        Generate a context string for this symbol.
        This is what gets sent to the AI model.
        """
        parts = []
        
        # Header with kind and location
        parts.append(f"# {self.kind.name}: {self.qualified_name}")
        parts.append(f"# File: {self.file_path}:{self.start_line}-{self.end_line}")
        parts.append(f"# Language: {self.language}")
        
        if self.modifiers:
            parts.append(f"# Modifiers: {', '.join(self.modifiers)}")
        
        if self.decorators:
            parts.append(f"# Decorators: {', '.join(self.decorators)}")
        
        # Signature
        if self.signature:
            parts.append(f"\n{self.signature}")
        
        # Docstring
        if self.docstring:
            parts.append(f'\n"""{self.docstring}"""')
        
        # Source code (full)
        if self.source_code:
            parts.append('\n' + self.source_code)
        
        return '\n'.join(parts)


class SymbolTable:
    """
    High-performance symbol table for large codebases.
    
    Features:
    - O(1) lookup by qualified name
    - Efficient prefix search for autocomplete
    - File-based indexing for incremental updates
    - Memory-efficient storage with lazy loading
    """
    
    def __init__(self):
        # Main storage: qualified_name -> Symbol
        self._symbols: Dict[str, Symbol] = {}
        
        # Index by file for incremental updates
        self._file_index: Dict[str, Set[str]] = {}  # file_path -> set of qualified_names
        
        # Index by kind for type-specific queries
        self._kind_index: Dict[SymbolKind, Set[str]] = {kind: set() for kind in SymbolKind}
        
        # Index by name (without qualification) for fuzzy search
        self._name_index: Dict[str, Set[str]] = {}  # simple_name -> set of qualified_names
        
        # Statistics
        self._stats = {
            'total_symbols': 0,
            'total_files': 0,
            'by_kind': {kind.name: 0 for kind in SymbolKind},
            'by_language': {}
        }
    
    def add_symbol(self, symbol: Symbol) -> None:
        """Add or update a symbol in the table"""
        qname = symbol.qualified_name
        
        # Remove old symbol if exists (for updates)
        if qname in self._symbols:
            self._remove_from_indices(self._symbols[qname])
        
        # Add to main storage
        self._symbols[qname] = symbol
        
        # Update file index
        if symbol.file_path not in self._file_index:
            self._file_index[symbol.file_path] = set()
            self._stats['total_files'] += 1
        self._file_index[symbol.file_path].add(qname)
        
        # Update kind index
        self._kind_index[symbol.kind].add(qname)
        
        # Update name index
        if symbol.name not in self._name_index:
            self._name_index[symbol.name] = set()
        self._name_index[symbol.name].add(qname)
        
        # Update statistics
        self._stats['total_symbols'] += 1
        self._stats['by_kind'][symbol.kind.name] += 1
        lang = symbol.language
        self._stats['by_language'][lang] = self._stats['by_language'].get(lang, 0) + 1
    
    def _remove_from_indices(self, symbol: Symbol) -> None:
        """Remove symbol from all indices"""
        qname = symbol.qualified_name
        
        if symbol.file_path in self._file_index:
            self._file_index[symbol.file_path].discard(qname)
        
        self._kind_index[symbol.kind].discard(qname)
        
        if symbol.name in self._name_index:
            self._name_index[symbol.name].discard(qname)
        
        self._stats['total_symbols'] -= 1
        self._stats['by_kind'][symbol.kind.name] -= 1
    
    def get_symbol(self, qualified_name: str) -> Optional[Symbol]:
        """Get symbol by fully qualified name - O(1)"""
        return self._symbols.get(qualified_name)
    
    def find_by_name(self, name: str) -> List[Symbol]:
        """Find all symbols with a given simple name"""
        qnames = self._name_index.get(name, set())
        return [self._symbols[qn] for qn in qnames if qn in self._symbols]
    
    def find_by_pattern(self, pattern: str, limit: int = 999999) -> List[Symbol]:
        """
        Find symbols matching a pattern (supports * wildcard).
        Used for fuzzy search.
        """
        import fnmatch
        results = []
        
        for qname in self._symbols:
            if fnmatch.fnmatch(qname.lower(), pattern.lower()):
                results.append(self._symbols[qname])
                if len(results) >= limit:
                    break
        
        return results
    
    def find_by_prefix(self, prefix: str, limit: int = 999999) -> List[Symbol]:
        """Find symbols with qualified names starting with prefix"""
        results = []
        prefix_lower = prefix.lower()
        
        for qname in self._symbols:
            if qname.lower().startswith(prefix_lower):
                results.append(self._symbols[qname])
                if len(results) >= limit:
                    break
        
        return results
    
    def get_by_kind(self, kind: SymbolKind, limit: int = 999999) -> List[Symbol]:
        """Get all symbols of a specific kind"""
        qnames = list(self._kind_index.get(kind, set()))[:limit]
        return [self._symbols[qn] for qn in qnames if qn in self._symbols]
    
    def get_all_in_file(self, file_path: str) -> List[Symbol]:
        """Get all symbols defined in a file"""
        qnames = self._file_index.get(file_path, set())
        symbols = [self._symbols[qn] for qn in qnames if qn in self._symbols]
        # Sort by line number
        return sorted(symbols, key=lambda s: s.start_line)
    
    def get_children(self, qualified_name: str) -> List[Symbol]:
        """Get all direct children of a symbol"""
        parent = self.get_symbol(qualified_name)
        if not parent:
            return []
        return [self._symbols[c] for c in parent.children if c in self._symbols]
    
    def remove_file(self, file_path: str) -> int:
        """Remove all symbols from a file (for updates). Returns count removed."""
        if file_path not in self._file_index:
            return 0
        
        qnames = list(self._file_index[file_path])
        for qname in qnames:
            if qname in self._symbols:
                self._remove_from_indices(self._symbols[qname])
                del self._symbols[qname]
        
        del self._file_index[file_path]
        self._stats['total_files'] -= 1
        
        return len(qnames)
    
    def update_file(self, file_path: str, symbols: List[Symbol]) -> None:
        """Update all symbols for a file (removes old, adds new)"""
        self.remove_file(file_path)
        for symbol in symbols:
            self.add_symbol(symbol)
    
    def get_statistics(self) -> Dict:
        """Get indexing statistics"""
        return self._stats.copy()
    
    def to_dict(self) -> dict:
        """Serialize entire symbol table to dictionary"""
        return {
            'symbols': {qn: s.to_dict() for qn, s in self._symbols.items()},
            'stats': self._stats
        }
    
    @classmethod
    def from_dict(cls, data: dict) -> 'SymbolTable':
        """Deserialize from dictionary"""
        table = cls()
        for qn, s_data in data.get('symbols', {}).items():
            symbol = Symbol.from_dict(s_data)
            table.add_symbol(symbol)
        return table
    
    def search(
        self,
        query: str,
        kinds: Optional[List[SymbolKind]] = None,
        file_pattern: Optional[str] = None,
        limit: int = 999999
    ) -> List[Symbol]:
        """
        Advanced search with multiple filters.
        
        Args:
            query: Search query (supports wildcards)
            kinds: Filter by symbol kinds
            file_pattern: Filter by file path pattern
            limit: Maximum results
        
        Returns:
            List of matching symbols, sorted by relevance
        """
        import fnmatch
        
        candidates = []
        query_lower = query.lower()
        
        for qname, symbol in self._symbols.items():
            # Kind filter
            if kinds and symbol.kind not in kinds:
                continue
            
            # File pattern filter
            if file_pattern and not fnmatch.fnmatch(symbol.file_path, file_pattern):
                continue
            
            # Query matching
            score = 0
            qname_lower = qname.lower()
            name_lower = symbol.name.lower()
            
            # Exact name match
            if name_lower == query_lower:
                score = 100
            # Name starts with query
            elif name_lower.startswith(query_lower):
                score = 80
            # Query in name
            elif query_lower in name_lower:
                score = 60
            # Query in qualified name
            elif query_lower in qname_lower:
                score = 40
            # Wildcard match
            elif '*' in query and fnmatch.fnmatch(qname_lower, query_lower):
                score = 30
            else:
                continue
            
            candidates.append((score, symbol))
        
        # Sort and return
        candidates.sort(key=lambda x: x[0], reverse=True)
        return [s for _, s in candidates]
    
    def __len__(self) -> int:
        return len(self._symbols)
    
    def __contains__(self, qualified_name: str) -> bool:
        return qualified_name in self._symbols
