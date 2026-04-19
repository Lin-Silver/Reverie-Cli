"""Blueprint and production-plan builders for Reverie-Gamer."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _system_spec(system_name: str, _game_request: Dict[str, Any]) -> Dict[str, Any]:
    name = str(system_name).strip()
    labels = {
        "camera": "Keep the playable space readable and reinforce combat awareness.",
        "movement": "Deliver responsive traversal with genre-correct control and acceleration.",
        "combat": "Support clear offense, defense, timing, and reward loops.",
        "interaction": "Make objectives and world affordances legible without excessive UI dependence.",
        "quest": "Track objective state, rewards, and progression gating.",
        "progression": "Turn slice rewards into visible build growth.",
        "save_load": "Persist progress and support versioned iteration safely.",
        "ui_hud": "Communicate state, objective, rewards, and combat readability clearly.",
        "world_slice": "Package one convincing playable zone with encounter pacing and landmarking.",
        "telemetry": "Record starts, failures, rewards, and completion to guide iteration.",
        "enemy_ai": "Present readable attack windows and pressure escalation.",
        "encounters": "Sequence enemy compositions and reward beats into a coherent slice arc.",
        "asset_pipeline": "Keep source assets, runtime imports, and budget notes aligned.",
        "lock_on": "Preserve target readability in a third-person action context.",
        "traversal_ability": "Support one notable movement fantasy such as glide or climb.",
    }
    deliverables = {
        "camera": ["camera rig", "view constraints", "combat readability defaults"],
        "movement": ["controller", "jump/dash or traversal tuning", "smoke path inputs"],
        "combat": ["light attack loop", "reaction target", "reward hook"],
        "interaction": ["objective trigger", "world interaction affordances", "feedback loop"],
        "quest": ["objective data", "completion trigger", "reward table"],
        "progression": ["upgrade track", "reward spend", "slice unlock"],
        "save_load": ["save slot schema", "restore path", "version metadata"],
        "ui_hud": ["health or state HUD", "objective text", "reward feedback"],
        "world_slice": ["main zone", "landmarks", "goal state"],
        "telemetry": ["session_start", "encounter_result", "reward_claimed", "slice_completed"],
    }
    tests = {
        "camera": ["camera follows correctly", "camera keeps objective readable during combat"],
        "movement": ["movement responds to directional input", "jump or dash path works in the main loop"],
        "combat": ["attack can damage the slice target", "combat reward advances the objective"],
        "save_load": ["save schema writes and restores key slice state"],
        "quest": ["quest completion condition is reachable in one run"],
        "telemetry": ["core events fire on start, failure, reward, and completion"],
    }
    telemetry = deliverables.get(name, ["system_started", "system_completed"])
    return {
        "name": name,
        "goal": labels.get(name, f"{name} should contribute directly to the first playable slice."),
        "deliverables": deliverables.get(name, [f"{name} slice implementation"]),
        "telemetry": telemetry,
        "tests": tests.get(name, ["real runtime smoke path", "data-driven sanity check"]),
    }


def build_blueprint_from_request(
    game_request: Dict[str, Any],
    *,
    runtime_profile: Dict[str, Any] | None = None,
    overrides: Dict[str, Any] | None = None,
) -> Dict[str, Any]:
    """Turn a compiled request into a structured production blueprint."""

    request = dict(game_request or {})
    meta = request.get("meta", {})
    creative = request.get("creative_target", {})
    experience = request.get("experience", {})
    production = request.get("production", {})
    runtime = dict(request.get("runtime_preferences", {}))
    runtime["selected_runtime"] = (
        (runtime_profile or {}).get("id")
        or runtime.get("preferred_runtime")
        or "reverie_engine"
    )

    required_systems = request.get("systems", {}).get("required", [])
    blueprint = {
        "meta": {
            "project_name": meta.get("project_name", "Untitled Reverie Slice"),
            "genre": creative.get("primary_genre", "action_rpg"),
            "dimension": experience.get("dimension", "3D"),
            "target_engine": runtime["selected_runtime"],
            "camera_model": experience.get("camera_model", "third_person"),
            "scope": production.get("delivery_scope", "vertical_slice"),
            "created_at": _utc_now(),
        },
        "request_snapshot": {
            "source_prompt": request.get("source_prompt", ""),
            "references": creative.get("references", []),
            "requested_scope": production.get("requested_scope", "vertical_slice"),
            "deferred_features": production.get("deferred_features", []),
        },
        "creative_direction": {
            "pillars": [
                "deliver the core fantasy inside the first 10-20 minutes",
                "keep the 3D slice readable under movement and combat stress",
                "connect rewards to visible build growth immediately",
            ],
            "tone": creative.get("tone", "kinetic and readable"),
            "references": creative.get("references", []),
            "art_direction": creative.get("art_direction", {}),
        },
        "gameplay_blueprint": {
            "core_loop": experience.get("core_loop", []),
            "meta_loop": experience.get("meta_loop", []),
            "player_verbs": experience.get("player_verbs", []),
            "movement_model": experience.get("movement_model", "third_person_action"),
            "combat_model": experience.get("combat_model", "ability_action"),
            "systems": {name: _system_spec(name, request) for name in required_systems},
        },
        "content_strategy": {
            "world_structure": "one authored 3D slice zone with a clear route, one combat pocket, one upgrade beat, and one finish state",
            "slice_spaces": production.get("content_scale", {}).get("slice_spaces", 1),
            "enemy_families": ["light_melee", "ranged_pressure"][: production.get("content_scale", {}).get("enemy_families", 1)],
            "quest_structure": ["intro_objective", "combat_clear", "activate_goal"],
            "reward_types": ["power", "currency", "narrative"],
        },
        "technical_strategy": {
            "runtime": {
                "engine_profile": runtime["selected_runtime"],
                "requested_runtime": runtime.get("requested_runtime", ""),
                "rendering_target": experience.get("dimension", "3D"),
                "runtime_requirements": runtime.get("runtime_requirements", []),
                "capabilities": list((runtime_profile or {}).get("capabilities", [])),
                "validation_ready": bool((runtime_profile or {}).get("can_validate", False)),
            },
            "data_contracts": {
                "save_schema": "versioned slot state for objective progress, health, stamina, and unlocked upgrades",
                "quest_schema": "objective id -> state -> rewards",
                "telemetry_events": ["session_start", "encounter_result", "reward_claimed", "slice_completed"],
            },
            "asset_pipeline": {
                "source_of_truth": ["design/", "assets/raw/", "assets/models/source/"],
                "runtime_exports": ["assets/processed/", "assets/models/runtime/"],
                "validation": ["naming", "dependencies", "budgets", "smoke import"],
            },
        },
        "production_strategy": {
            "milestones": [
                "compile_request",
                "foundation",
                "first_playable",
                "vertical_slice",
                "expansion_base",
            ],
            "vertical_slice_goals": production.get("slice_targets", []),
            "known_risks": production.get("known_risks", []),
            "deferred_features": production.get("deferred_features", []),
        },
        "quality_targets": request.get("quality_targets", {}),
    }

    if overrides:
        blueprint.update(dict(overrides))
    return blueprint


def build_vertical_slice_plan(
    game_request: Dict[str, Any],
    blueprint: Dict[str, Any],
    *,
    runtime_profile: Dict[str, Any] | None = None,
) -> Dict[str, Any]:
    """Build a concrete slice plan from a compiled request and blueprint."""

    meta = blueprint.get("meta", {})
    content = blueprint.get("content_strategy", {})
    production = blueprint.get("production_strategy", {})
    quality = blueprint.get("quality_targets", {})
    runtime_id = meta.get("target_engine", (runtime_profile or {}).get("id", "reverie_engine"))

    return {
        "project_name": meta.get("project_name", "Untitled Reverie Slice"),
        "target_runtime": f"{meta.get('dimension', '3D')} / {runtime_id}",
        "scope_tier": meta.get("scope", "vertical_slice"),
        "feature_lanes": [
            "third-person controller, camera, and readable combat target",
            "one 3D zone with landmarks, route guidance, and one encounter pocket",
            "one objective chain from entry to combat clear to shrine activation",
            "one progression beat that changes the player's next attempt",
        ],
        "systems_in_scope": list(blueprint.get("gameplay_blueprint", {}).get("systems", {}).keys())[:8],
        "content_budget": {
            "playable_spaces": content.get("slice_spaces", 1),
            "enemy_families": len(content.get("enemy_families", [])),
            "quest_steps": len(content.get("quest_structure", [])),
            "reward_types": content.get("reward_types", []),
        },
        "quality_gates": quality.get("must_have", []) + [
            "smoke path reaches the slice completion state",
            "players can understand the next objective without off-game explanation",
            "combat readability remains stable during movement and objective pressure",
            "critical system packets exist for controller, combat or challenge, quest, save/load, progression, and world structure",
        ],
        "critical_risks": production.get("known_risks", []),
        "deferred_features": production.get("deferred_features", []),
        "verification": {
            "required_tests": [
                "runtime smoke path",
                "system packet generation",
                "save/load sanity check",
                "telemetry event schema generation",
                "slice score evaluation",
                "quality-gate review for first playable",
            ],
            "playtest_questions": [
                "Was the player fantasy understandable within the first five minutes?",
                "Did combat, movement, and objective readability support each other?",
                "Did the reward make the next run feel meaningfully stronger or clearer?",
            ],
        },
    }


def build_production_plan(
    game_request: Dict[str, Any],
    blueprint: Dict[str, Any],
    *,
    runtime_profile: Dict[str, Any] | None = None,
) -> Dict[str, Any]:
    """Build a durable production plan suitable for long-running slice expansion."""

    vertical_slice = build_vertical_slice_plan(game_request, blueprint, runtime_profile=runtime_profile)
    return {
        "schema_version": "reverie.production_plan/1",
        "project_name": blueprint.get("meta", {}).get("project_name", "Untitled Reverie Slice"),
        "generated_at": _utc_now(),
        "runtime": runtime_profile or {"id": blueprint.get("meta", {}).get("target_engine", "reverie_engine")},
        "lanes": [
            {
                "name": "program_compilation",
                "goal": "turn one prompt into a durable game program, product strategy, feature matrix, milestone board, and risk register",
                "outputs": [
                    "artifacts/game_program.json",
                    "artifacts/game_bible.md",
                    "artifacts/feature_matrix.json",
                    "artifacts/content_matrix.json",
                    "artifacts/milestone_board.json",
                    "artifacts/risk_register.json",
                ],
            },
            {
                "name": "request_compilation",
                "goal": "stabilize one structured request and keep it aligned with delivered code",
                "outputs": ["artifacts/game_request.json", "artifacts/game_blueprint.json"],
            },
            {
                "name": "experience_design",
                "goal": "default-initialize personas, onboarding, difficulty, feedback, balance, accessibility, and runtime scaling guardrails",
                "outputs": [
                    "artifacts/design_intelligence.json",
                    "artifacts/design_playbook.md",
                ],
            },
            {
                "name": "large_scale_direction",
                "goal": "translate ambitious project scale into durable campaign, roster, live-ops, and operating-model artifacts before content sprawl takes over",
                "outputs": [
                    "artifacts/campaign_program.json",
                    "artifacts/roster_strategy.json",
                    "artifacts/live_ops_plan.json",
                    "artifacts/production_operating_model.json",
                ],
            },
            {
                "name": "runtime_foundation",
                "goal": "create a bootable game foundation with explicit runtime choice, local reference intelligence, and data contracts",
                "outputs": [
                    "artifacts/runtime_registry.json",
                    "artifacts/reference_intelligence.json",
                    "artifacts/runtime_capability_graph.json",
                    "artifacts/runtime_delivery_plan.json",
                    "artifacts/production_plan.json",
                    "artifacts/system_specs.json",
                    "artifacts/task_graph.json",
                ],
            },
            {
                "name": "asset_production",
                "goal": "seed the modeling workspace, registry, import rules, and first authored-asset queue before content breadth expands",
                "outputs": [
                    "artifacts/asset_pipeline.json",
                    "artifacts/character_kits.json",
                    "artifacts/environment_kits.json",
                    "artifacts/animation_plan.json",
                    "artifacts/asset_budget.json",
                    "data/models/model_registry.yaml",
                    "assets/models/source/*",
                    "assets/models/runtime/*",
                ],
            },
            {
                "name": "systems",
                "goal": "ship movement, combat or interaction, quest, progression, and save/load in one loop",
                "outputs": [
                    "runtime scripts",
                    "data/content/*",
                    "tests/smoke/*",
                    "artifacts/system_specs.md",
                ],
            },
            {
                "name": "slice_content",
                "goal": "package one polished world slice with encounter and reward pacing",
                "outputs": [
                    "main scene",
                    "slice objective chain",
                    "HUD",
                    "encounter content",
                    "artifacts/world_program.json",
                    "artifacts/region_kits.json",
                    "artifacts/faction_graph.json",
                    "artifacts/questline_program.json",
                    "artifacts/save_migration_plan.json",
                ],
            },
            {
                "name": "verification",
                "goal": "make the slice runnable, measurable, and ready for playtest iteration",
                "outputs": [
                    "playtest/test_plan.md",
                    "telemetry/schema.json",
                    "playtest/quality_gates.json",
                    "playtest/performance_budget.json",
                    "playtest/combat_feel_report.json",
                    "playtest/slice_score.json",
                    "playtest/continuation_recommendations.md",
                ],
            },
            {
                "name": "continuity",
                "goal": "leave durable expansion seeds, backlog state, and resume instructions for future sessions",
                "outputs": [
                    "artifacts/content_expansion.json",
                    "artifacts/expansion_backlog.json",
                    "artifacts/resume_state.json",
                ],
            },
        ],
        "vertical_slice": vertical_slice,
    }


def vertical_slice_markdown(plan: Dict[str, Any]) -> str:
    lines = [f"# {plan.get('project_name', 'Vertical Slice Plan')}", ""]
    lines.append(f"Target Runtime: {plan.get('target_runtime', 'unknown')}")
    lines.append(f"Scope Tier: {plan.get('scope_tier', 'vertical_slice')}")
    lines.append("")
    lines.append("## Feature Lanes")
    for item in plan.get("feature_lanes", []):
        lines.append(f"- {item}")
    lines.append("")
    lines.append("## Systems In Scope")
    for item in plan.get("systems_in_scope", []):
        lines.append(f"- {item}")
    lines.append("")
    lines.append("## Content Budget")
    for key, value in (plan.get("content_budget", {}) or {}).items():
        lines.append(f"- {key}: {value}")
    lines.append("")
    lines.append("## Quality Gates")
    for item in plan.get("quality_gates", []):
        lines.append(f"- {item}")
    lines.append("")
    lines.append("## Deferred Features")
    for item in plan.get("deferred_features", []):
        lines.append(f"- {item}")
    lines.append("")
    lines.append("## Verification")
    for item in plan.get("verification", {}).get("required_tests", []):
        lines.append(f"- {item}")
    lines.append("")
    lines.append("## Playtest Questions")
    for item in plan.get("verification", {}).get("playtest_questions", []):
        lines.append(f"- {item}")
    lines.append("")
    return "\n".join(lines)


def production_plan_markdown(plan: Dict[str, Any]) -> str:
    lines = [f"# Production Plan: {plan.get('project_name', 'Untitled Reverie Slice')}", ""]
    lines.append("## Lanes")
    for lane in plan.get("lanes", []):
        lines.append(f"- {lane.get('name')}: {lane.get('goal')}")
        for output in lane.get("outputs", []):
            lines.append(f"  - output: {output}")
    lines.append("")
    lines.append(vertical_slice_markdown(plan.get("vertical_slice", {})))
    return "\n".join(lines)
