"""
Knowledge Graph - Advanced relationship tracking for code understanding

The Knowledge Graph maintains a rich network of relationships between
code entities, enabling:
- Deep dependency analysis
- Impact prediction
- Architectural understanding
- Pattern discovery
- Intelligent context selection

This goes beyond simple dependency graphs by capturing semantic
relationships and architectural patterns.
"""

from pathlib import Path
from typing import List, Dict, Optional, Set, Tuple, Any
from dataclasses import dataclass, field
from enum import Enum, auto
from collections import defaultdict
import json
import time


class RelationType(Enum):
    """Types of relationships in the knowledge graph"""
    # Structural relationships
    CONTAINS = auto()           # Parent-child containment
    INHERITS = auto()           # Class inheritance
    IMPLEMENTS = auto()         # Interface implementation
    COMPOSES = auto()           # Composition relationship
    
    # Behavioral relationships
    CALLS = auto()              # Function/method calls
    USES = auto()               # Variable/constant usage
    INSTANTIATES = auto()       # Object creation
    DEPENDS_ON = auto()         # General dependency
    
    # Semantic relationships
    SIMILAR_TO = auto()         # Similar functionality
    ALTERNATIVE_TO = auto()     # Alternative implementation
    RELATED_TO = auto()         # General semantic relation
    
    # Architectural relationships
    PART_OF = auto()            # Part of a larger component
    SERVES = auto()             # Serves a purpose
    CONFIGURES = auto()         # Configuration relationship
    VALIDATES = auto()          # Validation relationship
    
    # Data flow
    FLOWS_TO = auto()           # Data flow
    TRANSFORMS = auto()         # Data transformation
    AGGREGATES = auto()         # Data aggregation
    
    # Cross-cutting concerns
    LOGS = auto()               # Logging
    CACHES = auto()             # Caching
    SECURES = auto()            # Security
    MONITORS = auto()           # Monitoring


@dataclass
class Relation:
    """A relationship between two entities in the knowledge graph"""
    id: str
    from_entity: str
    to_entity: str
    relation_type: RelationType
    strength: float = 1.0  # 0.0 to 1.0, indicates relationship strength
    
    # Context
    file_path: str = ""
    line: int = 0
    context: str = ""
    
    # Metadata
    created_at: float = field(default_factory=time.time)
    confidence: float = 1.0  # Confidence in this relationship
    
    def to_dict(self) -> dict:
        return {
            'id': self.id,
            'from_entity': self.from_entity,
            'to_entity': self.to_entity,
            'relation_type': self.relation_type.name,
            'strength': self.strength,
            'file_path': self.file_path,
            'line': self.line,
            'context': self.context,
            'created_at': self.created_at,
            'confidence': self.confidence
        }
    
    @classmethod
    def from_dict(cls, data: dict) -> 'Relation':
        return cls(
            id=data['id'],
            from_entity=data['from_entity'],
            to_entity=data['to_entity'],
            relation_type=RelationType[data['relation_type']],
            strength=data.get('strength', 1.0),
            file_path=data.get('file_path', ''),
            line=data.get('line', 0),
            context=data.get('context', ''),
            created_at=data.get('created_at', time.time()),
            confidence=data.get('confidence', 1.0)
        )


