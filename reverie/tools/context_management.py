
from typing import Dict, Any, List, Optional
from pathlib import Path
import json
import re
from datetime import datetime
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
        "Supports generic truncation/summarization and a game-dev optimized summary."
    )
    
    parameters = {
        "type": "object",
        "properties": {
            "action": {
                "type": "string",
                "enum": ["truncate_history", "summarize_history", "summarize_game_context"],
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
            },
            "gdd_path": {
                "type": "string",
                "description": "Optional path to GDD file for gamer summary."
            },
            "asset_manifest_path": {
                "type": "string",
                "description": "Optional path to asset manifest JSON for gamer summary."
            },
            "task_list_path": {
                "type": "string",
                "description": "Optional path to task list JSON for gamer summary."
            }
        },
        "required": ["action"]
    }
    
    def execute(
        self,
        action: str,
        keep_last_messages: int = 20,
        summary: str = "",
        gdd_path: str = "",
        asset_manifest_path: str = "",
        task_list_path: str = ""
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
            elif action == "summarize_game_context":
                return self._summarize_game_context(
                    agent,
                    keep_last_messages,
                    gdd_path=gdd_path,
                    asset_manifest_path=asset_manifest_path,
                    task_list_path=task_list_path
                )
            else:
                return ToolResult.fail(f"Unknown action: {action}")
                
        except Exception as e:
            return ToolResult.fail(f"Context management failed: {str(e)}")
            
    def _truncate_history(self, agent, keep_last: int) -> ToolResult:
        """Truncate message history"""
        history = agent.get_history()
        if len(history) <= keep_last:
            return ToolResult.ok(f"History is already short ({len(history)} messages). No changes made.")
            
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
        
        return ToolResult.ok(f"Truncated history. Removed {removed_count} messages. Kept last {keep_last}.")

    def _summarize_history(self, agent, keep_last: int, summary: str) -> ToolResult:
        """Summarize older history"""
        if not summary:
            return ToolResult.fail("Summary text is required for 'summarize_history' action.")
            
        history = agent.get_history()
        if len(history) <= keep_last:
            return ToolResult.ok(f"History is already short ({len(history)} messages). No changes made.")
            
        new_history = history[-keep_last:]
        removed_count = len(history) - len(new_history)
        
        # Inject the summary
        summary_note = {
            "role": "system",
            "content": f"[System: Previous conversation summary: {summary}]"
        }
        new_history.insert(0, summary_note)
        
        agent.set_history(new_history)
        
        return ToolResult.ok(f"Compressed history with summary. Removed {removed_count} messages.")

    def _summarize_game_context(
        self,
        agent,
        keep_last: int,
        gdd_path: str = "",
        asset_manifest_path: str = "",
        task_list_path: str = ""
    ) -> ToolResult:
        """Summarize game-dev context into a compact system note."""
        summary_parts: List[str] = []
        summary_parts.append(f"Game Context Summary ({datetime.now().strftime('%Y-%m-%d')}):")

        gdd_summary = self._summarize_gdd(gdd_path)
        if gdd_summary:
            summary_parts.append("GDD:")
            summary_parts.extend([f"- {line}" for line in gdd_summary])

        task_summary = self._summarize_task_list(task_list_path)
        if task_summary:
            summary_parts.append("Task Progress:")
            summary_parts.extend([f"- {line}" for line in task_summary])

        asset_summary = self._summarize_asset_manifest(asset_manifest_path)
        if asset_summary:
            summary_parts.append("Assets:")
            summary_parts.extend([f"- {line}" for line in asset_summary])

        summary = "\n".join(summary_parts).strip()
        return self._summarize_history(agent, keep_last, summary)

    def _summarize_gdd(self, gdd_path: str) -> List[str]:
        if not gdd_path:
            return []
        path = self._resolve_path(gdd_path)
        if not path or not path.exists():
            return []
        try:
            text = path.read_text(encoding="utf-8", errors="ignore")
        except Exception:
            return []
        lines = [line.strip() for line in text.splitlines() if line.strip()]
        highlights = []
        for line in lines:
            if line.startswith("# "):
                highlights.append(line[2:].strip())
            elif line.lower().startswith("genre") or line.lower().startswith("engine"):
                highlights.append(line)
            if len(highlights) >= 5:
                break
        return highlights

    def _summarize_task_list(self, task_list_path: str) -> List[str]:
        if not task_list_path:
            return []
        path = self._resolve_path(task_list_path)
        if not path or not path.exists():
            return []
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            return []
        tasks = data.get("tasks", [])
        total = len(tasks)
        completed = len([t for t in tasks if t.get("state") == "COMPLETED"])
        in_progress = len([t for t in tasks if t.get("state") == "IN_PROGRESS"])
        return [f"Total {total}, In Progress {in_progress}, Completed {completed}"]

    def _summarize_asset_manifest(self, asset_manifest_path: str) -> List[str]:
        if not asset_manifest_path:
            return []
        path = self._resolve_path(asset_manifest_path)
        if not path or not path.exists():
            return []
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            return []
        assets = data.get("assets", [])
        counts: Dict[str, int] = {}
        for asset in assets:
            asset_type = asset.get("type", "unknown")
            counts[asset_type] = counts.get(asset_type, 0) + 1
        parts = [f"{k}: {v}" for k, v in sorted(counts.items())]
        return parts[:8]

    def _resolve_path(self, raw_path: str) -> Optional[Path]:
        try:
            path = Path(raw_path)
            if not path.is_absolute():
                project_root = self.context.get("project_root")
                if project_root:
                    path = Path(project_root) / path
            return path
        except Exception:
            return None
