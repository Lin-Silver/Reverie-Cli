"""Large-scale production direction builders for Reverie-Gamer."""

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


def _live_service_enabled(game_request: Dict[str, Any]) -> bool:
    return bool(game_request.get("production", {}).get("live_service_profile", {}).get("enabled", False))


def _display_title(raw: str, fallback: str) -> str:
    parts = [part for part in str(raw or "").replace("-", "_").split("_") if part]
    return " ".join(part.capitalize() for part in parts) or fallback


def _combat_affinities(game_request: Dict[str, Any]) -> List[str]:
    references = {item.lower() for item in _references(game_request)}
    specialized = _specialized(game_request)
    if "elemental_reaction" in specialized or {"genshin impact", "wuthering waves"} & references:
        return ["flare", "tide", "volt", "gale", "frost", "terra"]
    if "urban_hub" in specialized or "zenless zone zero" in references:
        return ["shock", "break", "guard", "drive"]
    return ["steel", "arc", "guard", "rush"]


def build_campaign_program(
    game_request: Dict[str, Any],
    blueprint: Dict[str, Any],
    content_expansion: Dict[str, Any],
    world_program: Dict[str, Any],
    faction_graph: Dict[str, Any],
    *,
    runtime_profile: Dict[str, Any] | None = None,
) -> Dict[str, Any]:
    """Build a chapter-and-region campaign roadmap for large-scale growth."""

    regions = list(world_program.get("regions", []) or content_expansion.get("region_seeds", []) or [])
    quest_arcs = list(content_expansion.get("quest_arcs", []) or [])
    factions = list(faction_graph.get("factions", []) or [])
    live_service = _live_service_enabled(game_request)
    active_region_id = str(world_program.get("active_region_id", "")).strip()
    boss_priority_region_id = str(world_program.get("boss_priority_region_id", "")).strip()

    chapter_order: List[Dict[str, Any]] = []
    for index, region in enumerate(regions, start=1):
        region_id = str(region.get("id", "")).strip() or f"region_{index}"
        related_arc_ids = [
            str(arc.get("id", "")).strip()
            for arc in quest_arcs
            if region_id in {str(item).strip() for item in arc.get("regions", []) or []}
        ]
        featured_faction_ids = [
            str(faction.get("id", "")).strip()
            for faction in factions
            if region_id in {str(item).strip() for item in faction.get("regions", []) or []}
        ]
        story_role = "opening"
        if index == 2:
            story_role = "escalation"
        elif index == 3:
            story_role = "reveal"
        elif index > 3:
            story_role = "post_launch_expansion"

        release_wave = "launch" if index <= 3 else f"version_1_{index - 2}"
        chapter_order.append(
            {
                "id": f"chapter_{index:02d}_{region_id}",
                "title": f"Chapter {index}: {_display_title(region_id, f'Region {index}')}",
                "region_id": region_id,
                "biome": str(region.get("biome", "")),
                "signature_landmark": str(region.get("signature_landmark", "")),
                "story_role": story_role,
                "release_wave": release_wave,
                "quest_arc_ids": _unique(related_arc_ids),
                "featured_faction_ids": _unique(featured_faction_ids),
                "progression_gate": str(region.get("progression_gate", "complete the current frontier milestone")),
                "boss_anchor_id": f"{region_id}_boss_anchor",
                "is_active": region_id == active_region_id,
                "is_boss_priority": region_id == boss_priority_region_id,
            }
        )

    return {
        "schema_version": "reverie.campaign_program/1",
        "project_name": project_name(game_request, blueprint),
        "generated_at": _utc_now(),
        "runtime": target_runtime(blueprint, runtime_profile),
        "campaign_model": "live_region_chapters" if live_service else "chaptered_region_growth",
        "active_region_id": active_region_id,
        "boss_priority_region_id": boss_priority_region_id,
        "launch_window": {
            "starter_region_id": str(regions[0].get("id", "")) if regions else "",
            "launch_region_ids": [item["region_id"] for item in chapter_order[:3]],
            "first_boss_region_id": boss_priority_region_id or (chapter_order[0]["region_id"] if chapter_order else ""),
        },
        "chapter_order": chapter_order,
        "macro_arcs": [
            {
                "id": "awakening_frontier",
                "goal": "Introduce the first traversal and combat grammar while locking the project fantasy early.",
                "chapter_ids": [item["id"] for item in chapter_order[:2]],
            },
            {
                "id": "faction_breakpoint",
                "goal": "Escalate the stakes through faction conflict, questline crossover, and boss pressure.",
                "chapter_ids": [item["id"] for item in chapter_order[1:4]],
            },
        ],
        "set_piece_ladder": [
            "arrival and onboarding route",
            "mid-route combat escalation",
            "signature regional set piece",
            "boss or faction climax",
        ],
        "continuity_rules": [
            "Every new chapter must preserve stable region, quest, and faction identifiers.",
            "Launch chapters should deepen the same verbs before post-launch chapters broaden the world map.",
            "Boss anchors should pay off the active region instead of existing as detached arena fights.",
        ],
    }


