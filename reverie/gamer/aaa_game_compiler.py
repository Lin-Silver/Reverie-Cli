"""AAA-quality game program compiler for large-scale 3D games."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List
import json


def compile_aaa_game_program(
    prompt: str,
    *,
    project_name: str = "",
    target_quality: str = "aaa",
) -> Dict[str, Any]:
    """
    Compile a single prompt into a comprehensive AAA game program.
    
    This is the entry point for generating large-scale 3D games like
    Genshin Impact, Wuthering Waves, or Zenless Zone Zero.
    """
    
    from .prompt_compiler import compile_game_prompt
    from .scope_estimator import estimate_scope
    
    # First pass: basic compilation
    game_request = compile_game_prompt(
        prompt,
        project_name=project_name,
        overrides={"target_quality": target_quality},
    )
    
    # Enhance for AAA quality
    enhanced_request = _enhance_for_aaa(game_request, prompt)
    
    # Generate comprehensive game program
    game_program = _generate_game_program(enhanced_request, prompt)
    
    # Generate game bible
    game_bible = _generate_game_bible(enhanced_request, game_program)
    
    # Generate feature matrix
    feature_matrix = _generate_feature_matrix(enhanced_request, game_program)
    
    # Generate content matrix
    content_matrix = _generate_content_matrix(enhanced_request, game_program)
    
    # Generate milestone board
    milestone_board = _generate_milestone_board(enhanced_request, game_program)
    
    # Generate risk register
    risk_register = _generate_risk_register(enhanced_request, game_program)
    
    return {
        "schema_version": "reverie.aaa_game_program/1",
        "meta": {
            "project_name": game_request.get("meta", {}).get("project_name", "Untitled AAA Game"),
            "generated_at": _utc_now(),
            "target_quality": target_quality,
            "source_prompt": prompt,
        },
        "game_request": enhanced_request,
        "game_program": game_program,
        "game_bible": game_bible,
        "feature_matrix": feature_matrix,
        "content_matrix": content_matrix,
        "milestone_board": milestone_board,
        "risk_register": risk_register,
    }


def _enhance_for_aaa(game_request: Dict[str, Any], prompt: str) -> Dict[str, Any]:
    """Enhance game request with AAA-quality features."""
    
    enhanced = dict(game_request)
    source_prompt = prompt.lower()
    
    # Detect if this is a Genshin/Wuthering-like game
    is_genshin_like = any(word in source_prompt for word in [
        "genshin", "原神", "wuthering", "鸣潮", "zenless", "绝区零",
        "open world", "开放世界", "gacha", "抽卡"
    ])
    
    if is_genshin_like:
        enhanced = _enhance_for_genshin_like(enhanced, source_prompt)
    
    # Add AAA systems
    systems = enhanced.get("systems", {}).get("required", [])
    aaa_systems = [
        "advanced_camera",
        "traversal_abilities",
        "elemental_system",
        "character_swap",
        "gacha_system",
        "daily_quests",
        "achievement_system",
        "photo_mode",
        "co_op_multiplayer",
        "world_streaming",
        "weather_system",
        "day_night_cycle",
        "npc_ai",
        "dialogue_system",
        "cutscene_system",
        "voice_acting",
        "localization",
    ]
    
    for system in aaa_systems:
        if system not in systems:
            systems.append(system)
    
    enhanced["systems"]["required"] = systems
    
    # Enhance quality targets
    quality_targets = enhanced.get("quality_targets", {})
    quality_targets.update({
        "target_fps": 60,
        "target_resolution": "4K",
        "target_platforms": ["PC", "PS5", "Xbox Series X", "Mobile"],
        "graphics_quality": "AAA",
        "animation_quality": "Motion Captured",
        "audio_quality": "Orchestral + Voice Acting",
        "world_size": "Large Open World (10+ km²)",
        "content_hours": "100+ hours",
    })
    enhanced["quality_targets"] = quality_targets
    
    return enhanced


def _enhance_for_genshin_like(game_request: Dict[str, Any], prompt: str) -> Dict[str, Any]:
    """Enhance for Genshin Impact / Wuthering Waves style games."""
    
    enhanced = dict(game_request)
    
    # Add Genshin-specific systems
    enhanced["genshin_features"] = {
        "elemental_system": {
            "elements": ["Pyro", "Hydro", "Electro", "Cryo", "Anemo", "Geo", "Dendro"],
            "reactions": True,
            "resonance": True,
        },
        "character_system": {
            "gacha": True,
            "party_size": 4,
            "character_progression": ["level", "ascension", "talents", "constellations"],
            "weapon_system": True,
            "artifact_system": True,
        },
        "world_system": {
            "regions": ["Mondstadt", "Liyue", "Inazuma", "Sumeru", "Fontaine"],
            "teleport_waypoints": True,
            "statues_of_seven": True,
            "domains": True,
            "world_bosses": True,
        },
        "progression_system": {
            "adventure_rank": True,
            "world_level": True,
            "resin_system": True,
            "daily_commissions": True,
        },
        "social_features": {
            "co_op": True,
            "max_players": 4,
            "friend_system": True,
            "teapot_housing": True,
        },
    }
    
    # Enhance art direction
    art_direction = enhanced.get("creative_target", {}).get("art_direction", {})
    art_direction.update({
        "style": "Anime-inspired cel-shaded 3D",
        "character_design": "Highly detailed anime characters with unique silhouettes",
        "environment_style": "Painterly, vibrant, fantasy landscapes",
        "lighting": "Dynamic time-of-day with volumetric effects",
        "effects": "Stylized elemental effects with high visual impact",
    })
    
    return enhanced


def _generate_game_program(game_request: Dict[str, Any], prompt: str) -> Dict[str, Any]:
    """Generate comprehensive game program document."""
    
    creative = game_request.get("creative_target", {})
    experience = game_request.get("experience", {})
    production = game_request.get("production", {})
    
    return {
        "vision_statement": _generate_vision_statement(game_request, prompt),
        "core_pillars": _generate_core_pillars(game_request),
        "target_audience": _generate_target_audience(game_request),
        "unique_selling_points": _generate_usps(game_request),
        "gameplay_pillars": {
            "combat": _generate_combat_pillar(game_request),
            "exploration": _generate_exploration_pillar(game_request),
            "progression": _generate_progression_pillar(game_request),
            "social": _generate_social_pillar(game_request),
        },
        "world_design": _generate_world_design(game_request),
        "narrative_framework": _generate_narrative_framework(game_request),
        "monetization_strategy": _generate_monetization(game_request),
        "live_service_plan": _generate_live_service_plan(game_request),
    }


def _generate_vision_statement(game_request: Dict[str, Any], prompt: str) -> str:
    """Generate vision statement for the game."""
    
    creative = game_request.get("creative_target", {})
    genre = creative.get("primary_genre", "action_rpg")
    references = creative.get("references", [])
    
    if "Genshin Impact" in references or "Wuthering Waves" in references:
        return (
            "Create an expansive open-world action RPG that combines breathtaking exploration, "
            "dynamic elemental combat, and a rich gacha-based character collection system. "
            "Players will traverse stunning fantasy landscapes, master elemental reactions, "
            "and build their dream team of unique characters in an ever-expanding world."
        )
    
    return (
        f"Deliver a compelling {genre} experience that combines engaging gameplay, "
        "memorable characters, and a vibrant world that players will want to return to daily."
    )


def _generate_core_pillars(game_request: Dict[str, Any]) -> List[str]:
    """Generate core design pillars."""
    
    return [
        "Exploration: Reward curiosity with hidden treasures, secrets, and breathtaking vistas",
        "Combat: Deliver satisfying, skill-based combat with clear feedback and progression",
        "Collection: Build and customize your perfect team of characters and equipment",
        "Progression: Provide meaningful short-term and long-term goals",
        "Social: Enable cooperative play and community engagement",
    ]


def _generate_target_audience(game_request: Dict[str, Any]) -> Dict[str, Any]:
    """Generate target audience profile."""
    
    return {
        "primary": {
            "age_range": "18-35",
            "demographics": "Global, mobile-first gamers",
            "psychographics": "Collectors, completionists, social players",
            "gaming_habits": "Daily sessions, 1-3 hours per day",
        },
        "secondary": {
            "age_range": "13-17, 36-45",
            "demographics": "Console and PC gamers",
            "psychographics": "Story-driven, exploration-focused",
        },
    }


def _generate_usps(game_request: Dict[str, Any]) -> List[str]:
    """Generate unique selling points."""
    
    return [
        "Stunning anime-inspired art style with AAA production values",
        "Deep elemental combat system with emergent gameplay",
        "Massive open world with seamless exploration",
        "Regular content updates with new regions and characters",
        "Cross-platform play across mobile, PC, and console",
        "Free-to-play with fair monetization",
    ]


def _generate_combat_pillar(game_request: Dict[str, Any]) -> Dict[str, Any]:
    """Generate combat pillar details."""
    
    return {
        "core_loop": "Switch characters -> Apply elements -> Trigger reactions -> Defeat enemies",
        "depth": "Easy to learn, hard to master",
        "features": [
            "Real-time action combat",
            "Character switching mid-combat",
            "Elemental reaction system",
            "Ultimate abilities",
            "Dodge and parry mechanics",
        ],
        "progression": "Unlock new characters, level up talents, optimize artifacts",
    }


def _generate_exploration_pillar(game_request: Dict[str, Any]) -> Dict[str, Any]:
    """Generate exploration pillar details."""
    
    return {
        "core_loop": "Discover waypoints -> Unlock regions -> Find secrets -> Collect rewards",
        "features": [
            "Climbing and gliding",
            "Swimming and diving",
            "Teleport waypoints",
            "Hidden chests and puzzles",
            "World bosses and challenges",
        ],
        "rewards": "Primogems, artifacts, character materials, lore",
    }


def _generate_progression_pillar(game_request: Dict[str, Any]) -> Dict[str, Any]:
    """Generate progression pillar details."""
    
    return {
        "character_progression": [
            "Character level (1-90)",
            "Ascension phases",
            "Talent levels",
            "Constellation unlocks",
        ],
        "account_progression": [
            "Adventure Rank",
            "World Level",
            "Reputation systems",
            "Achievement points",
        ],
        "equipment_progression": [
            "Weapon enhancement",
            "Artifact farming and optimization",
            "Set bonuses",
        ],
    }


def _generate_social_pillar(game_request: Dict[str, Any]) -> Dict[str, Any]:
    """Generate social pillar details."""
    
    return {
        "co_op": {
            "max_players": 4,
            "activities": ["Domains", "World bosses", "Events"],
        },
        "friend_system": {
            "friend_list": True,
            "visit_worlds": True,
            "chat": True,
        },
        "community": {
            "events": "Limited-time co-op events",
            "leaderboards": "Challenge rankings",
            "sharing": "Photo mode and achievements",
        },
    }


def _generate_world_design(game_request: Dict[str, Any]) -> Dict[str, Any]:
    """Generate world design framework."""
    
    return {
        "structure": "Hub-based open world with distinct regions",
        "regions": [
            {
                "name": "Starter Region",
                "theme": "Temperate grasslands and forests",
                "size": "~15 km²",
                "level_range": "1-20",
                "features": ["Tutorial area", "First city", "Beginner domains"],
            },
            {
                "name": "Second Region",
                "theme": "Mountain peaks and ancient ruins",
                "size": "~20 km²",
                "level_range": "20-40",
                "features": ["Major city", "World boss", "Story dungeons"],
            },
            {
                "name": "Third Region",
                "theme": "Desert and oasis",
                "size": "~25 km²",
                "level_range": "40-60",
                "features": ["Underground areas", "Sandstorm mechanics"],
            },
        ],
        "points_of_interest": [
            "Cities and towns",
            "Teleport waypoints",
            "Statues of Seven",
            "Domains (dungeons)",
            "World bosses",
            "Hidden chests",
            "Puzzle shrines",
        ],
    }


def _generate_narrative_framework(game_request: Dict[str, Any]) -> Dict[str, Any]:
    """Generate narrative framework."""
    
    return {
        "main_story": {
            "structure": "Chapter-based with region-specific arcs",
            "length": "40+ hours",
            "delivery": "Cutscenes, dialogue, and environmental storytelling",
        },
        "character_stories": {
            "structure": "Individual character quests",
            "unlock": "Gacha or story progression",
            "depth": "Explore character backgrounds and motivations",
        },
        "world_quests": {
            "types": ["Side quests", "Daily commissions", "World events"],
            "purpose": "Flesh out world lore and provide rewards",
        },
    }


def _generate_monetization(game_request: Dict[str, Any]) -> Dict[str, Any]:
    """Generate monetization strategy."""
    
    return {
        "model": "Free-to-play with gacha",
        "premium_currency": {
            "name": "Primogems",
            "earn_rate": "~60 per day from dailies",
            "purchase_options": ["$0.99 to $99.99 packs"],
        },
        "gacha_system": {
            "rates": {
                "5_star": "0.6%",
                "4_star": "5.1%",
                "3_star": "94.3%",
            },
            "pity_system": {
                "soft_pity": 75,
                "hard_pity": 90,
                "guaranteed_featured": "50/50, then 100%",
            },
        },
        "battle_pass": {
            "free_track": True,
            "premium_track": "$9.99",
            "duration": "6 weeks",
        },
        "fairness": [
            "All content clearable with free characters",
            "No pay-to-win mechanics",
            "Generous free currency from events",
        ],
    }


def _generate_live_service_plan(game_request: Dict[str, Any]) -> Dict[str, Any]:
    """Generate live service plan."""
    
    return {
        "update_cadence": "6-week cycles",
        "content_types": [
            {
                "type": "New Character Banners",
                "frequency": "Every 3 weeks",
                "description": "Rotate featured 5-star and 4-star characters",
            },
            {
                "type": "Limited Events",
                "frequency": "2-3 per cycle",
                "description": "Temporary events with unique rewards",
            },
            {
                "type": "New Regions",
                "frequency": "Every 3-4 cycles",
                "description": "Major content expansions with new areas",
            },
            {
                "type": "Story Chapters",
                "frequency": "Every 2-3 cycles",
                "description": "Continue main story narrative",
            },
        ],
        "seasonal_events": [
            "Anniversary celebration",
            "Holiday events",
            "Collaboration events",
        ],
    }


def _generate_game_bible(enhanced_request: Dict[str, Any], game_program: Dict[str, Any]) -> str:
    """Generate game bible markdown document."""
    
    meta = enhanced_request.get("meta", {})
    project_name = meta.get("project_name", "Untitled AAA Game")
    
    lines = [
        f"# {project_name} - Game Bible",
        "",
        "## Vision Statement",
        "",
        game_program.get("vision_statement", ""),
        "",
        "## Core Pillars",
        "",
    ]
    
    for pillar in game_program.get("core_pillars", []):
        lines.append(f"- {pillar}")
    
    lines.extend([
        "",
        "## Target Audience",
        "",
        f"**Primary**: {game_program.get('target_audience', {}).get('primary', {}).get('demographics', '')}",
        "",
        "## Unique Selling Points",
        "",
    ])
    
    for usp in game_program.get("unique_selling_points", []):
        lines.append(f"- {usp}")
    
    lines.extend([
        "",
        "## Gameplay Pillars",
        "",
        "### Combat",
        "",
        game_program.get("gameplay_pillars", {}).get("combat", {}).get("core_loop", ""),
        "",
        "### Exploration",
        "",
        game_program.get("gameplay_pillars", {}).get("exploration", {}).get("core_loop", ""),
        "",
        "## World Design",
        "",
        f"**Structure**: {game_program.get('world_design', {}).get('structure', '')}",
        "",
        "## Monetization",
        "",
        f"**Model**: {game_program.get('monetization_strategy', {}).get('model', '')}",
        "",
    ])
    
    return "\n".join(lines)


def _generate_feature_matrix(enhanced_request: Dict[str, Any], game_program: Dict[str, Any]) -> Dict[str, Any]:
    """Generate feature matrix."""
    
    systems = enhanced_request.get("systems", {}).get("required", [])
    
    features = []
    for system in systems:
        features.append({
            "id": system,
            "name": system.replace("_", " ").title(),
            "priority": "P0" if system in ["movement", "combat", "camera"] else "P1",
            "status": "planned",
            "dependencies": [],
        })
    
    return {
        "features": features,
        "total_count": len(features),
        "p0_count": len([f for f in features if f["priority"] == "P0"]),
    }


def _generate_content_matrix(enhanced_request: Dict[str, Any], game_program: Dict[str, Any]) -> Dict[str, Any]:
    """Generate content matrix."""
    
    world_design = game_program.get("world_design", {})
    regions = world_design.get("regions", [])
    
    return {
        "regions": len(regions),
        "characters": 50,  # Target character count
        "weapons": 100,
        "artifacts": 20,  # Artifact sets
        "quests": {
            "main_story": 40,
            "character_stories": 50,
            "world_quests": 200,
            "daily_commissions": 20,
        },
        "enemies": {
            "common": 30,
            "elite": 15,
            "bosses": 10,
        },
    }


def _generate_milestone_board(enhanced_request: Dict[str, Any], game_program: Dict[str, Any]) -> Dict[str, Any]:
    """Generate milestone board."""
    
    return {
        "milestones": [
            {
                "id": "m1",
                "name": "Vertical Slice",
                "duration": "3 months",
                "deliverables": [
                    "Playable first region",
                    "Core combat system",
                    "3 playable characters",
                    "Basic gacha system",
                ],
            },
            {
                "id": "m2",
                "name": "Alpha",
                "duration": "6 months",
                "deliverables": [
                    "2 complete regions",
                    "10 playable characters",
                    "Main story Act 1",
                    "All core systems",
                ],
            },
            {
                "id": "m3",
                "name": "Beta",
                "duration": "9 months",
                "deliverables": [
                    "3 complete regions",
                    "20 playable characters",
                    "Main story Act 1-2",
                    "Polish and optimization",
                ],
            },
            {
                "id": "m4",
                "name": "Launch",
                "duration": "12 months",
                "deliverables": [
                    "Full launch content",
                    "Live service infrastructure",
                    "Marketing campaign",
                    "Platform certification",
                ],
            },
        ],
    }


def _generate_risk_register(enhanced_request: Dict[str, Any], game_program: Dict[str, Any]) -> Dict[str, Any]:
    """Generate risk register."""
    
    return {
        "risks": [
            {
                "id": "r1",
                "category": "technical",
                "description": "Open world streaming performance on mobile",
                "severity": "high",
                "mitigation": "Early performance testing, LOD system, aggressive culling",
            },
            {
                "id": "r2",
                "category": "scope",
                "description": "Content production cannot keep pace with live service cadence",
                "severity": "high",
                "mitigation": "Build content pipeline early, hire content team, reuse assets",
            },
            {
                "id": "r3",
                "category": "monetization",
                "description": "Gacha rates perceived as unfair",
                "severity": "medium",
                "mitigation": "Generous pity system, free characters, community feedback",
            },
            {
                "id": "r4",
                "category": "competition",
                "description": "Market saturation with similar games",
                "severity": "medium",
                "mitigation": "Focus on unique art style and gameplay innovations",
            },
        ],
    }


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
