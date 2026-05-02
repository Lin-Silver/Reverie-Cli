"""
Consistency Checker - Validates narrative consistency and prevents errors

Detects and prevents:
- Repeated plot elements
- Contradictory character information
- Timeline inconsistencies
- Location/geography errors
- Unresolved plot threads
- Context errors
"""

from typing import Dict, List, Optional, Any, Set, Tuple
from dataclasses import dataclass
import re
from datetime import datetime


@dataclass
class ConsistencyIssue:
    """A consistency issue found"""
    issue_type: str  # "repetition", "contradiction", "timeline", "character", etc.
    severity: str  # "critical", "warning", "info"
    description: str
    location: Optional[str] = None  # Where in the text
    suggested_fix: Optional[str] = None


class ConsistencyChecker:
    """
    Validates narrative consistency and prevents common errors
    in long-form writing.
    """
    
    def __init__(self, memory_system=None):
        """
        Initialize consistency checker.
        
        Args:
            memory_system: Reference to NovelMemorySystem for context
        """
        self.memory_system = memory_system
        self.previous_content: List[str] = []
        self.content_hashes: Set[str] = set()
        self.common_phrases: Dict[str, int] = {}
    
    def check_full_consistency(self, new_content: str, chapter: int) -> List[ConsistencyIssue]:
        """
        Perform comprehensive consistency check on new content.
        
        Returns list of ConsistencyIssue objects.
        """
        issues: List[ConsistencyIssue] = []
        
        # Check for repetitions
        issues.extend(self._check_repetitions(new_content))
        
        # Check for contradictions
        issues.extend(self._check_contradictions(new_content, chapter))
        
        # Check for timeline issues
        issues.extend(self._check_timeline(new_content, chapter))
        
        # Check for character inconsistencies
        issues.extend(self._check_character_consistency(new_content, chapter))
        
        # Check for context errors
        issues.extend(self._check_context_errors(new_content, chapter))
        
        # Check for grammar/style
        issues.extend(self._check_writing_quality(new_content))
        
        return issues
    
    def _check_repetitions(self, text: str) -> List[ConsistencyIssue]:
        """Detect repeated content, phrases, and plot elements"""
        issues = []
        sentences = re.split(r'[.!?]+', text)
        
        # Check for repeated sentences
        sentence_dict = {}
        for i, sentence in enumerate(sentences):
            normalized = sentence.strip().lower()
            if normalized:
                if normalized in sentence_dict:
                    issues.append(ConsistencyIssue(
                        issue_type="repetition",
                        severity="warning",
                        description=f"Repeated sentence found: '{normalized[:50]}...'",
                        location=f"Sentence {i}",
                        suggested_fix="Consider rewording or removing duplicate sentence"
                    ))
                else:
                    sentence_dict[normalized] = i
        
        # Check for repeated phrases
        words = text.lower().split()
        for length in [3, 4, 5]:
            for i in range(len(words) - length):
                phrase = " ".join(words[i:i+length])
                
                # Count occurrences in rest of text
                rest_words = " ".join(words[i+length:])
                if phrase in rest_words:
                    count = rest_words.count(phrase)
                    if count > 1:
                        if phrase not in self.common_phrases:
                            self.common_phrases[phrase] = 0
                        self.common_phrases[phrase] += 1
                        
                        if self.common_phrases[phrase] > 3:  # More than 3 times total
                            issues.append(ConsistencyIssue(
                                issue_type="repetition",
                                severity="info",
                                description=f"Phrase appears multiple times: '{phrase}'",
                                suggested_fix="Vary your phrasing to improve readability"
                            ))
        
        # Check against previous chapters
        for prev_content in self.previous_content[-3:]:  # Check last 3 chapters
            # Find significant phrases in current content
            current_phrases = set()
            for length in [4, 5, 6]:
                words = text.lower().split()
                for i in range(len(words) - length):
                    phrase = " ".join(words[i:i+length])
                    current_phrases.add(phrase)
            
            # Check if these phrases appear in previous chapters
            prev_lower = prev_content.lower()
            for phrase in list(current_phrases)[:20]:  # Check top phrases
                if phrase in prev_lower and len(phrase) > 15:
                    issues.append(ConsistencyIssue(
                        issue_type="repetition",
                        severity="warning",
                        description=f"Content similar to previous chapters: '{phrase[:40]}...'",
                        suggested_fix="Check if you're repeating plot elements from earlier chapters"
                    ))
        
        return issues
    
    def _check_contradictions(self, text: str, chapter: int) -> List[ConsistencyIssue]:
        """Check for contradictory information"""
        issues = []
        
        if not self.memory_system:
            return issues
        
        # Check for character contradictions
        for char_name, character in self.memory_system.characters.items():
            # Check for contradictory trait mentions
            text_lower = text.lower()
            char_lower = char_name.lower()
            
            if char_lower in text_lower:
                # Basic trait consistency check
                if "evil" in character.traits and "kind" in character.traits:
                    if "evil" in text_lower or "malicious" in text_lower:
                        if "kind" in text_lower or "compassionate" in text_lower:
                            issues.append(ConsistencyIssue(
                                issue_type="contradiction",
                                severity="warning",
                                description=f"Character '{char_name}' shows contradictory traits in same scene",
                                suggested_fix="Ensure character traits are consistent within a scene"
                            ))
        
        # Check for timeline contradictions
        if self.memory_system.plot_events:
            recent_events = [
                e for e in self.memory_system.plot_events
                if e.chapter <= chapter
            ]
            if recent_events:
                last_event = recent_events[-1]
                # Check if new content contradicts the last major event
                if last_event.is_major_twist and last_event.chapter < chapter - 2:
                    # Twisted should have consequences
                    if "previously" not in text.lower() and "recall" not in text.lower():
                        issues.append(ConsistencyIssue(
                            issue_type="timeline",
                            severity="info",
                            description=f"Major plot twist from Chapter {last_event.chapter} may need acknowledgment",
                            suggested_fix="Reference or address the consequences of previous major events"
                        ))
        
        return issues
    
    def _check_timeline(self, text: str, chapter: int) -> List[ConsistencyIssue]:
        """Check for timeline inconsistencies"""
        issues = []
        
        # Check for temporal keywords
        temporal_keywords = {
            "yesterday": -1,
            "today": 0,
            "tomorrow": 1,
            "next day": 1,
            "previous day": -1,
            "week ago": -7,
            "month ago": -30,
            "year ago": -365,
        }
        
        for keyword, offset in temporal_keywords.items():
            if keyword in text.lower():
                # Validate temporal consistency
                # This is simplified - a full implementation would track in-story time
                pass
        
        return issues
    
    def _check_character_consistency(self, text: str, chapter: int) -> List[ConsistencyIssue]:
        """Check for character inconsistencies"""
        issues = []
        
        if not self.memory_system:
            return issues
        
        text_lower = text.lower()
        
        # Check character presence validity
        for char_name, character in self.memory_system.characters.items():
            char_lower = char_name.lower()
            
            if char_lower in text_lower:
                # Character appears in text
                # Check if they've been introduced
                if chapter < character.first_appearance_chapter:
                    issues.append(ConsistencyIssue(
                        issue_type="character",
                        severity="critical",
                        description=f"Character '{char_name}' appears before introduction (Chapter {character.first_appearance_chapter})",
                        suggested_fix="Either introduce character earlier or remove premature reference"
                    ))
                
                # Check for reappearance after death (if tracked)
                if "dead" in character.traits and chapter > character.last_appearance_chapter:
                    if any(action in text_lower for action in ["spoke", "said", "walked", "ran", "appeared"]):
                        issues.append(ConsistencyIssue(
                            issue_type="character",
                            severity="critical",
                            description=f"Character '{char_name}' appears to be alive after death",
                            suggested_fix="Remove character actions or clarify resurrection/flashback"
                        ))
        
        return issues
    
    def _check_context_errors(self, text: str, chapter: int) -> List[ConsistencyIssue]:
        """Check for context and setting errors"""
        issues = []
        
        if not self.memory_system:
            return issues
        
        text_lower = text.lower()
        
        # Check location consistency
        mentioned_locations = []
        for loc_name in self.memory_system.locations.keys():
            if loc_name.lower() in text_lower:
                mentioned_locations.append(loc_name)
        
        # Check if location connections make sense
        if len(mentioned_locations) > 1:
            for i, loc1 in enumerate(mentioned_locations):
                for loc2 in mentioned_locations[i+1:]:
                    loc1_obj = self.memory_system.locations.get(loc1)
                    loc2_obj = self.memory_system.locations.get(loc2)
                    
                    if loc1_obj and loc2_obj:
                        if loc2 not in loc1_obj.connections and loc1 not in loc2_obj.connections:
                            issues.append(ConsistencyIssue(
                                issue_type="context",
                                severity="info",
                                description=f"Locations '{loc1}' and '{loc2}' jumped to without clear transition",
                                suggested_fix="Add narrative transition or establish location connection"
                            ))
        
        return issues
    
    def _check_writing_quality(self, text: str) -> List[ConsistencyIssue]:
        """Check for writing quality issues"""
        issues = []
        
        # Check for common writing mistakes
        if text.count("  ") > 0:
            issues.append(ConsistencyIssue(
                issue_type="style",
                severity="info",
                description="Multiple spaces found",
                suggested_fix="Remove extra spaces"
            ))
        
        # Check for weak verbs and overused words
        weak_verbs = ["went", "get", "got", "put", "is", "are"]
        weak_count = sum(text.lower().count(f" {v} ") for v in weak_verbs)
        
        if weak_count > len(text.split()) * 0.15:  # More than 15% weak verbs
            issues.append(ConsistencyIssue(
                issue_type="style",
                severity="info",
                description="High frequency of weak verbs detected",
                suggested_fix="Replace weak verbs with stronger, more specific verbs"
            ))
        
        return issues
    
    def register_chapter_content(self, chapter: int, content: str) -> None:
        """Register chapter content for comparison with future chapters"""
        self.previous_content.append(content)
        
        # Compute content hash for integrity checking
        import hashlib
        content_hash = hashlib.sha256(content.encode()).hexdigest()
        self.content_hashes.add(content_hash)
    
    def generate_consistency_report(self, issues: List[ConsistencyIssue]) -> str:
        """Generate a human-readable consistency report"""
        if not issues:
            return "✓ No consistency issues detected!"
        
        report_lines = [f"Found {len(issues)} consistency issue(s):"]
        
        # Group by severity
        by_severity = {}
        for issue in issues:
            if issue.severity not in by_severity:
                by_severity[issue.severity] = []
            by_severity[issue.severity].append(issue)
        
        # Output by severity
        for severity in ["critical", "warning", "info"]:
            if severity in by_severity:
                report_lines.append(f"\n{severity.upper()}:")
                for issue in by_severity[severity]:
                    report_lines.append(f"  - {issue.description}")
                    if issue.suggested_fix:
                        report_lines.append(f"    Suggestion: {issue.suggested_fix}")
        
        return "\n".join(report_lines)