def build_roster_strategy(
    game_request: Dict[str, Any],
    blueprint: Dict[str, Any],
    gameplay_factory: Dict[str, Any],
    character_kits: Dict[str, Any],
    *,
    runtime_profile: Dict[str, Any] | None = None,
) -> Dict[str, Any]:
    """Build a scalable party, roster, and release-wave strategy."""

    live_service = _live_service_enabled(game_request)
    party_model = _party_model(game_request)
    affinities = _combat_affinities(game_request)
    starter_roles = ["vanguard"]
    if party_model != "single_hero_focus":
        starter_roles = ["vanguard", "breaker", "support", "controller"]
    elif "ranged_reactive" in str(game_request.get("experience", {}).get("combat_model", "")):
        starter_roles = ["ranger"]

    starter_team = []
    for index, role in enumerate(starter_roles, start=1):
        starter_team.append(
            {
                "id": f"starter_{role}_{index}",
                "combat_role": role,
                "combat_affinity": affinities[(index - 1) % len(affinities)],
                "release_window": "launch",
                "signature_job": {
                    "vanguard": "drive the field and own the first readable combo loop",
                    "breaker": "convert staggers, guard breaks, and boss punish windows",
                    "support": "stabilize health, buffs, and tempo recovery",
                    "controller": "shape spacing, ranged setups, and route safety",
                    "ranger": "control mid-range pressure and encounter pacing",
                }.get(role, "cover the core fantasy cleanly"),
            }
        )

    launch_roster_target = len(starter_team)
    if party_model != "single_hero_focus":
        launch_roster_target = 8 if live_service else 6

    launch_roster_waves = [
        {
            "id": "launch_core",
            "cadence": "launch",
            "target_character_count": len(starter_team),
            "focus": "Ship the role-complete starter team and a first boss counterpick.",
            "hero_ids": [hero["id"] for hero in starter_team],
        },
        {
            "id": "version_1_1_wave" if live_service else "post_slice_wave",
            "cadence": "first_update" if live_service else "post_slice",
            "target_character_count": min(launch_roster_target, len(starter_team) + 2),
            "focus": "Add a region-linked recruitable wave that widens route planning and boss solutions.",
            "hero_ids": [f"expansion_wave_{index}" for index in range(1, 3)],
        },
    ]
    if live_service:
        launch_roster_waves.append(
            {
                "id": "version_1_2_wave",
                "cadence": "second_update",
                "target_character_count": launch_roster_target,
                "focus": "Rotate in a new event-facing hero wave without invalidating the launch roster.",
                "hero_ids": [f"service_wave_{index}" for index in range(1, 3)],
            }
        )

    return {
        "schema_version": "reverie.roster_strategy/1",
        "project_name": project_name(game_request, blueprint),
        "generated_at": _utc_now(),
        "runtime": target_runtime(blueprint, runtime_profile),
        "party_model": party_model,
        "launch_roster_target": launch_roster_target,
        "combat_affinities": affinities,
        "role_matrix": starter_roles,
        "starter_team": starter_team,
        "launch_roster_waves": launch_roster_waves,
        "weapon_families": ["blade", "gauntlet", "focus", "rifle"] if party_model != "single_hero_focus" else ["blade"],
        "progression_tracks": [
            "level and breakthrough",
            "signature skill upgrades",
            "gear or relic optimization",
            "team synergy passives" if party_model != "single_hero_focus" else "hero mastery",
        ],
        "runtime_seed_hooks": {
            "camera_presets": [item.get("id", "") for item in gameplay_factory.get("camera_presets", []) or []],
            "hero_kit_count": len(character_kits.get("hero_kits", []) or []),
        },
        "guardrails": [
            "Do not add new roster waves faster than the role matrix, boss design, and gear economy can support.",
            "Starter heroes should cover onboarding, boss readability, sustain, and route-solving before rarer variants are introduced.",
            "Every roster wave should unlock at least one new quest, boss, or region interaction instead of existing only as collection filler.",
        ],
    }


