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
            "skeletal_rig": resolved_preset == "production_character_pipeline",
            "animation_actions": resolved_preset == "production_character_pipeline",
            "ik_control_markers": resolved_preset == "production_character_pipeline",
            "lod_variants": resolved_preset == "production_character_pipeline",
            "vertex_group_weights": resolved_preset == "production_character_pipeline",
            "asset_validation_report": resolved_preset == "production_character_pipeline",
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
PIPELINE_STATE = {{"export_objects": [], "actions": [], "textures": {{}}, "collections": [], "armature": "", "shape_keys": [], "sockets": [], "rig_controls": [], "lods": [], "vertex_groups": {{}}, "validation": {{}}, "camera_action": ""}}


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
        return 0.42
    if "face" in name or "head" in name:
        return 0.58
    if "blade" in name or "weapon" in name:
        return 0.68
    if "glow" in name or "core" in name:
        return 0.52
    return 0.34


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


def create_texture_placeholders():
    textures = {{
        "basecolor": create_texture_image(OUTPUTS["texture_basecolor"], 2048, 2048, (*SPEC["palette"][0][:3], 1.0), colorspace="sRGB"),
        "normal": create_texture_image(OUTPUTS["texture_normal"], 2048, 2048, (0.5, 0.5, 1.0, 1.0), colorspace="Non-Color"),
        "orm": create_texture_image(OUTPUTS["texture_orm"], 2048, 2048, (1.0, SPEC["roughness"], SPEC["metallic"], 1.0), colorspace="Non-Color"),
        "id": create_texture_image(OUTPUTS["texture_id"], 2048, 2048, (*SPEC["palette"][1][:3], 1.0), colorspace="Non-Color"),
    }}
    PIPELINE_STATE["textures"] = {{key: str(OUTPUTS["texture_" + key]) for key in ("basecolor", "normal", "orm", "id")}}
    return textures


def get_or_create_node(nodes, node_type, name):
    node = nodes.get(name)
    if node is None:
        node = nodes.new(node_type)
        node.name = name
        node.label = name
    return node


def configure_runtime_material(mat, textures, material_id):
    mat.use_nodes = True
    nodes = mat.node_tree.nodes
    links = mat.node_tree.links
    bsdf = nodes.get("Principled BSDF")
    if bsdf is None:
        return
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
        links.new(tex_base.outputs["Color"], bsdf.inputs["Base Color"])
    except Exception:
        pass
    try:
        links.new(tex_normal.outputs["Color"], normal_map.inputs["Color"])
        links.new(normal_map.outputs["Normal"], bsdf.inputs["Normal"])
    except Exception:
        pass
    mat["reverie_material_id"] = material_id


def clone_runtime_materials(meshes, textures):
    for obj in meshes:
        if obj.type != "MESH":
            continue
        for index, slot in enumerate(obj.material_slots):
            if slot.material is None:
                continue
            slot.material = slot.material.copy()
            configure_runtime_material(slot.material, textures, SPEC["slug"] + "::" + obj.name + "::" + str(index))


def create_bake_cages(meshes, collection):
    cages = []
    for source in meshes:
        cage = duplicate_mesh_object(source, source.name + "_bake_cage")
        for modifier in list(cage.modifiers):
            cage.modifiers.remove(modifier)
        place_in_collection(cage, collection)
        cage.display_type = "WIRE"
        cage.hide_render = True
        cage.scale = tuple(component * 1.015 for component in cage.scale)
        cage["reverie_stage"] = "bake_cage"
        cages.append(cage)
    return cages


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
        return []
    names = []
    if target.data.shape_keys is None or "Basis" not in target.data.shape_keys.key_blocks:
        target.shape_key_add(name="Basis", from_mix=False)
    for name in ("blink_L", "blink_R", "smile_soft", "mouth_open"):
        key = target.shape_key_add(name=name, from_mix=False)
        key.value = 0.0
        names.append(key.name)
    target["reverie_face_mesh"] = True
    PIPELINE_STATE["shape_keys"] = names
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


