"""
Novel Memory System - Intelligent memory management for long-form novel content

Tracks:
- Characters (names, descriptions, relationships, traits)
- Locations (descriptions, connections, significance)
- Plot elements (events, timeline, causality)
- Emotional arcs (tone progression, character development)
- Themes (recurring ideas, symbolic elements)
- Content summary (condensed representations for context management)
"""

from typing import Dict, List, Optional, Set, Any
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
import json
import hashlib
from enum import Enum


class ElementType(Enum):
    """Types of narrative elements tracked in memory"""
    CHARACTER = "character"
    LOCATION = "location"
    PLOT_EVENT = "plot_event"
    EMOTIONAL_ARC = "emotional_arc"
    THEME = "theme"
    RELATIONSHIP = "relationship"
    FLASHBACK = "flashback"


@dataclass
class Character:
    """Character in the novel"""
    name: str
    description: str
    first_appearance_chapter: int
    traits: List[str] = field(default_factory=list)
    relationships: Dict[str, str] = field(default_factory=dict)  # name -> relationship_type
    development_arc: List[str] = field(default_factory=list)  # Character evolution notes
    last_appearance_chapter: int = 0
    is_protagonist: bool = False
    background: str = ""


@dataclass
class Location:
    """Location in the novel"""
    name: str
    description: str
    first_appearance_chapter: int
    connections: List[str] = field(default_factory=list)  # Connected locations
    significance: str = ""  # Why this location matters
    atmosphere: str = ""  # Emotional tone of this place
    last_appearance_chapter: int = 0


@dataclass
class PlotEvent:
    """Plot event or twist"""
    chapter: int
    summary: str
    participants: List[str] = field(default_factory=list)  # Character names
    location: str = ""
    causal_consequences: List[str] = field(default_factory=list)  # What this causes
    is_major_twist: bool = False
    timestamp_in_story: str = ""


@dataclass
class EmotionalArc:
    """Track emotional progression"""
    chapter: int
    character: str
    emotional_state: str
    tone: str
    intensity: float = 0.5  # 0.0 to 1.0
    triggers: List[str] = field(default_factory=list)


@dataclass
class Theme:
    """Recurring theme in the novel"""
    name: str
    description: str
    appearances: List[int] = field(default_factory=list)  # Chapter numbers
    variations: List[str] = field(default_factory=list)  # Different manifestations
    symbol: Optional[str] = None


@dataclass
class ContentSummary:
    """Compressed summary for efficient context management"""
    chapter: int
    content_hash: str  # SHA256 of original content
    summary: str  # Condensed version
    key_events: List[str]
    characters_involved: List[str]
    new_information: str  # What's new in this chapter
    tokens_estimated: int


