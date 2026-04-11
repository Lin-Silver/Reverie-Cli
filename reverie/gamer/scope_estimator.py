"""Scope estimation helpers for single-prompt game compilation."""

from __future__ import annotations

from typing import Any, Dict, Iterable, List


AMBITIOUS_SCOPE_PHRASES = {
    "aaa",
    "aa",
    "genshin",
    "wuthering",
    "\u9e23\u6f6e",
    "\u539f\u795e",
    "\u7edd\u533a\u96f6",
    "zenless",
    "elden",
    "open world",
    "open-world",
    "\u5f00\u653e\u4e16\u754c",
    "\u5927\u578b",
    "\u5927\u4e16\u754c",
    "massive",
    "huge",
    "expansive",
    "mmo",
    "live service",
    "live-service",
    "\u957f\u7ebf\u8fd0\u8425",
}

CONTENT_EXPANSION_PHRASES = {
    "city",
    "cities",
    "region",
    "regions",
    "continent",
    "continents",
    "district",
    "districts",
    "faction",
    "factions",
    "questline",
    "questlines",
    "chapters",
    "biome",
    "biomes",
    "\u533a\u57df",
    "\u5730\u533a",
    "\u9635\u8425",
    "\u7ae0\u8282",
    "\u751f\u6001\u533a",
}

SYSTEM_PRESSURE_PHRASES = {
    "craft",
    "crafting",
    "fishing",
    "housing",
    "gacha",
    "\u62bd\u5361",
    "multiplayer",
    "co-op",
    "coop",
    "\u8054\u673a",
    "\u591a\u4eba",
    "raid",
    "mount",
    "pet",
    "photo mode",
    "photomode",
    "weather",
    "climbing",
    "gliding",
    "parkour",
    "\u6ed1\u7fd4",
    "\u6500\u722c",
    "\u8dd1\u9177",
    "\u5bb6\u56ed",
    "\u9493\u9c7c",
}


def _tokenize(text: str) -> set[str]:
    lowered = str(text or "").lower()
    cleaned = []
    for ch in lowered:
        cleaned.append(ch if ch.isalnum() else " ")
    return {token for token in "".join(cleaned).split() if token}


def _matches_any(text: str, tokens: set[str], phrases: Iterable[str]) -> bool:
    for phrase in phrases:
        candidate = str(phrase or "").strip().lower()
        if not candidate:
            continue
        if candidate in tokens or candidate in text:
            return True
    return False


def _match_count(text: str, tokens: set[str], phrases: Iterable[str]) -> int:
    matched = 0
    for phrase in phrases:
        candidate = str(phrase or "").strip().lower()
        if not candidate:
            continue
        if candidate in tokens or candidate in text:
            matched += 1
    return matched


def _requested_scope_from_prompt(text: str, tokens: set[str], explicit_scope: str) -> str:
    raw = str(explicit_scope or "").strip().lower().replace("-", "_")
    aliases = {
        "first playable": "first_playable",
        "vertical slice": "vertical_slice",
        "full game": "full_game",
        "\u5b8c\u6574\u6e38\u620f": "full_game",
        "\u5782\u76f4\u5207\u7247": "vertical_slice",
        "\u539f\u578b": "prototype",
    }
    raw = aliases.get(raw, raw)
    if raw in {"prototype", "first_playable", "vertical_slice", "full_game"}:
        return raw
    if "prototype" in tokens or "\u539f\u578b" in text:
        return "prototype"
    if "slice" in tokens or "vertical" in tokens or "\u5782\u76f4\u5207\u7247" in text:
        return "vertical_slice"
    if {"full", "game"} <= tokens or "campaign" in tokens or "\u5b8c\u6574\u6e38\u620f" in text:
        return "full_game"
    if "demo" in tokens or "playable" in tokens or "\u53ef\u73a9" in text:
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

    text = str(prompt or "").lower()
    tokens = _tokenize(prompt)
    system_list = [str(item).strip() for item in (systems or []) if str(item).strip()]
    requested_tier = _requested_scope_from_prompt(text, tokens, explicit_scope)

    ambition_score = 0
    ambition_score += 28 if "3d" in str(dimension or "").lower() else 8
    ambition_score += 22 if _matches_any(text, tokens, AMBITIOUS_SCOPE_PHRASES) else 0

    content_hits = _match_count(text, tokens, CONTENT_EXPANSION_PHRASES)
    ambition_score += 12 if content_hits >= 2 else content_hits * 4

    ambition_score += _match_count(text, tokens, SYSTEM_PRESSURE_PHRASES) * 5
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
    if _matches_any(text, tokens, {"open world", "open-world", "\u5f00\u653e\u4e16\u754c", "\u5927\u4e16\u754c"}):
        deferred_features.append("multi-region open world streaming and traversal expansion")
    if _matches_any(text, tokens, {"gacha", "live service", "\u62bd\u5361", "\u957f\u7ebf\u8fd0\u8425"}):
        deferred_features.append("live-service economy, gacha, and post-launch operations")
    if _matches_any(text, tokens, {"multiplayer", "co-op", "coop", "\u8054\u673a", "\u591a\u4eba"}):
        deferred_features.append("online multiplayer, replication, and social systems")
    if content_hits >= 2:
        deferred_features.append("multi-biome questline breadth beyond the first polished slice")
    if _matches_any(text, tokens, {"housing", "craft", "crafting", "fishing", "mount", "pet", "\u5bb6\u56ed", "\u9493\u9c7c"}):
        deferred_features.append("side-activity ecosystem and lifestyle features")
    if _matches_any(text, tokens, {"cinematic", "cutscene", "cutscenes", "\u8fc7\u573a", "\u6f14\u51fa"}):
        deferred_features.append("full cinematic pipeline and high-volume authored narrative presentation")

    if str(dimension or "").upper() == "3D":
        deferred_features.append("late-phase performance optimization for large-scale 3D content")
        deferred_features.append("expanded authored asset set beyond primitive or template-backed slice content")

    known_risks = [
        "scope pressure exceeds what a first-pass vertical slice can validate"
        if ambition_score >= 50
        else "scope can drift if systems and content lanes expand in parallel",
        "3D feel work may require iteration across camera, movement, combat readability, and encounter density"
        if str(dimension or "").upper() == "3D"
        else "core loop readability may drift without early playtest coverage",
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
        "ambition_tokens": sorted(
            {
                phrase
                for phrase in AMBITIOUS_SCOPE_PHRASES
                if str(phrase).strip() and (str(phrase).lower() in tokens or str(phrase).lower() in text)
            }
        ),
    }
