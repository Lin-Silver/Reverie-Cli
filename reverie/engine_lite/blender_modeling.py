"""Built-in Blender authoring helpers for Reverie modeling workflows."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, Optional
import ast
import json
import os
import re
import shutil
import subprocess
import sys

from .modeling import (
    PREFERRED_RUNTIME_EXTENSIONS,
    inspect_modeling_workspace,
    materialize_modeling_workspace,
    project_modeling_paths,
    summarize_model_file,
    sync_model_registry,
)


BLENDER_MODEL_PRESETS = (
    "auto",
    "hero_prop",
    "fantasy_relic",
    "sci_fi_crate",
    "environment_diorama",
    "character_proxy",
    "anime_action_character",
    "production_character_pipeline",
    "modular_building",
)
BLENDER_EXPORT_FORMATS = ("glb", "gltf", "blend")
BLENDER_SCRIPT_BLOCKLIST = {
    "ctypes",
    "multiprocessing",
    "socket",
    "subprocess",
    "webbrowser",
}


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def _slugify(value: Any, fallback: str = "blender_model") -> str:
    normalized = "".join(ch.lower() if ch.isalnum() else "_" for ch in str(value or ""))
    normalized = re.sub(r"_+", "_", normalized).strip("_")
    return normalized or fallback


def _relative_to(root: Path, path: Path) -> str:
    try:
        return str(path.resolve().relative_to(root.resolve())).replace("\\", "/")
    except ValueError:
        return str(path.resolve())


def _read_json_file(path: Path) -> Dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        return payload if isinstance(payload, dict) else {}
    except Exception:
        return {}


def _artifact_record(root: Path, path: Path) -> Dict[str, Any]:
    exists = path.exists()
    return {
        "path": _relative_to(root, path),
        "absolute_path": str(path),
        "exists": exists,
        "size_bytes": path.stat().st_size if exists and path.is_file() else 0,
    }


def blender_modeling_paths(project_root: str | Path) -> Dict[str, Path]:
    """Return Blender-specific paths inside the standard modeling workspace."""
    paths = project_modeling_paths(project_root)
    root = paths["project_root"]
    blender_source = paths["source_models"] / "blender"
    return {
        **paths,
        "blender_source": blender_source,
        "blender_scripts": blender_source / "scripts",
        "blender_plans": blender_source / "plans",
        "blender_metadata": root / "data/models/blender",
    }


def _unique_paths(paths: Iterable[Path]) -> list[Path]:
    results: list[Path] = []
    seen: set[str] = set()
    for path in paths:
        key = str(path).lower()
        if key in seen:
            continue
        seen.add(key)
        results.append(path)
    return results


def _blender_install_candidates() -> list[Path]:
    candidates: list[Path] = []

    for env_name in ("REVERIE_BLENDER_PATH", "BLENDER_PATH"):
        raw = os.environ.get(env_name, "").strip()
        if raw:
            candidate = Path(raw)
            if candidate.is_dir():
                candidates.append(candidate / ("blender.exe" if os.name == "nt" else "blender"))
            else:
                candidates.append(candidate)

    which_blender = shutil.which("blender")
    if which_blender:
        candidates.append(Path(which_blender))

    if os.name == "nt":
        app_plugin_root: Optional[Path] = None
        try:
            from ..config import get_app_root

            app_plugin_root = get_app_root() / ".reverie" / "plugins" / "blender"
        except Exception:
            app_plugin_root = None
        portable_roots = [
            app_plugin_root,
            Path.cwd() / ".reverie" / "plugins" / "blender",
            Path.cwd() / "dist" / ".reverie" / "plugins" / "blender",
            Path(sys.executable).resolve().parent / ".reverie" / "plugins" / "blender",
        ]
        for root in [item for item in portable_roots if item is not None]:
            candidates.extend(
                [
                    root / "runtime" / "blender.exe",
                    root / "runtime" / "blender" / "blender.exe",
                    root / "blender.exe",
                    root / "bin" / "blender.exe",
                ]
            )
            runtime_root = root / "runtime"
            if runtime_root.exists():
                candidates.extend(sorted(runtime_root.glob("**/blender.exe"), key=lambda path: str(path).lower()))
        for root_name in ("ProgramFiles", "ProgramFiles(x86)", "LOCALAPPDATA"):
            root = os.environ.get(root_name, "").strip()
            if not root:
                continue
            base = Path(root) / "Blender Foundation"
            if base.exists():
                candidates.extend(sorted(base.glob("Blender */blender.exe"), reverse=True))
            candidates.append(base / "Blender" / "blender.exe")
    elif os.name == "posix":
        candidates.extend(
            [
                Path("/Applications/Blender.app/Contents/MacOS/Blender"),
                Path("/usr/bin/blender"),
                Path("/usr/local/bin/blender"),
                Path("/opt/blender/blender"),
                Path("/snap/bin/blender"),
            ]
        )

    return _unique_paths(candidates)


def _probe_blender_version(executable: Path, timeout_seconds: float = 4.0) -> Dict[str, Any]:
    try:
        completed = subprocess.run(
            [str(executable), "--version"],
            capture_output=True,
            text=True,
            timeout=timeout_seconds,
            check=False,
            encoding="utf-8",
            errors="replace",
        )
    except Exception as exc:
        return {
            "ok": False,
            "version": "",
            "stdout": "",
            "stderr": str(exc),
            "exit_code": -1,
        }

    first_line = ""
    for line in (completed.stdout or completed.stderr or "").splitlines():
        if line.strip():
            first_line = line.strip()
            break
    return {
        "ok": completed.returncode == 0,
        "version": first_line,
        "stdout": completed.stdout,
        "stderr": completed.stderr,
        "exit_code": completed.returncode,
    }


def detect_blender_installation(blender_path: Any = "") -> Dict[str, Any]:
    """Detect a local Blender executable and report version details."""
    candidates: list[Path] = []
    explicit = str(blender_path or "").strip()
    if explicit:
        explicit_path = Path(explicit)
        if explicit_path.is_dir():
            explicit_path = explicit_path / ("blender.exe" if os.name == "nt" else "blender")
        candidates.append(explicit_path)
    candidates.extend(_blender_install_candidates())
    candidates = _unique_paths(candidates)

    executable = next((candidate.resolve() for candidate in candidates if candidate.exists() and candidate.is_file()), None)
    version_info = _probe_blender_version(executable) if executable else {}
    return {
        "installed": executable is not None,
        "available": executable is not None and bool(version_info.get("ok", True)),
        "executable_path": str(executable) if executable else "",
        "version": str(version_info.get("version", "") or ""),
        "version_probe": version_info,
        "candidates": [str(path) for path in candidates],
        "manual_dependency": True,
        "install_hint": "Install Blender 3.6+, run /plugins deploy blender, or set REVERIE_BLENDER_PATH/BLENDER_PATH to blender.exe.",
    }


def infer_blender_preset(brief: str, requested_preset: str = "auto") -> str:
    """Choose a deterministic authoring preset from a freeform brief."""
    candidate = str(requested_preset or "auto").strip().lower()
    if candidate in BLENDER_MODEL_PRESETS and candidate != "auto":
        return candidate

    text = str(brief or "").lower()
    signals = {
        "production_character_pipeline": (
            "final character asset",
            "production character",
            "3a final",
            "aaa final",
            "hero asset",
            "high poly",
            "retopo",
            "uv unwrap",
            "texture bake",
            "rigged",
            "skinned",
            "game ready character",
            "\u9ad8\u6a21",
            "\u62d3\u6251",
            "\u91cd\u62d3\u6251",
            "uv",
            "\u8d34\u56fe",
            "\u7ed1\u5b9a",
            "\u6743\u91cd",
            "\u52a8\u4f5c",
            "\u6700\u7ec8\u89d2\u8272\u8d44\u4ea7",
            "\u6e38\u620f\u53ef\u7528\u4eba\u7269",
        ),
        "anime_action_character": (
            "aaa character",
            "3a character",
            "anime action",
            "stylized character",
            "hero character",
            "game character",
            "playable character",
            "genshin",
            "hoyoverse",
            "mihoyo",
            "zenless",
            "zzz",
            "ananta",
            "neverness",
            "\u7edd\u533a\u96f6",
            "\u539f\u795e",
            "\u5f02\u73af",
            "\u4e8c\u6e38",
            "\u89d2\u8272\u5efa\u6a21",
            "\u4eba\u7269\u5efa\u6a21",
        ),
        "character_proxy": (
            "character",
            "avatar",
            "hero",
            "npc",
            "person",
            "player",
            "body",
            "角色",
            "人物",
            "主角",
        ),
        "environment_diorama": (
            "environment",
            "diorama",
            "terrain",
            "landmark",
            "world",
            "forest",
            "ruin",
            "scene",
            "环境",
            "地形",
            "世界",
            "遗迹",
            "场景",
        ),
        "sci_fi_crate": (
            "sci-fi",
            "scifi",
            "mecha",
            "robot",
            "crate",
            "panel",
            "terminal",
            "cyber",
            "机械",
            "科幻",
            "机甲",
            "箱",
        ),
        "fantasy_relic": (
            "relic",
            "artifact",
            "crystal",
            "magic",
            "altar",
            "shrine",
            "fantasy",
            "spell",
            "圣物",
            "水晶",
            "魔法",
            "祭坛",
            "神龛",
            "幻想",
        ),
        "modular_building": (
            "building",
            "house",
            "tower",
            "wall",
            "modular",
            "city",
            "village",
            "建筑",
            "房屋",
            "塔",
            "城镇",
        ),
    }
    for preset, tokens in signals.items():
        if any(token in text for token in tokens):
            return preset
    return "hero_prop"


def _style_profile(style: str, brief: str) -> Dict[str, Any]:
    text = f"{style} {brief}".lower()
    if any(
        token in text
        for token in (
            "anime action",
            "stylized character",
            "genshin",
            "zenless",
            "zzz",
            "ananta",
            "hoyoverse",
            "\u7edd\u533a\u96f6",
            "\u539f\u795e",
            "\u5f02\u73af",
            "\u4e8c\u6e38",
        )
    ):
        return {
            "style": "anime_action",
            "palette": [[0.09, 0.11, 0.13, 1], [0.12, 0.72, 0.86, 1], [0.98, 0.68, 0.28, 1]],
            "metallic": 0.18,
            "roughness": 0.46,
        }
    if any(token in text for token in ("sci", "cyber", "mecha", "科幻", "机甲")):
        return {
            "style": "sci_fi",
            "palette": [[0.08, 0.11, 0.14, 1], [0.16, 0.55, 0.9, 1], [0.95, 0.72, 0.24, 1]],
            "metallic": 0.65,
            "roughness": 0.38,
        }
    if any(token in text for token in ("fantasy", "magic", "crystal", "魔法", "幻想", "水晶")):
        return {
            "style": "fantasy",
            "palette": [[0.48, 0.2, 0.78, 1], [0.08, 0.78, 0.84, 1], [0.96, 0.82, 0.34, 1]],
            "metallic": 0.22,
            "roughness": 0.48,
        }
    if any(token in text for token in ("real", "stone", "ruin", "岩", "石", "遗迹")):
        return {
            "style": "natural",
            "palette": [[0.45, 0.49, 0.44, 1], [0.22, 0.34, 0.26, 1], [0.72, 0.65, 0.52, 1]],
            "metallic": 0.0,
            "roughness": 0.82,
        }
    return {
        "style": "stylized",
        "palette": [[0.18, 0.28, 0.62, 1], [0.94, 0.38, 0.48, 1], [0.97, 0.82, 0.38, 1]],
        "metallic": 0.12,
        "roughness": 0.56,
    }


def build_blender_model_spec(
    *,
    brief: str,
    model_name: str,
    preset: str = "auto",
    style: str = "stylized",
    export_format: str = "glb",
) -> Dict[str, Any]:
    """Build a stable high-level model plan for the generated Blender script."""
    resolved_name = str(model_name or "").strip() or "blender_model"
    resolved_preset = infer_blender_preset(brief, preset)
    export_key = str(export_format or "glb").strip().lower()
    if export_key not in BLENDER_EXPORT_FORMATS:
        export_key = "glb"
    profile = _style_profile(style, brief)
    return {
        "schema": "reverie.blender_model_spec.v1",
        "generated_at": _utc_now(),
        "model_name": resolved_name,
        "slug": _slugify(resolved_name),
        "brief": str(brief or "").strip(),
        "preset": resolved_preset,
        "style": profile["style"],
        "palette": profile["palette"],
        "metallic": profile["metallic"],
        "roughness": profile["roughness"],
        "export_format": export_key,
        "quality_targets": {
            "beveled_edges": True,
            "weighted_normals": True,
            "named_objects": True,
            "camera_and_lighting": True,
            "hero_character_blockout": resolved_preset == "anime_action_character",
            "rig_and_lod_markers": resolved_preset == "anime_action_character",
            "material_ids_for_baking": True,
            "high_poly_collection": resolved_preset == "production_character_pipeline",
            "retopo_low_collection": resolved_preset == "production_character_pipeline",
            "uv_layout": resolved_preset == "production_character_pipeline",
            "texture_exports": resolved_preset == "production_character_pipeline",
            "procedural_texture_authoring": resolved_preset == "production_character_pipeline",
            "skeletal_rig": resolved_preset == "production_character_pipeline",
            "animation_actions": resolved_preset == "production_character_pipeline",
            "ik_control_markers": resolved_preset == "production_character_pipeline",
            "lod_variants": resolved_preset == "production_character_pipeline",
            "vertex_group_weights": resolved_preset == "production_character_pipeline",
            "material_tuning_pass": resolved_preset == "production_character_pipeline",
            "skinning_manifest": resolved_preset == "production_character_pipeline",
            "animation_manifest": resolved_preset == "production_character_pipeline",
            "facial_deformation_manifest": resolved_preset == "production_character_pipeline",
            "pose_stress_validation": resolved_preset == "production_character_pipeline",
            "visual_qa_report": resolved_preset == "production_character_pipeline",
            "engine_import_contract": resolved_preset == "production_character_pipeline",
            "production_stage_manifest": resolved_preset == "production_character_pipeline",
            "asset_validation_report": resolved_preset == "production_character_pipeline",
            "post_run_quality_audit": resolved_preset == "production_character_pipeline",
            "automation_iteration_plan": resolved_preset == "production_character_pipeline",
            "production_asset_card": resolved_preset == "production_character_pipeline",
            "runtime_export": export_key in {"glb", "gltf"},
        },
        "sources": {
            "design_pattern": "Built into Reverie from Blender CLI and bpy workflow research; no external MCP runtime required.",
            "execution": "Blender background mode with a workspace-local generated Python script.",
        },
    }


def _script_paths(project_root: str | Path, spec: Dict[str, Any], export_format: str) -> Dict[str, Path]:
    paths = blender_modeling_paths(project_root)
    slug = _slugify(spec.get("slug") or spec.get("model_name"))
    suffix = str(export_format or spec.get("export_format") or "glb").strip().lower()
    if suffix not in BLENDER_EXPORT_FORMATS:
        suffix = "glb"
    return {
        "plan": paths["blender_plans"] / f"{slug}.json",
        "script": paths["blender_scripts"] / f"{slug}.py",
        "blend": paths["source_models"] / f"{slug}.blend",
        "runtime": paths["runtime_models"] / f"{slug}.{suffix}" if suffix != "blend" else paths["source_models"] / f"{slug}.blend",
        "preview": paths["preview_renders"] / f"{slug}.png",
        "metadata": paths["blender_metadata"] / f"{slug}.json",
        "texture_basecolor": paths["project_root"] / "assets" / "textures" / "blender" / slug / f"{slug}_basecolor.png",
        "texture_normal": paths["project_root"] / "assets" / "textures" / "blender" / slug / f"{slug}_normal.png",
        "texture_orm": paths["project_root"] / "assets" / "textures" / "blender" / slug / f"{slug}_orm.png",
        "texture_id": paths["project_root"] / "assets" / "textures" / "blender" / slug / f"{slug}_id.png",
        "validation_report": paths["blender_metadata"] / f"{slug}_validation.json",
        "asset_card": paths["blender_metadata"] / f"{slug}_asset_card.json",
        "production_manifest": paths["blender_metadata"] / f"{slug}_production_manifest.json",
        "qa_report": paths["blender_metadata"] / f"{slug}_qa_report.json",
        "engine_contract": paths["blender_metadata"] / f"{slug}_engine_contract.json",
        "iteration_plan": paths["blender_metadata"] / f"{slug}_iteration_plan.json",
    }


def _build_authoring_script(spec: Dict[str, Any], outputs: Dict[str, Path], *, render_preview: bool) -> str:
    spec_json = json.dumps(spec, ensure_ascii=True, indent=2)
    output_json = json.dumps({key: str(value) for key, value in outputs.items()}, ensure_ascii=True, indent=2)
    return f'''# Generated by Reverie CLI. Run with Blender: blender --background --python this_file.py
from __future__ import annotations

import json
import math
from pathlib import Path

import bpy


SPEC = json.loads({spec_json!r})
OUTPUTS = {{key: Path(value) for key, value in json.loads({output_json!r}).items()}}
RENDER_PREVIEW = {bool(render_preview)!r}
PIPELINE_STATE = {{"export_objects": [], "actions": [], "textures": {{}}, "texture_manifest": {{}}, "texture_authoring_manifest": {{}}, "material_tuning": {{}}, "collections": [], "armature": "", "shape_keys": [], "facial_manifest": {{}}, "sockets": [], "rig_controls": [], "ik_targets": [], "ik_constraints": [], "collision_proxies": [], "lods": [], "vertex_groups": {{}}, "skinning_manifest": {{}}, "animation_manifest": {{}}, "pose_stress_report": {{}}, "mesh_metrics": {{}}, "bake_manifest": {{}}, "art_readiness_report": {{}}, "visual_qa_report": {{}}, "engine_import_contract": {{}}, "production_manifest": {{}}, "iteration_plan": {{}}, "validation": {{}}, "quality_gates": [], "asset_card": {{}}, "camera_action": ""}}


def ensure_parent(path):
    path.parent.mkdir(parents=True, exist_ok=True)


def clear_scene():
    bpy.ops.object.select_all(action="SELECT")
    bpy.ops.object.delete()


def set_active(obj):
    bpy.ops.object.select_all(action="DESELECT")
    obj.select_set(True)
    bpy.context.view_layer.objects.active = obj


def ensure_collection(name, parent=None):
    collection = bpy.data.collections.get(name)
    if collection is None:
        collection = bpy.data.collections.new(name)
    parent_collection = parent or bpy.context.scene.collection
    try:
        parent_collection.children.link(collection)
    except RuntimeError:
        pass
    return collection


def place_in_collection(obj, collection):
    if collection is None:
        return obj
    if collection.objects.get(obj.name) is None:
        collection.objects.link(obj)
    for existing in list(obj.users_collection):
        if existing == collection:
            continue
        try:
            existing.objects.unlink(obj)
        except RuntimeError:
            pass
    return obj


def apply_object_transforms(obj):
    if obj.type != "MESH":
        return obj
    try:
        set_active(obj)
        bpy.ops.object.transform_apply(location=False, rotation=True, scale=True)
    except Exception:
        pass
    return obj


def make_material(name, color, metallic=0.0, roughness=0.55, emission=None, strength=0.0):
    mat = bpy.data.materials.new(name)
    mat.use_nodes = True
    bsdf = mat.node_tree.nodes.get("Principled BSDF")
    if bsdf is not None:
        if "Base Color" in bsdf.inputs:
            bsdf.inputs["Base Color"].default_value = color
        if "Metallic" in bsdf.inputs:
            bsdf.inputs["Metallic"].default_value = metallic
        if "Roughness" in bsdf.inputs:
            bsdf.inputs["Roughness"].default_value = roughness
        if emission and "Emission Color" in bsdf.inputs:
            bsdf.inputs["Emission Color"].default_value = emission
        if emission and "Emission Strength" in bsdf.inputs:
            bsdf.inputs["Emission Strength"].default_value = strength
    return mat


def add_modifier(obj, mod_type, name, **kwargs):
    mod = obj.modifiers.new(name=name, type=mod_type)
    for key, value in kwargs.items():
        if hasattr(mod, key):
            setattr(mod, key, value)
    return mod


def polish(obj, bevel=0.025, weighted=True, shade=True):
    if obj.type == "MESH":
        if shade:
            try:
                bpy.context.view_layer.objects.active = obj
                obj.select_set(True)
                bpy.ops.object.shade_smooth()
                obj.select_set(False)
            except Exception:
                pass
        if bevel > 0:
            add_modifier(obj, "BEVEL", "reverie_bevel", width=bevel, segments=3, affect="EDGES")
        if weighted:
            add_modifier(obj, "WEIGHTED_NORMAL", "reverie_weighted_normals", keep_sharp=True)
    return obj


def assign(obj, mat):
    obj.data.materials.append(mat)
    return obj


def cube(name, loc, scale, mat, bevel=0.035):
    bpy.ops.mesh.primitive_cube_add(size=1.0, location=loc)
    obj = bpy.context.object
    obj.name = name
    obj.scale = scale
    assign(obj, mat)
    return polish(obj, bevel=bevel)


def cylinder(name, loc, radius, depth, mat, vertices=32, bevel=0.02):
    bpy.ops.mesh.primitive_cylinder_add(vertices=vertices, radius=radius, depth=depth, location=loc)
    obj = bpy.context.object
    obj.name = name
    assign(obj, mat)
    return polish(obj, bevel=bevel)


def sphere(name, loc, radius, mat, segments=32, ring_count=16, bevel=0.0):
    bpy.ops.mesh.primitive_uv_sphere_add(segments=segments, ring_count=ring_count, radius=radius, location=loc)
    obj = bpy.context.object
    obj.name = name
    assign(obj, mat)
    return polish(obj, bevel=bevel)


def ellipsoid(name, loc, radius, scale, mat, segments=32, ring_count=16, bevel=0.0):
    obj = sphere(name, loc, radius, mat, segments=segments, ring_count=ring_count, bevel=bevel)
    obj.scale = scale
    return obj


def cone(name, loc, radius1, radius2, depth, mat, vertices=32, bevel=0.02):
    bpy.ops.mesh.primitive_cone_add(vertices=vertices, radius1=radius1, radius2=radius2, depth=depth, location=loc)
    obj = bpy.context.object
    obj.name = name
    assign(obj, mat)
    return polish(obj, bevel=bevel)


def torus(name, loc, major, minor, mat, rotation=(0, 0, 0)):
    bpy.ops.mesh.primitive_torus_add(major_radius=major, minor_radius=minor, major_segments=72, minor_segments=12, location=loc, rotation=rotation)
    obj = bpy.context.object
    obj.name = name
    assign(obj, mat)
    return polish(obj, bevel=0.0)


def add_label(name, text, loc, mat, size=0.2, rotation=(math.radians(75), 0, 0)):
    curve = bpy.data.curves.new(name, type="FONT")
    curve.body = text
    curve.align_x = "CENTER"
    curve.align_y = "CENTER"
    curve.size = size
    curve.extrude = 0.012
    obj = bpy.data.objects.new(name, curve)
    bpy.context.collection.objects.link(obj)
    obj.location = loc
    obj.rotation_euler = rotation
    obj.data.materials.append(mat)
    return obj


def add_empty_marker(name, loc, size=0.08, display_type="SPHERE"):
    obj = bpy.data.objects.new(name, None)
    bpy.context.collection.objects.link(obj)
    obj.empty_display_type = display_type
    obj.empty_display_size = size
    obj.location = loc
    return obj


def material_set():
    palette = SPEC["palette"]
    return {{
        "primary": make_material("rv_primary_" + SPEC["style"], palette[0], SPEC["metallic"], SPEC["roughness"]),
        "accent": make_material("rv_accent_" + SPEC["style"], palette[1], 0.18, 0.42, emission=palette[1], strength=0.12),
        "gold": make_material("rv_trim_gold", palette[2], 0.7, 0.28),
        "dark": make_material("rv_dark_anchor", [0.055, 0.065, 0.075, 1], 0.25, 0.62),
        "soft": make_material("rv_soft_ivory", [0.82, 0.78, 0.68, 1], 0.0, 0.76),
        "skin": make_material("rv_skin_warm_porcelain", [0.93, 0.73, 0.62, 1], 0.0, 0.58),
        "hair": make_material("rv_hair_graphite", [0.055, 0.052, 0.06, 1], 0.05, 0.5),
        "cloth_alt": make_material("rv_cloth_secondary", [0.7, 0.11, 0.18, 1], 0.08, 0.62),
        "line": make_material("rv_ink_linework", [0.015, 0.017, 0.02, 1], 0.0, 0.7),
        "glow": make_material("rv_emissive_detail", palette[1], 0.0, 0.2, emission=palette[1], strength=1.8),
    }}


def capture_created_objects(builder, *args, **kwargs):
    before = set(obj.name for obj in bpy.context.scene.objects)
    builder(*args, **kwargs)
    return [obj for obj in bpy.context.scene.objects if obj.name not in before]


def build_production_collections():
    root = ensure_collection("rv_pipeline_" + SPEC["slug"])
    return {{
        "root": root,
        "high": ensure_collection("high_poly", root),
        "low": ensure_collection("retopo_low", root),
        "bake": ensure_collection("bake_support", root),
        "rig": ensure_collection("rig", root),
        "collision": ensure_collection("collision_proxy", root),
        "preview": ensure_collection("preview_helpers", root),
    }}


def route_production_objects(objects, collections):
    high_meshes = []
    support_objects = []
    for obj in objects:
        name = obj.name.lower()
        if obj.type == "MESH" and "silhouette_base" not in name and "centerline_rig_reference" not in name:
            place_in_collection(obj, collections["high"])
            high_meshes.append(obj)
            continue
        target = collections["rig"] if name.startswith(("rig_marker", "lod_marker")) or obj.type == "EMPTY" else collections["preview"]
        place_in_collection(obj, target)
        support_objects.append(obj)
    return high_meshes, support_objects


def high_poly_levels_for(obj):
    name = obj.name.lower()
    if "hair" in name or "face" in name or "blade" in name:
        return 3
    if "torso" in name or "head" in name or "jacket" in name:
        return 2
    return 1


def low_poly_ratio_for(obj):
    name = obj.name.lower()
    if "hair" in name:
        return 0.78
    if "face" in name or "head" in name or "eye" in name or "mouth" in name or "nose" in name:
        return 0.88
    if "blade" in name or "weapon" in name:
        return 0.82
    if "glow" in name or "core" in name:
        return 0.76
    if "torso" in name or "leg" in name or "arm" in name or "hand" in name:
        return 0.66
    return 0.58


def prepare_high_poly_meshes(meshes):
    for obj in meshes:
        if obj.type != "MESH":
            continue
        apply_object_transforms(obj)
        obj["reverie_stage"] = "high_poly"
        multires = add_modifier(obj, "MULTIRES", "rv_sculpt_multires")
        levels = high_poly_levels_for(obj)
        if hasattr(multires, "levels"):
            multires.levels = levels
        if hasattr(multires, "sculpt_levels"):
            multires.sculpt_levels = levels + 1
        if hasattr(multires, "render_levels"):
            multires.render_levels = levels + 1
        if hasattr(multires, "quality"):
            multires.quality = 6
        smooth = add_modifier(obj, "CORRECTIVE_SMOOTH", "rv_sculpt_relax", iterations=2)
        if hasattr(smooth, "factor"):
            smooth.factor = 0.45


def duplicate_mesh_object(source, name):
    obj = source.copy()
    obj.data = source.data.copy()
    obj.animation_data_clear()
    bpy.context.scene.collection.objects.link(obj)
    obj.name = name
    obj.matrix_world = source.matrix_world.copy()
    return obj


def make_low_poly_meshes(high_meshes, collection):
    low_meshes = []
    for source in high_meshes:
        low = duplicate_mesh_object(source, source.name + "_game")
        for modifier in list(low.modifiers):
            low.modifiers.remove(modifier)
        place_in_collection(low, collection)
        low["reverie_stage"] = "retopo_low"
        low["reverie_source_high"] = source.name
        decimate = add_modifier(low, "DECIMATE", "rv_game_mesh_density")
        if hasattr(decimate, "ratio"):
            decimate.ratio = low_poly_ratio_for(source)
        shrink = add_modifier(low, "SHRINKWRAP", "rv_high_surface", target=source)
        if hasattr(shrink, "wrap_method"):
            shrink.wrap_method = "NEAREST_SURFACEPOINT"
        if hasattr(shrink, "wrap_mode"):
            shrink.wrap_mode = "ABOVE_SURFACE"
        low_meshes.append(low)
    return low_meshes


def ensure_uv_layout(obj):
    if obj.type != "MESH":
        return
    if not obj.data.uv_layers:
        obj.data.uv_layers.new(name="UV_Main")
    try:
        set_active(obj)
        bpy.ops.object.mode_set(mode="EDIT")
        bpy.ops.mesh.select_all(action="SELECT")
        try:
            bpy.ops.uv.smart_project(angle_limit=1.1519, island_margin=0.03)
        except TypeError:
            bpy.ops.uv.smart_project()
    finally:
        try:
            bpy.ops.object.mode_set(mode="OBJECT")
        except Exception:
            pass


def create_texture_image(path, width, height, color, *, colorspace="sRGB"):
    ensure_parent(path)
    image = bpy.data.images.new(path.stem, width=width, height=height, alpha=True)
    image.generated_color = color
    image.filepath_raw = str(path)
    image.file_format = "PNG"
    try:
        image.colorspace_settings.name = colorspace
    except Exception:
        pass
    image.save()
    return image


def tint_color(color, amount):
    return tuple(max(0.0, min(1.0, component + amount)) for component in color[:3]) + (1.0,)


def create_procedural_texture_image(path, role, width, height):
    ensure_parent(path)
    image = bpy.data.images.new(path.stem, width=width, height=height, alpha=True)
    image.filepath_raw = str(path)
    image.file_format = "PNG"
    if role != "basecolor":
        try:
            image.colorspace_settings.name = "Non-Color"
        except Exception:
            pass
    primary = tuple(SPEC["palette"][0][:3])
    accent = tuple(SPEC["palette"][1][:3])
    trim = tuple(SPEC["palette"][2][:3])
    pixels = []
    for y in range(height):
        v = y / max(1, height - 1)
        for x in range(width):
            u = x / max(1, width - 1)
            checker = 0.03 if ((x // 48 + y // 48) % 2 == 0) else -0.022
            cloth_weave = (math.sin(u * 180.0) + math.sin(v * 220.0)) * 0.012
            panel_line = 0.075 if abs((u * 7.0) % 1.0 - 0.5) < 0.035 or abs((v * 9.0) % 1.0 - 0.5) < 0.03 else 0.0
            diagonal_trim = 0.055 if abs(((u + v) * 5.5) % 1.0 - 0.5) < 0.022 else 0.0
            edge_wear = 0.055 if min(u, v, 1.0 - u, 1.0 - v) < 0.035 else 0.0
            material_zone = int(u * 4.0) + int(v * 4.0) * 4
            if role == "basecolor":
                mix = 0.35 + 0.35 * v
                color = (
                    primary[0] * (1.0 - mix) + accent[0] * mix + checker + cloth_weave + panel_line + diagonal_trim + edge_wear,
                    primary[1] * (1.0 - mix) + accent[1] * mix + checker + cloth_weave + panel_line * 0.65 + diagonal_trim * 0.35 + edge_wear,
                    primary[2] * (1.0 - mix) + accent[2] * mix + checker + cloth_weave + panel_line * 0.45 + diagonal_trim * 0.25 + edge_wear,
                    1.0,
                )
            elif role == "normal":
                thread_x = math.sin(u * 260.0) * 0.018
                thread_y = math.sin(v * 240.0) * 0.018
                trim_raise = 0.04 if panel_line or diagonal_trim else 0.0
                color = (0.5 + (u - 0.5) * 0.035 + thread_x, 0.5 + (v - 0.5) * 0.035 + thread_y, 1.0 - trim_raise * 0.2, 1.0)
            elif role == "orm":
                occlusion = 0.92 - 0.18 * (1.0 - v)
                roughness = max(0.05, min(1.0, float(SPEC["roughness"]) + checker + cloth_weave))
                metallic = max(0.0, min(1.0, float(SPEC["metallic"]) + (0.18 if material_zone in (2, 5, 10, 13) else 0.0) + (0.12 if panel_line else 0.0)))
                color = (occlusion, roughness, metallic, 1.0)
            else:
                band = (material_zone + int(diagonal_trim > 0.0)) % 8
                swatches = [
                    (*primary, 1.0),
                    (*accent, 1.0),
                    (*trim, 1.0),
                    (0.08, 0.09, 0.12, 1.0),
                    (0.92, 0.73, 0.62, 1.0),
                    (0.05, 0.86, 0.78, 1.0),
                    (0.46, 0.06, 0.1, 1.0),
                    (0.12, 0.13, 0.18, 1.0),
                ]
                color = swatches[band]
            pixels.extend(max(0.0, min(1.0, value)) for value in color)
    image.pixels.foreach_set(pixels)
    image.update()
    image.save()
    return image


def create_production_texture_set():
    texture_size = 1024
    textures = {{
        "basecolor": create_procedural_texture_image(OUTPUTS["texture_basecolor"], "basecolor", texture_size, texture_size),
        "normal": create_procedural_texture_image(OUTPUTS["texture_normal"], "normal", texture_size, texture_size),
        "orm": create_procedural_texture_image(OUTPUTS["texture_orm"], "orm", texture_size, texture_size),
        "id": create_procedural_texture_image(OUTPUTS["texture_id"], "id", texture_size, texture_size),
    }}
    PIPELINE_STATE["textures"] = {{key: str(OUTPUTS["texture_" + key]) for key in ("basecolor", "normal", "orm", "id")}}
    PIPELINE_STATE["texture_manifest"] = {{
        key: {{
            "path": str(OUTPUTS["texture_" + key]),
            "width": image.size[0],
            "height": image.size[1],
            "colorspace": image.colorspace_settings.name,
            "role": key,
        }}
        for key, image in textures.items()
    }}
    PIPELINE_STATE["texture_authoring_manifest"] = {{
        "schema": "reverie.blender_texture_authoring_manifest.v1",
        "method": "deterministic_production_pbr_set",
        "asset_state": "generated_production_candidate",
        "resolution": [texture_size, texture_size],
        "maps": {{
            "basecolor": "palette gradient with panel masks, fabric weave, trim lines, and edge-wear readability detail",
            "normal": "neutral tangent normal map with fabric/thread micro variation and raised trim hints",
            "orm": "occlusion/roughness/metallic packed map for runtime PBR",
            "id": "material-ID swatches for deterministic mask selection across cloth, skin, metal, glow, and trim zones",
        }},
        "detail_features": ["panel_lines", "diagonal_trim", "cloth_weave", "edge_wear", "material_id_zones"],
        "replaceable_by_bake_or_paintover": True,
        "automated_art_scope": "lookdev-ready generated texture set; human art-direction approval is still required for final shipped key art",
        "notes": [
            "These maps are generated deterministically and wired into runtime materials as a production candidate.",
            "Bake cages and material IDs are available for optional high-to-low bake or hand-painted replacement passes.",
        ],
    }}
    return textures


def get_or_create_node(nodes, node_type, name):
    node = nodes.get(name)
    if node is None:
        node = nodes.new(node_type)
        node.name = name
        node.label = name
    return node


def material_role_from_name(name):
    lowered = name.lower()
    if "skin" in lowered or "porcelain" in lowered or "hand" in lowered:
        return "skin"
    if "hair" in lowered or "graphite" in lowered:
        return "hair"
    if "gold" in lowered or "trim" in lowered or "metal" in lowered:
        return "metal"
    if "cloth" in lowered or "jacket" in lowered or "cape" in lowered:
        return "cloth"
    if "glow" in lowered or "emissive" in lowered:
        return "glow"
    if "line" in lowered or "ink" in lowered or "dark" in lowered:
        return "line"
    if "soft" in lowered or "ivory" in lowered:
        return "soft"
    return "primary"


def role_tint(role, fallback):
    role_colors = {{
        "skin": (0.93, 0.72, 0.61, 1.0),
        "hair": (0.055, 0.052, 0.06, 1.0),
        "metal": (0.98, 0.72, 0.28, 1.0),
        "cloth": (0.66, 0.08, 0.16, 1.0),
        "glow": (0.22, 0.78, 1.0, 1.0),
        "line": (0.012, 0.014, 0.017, 1.0),
        "soft": (0.82, 0.78, 0.68, 1.0),
    }}
    return role_colors.get(role, fallback)


def configure_runtime_material(mat, textures, material_id):
    mat.use_nodes = True
    nodes = mat.node_tree.nodes
    links = mat.node_tree.links
    bsdf = nodes.get("Principled BSDF")
    if bsdf is None:
        return
    original_base = tuple(bsdf.inputs["Base Color"].default_value[:]) if "Base Color" in bsdf.inputs else (0.8, 0.8, 0.8, 1.0)
    role = material_role_from_name(mat.name)
    tint = role_tint(role, original_base)
    tex_base = get_or_create_node(nodes, "ShaderNodeTexImage", "rv_basecolor")
    tex_base.location = (-680, 180)
    tex_base.image = textures["basecolor"]
    tex_normal = get_or_create_node(nodes, "ShaderNodeTexImage", "rv_normal")
    tex_normal.location = (-680, -40)
    tex_normal.image = textures["normal"]
    tex_orm = get_or_create_node(nodes, "ShaderNodeTexImage", "rv_orm")
    tex_orm.location = (-680, -250)
    tex_orm.image = textures["orm"]
    normal_map = get_or_create_node(nodes, "ShaderNodeNormalMap", "rv_normal_map")
    normal_map.location = (-420, -40)
    try:
        tex_normal.image.colorspace_settings.name = "Non-Color"
        tex_orm.image.colorspace_settings.name = "Non-Color"
    except Exception:
        pass
    try:
        bsdf.inputs["Base Color"].default_value = tint
        if "Metallic" in bsdf.inputs:
            bsdf.inputs["Metallic"].default_value = 0.78 if role == "metal" else 0.0
        if "Roughness" in bsdf.inputs:
            bsdf.inputs["Roughness"].default_value = {{
                "skin": 0.55,
                "hair": 0.46,
                "metal": 0.26,
                "cloth": 0.68,
                "glow": 0.22,
                "line": 0.74,
            }}.get(role, float(SPEC["roughness"]))
        if role == "glow" and "Emission Color" in bsdf.inputs:
            bsdf.inputs["Emission Color"].default_value = tint
        if role == "glow" and "Emission Strength" in bsdf.inputs:
            bsdf.inputs["Emission Strength"].default_value = 1.8
    except Exception:
        pass
    try:
        if "Strength" in normal_map.inputs:
            normal_map.inputs["Strength"].default_value = {{
                "skin": 0.035,
                "soft": 0.04,
                "hair": 0.12,
                "metal": 0.18,
                "cloth": 0.22,
                "line": 0.06,
                "glow": 0.02,
            }}.get(role, 0.16)
        links.new(tex_normal.outputs["Color"], normal_map.inputs["Color"])
        links.new(normal_map.outputs["Normal"], bsdf.inputs["Normal"])
    except Exception:
        pass
    mat["reverie_material_id"] = material_id
    mat["reverie_material_role"] = role
    mat["reverie_texture_detail_overlay"] = "node_texture_set_available_without_flattening_role_color"


def clone_runtime_materials(meshes, textures):
    for obj in meshes:
        if obj.type != "MESH":
            continue
        for index, slot in enumerate(obj.material_slots):
            if slot.material is None:
                continue
            slot.material = slot.material.copy()
            configure_runtime_material(slot.material, textures, SPEC["slug"] + "::" + obj.name + "::" + str(index))


def tune_runtime_materials(meshes):
    manifest = {{}}
    for obj in meshes:
        if obj.type != "MESH":
            continue
        material_slots = []
        for index, slot in enumerate(obj.material_slots):
            mat = slot.material
            if mat is None:
                continue
            mat["reverie_pbr_workflow"] = "metallic_roughness"
            mat["reverie_shader_profile"] = "aaa_character_runtime"
            mat["reverie_texture_roles"] = ",".join(sorted(list(PIPELINE_STATE.get("textures", {{}}).keys())))
            mat["reverie_roughness_target"] = float(SPEC["roughness"])
            mat["reverie_metallic_target"] = float(SPEC["metallic"])
            material_slots.append({{
                "slot": index,
                "material": mat.name,
                "material_id": str(mat.get("reverie_material_id", "")),
                "workflow": "metallic_roughness",
                "material_role": str(mat.get("reverie_material_role", "")),
                "texture_detail_overlay": str(mat.get("reverie_texture_detail_overlay", "")),
                "basecolor_texture": PIPELINE_STATE.get("textures", {{}}).get("basecolor", ""),
                "normal_texture": PIPELINE_STATE.get("textures", {{}}).get("normal", ""),
                "orm_texture": PIPELINE_STATE.get("textures", {{}}).get("orm", ""),
            }})
        manifest[obj.name] = {{
            "mesh": obj.name,
            "material_slot_count": len(material_slots),
            "slots": material_slots,
            "lookdev_notes": [
                "Base role color is preserved per material so skin, hair, metal, cloth, linework, and glow remain visually separable.",
                "Generated basecolor, normal, and ORM maps remain available as runtime texture-detail overlays.",
                "Material IDs are stable and can be used by downstream bake or texture-painting passes.",
            ],
        }}
    PIPELINE_STATE["material_tuning"] = {{
        "workflow": "metallic_roughness",
        "shader_profile": "aaa_character_runtime",
        "texture_roles": sorted(list(PIPELINE_STATE.get("textures", {{}}).keys())),
        "meshes": manifest,
    }}
    return PIPELINE_STATE["material_tuning"]


def create_bake_cages(meshes, collection):
    cages = []
    manifest = {{}}
    for source in meshes:
        cage = duplicate_mesh_object(source, source.name + "_bake_cage")
        for modifier in list(cage.modifiers):
            cage.modifiers.remove(modifier)
        place_in_collection(cage, collection)
        cage.display_type = "WIRE"
        cage.hide_render = True
        cage.scale = tuple(component * 1.015 for component in cage.scale)
        cage["reverie_stage"] = "bake_cage"
        manifest[source.name] = {{
            "high_source": str(source.get("reverie_source_high", "")),
            "low_mesh": source.name,
            "cage": cage.name,
            "cage_scale_multiplier": 1.015,
            "maps": ["normal", "ambient_occlusion", "curvature", "material_id", "orm"],
        }}
        cages.append(cage)
    PIPELINE_STATE["bake_manifest"] = manifest
    return cages


def collect_mesh_metrics(high_meshes, low_meshes):
    def metrics(obj):
        return {{
            "vertices": len(obj.data.vertices) if obj.type == "MESH" else 0,
            "faces": len(obj.data.polygons) if obj.type == "MESH" else 0,
            "material_slots": len(obj.material_slots),
            "uv_layers": len(obj.data.uv_layers) if obj.type == "MESH" else 0,
            "modifiers": [modifier.type for modifier in obj.modifiers],
        }}

    high = {{obj.name: metrics(obj) for obj in high_meshes if obj.type == "MESH"}}
    low = {{obj.name: metrics(obj) for obj in low_meshes if obj.type == "MESH"}}
    PIPELINE_STATE["mesh_metrics"] = {{
        "high_poly": high,
        "retopo_low": low,
        "totals": {{
            "high_vertices": sum(item["vertices"] for item in high.values()),
            "high_faces": sum(item["faces"] for item in high.values()),
            "low_vertices": sum(item["vertices"] for item in low.values()),
            "low_faces": sum(item["faces"] for item in low.values()),
            "low_mesh_count": len(low),
        }},
    }}
    return PIPELINE_STATE["mesh_metrics"]


def create_humanoid_rig(collection):
    armature_data = bpy.data.armatures.new(SPEC["slug"] + "_rig_data")
    armature = bpy.data.objects.new(SPEC["slug"] + "_production_character_rig", armature_data)
    bpy.context.scene.collection.objects.link(armature)
    place_in_collection(armature, collection)
    set_active(armature)
    bpy.ops.object.mode_set(mode="EDIT")
    bones = {{}}

    def bone(name, head, tail, parent=None):
        edit_bone = armature_data.edit_bones.new(name)
        edit_bone.head = head
        edit_bone.tail = tail
        if parent:
            edit_bone.parent = bones[parent]
        bones[name] = edit_bone
        return edit_bone

    bone("root", (0.0, 0.0, 0.0), (0.0, 0.0, 0.22))
    bone("pelvis", (0.0, 0.0, 0.82), (0.0, 0.0, 1.03), "root")
    bone("spine", (0.0, 0.0, 1.03), (0.0, 0.0, 1.32), "pelvis")
    bone("chest", (0.0, 0.0, 1.32), (0.0, 0.0, 1.56), "spine")
    bone("neck", (0.0, 0.0, 1.56), (0.0, 0.0, 1.76), "chest")
    bone("head", (0.0, 0.0, 1.76), (0.0, 0.0, 2.05), "neck")
    for side_name, side in (("L", -1.0), ("R", 1.0)):
        shoulder = bone("shoulder." + side_name, (side * 0.12, 0.0, 1.5), (side * 0.32, 0.0, 1.48), "chest")
        upper_arm = bone("upper_arm." + side_name, shoulder.tail, (side * 0.58, 0.0, 1.16), "shoulder." + side_name)
        forearm = bone("forearm." + side_name, upper_arm.tail, (side * 0.78, -0.02, 0.86), "upper_arm." + side_name)
        bone("hand." + side_name, forearm.tail, (side * 0.92, -0.05, 0.7), "forearm." + side_name)
        thigh = bone("thigh." + side_name, (side * 0.12, 0.0, 0.82), (side * 0.16, 0.0, 0.44), "pelvis")
        shin = bone("shin." + side_name, thigh.tail, (side * 0.17, -0.02, 0.14), "thigh." + side_name)
        bone("foot." + side_name, shin.tail, (side * 0.22, -0.19, 0.04), "shin." + side_name)
    bpy.ops.object.mode_set(mode="OBJECT")
    armature.show_in_front = True
    PIPELINE_STATE["armature"] = armature.name
    return armature


def bind_meshes_to_rig(meshes, armature):
    try:
        bpy.ops.object.mode_set(mode="OBJECT")
    except Exception:
        pass
    bpy.ops.object.select_all(action="DESELECT")
    for obj in meshes:
        obj.select_set(True)
    armature.select_set(True)
    bpy.context.view_layer.objects.active = armature
    try:
        bpy.ops.object.parent_set(type="ARMATURE_AUTO")
        return True
    except Exception:
        for obj in meshes:
            add_modifier(obj, "ARMATURE", "rv_armature", object=armature)
        return False


def clear_pose(armature):
    for bone in armature.pose.bones:
        bone.rotation_mode = "XYZ"
        bone.rotation_euler = (0.0, 0.0, 0.0)
        bone.location = (0.0, 0.0, 0.0)


def key_pose(armature, frame, rotations, locations=None):
    locations = locations or {{}}
    for bone_name, rotation in rotations.items():
        bone = armature.pose.bones.get(bone_name)
        if bone is None:
            continue
        bone.rotation_mode = "XYZ"
        bone.rotation_euler = tuple(math.radians(value) for value in rotation)
        bone.keyframe_insert(data_path="rotation_euler", frame=frame)
    for bone_name, location in locations.items():
        bone = armature.pose.bones.get(bone_name)
        if bone is None:
            continue
        bone.location = location
        bone.keyframe_insert(data_path="location", frame=frame)


def stash_action(armature, action):
    armature.animation_data_create()
    track = armature.animation_data.nla_tracks.new()
    track.name = action.name
    track.mute = True
    track.strips.new(action.name, int(action.frame_range[0]), action)


def create_preview_actions(armature):
    armature.animation_data_create()
    actions = []
    for action_name, frames in (
        (
            SPEC["slug"] + "_character_idle_preview",
            [
                (1, {{"upper_arm.L": (-8, 2, -10), "upper_arm.R": (-6, -2, 12), "forearm.L": (-12, 0, 6), "forearm.R": (-10, 0, -8), "thigh.L": (2, 0, 3), "thigh.R": (-2, 0, -3)}}),
                (12, {{"upper_arm.L": (-2, 0, -6), "upper_arm.R": (-10, 0, 8), "forearm.L": (-20, 0, 4), "forearm.R": (-4, 0, -6), "head": (0, 3, 0)}}),
                (24, {{"upper_arm.L": (-8, 2, -10), "upper_arm.R": (-6, -2, 12), "forearm.L": (-12, 0, 6), "forearm.R": (-10, 0, -8), "thigh.L": (2, 0, 3), "thigh.R": (-2, 0, -3)}}),
            ],
        ),
        (
            SPEC["slug"] + "_character_attack_slash_preview",
            [
                (1, {{"upper_arm.R": (-18, -6, 18), "forearm.R": (-22, 0, 12), "upper_arm.L": (4, 0, -16), "forearm.L": (-10, 0, -8), "chest": (0, 0, 4)}}),
                (8, {{"upper_arm.R": (26, -8, -54), "forearm.R": (-52, 0, 18), "hand.R": (-12, 0, 20), "upper_arm.L": (-8, 0, 20), "chest": (0, 0, -18), "head": (0, -6, 0)}}),
                (16, {{"upper_arm.R": (-6, 2, 22), "forearm.R": (-16, 0, 10), "upper_arm.L": (-2, 0, -8), "chest": (0, 0, 6)}}),
            ],
        ),
    ):
        clear_pose(armature)
        action = bpy.data.actions.new(action_name)
        action.use_fake_user = True
        armature.animation_data.action = action
        for frame, rotations in frames:
            key_pose(armature, frame, rotations)
        stash_action(armature, action)
        actions.append(action)
    if actions:
        armature.animation_data.action = actions[0]
    PIPELINE_STATE["actions"] = [action.name for action in actions]
    return actions


def create_animation_manifest(armature, actions):
    clips = []
    for action in actions:
        start, end = action.frame_range
        name = action.name
        clips.append({{
            "name": name,
            "frame_start": int(start),
            "frame_end": int(end),
            "frame_count": int(end - start + 1),
            "loop": "idle" in name,
            "root_motion": False,
            "export_intent": "runtime_preview_action",
        }})
    manifest = {{
        "schema": "reverie.blender_animation_manifest.v1",
        "skeleton": armature.name if armature is not None else "",
        "clips": clips,
        "controls": list(PIPELINE_STATE.get("rig_controls", [])),
        "ik_targets": list(PIPELINE_STATE.get("ik_targets", [])),
        "ik_constraints": list(PIPELINE_STATE.get("ik_constraints", [])),
        "camera_action": PIPELINE_STATE.get("camera_action", ""),
    }}
    PIPELINE_STATE["animation_manifest"] = manifest
    return manifest


def create_pose_stress_action(armature):
    if armature is None or armature.pose is None:
        PIPELINE_STATE["pose_stress_report"] = {{}}
        return None
    clear_pose(armature)
    action = bpy.data.actions.new(SPEC["slug"] + "_skin_pose_stress_test")
    action.use_fake_user = True
    armature.animation_data_create()
    armature.animation_data.action = action
    frames = [
        (
            1,
            {{"upper_arm.L": (-52, 0, -48), "forearm.L": (-74, 0, 22), "upper_arm.R": (-50, 0, 48), "forearm.R": (-72, 0, -22), "thigh.L": (26, 0, 10), "shin.L": (-34, 0, 0), "thigh.R": (26, 0, -10), "shin.R": (-34, 0, 0), "chest": (0, 0, 8)}},
        ),
        (
            18,
            {{"upper_arm.L": (34, -12, 72), "forearm.L": (-38, 0, 26), "hand.L": (0, 0, 28), "upper_arm.R": (28, 10, -72), "forearm.R": (-36, 0, -26), "hand.R": (0, 0, -28), "thigh.L": (-18, 0, 14), "shin.L": (18, 0, 0), "thigh.R": (44, 0, -16), "shin.R": (-58, 0, 0), "head": (0, -8, 0)}},
        ),
        (
            36,
            {{"upper_arm.L": (-18, 24, -96), "forearm.L": (-64, 0, -34), "upper_arm.R": (-20, -24, 96), "forearm.R": (-62, 0, 34), "chest": (0, 0, -22), "spine": (0, 0, 14), "thigh.L": (58, 0, 8), "shin.L": (-76, 0, 0), "thigh.R": (58, 0, -8), "shin.R": (-76, 0, 0)}},
        ),
    ]
    for frame, rotations in frames:
        key_pose(armature, frame, rotations)
    stash_action(armature, action)
    existing = list(PIPELINE_STATE.get("actions", []))
    if action.name not in existing:
        existing.append(action.name)
    PIPELINE_STATE["actions"] = existing
    PIPELINE_STATE["pose_stress_report"] = {{
        "schema": "reverie.blender_pose_stress_report.v1",
        "action": action.name,
        "frames": [frame for frame, _rotations in frames],
        "stress_cases": ["cross_body_arms_crouch", "asymmetric_attack_reach", "deep_crouch_twist"],
        "checked_bones": sorted({{bone_name for _frame, rotations in frames for bone_name in rotations.keys()}}),
        "purpose": "Exercise shoulders, elbows, spine, hips, knees, and hands for generated skinning QA.",
    }}
    return action


def find_primary_face_mesh(meshes):
    for keyword in ("head", "face"):
        for obj in meshes:
            if obj.type == "MESH" and keyword in obj.name.lower():
                return obj
    return next((obj for obj in meshes if obj.type == "MESH"), None)


def create_expression_shape_keys(meshes):
    target = find_primary_face_mesh(meshes)
    if target is None or target.type != "MESH":
        PIPELINE_STATE["shape_keys"] = []
        PIPELINE_STATE["facial_manifest"] = {{}}
        return []
    names = []
    coords = [vertex.co.copy() for vertex in target.data.vertices]
    if not coords:
        PIPELINE_STATE["shape_keys"] = []
        PIPELINE_STATE["facial_manifest"] = {{}}
        return []
    min_x = min(coord.x for coord in coords)
    max_x = max(coord.x for coord in coords)
    min_z = min(coord.z for coord in coords)
    max_z = max(coord.z for coord in coords)
    center_x = (min_x + max_x) * 0.5
    center_z = (min_z + max_z) * 0.5
    width = max(0.001, max_x - min_x)
    height = max(0.001, max_z - min_z)

    def apply_delta(key, name):
        affected = 0
        for index, base in enumerate(coords):
            rel_x = (base.x - center_x) / width
            rel_z = (base.z - center_z) / height
            delta_x = 0.0
            delta_y = 0.0
            delta_z = 0.0
            if name == "blink_L" and rel_x < -0.03 and rel_z > 0.05:
                delta_z = -0.055 * (0.35 + min(1.0, abs(rel_x) * 2.0))
                affected += 1
            elif name == "blink_R" and rel_x > 0.03 and rel_z > 0.05:
                delta_z = -0.055 * (0.35 + min(1.0, abs(rel_x) * 2.0))
                affected += 1
            elif name == "smile_soft" and abs(rel_x) > 0.08 and rel_z < 0.05:
                delta_x = 0.025 if rel_x > 0 else -0.025
                delta_z = 0.035
                affected += 1
            elif name == "mouth_open" and abs(rel_x) < 0.18 and rel_z < -0.02:
                delta_y = -0.018
                delta_z = -0.075
                affected += 1
            if delta_x or delta_y or delta_z:
                key.data[index].co.x = base.x + delta_x
                key.data[index].co.y = base.y + delta_y
                key.data[index].co.z = base.z + delta_z
        return affected

    manifest = {{
        "schema": "reverie.blender_facial_manifest.v1",
        "face_mesh": target.name,
        "coordinate_space": "mesh_local",
        "shapes": {{}},
    }}
    if target.data.shape_keys is None or "Basis" not in target.data.shape_keys.key_blocks:
        target.shape_key_add(name="Basis", from_mix=False)
    for name in ("blink_L", "blink_R", "smile_soft", "mouth_open"):
        key = target.shape_key_add(name=name, from_mix=False)
        affected = apply_delta(key, name)
        key.value = 0.0
        names.append(key.name)
        manifest["shapes"][key.name] = {{
            "affected_vertices": affected,
            "non_destructive": True,
            "usage": "runtime facial expression target",
        }}
    target["reverie_face_mesh"] = True
    target["reverie_facial_shapes"] = ",".join(names)
    PIPELINE_STATE["shape_keys"] = names
    PIPELINE_STATE["facial_manifest"] = manifest
    return names


def create_bone_socket(armature, collection, name, bone_name, offset, *, display_type="ARROWS", size=0.09):
    if armature.pose is None or armature.pose.bones.get(bone_name) is None:
        return None
    socket = bpy.data.objects.new(name, None)
    bpy.context.scene.collection.objects.link(socket)
    place_in_collection(socket, collection)
    socket.empty_display_type = display_type
    socket.empty_display_size = size
    socket.parent = armature
    socket.parent_type = "BONE"
    socket.parent_bone = bone_name
    socket.location = offset
    socket.rotation_mode = "XYZ"
    return socket


def create_attachment_sockets(armature, collection):
    sockets = []
    for name, bone_name, offset in (
        (SPEC["slug"] + "_socket_weapon_r", "hand.R", (0.08, 0.0, 0.02)),
        (SPEC["slug"] + "_socket_weapon_l", "hand.L", (-0.08, 0.0, 0.02)),
        (SPEC["slug"] + "_socket_back", "chest", (0.0, 0.12, -0.04)),
        (SPEC["slug"] + "_socket_fx_head", "head", (0.0, 0.0, 0.18)),
        (SPEC["slug"] + "_socket_camera_target", "head", (0.0, -0.02, 0.06)),
    ):
        socket = create_bone_socket(armature, collection, name, bone_name, offset)
        if socket is not None:
            sockets.append(socket)
    PIPELINE_STATE["sockets"] = [socket.name for socket in sockets]
    return sockets


def ensure_vertex_group(obj, name):
    group = obj.vertex_groups.get(name)
    if group is None:
        group = obj.vertex_groups.new(name=name)
    return group


def assign_runtime_vertex_groups(meshes):
    summary = {{}}
    bone_names = (
        "root",
        "pelvis",
        "spine",
        "chest",
        "neck",
        "head",
        "upper_arm.L",
        "forearm.L",
        "hand.L",
        "upper_arm.R",
        "forearm.R",
        "hand.R",
        "thigh.L",
        "shin.L",
        "foot.L",
        "thigh.R",
        "shin.R",
        "foot.R",
    )
    for obj in meshes:
        if obj.type != "MESH":
            continue
        for name in bone_names:
            ensure_vertex_group(obj, name)
        for vertex in obj.data.vertices:
            world_z = (obj.matrix_world @ vertex.co).z
            if world_z > 1.68:
                targets = ("head", "neck")
            elif world_z > 1.2:
                targets = ("chest", "spine")
            elif world_z > 0.72:
                targets = ("spine", "pelvis")
            elif vertex.co.x < -0.08:
                targets = ("thigh.L", "shin.L", "foot.L")
            elif vertex.co.x > 0.08:
                targets = ("thigh.R", "shin.R", "foot.R")
            else:
                targets = ("root", "pelvis")
            for index, group_name in enumerate(targets):
                group = ensure_vertex_group(obj, group_name)
                group.add([vertex.index], 1.0 if index == 0 else 0.35, "ADD")
        obj["reverie_weighting_stage"] = "generated_weight_hints"
        summary[obj.name] = [group.name for group in obj.vertex_groups]
    PIPELINE_STATE["vertex_groups"] = summary
    return summary


def create_skinning_manifest(meshes, armature):
    deform_bones = []
    if armature is not None and getattr(armature, "data", None) is not None:
        deform_bones = [bone.name for bone in armature.data.bones if getattr(bone, "use_deform", True)]
        armature["reverie_skinning_profile"] = "generated_humanoid_four_influence"
    mesh_records = {{}}
    for obj in meshes:
        if obj.type != "MESH":
            continue
        groups = [group.name for group in obj.vertex_groups]
        mesh_records[obj.name] = {{
            "vertex_count": len(obj.data.vertices),
            "deform_group_count": len([name for name in groups if name in deform_bones]),
            "groups": groups,
            "max_influences": 4,
            "normalization": "zone_weighted_hint_pass",
            "bind_pose": "rest_pose",
        }}
    manifest = {{
        "schema": "reverie.blender_skinning_manifest.v1",
        "skeleton": armature.name if armature is not None else "",
        "deform_bones": deform_bones,
        "max_influences": 4,
        "weighting_method": "generated anatomical zone hints",
        "meshes": mesh_records,
    }}
    PIPELINE_STATE["skinning_manifest"] = manifest
    return manifest


def create_lod_variants(meshes, collection):
    lod_objects = []
    for source in meshes:
        if source.type != "MESH":
            continue
        for level, ratio in ((1, 0.55), (2, 0.28)):
            lod = duplicate_mesh_object(source, source.name + "_lod" + str(level))
            for modifier in list(lod.modifiers):
                lod.modifiers.remove(modifier)
            place_in_collection(lod, collection)
            decimate = add_modifier(lod, "DECIMATE", "rv_lod" + str(level) + "_density")
            if hasattr(decimate, "ratio"):
                decimate.ratio = ratio
            lod["reverie_stage"] = "runtime_lod"
            lod["reverie_lod_level"] = level
            lod["reverie_lod_source"] = source.name
            lod.hide_render = True
            lod_objects.append(lod)
    PIPELINE_STATE["lods"] = [obj.name for obj in lod_objects]
    return lod_objects


def create_rig_control_markers(armature, collection):
    controls = []
    for name, bone_name, offset, display_type, size in (
        (SPEC["slug"] + "_ctrl_head", "head", (0.0, 0.0, 0.22), "SPHERE", 0.12),
        (SPEC["slug"] + "_ctrl_chest", "chest", (0.0, 0.0, 0.18), "CUBE", 0.14),
        (SPEC["slug"] + "_ik_hand_L", "hand.L", (-0.16, -0.04, 0.0), "ARROWS", 0.12),
        (SPEC["slug"] + "_ik_hand_R", "hand.R", (0.16, -0.04, 0.0), "ARROWS", 0.12),
        (SPEC["slug"] + "_ik_foot_L", "foot.L", (-0.04, -0.08, -0.02), "PLAIN_AXES", 0.11),
        (SPEC["slug"] + "_ik_foot_R", "foot.R", (0.04, -0.08, -0.02), "PLAIN_AXES", 0.11),
    ):
        control = create_bone_socket(armature, collection, name, bone_name, offset, display_type=display_type, size=size)
        if control is not None:
            control["reverie_control_role"] = "animation_control"
            controls.append(control)
    PIPELINE_STATE["rig_controls"] = [obj.name for obj in controls]
    return controls


def create_ik_constraint_targets(armature, collection):
    if armature is None or armature.pose is None:
        PIPELINE_STATE["ik_targets"] = []
        PIPELINE_STATE["ik_constraints"] = []
        return []
    targets = []
    constraints = []
    specs = [
        ("hand_L", "forearm.L", (-0.82, -0.14, 0.7), 2),
        ("hand_R", "forearm.R", (0.82, -0.14, 0.7), 2),
        ("foot_L", "shin.L", (-0.22, -0.22, 0.04), 2),
        ("foot_R", "shin.R", (0.22, -0.22, 0.04), 2),
    ]
    for suffix, constrained_bone, loc, chain_count in specs:
        target = add_empty_marker(SPEC["slug"] + "_ik_target_" + suffix, loc, size=0.13, display_type="ARROWS")
        target.parent = armature
        target["reverie_control_role"] = "ik_target"
        place_in_collection(target, collection)
        targets.append(target)
        pose_bone = armature.pose.bones.get(constrained_bone)
        if pose_bone is None:
            continue
        constraint = pose_bone.constraints.new(type="IK")
        constraint.name = "rv_ik_" + suffix
        constraint.target = target
        constraint.chain_count = chain_count
        constraints.append({{
            "name": constraint.name,
            "bone": constrained_bone,
            "target": target.name,
            "chain_count": chain_count,
        }})
    PIPELINE_STATE["ik_targets"] = [obj.name for obj in targets]
    PIPELINE_STATE["ik_constraints"] = constraints
    return targets


def create_collision_proxies(m, collection):
    collision_mat = make_material("rv_collision_proxy_runtime", [0.05, 0.9, 0.45, 0.28], 0.0, 0.38)
    proxies = []
    specs = [
        ("ucx_" + SPEC["slug"] + "_body_capsule", "cylinder", (0.0, 0.02, 0.92), 0.34, 1.42, (0.0, 0.0, 0.0), "body"),
        ("ucx_" + SPEC["slug"] + "_head_sphere", "sphere", (0.0, -0.02, 1.82), 0.27, 0.0, (0.0, 0.0, 0.0), "head"),
        ("ucx_" + SPEC["slug"] + "_feet_box", "cube", (0.0, -0.05, 0.1), (0.55, 0.34, 0.12), 0.0, (0.0, 0.0, 0.0), "feet"),
        ("ucx_" + SPEC["slug"] + "_weapon_sweep", "cube", (0.9, -0.18, 1.08), (0.12, 0.16, 0.78), 0.0, (0.0, math.radians(-22), 0.0), "weapon"),
        ("ucx_" + SPEC["slug"] + "_interaction_capsule", "cylinder", (0.0, -0.02, 0.92), 0.46, 1.72, (0.0, 0.0, 0.0), "interaction"),
    ]
    for name, primitive, loc, size_a, size_b, rotation, role in specs:
        if primitive == "sphere":
            obj = sphere(name, loc, size_a, collision_mat, segments=16, ring_count=8)
        elif primitive == "cube":
            obj = cube(name, loc, size_a, collision_mat, bevel=0.0)
        else:
            obj = cylinder(name, loc, size_a, size_b, collision_mat, vertices=16, bevel=0.0)
        obj.rotation_euler = rotation
        obj.display_type = "WIRE"
        obj.hide_render = True
        obj["reverie_stage"] = "runtime_collision_proxy"
        obj["reverie_collision_role"] = role
        place_in_collection(obj, collection)
        proxies.append(obj)
    PIPELINE_STATE["collision_proxies"] = [obj.name for obj in proxies]
    return proxies


def quality_gate(gate_id, passed, detail):
    return {{"id": gate_id, "passed": bool(passed), "detail": detail}}


def create_art_readiness_report(low_meshes, high_meshes):
    texture_manifest = PIPELINE_STATE.get("texture_manifest", {{}})
    texture_roles = set(texture_manifest.keys()) if isinstance(texture_manifest, dict) else set()
    texture_authoring = PIPELINE_STATE.get("texture_authoring_manifest", {{}})
    facial_manifest = PIPELINE_STATE.get("facial_manifest", {{}})
    mesh_metrics = PIPELINE_STATE.get("mesh_metrics", {{}})
    totals = mesh_metrics.get("totals", {{}}) if isinstance(mesh_metrics, dict) else {{}}
    facial_deformation_count = sum(
        int(item.get("affected_vertices", 0) or 0)
        for item in (facial_manifest.get("shapes", {{}}) if isinstance(facial_manifest, dict) else {{}}).values()
        if isinstance(item, dict)
    )
    texture_resolution_ready = all(
        int(record.get("width", 0) or 0) >= 1024 and int(record.get("height", 0) or 0) >= 1024
        for record in texture_manifest.values()
        if isinstance(record, dict)
    )
    material_slot_count = sum(len(obj.material_slots) for obj in low_meshes if obj.type == "MESH")
    sculpt_modifier_count = sum(
        1
        for obj in high_meshes
        if obj.type == "MESH"
        for mod in obj.modifiers
        if mod.type in {{"MULTIRES", "BEVEL", "WEIGHTED_NORMAL", "CORRECTIVE_SMOOTH"}}
    )
    silhouette_pipeline_ready = (
        int(totals.get("high_vertices", 0) or 0) >= int(totals.get("low_vertices", 0) or 0) > 0
        and len(high_meshes) >= len(low_meshes) > 0
        and sculpt_modifier_count > 0
    )
    checks = [
        quality_gate("pbr_texture_roles", {{"basecolor", "normal", "orm", "id"}}.issubset(texture_roles), "Basecolor, normal, ORM, and material-ID maps are present."),
        quality_gate("texture_resolution", texture_resolution_ready and len(texture_roles) >= 4, "Generated texture maps meet the 1024px production-candidate floor."),
        quality_gate("material_assignment", material_slot_count >= len(low_meshes), "Runtime meshes carry material slots for lookdev review."),
        quality_gate("facial_target_evidence", len(PIPELINE_STATE.get("shape_keys", [])) >= 4 and facial_deformation_count > 0, "Facial targets include non-zero deformation evidence."),
        quality_gate("silhouette_complexity", silhouette_pipeline_ready, "High and runtime mesh metrics plus non-destructive sculpt modifiers show a sculpt-to-game silhouette pipeline."),
        quality_gate("runtime_lod_collision", len(PIPELINE_STATE.get("lods", [])) >= max(1, len(low_meshes)) * 2 and len(PIPELINE_STATE.get("collision_proxies", [])) >= 4, "LOD and collision evidence exists for runtime readability."),
    ]
    passed = all(bool(item.get("passed")) for item in checks)
    report = {{
        "schema": "reverie.blender_art_readiness_report.v1",
        "model_name": SPEC["model_name"],
        "asset_state": "generated_production_candidate" if passed else "needs_generation_repair",
        "automated_scope": "geometry, PBR texture roles, material coverage, facial deformation evidence, LOD/collision readiness",
        "human_art_director_review_required": True,
        "checks": checks,
        "passed": passed,
        "texture_authoring": texture_authoring,
        "facial_deformation_count": facial_deformation_count,
        "sculpt_modifier_count": sculpt_modifier_count,
        "mesh_metrics": mesh_metrics,
        "decision_notes": [
            "Automated checks can prove pipeline completeness and deformation/texture evidence.",
            "Final AAA art appeal, anatomy taste, material storytelling, and brand fit still require human art-direction approval.",
        ],
    }}
    PIPELINE_STATE["art_readiness_report"] = report
    return report


def validate_runtime_character_asset(low_meshes, armature):
    uv_ready = [obj.name for obj in low_meshes if obj.type == "MESH" and len(obj.data.uv_layers) > 0]
    material_ready = [
        obj.name
        for obj in low_meshes
        if obj.type == "MESH" and any(slot.material and slot.material.get("reverie_material_id") for slot in obj.material_slots)
    ]
    bake_cage_count = len(PIPELINE_STATE.get("bake_manifest", {{}}))
    texture_authoring_manifest = PIPELINE_STATE.get("texture_authoring_manifest", {{}})
    shape_key_count = len(PIPELINE_STATE.get("shape_keys", []))
    facial_manifest = PIPELINE_STATE.get("facial_manifest", {{}})
    material_tuning = PIPELINE_STATE.get("material_tuning", {{}})
    skinning_manifest = PIPELINE_STATE.get("skinning_manifest", {{}})
    animation_manifest = PIPELINE_STATE.get("animation_manifest", {{}})
    pose_stress_report = PIPELINE_STATE.get("pose_stress_report", {{}})
    art_readiness_report = PIPELINE_STATE.get("art_readiness_report", {{}})
    visual_qa_report = PIPELINE_STATE.get("visual_qa_report", {{}})
    engine_import_contract = PIPELINE_STATE.get("engine_import_contract", {{}})
    facial_deformation_count = sum(
        int(item.get("affected_vertices", 0) or 0)
        for item in (facial_manifest.get("shapes", {{}}) if isinstance(facial_manifest, dict) else {{}}).values()
        if isinstance(item, dict)
    )
    material_tuning_mesh_count = len(material_tuning.get("meshes", {{}})) if isinstance(material_tuning, dict) else 0
    skinning_manifest_mesh_count = len(skinning_manifest.get("meshes", {{}})) if isinstance(skinning_manifest, dict) else 0
    animation_clip_count = len(animation_manifest.get("clips", [])) if isinstance(animation_manifest, dict) else 0
    ik_constraint_count = len(PIPELINE_STATE.get("ik_constraints", []))
    pose_stress_frame_count = len(pose_stress_report.get("frames", [])) if isinstance(pose_stress_report, dict) else 0
    mesh_metrics = PIPELINE_STATE.get("mesh_metrics", {{}})
    totals = mesh_metrics.get("totals", {{}}) if isinstance(mesh_metrics, dict) else {{}}
    validation = {{
        "low_mesh_count": len(low_meshes),
        "has_armature": armature is not None,
        "action_count": len(PIPELINE_STATE.get("actions", [])),
        "texture_count": len(PIPELINE_STATE.get("textures", {{}})),
        "lod_count": len(PIPELINE_STATE.get("lods", [])),
        "socket_count": len(PIPELINE_STATE.get("sockets", [])),
        "control_count": len(PIPELINE_STATE.get("rig_controls", [])),
        "collision_proxy_count": len(PIPELINE_STATE.get("collision_proxies", [])),
        "weighted_mesh_count": len(PIPELINE_STATE.get("vertex_groups", {{}})),
        "uv_ready_mesh_count": len(uv_ready),
        "material_id_mesh_count": len(material_ready),
        "bake_cage_count": bake_cage_count,
        "texture_authoring_passed": bool(texture_authoring_manifest.get("schema") == "reverie.blender_texture_authoring_manifest.v1") if isinstance(texture_authoring_manifest, dict) else False,
        "shape_key_count": shape_key_count,
        "facial_deformation_count": facial_deformation_count,
        "material_tuning_mesh_count": material_tuning_mesh_count,
        "skinning_manifest_mesh_count": skinning_manifest_mesh_count,
        "animation_clip_count": animation_clip_count,
        "ik_constraint_count": ik_constraint_count,
        "pose_stress_frame_count": pose_stress_frame_count,
        "art_readiness_passed": bool(art_readiness_report.get("passed")) if isinstance(art_readiness_report, dict) else False,
        "visual_qa_passed": bool(visual_qa_report.get("passed")) if isinstance(visual_qa_report, dict) else False,
        "engine_import_contract_passed": bool(engine_import_contract.get("passed")) if isinstance(engine_import_contract, dict) else False,
        "low_vertices": int(totals.get("low_vertices", 0) or 0),
        "low_faces": int(totals.get("low_faces", 0) or 0),
        "high_vertices": int(totals.get("high_vertices", 0) or 0),
        "high_faces": int(totals.get("high_faces", 0) or 0),
    }}
    gates = [
        quality_gate("retopo_low_meshes", validation["low_mesh_count"] > 0, "Retopo/game mesh collection contains exportable meshes."),
        quality_gate("uv_unwrapped", validation["uv_ready_mesh_count"] == validation["low_mesh_count"], "Every runtime mesh has a UV layer."),
        quality_gate("texture_set", validation["texture_count"] >= 4, "Basecolor, normal, ORM, and ID texture files are authored."),
        quality_gate("procedural_texture_authoring", validation["texture_authoring_passed"], "Texture maps include a procedural authoring manifest."),
        quality_gate("material_ids", validation["material_id_mesh_count"] == validation["low_mesh_count"], "Runtime materials carry deterministic Reverie material IDs."),
        quality_gate("bake_cages", validation["bake_cage_count"] == validation["low_mesh_count"], "Each low mesh has a high-to-low bake cage entry."),
        quality_gate("material_tuning", validation["material_tuning_mesh_count"] == validation["low_mesh_count"], "Every runtime mesh has a PBR tuning manifest."),
        quality_gate("armature", validation["has_armature"], "A humanoid armature exists for skinning and animation."),
        quality_gate("weights", validation["weighted_mesh_count"] == validation["low_mesh_count"], "Every runtime mesh has generated vertex-group weight hints."),
        quality_gate("skinning_manifest", validation["skinning_manifest_mesh_count"] == validation["low_mesh_count"], "Every runtime mesh has a skinning contract."),
        quality_gate("actions", validation["action_count"] >= 2, "Idle and attack preview actions are stored."),
        quality_gate("animation_manifest", validation["animation_clip_count"] >= 2, "Animation clips are described in a runtime manifest."),
        quality_gate("face_keys", validation["shape_key_count"] >= 4, "Face expression shape keys exist."),
        quality_gate("facial_deformation", validation["facial_deformation_count"] > 0, "Expression shape keys contain non-zero vertex deformation data."),
        quality_gate("pose_stress", validation["pose_stress_frame_count"] >= 3, "A skinning stress-test action covers extreme poses."),
        quality_gate("art_readiness_report", validation["art_readiness_passed"], "Automated art-readiness checks passed for generated production-candidate evidence."),
        quality_gate("sockets", validation["socket_count"] >= 5, "Gameplay attachment/camera sockets exist."),
        quality_gate("rig_controls", validation["control_count"] >= 6, "Animation control markers exist."),
        quality_gate("ik_constraints", validation["ik_constraint_count"] >= 4, "IK target constraints exist for hands and feet."),
        quality_gate("collision_proxies", validation["collision_proxy_count"] >= 4, "Runtime body, head, feet, weapon, and interaction collision proxies exist."),
        quality_gate("lods", validation["lod_count"] >= validation["low_mesh_count"] * 2, "Two LOD variants exist per runtime mesh."),
        quality_gate("visual_qa_report", validation["visual_qa_passed"], "Visual QA report passed automated contract checks."),
        quality_gate("engine_import_contract", validation["engine_import_contract_passed"], "Runtime engine import contract is complete."),
        quality_gate("mesh_budget", validation["low_vertices"] > 0 and validation["low_faces"] > 0, "Runtime mesh budget metrics were collected."),
    ]
    validation["passed"] = bool(
        validation["low_mesh_count"] > 0
        and all(gate["passed"] for gate in gates)
    )
    validation["score"] = round(sum(1 for gate in gates if gate["passed"]) / max(1, len(gates)) * 100, 2)
    validation["failed_gates"] = [gate["id"] for gate in gates if not gate["passed"]]
    PIPELINE_STATE["quality_gates"] = gates
    PIPELINE_STATE["validation"] = validation
    return validation


def create_production_manifest(low_meshes, high_meshes, armature):
    validation = PIPELINE_STATE.get("validation", {{}})
    stages = [
        ("high_poly_sculpt", len(high_meshes), "high_poly", "Generated sculpt-support meshes with multires/corrective smooth modifiers."),
        ("retopo_low", len(low_meshes), "retopo_low", "Generated runtime meshes from high-poly sources with decimation and shrinkwrap surface following."),
        ("uv_layout", int(validation.get("uv_ready_mesh_count", 0) or 0), "uv", "Smart UV projection was run for every runtime mesh."),
        ("texture_bake_targets", len(PIPELINE_STATE.get("bake_manifest", {{}})), "bake", "Bake cages and map intents are registered for normal, AO, curvature, material ID, and ORM outputs."),
        ("procedural_textures", 1 if PIPELINE_STATE.get("texture_authoring_manifest", {{}}) else 0, "texture", "Generated basecolor, normal, ORM, and material-ID texture seed maps with authoring metadata."),
        ("material_tuning", len(PIPELINE_STATE.get("material_tuning", {{}}).get("meshes", {{}})), "lookdev", "Runtime PBR material graphs and material IDs are assigned."),
        ("skinning", len(PIPELINE_STATE.get("skinning_manifest", {{}}).get("meshes", {{}})), "rig", "Vertex groups and skinning manifest are generated for the humanoid skeleton."),
        ("animation", len(PIPELINE_STATE.get("animation_manifest", {{}}).get("clips", [])), "animation", "Idle and attack preview clips are authored and stored as actions."),
        ("face_shapes", len(PIPELINE_STATE.get("shape_keys", [])), "facial", "Face expression shape keys are authored with named runtime targets for downstream facial animation."),
        ("facial_deformation", len(PIPELINE_STATE.get("facial_manifest", {{}}).get("shapes", {{}})), "facial", "Expression shape keys contain non-zero vertex deformation evidence."),
        ("pose_stress", len(PIPELINE_STATE.get("pose_stress_report", {{}}).get("frames", [])), "rig", "Extreme pose action exists for skinning and deformation stress checks."),
        ("sockets", len(PIPELINE_STATE.get("sockets", [])), "runtime", "Gameplay attachment and camera sockets are parented to bones."),
        ("ik_controls", len(PIPELINE_STATE.get("ik_constraints", [])), "animation", "IK target controls and constraints are available for limbs."),
        ("lods", len(PIPELINE_STATE.get("lods", [])), "runtime", "Runtime LOD variants are generated for each game mesh."),
        ("collision", len(PIPELINE_STATE.get("collision_proxies", [])), "runtime", "Runtime collision proxies are generated for body, head, feet, weapon, and interaction volumes."),
        ("art_readiness", 1 if PIPELINE_STATE.get("art_readiness_report", {{}}).get("passed") else 0, "qa", "Automated art-readiness evidence covers textures, material assignment, facial deformation, silhouette metrics, LODs, and collision."),
        ("visual_qa", 1 if PIPELINE_STATE.get("visual_qa_report", {{}}) else 0, "qa", "Automated visual QA contract is generated for turntable review and silhouette checks."),
        ("engine_import", 1 if PIPELINE_STATE.get("engine_import_contract", {{}}) else 0, "runtime", "Engine import contract maps skeleton, animation clips, sockets, collisions, textures, and LOD policy."),
    ]
    stage_records = [
        {{
            "id": stage_id,
            "discipline": discipline,
            "status": "passed" if count > 0 else "missing",
            "evidence_count": count,
            "detail": detail,
        }}
        for stage_id, count, discipline, detail in stages
    ]
    manifest = {{
        "schema": "reverie.blender_production_manifest.v1",
        "model_name": SPEC["model_name"],
        "slug": SPEC["slug"],
        "preset": SPEC["preset"],
        "pipeline_state": "complete" if all(stage["status"] == "passed" for stage in stage_records) else "incomplete",
        "stages": stage_records,
        "runtime_acceptance": {{
            "export_format": SPEC["export_format"],
            "source_blend": str(OUTPUTS["blend"]),
            "runtime_export": str(OUTPUTS["runtime"]),
            "validation_score": validation.get("score", 0),
            "failed_gates": validation.get("failed_gates", []),
        }},
        "deliverables": {{
            "high_poly": [obj.name for obj in high_meshes],
            "runtime_meshes": [obj.name for obj in low_meshes],
            "armature": armature.name if armature is not None else "",
            "textures": PIPELINE_STATE.get("textures", {{}}),
            "texture_authoring_manifest": PIPELINE_STATE.get("texture_authoring_manifest", {{}}),
            "bake_manifest": PIPELINE_STATE.get("bake_manifest", {{}}),
            "material_tuning": PIPELINE_STATE.get("material_tuning", {{}}),
            "skinning_manifest": PIPELINE_STATE.get("skinning_manifest", {{}}),
            "animation_manifest": PIPELINE_STATE.get("animation_manifest", {{}}),
            "facial_manifest": PIPELINE_STATE.get("facial_manifest", {{}}),
            "pose_stress_report": PIPELINE_STATE.get("pose_stress_report", {{}}),
            "art_readiness_report": PIPELINE_STATE.get("art_readiness_report", {{}}),
            "visual_qa_report": PIPELINE_STATE.get("visual_qa_report", {{}}),
            "engine_import_contract": PIPELINE_STATE.get("engine_import_contract", {{}}),
            "iteration_plan": PIPELINE_STATE.get("iteration_plan", {{}}),
            "collision_proxies": PIPELINE_STATE.get("collision_proxies", []),
            "lods": PIPELINE_STATE.get("lods", []),
        }},
    }}
    PIPELINE_STATE["production_manifest"] = manifest
    return manifest


def create_blackbox_iteration_plan():
    validation = PIPELINE_STATE.get("validation", {{}})
    quality_gates = PIPELINE_STATE.get("quality_gates", [])
    if not isinstance(quality_gates, list):
        quality_gates = []
    production_manifest = PIPELINE_STATE.get("production_manifest", {{}})
    stages = production_manifest.get("stages", []) if isinstance(production_manifest, dict) else []
    if not isinstance(stages, list):
        stages = []

    failed_gate_ids = [
        str(gate.get("id", "")).strip()
        for gate in quality_gates
        if isinstance(gate, dict) and not bool(gate.get("passed"))
    ]
    missing_stage_ids = [
        str(stage.get("id", "")).strip()
        for stage in stages
        if isinstance(stage, dict) and stage.get("status") != "passed"
    ]
    failed_gate_ids = [item for item in failed_gate_ids if item]
    missing_stage_ids = [item for item in missing_stage_ids if item]

    repair_catalog = {{
        "high_poly_sculpt": "Regenerate sculpt-support meshes and reapply non-destructive detail modifiers.",
        "retopo_low": "Regenerate runtime meshes from high-poly sources and re-run shrinkwrap/decimation.",
        "uv_layout": "Re-run UV projection on all runtime meshes and verify UV layers are present.",
        "texture_set": "Regenerate basecolor, normal, ORM, and material-ID seed maps.",
        "procedural_texture_authoring": "Regenerate procedural texture authoring metadata and reconnect material texture roles.",
        "material_ids": "Reassign deterministic Reverie material IDs to every runtime material.",
        "bake_cages": "Rebuild high-to-low bake cages and bake intent manifests.",
        "material_tuning": "Rebuild PBR material node tuning and material manifests.",
        "armature": "Recreate the humanoid armature and parent runtime meshes.",
        "weights": "Regenerate vertex groups and weight hints for every runtime mesh.",
        "skinning_manifest": "Rebuild the skinning contract for all weighted meshes.",
        "actions": "Recreate idle and attack preview actions.",
        "animation_manifest": "Rebuild runtime animation clip metadata.",
        "face_keys": "Regenerate facial expression shape keys.",
        "facial_deformation": "Apply non-zero vertex offsets to expression shape keys.",
        "pose_stress": "Recreate the pose-stress action for deformation checks.",
        "art_readiness_report": "Rebuild automated art-readiness evidence for texture roles, material coverage, facial deformation, silhouette metrics, LODs, and collision.",
        "sockets": "Recreate gameplay sockets and bone parenting.",
        "rig_controls": "Regenerate visible rig control markers.",
        "ik_constraints": "Rebuild IK targets and limb constraints.",
        "collision_proxies": "Regenerate runtime collision proxy volumes.",
        "lods": "Regenerate LOD1 and LOD2 variants for each runtime mesh.",
        "visual_qa_report": "Rebuild visual QA checks and turntable review contract.",
        "engine_import_contract": "Rebuild engine import contract for skeleton, clips, sockets, textures, collision, and LODs.",
        "mesh_budget": "Recollect runtime mesh metrics and verify budget evidence.",
    }}

    repair_queue = []
    for gate_id in failed_gate_ids:
        repair_queue.append({{
            "source": "quality_gate",
            "id": gate_id,
            "action": repair_catalog.get(gate_id, "Inspect generated assets, repair the failed quality gate, then rerun validation."),
            "verification": "Run the generated Blender script again, then run `audit_model` / post-run audit.",
        }})
    for stage_id in missing_stage_ids:
        repair_queue.append({{
            "source": "production_stage",
            "id": stage_id,
            "action": repair_catalog.get(stage_id, "Regenerate the missing production-stage evidence and rerun validation."),
            "verification": "Confirm production manifest stage status is `passed`.",
        }})

    ready = bool(validation.get("passed")) and not failed_gate_ids and not missing_stage_ids
    plan = {{
        "schema": "reverie.blender_blackbox_iteration_plan.v1",
        "model_name": SPEC["model_name"],
        "slug": SPEC["slug"],
        "preset": SPEC["preset"],
        "state": "ready" if ready else "continue",
        "completion_policy": "continue automatically until validation, production stages, visual QA, engine import, and post-run audit gates are ready",
        "blocking_decisions": [],
        "failed_gate_ids": failed_gate_ids,
        "missing_stage_ids": missing_stage_ids,
        "automatic_repair_queue": repair_queue,
        "next_polish_backlog": [
            "Optionally replace generated production-candidate texture maps with approved hand-painted or baked finals after art-direction review.",
            "Run native downstream engine import and animation retarget checks when the selected target runtime is installed.",
            "Capture human art-direction notes for silhouette, anatomy, material storytelling, and facial appeal after generated QA passes.",
        ],
        "verification": {{
            "validation_passed": bool(validation.get("passed")),
            "validation_score": validation.get("score", 0),
            "quality_gate_count": len(quality_gates),
            "production_stage_count": len(stages),
        }},
    }}
    PIPELINE_STATE["iteration_plan"] = plan
    return plan


def create_visual_qa_report(low_meshes, armature, collections=None):
    collections = collections or {{}}
    mesh_metrics = PIPELINE_STATE.get("mesh_metrics", {{}})
    totals = mesh_metrics.get("totals", {{}}) if isinstance(mesh_metrics, dict) else {{}}
    art_readiness = PIPELINE_STATE.get("art_readiness_report", {{}})
    low_names = [obj.name.lower() for obj in low_meshes if obj.type == "MESH"]
    face_landmarks = {{
        "eye_white_sclera": any("eye_white_sclera" in name for name in low_names),
        "iris_catchlight": any("iris_catchlight" in name for name in low_names),
        "brow_expression": any("brow_expression" in name for name in low_names),
        "nose_soft_plane": any("nose_soft_plane" in name for name in low_names),
        "mouth_shadow_curve": any("mouth_shadow_curve" in name for name in low_names),
        "ear_anatomy": any("ear_anatomy" in name for name in low_names),
    }}
    material_roles = set()
    material_tuning = PIPELINE_STATE.get("material_tuning", {{}})
    if isinstance(material_tuning, dict):
        for mesh in material_tuning.get("meshes", {{}}).values():
            if not isinstance(mesh, dict):
                continue
            for slot in mesh.get("slots", []):
                if isinstance(slot, dict) and slot.get("material_role"):
                    material_roles.add(str(slot.get("material_role")))
    helper_objects = []
    for helper_name in ("rig", "preview", "collision"):
        helper_collection = collections.get(helper_name) if isinstance(collections, dict) else None
        if helper_collection is not None:
            helper_objects.extend([obj for obj in helper_collection.objects])
    report = {{
        "schema": "reverie.blender_visual_qa_report.v1",
        "model_name": SPEC["model_name"],
        "review_views": [
            {{"id": "front", "camera": [0.0, -5.2, 2.6], "target": [0.0, 0.0, 1.05]}},
            {{"id": "side", "camera": [5.2, 0.0, 2.6], "target": [0.0, 0.0, 1.05]}},
            {{"id": "three_quarter", "camera": [3.4, -4.8, 3.0], "target": [0.0, 0.0, 1.05]}},
        ],
        "checks": [
            {{"id": "silhouette_readability", "passed": len(low_meshes) > 0, "detail": "Runtime meshes exist for silhouette review."}},
            {{"id": "face_targets", "passed": len(PIPELINE_STATE.get("shape_keys", [])) >= 4, "detail": "Facial targets are present for expression review."}},
            {{"id": "facial_landmark_visibility", "passed": all(face_landmarks.values()), "detail": "Eyes, iris highlights, brows, nose, mouth, and ears exist as visible runtime mesh landmarks."}},
            {{"id": "material_slots", "passed": all(len(obj.material_slots) > 0 for obj in low_meshes if obj.type == "MESH"), "detail": "Every runtime mesh has material slots."}},
            {{"id": "material_role_coverage", "passed": {{"skin", "hair", "metal", "cloth"}}.issubset(material_roles), "detail": "Skin, hair, metal, and cloth material roles are present for lookdev separation."}},
            {{"id": "art_readiness", "passed": bool(art_readiness.get("passed")) if isinstance(art_readiness, dict) else False, "detail": "Generated art-readiness evidence passed automated checks."}},
            {{"id": "collision_visibility", "passed": len(PIPELINE_STATE.get("collision_proxies", [])) >= 4, "detail": "Runtime collision volumes are authored and hidden from render."}},
            {{"id": "render_helper_exclusion", "passed": bool(helper_objects) and all(bool(getattr(obj, "hide_render", False)) for obj in helper_objects), "detail": "Rig, preview, and collision helper objects are excluded from production preview renders."}},
            {{"id": "mesh_budget_known", "passed": int(totals.get("low_vertices", 0) or 0) > 0, "detail": "Mesh budget metrics exist for QA review."}},
            {{"id": "character_detail_floor", "passed": int(totals.get("low_vertices", 0) or 0) >= 5000 and len(low_meshes) >= 60, "detail": "Runtime character has enough authored mesh density and part coverage for a stylized production candidate."}},
        ],
        "render_contract": {{
            "preview_path": str(OUTPUTS.get("preview", "")),
            "turntable_action": PIPELINE_STATE.get("camera_action", ""),
            "resolution": [1280, 1280],
            "engine": "EEVEE/EEVEE_NEXT",
        }},
        "manual_review_prompts": [
            "Check silhouette readability at thumbnail size.",
            "Check shoulder, elbow, hip, knee, and spine deformation using the skin stress action.",
            "Check facial shape keys for asymmetry, eye closure, smile lift, and mouth-open deformation.",
            "Check material ID regions, generated texture detail, and whether hand-painted/baked finals are needed.",
        ],
        "art_readiness_report": art_readiness,
        "face_landmarks": face_landmarks,
        "material_roles": sorted(material_roles),
    }}
    report["passed"] = all(bool(item.get("passed")) for item in report["checks"])
    PIPELINE_STATE["visual_qa_report"] = report
    return report


def create_engine_import_contract(low_meshes, armature):
    animation_clips = PIPELINE_STATE.get("animation_manifest", {{}}).get("clips", [])
    humanoid_bone_map = {{
        "hips": "root",
        "spine": "spine",
        "head": "head",
        "left_upper_arm": "upper_arm.L",
        "left_lower_arm": "forearm.L",
        "right_upper_arm": "upper_arm.R",
        "right_lower_arm": "forearm.R",
        "left_upper_leg": "thigh.L",
        "left_lower_leg": "shin.L",
        "right_upper_leg": "thigh.R",
        "right_lower_leg": "shin.R",
    }}
    import_checks = [
        {{"id": "runtime_export_declared", "passed": bool(str(OUTPUTS["runtime"])), "detail": "Runtime export path is declared."}},
        {{"id": "skeleton_declared", "passed": armature is not None, "detail": "Humanoid skeleton is declared for import."}},
        {{"id": "animation_clips_declared", "passed": len(animation_clips) >= 2, "detail": "At least two animation clips are declared."}},
        {{"id": "retarget_map_declared", "passed": len(humanoid_bone_map) >= 10, "detail": "Humanoid retarget bone map is available."}},
        {{"id": "socket_collision_lod_declared", "passed": len(PIPELINE_STATE.get("sockets", [])) >= 5 and len(PIPELINE_STATE.get("collision_proxies", [])) >= 4 and len(PIPELINE_STATE.get("lods", [])) >= max(1, len(low_meshes)) * 2, "detail": "Sockets, collision proxies, and LOD variants are declared."}},
        {{"id": "texture_roles_declared", "passed": {{"basecolor", "normal", "orm", "id"}}.issubset(set(PIPELINE_STATE.get("textures", {{}}).keys())), "detail": "Runtime texture roles are declared."}},
    ]
    contract = {{
        "schema": "reverie.engine_import_contract.v1",
        "model_name": SPEC["model_name"],
        "source_format": "blend",
        "runtime_format": SPEC["export_format"],
        "runtime_export": str(OUTPUTS["runtime"]),
        "skeleton": armature.name if armature is not None else "",
        "runtime_meshes": [obj.name for obj in low_meshes],
        "texture_set": PIPELINE_STATE.get("textures", {{}}),
        "material_workflow": PIPELINE_STATE.get("material_tuning", {{}}).get("workflow", "metallic_roughness"),
        "animation_clips": animation_clips,
        "pose_stress_action": PIPELINE_STATE.get("pose_stress_report", {{}}).get("action", ""),
        "facial_targets": PIPELINE_STATE.get("shape_keys", []),
        "sockets": PIPELINE_STATE.get("sockets", []),
        "collision_proxies": PIPELINE_STATE.get("collision_proxies", []),
        "lod_policy": {{
            "variants": PIPELINE_STATE.get("lods", []),
            "strategy": "source_game_mesh_plus_decimated_lod1_lod2",
        }},
        "import_checks": [
            "Load runtime export.",
            "Verify skeleton hierarchy and animation clips.",
            "Bind sockets to gameplay equipment, camera, and VFX systems.",
            "Register collision proxies as runtime-only physics helpers.",
            "Apply texture set and material workflow.",
            "Verify LOD switching policy.",
        ],
        "artifact_import_validation": {{
            "schema": "reverie.engine_import_artifact_validation.v1",
            "validation_mode": "blender_export_contract",
            "checks": import_checks,
            "passed": all(bool(item.get("passed")) for item in import_checks),
        }},
        "retarget_profile": {{
            "schema": "reverie.animation_retarget_profile.v1",
            "source_skeleton": armature.name if armature is not None else "",
            "target_rig": "humanoid",
            "bone_map": humanoid_bone_map,
            "required_clips": [str(item.get("id", item)) if isinstance(item, dict) else str(item) for item in animation_clips],
            "facial_targets": PIPELINE_STATE.get("shape_keys", []),
        }},
        "target_runtime_execution": {{
            "status": "artifact_validated",
            "native_runtime_required_for_final": True,
            "detail": "Blender verified export contract and retarget metadata; native engine import is handled by the selected runtime adapter when that runtime is installed.",
        }},
    }}
    contract["passed"] = bool(contract["runtime_meshes"] and contract["skeleton"] and len(contract["animation_clips"]) >= 2 and contract["artifact_import_validation"]["passed"])
    PIPELINE_STATE["engine_import_contract"] = contract
    return contract


def create_runtime_asset_card(low_meshes, armature):
    card = {{
        "schema": "reverie.blender_production_asset_card.v1",
        "model_name": SPEC["model_name"],
        "slug": SPEC["slug"],
        "preset": SPEC["preset"],
        "style": SPEC["style"],
        "source_of_truth": "Generated .blend plus auditable bpy authoring script",
        "runtime_contract": {{
            "format": SPEC["export_format"],
            "export_objects": [obj.name for obj in low_meshes] + ([armature.name] if armature is not None else []),
            "texture_roles": sorted(list(PIPELINE_STATE.get("textures", {{}}).keys())),
            "skeleton": armature.name if armature is not None else "",
            "actions": list(PIPELINE_STATE.get("actions", [])),
            "animation_clips": list(PIPELINE_STATE.get("animation_manifest", {{}}).get("clips", [])),
            "sockets": list(PIPELINE_STATE.get("sockets", [])),
            "ik_targets": list(PIPELINE_STATE.get("ik_targets", [])),
            "ik_constraints": list(PIPELINE_STATE.get("ik_constraints", [])),
            "collision_proxies": list(PIPELINE_STATE.get("collision_proxies", [])),
            "lods": list(PIPELINE_STATE.get("lods", [])),
        }},
        "artist_review_notes": [
            "Generated asset includes high/low collections, bake cages, UVs, material IDs, rig, weights, actions, sockets, LODs, and validation gates.",
            "Automated art-readiness can prove generated production-candidate evidence; final shipped art appeal still needs human art-direction approval.",
        ],
        "quality": PIPELINE_STATE.get("validation", {{}}),
        "quality_gates": PIPELINE_STATE.get("quality_gates", []),
        "mesh_metrics": PIPELINE_STATE.get("mesh_metrics", {{}}),
        "texture_manifest": PIPELINE_STATE.get("texture_manifest", {{}}),
        "texture_authoring_manifest": PIPELINE_STATE.get("texture_authoring_manifest", {{}}),
        "material_tuning": PIPELINE_STATE.get("material_tuning", {{}}),
        "bake_manifest": PIPELINE_STATE.get("bake_manifest", {{}}),
        "skinning_manifest": PIPELINE_STATE.get("skinning_manifest", {{}}),
        "animation_manifest": PIPELINE_STATE.get("animation_manifest", {{}}),
        "facial_manifest": PIPELINE_STATE.get("facial_manifest", {{}}),
        "pose_stress_report": PIPELINE_STATE.get("pose_stress_report", {{}}),
        "art_readiness_report": PIPELINE_STATE.get("art_readiness_report", {{}}),
        "visual_qa_report": PIPELINE_STATE.get("visual_qa_report", {{}}),
        "engine_import_contract": PIPELINE_STATE.get("engine_import_contract", {{}}),
        "production_manifest": PIPELINE_STATE.get("production_manifest", {{}}),
        "iteration_plan": PIPELINE_STATE.get("iteration_plan", {{}}),
    }}
    PIPELINE_STATE["asset_card"] = card
    return card


def create_turntable_camera_animation(camera):
    if camera is None:
        PIPELINE_STATE["camera_action"] = ""
        return None
    camera.animation_data_clear()
    action = bpy.data.actions.new(SPEC["slug"] + "_camera_turntable")
    action.use_fake_user = True
    camera.animation_data_create()
    camera.animation_data.action = action
    bpy.context.scene.frame_start = 1
    bpy.context.scene.frame_end = 48
    for frame, location, rotation in (
        (1, (3.2, -5.0, 3.1), (math.radians(62), 0.0, math.radians(36))),
        (24, (5.0, 3.2, 3.1), (math.radians(62), 0.0, math.radians(126))),
        (48, (3.2, -5.0, 3.1), (math.radians(62), 0.0, math.radians(396))),
    ):
        camera.location = location
        camera.rotation_euler = rotation
        camera.keyframe_insert(data_path="location", frame=frame)
        camera.keyframe_insert(data_path="rotation_euler", frame=frame)
    PIPELINE_STATE["camera_action"] = action.name
    return action


def finalize_production_visibility(collections):
    for name in ("high", "bake", "rig", "preview", "collision"):
        for obj in collections[name].objects:
            obj.hide_render = True
            if hasattr(obj, "hide_set") and name in ("bake", "rig", "preview"):
                obj.hide_set(True)


def build_production_character_pipeline(m):
    collections = build_production_collections()
    created = capture_created_objects(build_anime_action_character, m)
    high_meshes, support_objects = route_production_objects(created, collections)
    prepare_high_poly_meshes(high_meshes)
    low_meshes = make_low_poly_meshes(high_meshes, collections["low"])
    for obj in low_meshes:
        ensure_uv_layout(obj)
    textures = create_production_texture_set()
    clone_runtime_materials(low_meshes, textures)
    tune_runtime_materials(low_meshes)
    create_bake_cages(low_meshes, collections["bake"])
    collect_mesh_metrics(high_meshes, low_meshes)
    armature = create_humanoid_rig(collections["rig"])
    bind_meshes_to_rig(low_meshes, armature)
    assign_runtime_vertex_groups(low_meshes)
    create_skinning_manifest(low_meshes, armature)
    create_lod_variants(low_meshes, collections["preview"])
    actions = create_preview_actions(armature)
    stress_action = create_pose_stress_action(armature)
    if stress_action is not None:
        actions.append(stress_action)
    create_expression_shape_keys(low_meshes)
    create_attachment_sockets(armature, collections["rig"])
    create_rig_control_markers(armature, collections["rig"])
    create_ik_constraint_targets(armature, collections["rig"])
    create_animation_manifest(armature, actions)
    collision_proxies = create_collision_proxies(m, collections["collision"])
    finalize_production_visibility(collections)
    create_art_readiness_report(low_meshes, high_meshes)
    create_visual_qa_report(low_meshes, armature, collections)
    create_engine_import_contract(low_meshes, armature)
    validation = validate_runtime_character_asset(low_meshes, armature)
    create_production_manifest(low_meshes, high_meshes, armature)
    create_blackbox_iteration_plan()
    create_runtime_asset_card(low_meshes, armature)
    pipeline_label = add_label("production_pipeline_nameplate", SPEC["model_name"][:18], (0, -0.9, 0.08), m["glow"], size=0.15)
    pipeline_label.hide_render = True
    PIPELINE_STATE["collections"] = [collections["high"].name, collections["low"].name, collections["bake"].name, collections["rig"].name, collections["collision"].name, collections["preview"].name]
    PIPELINE_STATE["export_objects"] = [obj.name for obj in low_meshes] + [armature.name] + [obj.name for obj in collision_proxies]
    return {{
        "high_mesh_count": len(high_meshes),
        "low_mesh_count": len(low_meshes),
        "support_count": len(support_objects),
        "collision_proxy_count": len(collision_proxies),
        "armature": armature.name,
        "validation": validation,
    }}


def build_fantasy_relic(m):
    cylinder("pedestal_base", (0, 0, 0.18), 1.15, 0.36, m["dark"], vertices=48, bevel=0.045)
    cylinder("inlaid_step", (0, 0, 0.44), 0.88, 0.18, m["gold"], vertices=48, bevel=0.035)
    cylinder("relic_core_socket", (0, 0, 0.68), 0.54, 0.32, m["primary"], vertices=36, bevel=0.03)
    cone("floating_crystal_lower", (0, 0, 1.26), 0.36, 0.08, 0.78, m["accent"], vertices=6, bevel=0.01)
    cone("floating_crystal_upper", (0, 0, 1.84), 0.08, 0.33, 0.62, m["accent"], vertices=6, bevel=0.01)
    for index, z in enumerate((0.88, 1.18, 1.56)):
        ring = torus(f"orbit_ring_{{index + 1}}", (0, 0, z), 0.82 + index * 0.08, 0.018, m["gold"], rotation=(math.radians(68 + index * 12), 0, math.radians(index * 35)))
        ring.scale.y = 0.72
    for index in range(8):
        angle = math.tau * index / 8
        x = math.cos(angle) * 1.16
        y = math.sin(angle) * 1.16
        ob = cube(f"rune_pillar_{{index + 1}}", (x, y, 0.74), (0.08, 0.08, 0.32), m["soft"], bevel=0.015)
        ob.rotation_euler.z = angle
        add_label(f"rune_mark_{{index + 1}}", "*", (x * 0.93, y * 0.93, 0.93), m["glow"], size=0.18, rotation=(math.radians(72), 0, angle + math.radians(90)))


def build_sci_fi_crate(m):
    cube("crate_main_hull", (0, 0, 0.7), (1.25, 0.85, 0.7), m["dark"], bevel=0.06)
    cube("front_armor_panel", (0, -0.88, 0.72), (0.96, 0.045, 0.42), m["primary"], bevel=0.025)
    cube("rear_armor_panel", (0, 0.88, 0.72), (0.96, 0.045, 0.42), m["primary"], bevel=0.025)
    for side, y in (("front", -0.94), ("rear", 0.94)):
        cube(f"{{side}}_glow_strip_upper", (0, y, 1.04), (0.82, 0.025, 0.035), m["glow"], bevel=0.008)
        cube(f"{{side}}_glow_strip_lower", (0, y, 0.40), (0.7, 0.025, 0.03), m["glow"], bevel=0.008)
    for sx in (-1, 1):
        for sy in (-1, 1):
            cube(f"corner_guard_{{sx}}_{{sy}}", (sx * 1.18, sy * 0.78, 0.72), (0.12, 0.14, 0.72), m["gold"], bevel=0.03)
    for sx in (-1, 1):
        cube(f"side_handle_{{sx}}", (sx * 1.34, 0, 0.86), (0.06, 0.48, 0.09), m["primary"], bevel=0.018)
    cylinder("top_lock_socket", (0, 0, 1.42), 0.28, 0.12, m["gold"], vertices=32, bevel=0.015)


def build_environment_diorama(m):
    cube("diorama_ground_slab", (0, 0, -0.03), (2.6, 2.0, 0.08), m["soft"], bevel=0.04)
    for index, (x, y, s) in enumerate([(-1.0, -0.55, 0.42), (-0.35, 0.72, 0.55), (0.9, 0.5, 0.38), (1.1, -0.7, 0.5)]):
        rock = cone(f"faceted_rock_{{index + 1}}", (x, y, s * 0.42), s * 0.42, s * 0.18, s * 0.82, m["primary"], vertices=7, bevel=0.012)
        rock.rotation_euler.z = index * 0.7
    cube("ancient_arch_left", (-0.58, 0, 0.68), (0.16, 0.22, 0.72), m["dark"], bevel=0.025)
    cube("ancient_arch_right", (0.58, 0, 0.68), (0.16, 0.22, 0.72), m["dark"], bevel=0.025)
    cube("ancient_arch_top", (0, 0, 1.34), (0.76, 0.24, 0.14), m["dark"], bevel=0.025)
    for index, x in enumerate((-1.45, 1.45)):
        cylinder(f"stylized_tree_trunk_{{index + 1}}", (x, 0.36, 0.35), 0.09, 0.7, m["gold"], vertices=12, bevel=0.01)
        cone(f"stylized_tree_canopy_{{index + 1}}", (x, 0.36, 0.94), 0.38, 0.08, 0.72, m["accent"], vertices=10, bevel=0.01)
    torus("pathway_energy_trace", (0, -0.34, 0.05), 0.78, 0.012, m["glow"], rotation=(0, 0, 0))


def build_anime_action_character(m):
    cube("lod0_character_silhouette_base", (0, 0, 0.015), (0.82, 0.62, 0.03), m["line"], bevel=0.02)
    cylinder("centerline_rig_reference", (0, 0.18, 1.08), 0.012, 2.15, m["glow"], vertices=8, bevel=0.0)
    cylinder("pelvis_blockout", (0, 0, 0.76), 0.2, 0.3, m["dark"], vertices=18, bevel=0.024)
    cylinder("waist_belt_layer", (0, -0.01, 0.95), 0.25, 0.11, m["gold"], vertices=24, bevel=0.014)
    ellipsoid("torso_anime_taper", (0, 0, 1.22), 0.4, (0.62, 0.4, 1.15), m["primary"], segments=32, ring_count=16, bevel=0.018)
    cube("front_inner_suit_panel", (0, -0.255, 1.2), (0.18, 0.025, 0.38), m["dark"], bevel=0.012)
    cube("cropped_jacket_left_panel", (-0.18, -0.29, 1.17), (0.13, 0.035, 0.43), m["cloth_alt"], bevel=0.018).rotation_euler.z = math.radians(-5)
    cube("cropped_jacket_right_panel", (0.18, -0.29, 1.17), (0.13, 0.035, 0.43), m["cloth_alt"], bevel=0.018).rotation_euler.z = math.radians(5)
    cube("chest_emblem_socket", (0, -0.325, 1.33), (0.13, 0.024, 0.1), m["gold"], bevel=0.01)
    sphere("chest_emissive_core", (0, -0.36, 1.34), 0.055, m["glow"], segments=16, ring_count=8)

    ellipsoid("neck_soft_link", (0, 0, 1.6), 0.075, (0.66, 0.55, 1.08), m["skin"], segments=16, ring_count=8)
    ellipsoid("head_stylized_face_mass", (0, -0.015, 1.82), 0.218, (0.82, 0.72, 1.08), m["skin"], segments=40, ring_count=20)
    ellipsoid("hair_cap_layer", (0, 0.02, 1.91), 0.228, (0.9, 0.76, 0.5), m["hair"], segments=40, ring_count=14)
    for index, (x, y, z, rx, rz, length) in enumerate([
        (-0.18, -0.055, 1.865, 18, -28, 0.19),
        (-0.075, -0.065, 1.93, 10, -12, 0.15),
        (0.085, -0.065, 1.93, 10, 12, 0.15),
        (0.19, -0.055, 1.865, 18, 28, 0.19),
        (0.0, 0.155, 1.98, -12, 0, 0.34),
    ]):
        clump = ellipsoid("layered_hair_clump_" + str(index + 1), (x, y, z), 0.09, (0.46, 0.18, max(0.45, length * 2.2)), m["hair"], segments=20, ring_count=10, bevel=0.0)
        clump.rotation_euler.x = math.radians(rx)
        clump.rotation_euler.z = math.radians(rz)
    ellipsoid("left_eye_white_sclera", (-0.07, -0.207, 1.845), 0.023, (1.45, 0.34, 0.72), m["soft"], segments=16, ring_count=8, bevel=0.0)
    ellipsoid("right_eye_white_sclera", (0.07, -0.207, 1.845), 0.023, (1.45, 0.34, 0.72), m["soft"], segments=16, ring_count=8, bevel=0.0)
    ellipsoid("left_iris_catchlight", (-0.071, -0.222, 1.844), 0.012, (0.8, 0.28, 1.05), m["glow"], segments=12, ring_count=8, bevel=0.0)
    ellipsoid("right_iris_catchlight", (0.071, -0.222, 1.844), 0.012, (0.8, 0.28, 1.05), m["glow"], segments=12, ring_count=8, bevel=0.0)
    cube("left_eye_ink_shape", (-0.07, -0.229, 1.86), (0.058, 0.008, 0.009), m["line"], bevel=0.003)
    cube("right_eye_ink_shape", (0.07, -0.229, 1.86), (0.058, 0.008, 0.009), m["line"], bevel=0.003)
    cube("face_highlight_bridge", (0, -0.199, 1.795), (0.014, 0.007, 0.042), m["soft"], bevel=0.004)
    ellipsoid("left_eye_gloss_lens", (-0.07, -0.205, 1.85), 0.015, (1.2, 0.38, 0.58), m["glow"], segments=16, ring_count=8, bevel=0.0)
    ellipsoid("right_eye_gloss_lens", (0.07, -0.205, 1.85), 0.015, (1.2, 0.38, 0.58), m["glow"], segments=16, ring_count=8, bevel=0.0)
    cube("left_brow_expression_plate", (-0.076, -0.198, 1.885), (0.057, 0.009, 0.01), m["hair"], bevel=0.003).rotation_euler.z = math.radians(7)
    cube("right_brow_expression_plate", (0.076, -0.198, 1.885), (0.057, 0.009, 0.01), m["hair"], bevel=0.003).rotation_euler.z = math.radians(-7)
    ellipsoid("nose_soft_plane", (0.0, -0.213, 1.81), 0.019, (0.45, 0.26, 0.85), m["skin"], segments=12, ring_count=8, bevel=0.0)
    cube("mouth_shadow_curve", (0.0, -0.215, 1.755), (0.058, 0.007, 0.009), m["line"], bevel=0.003)
    ellipsoid("left_ear_anatomy", (-0.195, -0.0, 1.815), 0.035, (0.48, 0.24, 0.9), m["skin"], segments=12, ring_count=8, bevel=0.0)
    ellipsoid("right_ear_anatomy", (0.195, -0.0, 1.815), 0.035, (0.48, 0.24, 0.9), m["skin"], segments=12, ring_count=8, bevel=0.0)
    for index, (sx, z, length) in enumerate([(-1, 1.76, 0.34), (-1, 1.66, 0.42), (1, 1.75, 0.32), (1, 1.65, 0.38)]):
        side_lock = cone("sideburn_hair_lock_" + str(index + 1), (sx * 0.24, -0.18, z), 0.038, 0.006, length, m["hair"], vertices=8, bevel=0.004)
        side_lock.rotation_euler.x = math.radians(18)
        side_lock.rotation_euler.z = math.radians(12 * sx)
    ponytail = cone("back_layered_ponytail_mass", (0.0, 0.22, 1.69), 0.11, 0.035, 0.58, m["hair"], vertices=12, bevel=0.008)
    ponytail.rotation_euler.x = math.radians(-18)

    for side_name, sx in (("L", -1), ("R", 1)):
        ellipsoid("shoulder_silhouette_" + side_name, (sx * 0.31, -0.01, 1.44), 0.14, (1.25, 0.72, 0.62), m["gold"], segments=20, ring_count=10, bevel=0.01)
        ellipsoid("layered_pauldron_upper_" + side_name, (sx * 0.36, -0.09, 1.48), 0.105, (1.35, 0.58, 0.38), m["gold"], segments=16, ring_count=8, bevel=0.008)
        upper = cylinder("upper_arm_sleeve_" + side_name, (sx * 0.43, -0.015, 1.18), 0.062, 0.48, m["primary"], vertices=14, bevel=0.012)
        upper.rotation_euler.y = math.radians(17 * sx)
        fore = cylinder("forearm_glove_" + side_name, (sx * 0.55, -0.08, 0.88), 0.058, 0.42, m["dark"], vertices=14, bevel=0.012)
        fore.rotation_euler.y = math.radians(-12 * sx)
        cube("forearm_trim_plate_" + side_name, (sx * 0.58, -0.155, 0.91), (0.032, 0.014, 0.14), m["gold"], bevel=0.004).rotation_euler.z = math.radians(-8 * sx)
        sphere("hand_pose_block_" + side_name, (sx * 0.62, -0.13, 0.64), 0.058, m["skin"], segments=16, ring_count=8)
        for finger_index, offset in enumerate((-0.036, -0.012, 0.012, 0.036)):
            finger = cylinder("finger_" + side_name + "_" + str(finger_index + 1), (sx * (0.64 + abs(offset) * 0.26), -0.18, 0.625 + offset), 0.0075, 0.088, m["skin"], vertices=8, bevel=0.002)
            finger.rotation_euler.x = math.radians(72)
            finger.rotation_euler.z = math.radians(5 * sx)
        thigh = cylinder("upper_leg_bootline_" + side_name, (sx * 0.13, 0.01, 0.48), 0.083, 0.6, m["primary"], vertices=14, bevel=0.012)
        thigh.rotation_euler.y = math.radians(-5 * sx)
        shin = cylinder("tall_boot_" + side_name, (sx * 0.17, -0.035, 0.19), 0.074, 0.48, m["dark"], vertices=14, bevel=0.012)
        shin.rotation_euler.y = math.radians(4 * sx)
        ellipsoid("knee_guard_layer_" + side_name, (sx * 0.16, -0.105, 0.43), 0.062, (1.15, 0.42, 0.72), m["gold"], segments=14, ring_count=8, bevel=0.004)
        cube("boot_front_armor_plate_" + side_name, (sx * 0.19, -0.125, 0.21), (0.048, 0.014, 0.18), m["gold"], bevel=0.004)
        cube("boot_toe_shape_" + side_name, (sx * 0.19, -0.15, 0.02), (0.09, 0.16, 0.04), m["dark"], bevel=0.015)
        cube("calf_emissive_slash_" + side_name, (sx * 0.205, -0.12, 0.31), (0.022, 0.018, 0.16), m["glow"], bevel=0.006).rotation_euler.z = math.radians(-12 * sx)

    for index, sx in enumerate((-1, 1)):
        panel = cube("asymmetric_coat_tail_" + str(index + 1), (sx * 0.17, 0.12, 0.72), (0.11, 0.035, 0.46), m["cloth_alt"], bevel=0.012)
        panel.rotation_euler.x = math.radians(-8)
        panel.rotation_euler.z = math.radians(8 * sx)
    for index, sx in enumerate((-1, 1, -0.35, 0.35)):
        sash = cube("layered_back_cape_panel_" + str(index + 1), (sx * 0.16, 0.24, 0.86), (0.085, 0.028, 0.58), m["cloth_alt"], bevel=0.01)
        sash.rotation_euler.x = math.radians(-14)
        sash.rotation_euler.z = math.radians(6 * sx)
    for index, (x, z) in enumerate([(-0.22, 1.3), (0.22, 1.3), (-0.16, 1.08), (0.16, 1.08), (0.0, 0.98)]):
        cube("chest_layered_armor_trim_" + str(index + 1), (x, -0.347, z), (0.075, 0.012, 0.026), m["gold"], bevel=0.004)
    cube("waist_hanging_charm_anchor", (0.0, -0.31, 0.82), (0.055, 0.022, 0.14), m["gold"], bevel=0.008)
    torus("waist_charm_energy_ring", (0, -0.34, 0.68), 0.1, 0.007, m["glow"], rotation=(math.radians(90), 0, 0))
    cube("weapon_grip_right_hand", (0.78, -0.18, 0.82), (0.035, 0.035, 0.34), m["dark"], bevel=0.008).rotation_euler.y = math.radians(-22)
    blade = cube("stylized_energy_blade_lod0", (0.91, -0.18, 1.06), (0.028, 0.04, 0.74), m["glow"], bevel=0.006)
    blade.rotation_euler.y = math.radians(-22)
    cube("weapon_guard_gold", (0.82, -0.18, 0.87), (0.16, 0.036, 0.035), m["gold"], bevel=0.008).rotation_euler.y = math.radians(-22)

    for name, loc in (
        ("rig_marker_head", (0, 0.32, 1.82)),
        ("rig_marker_chest", (0, 0.34, 1.25)),
        ("rig_marker_pelvis", (0, 0.32, 0.72)),
        ("lod_marker_weapon_tip", (1.05, -0.18, 1.42)),
    ):
        add_empty_marker(name, loc, size=0.07)
    nameplate = add_label("character_nameplate", SPEC["model_name"][:18], (0, -0.82, 0.08), m["glow"], size=0.15)
    nameplate.hide_render = True


def build_character_proxy(m):
    cylinder("character_boots", (0, 0, 0.18), 0.32, 0.28, m["dark"], vertices=16, bevel=0.018)
    cylinder("character_torso", (0, 0, 0.78), 0.34, 0.86, m["primary"], vertices=18, bevel=0.03)
    sphere("character_head", (0, 0, 1.42), 0.26, m["soft"], segments=24, ring_count=12)
    cube("chest_armor_plate", (0, -0.31, 0.86), (0.36, 0.04, 0.28), m["gold"], bevel=0.018)
    for sx in (-1, 1):
        cylinder(f"upper_arm_{{sx}}", (sx * 0.46, 0, 0.9), 0.075, 0.52, m["primary"], vertices=12, bevel=0.012).rotation_euler.y = math.radians(18 * sx)
        cylinder(f"forearm_{{sx}}", (sx * 0.62, -0.05, 0.54), 0.07, 0.42, m["dark"], vertices=12, bevel=0.012).rotation_euler.y = math.radians(-12 * sx)
        sphere(f"shoulder_guard_{{sx}}", (sx * 0.42, 0, 1.16), 0.14, m["gold"], segments=16, ring_count=8)
        cylinder(f"leg_{{sx}}", (sx * 0.16, 0, 0.36), 0.105, 0.54, m["dark"], vertices=12, bevel=0.012)
    blade = cube("proxy_weapon_blade", (0.86, -0.08, 0.82), (0.035, 0.055, 0.68), m["glow"], bevel=0.008)
    blade.rotation_euler.y = math.radians(-18)
    add_label("proxy_nameplate", SPEC["model_name"][:18], (0, -0.72, 0.08), m["glow"], size=0.16)


def build_modular_building(m):
    cube("foundation_block", (0, 0, 0.15), (1.35, 1.0, 0.16), m["dark"], bevel=0.035)
    cube("main_wall_module", (0, 0, 0.72), (1.15, 0.82, 0.72), m["soft"], bevel=0.025)
    cone("roof_cap", (0, 0, 1.28), 0.92, 0.42, 0.48, m["primary"], vertices=4, bevel=0.02).rotation_euler.z = math.radians(45)
    cube("door_recess", (0, -0.44, 0.48), (0.28, 0.035, 0.36), m["dark"], bevel=0.012)
    for sx in (-1, 1):
        cube(f"window_{{sx}}", (sx * 0.42, -0.45, 0.82), (0.18, 0.03, 0.18), m["glow"], bevel=0.008)
        cube(f"side_buttress_{{sx}}", (sx * 0.66, -0.03, 0.64), (0.08, 0.12, 0.68), m["gold"], bevel=0.014)
    cylinder("chimney_stack", (0.44, 0.18, 1.48), 0.08, 0.46, m["dark"], vertices=12, bevel=0.01)


def build_hero_prop(m):
    cylinder("display_plinth", (0, 0, 0.16), 0.92, 0.32, m["dark"], vertices=48, bevel=0.04)
    cube("hero_body_core", (0, 0, 0.76), (0.58, 0.44, 0.58), m["primary"], bevel=0.055)
    torus("hero_silhouette_ring", (0, 0, 0.98), 0.72, 0.024, m["gold"], rotation=(math.radians(82), 0, math.radians(34)))
    sphere("hero_focus_gem", (0, -0.48, 0.86), 0.16, m["accent"], segments=24, ring_count=12)
    for index in range(4):
        angle = math.tau * index / 4 + math.radians(45)
        cube(f"radial_fin_{{index + 1}}", (math.cos(angle) * 0.58, math.sin(angle) * 0.58, 0.76), (0.09, 0.28, 0.42), m["gold"], bevel=0.02).rotation_euler.z = angle
    add_label("hero_prop_title", SPEC["model_name"][:18], (0, -0.86, 0.13), m["glow"], size=0.16)


def add_camera_and_light():
    bpy.ops.object.light_add(type="AREA", location=(0, -4.2, 5.0))
    key = bpy.context.object
    key.name = "reverie_softbox_key"
    key.data.energy = 620
    key.data.size = 4.0
    bpy.ops.object.light_add(type="POINT", location=(-3.2, 2.4, 2.7))
    rim = bpy.context.object
    rim.name = "reverie_color_rim"
    rim.data.energy = 85
    rim.data.color = (0.55, 0.72, 1.0)
    bpy.ops.object.camera_add(location=(3.2, -5.0, 3.1), rotation=(math.radians(62), 0, math.radians(36)))
    cam = bpy.context.object
    bpy.context.scene.camera = cam
    cam.data.lens = 54
    cam.data.dof.use_dof = True
    cam.data.dof.focus_distance = 5.2
    cam.data.dof.aperture_fstop = 7.5
    return cam


def configure_scene():
    scene = bpy.context.scene
    for engine in ("BLENDER_EEVEE_NEXT", "BLENDER_EEVEE"):
        try:
            scene.render.engine = engine
            break
        except Exception:
            pass
    scene.render.resolution_x = 1280
    scene.render.resolution_y = 1280
    scene.view_settings.view_transform = "Filmic"
    scene.view_settings.look = "Medium High Contrast"
    scene.world = scene.world or bpy.data.worlds.new("World")
    scene.world.color = (0.028, 0.032, 0.04)


def build_scene():
    global PIPELINE_STATE
    clear_scene()
    configure_scene()
    mats = material_set()
    preset = SPEC["preset"]
    PIPELINE_STATE = {{"export_objects": [], "actions": [], "textures": {{}}, "texture_manifest": {{}}, "texture_authoring_manifest": {{}}, "material_tuning": {{}}, "collections": [], "armature": "", "shape_keys": [], "facial_manifest": {{}}, "sockets": [], "rig_controls": [], "ik_targets": [], "ik_constraints": [], "collision_proxies": [], "lods": [], "vertex_groups": {{}}, "skinning_manifest": {{}}, "animation_manifest": {{}}, "pose_stress_report": {{}}, "mesh_metrics": {{}}, "bake_manifest": {{}}, "art_readiness_report": {{}}, "visual_qa_report": {{}}, "engine_import_contract": {{}}, "production_manifest": {{}}, "iteration_plan": {{}}, "validation": {{}}, "quality_gates": [], "asset_card": {{}}, "camera_action": ""}}
    if preset == "fantasy_relic":
        build_fantasy_relic(mats)
    elif preset == "sci_fi_crate":
        build_sci_fi_crate(mats)
    elif preset == "environment_diorama":
        build_environment_diorama(mats)
    elif preset == "anime_action_character":
        build_anime_action_character(mats)
    elif preset == "production_character_pipeline":
        build_production_character_pipeline(mats)
    elif preset == "character_proxy":
        build_character_proxy(mats)
    elif preset == "modular_building":
        build_modular_building(mats)
    else:
        build_hero_prop(mats)
    camera = add_camera_and_light()
    if preset == "production_character_pipeline":
        create_turntable_camera_animation(camera)


def export_outputs():
    ensure_parent(OUTPUTS["blend"])
    bpy.ops.wm.save_as_mainfile(filepath=str(OUTPUTS["blend"]))
    export_format = SPEC["export_format"]
    export_names = [str(name) for name in PIPELINE_STATE.get("export_objects", []) if str(name).strip()]
    if export_format in {{"glb", "gltf"}}:
        ensure_parent(OUTPUTS["runtime"])
        gltf_format = "GLB" if export_format == "glb" else "GLTF_SEPARATE"
        bpy.ops.object.select_all(action="DESELECT")
        for name in export_names:
            obj = bpy.data.objects.get(name)
            if obj is not None:
                obj.select_set(True)
        if export_names:
            bpy.context.view_layer.objects.active = bpy.data.objects.get(export_names[0])
        try:
            bpy.ops.export_scene.gltf(
                filepath=str(OUTPUTS["runtime"]),
                export_format=gltf_format,
                export_apply=True,
                use_selection=bool(export_names),
            )
        except TypeError:
            try:
                bpy.ops.export_scene.gltf(
                    filepath=str(OUTPUTS["runtime"]),
                    export_format=gltf_format,
                    export_apply=True,
                    export_selected=bool(export_names),
                )
            except TypeError:
                bpy.ops.export_scene.gltf(filepath=str(OUTPUTS["runtime"]))
    if RENDER_PREVIEW:
        ensure_parent(OUTPUTS["preview"])
        bpy.context.scene.render.filepath = str(OUTPUTS["preview"])
        bpy.ops.render.render(write_still=True)
    ensure_parent(OUTPUTS["metadata"])
    objects = [
        {{"name": obj.name, "type": obj.type, "location": [round(v, 4) for v in obj.location]}}
        for obj in bpy.context.scene.objects
    ]
    OUTPUTS["metadata"].write_text(json.dumps({{
        "schema": "reverie.blender_authoring_result.v1",
        "model_name": SPEC["model_name"],
        "preset": SPEC["preset"],
        "style": SPEC["style"],
        "object_count": len(objects),
        "mesh_count": len([obj for obj in bpy.context.scene.objects if obj.type == "MESH"]),
        "objects": objects,
        "pipeline": PIPELINE_STATE,
        "export_selection": export_names,
        "outputs": {{key: str(value) for key, value in OUTPUTS.items()}},
    }}, indent=2), encoding="utf-8")
    if "validation_report" in OUTPUTS:
        ensure_parent(OUTPUTS["validation_report"])
        OUTPUTS["validation_report"].write_text(json.dumps({{
            "schema": "reverie.blender_asset_validation.v1",
            "model_name": SPEC["model_name"],
            "preset": SPEC["preset"],
            "validation": PIPELINE_STATE.get("validation", {{}}),
            "quality_gates": PIPELINE_STATE.get("quality_gates", []),
            "pipeline": PIPELINE_STATE,
        }}, indent=2), encoding="utf-8")
    if "production_manifest" in OUTPUTS:
        ensure_parent(OUTPUTS["production_manifest"])
        production_manifest = PIPELINE_STATE.get("production_manifest", {{}})
        if not production_manifest:
            production_manifest = {{
                "schema": "reverie.blender_production_manifest.v1",
                "model_name": SPEC["model_name"],
                "preset": SPEC["preset"],
                "pipeline_state": "not_applicable",
                "stages": [],
            }}
        production_manifest["outputs"] = {{key: str(value) for key, value in OUTPUTS.items()}}
        OUTPUTS["production_manifest"].write_text(json.dumps(production_manifest, indent=2), encoding="utf-8")
    if "qa_report" in OUTPUTS:
        ensure_parent(OUTPUTS["qa_report"])
        qa_report = PIPELINE_STATE.get("visual_qa_report", {{}})
        if not qa_report:
            qa_report = {{
                "schema": "reverie.blender_visual_qa_report.v1",
                "model_name": SPEC["model_name"],
                "passed": False,
                "checks": [],
            }}
        qa_report["outputs"] = {{key: str(value) for key, value in OUTPUTS.items()}}
        OUTPUTS["qa_report"].write_text(json.dumps(qa_report, indent=2), encoding="utf-8")
    if "engine_contract" in OUTPUTS:
        ensure_parent(OUTPUTS["engine_contract"])
        engine_contract = PIPELINE_STATE.get("engine_import_contract", {{}})
        if not engine_contract:
            engine_contract = {{
                "schema": "reverie.engine_import_contract.v1",
                "model_name": SPEC["model_name"],
                "passed": False,
            }}
        engine_contract["outputs"] = {{key: str(value) for key, value in OUTPUTS.items()}}
        OUTPUTS["engine_contract"].write_text(json.dumps(engine_contract, indent=2), encoding="utf-8")
    if "iteration_plan" in OUTPUTS:
        ensure_parent(OUTPUTS["iteration_plan"])
        iteration_plan = PIPELINE_STATE.get("iteration_plan", {{}})
        if not iteration_plan:
            iteration_plan = {{
                "schema": "reverie.blender_blackbox_iteration_plan.v1",
                "model_name": SPEC["model_name"],
                "preset": SPEC["preset"],
                "state": "continue",
                "automatic_repair_queue": [],
                "blocking_decisions": [],
            }}
        iteration_plan["outputs"] = {{key: str(value) for key, value in OUTPUTS.items()}}
        OUTPUTS["iteration_plan"].write_text(json.dumps(iteration_plan, indent=2), encoding="utf-8")
    if "asset_card" in OUTPUTS:
        ensure_parent(OUTPUTS["asset_card"])
        asset_card = PIPELINE_STATE.get("asset_card", {{}})
        if not asset_card:
            asset_card = {{
                "schema": "reverie.blender_production_asset_card.v1",
                "model_name": SPEC["model_name"],
                "preset": SPEC["preset"],
                "quality": PIPELINE_STATE.get("validation", {{}}),
                "quality_gates": PIPELINE_STATE.get("quality_gates", []),
            }}
        asset_card["outputs"] = {{key: str(value) for key, value in OUTPUTS.items()}}
        OUTPUTS["asset_card"].write_text(json.dumps(asset_card, indent=2), encoding="utf-8")


build_scene()
export_outputs()
'''


def validate_blender_script_text(script_text: str) -> tuple[bool, list[str]]:
    """Return whether a user script passes Reverie's conservative static scan."""
    issues: list[str] = []
    try:
        tree = ast.parse(script_text)
    except SyntaxError as exc:
        return False, [f"syntax error: {exc}"]

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                root = str(alias.name).split(".", 1)[0]
                if root in BLENDER_SCRIPT_BLOCKLIST:
                    issues.append(f"blocked import: {alias.name}")
        elif isinstance(node, ast.ImportFrom):
            root = str(node.module or "").split(".", 1)[0]
            if root in BLENDER_SCRIPT_BLOCKLIST:
                issues.append(f"blocked import: {node.module}")
        elif isinstance(node, ast.Call):
            func = node.func
            if isinstance(func, ast.Name) and func.id in {"eval", "exec", "compile"}:
                issues.append(f"blocked call: {func.id}")
            if isinstance(func, ast.Attribute) and isinstance(func.value, ast.Name):
                if func.value.id == "os" and func.attr in {"system", "popen", "spawnl", "spawnlp", "spawnv", "spawnvp"}:
                    issues.append(f"blocked os call: os.{func.attr}")

    return not issues, issues


