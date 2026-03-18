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


class GameDesignOrchestratorTool(BaseTool):
    name = "game_design_orchestrator"
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
                    "create_blueprint",
                    "expand_system",
                    "generate_vertical_slice",
                    "analyze_scope",
                    "export_markdown",
                ],
                "description": "Design orchestration action",
            },
            "blueprint_path": {
                "type": "string",
                "description": "Blueprint JSON path (default: docs/game_blueprint.json)",
            },
            "output_path": {
                "type": "string",
                "description": "Optional export path for markdown outputs",
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
            "system_name": {
                "type": "string",
                "description": "System name for expand_system",
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
        blueprint_path = self._resolve_path(kwargs.get("blueprint_path", "docs/game_blueprint.json"))

        try:
            if action == "create_blueprint":
                return self._create_blueprint(blueprint_path, kwargs)
            if action == "expand_system":
                system_name = kwargs.get("system_name")
                if not system_name:
                    return ToolResult.fail("system_name is required for expand_system")
                return self._expand_system(blueprint_path, system_name, kwargs.get("data") or {})
            if action == "generate_vertical_slice":
                output_path = self._resolve_path(
                    kwargs.get("output_path", "docs/vertical_slice_plan.md")
                )
                return self._generate_vertical_slice(blueprint_path, output_path, kwargs.get("data") or {})
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

    def _create_blueprint(self, blueprint_path: Path, kwargs: Dict[str, Any]) -> ToolResult:
        overwrite = kwargs.get("overwrite", False)
        if blueprint_path.exists() and not overwrite:
            return ToolResult.fail(
                f"Blueprint already exists at {blueprint_path}. Use overwrite=true to replace it."
            )

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

    def _generate_vertical_slice(
        self, blueprint_path: Path, output_path: Path, data: Dict[str, Any]
    ) -> ToolResult:
        blueprint = self._load_or_create_blueprint(blueprint_path, {})
        slice_plan = self._build_vertical_slice(blueprint, data)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(self._vertical_slice_to_markdown(slice_plan), encoding="utf-8")

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
