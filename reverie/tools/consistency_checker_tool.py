"""
Consistency Checker Tool - AI tool for validating story consistency

Provides AI agents with:
- Continuity checking
- Plot hole detection
- Repetition detection
- Character consistency validation
"""

from typing import Dict, Any, Optional

from .base import BaseTool, ToolResult
from ..writer import ConsistencyChecker


class ConsistencyCheckerTool(BaseTool):
    """
    Tool for checking consistency and continuity in novel content.
    """
    
    name = "consistency_checker"
    description = "Check for repetitions, contradictions, timeline issues, and continuity errors in novel content"
    
    parameters = {
        "type": "object",
        "properties": {
            "action": {
                "type": "string",
                "enum": [
                    "check_full",
                    "check_repetitions",
                    "check_contradictions",
                    "check_timeline",
                    "check_character",
                    "check_context",
                ]
            },
            "content": {
                "type": "string",
                "description": "Content to check"
            },
            "chapter": {
                "type": "integer",
                "description": "Chapter number"
            },
            "options": {
                "type": "object",
                "description": "Additional options for the check"
            }
        },
        "required": ["action", "content"]
    }
    
    def __init__(self, context: Optional[Dict] = None):
        super().__init__(context)
        self.checker = ConsistencyChecker()
    
    def execute(self, **kwargs) -> ToolResult:
        """Execute consistency check"""
        try:
            action = kwargs.get("action")
            content = kwargs.get("content", "")
            chapter = kwargs.get("chapter", 1)
            
            if action == "check_full":
                issues = self.checker.check_full_consistency(content, chapter)
                report = self.checker.generate_consistency_report(issues)
                return ToolResult.ok(report, data={"issues": issues})
            
            elif action == "check_repetitions":
                repetitions = self.checker._check_repetitions(content)
                return ToolResult.ok(
                    f"Found {len(repetitions)} repetitive issues:\n" +
                    "\n".join(f"- {issue.description}" for issue in repetitions),
                    data={"repetitions": repetitions}
                )
            
            elif action == "check_contradictions":
                contradictions = self.checker._check_contradictions(content, chapter)
                return ToolResult.ok(
                    f"Found {len(contradictions)} contradictions:\n" +
                    "\n".join(f"- {issue.description}" for issue in contradictions),
                    data={"contradictions": contradictions}
                )
            
            elif action == "check_timeline":
                timeline_issues = self.checker._check_timeline(content, chapter)
                return ToolResult.ok(
                    f"Found {len(timeline_issues)} timeline issues:\n" +
                    "\n".join(f"- {issue.description}" for issue in timeline_issues),
                    data={"timeline_issues": timeline_issues}
                )
            
            elif action == "check_character":
                char_issues = self.checker._check_character_consistency(content, chapter)
                return ToolResult.ok(
                    f"Found {len(char_issues)} character consistency issues:\n" +
                    "\n".join(f"- {issue.description}" for issue in char_issues),
                    data={"character_issues": char_issues}
                )
            
            elif action == "check_context":
                context_issues = self.checker._check_context_errors(content, chapter)
                return ToolResult.ok(
                    f"Found {len(context_issues)} context errors:\n" +
                    "\n".join(f"- {issue.description}" for issue in context_issues),
                    data={"context_issues": context_issues}
                )
            
            else:
                return ToolResult.fail(f"Unknown action: {action}")
        
        except Exception as e:
            return ToolResult.fail(f"Error checking consistency: {str(e)}")