def materialize_blender_workspace(project_root: str | Path, *, overwrite: bool = False) -> Dict[str, Any]:
    """Create the standard modeling workspace plus Blender-specific folders."""
    base = materialize_modeling_workspace(project_root, overwrite=overwrite)
    paths = blender_modeling_paths(project_root)
    directories: list[str] = list(base.get("directories", []))
    files: list[str] = list(base.get("files", []))
    for key in ("blender_source", "blender_scripts", "blender_plans", "blender_metadata"):
        target = paths[key]
        target.mkdir(parents=True, exist_ok=True)
        directories.append(str(target))

    readme = paths["blender_source"] / "README.md"
    if overwrite or not readme.exists():
        readme.write_text(
            "# Blender Source\n\n"
            "Reverie writes generated `.blend` source files, Blender Python scripts, and model plans here.\n"
            "The `blender_modeling_workbench` tool can run these scripts through Blender background mode and export runtime `.glb` files.\n",
            encoding="utf-8",
        )
        files.append(str(readme))

    return {
        **base,
        "directories": sorted(set(directories)),
        "files": sorted(set(files)),
        "blender": detect_blender_installation(),
    }


def create_blender_authoring_job(
    project_root: str | Path,
    *,
    brief: str,
    model_name: str,
    preset: str = "auto",
    style: str = "stylized",
    export_format: str = "glb",
    render_preview: bool = True,
    overwrite: bool = False,
) -> Dict[str, Any]:
    """Generate a workspace-local Blender plan and Python authoring script."""
    materialize_blender_workspace(project_root, overwrite=False)
    paths = blender_modeling_paths(project_root)
    spec = build_blender_model_spec(
        brief=brief,
        model_name=model_name,
        preset=preset,
        style=style,
        export_format=export_format,
    )
    outputs = _script_paths(project_root, spec, spec["export_format"])
    targets = [outputs["plan"], outputs["script"]]
    if not overwrite:
        for target in targets:
            if target.exists():
                raise FileExistsError(f"Target already exists: {target}")

    for target in targets:
        target.parent.mkdir(parents=True, exist_ok=True)

    outputs["plan"].write_text(json.dumps(spec, indent=2, ensure_ascii=False), encoding="utf-8")
    script = _build_authoring_script(spec, outputs, render_preview=render_preview)
    ok, issues = validate_blender_script_text(script)
    if not ok:
        raise ValueError("Generated Blender script failed static validation: " + "; ".join(issues))
    outputs["script"].write_text(script, encoding="utf-8")

    return {
        "spec": spec,
        "paths": {key: str(value) for key, value in outputs.items()},
        "relative_paths": {key: _relative_to(paths["project_root"], value) for key, value in outputs.items()},
        "render_preview": bool(render_preview),
    }


