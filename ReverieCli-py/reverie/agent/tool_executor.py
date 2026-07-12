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
from ..diagnostics import report_suppressed_exception
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
        "filename": "path",
        "dest": "path",
        "destination": "path",
        "dest_path": "path",
        "text": "content",
        "body": "content",
        "contents": "content",
        "file_text": "content",
        "markdown": "content",
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

    def _get_memory_os(self):
        """Return the shared Memory OS facade when available."""
        existing = self.context.get("memory_os")
        if existing is not None:
            return existing
        try:
            from ..memory import MemoryOS

            project_data_dir = self.context.get("project_data_dir") or get_project_data_dir(Path(self.project_root))
            memory_os = MemoryOS(Path(project_data_dir), project_root=Path(self.project_root))
            self.context["memory_os"] = memory_os
            return memory_os
        except Exception:
            logger.debug("Failed to initialize Memory OS from ToolExecutor", exc_info=True)
            return None

    def _record_memory_event(
        self,
        event_type: str,
        payload: Dict[str, Any],
        *,
        actor: str = "tool",
        tags: Optional[List[str]] = None,
        consolidate: bool = True,
    ) -> None:
        memory_os = self._get_memory_os()
        if not memory_os:
            return
        session_id = "default"
        agent = self.context.get("agent")
        if agent is not None and hasattr(agent, "_current_session_details"):
            try:
                session_id = agent._current_session_details("default")[0]
            except Exception:
                session_id = "default"
        try:
            memory_os.record_event(
                event_type,
                payload,
                actor=actor,
                session_id=session_id,
                tags=tags,
                consolidate=consolidate,
            )
        except Exception:
            logger.debug("Failed to record Memory OS tool event", exc_info=True)

    def _record_operation_usage(self, tool: Any, result: ToolResult, duration_ms: int = 0) -> None:
        manager = self.context.get("workspace_stats_manager")
        if manager is None or not hasattr(manager, "record_operation"):
            return
        tool_name = str(getattr(tool, "name", tool) or "").strip()
        metadata = getattr(tool, "metadata", {}) if tool is not None else {}
        plugin_id = str(metadata.get("plugin_id") or "").strip() if isinstance(metadata, dict) else ""
        category = "plugin-tool" if plugin_id else "tool"
        session_id = "default"
        agent = self.context.get("agent")
        if agent is not None and hasattr(agent, "_current_session_details"):
            try:
                session_id = agent._current_session_details("default")[0]
            except Exception:
                report_suppressed_exception("resolve tool execution session", logger=logger)
        try:
            manager.record_operation(
                category=category,
                name=tool_name,
                plugin_id=plugin_id,
                success=bool(result.success),
                duration_ms=max(int(duration_ms), 0),
                session_id=session_id,
            )
        except Exception:
            logger.debug("Failed to record tool usage statistics", exc_info=True)

    def _candidate_file_paths(self, tool_name: str, arguments: Dict[str, Any]) -> List[Path]:
        if tool_name not in {"str_replace_editor", "create_file", "delete_file", "file_ops"}:
            return []
        raw_paths: List[Any] = []
        for key in ("path", "file_path", "target_path", "target_file"):
            if key in arguments:
                raw_paths.append(arguments.get(key))
        paths: List[Path] = []
        root = Path(self.project_root).resolve()
        for raw_path in raw_paths:
            text = str(raw_path or "").strip()
            if not text:
                continue
            try:
                path = Path(text)
                if not path.is_absolute():
                    path = root / path
                resolved = path.resolve()
                try:
                    resolved.relative_to(root)
                except ValueError:
                    continue
                if resolved not in paths:
                    paths.append(resolved)
            except Exception:
                continue
        return paths

    @staticmethod
    def _read_text_snapshot(path: Path) -> Optional[str]:
        try:
            if not path.exists() or not path.is_file():
                return ""
            return path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            return None
        except Exception:
            return None

    def _snapshot_file_paths(self, paths: List[Path]) -> Dict[str, Optional[str]]:
        return {str(path): self._read_text_snapshot(path) for path in paths}

    def _record_file_diffs(
        self,
        *,
        before: Dict[str, Optional[str]],
        tool_name: str,
        arguments: Dict[str, Any],
        result: ToolResult,
    ) -> None:
        if not before:
            return
        for path_text, before_text in before.items():
            path = Path(path_text)
            after_text = self._read_text_snapshot(path)
            if before_text is None or after_text is None or before_text == after_text:
                continue
            diff = "\n".join(
                difflib.unified_diff(
                    (before_text or "").splitlines(),
                    (after_text or "").splitlines(),
                    fromfile=f"{path_text}:before",
                    tofile=f"{path_text}:after",
                    lineterm="",
                )
            )
            self._record_memory_event(
                "file_diff",
                {
                    "tool_name": tool_name,
                    "path": path_text,
                    "arguments": arguments,
                    "success": bool(result.success),
                    "diff": diff,
                },
                actor="tool",
                tags=["file_diff", tool_name],
            )

    def _tool_is_visible(self, name: str, tool: BaseTool, mode: object) -> bool:
        """Return whether a tool should be exposed in the supplied mode."""
        normalized_mode = normalize_mode(mode)
        if normalized_mode == "writer" and isinstance(tool, (MCPDynamicTool, RuntimePluginDynamicTool)):
            return False
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
        lines.append("Use one of the tool schemas included in the current request.")
        return ToolResult.fail(" ".join(lines))

    def _path_like_argument_values(self, arguments: Dict[str, Any]) -> List[str]:
        """Extract likely filesystem path arguments for subagent scope checks."""
        path_keys = {
            "path",
            "file",
            "file_path",
            "filepath",
            "source_path",
            "target_path",
            "dest_path",
            "destination",
            "output_path",
            "output_dir",
            "asset_dir",
            "manifest_path",
            "bbmodel_path",
            "relative_path",
        }
        values: List[str] = []
        for key, value in (arguments or {}).items():
            lowered = str(key or "").strip().lower()
            if lowered not in path_keys and not lowered.endswith("_path") and not lowered.endswith("_dir"):
                continue
            if isinstance(value, list):
                values.extend(str(item) for item in value if str(item or "").strip())
            elif isinstance(value, str) and value.strip():
                values.append(value.strip())
        return values

    def _resolve_scope_paths(self, raw_scope: Any) -> List[Path]:
        roots: List[Path] = []
        if not isinstance(raw_scope, list):
            return roots
        for item in raw_scope:
            text = str(item or "").strip()
            if not text:
                continue
            try:
                candidate = Path(text)
                if not candidate.is_absolute():
                    candidate = self.project_root / candidate
                roots.append(candidate.resolve(strict=False))
            except Exception:
                continue
        return roots

    def _argument_paths_in_scope(self, arguments: Dict[str, Any], scope_paths: List[Path]) -> bool:
        if not scope_paths:
            return False
        values = self._path_like_argument_values(arguments)
        if not values:
            return False
        for value in values:
            try:
                candidate = Path(value)
                if not candidate.is_absolute():
                    candidate = self.project_root / candidate
                resolved = candidate.resolve(strict=False)
            except Exception:
                return False
            if not any(resolved == scope or scope in resolved.parents for scope in scope_paths):
                return False
        return True

    def _code_query_in_read_scope(self, arguments: Dict[str, Any], scope_paths: List[Path]) -> bool:
        """Allow only code queries whose target path can be proven in scope."""
        query_type = str(arguments.get("query_type") or "").strip().lower()
        if query_type not in {"file", "outline"}:
            return False
        query = str(arguments.get("query") or "").strip()
        if not query:
            return False
        return self._argument_paths_in_scope({"path": query}, scope_paths)

    def _subagent_scope_denial(self, tool: BaseTool, arguments: Dict[str, Any]) -> Optional[str]:
        """Enforce default read-only and optional scope bounds for subagents."""
        if not self.context.get("is_subagent"):
            return None

        write_scope = self._resolve_scope_paths(self.context.get("subagent_write_scope"))
        read_scope = self._resolve_scope_paths(self.context.get("subagent_read_scope"))

        if not bool(getattr(tool, "read_only", False)):
            if not write_scope:
                return (
                    f"Subagent policy denied {tool.name}: subagents are read-only by default. "
                    "The main agent must provide write_scope for bounded edits."
                )
            if not self._argument_paths_in_scope(arguments, write_scope):
                return (
                    f"Subagent policy denied {tool.name}: write paths must be inside the assigned write_scope."
                )
            return None

        if read_scope:
            path_values = self._path_like_argument_values(arguments)
            if path_values and not self._argument_paths_in_scope(arguments, read_scope):
                return (
                    f"Subagent policy denied {tool.name}: read paths must be inside the assigned read_scope."
                )
            if tool.name == "codebase-retrieval" and not self._code_query_in_read_scope(arguments, read_scope):
                return (
                    f"Subagent policy denied {tool.name}: query scope cannot be safely proven "
                    "inside the assigned read_scope."
                )
        return None

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
                        except json.JSONDecodeError:
                            logger.debug("Tool array coercion kept original non-JSON value for %s", key)
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
            self._record_memory_event(
                "tool_call",
                {"tool_name": tool_name, "arguments": arguments or {}, "tool_call_id": str(tool_call_id or "")},
                actor="assistant",
                tags=["tool", str(tool_name or "")],
                consolidate=False,
            )
            result = self._unknown_tool_result(tool_name)
            self._record_memory_event(
                "tool_result",
                {
                    "tool_name": tool_name,
                    "arguments": arguments or {},
                    "tool_call_id": str(tool_call_id or ""),
                    "success": False,
                    "output": "",
                    "error": result.error,
                    "status": str(getattr(result.status, "value", "error")),
                },
                actor="tool",
                tags=["tool", "error", str(tool_name or "")],
            )
            self._record_operation_usage(tool_name, result)
            return result
        
        normalized_arguments = self._normalize_arguments(tool, arguments)
        agent = self.context.get("agent")
        active_mode = normalize_mode(getattr(agent, "mode", "reverie")) if agent is not None else "reverie"
        if active_mode == "writer" and tool.name in {"str_replace_editor", "create_file", "delete_file", "file_ops"}:
            raw_path = str(normalized_arguments.get("path", "") or "").strip()
            if raw_path:
                candidate = Path(raw_path)
                if not candidate.is_absolute():
                    candidate = self.project_root / candidate
                candidate = candidate.resolve(strict=False)
                novels_root = (self.project_root / "novels").resolve(strict=False)
                reader_root = (self.project_root / "novel").resolve(strict=False)
                if (
                    candidate == novels_root
                    or novels_root in candidate.parents
                    or candidate == reader_root
                    or reader_root in candidate.parents
                ):
                    return ToolResult.fail(
                        "Writer project files under novels/ and novel/ are transaction-managed. "
                        "Use serial_novel actions instead of generic file editing."
                    )
        before_snapshots = self._snapshot_file_paths(self._candidate_file_paths(tool.name, normalized_arguments))
        self._record_memory_event(
            "tool_call",
            {
                "tool_name": tool.name,
                "arguments": normalized_arguments,
                "tool_call_id": str(tool_call_id or ""),
            },
            actor="assistant",
            tags=["tool", tool.name],
            consolidate=False,
        )

        # Validate parameters
        validation_error = tool.validate_params(normalized_arguments)
        if validation_error:
            result = ToolResult.fail(f"Parameter validation failed: {validation_error}")
            self._record_memory_event(
                "tool_result",
                {
                    "tool_name": tool.name,
                    "arguments": normalized_arguments,
                    "tool_call_id": str(tool_call_id or ""),
                    "success": False,
                    "output": "",
                    "error": result.error,
                    "status": str(getattr(result.status, "value", "error")),
                },
                actor="tool",
                tags=["tool", "error", tool.name],
            )
            self._record_file_diffs(
                before=before_snapshots,
                tool_name=tool.name,
                arguments=normalized_arguments,
                result=result,
            )
            self._record_operation_usage(tool, result)
            return result

        subagent_denial = self._subagent_scope_denial(tool, normalized_arguments)
        if subagent_denial:
            result = ToolResult.fail(subagent_denial)
            self._record_memory_event(
                "tool_result",
                {
                    "tool_name": tool.name,
                    "arguments": normalized_arguments,
                    "tool_call_id": str(tool_call_id or ""),
                    "success": False,
                    "output": "",
                    "error": result.error,
                    "status": str(getattr(result.status, "value", "error")),
                },
                actor="tool",
                tags=["tool", "error", tool.name],
            )
            self._record_operation_usage(tool, result)
            return result
        
        previous_tool_name = self.context.get("active_tool_name")
        previous_tool_args = self.context.get("active_tool_arguments")
        previous_tool_call_id = self.context.get("active_tool_call_id")
        self.context["active_tool_name"] = tool_name
        self.context["active_tool_arguments"] = dict(normalized_arguments)
        self.context["active_tool_call_id"] = str(tool_call_id or "")

        lifecycle_manager = self.context.get("lifecycle_manager")
        if lifecycle_manager and hasattr(lifecycle_manager, "before_tool"):
            try:
                decision = lifecycle_manager.before_tool(tool.name, normalized_arguments, self.context)
            except Exception as exc:
                logger.debug("Lifecycle pre-tool hook failed: %s", exc, exc_info=True)
                decision = None
            if decision is not None and not getattr(decision, "allowed", True):
                self.context["active_tool_name"] = previous_tool_name
                self.context["active_tool_arguments"] = previous_tool_args
                self.context["active_tool_call_id"] = previous_tool_call_id
                result = ToolResult.fail(f"Lifecycle hook denied {tool.name}: {getattr(decision, 'reason', '')}")
                self._record_memory_event(
                    "tool_result",
                    {
                        "tool_name": tool.name,
                        "arguments": normalized_arguments,
                        "tool_call_id": str(tool_call_id or ""),
                        "success": False,
                        "output": "",
                        "error": result.error,
                        "status": str(getattr(result.status, "value", "error")),
                    },
                    actor="tool",
                    tags=["tool", "error", tool.name],
                )
                self._record_operation_usage(tool, result)
                return result

        started = time.perf_counter()
        try:
            result = tool.execute(**normalized_arguments)
            result = self._apply_result_budget(tool, result)
            if lifecycle_manager and hasattr(lifecycle_manager, "after_tool"):
                try:
                    lifecycle_manager.after_tool(
                        tool.name,
                        normalized_arguments,
                        result,
                        int((time.perf_counter() - started) * 1000),
                        self.context,
                    )
                except Exception as exc:
                    logger.debug("Lifecycle post-tool hook failed: %s", exc, exc_info=True)
            elapsed_ms = int((time.perf_counter() - started) * 1000)
            self._record_memory_event(
                "tool_result",
                {
                    "tool_name": tool.name,
                    "arguments": normalized_arguments,
                    "tool_call_id": str(tool_call_id or ""),
                    "success": bool(result.success),
                    "output": result.output,
                    "error": result.error,
                    "status": str(getattr(result.status, "value", "success")),
                    "elapsed_ms": elapsed_ms,
                },
                actor="tool",
                tags=["tool", "success" if result.success else "error", tool.name],
            )
            if tool.name == "command_exec":
                self._record_memory_event(
                    "command_result",
                    {
                        "arguments": normalized_arguments,
                        "success": bool(result.success),
                        "output": result.output,
                        "error": result.error,
                        "status": str(getattr(result.status, "value", "success")),
                    },
                    actor="tool",
                    tags=["command", "success" if result.success else "error"],
                )
            self._record_file_diffs(
                before=before_snapshots,
                tool_name=tool.name,
                arguments=normalized_arguments,
                result=result,
            )
            self._record_operation_usage(tool, result, elapsed_ms)
            return result
        except Exception as e:
            result = ToolResult.fail(f"Tool execution error: {str(e)}")
            if lifecycle_manager and hasattr(lifecycle_manager, "after_tool"):
                try:
                    lifecycle_manager.after_tool(
                        tool.name,
                        normalized_arguments,
                        result,
                        int((time.perf_counter() - started) * 1000),
                        self.context,
                    )
                except Exception as exc:
                    logger.debug("Lifecycle error hook failed: %s", exc, exc_info=True)
            elapsed_ms = int((time.perf_counter() - started) * 1000)
            self._record_memory_event(
                "tool_result",
                {
                    "tool_name": tool.name,
                    "arguments": normalized_arguments,
                    "tool_call_id": str(tool_call_id or ""),
                    "success": False,
                    "output": "",
                    "error": result.error,
                    "status": str(getattr(result.status, "value", "error")),
                    "elapsed_ms": elapsed_ms,
                },
                actor="tool",
                tags=["tool", "error", tool.name],
            )
            self._record_operation_usage(tool, result, elapsed_ms)
            return result
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
