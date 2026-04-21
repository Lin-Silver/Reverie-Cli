"""Built-in Blender modeling workbench."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, Optional

from .base import BaseTool, ToolResult
from ..engine import (
    BLENDER_EXPORT_FORMATS,
    BLENDER_MODEL_PRESETS,
    create_blender_authoring_job,
    create_blender_model,
    detect_blender_installation,
    inspect_blender_modeling_workspace,
    materialize_blender_workspace,
    run_blender_script,
    sync_model_registry,
    validate_blender_script_text,
)


class BlenderModelingWorkbenchTool(BaseTool):
    """Use Blender directly from Reverie without an external MCP server."""

    name = "blender_modeling_workbench"
    aliases = ("blender_workbench", "blender_modeling", "blender")
    search_hint = "create inspect and export Blender models with built-in bpy scripts"
    tool_category = "game-modeling"
    tool_tags = ("blender", "bpy", "3d", "model", "glb", "gltf", "render", "asset")
    destructive = False
    max_result_chars = 40_000
    description = (
        "Built-in Blender authoring workflow. Detect Blender, prepare the Reverie modeling workspace, "
        "generate polished procedural Blender scripts from a modeling brief, run workspace-local bpy scripts "
        "in Blender background mode, export `.blend`/`.glb`/`.gltf`, render previews, and sync the model registry. "
        "This is first-party Reverie tooling, not an external MCP or Skill dependency."
    )

    parameters = {
        "type": "object",
        "properties": {
            "action": {
                "type": "string",
                "enum": [
                    "inspect_stack",
                    "setup_workspace",
                    "create_model",
                    "generate_script",
                    "run_script",
                    "validate_script",
                    "sync_registry",
                ],
                "description": "Blender modeling action",
            },
            "output_dir": {"type": "string", "description": "Project root for the modeling workspace"},
            "brief": {"type": "string", "description": "Natural-language model brief or art direction"},
            "model_name": {"type": "string", "description": "Stable model/source/export name"},
            "preset": {
                "type": "string",
                "enum": list(BLENDER_MODEL_PRESETS),
                "description": "High-level built-in Blender authoring preset",
            },
            "style": {"type": "string", "description": "Visual style hint such as stylized, fantasy, sci_fi, natural"},
            "export_format": {
                "type": "string",
                "enum": list(BLENDER_EXPORT_FORMATS),
                "description": "Runtime export format. `glb` is preferred for games.",
            },
            "script_path": {"type": "string", "description": "Workspace-local Blender Python script path for run/validate"},
            "blender_path": {"type": "string", "description": "Optional explicit Blender executable path"},
            "render_preview": {"type": "boolean", "description": "Render a preview PNG when running Blender"},
            "run_blender": {"type": "boolean", "description": "Execute Blender after generating the script"},
            "overwrite": {"type": "boolean", "description": "Overwrite existing generated plan/script/output files"},
            "timeout_seconds": {"type": "integer", "description": "Maximum Blender execution time"},
            "allow_unsafe_python": {"type": "boolean", "description": "Bypass conservative script blocklist for trusted scripts"},
        },
        "required": ["action"],
    }

    def __init__(self, context: Optional[Dict] = None):
        super().__init__(context)
        self.project_root = Path(context.get("project_root")) if context and context.get("project_root") else Path.cwd()

    def execute(self, **kwargs) -> ToolResult:
        action = str(kwargs.get("action") or "").strip().lower()
        project_root = self._resolve_output_dir(kwargs)

        try:
            if action == "inspect_stack":
                return self._inspect_stack(project_root, kwargs)
            if action == "setup_workspace":
                return self._setup_workspace(project_root, kwargs)
            if action == "create_model":
                return self._create_model(project_root, kwargs)
            if action == "generate_script":
                return self._generate_script(project_root, kwargs)
            if action == "run_script":
                return self._run_script(project_root, kwargs)
            if action == "validate_script":
                return self._validate_script(project_root, kwargs)
            if action == "sync_registry":
                return self._sync_registry(project_root)
            return ToolResult.fail(f"Unknown action: {action}")
        except Exception as exc:
            return ToolResult.fail(f"Error executing {action}: {str(exc)}")

    def _resolve_output_dir(self, kwargs: Dict[str, Any]) -> Path:
        return self.resolve_workspace_path(
            kwargs.get("output_dir", "."),
            purpose="resolve Blender modeling workspace root",
        )

    def _resolve_project_path(self, project_root: Path, raw_path: Any, *, purpose: str) -> Path:
        if not str(raw_path or "").strip():
            raise ValueError("path is required")
        candidate = Path(str(raw_path))
        if not candidate.is_absolute():
            candidate = (project_root / candidate).resolve()
        return self.ensure_workspace_path(candidate, purpose=purpose)

    def _config_blender_path(self) -> str:
        config_manager = self.context.get("config_manager")
        if config_manager:
            try:
                config = config_manager.load()
                gamer_mode = getattr(config, "gamer_mode", {}) or {}
                blender_path = str(gamer_mode.get("blender_path", "") or "").strip()
                if blender_path:
                    return blender_path
            except Exception:
                pass
        return ""

    def _blender_path(self, kwargs: Dict[str, Any]) -> str:
        return str(kwargs.get("blender_path") or self._config_blender_path() or "").strip()

    def _ensure_blender_path(self, kwargs: Dict[str, Any], *, deploy: bool) -> str:
        """Resolve Blender, optionally asking the official runtime plugin to deploy it."""
        explicit = self._blender_path(kwargs)
        if explicit:
            return explicit

        blender = detect_blender_installation("")
        if blender.get("available") and blender.get("executable_path"):
            return str(blender.get("executable_path") or "")

        if not deploy:
            return ""

        manager = self.context.get("runtime_plugin_manager")
        if manager is None:
            return ""

        try:
            result = manager.deploy_sdk_package("blender", overwrite=False)
        except Exception:
            return ""
        if not result.get("success", False):
            return ""
        status = result.get("status", {}) if isinstance(result.get("status"), dict) else {}
        entry_path = status.get("entry_path")
        return str(entry_path) if entry_path else ""

    def _inspect_stack(self, project_root: Path, kwargs: Dict[str, Any]) -> ToolResult:
        info = inspect_blender_modeling_workspace(project_root, blender_path=self._blender_path(kwargs))
        blender = info.get("blender", {})
        output = (
            f"Blender modeling workspace: {project_root}\n"
            f"Blender: {'detected' if blender.get('available') else 'not detected'}\n"
            f"Executable: {blender.get('executable_path') or '(none)'}\n"
            f"Version: {blender.get('version') or '(unknown)'}\n"
            f"Pipeline manifest: {'present' if info.get('pipeline_exists') else 'missing'}\n"
            f"Registry: {'present' if info.get('registry_exists') else 'missing'}\n"
            f"Source models: {info.get('source_model_count', 0)} | Runtime models: {info.get('runtime_model_count', 0)} | Previews: {info.get('preview_count', 0)}\n"
            f"Generated scripts: {info.get('script_count', 0)} | Model plans: {info.get('plan_count', 0)}"
        )
        if not blender.get("available"):
            output += f"\nInstall hint: {blender.get('install_hint', '')}"
        return ToolResult.ok(output, info)

    def _setup_workspace(self, project_root: Path, kwargs: Dict[str, Any]) -> ToolResult:
        result = materialize_blender_workspace(project_root, overwrite=bool(kwargs.get("overwrite", False)))
        blender = detect_blender_installation(self._ensure_blender_path(kwargs, deploy=True))
        result["blender"] = blender
        output = (
            f"Prepared Blender modeling workspace in {project_root}\n"
            f"Directories created: {len(result.get('directories', []))}\n"
            f"Files written: {len(result.get('files', []))}\n"
            f"Blender: {'detected' if blender.get('available') else 'manual install or REVERIE_BLENDER_PATH required'}"
        )
        return ToolResult.ok(output, result)

    def _model_kwargs(self, kwargs: Dict[str, Any]) -> Dict[str, Any]:
        model_name = str(kwargs.get("model_name") or "").strip()
        if not model_name:
            return {"error": "model_name is required"}
        brief = str(kwargs.get("brief") or "").strip() or model_name
        return {
            "brief": brief,
            "model_name": model_name,
            "preset": str(kwargs.get("preset") or "auto").strip().lower(),
            "style": str(kwargs.get("style") or "stylized").strip(),
            "export_format": str(kwargs.get("export_format") or "glb").strip().lower(),
            "render_preview": bool(kwargs.get("render_preview", True)),
            "overwrite": bool(kwargs.get("overwrite", False)),
        }

    def _generate_script(self, project_root: Path, kwargs: Dict[str, Any]) -> ToolResult:
        params = self._model_kwargs(kwargs)
        if params.get("error"):
            return ToolResult.fail(str(params["error"]))
        job = create_blender_authoring_job(project_root, **params)
        output = (
            f"Generated Blender authoring plan for '{job['spec']['model_name']}'\n"
            f"Preset: {job['spec']['preset']} | Style: {job['spec']['style']}\n"
            f"Plan: {job['relative_paths']['plan']}\n"
            f"Script: {job['relative_paths']['script']}\n"
            f"Planned runtime export: {job['relative_paths']['runtime']}"
        )
        return ToolResult.ok(output, job)

    def _create_model(self, project_root: Path, kwargs: Dict[str, Any]) -> ToolResult:
        params = self._model_kwargs(kwargs)
        if params.get("error"):
            return ToolResult.fail(str(params["error"]))
        result = create_blender_model(
            project_root,
            **params,
            run_blender=bool(kwargs.get("run_blender", True)),
            blender_path=self._ensure_blender_path(kwargs, deploy=bool(kwargs.get("run_blender", True))),
            timeout_seconds=int(kwargs.get("timeout_seconds", 240) or 240),
        )
        run_result = result.get("run", {})
        spec = result.get("spec", {})
        output = (
            f"Created Blender modeling job for '{spec.get('model_name', '')}'\n"
            f"Preset: {spec.get('preset', '')} | Style: {spec.get('style', '')}\n"
            f"Script: {result['relative_paths']['script']}\n"
            f"Blend source: {result['relative_paths']['blend']}\n"
            f"Runtime export: {result['relative_paths']['runtime']}\n"
            f"Preview: {result['relative_paths']['preview']}\n"
            f"Blender run: {'succeeded' if run_result.get('success') else ('skipped' if run_result.get('skipped') else 'not completed')}"
        )
        if run_result.get("stderr") and not run_result.get("success"):
            output += f"\nBlender detail: {str(run_result.get('stderr'))[:600]}"
        if run_result.get("success"):
            output += f"\nRegistry synced: {result['registry']['registry_path']}"
            return ToolResult.ok(output, result)
        if run_result.get("skipped"):
            return ToolResult.ok(output, result)
        return ToolResult.partial(output, str(run_result.get("stderr") or "Blender execution did not complete."))

    def _run_script(self, project_root: Path, kwargs: Dict[str, Any]) -> ToolResult:
        raw_path = kwargs.get("script_path")
        if not str(raw_path or "").strip():
            return ToolResult.fail("script_path is required for run_script")
        script_path = self._resolve_project_path(project_root, raw_path, purpose="resolve Blender script")
        result = run_blender_script(
            project_root,
            script_path,
            blender_path=self._ensure_blender_path(kwargs, deploy=True),
            timeout_seconds=int(kwargs.get("timeout_seconds", 240) or 240),
            allow_unsafe_python=bool(kwargs.get("allow_unsafe_python", False)),
        )
        registry = sync_model_registry(project_root, overwrite=True)
        output = (
            f"Ran Blender script: {script_path}\n"
            f"Exit code: {result.get('exit_code')}\n"
            f"Registry synced: {registry['registry_path']}"
        )
        if result.get("success"):
            return ToolResult.ok(output, {"run": result, "registry": registry})
        detail = str(result.get("stderr") or result.get("stdout") or "Blender script failed.")
        return ToolResult.partial(output, detail)

    def _validate_script(self, project_root: Path, kwargs: Dict[str, Any]) -> ToolResult:
        raw_path = kwargs.get("script_path")
        if not str(raw_path or "").strip():
            return ToolResult.fail("script_path is required for validate_script")
        script_path = self._resolve_project_path(project_root, raw_path, purpose="validate Blender script")
        ok, issues = validate_blender_script_text(script_path.read_text(encoding="utf-8"))
        output = f"Blender script validation: {'passed' if ok else 'blocked'}\nPath: {script_path}"
        if issues:
            output += "\nIssues:\n" + "\n".join(f"- {issue}" for issue in issues)
        return ToolResult.ok(output, {"ok": ok, "issues": issues, "script_path": str(script_path)}) if ok else ToolResult.fail(output)

    def _sync_registry(self, project_root: Path) -> ToolResult:
        result = sync_model_registry(project_root, overwrite=True)
        counts = result["registry"].get("counts", {})
        output = (
            f"Synchronized model registry for {project_root}\n"
            f"Registry path: {result['registry_path']}\n"
            f"Models: {counts.get('models', 0)} | Source files: {counts.get('source_models', 0)} | Runtime files: {counts.get('runtime_models', 0)}"
        )
        return ToolResult.ok(output, result)

    def get_execution_message(self, **kwargs) -> str:
        return f"Blender modeling workbench: {kwargs.get('action', 'unknown')}"
