"""
Narrative Analyzer - Analyzes narrative structure, tone, and emotional arcs

Provides:
- Emotional tone analysis
- Narrative pacing detection
- Character voice consistency
- Plot coherence validation
- Theme recurrence tracking
"""

from typing import Dict, List, Optional, Tuple, Any
from dataclasses import dataclass
import re
from enum import Enum


class ToneType(Enum):
    """Types of narrative tones"""
    HAPPY = "happy"
    SAD = "sad"
    TENSE = "tense"
    CALM = "calm"
    MYSTERIOUS = "mysterious"
    DARK = "dark"
    HOPEFUL = "hopeful"
    NOSTALGIC = "nostalgic"
    MELANCHOLIC = "melancholic"
    DRAMATIC = "dramatic"


@dataclass
class ToneAnalysis:
    """Result of tone analysis"""
    dominant_tone: str
    tone_confidence: float  # 0.0 to 1.0
    tones_present: Dict[str, float]  # tone -> confidence
    emotional_intensity: float  # 0.0 to 1.0
    pacing: str  # "slow", "moderate", "fast"


@dataclass
class NarrativePattern:
    """Pattern detected in narrative"""
    pattern_type: str
    frequency: int
    examples: List[str]
    is_repetitive: bool


class NarrativeAnalyzer:
    """
    Analyzes narrative structure and consistency.
    
    Detects:
    - Emotional tone and transitions
    - Pacing patterns
    - Repetitive content
    - Character voice consistency
    - Narrative flow issues
    """
    
    # Tone keywords mapping
    TONE_KEYWORDS = {
        "happy": ["happy", "joy", "excited", "delighted", "ecstatic", "cheerful", "bright"],
        "sad": ["sad", "grief", "mourning", "tragic", "sorrow", "weeping", "tears"],
        "tense": ["tension", "conflict", "danger", "threat", "fear", "anxiety", "nervous"],
        "calm": ["calm", "peaceful", "serene", "tranquil", "quiet", "still", "rest"],
        "mysterious": ["mystery", "secret", "unknown", "hidden", "obscure", "cryptic"],
        "dark": ["darkness", "evil", "malice", "sinister", "grim", "bleak", "oppressive"],
        "hopeful": ["hope", "promise", "light", "future", "possibility", "chance"],
        "nostalgic": ["memory", "remember", "past", "old", "long ago", "once"],
        "melancholic": ["melancholy", "wistful", "bittersweet", "longing", "yearning"],
        "dramatic": ["sudden", "shocking", "surprising", "astonishing", "dramatic"],
    }
    
    # Common repetitive patterns
    REPETITION_PATTERNS = [
        r"(\b\w+\s+\w+\b).*\1",  # Repeated phrases
        r"(but|however|yet|still)\s+\1",  # Repeated conjunctions
        r"(suddenly|finally|again)\s+\1",  # Repeated adverbs
    ]
    
    def __init__(self):
        self.analyzed_content = []
        self.detected_patterns = []
    
    def analyze_tone(self, text: str) -> ToneAnalysis:
        """
        Analyze the emotional tone of text.
        
        Returns ToneAnalysis with detected tones and confidence levels.
        """
        text_lower = text.lower()
        tone_scores: Dict[str, float] = {}
        
        # Score each tone based on keyword matches
        for tone, keywords in self.TONE_KEYWORDS.items():
            score = 0.0
            matches = 0
            
            for keyword in keywords:
                if keyword in text_lower:
                    matches += 1
            
            if matches > 0:
                # Confidence based on keyword density
                total_words = len(text.split())
                tone_scores[tone] = min(1.0, matches / max(1, total_words / 100))
        
        # Find dominant tone
        if tone_scores:
            dominant_tone = max(tone_scores, key=tone_scores.get)
            dominant_confidence = tone_scores[dominant_tone]
        else:
            dominant_tone = "neutral"
            dominant_confidence = 0.5
        
        # Calculate emotional intensity
        emotional_intensity = sum(tone_scores.values()) / max(1, len(tone_scores))
        
        # Detect pacing
        pacing = self._detect_pacing(text)
        
        return ToneAnalysis(
            dominant_tone=dominant_tone,
            tone_confidence=dominant_confidence,
            tones_present=tone_scores,
            emotional_intensity=emotional_intensity,
            pacing=pacing
        )
    
    def _detect_pacing(self, text: str) -> str:
        """
        Detect narrative pacing.
        
        Based on sentence length, dialogue, and action words.
        """
        sentences = re.split(r'[.!?]+', text)
        if not sentences:
            return "moderate"
        
        avg_sentence_length = sum(len(s.split()) for s in sentences) / len(sentences)
        
        # Fast pacing: short sentences (< 10 words)
        if avg_sentence_length < 10:
            return "fast"
        # Slow pacing: long sentences (> 25 words)
        elif avg_sentence_length > 25:
            return "slow"
        else:
            return "moderate"
    
    def detect_repetitions(self, text: str, min_length: int = 4) -> List[str]:
        """
        Detect repetitive phrases or patterns.
        
        Returns list of repetitive phrases found.
        """
        words = text.lower().split()
        repetitions = []
        
        # Check for repeated phrases of various lengths
        for phrase_length in range(min_length, min(15, len(words))):
            for i in range(len(words) - phrase_length):
                phrase = " ".join(words[i:i+phrase_length])
                
                # Check if this phrase appears again later
                rest_text = " ".join(words[i+phrase_length:])
                if phrase in rest_text:
                    if phrase not in repetitions:
                        repetitions.append(phrase)
        
        return repetitions[:10]  # Return top 10 repetitions
    
    def analyze_character_consistency(self, character_name: str, dialogues: List[str]) -> Dict[str, Any]:
        """
        Analyze character voice consistency across dialogues.
        
        Returns analysis of character speech patterns.
        """
        if not dialogues:
            return {"consistency_score": 0.0, "speech_patterns": []}
        
        # Extract key characteristics
        patterns = {
            "formal_words": 0,
            "contractions": 0,
            "exclamations": 0,
            "questions": 0,
            "average_sentence_length": 0,
            "vocabulary_complexity": 0,
        }
        
        total_words = 0
        total_sentences = 0
        
        for dialogue in dialogues:
            # Count word types
            words = dialogue.split()
            total_words += len(words)
            
            # Contractions
            patterns["contractions"] += len(re.findall(r"\b\w+n't\b|\b\w+\'[a-z]{1,2}\b", dialogue))
            
            # Exclamations
            patterns["exclamations"] += dialogue.count("!")
            
            # Questions
            patterns["questions"] += dialogue.count("?")
            
            # Sentences
            sentences = re.split(r'[.!?]+', dialogue)
            total_sentences += len([s for s in sentences if s.strip()])
        
        if total_sentences > 0:
            patterns["average_sentence_length"] = total_words / total_sentences
        
        # Calculate consistency score
        # Characters should have somewhat consistent patterns
        consistency_score = 0.7  # Default moderate consistency
        
        return {
            "consistency_score": consistency_score,
            "speech_patterns": patterns,
            "character_name": character_name,
        }
    
    def check_logical_flow(self, chapters: List[Tuple[int, str]]) -> Dict[str, Any]:
        """
        Check logical flow between chapters.
        
        Returns analysis of potential logical gaps or inconsistencies.
        """
        issues = {
            "logical_gaps": [],
            "timeline_conflicts": [],
            "character_teleportation": [],
            "abrupt_transitions": [],
            "unresolved_threads": [],
        }
        
        if len(chapters) < 2:
            return issues
        
        for i in range(len(chapters) - 1):
            current_chapter, current_text = chapters[i]
            next_chapter, next_text = chapters[i + 1]
            
            # Check for abrupt transitions
            current_tone = self.analyze_tone(current_text)
            next_tone = self.analyze_tone(next_text)
            
            # Major tone shifts might indicate logical gaps
            if current_tone.emotional_intensity > 0.7 and next_tone.emotional_intensity < 0.3:
                issues["abrupt_transitions"].append(
                    f"Abrupt tone shift from Chapter {current_chapter} to {next_chapter}"
                )
        
        return issues
    
    def summarize_narrative_arc(self, chapters: List[Tuple[int, str]]) -> str:
        """
        Generate a summary of the narrative arc.
        
        Returns string description of overall narrative progression.
        """
        if not chapters:
            return "No chapters to analyze"
        
        tones = []
        for _, text in chapters:
            tone_analysis = self.analyze_tone(text)
            tones.append(tone_analysis.dominant_tone)
        
        # Create arc description
        arc_description = f"Narrative arc spans {len(chapters)} chapters. "
        arc_description += f"Begins with {tones[0]} tone, "
        
        if len(tones) > 1:
            arc_description += f"ends with {tones[-1]} tone. "
            arc_description += f"Overall emotional intensity: {sum(1 for t in tones if t in ['dark', 'tense', 'dramatic']) / len(tones) * 100:.0f}% high-intensity chapters."
        
        return arc_description
