"""
Reverie Context Engine

The world-class Context Engine that powers Reverie's ability to
understand and work with large codebases while minimizing AI hallucinations.

Core Components:
- Symbol Table: High-performance storage for code symbols
- Dependency Graph: Track relationships between symbols
- Codebase Indexer: Scan and index project files
- Context Retriever: Intelligent context selection
- Cache Manager: Persistent storage
- Git Integration: Version control context
"""

from .symbol_table import Symbol, SymbolTable, SymbolKind
from .dependency_graph import Dependency, DependencyGraph, DependencyType
from .indexer import CodebaseIndexer, IndexResult, FileInfo, IndexConfig
from .retriever import ContextRetriever, ContextPackage, SymbolContext, EditContext
from .cache import CacheManager
from .git_integration import GitIntegration, CommitInfo, BlameInfo, CommitDetails


__all__ = [
    # Symbol Table
    'Symbol',
    'SymbolTable',
    'SymbolKind',
    # Dependency Graph
    'Dependency',
    'DependencyGraph',
    'DependencyType',
    # Indexer
    'CodebaseIndexer',
    'IndexResult',
    'FileInfo',
    # Retriever
    'ContextRetriever',
    'ContextPackage',
    'SymbolContext',
    'EditContext',
    # Cache
    'CacheManager',
    # Git
    'GitIntegration',
    'CommitInfo',
    'BlameInfo',
    'CommitDetails',
]
