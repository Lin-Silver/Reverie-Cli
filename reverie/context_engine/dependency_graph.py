"""
Dependency Graph - Tracks relationships between symbols

The dependency graph is crucial for the Context Engine to provide
"minimal but complete" context. It enables:
- Call chain analysis
- Impact analysis (what will be affected by a change)
- Intelligent context expansion (include related symbols)

Optimized for large codebases with efficient graph traversal.
"""

from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Dict, List, Set, Optional, Tuple
from collections import defaultdict
import json


class DependencyType(Enum):
    """Types of dependencies between symbols"""
    IMPORTS = auto()        # Module/package imports
    INHERITS = auto()       # Class inheritance
    IMPLEMENTS = auto()     # Interface implementation
    CALLS = auto()          # Function/method calls
    INSTANTIATES = auto()   # Class instantiation
    USES = auto()           # Variable/constant usage
    REFERENCES = auto()     # General reference
    DECORATES = auto()      # Decorator application
    TYPE_HINTS = auto()     # Type annotation reference
    CONTAINS = auto()       # Parent-child containment
    OVERRIDES = auto()      # Method override


@dataclass
class Dependency:
    """Represents a dependency from one symbol to another"""
    from_symbol: str       # Qualified name of source symbol
    to_symbol: str         # Qualified name of target symbol
    dep_type: DependencyType
    file_path: str         # Where this dependency is declared
    line: int              # Line number
    context: str = ""      # Code snippet showing the dependency
    
    def to_dict(self) -> dict:
        return {
            'from_symbol': self.from_symbol,
            'to_symbol': self.to_symbol,
            'dep_type': self.dep_type.name,
            'file_path': self.file_path,
            'line': self.line,
            'context': self.context
        }
    
    @classmethod
    def from_dict(cls, data: dict) -> 'Dependency':
        return cls(
            from_symbol=data['from_symbol'],
            to_symbol=data['to_symbol'],
            dep_type=DependencyType[data['dep_type']],
            file_path=data['file_path'],
            line=data['line'],
            context=data.get('context', '')
        )


