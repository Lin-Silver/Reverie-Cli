"""
Reverie-Ant Tools - Advanced tools for Reverie-Ant autonomous agentic mode

These tools enable:
- Transparent task progress tracking via task_boundary
- Intelligent user notifications with artifact review requests
- Artifact generation and management (task.md, implementation_plan.md, walkthrough.md)
- Continuous learning through context storage
"""

from typing import Dict, List, Optional
from rich.panel import Panel
from rich.text import Text
from rich import box

from .base import BaseTool, ToolResult

class TaskBoundaryTool(BaseTool):
    """
    Task Boundary Tool - Transparent progress tracking for autonomous agents
    
    Communicates current task, mode (PLANNING/EXECUTION/VERIFICATION), progress,
    and estimated scope to create a visible task UI for users.
    """
    name = "task_boundary"
    description = """
Communicate task progress and current focus through a structured boundary update.
Call this FREQUENTLY during agentic work to maintain transparency.

Used to:
- Start a new task with goal and estimated scope
- Update progress within a task (same TaskName = same UI block)
- Switch modes (PLANNING → EXECUTION → VERIFICATION)
- Signal completion of major milestones

BEST PRACTICES:
- Call BEFORE starting significant work phases (researching, implementing, testing)
- Call when switching between different component implementations
- Update TaskSummary cumulatively - include accomplishments AND what's currently being done
- Set TaskStatus to what you're ABOUT TO DO, not what you just finished
- Estimate PredictedTaskSize as number of tool calls needed
"""
    parameters = {
        "type": "object",
        "properties": {
            "TaskName": {
                "type": "string",
                "description": "Identifier of the current task objective (e.g., 'Planning API', 'Implementing Auth', 'Verifying Tests'). Same name = same UI block."
            },
            "TaskSummary": {
                "type": "string",
                "description": "Cumulative summary of what's been done and what's in progress. Include accomplishments + current work."
            },
            "TaskStatus": {
                "type": "string",
                "description": "What you're GOING TO DO NEXT - describes the immediate next steps or current action."
            },
            "Mode": {
                "type": "string",
                "description": "Agent mode: PLANNING (analyzing/designing), EXECUTION (building), VERIFICATION (testing/validating)."
            },
            "PredictedTaskSize": {
                "type": "integer",
                "description": "Estimated number of tool calls needed to complete this task phase."
            }
        },
        "required": ["TaskName", "Mode", "TaskSummary", "TaskStatus", "PredictedTaskSize"]
    }

    def execute(self, TaskName: str, Mode: str, TaskSummary: str, TaskStatus: str, PredictedTaskSize: int) -> ToolResult:
        """Execute task boundary update - display progress UI"""
        
        # Rich formatted output for beautiful CLI display
        rich_output = f"""
[bold #FFB8D1]╭── ✧ Task: {TaskName} ✧ ──╮[/bold #FFB8D1]
[bold #E4B0FF]│ Mode:[/bold #E4B0FF] {Mode} {'🔵' if Mode == 'PLANNING' else '⚙️' if Mode == 'EXECUTION' else '✓'}
[bold #E4B0FF]│[/bold #E4B0FF]
[bold #E4B0FF]│ Summary:[/bold #E4B0FF]
[#D9D9FF]{TaskSummary}[/#D9D9FF]
[bold #E4B0FF]│[/bold #E4B0FF]
[bold #E4B0FF]│ Next Steps:[/bold #E4B0FF]
[#D9D9FF]{TaskStatus}[/#D9D9FF]
[bold #E4B0FF]│[/bold #E4B0FF]
[bold #E4B0FF]│ Est. Scope:[/bold #E4B0FF] {PredictedTaskSize} tool calls
[bold #FFB8D1]╰──────────────────────────────────────────╯[/bold #FFB8D1]
"""
        return ToolResult.ok(rich_output.strip())

    def get_execution_message(self, **kwargs) -> str:
        return f"Task: {kwargs.get('TaskName', 'Unknown')} ({kwargs.get('Mode', 'PLANNING')}) - Next: {kwargs.get('TaskStatus', 'Continue')}"


class NotifyUserTool(BaseTool):
    """
    Notify User Tool - Request user review and feedback during agentic work
    
    Used to:
    - Request review of generated artifacts (implementation_plan.md, task.md)
    - Ask clarifying questions that block progress
    - Signal completion and readiness for next phase
    - Exit task mode for user interaction
    """
    name = "notify_user"
    description = """
Communicate with the user during task mode to request review, ask questions, or provide updates.

This is the PRIMARY mechanism for user interaction during agentic work.

CRITICAL: While in task mode, this is the ONLY way users see your messages.
Regular responses are hidden until you call notify_user.

USAGE:
1. Request artifact review:
   - PathsToReview: ["path/to/implementation_plan.md", "path/to/task.md"]
   - BlockedOnUser: true (wait for feedback) or false (can proceed)
   
2. Ask clarifying questions:
   - Message should ask specific questions
   - Set BlockedOnUser=true if you can't proceed without answers
   
3. Provide status updates:
   - Message summarizes progress
   - BlockedOnUser=false to continue autonomously

4. Signal completion:
   - Message describes what was accomplished
   - PathsToReview: relevant artifacts
   - BlockedOnUser=false (task complete)
"""
    parameters = {
        "type": "object",
        "properties": {
            "PathsToReview": {
                "type": "array",
                "items": {"type": "string"},
                "description": "List of ABSOLUTE file paths for user to review (implementation_plan.md, task.md, walkthrough.md, etc.)"
            },
            "BlockedOnUser": {
                "type": "boolean",
                "description": "true: wait for user feedback to proceed | false: can continue autonomously"
            },
            "Message": {
                "type": "string",
                "description": "Message to user - explain what's being reviewed, questions asked, or progress made."
            }
        },
        "required": ["PathsToReview", "BlockedOnUser", "Message"]
    }

    def execute(self, PathsToReview: List[str], BlockedOnUser: bool, Message: str) -> ToolResult:
        """Execute user notification - signal task mode exit for user interaction"""
        
        rich_output = f"""
[bold #FF5252]━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━[/bold #FF5252]
[bold #FF5252]→ User Review Required[/bold #FF5252]
[bold #FF5252]━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━[/bold #FF5252]

[#D9D9FF]{Message}[/#D9D9FF]
"""
        
        if PathsToReview:
            rich_output += "\n[bold #FFB8D1]📄 Files to Review:[/bold #FFB8D1]\n"
            for path in PathsToReview:
                rich_output += f"  → {path}\n"
        
        if BlockedOnUser:
            rich_output += "\n[bold #FF9500]⏸ WAITING FOR YOUR FEEDBACK[/bold #FF9500]\n"
            rich_output += "[#D9D9FF]Your input is required before the agent can continue.[/#D9D9FF]"
        else:
            rich_output += "\n[bold #4CAF50]✓ Can proceed autonomously[/bold #4CAF50]"
            
        return ToolResult.ok(rich_output.strip())

    def get_execution_message(self, **kwargs) -> str:
        return "Requesting user feedback..." if kwargs.get('BlockedOnUser') else "Notifying user of progress..."
