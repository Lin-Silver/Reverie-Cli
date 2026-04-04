"""Scope estimation helpers for single-prompt game compilation."""

from __future__ import annotations

from typing import Any, Dict, Iterable, List


AMBITIOUS_SCOPE_TOKENS = {
    "aaa",
    "aa",
    "genshin",
    "wuthering",
    "鸣潮",
    "原神",
    "elden",
    "open",
    "world",
    "massive",
    "huge",
    "expansive",
    "mmo",
    "live",
    "service",
}

CONTENT_EXPANSION_TOKENS = {
    "city",
    "region",
    "regions",
    "continent",
    "continents",
    "faction",
    "factions",
    "questline",
    "questlines",
    "chapters",
    "biome",
    "biomes",
}

SYSTEM_PRESSURE_TOKENS = {
    "craft",
    "crafting",
    "fishing",
    "housing",
    "gacha",
    "multiplayer",
    "co-op",
    "coop",
    "raid",
    "mount",
    "pet",
    "photomode",
    "photo",
    "weather",
    "climbing",
    "gliding",
    "parkour",
}


def _tokenize(text: str) -> set[str]:
    lowered = str(text or "").lower()
    cleaned = []
    for ch in lowered:
        cleaned.append(ch if ch.isalnum() else " ")
    return {token for token in "".join(cleaned).split() if token}


def _requested_scope_from_prompt(tokens: set[str], explicit_scope: str) -> str:
    raw = str(explicit_scope or "").strip().lower().replace("-", "_")
    aliases = {
        "first playable": "first_playable",
        "vertical slice": "vertical_slice",
        "full game": "full_game",
    }
    raw = aliases.get(raw, raw)
    if raw in {"prototype", "first_playable", "vertical_slice", "full_game"}:
        return raw
    if "prototype" in tokens:
        return "prototype"
    if "slice" in tokens or "vertical" in tokens:
        return "vertical_slice"
    if {"full", "game"} <= tokens or "campaign" in tokens:
        return "full_game"
    if "demo" in tokens or "playable" in tokens:
        return "first_playable"
    return "vertical_slice"


def estimate_scope(
    prompt: str,
    *,
    dimension: str = "2D",
    systems: Iterable[str] | None = None,
    explicit_scope: str = "",
) -> Dict[str, Any]:
    """Estimate a realistic delivery tier for the current repository."""

    tokens = _tokenize(prompt)
    system_list = [str(item).strip() for item in (systems or []) if str(item).strip()]
    requested_tier = _requested_scope_from_prompt(tokens, explicit_scope)

    ambition_score = 0
    ambition_score += 28 if "3d" in str(dimension or "").lower() else 8
    ambition_score += 22 if tokens & AMBITIOUS_SCOPE_TOKENS else 0
    ambition_score += 12 if len(tokens & CONTENT_EXPANSION_TOKENS) >= 2 else len(tokens & CONTENT_EXPANSION_TOKENS) * 4
    ambition_score += len(tokens & SYSTEM_PRESSURE_TOKENS) * 5
    ambition_score += max(len(system_list) - 4, 0) * 4

    if requested_tier == "full_game":
        ambition_score += 20
    elif requested_tier == "vertical_slice":
        ambition_score += 8

    if ambition_score >= 65:
        delivery_tier = "vertical_slice"
    elif ambition_score >= 38:
        delivery_tier = "first_playable"
    else:
        delivery_tier = requested_tier if requested_tier in {"prototype", "first_playable"} else "prototype"

    deferred_features: List[str] = []
    if tokens & {"open", "world"}:
        deferred_features.append("multi-region open world streaming and traversal expansion")
    if tokens & {"gacha", "live", "service"}:
        deferred_features.append("live-service economy, gacha, and post-launch operations")
    if tokens & {"multiplayer", "coop", "co", "op"}:
        deferred_features.append("online multiplayer, replication, and social systems")
    if len(tokens & CONTENT_EXPANSION_TOKENS) >= 2:
        deferred_features.append("multi-biome questline breadth beyond the first polished slice")
    if tokens & {"housing", "craft", "crafting", "fishing", "mount", "pet"}:
        deferred_features.append("side-activity ecosystem and lifestyle features")
    if tokens & {"cinematic", "cutscene", "cutscenes"}:
        deferred_features.append("full cinematic pipeline and high-volume authored narrative presentation")

    if str(dimension or "").upper() == "3D":
        deferred_features.append("late-phase performance optimization for large-scale 3D content")
        deferred_features.append("expanded authored asset set beyond primitive or template-backed slice content")

    known_risks = [
        "scope pressure exceeds what a first-pass vertical slice can validate" if ambition_score >= 50 else "scope can drift if systems and content lanes expand in parallel",
        "3D feel work may require iteration across camera, movement, combat readability, and encounter density" if str(dimension or "").upper() == "3D" else "core loop readability may drift without early playtest coverage",
        "asset production can outpace runtime verification unless contracts and budgets stay explicit",
    ]

    slice_targets = [
        "ship one polished playable space with clear start, combat or interaction beat, reward, and completion state",
        "prove one progression or unlock decision with visible consequences inside the slice",
        "stabilize smoke checks, telemetry, and basic content gates before expanding breadth",
    ]

    return {
        "requested_tier": requested_tier,
        "delivery_tier": delivery_tier,
        "complexity_score": ambition_score,
        "deferred_features": list(dict.fromkeys(deferred_features)),
        "known_risks": known_risks,
        "slice_targets": slice_targets,
        "ambition_tokens": sorted(tokens & AMBITIOUS_SCOPE_TOKENS),
    }
