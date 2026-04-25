"""Asset-pipeline planning for long-running Reverie-Gamer projects."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List

from .system_generators.shared import project_name, target_runtime


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _display_name(raw: str, fallback: str) -> str:
    text = str(raw or "").strip().replace("_", " ")
    return text.title() if text else fallback


def _runtime_delivery(runtime: str) -> Dict[str, Any]:
    normalized = str(runtime or "reverie_engine").strip().lower() or "reverie_engine"
    if normalized == "godot":
        return {
            "runtime_root": "engine/godot",
            "asset_registry_path": "engine/godot/data/asset_registry.json",
            "import_profile_path": "engine/godot/data/asset_import_profile.json",
            "notes": [
                "Keep authored imports under engine/godot/assets while the project-level modeling workspace remains the source of truth.",
                "Mirror approved runtime models from assets/models/runtime into authored Godot scenes once registry and import checks pass.",
            ],
        }
    if normalized == "o3de":
        return {
            "runtime_root": "engine/o3de",
            "asset_registry_path": "engine/o3de/Registry/asset_registry.json",
            "import_profile_path": "engine/o3de/Registry/asset_import_profile.json",
            "notes": [
                "Use the project-level modeling workspace as the authoring source and promote validated exports into O3DE content gems later.",
            ],
        }
    return {
        "runtime_root": ".",
        "asset_registry_path": "data/content/asset_registry.yaml",
        "import_profile_path": "data/content/asset_import_profile.yaml",
        "notes": [
            "The built-in Reverie Engine reads the project-level modeling workspace directly and can consume generated runtime exports without a second asset mirror.",
        ],
    }


def _import_profile(runtime: str) -> Dict[str, Any]:
    normalized = str(runtime or "reverie_engine").strip().lower() or "reverie_engine"
    profile = {
        "runtime": normalized,
        "preferred_model_formats": [".glb", ".gltf"],
        "accepted_texture_formats": [".png", ".webp", ".jpg"],
        "accepted_audio_formats": [".ogg", ".wav"],
        "material_expectations": [
            "readable silhouette-first starter materials before final authored shaders",
            "texture names stay aligned with model stems whenever possible",
            "collision and interaction helpers are tracked as explicit companion assets",
        ],
        "import_steps": [
            "author or revise source files in assets/models/source",
            "export runtime geometry into assets/models/runtime",
            "refresh model_registry and asset manifests before scene integration",
            "validate naming, dependencies, and per-slice budgets",
        ],
    }
    if normalized == "godot":
        profile.update(
            {
                "engine_asset_root": "engine/godot/assets",
                "scene_integration": "Prefer glTF scene imports, keep scripts data-driven, and move final rigs into authored Godot scenes only after registry validation.",
                "import_flags": ["generate_tangents_when_needed", "preserve_named_nodes", "track_collision_helpers"],
            }
        )
        return profile
    if normalized == "o3de":
        profile.update(
            {
                "engine_asset_root": "engine/o3de/Assets",
                "scene_integration": "Promote validated runtime exports into asset processor-friendly folders and bind gameplay prefabs after schema validation.",
                "import_flags": ["asset_processor_ready", "streaming_budget_tags", "lod_group_required_for_large_props"],
            }
        )
        return profile
    profile.update(
        {
            "engine_asset_root": "assets/models/runtime",
            "scene_integration": "Built-in Reverie Engine content can reference runtime exports directly through registry and scene data.",
            "import_flags": ["registry_sync_required", "starter_asset_ready", "smoke_import"],
        }
    )
    return profile


def _validation_rules(runtime: str, world_packet: Dict[str, Any]) -> Dict[str, Any]:
    asset_contracts = dict(world_packet.get("asset_contracts", {}) or {})
    budget_notes = dict(asset_contracts.get("budget_notes", {}) or {})
    return {
        "naming": {
            "asset_id_pattern": "^[a-z0-9_]+$",
            "region_prefix_required_for_world_assets": True,
            "categories": {
                "character": "char_<name> or npc_<name>",
                "enemy": "enemy_<family>_<role>",
                "world_kit": "<region>_<landmark_or_kit>",
                "effect": "fx_<purpose>",
                "ui": "ui_<surface>_<state>",
                "audio": "audio_<family>_<cue>",
            },
        },
        "dependencies": [
            "Every runtime model should map back to one source authoring file or documented source exception.",
            "Combat-facing assets need an owning gameplay contract before scene integration.",
            "Quest-critical landmarks need stable ids that match slice manifest and world graph references.",
        ],
        "budgets": {
            "hero_proxy_count": int(budget_notes.get("hero_proxy_count", 1) or 1),
            "enemy_proxy_count": int(budget_notes.get("enemy_proxy_count", 2) or 2),
            "landmark_kit_count": int(budget_notes.get("landmark_kit_count", 3) or 3),
            "vfx_budget": str(budget_notes.get("vfx_budget", "one attack hit and one shrine completion effect")),
        },
        "review_gates": [
            "readability_review",
            "dependency_review",
            "budget_review",
            "runtime_import_review",
            "slice_smoke_review",
        ],
        "runtime_notes": _runtime_delivery(runtime).get("notes", []),
    }


def _model_seed(
    *,
    asset_id: str,
    label: str,
    category: str,
    primitive: str,
    region_id: str = "",
    width: float = 1.0,
    height: float = 1.0,
    depth: float = 1.0,
    radius: float = 0.5,
    segments: int = 16,
) -> Dict[str, Any]:
    return {
        "id": asset_id,
        "label": label,
        "category": category,
        "region_id": region_id,
        "primitive": primitive,
        "dimensions": {
            "width": float(width),
            "height": float(height),
            "depth": float(depth),
            "radius": float(radius),
            "segments": int(segments),
        },
        "source_stub": f"assets/models/source/{asset_id}.bbmodel",
        "runtime_target": f"assets/models/runtime/{asset_id}.gltf",
        "preview_target": f"playtest/renders/models/{asset_id}.png",
    }


def _local_model_assistants() -> Dict[str, Any]:
    """Return the default local-model support policy for asset production."""
    return {
        "plugin_id": "game_models",
        "plugin_depot": ".reverie/plugins/game_models",
        "model_depot": ".reverie/plugins/game_models/models",
        "venv": ".reverie/plugins/game_models/venv",
        "hardware_profile": {"ram_gb": 24, "vram_gb": 8},
        "recommended_models": [
            {
                "id": "trellis-text-xlarge",
                "repo_id": "microsoft/TRELLIS-text-xlarge",
                "role": "text_to_3d_primary_low_vram",
                "profile": "low_vram",
                "reason": "Primary local text-to-3D candidate; use the 8GB low_vram profile, then run Blender cleanup, retopo, rig, and material validation.",
            },
            {
                "id": "stable-fast-3d",
                "repo_id": "stabilityai/stable-fast-3d",
                "role": "image_to_3d_asset_candidate",
                "reason": "Default 8GB-VRAM-friendly local 3D asset ideation path after concept-image generation.",
            },
            {
                "id": "hunyuan3d-2mini",
                "repo_id": "tencent/Hunyuan3D-2mini",
                "role": "image_to_3d_higher_quality_mini",
                "profile": "low_vram",
                "reason": "Optional smaller Hunyuan3D image-to-3D lane for concept-image-to-mesh candidates on 24GB RAM / 8GB VRAM systems.",
            },
            {
                "id": "tripo-sr",
                "repo_id": "stabilityai/TripoSR",
                "role": "image_to_3d_fallback",
                "reason": "Fallback reconstruction model for smaller local hardware.",
            },
        ],
        "guarded_heavy_models": [
            {
                "id": "hy-motion-1.0",
                "repo_id": "tencent/HY-Motion-1.0",
                "role": "human_motion_generation",
                "guard": "Requires explicit allow_heavy; use only after the humanoid skeleton and retarget contract are stable.",
            },
        ],
        "character_modeling_contract": [
            "Use text-to-3D outputs as candidate meshes, not final shipped anatomy.",
            "For playable humanoids, require a continuous body core, one retargetable armature, explicit face landmarks, material roles, UVs, and GLB import validation.",
            "Layer clothing, hair, accessories, and weapon meshes over the continuous body core instead of leaving limbs or torso visually disconnected.",
        ],
        "usage_policy": [
            "Use rc_game_models_deployment_plan before downloading model packages.",
            "Use rc_game_models_select_model to persist the chosen model/profile; use profile=low_vram for TRELLIS on 8GB VRAM.",
            "Use rc_game_models_prepare_environment to create the plugin-local venv.",
            "Use rc_game_models_download_model with dry_run=true before heavy downloads.",
            "Never place model snapshots in C:\\Users, global HuggingFace cache folders, or system SDK paths by default.",
        ],
    }


def _budget_profile(
    playable_character_count: int,
    content_expansion: Dict[str, Any],
    combat_packet: Dict[str, Any],
    quest_packet: Dict[str, Any],
    world_packet: Dict[str, Any],
) -> Dict[str, Any]:
    region_count = len(content_expansion.get("region_seeds", []) or [])
    npc_count = len(content_expansion.get("npc_roster", []) or [])
    quest_arc_count = len(content_expansion.get("quest_arcs", []) or [])
    enemy_count = len(combat_packet.get("enemy_archetypes", []) or [])
    landmark_count = len(world_packet.get("landmarks", []) or [])
    objective_count = len(quest_packet.get("slice_objectives", []) or [])
    return {
        "slice_targets": {
            "playable_character_kits": max(1, playable_character_count),
            "npc_kits": max(1, min(npc_count, 4)),
            "enemy_kits": max(2, enemy_count),
            "region_landmark_kits": max(3, region_count),
            "quest_presentation_sets": max(1, objective_count // 2),
            "ui_surfaces": 3,
            "music_cues": 3,
            "combat_vfx_sets": 4,
        },
        "expansion_targets": {
            "region_templates": max(3, region_count),
            "quest_arc_manifests": max(2, quest_arc_count),
            "landmark_library": max(3, landmark_count),
            "enemy_family_library": max(3, enemy_count),
        },
        "budget_rules": [
            "Promote the highest-leverage starter assets first: player, guide, two enemy families, shrine finale, and one regional landmark kit.",
            "Do not widen region count until the current region kit, combat readability, and import validation all stay stable together.",
            "Treat UI, VFX, audio, and landmark kits as first-class production lanes instead of leaving them as unnamed polish debt.",
        ],
    }


def _starter_hero_model_seeds(
    game_request: Dict[str, Any],
    regions: List[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    party_model = str(game_request.get("experience", {}).get("party_model", "single_hero_focus")).strip()
    if party_model == "single_hero_focus":
        return []

    specialized = {
        str(item).strip()
        for item in game_request.get("systems", {}).get("specialized", []) or []
        if str(item).strip()
    }
    affinities = ["steel", "arc", "guard", "rush"]
    if "elemental_reaction" in specialized:
        affinities = ["flare", "tide", "volt", "gale"]

    role_specs = [
        ("starter_breaker", "Starter Breaker Runtime Kit", "breaker"),
        ("starter_support", "Starter Support Runtime Kit", "support"),
        ("starter_controller", "Starter Controller Runtime Kit", "controller"),
    ]
    seeds: List[Dict[str, Any]] = []
    home_region = str(regions[0].get("id", "starter_ruins")) if regions else "starter_ruins"
    for index, (asset_id, label, combat_role) in enumerate(role_specs):
        seed = _model_seed(
            asset_id=asset_id,
            label=label,
            category="character",
            primitive="box",
            region_id=home_region,
            width=0.9,
            height=1.85,
            depth=0.8,
        )
        seed["playable"] = True
        seed["combat_role"] = combat_role
        seed["combat_affinity"] = affinities[index % len(affinities)]
        seeds.append(seed)
    return seeds


def build_asset_pipeline_plan(
    game_request: Dict[str, Any],
    blueprint: Dict[str, Any],
    system_bundle: Dict[str, Any],
    content_expansion: Dict[str, Any],
    *,
    runtime_profile: Dict[str, Any] | None = None,
) -> Dict[str, Any]:
    """Build deterministic asset-production guidance for the current project."""

    runtime = target_runtime(blueprint, runtime_profile)
    packets = dict(system_bundle.get("packets", {}) or {})
    combat_packet = dict(packets.get("combat", {}) or {})
    quest_packet = dict(packets.get("quest", {}) or {})
    world_packet = dict(packets.get("world_structure", {}) or {})
    regions = list(content_expansion.get("region_seeds", []) or [])
    npcs = list(content_expansion.get("npc_roster", []) or [])
    quest_arcs = list(content_expansion.get("quest_arcs", []) or [])
    landmarks = [str(item).strip() for item in world_packet.get("landmarks", []) if str(item).strip()]
    enemy_archetypes = list(combat_packet.get("enemy_archetypes", []) or [])

    hero_seeds = _starter_hero_model_seeds(game_request, regions)
    modeling_seed: List[Dict[str, Any]] = [
        _model_seed(
            asset_id="player_avatar",
            label="Player Avatar Runtime Kit",
            category="character",
            primitive="box",
            region_id=str(regions[0].get("id", "starter_ruins")) if regions else "starter_ruins",
            width=0.9,
            height=1.9,
            depth=0.8,
        )
    ]
    modeling_seed[0]["playable"] = True
    modeling_seed[0]["combat_role"] = "vanguard"
    modeling_seed[0]["combat_affinity"] = hero_seeds[0].get("combat_affinity", "steel") if hero_seeds else "steel"
    modeling_seed.extend(hero_seeds)
    if npcs:
        first_npc = npcs[0]
        modeling_seed.append(
            _model_seed(
                asset_id=str(first_npc.get("id", "guide_beacon")),
                label=_display_name(first_npc.get("id", ""), "Guide Beacon"),
                category="npc",
                primitive="box",
                region_id=str(first_npc.get("home_region", regions[0].get("id", "starter_ruins") if regions else "starter_ruins")),
                width=0.85,
                height=1.8,
                depth=0.75,
            )
        )
    for archetype in enemy_archetypes[:4]:
        archetype_id = str(archetype.get("id", "")).strip()
        if not archetype_id:
            continue
        primitive = "pyramid" if "warden" in archetype_id or "boss" in archetype_id else "box"
        modeling_seed.append(
            _model_seed(
                asset_id=archetype_id,
                label=_display_name(archetype_id, "Enemy Runtime Kit"),
                category="enemy",
                primitive=primitive,
                region_id=str(regions[0].get("id", "starter_ruins")) if regions else "starter_ruins",
                width=1.0 if primitive == "box" else 2.2,
                height=1.8 if primitive == "box" else 3.0,
                depth=0.9 if primitive == "box" else 2.2,
            )
        )
    for index, region in enumerate(regions[:3], start=1):
        region_id = str(region.get("id", f"region_{index}"))
        modeling_seed.append(
            _model_seed(
                asset_id=f"{region_id}_landmark",
                label=f"{_display_name(region_id, f'Region {index}')} Landmark",
                category="world_kit",
                primitive="pyramid",
                region_id=region_id,
                width=3.0,
                height=4.6,
                depth=3.0,
            )
        )

    registry_seed = {
        "regions": [
            {
                "id": str(region.get("id", "")),
                "label": _display_name(region.get("id", ""), "Region"),
                "biome": str(region.get("biome", "")),
                "signature_landmark": str(region.get("signature_landmark", "")),
            }
            for region in regions
        ],
        "npc_cast": [
            {
                "id": str(npc.get("id", "")),
                "label": _display_name(npc.get("id", ""), "NPC"),
                "role": str(npc.get("role", "")),
                "home_region": str(npc.get("home_region", "")),
            }
            for npc in npcs
        ],
        "enemy_families": [
            {
                "id": str(enemy.get("id", "")),
                "label": _display_name(enemy.get("id", ""), "Enemy"),
                "role": str(enemy.get("role", "")),
            }
            for enemy in enemy_archetypes
        ],
        "landmarks": landmarks,
        "quest_arcs": [
            {
                "id": str(arc.get("id", "")),
                "title": str(arc.get("title", "")),
                "lead_npc": str(arc.get("lead_npc", "")),
            }
            for arc in quest_arcs
        ],
        "playable_roster": [
            {
                "id": str(seed.get("id", "")),
                "label": _display_name(seed.get("id", ""), "Playable Hero"),
                "combat_role": str(seed.get("combat_role", "vanguard")),
                "combat_affinity": str(seed.get("combat_affinity", "steel")),
            }
            for seed in modeling_seed
            if bool(seed.get("playable", False))
        ],
    }

    production_queue: List[Dict[str, Any]] = []
    for seed in modeling_seed:
        category = str(seed.get("category", "world_kit"))
        asset_id = str(seed.get("id", "asset"))
        priority = "now"
        if category == "world_kit" and str(seed.get("region_id", "")) not in {"", "starter_ruins"}:
            priority = "next"
        if category == "npc" and asset_id not in {str(npcs[0].get("id", "")) if npcs else ""}:
            priority = "next"
        production_queue.append(
            {
                "id": f"{asset_id}_production",
                "priority": priority,
                "category": category,
                "goal": f"Promote {asset_id} into an authored production-ready asset package with source, runtime export, preview, and import evidence.",
                "source_stub": seed["source_stub"],
                "runtime_target": seed["runtime_target"],
                "validation": ["naming", "dependencies", "budgets", "runtime_import_review"],
            }
        )

    production_queue.extend(
        [
            {
                "id": "combat_vfx_pass",
                "priority": "next",
                "category": "effect",
                "goal": "Author hit, guard, perfect-guard, projectile, and shrine-completion effects that read clearly under movement pressure.",
                "source_stub": "assets/raw/vfx/combat",
                "runtime_target": "assets/processed/vfx/combat",
                "validation": ["readability_review", "budget_review", "slice_smoke_review"],
            },
            {
                "id": "hud_surface_upgrade",
                "priority": "next",
                "category": "ui",
                "goal": "Author a coherent ARPG HUD presentation kit for health, stamina, objective, and guard states.",
                "source_stub": "assets/raw/ui/hud",
                "runtime_target": "assets/processed/ui/hud",
                "validation": ["readability_review", "slice_smoke_review"],
            },
            {
                "id": "regional_audio_palette",
                "priority": "later",
                "category": "audio",
                "goal": "Establish regional ambiences, combat stingers, and completion cues that can scale across multiple regions.",
                "source_stub": "assets/raw/audio/regions",
                "runtime_target": "assets/processed/audio/regions",
                "validation": ["budget_review", "runtime_import_review"],
            },
        ]
    )

    delivery = _runtime_delivery(runtime)
    return {
        "schema_version": "reverie.asset_pipeline/1",
        "project_name": project_name(game_request, blueprint),
        "generated_at": _utc_now(),
        "runtime": runtime,
        "runtime_delivery": delivery,
        "modeling_workspace": {
            "source_models": "assets/models/source",
            "runtime_models": "assets/models/runtime",
            "preview_renders": "playtest/renders/models",
            "registry_path": "data/models/model_registry.yaml",
            "pipeline_manifest_path": "data/models/pipeline.yaml",
        },
        "import_profile": _import_profile(runtime),
        "local_model_assistants": _local_model_assistants(),
        "validation_rules": _validation_rules(runtime, world_packet),
        "budget_profile": _budget_profile(
            len([seed for seed in modeling_seed if bool(seed.get("playable", False))]),
            content_expansion,
            combat_packet,
            quest_packet,
            world_packet,
        ),
        "content_sets": {
            "regions": registry_seed["regions"],
            "npc_cast": registry_seed["npc_cast"],
            "enemy_families": registry_seed["enemy_families"],
            "quest_arcs": registry_seed["quest_arcs"],
            "landmarks": landmarks,
            "playable_roster": registry_seed["playable_roster"],
        },
        "registry_seed": registry_seed,
        "modeling_seed": modeling_seed,
        "starter_asset_packages": [
            {
                "id": str(seed.get("id", "")),
                "category": str(seed.get("category", "world_kit")),
                "source_stub": str(seed.get("source_stub", "")),
                "runtime_target": str(seed.get("runtime_target", "")),
                "preview_target": str(seed.get("preview_target", "")),
                "status": "generated_runtime_starter",
                "required_evidence": ["source_stub", "runtime_export", "preview", "model_registry_entry"],
            }
            for seed in modeling_seed
        ],
        "production_queue": production_queue,
        "continuity_rules": [
            "Treat the project-level modeling workspace as the source of truth even when the selected runtime keeps its own asset mirror.",
            "Do not widen visual fidelity faster than combat readability, quest ids, and slice validation can keep up.",
            "Refresh the model registry and asset pipeline artifact together whenever starter assets are promoted into authored content.",
        ],
    }


def asset_pipeline_markdown(plan: Dict[str, Any]) -> str:
    lines = [f"# Asset Pipeline: {plan.get('project_name', 'Untitled Reverie Slice')}", ""]
    lines.append(f"Runtime: {plan.get('runtime', 'reverie_engine')}")
    lines.append(f"Registry Path: {plan.get('modeling_workspace', {}).get('registry_path', 'data/models/model_registry.yaml')}")
    lines.append("")
    lines.append("## Modeling Workspace")
    for key, value in (plan.get("modeling_workspace", {}) or {}).items():
        lines.append(f"- {key}: {value}")
    lines.append("")
    lines.append("## Import Profile")
    for key, value in (plan.get("import_profile", {}) or {}).items():
        lines.append(f"- {key}: {value}")
    lines.append("")
    lines.append("## Local Model Assistants")
    assistants = plan.get("local_model_assistants", {}) or {}
    lines.append(f"- plugin: {assistants.get('plugin_id', 'game_models')}")
    lines.append(f"- model depot: {assistants.get('model_depot', '.reverie/plugins/game_models/models')}")
    for item in assistants.get("recommended_models", []):
        lines.append(f"- recommended: {item.get('id', 'model')} | {item.get('repo_id', '')}")
    for item in assistants.get("guarded_heavy_models", []):
        lines.append(f"- guarded: {item.get('id', 'model')} | {item.get('repo_id', '')}")
    lines.append("")
    lines.append("## Production Queue")
    for item in plan.get("production_queue", []):
        lines.append(
            f"- {item.get('id', 'item')}: [{item.get('priority', 'later')}] {item.get('category', 'asset')} -> {item.get('goal', '')}"
        )
    lines.append("")
    lines.append("## Starter Asset Packages")
    for item in plan.get("starter_asset_packages", []):
        lines.append(
            f"- {item.get('id', 'asset')}: {item.get('status', 'generated')} | {item.get('runtime_target', '')}"
        )
    lines.append("")
    lines.append("## Modeling Seeds")
    for seed in plan.get("modeling_seed", []):
        lines.append(
            f"- {seed.get('id', 'seed')}: {seed.get('primitive', 'box')} | {seed.get('source_stub', '')} -> {seed.get('runtime_target', '')}"
        )
    lines.append("")
    return "\n".join(lines)