def run_blender_script(
    project_root: str | Path,
    script_path: str | Path,
    *,
    blender_path: Any = "",
    timeout_seconds: int = 240,
    allow_unsafe_python: bool = False,
) -> Dict[str, Any]:
    """Run a workspace-local Blender Python script in background mode."""
    root = Path(project_root).resolve()
    script = Path(script_path)
    if not script.is_absolute():
        script = (root / script).resolve()
    if not script.exists():
        raise FileNotFoundError(f"Blender script not found: {script}")
    try:
        script.relative_to(root)
    except ValueError as exc:
        raise ValueError(f"Blender script must stay inside the workspace: {script}") from exc

    script_text = script.read_text(encoding="utf-8")
    if not allow_unsafe_python:
        ok, issues = validate_blender_script_text(script_text)
        if not ok:
            return {
                "success": False,
                "exit_code": -1,
                "command": [],
                "stdout": "",
                "stderr": "; ".join(issues),
                "script_path": str(script),
                "blocked": True,
            }

    blender = detect_blender_installation(blender_path)
    executable = str(blender.get("executable_path") or "")
    if not executable:
        return {
            "success": False,
            "exit_code": -1,
            "command": [],
            "stdout": "",
            "stderr": blender.get("install_hint", "Blender executable not found."),
            "script_path": str(script),
            "blocked": False,
            "blender": blender,
        }

    command = [
        executable,
        "--background",
        "--python-exit-code",
        "23",
        "--python",
        str(script),
    ]
    completed = subprocess.run(
        command,
        cwd=str(root),
        capture_output=True,
        text=True,
        timeout=max(10, int(timeout_seconds or 240)),
        check=False,
        encoding="utf-8",
        errors="replace",
    )
    return {
        "success": completed.returncode == 0,
        "exit_code": completed.returncode,
        "command": command,
        "stdout": completed.stdout,
        "stderr": completed.stderr,
        "script_path": str(script),
        "blocked": False,
        "blender": blender,
    }