@dataclass
class Entity:
    """An entity in the knowledge graph"""
    id: str
    name: str
    type: str  # function, class, module, file, component, etc.
    qualified_name: str
    file_path: str
    line_start: int
    line_end: int
    
    # Semantic information
    description: Optional[str] = None
    keywords: List[str] = field(default_factory=list)
    tags: List[str] = field(default_factory=list)
    
    # Architectural role
    layer: Optional[str] = None  # presentation, business, data, infrastructure
    component: Optional[str] = None  # Which component/module
    responsibility: Optional[str] = None  # What it's responsible for
    
    # Metrics
    complexity: int = 0
    stability: float = 1.0  # How stable this entity is (0-1)
    importance: float = 1.0  # How important this entity is (0-1)
    
    # Relationships
    outgoing_relations: List[str] = field(default_factory=list)
    incoming_relations: List[str] = field(default_factory=list)
    
    def to_dict(self) -> dict:
        return {
            'id': self.id,
            'name': self.name,
            'type': self.type,
            'qualified_name': self.qualified_name,
            'file_path': self.file_path,
            'line_start': self.line_start,
            'line_end': self.line_end,
            'description': self.description,
            'keywords': self.keywords,
            'tags': self.tags,
            'layer': self.layer,
            'component': self.component,
            'responsibility': self.responsibility,
            'complexity': self.complexity,
            'stability': self.stability,
            'importance': self.importance,
            'outgoing_relations': self.outgoing_relations,
            'incoming_relations': self.incoming_relations
        }
    
    @classmethod
    def from_dict(cls, data: dict) -> 'Entity':
        return cls(
            id=data['id'],
            name=data['name'],
            type=data['type'],
            qualified_name=data['qualified_name'],
            file_path=data['file_path'],
            line_start=data['line_start'],
            line_end=data['line_end'],
            description=data.get('description'),
            keywords=data.get('keywords', []),
            tags=data.get('tags', []),
            layer=data.get('layer'),
            component=data.get('component'),
            responsibility=data.get('responsibility'),
            complexity=data.get('complexity', 0),
            stability=data.get('stability', 1.0),
            importance=data.get('importance', 1.0),
            outgoing_relations=data.get('outgoing_relations', []),
            incoming_relations=data.get('incoming_relations', [])
        )


@dataclass
class PathResult:
    """Result of a path query in the knowledge graph"""
    path: List[str]  # Entity IDs in the path
    relations: List[Relation]  # Relations between entities
    total_strength: float
    path_length: int
    
    def to_dict(self) -> dict:
        return {
            'path': self.path,
            'relations': [r.to_dict() for r in self.relations],
            'total_strength': self.total_strength,
            'path_length': self.path_length
        }


