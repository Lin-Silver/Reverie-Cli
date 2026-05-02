"""
Continuity Validator - Validates continuity across chapters

Provides:
- Timeline consistency checking
- Character state tracking
- Location consistency
- Object/item tracking
- Knowledge consistency (what characters know)
"""

from typing import Dict, List, Optional, Any, Set
from dataclasses import dataclass, field
from datetime import datetime


@dataclass
class CharacterState:
    """State of a character at a point in the story"""
    chapter: int
    character_name: str
    location: Optional[str] = None
    emotional_state: Optional[str] = None
    physical_state: Optional[str] = None  # injured, tired, etc.
    knowledge: Set[str] = field(default_factory=set)  # What they know
    relationships: Dict[str, str] = field(default_factory=dict)  # relationship_type -> character


@dataclass
class TemporalEvent:
    """An event at a specific point in story time"""
    chapter: int
    story_date: Optional[str] = None  # In-story date if applicable
    description: str = ""
    duration_chapters: int = 1  # How many chapters does this span?


class ContinuityValidator:
    """
    Validates continuity across chapters.
    
    Maintains:
    - Character states and locations
    - Timeline consistency
    - Knowledge consistency
    - Physical object tracking
    """
    
    def __init__(self):
        self.character_states: Dict[str, List[CharacterState]] = {}  # character_name -> states
        self.temporal_events: List[TemporalEvent] = []
        self.object_locations: Dict[str, Dict[int, Optional[str]]] = {}  # object -> chapter -> location
        self.continuity_issues: List[Dict[str, Any]] = []
    
    def record_character_state(self, state: CharacterState) -> None:
        """Record a character's state at a chapter"""
        if state.character_name not in self.character_states:
            self.character_states[state.character_name] = []
        
        self.character_states[state.character_name].append(state)
    
    def record_temporal_event(self, event: TemporalEvent) -> None:
        """Record a temporal event"""
        self.temporal_events.append(event)
    
    def track_object(self, object_name: str, chapter: int, location: Optional[str]) -> None:
        """Track an object's location"""
        if object_name not in self.object_locations:
            self.object_locations[object_name] = {}
        
        self.object_locations[object_name][chapter] = location
    
    def validate_character_continuity(self, character: str, chapter: int) -> Dict[str, Any]:
        """
        Validate a character's continuity at a chapter.
        
        Returns validation result.
        """
        if character not in self.character_states:
            return {"is_valid": True, "issues": []}
        
        states = self.character_states[character]
        
        # Filter states up to current chapter
        relevant_states = [s for s in states if s.chapter <= chapter]
        if not relevant_states:
            return {"is_valid": True, "issues": []}
        
        issues = []
        
        # Check for teleportation (character in two places without travel time)
        for i in range(len(relevant_states) - 1):
            current = relevant_states[i]
            next_state = relevant_states[i + 1]
            
            if (current.location and next_state.location and 
                current.location != next_state.location and
                next_state.chapter - current.chapter <= 1):
                # Character teleported without explanation
                issues.append({
                    "type": "teleportation",
                    "description": f"{character} teleported from {current.location} to {next_state.location}",
                    "chapters": (current.chapter, next_state.chapter),
                })
        
        # Check for knowledge inconsistencies
        for i in range(len(relevant_states) - 1):
            current = relevant_states[i]
            next_state = relevant_states[i + 1]
            
            # Knowledge can increase but not decrease (unless memory loss plot point)
            if not next_state.knowledge.issuperset(current.knowledge):
                forgotten = current.knowledge - next_state.knowledge
                issues.append({
                    "type": "knowledge_loss",
                    "description": f"{character} forgot: {', '.join(forgotten)}",
                    "chapters": (current.chapter, next_state.chapter),
                })
        
        return {
            "is_valid": len(issues) == 0,
            "issues": issues,
            "current_state": relevant_states[-1],
        }
    
    def validate_object_continuity(self, obj_name: str) -> Dict[str, Any]:
        """
        Validate an object's continuity across chapters.
        
        Returns validation result.
        """
        if obj_name not in self.object_locations:
            return {"is_valid": True, "issues": []}
        
        locations = self.object_locations[obj_name]
        chapters = sorted(locations.keys())
        
        issues = []
        
        # Check for impossible teleportation
        for i in range(len(chapters) - 1):
            ch1 = chapters[i]
            ch2 = chapters[i + 1]
            loc1 = locations[ch1]
            loc2 = locations[ch2]
            
            if loc1 != loc2 and loc1 is not None and loc2 is not None:
                if ch2 - ch1 == 1:
                    # Object moved between adjacent chapters without travel
                    issues.append({
                        "type": "object_teleportation",
                        "description": f"'{obj_name}' moved from {loc1} to {loc2} instantly",
                        "chapters": (ch1, ch2),
                    })
        
        return {
            "is_valid": len(issues) == 0,
            "issues": issues,
        }
    
    def validate_timeline_consistency(self) -> List[Dict[str, Any]]:
        """
        Validate overall timeline consistency.
        
        Returns list of timeline inconsistencies.
        """
        issues = []
        
        # Check for temporal event overlaps
        for i in range(len(self.temporal_events) - 1):
            event1 = self.temporal_events[i]
            event2 = self.temporal_events[i + 1]
            
            # Check if events overlap incorrectly
            event1_end = event1.chapter + event1.duration_chapters
            if event1_end > event2.chapter:
                issues.append({
                    "type": "timeline_overlap",
                    "description": f"Temporal events overlap: '{event1.description}' -> '{event2.description}'",
                    "chapters": (event1.chapter, event2.chapter),
                })
        
        return issues
    
    def get_character_location_history(self, character: str) -> List[Dict[str, Any]]:
        """Get location history for a character"""
        if character not in self.character_states:
            return []
        
        history = []
        states = sorted(
            self.character_states[character],
            key=lambda s: s.chapter
        )
        
        for state in states:
            history.append({
                "chapter": state.chapter,
                "location": state.location,
                "state": state.emotional_state,
            })
        
        return history
    
    def get_continuity_report(self) -> Dict[str, Any]:
        """Generate comprehensive continuity report"""
        report = {
            "total_characters": len(self.character_states),
            "total_temporal_events": len(self.temporal_events),
            "tracked_objects": len(self.object_locations),
            "issues": self.continuity_issues,
        }
        
        return report
