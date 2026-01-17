"""
Context Engine Core - Unified context management system

The Context Engine Core integrates all context engine components:
- Semantic Indexer: Deep code understanding
- Knowledge Graph: Relationship tracking
- Commit History Indexer: Learning from past changes
- Symbol Table: Traditional symbol indexing
- Dependency Graph: Dependency tracking
- Git Integration: Version control context

This provides a unified interface for intelligent context retrieval
and code understanding.
"""

from pathlib import Path
from typing import List, Dict, Optional, Set, Tuple, Any
from dataclasses import dataclass, field
import json
import time

from .symbol_table import SymbolTable, Symbol
from .dependency_graph import DependencyGraph
from .semantic_indexer import SemanticIndexer, SemanticNode, CodePattern
from .knowledge_graph import KnowledgeGraph, Entity, Relation, RelationType
from .commit_history_indexer import CommitHistoryIndexer, CommitPattern
from .cache import CacheManager


@dataclass
class ContextQuery:
    """A query for context"""
    query_type: str  # symbol, file, search, semantic, pattern, impact
    query: str
    options: Dict = field(default_factory=dict)
    
    def to_dict(self) -> dict:
        return {
            'query_type': self.query_type,
            'query': self.query,
            'options': self.options
        }


@dataclass
class ContextResult:
    """Result of a context query"""
    success: bool
    data: Any
    metadata: Dict = field(default_factory=dict)
    errors: List[str] = field(default_factory=list)
    
    def to_dict(self) -> dict:
        return {
            'success': self.success,
            'data': self.data,
            'metadata': self.metadata,
            'errors': self.errors
        }