class KnowledgeGraph:
    """
    Advanced knowledge graph for deep code understanding.
    
    Features:
    - Multi-type relationship tracking
    - Path finding and impact analysis
    - Architectural layering
    - Entity importance scoring
    - Pattern discovery
    """
    
    def __init__(self):
        self.entities: Dict[str, Entity] = {}
        self.relations: Dict[str, Relation] = {}
        
        # Indexes for fast lookup
        self._entity_by_type: Dict[str, Set[str]] = defaultdict(set)
        self._entity_by_layer: Dict[str, Set[str]] = defaultdict(set)
        self._entity_by_component: Dict[str, Set[str]] = defaultdict(set)
        self._relations_by_type: Dict[RelationType, Set[str]] = defaultdict(set)
        
        # Adjacency lists
        self._outgoing: Dict[str, Set[str]] = defaultdict(set)
        self._incoming: Dict[str, Set[str]] = defaultdict(set)
        
        # Statistics
        self._stats = {
            'total_entities': 0,
            'total_relations': 0,
            'avg_connections': 0.0
        }
    
    def add_entity(self, entity: Entity) -> None:
        """Add an entity to the graph"""
        self.entities[entity.id] = entity
        
        # Update indexes
        self._entity_by_type[entity.type].add(entity.id)
        if entity.layer:
            self._entity_by_layer[entity.layer].add(entity.id)
        if entity.component:
            self._entity_by_component[entity.component].add(entity.id)
        
        self._stats['total_entities'] = len(self.entities)
    
    def add_relation(self, relation: Relation) -> None:
        """Add a relation to the graph"""
        self.relations[relation.id] = relation
        
        # Update indexes
        self._relations_by_type[relation.relation_type].add(relation.id)
        
        # Update adjacency
        self._outgoing[relation.from_entity].add(relation.id)
        self._incoming[relation.to_entity].add(relation.id)
        
        # Update entity relation lists
        if relation.from_entity in self.entities:
            self.entities[relation.from_entity].outgoing_relations.append(relation.id)
        if relation.to_entity in self.entities:
            self.entities[relation.to_entity].incoming_relations.append(relation.id)
        
        self._stats['total_relations'] = len(self.relations)
        self._update_avg_connections()
    
    def find_path(
        self,
        from_entity: str,
        to_entity: str,
        relation_types: Optional[List[RelationType]] = None,
        max_depth: int = 5
    ) -> Optional[PathResult]:
        """
        Find a path between two entities.
        
        Args:
            from_entity: Starting entity ID
            to_entity: Target entity ID
            relation_types: Filter by relation types (None = all)
            max_depth: Maximum path length
        
        Returns:
            PathResult if path found, None otherwise
        """
        if from_entity not in self.entities or to_entity not in self.entities:
            return None
        
        # BFS to find shortest path
        from collections import deque
        
        queue = deque([(from_entity, [], 1.0)])
        visited = {from_entity}
        
        while queue:
            current, path, strength = queue.popleft()
            
            if current == to_entity:
                # Build path result
                relations = []
                for i in range(len(path)):
                    relations.append(self.relations[path[i]])
                
                return PathResult(
                    path=[from_entity] + [self.relations[r].to_entity for r in path],
                    relations=relations,
                    total_strength=strength,
                    path_length=len(path)
                )
            
            if len(path) >= max_depth:
                continue
            
            # Explore neighbors
            for rel_id in self._outgoing[current]:
                rel = self.relations[rel_id]
                
                if relation_types and rel.relation_type not in relation_types:
                    continue
                
                next_entity = rel.to_entity
                if next_entity in visited:
                    continue
                
                visited.add(next_entity)
                new_strength = strength * rel.strength
                queue.append((next_entity, path + [rel_id], new_strength))
        
        return None
    
    def get_impact_analysis(
        self,
        entity_id: str,
        max_depth: int = 3
    ) -> Dict[str, Any]:
        """
        Analyze the impact of changes to an entity.
        
        Returns:
            Dict with:
            - affected_entities: List of affected entity IDs
            - impact_paths: List of paths to affected entities
            - critical_entities: Entities that would be critically affected
            - suggested_tests: Suggested test cases
        """
        if entity_id not in self.entities:
            return {}
        
        # Find all entities that depend on this one
        affected = set()
        impact_paths = []
        
        # BFS to find dependents
        from collections import deque
        queue = deque([(entity_id, [])])
        visited = {entity_id}
        
        while queue and len(visited) <= 100:  # Limit to prevent explosion
            current, path = queue.popleft()
            
            for rel_id in self._incoming[current]:
                rel = self.relations[rel_id]
                dependent = rel.from_entity
                
                if dependent not in visited:
                    visited.add(dependent)
                    affected.add(dependent)
                    new_path = path + [rel_id]
                    impact_paths.append((dependent, new_path))
                    queue.append((dependent, new_path))
        
        # Identify critical entities (high importance, high stability)
        critical_entities = []
        for eid in affected:
            entity = self.entities.get(eid)
            if entity and entity.importance > 0.7 and entity.stability > 0.8:
                critical_entities.append(eid)
        
        # Generate test suggestions
        suggested_tests = self._generate_test_suggestions(
            entity_id,
            list(affected),
            critical_entities
        )
        
        return {
            'affected_entities': list(affected),
            'impact_paths': impact_paths,
            'critical_entities': critical_entities,
            'suggested_tests': suggested_tests
        }
    
    def get_architecture_overview(self) -> Dict[str, Any]:
        """Get an overview of the codebase architecture"""
        layers = {}
        components = {}
        
        # Group by layer
        for layer, entity_ids in self._entity_by_layer.items():
            layers[layer] = {
                'entity_count': len(entity_ids),
                'entities': list(entity_ids)
            }
        
        # Group by component
        for component, entity_ids in self._entity_by_component.items():
            components[component] = {
                'entity_count': len(entity_ids),
                'entities': list(entity_ids)
            }
        
        # Find key entities
        key_entities = sorted(
            self.entities.values(),
            key=lambda e: e.importance,
            reverse=True
        )[:20]
        
        return {
            'layers': layers,
            'components': components,
            'key_entities': [e.id for e in key_entities],
            'total_entities': len(self.entities),
            'total_relations': len(self.relations)
        }
    
    def find_similar_entities(
        self,
        entity_id: str,
        limit: int = 10
    ) -> List[Tuple[Entity, float]]:
        """Find entities similar to the given entity"""
        if entity_id not in self.entities:
            return []
        
        target = self.entities[entity_id]
        similar = []
        
        for other_id, other in self.entities.items():
            if other_id == entity_id:
                continue
            
            similarity = self._calculate_entity_similarity(target, other)
            if similarity > 0.3:
                similar.append((other, similarity))
        
        similar.sort(key=lambda x: x[1], reverse=True)
        return similar[:limit]
    
    def _calculate_entity_similarity(
        self,
        entity1: Entity,
        entity2: Entity
    ) -> float:
        """Calculate similarity between two entities"""
        similarity = 0.0
        
        # Type similarity
        if entity1.type == entity2.type:
            similarity += 0.3
        
        # Layer similarity
        if entity1.layer and entity1.layer == entity2.layer:
            similarity += 0.2
        
        # Component similarity
        if entity1.component and entity1.component == entity2.component:
            similarity += 0.2
        
        # Keyword overlap
        keywords1 = set(k.lower() for k in entity1.keywords)
        keywords2 = set(k.lower() for k in entity2.keywords)
        
        if keywords1 and keywords2:
            overlap = len(keywords1 & keywords2)
            union = len(keywords1 | keywords2)
            similarity += (overlap / union) * 0.3
        
        return similarity
    
    def _generate_test_suggestions(
        self,
        changed_entity: str,
        affected_entities: List[str],
        critical_entities: List[str]
    ) -> List[str]:
        """Generate test suggestions based on impact analysis"""
        suggestions = []
        
        # Test the changed entity
        changed = self.entities.get(changed_entity)
        if changed:
            suggestions.append(f"Test {changed.name} ({changed.type})")
        
        # Test critical entities
        for eid in critical_entities:
            entity = self.entities.get(eid)
            if entity:
                suggestions.append(f"Critical: Test {entity.name} ({entity.type})")
        
        # Test integration points
        suggestions.append("Integration tests for affected components")
        suggestions.append("Regression tests for dependent functionality")
        
        return suggestions[:10]
    
    def _update_avg_connections(self) -> None:
        """Update average connections statistic"""
        if self.entities:
            total_connections = sum(
                len(e.outgoing_relations) + len(e.incoming_relations)
                for e in self.entities.values()
            )
            self._stats['avg_connections'] = total_connections / len(self.entities)
    
    def to_dict(self) -> dict:
        """Serialize to dictionary"""
        return {
            'entities': {eid: e.to_dict() for eid, e in self.entities.items()},
            'relations': {rid: r.to_dict() for rid, r in self.relations.items()},
            'stats': self._stats
        }
    
    @classmethod
    def from_dict(cls, data: dict) -> 'KnowledgeGraph':
        """Deserialize from dictionary"""
        graph = cls()
        
        # Load entities
        for eid, entity_data in data.get('entities', {}).items():
            entity = Entity.from_dict(entity_data)
            graph.entities[eid] = entity
            
            # Update indexes
            graph._entity_by_type[entity.type].add(eid)
            if entity.layer:
                graph._entity_by_layer[entity.layer].add(eid)
            if entity.component:
                graph._entity_by_component[entity.component].add(eid)
        
        # Load relations
        for rid, relation_data in data.get('relations', {}).items():
            relation = Relation.from_dict(relation_data)
            graph.relations[rid] = relation
            
            # Update indexes
            graph._relations_by_type[relation.relation_type].add(rid)
            graph._outgoing[relation.from_entity].add(rid)
            graph._incoming[relation.to_entity].add(rid)
            
            # Update entity relation lists
            if relation.from_entity in graph.entities:
                graph.entities[relation.from_entity].outgoing_relations.append(rid)
            if relation.to_entity in graph.entities:
                graph.entities[relation.to_entity].incoming_relations.append(rid)
        
        graph._stats = data.get('stats', {})
        
        return graph