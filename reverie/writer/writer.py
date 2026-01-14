"""
Writer Mode Controller - Main orchestrator for long-form novel creation

Coordinates:
- Novel memory management
- Narrative analysis
- Consistency checking
- Context management for large novels
- Chapter progression and validation
"""

from typing import Dict, List, Optional, Any, Tuple
from pathlib import Path
from datetime import datetime

from .novel_memory import NovelMemorySystem, Character, Location, PlotEvent, EmotionalArc, Theme, ContentSummary
from .narrative_analyzer import NarrativeAnalyzer
from .consistency_checker import ConsistencyChecker


class WriterMode:
    """
    Main controller for Writer Mode in Reverie.
    
    Manages the complete novel creation workflow:
    1. Content generation with context awareness
    2. Automatic memory and tracking updates
    3. Consistency and continuity validation
    4. Narrative analysis and feedback
    5. Long-term story coherence maintenance
    """
    
    def __init__(self, novel_id: str, novel_title: str, storage_dir: Optional[Path] = None):
        """
        Initialize Writer Mode for a novel.
        
        Args:
            novel_id: Unique identifier for the novel
            novel_title: Title of the novel
            storage_dir: Where to store novel data
        """
        self.novel_id = novel_id
        self.novel_title = novel_title
        
        # Core systems
        self.memory_system = NovelMemorySystem(novel_id, storage_dir)
        self.narrative_analyzer = NarrativeAnalyzer()
        self.consistency_checker = ConsistencyChecker(self.memory_system)
        
        # Novel metadata
        self.created_at = datetime.now()
        self.last_updated = datetime.now()
        self.total_chapters = 0
        self.total_word_count = 0
        
        # Session state
        self.current_chapter = 0
        self.chapter_drafts = {}  # chapter_num -> text
        self.chapter_metadata = {}  # chapter_num -> metadata
    
    def start_new_chapter(self, chapter_num: int, chapter_title: str = "") -> Dict[str, Any]:
        """
        Start writing a new chapter.
        
        Returns context information for the chapter.
        """
        self.current_chapter = chapter_num
        
        # Get relevant context from memory
        context = self.get_chapter_context(chapter_num)
        
        return {
            "chapter_number": chapter_num,
            "chapter_title": chapter_title,
            "context": context,
            "active_characters": list(self.memory_system.characters.keys()),
            "active_themes": list(self.memory_system.get_active_themes(chapter_num).keys()),
            "recent_plot_events": self.memory_system.get_plot_context(chapter_num, lookback_chapters=3),
        }
    
    def get_chapter_context(self, chapter: int, context_window: int = 5) -> Dict[str, Any]:
        """
        Get comprehensive context for a chapter.
        
        Returns detailed information about what's happened before.
        """
        return {
            "chapter_summary": self.memory_system.get_chapter_context(chapter, window=context_window),
            "active_characters": [
                {
                    "name": char.name,
                    "description": char.description,
                    "last_seen": char.last_appearance_chapter,
                    "traits": char.traits,
                }
                for char in self.memory_system.characters.values()
            ],
            "active_locations": [
                {
                    "name": loc.name,
                    "description": loc.description,
                    "atmosphere": loc.atmosphere,
                }
                for loc in self.memory_system.locations.values()
            ],
            "recent_events": self.memory_system.get_plot_context(chapter, lookback_chapters=3),
            "active_themes": self.memory_system.get_active_themes(chapter),
        }
    
    def analyze_written_content(self, chapter_num: int, content: str) -> Dict[str, Any]:
        """
        Analyze written content for quality and consistency.
        
        Returns comprehensive analysis report.
        """
        # Tone analysis
        tone_analysis = self.narrative_analyzer.analyze_tone(content)
        
        # Repetition detection
        repetitions = self.narrative_analyzer.detect_repetitions(content)
        
        # Consistency checking
        consistency_issues = self.consistency_checker.check_full_consistency(content, chapter_num)
        
        # Word count
        word_count = len(content.split())
        
        return {
            "word_count": word_count,
            "tone_analysis": {
                "dominant_tone": tone_analysis.dominant_tone,
                "confidence": tone_analysis.tone_confidence,
                "all_tones": tone_analysis.tones_present,
                "emotional_intensity": tone_analysis.emotional_intensity,
                "pacing": tone_analysis.pacing,
            },
            "repetitions_found": repetitions,
            "consistency_issues": consistency_issues,
            "consistency_report": self.consistency_checker.generate_consistency_report(consistency_issues),
            "quality_score": self._calculate_quality_score(repetitions, consistency_issues, tone_analysis),
        }
    
    def _calculate_quality_score(self, repetitions: List[str], issues: List[Any], tone_analysis: Any) -> float:
        """Calculate overall quality score (0-100)"""
        score = 100.0
        
        # Penalize repetitions
        score -= len(repetitions) * 2
        
        # Penalize consistency issues by severity
        critical_count = sum(1 for i in issues if i.severity == "critical")
        warning_count = sum(1 for i in issues if i.severity == "warning")
        info_count = sum(1 for i in issues if i.severity == "info")
        
        score -= critical_count * 10
        score -= warning_count * 3
        score -= info_count * 0.5
        
        # Boost for good tone consistency
        if tone_analysis.tone_confidence > 0.8:
            score += 5
        
        return max(0, score)
    
    def finalize_chapter(
        self,
        chapter_num: int,
        content: str,
        chapter_title: str = "",
        key_events: Optional[List[str]] = None,
        characters_involved: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        """
        Finalize a chapter and update memory system.
        
        Stores chapter content and updates all tracking systems.
        """
        # Generate content summary
        content_hash = self._compute_hash(content)
        
        summary = ContentSummary(
            chapter=chapter_num,
            content_hash=content_hash,
            summary=self._generate_summary(content, max_length=500),
            key_events=key_events or [],
            characters_involved=characters_involved or [],
            new_information=self._extract_new_information(content),
            tokens_estimated=self._estimate_tokens(content),
        )
        
        # Register content with consistency checker
        self.consistency_checker.register_chapter_content(chapter_num, content)
        
        # Update memory
        self.memory_system.add_content_summary(summary)
        self.chapter_metadata[chapter_num] = {
            "title": chapter_title,
            "created_at": datetime.now().isoformat(),
            "word_count": len(content.split()),
            "tone": self.narrative_analyzer.analyze_tone(content).dominant_tone,
        }
        
        # Update global stats
        self.total_chapters = max(self.total_chapters, chapter_num)
        self.total_word_count += len(content.split())
        self.last_updated = datetime.now()
        
        # Save memory
        self.memory_system.save()
        
        return {
            "chapter": chapter_num,
            "status": "finalized",
            "word_count": len(content.split()),
            "content_hash": content_hash,
            "summary_length": len(summary.summary),
        }
    
    def update_character(
        self,
        name: str,
        description: Optional[str] = None,
        traits: Optional[List[str]] = None,
        relationships: Optional[Dict[str, str]] = None,
        development_notes: Optional[str] = None,
        chapter: Optional[int] = None,
    ) -> None:
        """Update character information in memory"""
        char = self.memory_system.get_character_by_name(name)
        
        if char:
            if description:
                char.description = description
            if traits:
                char.traits = traits
            if relationships:
                char.relationships.update(relationships)
            if development_notes:
                char.development_arc.append(development_notes)
            if chapter:
                char.last_appearance_chapter = chapter
        
        self.memory_system.save()
    
    def update_location(
        self,
        name: str,
        description: Optional[str] = None,
        atmosphere: Optional[str] = None,
        connections: Optional[List[str]] = None,
        chapter: Optional[int] = None,
    ) -> None:
        """Update location information in memory"""
        loc = self.memory_system.get_location_by_name(name)
        
        if loc:
            if description:
                loc.description = description
            if atmosphere:
                loc.atmosphere = atmosphere
            if connections:
                loc.connections.extend(connections)
            if chapter:
                loc.last_appearance_chapter = chapter
        
        self.memory_system.save()
    
    def add_plot_event(
        self,
        chapter: int,
        summary: str,
        participants: List[str],
        location: str = "",
        is_major_twist: bool = False,
        consequences: Optional[List[str]] = None,
    ) -> None:
        """Record a significant plot event"""
        event = PlotEvent(
            chapter=chapter,
            summary=summary,
            participants=participants,
            location=location,
            is_major_twist=is_major_twist,
            causal_consequences=consequences or [],
        )
        self.memory_system.add_plot_event(event)
        self.memory_system.save()
    
    def add_theme(
        self,
        name: str,
        description: str,
        first_appearance_chapter: int,
        symbol: Optional[str] = None,
    ) -> None:
        """Register a theme in the novel"""
        theme = Theme(
            name=name,
            description=description,
            appearances=[first_appearance_chapter],
            symbol=symbol,
        )
        self.memory_system.add_theme(theme)
        self.memory_system.save()
    
    def get_memory_stats(self) -> Dict[str, Any]:
        """Get comprehensive stats about the novel and its memory"""
        return {
            "novel": {
                "id": self.novel_id,
                "title": self.novel_title,
                "created_at": self.created_at.isoformat(),
                "last_updated": self.last_updated.isoformat(),
            },
            "content": {
                "total_chapters": self.total_chapters,
                "total_words": self.total_word_count,
                "chapters_with_metadata": len(self.chapter_metadata),
            },
            "memory": self.memory_system.get_memory_stats(),
        }
    
    # Private helper methods
    def _compute_hash(self, content: str) -> str:
        """Compute SHA256 hash of content"""
        import hashlib
        return hashlib.sha256(content.encode()).hexdigest()
    
    def _generate_summary(self, content: str, max_length: int = 500) -> str:
        """Generate a summary of the content"""
        # Simple extractive summary - take first sentences until max_length
        sentences = content.split(".")
        summary = ""
        for sentence in sentences:
            if len(summary) + len(sentence) < max_length:
                summary += sentence.strip() + ". "
            else:
                break
        return summary.strip()
    
    def _extract_new_information(self, content: str) -> str:
        """Extract what's new/unique in this content"""
        # Look for new character/location introductions
        new_info = []
        
        # This would be enhanced with actual NLP
        if "introduced" in content.lower() or "met" in content.lower():
            new_info.append("New character introductions")
        
        if "arrived at" in content.lower() or "reached" in content.lower():
            new_info.append("New locations")
        
        if "revealed" in content.lower() or "discovered" in content.lower():
            new_info.append("Plot revelations")
        
        return "; ".join(new_info) if new_info else "Character development and narrative progression"
    
    def _estimate_tokens(self, content: str) -> int:
        """Estimate token count for content"""
        # Rough estimation: ~1 token per 4 characters
        return len(content) // 4
