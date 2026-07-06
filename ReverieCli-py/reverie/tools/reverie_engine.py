"""First-party runtime and scaffolding tool for Reverie Engine."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Dict, Optional

from .base import BaseTool, ToolResult
from ..engine import (
    ArchetypeDocument,
    ENGINE_BRAND,
    ENGINE_NAME,
    assess_project_scope,
    benchmark_project,
    build_engine_config,
    build_project_health_report,
    create_project_skeleton,
    export_project_video,
    import_renpy_script,
    inspect_legacy_project,
    inspect_renpy_project,
    inspect_project,
    materialize_sample,
    package_project,
    migrate_legacy_project,
    normalize_genre,
    outline_renpy_script,
    pack_archetype,
    run_project_smoke,
    runtime_capabilities,
    supported_game_families,
    save_archetype,
    save_prefab,
    save_scene,
    scene_from_dict,
    validate_archetype_document,
    validate_engine_config_schema,
    validate_gameplay_manifest_schema,
    validate_project,
    validate_renpy_project,
    validate_scene_document,
)
from ..engine.serialization import node_from_dict


class _BaseReverieEngineTool(BaseTool):
    aliases = ("engine_runtime",)
    search_hint = "create validate and smoke test reverie engine projects"
    tool_category = "game-runtime"
    tool_tags = ("game", "engine", "runtime", "scene", "prefab", "sample", "benchmark")
    description = (
        "Create, inspect, validate, sample, and smoke-test projects powered by "
        "the built-in Reverie Engine runtime."
    )

    parameters = {
        "type": "object",
        "properties": {
            "action": {
                "type": "string",
                "enum": [
                    "list_capabilities",
                    "assess_scope",
                    "create_project",
                    "inspect_project",
                    "generate_scene",
                    "generate_prefab",
                    "generate_archetype",
                    "author_scene_blueprint",
                    "author_prefab_blueprint",
                    "validate_authoring_payload",
                    "materialize_sample",
                    "run_smoke",
                    "validate_project",
                    "project_health",
                    "package_project",
                    "benchmark_project",
                    "export_video",
                    "import_renpy",
                    "inspect_renpy",
                    "outline_renpy",
                    "validate_renpy",
                    "inspect_legacy_project",
                    "migrate_legacy_project",
                ],
                "description": "Reverie Engine action",
            },
            "output_dir": {"type": "string", "description": "Target project directory"},
            "project_name": {"type": "string", "description": "Project name for create_project"},
            "dimension": {"type": "string", "description": "2D, 2.5D, or 3D"},
            "genre": {"type": "string", "description": "Gameplay profile such as platformer, galgame, tower_defense, or arena"},
            "quality_tier": {"type": "string", "description": "Production tier such as indie, AA, or AAA"},
            "world_structure": {"type": "string", "description": "World shape such as focused, hub, regional, or open_world"},
            "source_dir": {"type": "string", "description": "Legacy Godot, O3DE, or Ren'Py source project directory"},
            "sample_name": {
                "type": "string",
                "description": "Sample to materialize: 2d_platformer, iso_adventure, 3d_arena, galgame_live2d, or tower_defense",
            },
            "scene_path": {"type": "string", "description": "Scene path for generation or smoke execution"},
            "prefab_path": {"type": "string", "description": "Prefab path for generation"},
            "archetype_path": {"type": "string", "description": "Archetype path for generation"},
            "output_path": {"type": "string", "description": "Optional output log or generated file path"},
            "headless": {"type": "boolean", "description": "Use headless runtime execution"},
            "overwrite": {"type": "boolean", "description": "Overwrite starter files if they exist"},
            "iterations": {"type": "integer", "description": "Benchmark iteration count"},
            "include_smoke": {"type": "boolean", "description": "Run smoke validation as part of the action"},
            "format": {"type": "string", "description": "Video export format: mp4, gif, or frames"},
            "fps": {"type": "integer", "description": "Video export framerate"},
            "frames": {"type": "integer", "description": "Number of runtime frames to simulate during export"},
            "frame_stride": {"type": "integer", "description": "Capture every Nth runtime frame when exporting video"},
            "script_path": {"type": "string", "description": "Ren'Py .rpy script path for dialogue import"},
            "conversation_id": {"type": "string", "description": "Optional target conversation id for dialogue import"},
            "entry_label": {"type": "string", "description": "Optional Ren'Py entry label override"},
            "autostart": {"type": "boolean", "description": "Update the main scene to autostart the imported conversation"},
            "data": {"type": "object", "description": "Inline scene or prefab data"},
            "payload_type": {
                "type": "string",
                "description": "Structured payload type: scene, prefab, archetype, engine_config, gameplay_manifest, or project",
            },
        },
        "required": ["action"],
    }

    def __init__(self, context: Optional[Dict] = None):
        super().__init__(context)
        self.project_root = Path(context.get("project_root")) if context and context.get("project_root") else Path.cwd()

    def execute(self, **kwargs) -> ToolResult:
        if "output_dir" not in kwargs and kwargs.get("project_dir"):
            kwargs["output_dir"] = kwargs["project_dir"]
        if kwargs.get("action") == "run_smoke" and "output_dir" not in kwargs and kwargs.get("output_path"):
            output_candidate = Path(str(kwargs["output_path"])).expanduser()
            if output_candidate.is_dir():
                kwargs["output_dir"] = str(output_candidate)
                kwargs.pop("output_path", None)
        nested_data = kwargs.get("data")
        if isinstance(nested_data, dict) and kwargs.get("action") in {"assess_scope", "create_project"}:
            for key in (
                "output_dir",
                "project_name",
                "dimension",
                "genre",
                "quality_tier",
                "world_structure",
                "sample_name",
                "overwrite",
            ):
                if key not in kwargs and key in nested_data:
                    kwargs[key] = nested_data[key]
        action = kwargs.get("action")
        try:
            if action == "list_capabilities":
                return self._list_capabilities(kwargs)
            if action == "assess_scope":
                return self._assess_scope(kwargs)
            if action == "create_project":
                return self._create_project(kwargs)
            if action == "inspect_project":
                return self._inspect_project(kwargs)
            if action == "generate_scene":
                return self._generate_scene(kwargs)
            if action == "generate_prefab":
                return self._generate_prefab(kwargs)
            if action == "generate_archetype":
                return self._generate_archetype(kwargs)
            if action == "author_scene_blueprint":
                return self._author_scene_blueprint(kwargs)
            if action == "author_prefab_blueprint":
                return self._author_prefab_blueprint(kwargs)
            if action == "validate_authoring_payload":
                return self._validate_authoring_payload(kwargs)
            if action == "materialize_sample":
                return self._materialize_sample(kwargs)
            if action == "run_smoke":
                return self._run_smoke(kwargs)
            if action == "validate_project":
                return self._validate_project(kwargs)
            if action == "project_health":
                return self._project_health(kwargs)
            if action == "package_project":
                return self._package_project(kwargs)
            if action == "benchmark_project":
                return self._benchmark_project(kwargs)
            if action == "export_video":
                return self._export_video(kwargs)
            if action == "import_renpy":
                return self._import_renpy(kwargs)
            if action == "inspect_renpy":
                return self._inspect_renpy(kwargs)
            if action == "outline_renpy":
                return self._outline_renpy(kwargs)
            if action == "validate_renpy":
                return self._validate_renpy(kwargs)
            if action == "inspect_legacy_project":
                return self._inspect_legacy_project(kwargs)
            if action == "migrate_legacy_project":
                return self._migrate_legacy_project(kwargs)
            return ToolResult.fail(f"Unknown action: {action}")
        except Exception as exc:
            return ToolResult.fail(f"Error executing {action}: {str(exc)}")

    def _resolve_output_dir(self, kwargs: Dict[str, Any]) -> Path:
        return self.resolve_workspace_path(
            kwargs.get("output_dir", "."),
            purpose=f"resolve {ENGINE_BRAND} project path",
        )

    def _list_capabilities(self, kwargs: Dict[str, Any]) -> ToolResult:
        root = self._resolve_output_dir(kwargs)
        capabilities = runtime_capabilities(root)
        families = supported_game_families()
        return ToolResult.ok(
            f"{ENGINE_BRAND} unified runtime: {len(families)} game families across 2D, 2.5D, and focused 3D",
            {"capabilities": capabilities, "game_families": families},
        )

    def _assess_scope(self, kwargs: Dict[str, Any]) -> ToolResult:
        assessment = assess_project_scope(
            dimension=str(kwargs.get("dimension") or "2D"),
            genre=str(kwargs.get("genre") or "sandbox"),
            quality_tier=str(kwargs.get("quality_tier") or "indie"),
            world_structure=str(kwargs.get("world_structure") or "focused"),
        )
        status = "supported" if assessment["supported"] else "out of scope"
        return ToolResult.ok(f"{ENGINE_BRAND} scope assessment: {status}", assessment)

    def _create_project(self, kwargs: Dict[str, Any]) -> ToolResult:
        output_dir = self._resolve_output_dir(kwargs)
        project_name = kwargs.get("project_name") or output_dir.name or "Reverie Game"
        dimension = kwargs.get("dimension", "2D")
        sample_name = kwargs.get("sample_name")
        overwrite = kwargs.get("overwrite", False)
        genre = kwargs.get("genre") or self._infer_genre_from_project_name(str(project_name))
        result = create_project_skeleton(
            output_dir,
            project_name=project_name,
            dimension=dimension,
            sample_name=sample_name,
            genre=genre,
            overwrite=overwrite,
        )
        output = (
            f"Created {ENGINE_BRAND} project in {output_dir}\n"
            f"Project: {project_name}\n"
            f"Dimension: {dimension}\n"
            f"Engine: {ENGINE_NAME}\n"
            f"Genre: {result.get('genre', kwargs.get('genre', 'sandbox'))}\n"
            f"Modeling workspace: {'enabled' if result.get('modeling_enabled') else 'disabled'}\n"
            f"Directories created: {len(result['directories'])}\n"
            f"Files written: {len(result['files'])}"
        )
        if sample_name:
            output += f"\nSample materialized: {sample_name}"
        return ToolResult.ok(output, {"project_root": str(output_dir), **result})

    @staticmethod
    def _infer_genre_from_project_name(project_name: str) -> str:
        compact_name = re.sub(r"[^a-z0-9]+", "", str(project_name or "").lower())
        for family in supported_game_families():
            genre_id = str(family.get("id") or "")
            if genre_id != "sandbox" and genre_id.replace("_", "") in compact_name:
                return genre_id
        hints = {
            "card": "card_game",
            "deck": "card_game",
            "visualnovel": "galgame",
            "galgame": "galgame",
            "towerdefense": "tower_defense",
            "platform": "platformer",
            "metroid": "metroidvania",
            "rogue": "roguelike",
            "rhythm": "rhythm",
            "racing": "racing",
            "shooter": "shooter",
            "survival": "survival",
            "tactics": "tactics",
        }
        for token, genre_id in hints.items():
            if token in compact_name:
                return genre_id
        return normalize_genre(None)

    def _inspect_project(self, kwargs: Dict[str, Any]) -> ToolResult:
        output_dir = self._resolve_output_dir(kwargs)
        info = inspect_project(output_dir)
        validation = validate_project(output_dir)
        output = (
            f"{ENGINE_BRAND} project: {output_dir}\n"
            f"Scenes: {info['scene_count']} | Prefabs: {info['prefab_count']} | Content files: {info['content_count']}\n"
            f"Bootstrap present: {info['has_bootstrap']}\n"
            f"Genre: {info.get('genre', 'sandbox')} | Dimension: {info.get('dimension', '2D')}\n"
            f"Models: {info.get('modeling', {}).get('runtime_model_count', 0)} runtime | {info.get('modeling', {}).get('source_model_count', 0)} source\n"
            f"Runtime capabilities: {runtime_capabilities(output_dir)}\n"
            f"Validation: {'ok' if validation['valid'] else 'issues found'}"
        )
        return ToolResult.ok(output, {"info": info, "validation": validation})

    def _generate_scene(self, kwargs: Dict[str, Any]) -> ToolResult:
        output_dir = self._resolve_output_dir(kwargs)
        scene_path = self.resolve_workspace_path(
            kwargs.get("scene_path", str(output_dir / "data/scenes/main.relscene.json")),
            purpose=f"resolve {ENGINE_BRAND} scene path",
        )
        payload = kwargs.get("data") or {
            "name": "Main",
            "type": "Scene",
            "scene_id": "main",
            "metadata": {"engine": ENGINE_NAME},
            "components": [{"type": "Transform", "position": [0, 0, 0]}],
            "children": [],
        }
        errors = validate_scene_document(payload)
        if errors:
            return ToolResult.fail("; ".join(errors))
        save_scene(scene_from_dict(payload), scene_path)
        return ToolResult.ok(
            f"Generated scene at {scene_path}",
            {"scene_path": str(scene_path), "scene_name": payload.get("name", "Main")},
        )

    def _generate_prefab(self, kwargs: Dict[str, Any]) -> ToolResult:
        output_dir = self._resolve_output_dir(kwargs)
        prefab_path = self.resolve_workspace_path(
            kwargs.get("prefab_path", str(output_dir / "data/prefabs/object.relprefab.json")),
            purpose=f"resolve {ENGINE_BRAND} prefab path",
        )
        payload = kwargs.get("data") or {
            "name": "RuntimeObject",
            "type": "Actor",
            "components": [
                {"type": "Transform", "position": [0, 0, 0]},
                {"type": "Collider", "size": [1, 1, 1], "layer": "world"},
            ],
            "children": [],
        }
        save_prefab(node_from_dict(payload), prefab_path)
        return ToolResult.ok(
            f"Generated prefab at {prefab_path}",
            {"prefab_path": str(prefab_path), "prefab_name": payload.get("name", "RuntimeObject")},
        )

    def _generate_archetype(self, kwargs: Dict[str, Any]) -> ToolResult:
        output_dir = self._resolve_output_dir(kwargs)
        archetype_path = self.resolve_workspace_path(
            kwargs.get("archetype_path", str(output_dir / "data/prefabs/object.relarchetype.json")),
            purpose=f"resolve {ENGINE_BRAND} archetype path",
        )
        payload = kwargs.get("data") or {
            "name": "RuntimeArchetype",
            "type": "Actor",
            "components": [
                {"type": "Transform", "position": [0, 0, 0]},
                {"type": "Health", "max_health": 25, "current_health": 25},
            ],
            "children": [],
        }
        document = pack_archetype(node_from_dict(payload), archetype_id=payload.get("name", "RuntimeArchetype"))
        errors = validate_archetype_document(document.to_dict())
        if errors:
            return ToolResult.fail("; ".join(errors))
        save_archetype(document, archetype_path)
        return ToolResult.ok(
            f"Generated archetype at {archetype_path}",
            {"archetype_path": str(archetype_path), "archetype_id": document.archetype_id},
        )

    def _author_scene_blueprint(self, kwargs: Dict[str, Any]) -> ToolResult:
        payload = kwargs.get("data") or {}
        scene_name = str(payload.get("name") or "Main")
        scene_payload = {
            "name": scene_name,
            "type": "Scene",
            "scene_id": str(payload.get("scene_id") or "main"),
            "metadata": dict(payload.get("metadata") or {"engine": ENGINE_NAME}),
            "components": list(payload.get("components") or [{"type": "Transform", "position": [0, 0, 0]}]),
            "children": list(payload.get("children") or []),
        }
        errors = validate_scene_document(scene_payload)
        if errors:
            return ToolResult.fail("; ".join(errors))

        saved_path = ""
        if kwargs.get("scene_path"):
            output_dir = self._resolve_output_dir(kwargs)
            scene_path = self.resolve_workspace_path(
                kwargs.get("scene_path", str(output_dir / "data/scenes/main.relscene.json")),
                purpose=f"resolve {ENGINE_BRAND} scene blueprint path",
            )
            save_scene(scene_from_dict(scene_payload), scene_path)
            saved_path = str(scene_path)

        return ToolResult.ok(
            f"Authored scene blueprint '{scene_name}'",
            {"payload_type": "scene", "scene": scene_payload, "saved_path": saved_path},
        )

    def _author_prefab_blueprint(self, kwargs: Dict[str, Any]) -> ToolResult:
        payload = kwargs.get("data") or {}
        prefab_payload = {
            "name": str(payload.get("name") or "RuntimeObject"),
            "type": str(payload.get("type") or "Actor"),
            "metadata": dict(payload.get("metadata") or {}),
            "tags": list(payload.get("tags") or []),
            "components": list(
                payload.get("components")
                or [
                    {"type": "Transform", "position": [0, 0, 0]},
                    {"type": "Collider", "size": [1, 1, 1], "layer": "world"},
                ]
            ),
            "children": list(payload.get("children") or []),
        }
        node = node_from_dict(prefab_payload)

        saved_path = ""
        if kwargs.get("prefab_path"):
            output_dir = self._resolve_output_dir(kwargs)
            prefab_path = self.resolve_workspace_path(
                kwargs.get("prefab_path", str(output_dir / "data/prefabs/object.relprefab.json")),
                purpose=f"resolve {ENGINE_BRAND} prefab blueprint path",
            )
            save_prefab(node, prefab_path)
            saved_path = str(prefab_path)

        return ToolResult.ok(
            f"Authored prefab blueprint '{prefab_payload['name']}'",
            {"payload_type": "prefab", "prefab": node.to_dict(), "saved_path": saved_path},
        )

    def _validate_authoring_payload(self, kwargs: Dict[str, Any]) -> ToolResult:
        payload_type = str(kwargs.get("payload_type") or "scene").strip().lower()
        payload = dict(kwargs.get("data") or {})
        errors: list[str]

        if payload_type == "scene":
            errors = validate_scene_document(payload)
        elif payload_type == "prefab":
            node = node_from_dict(payload)
            errors = []
            if not str(node.name).strip():
                errors.append("prefab requires a non-empty name")
        elif payload_type == "archetype":
            errors = validate_archetype_document(payload)
        elif payload_type == "engine_config":
            errors = validate_engine_config_schema(payload)
        elif payload_type == "gameplay_manifest":
            errors = validate_gameplay_manifest_schema(payload)
        elif payload_type == "project":
            output_dir = self._resolve_output_dir(kwargs)
            validation = validate_project(output_dir)
            return ToolResult.ok(
                f"Validated {ENGINE_BRAND} project at {output_dir}: {'ok' if validation['valid'] else 'issues found'}",
                {"payload_type": "project", "validation": validation},
            )
        else:
            return ToolResult.fail(f"Unsupported payload_type: {payload_type}")

        return ToolResult.ok(
            f"Validated {payload_type} payload: {'ok' if not errors else 'issues found'}",
            {"payload_type": payload_type, "errors": errors, "valid": not errors},
        )

    def _materialize_sample(self, kwargs: Dict[str, Any]) -> ToolResult:
        output_dir = self._resolve_output_dir(kwargs)
        sample_name = kwargs.get("sample_name", "2d_platformer")
        overwrite = kwargs.get("overwrite", False)
        result = materialize_sample(output_dir, sample_name, overwrite=overwrite)
        return ToolResult.ok(
            f"Materialized sample '{sample_name}' in {output_dir}",
            {"project_root": str(output_dir), **result},
        )

    def _run_smoke(self, kwargs: Dict[str, Any]) -> ToolResult:
        output_dir = self._resolve_output_dir(kwargs)
        scene_path = kwargs.get("scene_path")
        output_path = kwargs.get("output_path") or str(output_dir / "playtest/logs/engine_smoke.json")
        result = run_project_smoke(output_dir, scene_path=scene_path, output_log=output_path)
        return ToolResult.ok(
            f"{ENGINE_BRAND} smoke completed for {output_dir}\n"
            f"Events: {result['summary']['event_count']}\n"
            f"Log: {result['log_path']}",
            result,
        )

    def _validate_project(self, kwargs: Dict[str, Any]) -> ToolResult:
        output_dir = self._resolve_output_dir(kwargs)
        validation = validate_project(output_dir)
        config_path = output_dir / "data/config/engine.yaml"
        config_preview = (
            build_engine_config(output_dir.name, kwargs.get("dimension", "2D"), genre=kwargs.get("genre"))
            if not config_path.exists()
            else {}
        )
        output = (
            f"Validation for {output_dir}: {'ok' if validation['valid'] else 'issues found'}\n"
            f"Required paths: {len(validation['required_paths'])}\n"
            f"Errors: {len(validation['errors'])}"
        )
        if validation["errors"]:
            output += "\n" + "\n".join(f"- {item}" for item in validation["errors"])
        if validation.get("warnings"):
            output += "\nWarnings:\n" + "\n".join(f"- {item}" for item in validation["warnings"])
        return ToolResult.ok(output, {"validation": validation, "suggested_engine_config": config_preview})

    def _project_health(self, kwargs: Dict[str, Any]) -> ToolResult:
        output_dir = self._resolve_output_dir(kwargs)
        report = build_project_health_report(output_dir, include_smoke=bool(kwargs.get("include_smoke", False)))
        output = (
            f"Health report for {output_dir}\n"
            f"Status: {report['status']}\n"
            f"Score: {report['score']}/100\n"
            f"Errors: {len(report['validation']['errors'])} | Warnings: {len(report['validation']['warnings'])}"
        )
        if report["recommendations"]:
            output += "\n" + "\n".join(f"- {item}" for item in report["recommendations"])
        return ToolResult.ok(output, {"health": report})

    def _package_project(self, kwargs: Dict[str, Any]) -> ToolResult:
        output_dir = self._resolve_output_dir(kwargs)
        result = package_project(
            output_dir,
            output_path=kwargs.get("output_path"),
            include_smoke=bool(kwargs.get("include_smoke", True)),
        )
        if not result.get("success", False):
            return ToolResult.fail(result.get("error", "package failed"))
        output = (
            f"Packaged {ENGINE_BRAND} project\n"
            f"Archive: {result['package_path']}\n"
            f"Files: {result['file_count']}\n"
            f"Smoke: {'ok' if result.get('smoke', {}).get('success', False) else 'skipped'}"
        )
        return ToolResult.ok(output, result)

    def _benchmark_project(self, kwargs: Dict[str, Any]) -> ToolResult:
        output_dir = self._resolve_output_dir(kwargs)
        result = benchmark_project(
            output_dir,
            iterations=int(kwargs.get("iterations", 10)),
            scene_path=kwargs.get("scene_path"),
        )
        if kwargs.get("output_path"):
            output_path = self.resolve_workspace_path(
                kwargs["output_path"],
                purpose=f"resolve {ENGINE_BRAND} benchmark output path",
            )
            output_path.parent.mkdir(parents=True, exist_ok=True)
            output_path.write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")
            result["output_path"] = str(output_path)
        instantiation = result["benchmarks"]["scene_instantiation"]
        ai_latency = result["benchmarks"]["ai_command_latency"]
        output = (
            f"Benchmarked {ENGINE_BRAND} project\n"
            f"Scene instantiation avg: {instantiation['avg_ms']} ms\n"
            f"AI authoring latency avg: {ai_latency['avg_ms']} ms"
        )
        if result.get("output_path"):
            output += f"\nSaved: {result['output_path']}"
        return ToolResult.ok(output, result)

    def _export_video(self, kwargs: Dict[str, Any]) -> ToolResult:
        output_dir = self._resolve_output_dir(kwargs)
        result = export_project_video(
            output_dir,
            scene_path=kwargs.get("scene_path"),
            format_name=str(kwargs.get("format") or "mp4"),
            output_path=kwargs.get("output_path"),
            fps=int(kwargs.get("fps", 30) or 30),
            frames=int(kwargs.get("frames", 180) or 180),
            frame_stride=int(kwargs.get("frame_stride", 1) or 1),
        )
        output = (
            f"Exported {ENGINE_BRAND} playblast\n"
            f"Format: {result['format']}\n"
            f"Captured frames: {result['frame_count']}\n"
            f"Frames dir: {result['frames_dir']}"
        )
        if result.get("output_path"):
            output += f"\nVideo: {result['output_path']}"
        if result.get("telemetry_path"):
            output += f"\nTelemetry: {result['telemetry_path']}"
        if result.get("manifest_path"):
            output += f"\nManifest: {result['manifest_path']}"
        if result.get("ffmpeg_error"):
            output += f"\nEncoder status: {result['ffmpeg_error']}"
        return ToolResult.ok(output, result)

    def _import_renpy(self, kwargs: Dict[str, Any]) -> ToolResult:
        output_dir = self._resolve_output_dir(kwargs)
        script_path = str(kwargs.get("script_path") or "").strip()
        if not script_path:
            return ToolResult.fail("script_path is required for import_renpy")
        result = import_renpy_script(
            output_dir,
            script_path,
            conversation_id=str(kwargs.get("conversation_id") or "").strip(),
            entry_label=str(kwargs.get("entry_label") or "").strip(),
            autostart=bool(kwargs.get("autostart", False)),
            overwrite=bool(kwargs.get("overwrite", True)),
        )
        output = (
            f"Imported Ren'Py dialogue script\n"
            f"Source: {result['source_path']}\n"
            f"Conversation: {result['conversation_id']}\n"
            f"Start node: {result['start_node']}\n"
            f"Nodes: {result['node_count']}\n"
            f"Dialogue file: {result['dialogue_path']}"
        )
        if result.get("autostart_updated"):
            output += "\nMain scene autostart_conversation updated."
        if result.get("warning_count"):
            output += f"\nWarnings: {result['warning_count']}"
        return ToolResult.ok(output, result)

    def _resolve_renpy_source(self, kwargs: Dict[str, Any], *, require_script: bool = False) -> Path:
        raw_path = kwargs.get("script_path") if require_script else kwargs.get("source_dir") or kwargs.get("output_dir", ".")
        return self.resolve_workspace_path(
            raw_path or ".",
            purpose="resolve built-in Ren'Py source path",
        )

    def _inspect_renpy(self, kwargs: Dict[str, Any]) -> ToolResult:
        source = self._resolve_renpy_source(kwargs)
        result = inspect_renpy_project(source)
        return ToolResult.ok(
            f"Inspected Ren'Py project with the built-in engine parser: {result['script_count']} script(s)",
            result,
        )

    def _outline_renpy(self, kwargs: Dict[str, Any]) -> ToolResult:
        source = self._resolve_renpy_source(kwargs, require_script=True)
        result = outline_renpy_script(source)
        return ToolResult.ok(
            f"Outlined Ren'Py script: {result['counts']['labels']} label(s), {result['counts']['menus']} menu(s)",
            result,
        )

    def _validate_renpy(self, kwargs: Dict[str, Any]) -> ToolResult:
        source = self._resolve_renpy_source(kwargs)
        result = validate_renpy_project(source)
        return ToolResult.ok(
            f"Validated Ren'Py source with the built-in engine parser: {'ok' if result['valid'] else 'issues found'}",
            result,
        )

    def _inspect_legacy_project(self, kwargs: Dict[str, Any]) -> ToolResult:
        source = self._resolve_renpy_source(kwargs)
        result = inspect_legacy_project(source)
        return ToolResult.ok(
            f"Legacy project source: {result.get('source_engine') or 'not detected'} -> {ENGINE_NAME}",
            result,
        )

    def _migrate_legacy_project(self, kwargs: Dict[str, Any]) -> ToolResult:
        source = self._resolve_renpy_source(kwargs)
        output_dir = self._resolve_output_dir(kwargs)
        result = migrate_legacy_project(
            source,
            output_dir,
            project_name=str(kwargs.get("project_name") or ""),
            overwrite=bool(kwargs.get("overwrite", False)),
        )
        return ToolResult.ok(
            f"Migrated {result['source_engine']} source into {ENGINE_BRAND} at {output_dir}",
            result,
        )

    def get_execution_message(self, **kwargs) -> str:
        return f"{ENGINE_BRAND}: {kwargs.get('action', 'unknown')}"


class ReverieEngineTool(_BaseReverieEngineTool):
    name = ENGINE_NAME
