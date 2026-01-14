"""
Novel Context Manager Tool - AI tool for managing novel context

Provides AI agents with tools to:
- Query novel memory and context
- Manage characters, locations, plot elements
- Track story progression
- Validate continuity
"""

from typing import Dict, Any, Optional, List
from pathlib import Path

from .base import BaseTool, ToolResult
from ..writer import WriterMode


class NovelContextManagerTool(BaseTool):
    """
    Tool for managing and querying novel context.
    
    Allows AI agents to:
    - Start new chapters with proper context
    - Query character information
    - Manage plot events
    - Check continuity
    """
    
    name = "novel_context_manager"
    description = "Manage novel content, memory, and context for long-form story writing"
    
    parameters = {
        "type": "object",
        "properties": {
            "action": {
                "type": "string",
                "enum": [
                    "start_chapter",
                    "get_context",
                    "add_character",
                    "add_location",
                    "add_plot_event",
                    "get_memory_stats",
                    "finalize_chapter",
                ],
                "description": "Action to perform"
            },
            "novel_id": {
                "type": "string",
                "description": "ID of the novel being worked on"
            },
            "chapter": {
                "type": "integer",
                "description": "Chapter number"
            },
            "data": {
                "type": "object",
                "description": "Data for the action (varies by action)"
            }
        },
        "required": ["action", "novel_id"]
    }
    
    def __init__(self, context: Optional[Dict] = None):
        super().__init__(context)
        self.writers: Dict[str, WriterMode] = {}  # novel_id -> WriterMode
    
    def execute(self, **kwargs) -> ToolResult:
        """Execute the tool"""
        try:
            action = kwargs.get("action")
            novel_id = kwargs.get("novel_id")
            
            # Get or create WriterMode
            writer = self._get_writer(novel_id)
            
            if action == "start_chapter":
                return self._start_chapter(writer, kwargs)
            elif action == "get_context":
                return self._get_context(writer, kwargs)
            elif action == "add_character":
                return self._add_character(writer, kwargs)
            elif action == "add_location":
                return self._add_location(writer, kwargs)
            elif action == "add_plot_event":
                return self._add_plot_event(writer, kwargs)
            elif action == "get_memory_stats":
                return self._get_memory_stats(writer)
            elif action == "finalize_chapter":
                return self._finalize_chapter(writer, kwargs)
            else:
                return ToolResult.fail(f"Unknown action: {action}")
        
        except Exception as e:
            return ToolResult.fail(f"Error: {str(e)}")
    
    def _get_writer(self, novel_id: str) -> WriterMode:
        """Get or create a WriterMode instance"""
        if novel_id not in self.writers:
            # Try to load existing or create new
            self.writers[novel_id] = WriterMode(
                novel_id=novel_id,
                novel_title=f"Novel {novel_id}",
            )
        return self.writers[novel_id]
    
    def _start_chapter(self, writer: WriterMode, kwargs: Dict) -> ToolResult:
        """Start a new chapter"""
        chapter = kwargs.get("chapter", writer.current_chapter + 1)
        title = kwargs.get("data", {}).get("title", "")
        
        context = writer.start_new_chapter(chapter, title)
        
        return ToolResult.ok(
            f"Started Chapter {chapter}. Ready to write.",
            data=context
        )
    
    def _get_context(self, writer: WriterMode, kwargs: Dict) -> ToolResult:
        """Get comprehensive context for writing"""
        chapter = kwargs.get("chapter", writer.current_chapter)
        
        context = writer.get_chapter_context(chapter)
        
        context_str = self._format_context(context)
        
        return ToolResult.ok(context_str, data=context)
    
    def _add_character(self, writer: WriterMode, kwargs: Dict) -> ToolResult:
        """Add/update character"""
        data = kwargs.get("data", {})
        
        writer.update_character(
            name=data.get("name"),
            description=data.get("description"),
            traits=data.get("traits"),
            relationships=data.get("relationships"),
            development_notes=data.get("development_notes"),
            chapter=kwargs.get("chapter", writer.current_chapter),
        )
        
        return ToolResult.ok(f"Character '{data.get('name')}' updated.")
    
    def _add_location(self, writer: WriterMode, kwargs: Dict) -> ToolResult:
        """Add/update location"""
        data = kwargs.get("data", {})
        
        writer.update_location(
            name=data.get("name"),
            description=data.get("description"),
            atmosphere=data.get("atmosphere"),
            connections=data.get("connections"),
            chapter=kwargs.get("chapter", writer.current_chapter),
        )
        
        return ToolResult.ok(f"Location '{data.get('name')}' updated.")
    
    def _add_plot_event(self, writer: WriterMode, kwargs: Dict) -> ToolResult:
        """Add a plot event"""
        data = kwargs.get("data", {})
        
        writer.add_plot_event(
            chapter=kwargs.get("chapter", writer.current_chapter),
            summary=data.get("summary"),
            participants=data.get("participants", []),
            location=data.get("location", ""),
            is_major_twist=data.get("is_major_twist", False),
            consequences=data.get("consequences"),
        )
        
        return ToolResult.ok("Plot event recorded.")
    
    def _get_memory_stats(self, writer: WriterMode) -> ToolResult:
        """Get memory statistics"""
        stats = writer.get_memory_stats()
        
        stats_str = f"""
Novel Memory Statistics:
- Title: {stats['novel']['title']}
- Created: {stats['novel']['created_at']}
- Current Chapter: {stats['content']['total_chapters']}
- Total Words: {stats['content']['total_words']}
- Characters: {stats['memory']['total_characters']}
- Locations: {stats['memory']['total_locations']}
- Plot Events: {stats['memory']['total_plot_events']}
- Themes: {stats['memory']['total_themes']}
"""
        
        return ToolResult.ok(stats_str, data=stats)
    
    def _finalize_chapter(self, writer: WriterMode, kwargs: Dict) -> ToolResult:
        """Finalize and save a chapter"""
        chapter = kwargs.get("chapter", writer.current_chapter)
        content = kwargs.get("data", {}).get("content", "")
        title = kwargs.get("data", {}).get("title", "")
        
        # Analyze content first
        analysis = writer.analyze_written_content(chapter, content)
        
        # Finalize
        result = writer.finalize_chapter(
            chapter_num=chapter,
            content=content,
            chapter_title=title,
            key_events=kwargs.get("data", {}).get("key_events"),
            characters_involved=kwargs.get("data", {}).get("characters_involved"),
        )
        
        report = f"""
Chapter {chapter} Analysis:
- Word Count: {analysis['word_count']}
- Tone: {analysis['tone_analysis']['dominant_tone']}
- Emotional Intensity: {analysis['tone_analysis']['emotional_intensity']:.2f}
- Pacing: {analysis['tone_analysis']['pacing']}
- Quality Score: {analysis['quality_score']:.1f}/100

Consistency Report:
{analysis['consistency_report']}
"""
        
        return ToolResult.ok(report, data={
            "analysis": analysis,
            "result": result
        })
    
    def _format_context(self, context: Dict) -> str:
        """Format context for readable output"""
        lines = [
            "=== STORY CONTEXT ===",
            context.get("chapter_summary", "No previous context"),
            "",
            "=== ACTIVE CHARACTERS ===",
        ]
        
        for char in context.get("active_characters", []):
            lines.append(f"- {char['name']}: {char['description'][:80]}...")
        
        lines.extend([
            "",
            "=== LOCATIONS ===",
        ])
        
        for loc in context.get("active_locations", []):
            lines.append(f"- {loc['name']}: {loc['atmosphere']}")
        
        return "\n".join(lines)
