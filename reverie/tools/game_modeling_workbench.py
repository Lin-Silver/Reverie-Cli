"""Reverie-Gamer modeling workbench for Blockbench and Ashfox workflows."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, Optional

from .base import BaseTool, ToolResult
from ..engine import (
    ASHFOX_DEFAULT_ENDPOINT,
    ASHFOX_MCP_SERVER_NAME,
    PRIMITIVE_MODEL_TYPES,
    copy_imported_model,
    create_model_stub,
    create_primitive_model,
    inspect_modeling_workspace,
    materialize_modeling_workspace,
    sync_model_registry,
)


class GameModelingWorkbenchTool(BaseTool):
    name = "game_modeling_workbench"
    description = (
        "Manage Reverie-Gamer's built-in modeling workflow: inspect Blockbench and Ashfox MCP availability, "
        "materialize workspace folders, create `.bbmodel` stubs, import runtime exports, and call the built-in "
        "Ashfox MCP server."
    )

    parameters = {
        "type": "object",
        "properties": {
            "action": {
                "type": "string",
                "enum": [
                    "inspect_stack",
                    "setup_workspace",
                    "sync_registry",
                    "create_model_stub",
                    "generate_primitive",
                    "import_export",
                    "list_ashfox_tools",
                    "ashfox_call",
                ],
                "description": "Modeling workbench action",
            },
            "output_dir": {"type": "string", "description": "Project root for the modeling workspace"},
            "model_name": {"type": "string", "description": "Model name for stub creation"},
            "relative_path": {"type": "string", "description": "Optional explicit path for the created `.bbmodel`"},
            "source_path": {"type": "string", "description": "Runtime export to import into `assets/models/runtime`"},
            "source_model_path": {"type": "string", "description": "Optional source authoring file to copy into `assets/models/source`"},
            "preview_path": {"type": "string", "description": "Optional preview image path for the model"},
            "dest_name": {"type": "string", "description": "Optional target stem for imported files"},
            "endpoint": {"type": "string", "description": "Ashfox MCP endpoint override for status text"},
            "tool_name": {"type": "string", "description": "Ashfox tool name for `ashfox_call`"},
            "arguments": {"type": "object", "description": "Arguments passed to the Ashfox tool"},
            "primitive": {
                "type": "string",
                "enum": list(PRIMITIVE_MODEL_TYPES),
                "description": "Built-in primitive mesh type for `generate_primitive`",
            },
            "size": {"type": "number", "description": "Fallback size for the generated primitive"},
            "width": {"type": "number", "description": "Optional width override for the primitive"},
            "height": {"type": "number", "description": "Optional height override for the primitive"},
            "depth": {"type": "number", "description": "Optional depth override for the primitive"},
            "radius": {"type": "number", "description": "Optional radius override for sphere generation"},
            "segments": {"type": "integer", "description": "Optional segment count for sphere generation"},
            "create_preview": {"type": "boolean", "description": "Whether to generate a preview image for the primitive"},
            "overwrite": {"type": "boolean", "description": "Overwrite generated or imported files"},
        },
        "required": ["action"],
    }

    def __init__(self, context: Optional[Dict] = None):
        super().__init__(context)
        self.project_root = Path(context.get("project_root")) if context and context.get("project_root") else Path.cwd()

    def execute(self, **kwargs) -> ToolResult:
        action = kwargs.get("action")
        project_root = self._resolve_output_dir(kwargs)

        try:
            if action == "inspect_stack":
                return self._inspect_stack(project_root)
            if action == "setup_workspace":
                return self._setup_workspace(project_root, overwrite=bool(kwargs.get("overwrite", False)))
            if action == "sync_registry":
                return self._sync_registry(project_root)
            if action == "create_model_stub":
                return self._create_stub(project_root, kwargs)
            if action == "generate_primitive":
                return self._generate_primitive(project_root, kwargs)
            if action == "import_export":
                return self._import_export(project_root, kwargs)
            if action == "list_ashfox_tools":
                return self._list_ashfox_tools()
            if action == "ashfox_call":
                tool_name = str(kwargs.get("tool_name") or "").strip()
                if not tool_name:
                    return ToolResult.fail("tool_name is required for ashfox_call")
                return self._ashfox_call(tool_name, kwargs.get("arguments") or {})
            return ToolResult.fail(f"Unknown action: {action}")
        except Exception as exc:
            return ToolResult.fail(f"Error executing {action}: {str(exc)}")

    def _resolve_output_dir(self, kwargs: Dict[str, Any]) -> Path:
        return self.resolve_workspace_path(
            kwargs.get("output_dir", "."),
            purpose="resolve modeling workspace root",
        )

    def _resolve_project_path(self, project_root: Path, raw_path: str, *, purpose: str) -> Path:
        candidate = Path(str(raw_path))
        if not candidate.is_absolute():
            candidate = (project_root / candidate).resolve()
        return self.ensure_workspace_path(candidate, purpose=purpose)

    def _ashfox_server_name(self) -> str:
        config_manager = self.context.get("config_manager")
        if config_manager:
            try:
                config = config_manager.load()
                gamer_mode = getattr(config, "gamer_mode", {}) or {}
                server_name = str(gamer_mode.get("ashfox_server_name", "") or "").strip()
                if server_name:
                    return server_name
            except Exception:
                pass
        return ASHFOX_MCP_SERVER_NAME

    def _ashfox_runtime(self):
        return self.context.get("mcp_runtime")

    def _ashfox_tool_definitions(self) -> list[Dict[str, Any]]:
        runtime = self._ashfox_runtime()
        if runtime is None:
            raise RuntimeError("Ashfox MCP runtime is not available in the current session.")
        server_name = self._ashfox_server_name()
        definitions = runtime.get_tool_definitions(force_refresh=False)
        return [
            item
            for item in definitions
            if isinstance(item, dict) and str(item.get("server_name", "") or "").strip().lower() == server_name.lower()
        ]

    def _inspect_stack(self, project_root: Path) -> ToolResult:
        info = inspect_modeling_workspace(project_root)
        stack = info.get("stack", {})
        blockbench = stack.get("blockbench", {})
        ashfox = stack.get("ashfox", {})

        discovered_tools = 0
        try:
            discovered_tools = len(self._ashfox_tool_definitions())
        except Exception:
            discovered_tools = int(ashfox.get("tool_count", 0) or 0)

        output = (
            f"Modeling workspace: {project_root}\n"
            f"Stack ready: {info.get('stack_ready', False)}\n"
            f"Pipeline manifest: {'present' if info.get('pipeline_exists') else 'missing'}\n"
            f"Registry: {'present' if info.get('registry_exists') else 'missing'}\n"
            f"Source models: {info.get('source_model_count', 0)} | Runtime models: {info.get('runtime_model_count', 0)} | Previews: {info.get('preview_count', 0)}\n"
            f"Blockbench desktop: {'detected' if blockbench.get('installed') else 'not detected'}\n"
            f"Ashfox MCP: {'reachable' if ashfox.get('reachable') else 'offline'}\n"
            f"Ashfox endpoint: {ashfox.get('endpoint', ASHFOX_DEFAULT_ENDPOINT)}\n"
            f"Ashfox server name: {ashfox.get('server_name', self._ashfox_server_name())}\n"
            f"Discovered Ashfox tools: {discovered_tools}"
        )
        if ashfox.get("error"):
            output += f"\nAshfox status detail: {ashfox['error']}"
        return ToolResult.ok(output, info)

    def _setup_workspace(self, project_root: Path, *, overwrite: bool) -> ToolResult:
        result = materialize_modeling_workspace(project_root, overwrite=overwrite)
        output = (
            f"Prepared Reverie-Gamer modeling workspace in {project_root}\n"
            f"Directories created: {len(result['directories'])}\n"
            f"Files written: {len(result['files'])}\n"
            f"Blockbench desktop: {'detected' if result['stack']['blockbench']['installed'] else 'manual install required'}\n"
            f"Ashfox MCP: {'reachable' if result['stack']['ashfox']['reachable'] else 'launch Blockbench with the Ashfox plugin'}"
        )
        return ToolResult.ok(output, result)

    def _sync_registry(self, project_root: Path) -> ToolResult:
        result = sync_model_registry(project_root, overwrite=True)
        counts = result["registry"].get("counts", {})
        output = (
            f"Synchronized model registry for {project_root}\n"
            f"Registry path: {result['registry_path']}\n"
            f"Models: {counts.get('models', 0)} | Source files: {counts.get('source_models', 0)} | Runtime files: {counts.get('runtime_models', 0)}"
        )
        return ToolResult.ok(output, result)

    def _create_stub(self, project_root: Path, kwargs: Dict[str, Any]) -> ToolResult:
        model_name = str(kwargs.get("model_name") or "").strip()
        if not model_name:
            return ToolResult.fail("model_name is required for create_model_stub")
        relative_path = kwargs.get("relative_path")
        if relative_path:
            relative_path = str(self._resolve_project_path(project_root, str(relative_path), purpose="resolve model stub path"))
        target = create_model_stub(
            project_root,
            model_name,
            relative_path=relative_path,
            overwrite=bool(kwargs.get("overwrite", False)),
        )
        registry = sync_model_registry(project_root, overwrite=True)
        output = (
            f"Created Blockbench model stub for '{model_name}'\n"
            f"Path: {target}\n"
            f"Registry synced: {registry['registry_path']}"
        )
        return ToolResult.ok(output, {"stub_path": str(target), "registry": registry})

    def _generate_primitive(self, project_root: Path, kwargs: Dict[str, Any]) -> ToolResult:
        model_name = str(kwargs.get("model_name") or "").strip()
        if not model_name:
            return ToolResult.fail("model_name is required for generate_primitive")
        primitive = str(kwargs.get("primitive") or "box").strip().lower()
        if primitive not in PRIMITIVE_MODEL_TYPES:
            return ToolResult.fail(f"primitive must be one of: {', '.join(PRIMITIVE_MODEL_TYPES)}")
        generated = create_primitive_model(
            project_root,
            model_name,
            primitive=primitive,
            size=float(kwargs.get("size", 1.0) or 1.0),
            width=kwargs.get("width"),
            height=kwargs.get("height"),
            depth=kwargs.get("depth"),
            radius=kwargs.get("radius"),
            segments=int(kwargs.get("segments", 12) or 12),
            overwrite=bool(kwargs.get("overwrite", False)),
            create_preview=bool(kwargs.get("create_preview", True)),
        )
        output = (
            f"Generated primitive runtime model '{model_name}'\n"
            f"Primitive: {primitive}\n"
            f"Runtime target: {generated['runtime_path']}\n"
            f"Triangles: {generated['mesh_summary']['triangle_count']} | Vertices: {generated['mesh_summary']['vertex_count']}\n"
            f"Registry synced: {generated['registry']['registry_path']}"
        )
        if generated.get("preview_path"):
            output += f"\nPreview image: {generated['preview_path']}"
        return ToolResult.ok(output, generated)

    def _import_export(self, project_root: Path, kwargs: Dict[str, Any]) -> ToolResult:
        source_path = str(kwargs.get("source_path") or "").strip()
        if not source_path:
            return ToolResult.fail("source_path is required for import_export")
        runtime_source = str(self._resolve_project_path(project_root, source_path, purpose="resolve runtime model import"))
        source_model_path = kwargs.get("source_model_path")
        preview_path = kwargs.get("preview_path")
        copied = copy_imported_model(
            project_root,
            runtime_source,
            source_model=(
                str(self._resolve_project_path(project_root, str(source_model_path), purpose="resolve source model import"))
                if source_model_path
                else None
            ),
            preview_image=(
                str(self._resolve_project_path(project_root, str(preview_path), purpose="resolve model preview import"))
                if preview_path
                else None
            ),
            dest_name=kwargs.get("dest_name"),
            overwrite=bool(kwargs.get("overwrite", False)),
        )
        registry = sync_model_registry(project_root, overwrite=True)
        output = (
            f"Imported runtime model into {project_root}\n"
            f"Runtime target: {copied.get('runtime_path', '')}\n"
            f"Registry synced: {registry['registry_path']}"
        )
        if copied.get("source_path"):
            output += f"\nSource model: {copied['source_path']}"
        if copied.get("preview_path"):
            output += f"\nPreview image: {copied['preview_path']}"
        return ToolResult.ok(output, {"copied": copied, "registry": registry})

    def _list_ashfox_tools(self) -> ToolResult:
        definitions = self._ashfox_tool_definitions()
        server_name = self._ashfox_server_name()
        output = f"Ashfox MCP tools via server '{server_name}'\nCount: {len(definitions)}"
        for item in definitions[:60]:
            output += f"\n- {item.get('tool_name', item.get('name', ''))}"
        return ToolResult.ok(output, {"server_name": server_name, "tools": definitions})

    def _ashfox_call(self, tool_name: str, arguments: Dict[str, Any]) -> ToolResult:
        runtime = self._ashfox_runtime()
        if runtime is None:
            return ToolResult.fail("Ashfox MCP runtime is not available in the current session.")

        server_name = self._ashfox_server_name()
        response = runtime.call_tool(server_name, tool_name, arguments or {})
        output = str(response.get("output", "") or "").strip() or f"Ashfox tool call succeeded: {tool_name}"
        payload = {
            "server_name": server_name,
            "tool_name": tool_name,
            "arguments": arguments or {},
            "result": response.get("result", {}),
            "data": response.get("data", {}),
        }
        if response.get("success", True):
            return ToolResult.ok(output, payload)
        return ToolResult.fail(output)

    def get_execution_message(self, **kwargs) -> str:
        return f"Modeling workbench: {kwargs.get('action', 'unknown')}"