def create_blender_model(
    project_root: str | Path,
    *,
    brief: str,
    model_name: str,
    preset: str = "auto",
    style: str = "stylized",
    export_format: str = "glb",
    render_preview: bool = True,
    run_blender: bool = True,
    blender_path: Any = "",
    overwrite: bool = False,
    timeout_seconds: int = 240,
) -> Dict[str, Any]:
    """Generate a Blender script and optionally execute it to create assets."""
    job = create_blender_authoring_job(
        project_root,
        brief=brief,
        model_name=model_name,
        preset=preset,
        style=style,
        export_format=export_format,
        render_preview=render_preview,
        overwrite=overwrite,
    )
    run_result: Dict[str, Any] = {
        "success": False,
        "skipped": True,
        "reason": "run_blender is false",
    }
    if run_blender:
        run_result = run_blender_script(
            project_root,
            job["paths"]["script"],
            blender_path=blender_path,
            timeout_seconds=timeout_seconds,
            allow_unsafe_python=False,
        )

    registry = sync_model_registry(project_root, overwrite=True)
    audit: Dict[str, Any] = {}
    if run_result.get("success"):
        audit = audit_blender_model(project_root, job["spec"]["model_name"], export_format=job["spec"]["export_format"])
    return {
        **job,
        "run": run_result,
        "registry": registry,
        "audit": audit,
    }


