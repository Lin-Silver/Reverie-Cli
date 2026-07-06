"""Reverie Context Engine + Memory OS primitives."""

from .assembler import ContextAssembler
from .consolidator import MemoryConsolidator
from .event_store import EventStore
from .evolution import EvolutionFeedbackPipeline
from .models import (
    ContextPackage,
    EventRecord,
    LearningProposal,
    MEMORY_CONTEXT_PROMPT_HEADER,
    MEMANTO_MEMORY_TYPES,
    MEMORY_TYPES,
    MemoryItem,
    MemorySearchHit,
)
from .os import MemoryOS
from .retriever import MemoryRetriever
from .store import MemoryStore

__all__ = [
    "ContextAssembler",
    "ContextPackage",
    "EventRecord",
    "EventStore",
    "EvolutionFeedbackPipeline",
    "LearningProposal",
    "MEMORY_CONTEXT_PROMPT_HEADER",
    "MEMANTO_MEMORY_TYPES",
    "MEMORY_TYPES",
    "MemoryConsolidator",
    "MemoryItem",
    "MemoryOS",
    "MemoryRetriever",
    "MemorySearchHit",
    "MemoryStore",
]
