"""
Plot Analyzer Tool - AI tool for analyzing and managing plot elements

Provides:
- Plot event recording
- Causality chain tracking
- Plot hole detection
- Story structure analysis
"""

from typing import Dict, Any, Optional

from .base import BaseTool, ToolResult
from ..writer import NarrativeAnalyzer


class PlotAnalyzerTool(BaseTool):
    """
    Tool for analyzing and managing plot elements.
    """
    
    name = "plot_analyzer"
    description = "Analyze plot structure, detect plot holes, and track narrative elements"
    
    parameters = {
        "type": "object",
        "properties": {
            "action": {
                "type": "string",
                "enum": [
                    "analyze_tone",
                    "detect_repetitions",
                    "check_character_voice",
                    "analyze_flow",
                    "summarize_arc",
                ]
            },
            "content": {
                "type": "string",
                "description": "Content to analyze"
            },
            "character": {
                "type": "string",
                "description": "Character name (for voice analysis)"
            },
            "chapters": {
                "type": "array",
                "description": "Chapters to analyze (for arc analysis)"
            }
        },
        "required": ["action"]
    }
    
    def __init__(self, context: Optional[Dict] = None):
        super().__init__(context)
        self.analyzer = NarrativeAnalyzer()
    
    def execute(self, **kwargs) -> ToolResult:
        """Execute plot analysis"""
        try:
            action = kwargs.get("action")
            content = kwargs.get("content", "")
            
            if action == "analyze_tone":
                tone = self.analyzer.analyze_tone(content)
                
                tone_report = f"""
TONE ANALYSIS:
- Dominant Tone: {tone.dominant_tone}
- Confidence: {tone.tone_confidence:.1%}
- Emotional Intensity: {tone.emotional_intensity:.1%}
- Pacing: {tone.pacing}
- Detected Tones: {', '.join(f'{t}: {c:.0%}' for t, c in tone.tones_present.items() if c > 0.1)}
"""
                return ToolResult.ok(tone_report, data={
                    "tone": tone.dominant_tone,
                    "confidence": tone.tone_confidence,
                    "intensity": tone.emotional_intensity,
                    "pacing": tone.pacing,
                    "all_tones": tone.tones_present,
                })
            
            elif action == "detect_repetitions":
                repetitions = self.analyzer.detect_repetitions(content)
                
                if repetitions:
                    rep_report = f"Found {len(repetitions)} repeated phrases:\n"
                    rep_report += "\n".join(f"- '{rep}'" for rep in repetitions)
                else:
                    rep_report = "No significant repetitions detected."
                
                return ToolResult.ok(rep_report, data={"repetitions": repetitions})
            
            elif action == "check_character_voice":
                character = kwargs.get("character", "Unknown")
                dialogues = kwargs.get("dialogues", [])
                
                if not dialogues:
                    return ToolResult.fail("No dialogues provided for character voice analysis")
                
                consistency = self.analyzer.analyze_character_consistency(character, dialogues)
                
                report = f"""
CHARACTER VOICE ANALYSIS FOR: {character}
- Consistency Score: {consistency['consistency_score']:.1%}
- Speech Patterns:
  - Formal Words: {consistency['speech_patterns'].get('formal_words', 0)}
  - Contractions: {consistency['speech_patterns'].get('contractions', 0)}
  - Exclamations: {consistency['speech_patterns'].get('exclamations', 0)}
  - Questions: {consistency['speech_patterns'].get('questions', 0)}
  - Average Sentence Length: {consistency['speech_patterns'].get('average_sentence_length', 0):.1f} words
"""
                return ToolResult.ok(report, data=consistency)
            
            elif action == "analyze_flow":
                chapters = kwargs.get("chapters", [])
                
                if not chapters:
                    return ToolResult.fail("No chapters provided for flow analysis")
                
                flow_issues = self.analyzer.check_logical_flow(chapters)
                
                if any(flow_issues.values()):
                    flow_report = "LOGICAL FLOW ISSUES DETECTED:\n"
                    for issue_type, issues in flow_issues.items():
                        if issues:
                            flow_report += f"\n{issue_type.replace('_', ' ').title()}:\n"
                            flow_report += "\n".join(f"- {issue}" for issue in issues)
                else:
                    flow_report = "No logical flow issues detected."
                
                return ToolResult.ok(flow_report, data=flow_issues)
            
            elif action == "summarize_arc":
                chapters = kwargs.get("chapters", [])
                
                if not chapters:
                    return ToolResult.fail("No chapters provided for arc analysis")
                
                arc_summary = self.analyzer.summarize_narrative_arc(chapters)
                return ToolResult.ok(arc_summary)
            
            else:
                return ToolResult.fail(f"Unknown action: {action}")
        
        except Exception as e:
            return ToolResult.fail(f"Error analyzing plot: {str(e)}")
