"""Local reference-repository intelligence for Reverie-Gamer."""

from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
from fnmatch import fnmatch
from pathlib import Path
from typing import Any, Dict, Iterable, List
import json
import os


_REFERENCE_SCAN_CACHE: Dict[str, Dict[str, Any]] = {}
_REFERENCE_MANIFEST_CACHE: Dict[str, Dict[str, Any]] = {}
_REFERENCE_REPOSITORIES = (
    "godot-tps-demo",
    "godot-demo-projects",
    "o3de-multiplayersample",
    "o3de-multiplayersample-assets",
    "blender",
    "blockbench",
    "blockbench-plugins",
    "gltf-blender-io",
    "gltf-validator",
    "gltf-sample-assets",
)


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _read_text(path: Path, *, limit: int = 12000) -> str:
    if not path.exists():
        return ""
    try:
        return path.read_text(encoding="utf-8", errors="ignore")[:limit]
    except OSError:
        return ""


def _read_json(path: Path) -> Dict[str, Any]:
    raw = _read_text(path, limit=50000)
    if not raw:
        return {}
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError:
        return {}
    return payload if isinstance(payload, dict) else {}


def _normalize_path(value: str) -> str:
    return str(value or "").replace("\\", "/").strip("/")


def _manifest_fingerprint(repo_root: Path) -> str:
    try:
        stat = repo_root.stat()
    except OSError:
        return f"{repo_root.resolve()}:unreadable"
    return f"{repo_root.resolve()}:{stat.st_mtime_ns}:{stat.st_size}"


def _build_repo_manifest(repo_root: Path) -> Dict[str, Any]:
    suffix_counts: Dict[str, int] = {}
    name_counts: Dict[str, int] = {}
    subtree_suffix_counts: Dict[str, Dict[str, int]] = {}
    file_count = 0
    dir_count = 0

    if not repo_root.exists():
        return {
            "repo_root": str(repo_root),
            "fingerprint": _manifest_fingerprint(repo_root),
            "file_count": 0,
            "dir_count": 0,
            "suffix_counts": {},
            "name_counts": {},
            "subtree_suffix_counts": {},
        }

    for current_root, dirnames, filenames in os.walk(repo_root):
        dir_count += len(dirnames)
        current_path = Path(current_root)
        rel_dir = _normalize_path(_rel(current_path, repo_root))
        for filename in filenames:
            file_count += 1
            name_counts[filename] = name_counts.get(filename, 0) + 1
            suffix = Path(filename).suffix.lower()
            if suffix:
                suffix_counts[suffix] = suffix_counts.get(suffix, 0) + 1
                subtree_key = rel_dir or "."
                subtree_counts = subtree_suffix_counts.setdefault(subtree_key, {})
                subtree_counts[suffix] = subtree_counts.get(suffix, 0) + 1

    return {
        "repo_root": str(repo_root),
        "fingerprint": _manifest_fingerprint(repo_root),
        "file_count": file_count,
        "dir_count": dir_count,
        "suffix_counts": suffix_counts,
        "name_counts": name_counts,
        "subtree_suffix_counts": subtree_suffix_counts,
    }


def _repo_manifest(repo_root: Path) -> Dict[str, Any]:
    repo_root = Path(repo_root)
    cache_key = str(repo_root.resolve())
    fingerprint = _manifest_fingerprint(repo_root)
    cached = _REFERENCE_MANIFEST_CACHE.get(cache_key)
    if cached and cached.get("fingerprint") == fingerprint:
        return deepcopy(cached["manifest"])

    manifest = _build_repo_manifest(repo_root)
    _REFERENCE_MANIFEST_CACHE[cache_key] = {
        "fingerprint": fingerprint,
        "manifest": deepcopy(manifest),
    }
    return manifest


def _count_repo_files(repo_root: Path, pattern: str, *, subdir: str = "", limit: int = 2000) -> int:
    repo_root = Path(repo_root)
    if not repo_root.exists():
        return 0

    manifest = _repo_manifest(repo_root)
    normalized_subdir = _normalize_path(subdir)
    normalized_pattern = str(pattern or "").strip()

    if not normalized_subdir and normalized_pattern.startswith("*.") and "*" not in normalized_pattern[1:]:
        count = int(manifest.get("suffix_counts", {}).get(normalized_pattern[1:].lower(), 0))
        return min(count, limit)
    if not normalized_subdir and "*" not in normalized_pattern and "?" not in normalized_pattern:
        count = int(manifest.get("name_counts", {}).get(normalized_pattern, 0))
        return min(count, limit)
    if normalized_subdir and normalized_pattern.startswith("*.") and "*" not in normalized_pattern[1:]:
        suffix_key = normalized_pattern[1:].lower()
        count = 0
        for subtree_key, subtree_counts in manifest.get("subtree_suffix_counts", {}).items():
            normalized_key = _normalize_path(subtree_key)
            if normalized_key == normalized_subdir or normalized_key.startswith(f"{normalized_subdir}/"):
                count += int(subtree_counts.get(suffix_key, 0) or 0)
        return min(count, limit)

    target_root = repo_root / normalized_subdir if normalized_subdir else repo_root
    if not target_root.exists():
        return 0
    count = 0
    for candidate in target_root.rglob("*"):
        if candidate.is_file() and fnmatch(candidate.name, normalized_pattern):
            count += 1
            if count >= limit:
                return limit
    return count