def validate_runtime_character_asset(low_meshes, armature):
    validation = {{
        "low_mesh_count": len(low_meshes),
        "has_armature": armature is not None,
        "action_count": len(PIPELINE_STATE.get("actions", [])),
        "texture_count": len(PIPELINE_STATE.get("textures", {{}})),
        "lod_count": len(PIPELINE_STATE.get("lods", [])),
        "socket_count": len(PIPELINE_STATE.get("sockets", [])),
        "control_count": len(PIPELINE_STATE.get("rig_controls", [])),
        "weighted_mesh_count": len(PIPELINE_STATE.get("vertex_groups", {{}})),
    }}
    validation["passed"] = bool(
        validation["low_mesh_count"] > 0
        and validation["has_armature"]
        and validation["action_count"] >= 2
        and validation["texture_count"] >= 4
        and validation["lod_count"] >= 2
        and validation["weighted_mesh_count"] == validation["low_mesh_count"]
    )
    PIPELINE_STATE["validation"] = validation
    return validation


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
    for obj in collections["high"].objects:
        obj.hide_render = True
    for obj in collections["bake"].objects:
        obj.hide_render = True
        if hasattr(obj, "hide_set"):
            obj.hide_set(True)


def build_production_character_pipeline(m):
    collections = build_production_collections()
    created = capture_created_objects(build_anime_action_character, m)
    high_meshes, support_objects = route_production_objects(created, collections)
    prepare_high_poly_meshes(high_meshes)
    low_meshes = make_low_poly_meshes(high_meshes, collections["low"])
    for obj in low_meshes:
        ensure_uv_layout(obj)
    textures = create_texture_placeholders()
    clone_runtime_materials(low_meshes, textures)
    create_bake_cages(low_meshes, collections["bake"])
    armature = create_humanoid_rig(collections["rig"])
    bind_meshes_to_rig(low_meshes, armature)
    assign_runtime_vertex_groups(low_meshes)
    create_lod_variants(low_meshes, collections["preview"])
    create_preview_actions(armature)
    create_expression_shape_keys(low_meshes)
    create_attachment_sockets(armature, collections["rig"])
    create_rig_control_markers(armature, collections["rig"])
    validation = validate_runtime_character_asset(low_meshes, armature)
    finalize_production_visibility(collections)
    add_label("production_pipeline_nameplate", SPEC["model_name"][:18], (0, -0.9, 0.08), m["glow"], size=0.15)
    PIPELINE_STATE["collections"] = [collections["high"].name, collections["low"].name, collections["bake"].name, collections["rig"].name, collections["preview"].name]
    PIPELINE_STATE["export_objects"] = [obj.name for obj in low_meshes] + [armature.name]
    return {{
        "high_mesh_count": len(high_meshes),
        "low_mesh_count": len(low_meshes),
        "support_count": len(support_objects),
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
    cylinder("pelvis_blockout", (0, 0, 0.72), 0.24, 0.32, m["dark"], vertices=18, bevel=0.024)
    cylinder("waist_belt_layer", (0, -0.01, 0.93), 0.28, 0.12, m["gold"], vertices=24, bevel=0.014)
    ellipsoid("torso_anime_taper", (0, 0, 1.2), 0.42, (0.72, 0.46, 1.08), m["primary"], segments=32, ring_count=16, bevel=0.018)
    cube("front_inner_suit_panel", (0, -0.255, 1.2), (0.18, 0.025, 0.38), m["dark"], bevel=0.012)
    cube("cropped_jacket_left_panel", (-0.18, -0.29, 1.17), (0.13, 0.035, 0.43), m["cloth_alt"], bevel=0.018).rotation_euler.z = math.radians(-5)
    cube("cropped_jacket_right_panel", (0.18, -0.29, 1.17), (0.13, 0.035, 0.43), m["cloth_alt"], bevel=0.018).rotation_euler.z = math.radians(5)
    cube("chest_emblem_socket", (0, -0.325, 1.33), (0.13, 0.024, 0.1), m["gold"], bevel=0.01)
    sphere("chest_emissive_core", (0, -0.36, 1.34), 0.055, m["glow"], segments=16, ring_count=8)

    ellipsoid("neck_soft_link", (0, 0, 1.61), 0.09, (0.7, 0.6, 1.0), m["skin"], segments=16, ring_count=8)
    ellipsoid("head_stylized_face_mass", (0, -0.02, 1.82), 0.28, (0.86, 0.78, 1.04), m["skin"], segments=32, ring_count=16)
    ellipsoid("hair_cap_layer", (0, 0.025, 1.92), 0.29, (0.92, 0.82, 0.52), m["hair"], segments=32, ring_count=12)
    for index, (x, y, z, rx, rz, length) in enumerate([
        (-0.18, -0.25, 1.83, 24, -18, 0.28),
        (-0.06, -0.29, 1.86, 18, -6, 0.34),
        (0.08, -0.29, 1.86, 18, 8, 0.33),
        (0.2, -0.24, 1.83, 24, 18, 0.27),
        (0.0, 0.16, 1.98, -12, 0, 0.38),
    ]):
        clump = cone("layered_hair_clump_" + str(index + 1), (x, y, z), 0.07, 0.01, length, m["hair"], vertices=7, bevel=0.006)
        clump.rotation_euler.x = math.radians(rx)
        clump.rotation_euler.z = math.radians(rz)
    cube("left_eye_ink_shape", (-0.085, -0.235, 1.85), (0.055, 0.012, 0.015), m["line"], bevel=0.004)
    cube("right_eye_ink_shape", (0.085, -0.235, 1.85), (0.055, 0.012, 0.015), m["line"], bevel=0.004)
    cube("face_highlight_bridge", (0, -0.246, 1.79), (0.018, 0.008, 0.045), m["soft"], bevel=0.004)

    for side_name, sx in (("L", -1), ("R", 1)):
        ellipsoid("shoulder_silhouette_" + side_name, (sx * 0.34, -0.01, 1.43), 0.16, (1.25, 0.72, 0.68), m["gold"], segments=20, ring_count=10, bevel=0.01)
        upper = cylinder("upper_arm_sleeve_" + side_name, (sx * 0.47, -0.015, 1.18), 0.07, 0.45, m["primary"], vertices=14, bevel=0.012)
        upper.rotation_euler.y = math.radians(17 * sx)
        fore = cylinder("forearm_glove_" + side_name, (sx * 0.59, -0.08, 0.9), 0.065, 0.38, m["dark"], vertices=14, bevel=0.012)
        fore.rotation_euler.y = math.radians(-12 * sx)
        sphere("hand_pose_block_" + side_name, (sx * 0.66, -0.13, 0.68), 0.07, m["skin"], segments=16, ring_count=8)
        thigh = cylinder("upper_leg_bootline_" + side_name, (sx * 0.14, 0.01, 0.46), 0.095, 0.52, m["primary"], vertices=14, bevel=0.012)
        thigh.rotation_euler.y = math.radians(-5 * sx)
        shin = cylinder("tall_boot_" + side_name, (sx * 0.18, -0.035, 0.2), 0.085, 0.42, m["dark"], vertices=14, bevel=0.012)
        shin.rotation_euler.y = math.radians(4 * sx)
        cube("boot_toe_shape_" + side_name, (sx * 0.2, -0.15, 0.02), (0.1, 0.16, 0.045), m["dark"], bevel=0.015)
        cube("calf_emissive_slash_" + side_name, (sx * 0.22, -0.12, 0.31), (0.025, 0.018, 0.15), m["glow"], bevel=0.006).rotation_euler.z = math.radians(-12 * sx)

    for index, sx in enumerate((-1, 1)):
        panel = cube("asymmetric_coat_tail_" + str(index + 1), (sx * 0.17, 0.12, 0.72), (0.11, 0.035, 0.46), m["cloth_alt"], bevel=0.012)
        panel.rotation_euler.x = math.radians(-8)
        panel.rotation_euler.z = math.radians(8 * sx)
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
    add_label("character_nameplate", SPEC["model_name"][:18], (0, -0.82, 0.08), m["glow"], size=0.15)


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
    PIPELINE_STATE = {{"export_objects": [], "actions": [], "textures": {{}}, "collections": [], "armature": "", "shape_keys": [], "sockets": [], "rig_controls": [], "lods": [], "vertex_groups": {{}}, "validation": {{}}, "camera_action": ""}}
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
            "pipeline": PIPELINE_STATE,
        }}, indent=2), encoding="utf-8")


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
    return {
        **job,
        "run": run_result,
        "registry": registry,
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
    "blender_modeling_paths",
    "build_blender_model_spec",
    "create_blender_authoring_job",
    "create_blender_model",
    "detect_blender_installation",
    "infer_blender_preset",
    "inspect_blender_modeling_workspace",
    "materialize_blender_workspace",
    "run_blender_script",
    "validate_blender_script_text",
]
