"""Deterministic prompt compiler for Reverie-Gamer."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict

from .scope_estimator import estimate_scope


GENRE_HINTS = (
    ("action_rpg", {"action", "rpg", "arpg", "loot", "boss", "build", "skill", "combo", "elemental"}),
    ("adventure", {"adventure", "exploration", "explore", "story", "quest"}),
    ("arena", {"arena", "shooter", "combat", "duel"}),
    ("platformer", {"platformer", "jump", "precision"}),
    ("galgame", {"visual", "novel", "galgame", "dating"}),
)

REFERENCE_HINTS = (
    ("Genshin Impact", {"genshin", "原神"}),
    ("Wuthering Waves", {"wuthering", "鸣潮"}),
    ("The Legend of Zelda", {"zelda"}),
    ("Elden Ring", {"elden"}),
)


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _tokenize(text: str) -> set[str]:
    lowered = str(text or "").lower()
    cleaned = []
    for ch in lowered:
        cleaned.append(ch if ch.isalnum() else " ")
    return {token for token in "".join(cleaned).split() if token}


def _pick_primary_genre(tokens: set[str]) -> tuple[str, list[str]]:
    scores: list[tuple[int, str]] = []
    matched: list[str] = []
    for genre, keywords in GENRE_HINTS:
        score = len(tokens & keywords)
        if score:
            matched.append(genre)
        scores.append((score, genre))
    scores.sort(reverse=True)
    primary = scores[0][1] if scores and scores[0][0] > 0 else "action_rpg"
    tags = [primary]
    for genre in matched:
        if genre != primary:
            tags.append(genre)
    if primary == "action_rpg" and "open" in tokens and "world" in tokens:
        tags.append("open_world")
    return primary, tags


def _infer_dimension(tokens: set[str], overrides: Dict[str, Any]) -> str:
    explicit = str(overrides.get("dimension") or "").strip().upper()
    if explicit in {"2D", "2.5D", "3D"}:
        return explicit
    if "isometric" in tokens:
        return "2.5D"
    if "2d" in tokens or {"pixel", "side"} & tokens:
        return "2D"
    return "3D"


def _infer_camera(tokens: set[str], dimension: str) -> str:
    if {"first", "person"} <= tokens or "fps" in tokens:
        return "first_person"
    if {"third", "person"} <= tokens or {"over", "shoulder"} <= tokens:
        return "third_person"
    if "isometric" in tokens:
        return "isometric"
    if {"top", "down"} <= tokens:
        return "top_down"
    if dimension == "2D":
        return "side_view"
    if dimension == "2.5D":
        return "isometric"
    return "third_person"


def _infer_movement_model(tokens: set[str], camera_model: str, genre: str) -> str:
    if {"glide", "gliding"} & tokens:
        return "third_person_exploration"
    if {"parkour", "climb", "climbing", "dash"} & tokens:
        return "traversal_action"
    if genre == "action_rpg" and camera_model == "third_person":
        return "third_person_action"
    if genre == "arena":
        return "combat_arena"
    if camera_model == "first_person":
        return "fps_movement"
    return "exploration"


def _infer_combat_model(tokens: set[str], genre: str) -> str:
    if genre in {"platformer", "galgame"}:
        return "light_interaction"
    if {"shoot", "shooter", "gun"} & tokens:
        return "ranged_reactive"
    if {"combo", "parry", "dodge", "lock"} & tokens:
        return "lock_on_action"
    return "ability_action"


def _infer_reference_titles(tokens: set[str]) -> list[str]:
    titles = []
    for title, keywords in REFERENCE_HINTS:
        if tokens & keywords:
            titles.append(title)
    return titles


def _build_core_loop(genre: str, tokens: set[str]) -> list[str]:
    if genre == "action_rpg":
        loop = [
            "Traverse the current combat-ready zone and identify the next objective",
            "Engage a readable enemy group with dodge, attack, and skill timing",
            "Claim upgrade resources or narrative progress from the cleared objective",
            "Invest the reward into build growth that changes the next encounter",
        ]
        if "exploration" in tokens or "open" in tokens:
            loop.insert(1, "Use traversal and world interactions to approach the encounter from a favorable route")
        return loop
    if genre == "adventure":
        return [
            "Explore the current space and gather clues or resources",
            "Solve one traversal, interaction, or light combat challenge",
            "Resolve the local objective and unlock the next route",
            "Carry rewards or story state into the next space",
        ]
    return [
        "Enter the current challenge space",
        "Use the primary verbs to resolve one clear obstacle",
        "Receive a reward or unlock",
        "Repeat with a slightly richer tactical decision",
    ]


def _build_meta_loop(genre: str) -> list[str]:
    if genre == "action_rpg":
        return [
            "Complete slice objectives and collect upgrade materials",
            "Unlock or rank up one combat, mobility, or utility option",
            "Return to a stronger version of the loop with better expression and survivability",
        ]
    return [
        "Complete objectives",
        "Unlock or strengthen one persistent option",
        "Return for a richer version of the same fantasy",
    ]


def _build_systems(genre: str, dimension: str, camera_model: str, tokens: set[str]) -> list[str]:
    systems = [
        "camera",
        "movement",
        "combat" if genre in {"action_rpg", "arena"} else "interaction",
        "quest",
        "progression",
        "save_load",
        "ui_hud",
        "world_slice",
        "telemetry",
    ]
    if dimension == "3D":
        systems.extend(["enemy_ai", "encounters", "asset_pipeline"])
    if camera_model == "third_person":
        systems.append("lock_on")
    if {"glide", "gliding", "climb", "climbing"} & tokens:
        systems.append("traversal_ability")
    return list(dict.fromkeys(systems))


def _build_quality_targets(dimension: str, delivery_tier: str) -> Dict[str, Any]:
    target_fps = 60 if dimension == "3D" else 120 if dimension == "2D" else 60
    playable_minutes = 20 if delivery_tier == "vertical_slice" else 10
    return {
        "target_fps": target_fps,
        "target_load_time_seconds": 12 if dimension == "3D" else 5,
        "slice_playable_minutes": playable_minutes,
        "must_have": [
            "boots into a real scene or engine entry point",
            "supports a complete start-to-objective gameplay path",
            "has smoke-test, telemetry, and content-gate artifacts",
        ],
    }


def _infer_runtime_preferences(
    tokens: set[str],
    *,
    dimension: str,
    requested_runtime: str,
    existing_runtime: str,
) -> Dict[str, Any]:
    explicit = str(requested_runtime or "").strip().lower()
    if not explicit:
        if "godot" in tokens:
            explicit = "godot"
        elif "o3de" in tokens:
            explicit = "o3de"
        elif "unity" in tokens:
            explicit = "unity"
        elif "unreal" in tokens:
            explicit = "unreal"

    external_preferred = bool(explicit in {"godot", "o3de", "unity", "unreal"})
    if not explicit and dimension == "3D" and ({"genshin", "wuthering", "open", "world"} & tokens):
        explicit = "godot"
        external_preferred = True

    preferred = explicit or existing_runtime or "reverie_engine"
    return {
        "requested_runtime": explicit,
        "existing_runtime": str(existing_runtime or "").strip().lower(),
        "preferred_runtime": preferred,
        "external_runtime_preferred": external_preferred,
        "runtime_requirements": [
            "scene generation",
            "third-person movement support" if dimension == "3D" else "genre-correct movement support",
            "save/load validation",
            "smoke-test entry path",
        ],
    }


def _content_scale(tokens: set[str], delivery_tier: str) -> Dict[str, Any]:
    requested = "single_slice"
    if {"open", "world"} <= tokens:
        requested = "large_open_world"
    elif "region" in tokens or "biome" in tokens:
        requested = "multi_space_slice"

    delivery_target = "single_region_vertical_slice" if delivery_tier == "vertical_slice" else "first_playable_zone"
    return {
        "requested_scale": requested,
        "delivery_target": delivery_target,
        "slice_spaces": 2 if delivery_tier == "vertical_slice" else 1,
        "enemy_families": 2 if delivery_tier == "vertical_slice" else 1,
        "boss_encounters": 1 if delivery_tier == "vertical_slice" else 0,
        "quest_count": 1 if delivery_tier in {"prototype", "first_playable"} else 2,
    }


def compile_game_prompt(
    prompt: str,
    *,
    project_name: str = "",
    requested_runtime: str = "",
    existing_runtime: str = "",
    overrides: Dict[str, Any] | None = None,
) -> Dict[str, Any]:
    """Compile a raw prompt into a structured production request."""

    override_map = dict(overrides or {})
    tokens = _tokenize(prompt)
    primary_genre, genre_tags = _pick_primary_genre(tokens)
    dimension = _infer_dimension(tokens, override_map)
    camera_model = str(override_map.get("camera_model") or _infer_camera(tokens, dimension))
    movement_model = _infer_movement_model(tokens, camera_model, primary_genre)
    combat_model = _infer_combat_model(tokens, primary_genre)
    systems = _build_systems(primary_genre, dimension, camera_model, tokens)
    scope = estimate_scope(
        prompt,
        dimension=dimension,
        systems=systems,
        explicit_scope=str(override_map.get("scope") or ""),
    )
    runtime_preferences = _infer_runtime_preferences(
        tokens,
        dimension=dimension,
        requested_runtime=requested_runtime or str(override_map.get("target_runtime") or ""),
        existing_runtime=existing_runtime,
    )
    player_verbs = ["move", "observe", "interact"]
    if primary_genre in {"action_rpg", "arena"}:
        player_verbs.extend(["attack", "dodge", "upgrade"])
    else:
        player_verbs.extend(["solve", "unlock", "progress"])

    compiled_project_name = str(project_name or override_map.get("project_name") or "").strip() or "Untitled Reverie Slice"

    return {
        "schema_version": "reverie.game_request/1",
        "meta": {
            "project_name": compiled_project_name,
            "generated_at": _utc_now(),
            "request_type": "single_prompt_compilation",
        },
        "source_prompt": str(prompt or "").strip(),
        "creative_target": {
            "primary_genre": primary_genre,
            "genre_tags": genre_tags,
            "references": _infer_reference_titles(tokens),
            "tone": "heroic, kinetic, and exploratory" if primary_genre == "action_rpg" else "readable, expressive, and progression-driven",
            "art_direction": {
                "style": "stylized anime-adjacent action fantasy" if tokens & {"genshin", "wuthering"} else "stylized high-readability production art",
                "lighting": "high-contrast adventurous daylight with combat readability anchors",
                "materials": "clean silhouettes, readable value groups, and controlled effect noise",
            },
        },
        "experience": {
            "dimension": dimension,
            "camera_model": camera_model,
            "movement_model": movement_model,
            "combat_model": combat_model,
            "interaction_model": "objective-driven exploration",
            "player_verbs": player_verbs,
            "core_loop": _build_core_loop(primary_genre, tokens),
            "meta_loop": _build_meta_loop(primary_genre),
        },
        "systems": {
            "required": systems,
            "optional": [
                "photo_mode",
                "co_op",
                "crafting",
                "advanced_streaming",
            ],
        },
        "production": {
            "requested_scope": scope["requested_tier"],
            "delivery_scope": scope["delivery_tier"],
            "complexity_score": scope["complexity_score"],
            "content_scale": _content_scale(tokens, scope["delivery_tier"]),
            "deferred_features": scope["deferred_features"],
            "known_risks": scope["known_risks"],
            "slice_targets": scope["slice_targets"],
        },
        "runtime_preferences": runtime_preferences,
        "quality_targets": _build_quality_targets(dimension, scope["delivery_tier"]),
    }