def _rel(path: Path, base: Path) -> str:
    try:
        return str(path.relative_to(base)).replace("\\", "/")
    except ValueError:
        return str(path).replace("\\", "/")


def _repo_root(*, project_root: Path | None = None, app_root: Path | None = None) -> Path:
    candidates: List[Path] = []
    if app_root:
        candidates.append(Path(app_root) / "references")
    if project_root:
        candidates.append(Path(project_root) / "references")
    candidates.append(Path(__file__).resolve().parents[2] / "references")

    seen: set[str] = set()
    ordered: List[Path] = []
    for candidate in candidates:
        key = str(candidate.resolve())
        if key in seen:
            continue
        seen.add(key)
        ordered.append(candidate.resolve())

    for candidate in ordered:
        if candidate.exists():
            return candidate
    return ordered[0] if ordered else Path("references").resolve()


def _reference_fingerprint(reference_root: Path) -> str:
    root = Path(reference_root).resolve()
    parts = [str(root)]
    for repo_name in _REFERENCE_REPOSITORIES:
        candidate = root / repo_name
        if not candidate.exists():
            parts.append(f"{repo_name}:missing")
            continue
        try:
            stat = candidate.stat()
            parts.append(f"{repo_name}:{stat.st_mtime_ns}:{stat.st_size}")
        except OSError:
            parts.append(f"{repo_name}:unreadable")
    return "|".join(parts)


def _entry(
    *,
    reference_root: Path,
    repo_root: Path,
    reference_id: str,
    display_name: str,
    category: str,
    engine: str,
    direct_applicability: str,
    signals: Iterable[str],
    recommended_usage: Iterable[str],
    evidence: Iterable[Dict[str, str]],
    stats: Dict[str, Any] | None = None,
    runtime_affinity: Dict[str, float] | None = None,
    reuse_policy: str = "pattern_only",
    guardrails: Iterable[Dict[str, str]] | None = None,
) -> Dict[str, Any]:
    return {
        "id": reference_id,
        "display_name": display_name,
        "category": category,
        "engine": engine,
        "path": _rel(repo_root, reference_root),
        "available": repo_root.exists(),
        "direct_applicability": direct_applicability,
        "signals": sorted({str(item).strip() for item in signals if str(item).strip()}),
        "recommended_usage": [str(item).strip() for item in recommended_usage if str(item).strip()],
        "evidence": list(evidence),
        "stats": dict(stats or {}),
        "runtime_affinity": dict(runtime_affinity or {}),
        "reuse_policy": reuse_policy,
        "guardrails": list(guardrails or []),
    }


def _analyze_godot_tps_demo(reference_root: Path) -> Dict[str, Any] | None:
    repo = reference_root / "godot-tps-demo"
    if not repo.exists():
        return None

    player_script = repo / "player" / "player.gd"
    input_script = repo / "player" / "player_input.gd"
    enemy_script = repo / "enemies" / "red_robot" / "red_robot.gd"
    player_text = _read_text(player_script)
    input_text = _read_text(input_script)

    signals = {
        "3d",
        "third_person",
        "camera_orbit",
        "aim_mode",
        "shooting",
        "jump",
        "crosshair",
        "projectile_feedback",
    }
    if "MultiplayerSynchronizer" in input_text or "multiplayer.is_server" in player_text:
        signals.add("multiplayer_sync")

    return _entry(
        reference_root=reference_root,
        repo_root=repo,
        reference_id="godot-tps-demo",
        display_name="Godot TPS Demo",
        category="runtime_template",
        engine="godot",
        direct_applicability="high",
        signals=signals,
        recommended_usage=[
            "Use as the primary local template for third-person camera, aim, jump, and combat readability.",
            "Mirror the split between player control, input synchronization, and enemy-pressure scripts when extending the Godot scaffold.",
        ],
        evidence=[
            {
                "path": _rel(repo / "project.godot", reference_root),
                "signal": "godot_project",
                "note": "Confirms a full Godot project foundation is available locally.",
            },
            {
                "path": _rel(player_script, reference_root),
                "signal": "third_person_controller",
                "note": "Shows CharacterBody3D-based locomotion, aiming, jump, and firing flow.",
            },
            {
                "path": _rel(input_script, reference_root),
                "signal": "camera_and_input",
                "note": "Demonstrates camera orbit, aim toggling, mouse look, and shoot targeting.",
            },
            {
                "path": _rel(enemy_script, reference_root),
                "signal": "enemy_pressure",
                "note": "Provides a concrete enemy-side combat and reaction reference.",
            },
        ],
        stats={
            "scene_files": _count_repo_files(repo, "*.tscn"),
            "gdscript_files": _count_repo_files(repo, "*.gd"),
            "model_files": _count_repo_files(repo, "*.glb"),
            "total_files": _repo_manifest(repo).get("file_count", 0),
        },
        runtime_affinity={"godot": 0.96, "reverie_engine": 0.42, "o3de": 0.18},
    )


