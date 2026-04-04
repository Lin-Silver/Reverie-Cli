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
import difflib
import json
import logging
import math
import re
import time

from ..config import get_project_data_dir
from ..modes import normalize_mode
from ..tools.base import BaseTool, ToolResult
from ..tools.mcp_dynamic import MCPDynamicTool
from ..tools.registry import (
    get_registered_tool_classes,
    get_supported_modes_for_tool,
    is_tool_visible_in_mode,
)
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
    DEFAULT_MAX_RESULT_CHARS = 50_000
    RESULT_PREVIEW_CHARS = 4_000
    
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
        self._tool_alias_lookup: Dict[str, str] = {}
        self._dynamic_tool_names: set[str] = set()
        self._mcp_generation: int = -1
        self._runtime_plugin_tool_names: set[str] = set()
        self._runtime_plugin_generation: int = -1
        self._schema_cache: Dict[tuple[Any, ...], List[Dict[str, Any]]] = {}
        self._init_tools()
    
    def _init_tools(self) -> None:
        """Initialize all available tools with context"""
        self._tools = {}
        for tool_class in get_registered_tool_classes(include_hidden=True):
            self._register_tool_instance(tool_class(self.context))
        self._rebuild_tool_alias_lookup()

    def _register_tool_instance(self, tool: BaseTool) -> None:
        """Register one concrete tool instance."""
        self._tools[str(tool.name or "").strip()] = tool

    def _rebuild_tool_alias_lookup(self) -> None:
        """Refresh alias -> primary-name mappings for the current tool pool."""
        lookup: Dict[str, str] = {}
        for name, tool in self._tools.items():
            normalized_name = str(name or "").strip()
            if not normalized_name:
                continue
            lookup.setdefault(normalized_name.lower(), normalized_name)
            for alias in tool.get_aliases():
                lookup.setdefault(alias.lower(), normalized_name)
        self._tool_alias_lookup = lookup

    def _invalidate_schema_cache(self) -> None:
        self._schema_cache = {}

    def _tool_is_visible(self, name: str, tool: BaseTool, mode: object) -> bool:
        """Return whether a tool should be exposed in the supplied mode."""
        normalized_mode = normalize_mode(mode)
        if isinstance(tool, MCPDynamicTool) and not tool.visible_in_mode(normalized_mode):
            return False
        if isinstance(tool, RuntimePluginDynamicTool) and not tool.visible_in_mode(normalized_mode):
            return False
        return is_tool_visible_in_mode(name, normalized_mode)

    def resolve_tool_name(self, name: str) -> str:
        """Resolve a tool name or alias to the registered primary tool name."""
        self._sync_dynamic_tools()
        wanted = str(name or "").strip()
        if not wanted:
            return ""
        if wanted in self._tools:
            return wanted

        lowered = wanted.lower()
        resolved = self._tool_alias_lookup.get(lowered)
        if resolved:
            return resolved

        for actual_name in self._tools:
            if actual_name.lower() == lowered:
                return actual_name
        return ""

    def _sync_mcp_tools(self) -> None:
        """Refresh dynamic MCP-backed tools when the MCP catalog changes."""
        runtime = self.context.get("mcp_runtime")
        if runtime is None:
            if self._dynamic_tool_names:
                for name in list(self._dynamic_tool_names):
                    self._tools.pop(name, None)
                self._dynamic_tool_names = set()
                self._mcp_generation = -1
                self._rebuild_tool_alias_lookup()
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
            self._register_tool_instance(tool)
            new_dynamic_names.add(tool.name)

        self._dynamic_tool_names = new_dynamic_names
        self._mcp_generation = generation
        self._rebuild_tool_alias_lookup()
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
                self._rebuild_tool_alias_lookup()
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
            self._register_tool_instance(tool)
            new_dynamic_names.add(tool.name)

        self._runtime_plugin_tool_names = new_dynamic_names
        self._runtime_plugin_generation = generation
        self._rebuild_tool_alias_lookup()
        self._invalidate_schema_cache()

    def _sync_dynamic_tools(self) -> None:
        """Refresh all non-built-in dynamic tool surfaces."""
        self._sync_mcp_tools()
        self._sync_runtime_plugin_tools()
    
    def get_tool(self, name: str) -> Optional[BaseTool]:
        """Get a tool by name"""
        self._sync_dynamic_tools()
        resolved = self.resolve_tool_name(name)
        if not resolved:
            return None
        return self._tools.get(resolved)
    
    def list_tools(self, mode: Optional[str] = None, include_aliases: bool = False) -> List[str]:
        """List available tool names, optionally filtered by visibility and aliases."""
        self._sync_dynamic_tools()
        normalized_mode = normalize_mode(mode) if mode is not None else ""
        visible: List[str] = []
        for name, tool in self._tools.items():
            if normalized_mode and not self._tool_is_visible(name, tool, normalized_mode):
                continue
            visible.append(name)
            if include_aliases:
                visible.extend(tool.get_aliases())
        return visible

    def get_tool_records(self, mode: str = "reverie") -> List[Dict[str, Any]]:
        """Return discovery-ready tool records for the visible tool surface."""
        normalized_mode = normalize_mode(mode)
        self._sync_dynamic_tools()
        records: List[Dict[str, Any]] = []

        for name, tool in self._tools.items():
            if not self._tool_is_visible(name, tool, normalized_mode):
                continue

            try:
                schema = tool.get_schema()
                json.dumps(schema, ensure_ascii=False)
            except Exception as exc:
                logger.error("Failed to get schema for tool %s: %s", name, exc)
                continue

            function = schema.get("function", {}) if isinstance(schema, dict) else {}
            parameters = function.get("parameters", {}) if isinstance(function, dict) else {}
            properties = parameters.get("properties", {}) if isinstance(parameters, dict) else {}
            metadata = tool.get_metadata()
            records.append(
                {
                    "name": name,
                    "tool": tool,
                    "schema": schema,
                    "description": str(function.get("description", "") or getattr(tool, "description", "") or "").strip(),
                    "required": list(parameters.get("required", [])) if isinstance(parameters, dict) else [],
                    "properties": list(properties.keys()) if isinstance(properties, dict) else [],
                    "property_schemas": dict(properties) if isinstance(properties, dict) else {},
                    "metadata": metadata,
                    "supported_modes": get_supported_modes_for_tool(name, include_hidden=True),
                }
            )

        return records

    def _extract_search_terms(self, tool: BaseTool) -> List[str]:
        """Collect discovery terms from one tool."""
        metadata = tool.get_metadata()
        values = [
            tool.name,
            *metadata.get("aliases", []),
            metadata.get("search_hint", ""),
            metadata.get("category", ""),
            *metadata.get("tags", []),
            getattr(tool, "description", ""),
        ]
        terms: List[str] = []
        for value in values:
            text = str(value or "").strip().lower()
            if text:
                terms.append(text)
        return terms

    def _suggest_tool_names(self, tool_name: str, *, mode: Optional[str] = None, limit: int = 5) -> List[str]:
        """Suggest the closest visible tool names for an unknown tool reference."""
        wanted = str(tool_name or "").strip().lower()
        if not wanted:
            return []

        normalized_mode = normalize_mode(mode) if mode else ""
        scored: List[tuple[float, str]] = []
        for name, tool in self._tools.items():
            if normalized_mode and not self._tool_is_visible(name, tool, normalized_mode):
                continue

            best_ratio = difflib.SequenceMatcher(None, wanted, name.lower()).ratio()
            for alias in tool.get_aliases():
                best_ratio = max(best_ratio, difflib.SequenceMatcher(None, wanted, alias.lower()).ratio())

            haystack = " ".join(self._extract_search_terms(tool))
            token_bonus = 0.0
            for token in re.findall(r"[A-Za-z0-9][A-Za-z0-9._-]*", wanted):
                lowered = token.lower()
                if lowered in haystack:
                    token_bonus += 0.08

            score = best_ratio + token_bonus
            if score >= 0.36:
                scored.append((score, name))

        scored.sort(key=lambda item: (-item[0], item[1].lower()))
        return [name for _, name in scored[: max(1, limit)]]

    def _unknown_tool_result(self, tool_name: str) -> ToolResult:
        """Build a helpful failure when a tool name cannot be resolved."""
        agent = self.context.get("agent")
        mode = normalize_mode(getattr(agent, "mode", "reverie")) if agent else "reverie"
        suggestions = self._suggest_tool_names(tool_name, mode=mode)
        lines = [f"Unknown tool: {tool_name}."]
        if suggestions:
            lines.append(f"Did you mean: {', '.join(suggestions)}?")
        lines.append(
            "If the exact tool is unclear, inspect the live tool surface with "
            "tool_catalog(operation=\"search\", query=\"...\")."
        )
        return ToolResult.fail(" ".join(lines))

    def _tool_result_dir(self) -> Path:
        """Return the workspace-local directory used for persisted tool outputs."""
        project_data_dir = self.context.get("project_data_dir")
        if project_data_dir:
            base_dir = Path(project_data_dir)
        else:
            base_dir = get_project_data_dir(self.project_root)
        result_dir = base_dir / "tool_results"
        result_dir.mkdir(parents=True, exist_ok=True)
        return result_dir

    def _coerce_result_limit(self, tool: BaseTool) -> Optional[int]:
        """Resolve one tool's max textual result budget."""
        value = getattr(tool, "max_result_chars", self.DEFAULT_MAX_RESULT_CHARS)
        try:
            number = float(value)
        except (TypeError, ValueError):
            number = float(self.DEFAULT_MAX_RESULT_CHARS)
        if not math.isfinite(number):
            return None
        return max(256, int(number))

    def _persist_large_text(self, tool_name: str, label: str, text: str) -> Path:
        """Write oversized tool text to the project cache and return the saved path."""
        safe_tool_name = re.sub(r"[^A-Za-z0-9._-]+", "-", str(tool_name or "tool")).strip("-._") or "tool"
        safe_label = re.sub(r"[^A-Za-z0-9._-]+", "-", str(label or "output")).strip("-._") or "output"
        target = self._tool_result_dir() / f"{safe_tool_name}-{safe_label}-{int(time.time() * 1000)}.txt"
        target.write_text(text, encoding="utf-8")
        return target

    def _truncate_tool_text(self, tool_name: str, label: str, text: str, limit: int) -> tuple[str, Dict[str, Any]]:
        """Persist and preview overly large tool output."""
        saved_to = self._persist_large_text(tool_name, label, text)
        preview_chars = min(self.RESULT_PREVIEW_CHARS, max(400, limit // 4))
        preview = text[:preview_chars].rstrip()
        clipped = (
            f"{preview}\n\n"
            f"[{label} truncated at {preview_chars}/{len(text)} chars]\n"
            f"Full {label} saved to: {saved_to}"
        )
        return clipped, {
            f"{label}_saved_to": str(saved_to),
            f"{label}_original_chars": len(text),
            f"{label}_preview_chars": len(preview),
            "tool_result_budget_applied": True,
        }

    def _apply_result_budget(self, tool: BaseTool, result: ToolResult) -> ToolResult:
        """Persist huge tool outputs so they do not overwhelm model context."""
        limit = self._coerce_result_limit(tool)
        if limit is None:
            return result

        output = result.output
        error = result.error
        metadata = dict(result.data or {})

        if isinstance(output, str) and len(output) > limit:
            output, extra = self._truncate_tool_text(tool.name, "output", output, limit)
            metadata.update(extra)

        if isinstance(error, str) and len(error) > limit:
            error, extra = self._truncate_tool_text(tool.name, "error", error, limit)
            metadata.update(extra)

        if metadata == (result.data or {}) and output == result.output and error == result.error:
            return result

        return ToolResult(
            success=result.success,
            output=output,
            error=error,
            data=metadata,
            status=result.status,
        )

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
    
    def execute(self, tool_name: str, arguments: Dict[str, Any], tool_call_id: str = "") -> ToolResult:
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
            return self._unknown_tool_result(tool_name)
        
        normalized_arguments = self._normalize_arguments(tool, arguments)

        # Validate parameters
        validation_error = tool.validate_params(normalized_arguments)
        if validation_error:
            return ToolResult.fail(f"Parameter validation failed: {validation_error}")
        
        previous_tool_name = self.context.get("active_tool_name")
        previous_tool_args = self.context.get("active_tool_arguments")
        previous_tool_call_id = self.context.get("active_tool_call_id")
        self.context["active_tool_name"] = tool_name
        self.context["active_tool_arguments"] = dict(normalized_arguments)
        self.context["active_tool_call_id"] = str(tool_call_id or "")

        try:
            result = tool.execute(**normalized_arguments)
            return self._apply_result_budget(tool, result)
        except Exception as e:
            return ToolResult.fail(f"Tool execution error: {str(e)}")
        finally:
            self.context["active_tool_name"] = previous_tool_name
            self.context["active_tool_arguments"] = previous_tool_args
            self.context["active_tool_call_id"] = previous_tool_call_id
    
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

        schemas: List[Dict[str, Any]] = [
            dict(record["schema"])
            for record in self.get_tool_records(mode=normalized_mode)
        ]

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