def _load_blender_repair_spec(root: Path, model_name: str, export_format: str) -> Dict[str, Any]:
    paths = blender_modeling_paths(root)
    slug = _slugify(model_name)
    spec = _read_json_file(paths["blender_plans"] / f"{slug}.json")
    if spec:
        return spec
    return build_blender_model_spec(
        brief=str(model_name or slug),
        model_name=str(model_name or slug),
        preset="auto",
        style="stylized",
        export_format=export_format,
    )


def _repair_report_path(root: Path, spec: Dict[str, Any], export_format: str) -> Path:
    paths = blender_modeling_paths(root)
    slug = _slugify(spec.get("slug") or spec.get("model_name"))
    return paths["blender_metadata"] / f"{slug}_repair_report.json"


def _repair_queue_for_audit(outputs: Dict[str, Path], audit: Dict[str, Any]) -> tuple[list[Dict[str, Any]], Dict[str, Any]]:
    iteration_plan = _read_json_file(outputs["iteration_plan"])
    queue = iteration_plan.get("automatic_repair_queue", [])
    if not isinstance(queue, list):
        queue = []
    normalized_queue = [dict(item) for item in queue if isinstance(item, dict)]
    if normalized_queue:
        return normalized_queue, iteration_plan

    failed_gates = [str(item).strip() for item in audit.get("failed_gates", []) if str(item).strip()]
    synthesized = [
        {
            "source": "audit_gate",
            "id": gate_id,
            "action": "Regenerate the authoring script, rerun Blender, and re-audit this failed gate.",
            "verification": "The next audit must pass this gate or report the remaining blocker.",
        }
        for gate_id in failed_gates
    ]
    return synthesized, iteration_plan