def _analyze_godot_demo_projects(reference_root: Path) -> Dict[str, Any] | None:
    repo = reference_root / "godot-demo-projects"
    if not repo.exists():
        return None

    return _entry(
        reference_root=reference_root,
        repo_root=repo,
        reference_id="godot-demo-projects",
        display_name="Godot Demo Projects",
        category="runtime_pattern_library",
        engine="godot",
        direct_applicability="medium",
        signals={
            "scene_catalog",
            "engine_conventions",
            "sample_layouts",
            "project_variants",
        },
        recommended_usage=[
            "Use as a local pattern library for Godot folder layout, scene conventions, and small self-contained samples.",
            "Borrow organization and runtime idioms, not project-specific gameplay wholesale.",
        ],
        evidence=[
            {
                "path": _rel(repo / "mono" / "squash_the_creeps" / "project.godot", reference_root),
                "signal": "sample_project",
                "note": "Shows another maintained Godot sample project layout.",
            },
            {
                "path": _rel(repo / "mono" / "squash_the_creeps" / "Main.tscn", reference_root),
                "signal": "scene_structure",
                "note": "Provides a compact reference for main-scene organization and data flow.",
            },
        ],
        stats={
            "project_files": _count_repo_files(repo, "project.godot"),
            "scene_files": _count_repo_files(repo, "*.tscn"),
            "script_files": _count_repo_files(repo, "*.gd") + _count_repo_files(repo, "*.cs"),
            "total_files": _repo_manifest(repo).get("file_count", 0),
        },
        runtime_affinity={"godot": 0.68, "reverie_engine": 0.22, "o3de": 0.1},
    )


def _analyze_o3de_multiplayersample(reference_root: Path) -> Dict[str, Any] | None:
    repo = reference_root / "o3de-multiplayersample"
    if not repo.exists():
        return None

    project_payload = _read_json(repo / "project.json")
    readme = _read_text(repo / "README.md")

    signals = {
        "3d",
        "third_person",
        "multiplayer",
        "weapon_loop",
        "round_structure",
        "server_client_launchers",
        "asset_gem_registration",
        "teleporter",
        "jump_pad",
        "environmental_hazards",
    }
    if "Support for 1 to 10 players" in readme:
        signals.add("scalable_session_count")
    if "shield" in readme.lower():
        signals.add("shield_resource")

    gem_names = [str(item).strip() for item in project_payload.get("gem_names", []) if str(item).strip()]

    return _entry(
        reference_root=reference_root,
        repo_root=repo,
        reference_id="o3de-multiplayersample",
        display_name="O3DE Multiplayer Sample",
        category="runtime_architecture",
        engine="o3de",
        direct_applicability="medium",
        signals=signals,
        recommended_usage=[
            "Use as a future-scale reference for multiplayer architecture, launcher separation, registry-driven gameplay tuning, and world traversal devices.",
            "Mine it for packaging and systems patterns, but treat it as architecture guidance rather than immediate slice scaffolding.",
        ],
        evidence=[
            {
                "path": _rel(repo / "project.json", reference_root),
                "signal": "project_manifest",
                "note": "Defines the O3DE project manifest and gem dependencies.",
            },
            {
                "path": _rel(repo / "README.md", reference_root),
                "signal": "feature_overview",
                "note": "Lists third-person multiplayer, weapons, hazards, rounds, teleporters, and player-count support.",
            },
            {
                "path": _rel(repo / "Documentation" / "GamplayConfiguration.md", reference_root),
                "signal": "world_devices",
                "note": "Documents teleporter setup, gameplay registry tuning, and level configuration hooks.",
            },
            {
                "path": _rel(repo / "ExportScripts" / "export_mps.py", reference_root),
                "signal": "delivery_packaging",
                "note": "Shows export and launcher packaging patterns for a larger O3DE project.",
            },
        ],
        stats={
            "gem_count": len(gem_names),
            "seed_list_files": _count_repo_files(repo, "*.seed", subdir="AssetBundling/SeedLists"),
            "prefab_files": _count_repo_files(repo, "*.prefab"),
            "total_files": _repo_manifest(repo).get("file_count", 0),
        },
        runtime_affinity={"o3de": 0.95, "godot": 0.24, "reverie_engine": 0.18},
    )


