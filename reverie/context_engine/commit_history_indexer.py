"""
Commit History Indexer - Learn from past changes

The Commit History Indexer analyzes Git commit history to:
- Extract successful patterns from past implementations
- Learn from common mistakes and fixes
- Understand team conventions and preferences
- Provide context-aware suggestions based on historical data
- Track code evolution and architectural decisions

This enables the AI to learn from the project's history and
apply successful patterns to new changes.
"""

from pathlib import Path
from typing import List, Dict, Optional, Set, Tuple, Any
from dataclasses import dataclass, field
from enum import Enum, auto
import json
import re
import time
from collections import defaultdict
from datetime import datetime


class ChangeType(Enum):
    """Types of changes in commits"""
    ADD = auto()           # Adding new code
    MODIFY = auto()        # Modifying existing code
    DELETE = auto()        # Deleting code
    REFACTOR = auto()      # Refactoring
    FIX = auto()           # Bug fix
    FEATURE = auto()       # New feature
    PERFORMANCE = auto()   # Performance improvement
    SECURITY = auto()      # Security fix
    DOCUMENTATION = auto() # Documentation update
    TEST = auto()          # Test changes


@dataclass
class CommitPattern:
    """A pattern learned from commits"""
    id: str
    name: str
    pattern_type: str  # implementation, refactoring, fix, etc.
    description: str
    
    # Pattern statistics
    frequency: int = 0
    success_rate: float = 1.0  # Based on follow-up commits
    avg_files_changed: float = 0.0
    
    # Pattern examples
    example_commits: List[str] = field(default_factory=list)
    
    # Related patterns
    related_patterns: List[str] = field(default_factory=list)
    
    # When to use this pattern
    use_cases: List[str] = field(default_factory=list)
    
    # Common mistakes
    common_mistakes: List[str] = field(default_factory=list)
    
    def to_dict(self) -> dict:
        return {
            'id': self.id,
            'name': self.name,
            'pattern_type': self.pattern_type,
            'description': self.description,
            'frequency': self.frequency,
            'success_rate': self.success_rate,
            'avg_files_changed': self.avg_files_changed,
            'example_commits': self.example_commits,
            'related_patterns': self.related_patterns,
            'use_cases': self.use_cases,
            'common_mistakes': self.common_mistakes
        }
    
    @classmethod
    def from_dict(cls, data: dict) -> 'CommitPattern':
        return cls(
            id=data['id'],
            name=data['name'],
            pattern_type=data['pattern_type'],
            description=data['description'],
            frequency=data.get('frequency', 0),
            success_rate=data.get('success_rate', 1.0),
            avg_files_changed=data.get('avg_files_changed', 0.0),
            example_commits=data.get('example_commits', []),
            related_patterns=data.get('related_patterns', []),
            use_cases=data.get('use_cases', []),
            common_mistakes=data.get('common_mistakes', [])
        )


@dataclass
class CodeEvolution:
    """Track how code has evolved over time"""
    file_path: str
    entity_name: str  # Function, class, etc.
    
    # Evolution history
    versions: List[Dict] = field(default_factory=list)  # Each version with commit info
    
    # Evolution metrics
    total_changes: int = 0
    stability_score: float = 1.0  # Higher = more stable
    complexity_trend: str = "stable"  # increasing, decreasing, stable
    
    # Common modifications
    common_modifications: List[str] = field(default_factory=list)
    
    def to_dict(self) -> dict:
        return {
            'file_path': self.file_path,
            'entity_name': self.entity_name,
            'versions': self.versions,
            'total_changes': self.total_changes,
            'stability_score': self.stability_score,
            'complexity_trend': self.complexity_trend,
            'common_modifications': self.common_modifications
        }
    
    @classmethod
    def from_dict(cls, data: dict) -> 'CodeEvolution':
        return cls(
            file_path=data['file_path'],
            entity_name=data['entity_name'],
            versions=data.get('versions', []),
            total_changes=data.get('total_changes', 0),
            stability_score=data.get('stability_score', 1.0),
            complexity_trend=data.get('complexity_trend', 'stable'),
            common_modifications=data.get('common_modifications', [])
        )


