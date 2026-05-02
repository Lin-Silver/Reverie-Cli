"""
Writer Mode Module - Long-form Novel Creation Assistant

Enables AI to create and manage long-form novel content with:
- Intelligent content memory and tracking
- Plot and narrative analysis
- Consistency and continuity checking
- Emotional tone tracking
- Context-aware story progression

This module provides a specialized writing assistant that maintains coherence
across thousands of words while preventing repetition, logical gaps, and
narrative inconsistencies.
"""

from .writer import WriterMode
from .novel_memory import NovelMemorySystem
from .narrative_analyzer import NarrativeAnalyzer
from .consistency_checker import ConsistencyChecker

__all__ = [
    'WriterMode',
    'NovelMemorySystem',
    'NarrativeAnalyzer',
    'ConsistencyChecker',
]