def _analyze_o3de_multiplayersample_assets(reference_root: Path) -> Dict[str, Any] | None:
    repo = reference_root / "o3de-multiplayersample-assets"
    if not repo.exists():
        return None

    gem_paths = sorted((repo / "Gems").glob("*/gem.json"))
    guardrails: List[Dict[str, str]] = []

    if _read_json(repo / "Gems" / "kb3d_mps" / "gem.json"):
        guardrails.append(
            {
                "scope": "asset_reuse",
                "policy": "pattern_only",
                "reference_id": "o3de-multiplayersample-assets",
                "note": "Kitbash3D-derived assets are restricted; use folder structure and pipeline patterns, not shipped asset files.",
            }
        )

    if _read_json(repo / "Gems" / "character_mps" / "gem.json"):
        guardrails.append(
            {
                "scope": "character_assets",
                "policy": "do_not_redistribute",
                "reference_id": "o3de-multiplayersample-assets",
                "note": "Mixamo-derived assets require separate rights; treat them as pipeline examples only.",
            }
        )

    return _entry(
        reference_root=reference_root,
        repo_root=repo,
        reference_id="o3de-multiplayersample-assets",
        display_name="O3DE Multiplayer Sample Assets",
        category="asset_pipeline",
        engine="o3de",
        direct_applicability="medium",
        signals={
            "asset_gems",
            "modular_asset_packs",
            "character_library",
            "material_library",
            "level_art_library",
            "dcc_bootstrap",
        },
        recommended_usage=[
            "Use as a structure reference for modular asset-pack organization, DCC bootstrapping, and asset-pack registration.",
            "Carry over gem-style packaging ideas into Reverie's region and environment kit planning without copying restricted assets.",
        ],
        evidence=[
            {
                "path": _rel(repo / "readme.md", reference_root),
                "signal": "asset_repo_structure",
                "note": "Explains the asset-gem repository layout and registration flow.",
            },
            {
                "path": _rel(repo / "Gems" / "character_mps" / "gem.json", reference_root),
                "signal": "character_packaging",
                "note": "Shows modular character-asset packaging and external requirements.",
            },
            {
                "path": _rel(repo / "Guides" / "GettingStarted.md", reference_root),
                "signal": "dcc_bootstrap",
                "note": "Documents DCC bootstrapping and asset authoring setup.",
            },
        ],
        stats={
            "asset_gem_count": len(gem_paths),
            "documented_asset_packs": len(gem_paths),
            "total_files": _repo_manifest(repo).get("file_count", 0),
        },
        runtime_affinity={"o3de": 0.84, "godot": 0.38, "reverie_engine": 0.34},
        guardrails=guardrails,
    )


def _analyze_cross_runtime_tool(
    reference_root: Path,
    repo_name: str,
    *,
    reference_id: str,
    display_name: str,
    signals: Iterable[str],
    usage: Iterable[str],
    runtime_affinity: Dict[str, float] | None = None,
) -> Dict[str, Any] | None:
    repo = reference_root / repo_name
    if not repo.exists():
        return None

    return _entry(
        reference_root=reference_root,
        repo_root=repo,
        reference_id=reference_id,
        display_name=display_name,
        category="toolchain",
        engine="cross_runtime",
        direct_applicability="supporting",
        signals=signals,
        recommended_usage=usage,
        evidence=[
            {
                "path": _rel(repo, reference_root),
                "signal": "toolchain_available",
                "note": "The repository is present locally and can inform the authoring or validation stack.",
            }
        ],
        stats={
            "total_files": _repo_manifest(repo).get("file_count", 0),
            "directory_count": _repo_manifest(repo).get("dir_count", 0),
        },
        runtime_affinity=runtime_affinity or {"godot": 0.32, "o3de": 0.32, "reverie_engine": 0.32},
        reuse_policy="workflow_reference",
    )


