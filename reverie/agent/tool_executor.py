"""
Tool Executor - Executes tool calls from the AI

Handles:
- Tool instantiation with proper context
- Parameter validation
- Execution and result formatting
- Error handling
"""

from typing import Dict, Any, Optional, List
from pathlib import Path

from ..tools import (
    BaseTool,
    ToolResult,
    CodebaseRetrievalTool,
    GitCommitRetrievalTool,
    StrReplaceEditorTool,
    FileOpsTool,
    CommandExecTool,
    WebSearchTool,
    TaskManagerTool,
    ContextManagementTool,
    CreateFileTool,
    UserInputTool,
    UserInputTool,
    ClarificationTool,
    TaskBoundaryTool,
    NotifyUserTool,
    GameAssetManagerTool,
    GameBalanceAnalyzerTool,
    LevelDesignTool,
    GameConfigEditorTool,
    GameAssetPackerTool,
    GameGDDManagerTool,
    StoryDesignTool,
    GameMathSimulatorTool,
    GameStatsAnalyzerTool
)


class ToolExecutor:
    """
    Executor for AI tool calls.
    
    Manages tool instances and executes calls with proper context.
    """
    
    def __init__(
        self,
        project_root: Path,
        retriever=None,
        indexer=None,
        git_integration=None
    ):
        self.project_root = project_root
        
        # Shared context for all tools
        self.context = {
            'project_root': project_root,
            'retriever': retriever,
            'indexer': indexer,
            'git_integration': git_integration
        }
        
        # Initialize tools
        self._tools: Dict[str, BaseTool] = {}
        self._init_tools()
    
    def _init_tools(self) -> None:
        """Initialize all available tools with context"""
        tool_classes = [
            CodebaseRetrievalTool,
            GitCommitRetrievalTool,
            StrReplaceEditorTool,
            FileOpsTool,
            CommandExecTool,
            WebSearchTool,
            TaskManagerTool,
            ContextManagementTool,
            CreateFileTool,
            UserInputTool,
            UserInputTool,
            ClarificationTool,
            TaskBoundaryTool,
            NotifyUserTool,
            GameAssetManagerTool,
            GameBalanceAnalyzerTool,
            LevelDesignTool,
            GameConfigEditorTool,
            GameAssetPackerTool,
            GameGDDManagerTool,
            StoryDesignTool,
            GameMathSimulatorTool,
            GameStatsAnalyzerTool
        ]
        
        for tool_class in tool_classes:
            tool = tool_class(self.context)
            self._tools[tool.name] = tool
    
    def get_tool(self, name: str) -> Optional[BaseTool]:
        """Get a tool by name"""
        return self._tools.get(name)
    
    def list_tools(self) -> List[str]:
        """List all available tool names"""
        return list(self._tools.keys())
    
    def execute(self, tool_name: str, arguments: Dict[str, Any]) -> ToolResult:
        """
        Execute a tool with given arguments.
        
        Args:
            tool_name: Name of the tool to execute
            arguments: Arguments to pass to the tool
        
        Returns:
            ToolResult with success status and output
        """
        tool = self.get_tool(tool_name)
        
        if not tool:
            return ToolResult.fail(
                f"Unknown tool: {tool_name}. "
                f"Available tools: {', '.join(self.list_tools())}"
            )
        
        # Validate parameters
        validation_error = tool.validate_params(arguments)
        if validation_error:
            return ToolResult.fail(f"Parameter validation failed: {validation_error}")
        
        try:
            result = tool.execute(**arguments)
            return result
        except Exception as e:
            return ToolResult.fail(f"Tool execution error: {str(e)}")
    
    def get_tool_schemas(self, mode: str = "reverie") -> List[Dict]:
        """
        Get OpenAI-format schemas for all tools, filtered by mode.
        
        This method ensures that all tool schemas are properly validated
        and safe for JSON serialization before returning them.
        """
        schemas = []
        for name, tool in self._tools.items():
            # Filter task_manager in non-reverie modes
            if name == "task_manager" and mode not in ["reverie", "reverie-gamer", "Reverie-Gamer"]:
                continue
            
            # Filter ask_clarification in non-writer modes
            if name == "ask_clarification" and mode != "writer":
                continue
                
            # Filter Reverie-ant tools
            if name in ["task_boundary", "notify_user"] and mode not in ["reverie-ant", "Reverie-ant"]:
                continue
                
            # Filter TaskManager in Reverie-ant (optional, but requested in prompt logic)
            # The prompt for Ant says "task_manager... tool is only for Reverie".
            # If we strictly follow, we hide it.
            if name == "task_manager" and mode in ["reverie-ant", "Reverie-ant"]:
                continue

            gamer_tools = {
                "game_asset_manager",
                "game_balance_analyzer",
                "level_design",
                "game_config_editor",
                "game_asset_packer",
                "game_gdd_manager",
                "story_design",
                "game_math_simulator",
                "game_stats_analyzer",
            }
            if name in gamer_tools and mode not in ["reverie-gamer", "Reverie-Gamer"]:
                continue
                
            # Get schema and validate it
            try:
                schema = tool.get_schema()
                # Validate that the schema can be serialized
                import json
                json.dumps(schema, ensure_ascii=False)
                schemas.append(schema)
            except Exception as e:
                import logging
                logger = logging.getLogger(__name__)
                logger.error(f"Failed to get schema for tool {name}: {e}")
                # Skip this tool rather than breaking the entire request
                continue
        
        return schemas
    
    def update_context(self, key: str, value: Any) -> None:
        """Update shared context and reinitialize tools"""
        self.context[key] = value
        
        # Update all tool contexts
        for tool in self._tools.values():
            tool.context = self.context
