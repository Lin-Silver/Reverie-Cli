"""Deterministic prompt compiler for Reverie-Gamer."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, Iterable

from .scope_estimator import estimate_scope


GENRE_HINTS = (
    (
        "action_rpg",
        {
            "action",
            "rpg",
            "arpg",
            "loot",
            "boss",
            "build",
            "skill",
            "combo",
            "elemental",
            "\u52a8\u4f5c",
            "\u6218\u6597",
            "\u5f00\u653e\u4e16\u754c\u52a8\u4f5c",
            "\u52a8\u4f5c\u89d2\u8272\u626e\u6f14",
        },
    ),
    ("adventure", {"adventure", "exploration", "explore", "story", "quest", "\u89e3\u8c1c", "\u63a2\u7d22", "\u5192\u9669"}),
    ("arena", {"arena", "shooter", "combat", "duel", "\u7ade\u6280\u573a", "\u5bf9\u6218", "\u5c04\u51fb"}),
    ("platformer", {"platformer", "jump", "precision", "\u5e73\u53f0\u8df3\u8dc3", "\u6a2a\u7248\u52a8\u4f5c"}),
    ("galgame", {"visual", "novel", "galgame", "dating", "\u89c6\u89c9\u5c0f\u8bf4", "\u604b\u7231\u6a21\u62df"}),
)

REFERENCE_HINTS = (
    ("Genshin Impact", {"genshin", "\u539f\u795e"}),
    ("Wuthering Waves", {"wuthering", "\u9e23\u6f6e"}),
    ("Zenless Zone Zero", {"zenless", "zzz", "\u7edd\u533a\u96f6"}),
    ("The Legend of Zelda", {"zelda", "\u585e\u5c14\u8fbe"}),
    ("Elden Ring", {"elden", "\u827e\u5c14\u767b"}),
)

SPECIAL_FEATURE_HINTS = (
    ("character_swap", {"swap", "switch character", "character swap", "\u5207\u4eba", "\u5207\u6362\u89d2\u8272", "\u89d2\u8272\u5207\u6362"}),
    ("elemental_reaction", {"elemental", "reaction", "\u5143\u7d20\u53cd\u5e94", "\u5c5e\u6027\u53cd\u5e94", "\u5143\u7d20"}),
    ("gacha_roster", {"gacha", "\u62bd\u5361", "\u89d2\u8272\u6536\u96c6"}),
    ("open_world_exploration", {"open world", "open-world", "\u5f00\u653e\u4e16\u754c", "\u5927\u4e16\u754c"}),
    ("aerial_combat", {"air combo", "aerial", "\u7a7a\u6218", "\u7a7a\u4e2d\u8fde\u6bb5", "\u7a7a\u4e2d\u6218\u6597"}),
    ("urban_hub", {"district", "city hub", "urban", "\u8857\u533a", "\u90fd\u5e02", "\u57ce\u533a"}),
    ("glide", {"glide", "gliding", "\u6ed1\u7fd4"}),
    ("climb", {"climb", "climbing", "\u6500\u722c"}),
    ("parry", {"parry", "perfect guard", "\u5f39\u53cd", "\u62db\u67b6", "\u683c\u6321"}),
)


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _tokenize(text: str) -> set[str]:
    lowered = str(text or "").lower()
    cleaned = []
    for ch in lowered:
        cleaned.append(ch if ch.isalnum() else " ")
    return {token for token in "".join(cleaned).split() if token}


def _matches_any(text: str, tokens: set[str], keywords: Iterable[str]) -> bool:
    for keyword in keywords:
        candidate = str(keyword or "").strip().lower()
        if not candidate:
            continue
        if candidate in tokens or candidate in text:
            return True
    return False


def _unique(values: Iterable[str]) -> list[str]:
    seen: set[str] = set()
    ordered: list[str] = []
    for value in values:
        item = str(value or "").strip()
        if not item or item in seen:
            continue
        seen.add(item)
        ordered.append(item)
    return ordered


def _pick_primary_genre(text: str, tokens: set[str]) -> tuple[str, list[str]]:
    scores: list[tuple[int, str]] = []
    matched: list[str] = []
    for genre, keywords in GENRE_HINTS:
        score = sum(1 for keyword in keywords if _matches_any(text, tokens, {keyword}))
        if score:
            matched.append(genre)
        scores.append((score, genre))
    scores.sort(reverse=True)
    primary = scores[0][1] if scores and scores[0][0] > 0 else "action_rpg"
    tags = [primary]
    for genre in matched:
        if genre != primary:
            tags.append(genre)
    if _matches_any(text, tokens, {"open world", "open-world", "\u5f00\u653e\u4e16\u754c", "\u5927\u4e16\u754c"}):
        tags.append("open_world")
    if _matches_any(text, tokens, {"large-scale", "aaa", "\u5927\u578b", "\u957f\u7ebf\u8fd0\u8425"}):
        tags.append("large_scale")
    return primary, _unique(tags)


def _infer_dimension(text: str, tokens: set[str], overrides: Dict[str, Any]) -> str:
    explicit = str(overrides.get("dimension") or "").strip().upper()
    if explicit in {"2D", "2.5D", "3D"}:
        return explicit
    if _matches_any(text, tokens, {"isometric", "2.5d", "\u7b49\u8ddd"}):
        return "2.5D"
    if _matches_any(text, tokens, {"2d", "pixel", "side", "\u50cf\u7d20", "\u6a2a\u7248"}):
        return "2D"
    if _matches_any(text, tokens, {"3d", "\u4e09\u7ef4", "\u7b2c\u4e09\u4eba\u79f0", "\u5f00\u653e\u4e16\u754c"}):
        return "3D"
    return "3D"


def _infer_camera(text: str, tokens: set[str], dimension: str) -> str:
    if _matches_any(text, tokens, {"first person", "fps", "\u7b2c\u4e00\u4eba\u79f0"}):
        return "first_person"
    if _matches_any(text, tokens, {"third person", "third-person", "over shoulder", "\u7b2c\u4e09\u4eba\u79f0"}):
        return "third_person"
    if _matches_any(text, tokens, {"isometric", "\u7b49\u8ddd"}):
        return "isometric"
    if _matches_any(text, tokens, {"top down", "top-down", "\u4fef\u89c6"}):
        return "top_down"
    if dimension == "2D":
        return "side_view"
    if dimension == "2.5D":
        return "isometric"
    return "third_person"


def _infer_movement_model(text: str, tokens: set[str], camera_model: str, genre: str) -> str:
    if _matches_any(text, tokens, {"glide", "gliding", "\u6ed1\u7fd4", "wing"}):
        return "third_person_exploration"
    if _matches_any(text, tokens, {"parkour", "climb", "climbing", "dash", "\u8dd1\u9177", "\u6500\u722c", "\u51b2\u523a"}):
        return "traversal_action"
    if genre == "action_rpg" and camera_model == "third_person":
        return "third_person_action"
    if genre == "arena":
        return "combat_arena"
    if camera_model == "first_person":
        return "fps_movement"
    return "exploration"


def _infer_combat_model(text: str, tokens: set[str], genre: str) -> str:
    if genre in {"platformer", "galgame"}:
        return "light_interaction"
    if _matches_any(text, tokens, {"shoot", "shooter", "gun", "\u5c04\u51fb"}):
        return "ranged_reactive"
    if _matches_any(text, tokens, {"combo", "parry", "dodge", "lock", "\u8fde\u6bb5", "\u5f39\u53cd", "\u95ea\u907f", "\u9501\u5b9a"}):
        return "lock_on_action"
    return "ability_action"


def _infer_reference_titles(text: str, tokens: set[str]) -> list[str]:
    titles = []
    for title, keywords in REFERENCE_HINTS:
        if _matches_any(text, tokens, keywords):
            titles.append(title)
    return titles


def _infer_special_features(text: str, tokens: set[str]) -> list[str]:
    features: list[str] = []
    for feature, keywords in SPECIAL_FEATURE_HINTS:
        if _matches_any(text, tokens, keywords):
            features.append(feature)
    return _unique(features)


def _infer_world_structure(text: str, tokens: set[str], references: list[str]) -> str:
    lowered_references = {item.lower() for item in references}
    if _matches_any(text, tokens, {"open world", "open-world", "\u5f00\u653e\u4e16\u754c", "\u5927\u4e16\u754c"}):
        return "open_world_regions"
    if "zenless zone zero" in lowered_references or _matches_any(text, tokens, {"district", "urban", "\u8857\u533a", "\u90fd\u5e02"}):
        return "hub_and_districts"
    return "regional_action_slice"


def _infer_party_model(text: str, tokens: set[str], references: list[str]) -> str:
    lowered_references = {item.lower() for item in references}
    if "genshin impact" in lowered_references or "wuthering waves" in lowered_references:
        return "character_swap_party"
    if "zenless zone zero" in lowered_references:
        return "small_squad_fast_swap"
    if _matches_any(text, tokens, {"switch character", "character swap", "\u5207\u4eba", "\u89d2\u8272\u5207\u6362"}):
        return "character_swap_party"
    return "single_hero_focus"


def _infer_progression_model(text: str, tokens: set[str], special_features: list[str]) -> str:
    if "gacha_roster" in special_features or _matches_any(text, tokens, {"artifact", "weapon", "\u62bd\u5361", "\u89d2\u8272\u6536\u96c6"}):
        return "roster_growth_and_gear"
    return "ability_unlocks_and_rewards"


def _infer_combat_pacing(text: str, tokens: set[str], references: list[str]) -> str:
    lowered_references = {item.lower() for item in references}
    if "zenless zone zero" in lowered_references or _matches_any(text, tokens, {"fast", "stylish", "\u9ad8\u673a\u52a8", "\u9ad8\u901f"}):
        return "high_speed_cancel_action"
    if "wuthering waves" in lowered_references or _matches_any(text, tokens, {"parry", "counter", "\u5f39\u53cd", "\u53cd\u51fb"}):
        return "reactive_precision_action"
    return "readable_action_rpg"


def _infer_live_service_profile(
    text: str,
    tokens: set[str],
    special_features: list[str],
    reference_titles: list[str],
) -> Dict[str, Any]:
    lowered_references = {item.lower() for item in reference_titles}
    implied_live_service = bool(
        lowered_references & {"genshin impact", "wuthering waves", "zenless zone zero"}
    )
    enabled = (
        _matches_any(text, tokens, {"live service", "gacha", "\u62bd\u5361", "\u957f\u7ebf\u8fd0\u8425"})
        or "gacha_roster" in special_features
        or implied_live_service
    )
    cadence = "seasonal_expansion"
    if enabled:
        cadence = "six_week_content_cycles"
    return {
        "enabled": enabled,
        "cadence": cadence,
        "content_waves": ["character_drop", "event_story", "region_update"] if enabled else ["slice_polish", "next_region"],
        "signals": _unique(
            [
                "explicit_live_service"
                if _matches_any(text, tokens, {"live service", "gacha", "\u62bd\u5361", "\u957f\u7ebf\u8fd0\u8425"})
                else "",
                "gacha_roster_feature" if "gacha_roster" in special_features else "",
                "reference_implied_live_service" if implied_live_service else "",
            ]
        ),
    }


def _build_core_loop(
    genre: str,
    text: str,
    tokens: set[str],
    special_features: list[str],
    world_structure: str,
) -> list[str]:
    if genre == "action_rpg":
        loop = [
            "Traverse the current combat-ready zone and identify the next objective",
            "Engage a readable enemy group with dodge, attack, and skill timing",
            "Claim upgrade resources or narrative progress from the cleared objective",
            "Invest the reward into build growth that changes the next encounter",
        ]
        if world_structure == "open_world_regions":
            loop.insert(1, "Use traversal and world interactions to approach the encounter from a favorable route")
        if "elemental_reaction" in special_features:
            loop[2] = "Trigger synergistic combat states and secure a higher-value route, reward, or boss opening"
        if "character_swap" in special_features:
            loop[1] = "Chain player actions across mobility, dodge, and character swapping to control the encounter"
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


def _build_meta_loop(special_features: list[str], party_model: str) -> list[str]:
    loop = [
        "Complete slice objectives and collect upgrade materials",
        "Unlock or rank up one combat, mobility, or utility option",
        "Return to a stronger version of the loop with better expression and survivability",
    ]
    if party_model != "single_hero_focus":
        loop.insert(1, "Grow the roster or active squad so later encounters support richer team expression")
    if "gacha_roster" in special_features:
        loop.append("Feed long-term collection, build tuning, and future content expansion without restarting the project")
    return _unique(loop)


def _build_systems(
    genre: str,
    dimension: str,
    camera_model: str,
    text: str,
    tokens: set[str],
    special_features: list[str],
) -> list[str]:
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
    if _matches_any(text, tokens, {"glide", "gliding", "climb", "climbing", "\u6ed1\u7fd4", "\u6500\u722c"}) or {"glide", "climb"} & set(special_features):
        systems.append("traversal_ability")
    return _unique(systems)


def _build_quality_targets(
    dimension: str,
    delivery_tier: str,
    world_structure: str,
    live_service_profile: Dict[str, Any],
) -> Dict[str, Any]:
    target_fps = 60 if dimension == "3D" else 120 if dimension == "2D" else 60
    playable_minutes = 20 if delivery_tier == "vertical_slice" else 10
    must_have = [
        "boots into a real scene or engine entry point",
        "supports a complete start-to-objective gameplay path",
        "has smoke-test, telemetry, and content-gate artifacts",
        "reuses durable artifacts before widening scope in later sessions",
    ]
    if world_structure == "open_world_regions":
        must_have.append("proves one credible route from exploration into combat, reward, and return-state flow")
    if live_service_profile.get("enabled"):
        must_have.append("keeps continuation and content-wave planning attached to the project root")
    return {
        "target_fps": target_fps,
        "target_load_time_seconds": 12 if dimension == "3D" else 5,
        "slice_playable_minutes": playable_minutes,
        "must_have": must_have,
    }


def _infer_target_quality(
    text: str,
    tokens: set[str],
    *,
    overrides: Dict[str, Any],
    reference_titles: list[str],
    dimension: str,
    world_structure: str,
) -> str:
    explicit = str(overrides.get("target_quality") or "").strip().lower()
    if explicit in {"aaa", "aa", "indie"}:
        return explicit
    if _matches_any(text, tokens, {"aaa", "console quality", "4k", "cross platform", "voice acting"}):
        return "aaa"
    if str(dimension).upper() == "3D" and (
        world_structure in {"open_world_regions", "hub_and_districts"}
        or bool({item.lower() for item in reference_titles} & {"genshin impact", "wuthering waves", "zenless zone zero"})
    ):
        return "aaa"
    if str(dimension).upper() == "3D":
        return "aa"
    return "indie"


def _apply_quality_profile(
    base: Dict[str, Any],
    *,
    target_quality: str,
    live_service_profile: Dict[str, Any],
    party_model: str,
) -> Dict[str, Any]:
    quality = dict(base or {})
    if target_quality == "aaa":
        quality.update(
            {
                "target_resolution": "4K",
                "target_platforms": ["PC", "PS5", "Xbox Series X", "Mobile"] if live_service_profile.get("enabled") else ["PC", "PS5", "Xbox Series X"],
                "graphics_quality": "AAA",
                "animation_quality": "motion_captured_or_hand_keyed_hero_quality",
                "audio_quality": "orchestral_plus_voice_acting",
                "world_size": "large_open_world_or_multi_district_service_map",
                "content_hours": "80_plus_hours_with_live_growth" if live_service_profile.get("enabled") else "40_plus_hours_with_expansions",
                "target_concurrency_profile": "daily_return_sessions" if live_service_profile.get("enabled") else "campaign_completion_sessions",
            }
        )
    elif target_quality == "aa":
        quality.update(
            {
                "target_resolution": "1440p",
                "target_platforms": ["PC", "Console"],
                "graphics_quality": "AA",
                "animation_quality": "stylized_action_quality",
                "audio_quality": "full_mix_with_select_voice",
                "world_size": "regional_3d_action_game",
                "content_hours": "20_to_40_hours",
            }
        )
    else:
        quality.update(
            {
                "target_resolution": "1080p",
                "target_platforms": ["PC"],
                "graphics_quality": "indie",
                "animation_quality": "readable_placeholder_to_stylized",
                "audio_quality": "essential_mix",
                "world_size": "focused_slice_or_small_world",
                "content_hours": "5_to_20_hours",
            }
        )
    quality["party_scale_target"] = 4 if party_model == "character_swap_party" else 3 if party_model == "small_squad_fast_swap" else 1
    return quality


def _infer_runtime_preferences(
    text: str,
    tokens: set[str],
    *,
    dimension: str,
    requested_runtime: str,
    existing_runtime: str,
) -> Dict[str, Any]:
    explicit = str(requested_runtime or "").strip().lower()
    unsupported_explicit = ""
    if not explicit:
        if _matches_any(text, tokens, {"godot"}):
            explicit = "godot"
        elif _matches_any(text, tokens, {"o3de"}):
            explicit = "o3de"
    if explicit and explicit not in {"godot", "o3de", "reverie_engine", "reverie_engine_lite", "custom"}:
        unsupported_explicit = explicit
        explicit = ""

    external_preferred = bool(explicit in {"godot", "o3de"})
    if not explicit and dimension == "3D" and _matches_any(text, tokens, {"genshin", "wuthering", "zenless", "\u5f00\u653e\u4e16\u754c", "open world"}):
        explicit = "godot"
        external_preferred = True

    preferred = explicit or existing_runtime or "reverie_engine"
    return {
        "requested_runtime": explicit,
        "unsupported_requested_runtime": unsupported_explicit,
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


def _content_scale(text: str, tokens: set[str], delivery_tier: str, world_structure: str) -> Dict[str, Any]:
    requested = "single_slice"
    if world_structure == "open_world_regions":
        requested = "large_open_world"
    elif _matches_any(text, tokens, {"region", "biome", "\u533a\u57df", "\u751f\u6001\u533a"}):
        requested = "multi_space_slice"

    delivery_target = "single_region_vertical_slice" if delivery_tier == "vertical_slice" else "first_playable_zone"
    return {
        "requested_scale": requested,
        "delivery_target": delivery_target,
        "slice_spaces": 2 if delivery_tier == "vertical_slice" else 1,
        "enemy_families": 2 if delivery_tier == "vertical_slice" else 1,
        "boss_encounters": 1 if delivery_tier in {"vertical_slice", "first_playable"} else 0,
        "quest_count": 1 if delivery_tier in {"prototype", "first_playable"} else 2,
    }


def _default_design_capabilities(
    *,
    dimension: str,
    world_structure: str,
    party_model: str,
    live_service_profile: Dict[str, Any],
    reference_titles: list[str],
) -> list[str]:
    capabilities = [
        "persona_synthesis",
        "mda_experience_mapping",
        "flow_curve_planning",
        "dynamic_difficulty_adjustment",
        "reinforcement_feedback_loops",
        "doubling_halving_balance_lab",
        "fail_forward_and_recovery",
        "accessibility_baseline",
    ]
    if str(dimension).upper() == "3D":
        capabilities.append("3d_readability_and_camera_guardrails")
    if world_structure in {"open_world_regions", "hub_and_districts"}:
        capabilities.append("world_route_onboarding")
    if party_model != "single_hero_focus":
        capabilities.append("party_synergy_role_matrix")
    if live_service_profile.get("enabled"):
        capabilities.append("service_cadence_guardrails")
    if {item.lower() for item in reference_titles} & {"genshin impact", "wuthering waves", "zenless zone zero"}:
        capabilities.append("anime_action_service_grammar")
    return _unique(capabilities)


def _build_large_scale_profile(
    *,
    dimension: str,
    world_structure: str,
    party_model: str,
    live_service_profile: Dict[str, Any],
    reference_titles: list[str],
    special_features: list[str],
) -> Dict[str, Any]:
    lowered_references = {item.lower() for item in reference_titles}
    anime_service_signal = bool(
        lowered_references & {"genshin impact", "wuthering waves", "zenless zone zero"}
    )
    project_shape = "regional_action_rpg"
    if world_structure == "open_world_regions":
        project_shape = "anime_action_open_world" if anime_service_signal else "open_world_action_rpg"
    elif world_structure == "hub_and_districts":
        project_shape = "district_service_action"

    signature_systems = [
        "third_person_combat",
        "regional_world_growth" if world_structure in {"open_world_regions", "hub_and_districts"} else "frontier_slice_growth",
        "party_swap_expression" if party_model != "single_hero_focus" else "hero_mastery_expression",
        "service_content_cadence" if live_service_profile.get("enabled") else "expansion_pack_growth",
    ]
    if "elemental_reaction" in special_features:
        signature_systems.append("elemental_reaction_matrix")
    if "gacha_roster" in special_features:
        signature_systems.append("roster_collection_program")
    if {"glide", "climb"} & set(special_features):
        signature_systems.append("world_traversal_ability_graph")

    launch_region_target = 1
    post_launch_region_target = 2
    if world_structure == "open_world_regions":
        launch_region_target = 3
        post_launch_region_target = 6 if live_service_profile.get("enabled") else 4
    elif world_structure == "hub_and_districts":
        launch_region_target = 3
        post_launch_region_target = 5 if live_service_profile.get("enabled") else 4

    starter_party_size = 1
    if party_model == "character_swap_party":
        starter_party_size = 4
    elif party_model == "small_squad_fast_swap":
        starter_party_size = 3

    world_cell_strategy = "single_slice_lane"
    if world_structure == "open_world_regions":
        world_cell_strategy = "region_cells_with_landmark_routes"
    elif world_structure == "hub_and_districts":
        world_cell_strategy = "hub_plus_mission_district_cells"

    runtime_contracts = [
        "party_roster",
        "world_streaming",
        "commission_board",
        "regional_objectives",
    ]
    if "elemental_reaction" in special_features:
        runtime_contracts.append("elemental_matrix")

    return {
        "project_shape": project_shape,
        "launch_region_target": launch_region_target,
        "post_launch_region_target": post_launch_region_target,
        "starter_party_size": starter_party_size,
        "world_cell_strategy": world_cell_strategy,
        "signature_systems": _unique(signature_systems),
        "content_cadence": str(
            live_service_profile.get(
                "cadence",
                "major_expansion_packs" if not live_service_profile.get("enabled") else "six_week_content_cycles",
            )
        ),
        "runtime_contracts": _unique(runtime_contracts),
        "presentation_goal": (
            "Large-scale 3D action foundation with region, roster, and long-cycle continuation hooks."
            if str(dimension).upper() == "3D"
            else "Readable stylized foundation with durable growth contracts."
        ),
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
    text = str(prompt or "").lower()
    tokens = _tokenize(prompt)
    primary_genre, genre_tags = _pick_primary_genre(text, tokens)
    dimension = _infer_dimension(text, tokens, override_map)
    camera_model = str(override_map.get("camera_model") or _infer_camera(text, tokens, dimension))
    reference_titles = _infer_reference_titles(text, tokens)
    special_features = _infer_special_features(text, tokens)
    movement_model = _infer_movement_model(text, tokens, camera_model, primary_genre)
    combat_model = _infer_combat_model(text, tokens, primary_genre)
    world_structure = _infer_world_structure(text, tokens, reference_titles)
    party_model = _infer_party_model(text, tokens, reference_titles)
    progression_model = _infer_progression_model(text, tokens, special_features)
    combat_pacing = _infer_combat_pacing(text, tokens, reference_titles)
    live_service_profile = _infer_live_service_profile(text, tokens, special_features, reference_titles)
    large_scale_profile = _build_large_scale_profile(
        dimension=dimension,
        world_structure=world_structure,
        party_model=party_model,
        live_service_profile=live_service_profile,
        reference_titles=reference_titles,
        special_features=special_features,
    )
    systems = _build_systems(primary_genre, dimension, camera_model, text, tokens, special_features)
    scope = estimate_scope(
        prompt,
        dimension=dimension,
        systems=systems,
        explicit_scope=str(override_map.get("scope") or ""),
    )
    runtime_preferences = _infer_runtime_preferences(
        text,
        tokens,
        dimension=dimension,
        requested_runtime=requested_runtime or str(override_map.get("target_runtime") or ""),
        existing_runtime=existing_runtime,
    )
    player_verbs = ["move", "observe", "interact"]
    if primary_genre in {"action_rpg", "arena"}:
        player_verbs.extend(["attack", "dodge", "upgrade"])
        if party_model != "single_hero_focus":
            player_verbs.append("swap")
    else:
        player_verbs.extend(["solve", "unlock", "progress"])

    compiled_project_name = str(project_name or override_map.get("project_name") or "").strip() or "Untitled Reverie Slice"

    target_quality = _infer_target_quality(
        text,
        tokens,
        overrides=override_map,
        reference_titles=reference_titles,
        dimension=dimension,
        world_structure=world_structure,
    )
    quality_targets = _apply_quality_profile(
        _build_quality_targets(
            dimension,
            scope["delivery_tier"],
            world_structure,
            live_service_profile,
        ),
        target_quality=target_quality,
        live_service_profile=live_service_profile,
        party_model=party_model,
    )

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
            "references": reference_titles,
            "tone": "heroic, kinetic, and exploratory" if primary_genre == "action_rpg" else "readable, expressive, and progression-driven",
            "art_direction": {
                "style": "stylized anime-adjacent action fantasy" if reference_titles else "stylized high-readability production art",
                "lighting": "high-contrast adventurous daylight with combat readability anchors",
                "materials": "clean silhouettes, readable value groups, and controlled effect noise",
            },
            "reference_profile": {
                "scale_profile": (
                    "large_scale_anime_action"
                    if (
                        "open_world" in genre_tags
                        or live_service_profile.get("enabled")
                        or bool({item.lower() for item in reference_titles} & {"genshin impact", "wuthering waves", "zenless zone zero"})
                    )
                    else "regional_action_slice"
                ),
                "franchise_targets": reference_titles,
            },
            "special_features": special_features,
        },
        "experience": {
            "dimension": dimension,
            "camera_model": camera_model,
            "movement_model": movement_model,
            "combat_model": combat_model,
            "interaction_model": "objective-driven exploration",
            "world_structure": world_structure,
            "party_model": party_model,
            "progression_model": progression_model,
            "combat_pacing": combat_pacing,
            "player_verbs": _unique(player_verbs),
            "core_loop": _build_core_loop(primary_genre, text, tokens, special_features, world_structure),
            "meta_loop": _build_meta_loop(special_features, party_model),
        },
        "systems": {
            "required": systems,
            "specialized": special_features,
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
            "target_quality": target_quality,
            "content_scale": _content_scale(text, tokens, scope["delivery_tier"], world_structure),
            "deferred_features": scope["deferred_features"],
            "known_risks": scope["known_risks"],
            "slice_targets": scope["slice_targets"],
            "continuation_ready": True,
            "one_prompt_goal": "prompt -> game program -> runtime foundation -> verified 3d slice -> continuity pack",
            "full_game_aspiration": (
                "multi-region, cross-platform, content-expanding 3D action production base"
                if target_quality == "aaa"
                else "credible production-ready action game foundation"
            ),
            "live_service_profile": live_service_profile,
            "large_scale_profile": large_scale_profile,
            "default_design_capabilities": _default_design_capabilities(
                dimension=dimension,
                world_structure=world_structure,
                party_model=party_model,
                live_service_profile=live_service_profile,
                reference_titles=reference_titles,
            ),
        },
        "runtime_preferences": runtime_preferences,
        "quality_targets": quality_targets,
    }
