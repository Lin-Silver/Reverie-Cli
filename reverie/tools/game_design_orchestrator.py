"""
Game Design Orchestrator Tool.

Creates structured blueprints for large-scale game production and helps the
agent move from concept to vertical slice with concrete system definitions.
"""

from __future__ import annotations

from typing import Optional, Dict, Any, List
from pathlib import Path
from datetime import datetime
import json

from .base import BaseTool, ToolResult
from ..engine import canonical_engine_name, is_builtin_engine_name
from ..gamer.asset_pipeline import build_asset_pipeline_plan, asset_pipeline_markdown
from ..gamer.asset_budgeting import build_asset_budget
from ..gamer.animation_pipeline import build_animation_plan
from ..gamer.character_factory import build_character_kits
from ..gamer.content_lattice import build_content_matrix
from ..gamer.continuation_director import (
    build_continuation_recommendations,
    continuation_recommendations_markdown,
)
from ..gamer.environment_factory import build_environment_kits
from ..gamer.expansion_planner import (
    build_content_expansion_plan,
    build_expansion_backlog,
    build_resume_state,
    content_expansion_markdown,
    expansion_backlog_markdown,
    resume_state_markdown,
)
from ..gamer.faction_graph import build_enemy_faction_packet, build_faction_graph
from ..gamer.gameplay_factory import build_boss_arc, build_gameplay_factory
from ..gamer.milestone_planner import build_feature_matrix, build_milestone_board, build_risk_register
from ..gamer.program_compiler import build_game_program, game_bible_markdown
from ..gamer.prompt_compiler import compile_game_prompt
from ..gamer.production_plan import (
    build_blueprint_from_request,
    build_production_plan,
    build_vertical_slice_plan,
    vertical_slice_markdown,
)
from ..gamer.region_expander import build_region_expansion_plan, build_region_kits
from ..gamer.runtime_capability_graph import build_runtime_capability_graph
from ..gamer.runtime_delivery import build_runtime_delivery_plan
from ..gamer.runtime_registry import discover_runtime_profiles, select_runtime_profile
from ..gamer.save_migration import build_save_migration_plan
from ..gamer.system_generators import (
    build_system_packet_bundle,
    build_task_graph,
    system_packet_markdown,
    task_graph_markdown,
)
from ..gamer.verification import (
    build_combat_feel_report,
    build_performance_budget,
    build_quality_gate_report,
)
from ..gamer.world_program import build_questline_program, build_world_program