class ContextEngineCore:
    """
    Unified Context Engine for deep code understanding.
    
    This is the main entry point for all context-related operations.
    It integrates multiple specialized components to provide:
    - Symbol-based code understanding
    - Semantic search and analysis
    - Relationship tracking
    - Historical context
    - Pattern recognition
    """
    
    def __init__(self, project_root: Path):
        self.project_root = project_root
        
        # Core components
        self.symbol_table = SymbolTable()
        self.dependency_graph = DependencyGraph()
        self.semantic_indexer = SemanticIndexer(project_root)
        self.knowledge_graph = KnowledgeGraph()
        self.commit_history = CommitHistoryIndexer(project_root)
        
        # Cache manager
        cache_dir = project_root / '.reverie' / 'context_cache'
        self.cache_manager = CacheManager(cache_dir)
        
        # Statistics
        self._stats = {
            'total_symbols': 0,
            'total_dependencies': 0,
            'total_semantic_nodes': 0,
            'total_knowledge_entities': 0,
            'total_patterns': 0,
            'index_time_ms': 0
        }
    
    def query(self, context_query: ContextQuery) -> ContextResult:
        """
        Execute a context query.
        
        This is the main entry point for context retrieval.
        """
        try:
            if context_query.query_type == 'symbol':
                return self._query_symbol(context_query)
            elif context_query.query_type == 'file':
                return self._query_file(context_query)
            elif context_query.query_type == 'search':
                return self._query_search(context_query)
            elif context_query.query_type == 'semantic':
                return self._query_semantic(context_query)
            elif context_query.query_type == 'pattern':
                return self._query_pattern(context_query)
            elif context_query.query_type == 'impact':
                return self._query_impact(context_query)
            elif context_query.query_type == 'architecture':
                return self._query_architecture(context_query)
            elif context_query.query_type == 'history':
                return self._query_history(context_query)
            else:
                return ContextResult(
                    success=False,
                    data=None,
                    errors=[f"Unknown query type: {context_query.query_type}"]
                )
        except Exception as e:
            return ContextResult(
                success=False,
                data=None,
                errors=[str(e)]
            )
    
    def _query_symbol(self, query: ContextQuery) -> ContextResult:
        """Query for symbol information"""
        symbol_name = query.query
        include_source = query.options.get('include_source', True)
        include_dependencies = query.options.get('include_dependencies', True)
        
        # Get symbol from symbol table
        symbol = self.symbol_table.get_symbol(symbol_name)
        
        if not symbol:
            # Try fuzzy search
            matches = self.symbol_table.find_by_name(symbol_name)
            if matches:
                symbol = matches[0]
            else:
                return ContextResult(
                    success=False,
                    data=None,
                    errors=[f"Symbol not found: {symbol_name}"]
                )
        
        # Build result
        result = {
            'symbol': symbol.to_dict() if include_source else {
                'name': symbol.name,
                'qualified_name': symbol.qualified_name,
                'kind': symbol.kind.name,
                'file_path': symbol.file_path,
                'line_start': symbol.line_start,
                'line_end': symbol.line_end
            }
        }
        
        # Add dependencies if requested
        if include_dependencies:
            deps = self.dependency_graph.get_dependencies(
                symbol.qualified_name,
                depth=query.options.get('max_depth', 2)
            )
            result['dependencies'] = [d.to_dict() for d in deps]
        
        # Add semantic information if available
        semantic_node = self.semantic_indexer.nodes.get(symbol.qualified_name)
        if semantic_node:
            result['semantic'] = semantic_node.to_dict()
        
        return ContextResult(success=True, data=result)
    
    def _query_file(self, query: ContextQuery) -> ContextResult:
        """Query for file information"""
        file_path = query.query
        
        # Get symbols in file
        symbols = self.symbol_table.get_symbols_in_file(file_path)
        
        # Get semantic nodes in file
        semantic_nodes = [
            node for node in self.semantic_indexer.nodes.values()
            if node.file_path == file_path
        ]
        
        # Get knowledge entities in file
        entities = [
            entity for entity in self.knowledge_graph.entities.values()
            if entity.file_path == file_path
        ]
        
        result = {
            'file_path': file_path,
            'symbols': [s.to_dict() for s in symbols],
            'semantic_nodes': [n.to_dict() for n in semantic_nodes],
            'entities': [e.to_dict() for e in entities],
            'symbol_count': len(symbols),
            'semantic_node_count': len(semantic_nodes),
            'entity_count': len(entities)
        }
        
        return ContextResult(success=True, data=result)
    
    def _query_search(self, query: ContextQuery) -> ContextResult:
        """Search for symbols"""
        pattern = query.query
        filter_kind = query.options.get('filter_kind', 'all')
        limit = query.options.get('limit', 20)
        
        # Search symbol table
        symbols = self.symbol_table.find_by_pattern(pattern, limit=limit)
        
        # Filter by kind if specified
        if filter_kind != 'all':
            from .symbol_table import SymbolKind
            try:
                kind_filter = SymbolKind[filter_kind.upper()]
                symbols = [s for s in symbols if s.kind == kind_filter]
            except KeyError:
                pass
        
        result = {
            'query': pattern,
            'matches': [s.to_dict() for s in symbols],
            'match_count': len(symbols)
        }
        
        return ContextResult(success=True, data=result)
    
    def _query_semantic(self, query: ContextQuery) -> ContextResult:
        """Perform semantic search"""
        search_query = query.query
        node_type = query.options.get('node_type')
        limit = query.options.get('limit', 20)
        
        # Use semantic indexer
        results = self.semantic_indexer.semantic_search(
            search_query,
            node_type=node_type,
            limit=limit
        )
        
        result = {
            'query': search_query,
            'results': [
                {
                    'node': node.to_dict(),
                    'relevance_score': score
                }
                for node, score in results
            ],
            'result_count': len(results)
        }
        
        return ContextResult(success=True, data=result)
    
    def _query_pattern(self, query: ContextQuery) -> ContextResult:
        """Find relevant code patterns"""
        context = query.query
        pattern_type = query.options.get('pattern_type')
        limit = query.options.get('limit', 10)
        
        # Find patterns from semantic indexer
        semantic_patterns = self.semantic_indexer.find_patterns(
            context,
            pattern_type=pattern_type,
            limit=limit
        )
        
        # Find patterns from commit history
        commit_patterns = self.commit_history.find_relevant_patterns(
            context,
            change_type=pattern_type,
            limit=limit
        )
        
        result = {
            'context': context,
            'semantic_patterns': [p.to_dict() for p in semantic_patterns],
            'commit_patterns': [p.to_dict() for p in commit_patterns],
            'total_patterns': len(semantic_patterns) + len(commit_patterns)
        }
        
        return ContextResult(success=True, data=result)
    
    def _query_impact(self, query: ContextQuery) -> ContextResult:
        """Analyze impact of changes"""
        entity_id = query.query
        max_depth = query.options.get('max_depth', 3)
        
        # Get impact analysis from knowledge graph
        impact = self.knowledge_graph.get_impact_analysis(
            entity_id,
            max_depth=max_depth
        )
        
        result = {
            'entity_id': entity_id,
            'impact_analysis': impact
        }
        
        return ContextResult(success=True, data=result)
    
    def _query_architecture(self, query: ContextQuery) -> ContextResult:
        """Get architecture overview"""
        overview = self.knowledge_graph.get_architecture_overview()
        
        result = {
            'architecture': overview
        }
        
        return ContextResult(success=True, data=result)
    
    def _query_history(self, query: ContextQuery) -> ContextResult:
        """Query commit history"""
        file_path = query.query
        entity_name = query.options.get('entity_name')
        
        # Get evolution history
        evolutions = self.commit_history.get_evolution_history(
            file_path,
            entity_name=entity_name
        )
        
        result = {
            'file_path': file_path,
            'evolutions': [e.to_dict() for e in evolutions],
            'evolution_count': len(evolutions)
        }
        
        return ContextResult(success=True, data=result)
    
    def get_intelligent_context(
        self,
        file_path: str,
        line_range: Tuple[int, int],
        max_tokens: int = 10000
    ) -> Dict[str, Any]:
        """
        Get intelligent context for an edit operation.
        
        This combines information from all context engine components
        to provide comprehensive context for code editing.
        """
        # Get context from semantic indexer
        semantic_context = self.semantic_indexer.get_context_for_edit(
            file_path,
            line_range,
            max_tokens=max_tokens
        )
        
        # Get symbols in the file
        symbols = self.symbol_table.get_symbols_in_file(file_path)
        
        # Find overlapping symbols
        overlapping_symbols = [
            s for s in symbols
            if not (s.line_end < line_range[0] or s.line_start > line_range[1])
        ]
        
        # Get impact analysis for overlapping symbols
        impact_analyses = []
        for symbol in overlapping_symbols:
            impact = self.knowledge_graph.get_impact_analysis(
                symbol.qualified_name,
                max_depth=2
            )
            if impact:
                impact_analyses.append({
                    'symbol': symbol.qualified_name,
                    'impact': impact
                })
        
        # Get relevant patterns
        context_keywords = []
        for node in semantic_context.get('relevant_nodes', []):
            context_keywords.extend(node.keywords)
            context_keywords.extend(node.concepts)
        
        patterns = self.semantic_indexer.find_patterns(
            " ".join(context_keywords),
            limit=5
        )
        
        return {
            'semantic_context': semantic_context,
            'overlapping_symbols': [s.to_dict() for s in overlapping_symbols],
            'impact_analyses': impact_analyses,
            'patterns': [p.to_dict() for p in patterns],
            'suggestions': semantic_context.get('suggestions', []),
            'warnings': semantic_context.get('warnings', [])
        }
    
    def save_to_cache(self) -> bool:
        """Save all context engine data to cache"""
        try:
            # Save traditional components
            file_info = {}  # Would be populated by indexer
            
            self.cache_manager.save(
                self.symbol_table,
                self.dependency_graph,
                file_info,
                metadata={
                    'semantic_indexer': self.semantic_indexer.to_dict(),
                    'knowledge_graph': self.knowledge_graph.to_dict(),
                    'commit_history': self.commit_history.to_dict()
                }
            )
            
            return True
        except Exception as e:
            print(f"Error saving to cache: {e}")
            return False
    
    def load_from_cache(self) -> bool:
        """Load all context engine data from cache"""
        try:
            cached_data = self.cache_manager.load()
            
            if not cached_data:
                return False
            
            # Load traditional components
            self.symbol_table = cached_data['symbol_table']
            self.dependency_graph = cached_data['dependency_graph']
            
            # Load advanced components from metadata
            metadata = cached_data.get('metadata', {})
            
            if 'semantic_indexer' in metadata:
                self.semantic_indexer = SemanticIndexer.from_dict(
                    metadata['semantic_indexer'],
                    self.project_root
                )
            
            if 'knowledge_graph' in metadata:
                self.knowledge_graph = KnowledgeGraph.from_dict(
                    metadata['knowledge_graph']
                )
            
            if 'commit_history' in metadata:
                self.commit_history = CommitHistoryIndexer.from_dict(
                    metadata['commit_history'],
                    self.project_root
                )
            
            return True
        except Exception as e:
            print(f"Error loading from cache: {e}")
            return False
    
    def get_statistics(self) -> Dict[str, Any]:
        """Get context engine statistics"""
        return {
            'symbols': len(self.symbol_table),
            'dependencies': len(self.dependency_graph),
            'semantic_nodes': len(self.semantic_indexer.nodes),
            'knowledge_entities': len(self.knowledge_graph.entities),
            'knowledge_relations': len(self.knowledge_graph.relations),
            'patterns': len(self.semantic_indexer.patterns),
            'commit_patterns': len(self.commit_history.patterns),
            'conventions': len(self.commit_history.conventions),
            'evolutions': len(self.commit_history.evolutions)
        }