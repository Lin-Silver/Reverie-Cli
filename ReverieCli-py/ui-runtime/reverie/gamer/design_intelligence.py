"""Default game-creation intelligence for Reverie-Gamer."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, Iterable, List

from .system_generators.shared import project_name, target_runtime


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _unique(values: Iterable[str]) -> List[str]:
    seen: set[str] = set()
    ordered: List[str] = []
    for value in values:
        item = str(value or "").strip()
        if not item or item in seen:
            continue
        seen.add(item)
        ordered.append(item)
    return ordered


def _references(game_request: Dict[str, Any]) -> List[str]:
    return _unique(game_request.get("creative_target", {}).get("references", []) or [])


def _specialized(game_request: Dict[str, Any]) -> set[str]:
    return {
        str(item).strip()
        for item in game_request.get("systems", {}).get("specialized", []) or []
        if str(item).strip()
    }


def _party_model(game_request: Dict[str, Any]) -> str:
    return str(game_request.get("experience", {}).get("party_model", "single_hero_focus")).strip() or "single_hero_focus"


def _world_structure(game_request: Dict[str, Any]) -> str:
    return str(game_request.get("experience", {}).get("world_structure", "regional_action_slice")).strip() or "regional_action_slice"


def _live_service_enabled(game_request: Dict[str, Any]) -> bool:
    return bool(game_request.get("production", {}).get("live_service_profile", {}).get("enabled", False))


def _default_capabilities(game_request: Dict[str, Any]) -> List[Dict[str, Any]]:
    references = {item.lower() for item in _references(game_request)}
    party_model = _party_model(game_request)
    world_structure = _world_structure(game_request)
    live_service = _live_service_enabled(game_request)
    capabilities = [
        {
            "id": "persona_synthesis",
            "goal": "Turn one prompt into concrete player types, session expectations, and friction budgets.",
        },
        {
            "id": "mda_experience_mapping",
            "goal": "Map mechanics to runtime dynamics and intended aesthetics before implementation fans out.",
        },
        {
            "id": "flow_curve_planning",
            "goal": "Shape onboarding, mastery ramps, and boss exams around readable escalation instead of random spikes.",
        },
        {
            "id": "dynamic_difficulty_adjustment",
            "goal": "Use subtle support surfaces when players stall, without invalidating earned mastery.",
        },
        {
            "id": "reinforcement_feedback_loops",
            "goal": "Preserve the telegraph -> action -> confirm -> payoff loop across combat, exploration, and rewards.",
        },
        {
            "id": "doubling_halving_balance_lab",
            "goal": "Seed balance probes that can be tuned quickly before content scale increases.",
        },
        {
            "id": "fail_forward_and_recovery",
            "goal": "Keep losses educational, recoverable, and connected to clear next actions.",
        },
        {
            "id": "accessibility_baseline",
            "goal": "Ship readable controls, audio/visual redundancy, subtitles, remapping, and forgiving interaction defaults.",
        },
        {
            "id": "runtime_scaling_guardrails",
            "goal": "Tie large 3D ambitions to navigation, visibility, occlusion, and scene-budget guardrails.",
        },
    ]
    if party_model != "single_hero_focus":
        capabilities.append(
            {
                "id": "party_synergy_role_matrix",
                "goal": "Protect roster roles, swap logic, and boss counterplay from collapsing into one dominant team.",
            }
        )
    if world_structure in {"open_world_regions", "hub_and_districts"}:
        capabilities.append(
            {
                "id": "world_route_onboarding",
                "goal": "Teach navigation, landmarks, and route value through level flow instead of exposition alone.",
            }
        )
    if live_service:
        capabilities.append(
            {
                "id": "service_cadence_guardrails",
                "goal": "Keep version cadence, roster drops, and event layers subordinate to slice quality and system health.",
            }
        )
    if references & {"genshin impact", "wuthering waves", "zenless zone zero"}:
        capabilities.append(
            {
                "id": "anime_action_service_grammar",
                "goal": "Default to region cells, roster expression, event beats, and spectacle pacing suited to large anime-action projects.",
            }
        )
    return capabilities


def _player_personas(game_request: Dict[str, Any]) -> List[Dict[str, Any]]:
    world_structure = _world_structure(game_request)
    party_model = _party_model(game_request)
    live_service = _live_service_enabled(game_request)
    personas = [
        {
            "id": "exploration_pathfinder",
            "fantasy": "Discover a striking route, landmark, or shortcut before the system fully explains it.",
            "preferred_sessions": "20-45 minute loops that mix traversal, puzzle-light routing, and reward caches.",
            "success_signals": ["finds optional chests or shortcuts", "re-enters the region voluntarily", "remembers landmarks"],
            "friction_budget": "medium mechanical pressure, low menu friction",
        },
        {
            "id": "combat_optimizer",
            "fantasy": "Read enemies quickly, improve timing, and express mastery through cleaner clears.",
            "preferred_sessions": "10-25 minute high-focus combat routes with visible progress on damage, break, or survival.",
            "success_signals": ["retries bosses willingly", "uses dodge, guard, or swap tech intentionally", "adopts build experiments"],
            "friction_budget": "high combat pressure, low ambiguity on feedback",
        },
    ]
    if party_model != "single_hero_focus":
        personas.append(
            {
                "id": "roster_theorycrafter",
                "fantasy": "Assemble a team with roles, synergies, and counterpicks that alter encounter feel.",
                "preferred_sessions": "15-40 minute loops that convert rewards into party growth and matchup planning.",
                "success_signals": ["rotates party slots", "changes build for a boss", "reacts to new roster waves"],
                "friction_budget": "medium system depth, low inventory clutter",
            }
        )
    if live_service or world_structure == "hub_and_districts":
        personas.append(
            {
                "id": "returning_live_player",
                "fantasy": "Return to a familiar project that always has one clear, meaningful next objective.",
                "preferred_sessions": "8-20 minute re-entry loops with one event beat, one reward beat, and one forward hook.",
                "success_signals": ["completes a daily or short arc", "checks the next chapter or roster beat", "stays oriented after a break"],
                "friction_budget": "low re-entry friction, high clarity of next-step guidance",
            }
        )
    return personas


def _mda_map(game_request: Dict[str, Any], system_bundle: Dict[str, Any]) -> Dict[str, Any]:
    world_structure = _world_structure(game_request)
    party_model = _party_model(game_request)
    mechanics = [
        "third-person traversal",
        "combat verbs",
        "quest objectives",
        "progression unlocks",
        "save/load continuity",
    ]
    if world_structure in {"open_world_regions", "hub_and_districts"}:
        mechanics.append("regional routing and landmark navigation")
    if party_model != "single_hero_focus":
        mechanics.append("party swaps and role synergy")
    mechanics.extend(
        str(key).strip()
        for key in system_bundle.get("packets", {}).keys()
        if str(key).strip() and str(key).strip() not in mechanics
    )
    aesthetics = ["fantasy", "challenge", "discovery"]
    if party_model != "single_hero_focus":
        aesthetics.append("expression")
    if world_structure == "hub_and_districts":
        aesthetics.append("fellowship")
    aesthetics.append("narrative")
    dynamics = [
        "route planning before combat escalation",
        "telegraphed pressure and release during boss or elite loops",
        "reward conversion into the next mastery attempt",
    ]
    if party_model != "single_hero_focus":
        dynamics.append("role handoff and swap-triggered tempo control")
    if _live_service_enabled(game_request):
        dynamics.append("repeatable short-session return hooks without losing the chapter arc")
    return {
        "aesthetics": _unique(aesthetics),
        "dynamics": _unique(dynamics),
        "mechanics": _unique(mechanics),
    }


def _session_model(game_request: Dict[str, Any]) -> Dict[str, Any]:
    world_structure = _world_structure(game_request)
    live_service = _live_service_enabled(game_request)
    hooks = [
        "boot into a known safe anchor with one obvious next objective",
        "surface one short mastery or resource loop within the first few minutes",
        "end each session with a payoff and a visible future hook",
    ]
    if world_structure == "open_world_regions":
        hooks.append("make the route to the next combat beat readable from a landmark or terrain cue")
    if live_service:
        hooks.append("support low-friction return sessions through event, roster, or commission style beats")
    return {
        "micro_session_minutes": {"min": 10, "max": 20 if live_service else 25},
        "mid_session_minutes": {"min": 25, "max": 45},
        "macro_session_minutes": {"min": 60, "max": 120},
        "session_hooks": hooks,
    }


def _onboarding_ladder(game_request: Dict[str, Any]) -> List[Dict[str, Any]]:
    party_model = _party_model(game_request)
    ladder = [
        {
            "id": "safe_verb_rehearsal",
            "goal": "Teach movement, camera, and one primary action in a low-threat pocket.",
            "success_signal": "Players reach the first objective without hidden control friction.",
        },
        {
            "id": "first_pressure_read",
            "goal": "Introduce one telegraphed enemy or hazard that proves readable danger and recovery.",
            "success_signal": "Players understand dodge, guard, or spacing before punishment escalates.",
        },
        {
            "id": "reward_conversion",
            "goal": "Pay out one meaningful reward and force the player to convert it into visible power or utility.",
            "success_signal": "The next encounter feels measurably easier or more expressive.",
        },
        {
            "id": "route_choice",
            "goal": "Present a branch, shortcut, or optional encounter that shows the game values player intent.",
            "success_signal": "Players recognize why exploration matters beyond raw map size.",
        },
    ]
    if party_model != "single_hero_focus":
        ladder.append(
            {
                "id": "party_handoff",
                "goal": "Teach at least one swap, role handoff, or synergy payoff before the first boss exam.",
                "success_signal": "Players see that team expression changes encounter rhythm.",
            }
        )
    ladder.append(
        {
            "id": "boss_exam",
            "goal": "Use one high-readability boss or elite exam to recap movement, defense, and reward mastery.",
            "success_signal": "Players fail for understandable reasons and return with a clear improvement path.",
        }
    )
    return ladder


def _difficulty_model(game_request: Dict[str, Any]) -> Dict[str, Any]:
    specialized = _specialized(game_request)
    live_service = _live_service_enabled(game_request)
    phases = [
        {
            "id": "orientation",
            "target_experience": "High clarity, low punishments, strong feedback.",
            "knobs": ["enemy count", "telegraph length", "healing surplus"],
        },
        {
            "id": "pressure_ramp",
            "target_experience": "Teach pacing, stamina, spacing, and route commitment.",
            "knobs": ["mixed enemy waves", "environmental pressure", "resource spacing"],
        },
        {
            "id": "mastery_exam",
            "target_experience": "Demand deliberate defense and punish windows without becoming opaque.",
            "knobs": ["boss phase timings", "break windows", "checkpoint spacing"],
        },
    ]
    if live_service:
        phases.append(
            {
                "id": "returning_player_reentry",
                "target_experience": "Support returning players without flattening the mastery ceiling.",
                "knobs": ["event complexity", "daily objective length", "re-entry hints"],
            }
        )
    responses = [
        "lengthen telegraphs or reduce simultaneous pressure for struggling players",
        "increase checkpoint generosity after repeated failure clusters",
        "offer clearer route or quest guidance before adding raw damage",
    ]
    if "parry" in specialized:
        responses.append("slightly widen perfect-guard teaching windows during the first mastery phase")
    return {
        "curve": "flow_ramp_with_mastery_checks",
        "phases": phases,
        "dynamic_adjustment": {
            "enabled": True,
            "signals": [
                "repeat deaths in the same encounter family",
                "long time-to-clear without forward progress",
                "resource drain before objective completion",
                "drop-off after onboarding or re-entry beats",
            ],
            "responses": responses,
            "constraints": [
                "Never erase the need to learn dodge, guard, route, or boss punish windows.",
                "Do not silently invalidate player build choices or role expression.",
                "Prefer readability and recovery support over hidden stat nerfs.",
            ],
        },
        "fail_forward": [
            "teach through recoverable losses",
            "keep restart distance short around skill exams",
            "preserve earned rewards when possible so retries feel worthwhile",
        ],
    }


def _reinforcement_model(game_request: Dict[str, Any]) -> Dict[str, Any]:
    party_model = _party_model(game_request)
    reward_layers = [
        {
            "id": "instant_feedback",
            "purpose": "Hit confirms, telegraph readability, and small pickup rewards keep every action legible.",
        },
        {
            "id": "short_horizon_growth",
            "purpose": "Quest rewards, upgrade materials, and one immediate power choice reshape the next 10-30 minutes.",
        },
        {
            "id": "long_horizon_aspiration",
            "purpose": "Regions, roster arcs, and gear or skill milestones create reasons to return later.",
        },
    ]
    if party_model != "single_hero_focus":
        reward_layers.append(
            {
                "id": "team_expression",
                "purpose": "Reward roster planning and swap execution, not just one dominant build.",
            }
        )
    return {
        "feedback_contract": [
            "telegraph danger clearly before demanding precision",
            "confirm successful inputs immediately through animation, audio, and UI response",
            "pay out recovery windows, stagger states, or reward drops fast enough to feel earned",
            "show the next available action so momentum continues after the payoff",
        ],
        "reward_layers": reward_layers,
        "punishment_rules": [
            "avoid punitive losses that erase the lesson of the last encounter",
            "prefer repairable setbacks over hard dead-ends",
            "keep menu friction lower than gameplay friction during retries",
        ],
    }


def _balance_lab(game_request: Dict[str, Any]) -> Dict[str, Any]:
    party_model = _party_model(game_request)
    probes = [
        {
            "id": "enemy_health_band",
            "variable": "regular enemy health",
            "half_value_test": "0.5x health to locate the lower readability floor",
            "double_value_test": "2.0x health to identify pacing collapse",
            "success_signal": "Trash waves remain readable without feeling spongey.",
        },
        {
            "id": "boss_break_window",
            "variable": "boss stagger or punish window",
            "half_value_test": "halve the window to expose mastery ceiling pressure",
            "double_value_test": "double the window to expose trivialization",
            "success_signal": "Players can convert reads into payoff without auto-winning.",
        },
        {
            "id": "healing_and_revival_surplus",
            "variable": "healing economy and revive frequency",
            "half_value_test": "halve sustain to see if failures become opaque",
            "double_value_test": "double sustain to see if tension disappears",
            "success_signal": "Players survive long enough to learn, but still respect incoming pressure.",
        },
    ]
    if party_model != "single_hero_focus":
        probes.append(
            {
                "id": "swap_resource_regen",
                "variable": "swap, burst, or team resource regeneration",
                "half_value_test": "slow regeneration to test role dependency",
                "double_value_test": "speed regeneration to detect spam loops",
                "success_signal": "Swaps stay expressive without collapsing into permanent invulnerability or spam.",
            }
        )
    return {
        "doubling_halving_probes": probes,
        "anti_minmax_rules": [
            "Do not let one role or affinity solve every boss and route.",
            "Keep early meta picks strong enough to teach mastery, not so dominant that later roster options become cosmetic.",
            "Test reward sources and sinks together so one progression lane does not invalidate the others.",
        ],
        "telemetry_watch": [
            "death clusters by encounter family",
            "boss clear time bands",
            "resource hoarding versus starvation",
            "roster usage concentration",
        ],
    }


def _accessibility_baseline(game_request: Dict[str, Any]) -> Dict[str, Any]:
    required = [
        "full subtitle coverage for important speech and mission-critical barks",
        "remappable controls with per-action rebinding",
        "toggle alternatives for hold actions",
        "separate audio sliders for music, speech, and effects",
        "camera sensitivity and camera shake controls",
        "difficulty choices or assist surfaces that do not break progression",
        "visual redundancy for information that would otherwise be audio-only",
        "settings persistence and visible accessibility summary in-game",
    ]
    combat_specific = [
        "distinct telegraphs for elite and boss danger states",
        "timing-critical actions should have readable visual as well as audio cues",
        "practice-safe onboarding or sandbox pockets before demanding precision chains",
    ]
    if _world_structure(game_request) in {"open_world_regions", "hub_and_districts"}:
        combat_specific.append("landmarks, quest guidance, or navigation aids that reduce re-entry disorientation")
    return {
        "required_features": required,
        "combat_specific_features": combat_specific,
        "ui_rules": [
            "keep essential HUD elements readable at a glance",
            "avoid color-only communication for objectives or enemy states",
            "use large-enough interaction targets for menus and touch-adjacent surfaces",
        ],
    }


def _runtime_guardrails(
    game_request: Dict[str, Any],
    runtime_delivery_plan: Dict[str, Any],
    reference_intelligence: Dict[str, Any],
) -> Dict[str, Any]:
    runtime = str(runtime_delivery_plan.get("runtime", target_runtime({}, None))).strip() or "reverie_engine"
    reference_stack = [
        str(item.get("reference_id", "")).strip()
        for item in reference_intelligence.get("recommended_reference_stack", []) or []
        if str(item.get("reference_id", "")).strip()
    ]
    scalability_patterns = [
        "split the game into verified region or district cells before chasing continuous mega-world breadth",
        "budget AI, VFX, and landmark density around the slice critical path first",
        "promote authored content only after it passes import, readability, and frame-budget review",
    ]
    scene_authoring_rules = [
        "author one clear route from spawn to objective to payoff before widening the playable footprint",
        "treat navigation, camera framing, and combat arenas as one readability problem",
        "keep encounter spaces sized for telegraphs, lock-on readability, and recovery paths",
    ]
    source_links = [
        {
            "id": "mda_framework",
            "label": "MDA framework",
            "source": "https://users.cs.northwestern.edu/~hunicke/MDA.pdf",
            "focus": "connect mechanics, dynamics, and player aesthetics",
        },
        {
            "id": "orange_violin_gamedev_pack",
            "label": "OrangeViolin game-design capability gist",
            "source": "https://gist.github.com/OrangeViolin/53ad898cdbc8734d8bb5c6a6ddf5cec4",
            "focus": "user-centered design, flow, DDA, reinforcement, balance, and error handling",
        },
        {
            "id": "game_accessibility_guidelines",
            "label": "Game Accessibility Guidelines",
            "source": "https://gameaccessibilityguidelines.com/basic/",
            "focus": "baseline accessibility features that should be planned early",
        },
    ]
    if runtime == "godot":
        scalability_patterns.extend(
            [
                "use NavigationAgent3D and region-aware navigation authoring for enemies and escorts",
                "combine visibility ranges, LOD, and occlusion for large 3D scene budgets",
                "prefer hub-to-region or region-cell growth over uncontrolled always-loaded worlds",
            ]
        )
        scene_authoring_rules.extend(
            [
                "bake navigation and validate agent path distances against actual movement speed",
                "apply visibility ranges to distant landmarks, props, and grouped geometry to reduce draw calls",
                "bake or author occluders for dense indoor or district spaces where line-of-sight can be broken",
            ]
        )
        source_links.extend(
            [
                {
                    "id": "godot_navigation_3d",
                    "label": "Godot 3D navigation overview",
                    "source": "https://docs.godotengine.org/en/stable/tutorials/navigation/navigation_introduction_3d.html",
                    "focus": "navigation regions and NavigationAgent3D for 3D movement",
                },
                {
                    "id": "godot_visibility_ranges",
                    "label": "Godot visibility ranges (HLOD)",
                    "source": "https://docs.godotengine.org/en/stable/tutorials/3d/visibility_ranges.html",
                    "focus": "hierarchical visibility ranges for large 3D scenes",
                },
                {
                    "id": "godot_occlusion_culling",
                    "label": "Godot occlusion culling",
                    "source": "https://docs.godotengine.org/en/stable/tutorials/3d/occlusion_culling.html",
                    "focus": "occluder-based culling and large-scene performance",
                },
            ]
        )
    if _world_structure(game_request) == "open_world_regions":
        scalability_patterns.append("gate each new region behind one landmark, one traversal lesson, and one boss or objective anchor")
    if _world_structure(game_request) == "hub_and_districts":
        scalability_patterns.append("treat each district as a reusable mission shell with persistent landmarks and short re-entry loops")
    return {
        "runtime": runtime,
        "local_reference_hooks": reference_stack,
        "scalability_patterns": _unique(scalability_patterns),
        "scene_authoring_rules": _unique(scene_authoring_rules),
        "source_links": source_links,
    }


def _genre_growth_templates(game_request: Dict[str, Any]) -> List[Dict[str, Any]]:
    world_structure = _world_structure(game_request)
    templates = [
        {
            "id": "region_or_district_cell",
            "beats": [
                "arrival anchor",
                "landmark route",
                "combat or challenge midpoint",
                "reward conversion",
                "boss or objective payoff",
            ],
        },
        {
            "id": "quest_loop",
            "beats": [
                "goal reveal",
                "route learning",
                "pressure escalation",
                "payoff and handoff",
            ],
        },
    ]
    if _party_model(game_request) != "single_hero_focus":
        templates.append(
            {
                "id": "roster_wave",
                "beats": [
                    "new role or affinity arrives",
                    "one boss or route counterpick is unlocked",
                    "party mastery pressure rises without invalidating the starter team",
                ],
            }
        )
    if _live_service_enabled(game_request):
        templates.append(
            {
                "id": "version_update",
                "beats": [
                    "one event layer",
                    "one progression or roster beat",
                    "one region-pressure objective",
                    "one clean return hook for the next cycle",
                ],
            }
        )
    if world_structure == "hub_and_districts":
        templates.append(
            {
                "id": "district_mission_shell",
                "beats": [
                    "hub briefing",
                    "mission instancing or district deployment",
                    "combat remix or boss spike",
                    "hub return with social or progression follow-up",
                ],
            }
        )
    return templates


def build_design_intelligence(
    game_request: Dict[str, Any],
    blueprint: Dict[str, Any],
    system_bundle: Dict[str, Any],
    content_expansion: Dict[str, Any],
    runtime_delivery_plan: Dict[str, Any],
    *,
    reference_intelligence: Dict[str, Any] | None = None,
    runtime_profile: Dict[str, Any] | None = None,
) -> Dict[str, Any]:
    """Build default game-creation intelligence for the project."""

    reference_intelligence = dict(reference_intelligence or {})
    personas = _player_personas(game_request)
    capabilities = _default_capabilities(game_request)
    onboarding_ladder = _onboarding_ladder(game_request)
    difficulty_model = _difficulty_model(game_request)
    reinforcement_model = _reinforcement_model(game_request)
    balance_lab = _balance_lab(game_request)
    accessibility_baseline = _accessibility_baseline(game_request)
    runtime_guardrails = _runtime_guardrails(game_request, runtime_delivery_plan, reference_intelligence)
    region_ids = [
        str(item.get("id", "")).strip()
        for item in content_expansion.get("region_seeds", []) or []
        if str(item.get("id", "")).strip()
    ]
    return {
        "schema_version": "reverie.design_intelligence/1",
        "project_name": project_name(game_request, blueprint),
        "generated_at": _utc_now(),
        "runtime": target_runtime(blueprint, runtime_profile),
        "source_library": runtime_guardrails["source_links"],
        "default_capabilities": capabilities,
        "player_personas": personas,
        "mda_map": _mda_map(game_request, system_bundle),
        "session_model": _session_model(game_request),
        "onboarding_ladder": onboarding_ladder,
        "difficulty_model": difficulty_model,
        "reinforcement_model": reinforcement_model,
        "balance_lab": balance_lab,
        "accessibility_baseline": accessibility_baseline,
        "runtime_guardrails": runtime_guardrails,
        "genre_growth_templates": _genre_growth_templates(game_request),
        "next_design_prompts": _unique(
            [
                "tighten onboarding, readability, and reward conversion before widening content breadth",
                "run one doubling-halving balance pass on the current slice before adding new enemy families",
                "verify accessibility defaults, return-session clarity, and fail-forward behavior against the latest slice",
                "use the same design-intelligence artifact to guide the next region, district, boss, or roster beat",
            ]
        ),
        "active_region_ids": region_ids,
    }


def design_playbook_markdown(plan: Dict[str, Any]) -> str:
    """Render a readable design playbook from the design-intelligence artifact."""

    lines = [f"# Design Playbook: {plan.get('project_name', 'Untitled Reverie Slice')}", ""]
    lines.append(f"Runtime: {plan.get('runtime', 'reverie_engine')}")
    lines.append("")
    lines.append("## Default Capabilities")
    for item in plan.get("default_capabilities", []):
        lines.append(f"- {item.get('id', 'capability')}: {item.get('goal', '')}")
    lines.append("")
    lines.append("## Player Personas")
    for item in plan.get("player_personas", []):
        lines.append(f"- {item.get('id', 'persona')}: {item.get('fantasy', '')}")
    lines.append("")
    lines.append("## MDA Map")
    for key in ("aesthetics", "dynamics", "mechanics"):
        values = plan.get("mda_map", {}).get(key, [])
        lines.append(f"- {key}: {', '.join(values) if values else 'none'}")
    lines.append("")
    lines.append("## Onboarding Ladder")
    for item in plan.get("onboarding_ladder", []):
        lines.append(f"- {item.get('id', 'beat')}: {item.get('goal', '')}")
    lines.append("")
    lines.append("## Difficulty Model")
    lines.append(f"- Curve: {plan.get('difficulty_model', {}).get('curve', 'flow_ramp_with_mastery_checks')}")
    for item in plan.get("difficulty_model", {}).get("phases", []):
        lines.append(f"- {item.get('id', 'phase')}: {item.get('target_experience', '')}")
    lines.append("")
    lines.append("## Feedback And Rewards")
    for item in plan.get("reinforcement_model", {}).get("feedback_contract", []):
        lines.append(f"- {item}")
    lines.append("")
    lines.append("## Balance Lab")
    for item in plan.get("balance_lab", {}).get("doubling_halving_probes", []):
        lines.append(f"- {item.get('id', 'probe')}: {item.get('variable', '')}")
    lines.append("")
    lines.append("## Accessibility Baseline")
    for item in plan.get("accessibility_baseline", {}).get("required_features", []):
        lines.append(f"- {item}")
    lines.append("")
    lines.append("## Runtime Guardrails")
    for item in plan.get("runtime_guardrails", {}).get("scalability_patterns", []):
        lines.append(f"- {item}")
    lines.append("")
    lines.append("## Source Library")
    for item in plan.get("source_library", []):
        lines.append(f"- {item.get('label', 'source')}: {item.get('source', '')}")
    lines.append("")
    return "\n".join(lines)