class GameDesignOrchestratorTool(BaseTool):
    name = "game_design_orchestrator"
    aliases = ("game_blueprint", "blueprint_orchestrator")
    search_hint = "create game blueprints and vertical slice plans"
    tool_category = "game-design"
    tool_tags = ("game", "blueprint", "design", "system", "vertical-slice", "scope")
    description = (
        "Create structured game blueprints, expand gameplay systems, plan "
        "vertical slices, analyze scope, and export markdown design packets."
    )

    parameters = {
        "type": "object",
        "properties": {
            "action": {
                "type": "string",
                "enum": [
                    "compile_request",
                    "compile_program",
                    "create_blueprint",
                    "plan_production",
                    "expand_system",
                    "generate_gameplay_factory",
                    "plan_boss_arc",
                    "expand_region",
                    "generate_character_kit",
                    "build_enemy_faction",
                    "generate_vertical_slice",
                    "analyze_scope",
                    "export_markdown",
                ],
                "description": "Design orchestration action",
            },
            "blueprint_path": {
                "type": "string",
                "description": "Blueprint JSON path (default: artifacts/game_blueprint.json)",
            },
            "request_path": {
                "type": "string",
                "description": "Compiled request JSON path (default: artifacts/game_request.json)",
            },
            "output_path": {
                "type": "string",
                "description": "Optional export path for markdown outputs",
            },
            "prompt": {
                "type": "string",
                "description": "Single prompt used for request compilation or production planning",
            },
            "project_name": {
                "type": "string",
                "description": "Project name for blueprint creation",
            },
            "genre": {
                "type": "string",
                "description": "Primary game genre",
            },
            "dimension": {
                "type": "string",
                "description": "Game dimension or rendering target (2D, 2.5D, 3D)",
            },
            "target_engine": {
                "type": "string",
                "description": "Target engine or framework",
            },
            "camera_model": {
                "type": "string",
                "description": "Camera model such as side-view, top-down, isometric, third-person",
            },
            "scope": {
                "type": "string",
                "description": "Target production scope such as prototype, vertical_slice, full_game",
            },
            "requested_runtime": {
                "type": "string",
                "description": "Optional explicit runtime request such as reverie_engine or godot",
            },
            "existing_runtime": {
                "type": "string",
                "description": "Optional existing runtime that should be preserved",
            },
            "system_name": {
                "type": "string",
                "description": "System name for expand_system",
            },
            "region_id": {
                "type": "string",
                "description": "Region id for expand_region",
            },
            "faction_id": {
                "type": "string",
                "description": "Faction id for build_enemy_faction",
            },
            "character_id": {
                "type": "string",
                "description": "Character or kit id for generate_character_kit",
            },
            "pillars": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Creative pillars for the project",
            },
            "references": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Reference games or inspirations",
            },
            "data": {
                "type": "object",
                "description": "Additional blueprint or system data",
            },
            "overwrite": {
                "type": "boolean",
                "description": "Overwrite an existing blueprint when creating",
            },
        },
        "required": ["action"],
    }

    def __init__(self, context: Optional[Dict] = None):
        super().__init__(context)
        self.project_root = Path(context.get("project_root")) if context and context.get("project_root") else Path.cwd()

    def execute(self, **kwargs) -> ToolResult:
        action = kwargs.get("action")
        blueprint_path = self._resolve_path(kwargs.get("blueprint_path", "artifacts/game_blueprint.json"))
        request_path = self._resolve_path(kwargs.get("request_path", "artifacts/game_request.json"))

        try:
            if action == "compile_request":
                return self._compile_request(request_path, kwargs)
            if action == "compile_program":
                output_path = self._resolve_path(
                    kwargs.get("output_path", "artifacts/production_plan.json")
                )
                return self._compile_program(request_path, blueprint_path, output_path, kwargs)
            if action == "create_blueprint":
                return self._create_blueprint(request_path, blueprint_path, kwargs)
            if action == "plan_production":
                output_path = self._resolve_path(
                    kwargs.get("output_path", "artifacts/production_plan.json")
                )
                return self._plan_production(request_path, blueprint_path, output_path, kwargs)
            if action == "expand_system":
                system_name = kwargs.get("system_name")
                if not system_name:
                    return ToolResult.fail("system_name is required for expand_system")
                return self._expand_system(blueprint_path, system_name, kwargs.get("data") or {})
            if action == "generate_gameplay_factory":
                output_path = self._resolve_path(kwargs.get("output_path", "artifacts/gameplay_factory.json"))
                return self._generate_gameplay_factory(request_path, blueprint_path, output_path, kwargs)
            if action == "plan_boss_arc":
                output_path = self._resolve_path(kwargs.get("output_path", "artifacts/boss_arc.json"))
                return self._plan_boss_arc(request_path, blueprint_path, output_path, kwargs)
            if action == "expand_region":
                output_path = self._resolve_path(kwargs.get("output_path", "artifacts/region_expansion.json"))
                return self._expand_region(request_path, blueprint_path, output_path, kwargs)
            if action == "generate_character_kit":
                output_path = self._resolve_path(kwargs.get("output_path", "artifacts/character_kits.json"))
                return self._generate_character_kit(request_path, blueprint_path, output_path, kwargs)
            if action == "build_enemy_faction":
                output_path = self._resolve_path(kwargs.get("output_path", "artifacts/enemy_faction.json"))
                return self._build_enemy_faction(request_path, blueprint_path, output_path, kwargs)
            if action == "generate_vertical_slice":
                output_path = self._resolve_path(
                    kwargs.get("output_path", "artifacts/vertical_slice_plan.md")
                )
                return self._generate_vertical_slice(request_path, blueprint_path, output_path, kwargs.get("data") or {})
            if action == "analyze_scope":
                return self._analyze_scope(blueprint_path, kwargs)
            if action == "export_markdown":
                output_path = self._resolve_path(
                    kwargs.get("output_path", str(blueprint_path.with_suffix(".md")))
                )
                return self._export_markdown(blueprint_path, output_path)
            return ToolResult.fail(f"Unknown action: {action}")
        except Exception as exc:
            return ToolResult.fail(f"Error executing {action}: {str(exc)}")

    def _compile_request(self, request_path: Path, kwargs: Dict[str, Any]) -> ToolResult:
        request = compile_game_prompt(
            self._resolve_prompt(kwargs),
            project_name=kwargs.get("project_name", ""),
            requested_runtime=kwargs.get("requested_runtime", ""),
            existing_runtime=kwargs.get("existing_runtime", ""),
            overrides=kwargs.get("data") or kwargs,
        )
        request_path.parent.mkdir(parents=True, exist_ok=True)
        request_path.write_text(json.dumps(request, indent=2, ensure_ascii=False), encoding="utf-8")
        output = (
            f"Compiled request at {request_path}\n"
            f"Project: {request['meta']['project_name']}\n"
            f"Genre: {request['creative_target']['primary_genre']}\n"
            f"Dimension: {request['experience']['dimension']}\n"
            f"Scope: {request['production']['delivery_scope']}\n"
            f"Preferred runtime: {request['runtime_preferences']['preferred_runtime']}"
        )
        return ToolResult.ok(
            output,
            {
                "request_path": str(request_path.relative_to(self.project_root)),
                "game_request": request,
            },
        )

    def _write_json_doc(self, path: Path, payload: Dict[str, Any]) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")

    def _write_text_doc(self, path: Path, payload: str) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(payload, encoding="utf-8")

    def _collect_production_context(self, request_path: Path, kwargs: Dict[str, Any]) -> Dict[str, Any]:
        game_request = self._load_or_compile_request(request_path, kwargs)
        runtime_selection = select_runtime_profile(
            game_request,
            project_root=self.project_root,
            requested_runtime=kwargs.get("requested_runtime", ""),
            existing_runtime=kwargs.get("existing_runtime", ""),
        )
        blueprint = build_blueprint_from_request(
            game_request,
            runtime_profile=runtime_selection["profile"],
            overrides=kwargs.get("data") or {},
        )
        reference_intelligence = dict(runtime_selection.get("reference_intelligence", {}) or {})
        if reference_intelligence:
            blueprint.setdefault("technical_strategy", {})["reference_strategy"] = {
                "reference_root": reference_intelligence.get("reference_root", ""),
                "recommended_stack": list(reference_intelligence.get("recommended_reference_stack", []) or []),
                "legal_guardrails": list(reference_intelligence.get("legal_guardrails", []) or []),
            }
        production_plan = build_production_plan(
            game_request,
            blueprint,
            runtime_profile=runtime_selection["profile"],
        )
        system_bundle = build_system_packet_bundle(
            game_request,
            blueprint,
            runtime_profile=runtime_selection["profile"],
        )
        task_graph = build_task_graph(
            game_request,
            blueprint,
            system_bundle,
            runtime_profile=runtime_selection["profile"],
            production_plan=production_plan,
        )
        content_expansion = build_content_expansion_plan(
            game_request,
            blueprint,
            runtime_profile=runtime_selection["profile"],
        )
        asset_pipeline = build_asset_pipeline_plan(
            game_request,
            blueprint,
            system_bundle,
            content_expansion,
            runtime_profile=runtime_selection["profile"],
        )
        if reference_intelligence:
            asset_pipeline["reference_stack"] = list(reference_intelligence.get("recommended_reference_stack", []) or [])
            asset_pipeline["reference_guardrails"] = list(reference_intelligence.get("legal_guardrails", []) or [])
        expansion_backlog = build_expansion_backlog(
            game_request,
            blueprint,
            task_graph,
            content_expansion,
        )
        resume_state = build_resume_state(
            game_request,
            blueprint,
            production_plan,
            task_graph,
            content_expansion,
            expansion_backlog,
            runtime_profile=runtime_selection["profile"],
        )
        return {
            "game_request": game_request,
            "runtime_selection": runtime_selection,
            "blueprint": blueprint,
            "production_plan": production_plan,
            "system_bundle": system_bundle,
            "task_graph": task_graph,
            "content_expansion": content_expansion,
            "asset_pipeline": asset_pipeline,
            "expansion_backlog": expansion_backlog,
            "resume_state": resume_state,
        }

    def _collect_extended_artifacts(self, context: Dict[str, Any]) -> Dict[str, Any]:
        game_request = context["game_request"]
        blueprint = context["blueprint"]
        runtime_selection = context["runtime_selection"]
        production_plan = context["production_plan"]
        system_bundle = context["system_bundle"]
        task_graph = context["task_graph"]
        content_expansion = context["content_expansion"]
        asset_pipeline = context["asset_pipeline"]
        expansion_backlog = context["expansion_backlog"]
        resume_state = context["resume_state"]
        reference_intelligence = dict(runtime_selection.get("reference_intelligence", {}) or {})

        game_program = build_game_program(
            game_request,
            blueprint,
            runtime_profile=runtime_selection["profile"],
        )
        feature_matrix = build_feature_matrix(
            game_request,
            blueprint,
            system_bundle,
            runtime_profile=runtime_selection["profile"],
        )
        content_matrix = build_content_matrix(
            game_request,
            blueprint,
            content_expansion,
            asset_pipeline,
            runtime_profile=runtime_selection["profile"],
        )
        milestone_board = build_milestone_board(
            game_request,
            blueprint,
            production_plan,
            runtime_profile=runtime_selection["profile"],
        )
        risk_register = build_risk_register(
            game_request,
            blueprint,
            runtime_profile=runtime_selection["profile"],
        )
        runtime_capability_graph = build_runtime_capability_graph(game_request, runtime_selection)
        runtime_delivery_plan = build_runtime_delivery_plan(
            game_request,
            blueprint,
            runtime_selection,
            runtime_capability_graph,
            system_bundle=system_bundle,
        )
        character_kits = build_character_kits(
            game_request,
            blueprint,
            content_expansion,
            asset_pipeline,
            runtime_profile=runtime_selection["profile"],
        )
        environment_kits = build_environment_kits(
            game_request,
            blueprint,
            content_expansion,
            asset_pipeline,
            runtime_profile=runtime_selection["profile"],
        )
        animation_plan = build_animation_plan(
            game_request,
            blueprint,
            system_bundle,
            runtime_profile=runtime_selection["profile"],
        )
        asset_budget = build_asset_budget(
            game_request,
            blueprint,
            asset_pipeline,
            content_expansion,
            runtime_profile=runtime_selection["profile"],
        )
        world_program = build_world_program(
            game_request,
            blueprint,
            content_expansion,
            runtime_profile=runtime_selection["profile"],
        )
        region_kits = build_region_kits(
            game_request,
            blueprint,
            content_expansion,
            world_program,
        )
        faction_graph = build_faction_graph(
            game_request,
            blueprint,
            content_expansion,
            runtime_profile=runtime_selection["profile"],
        )
        questline_program = build_questline_program(
            game_request,
            blueprint,
            content_expansion,
            runtime_profile=runtime_selection["profile"],
        )
        save_migration_plan = build_save_migration_plan(
            game_request,
            blueprint,
            system_bundle,
            content_expansion,
            runtime_profile=runtime_selection["profile"],
        )
        gameplay_factory = build_gameplay_factory(
            game_request,
            blueprint,
            system_bundle,
            content_expansion,
            runtime_profile=runtime_selection["profile"],
        )
        boss_arc = build_boss_arc(
            game_request,
            blueprint,
            system_bundle,
            content_expansion,
            runtime_profile=runtime_selection["profile"],
        )
        quality_gates = build_quality_gate_report(
            game_request,
            blueprint,
            system_bundle,
            runtime_profile=runtime_selection["profile"],
            asset_pipeline=asset_pipeline,
        )
        performance_budget = build_performance_budget(
            game_request,
            blueprint,
            asset_pipeline,
            runtime_profile=runtime_selection["profile"],
        )
        combat_feel_report = build_combat_feel_report(
            game_request,
            blueprint,
            system_bundle,
        )
        continuation_recommendations = build_continuation_recommendations(
            game_request,
            blueprint,
            production_plan,
            task_graph,
            expansion_backlog,
            resume_state,
            quality_gates=quality_gates,
            world_program=world_program,
            reference_intelligence=reference_intelligence,
        )
        return {
            "game_program": game_program,
            "feature_matrix": feature_matrix,
            "content_matrix": content_matrix,
            "milestone_board": milestone_board,
            "risk_register": risk_register,
            "reference_intelligence": reference_intelligence,
            "runtime_capability_graph": runtime_capability_graph,
            "runtime_delivery_plan": runtime_delivery_plan,
            "character_kits": character_kits,
            "environment_kits": environment_kits,
            "animation_plan": animation_plan,
            "asset_budget": asset_budget,
            "world_program": world_program,
            "region_kits": region_kits,
            "faction_graph": faction_graph,
            "questline_program": questline_program,
            "save_migration_plan": save_migration_plan,
            "gameplay_factory": gameplay_factory,
            "boss_arc": boss_arc,
            "quality_gates": quality_gates,
            "performance_budget": performance_budget,
            "combat_feel_report": combat_feel_report,
            "continuation_recommendations": continuation_recommendations,
        }

    def _compile_program(
        self,
        request_path: Path,
        blueprint_path: Path,
        output_path: Path,
        kwargs: Dict[str, Any],
    ) -> ToolResult:
        result = self._plan_production(request_path, blueprint_path, output_path, kwargs)
        if not result.success:
            return result
        return ToolResult.ok(
            result.output.replace("Planned production", "Compiled program and planned production"),
            result.data,
        )

    def _create_blueprint(self, request_path: Path, blueprint_path: Path, kwargs: Dict[str, Any]) -> ToolResult:
        overwrite = kwargs.get("overwrite", False)
        if blueprint_path.exists() and not overwrite:
            return ToolResult.fail(
                f"Blueprint already exists at {blueprint_path}. Use overwrite=true to replace it."
            )

        if request_path.exists() or kwargs.get("prompt"):
            game_request = self._load_or_compile_request(request_path, kwargs)
            runtime_selection = select_runtime_profile(
                game_request,
                project_root=self.project_root,
                requested_runtime=kwargs.get("requested_runtime", ""),
                existing_runtime=kwargs.get("existing_runtime", ""),
            )
            blueprint = build_blueprint_from_request(
                game_request,
                runtime_profile=runtime_selection["profile"],
                overrides=kwargs.get("data") or {},
            )
            reference_intelligence = dict(runtime_selection.get("reference_intelligence", {}) or {})
            if reference_intelligence:
                blueprint.setdefault("technical_strategy", {})["reference_strategy"] = {
                    "reference_root": reference_intelligence.get("reference_root", ""),
                    "recommended_stack": list(reference_intelligence.get("recommended_reference_stack", []) or []),
                    "legal_guardrails": list(reference_intelligence.get("legal_guardrails", []) or []),
                }
        else:
            blueprint = self._deep_merge(self._default_blueprint(kwargs), kwargs.get("data") or {})
        blueprint_path.parent.mkdir(parents=True, exist_ok=True)
        blueprint_path.write_text(json.dumps(blueprint, indent=2, ensure_ascii=False), encoding="utf-8")

        systems = blueprint.get("gameplay_blueprint", {}).get("systems", {})
        output = (
            f"Created game blueprint at {blueprint_path}\n"
            f"Project: {blueprint['meta']['project_name']}\n"
            f"Genre: {blueprint['meta']['genre']}\n"
            f"Dimension: {blueprint['meta']['dimension']}\n"
            f"Engine: {blueprint['meta']['target_engine']}\n"
            f"Defined systems: {len(systems)}"
        )
        return ToolResult.ok(
            output,
            {
                "blueprint_path": str(blueprint_path.relative_to(self.project_root)),
                "blueprint": blueprint,
            },
        )

    def _plan_production(
        self,
        request_path: Path,
        blueprint_path: Path,
        output_path: Path,
        kwargs: Dict[str, Any],
    ) -> ToolResult:
        context = self._collect_production_context(request_path, kwargs)
        game_request = context["game_request"]
        runtime_selection = context["runtime_selection"]
        blueprint = context["blueprint"]
        production_plan = context["production_plan"]
        system_bundle = context["system_bundle"]
        task_graph = context["task_graph"]
        content_expansion = context["content_expansion"]
        asset_pipeline = context["asset_pipeline"]
        expansion_backlog = context["expansion_backlog"]
        resume_state = context["resume_state"]
        extended = self._collect_extended_artifacts(context)

        self._write_json_doc(request_path, game_request)
        self._write_json_doc(blueprint_path, blueprint)
        self._write_json_doc(output_path, production_plan)

        system_specs_path = self._resolve_path("artifacts/system_specs.json")
        self._write_json_doc(system_specs_path, system_bundle)

        system_specs_markdown_path = self._resolve_path("artifacts/system_specs.md")
        self._write_text_doc(system_specs_markdown_path, system_packet_markdown(system_bundle))

        task_graph_path = self._resolve_path("artifacts/task_graph.json")
        self._write_json_doc(task_graph_path, task_graph)

        task_graph_markdown_path = self._resolve_path("artifacts/task_graph.md")
        self._write_text_doc(task_graph_markdown_path, task_graph_markdown(task_graph))

        content_expansion_path = self._resolve_path("artifacts/content_expansion.json")
        self._write_json_doc(content_expansion_path, content_expansion)

        content_expansion_markdown_path = self._resolve_path("artifacts/content_expansion.md")
        self._write_text_doc(content_expansion_markdown_path, content_expansion_markdown(content_expansion))

        asset_pipeline_path = self._resolve_path("artifacts/asset_pipeline.json")
        self._write_json_doc(asset_pipeline_path, asset_pipeline)

        asset_pipeline_markdown_path = self._resolve_path("artifacts/asset_pipeline.md")
        self._write_text_doc(asset_pipeline_markdown_path, asset_pipeline_markdown(asset_pipeline))

        expansion_backlog_path = self._resolve_path("artifacts/expansion_backlog.json")
        self._write_json_doc(expansion_backlog_path, expansion_backlog)

        expansion_backlog_markdown_path = self._resolve_path("artifacts/expansion_backlog.md")
        self._write_text_doc(expansion_backlog_markdown_path, expansion_backlog_markdown(expansion_backlog))

        resume_state_path = self._resolve_path("artifacts/resume_state.json")
        self._write_json_doc(resume_state_path, resume_state)

        resume_state_markdown_path = self._resolve_path("artifacts/resume_state.md")
        self._write_text_doc(resume_state_markdown_path, resume_state_markdown(resume_state))

        self._write_json_doc(self._resolve_path("artifacts/game_program.json"), extended["game_program"])
        self._write_text_doc(self._resolve_path("artifacts/game_bible.md"), game_bible_markdown(extended["game_program"]))
        self._write_json_doc(self._resolve_path("artifacts/feature_matrix.json"), extended["feature_matrix"])
        self._write_json_doc(self._resolve_path("artifacts/content_matrix.json"), extended["content_matrix"])
        self._write_json_doc(self._resolve_path("artifacts/milestone_board.json"), extended["milestone_board"])
        self._write_json_doc(self._resolve_path("artifacts/risk_register.json"), extended["risk_register"])
        self._write_json_doc(self._resolve_path("artifacts/reference_intelligence.json"), extended["reference_intelligence"])
        self._write_json_doc(self._resolve_path("artifacts/runtime_capability_graph.json"), extended["runtime_capability_graph"])
        self._write_json_doc(self._resolve_path("artifacts/runtime_delivery_plan.json"), extended["runtime_delivery_plan"])
        self._write_json_doc(self._resolve_path("artifacts/character_kits.json"), extended["character_kits"])
        self._write_json_doc(self._resolve_path("artifacts/environment_kits.json"), extended["environment_kits"])
        self._write_json_doc(self._resolve_path("artifacts/animation_plan.json"), extended["animation_plan"])
        self._write_json_doc(self._resolve_path("artifacts/asset_budget.json"), extended["asset_budget"])
        self._write_json_doc(self._resolve_path("artifacts/world_program.json"), extended["world_program"])
        self._write_json_doc(self._resolve_path("artifacts/region_kits.json"), extended["region_kits"])
        self._write_json_doc(self._resolve_path("artifacts/faction_graph.json"), extended["faction_graph"])
        self._write_json_doc(self._resolve_path("artifacts/questline_program.json"), extended["questline_program"])
        self._write_json_doc(self._resolve_path("artifacts/save_migration_plan.json"), extended["save_migration_plan"])
        self._write_json_doc(self._resolve_path("artifacts/gameplay_factory.json"), extended["gameplay_factory"])
        self._write_json_doc(self._resolve_path("artifacts/boss_arc.json"), extended["boss_arc"])
        self._write_json_doc(self._resolve_path("playtest/quality_gates.json"), extended["quality_gates"])
        self._write_json_doc(self._resolve_path("playtest/performance_budget.json"), extended["performance_budget"])
        self._write_json_doc(self._resolve_path("playtest/combat_feel_report.json"), extended["combat_feel_report"])
        self._write_text_doc(
            self._resolve_path("playtest/continuation_recommendations.md"),
            continuation_recommendations_markdown(extended["continuation_recommendations"]),
        )

        runtime_registry_path = self._resolve_path("artifacts/runtime_registry.json")
        runtime_registry_payload = {
            "selected_runtime": runtime_selection["selected_runtime"],
            "reason": runtime_selection["reason"],
            "fallback_reason": runtime_selection["fallback_reason"],
            "profiles": discover_runtime_profiles(self.project_root),
            "reference_alignment": runtime_selection.get("reference_alignment", {}),
        }
        runtime_registry_path.parent.mkdir(parents=True, exist_ok=True)
        runtime_registry_path.write_text(
            json.dumps(runtime_registry_payload, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )

        output = (
            f"Planned production at {output_path}\n"
            f"Project: {blueprint['meta']['project_name']}\n"
            f"Runtime: {runtime_selection['selected_runtime']}\n"
            f"Scope: {blueprint['meta']['scope']}\n"
            f"Lanes: {len(production_plan.get('lanes', []))}\n"
            f"System packets: {len(system_bundle.get('packets', {}))}"
        )
        return ToolResult.ok(
            output,
            {
                "request_path": str(request_path.relative_to(self.project_root)),
                "blueprint_path": str(blueprint_path.relative_to(self.project_root)),
                "output_path": str(output_path.relative_to(self.project_root)),
                "runtime_registry_path": str(runtime_registry_path.relative_to(self.project_root)),
                "reference_intelligence_path": "artifacts/reference_intelligence.json",
                "system_specs_path": str(system_specs_path.relative_to(self.project_root)),
                "task_graph_path": str(task_graph_path.relative_to(self.project_root)),
                "content_expansion_path": str(content_expansion_path.relative_to(self.project_root)),
                "asset_pipeline_path": str(asset_pipeline_path.relative_to(self.project_root)),
                "expansion_backlog_path": str(expansion_backlog_path.relative_to(self.project_root)),
                "resume_state_path": str(resume_state_path.relative_to(self.project_root)),
                "production_plan": production_plan,
                "system_bundle": system_bundle,
                "task_graph": task_graph,
                "content_expansion": content_expansion,
                "asset_pipeline": asset_pipeline,
                "expansion_backlog": expansion_backlog,
                "resume_state": resume_state,
                "game_program": extended["game_program"],
                "reference_intelligence": extended["reference_intelligence"],
                "runtime_capability_graph": extended["runtime_capability_graph"],
                "runtime_delivery_plan": extended["runtime_delivery_plan"],
                "character_kits": extended["character_kits"],
                "environment_kits": extended["environment_kits"],
                "animation_plan": extended["animation_plan"],
                "asset_budget": extended["asset_budget"],
                "world_program": extended["world_program"],
                "region_kits": extended["region_kits"],
                "faction_graph": extended["faction_graph"],
                "questline_program": extended["questline_program"],
                "save_migration_plan": extended["save_migration_plan"],
                "gameplay_factory": extended["gameplay_factory"],
                "boss_arc": extended["boss_arc"],
                "quality_gates": extended["quality_gates"],
                "performance_budget": extended["performance_budget"],
                "combat_feel_report": extended["combat_feel_report"],
            },
        )

    def _expand_system(self, blueprint_path: Path, system_name: str, data: Dict[str, Any]) -> ToolResult:
        blueprint = self._load_or_create_blueprint(blueprint_path, {})
        systems = blueprint.setdefault("gameplay_blueprint", {}).setdefault("systems", {})
        system_key = self._slugify(system_name)
        system_spec = self._deep_merge(self._default_system_spec(system_name), data)
        systems[system_key] = system_spec

        blueprint_path.parent.mkdir(parents=True, exist_ok=True)
        blueprint_path.write_text(json.dumps(blueprint, indent=2, ensure_ascii=False), encoding="utf-8")

        output = (
            f"Expanded system '{system_name}' in {blueprint_path}\n"
            f"Hooks: {len(system_spec.get('progression_hooks', []))}\n"
            f"Tuning knobs: {len(system_spec.get('tuning_knobs', []))}\n"
            f"Telemetry events: {len(system_spec.get('telemetry', []))}"
        )
        return ToolResult.ok(
            output,
            {
                "blueprint_path": str(blueprint_path.relative_to(self.project_root)),
                "system_key": system_key,
                "system": system_spec,
            },
        )

    def _generate_gameplay_factory(
        self,
        request_path: Path,
        blueprint_path: Path,
        output_path: Path,
        kwargs: Dict[str, Any],
    ) -> ToolResult:
        context = self._collect_production_context(request_path, kwargs)
        extended = self._collect_extended_artifacts(context)
        self._write_json_doc(output_path, extended["gameplay_factory"])
        return ToolResult.ok(
            f"Generated gameplay factory at {output_path}",
            {
                "output_path": str(output_path.relative_to(self.project_root)),
                "gameplay_factory": extended["gameplay_factory"],
            },
        )

    def _plan_boss_arc(
        self,
        request_path: Path,
        blueprint_path: Path,
        output_path: Path,
        kwargs: Dict[str, Any],
    ) -> ToolResult:
        context = self._collect_production_context(request_path, kwargs)
        extended = self._collect_extended_artifacts(context)
        self._write_json_doc(output_path, extended["boss_arc"])
        return ToolResult.ok(
            f"Generated boss arc at {output_path}",
            {
                "output_path": str(output_path.relative_to(self.project_root)),
                "boss_arc": extended["boss_arc"],
            },
        )

    def _expand_region(
        self,
        request_path: Path,
        blueprint_path: Path,
        output_path: Path,
        kwargs: Dict[str, Any],
    ) -> ToolResult:
        region_id = str(kwargs.get("region_id") or "").strip()
        if not region_id:
            return ToolResult.fail("region_id is required for expand_region")
        context = self._collect_production_context(request_path, kwargs)
        extended = self._collect_extended_artifacts(context)
        expansion = build_region_expansion_plan(
            region_id,
            extended["region_kits"],
            extended["world_program"],
        )
        self._write_json_doc(output_path, expansion)
        return ToolResult.ok(
            f"Generated region expansion at {output_path}",
            {
                "output_path": str(output_path.relative_to(self.project_root)),
                "region_expansion": expansion,
            },
        )

    def _generate_character_kit(
        self,
        request_path: Path,
        blueprint_path: Path,
        output_path: Path,
        kwargs: Dict[str, Any],
    ) -> ToolResult:
        character_id = str(kwargs.get("character_id") or "").strip()
        context = self._collect_production_context(request_path, kwargs)
        extended = self._collect_extended_artifacts(context)
        payload = extended["character_kits"]
        if character_id:
            selected = None
            if character_id == "player_avatar":
                selected = payload.get("hero_kit")
            else:
                for item in payload.get("npc_kits", []) + payload.get("enemy_kits", []):
                    if str(item.get("id", "")).strip() == character_id:
                        selected = item
                        break
            if selected is not None:
                payload = {"selected_kit": selected, "character_kits": extended["character_kits"]}
        self._write_json_doc(output_path, payload)
        return ToolResult.ok(
            f"Generated character kit data at {output_path}",
            {
                "output_path": str(output_path.relative_to(self.project_root)),
                "character_kits": payload,
            },
        )

    def _build_enemy_faction(
        self,
        request_path: Path,
        blueprint_path: Path,
        output_path: Path,
        kwargs: Dict[str, Any],
    ) -> ToolResult:
        faction_id = str(kwargs.get("faction_id") or "").strip()
        if not faction_id:
            return ToolResult.fail("faction_id is required for build_enemy_faction")
        context = self._collect_production_context(request_path, kwargs)
        extended = self._collect_extended_artifacts(context)
        payload = build_enemy_faction_packet(faction_id, extended["faction_graph"])
        self._write_json_doc(output_path, payload)
        return ToolResult.ok(
            f"Generated enemy faction packet at {output_path}",
            {
                "output_path": str(output_path.relative_to(self.project_root)),
                "enemy_faction": payload,
            },
        )

    def _generate_vertical_slice(
        self, request_path: Path, blueprint_path: Path, output_path: Path, data: Dict[str, Any]
    ) -> ToolResult:
        blueprint = self._load_or_create_blueprint(blueprint_path, {})
        game_request = self._load_request(request_path)
        if game_request:
            runtime_selection = select_runtime_profile(
                game_request,
                project_root=self.project_root,
                requested_runtime="",
                existing_runtime="",
            )
            slice_plan = self._deep_merge(
                build_vertical_slice_plan(
                    game_request,
                    blueprint,
                    runtime_profile=runtime_selection["profile"],
                ),
                data,
            )
            markdown = vertical_slice_markdown(slice_plan)
        else:
            slice_plan = self._build_vertical_slice(blueprint, data)
            markdown = self._vertical_slice_to_markdown(slice_plan)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(markdown, encoding="utf-8")

        output = (
            f"Generated vertical slice plan at {output_path}\n"
            f"Feature lanes: {len(slice_plan.get('feature_lanes', []))}\n"
            f"Quality gates: {len(slice_plan.get('quality_gates', []))}\n"
            f"Critical risks: {len(slice_plan.get('critical_risks', []))}"
        )
        return ToolResult.ok(
            output,
            {
                "output_path": str(output_path.relative_to(self.project_root)),
                "slice_plan": slice_plan,
            },
        )

    def _analyze_scope(self, blueprint_path: Path, kwargs: Dict[str, Any]) -> ToolResult:
        blueprint = self._load_or_create_blueprint(blueprint_path, kwargs)
        analysis = self._scope_analysis(blueprint)

        output = (
            "Scope Analysis:\n\n"
            f"Risk tier: {analysis['risk_tier']}\n"
            f"Complexity score: {analysis['complexity_score']}\n"
            f"Dimension pressure: {analysis['dimension_pressure']}\n"
            f"Systems counted: {analysis['system_count']}\n"
            f"Recommended order: {', '.join(analysis['recommended_order'])}\n"
            f"Major gaps: {', '.join(analysis['major_gaps']) if analysis['major_gaps'] else 'none'}\n"
        )
        if analysis["recommendations"]:
            output += "\nRecommendations:\n"
            for item in analysis["recommendations"]:
                output += f"- {item}\n"

        return ToolResult.ok(output, analysis)

    def _export_markdown(self, blueprint_path: Path, output_path: Path) -> ToolResult:
        if not blueprint_path.exists():
            return ToolResult.fail(f"Blueprint not found at {blueprint_path}")

        blueprint = json.loads(blueprint_path.read_text(encoding="utf-8"))
        markdown = self._dict_to_markdown(blueprint, title=blueprint.get("meta", {}).get("project_name", "Game Blueprint"))

        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(markdown, encoding="utf-8")
        return ToolResult.ok(
            f"Exported blueprint markdown to {output_path}",
            {
                "output_path": str(output_path.relative_to(self.project_root)),
                "markdown_length": len(markdown),
            },
        )

    def _load_or_create_blueprint(self, blueprint_path: Path, kwargs: Dict[str, Any]) -> Dict[str, Any]:
        if blueprint_path.exists():
            return json.loads(blueprint_path.read_text(encoding="utf-8"))
        return self._default_blueprint(kwargs)

    def _load_request(self, request_path: Path) -> Dict[str, Any]:
        if not request_path.exists():
            return {}
        try:
            return json.loads(request_path.read_text(encoding="utf-8"))
        except Exception:
            return {}

    def _load_or_compile_request(self, request_path: Path, kwargs: Dict[str, Any]) -> Dict[str, Any]:
        existing = self._load_request(request_path)
        if existing:
            return existing
        return compile_game_prompt(
            self._resolve_prompt(kwargs),
            project_name=kwargs.get("project_name", ""),
            requested_runtime=kwargs.get("requested_runtime", ""),
            existing_runtime=kwargs.get("existing_runtime", ""),
            overrides=kwargs.get("data") or kwargs,
        )

    def _resolve_prompt(self, kwargs: Dict[str, Any]) -> str:
        prompt = str(kwargs.get("prompt") or "").strip()
        if prompt:
            return prompt
        fragments = [
            kwargs.get("project_name", ""),
            kwargs.get("genre", ""),
            kwargs.get("dimension", ""),
            kwargs.get("camera_model", ""),
            " ".join(kwargs.get("pillars") or []),
            " ".join(kwargs.get("references") or []),
        ]
        fallback = " ".join(str(fragment).strip() for fragment in fragments if str(fragment).strip())
        return fallback or "Build a game vertical slice with a clear core loop and production-ready foundation."

    def _default_blueprint(self, kwargs: Dict[str, Any]) -> Dict[str, Any]:
        project_name = kwargs.get("project_name", "Untitled Game")
        genre = kwargs.get("genre", "Action Adventure")
        dimension = kwargs.get("dimension", "2D")
        target_engine = canonical_engine_name(kwargs.get("target_engine", "reverie_engine"))
        camera_model = kwargs.get("camera_model", self._default_camera_for_dimension(dimension))
        scope = kwargs.get("scope", "full_game")
        pillars = kwargs.get("pillars") or [
            "Immediate player fantasy",
            "Depth from interacting systems",
            "Readable feedback and strong pacing",
        ]
        references = kwargs.get("references") or []

        return {
            "meta": {
                "project_name": project_name,
                "genre": genre,
                "dimension": dimension,
                "target_engine": target_engine,
                "camera_model": camera_model,
                "scope": scope,
                "created_at": datetime.utcnow().isoformat(timespec="seconds") + "Z",
            },
            "creative_direction": {
                "pillars": pillars,
                "player_fantasy": "Master a deep gameplay loop that stays readable under pressure.",
                "tone": "Confident, atmospheric, and mechanically expressive",
                "references": references,
                "art_direction": {
                    "visual_language": "Readable silhouettes, strong contrast, clear thematic motifs",
                    "animation_feel": "Snappy anticipation and generous impact frames",
                    "audio_feel": "Layered feedback that supports gameplay clarity",
                },
            },
            "gameplay_blueprint": {
                "core_loop": [
                    "Scout the current objective or space",
                    "Engage with the main mechanic under constraint",
                    "Claim a reward that feeds build progression",
                    "Unlock a new tactical decision for the next run",
                ],
                "meta_loop": [
                    "Complete missions or runs",
                    "Invest in persistent growth",
                    "Unlock harder encounters and richer content sets",
                ],
                "player_verbs": ["move", "observe", "interact", "fight", "upgrade"],
                "systems": {
                    "combat": self._default_system_spec("Combat"),
                    "progression": self._default_system_spec("Progression"),
                    "content_delivery": self._default_system_spec("Content Delivery"),
                },
            },
            "content_strategy": {
                "world_structure": "Start with one polished biome or district, then scale by rules and variants",
                "encounter_families": ["trash", "elite", "boss", "puzzle", "set_piece"],
                "reward_types": ["power", "currency", "narrative", "cosmetic", "mobility"],
                "replayability_hooks": ["branching upgrades", "remixed encounters", "challenge modifiers"],
            },
            "technical_strategy": {
                "runtime": {
                    "engine_profile": target_engine,
                    "rendering_target": dimension,
                    "save_system": "Versioned slot saves with migration path",
                    "telemetry": "Track funnel, failure points, economy sinks, and performance spikes",
                    "entry_scene": "data/scenes/main.relscene.json" if is_builtin_engine_name(target_engine) else "",
                    "scene_format": ".relscene.json" if is_builtin_engine_name(target_engine) else "",
                    "prefab_format": ".relprefab.json" if is_builtin_engine_name(target_engine) else "",
                },
                "quality_bars": {
                    "input_feel": "Actions are readable within one short play session",
                    "performance": "Stable frame pacing for the target camera density",
                    "testability": "Core systems support repeatable smoke and simulation checks",
                },
            },
            "production_strategy": {
                "vertical_slice_goals": [
                    "Demonstrate the main fantasy in 10-20 minutes",
                    "Prove one progression loop and one content loop",
                    "Show the final quality target for feel and presentation",
                ],
                "major_risks": [
                    "Scope expansion before the first playable loop is stable",
                    "Content production outrunning tool and pipeline maturity",
                    "Late discovery of feel or readability problems",
                ],
                "definition_of_done": [
                    "Core loop is fun and repeatable",
                    "Save/load, UI flow, and critical content are integrated",
                    "Tests, smoke runs, and playtest gates pass",
                ],
            },
        }

    def _default_system_spec(self, system_name: str) -> Dict[str, Any]:
        return {
            "name": system_name,
            "fantasy": f"{system_name} should create clear choices, escalation, and readable mastery.",
            "player_inputs": ["primary action", "secondary action", "movement modifier"],
            "state_machine": ["idle", "engage", "resolve", "reward"],
            "resources": ["time", "positioning", "currency", "cooldowns"],
            "progression_hooks": [
                "unlock new options",
                "raise mastery ceiling",
                "introduce a stronger trade-off",
            ],
            "tuning_knobs": ["damage", "speed", "spawn rate", "reward rate"],
            "failure_modes": [
                "dominant strategy with no cost",
                "too much randomness for the intended skill test",
                "poor feedback during fast interactions",
            ],
            "telemetry": [
                "session_start",
                "session_end",
                "system_success",
                "system_failure",
                "economy_delta",
            ],
            "tests": [
                "unit coverage for deterministic rules",
                "simulation coverage for edge distributions",
                "smoke path through the real runtime",
            ],
        }

    def _build_vertical_slice(self, blueprint: Dict[str, Any], overrides: Dict[str, Any]) -> Dict[str, Any]:
        meta = blueprint.get("meta", {})
        creative = blueprint.get("creative_direction", {})
        gameplay = blueprint.get("gameplay_blueprint", {})
        systems = gameplay.get("systems", {})
        system_names = [spec.get("name", key) for key, spec in systems.items()]

        slice_plan = {
            "project_name": meta.get("project_name", "Untitled Game"),
            "target_runtime": f"{meta.get('dimension', '2D')} / {canonical_engine_name(meta.get('target_engine', 'reverie_engine'))}",
            "pillars": creative.get("pillars", []),
            "feature_lanes": [
                "one complete moment-to-moment gameplay loop",
                "one onboarding sequence with teachable friction",
                "one progression upgrade choice with visible consequences",
                "one polished content set showing final art and audio intent",
            ],
            "systems_in_scope": system_names[:4],
            "content_budget": {
                "playable_spaces": 1 if meta.get("scope") == "prototype" else 2,
                "enemy_families": 2,
                "bosses": 1,
                "ui_flows": ["boot", "play", "upgrade", "result"],
            },
            "quality_gates": [
                "new player can finish the slice without external guidance",
                "frame pacing stays stable during the busiest encounter",
                "failure is understandable and encourages one more try",
                "core loop remains fun for at least three consecutive runs",
            ],
            "critical_risks": [
                "first 5 minutes do not communicate the fantasy quickly enough",
                "content scripting is slower than system implementation",
                "camera and readability break under stress",
            ],
            "verification": {
                "required_tests": [
                    "unit tests for core rules",
                    "integration tests for save/load and progression",
                    "runtime smoke test through the critical path",
                    "telemetry capture for funnel and failure analysis",
                ],
                "playtest_questions": [
                    "What felt powerful or expressive?",
                    "Where did the player hesitate or misunderstand?",
                    "When did motivation spike or drop?",
                ],
            },
        }

        return self._deep_merge(slice_plan, overrides)

    def _scope_analysis(self, blueprint: Dict[str, Any]) -> Dict[str, Any]:
        meta = blueprint.get("meta", {})
        gameplay = blueprint.get("gameplay_blueprint", {})
        content = blueprint.get("content_strategy", {})
        systems = gameplay.get("systems", {})
        dimension = str(meta.get("dimension", "2D")).lower()

        dimension_pressure = 1
        if "2.5" in dimension:
            dimension_pressure = 2
        elif "3" in dimension:
            dimension_pressure = 3

        complexity_score = len(systems) * 12 + dimension_pressure * 15
        complexity_score += len(content.get("encounter_families", [])) * 4
        complexity_score += len(content.get("replayability_hooks", [])) * 3

        major_gaps = []
        runtime = blueprint.get("technical_strategy", {}).get("runtime", {})
        production = blueprint.get("production_strategy", {})
        if not gameplay.get("core_loop"):
            major_gaps.append("missing core loop")
        if not systems:
            major_gaps.append("missing system breakdown")
        if not runtime.get("save_system"):
            major_gaps.append("missing save/load plan")
        if not runtime.get("telemetry"):
            major_gaps.append("missing telemetry plan")
        if not production.get("vertical_slice_goals"):
            major_gaps.append("missing vertical slice goals")

        if complexity_score >= 90:
            risk_tier = "high"
        elif complexity_score >= 55:
            risk_tier = "medium"
        else:
            risk_tier = "low"

        recommendations: List[str] = []
        if dimension_pressure >= 3:
            recommendations.append("Lock camera, traversal, and asset style early before adding wide content scope.")
        if len(systems) >= 5:
            recommendations.append("Deliver one vertical slice before building all systems in parallel.")
        if "full_game" == meta.get("scope") and len(systems) >= 4:
            recommendations.append("Split work into foundation, first playable, vertical slice, and production scaling milestones.")
        if not runtime.get("telemetry"):
            recommendations.append("Add telemetry before larger playtests so balancing work compounds.")

        recommended_order = [
            "core loop",
            "input feel",
            "save/load and data schema",
            "vertical slice content",
            "telemetry and playtest analysis",
        ]

        return {
            "risk_tier": risk_tier,
            "complexity_score": complexity_score,
            "dimension_pressure": dimension_pressure,
            "system_count": len(systems),
            "major_gaps": major_gaps,
            "recommended_order": recommended_order,
            "recommendations": recommendations,
        }

    def _vertical_slice_to_markdown(self, slice_plan: Dict[str, Any]) -> str:
        lines = [f"# {slice_plan.get('project_name', 'Vertical Slice Plan')}", ""]
        lines.append(f"Target Runtime: {slice_plan.get('target_runtime', 'unknown')}")
        lines.append("")
        lines.append("## Pillars")
        for pillar in slice_plan.get("pillars", []):
            lines.append(f"- {pillar}")
        lines.append("")
        lines.append("## Feature Lanes")
        for lane in slice_plan.get("feature_lanes", []):
            lines.append(f"- {lane}")
        lines.append("")
        lines.append("## Systems In Scope")
        for system_name in slice_plan.get("systems_in_scope", []):
            lines.append(f"- {system_name}")
        lines.append("")
        lines.append("## Quality Gates")
        for gate in slice_plan.get("quality_gates", []):
            lines.append(f"- {gate}")
        lines.append("")
        lines.append("## Critical Risks")
        for risk in slice_plan.get("critical_risks", []):
            lines.append(f"- {risk}")
        lines.append("")
        verification = slice_plan.get("verification", {})
        lines.append("## Verification")
        for test_name in verification.get("required_tests", []):
            lines.append(f"- {test_name}")
        lines.append("")
        lines.append("## Playtest Questions")
        for question in verification.get("playtest_questions", []):
            lines.append(f"- {question}")
        lines.append("")
        return "\n".join(lines)

    def _dict_to_markdown(self, data: Dict[str, Any], title: str) -> str:
        lines = [f"# {title}", ""]
        lines.extend(self._markdown_lines(data, level=2))
        return "\n".join(lines)

    def _markdown_lines(self, value: Any, level: int, key_name: str = "") -> List[str]:
        lines: List[str] = []
        if isinstance(value, dict):
            for key, item in value.items():
                lines.append(f"{'#' * level} {key}")
                lines.extend(self._markdown_lines(item, level + 1, key))
                lines.append("")
            return lines

        if isinstance(value, list):
            if not value:
                lines.append("- none")
            for item in value:
                if isinstance(item, (dict, list)):
                    lines.extend(self._markdown_lines(item, level, key_name))
                else:
                    lines.append(f"- {item}")
            return lines

        lines.append(str(value))
        return lines

    def _deep_merge(self, base: Dict[str, Any], updates: Dict[str, Any]) -> Dict[str, Any]:
        merged = dict(base)
        for key, value in (updates or {}).items():
            if isinstance(value, dict) and isinstance(merged.get(key), dict):
                merged[key] = self._deep_merge(merged[key], value)
            else:
                merged[key] = value
        return merged

    def _slugify(self, text: str) -> str:
        cleaned = "".join(ch.lower() if ch.isalnum() else "_" for ch in str(text))
        while "__" in cleaned:
            cleaned = cleaned.replace("__", "_")
        return cleaned.strip("_") or "system"

    def _default_camera_for_dimension(self, dimension: str) -> str:
        normalized = str(dimension).lower()
        if "3" in normalized:
            return "third_person"
        if "2.5" in normalized:
            return "isometric"
        return "side_view"

    def _resolve_path(self, raw: str) -> Path:
        return self.resolve_workspace_path(raw, purpose="resolve game design orchestrator path")

    def get_execution_message(self, **kwargs) -> str:
        return f"Game design orchestration: {kwargs.get('action', 'unknown')}"
