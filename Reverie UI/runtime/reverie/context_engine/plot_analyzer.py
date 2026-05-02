"""
Plot Analyzer - Analyzes plot structure and causality chains

Provides:
- Plot event tracking and sequencing
- Causality chain analysis
- Subplot management
- Plot hole detection
- Story structure analysis
"""

from typing import Dict, List, Optional, Any, Set
from dataclasses import dataclass, field
from enum import Enum


class PlotType(Enum):
    """Types of plot elements"""
    INCITING_INCIDENT = "inciting_incident"
    RISING_ACTION = "rising_action"
    CLIMAX = "climax"
    FALLING_ACTION = "falling_action"
    RESOLUTION = "resolution"
    SUBPLOT = "subplot"
    TWIST = "twist"
    REVELATION = "revelation"


@dataclass
class CausalityChain:
    """Represents a chain of cause and effect"""
    events: List[str]  # Event summaries
    chapters: List[int]  # Chapters where events occur
    resolved: bool = False


class PlotAnalyzer:
    """
    Analyzes plot structure and narrative causality.
    
    Helps maintain:
    - Logical plot progression
    - Resolved plot threads
    - Character motivations
    - Cause-and-effect relationships
    """
    
    def __init__(self):
        self.plot_events: Dict[int, List[Dict[str, Any]]] = {}  # chapter -> events
        self.causality_chains: List[CausalityChain] = []
        self.open_threads: Set[str] = set()  # Unresolved plot threads
        self.subplots: Dict[str, List[int]] = {}  # subplot_name -> chapters
    
    def add_plot_event(
        self,
        chapter: int,
        description: str,
        plot_type: str = "rising_action",
        participants: Optional[List[str]] = None,
        causal_causes: Optional[List[str]] = None,
        causal_effects: Optional[List[str]] = None,
    ) -> None:
        """Add a plot event"""
        if chapter not in self.plot_events:
            self.plot_events[chapter] = []
        
        event = {
            "description": description,
            "type": plot_type,
            "participants": participants or [],
            "causes": causal_causes or [],
            "effects": causal_effects or [],
        }
        
        self.plot_events[chapter].append(event)
        
        # If this event opens a thread, track it
        if plot_type in ["twist", "revelation", "inciting_incident"]:
            self.open_threads.add(description)
        
        # If this event resolves something, remove from open threads
        if causal_causes:
            for cause in causal_causes:
                self.open_threads.discard(cause)
    
    def add_causality_chain(self, chain: CausalityChain) -> None:
        """Add a causality chain to track"""
        self.causality_chains.append(chain)
    
    def add_subplot(self, subplot_name: str, chapters: List[int]) -> None:
        """Track a subplot across chapters"""
        self.subplots[subplot_name] = chapters
    
    def get_plot_context(self, chapter: int, lookback: int = 5) -> Dict[str, Any]:
        """Get plot context around a chapter"""
        start_chapter = max(1, chapter - lookback)
        
        context = {
            "recent_events": [],
            "open_threads": list(self.open_threads),
            "active_subplots": [],
        }
        
        # Get recent plot events
        for ch in range(start_chapter, chapter + 1):
            if ch in self.plot_events:
                context["recent_events"].extend(self.plot_events[ch])
        
        # Get active subplots
        for subplot_name, chapters in self.subplots.items():
            if start_chapter <= chapter <= max(chapters):
                context["active_subplots"].append(subplot_name)
        
        return context
    
    def detect_plot_holes(self) -> List[Dict[str, Any]]:
        """Detect potential plot holes"""
        issues = []
        
        # Check for unresolved threads
        if self.open_threads:
            issues.append({
                "type": "unresolved_threads",
                "severity": "warning",
                "description": f"Found {len(self.open_threads)} unresolved plot threads",
                "threads": list(self.open_threads),
            })
        
        # Check for causality chains
        for chain in self.causality_chains:
            if not chain.resolved and len(chain.events) > 0:
                issues.append({
                    "type": "unresolved_chain",
                    "severity": "warning",
                    "description": f"Causality chain unresolved: {chain.events[0]} -> ...",
                    "chain": chain.events,
                })
        
        return issues
    
    def get_story_structure(self) -> Dict[str, Any]:
        """Analyze overall story structure"""
        if not self.plot_events:
            return {"structure": "unknown", "acts": []}
        
        # Find major turning points
        climax = None
        inciting_incident = None
        
        for chapter in sorted(self.plot_events.keys()):
            for event in self.plot_events[chapter]:
                if event["type"] == "inciting_incident" and not inciting_incident:
                    inciting_incident = chapter
                elif event["type"] == "climax" and not climax:
                    climax = chapter
        
        max_chapter = max(self.plot_events.keys())
        
        return {
            "inciting_incident_chapter": inciting_incident,
            "climax_chapter": climax,
            "total_chapters": max_chapter,
            "open_threads": len(self.open_threads),
            "resolved_chains": sum(1 for c in self.causality_chains if c.resolved),
        }
    
    def resolve_thread(self, thread_description: str) -> bool:
        """Mark a plot thread as resolved"""
        if thread_description in self.open_threads:
            self.open_threads.remove(thread_description)
            return True
        return False