class DependencyGraph:
    """
    Directed graph of symbol dependencies.
    
    Provides efficient queries for:
    - Forward dependencies (what does this symbol depend on?)
    - Reverse dependencies (what depends on this symbol?)
    - Transitive dependencies with depth control
    - Call chain visualization
    """
    
    def __init__(self):
        # Adjacency list: from_symbol -> list of (to_symbol, Dependency)
        self._outgoing: Dict[str, List[Dependency]] = defaultdict(list)
        
        # Reverse adjacency: to_symbol -> list of (from_symbol, Dependency)
        self._incoming: Dict[str, List[Dependency]] = defaultdict(list)
        
        # Index by file for incremental updates
        self._file_index: Dict[str, Set[Tuple[str, str]]] = defaultdict(set)
        
        # Statistics
        self._stats = {
            'total_edges': 0,
            'by_type': {t.name: 0 for t in DependencyType}
        }
    
    def add_dependency(self, dep: Dependency) -> None:
        """Add a dependency edge to the graph"""
        self._outgoing[dep.from_symbol].append(dep)
        self._incoming[dep.to_symbol].append(dep)
        self._file_index[dep.file_path].add((dep.from_symbol, dep.to_symbol))
        
        self._stats['total_edges'] += 1
        self._stats['by_type'][dep.dep_type.name] += 1
    
    def add_simple(
        self,
        from_symbol: str,
        to_symbol: str,
        dep_type: DependencyType,
        file_path: str = "",
        line: int = 0,
        context: str = ""
    ) -> None:
        """Convenience method to add dependency without creating Dependency object"""
        dep = Dependency(
            from_symbol=from_symbol,
            to_symbol=to_symbol,
            dep_type=dep_type,
            file_path=file_path,
            line=line,
            context=context
        )
        self.add_dependency(dep)
    
    def get_dependencies(
        self,
        symbol: str,
        dep_types: Optional[List[DependencyType]] = None,
        depth: int = 1
    ) -> List[Dependency]:
        """
        Get dependencies of a symbol (what it depends on).
        
        Args:
            symbol: Qualified name of the symbol
            dep_types: Filter by dependency types (None = all)
            depth: How many levels deep to traverse (1 = direct only)
        
        Returns:
            List of dependencies
        """
        result = []
        visited = set()
        
        def collect(sym: str, current_depth: int):
            if current_depth > depth or sym in visited:
                return
            visited.add(sym)
            
            for dep in self._outgoing.get(sym, []):
                if dep_types is None or dep.dep_type in dep_types:
                    result.append(dep)
                if current_depth < depth:
                    collect(dep.to_symbol, current_depth + 1)
        
        collect(symbol, 1)
        return result
    
    def get_dependents(
        self,
        symbol: str,
        dep_types: Optional[List[DependencyType]] = None,
        depth: int = 1
    ) -> List[Dependency]:
        """
        Get dependents of a symbol (what depends on it).
        This is crucial for impact analysis.
        
        Args:
            symbol: Qualified name of the symbol
            dep_types: Filter by dependency types
            depth: How many levels deep to traverse
        
        Returns:
            List of dependencies where this symbol is the target
        """
        result = []
        visited = set()
        
        def collect(sym: str, current_depth: int):
            if current_depth > depth or sym in visited:
                return
            visited.add(sym)
            
            for dep in self._incoming.get(sym, []):
                if dep_types is None or dep.dep_type in dep_types:
                    result.append(dep)
                if current_depth < depth:
                    collect(dep.from_symbol, current_depth + 1)
        
        collect(symbol, 1)
        return result
    
    def get_call_chain(
        self,
        symbol: str,
        direction: str = "down",
        max_depth: int = 5
    ) -> List[List[str]]:
        """
        Get call chains from/to a symbol.
        
        Args:
            symbol: Starting symbol
            direction: "down" (what it calls) or "up" (what calls it)
            max_depth: Maximum chain depth
        
        Returns:
            List of call chains (each chain is a list of qualified names)
        """
        chains = []
        
        def trace(path: List[str], current: str, depth: int):
            if depth > max_depth:
                chains.append(path[:])
                return
            
            if direction == "down":
                deps = self._outgoing.get(current, [])
                deps = [d for d in deps if d.dep_type == DependencyType.CALLS]
            else:
                deps = self._incoming.get(current, [])
                deps = [d for d in deps if d.dep_type == DependencyType.CALLS]
            
            if not deps:
                if len(path) > 1:  # Don't add single-node chains
                    chains.append(path[:])
                return
            
            for dep in deps:
                next_sym = dep.to_symbol if direction == "down" else dep.from_symbol
                if next_sym not in path:  # Avoid cycles
                    path.append(next_sym)
                    trace(path, next_sym, depth + 1)
                    path.pop()
        
        trace([symbol], symbol, 1)
        return chains
    
    def get_inheritance_tree(self, symbol: str, direction: str = "up") -> Dict:
        """
        Get inheritance hierarchy for a class.
        
        Args:
            symbol: Class qualified name
            direction: "up" (ancestors) or "down" (descendants)
        
        Returns:
            Nested dict representing the tree
        """
        def build_tree(sym: str, visited: Set[str]) -> Dict:
            if sym in visited:
                return {"name": sym, "cycle": True}
            visited.add(sym)
            
            if direction == "up":
                deps = [d for d in self._outgoing.get(sym, [])
                       if d.dep_type == DependencyType.INHERITS]
                children_syms = [d.to_symbol for d in deps]
            else:
                deps = [d for d in self._incoming.get(sym, [])
                       if d.dep_type == DependencyType.INHERITS]
                children_syms = [d.from_symbol for d in deps]
            
            children = [build_tree(c, visited.copy()) for c in children_syms]
            
            return {
                "name": sym,
                "children": children if children else None
            }
        
        return build_tree(symbol, set())
    
    def get_related_symbols(
        self,
        symbol: str,
        max_distance: int = 2,
        max_results: int = 50
    ) -> List[Tuple[str, int, DependencyType]]:
        """
        Get all symbols related to a given symbol within a distance.
        
        Returns:
            List of (qualified_name, distance, relationship_type)
        """
        result = []
        visited = {symbol: 0}
        queue = [(symbol, 0)]
        
        while queue and len(result) < max_results:
            current, dist = queue.pop(0)
            
            if dist >= max_distance:
                continue
            
            # Outgoing edges
            for dep in self._outgoing.get(current, []):
                if dep.to_symbol not in visited:
                    visited[dep.to_symbol] = dist + 1
                    result.append((dep.to_symbol, dist + 1, dep.dep_type))
                    queue.append((dep.to_symbol, dist + 1))
            
            # Incoming edges
            for dep in self._incoming.get(current, []):
                if dep.from_symbol not in visited:
                    visited[dep.from_symbol] = dist + 1
                    result.append((dep.from_symbol, dist + 1, dep.dep_type))
                    queue.append((dep.from_symbol, dist + 1))
        
        return result
    
    def remove_file(self, file_path: str) -> int:
        """Remove all dependencies from a file. Returns count removed."""
        if file_path not in self._file_index:
            return 0
        
        edges = list(self._file_index[file_path])
        count = 0
        
        for from_sym, to_sym in edges:
            # Remove from outgoing
            if from_sym in self._outgoing:
                self._outgoing[from_sym] = [
                    d for d in self._outgoing[from_sym]
                    if d.file_path != file_path
                ]
            
            # Remove from incoming
            if to_sym in self._incoming:
                self._incoming[to_sym] = [
                    d for d in self._incoming[to_sym]
                    if d.file_path != file_path
                ]
            
            count += 1
        
        del self._file_index[file_path]
        self._stats['total_edges'] -= count
        
        return count
    
    def visualize(self, symbol: str, depth: int = 2) -> str:
        """
        Generate ASCII visualization of dependencies.
        
        Returns a tree-like string representation.
        """
        lines = [f"Dependencies for: {symbol}", "=" * 50]
        
        def draw_deps(sym: str, prefix: str, is_last: bool, visited: Set[str], d: int):
            if d > depth:
                return
            
            connector = "└── " if is_last else "├── "
            lines.append(f"{prefix}{connector}{sym}")
            
            if sym in visited:
                lines[-1] += " (circular)"
                return
            visited.add(sym)
            
            deps = self._outgoing.get(sym, [])
            for i, dep in enumerate(deps):
                new_prefix = prefix + ("    " if is_last else "│   ")
                is_last_dep = i == len(deps) - 1
                draw_deps(dep.to_symbol, new_prefix, is_last_dep, visited.copy(), d + 1)
        
        lines.append("")
        lines.append("Outgoing (what it depends on):")
        deps = self._outgoing.get(symbol, [])
        for i, dep in enumerate(deps):
            draw_deps(dep.to_symbol, "", i == len(deps) - 1, {symbol}, 1)
        
        lines.append("")
        lines.append("Incoming (what depends on it):")
        deps = self._incoming.get(symbol, [])
        for i, dep in enumerate(deps):
            lines.append(f"{'└── ' if i == len(deps) - 1 else '├── '}{dep.from_symbol} ({dep.dep_type.name})")
        
        return "\n".join(lines)
    
    def get_statistics(self) -> Dict:
        """Get graph statistics"""
        return {
            **self._stats,
            'unique_sources': len(self._outgoing),
            'unique_targets': len(self._incoming)
        }
    
    def to_dict(self) -> dict:
        """Serialize graph to dictionary"""
        all_deps = []
        for deps in self._outgoing.values():
            all_deps.extend([d.to_dict() for d in deps])
        
        return {
            'dependencies': all_deps,
            'stats': self._stats
        }
    
    @classmethod
    def from_dict(cls, data: dict) -> 'DependencyGraph':
        """Deserialize from dictionary"""
        graph = cls()
        for dep_data in data.get('dependencies', []):
            dep = Dependency.from_dict(dep_data)
            graph.add_dependency(dep)
        return graph
    
    def __len__(self) -> int:
        return self._stats['total_edges']