def build_live_ops_plan(
    game_request: Dict[str, Any],
    blueprint: Dict[str, Any],
    campaign_program: Dict[str, Any],
    roster_strategy: Dict[str, Any],
    runtime_delivery_plan: Dict[str, Any],
    *,
    runtime_profile: Dict[str, Any] | None = None,
) -> Dict[str, Any]:
    """Build a release-train and service-cadence plan for large projects."""

    live_service_profile = dict(game_request.get("production", {}).get("live_service_profile", {}) or {})
    enabled = bool(live_service_profile.get("enabled", False))
    chapter_order = list(campaign_program.get("chapter_order", []) or [])
    roster_waves = list(roster_strategy.get("launch_roster_waves", []) or [])
    selected_runtime = str(runtime_delivery_plan.get("runtime", target_runtime(blueprint, runtime_profile)))

    release_beats = [
        {
            "id": "launch_1_0",
            "delivery_window": "launch",
            "region_ids": [item.get("region_id", "") for item in chapter_order[:2]],
            "roster_wave_id": roster_waves[0].get("id", "") if roster_waves else "",
            "focus": "Ship the verified slice plus enough durable systems to support immediate continuation.",
        }
    ]
    if enabled:
        release_beats.extend(
            [
                {
                    "id": "version_1_1",
                    "delivery_window": "six_weeks",
                    "region_ids": [item.get("region_id", "") for item in chapter_order[2:3]],
                    "roster_wave_id": roster_waves[1].get("id", "") if len(roster_waves) > 1 else "",
                    "focus": "Add one recruitable wave, one event layer, and one new frontier objective.",
                },
                {
                    "id": "version_1_2",
                    "delivery_window": "twelve_weeks",
                    "region_ids": [item.get("region_id", "") for item in chapter_order[3:4]],
                    "roster_wave_id": roster_waves[2].get("id", "") if len(roster_waves) > 2 else "",
                    "focus": "Promote the campaign into a visible multi-region service cadence with repeatable endgame hooks.",
                },
            ]
        )
    else:
        release_beats.append(
            {
                "id": "expansion_pack_1",
                "delivery_window": "post_launch",
                "region_ids": [item.get("region_id", "") for item in chapter_order[2:4]],
                "roster_wave_id": roster_waves[1].get("id", "") if len(roster_waves) > 1 else "",
                "focus": "Turn the slice into the first premium expansion arc with one new region and one new roster beat.",
            }
        )

    return {
        "schema_version": "reverie.live_ops_plan/1",
        "project_name": project_name(game_request, blueprint),
        "generated_at": _utc_now(),
        "runtime": selected_runtime,
        "service_model": "live_service" if enabled else "boxed_release_plus_expansions",
        "cadence": str(live_service_profile.get("cadence", "major_expansion_packs" if not enabled else "six_week_content_cycles")),
        "release_beats": release_beats,
        "event_pillars": [
            "combat mastery event",
            "regional story event",
            "boss challenge refresh",
            "social or photo-mode showcase" if enabled else "campaign expansion spotlight",
        ],
        "endgame_lanes": [
            "boss rematch ladder",
            "score attack or survival trials",
            "route-optimization challenge runs",
        ],
        "economy_loops": {
            "sources": ["quest completion", "regional challenges", "boss clears", "event participation" if enabled else "campaign milestones"],
            "sinks": ["hero growth", "gear tuning", "crafting", "cosmetic unlocks"],
            "guardrails": [
                "Keep the verified slice fully enjoyable without requiring later service beats.",
                "Use events to remix existing systems before demanding entirely new production lanes.",
                "Never let monetization or event pacing outgrow the project's current combat and content quality bar.",
            ],
        },
        "delivery_rules": [
            "Every release beat must point back to a chapter, roster wave, and runtime validation plan.",
            "Do not widen cadence until the slice score and quality gates remain stable across at least one full iteration loop.",
            "Treat post-launch beats as structured expansions of the same production memory, not disconnected mini-projects.",
        ],
    }