def scan_reference_catalog(
    *,
    project_root: Path | None = None,
    app_root: Path | None = None,
) -> Dict[str, Any]:
    """Scan the local references workspace and return a compact catalog."""

    reference_root = _repo_root(project_root=project_root, app_root=app_root)
    fingerprint = _reference_fingerprint(reference_root)
    cached = _REFERENCE_SCAN_CACHE.get(str(reference_root))
    if cached and cached.get("fingerprint") == fingerprint:
        payload = deepcopy(cached.get("payload", {}))
        payload["cache_status"] = "hit"
        return payload

    entries = [
        _analyze_godot_tps_demo(reference_root),
        _analyze_godot_demo_projects(reference_root),
        _analyze_o3de_multiplayersample(reference_root),
        _analyze_o3de_multiplayersample_assets(reference_root),
        _analyze_cross_runtime_tool(
            reference_root,
            "blender",
            reference_id="blender",
            display_name="Blender",
            signals=("dcc", "mesh_authoring", "animation_authoring", "export_pipeline"),
            usage=("Use as the heavyweight DCC reference for authored meshes, rigs, and animation export.",),
            runtime_affinity={"godot": 0.44, "o3de": 0.44, "reverie_engine": 0.44},
        ),
        _analyze_cross_runtime_tool(
            reference_root,
            "blockbench",
            reference_id="blockbench",
            display_name="Blockbench",
            signals=("dcc", "graybox_modeling", "stylized_source_assets"),
            usage=("Use for fast source-asset blocking and low-friction early content authoring.",),
            runtime_affinity={"godot": 0.36, "o3de": 0.28, "reverie_engine": 0.4},
        ),
        _analyze_cross_runtime_tool(
            reference_root,
            "blockbench-plugins",
            reference_id="blockbench-plugins",
            display_name="Blockbench Plugins",
            signals=("tool_extension", "authoring_automation"),
            usage=("Use as a reference bank for extending Blockbench-centric authoring workflows.",),
            runtime_affinity={"godot": 0.28, "o3de": 0.28, "reverie_engine": 0.3},
        ),
        _analyze_cross_runtime_tool(
            reference_root,
            "gltf-blender-io",
            reference_id="gltf-blender-io",
            display_name="glTF Blender IO",
            signals=("gltf_export", "blender_bridge", "asset_interchange"),
            usage=("Use for glTF export conventions and Blender-to-runtime interchange decisions.",),
            runtime_affinity={"godot": 0.42, "o3de": 0.36, "reverie_engine": 0.34},
        ),
        _analyze_cross_runtime_tool(
            reference_root,
            "gltf-validator",
            reference_id="gltf-validator",
            display_name="glTF Validator",
            signals=("gltf_validation", "asset_gate", "import_health"),
            usage=("Use as the validation reference before promoting authored assets into runtime import lanes.",),
            runtime_affinity={"godot": 0.34, "o3de": 0.34, "reverie_engine": 0.34},
        ),
        _analyze_cross_runtime_tool(
            reference_root,
            "gltf-sample-assets",
            reference_id="gltf-sample-assets",
            display_name="glTF Sample Assets",
            signals=("asset_samples", "material_reference", "interchange_examples"),
            usage=("Use as neutral sample material when validating glTF import assumptions and renderer expectations.",),
            runtime_affinity={"godot": 0.22, "o3de": 0.22, "reverie_engine": 0.22},
        ),
    ]
    detected = [entry for entry in entries if entry]
    guardrails: List[Dict[str, str]] = []
    for entry in detected:
        guardrails.extend(entry.get("guardrails", []))

    counts_by_engine: Dict[str, int] = {}
    counts_by_category: Dict[str, int] = {}
    total_files = 0
    total_directories = 0
    for entry in detected:
        counts_by_engine[entry["engine"]] = counts_by_engine.get(entry["engine"], 0) + 1
        counts_by_category[entry["category"]] = counts_by_category.get(entry["category"], 0) + 1
        total_files += int(entry.get("stats", {}).get("total_files", 0) or 0)
        total_directories += int(entry.get("stats", {}).get("directory_count", 0) or 0)

    payload = {
        "reference_root": str(reference_root),
        "available": reference_root.exists(),
        "detected_repositories": detected,
        "summary": {
            "repository_count": len(detected),
            "engines": counts_by_engine,
            "categories": counts_by_category,
            "total_files": total_files,
            "total_directories": total_directories,
        },
        "legal_guardrails": guardrails,
        "cache_status": "miss",
    }
    _REFERENCE_SCAN_CACHE[str(reference_root)] = {
        "fingerprint": fingerprint,
        "payload": deepcopy(payload),
    }
    return payload


def _request_profile(game_request: Dict[str, Any]) -> Dict[str, Any]:
    source_prompt = str(game_request.get("source_prompt", "")).lower()
    creative = dict(game_request.get("creative_target", {}) or {})
    experience = dict(game_request.get("experience", {}) or {})
    production = dict(game_request.get("production", {}) or {})

    combined = " ".join(
        [
            source_prompt,
            str(creative.get("primary_genre", "")),
            str(experience.get("camera_model", "")),
            str(experience.get("movement_model", "")),
            str(production.get("delivery_scope", "")),
            " ".join(str(item) for item in creative.get("references", []) or []),
        ]
    ).lower()

    def has(tokens: Iterable[str]) -> bool:
        return any(token in combined for token in tokens)

    flags = {
        "three_d": str(experience.get("dimension", "3D")).upper() == "3D",
        "third_person": "third" in str(experience.get("camera_model", "")).lower() or has(("third-person", "third person", "三人称")),
        "action": has(("action", "combat", "arpg", "hack", "slash", "动作", "战斗")),
        "rpg": has(("rpg", "role-playing", "角色扮演")),
        "shooter": has(("shooter", "gun", "shoot", "射击")),
        "multiplayer": has(("multiplayer", "co-op", "coop", "online", "联机", "多人")),
        "open_world": has(("open world", "open-world", "开放世界")),
        "large_scale": has(("large-scale", "aaa", "genshin", "wuthering", "原神", "鸣潮", "绝区零")),
        "vertical_slice": str(production.get("delivery_scope", "vertical_slice")).lower() in {"prototype", "first_playable", "vertical_slice"},
    }
    active_flags = [name for name, enabled in flags.items() if enabled]
    return {
        "dimension": str(experience.get("dimension", "3D")),
        "camera_model": str(experience.get("camera_model", "third_person")),
        "genre": str(creative.get("primary_genre", "action_rpg")),
        "scope": str(production.get("delivery_scope", "vertical_slice")),
        "active_flags": active_flags,
    }


