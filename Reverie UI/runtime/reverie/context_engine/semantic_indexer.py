"""
Semantic Indexer - Advanced code understanding through semantic analysis

The Semantic Indexer goes beyond traditional symbol-based indexing by:
- Understanding code semantics and intent
- Building embeddings for semantic search
- Maintaining a knowledge graph of code relationships
- Learning from commit history and patterns
- Providing intelligent context selection

This is the core of Reverie's ability to understand large codebases
and provide relevant context for AI assistance.
"""

from pathlib import Path
from typing import List, Dict, Optional, Set, Tuple, Any
from dataclasses import dataclass, field
import json
import hashlib
import re
from collections import defaultdict
import time


@dataclass
class SemanticNode:
    """A node in the semantic knowledge graph"""
    id: str
    type: str  # function, class, module, pattern, concept
    name: str
    qualified_name: str
    file_path: str
    line_start: int
    line_end: int
    
    # Semantic information
    embedding: Optional[List[float]] = None  # Vector embedding
    keywords: List[str] = field(default_factory=list)
    concepts: List[str] = field(default_factory=list)
    intent: Optional[str] = None  # What this code does
    
    # Code patterns
    patterns: List[str] = field(default_factory=list)
    anti_patterns: List[str] = field(default_factory=list)
    
    # Relationships
    related_nodes: List[str] = field(default_factory=list)
    similar_nodes: List[str] = field(default_factory=list)
    
    # Metadata
    created_at: float = field(default_factory=time.time)
    last_modified: float = field(default_factory=time.time)
    usage_count: int = 0
    
    def to_dict(self) -> dict:
        return {
            'id': self.id,
            'type': self.type,
            'name': self.name,
            'qualified_name': self.qualified_name,
            'file_path': self.file_path,
            'line_start': self.line_start,
            'line_end': self.line_end,
            'embedding': self.embedding,
            'keywords': self.keywords,
            'concepts': self.concepts,
            'intent': self.intent,
            'patterns': self.patterns,
            'anti_patterns': self.anti_patterns,
            'related_nodes': self.related_nodes,
            'similar_nodes': self.similar_nodes,
            'created_at': self.created_at,
            'last_modified': self.last_modified,
            'usage_count': self.usage_count
        }
    
    @classmethod
    def from_dict(cls, data: dict) -> 'SemanticNode':
        return cls(
            id=data['id'],
            type=data['type'],
            name=data['name'],
            qualified_name=data['qualified_name'],
            file_path=data['file_path'],
            line_start=data['line_start'],
            line_end=data['line_end'],
            embedding=data.get('embedding'),
            keywords=data.get('keywords', []),
            concepts=data.get('concepts', []),
            intent=data.get('intent'),
            patterns=data.get('patterns', []),
            anti_patterns=data.get('anti_patterns', []),
            related_nodes=data.get('related_nodes', []),
            similar_nodes=data.get('similar_nodes', []),
            created_at=data.get('created_at', time.time()),
            last_modified=data.get('last_modified', time.time()),
            usage_count=data.get('usage_count', 0)
        )


@dataclass
class CodePattern:
    """A reusable code pattern learned from the codebase"""
    id: str
    name: str
    pattern_type: str  # architectural, implementation, error_handling, etc.
    description: str
    
    # Pattern instances
    instances: List[Dict] = field(default_factory=list)  # Where this pattern is used
    
    # Pattern characteristics
    complexity: str = "medium"  # simple, medium, complex
    frequency: int = 0
    success_rate: float = 1.0  # Based on commit history
    
    # Related patterns
    related_patterns: List[str] = field(default_factory=list)
    alternative_patterns: List[str] = field(default_factory=list)
    
    # Best practices
    best_practices: List[str] = field(default_factory=list)
    common_mistakes: List[str] = field(default_factory=list)
    
    def to_dict(self) -> dict:
        return {
            'id': self.id,
            'name': self.name,
            'pattern_type': self.pattern_type,
            'description': self.description,
            'instances': self.instances,
            'complexity': self.complexity,
            'frequency': self.frequency,
            'success_rate': self.success_rate,
            'related_patterns': self.related_patterns,
            'alternative_patterns': self.alternative_patterns,
            'best_practices': self.best_practices,
            'common_mistakes': self.common_mistakes
        }
    
    @classmethod
    def from_dict(cls, data: dict) -> 'CodePattern':
        return cls(
            id=data['id'],
            name=data['name'],
            pattern_type=data['pattern_type'],
            description=data['description'],
            instances=data.get('instances', []),
            complexity=data.get('complexity', 'medium'),
            frequency=data.get('frequency', 0),
            success_rate=data.get('success_rate', 1.0),
            related_patterns=data.get('related_patterns', []),
            alternative_patterns=data.get('alternative_patterns', []),
            best_practices=data.get('best_practices', []),
            common_mistakes=data.get('common_mistakes', [])
        )