def build_production_operating_model(
    game_request: Dict[str, Any],
    blueprint: Dict[str, Any],
    runtime_selection: Dict[str, Any],
    runtime_delivery_plan: Dict[str, Any],
    asset_pipeline: Dict[str, Any],
    *,
    reference_intelligence: Dict[str, Any] | None = None,
    runtime_profile: Dict[str, Any] | None = None,
) -> Dict[str, Any]:
    """Build an operating model that keeps large projects coherent across many turns."""

    reference_intelligence = dict(reference_intelligence or runtime_selection.get("reference_intelligence", {}) or {})
    reference_stack = list(reference_intelligence.get("recommended_reference_stack", []) or [])
    toolchain_matrix = list(reference_intelligence.get("toolchain_matrix", []) or [])
    adoption_plan = list(reference_intelligence.get("adoption_plan", []) or [])
    live_service = _live_service_enabled(game_request)
    runtime = str(runtime_delivery_plan.get("runtime", target_runtime(blueprint, runtime_profile)))

    workstreams = [
        {
            "id": "program_direction",
            "goal": "Keep the high-level fantasy, scope control, milestones, and risk ledger aligned.",
            "artifacts": [
                "artifacts/game_program.json",
                "artifacts/milestone_board.json",
                "artifacts/risk_register.json",
                "artifacts/campaign_program.json",
            ],
        },
        {
            "id": "runtime_and_systems",
            "goal": "Carry the slice through runtime delivery, system integration, and validation without drift.",
            "artifacts": [
                "artifacts/runtime_capability_graph.json",
                "artifacts/runtime_delivery_plan.json",
                "artifacts/system_specs.json",
                "artifacts/task_graph.json",
            ],
        },
        {
            "id": "world_and_quest",
            "goal": "Grow regions, quests, bosses, and faction pressure from the same durable world memory.",
            "artifacts": [
                "artifacts/world_program.json",
                "artifacts/region_kits.json",
                "artifacts/faction_graph.json",
                "artifacts/questline_program.json",
            ],
        },
        {
            "id": "character_roster",
            "goal": "Scale the roster, gameplay factory, and boss-counter matrix without fragmenting combat feel.",
            "artifacts": [
                "artifacts/character_kits.json",
                "artifacts/gameplay_factory.json",
                "artifacts/boss_arc.json",
                "artifacts/roster_strategy.json",
            ],
        },
        {
            "id": "asset_and_animation",
            "goal": "Promote generated starter assets into validated production-ready kits with reviewable budgets.",
            "artifacts": [
                "artifacts/asset_pipeline.json",
                "artifacts/environment_kits.json",
                "artifacts/animation_plan.json",
                "artifacts/asset_budget.json",
            ],
        },
        {
            "id": "quality_and_scale",
            "goal": "Keep playtest evidence, continuation prompts, and long-cycle scaling attached to the project root.",
            "artifacts": [
                "playtest/quality_gates.json",
                "playtest/performance_budget.json",
                "playtest/combat_feel_report.json",
                "playtest/slice_score.json",
                "artifacts/expansion_backlog.json",
                "artifacts/resume_state.json",
                "artifacts/live_ops_plan.json",
                "artifacts/production_operating_model.json",
            ],
        },
    ]
    if live_service:
        workstreams.append(
            {
                "id": "service_release_train",
                "goal": "Translate live-service ambitions into a versioned release train that still respects slice quality gates.",
                "artifacts": [
                    "artifacts/live_ops_plan.json",
                    "playtest/continuation_recommendations.md",
                ],
            }
        )
    if toolchain_matrix:
        workstreams.append(
            {
                "id": "reference_and_toolchain",
                "goal": "Keep runtime templates, DCC tooling, and asset validation references aligned with the active production lane.",
                "artifacts": [
                    "artifacts/reference_intelligence.json",
                    "artifacts/asset_pipeline.json",
                    "artifacts/runtime_delivery_plan.json",
                ],
            }
        )

    validation_stack = [
        "runtime validation",
        "quality gates",
        "slice score",
        "asset import review",
    ]
    import_flags = list(asset_pipeline.get("import_profile", {}).get("import_flags", []) or [])
    validation_stack.extend(str(item) for item in import_flags if str(item).strip())

    return {
        "schema_version": "reverie.production_operating_model/1",
        "project_name": project_name(game_request, blueprint),
        "generated_at": _utc_now(),
        "runtime": runtime,
        "delivery_model": "slice_first_service_scale" if live_service else "slice_first_campaign_growth",
        "workstreams": workstreams,
        "toolchain": {
            "runtime_root": str(runtime_delivery_plan.get("runtime_root", ".")),
            "reference_stack": reference_stack,
            "toolchain_matrix": toolchain_matrix,
            "adoption_plan": adoption_plan,
            "dcc_stack": [
                item.get("reference_id", "")
                for item in reference_stack
                if item.get("reference_id", "") in {"blender", "blockbench", "gltf-blender-io"}
            ],
            "validation_stack": _unique(validation_stack),
        },
        "governance": {
            "artifact_open_order": [
                "artifacts/production_directive.json",
                "artifacts/game_program.json",
                "artifacts/campaign_program.json",
                "artifacts/roster_strategy.json",
                "artifacts/live_ops_plan.json",
                "artifacts/production_operating_model.json",
                "artifacts/runtime_delivery_plan.json",
                "artifacts/content_expansion.json",
                "artifacts/asset_pipeline.json",
                "artifacts/resume_state.json",
                "playtest/slice_score.json",
            ],
            "promotion_gates": [
                "Do not widen chapters or roster waves until quality gates and combat feel both remain reviewable.",
                "Keep the runtime delivery plan authoritative for engine-root decisions and validation blockers.",
                "Refresh continuation prompts only after the latest backlog, slice score, and scale artifacts agree on the next milestone.",
            ],
            "handoff_rules": [
                "Every new region, roster wave, or live event must map back to a durable artifact before implementation.",
                "Prefer extending the current project memory over creating new one-off production documents.",
            ],
        },
    }