def _append_repair_history(
    iteration_plan_path: Path,
    *,
    attempt: Dict[str, Any],
    final_audit: Dict[str, Any],
) -> None:
    plan = _read_json_file(iteration_plan_path)
    if not plan:
        return
    history = plan.get("repair_history", [])
    if not isinstance(history, list):
        history = []
    history.append(attempt)
    plan["repair_history"] = history
    plan["consumed_repair_count"] = int(plan.get("consumed_repair_count", 0) or 0) + int(attempt.get("repair_count", 0) or 0)
    plan["last_repair_at"] = _utc_now()
    plan["last_repair_status"] = attempt.get("status", "unknown")
    if final_audit.get("passed"):
        plan["state"] = "ready"
        plan["automatic_repair_queue"] = []
    elif attempt.get("status") == "blocked":
        plan["state"] = "blocked"
    else:
        plan["state"] = "continue"
    plan["post_repair_audit"] = {
        "status": final_audit.get("status", "unknown"),
        "score": final_audit.get("score", 0),
        "failed_gates": final_audit.get("failed_gates", []),
    }
    iteration_plan_path.parent.mkdir(parents=True, exist_ok=True)
    iteration_plan_path.write_text(json.dumps(plan, indent=2, ensure_ascii=False), encoding="utf-8")


