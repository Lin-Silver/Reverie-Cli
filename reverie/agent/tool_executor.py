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
import json

from ..modes import normalize_mode
from ..tools import (
    BaseTool,
    ToolResult,
    CodebaseRetrievalTool,
    GitCommitRetrievalTool,
    StrReplaceEditorTool,
    FileOpsTool,
    DeleteFileTool,
    CommandExecTool,
    WebSearchTool,
    TaskManagerTool,
    ContextManagementTool,
    CreateFileTool,
    UserInputTool,
    ClarificationTool,
    TextToImageTool,
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
    GameStatsAnalyzerTool,
    GameDesignOrchestratorTool,
    GameProjectScaffolderTool,
    GamePlaytestLabTool,
    AtlasDeliveryOrchestratorTool,
    ReverieEngineTool,
    ReverieEngineLiteTool,
    VisionUploadTool,
    TokenCounterTool,
    ModeSwitchTool,
    ComputerControlTool,
)


class ToolExecutor:
    """
    Executor for AI tool calls.
    
    Manages tool instances and executes calls with proper context.
    """
    COMMON_PARAM_ALIASES = {
        "q": "query",
        "question": "query",
        "limit": "max_results",
        "num_results": "max_results",
        "timeout": "request_timeout",
        "retries": "max_retries",
        "workers": "fetch_workers",
        "worker": "fetch_workers",
        "filepath": "path",
        "file": "path",
    }
    WRAPPER_KEYS = {"args", "arguments", "parameters", "input", "payload"}
    
    def __init__(
        self,
        project_root: Path,
        retriever=None,
        indexer=None,
        git_integration=None,
        lsp_manager=None,
        memory_indexer=None,
    ):
        self.project_root = project_root
        
        # Shared context for all tools
        self.context = {
            'project_root': project_root,
            'retriever': retriever,
            'indexer': indexer,
            'git_integration': git_integration,
            'lsp_manager': lsp_manager,
            'memory_indexer': memory_indexer,
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
            DeleteFileTool,
            CommandExecTool,
            WebSearchTool,
            TaskManagerTool,
            ContextManagementTool,
            CreateFileTool,
            UserInputTool,
            ClarificationTool,
            TextToImageTool,
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
            GameStatsAnalyzerTool,
            GameDesignOrchestratorTool,
            GameProjectScaffolderTool,
            GamePlaytestLabTool,
            AtlasDeliveryOrchestratorTool,
            ReverieEngineTool,
            ReverieEngineLiteTool,
            VisionUploadTool,
            TokenCounterTool,
            ModeSwitchTool,
            ComputerControlTool,
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

    def _unwrap_arguments(self, arguments: Dict[str, Any]) -> Dict[str, Any]:
        """Unwrap common nested argument containers produced by some models."""
        if not isinstance(arguments, dict):
            return {}

        current = dict(arguments)
        for _ in range(2):
            if len(current) != 1:
                break
            key, value = next(iter(current.items()))
            if str(key).strip().lower() in self.WRAPPER_KEYS and isinstance(value, dict):
                current = dict(value)
                continue
            break
        return current

    def _normalize_arguments(self, tool: BaseTool, arguments: Dict[str, Any]) -> Dict[str, Any]:
        """Normalize tool arguments to reduce avoidable call failures."""
        normalized = self._unwrap_arguments(arguments)
        if not normalized:
            return {}

        # Canonicalize keys and drop empty key names
        normalized = {
            str(key).strip(): value
            for key, value in normalized.items()
            if str(key).strip()
        }

        properties = tool.parameters.get("properties", {}) if isinstance(tool.parameters, dict) else {}
        if not properties:
            return normalized

        # Case-insensitive key normalization to schema keys
        schema_key_map = {key.lower(): key for key in properties.keys()}
        for key in list(normalized.keys()):
            canonical = schema_key_map.get(key.lower())
            if canonical and canonical != key and canonical not in normalized:
                normalized[canonical] = normalized.pop(key)

        # Alias mapping (only if target schema key exists)
        for alias, target in self.COMMON_PARAM_ALIASES.items():
            if alias in normalized and target in properties and target not in normalized:
                normalized[target] = normalized.pop(alias)

        # Type coercion based on declared JSON schema
        for key, schema in properties.items():
            if key not in normalized:
                continue
            expected_type = schema.get("type")
            value = normalized[key]

            if expected_type == "integer":
                if isinstance(value, str):
                    try:
                        normalized[key] = int(value.strip())
                    except ValueError:
                        pass
                elif isinstance(value, float):
                    normalized[key] = int(value)

            elif expected_type == "boolean":
                if isinstance(value, str):
                    lowered = value.strip().lower()
                    if lowered in {"true", "1", "yes", "on"}:
                        normalized[key] = True
                    elif lowered in {"false", "0", "no", "off"}:
                        normalized[key] = False
                elif isinstance(value, (int, float)):
                    normalized[key] = bool(value)

            elif expected_type == "array":
                if isinstance(value, str):
                    stripped = value.strip()
                    if stripped.startswith("[") and stripped.endswith("]"):
                        try:
                            parsed = json.loads(stripped)
                            if isinstance(parsed, list):
                                normalized[key] = parsed
                        except Exception:
                            pass
                    else:
                        normalized[key] = [item.strip() for item in stripped.split(",") if item.strip()]

            elif expected_type == "string":
                if isinstance(value, (dict, list)):
                    normalized[key] = json.dumps(value, ensure_ascii=False)
                elif value is None:
                    normalized[key] = ""
                elif not isinstance(value, str):
                    normalized[key] = str(value)

        return normalized
    
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
        
        normalized_arguments = self._normalize_arguments(tool, arguments)

        # Validate parameters
        validation_error = tool.validate_params(normalized_arguments)
        if validation_error:
            return ToolResult.fail(f"Parameter validation failed: {validation_error}")
        
        try:
            result = tool.execute(**normalized_arguments)
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
        normalized_mode = normalize_mode(mode)

        for name, tool in self._tools.items():
            if name == "context_management":
                continue
            # Filter task_manager in non-reverie modes
            if name == "task_manager" and normalized_mode not in ["reverie", "reverie-gamer"]:
                continue
            
            # Filter ask_clarification in non-writer modes
            if name == "ask_clarification" and normalized_mode != "writer":
                continue
                
            # Filter Reverie-ant tools
            if name in ["task_boundary", "notify_user"] and normalized_mode != "reverie-ant":
                continue
                
            # Filter TaskManager in Reverie-ant (optional, but requested in prompt logic)
            # The prompt for Ant says "task_manager... tool is only for Reverie".
            # If we strictly follow, we hide it.
            if name == "task_manager" and normalized_mode == "reverie-ant":
                continue

            if name == "switch_mode" and normalized_mode == "computer-controller":
                continue

            if name == "computer_control" and normalized_mode != "computer-controller":
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
                "game_design_orchestrator",
                "game_project_scaffolder",
                "game_playtest_lab",
                "reverie_engine",
                "reverie_engine_lite",
            }
            if name in gamer_tools and normalized_mode != "reverie-gamer":
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