class NovelMemorySystem:
    """
    Intelligent memory management system for novel creation.
    
    Maintains comprehensive tracking of all narrative elements to ensure:
    - No repeated content
    - Correct contextual references
    - Logical plot progression
    - Character consistency
    - Emotional coherence
    """
    
    def __init__(self, novel_id: str, storage_dir: Optional[Path] = None):
        """
        Initialize the memory system.
        
        Args:
            novel_id: Unique identifier for the novel
            storage_dir: Directory for persisting memory data
        """
        self.novel_id = novel_id
        self.storage_dir = storage_dir or Path.home() / ".reverie" / "novels" / novel_id
        self.storage_dir.mkdir(parents=True, exist_ok=True)
        
        # Core memory structures
        self.characters: Dict[str, Character] = {}
        self.locations: Dict[str, Location] = {}
        self.plot_events: List[PlotEvent] = []
        self.emotional_arcs: List[EmotionalArc] = []
        self.themes: Dict[str, Theme] = {}
        self.content_summaries: List[ContentSummary] = []
        
        # Metadata
        self.created_at = datetime.now()
        self.current_chapter = 0
        self.total_words = 0
        self.last_updated = datetime.now()
        
        # Load existing memory if available
        self._load_from_disk()
    
    def add_character(self, character: Character) -> None:
        """Add a character to memory"""
        self.characters[character.name] = character
        self.last_updated = datetime.now()
    
    def add_location(self, location: Location) -> None:
        """Add a location to memory"""
        self.locations[location.name] = location
        self.last_updated = datetime.now()
    
    def add_plot_event(self, event: PlotEvent) -> None:
        """Add a plot event to memory"""
        self.plot_events.append(event)
        # Validate causality
        self.plot_events.sort(key=lambda e: e.chapter)
        self.last_updated = datetime.now()
    
    def add_emotional_arc(self, arc: EmotionalArc) -> None:
        """Track emotional progression for a character"""
        self.emotional_arcs.append(arc)
        self.last_updated = datetime.now()
    
    def add_theme(self, theme: Theme) -> None:
        """Register a theme in the novel"""
        self.themes[theme.name] = theme
        self.last_updated = datetime.now()
    
    def add_content_summary(self, summary: ContentSummary) -> None:
        """Store compressed summary of chapter content"""
        self.content_summaries.append(summary)
        self.current_chapter = summary.chapter
        self.last_updated = datetime.now()
    
    def get_character_by_name(self, name: str) -> Optional[Character]:
        """Retrieve character information"""
        # Try exact match first
        if name in self.characters:
            return self.characters[name]
        
        # Try fuzzy matching
        for char_name, char in self.characters.items():
            if name.lower() in char_name.lower() or char_name.lower() in name.lower():
                return char
        
        return None
    
    def get_location_by_name(self, name: str) -> Optional[Location]:
        """Retrieve location information"""
        if name in self.locations:
            return self.locations[name]
        
        for loc_name, loc in self.locations.items():
            if name.lower() in loc_name.lower() or loc_name.lower() in name.lower():
                return loc
        
        return None
    
    def get_character_relationships(self, character_name: str) -> Dict[str, str]:
        """Get all relationships for a character"""
        char = self.get_character_by_name(character_name)
        return char.relationships if char else {}
    
    def get_plot_context(self, chapter: int, lookback_chapters: int = 5) -> List[PlotEvent]:
        """
        Get relevant plot events for context.
        
        Returns events from lookback_chapters back to current chapter.
        """
        start_chapter = max(1, chapter - lookback_chapters)
        return [e for e in self.plot_events if start_chapter <= e.chapter <= chapter]
    
    def get_character_emotional_arc(self, character: str, chapter: int) -> List[EmotionalArc]:
        """Get emotional arc progression for a character up to a chapter"""
        return [
            arc for arc in self.emotional_arcs
            if arc.character.lower() == character.lower() and arc.chapter <= chapter
        ]
    
    def get_active_themes(self, chapter: int) -> Dict[str, Theme]:
        """Get themes active in or before a chapter"""
        return {
            name: theme for name, theme in self.themes.items()
            if theme.appearances and max(theme.appearances) <= chapter
        }
    
    def get_chapter_context(self, chapter: int, window: int = 3) -> str:
        """
        Get comprehensive context around a chapter.
        
        Returns formatted string with key information about surrounding chapters.
        """
        relevant_summaries = [
            s for s in self.content_summaries
            if chapter - window <= s.chapter <= chapter
        ]
        
        context_parts = []
        for summary in relevant_summaries:
            context_parts.append(f"Chapter {summary.chapter}: {summary.summary}")
            if summary.key_events:
                context_parts.append(f"  Events: {', '.join(summary.key_events)}")
        
        return "\n".join(context_parts)
    
    def validate_continuity(self, chapter: int, new_content: str) -> Dict[str, Any]:
        """
        Validate new content for continuity issues.
        
        Returns validation report with potential issues.
        """
        issues = {
            "repeated_events": [],
            "unknown_characters": [],
            "timeline_conflicts": [],
            "character_inconsistencies": [],
            "location_issues": [],
            "warnings": []
        }
        
        # Extract names and locations mentioned in new content
        content_lower = new_content.lower()
        
        # Check for unknown characters
        for char_name in self.characters.keys():
            if char_name.lower() in content_lower:
                char = self.characters[char_name]
                if char.last_appearance_chapter > 0 and chapter - char.last_appearance_chapter > 50:
                    issues["character_inconsistencies"].append(
                        f"Character '{char_name}' reappears after long absence ({chapter - char.last_appearance_chapter} chapters)"
                    )
                char.last_appearance_chapter = chapter
        
        # Similar validation for locations
        for loc_name in self.locations.keys():
            if loc_name.lower() in content_lower:
                loc = self.locations[loc_name]
                loc.last_appearance_chapter = chapter
        
        return issues
    
    def get_memory_stats(self) -> Dict[str, Any]:
        """Get memory system statistics"""
        return {
            "novel_id": self.novel_id,
            "current_chapter": self.current_chapter,
            "total_characters": len(self.characters),
            "total_locations": len(self.locations),
            "total_plot_events": len(self.plot_events),
            "total_themes": len(self.themes),
            "total_summaries": len(self.content_summaries),
            "created_at": self.created_at.isoformat(),
            "last_updated": self.last_updated.isoformat(),
        }
    
    def _save_to_disk(self) -> None:
        """Persist memory to disk"""
        try:
            # Save characters
            chars_file = self.storage_dir / "characters.json"
            chars_data = {
                name: {
                    "name": char.name,
                    "description": char.description,
                    "first_appearance_chapter": char.first_appearance_chapter,
                    "traits": char.traits,
                    "relationships": char.relationships,
                    "development_arc": char.development_arc,
                    "last_appearance_chapter": char.last_appearance_chapter,
                    "is_protagonist": char.is_protagonist,
                    "background": char.background,
                }
                for name, char in self.characters.items()
            }
            chars_file.write_text(json.dumps(chars_data, ensure_ascii=False, indent=2))
            
            # Save locations
            locs_file = self.storage_dir / "locations.json"
            locs_data = {
                name: {
                    "name": loc.name,
                    "description": loc.description,
                    "first_appearance_chapter": loc.first_appearance_chapter,
                    "connections": loc.connections,
                    "significance": loc.significance,
                    "atmosphere": loc.atmosphere,
                    "last_appearance_chapter": loc.last_appearance_chapter,
                }
                for name, loc in self.locations.items()
            }
            locs_file.write_text(json.dumps(locs_data, ensure_ascii=False, indent=2))
            
            # Save themes
            themes_file = self.storage_dir / "themes.json"
            themes_data = {
                name: {
                    "name": theme.name,
                    "description": theme.description,
                    "appearances": theme.appearances,
                    "variations": theme.variations,
                    "symbol": theme.symbol,
                }
                for name, theme in self.themes.items()
            }
            themes_file.write_text(json.dumps(themes_data, ensure_ascii=False, indent=2))
            
            # Save metadata
            meta_file = self.storage_dir / "metadata.json"
            meta_data = {
                "novel_id": self.novel_id,
                "created_at": self.created_at.isoformat(),
                "last_updated": self.last_updated.isoformat(),
                "current_chapter": self.current_chapter,
                "total_words": self.total_words,
            }
            meta_file.write_text(json.dumps(meta_data, ensure_ascii=False, indent=2))
        except Exception as e:
            print(f"Error saving memory to disk: {e}")
    
    def _load_from_disk(self) -> None:
        """Load memory from disk if available"""
        try:
            # Load characters
            chars_file = self.storage_dir / "characters.json"
            if chars_file.exists():
                chars_data = json.loads(chars_file.read_text(encoding='utf-8'))
                for name, data in chars_data.items():
                    char = Character(
                        name=data["name"],
                        description=data["description"],
                        first_appearance_chapter=data["first_appearance_chapter"],
                        traits=data.get("traits", []),
                        relationships=data.get("relationships", {}),
                        development_arc=data.get("development_arc", []),
                        last_appearance_chapter=data.get("last_appearance_chapter", 0),
                        is_protagonist=data.get("is_protagonist", False),
                        background=data.get("background", ""),
                    )
                    self.characters[name] = char
            
            # Load locations
            locs_file = self.storage_dir / "locations.json"
            if locs_file.exists():
                locs_data = json.loads(locs_file.read_text(encoding='utf-8'))
                for name, data in locs_data.items():
                    loc = Location(
                        name=data["name"],
                        description=data["description"],
                        first_appearance_chapter=data["first_appearance_chapter"],
                        connections=data.get("connections", []),
                        significance=data.get("significance", ""),
                        atmosphere=data.get("atmosphere", ""),
                        last_appearance_chapter=data.get("last_appearance_chapter", 0),
                    )
                    self.locations[name] = loc
            
            # Load themes
            themes_file = self.storage_dir / "themes.json"
            if themes_file.exists():
                themes_data = json.loads(themes_file.read_text(encoding='utf-8'))
                for name, data in themes_data.items():
                    theme = Theme(
                        name=data["name"],
                        description=data["description"],
                        appearances=data.get("appearances", []),
                        variations=data.get("variations", []),
                        symbol=data.get("symbol"),
                    )
                    self.themes[name] = theme
            
            # Load metadata
            meta_file = self.storage_dir / "metadata.json"
            if meta_file.exists():
                meta_data = json.loads(meta_file.read_text(encoding='utf-8'))
                self.current_chapter = meta_data.get("current_chapter", 0)
                self.total_words = meta_data.get("total_words", 0)
                self.created_at = datetime.fromisoformat(meta_data.get("created_at", datetime.now().isoformat()))
                self.last_updated = datetime.fromisoformat(meta_data.get("last_updated", datetime.now().isoformat()))
        except Exception as e:
            print(f"Error loading memory from disk: {e}")
    
    def save(self) -> None:
        """Save all memory to disk"""
        self._save_to_disk()
