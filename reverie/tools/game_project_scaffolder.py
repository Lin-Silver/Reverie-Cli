"""
Game Project Scaffolder Tool.

Provides engine-aware structure planning so Reverie-Gamer can turn a blueprint
into a practical project foundation for 2D, 2.5D, and 3D games.
"""

from __future__ import annotations

from typing import Optional, Dict, Any, List
from pathlib import Path
import json

from .base import BaseTool, ToolResult
from ..engine import canonical_engine_name, create_project_skeleton, is_builtin_engine_name
from ..gamer.prompt_compiler import compile_game_prompt
from ..gamer.production_plan import build_blueprint_from_request
from ..gamer.runtime_registry import select_runtime_profile
from ..gamer.vertical_slice_builder import build_vertical_slice_project


class GameProjectScaffolderTool(BaseTool):
    name = "game_project_scaffolder"
    aliases = ("game_scaffold",)
    search_hint = "scaffold engine aware game project foundations"
    tool_category = "game-scaffold"
    tool_tags = ("game", "scaffold", "project", "engine", "pipeline", "module")
    description = (
        "Plan and scaffold engine-aware game project foundations, module maps, "
        "and content pipelines for 2D, 2.5D, and 3D projects."
    )

    parameters = {
        "type": "object",
        "properties": {
            "action": {
                "type": "string",
                "enum": [
                    "plan_structure",
                    "create_foundation",
                    "create_from_request",
                    "generate_vertical_slice",
                    "generate_module_map",
                    "generate_content_pipeline",
                ],
                "description": "Scaffolding action",
            },
            "output_dir": {
                "type": "string",
                "description": "Target project directory (default: .)",
            },
            "output_path": {
                "type": "string",
                "description": "Optional path for generated docs",
            },
            "blueprint_path": {
                "type": "string",
                "description": "Optional blueprint path to read project context from",
            },
            "request_path": {
                "type": "string",
                "description": "Optional compiled request path (default: artifacts/game_request.json)",
            },
            "prompt": {
                "type": "string",
                "description": "Single prompt used to compile a request when no request artifact exists",
            },
            "project_name": {
                "type": "string",
                "description": "Project name",
            },
            "engine": {
                "type": "string",
                "description": "Engine or framework such as custom, godot, unity, unreal, phaser, pygame",
            },
            "dimension": {
                "type": "string",
                "description": "2D, 2.5D, or 3D",
            },
            "language": {
                "type": "string",
                "description": "Primary language for the scaffolding output",
            },
            "include_tests": {
                "type": "boolean",
                "description": "Include testing folders and starter files",
            },
            "include_tools": {
                "type": "boolean",
                "description": "Include tooling and playtest support folders",
            },
            "overwrite": {
                "type": "boolean",
                "description": "Overwrite starter files if they already exist",
            },
            "requested_runtime": {
                "type": "string",
                "description": "Optional explicit runtime request such as reverie_engine or godot",
            },
            "existing_runtime": {
                "type": "string",
                "description": "Optional existing runtime to preserve",
            },
            "data": {
                "type": "object",
                "description": "Optional override data for scaffolding outputs",
            },
        },
        "required": ["action"],
    }

    def __init__(self, context: Optional[Dict] = None):
        super().__init__(context)
        self.project_root = Path(context.get("project_root")) if context and context.get("project_root") else Path.cwd()

    def execute(self, **kwargs) -> ToolResult:
        action = kwargs.get("action")
        output_dir = self._resolve_path(kwargs.get("output_dir", "."))
        request_path = self._resolve_path(kwargs.get("request_path", str(output_dir / "artifacts/game_request.json")))

        try:
            if action == "plan_structure":
                return self._plan_structure(output_dir, kwargs)
            if action == "create_foundation":
                return self._create_foundation(output_dir, kwargs)
            if action == "create_from_request":
                return self._create_from_request(output_dir, request_path, kwargs)
            if action == "generate_vertical_slice":
                return self._generate_vertical_slice(output_dir, request_path, kwargs)
            if action == "generate_module_map":
                output_path = self._resolve_path(kwargs.get("output_path", str(output_dir / "artifacts/module_map.json")))
                return self._generate_module_map(output_dir, output_path, kwargs)
            if action == "generate_content_pipeline":
                output_path = self._resolve_path(
                    kwargs.get("output_path", str(output_dir / "artifacts/content_pipeline.md"))
                )
                return self._generate_content_pipeline(output_dir, output_path, kwargs)
            return ToolResult.fail(f"Unknown action: {action}")
        except Exception as exc:
            return ToolResult.fail(f"Error executing {action}: {str(exc)}")

    def _plan_structure(self, output_dir: Path, kwargs: Dict[str, Any]) -> ToolResult:
        profile = self._build_profile(kwargs)
        structure = self._recommended_structure(profile, kwargs)
        output = (
            f"Project structure plan for {profile['project_name']}\n"
            f"Engine: {profile['engine']} | Dimension: {profile['dimension']} | Language: {profile['language']}\n\n"
        )
        for item in structure:
            output += f"- {item}\n"
        return ToolResult.ok(output, {"profile": profile, "structure": structure})

    def _create_foundation(self, output_dir: Path, kwargs: Dict[str, Any]) -> ToolResult:
        profile = self._build_profile(kwargs)
        structure = self._recommended_structure(profile, kwargs)
        overwrite = kwargs.get("overwrite", False)

        created_paths: List[str] = []
        for relative in structure:
            target = output_dir / relative
            target.mkdir(parents=True, exist_ok=True)
            created_paths.append(str(target.relative_to(self.project_root)))

        starter_files = self._starter_files(profile, output_dir, kwargs)
        written = []
        for path, content in starter_files.items():
            if path.exists() and not overwrite:
                continue
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(content, encoding="utf-8")
            written.append(str(path.relative_to(self.project_root)))

        if is_builtin_engine_name(profile["engine"]):
            engine_seed = create_project_skeleton(
                output_dir,
                project_name=profile["project_name"],
                dimension=profile["dimension"],
                overwrite=overwrite,
            )
            created_paths.extend(engine_seed["directories"])
            written.extend(engine_seed["files"])

        output = (
            f"Created project foundation in {output_dir}\n"
            f"Directories created: {len(created_paths)}\n"
            f"Starter files written: {len(written)}"
        )
        return ToolResult.ok(
            output,
            {
                "profile": profile,
                "directories": created_paths,
                "files": written,
            },
        )

    def _create_from_request(self, output_dir: Path, request_path: Path, kwargs: Dict[str, Any]) -> ToolResult:
        game_request = self._load_or_compile_request(request_path, kwargs, output_dir=output_dir)
        runtime_selection = select_runtime_profile(
            game_request,
            project_root=output_dir,
            requested_runtime=kwargs.get("requested_runtime", ""),
            existing_runtime=kwargs.get("existing_runtime", ""),
        )
        blueprint = build_blueprint_from_request(
            game_request,
            runtime_profile=runtime_selection["profile"],
            overrides=kwargs.get("data") or {},
        )
        merged_kwargs = dict(kwargs)
        merged_kwargs["project_name"] = blueprint.get("meta", {}).get("project_name", kwargs.get("project_name", "Untitled Game"))
        merged_kwargs["engine"] = runtime_selection["selected_runtime"]
        merged_kwargs["dimension"] = blueprint.get("meta", {}).get("dimension", kwargs.get("dimension", "3D"))
        foundation = self._create_foundation(output_dir, merged_kwargs)
        if not foundation.success:
            return foundation

        blueprint_path = self._resolve_path(kwargs.get("blueprint_path", str(output_dir / "artifacts/game_blueprint.json")))
        blueprint_path.parent.mkdir(parents=True, exist_ok=True)
        blueprint_path.write_text(json.dumps(blueprint, indent=2, ensure_ascii=False), encoding="utf-8")
        request_path.parent.mkdir(parents=True, exist_ok=True)
        request_path.write_text(json.dumps(game_request, indent=2, ensure_ascii=False), encoding="utf-8")

        output = (
            f"Created request-backed foundation in {output_dir}\n"
            f"Runtime: {runtime_selection['selected_runtime']}\n"
            f"Scope: {game_request['production']['delivery_scope']}\n"
            f"Blueprint: {blueprint_path}"
        )
        data = dict(foundation.data)
        data.update(
            {
                "request_path": str(request_path.relative_to(self.project_root)),
                "blueprint_path": str(blueprint_path.relative_to(self.project_root)),
                "runtime": runtime_selection["selected_runtime"],
            }
        )
        return ToolResult.ok(output, data)

    def _generate_vertical_slice(self, output_dir: Path, request_path: Path, kwargs: Dict[str, Any]) -> ToolResult:
        result = build_vertical_slice_project(
            output_dir,
            prompt=self._resolve_prompt(kwargs),
            project_name=kwargs.get("project_name", ""),
            requested_runtime=kwargs.get("requested_runtime", ""),
            existing_runtime=kwargs.get("existing_runtime", ""),
            overwrite=kwargs.get("overwrite", False),
            app_root=self.project_root,
        )
        verification = result.get("verification", {})
        output = (
            f"Generated vertical slice in {output_dir}\n"
            f"Runtime: {result['runtime']}\n"
            f"Artifacts: {len(result.get('written_artifacts', []))}\n"
            f"Runtime files: {len(result.get('runtime_files', []))}\n"
            f"Verification: {'ok' if verification.get('valid', False) else 'needs review'}\n"
            f"Slice score: {result.get('slice_score', {}).get('score', 0)}/100"
        )
        return ToolResult.ok(
            output,
            {
                "project_root": result["project_root"],
                "runtime": result["runtime"],
                "request_path": str(request_path.relative_to(self.project_root)),
                "runtime_files": result.get("runtime_files", []),
                "written_artifacts": result.get("written_artifacts", []),
                "verification": verification,
                "slice_score": result.get("slice_score", {}),
                "task_graph": result.get("task_graph", {}),
                "content_expansion": result.get("content_expansion", {}),
                "asset_pipeline": result.get("asset_pipeline", {}),
                "expansion_backlog": result.get("expansion_backlog", {}),
                "resume_state": result.get("resume_state", {}),
                "modeling_workspace": result.get("modeling_workspace", {}),
            },
        )

    def _generate_module_map(self, output_dir: Path, output_path: Path, kwargs: Dict[str, Any]) -> ToolResult:
        profile = self._build_profile(kwargs)
        blueprint = self._load_blueprint(kwargs.get("blueprint_path"))
        systems = blueprint.get("gameplay_blueprint", {}).get("systems", {})

        module_map = {
            "project": profile["project_name"],
            "runtime": {
                "engine": profile["engine"],
                "dimension": profile["dimension"],
                "language": profile["language"],
            },
            "modules": {
                "runtime_core": ["bootstrap", "scene_flow", "state_store", "save_system"],
                "gameplay": [spec.get("name", key) for key, spec in systems.items()] or ["combat", "progression", "content_delivery"],
                "content": ["levels", "quests", "dialogue", "items", "encounters"],
                "presentation": ["camera", "ui", "vfx", "audio", "animation"],
                "quality": ["tests", "smoke", "telemetry", "playtest"],
            },
        }

        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(json.dumps(module_map, indent=2, ensure_ascii=False), encoding="utf-8")
        return ToolResult.ok(
            f"Generated module map at {output_path}",
            {
                "output_path": str(output_path.relative_to(self.project_root)),
                "module_map": module_map,
            },
        )

    def _generate_content_pipeline(self, output_dir: Path, output_path: Path, kwargs: Dict[str, Any]) -> ToolResult:
        profile = self._build_profile(kwargs)
        blueprint = self._load_blueprint(kwargs.get("blueprint_path"))
        content_strategy = blueprint.get("content_strategy", {})

        lines = [
            f"# Content Pipeline for {profile['project_name']}",
            "",
            f"Engine: {profile['engine']}",
            f"Dimension: {profile['dimension']}",
            "",
            "## Source of Truth",
            "- `design/` owns intent, references, and content specs.",
            "- `assets/raw/` stores source art, audio, and high-resolution working files.",
            "- `assets/processed/` stores optimized runtime exports.",
            "- `data/` stores gameplay, progression, encounter, and localization data.",
            "",
            "## Import Stages",
            "- Author content against naming conventions and budget tags.",
            "- Validate naming and dependency usage before integrating assets.",
            "- Convert assets into runtime-friendly formats and atlases.",
            "- Register content in manifests and data tables.",
            "- Run smoke and playtest gates before promoting to release content.",
            "",
            "## Recommended Runtime Sets",
        ]

        for reward_type in content_strategy.get("reward_types", ["power", "currency", "narrative"]):
            lines.append(f"- reward/{reward_type}")
        for encounter in content_strategy.get("encounter_families", ["trash", "elite", "boss"]):
            lines.append(f"- encounter/{encounter}")

        lines.extend(
            [
                "",
                "## Review Gates",
                "- Style review: silhouette, readability, and thematic fit",
                "- Technical review: memory footprint, import settings, dependency health",
                "- Gameplay review: communicates affordances and reward clarity",
                "- Release review: coverage in test plans, telemetry, and content manifests",
                "",
                f"Output root: `{output_dir}`",
                "",
            ]
        )

        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text("\n".join(lines), encoding="utf-8")
        return ToolResult.ok(
            f"Generated content pipeline at {output_path}",
            {
                "output_path": str(output_path.relative_to(self.project_root)),
                "engine": profile["engine"],
            },
        )

    def _build_profile(self, kwargs: Dict[str, Any]) -> Dict[str, Any]:
        blueprint = self._load_blueprint(kwargs.get("blueprint_path"))
        meta = blueprint.get("meta", {})

        engine = canonical_engine_name(kwargs.get("engine") or meta.get("target_engine", "reverie_engine"))
        dimension = kwargs.get("dimension") or meta.get("dimension", "2D")
        language = kwargs.get("language") or self._default_language(engine)
        project_name = kwargs.get("project_name") or meta.get("project_name", "Untitled Game")

        return {
            "project_name": project_name,
            "engine": engine,
            "dimension": dimension,
            "language": language,
            "include_tests": kwargs.get("include_tests", True),
            "include_tools": kwargs.get("include_tools", True),
        }

    def _recommended_structure(self, profile: Dict[str, Any], kwargs: Dict[str, Any]) -> List[str]:
        structure = [
            "artifacts",
            "design",
            "assets/raw",
            "assets/processed",
            "assets/audio",
            "assets/ui",
            "data/config",
            "data/content",
            "src",
        ]
        if profile["include_tests"]:
            structure.extend(["tests/unit", "tests/integration", "tests/smoke"])
        if profile["include_tools"]:
            structure.extend(["playtest/logs", "tools", "telemetry"])

        engine = canonical_engine_name(profile["engine"])
        if is_builtin_engine_name(engine):
            structure.extend(
                [
                    "assets/models",
                    "assets/textures",
                    "data/prefabs",
                    "data/scenes",
                    "src/game/scripts",
                    "telemetry",
                ]
            )
        elif engine in {"godot", "unity", "unreal"}:
            structure.extend(["engine", "engine/runtime_notes"])
        elif engine in {"pygame", "custom"}:
            structure.extend(["src/game", "src/game/systems", "src/game/content"])
        elif engine in {"phaser", "pixijs", "threejs"}:
            structure.extend(["src/game", "src/game/scenes", "src/game/systems"])
        elif engine == "love2d":
            structure.extend(["src/game", "src/game/systems"])

        extra = kwargs.get("data", {}).get("extra_directories", [])
        structure.extend(str(item) for item in extra if str(item).strip())
        return sorted(set(structure))

    def _starter_files(self, profile: Dict[str, Any], output_dir: Path, kwargs: Dict[str, Any]) -> Dict[Path, str]:
        engine = canonical_engine_name(profile["engine"])
        project_name = profile["project_name"]
        files: Dict[Path, str] = {
            output_dir / "artifacts/engine_profile.md": self._engine_profile_markdown(profile),
            output_dir / "artifacts/production_plan.md": self._production_plan_markdown(profile),
            output_dir / "design/README.md": "# Design Workspace\n\nUse this folder for blueprints, loops, and content specs.\n",
        }

        if is_builtin_engine_name(engine):
            return files

        if engine in {"pygame", "custom"}:
            files[output_dir / "src/main.py"] = (
                "from game.bootstrap import run_game\n\n\n"
                "if __name__ == '__main__':\n"
                "    run_game()\n"
            )
            files[output_dir / "src/game/bootstrap.py"] = (
                "def run_game() -> None:\n"
                f"    print('Bootstrapping {project_name}')\n"
            )
        elif engine in {"phaser", "pixijs", "threejs"}:
            files[output_dir / "src/main.ts"] = (
                f"export function boot{self._pascal_case(project_name)}(): void {{\n"
                "  console.log('Booting game runtime');\n"
                "}\n"
            )
        elif engine == "love2d":
            files[output_dir / "main.lua"] = (
                "function love.load()\n"
                f"  print('Bootstrapping {project_name}')\n"
                "end\n"
            )
        else:
            files[output_dir / "engine/README.md"] = (
                f"# {project_name} Engine Workspace\n\n"
                "Mirror engine-side scenes, prefabs, levels, or content assets here.\n"
                "Keep architecture and data contracts aligned with the artifacts folder.\n"
            )

        if profile["include_tests"]:
            files[output_dir / "tests/smoke/README.md"] = (
                "# Smoke Tests\n\nDocument the shortest repeatable playable path and automated checks here.\n"
            )

        return files

    def _engine_profile_markdown(self, profile: Dict[str, Any]) -> str:
        return (
            f"# Engine Profile: {profile['project_name']}\n\n"
            f"- Engine: {profile['engine']}\n"
            f"- Dimension: {profile['dimension']}\n"
            f"- Language: {profile['language']}\n"
            "- Baseline requirement: keep the first playable loop runnable before scaling content.\n"
            "- Test requirement: maintain smoke, integration, and playtest coverage from the start.\n"
        )

    def _production_plan_markdown(self, profile: Dict[str, Any]) -> str:
        return (
            f"# Production Plan: {profile['project_name']}\n\n"
            "1. Build the foundation and data contracts.\n"
            "2. Deliver a first playable loop.\n"
            "3. Upgrade that loop into a vertical slice with target quality.\n"
            "4. Expand content only after quality gates and telemetry are stable.\n"
        )

    def _load_blueprint(self, blueprint_path: Optional[str]) -> Dict[str, Any]:
        if not blueprint_path:
            return {}
        path = self._resolve_path(blueprint_path)
        if not path.exists():
            return {}
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            return {}

    def _load_or_compile_request(self, request_path: Path, kwargs: Dict[str, Any], *, output_dir: Path) -> Dict[str, Any]:
        if request_path.exists():
            try:
                return json.loads(request_path.read_text(encoding="utf-8"))
            except Exception:
                pass
        request = compile_game_prompt(
            self._resolve_prompt(kwargs),
            project_name=kwargs.get("project_name", output_dir.name or "Untitled Reverie Slice"),
            requested_runtime=kwargs.get("requested_runtime", ""),
            existing_runtime=kwargs.get("existing_runtime", ""),
            overrides=kwargs.get("data") or kwargs,
        )
        return request

    def _resolve_prompt(self, kwargs: Dict[str, Any]) -> str:
        prompt = str(kwargs.get("prompt") or "").strip()
        if prompt:
            return prompt
        fragments = [
            kwargs.get("project_name", ""),
            kwargs.get("engine", ""),
            kwargs.get("dimension", ""),
            " ".join((kwargs.get("data") or {}).get("themes", [])),
        ]
        fallback = " ".join(str(fragment).strip() for fragment in fragments if str(fragment).strip())
        return fallback or "Build a polished vertical slice with a complete gameplay loop and runtime-ready structure."

    def _default_language(self, engine: str) -> str:
        normalized = str(engine).lower()
        if normalized in {"phaser", "pixijs", "threejs"}:
            return "typescript"
        if normalized == "love2d":
            return "lua"
        if normalized == "godot":
            return "gdscript"
        if normalized in {"unity", "unreal"}:
            return "csharp" if normalized == "unity" else "cpp"
        return "python"

    def _pascal_case(self, text: str) -> str:
        parts = [part for part in "".join(ch if ch.isalnum() else " " for ch in text).split() if part]
        return "".join(part.capitalize() for part in parts) or "Game"

    def _resolve_path(self, raw: str) -> Path:
        return self.resolve_workspace_path(raw, purpose="resolve game project scaffolder path")

    def get_execution_message(self, **kwargs) -> str:
        return f"Game project scaffolding: {kwargs.get('action', 'unknown')}"
