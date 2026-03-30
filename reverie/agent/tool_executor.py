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
import logging

from ..modes import normalize_mode
from ..tools.base import BaseTool, ToolResult
from ..tools.mcp_dynamic import MCPDynamicTool
from ..tools.registry import get_registered_tool_classes, is_tool_visible_in_mode
from ..plugin.dynamic_tool import RuntimePluginDynamicTool


logger = logging.getLogger(__name__)


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
        self._dynamic_tool_names: set[str] = set()
        self._mcp_generation: int = -1
        self._runtime_plugin_tool_names: set[str] = set()
        self._runtime_plugin_generation: int = -1
        self._schema_cache: Dict[tuple[Any, ...], List[Dict[str, Any]]] = {}
        self._init_tools()
    
    def _init_tools(self) -> None:
        """Initialize all available tools with context"""
        for tool_class in get_registered_tool_classes(include_hidden=True):
            tool = tool_class(self.context)
            self._tools[tool.name] = tool

    def _invalidate_schema_cache(self) -> None:
        self._schema_cache = {}

    def _sync_mcp_tools(self) -> None:
        """Refresh dynamic MCP-backed tools when the MCP catalog changes."""
        runtime = self.context.get("mcp_runtime")
        if runtime is None:
            if self._dynamic_tool_names:
                for name in list(self._dynamic_tool_names):
                    self._tools.pop(name, None)
                self._dynamic_tool_names = set()
                self._mcp_generation = -1
                self._invalidate_schema_cache()
            return

        try:
            definitions = runtime.get_tool_definitions(force_refresh=False)
            generation = int(runtime.get_generation())
        except Exception as exc:
            logger.debug("Failed to sync MCP tools: %s", exc, exc_info=True)
            return

        definition_names = {
            str(item.get("name", "")).strip()
            for item in definitions
            if isinstance(item, dict) and str(item.get("name", "")).strip()
        }

        if generation == self._mcp_generation and definition_names == self._dynamic_tool_names:
            return

        for name in list(self._dynamic_tool_names):
            self._tools.pop(name, None)

        new_dynamic_names: set[str] = set()
        for metadata in definitions:
            if not isinstance(metadata, dict):
                continue
            tool = MCPDynamicTool(self.context, metadata)
            self._tools[tool.name] = tool
            new_dynamic_names.add(tool.name)

        self._dynamic_tool_names = new_dynamic_names
        self._mcp_generation = generation
        self._invalidate_schema_cache()

    def _sync_runtime_plugin_tools(self) -> None:
        """Refresh dynamic Reverie runtime-plugin tools when the catalog changes."""
        manager = self.context.get("runtime_plugin_manager")
        if manager is None:
            if self._runtime_plugin_tool_names:
                for name in list(self._runtime_plugin_tool_names):
                    self._tools.pop(name, None)
                self._runtime_plugin_tool_names = set()
                self._runtime_plugin_generation = -1
                self._invalidate_schema_cache()
            return

        try:
            definitions = manager.get_tool_definitions(force_refresh=False)
            generation = int(manager.get_generation())
        except Exception as exc:
            logger.debug("Failed to sync runtime plugin tools: %s", exc, exc_info=True)
            return

        definition_names = {
            str(item.get("name", "")).strip()
            for item in definitions
            if isinstance(item, dict) and str(item.get("name", "")).strip()
        }

        if generation == self._runtime_plugin_generation and definition_names == self._runtime_plugin_tool_names:
            return

        for name in list(self._runtime_plugin_tool_names):
            self._tools.pop(name, None)

        new_dynamic_names: set[str] = set()
        for metadata in definitions:
            if not isinstance(metadata, dict):
                continue
            tool = RuntimePluginDynamicTool(self.context, metadata)
            self._tools[tool.name] = tool
            new_dynamic_names.add(tool.name)

        self._runtime_plugin_tool_names = new_dynamic_names
        self._runtime_plugin_generation = generation
        self._invalidate_schema_cache()

    def _sync_dynamic_tools(self) -> None:
        """Refresh all non-built-in dynamic tool surfaces."""
        self._sync_mcp_tools()
        self._sync_runtime_plugin_tools()
    
    def get_tool(self, name: str) -> Optional[BaseTool]:
        """Get a tool by name"""
        self._sync_dynamic_tools()
        return self._tools.get(name)
    
    def list_tools(self) -> List[str]:
        """List all available tool names"""
        self._sync_dynamic_tools()
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
        self._sync_dynamic_tools()
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
        normalized_mode = normalize_mode(mode)
        self._sync_dynamic_tools()
        cache_key = (normalized_mode, self._mcp_generation, self._runtime_plugin_generation)
        cached = self._schema_cache.get(cache_key)
        if cached is not None:
            return list(cached)

        schemas: List[Dict[str, Any]] = []

        for name, tool in self._tools.items():
            if isinstance(tool, MCPDynamicTool) and not tool.visible_in_mode(normalized_mode):
                continue
            if isinstance(tool, RuntimePluginDynamicTool) and not tool.visible_in_mode(normalized_mode):
                continue
            if not is_tool_visible_in_mode(name, normalized_mode):
                continue
                 
            # Get schema and validate it
            try:
                schema = tool.get_schema()
                json.dumps(schema, ensure_ascii=False)
                schemas.append(schema)
            except Exception as e:
                logger.error(f"Failed to get schema for tool {name}: {e}")
                # Skip this tool rather than breaking the entire request
                continue

        self._schema_cache[cache_key] = list(schemas)
        return schemas
    
    def update_context(self, key: str, value: Any) -> None:
        """Update shared context and reinitialize tools"""
        self.context[key] = value
        
        # Update all tool contexts
        for tool in self._tools.values():
            tool.context = self.context
        if key == "mcp_runtime":
            self._mcp_generation = -1
            self._sync_mcp_tools()
        if key == "runtime_plugin_manager":
            self._runtime_plugin_generation = -1
            self._sync_runtime_plugin_tools()
        self._invalidate_schema_cache()