def _runtime_alignment(
    request_profile: Dict[str, Any],
    detected_repositories: List[Dict[str, Any]],
    runtime_profiles: Iterable[Dict[str, Any]] | None = None,
) -> List[Dict[str, Any]]:
    runtime_profile_map = {
        str(profile.get("id", "")).strip(): dict(profile)
        for profile in (runtime_profiles or [])
        if str(profile.get("id", "")).strip()
    }
    repo_map = {entry["id"]: entry for entry in detected_repositories}
    flags = set(request_profile.get("active_flags", []))

    scores = {"reverie_engine": 0.34, "godot": 0.24, "o3de": 0.16}
    reasons: Dict[str, List[str]] = {key: [] for key in scores}
    support: Dict[str, List[str]] = {key: [] for key in scores}

    if "vertical_slice" in flags:
        scores["reverie_engine"] += 0.16
        reasons["reverie_engine"].append("Repository-native runtime is still the fastest verified path for playable slices.")

    if "three_d" in flags and "third_person" in flags and "action" in flags and "godot-tps-demo" in repo_map:
        scores["godot"] += 0.48
        reasons["godot"].append("Local Godot TPS demo strongly matches third-person 3D action control needs.")
        support["godot"].append("godot-tps-demo")

    if "godot-demo-projects" in repo_map:
        scores["godot"] += 0.08
        reasons["godot"].append("Additional local Godot samples reinforce scene and project conventions.")
        support["godot"].append("godot-demo-projects")

    if ("large_scale" in flags or "open_world" in flags or "multiplayer" in flags) and "o3de-multiplayersample" in repo_map:
        scores["o3de"] += 0.46
        reasons["o3de"].append("Local O3DE multiplayer sample is a strong architecture reference for larger-scale runtime planning.")
        support["o3de"].append("o3de-multiplayersample")

    if ("large_scale" in flags or "open_world" in flags or "multiplayer" in flags) and "o3de-multiplayersample-assets" in repo_map:
        scores["o3de"] += 0.18
        reasons["o3de"].append("Local O3DE asset-gem repository supports modular large-project content packaging.")
        support["o3de"].append("o3de-multiplayersample-assets")

    if "shooter" in flags and "godot-tps-demo" in repo_map:
        scores["godot"] += 0.12
        reasons["godot"].append("The TPS demo provides a nearby aiming and projectile reference for shooter-adjacent loops.")

    if "multiplayer" in flags and "godot-tps-demo" in repo_map and "multiplayer_sync" in repo_map["godot-tps-demo"].get("signals", []):
        scores["godot"] += 0.08
        reasons["godot"].append("The local Godot TPS demo already exposes multiplayer synchronization patterns.")

    if any(repo_id in repo_map for repo_id in ("blender", "blockbench", "gltf-validator", "gltf-blender-io")):
        for runtime_id in scores:
            scores[runtime_id] += 0.04
        reasons["godot"].append("The local authoring stack supports cross-runtime asset production for Godot slices.")
        reasons["o3de"].append("The local authoring stack supports cross-runtime asset production for O3DE research lanes.")
        reasons["reverie_engine"].append("The local authoring stack supports source-asset creation for first-party runtime slices.")

    alignments: List[Dict[str, Any]] = []
    for runtime_id in ("reverie_engine", "godot", "o3de"):
        profile = runtime_profile_map.get(runtime_id, {})
        score = max(0.0, min(scores.get(runtime_id, 0.0), 0.99))
        readiness = "reference_only"
        if profile.get("can_scaffold"):
            readiness = "scaffold_ready"
        elif profile.get("available"):
            readiness = "research_only"

        fit = "supporting_reference"
        if score >= 0.75 and readiness == "scaffold_ready":
            fit = "active_slice_template"
        elif score >= 0.7 and readiness != "scaffold_ready":
            fit = "expansion_architecture_reference"
        elif score < 0.35:
            fit = "low_relevance"

        alignments.append(
            {
                "runtime_id": runtime_id,
                "reference_fit_score": int(round(score * 100)),
                "fit": fit,
                "execution_readiness": readiness,
                "supporting_references": sorted({item for item in support.get(runtime_id, []) if item}),
                "reasons": reasons.get(runtime_id, []) or ["No strong local reference bias was detected for this runtime."],
            }
        )
    return alignments


