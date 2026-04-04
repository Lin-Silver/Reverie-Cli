"""Durable expansion planning for long-running Reverie-Gamer projects."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List

from .system_generators.shared import project_name, target_runtime


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _references(game_request: Dict[str, Any]) -> List[str]:
    return [
        str(item).strip()
        for item in game_request.get("creative_target", {}).get("references", [])
        if str(item).strip()
    ]


def _genre(game_request: Dict[str, Any]) -> str:
    return str(game_request.get("creative_target", {}).get("primary_genre", "action_rpg")).strip() or "action_rpg"


def _dimension(game_request: Dict[str, Any]) -> str:
    return str(game_request.get("experience", {}).get("dimension", "3D")).strip() or "3D"


def _phase(
    phase_id: str,
    title: str,
    *,
    goals: List[str],
    systems: List[str],
    deliverables: List[str],
    unlocks: List[str],
) -> Dict[str, Any]:
    return {
        "id": phase_id,
        "title": title,
        "goals": list(goals),
        "systems": list(systems),
        "deliverables": list(deliverables),
        "unlocks": list(unlocks),
    }


def _region_seed(seed_id: str, biome: str, purpose: str, landmark: str, gate: str) -> Dict[str, Any]:
    return {
        "id": seed_id,
        "biome": biome,
        "purpose": purpose,
        "signature_landmark": landmark,
        "progression_gate": gate,
    }


def _npc_seed(npc_id: str, role: str, function: str, home_region: str) -> Dict[str, Any]:
    return {
        "id": npc_id,
        "role": role,
        "function": function,
        "home_region": home_region,
    }


def _quest_arc(arc_id: str, title: str, beat_count: int, lead_npc: str, regions: List[str]) -> Dict[str, Any]:
    return {
        "id": arc_id,
        "title": title,
        "beat_count": beat_count,
        "lead_npc": lead_npc,
        "regions": list(regions),
    }


def build_content_expansion_plan(
    game_request: Dict[str, Any],
    blueprint: Dict[str, Any],
    *,
    runtime_profile: Dict[str, Any] | None = None,
) -> Dict[str, Any]:
    """Build a deterministic long-cycle content expansion plan."""

    references = _references(game_request)
    production = dict(game_request.get("production", {}) or {})
    required_systems = [
        str(item).strip()
        for item in game_request.get("systems", {}).get("required", [])
        if str(item).strip()
    ]
    project = project_name(game_request, blueprint)
    runtime = target_runtime(blueprint, runtime_profile)
    genre = _genre(game_request)
    dimension = _dimension(game_request)
    open_world_signal = "open_world" in game_request.get("creative_target", {}).get("genre_tags", [])
    deferred_features = [
        str(item).strip()
        for item in production.get("deferred_features", [])
        if str(item).strip()
    ]

    region_seeds = [
        _region_seed(
            "starter_ruins",
            "wind-carved ruins",
            "onboard traversal, lock-on combat, and shrine purification",
            "sunken archway",
            "clear the sentinel pocket and activate the shrine",
        ),
        _region_seed(
            "cloudstep_basin",
            "tiered canyon wetlands",
            "teach vertical traversal, side-route rewards, and ranged enemy pressure",
            "storm bridge aqueduct",
            "unlock glide or climb-assisted route access",
        ),
        _region_seed(
            "echo_watch",
            "highland observatory frontier",
            "introduce elite encounters, faction pressure, and stronger story payoffs",
            "broken resonance tower",
            "complete the first regional quest arc finale",
        ),
    ]
    if open_world_signal:
        region_seeds.append(
            _region_seed(
                "emberfall_steppe",
                "wide volcanic grasslands",
                "prove streaming, mounted traversal or long-route exploration pacing",
                "glassfire crater",
                "stabilize world streaming and regional boss cadence",
            )
        )

    npc_roster = [
        _npc_seed("keeper_aeris", "guide", "explains shrine purification and anchors the first region hub loop", "starter_ruins"),
        _npc_seed("marshal_toren", "combat_trainer", "unlocks challenge rematches and advanced combat tutorials", "cloudstep_basin"),
        _npc_seed("scribe_ves", "historian", "feeds world lore, relic collection, and archive rewards", "echo_watch"),
        _npc_seed("forge_luma", "craftsmith", "converts drop materials into upgrades and progression spends", "starter_ruins"),
    ]

    quest_arcs = [
        _quest_arc(
            "purification_path",
            "Purification Path",
            beat_count=4,
            lead_npc="keeper_aeris",
            regions=["starter_ruins", "cloudstep_basin"],
        ),
        _quest_arc(
            "watchtower_resonance",
            "Watchtower Resonance",
            beat_count=5,
            lead_npc="scribe_ves",
            regions=["cloudstep_basin", "echo_watch"],
        ),
    ]
    if open_world_signal:
        quest_arcs.append(
            _quest_arc(
                "frontier_faultline",
                "Frontier Faultline",
                beat_count=6,
                lead_npc="marshal_toren",
                regions=["echo_watch", "emberfall_steppe"],
            )
        )

    expansion_phases = [
        _phase(
            "foundation_scale_up",
            "Foundation Scale-Up",
            goals=[
                "Convert the slice into a reusable region template with hub, route guidance, and stronger combat pacing.",
                "Promote save/load, progression, and quest flow into reusable multi-region contracts.",
            ],
            systems=["save_load", "quest", "progression", "world_slice", "asset_pipeline"],
            deliverables=["multi-region data schema", "hub + return loop", "regional quest-arc state model"],
            unlocks=["second region production", "repeatable side-route rewards"],
        ),
        _phase(
            "combat_depth",
            "Combat Depth",
            goals=[
                "Add a richer enemy ecology with elites, ranged pressure, and boss-level telegraph patterns.",
                "Turn the player controller into a real ARPG combat base with stronger skills, reactions, and hit feedback.",
            ],
            systems=["character_controller", "combat", "enemy_ai", "encounters", "ui_hud"],
            deliverables=[
                "animation-state driven combat hooks",
                "elite and boss encounter templates",
                "telegraphed attack and reaction contracts",
            ],
            unlocks=["combat mastery loop", "boss-ready region finales"],
        ),
        _phase(
            "world_and_story_growth",
            "World And Story Growth",
            goals=[
                "Grow the project from one slice into a regional progression structure with recurring NPCs and quest arcs.",
                "Keep authored content scalable by anchoring every new region to shared rules, landmarks, and budgets.",
            ],
            systems=["quest", "world_slice", "progression", "telemetry", "asset_pipeline"],
            deliverables=["region seed set", "npc roster", "quest arc manifest"],
            unlocks=["multi-region roadmap", "content production backlog"],
        ),
    ]

    target_scale = "regional_arpg_base"
    if dimension == "3D" and genre == "action_rpg" and references:
        target_scale = "large_scale_3d_action_rpg_base"

    return {
        "schema_version": "reverie.content_expansion/1",
        "project_name": project,
        "generated_at": _utc_now(),
        "runtime": runtime,
        "target_scale": target_scale,
        "reference_titles": references,
        "deferred_features": deferred_features,
        "required_systems": required_systems,
        "expansion_phases": expansion_phases,
        "region_seeds": region_seeds,
        "npc_roster": npc_roster,
        "quest_arcs": quest_arcs,
        "continuity_rules": [
            "Always reopen the latest resume_state before expanding scope.",
            "Do not add new regions until the current slice score is at least credible_vertical_slice_base.",
            "Treat region seeds, NPC roster, and quest arcs as durable memory artifacts for later sessions.",
        ],
    }


def build_expansion_backlog(
    game_request: Dict[str, Any],
    blueprint: Dict[str, Any],
    task_graph: Dict[str, Any],
    content_expansion: Dict[str, Any],
    *,
    slice_score: Dict[str, Any] | None = None,
) -> Dict[str, Any]:
    """Build a resumable backlog aligned to the current slice and future scale-up."""

    score = dict(slice_score or {})
    blockers = [str(item).strip() for item in score.get("blockers", []) if str(item).strip()]
    recommendations = [str(item).strip() for item in score.get("recommendations", []) if str(item).strip()]

    items: List[Dict[str, Any]] = [
        {
            "id": "stabilize_current_slice",
            "priority": "now",
            "status": "active",
            "lane": "verification",
            "goal": "Close the highest-risk blockers before content breadth expands.",
            "depends_on": ["verification_loop"] if "verification_loop" in task_graph.get("resume_order", []) else [],
            "acceptance": blockers or recommendations[:2] or ["slice score remains stable across repeated runs"],
        },
        {
            "id": "promote_region_template",
            "priority": "next",
            "status": "queued",
            "lane": "world_scale",
            "goal": "Turn the current slice into a reusable region template with hub, route, challenge pocket, and finale beats.",
            "depends_on": ["stabilize_current_slice"],
            "acceptance": [
                "region seeds are mirrored into runtime data",
                "quest arcs and NPC roster resolve through durable data contracts",
                "save/load survives multi-region state growth",
            ],
        },
        {
            "id": "combat_depth_upgrade",
            "priority": "next",
            "status": "queued",
            "lane": "combat_scale",
            "goal": "Deepen the ARPG combat base with more reusable enemy and skill contracts.",
            "depends_on": ["stabilize_current_slice"],
            "acceptance": [
                "combat state hooks support stronger enemy archetypes",
                "encounter templates cover melee, ranged, elite, and boss escalation",
                "feedback and telegraph readability improve under movement pressure",
            ],
        },
        {
            "id": "multi_region_content_wave",
            "priority": "later",
            "status": "seeded",
            "lane": "content_expansion",
            "goal": "Use the region, NPC, and quest seeds to grow the project past one polished slice.",
            "depends_on": ["promote_region_template", "combat_depth_upgrade"],
            "acceptance": [
                "at least one additional region is playable from shared templates",
                "quest arcs span multiple spaces without schema drift",
                "content backlog remains aligned with runtime and asset budgets",
            ],
        },
    ]

    for index, phase in enumerate(content_expansion.get("expansion_phases", []), start=1):
        items.append(
            {
                "id": f"phase_seed_{index}",
                "priority": "seed",
                "status": "seeded",
                "lane": "continuity",
                "goal": phase.get("title", f"Expansion Phase {index}"),
                "depends_on": ["multi_region_content_wave"] if index > 1 else ["promote_region_template"],
                "acceptance": list(phase.get("deliverables", [])),
            }
        )

    return {
        "schema_version": "reverie.expansion_backlog/1",
        "project_name": project_name(game_request, blueprint),
        "runtime": target_runtime(blueprint),
        "slice_verdict": score.get("verdict", "planning_only"),
        "release_recommendation": score.get("release_recommendation", "iterate_then_expand"),
        "blocker_count": len(blockers),
        "recommended_focus": items[0]["id"],
        "items": items,
    }


def build_resume_state(
    game_request: Dict[str, Any],
    blueprint: Dict[str, Any],
    production_plan: Dict[str, Any],
    task_graph: Dict[str, Any],
    content_expansion: Dict[str, Any],
    expansion_backlog: Dict[str, Any],
    *,
    runtime_profile: Dict[str, Any] | None = None,
    verification: Dict[str, Any] | None = None,
    slice_score: Dict[str, Any] | None = None,
) -> Dict[str, Any]:
    """Build the durable state a future session should reopen first."""

    verification = dict(verification or {})
    slice_score = dict(slice_score or {})

    return {
        "schema_version": "reverie.resume_state/1",
        "project_name": project_name(game_request, blueprint),
        "generated_at": _utc_now(),
        "runtime": target_runtime(blueprint, runtime_profile),
        "scope_tier": blueprint.get("meta", {}).get("scope", "vertical_slice"),
        "current_status": {
            "verification_valid": bool(verification.get("valid", False)),
            "slice_score": slice_score.get("score", 0),
            "slice_verdict": slice_score.get("verdict", "planning_only"),
            "release_recommendation": slice_score.get("release_recommendation", "iterate_then_expand"),
        },
        "artifacts_to_open_first": [
            "artifacts/resume_state.json",
            "artifacts/expansion_backlog.json",
            "artifacts/content_expansion.json",
            "artifacts/asset_pipeline.json",
            "playtest/slice_score.json",
            "artifacts/task_graph.json",
        ],
        "completed_artifacts": [
            "artifacts/game_request.json",
            "artifacts/game_blueprint.json",
            "artifacts/runtime_registry.json",
            "artifacts/production_plan.json",
            "artifacts/system_specs.json",
            "artifacts/task_graph.json",
            "artifacts/content_expansion.json",
            "artifacts/asset_pipeline.json",
            "artifacts/expansion_backlog.json",
            "artifacts/resume_state.json",
        ],
        "critical_path": list(task_graph.get("critical_path", [])),
        "next_actions": [
            expansion_backlog.get("recommended_focus", "stabilize_current_slice"),
            "review playtest/slice_score.json and artifacts/expansion_backlog.json together before adding scope",
            "continue from the first queued backlog item rather than re-planning from scratch",
        ],
        "continuity_memory": {
            "source_prompt": game_request.get("source_prompt", ""),
            "deferred_features": list(game_request.get("production", {}).get("deferred_features", [])),
            "expansion_phase_ids": [phase.get("id") for phase in content_expansion.get("expansion_phases", [])],
            "backlog_item_ids": [item.get("id") for item in expansion_backlog.get("items", [])],
        },
        "resume_instruction": (
            "Read artifacts/resume_state.json, artifacts/expansion_backlog.json, artifacts/content_expansion.json, "
            "and playtest/slice_score.json first, then continue from the recommended backlog item without re-deriving the project."
        ),
        "production_lanes": [lane.get("name") for lane in production_plan.get("lanes", []) if lane.get("name")],
    }


def content_expansion_markdown(plan: Dict[str, Any]) -> str:
    lines = [f"# Content Expansion: {plan.get('project_name', 'Untitled Reverie Slice')}", ""]
    lines.append(f"Runtime: {plan.get('runtime', 'reverie_engine')}")
    lines.append(f"Target Scale: {plan.get('target_scale', 'regional_arpg_base')}")
    lines.append("")
    lines.append("## Expansion Phases")
    for phase in plan.get("expansion_phases", []):
        lines.append(f"### {phase.get('id', 'phase')}: {phase.get('title', '')}")
        for item in phase.get("goals", []):
            lines.append(f"- Goal: {item}")
        for item in phase.get("deliverables", []):
            lines.append(f"- Deliverable: {item}")
        for item in phase.get("unlocks", []):
            lines.append(f"- Unlock: {item}")
        lines.append("")
    lines.append("## Region Seeds")
    for region in plan.get("region_seeds", []):
        lines.append(
            f"- {region.get('id')}: {region.get('biome')} | {region.get('purpose')} | gate: {region.get('progression_gate')}"
        )
    lines.append("")
    lines.append("## NPC Roster")
    for npc in plan.get("npc_roster", []):
        lines.append(f"- {npc.get('id')}: {npc.get('role')} in {npc.get('home_region')}")
    lines.append("")
    lines.append("## Quest Arcs")
    for arc in plan.get("quest_arcs", []):
        lines.append(f"- {arc.get('id')}: {arc.get('title')} ({arc.get('beat_count')} beats)")
    lines.append("")
    return "\n".join(lines)


def expansion_backlog_markdown(backlog: Dict[str, Any]) -> str:
    lines = [f"# Expansion Backlog: {backlog.get('project_name', 'Untitled Reverie Slice')}", ""]
    lines.append(f"Runtime: {backlog.get('runtime', 'reverie_engine')}")
    lines.append(f"Recommendation: {backlog.get('release_recommendation', 'iterate_then_expand')}")
    lines.append("")
    for item in backlog.get("items", []):
        lines.append(f"## {item.get('id', 'item')}")
        lines.append(f"- Priority: {item.get('priority', 'later')}")
        lines.append(f"- Status: {item.get('status', 'queued')}")
        lines.append(f"- Lane: {item.get('lane', 'continuity')}")
        lines.append(f"- Goal: {item.get('goal', '')}")
        lines.append(f"- Depends On: {', '.join(item.get('depends_on', [])) or 'none'}")
        for acceptance in item.get("acceptance", []):
            lines.append(f"- Acceptance: {acceptance}")
        lines.append("")
    return "\n".join(lines)


def resume_state_markdown(state: Dict[str, Any]) -> str:
    status = dict(state.get("current_status", {}) or {})
    lines = [f"# Resume State: {state.get('project_name', 'Untitled Reverie Slice')}", ""]
    lines.append(f"Runtime: {state.get('runtime', 'reverie_engine')}")
    lines.append(f"Scope Tier: {state.get('scope_tier', 'vertical_slice')}")
    lines.append(f"Verification Valid: {status.get('verification_valid', False)}")
    lines.append(f"Slice Verdict: {status.get('slice_verdict', 'planning_only')}")
    lines.append("")
    lines.append("## Open First")
    for path in state.get("artifacts_to_open_first", []):
        lines.append(f"- {path}")
    lines.append("")
    lines.append("## Next Actions")
    for action in state.get("next_actions", []):
        lines.append(f"- {action}")
    lines.append("")
    lines.append("## Resume Instruction")
    lines.append(state.get("resume_instruction", ""))
    lines.append("")
    return "\n".join(lines)