def repair_blender_model(
    project_root: str | Path,
    model_name: str,
    *,
    export_format: str = "glb",
    blender_path: Any = "",
    max_iterations: int = 3,
    timeout_seconds: int = 240,
    render_preview: bool = True,
) -> Dict[str, Any]:
    """Consume a generated black-box repair queue by regenerating, rerunning, and re-auditing."""
    root = Path(project_root).resolve()
    materialize_blender_workspace(root, overwrite=False)
    requested_format = str(export_format or "glb").strip().lower()
    if requested_format not in BLENDER_EXPORT_FORMATS:
        requested_format = "glb"

    spec = _load_blender_repair_spec(root, model_name, requested_format)
    resolved_format = str(spec.get("export_format") or requested_format or "glb").strip().lower()
    if resolved_format not in BLENDER_EXPORT_FORMATS:
        resolved_format = requested_format
    spec["export_format"] = resolved_format
    outputs = _script_paths(root, spec, resolved_format)

    initial_audit = audit_blender_model(root, str(spec.get("model_name") or model_name), export_format=resolved_format)
    current_audit = initial_audit
    attempts: list[Dict[str, Any]] = []
    max_iterations = max(1, int(max_iterations or 1))

    for iteration in range(1, max_iterations + 1):
        if current_audit.get("passed"):
            break
        repair_queue, iteration_plan = _repair_queue_for_audit(outputs, current_audit)
        if not repair_queue and not current_audit.get("failed_gates"):
            break

        attempt: Dict[str, Any] = {
            "iteration": iteration,
            "started_at": _utc_now(),
            "repair_count": len(repair_queue),
            "repair_ids": [str(item.get("id", "")) for item in repair_queue],
            "pre_audit_status": current_audit.get("status", "unknown"),
            "pre_failed_gates": current_audit.get("failed_gates", []),
            "iteration_plan_state": iteration_plan.get("state", ""),
            "status": "running",
        }
        try:
            job = create_blender_authoring_job(
                root,
                brief=str(spec.get("brief") or spec.get("model_name") or model_name),
                model_name=str(spec.get("model_name") or model_name),
                preset=str(spec.get("preset") or "auto"),
                style=str(spec.get("style") or "stylized"),
                export_format=resolved_format,
                render_preview=render_preview,
                overwrite=True,
            )
            attempt["script_regenerated"] = True
            attempt["script_path"] = job["paths"]["script"]
            spec = dict(job.get("spec", spec))
            outputs = {key: Path(value) for key, value in job["paths"].items()}
        except Exception as exc:
            attempt["status"] = "blocked"
            attempt["error"] = f"script regeneration failed: {exc}"
            attempts.append(attempt)
            _append_repair_history(outputs["iteration_plan"], attempt=attempt, final_audit=current_audit)
            break

        run_result = run_blender_script(
            root,
            outputs["script"],
            blender_path=blender_path,
            timeout_seconds=timeout_seconds,
            allow_unsafe_python=False,
        )
        attempt["run"] = {
            "success": bool(run_result.get("success")),
            "exit_code": run_result.get("exit_code"),
            "blocked": bool(run_result.get("blocked")),
            "stderr": str(run_result.get("stderr", ""))[:1200],
        }
        sync_model_registry(root, overwrite=True)
        current_audit = audit_blender_model(root, str(spec.get("model_name") or model_name), export_format=resolved_format)
        attempt["finished_at"] = _utc_now()
        attempt["post_audit_status"] = current_audit.get("status", "unknown")
        attempt["post_failed_gates"] = current_audit.get("failed_gates", [])
        if current_audit.get("passed"):
            attempt["status"] = "repaired"
        elif not run_result.get("success"):
            attempt["status"] = "blocked"
        else:
            attempt["status"] = "needs_followup"
        attempts.append(attempt)
        _append_repair_history(outputs["iteration_plan"], attempt=attempt, final_audit=current_audit)
        if attempt["status"] == "blocked":
            break

    report = {
        "schema": "reverie.blender_blackbox_repair_report.v1",
        "generated_at": _utc_now(),
        "project_root": str(root),
        "model_name": spec.get("model_name") or model_name,
        "slug": _slugify(spec.get("slug") or spec.get("model_name") or model_name),
        "export_format": resolved_format,
        "max_iterations": max_iterations,
        "attempt_count": len(attempts),
        "success": bool(current_audit.get("passed")),
        "initial_audit": {
            "status": initial_audit.get("status", "unknown"),
            "score": initial_audit.get("score", 0),
            "failed_gates": initial_audit.get("failed_gates", []),
        },
        "final_audit": current_audit,
        "attempts": attempts,
    }
    report_path = _repair_report_path(root, spec, resolved_format)
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    report["repair_report_path"] = str(report_path)
    return report


