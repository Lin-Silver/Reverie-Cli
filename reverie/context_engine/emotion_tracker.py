"""
Emotion Tracker - Tracks emotional arcs and tone progression across the novel

Provides:
- Character emotional state tracking
- Overall narrative tone tracking
- Emotional intensity analysis
- Tone consistency checking
- Emotional climax detection
"""

from typing import Dict, List, Optional, Any, Tuple
from dataclasses import dataclass
from enum import Enum


class EmotionalState(Enum):
    """Predefined emotional states"""
    JOYFUL = "joyful"
    HOPEFUL = "hopeful"
    NEUTRAL = "neutral"
    ANXIOUS = "anxious"
    SAD = "sad"
    ANGRY = "angry"
    CONFUSED = "confused"
    PEACEFUL = "peaceful"
    EXCITED = "excited"
    DEVASTATED = "devastated"


@dataclass
class EmotionalSnapshot:
    """Snapshot of emotional state at a point in story"""
    chapter: int
    character: str
    state: str
    intensity: float  # 0.0 to 1.0
    trigger: str
    narrative_context: str


class EmotionTracker:
    """
    Tracks emotional progression across the novel.
    
    Helps maintain:
    - Emotional coherence
    - Character development arcs
    - Proper emotional pacing
    - Tone consistency
    """
    
    def __init__(self):
        self.snapshots: List[EmotionalSnapshot] = []
        self.character_arcs: Dict[str, List[EmotionalSnapshot]] = {}
        self.narrative_tone_progression: List[Tuple[int, str, float]] = []  # (chapter, tone, intensity)
    
    def record_emotional_state(
        self,
        chapter: int,
        character: str,
        state: str,
        intensity: float,
        trigger: str = "",
        context: str = "",
    ) -> None:
        """Record an emotional state snapshot"""
        snapshot = EmotionalSnapshot(
            chapter=chapter,
            character=character,
            state=state,
            intensity=intensity,
            trigger=trigger,
            narrative_context=context,
        )
        
        self.snapshots.append(snapshot)
        
        if character not in self.character_arcs:
            self.character_arcs[character] = []
        self.character_arcs[character].append(snapshot)
    
    def record_narrative_tone(self, chapter: int, tone: str, intensity: float) -> None:
        """Record overall narrative tone for a chapter"""
        self.narrative_tone_progression.append((chapter, tone, intensity))
    
    def get_character_emotional_arc(self, character: str) -> List[EmotionalSnapshot]:
        """Get emotional arc for a character"""
        return self.character_arcs.get(character, [])
    
    def get_emotional_climax(self) -> Optional[Tuple[int, str, float]]:
        """
        Detect the emotional climax of the story.
        
        Returns (chapter, emotion_type, intensity).
        """
        if not self.snapshots:
            return None
        
        # Find the snapshot with highest intensity
        max_snapshot = max(self.snapshots, key=lambda s: s.intensity)
        return (max_snapshot.chapter, max_snapshot.state, max_snapshot.intensity)
    
    def check_emotional_consistency(self, character: str, chapter: int) -> Dict[str, Any]:
        """
        Check if character's emotional state is consistent.
        
        Returns analysis of emotional consistency.
        """
        arc = self.get_character_emotional_arc(character)
        
        if not arc:
            return {"is_consistent": True, "issues": []}
        
        # Filter to chapter or before
        relevant_arc = [s for s in arc if s.chapter <= chapter]
        if not relevant_arc:
            return {"is_consistent": True, "issues": []}
        
        # Check for abrupt emotional shifts
        issues = []
        for i in range(len(relevant_arc) - 1):
            current = relevant_arc[i]
            next_state = relevant_arc[i + 1]
            
            # Major emotional shifts without clear reason
            intensity_diff = abs(next_state.intensity - current.intensity)
            if intensity_diff > 0.5 and not next_state.trigger:
                issues.append(
                    f"Abrupt emotional shift in Chapter {next_state.chapter}: "
                    f"{current.state} -> {next_state.state} without clear trigger"
                )
        
        return {
            "is_consistent": len(issues) == 0,
            "issues": issues,
            "current_state": relevant_arc[-1].state if relevant_arc else None,
            "current_intensity": relevant_arc[-1].intensity if relevant_arc else None,
        }
    
    def get_emotional_summary(self) -> Dict[str, Any]:
        """Get summary of emotional arcs in the story"""
        return {
            "total_snapshots": len(self.snapshots),
            "characters_tracked": list(self.character_arcs.keys()),
            "emotional_climax": self.get_emotional_climax(),
            "tone_progression": self.narrative_tone_progression,
        }
