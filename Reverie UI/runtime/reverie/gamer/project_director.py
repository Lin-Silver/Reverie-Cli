"""Prompt-aware production direction for long-running Reverie-Gamer projects."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List
import copy
import json

from .production_plan import build_blueprint_from_request
from .prompt_compiler import compile_game_prompt


ARTIFACT_REOPEN_ORDER = [
    "artifacts/production_directive.json",
    "artifacts/game_program.json",
    "artifacts/design_intelligence.json",
    "artifacts/campaign_program.json",
    "artifacts/roster_strategy.json",
    "artifacts/live_ops_plan.json",
    "artifacts/production_operating_model.json",
    "artifacts/milestone_board.json",
    "artifacts/reference_intelligence.json",
    "artifacts/runtime_delivery_plan.json",
    "artifacts/content_expansion.json",
    "artifacts/world_program.json",
    "artifacts/asset_pipeline.json",
    "artifacts/resume_state.json",
    "playtest/slice_score.json",
]

KNOWN_ARTIFACTS = [
    "artifacts/production_directive.json",
    "artifacts/game_request.json",
    "artifacts/game_blueprint.json",
    "artifacts/game_program.json",
    "artifacts/feature_matrix.json",
    "artifacts/content_matrix.json",
    "artifacts/design_intelligence.json",
    "artifacts/campaign_program.json",
    "artifacts/roster_strategy.json",
    "artifacts/live_ops_plan.json",
    "artifacts/production_operating_model.json",
    "artifacts/milestone_board.json",
    "artifacts/risk_register.json",
    "artifacts/runtime_registry.json",
    "artifacts/reference_intelligence.json",
    "artifacts/runtime_capability_graph.json",
    "artifacts/runtime_delivery_plan.json",
    "artifacts/production_plan.json",
    "artifacts/system_specs.json",
    "artifacts/task_graph.json",
    "artifacts/content_expansion.json",
    "artifacts/asset_pipeline.json",
    "artifacts/character_kits.json",
    "artifacts/environment_kits.json",
    "artifacts/animation_plan.json",
    "artifacts/asset_budget.json",
    "artifacts/world_program.json",
    "artifacts/region_kits.json",
    "artifacts/faction_graph.json",
    "artifacts/questline_program.json",
    "artifacts/save_migration_plan.json",
    "artifacts/gameplay_factory.json",
    "artifacts/boss_arc.json",
    "artifacts/expansion_backlog.json",
    "artifacts/resume_state.json",
    "playtest/quality_gates.json",
    "playtest/performance_budget.json",
    "playtest/combat_feel_report.json",
    "playtest/slice_score.json",
]

REGION_LIBRARY = [
    {
        "id": "emberfall_steppe",
        "biome": "volcanic grasslands",
        "purpose": "open the project into longer sightlines, mounted route pressure, and large landmark traversal",
        "signature_landmark": "glassfire crater",
        "progression_gate": "stabilize the frontier signal lattice and clear the first boss rematch lane",
    },
    {
        "id": "glass_tide_harbor",
        "biome": "storm-battered port district",
        "purpose": "shift the slice into layered streets, docks, and vertical combat routes with stronger faction conflict",
        "signature_landmark": "mirrorbreak lighthouse",
        "progression_gate": "unlock district access and secure the harbor relay route",
    },
    {
        "id": "frostveil_ridge",
        "biome": "snow ridge ruins",
        "purpose": "stress traversal control, visibility, and boss telegraph readability under harsher world pressure",
        "signature_landmark": "silent observatory",
        "progression_gate": "complete the ridge ascent and awaken the observatory core",
    },
    {
        "id": "neon_parallax",
        "biome": "dense neon combat district",
        "purpose": "push faster close-quarters combat, squad swaps, and event-heavy urban encounters",
        "signature_landmark": "parallax transit ring",
        "progression_gate": "win district control and unlock the event circuit",
    },
]


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


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


def _deep_merge(base: Dict[str, Any], updates: Dict[str, Any]) -> Dict[str, Any]:
    merged = copy.deepcopy(base)
    for key, value in (updates or {}).items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = _deep_merge(merged[key], value)
        else:
            merged[key] = copy.deepcopy(value)
    return merged


def _merge_records_by_id(primary: Iterable[Dict[str, Any]], secondary: Iterable[Dict[str, Any]]) -> List[Dict[str, Any]]:
    merged: Dict[str, Dict[str, Any]] = {}
    ordered_ids: List[str] = []
    for collection in (primary, secondary):
        for record in collection or []:
            item = dict(record or {})
            record_id = str(item.get("id", "")).strip()
            if not record_id:
                continue
            if record_id not in merged:
                merged[record_id] = item
                ordered_ids.append(record_id)
            else:
                merged[record_id] = _deep_merge(merged[record_id], item)
    return [merged[record_id] for record_id in ordered_ids]


def _merge_prompt_history(history: Iterable[Dict[str, Any]], entry: Dict[str, Any]) -> List[Dict[str, Any]]:
    items = [dict(item) for item in (history or []) if isinstance(item, dict)]
    prompt = str(entry.get("prompt", "")).strip()
    if prompt:
        items.append(entry)
    return items[-12:]


def _load_json(path: Path) -> Dict[str, Any]:
    if not path.exists():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    return payload if isinstance(payload, dict) else {}


def load_existing_artifacts(project_root: Path | str) -> Dict[str, Dict[str, Any]]:
    """Load known project artifacts when they already exist."""

    root = Path(project_root)
    artifacts: Dict[str, Dict[str, Any]] = {}
    for relative_path in KNOWN_ARTIFACTS:
        payload = _load_json(root / relative_path)
        if payload:
            artifacts[relative_path] = payload
    return artifacts


def _requested_runtime_hint(text: str, tokens: set[str]) -> str:
    if _matches_any(text, tokens, {"godot"}):
        return "godot"
    if _matches_any(text, tokens, {"o3de"}):
        return "o3de"
    if _matches_any(text, tokens, {"reverie engine", "reverie_engine"}):
        return "reverie_engine"
    return ""


def _requested_systems(text: str, tokens: set[str]) -> List[str]:
    requested: List[str] = []
    if _matches_any(text, tokens, {"combat", "boss", "\u6218\u6597", "\u8fde\u6bb5", "\u5f39\u53cd"}):
        requested.append("combat")
    if _matches_any(text, tokens, {"camera", "lock-on", "lock on", "\u955c\u5934", "\u89c6\u89d2", "\u9501\u5b9a"}):
        requested.extend(["camera", "lock_on"])
    if _matches_any(text, tokens, {"movement", "mobility", "dash", "\u95ea\u907f", "\u673a\u52a8"}):
        requested.append("movement")
    if _matches_any(text, tokens, {"glide", "gliding", "climb", "climbing", "\u6ed1\u7fd4", "\u6500\u722c", "\u7a7a\u6218"}):
        requested.append("traversal_ability")
    if _matches_any(text, tokens, {"region", "open world", "\u5f00\u653e\u4e16\u754c", "\u533a\u57df"}):
        requested.append("world_slice")
    if _matches_any(text, tokens, {"quest", "story", "\u4efb\u52a1", "\u5267\u60c5", "\u652f\u7ebf"}):
        requested.append("quest")
    if _matches_any(text, tokens, {"progression", "growth", "\u517b\u6210", "build"}):
        requested.append("progression")
    if _matches_any(text, tokens, {"combat", "战斗", "boss", "连段", "弹反"}):
        requested.append("combat")
    if _matches_any(text, tokens, {"camera", "镜头", "视角", "lock-on", "lock on", "锁定"}):
        requested.extend(["camera", "lock_on"])
    if _matches_any(text, tokens, {"movement", "mobility", "dash", "闪避", "机动"}):
        requested.append("movement")
    if _matches_any(text, tokens, {"glide", "gliding", "climb", "climbing", "滑翔", "攀爬", "空战"}):
        requested.append("traversal_ability")
    if _matches_any(text, tokens, {"region", "open world", "开放世界", "区域"}):
        requested.append("world_slice")
    if _matches_any(text, tokens, {"quest", "story", "任务", "剧情", "支线"}):
        requested.append("quest")
    if _matches_any(text, tokens, {"progression", "growth", "养成", "build"}):
        requested.append("progression")
    return _unique(requested)


def _requested_region_index(text: str) -> int:
    ordered_markers = [
        (1, {"first region", "第一区域", "一区", "首个区域"}),
        (2, {"second region", "第二区域", "二区", "第二张地图"}),
        (3, {"third region", "第三区域", "三区", "第三张地图"}),
        (4, {"fourth region", "第四区域", "四区", "第四张地图"}),
    ]
    lowered = str(text or "").lower()
    corrected_markers = [
        (1, {"first region", "\u7b2c\u4e00\u533a\u57df", "\u4e00\u533a", "\u9996\u4e2a\u533a\u57df"}),
        (2, {"second region", "\u7b2c\u4e8c\u533a\u57df", "\u4e8c\u533a", "\u7b2c\u4e8c\u5f20\u5730\u56fe"}),
        (3, {"third region", "\u7b2c\u4e09\u533a\u57df", "\u4e09\u533a", "\u7b2c\u4e09\u5f20\u5730\u56fe"}),
        (4, {"fourth region", "\u7b2c\u56db\u533a\u57df", "\u56db\u533a", "\u7b2c\u56db\u5f20\u5730\u56fe"}),
    ]
    for index, markers in corrected_markers:
        if any(marker.lower() in lowered for marker in markers):
            return index
    for index, markers in ordered_markers:
        if any(marker.lower() in lowered for marker in markers):
            return index
    if any(
        marker in lowered
        for marker in (
            "next region",
            "expand the next region",
            "\u4e0b\u4e00\u4e2a\u533a\u57df",
            "\u6269\u5c55\u4e0b\u4e00\u4e2a\u533a\u57df",
            "\u4e0b\u4e00\u5f20\u5730\u56fe",
        )
    ):
        return -1
    if any(marker in lowered for marker in ("next region", "expand the next region", "下一个区域", "扩展下一个区域", "下一张地图")):
        return -1
    return 0


def _pick_region_id(
    text: str,
    existing_regions: List[Dict[str, Any]],
    active_region_id: str,
) -> str:
    lowered = str(text or "").lower()
    region_ids = [str(region.get("id", "")).strip() for region in existing_regions if str(region.get("id", "")).strip()]
    for region_id in region_ids:
        if region_id.lower() in lowered:
            return region_id

    requested_index = _requested_region_index(lowered)
    if requested_index > 0 and len(region_ids) >= requested_index:
        return region_ids[requested_index - 1]
    if requested_index == -1 and region_ids:
        if active_region_id and active_region_id in region_ids:
            active_index = region_ids.index(active_region_id)
            if active_index + 1 < len(region_ids):
                return region_ids[active_index + 1]
        if len(region_ids) > 1:
            return region_ids[1]
        return region_ids[0]
    return ""


def _synthesized_region(game_request: Dict[str, Any], existing_regions: List[Dict[str, Any]], prompt: str) -> Dict[str, Any]:
    existing_ids = {str(region.get("id", "")).strip() for region in existing_regions}
    lowered = str(prompt or "").lower()

    preferred = []
    if any(token in lowered for token in ("desert", "\u6c99\u6f20")):
        preferred.append(
            {
                "id": "sunscar_dunes",
                "biome": "sun-scorched dunes",
                "purpose": "stress route planning, visibility, and long-distance encounter staging",
                "signature_landmark": "solar mirror citadel",
                "progression_gate": "restore the citadel mirrors and clear the heatstorm gauntlet",
            }
        )
    if any(token in lowered for token in ("city", "urban", "\u90fd\u5e02", "\u57ce\u533a", "\u8857\u533a")):
        preferred.append(
            {
                "id": "neon_parallax",
                "biome": "dense neon combat district",
                "purpose": "push faster close-quarters combat, squad swaps, and event-heavy urban encounters",
                "signature_landmark": "parallax transit ring",
                "progression_gate": "win district control and unlock the event circuit",
            }
        )
    if any(token in lowered for token in ("snow", "ice", "\u96ea", "\u51b0")):
        preferred.append(
            {
                "id": "frostveil_ridge",
                "biome": "snow ridge ruins",
                "purpose": "stress traversal control, visibility, and boss telegraph readability under harsher world pressure",
                "signature_landmark": "silent observatory",
                "progression_gate": "complete the ridge ascent and awaken the observatory core",
            }
        )
    if any(token in lowered for token in ("desert", "沙漠")):
        preferred.append(
            {
                "id": "sunscar_dunes",
                "biome": "sun-scorched dunes",
                "purpose": "stress route planning, visibility, and long-distance encounter staging",
                "signature_landmark": "solar mirror citadel",
                "progression_gate": "restore the citadel mirrors and clear the heatstorm gauntlet",
            }
        )
    if any(token in lowered for token in ("city", "urban", "都市", "城区", "街区")):
        preferred.append(
            {
                "id": "neon_parallax",
                "biome": "dense neon combat district",
                "purpose": "push faster close-quarters combat, squad swaps, and event-heavy urban encounters",
                "signature_landmark": "parallax transit ring",
                "progression_gate": "win district control and unlock the event circuit",
            }
        )
    if any(token in lowered for token in ("snow", "ice", "雪", "冰")):
        preferred.append(
            {
                "id": "frostveil_ridge",
                "biome": "snow ridge ruins",
                "purpose": "stress traversal control, visibility, and boss telegraph readability under harsher world pressure",
                "signature_landmark": "silent observatory",
                "progression_gate": "complete the ridge ascent and awaken the observatory core",
            }
        )

    for candidate in preferred + REGION_LIBRARY:
        if candidate["id"] not in existing_ids:
            return dict(candidate)

    suffix = len(existing_regions) + 1
    return {
        "id": f"frontier_region_{suffix}",
        "biome": "frontier biome",
        "purpose": "expand the game through another reusable region kit and progression lane",
        "signature_landmark": f"frontier nexus {suffix}",
        "progression_gate": "complete the current frontier milestone and unlock the next route",
    }


def build_production_directive(
    prompt: str,
    *,
    project_root: Path | str | None = None,
    existing_artifacts: Dict[str, Dict[str, Any]] | None = None,
) -> Dict[str, Any]:
    """Classify a prompt as a fresh build or a continuation directive."""

    text = str(prompt or "").strip()
    lowered = text.lower()
    tokens = _tokenize(text)
    artifacts = existing_artifacts if existing_artifacts is not None else load_existing_artifacts(project_root or Path.cwd())
    existing_regions = list((artifacts.get("artifacts/content_expansion.json", {}) or {}).get("region_seeds", []) or [])
    active_region_id = str((artifacts.get("artifacts/content_expansion.json", {}) or {}).get("active_region_id", "")).strip()

    operations: List[str] = []
    if _matches_any(lowered, tokens, {"expand", "add region", "next region", "region expansion", "扩展", "下一个区域", "新区域", "区域"}):
        operations.append("expand_region")
    if _matches_any(lowered, tokens, {"boss", "phase", "raid", "首领", "boss战", "多阶段"}):
        operations.append("plan_boss_arc")
    if _matches_any(lowered, tokens, {"camera", "combat feel", "traversal", "movement", "lock-on", "镜头", "手感", "空战", "连段", "攀爬", "滑翔"}):
        operations.append("upgrade_gameplay_factory")
    if _matches_any(lowered, tokens, {"runtime", "godot", "o3de", "engine", "引擎"}):
        operations.append("refresh_runtime_delivery")
    if _matches_any(lowered, tokens, {"quality", "validation", "optimize", "performance", "测试", "验证", "性能", "优化"}):
        operations.append("refresh_quality_loop")
    if _matches_any(lowered, tokens, {"faction", "npc", "questline", "character", "阵营", "角色", "任务线"}):
        operations.append("refresh_content_expansion")

    has_existing = bool(artifacts)
    if not operations:
        operations.append("compile_program" if not has_existing else "refresh_production_baseline")

    requested_region_id = _pick_region_id(lowered, existing_regions, active_region_id)
    mode = "continue_project" if has_existing and operations[0] != "compile_program" else "fresh_project"

    history_entry = {
        "timestamp": _utc_now(),
        "prompt": text,
        "mode": mode,
        "operations": _unique(operations),
    }

    return {
        "schema_version": "reverie.production_directive/1",
        "generated_at": _utc_now(),
        "mode": mode,
        "prompt": text,
        "has_existing_artifacts": has_existing,
        "existing_artifact_count": len(artifacts),
        "artifact_reopen_order": [
            path for path in ARTIFACT_REOPEN_ORDER if path in artifacts or path == "artifacts/production_directive.json"
        ],
        "operations": _unique(operations),
        "focus": {
            "primary_operation": _unique(operations)[0],
            "requested_runtime": _requested_runtime_hint(lowered, tokens),
            "requested_systems": _requested_systems(lowered, tokens),
            "requested_region_id": requested_region_id,
            "active_region_id": active_region_id,
        },
        "regeneration_plan": {
            "refresh_request": bool(text) or not has_existing,
            "refresh_blueprint": bool(text) or not has_existing,
            "refresh_runtime_delivery": "refresh_runtime_delivery" in operations or not has_existing,
            "refresh_gameplay_factory": any(
                item in operations for item in ("upgrade_gameplay_factory", "plan_boss_arc")
            )
            or not has_existing,
            "refresh_content_expansion": any(
                item in operations for item in ("expand_region", "refresh_content_expansion")
            )
            or not has_existing,
            "refresh_quality_loop": "refresh_quality_loop" in operations or not has_existing,
        },
        "history_entry": history_entry,
    }


def build_or_update_game_request(
    prompt: str,
    *,
    project_name: str = "",
    requested_runtime: str = "",
    existing_runtime: str = "",
    overrides: Dict[str, Any] | None = None,
    base_request: Dict[str, Any] | None = None,
    existing_artifacts: Dict[str, Dict[str, Any]] | None = None,
) -> tuple[Dict[str, Any], Dict[str, Any]]:
    """Compile a fresh request or merge a continuation prompt into an existing one."""

    artifacts = existing_artifacts or {}
    seed_request = dict(base_request or artifacts.get("artifacts/game_request.json", {}) or {})
    directive = build_production_directive(prompt, existing_artifacts=artifacts)
    delta_request = compile_game_prompt(
        prompt or seed_request.get("latest_prompt") or seed_request.get("source_prompt", ""),
        project_name=project_name or seed_request.get("meta", {}).get("project_name", ""),
        requested_runtime=requested_runtime,
        existing_runtime=existing_runtime or seed_request.get("runtime_preferences", {}).get("existing_runtime", ""),
        overrides=overrides or {},
    )

    if not seed_request:
        request = copy.deepcopy(delta_request)
    else:
        request = copy.deepcopy(seed_request)
        request.setdefault("meta", {})
        request["meta"]["project_name"] = (
            project_name
            or request["meta"].get("project_name")
            or delta_request.get("meta", {}).get("project_name")
            or "Untitled Reverie Slice"
        )
        request["meta"]["last_updated_at"] = _utc_now()

        creative = dict(request.get("creative_target", {}) or {})
        delta_creative = dict(delta_request.get("creative_target", {}) or {})
        creative["references"] = _unique(
            list(creative.get("references", []) or []) + list(delta_creative.get("references", []) or [])
        )
        creative["genre_tags"] = _unique(
            list(creative.get("genre_tags", []) or []) + list(delta_creative.get("genre_tags", []) or [])
        )
        creative["special_features"] = _unique(
            list(creative.get("special_features", []) or []) + list(delta_creative.get("special_features", []) or [])
        )
        if not creative.get("primary_genre"):
            creative["primary_genre"] = delta_creative.get("primary_genre", "action_rpg")
        creative["art_direction"] = _deep_merge(
            dict(creative.get("art_direction", {}) or {}),
            dict(delta_creative.get("art_direction", {}) or {}),
        )
        creative["reference_profile"] = _deep_merge(
            dict(creative.get("reference_profile", {}) or {}),
            dict(delta_creative.get("reference_profile", {}) or {}),
        )
        creative["reference_profile"]["franchise_targets"] = _unique(
            list(creative["reference_profile"].get("franchise_targets", []) or [])
            + list(delta_creative.get("reference_profile", {}).get("franchise_targets", []) or [])
        )
        request["creative_target"] = creative

        experience = dict(request.get("experience", {}) or {})
        delta_experience = dict(delta_request.get("experience", {}) or {})
        for key in ("dimension", "camera_model", "movement_model", "combat_model", "interaction_model"):
            experience[key] = experience.get(key) or delta_experience.get(key)
        for key in ("world_structure", "party_model", "progression_model", "combat_pacing"):
            experience[key] = experience.get(key) or delta_experience.get(key)
        experience["player_verbs"] = _unique(
            list(experience.get("player_verbs", []) or []) + list(delta_experience.get("player_verbs", []) or [])
        )
        experience["core_loop"] = _unique(
            list(experience.get("core_loop", []) or []) + list(delta_experience.get("core_loop", []) or [])
        )
        experience["meta_loop"] = _unique(
            list(experience.get("meta_loop", []) or []) + list(delta_experience.get("meta_loop", []) or [])
        )
        request["experience"] = experience

        systems = dict(request.get("systems", {}) or {})
        delta_systems = dict(delta_request.get("systems", {}) or {})
        systems["required"] = _unique(
            list(systems.get("required", []) or [])
            + list(delta_systems.get("required", []) or [])
            + list(directive.get("focus", {}).get("requested_systems", []) or [])
        )
        systems["specialized"] = _unique(
            list(systems.get("specialized", []) or []) + list(delta_systems.get("specialized", []) or [])
        )
        systems["optional"] = _unique(
            list(systems.get("optional", []) or []) + list(delta_systems.get("optional", []) or [])
        )
        request["systems"] = systems

        production = dict(request.get("production", {}) or {})
        delta_production = dict(delta_request.get("production", {}) or {})
        content_scale = _deep_merge(
            dict(production.get("content_scale", {}) or {}),
            dict(delta_production.get("content_scale", {}) or {}),
        )
        if "expand_region" in directive.get("operations", []):
            content_scale["slice_spaces"] = max(int(content_scale.get("slice_spaces", 1) or 1) + 1, 2)
            content_scale["quest_count"] = max(int(content_scale.get("quest_count", 1) or 1), 2)
        if "plan_boss_arc" in directive.get("operations", []):
            content_scale["boss_encounters"] = max(int(content_scale.get("boss_encounters", 0) or 0), 1)
        production["content_scale"] = content_scale
        production["requested_scope"] = production.get("requested_scope") or delta_production.get("requested_scope", "vertical_slice")
        production["delivery_scope"] = production.get("delivery_scope") or delta_production.get("delivery_scope", "vertical_slice")
        production["complexity_score"] = max(
            int(production.get("complexity_score", 0) or 0),
            int(delta_production.get("complexity_score", 0) or 0),
        )
        production["deferred_features"] = _unique(
            list(production.get("deferred_features", []) or []) + list(delta_production.get("deferred_features", []) or [])
        )
        production["known_risks"] = _unique(
            list(production.get("known_risks", []) or []) + list(delta_production.get("known_risks", []) or [])
        )
        production["slice_targets"] = _unique(
            list(production.get("slice_targets", []) or []) + list(delta_production.get("slice_targets", []) or [])
        )
        production["continuation_ready"] = True
        production["one_prompt_goal"] = (
            production.get("one_prompt_goal")
            or delta_production.get("one_prompt_goal")
            or "prompt -> game program -> runtime foundation -> verified 3d slice -> continuity pack"
        )
        production["live_service_profile"] = _deep_merge(
            dict(production.get("live_service_profile", {}) or {}),
            dict(delta_production.get("live_service_profile", {}) or {}),
        )
        production["director_mode"] = directive.get("mode", "fresh_project")
        production["operation_queue"] = list(directive.get("operations", []) or [])
        request["production"] = production

        runtime_preferences = dict(request.get("runtime_preferences", {}) or {})
        delta_runtime_preferences = dict(delta_request.get("runtime_preferences", {}) or {})
        target_runtime = requested_runtime or directive.get("focus", {}).get("requested_runtime", "")
        if target_runtime:
            delta_runtime_preferences["requested_runtime"] = target_runtime
            delta_runtime_preferences["preferred_runtime"] = target_runtime
        request["runtime_preferences"] = _deep_merge(runtime_preferences, delta_runtime_preferences)

        quality_targets = dict(request.get("quality_targets", {}) or {})
        delta_quality_targets = dict(delta_request.get("quality_targets", {}) or {})
        quality_targets["target_fps"] = max(
            int(quality_targets.get("target_fps", 0) or 0),
            int(delta_quality_targets.get("target_fps", 0) or 0),
        )
        quality_targets["target_load_time_seconds"] = min(
            int(quality_targets.get("target_load_time_seconds", 999) or 999),
            int(delta_quality_targets.get("target_load_time_seconds", 999) or 999),
        )
        quality_targets["slice_playable_minutes"] = max(
            int(quality_targets.get("slice_playable_minutes", 0) or 0),
            int(delta_quality_targets.get("slice_playable_minutes", 0) or 0),
        )
        quality_targets["must_have"] = _unique(
            list(quality_targets.get("must_have", []) or []) + list(delta_quality_targets.get("must_have", []) or [])
        )
        request["quality_targets"] = quality_targets

    request.setdefault("meta", {})
    request["meta"]["project_name"] = project_name or request["meta"].get("project_name") or delta_request.get("meta", {}).get("project_name", "Untitled Reverie Slice")
    request["latest_prompt"] = str(prompt or "").strip() or request.get("latest_prompt") or request.get("source_prompt", "")
    if not request.get("source_prompt"):
        request["source_prompt"] = delta_request.get("source_prompt", "")
    request["prompt_history"] = _merge_prompt_history(
        request.get("prompt_history", []),
        directive.get("history_entry", {}),
    )
    request["continuity"] = {
        "artifact_reopen_order": list(directive.get("artifact_reopen_order", []) or []),
        "latest_operations": list(directive.get("operations", []) or []),
        "requested_region_id": str(directive.get("focus", {}).get("requested_region_id", "")).strip(),
        "active_region_id": str(directive.get("focus", {}).get("active_region_id", "")).strip(),
    }
    return request, directive


def _directive_pillars(production_directive: Dict[str, Any]) -> List[str]:
    operations = set(production_directive.get("operations", []) or [])
    pillars: List[str] = []
    if "expand_region" in operations:
        pillars.append("grow new regions from reusable kits and continuity artifacts instead of restarting project structure")
    if "plan_boss_arc" in operations:
        pillars.append("boss arcs should pay off the current mastery lane, not sit outside the progression fabric")
    if "upgrade_gameplay_factory" in operations:
        pillars.append("camera, traversal, and combat feel must sharpen together during iteration")
    if "refresh_runtime_delivery" in operations:
        pillars.append("runtime delivery should stay reference-aware, data-driven, and safe to refresh")
    return pillars


def build_or_update_blueprint(
    game_request: Dict[str, Any],
    *,
    runtime_profile: Dict[str, Any] | None = None,
    base_blueprint: Dict[str, Any] | None = None,
    overrides: Dict[str, Any] | None = None,
    production_directive: Dict[str, Any] | None = None,
) -> Dict[str, Any]:
    """Build a blueprint or refresh an existing one without losing continuity."""

    fresh = build_blueprint_from_request(
        game_request,
        runtime_profile=runtime_profile,
    )
    if not base_blueprint:
        blueprint = fresh
    else:
        blueprint = _deep_merge(dict(base_blueprint), fresh)
        blueprint.setdefault("meta", {})
        if base_blueprint.get("meta", {}).get("created_at"):
            blueprint["meta"]["created_at"] = base_blueprint["meta"]["created_at"]

    directive = dict(production_directive or {})
    creative_direction = dict(blueprint.get("creative_direction", {}) or {})
    creative_direction["pillars"] = _unique(
        list(creative_direction.get("pillars", []) or []) + _directive_pillars(directive)
    )
    creative_direction["references"] = _unique(
        list(creative_direction.get("references", []) or [])
        + list(game_request.get("creative_target", {}).get("references", []) or [])
    )
    blueprint["creative_direction"] = creative_direction

    gameplay_blueprint = dict(blueprint.get("gameplay_blueprint", {}) or {})
    gameplay_blueprint["systems"] = _deep_merge(
        dict(base_blueprint.get("gameplay_blueprint", {}).get("systems", {}) if base_blueprint else {}),
        dict(fresh.get("gameplay_blueprint", {}).get("systems", {}) or {}),
    )
    blueprint["gameplay_blueprint"] = gameplay_blueprint

    request_snapshot = dict(blueprint.get("request_snapshot", {}) or {})
    request_snapshot["source_prompt"] = game_request.get("source_prompt", "")
    request_snapshot["latest_prompt"] = game_request.get("latest_prompt", game_request.get("source_prompt", ""))
    request_snapshot["references"] = _unique(
        list(request_snapshot.get("references", []) or [])
        + list(game_request.get("creative_target", {}).get("references", []) or [])
    )
    request_snapshot["operations"] = list(directive.get("operations", []) or [])
    blueprint["request_snapshot"] = request_snapshot

    content_strategy = dict(blueprint.get("content_strategy", {}) or {})
    content_strategy["world_structure"] = game_request.get("experience", {}).get("world_structure", content_strategy.get("world_structure", "regional_action_slice"))
    content_strategy["slice_spaces"] = max(
        int(content_strategy.get("slice_spaces", 1) or 1),
        int(game_request.get("production", {}).get("content_scale", {}).get("slice_spaces", 1) or 1),
    )
    blueprint["content_strategy"] = content_strategy

    production_strategy = dict(blueprint.get("production_strategy", {}) or {})
    production_strategy["directive_history"] = _merge_prompt_history(
        production_strategy.get("directive_history", []),
        dict(directive.get("history_entry", {}) or {}),
    )
    blueprint["production_strategy"] = production_strategy

    if overrides:
        blueprint = _deep_merge(blueprint, dict(overrides))
    return blueprint


def evolve_content_expansion(
    base_plan: Dict[str, Any],
    *,
    game_request: Dict[str, Any],
    blueprint: Dict[str, Any],
    production_directive: Dict[str, Any] | None = None,
    existing_plan: Dict[str, Any] | None = None,
) -> Dict[str, Any]:
    """Refresh content expansion while preserving long-term project continuity."""

    directive = dict(production_directive or {})
    plan = copy.deepcopy(base_plan or {})
    if existing_plan:
        plan["region_seeds"] = _merge_records_by_id(
            existing_plan.get("region_seeds", []),
            plan.get("region_seeds", []),
        )
        plan["npc_roster"] = _merge_records_by_id(
            existing_plan.get("npc_roster", []),
            plan.get("npc_roster", []),
        )
        plan["quest_arcs"] = _merge_records_by_id(
            existing_plan.get("quest_arcs", []),
            plan.get("quest_arcs", []),
        )
        if existing_plan.get("active_region_id"):
            plan["active_region_id"] = existing_plan.get("active_region_id")

    regions = list(plan.get("region_seeds", []) or [])
    requested_region_id = str(directive.get("focus", {}).get("requested_region_id", "")).strip()
    if "expand_region" in directive.get("operations", []):
        if not requested_region_id:
            requested_region_id = _pick_region_id(
                directive.get("prompt", ""),
                regions,
                str(plan.get("active_region_id", "")),
            )
        if requested_region_id and all(str(region.get("id", "")).strip() != requested_region_id for region in regions):
            synthesized = _synthesized_region(game_request, regions, directive.get("prompt", ""))
            synthesized["id"] = requested_region_id or synthesized["id"]
            regions.append(synthesized)
        elif not requested_region_id:
            synthesized = _synthesized_region(game_request, regions, directive.get("prompt", ""))
            requested_region_id = synthesized["id"]
            regions.append(synthesized)
        plan["active_region_id"] = requested_region_id

    if not plan.get("active_region_id") and regions:
        plan["active_region_id"] = str(regions[0].get("id", ""))

    if "plan_boss_arc" in directive.get("operations", []):
        if regions:
            plan["boss_priority_region_id"] = plan.get("active_region_id") or str(regions[-1].get("id", ""))

    plan["region_seeds"] = regions
    plan["system_emphasis"] = _unique(
        list(plan.get("system_emphasis", []) or [])
        + list(directive.get("focus", {}).get("requested_systems", []) or [])
    )
    plan["continuity_rules"] = _unique(
        list(plan.get("continuity_rules", []) or [])
        + ["Always reopen the latest production directive before widening scope again."]
    )
    plan["directive_history"] = _merge_prompt_history(
        plan.get("directive_history", []),
        dict(directive.get("history_entry", {}) or {}),
    )
    return plan


def evolve_world_program(
    base_program: Dict[str, Any],
    *,
    content_expansion: Dict[str, Any],
    production_directive: Dict[str, Any] | None = None,
    existing_program: Dict[str, Any] | None = None,
) -> Dict[str, Any]:
    """Refresh the durable world program using the latest continuity directive."""

    directive = dict(production_directive or {})
    program = copy.deepcopy(existing_program or base_program or {})
    base_regions = list(program.get("regions", []) or [])
    updated_regions = _merge_records_by_id(base_regions, content_expansion.get("region_seeds", []))
    program["regions"] = updated_regions
    program["region_order"] = [str(region.get("id", "")).strip() for region in updated_regions if str(region.get("id", "")).strip()]
    program["active_region_id"] = str(content_expansion.get("active_region_id", "")).strip() or str(program.get("active_region_id", "")).strip()
    program["boss_priority_region_id"] = str(content_expansion.get("boss_priority_region_id", "")).strip() or str(program.get("boss_priority_region_id", "")).strip()
    program["directive_history"] = _merge_prompt_history(
        program.get("directive_history", []),
        dict(directive.get("history_entry", {}) or {}),
    )
    program["growth_tracks"] = {
        "active_region_id": program.get("active_region_id", ""),
        "available_region_count": len(program.get("region_order", [])),
        "boss_priority_region_id": program.get("boss_priority_region_id", ""),
    }
    return program


def evolve_gameplay_factory(
    base_factory: Dict[str, Any],
    *,
    production_directive: Dict[str, Any] | None = None,
    game_request: Dict[str, Any] | None = None,
    blueprint: Dict[str, Any] | None = None,
    content_expansion: Dict[str, Any] | None = None,
    existing_factory: Dict[str, Any] | None = None,
) -> Dict[str, Any]:
    """Refresh gameplay presets so follow-up prompts sharpen the same project foundation."""

    directive = dict(production_directive or {})
    request = dict(game_request or {})
    factory = copy.deepcopy(existing_factory or base_factory or {})
    specialized = set(request.get("systems", {}).get("specialized", []) or [])
    requested_systems = set(directive.get("focus", {}).get("requested_systems", []) or [])

    traversal_presets = list(factory.get("traversal_presets", []) or [])
    camera_presets = list(factory.get("camera_presets", []) or [])
    ability_graph = dict(factory.get("ability_graph", {}) or {})
    encounter_grammar = list(factory.get("encounter_grammar", []) or [])
    boss_phase_seeds = list(factory.get("boss_phase_seeds", []) or [])
    quest_event_director = dict(factory.get("quest_event_director", {}) or {})

    if {"aerial_combat", "glide", "climb"} & specialized or "traversal_ability" in requested_systems:
        traversal_presets = _merge_records_by_id(
            traversal_presets,
            [
                {"id": "aerial_chain", "movement_model": "aerial_combo_route"},
                {"id": "frontier_climb", "movement_model": "vertical_route_control"},
            ],
        )
    if {"camera", "lock_on"} & requested_systems or "plan_boss_arc" in directive.get("operations", []):
        camera_presets = _merge_records_by_id(
            camera_presets,
            [
                {"id": "boss_duel", "camera_model": "third_person_duel_focus"},
                {"id": "frontier_chase", "camera_model": "third_person_speed_follow"},
            ],
        )

    starter = list(ability_graph.get("starter", []) or [])
    growth = list(ability_graph.get("growth", []) or [])
    if {"aerial_combat"} & specialized:
        growth.extend(["launcher", "air_followup"])
    if {"parry"} & specialized:
        growth.append("perfect_guard_counter")
    if request.get("experience", {}).get("party_model") != "single_hero_focus":
        growth.append("swap_cancel")
    ability_graph["starter"] = _unique(starter)
    ability_graph["growth"] = _unique(growth)

    if "plan_boss_arc" in directive.get("operations", []):
        encounter_grammar.extend(["mid-boss duel", "arena transition", "multi-phase climax"])
        boss_phase_seeds.extend(["adds or summons", "arena shift"])
    factory["traversal_presets"] = traversal_presets
    factory["camera_presets"] = camera_presets
    factory["ability_graph"] = ability_graph
    factory["encounter_grammar"] = _unique(encounter_grammar)
    factory["boss_phase_seeds"] = _unique(boss_phase_seeds)
    factory["quest_event_director"] = _deep_merge(
        quest_event_director,
        {
            "active_region_id": str((content_expansion or {}).get("active_region_id", "")).strip(),
            "operations": list(directive.get("operations", []) or []),
        },
    )
    return factory


def evolve_boss_arc(
    base_arc: Dict[str, Any],
    *,
    production_directive: Dict[str, Any] | None = None,
    content_expansion: Dict[str, Any] | None = None,
    existing_arc: Dict[str, Any] | None = None,
) -> Dict[str, Any]:
    """Refresh boss-arc planning so follow-up boss prompts target the active frontier."""

    directive = dict(production_directive or {})
    arc = copy.deepcopy(existing_arc or base_arc or {})
    active_region_id = str((content_expansion or {}).get("active_region_id", "")).strip()
    boss_region_id = str((content_expansion or {}).get("boss_priority_region_id", "")).strip()
    target_region = active_region_id or boss_region_id or str(arc.get("target_region", "")).strip()
    if target_region:
        arc["target_region"] = target_region

    if "plan_boss_arc" in directive.get("operations", []):
        arc["phases"] = _unique(
            list(arc.get("phases", []) or [])
            + ["telegraphed opener", "adds or summons", "arena shift", "high-pressure finale"]
        )
        arc["rewards"] = _unique(
            list(arc.get("rewards", []) or [])
            + ["region unlock", "boss material", "continuation hook"]
        )
        arc["arc_status"] = "priority"
    else:
        arc["arc_status"] = arc.get("arc_status", "seeded")

    arc["latest_operations"] = list(directive.get("operations", []) or [])
    return arc
