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

Advanced Components:
- Semantic Indexer: Deep code understanding through semantic analysis
- Knowledge Graph: Advanced relationship tracking
- Commit History Indexer: Learn from past changes
- Context Engine Core: Unified context management
"""

from .symbol_table import Symbol, SymbolTable, SymbolKind
from .dependency_graph import Dependency, DependencyGraph, DependencyType
from .indexer import CodebaseIndexer, IndexResult, FileInfo, IndexConfig
from .retriever import ContextRetriever, ContextPackage, SymbolContext, EditContext
from .cache import CacheManager
from .git_integration import GitIntegration, CommitInfo, BlameInfo, CommitDetails
from .novel_index import NovelIndex, IndexEntry
from .emotion_tracker import EmotionTracker, EmotionalSnapshot
from .plot_analyzer import PlotAnalyzer, CausalityChain, PlotType
from .continuity_validator import ContinuityValidator, CharacterState, TemporalEvent

# Advanced components
from .semantic_indexer import SemanticIndexer, SemanticNode, CodePattern
from .knowledge_graph import KnowledgeGraph, Entity, Relation, RelationType, PathResult
from .commit_history_indexer import CommitHistoryIndexer, CommitPattern, CodeEvolution, TeamConvention, ChangeType
from .context_engine_core import ContextEngineCore, ContextQuery, ContextResult


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
    # Novel-specific (Writer Mode)
    'NovelIndex',
    'IndexEntry',
    'EmotionTracker',
    'EmotionalSnapshot',
    'PlotAnalyzer',
    'CausalityChain',
    'PlotType',
    'ContinuityValidator',
    'CharacterState',
    'TemporalEvent',
    # Advanced components
    'SemanticIndexer',
    'SemanticNode',
    'CodePattern',
    'KnowledgeGraph',
    'Entity',
    'Relation',
    'RelationType',
    'PathResult',
    'CommitHistoryIndexer',
    'CommitPattern',
    'CodeEvolution',
    'TeamConvention',
    'ChangeType',
    'ContextEngineCore',
    'ContextQuery',
    'ContextResult',
]
