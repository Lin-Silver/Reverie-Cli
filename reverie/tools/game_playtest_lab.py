"""
Game Playtest Lab Tool.

Turns design intent into repeatable quality gates, telemetry schemas, and
playtest analysis workflows that can guide iterative game development.
"""

from __future__ import annotations

from typing import Optional, Dict, Any, List
from pathlib import Path
from collections import Counter
import csv
import json

from .base import BaseTool, ToolResult
from ..engine import is_builtin_engine_name
from ..gamer.continuation_director import (
    build_continuation_recommendations,
    continuation_recommendations_markdown,
)
from ..gamer.verification import (
    build_combat_feel_report,
    build_performance_budget,
    build_quality_gate_report,
)


class GamePlaytestLabTool(BaseTool):
    name = "game_playtest_lab"
    aliases = ("playtest_lab",)
    search_hint = "create playtest plans telemetry and quality gates"
    tool_category = "game-playtest"
    tool_tags = ("game", "playtest", "telemetry", "quality", "feedback", "session")
    description = (
        "Create playtest plans, telemetry schemas, quality gates, and analyze "
        "session logs or playtest feedback for game development."
    )

    parameters = {
        "type": "object",
        "properties": {
            "action": {
                "type": "string",
                "enum": [
                    "create_test_plan",
                    "generate_telemetry_schema",
                    "create_quality_gates",
                    "run_quality_gates",
                    "score_combat_feel",
                    "plan_next_iteration",
                    "analyze_session_log",
                    "synthesize_feedback",
                ],
                "description": "Playtest laboratory action",
            },
            "blueprint_path": {
                "type": "string",
                "description": "Optional game blueprint path for context",
            },
            "request_path": {
                "type": "string",
                "description": "Optional game request path (default: artifacts/game_request.json)",
            },
            "system_specs_path": {
                "type": "string",
                "description": "Optional system specs path (default: artifacts/system_specs.json)",
            },
            "asset_pipeline_path": {
                "type": "string",
                "description": "Optional asset pipeline path (default: artifacts/asset_pipeline.json)",
            },
            "task_graph_path": {
                "type": "string",
                "description": "Optional task graph path (default: artifacts/task_graph.json)",
            },
            "production_plan_path": {
                "type": "string",
                "description": "Optional production plan path (default: artifacts/production_plan.json)",
            },
            "expansion_backlog_path": {
                "type": "string",
                "description": "Optional expansion backlog path (default: artifacts/expansion_backlog.json)",
            },
            "resume_state_path": {
                "type": "string",
                "description": "Optional resume state path (default: artifacts/resume_state.json)",
            },
            "world_program_path": {
                "type": "string",
                "description": "Optional world program path (default: artifacts/world_program.json)",
            },
            "production_directive_path": {
                "type": "string",
                "description": "Optional production directive path (default: artifacts/production_directive.json)",
            },
            "output_path": {
                "type": "string",
                "description": "Path for generated plan/schema output",
            },
            "session_log_path": {
                "type": "string",
                "description": "Path to a session log file for analysis",
            },
            "feedback_path": {
                "type": "string",
                "description": "Path to feedback notes or survey export",
            },
            "test_focus": {
                "type": "string",
                "description": "Focus area such as tutorial, combat, economy, progression, or full_loop",
            },
            "session_minutes": {
                "type": "integer",
                "description": "Planned test session length in minutes",
            },
            "audience": {
                "type": "string",
                "description": "Target tester audience such as new_players or genre_veterans",
            },
            "data": {
                "type": "object",
                "description": "Optional inline data for test plans or feedback synthesis",
            },
        },
        "required": ["action"],
    }

    def __init__(self, context: Optional[Dict] = None):
        super().__init__(context)
        self.project_root = Path(context.get("project_root")) if context and context.get("project_root") else Path.cwd()

    def execute(self, **kwargs) -> ToolResult:
        action = kwargs.get("action")

        try:
            if action == "create_test_plan":
                output_path = self._resolve_path(kwargs.get("output_path", "playtest/test_plan.md"))
                return self._create_test_plan(output_path, kwargs)
            if action == "generate_telemetry_schema":
                output_path = self._resolve_path(kwargs.get("output_path", "telemetry/schema.json"))
                return self._generate_telemetry_schema(output_path, kwargs)
            if action == "create_quality_gates":
                output_path = self._resolve_path(kwargs.get("output_path", "playtest/quality_gates.json"))
                return self._create_quality_gates(output_path, kwargs)
            if action == "run_quality_gates":
                output_path = self._resolve_path(kwargs.get("output_path", "playtest/quality_gates.json"))
                return self._run_quality_gates(output_path, kwargs)
            if action == "score_combat_feel":
                output_path = self._resolve_path(kwargs.get("output_path", "playtest/combat_feel_report.json"))
                return self._score_combat_feel(output_path, kwargs)
            if action == "plan_next_iteration":
                output_path = self._resolve_path(kwargs.get("output_path", "playtest/continuation_recommendations.md"))
                return self._plan_next_iteration(output_path, kwargs)
            if action == "analyze_session_log":
                log_path = kwargs.get("session_log_path")
                if not log_path:
                    return ToolResult.fail("session_log_path is required for analyze_session_log")
                return self._analyze_session_log(self._resolve_path(log_path))
            if action == "synthesize_feedback":
                return self._synthesize_feedback(kwargs)
            return ToolResult.fail(f"Unknown action: {action}")
        except Exception as exc:
            return ToolResult.fail(f"Error executing {action}: {str(exc)}")

    def _create_test_plan(self, output_path: Path, kwargs: Dict[str, Any]) -> ToolResult:
        blueprint = self._load_blueprint(kwargs.get("blueprint_path"))
        meta = blueprint.get("meta", {})
        gameplay = blueprint.get("gameplay_blueprint", {})
        focus = kwargs.get("test_focus", "full_loop")
        session_minutes = kwargs.get("session_minutes", 30)
        audience = kwargs.get("audience", "new_players")

        lines = [
            f"# Playtest Plan: {meta.get('project_name', 'Untitled Game')}",
            "",
            f"- Focus: {focus}",
            f"- Audience: {audience}",
            f"- Session Length: {session_minutes} minutes",
            "",
            "## Objectives",
            "- Verify that the core fantasy is understandable within the opening minutes.",
            "- Observe where players hesitate, fail, or misunderstand the intended loop.",
            "- Measure whether reward pacing motivates another run or another mission.",
            "",
            "## Test Script",
            "- Intro: explain only the absolute minimum controls and goal.",
            "- First task: ask the player to reach the first meaningful interaction without hints.",
            "- Main loop: observe one complete loop from challenge to reward.",
            "- Reflection: capture what felt strong, confusing, or repetitive.",
            "",
            "## Systems Under Observation",
        ]

        for system_name in gameplay.get("systems", {}).keys():
            lines.append(f"- {system_name}")
        if not gameplay.get("systems"):
            lines.append("- core loop")

        lines.extend(
            [
                "",
                "## Metrics",
                "- Time to first success",
                "- Time to first failure",
                "- Abandon or confusion points",
                "- Retry count",
                "- Upgrade or reward engagement rate",
                "",
                "## Moderator Questions",
                "- What did you believe the game wanted you to do next?",
                "- What felt satisfying or expressive?",
                "- Where did the game fail to explain itself through play?",
                "",
            ]
        )

        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text("\n".join(lines), encoding="utf-8")
        return ToolResult.ok(
            f"Created playtest plan at {output_path}",
            {"output_path": str(output_path.relative_to(self.project_root)), "focus": focus},
        )

    def _generate_telemetry_schema(self, output_path: Path, kwargs: Dict[str, Any]) -> ToolResult:
        blueprint = self._load_blueprint(kwargs.get("blueprint_path"))
        systems = blueprint.get("gameplay_blueprint", {}).get("systems", {})
        focus = kwargs.get("test_focus", "full_loop")
        target_engine = blueprint.get("meta", {}).get("target_engine", "")

        events = [
            self._event_schema("session_start", ["build_id", "profile_id", "entry_point"]),
            self._event_schema("session_end", ["duration_seconds", "result", "quit_reason"]),
            self._event_schema("checkpoint", ["checkpoint_id", "elapsed_seconds"]),
            self._event_schema("failure", ["reason", "location", "loadout"]),
            self._event_schema("reward_claimed", ["reward_type", "amount", "source"]),
        ]

        for system_name, system_spec in systems.items():
            telemetry = system_spec.get("telemetry", [])
            for event_name in telemetry:
                events.append(
                    self._event_schema(
                        f"{system_name}_{event_name}",
                        ["difficulty", "loadout", "state", "outcome"],
                    )
                )

        schema = {
            "focus": focus,
            "common_dimensions": ["build_id", "session_id", "level_id", "difficulty"],
            "events": self._unique_events(events),
        }
        if is_builtin_engine_name(target_engine):
            schema["common_dimensions"].extend(["scene_id", "node_name", "prefab_id"])

        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(json.dumps(schema, indent=2, ensure_ascii=False), encoding="utf-8")
        return ToolResult.ok(
            f"Generated telemetry schema at {output_path}",
            {
                "output_path": str(output_path.relative_to(self.project_root)),
                "event_count": len(schema["events"]),
            },
        )

    def _create_quality_gates(self, output_path: Path, kwargs: Dict[str, Any]) -> ToolResult:
        focus = kwargs.get("test_focus", "full_loop")
        gates = {
            "prototype": [
                "core input loop is responsive and understandable",
                "one complete play path exists without critical blockers",
                "crashes and hard locks are absent in the main path",
            ],
            "first_playable": [
                "save/load or restart flow works reliably",
                "smoke tests cover the shortest intended player path",
                "telemetry captures start, fail, reward, and completion events",
                "Reverie Engine validation passes for the generated project structure",
            ],
            "vertical_slice": [
                "content quality reflects target art, audio, and UI direction",
                "players can complete the slice with low moderator intervention",
                "playtest feedback identifies delight more often than confusion",
            ],
            "release_candidate": [
                "regression suite passes",
                "performance and memory budgets are within target",
                "known blockers are resolved or explicitly waived",
            ],
        }

        payload = {
            "focus": focus,
            "gates": gates,
        }
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
        return ToolResult.ok(
            f"Generated quality gates at {output_path}",
            {
                "output_path": str(output_path.relative_to(self.project_root)),
                "gate_sets": list(gates.keys()),
            },
        )

    def _run_quality_gates(self, output_path: Path, kwargs: Dict[str, Any]) -> ToolResult:
        blueprint = self._load_blueprint(kwargs.get("blueprint_path")) or self._load_json_artifact("artifacts/game_blueprint.json")
        game_request = self._load_json_artifact(kwargs.get("request_path"), default_relative="artifacts/game_request.json")
        system_bundle = self._load_json_artifact(kwargs.get("system_specs_path"), default_relative="artifacts/system_specs.json")
        asset_pipeline = self._load_json_artifact(kwargs.get("asset_pipeline_path"), default_relative="artifacts/asset_pipeline.json")
        design_intelligence = self._load_json_artifact("artifacts/design_intelligence.json", default_relative="artifacts/design_intelligence.json")
        slice_score = self._load_json_artifact("playtest/slice_score.json", default_relative="playtest/slice_score.json")
        quality_gates = build_quality_gate_report(
            game_request,
            blueprint,
            system_bundle,
            slice_score=slice_score,
            asset_pipeline=asset_pipeline,
            design_intelligence=design_intelligence,
        )
        performance_budget = build_performance_budget(
            game_request,
            blueprint,
            asset_pipeline,
            design_intelligence=design_intelligence,
        )
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(json.dumps(quality_gates, indent=2, ensure_ascii=False), encoding="utf-8")
        perf_path = self._resolve_path("playtest/performance_budget.json")
        perf_path.parent.mkdir(parents=True, exist_ok=True)
        perf_path.write_text(json.dumps(performance_budget, indent=2, ensure_ascii=False), encoding="utf-8")
        return ToolResult.ok(
            f"Ran quality gates at {output_path}",
            {
                "output_path": str(output_path.relative_to(self.project_root)),
                "performance_budget_path": str(perf_path.relative_to(self.project_root)),
                "quality_gates": quality_gates,
                "performance_budget": performance_budget,
            },
        )

    def _score_combat_feel(self, output_path: Path, kwargs: Dict[str, Any]) -> ToolResult:
        blueprint = self._load_blueprint(kwargs.get("blueprint_path")) or self._load_json_artifact("artifacts/game_blueprint.json")
        game_request = self._load_json_artifact(kwargs.get("request_path"), default_relative="artifacts/game_request.json")
        system_bundle = self._load_json_artifact(kwargs.get("system_specs_path"), default_relative="artifacts/system_specs.json")
        design_intelligence = self._load_json_artifact("artifacts/design_intelligence.json", default_relative="artifacts/design_intelligence.json")
        slice_score = self._load_json_artifact("playtest/slice_score.json", default_relative="playtest/slice_score.json")
        report = build_combat_feel_report(
            game_request,
            blueprint,
            system_bundle,
            slice_score=slice_score,
            design_intelligence=design_intelligence,
        )
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
        return ToolResult.ok(
            f"Scored combat feel at {output_path}",
            {
                "output_path": str(output_path.relative_to(self.project_root)),
                "combat_feel_report": report,
            },
        )

    def _plan_next_iteration(self, output_path: Path, kwargs: Dict[str, Any]) -> ToolResult:
        blueprint = self._load_blueprint(kwargs.get("blueprint_path")) or self._load_json_artifact("artifacts/game_blueprint.json")
        game_request = self._load_json_artifact(kwargs.get("request_path"), default_relative="artifacts/game_request.json")
        production_plan = self._load_json_artifact(kwargs.get("production_plan_path"), default_relative="artifacts/production_plan.json")
        task_graph = self._load_json_artifact(kwargs.get("task_graph_path"), default_relative="artifacts/task_graph.json")
        expansion_backlog = self._load_json_artifact(kwargs.get("expansion_backlog_path"), default_relative="artifacts/expansion_backlog.json")
        resume_state = self._load_json_artifact(kwargs.get("resume_state_path"), default_relative="artifacts/resume_state.json")
        world_program = self._load_json_artifact(kwargs.get("world_program_path"), default_relative="artifacts/world_program.json")
        reference_intelligence = self._load_json_artifact(
            kwargs.get("reference_intelligence_path"),
            default_relative="artifacts/reference_intelligence.json",
        )
        production_directive = self._load_json_artifact(
            kwargs.get("production_directive_path"),
            default_relative="artifacts/production_directive.json",
        )
        design_intelligence = self._load_json_artifact("artifacts/design_intelligence.json", default_relative="artifacts/design_intelligence.json")
        campaign_program = self._load_json_artifact("artifacts/campaign_program.json", default_relative="artifacts/campaign_program.json")
        roster_strategy = self._load_json_artifact("artifacts/roster_strategy.json", default_relative="artifacts/roster_strategy.json")
        live_ops_plan = self._load_json_artifact("artifacts/live_ops_plan.json", default_relative="artifacts/live_ops_plan.json")
        production_operating_model = self._load_json_artifact(
            "artifacts/production_operating_model.json",
            default_relative="artifacts/production_operating_model.json",
        )
        quality_gates = self._load_json_artifact("playtest/quality_gates.json", default_relative="playtest/quality_gates.json")
        slice_score = self._load_json_artifact("playtest/slice_score.json", default_relative="playtest/slice_score.json")
        plan = build_continuation_recommendations(
            game_request,
            blueprint,
            production_plan,
            task_graph,
            expansion_backlog,
            resume_state,
            slice_score=slice_score,
            quality_gates=quality_gates,
            world_program=world_program,
            reference_intelligence=reference_intelligence,
            production_directive=production_directive,
            campaign_program=campaign_program,
            roster_strategy=roster_strategy,
            live_ops_plan=live_ops_plan,
            production_operating_model=production_operating_model,
            design_intelligence=design_intelligence,
        )
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(continuation_recommendations_markdown(plan), encoding="utf-8")
        return ToolResult.ok(
            f"Planned next iteration at {output_path}",
            {
                "output_path": str(output_path.relative_to(self.project_root)),
                "continuation_plan": plan,
            },
        )

    def _analyze_session_log(self, log_path: Path) -> ToolResult:
        if not log_path.exists():
            return ToolResult.fail(f"Session log not found: {log_path}")

        rows = self._load_log_rows(log_path)
        if not rows:
            return ToolResult.fail("Session log is empty or unsupported")

        event_counter = Counter()
        failure_counter = Counter()
        quit_reasons = Counter()

        for row in rows:
            event_name = row.get("event") or row.get("type") or row.get("name") or "unknown"
            event_counter[event_name] += 1

            lowered = json.dumps(row, ensure_ascii=False).lower()
            if any(token in lowered for token in ["death", "fail", "lost", "stuck", "crash"]):
                failure_counter[event_name] += 1
            if "quit_reason" in row and str(row["quit_reason"]).strip():
                quit_reasons[str(row["quit_reason"]).strip()] += 1

        total_events = sum(event_counter.values())
        top_events = event_counter.most_common(5)
        top_failures = failure_counter.most_common(5)
        warnings = []
        if failure_counter:
            warnings.append("Failure-related events are present and should be reviewed against encounter pacing.")
        if quit_reasons:
            warnings.append("Session exits contain explicit quit reasons that may indicate friction points.")

        output = "Session Log Analysis:\n\n"
        output += f"Events processed: {total_events}\n"
        output += "Top events:\n"
        for name, count in top_events:
            output += f"- {name}: {count}\n"
        if top_failures:
            output += "\nLikely failure clusters:\n"
            for name, count in top_failures:
                output += f"- {name}: {count}\n"
        if quit_reasons:
            output += "\nQuit reasons:\n"
            for reason, count in quit_reasons.items():
                output += f"- {reason}: {count}\n"
        if warnings:
            output += "\nWarnings:\n"
            for warning in warnings:
                output += f"- {warning}\n"

        return ToolResult.ok(
            output,
            {
                "total_events": total_events,
                "top_events": top_events,
                "top_failures": top_failures,
                "quit_reasons": dict(quit_reasons),
            },
        )

    def _synthesize_feedback(self, kwargs: Dict[str, Any]) -> ToolResult:
        entries = self._load_feedback_entries(kwargs)
        if not entries:
            return ToolResult.fail("No feedback entries available for synthesis")

        positive = Counter()
        negative = Counter()
        suggestions = Counter()

        for entry in entries:
            lowered = entry.lower()
            for token in ["fun", "smooth", "satisfying", "clear", "cool", "immersive"]:
                if token in lowered:
                    positive[token] += 1
            for token in ["confusing", "slow", "hard", "boring", "frustrating", "clunky", "bug"]:
                if token in lowered:
                    negative[token] += 1
            for token in ["more", "less", "faster", "clearer", "better", "need", "wish"]:
                if token in lowered:
                    suggestions[token] += 1

        output = "Feedback Synthesis:\n\n"
        output += "Positive signals:\n"
        for token, count in positive.most_common(5):
            output += f"- {token}: {count}\n"
        output += "\nFriction signals:\n"
        for token, count in negative.most_common(5):
            output += f"- {token}: {count}\n"
        output += "\nChange pressure:\n"
        for token, count in suggestions.most_common(5):
            output += f"- {token}: {count}\n"

        return ToolResult.ok(
            output,
            {
                "entry_count": len(entries),
                "positive": dict(positive),
                "negative": dict(negative),
                "suggestions": dict(suggestions),
            },
        )

    def _event_schema(self, name: str, fields: List[str]) -> Dict[str, Any]:
        return {
            "name": name,
            "fields": fields,
        }

    def _unique_events(self, events: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        unique: Dict[str, Dict[str, Any]] = {}
        for event in events:
            unique[event["name"]] = event
        return list(unique.values())

    def _load_log_rows(self, log_path: Path) -> List[Dict[str, Any]]:
        suffix = log_path.suffix.lower()
        if suffix == ".json":
            payload = json.loads(log_path.read_text(encoding="utf-8"))
            if isinstance(payload, dict):
                if isinstance(payload.get("events"), list):
                    return [row for row in payload["events"] if isinstance(row, dict)]
                return [payload]
            if isinstance(payload, list):
                return [row for row in payload if isinstance(row, dict)]
            return []

        if suffix == ".csv":
            with log_path.open("r", encoding="utf-8", newline="") as handle:
                return [dict(row) for row in csv.DictReader(handle)]

        rows = []
        for line in log_path.read_text(encoding="utf-8", errors="ignore").splitlines():
            stripped = line.strip()
            if not stripped:
                continue
            rows.append({"event": "log_line", "text": stripped})
        return rows

    def _load_feedback_entries(self, kwargs: Dict[str, Any]) -> List[str]:
        entries = []
        data = kwargs.get("data") or {}
        for item in data.get("entries", []):
            if isinstance(item, str) and item.strip():
                entries.append(item.strip())

        feedback_path = kwargs.get("feedback_path")
        if not feedback_path:
            return entries

        path = self._resolve_path(feedback_path)
        if not path.exists():
            return entries

        if path.suffix.lower() == ".json":
            payload = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(payload, list):
                for item in payload:
                    if isinstance(item, str):
                        entries.append(item)
                    elif isinstance(item, dict):
                        text = item.get("text") or item.get("feedback") or item.get("comment")
                        if text:
                            entries.append(str(text))
            elif isinstance(payload, dict):
                for key in ["entries", "feedback", "comments"]:
                    value = payload.get(key)
                    if isinstance(value, list):
                        for item in value:
                            if isinstance(item, str):
                                entries.append(item)
                            elif isinstance(item, dict):
                                text = item.get("text") or item.get("feedback") or item.get("comment")
                                if text:
                                    entries.append(str(text))
        else:
            for line in path.read_text(encoding="utf-8", errors="ignore").splitlines():
                stripped = line.strip()
                if stripped:
                    entries.append(stripped)

        return entries

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

    def _load_json_artifact(self, raw_path: Optional[str], *, default_relative: str = "") -> Dict[str, Any]:
        candidate = str(raw_path or default_relative or "").strip()
        if not candidate:
            return {}
        path = self._resolve_path(candidate)
        if not path.exists():
            return {}
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            return {}
        return payload if isinstance(payload, dict) else {}

    def _resolve_path(self, raw: str) -> Path:
        return self.resolve_workspace_path(raw, purpose="resolve game playtest lab path")

    def get_execution_message(self, **kwargs) -> str:
        return f"Game playtest lab: {kwargs.get('action', 'unknown')}"