def _audit_gate(gate_id: str, passed: bool, detail: str, *, severity: str = "blocker") -> Dict[str, Any]:
    return {
        "id": gate_id,
        "passed": bool(passed),
        "severity": severity,
        "detail": detail,
    }


def audit_blender_model(project_root: str | Path, model_name: str, *, export_format: str = "glb") -> Dict[str, Any]:
    """Audit generated Blender artifacts and return a production-readiness report."""
    root = Path(project_root).resolve()
    materialize_blender_workspace(root, overwrite=False)
    paths = blender_modeling_paths(root)
    slug = _slugify(model_name)
    plan_path = paths["blender_plans"] / f"{slug}.json"
    spec = _read_json_file(plan_path)
    if not spec:
        spec = {
            "model_name": str(model_name or slug),
            "slug": slug,
            "preset": "unknown",
            "export_format": str(export_format or "glb").lower(),
        }
    else:
        slug = _slugify(spec.get("slug") or spec.get("model_name") or slug)
    resolved_export_format = str(spec.get("export_format") or export_format or "glb").lower()
    outputs = _script_paths(root, {"slug": slug, "model_name": spec.get("model_name", model_name), "export_format": resolved_export_format}, resolved_export_format)

    artifacts = {name: _artifact_record(root, path) for name, path in outputs.items()}
    metadata = _read_json_file(outputs["metadata"])
    validation_report = _read_json_file(outputs["validation_report"])
    asset_card = _read_json_file(outputs["asset_card"])
    production_manifest = _read_json_file(outputs["production_manifest"])
    qa_report = _read_json_file(outputs["qa_report"])
    engine_contract = _read_json_file(outputs["engine_contract"])
    iteration_plan = _read_json_file(outputs["iteration_plan"])
    validation = validation_report.get("validation", {}) if isinstance(validation_report.get("validation"), dict) else {}
    pipeline = validation_report.get("pipeline", {}) if isinstance(validation_report.get("pipeline"), dict) else {}

    script_ok = False
    script_issues: list[str] = []
    if outputs["script"].exists():
        script_ok, script_issues = validate_blender_script_text(outputs["script"].read_text(encoding="utf-8"))

    runtime_summary: Dict[str, Any] = {}
    if outputs["runtime"].exists() and outputs["runtime"].is_file():
        try:
            runtime_summary = summarize_model_file(outputs["runtime"])
        except Exception as exc:
            runtime_summary = {"error": str(exc)}

    texture_keys = ("texture_basecolor", "texture_normal", "texture_orm", "texture_id")
    texture_records = {key: artifacts[key] for key in texture_keys}
    texture_complete = all(record["exists"] and record["size_bytes"] > 0 for record in texture_records.values())
    required_artifacts = ("plan", "script", "blend", "runtime", "metadata", "validation_report", "production_manifest", "qa_report", "engine_contract", "iteration_plan")
    artifact_complete = all(artifacts[key]["exists"] and artifacts[key]["size_bytes"] > 0 for key in required_artifacts)
    runtime_valid = bool(
        artifacts["runtime"]["exists"]
        and artifacts["runtime"]["size_bytes"] > 0
        and (
            outputs["runtime"].suffix.lower() != ".glb"
            or runtime_summary.get("valid_header") is True
        )
    )

    low_mesh_count = int(validation.get("low_mesh_count", 0) or 0)
    weighted_mesh_count = int(validation.get("weighted_mesh_count", 0) or 0)
    uv_ready_mesh_count = int(validation.get("uv_ready_mesh_count", 0) or 0)
    material_id_mesh_count = int(validation.get("material_id_mesh_count", 0) or 0)
    bake_cage_count = int(validation.get("bake_cage_count", 0) or 0)
    texture_authoring_passed = bool(validation.get("texture_authoring_passed"))
    collision_proxy_count = int(validation.get("collision_proxy_count", 0) or 0)
    lod_count = int(validation.get("lod_count", 0) or 0)
    material_tuning_mesh_count = int(validation.get("material_tuning_mesh_count", 0) or 0)
    skinning_manifest_mesh_count = int(validation.get("skinning_manifest_mesh_count", 0) or 0)
    animation_clip_count = int(validation.get("animation_clip_count", 0) or 0)
    ik_constraint_count = int(validation.get("ik_constraint_count", 0) or 0)
    facial_deformation_count = int(validation.get("facial_deformation_count", 0) or 0)
    pose_stress_frame_count = int(validation.get("pose_stress_frame_count", 0) or 0)
    art_readiness_passed = bool(validation.get("art_readiness_passed"))
    quality_gates = validation_report.get("quality_gates", [])
    if not isinstance(quality_gates, list):
        quality_gates = []
    production_stages = production_manifest.get("stages", [])
    if not isinstance(production_stages, list):
        production_stages = []
    automatic_repair_queue = iteration_plan.get("automatic_repair_queue", [])
    if not isinstance(automatic_repair_queue, list):
        automatic_repair_queue = []

    gates = [
        _audit_gate("script_static_validation", script_ok, "; ".join(script_issues) if script_issues else "Generated Blender Python passes Reverie's static scan."),
        _audit_gate("required_artifacts", artifact_complete, "Plan, script, blend, runtime export, metadata, validation report, production evidence, and iteration plan exist."),
        _audit_gate("runtime_export", runtime_valid, f"Runtime export is present and parseable: {runtime_summary}"),
        _audit_gate("texture_set", texture_complete, "Basecolor, normal, ORM, and material-ID textures exist."),
        _audit_gate("texture_authoring_manifest", texture_authoring_passed, "Procedural texture authoring manifest exists and is wired into validation."),
        _audit_gate("asset_card", artifacts["asset_card"]["exists"] and artifacts["asset_card"]["size_bytes"] > 0, "Production asset card exists.", severity="warning"),
        _audit_gate("production_manifest", production_manifest.get("schema") == "reverie.blender_production_manifest.v1" and bool(production_stages), "Production stage manifest exists and contains stage evidence."),
        _audit_gate("qa_report", qa_report.get("schema") == "reverie.blender_visual_qa_report.v1" and bool(qa_report.get("passed")), "Visual QA report exists and passes generated checks."),
        _audit_gate("engine_import_contract", engine_contract.get("schema") == "reverie.engine_import_contract.v1" and bool(engine_contract.get("passed")), "Engine import contract exists and is complete."),
        _audit_gate("blackbox_iteration_plan", iteration_plan.get("schema") == "reverie.blender_blackbox_iteration_plan.v1" and iteration_plan.get("state") in {"ready", "continue"} and isinstance(automatic_repair_queue, list), "Black-box iteration plan exists and can drive automatic remediation."),
        _audit_gate("metadata_schema", metadata.get("schema") == "reverie.blender_authoring_result.v1", "Authoring metadata schema is recognized."),
        _audit_gate("validation_schema", validation_report.get("schema") == "reverie.blender_asset_validation.v1", "Validation report schema is recognized."),
        _audit_gate("pipeline_validation", bool(validation.get("passed")), f"Pipeline validation score: {validation.get('score', 'n/a')}."),
        _audit_gate("retopo_and_weights", low_mesh_count > 0 and weighted_mesh_count == low_mesh_count, "Every runtime mesh has generated vertex-group weight hints."),
        _audit_gate("material_tuning", low_mesh_count > 0 and material_tuning_mesh_count == low_mesh_count, "Every runtime mesh has a PBR material tuning manifest."),
        _audit_gate("skinning_manifest", low_mesh_count > 0 and skinning_manifest_mesh_count == low_mesh_count, "Every runtime mesh has a skinning contract."),
        _audit_gate("uvs_materials_bakes", low_mesh_count > 0 and uv_ready_mesh_count == low_mesh_count and material_id_mesh_count == low_mesh_count and bake_cage_count == low_mesh_count, "Runtime meshes have UVs, material IDs, and bake cages."),
        _audit_gate("animation_rig", bool(validation.get("has_armature")) and int(validation.get("action_count", 0) or 0) >= 2 and animation_clip_count >= 2, "Armature and at least two manifest-backed preview actions exist."),
        _audit_gate("facial_deformation", facial_deformation_count > 0, "Facial shape keys contain non-zero deformation evidence."),
        _audit_gate("pose_stress", pose_stress_frame_count >= 3, "Skinning stress-test action contains enough stress frames."),
        _audit_gate("art_readiness", art_readiness_passed, "Automated art-readiness report passed generated production-candidate checks."),
        _audit_gate("ik_constraints", ik_constraint_count >= 4, "IK constraints exist for hands and feet."),
        _audit_gate("collision_proxies", collision_proxy_count >= 4, "Runtime character collision proxies exist."),
        _audit_gate("lod_coverage", low_mesh_count > 0 and lod_count >= low_mesh_count * 2, "At least two LOD variants exist per runtime mesh."),
        _audit_gate("script_quality_gates", bool(quality_gates) and all(bool(item.get("passed")) for item in quality_gates if isinstance(item, dict)), "Generated in-Blender quality gates all passed."),
    ]
    blocker_gates = [gate for gate in gates if gate["severity"] == "blocker"]
    score = round(sum(1 for gate in gates if gate["passed"]) / max(1, len(gates)) * 100, 2)
    blocker_score = round(sum(1 for gate in blocker_gates if gate["passed"]) / max(1, len(blocker_gates)) * 100, 2)
    failed = [gate for gate in gates if not gate["passed"]]
    status = "passed" if not failed else ("warning" if all(gate["severity"] == "warning" for gate in failed) else "failed")

    return {
        "schema": "reverie.blender_model_audit.v1",
        "generated_at": _utc_now(),
        "project_root": str(root),
        "model_name": spec.get("model_name") or model_name,
        "slug": slug,
        "preset": spec.get("preset", "unknown"),
        "status": status,
        "score": score,
        "blocker_score": blocker_score,
        "passed": status == "passed",
        "failed_gates": [gate["id"] for gate in failed],
        "gates": gates,
        "artifacts": artifacts,
        "runtime_summary": runtime_summary,
        "texture_records": texture_records,
        "metadata": {
            "schema": metadata.get("schema", ""),
            "object_count": metadata.get("object_count", 0),
            "mesh_count": metadata.get("mesh_count", 0),
            "export_selection_count": len(metadata.get("export_selection") or []),
        },
        "validation": validation,
        "quality_gates": quality_gates,
        "asset_card": {
            "schema": asset_card.get("schema", ""),
            "runtime_contract": asset_card.get("runtime_contract", {}),
        },
        "production_manifest": {
            "schema": production_manifest.get("schema", ""),
            "pipeline_state": production_manifest.get("pipeline_state", ""),
            "stage_count": len(production_stages),
            "missing_stages": [
                stage.get("id", "")
                for stage in production_stages
                if isinstance(stage, dict) and stage.get("status") != "passed"
            ],
        },
        "qa_report": {
            "schema": qa_report.get("schema", ""),
            "passed": bool(qa_report.get("passed")),
            "check_count": len(qa_report.get("checks") or []),
        },
        "engine_contract": {
            "schema": engine_contract.get("schema", ""),
            "passed": bool(engine_contract.get("passed")),
            "runtime_format": engine_contract.get("runtime_format", ""),
            "animation_clip_count": len(engine_contract.get("animation_clips") or []),
            "validation_mode": (engine_contract.get("artifact_import_validation", {}) if isinstance(engine_contract.get("artifact_import_validation"), dict) else {}).get("validation_mode", ""),
            "native_runtime_status": (engine_contract.get("target_runtime_execution", {}) if isinstance(engine_contract.get("target_runtime_execution"), dict) else {}).get("status", ""),
        },
        "iteration_plan": {
            "schema": iteration_plan.get("schema", ""),
            "state": iteration_plan.get("state", ""),
            "repair_count": len(automatic_repair_queue),
            "blocking_decision_count": len(iteration_plan.get("blocking_decisions") or []),
        },
        "pipeline": {
            "collections": pipeline.get("collections", []),
            "actions": pipeline.get("actions", []),
            "sockets": pipeline.get("sockets", []),
            "rig_controls": pipeline.get("rig_controls", []),
            "ik_targets": pipeline.get("ik_targets", []),
            "ik_constraints": pipeline.get("ik_constraints", []),
            "collision_proxies": pipeline.get("collision_proxies", []),
            "shape_keys": pipeline.get("shape_keys", []),
            "material_tuning": pipeline.get("material_tuning", {}),
            "texture_authoring_manifest": pipeline.get("texture_authoring_manifest", {}),
            "skinning_manifest": pipeline.get("skinning_manifest", {}),
            "animation_manifest": pipeline.get("animation_manifest", {}),
            "facial_manifest": pipeline.get("facial_manifest", {}),
            "pose_stress_report": pipeline.get("pose_stress_report", {}),
            "art_readiness_report": pipeline.get("art_readiness_report", {}),
            "visual_qa_report": pipeline.get("visual_qa_report", {}),
            "engine_import_contract": pipeline.get("engine_import_contract", {}),
            "iteration_plan": pipeline.get("iteration_plan", {}),
        },
    }


def inspect_blender_modeling_workspace(project_root: str | Path, *, blender_path: Any = "") -> Dict[str, Any]:
    """Inspect Reverie's modeling workspace with Blender-specific readiness."""
    root = Path(project_root).resolve()
    paths = blender_modeling_paths(root)
    base = inspect_modeling_workspace(root)
    blender = detect_blender_installation(blender_path)
    script_files = sorted(paths["blender_scripts"].glob("*.py")) if paths["blender_scripts"].exists() else []
    plan_files = sorted(paths["blender_plans"].glob("*.json")) if paths["blender_plans"].exists() else []
    return {
        **base,
        "integration": "built_in_blender_background",
        "blender": blender,
        "blender_ready": bool(blender.get("available")),
        "script_count": len(script_files),
        "plan_count": len(plan_files),
        "workspace_paths": {
            "blender_source": _relative_to(root, paths["blender_source"]),
            "blender_scripts": _relative_to(root, paths["blender_scripts"]),
            "blender_plans": _relative_to(root, paths["blender_plans"]),
            "runtime_extensions": list(PREFERRED_RUNTIME_EXTENSIONS),
        },
    }


__all__ = [
    "BLENDER_EXPORT_FORMATS",
    "BLENDER_MODEL_PRESETS",
    "audit_blender_model",
    "blender_modeling_paths",
    "build_blender_model_spec",
    "create_blender_authoring_job",
    "create_blender_model",
    "detect_blender_installation",
    "infer_blender_preset",
    "inspect_blender_modeling_workspace",
    "materialize_blender_workspace",
    "repair_blender_model",
    "run_blender_script",
    "validate_blender_script_text",
]
