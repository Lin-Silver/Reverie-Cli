
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
                "enum": ["compress", "truncate_history", "summarize_history", "summarize_game_context", "checkpoint", "restore"],
                "description": "The action to perform."
            },
            "keep_last_messages": {
                "type": "integer",
                "description": "For 'truncate_history' or 'compress': Number of recent messages to keep (e.g., 10). Default is 20.",
                "default": 20
            },
            "summary": {
                "type": "string",
                "description": "For 'summarize_history': The summary of the removed messages to inject as a system note."
            },
            "checkpoint_id": {
                "type": "string",
                "description": "For 'restore': The checkpoint ID to restore from."
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
        checkpoint_id: str = "",
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
            if action == "compress":
                # Use the compressor for intelligent compression
                return self._compress_with_llm(agent, keep_last_messages)
            elif action == "truncate_history":
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
            elif action == "checkpoint":
                return self._create_checkpoint(agent)
            elif action == "restore":
                return self._restore_checkpoint(agent, checkpoint_id)
            else:
                return ToolResult.fail(f"Unknown action: {action}")
                
        except Exception as e:
            return ToolResult.fail(f"Context management failed: {str(e)}")
            
    def _truncate_history(self, agent, keep_last: int) -> ToolResult:
        """Truncate message history"""
        history = agent.get_history()
        if len(history) <= keep_last:
            return ToolResult.ok(f"History is already short ({len(history)} messages). No changes made.")
            
        # Save checkpoint before truncation
        session_manager = self.context.get('session_manager')
        if session_manager and hasattr(session_manager, 'get_current_session'):
            current_session = session_manager.get_current_session()
            if current_session:
                # Save current state before truncation
                session_manager.update_messages(history)
        
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
        
        # Save truncated state
        if session_manager and current_session:
            session_manager.update_messages(new_history)
        
        return ToolResult.ok(f"Truncated history. Removed {removed_count} messages. Kept last {keep_last}.")

    def _summarize_history(self, agent, keep_last: int, summary: str) -> ToolResult:
        """Summarize older history"""
        if not summary:
            return ToolResult.fail("Summary text is required for 'summarize_history' action.")
            
        history = agent.get_history()
        if len(history) <= keep_last:
            return ToolResult.ok(f"History is already short ({len(history)} messages). No changes made.")
        
        # Save checkpoint before summarization
        session_manager = self.context.get('session_manager')
        if session_manager and hasattr(session_manager, 'get_current_session'):
            current_session = session_manager.get_current_session()
            if current_session:
                # Save current state before summarization
                session_manager.update_messages(history)
        
        new_history = history[-keep_last:]
        removed_count = len(history) - len(new_history)
        
        # Inject the summary
        summary_note = {
            "role": "system",
            "content": f"[System: Previous conversation summary: {summary}]"
        }
        new_history.insert(0, summary_note)
        
        agent.set_history(new_history)
        
        # Save summarized state
        if session_manager and current_session:
            session_manager.update_messages(new_history)
        
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
            return self.resolve_workspace_path(raw_path, purpose="resolve context-management path")
        except Exception:
            return None
    
    def _compress_with_llm(self, agent, keep_last: int) -> ToolResult:
        """Compress history using LLM-based compression"""
        from ..context_engine.compressor import ContextCompressor
        
        history = agent.get_history()
        if len(history) <= keep_last:
            return ToolResult.ok(f"History is already short ({len(history)} messages). No changes made.")
        
        # Get compressor
        project_root = self.context.get('project_root')
        if not project_root:
            return ToolResult.fail("Project root not available for compression")
        
        compressor = ContextCompressor(Path(project_root) / '.reverie')
        
        # Get session info
        session_manager = self.context.get('session_manager')
        session_id = "default"
        if session_manager and hasattr(session_manager, 'get_current_session'):
            current_session = session_manager.get_current_session()
            if current_session:
                session_id = current_session.id
        
        # Get model info from agent
        model = getattr(agent, 'model', 'gpt-4')
        provider = getattr(agent, 'provider', 'openai-sdk')
        base_url = getattr(agent, 'base_url', '')
        api_key = getattr(agent, 'api_key', '')
        
        # Get client
        client = None
        if provider in ['openai-sdk', 'anthropic']:
            client = getattr(agent, '_client', None)
        
        # Compress
        try:
            compressed_history = compressor.compress(
                messages=history,
                client=client,
                model=model,
                session_id=session_id,
                provider=provider,
                base_url=base_url,
                api_key=api_key
            )
            
            # Update agent history
            agent.set_history(compressed_history)
            
            # Save to session
            if session_manager and hasattr(session_manager, 'update_messages'):
                session_manager.update_messages(compressed_history)
            
            removed_count = len(history) - len(compressed_history)
            return ToolResult.ok(
                f"Successfully compressed conversation history.\n"
                f"Original: {len(history)} messages\n"
                f"Compressed: {len(compressed_history)} messages\n"
                f"Removed: {removed_count} messages\n"
                f"Checkpoint saved before compression."
            )
        except Exception as e:
            return ToolResult.fail(f"Compression failed: {str(e)}")
    
    def _create_checkpoint(self, agent) -> ToolResult:
        """Create a checkpoint of current conversation state"""
        from ..context_engine.compressor import ContextCompressor
        
        history = agent.get_history()
        
        # Get compressor
        project_root = self.context.get('project_root')
        if not project_root:
            return ToolResult.fail("Project root not available for checkpoint")
        
        compressor = ContextCompressor(Path(project_root) / '.reverie')
        
        # Get session info
        session_manager = self.context.get('session_manager')
        session_id = "default"
        if session_manager and hasattr(session_manager, 'get_current_session'):
            current_session = session_manager.get_current_session()
            if current_session:
                session_id = current_session.id
        
        # Save checkpoint
        checkpoint_path = compressor.save_checkpoint(
            messages=history,
            note="Manual checkpoint via context_management tool",
            session_id=session_id
        )
        
        if checkpoint_path:
            return ToolResult.ok(
                f"Checkpoint created successfully.\n"
                f"Messages saved: {len(history)}\n"
                f"Checkpoint file: {Path(checkpoint_path).name}"
            )
        else:
            return ToolResult.fail("Failed to create checkpoint")
    
    def _restore_checkpoint(self, agent, checkpoint_id: str) -> ToolResult:
        """Restore from a checkpoint"""
        if not checkpoint_id:
            return ToolResult.fail("Checkpoint ID is required for restore action")
        
        from ..context_engine.compressor import ContextCompressor
        
        # Get compressor
        project_root = self.context.get('project_root')
        if not project_root:
            return ToolResult.fail("Project root not available for restore")
        
        compressor = ContextCompressor(Path(project_root) / '.reverie')
        
        # Find checkpoint file
        checkpoint_path = Path(checkpoint_id)
        if checkpoint_path.is_absolute():
            checkpoint_path = self.ensure_workspace_path(
                checkpoint_path,
                purpose="restore checkpoint",
            )
        else:
            checkpoint_path = self.ensure_workspace_path(
                compressor.cache_dir / checkpoint_id,
                purpose="restore checkpoint",
            )
        
        if not checkpoint_path.exists():
            return ToolResult.fail(f"Checkpoint not found: {checkpoint_id}")
        
        # Load checkpoint
        try:
            import json
            with open(checkpoint_path, 'r', encoding='utf-8') as f:
                checkpoint_data = json.load(f)
            
            messages = checkpoint_data.get('messages', [])
            if not messages:
                return ToolResult.fail("Checkpoint contains no messages")
            
            # Restore to agent
            agent.set_history(messages)
            
            # Save to session
            session_manager = self.context.get('session_manager')
            if session_manager and hasattr(session_manager, 'update_messages'):
                session_manager.update_messages(messages)
            
            return ToolResult.ok(
                f"Successfully restored from checkpoint.\n"
                f"Restored {len(messages)} messages\n"
                f"Checkpoint: {checkpoint_data.get('note', 'N/A')}\n"
                f"Timestamp: {checkpoint_data.get('timestamp', 'N/A')}"
            )
        except Exception as e:
            return ToolResult.fail(f"Failed to restore checkpoint: {str(e)}")