class SemanticIndexer:
    """
    Advanced semantic indexer for deep code understanding.
    
    Features:
    - Semantic search using embeddings
    - Pattern recognition and learning
    - Knowledge graph maintenance
    - Intent understanding
    - Context-aware retrieval
    """
    
    def __init__(self, project_root: Path):
        self.project_root = project_root
        self.nodes: Dict[str, SemanticNode] = {}
        self.patterns: Dict[str, CodePattern] = {}
        self.keyword_index: Dict[str, Set[str]] = defaultdict(set)
        self.concept_index: Dict[str, Set[str]] = defaultdict(set)
        
        # Statistics
        self._stats = {
            'total_nodes': 0,
            'total_patterns': 0,
            'total_keywords': 0,
            'total_concepts': 0,
            'index_time_ms': 0
        }
    
    def add_node(self, node: SemanticNode) -> None:
        """Add a semantic node to the index"""
        self.nodes[node.id] = node
        
        # Update keyword index
        for keyword in node.keywords:
            self.keyword_index[keyword.lower()].add(node.id)
        
        # Update concept index
        for concept in node.concepts:
            self.concept_index[concept.lower()].add(node.id)
        
        self._stats['total_nodes'] = len(self.nodes)
        self._stats['total_keywords'] = len(self.keyword_index)
        self._stats['total_concepts'] = len(self.concept_index)
    
    def add_pattern(self, pattern: CodePattern) -> None:
        """Add a code pattern to the index"""
        self.patterns[pattern.id] = pattern
        self._stats['total_patterns'] = len(self.patterns)
    
    def semantic_search(
        self,
        query: str,
        node_type: Optional[str] = None,
        limit: int = 20
    ) -> List[Tuple[SemanticNode, float]]:
        """
        Perform semantic search for relevant nodes.
        
        Args:
            query: Search query (natural language or code)
            node_type: Filter by node type
            limit: Maximum results
        
        Returns:
            List of (node, relevance_score) tuples
        """
        # Extract keywords from query
        query_keywords = self._extract_keywords(query)
        
        # Score nodes based on keyword matching
        scored_nodes = []
        
        for node_id, node in self.nodes.items():
            if node_type and node.type != node_type:
                continue
            
            score = self._calculate_relevance(node, query_keywords, query)
            if score > 0:
                scored_nodes.append((node, score))
        
        # Sort by relevance score
        scored_nodes.sort(key=lambda x: x[1], reverse=True)
        
        return scored_nodes[:limit]
    
    def find_similar_nodes(
        self,
        node_id: str,
        limit: int = 10
    ) -> List[Tuple[SemanticNode, float]]:
        """Find nodes similar to the given node"""
        if node_id not in self.nodes:
            return []
        
        target_node = self.nodes[node_id]
        similar_nodes = []
        
        for other_id, other_node in self.nodes.items():
            if other_id == node_id:
                continue
            
            similarity = self._calculate_similarity(target_node, other_node)
            if similarity > 0.3:  # Threshold for similarity
                similar_nodes.append((other_node, similarity))
        
        similar_nodes.sort(key=lambda x: x[1], reverse=True)
        return similar_nodes[:limit]
    
    def find_patterns(
        self,
        context: str,
        pattern_type: Optional[str] = None,
        limit: int = 10
    ) -> List[CodePattern]:
        """Find relevant code patterns for a given context"""
        scored_patterns = []
        
        for pattern in self.patterns.values():
            if pattern_type and pattern.pattern_type != pattern_type:
                continue
            
            score = self._calculate_pattern_relevance(pattern, context)
            if score > 0:
                scored_patterns.append((pattern, score))
        
        scored_patterns.sort(key=lambda x: x[1], reverse=True)
        return [p[0] for p in scored_patterns[:limit]]
    
    def get_context_for_edit(
        self,
        file_path: str,
        line_range: Tuple[int, int],
        max_tokens: int = 10000
    ) -> Dict[str, Any]:
        """
        Get intelligent context for an edit operation.
        
        Returns:
            Dict with:
            - relevant_nodes: List of relevant semantic nodes
            - patterns: List of relevant code patterns
            - suggestions: Context-aware suggestions
            - warnings: Potential issues to watch for
        """
        # Find nodes in the file
        file_nodes = [
            node for node in self.nodes.values()
            if node.file_path == file_path
        ]
        
        # Find nodes that overlap with the edit range
        overlapping_nodes = [
            node for node in file_nodes
            if not (node.line_end < line_range[0] or node.line_start > line_range[1])
        ]
        
        # Find related nodes
        related_node_ids = set()
        for node in overlapping_nodes:
            related_node_ids.update(node.related_nodes)
        
        related_nodes = [
            self.nodes[nid] for nid in related_node_ids
            if nid in self.nodes
        ]
        
        # Find relevant patterns
        context_keywords = []
        for node in overlapping_nodes:
            context_keywords.extend(node.keywords)
            context_keywords.extend(node.concepts)
        
        patterns = self.find_patterns(
            " ".join(context_keywords),
            limit=5
        )
        
        return {
            'relevant_nodes': overlapping_nodes + related_nodes,
            'patterns': patterns,
            'suggestions': self._generate_suggestions(overlapping_nodes, patterns),
            'warnings': self._generate_warnings(overlapping_nodes)
        }
    
    def _extract_keywords(self, text: str) -> List[str]:
        """Extract keywords from text"""
        # Simple keyword extraction (can be enhanced with NLP)
        words = re.findall(r'\b[a-zA-Z_][a-zA-Z0-9_]*\b', text.lower())
        
        # Filter out common words
        stop_words = {
            'the', 'a', 'an', 'is', 'are', 'was', 'were', 'be', 'been', 'being',
            'have', 'has', 'had', 'do', 'does', 'did', 'will', 'would', 'could',
            'should', 'may', 'might', 'must', 'shall', 'can', 'need', 'dare',
            'and', 'or', 'but', 'if', 'then', 'else', 'when', 'where', 'while',
            'for', 'to', 'of', 'in', 'on', 'at', 'by', 'with', 'from', 'as',
            'into', 'through', 'during', 'before', 'after', 'above', 'below',
            'between', 'under', 'again', 'further', 'once', 'here', 'there',
            'why', 'how', 'all', 'each', 'few', 'more', 'most', 'other', 'some',
            'such', 'no', 'nor', 'not', 'only', 'own', 'same', 'so', 'than',
            'too', 'very', 'just', 'also', 'now', 'get', 'make', 'use', 'this'
        }
        
        keywords = [w for w in words if w not in stop_words and len(w) > 2]
        return keywords
    
    def _calculate_relevance(
        self,
        node: SemanticNode,
        query_keywords: List[str],
        query: str
    ) -> float:
        """Calculate relevance score for a node"""
        score = 0.0
        
        # Keyword matching
        node_keywords = set(k.lower() for k in node.keywords)
        query_keywords_set = set(k.lower() for k in query_keywords)
        
        keyword_matches = node_keywords & query_keywords_set
        if keyword_matches:
            score += len(keyword_matches) * 2.0
        
        # Concept matching
        node_concepts = set(c.lower() for c in node.concepts)
        concept_matches = node_concepts & query_keywords_set
        if concept_matches:
            score += len(concept_matches) * 3.0
        
        # Name matching
        if query.lower() in node.name.lower():
            score += 5.0
        
        # Intent matching
        if node.intent and query.lower() in node.intent.lower():
            score += 4.0
        
        # Usage count boost
        score += min(node.usage_count * 0.1, 2.0)
        
        return score
    
    def _calculate_similarity(
        self,
        node1: SemanticNode,
        node2: SemanticNode
    ) -> float:
        """Calculate similarity between two nodes"""
        similarity = 0.0
        
        # Type similarity
        if node1.type == node2.type:
            similarity += 0.3
        
        # Keyword overlap
        keywords1 = set(k.lower() for k in node1.keywords)
        keywords2 = set(k.lower() for k in node2.keywords)
        
        if keywords1 and keywords2:
            overlap = len(keywords1 & keywords2)
            union = len(keywords1 | keywords2)
            similarity += (overlap / union) * 0.4
        
        # Concept overlap
        concepts1 = set(c.lower() for c in node1.concepts)
        concepts2 = set(c.lower() for c in node2.concepts)
        
        if concepts1 and concepts2:
            overlap = len(concepts1 & concepts2)
            union = len(concepts1 | concepts2)
            similarity += (overlap / union) * 0.3
        
        return similarity
    
    def _calculate_pattern_relevance(
        self,
        pattern: CodePattern,
        context: str
    ) -> float:
        """Calculate relevance of a pattern for a given context"""
        score = 0.0
        
        context_lower = context.lower()
        
        # Name matching
        if pattern.name.lower() in context_lower:
            score += 3.0
        
        # Description matching
        if pattern.description:
            desc_words = self._extract_keywords(pattern.description)
            context_words = self._extract_keywords(context)
            matches = set(desc_words) & set(context_words)
            score += len(matches) * 0.5
        
        # Frequency boost
        score += min(pattern.frequency * 0.1, 2.0)
        
        # Success rate boost
        score += pattern.success_rate * 2.0
        
        return score
    
    def _generate_suggestions(
        self,
        nodes: List[SemanticNode],
        patterns: List[CodePattern]
    ) -> List[str]:
        """Generate context-aware suggestions"""
        suggestions = []
        
        # Pattern-based suggestions
        for pattern in patterns:
            if pattern.best_practices:
                suggestions.append(f"Consider using {pattern.name}: {pattern.description}")
        
        # Node-based suggestions
        for node in nodes:
            if node.patterns:
                suggestions.append(f"Follow existing pattern: {', '.join(node.patterns)}")
        
        return suggestions[:5]
    
    def _generate_warnings(
        self,
        nodes: List[SemanticNode]
    ) -> List[str]:
        """Generate warnings for potential issues"""
        warnings = []
        
        for node in nodes:
            if node.anti_patterns:
                warnings.append(f"Avoid anti-patterns: {', '.join(node.anti_patterns)}")
        
        return warnings
    
    def to_dict(self) -> dict:
        """Serialize to dictionary"""
        return {
            'nodes': {nid: node.to_dict() for nid, node in self.nodes.items()},
            'patterns': {pid: pattern.to_dict() for pid, pattern in self.patterns.items()},
            'stats': self._stats
        }
    
    @classmethod
    def from_dict(cls, data: dict, project_root: Path) -> 'SemanticIndexer':
        """Deserialize from dictionary"""
        indexer = cls(project_root)
        
        # Load nodes
        for nid, node_data in data.get('nodes', {}).items():
            indexer.nodes[nid] = SemanticNode.from_dict(node_data)
        
        # Load patterns
        for pid, pattern_data in data.get('patterns', {}).items():
            indexer.patterns[pid] = CodePattern.from_dict(pattern_data)
        
        # Rebuild indexes
        for node in indexer.nodes.values():
            for keyword in node.keywords:
                indexer.keyword_index[keyword.lower()].add(node.id)
            for concept in node.concepts:
                indexer.concept_index[concept.lower()].add(node.id)
        
        indexer._stats = data.get('stats', {})
        
        return indexer