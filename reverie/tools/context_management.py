
from typing import Dict, Any, List
from .base import BaseTool, ToolResult

class ContextManagementTool(BaseTool):
    """
    Tool for managing and compressing the agent's context window.
    Allows the model to actively reduce token usage by summarizing 
    or truncating its own conversation history.
    """
    
    name = "context_management"
    description = (
        "Manage and compress your own context window. "
        "Use this when you are running low on tokens or want to declutter conversation history. "
        "You can truncate history to keep only the most recent messages."
    )
    
    parameters = {
        "type": "object",
        "properties": {
            "action": {
                "type": "string",
                "enum": ["truncate_history", "summarize_history"],
                "description": "The action to perform."
            },
            "keep_last_messages": {
                "type": "integer",
                "description": "For 'truncate_history': Number of recent messages to keep (e.g., 10). Default is 20.",
                "default": 20
            },
            "summary": {
                "type": "string",
                "description": "For 'summarize_history': The summary of the removed messages to inject as a system note."
            }
        },
        "required": ["action"]
    }
    
    def execute(
        self,
        action: str,
        keep_last_messages: int = 20,
        summary: str = ""
    ) -> ToolResult:
        """
        Execute context management action.
        """
        # We need access to the agent instance
        agent = self.context.get('agent')
        if not agent:
            return ToolResult.fail("Context tool requires access to Agent instance")
        
        try:
            if action == "truncate_history":
                return self._truncate_history(agent, keep_last_messages)
            elif action == "summarize_history":
                return self._summarize_history(agent, keep_last_messages, summary)
            else:
                return ToolResult.fail(f"Unknown action: {action}")
                
        except Exception as e:
            return ToolResult.fail(f"Context management failed: {str(e)}")
            
    def _truncate_history(self, agent, keep_last: int) -> ToolResult:
        """Truncate message history"""
        history = agent.get_history()
        if len(history) <= keep_last:
            return ToolResult.success(f"History is already short ({len(history)} messages). No changes made.")
            
        # Always keep system prompt (index 0 if it's there, but agent handles that separately usually)
        # Agent.messages usually starts with user/assistant exchanges. System prompt is separate.
        
        new_history = history[-keep_last:]
        
        # Calculate removed
        removed_count = len(history) - len(new_history)
        
        # Inject a system note about the truncation
        truncation_note = {
            "role": "system",
            "content": f"[System: Conversation history was truncated. {removed_count} older messages were removed to save tokens.]"
        }
        new_history.insert(0, truncation_note)
        
        agent.set_history(new_history)
        
        return ToolResult.success(f"Truncated history. Removed {removed_count} messages. Kept last {keep_last}.")

    def _summarize_history(self, agent, keep_last: int, summary: str) -> ToolResult:
        """Summarize older history"""
        if not summary:
            return ToolResult.fail("Summary text is required for 'summarize_history' action.")
            
        history = agent.get_history()
        if len(history) <= keep_last:
            return ToolResult.success(f"History is already short ({len(history)} messages). No changes made.")
            
        new_history = history[-keep_last:]
        removed_count = len(history) - len(new_history)
        
        # Inject the summary
        summary_note = {
            "role": "system",
            "content": f"[System: Previous conversation summary: {summary}]"
        }
        new_history.insert(0, summary_note)
        
        agent.set_history(new_history)
        
        return ToolResult.success(f"Compressed history with summary. Removed {removed_count} messages.")