@dataclass
class TeamConvention:
    """Team coding conventions learned from commits"""
    id: str
    convention_type: str  # naming, structure, error_handling, etc.
    description: str
    
    # Convention details
    pattern: str  # Regex or description of the pattern
    examples: List[str] = field(default_factory=list)
    
    # Adherence
    adherence_rate: float = 1.0  # How often this is followed
    violations: List[str] = field(default_factory=list)
    
    # When to apply
    context: List[str] = field(default_factory=list)
    
    def to_dict(self) -> dict:
        return {
            'id': self.id,
            'convention_type': self.convention_type,
            'description': self.description,
            'pattern': self.pattern,
            'examples': self.examples,
            'adherence_rate': self.adherence_rate,
            'violations': self.violations,
            'context': self.context
        }
    
    @classmethod
    def from_dict(cls, data: dict) -> 'TeamConvention':
        return cls(
            id=data['id'],
            convention_type=data['convention_type'],
            description=data['description'],
            pattern=data['pattern'],
            examples=data.get('examples', []),
            adherence_rate=data.get('adherence_rate', 1.0),
            violations=data.get('violations', []),
            context=data.get('context', [])
        )


class CommitHistoryIndexer:
    """
    Index and learn from Git commit history.
    
    Features:
    - Pattern extraction from commits
    - Code evolution tracking
    - Team convention learning
    - Success rate analysis
    - Historical context for changes
    """
    
    def __init__(self, project_root: Path):
        self.project_root = project_root
        self.patterns: Dict[str, CommitPattern] = {}
        self.evolutions: Dict[str, CodeEvolution] = {}  # key: file_path:entity_name
        self.conventions: Dict[str, TeamConvention] = {}
        
        # Indexes
        self._pattern_by_type: Dict[str, Set[str]] = defaultdict(set)
        self._evolution_by_file: Dict[str, Set[str]] = defaultdict(set)
        self._convention_by_type: Dict[str, Set[str]] = defaultdict(set)
        
        # Statistics
        self._stats = {
            'total_commits_analyzed': 0,
            'total_patterns': 0,
            'total_evolutions': 0,
            'total_conventions': 0
        }
    
    def index_commits(
        self,
        commits: List[Dict],
        max_commits: int = 1000
    ) -> None:
        """
        Index commits and extract patterns.
        
        Args:
            commits: List of commit dictionaries with:
                - hash: Commit hash
                - message: Commit message
                - author: Author name
                - date: Commit date
                - files: List of changed files
                - diff: Diff content
            max_commits: Maximum number of commits to analyze
        """
        commits_to_analyze = commits[:max_commits]
        self._stats['total_commits_analyzed'] = len(commits_to_analyze)
        
        for commit in commits_to_analyze:
            self._analyze_commit(commit)
        
        # Post-process to find patterns
        self._extract_patterns()
        self._learn_conventions()
    
    def _analyze_commit(self, commit: Dict) -> None:
        """Analyze a single commit"""
        commit_hash = commit.get('hash', '')
        message = commit.get('message', '')
        files = commit.get('files', [])
        diff = commit.get('diff', '')
        
        # Determine change type
        change_type = self._classify_change(message, files)
        
        # Track code evolution
        for file_path in files:
            self._track_evolution(file_path, commit, diff)
        
        # Extract potential patterns
        self._extract_commit_patterns(commit, change_type)
    
    def _classify_change(self, message: str, files: List[str]) -> ChangeType:
        """Classify the type of change"""
        message_lower = message.lower()
        
        if any(word in message_lower for word in ['fix', 'bug', 'issue', 'hotfix']):
            return ChangeType.FIX
        elif any(word in message_lower for word in ['feature', 'add', 'implement', 'new']):
            return ChangeType.FEATURE
        elif any(word in message_lower for word in ['refactor', 'clean', 'simplify']):
            return ChangeType.REFACTOR
        elif any(word in message_lower for word in ['performance', 'optimize', 'speed']):
            return ChangeType.PERFORMANCE
        elif any(word in message_lower for word in ['security', 'vulnerability', 'secure']):
            return ChangeType.SECURITY
        elif any(word in message_lower for word in ['test', 'spec', 'testing']):
            return ChangeType.TEST
        elif any(word in message_lower for word in ['doc', 'readme', 'comment']):
            return ChangeType.DOCUMENTATION
        else:
            return ChangeType.MODIFY
    
    def _track_evolution(self, file_path: str, commit: Dict, diff: str) -> None:
        """Track how code has evolved"""
        # Extract entities from diff (simplified)
        entities = self._extract_entities_from_diff(diff)
        
        for entity in entities:
            key = f"{file_path}:{entity}"
            
            if key not in self.evolutions:
                self.evolutions[key] = CodeEvolution(
                    file_path=file_path,
                    entity_name=entity
                )
                self._evolution_by_file[file_path].add(key)
            
            evolution = self.evolutions[key]
            evolution.versions.append({
                'commit_hash': commit.get('hash', ''),
                'date': commit.get('date', ''),
                'message': commit.get('message', ''),
                'change_type': self._classify_change(commit.get('message', ''), [file_path]).name
            })
            evolution.total_changes += 1
    
    def _extract_entities_from_diff(self, diff: str) -> List[str]:
        """Extract function/class names from diff"""
        entities = []
        
        # Look for function/class definitions in diff
        # This is simplified - a real implementation would use proper parsing
        patterns = [
            r'def\s+(\w+)\s*\(',  # Python functions
            r'class\s+(\w+)\s*:',  # Python classes
            r'function\s+(\w+)\s*\(',  # JavaScript functions
            r'interface\s+(\w+)',  # TypeScript interfaces
        ]
        
        for pattern in patterns:
            matches = re.findall(pattern, diff)
            entities.extend(matches)
        
        return list(set(entities))
    
    def _extract_commit_patterns(self, commit: Dict, change_type: ChangeType) -> None:
        """Extract patterns from a commit"""
        message = commit.get('message', '')
        files = commit.get('files', [])
        
        # Look for common patterns in commit messages
        patterns = self._identify_message_patterns(message)
        
        for pattern_name in patterns:
            pattern_id = f"{change_type.name.lower()}_{pattern_name}"
            
            if pattern_id not in self.patterns:
                self.patterns[pattern_id] = CommitPattern(
                    id=pattern_id,
                    name=pattern_name,
                    pattern_type=change_type.name.lower(),
                    description=f"Pattern for {pattern_name} in {change_type.name.lower()} changes"
                )
                self._pattern_by_type[change_type.name.lower()].add(pattern_id)
            
            pattern = self.patterns[pattern_id]
            pattern.frequency += 1
            pattern.avg_files_changed = (
                (pattern.avg_files_changed * (pattern.frequency - 1) + len(files)) /
                pattern.frequency
            )
            
            if commit.get('hash') not in pattern.example_commits:
                pattern.example_commits.append(commit.get('hash', ''))
    
    def _identify_message_patterns(self, message: str) -> List[str]:
        """Identify patterns in commit messages"""
        patterns = []
        message_lower = message.lower()
        
        # Common patterns
        if 'add' in message_lower and 'test' in message_lower:
            patterns.append('add_tests')
        if 'update' in message_lower and 'dependency' in message_lower:
            patterns.append('update_dependencies')
        if 'fix' in message_lower and 'typo' in message_lower:
            patterns.append('fix_typo')
        if 'refactor' in message_lower and 'extract' in message_lower:
            patterns.append('extract_method')
        if 'improve' in message_lower and 'error' in message_lower:
            patterns.append('improve_error_handling')
        if 'add' in message_lower and 'logging' in message_lower:
            patterns.append('add_logging')
        
        return patterns
    
    def _extract_patterns(self) -> None:
        """Extract and refine patterns from analyzed commits"""
        # Group similar patterns
        pattern_groups = defaultdict(list)
        
        for pattern in self.patterns.values():
            key = f"{pattern.pattern_type}_{pattern.name}"
            pattern_groups[key].append(pattern)
        
        # Merge similar patterns
        for key, group in pattern_groups.items():
            if len(group) > 1:
                # Merge patterns
                merged = group[0]
                for other in group[1:]:
                    merged.frequency += other.frequency
                    merged.example_commits.extend(other.example_commits)
                
                # Remove duplicates
                merged.example_commits = list(set(merged.example_commits))
    
    def _learn_conventions(self) -> None:
        """Learn team conventions from commits"""
        # This would analyze code style, naming conventions, etc.
        # Simplified implementation
        
        # Example: naming conventions
        naming_convention = TeamConvention(
            id='naming_snake_case',
            convention_type='naming',
            description='Use snake_case for function and variable names',
            pattern=r'^[a-z][a-z0-9_]*$',
            examples=['get_user_data', 'process_request', 'calculate_total']
        )
        
        self.conventions[naming_convention.id] = naming_convention
        self._convention_by_type['naming'].add(naming_convention.id)
        
        self._stats['total_conventions'] = len(self.conventions)
    
    def find_relevant_patterns(
        self,
        context: str,
        change_type: Optional[str] = None,
        limit: int = 10
    ) -> List[CommitPattern]:
        """Find patterns relevant to a given context"""
        scored_patterns = []
        
        for pattern in self.patterns.values():
            if change_type and pattern.pattern_type != change_type:
                continue
            
            score = self._calculate_pattern_relevance(pattern, context)
            if score > 0:
                scored_patterns.append((pattern, score))
        
        scored_patterns.sort(key=lambda x: x[1], reverse=True)
        return [p[0] for p in scored_patterns[:limit]]
    
    def get_evolution_history(
        self,
        file_path: str,
        entity_name: Optional[str] = None
    ) -> List[CodeEvolution]:
        """Get evolution history for a file or entity"""
        if entity_name:
            key = f"{file_path}:{entity_name}"
            return [self.evolutions[key]] if key in self.evolutions else []
        else:
            return [
                self.evolutions[key]
                for key in self._evolution_by_file.get(file_path, set())
            ]
    
    def get_conventions(
        self,
        convention_type: Optional[str] = None
    ) -> List[TeamConvention]:
        """Get team conventions"""
        if convention_type:
            return [
                self.conventions[cid]
                for cid in self._convention_by_type.get(convention_type, set())
            ]
        return list(self.conventions.values())
    
    def _calculate_pattern_relevance(
        self,
        pattern: CommitPattern,
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
            desc_words = set(pattern.description.lower().split())
            context_words = set(context_lower.split())
            matches = desc_words & context_words
            score += len(matches) * 0.5
        
        # Frequency boost
        score += min(pattern.frequency * 0.1, 2.0)
        
        # Success rate boost
        score += pattern.success_rate * 2.0
        
        return score
    
    def to_dict(self) -> dict:
        """Serialize to dictionary"""
        return {
            'patterns': {pid: p.to_dict() for pid, p in self.patterns.items()},
            'evolutions': {eid: e.to_dict() for eid, e in self.evolutions.items()},
            'conventions': {cid: c.to_dict() for cid, c in self.conventions.items()},
            'stats': self._stats
        }
    
    @classmethod
    def from_dict(cls, data: dict, project_root: Path) -> 'CommitHistoryIndexer':
        """Deserialize from dictionary"""
        indexer = cls(project_root)
        
        # Load patterns
        for pid, pattern_data in data.get('patterns', {}).items():
            pattern = CommitPattern.from_dict(pattern_data)
            indexer.patterns[pid] = pattern
            indexer._pattern_by_type[pattern.pattern_type].add(pid)
        
        # Load evolutions
        for eid, evolution_data in data.get('evolutions', {}).items():
            evolution = CodeEvolution.from_dict(evolution_data)
            indexer.evolutions[eid] = evolution
            indexer._evolution_by_file[evolution.file_path].add(eid)
        
        # Load conventions
        for cid, convention_data in data.get('conventions', {}).items():
            convention = TeamConvention.from_dict(convention_data)
            indexer.conventions[cid] = convention
            indexer._convention_by_type[convention.convention_type].add(cid)
        
        indexer._stats = data.get('stats', {})
        
        return indexer