def _recommended_reference_stack(
    request_profile: Dict[str, Any],
    detected_repositories: List[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    repo_map = {entry["id"]: entry for entry in detected_repositories}
    flags = set(request_profile.get("active_flags", []))
    stack: List[Dict[str, Any]] = []

    def add(reference_id: str, role: str, adoption_mode: str) -> None:
        entry = repo_map.get(reference_id)
        if not entry:
            return
        stack.append(
            {
                "reference_id": reference_id,
                "role": role,
                "adoption_mode": adoption_mode,
                "reuse_policy": entry.get("reuse_policy", "pattern_only"),
            }
        )

    if "three_d" in flags and "third_person" in flags and "godot-tps-demo" in repo_map:
        add("godot-tps-demo", "third-person movement, camera, aim, and combat reference", "runtime_pattern")
    if "godot-demo-projects" in repo_map:
        add("godot-demo-projects", "Godot scene-layout and project-convention library", "pattern_library")
    if ("large_scale" in flags or "open_world" in flags or "multiplayer" in flags) and "o3de-multiplayersample" in repo_map:
        add("o3de-multiplayersample", "future expansion architecture, packaging, and traversal-device reference", "architecture_reference")
    if "o3de-multiplayersample-assets" in repo_map:
        add("o3de-multiplayersample-assets", "modular asset-pack and DCC bootstrap reference", "pipeline_reference")
    if "blender" in repo_map:
        add("blender", "high-fidelity mesh, rig, and animation authoring base", "toolchain")
    if "blockbench" in repo_map:
        add("blockbench", "rapid graybox and source-model authoring base", "toolchain")
    if "gltf-blender-io" in repo_map:
        add("gltf-blender-io", "Blender-to-glTF interchange reference", "toolchain")
    if "gltf-validator" in repo_map:
        add("gltf-validator", "asset-import validation gate", "toolchain")
    if "gltf-sample-assets" in repo_map:
        add("gltf-sample-assets", "neutral sample assets for renderer or import checks", "samples")

    return stack


def _gameplay_patterns(
    request_profile: Dict[str, Any],
    detected_repositories: List[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    repo_map = {entry["id"]: entry for entry in detected_repositories}
    flags = set(request_profile.get("active_flags", []))
    patterns: List[Dict[str, Any]] = []

    if "godot-tps-demo" in repo_map and "three_d" in flags and "third_person" in flags:
        patterns.append(
            {
                "pattern_id": "third_person_control_stack",
                "source_reference": "godot-tps-demo",
                "summary": "Split player movement, input/camera, and enemy scripts into separate runtime contracts.",
            }
        )
        patterns.append(
            {
                "pattern_id": "aim_and_projectile_feedback",
                "source_reference": "godot-tps-demo",
                "summary": "Treat aim mode, target raycasts, projectiles, and camera feedback as one coherent loop.",
            }
        )

    if "o3de-multiplayersample" in repo_map and ("large_scale" in flags or "multiplayer" in flags or "open_world" in flags):
        patterns.append(
            {
                "pattern_id": "device_driven_world_traversal",
                "source_reference": "o3de-multiplayersample",
                "summary": "Promote teleporters, jump pads, hazards, and other world devices into explicit system packets.",
            }
        )
        patterns.append(
            {
                "pattern_id": "launcher_and_server_split",
                "source_reference": "o3de-multiplayersample",
                "summary": "Keep client, server, and export paths explicit when planning future runtime expansion.",
            }
        )

    if "o3de-multiplayersample-assets" in repo_map:
        patterns.append(
            {
                "pattern_id": "modular_asset_packs",
                "source_reference": "o3de-multiplayersample-assets",
                "summary": "Package content in modular environment, character, and material packs instead of one flat asset dump.",
            }
        )

    return patterns


def _toolchain_matrix(detected_repositories: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    repo_map = {entry["id"]: entry for entry in detected_repositories}
    lanes: List[Dict[str, Any]] = []

    def add(lane_id: str, capability: str, references: Iterable[str], outcomes: Iterable[str]) -> None:
        chosen = [reference_id for reference_id in references if reference_id in repo_map]
        if not chosen:
            return
        lanes.append(
            {
                "id": lane_id,
                "capability": capability,
                "status": "ready",
                "references": chosen,
                "outcomes": [str(item).strip() for item in outcomes if str(item).strip()],
            }
        )

    add(
        "runtime_templates",
        "execution-ready runtime patterns",
        ("godot-tps-demo", "godot-demo-projects", "o3de-multiplayersample"),
        (
            "seed a third-person 3D action project foundation",
            "borrow project layout and scene conventions",
            "shape future large-scale runtime architecture choices",
        ),
    )
    add(
        "dcc_authoring",
        "source asset authoring and graybox iteration",
        ("blender", "blockbench", "blockbench-plugins"),
        (
            "graybox characters, landmarks, and encounter props quickly",
            "promote approved source assets into the runtime import lane",
        ),
    )
    add(
        "asset_interchange",
        "glTF interchange and validation",
        ("gltf-blender-io", "gltf-validator", "gltf-sample-assets"),
        (
            "keep authored assets exportable and validator-friendly",
            "test renderer assumptions with neutral sample assets",
        ),
    )
    add(
        "modular_asset_packs",
        "region, character, and material pack structuring",
        ("o3de-multiplayersample-assets",),
        (
            "package region kits and character kits as modular content waves",
            "keep restricted third-party assets in pattern-only territory",
        ),
    )
    return lanes


def _adoption_plan(
    request_profile: Dict[str, Any],
    detected_repositories: List[Dict[str, Any]],
    runtime_alignment: List[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    repo_map = {entry["id"]: entry for entry in detected_repositories}
    alignment_map = {
        str(item.get("runtime_id", "")).strip(): dict(item)
        for item in runtime_alignment
        if str(item.get("runtime_id", "")).strip()
    }
    flags = set(request_profile.get("active_flags", []))
    phases: List[Dict[str, Any]] = []

    slice_references = [item for item in ("godot-tps-demo", "godot-demo-projects") if item in repo_map]
    if slice_references:
        phases.append(
            {
                "id": "slice_bootstrap",
                "goal": "Stand up a playable third-person 3D action slice from one prompt.",
                "references": slice_references,
                "adoption_mode": "runtime_pattern",
                "runtime_bias": alignment_map.get("godot", {}),
            }
        )

    if flags & {"large_scale", "open_world", "multiplayer"} and "o3de-multiplayersample" in repo_map:
        phases.append(
            {
                "id": "scale_architecture",
                "goal": "Extract multi-region, packaging, and future-scale architecture patterns without blocking slice delivery.",
                "references": ["o3de-multiplayersample"],
                "adoption_mode": "architecture_reference",
                "runtime_bias": alignment_map.get("o3de", {}),
            }
        )

    asset_references = [
        item
        for item in ("o3de-multiplayersample-assets", "blender", "blockbench", "gltf-blender-io", "gltf-validator")
        if item in repo_map
    ]
    if asset_references:
        phases.append(
            {
                "id": "asset_and_dcc_lane",
                "goal": "Keep source-asset authoring, interchange, and runtime validation aligned as content scale grows.",
                "references": asset_references,
                "adoption_mode": "pipeline_reference",
                "runtime_bias": alignment_map.get("godot", {}),
            }
        )

    if not phases:
        phases.append(
            {
                "id": "minimal_reference_mode",
                "goal": "Proceed with repo-native patterns only until stronger references become available.",
                "references": [],
                "adoption_mode": "fallback",
                "runtime_bias": alignment_map.get("reverie_engine", {}),
            }
        )
    return phases


def build_reference_intelligence(
    game_request: Dict[str, Any],
    *,
    project_root: Path | None = None,
    app_root: Path | None = None,
    runtime_profiles: Iterable[Dict[str, Any]] | None = None,
) -> Dict[str, Any]:
    """Build request-aware reference intelligence from the local references workspace."""

    catalog = scan_reference_catalog(project_root=project_root, app_root=app_root)
    request_profile = _request_profile(game_request)
    alignments = _runtime_alignment(request_profile, catalog["detected_repositories"], runtime_profiles)
    recommended_stack = _recommended_reference_stack(
        request_profile,
        catalog["detected_repositories"],
    )
    gameplay_patterns = _gameplay_patterns(
        request_profile,
        catalog["detected_repositories"],
    )

    return {
        "schema_version": "reverie.reference_intelligence/1",
        "project_name": str(game_request.get("meta", {}).get("project_name", "Untitled Reverie Project")),
        "generated_at": _utc_now(),
        "reference_root": catalog["reference_root"],
        "reference_root_available": catalog["available"],
        "request_profile": request_profile,
        "catalog_summary": catalog["summary"],
        "detected_repositories": catalog["detected_repositories"],
        "runtime_alignment": alignments,
        "recommended_reference_stack": recommended_stack,
        "gameplay_patterns": gameplay_patterns,
        "toolchain_matrix": _toolchain_matrix(catalog["detected_repositories"]),
        "adoption_plan": _adoption_plan(request_profile, catalog["detected_repositories"], alignments),
        "legal_guardrails": catalog["legal_guardrails"],
        "notes": [
            "Use local references to guide runtime shape, system seams, and asset-pipeline structure, not to justify copying shipped game content wholesale.",
            "Prefer architecture and workflow reuse over direct asset reuse, especially when third-party content restrictions are present.",
        ],
    }
