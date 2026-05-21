"""
Novel Index - Specialized indexing for long-form novel content

Provides:
- Chapter-level indexing
- Character and location indexing
- Plot element tracking
- Theme indexing
- Efficient retrieval for large novels
"""

from typing import Dict, List, Optional, Set, Any
from dataclasses import dataclass
from pathlib import Path
import json


@dataclass
class IndexEntry:
    """Entry in the novel index"""
    element_type: str  # "character", "location", "plot", "theme"
    name: str
    chapters: List[int]
    first_appearance: int
    last_appearance: int
    metadata: Dict[str, Any]


class NovelIndex:
    """
    Specialized index for novel content.
    
    Optimized for:
    - Fast character/location lookup
    - Plot timeline queries
    - Theme tracking
    - Chapter-to-element mapping
    """
    
    def __init__(self):
        self.entries: Dict[str, IndexEntry] = {}
        self.chapter_index: Dict[int, Set[str]] = {}  # chapter -> element names
        self.element_type_index: Dict[str, Set[str]] = {}  # type -> element names
    
    def add_entry(self, entry: IndexEntry) -> None:
        """Add an entry to the index"""
        self.entries[f"{entry.element_type}:{entry.name}"] = entry
        
        # Update chapter index
        for chapter in entry.chapters:
            if chapter not in self.chapter_index:
                self.chapter_index[chapter] = set()
            self.chapter_index[chapter].add(entry.name)
        
        # Update type index
        if entry.element_type not in self.element_type_index:
            self.element_type_index[entry.element_type] = set()
        self.element_type_index[entry.element_type].add(entry.name)
    
    def get_by_chapter(self, chapter: int) -> List[IndexEntry]:
        """Get all indexed elements in a chapter"""
        element_names = self.chapter_index.get(chapter, set())
        return [
            self.entries[f"{self._infer_type(name)}:{name}"]
            for name in element_names
            if f"{self._infer_type(name)}:{name}" in self.entries
        ]
    
    def get_by_type(self, element_type: str) -> List[IndexEntry]:
        """Get all elements of a specific type"""
        names = self.element_type_index.get(element_type, set())
        return [
            self.entries[f"{element_type}:{name}"]
            for name in names
        ]
    
    def get_chapter_range(self, start_chapter: int, end_chapter: int) -> Dict[int, List[IndexEntry]]:
        """Get all elements across a chapter range"""
        result = {}
        for chapter in range(start_chapter, end_chapter + 1):
            result[chapter] = self.get_by_chapter(chapter)
        return result
    
    def _infer_type(self, name: str) -> str:
        """Try to infer element type from its name"""
        # This is a simplified approach - in practice, look up in entries
        for entry in self.entries.values():
            if entry.name == name:
                return entry.element_type
        return "unknown"
