"""Migration helpers that absorb Godot, O3DE, and Ren'Py projects into Reverie Engine."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, Iterable
import json
import re
import shutil

from .config import ENGINE_NAME
from .project import create_project_skeleton
from .renpy_import import import_renpy_script, inspect_renpy_project
from .serialization import node_from_dict, pack_archetype, save_archetype, save_scene, scene_from_dict


PORTABLE_ASSET_EXTENSIONS = {
    ".avif",
    ".glb",
    ".gltf",
    ".jpeg",
    ".jpg",
    ".ogg",
    ".png",
    ".svg",
    ".wav",
    ".webp",
}


def _read_json(path: Path) -> Dict[str, Any]:
    if not path.is_file():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8", errors="replace"))
    except (OSError, json.JSONDecodeError):
        return {}
    return payload if isinstance(payload, dict) else {}


def _files(root: Path, patterns: Iterable[str]) -> list[Path]:
    found: list[Path] = []
    seen: set[str] = set()
    for pattern in patterns:
        for path in root.rglob(pattern):
            if not path.is_file():
                continue
            key = str(path.resolve(strict=False)).lower()
            if key not in seen:
                found.append(path)
                seen.add(key)
    return sorted(found)


def _write_json(path: Path, payload: Dict[str, Any]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def _slug(value: Any, fallback: str = "legacy") -> str:
    normalized = re.sub(r"[^A-Za-z0-9._-]+", "_", str(value or "").strip()).strip("._-").lower()
    return normalized or fallback


_GODOT_ATTRIBUTE_RE = re.compile(r"([A-Za-z_][A-Za-z0-9_]*)=(\"(?:\\.|[^\"])*\"|\[[^\]]*\]|[^\s]+)")
_GODOT_VECTOR_RE = re.compile(r"^(Vector[234]|Color)\((.*)\)$")
_GODOT_RESOURCE_RE = re.compile(r"^(ExtResource|SubResource)\(\"?([^\")]+)\"?\)$")


def _parse_godot_value(raw_value: str) -> Any:
    value = str(raw_value or "").strip()
    if not value:
        return ""
    resource_match = _GODOT_RESOURCE_RE.match(value)
    if resource_match:
        return {resource_match.group(1).lower(): resource_match.group(2)}
    vector_match = _GODOT_VECTOR_RE.match(value)
    if vector_match:
        values: list[float] = []
        for item in vector_match.group(2).split(","):
            try:
                values.append(float(item.strip()))
            except ValueError:
                return value
        return values
    if value.lower() in {"true", "false"}:
        return value.lower() == "true"
    if value.lower() in {"null", "nil"}:
        return None
    try:
        return json.loads(value)
    except (json.JSONDecodeError, TypeError):
        pass
    try:
        return float(value) if any(marker in value.lower() for marker in (".", "e")) else int(value)
    except ValueError:
        return value.strip('"')


def _godot_header_attributes(header: str) -> Dict[str, Any]:
    return {match.group(1): _parse_godot_value(match.group(2)) for match in _GODOT_ATTRIBUTE_RE.finditer(header)}


def _parse_godot_project(path: Path, source_root: Path) -> Dict[str, Any]:
    sections: Dict[str, Dict[str, Any]] = {"root": {}}
    active = sections["root"]
    for raw_line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        line = raw_line.strip()
        if not line or line.startswith((";", "#")):
            continue
        if line.startswith("[") and line.endswith("]"):
            section = line[1:-1].strip()
            active = sections.setdefault(section, {})
            continue
        if "=" in line:
            key, value = line.split("=", 1)
            active[key.strip()] = _parse_godot_value(value)
    return {
        "schema_version": "reverie.godot_project/1",
        "source_engine": "godot",
        "target_engine": ENGINE_NAME,
        "source_path": str(path.relative_to(source_root)).replace("\\", "/"),
        "sections": sections,
        "main_scene": str(sections.get("application", {}).get("run/main_scene") or ""),
        "input_actions": sorted(sections.get("input", {})),
        "autoloads": dict(sections.get("autoload", {})),
    }


def _godot_resource_path(value: Any, resources: Dict[str, Dict[str, Any]]) -> str:
    if not isinstance(value, dict) or "extresource" not in value:
        return ""
    resource = resources.get(str(value["extresource"])) or {}
    return str(resource.get("path") or "")


def _godot_node_components(
    godot_type: str,
    properties: Dict[str, Any],
    resources: Dict[str, Dict[str, Any]],
) -> tuple[str, list[Dict[str, Any]]]:
    position = properties.get("position") or properties.get("global_position") or [0.0, 0.0, 0.0]
    if isinstance(position, list) and len(position) == 2:
        position = [position[0], position[1], 0.0]
    scale = properties.get("scale") or [1.0, 1.0, 1.0]
    if isinstance(scale, list) and len(scale) == 2:
        scale = [scale[0], scale[1], 1.0]
    components: list[Dict[str, Any]] = [{"type": "Transform", "position": position, "scale": scale}]
    node_type = "Node"
    normalized = str(godot_type or "Node")

    if normalized.startswith("CharacterBody"):
        node_type = "Actor"
        components.extend(
            [
                {"type": "KinematicBody", "speed": float(properties.get("speed", 4.0) or 4.0)},
                {"type": "Collider", "shape": "capsule", "layer": "actor"},
            ]
        )
    elif normalized.startswith("RigidBody"):
        node_type = "Actor"
        components.extend(
            [
                {"type": "RigidBody", "mass": float(properties.get("mass", 1.0) or 1.0)},
                {"type": "Collider", "shape": "box", "layer": "physics"},
            ]
        )
    elif normalized.startswith("StaticBody"):
        node_type = "StaticBody"
        components.append({"type": "Collider", "shape": "box", "layer": "world"})
    elif normalized.startswith("Area") or normalized.startswith("CollisionShape"):
        node_type = "Trigger" if normalized.startswith("Area") else "Collider"
        components.append({"type": "Collider", "shape": "box", "is_trigger": normalized.startswith("Area")})
    elif normalized == "Camera2D":
        node_type = "Camera"
        components.append({"type": "Camera2D", "zoom": float(properties.get("zoom", 1.0) or 1.0)})
    elif normalized == "Camera3D":
        node_type = "Camera"
        components.append({"type": "Camera3D", "fov": float(properties.get("fov", 70.0) or 70.0)})
    elif "Light" in normalized:
        node_type = "Light"
        components.append(
            {
                "type": "Light",
                "light_type": "directional" if "Directional" in normalized else "point",
                "intensity": float(properties.get("light_energy", 1.0) or 1.0),
            }
        )
    elif normalized.startswith("Sprite"):
        node_type = "Sprite"
        components.append({"type": "Sprite", "texture": _godot_resource_path(properties.get("texture"), resources)})
    elif normalized.startswith("MeshInstance"):
        node_type = "Mesh"
        components.append({"type": "Mesh", "mesh": _godot_resource_path(properties.get("mesh"), resources) or "legacy_mesh"})
    elif normalized.startswith("AudioStreamPlayer"):
        node_type = "Audio"
        components.append(
            {
                "type": "AudioSource",
                "clip": _godot_resource_path(properties.get("stream"), resources),
                "loop": bool(properties.get("autoplay", False)),
            }
        )
    elif normalized == "AnimationPlayer":
        node_type = "Animator"
        components.append({"type": "Animator"})
    elif normalized.startswith("NavigationAgent"):
        node_type = "NavigationAgent"
        components.append({"type": "NavigationAgent", "speed": float(properties.get("max_speed", 2.0) or 2.0)})
    elif normalized.startswith("TileMap"):
        node_type = "TileMap"
        components.append({"type": "TileMap"})
    elif "Particles" in normalized:
        node_type = "ParticleSystem"
        components.append(
            {
                "type": "ParticleSystem",
                "amount": int(properties.get("amount", 100) or 100),
                "lifetime": float(properties.get("lifetime", 1.0) or 1.0),
            }
        )
    elif normalized in {"Control", "Container", "MarginContainer", "VBoxContainer", "HBoxContainer"}:
        node_type = "UI"
        components.append({"type": "UIControl"})
    elif normalized in {"Label", "RichTextLabel"}:
        node_type = "UI"
        components.extend([{"type": "UIControl"}, {"type": "TextLabel", "text": str(properties.get("text") or "")}])
    elif normalized in {"Button", "TextureButton"}:
        node_type = "UI"
        components.extend([{"type": "UIControl"}, {"type": "Button", "text": str(properties.get("text") or "")}])
    elif normalized in {"ProgressBar", "TextureProgressBar"}:
        node_type = "UI"
        components.extend(
            [
                {"type": "UIControl"},
                {
                    "type": "ProgressBar",
                    "min_value": float(properties.get("min_value", 0.0) or 0.0),
                    "max_value": float(properties.get("max_value", 100.0) or 100.0),
                    "value": float(properties.get("value", 0.0) or 0.0),
                },
            ]
        )

    script_path = _godot_resource_path(properties.get("script"), resources)
    if script_path:
        components.append(
            {
                "type": "ScriptBehaviour",
                "script": script_path,
                "params": {"language": "gdscript", "migration": "contract_only"},
            }
        )
    return node_type, components


def _convert_godot_scene(source_root: Path, scene_path: Path, target_root: Path) -> Dict[str, Any]:
    resources: Dict[str, Dict[str, Any]] = {}
    nodes: list[Dict[str, Any]] = []
    current: Dict[str, Any] | None = None
    for raw_line in scene_path.read_text(encoding="utf-8", errors="replace").splitlines():
        line = raw_line.strip()
        if not line or line.startswith(";"):
            continue
        if line.startswith("[") and line.endswith("]"):
            header = line[1:-1]
            kind, _, remainder = header.partition(" ")
            attributes = _godot_header_attributes(remainder)
            current = None
            if kind == "ext_resource":
                resources[str(attributes.get("id") or "")] = attributes
            elif kind == "node":
                current = {"attributes": attributes, "properties": {}}
                nodes.append(current)
            continue
        if current is not None and "=" in line:
            key, value = line.split("=", 1)
            current["properties"][key.strip()] = _parse_godot_value(value)

    scene_id = f"imported_godot_{_slug(scene_path.stem, 'scene')}"
    root_payload: Dict[str, Any] = {
        "name": scene_path.stem,
        "type": "Scene",
        "scene_id": scene_id,
        "metadata": {
            "legacy_engine": "godot",
            "source_path": str(scene_path.relative_to(source_root)).replace("\\", "/"),
        },
        "components": [{"type": "Transform"}],
        "children": [],
    }
    path_map: Dict[str, Dict[str, Any]] = {".": root_payload}
    for index, record in enumerate(nodes):
        attributes = dict(record.get("attributes") or {})
        properties = dict(record.get("properties") or {})
        name = str(attributes.get("name") or f"Node{index}")
        godot_type = str(attributes.get("type") or "Node")
        node_type, components = _godot_node_components(godot_type, properties, resources)
        groups = attributes.get("groups") if isinstance(attributes.get("groups"), list) else []
        converted = {
            "name": name,
            "type": "Scene" if index == 0 else node_type,
            "active": True,
            "tags": [],
            "groups": [str(item) for item in groups],
            "metadata": {
                "legacy_engine": "godot",
                "godot_type": godot_type,
                "godot_properties": properties,
            },
            "components": components,
            "children": [],
        }
        if index == 0:
            converted["scene_id"] = scene_id
            converted["metadata"].update(root_payload["metadata"])
            root_payload = converted
            path_map["."] = root_payload
            continue
        parent_path = str(attributes.get("parent") or ".")
        parent = path_map.get(parent_path, root_payload)
        parent.setdefault("children", []).append(converted)
        node_path = name if parent_path == "." else f"{parent_path}/{name}"
        path_map[node_path] = converted

    target_path = target_root / "data" / "scenes" / f"{scene_id}.relscene.json"
    save_scene(scene_from_dict(root_payload), target_path)
    return {
        "kind": "godot_scene",
        "source_path": str(scene_path),
        "target_path": str(target_path),
        "scene_id": scene_id,
        "node_count": len(nodes),
        "resource_count": len(resources),
    }


def _convert_godot_scripts(source_root: Path, target_root: Path) -> Dict[str, Any]:
    scripts: list[Dict[str, Any]] = []
    for script_path in _files(source_root, ("*.gd",)):
        text = script_path.read_text(encoding="utf-8", errors="replace")
        extends_match = re.search(r"(?m)^\s*extends\s+([^\s#]+)", text)
        class_match = re.search(r"(?m)^\s*class_name\s+([A-Za-z_][A-Za-z0-9_]*)", text)
        scripts.append(
            {
                "relative_path": str(script_path.relative_to(source_root)).replace("\\", "/"),
                "extends": extends_match.group(1) if extends_match else "",
                "class_name": class_match.group(1) if class_match else "",
                "signals": re.findall(r"(?m)^\s*signal\s+([A-Za-z_][A-Za-z0-9_]*)", text),
                "functions": re.findall(r"(?m)^\s*func\s+([A-Za-z_][A-Za-z0-9_]*)", text),
                "exports": re.findall(r"(?m)^\s*@export(?:_[A-Za-z0-9_]+)?\s+var\s+([A-Za-z_][A-Za-z0-9_]*)", text),
                "migration": "behaviour_contract",
            }
        )
    payload = {
        "schema_version": "reverie.godot_scripts/1",
        "source_engine": "godot",
        "target_engine": ENGINE_NAME,
        "scripts": scripts,
    }
    target_path = _write_json(target_root / "data" / "migration" / "godot_scripts.json", payload)
    return {"kind": "godot_script_contracts", "target_path": str(target_path), "script_count": len(scripts)}


def _convert_godot_project(source_root: Path, target_root: Path) -> list[Dict[str, Any]]:
    converted: list[Dict[str, Any]] = []
    project_candidates = [source_root / "project.godot", *_files(source_root, ("project.godot",))]
    project_path = next((path for path in project_candidates if path.is_file()), None)
    if project_path:
        contract = _parse_godot_project(project_path, source_root)
        target_path = _write_json(target_root / "data" / "migration" / "godot_project.json", contract)
        converted.append({"kind": "godot_project", "source_path": str(project_path), "target_path": str(target_path)})
    for scene_path in _files(source_root, ("*.tscn",)):
        converted.append(_convert_godot_scene(source_root, scene_path, target_root))
    converted.append(_convert_godot_scripts(source_root, target_root))
    return converted


def _script_inventory(source_root: Path, patterns: Iterable[str]) -> list[Dict[str, Any]]:
    scripts: list[Dict[str, Any]] = []
    for script_path in _files(source_root, patterns):
        text = script_path.read_text(encoding="utf-8", errors="replace")
        if script_path.suffix.lower() == ".lua":
            functions = re.findall(r"(?m)^\s*function\s+([A-Za-z_][A-Za-z0-9_:.]*)\s*\(", text)
            language = "lua"
        else:
            functions = re.findall(r"(?m)^\s*(?:async\s+)?def\s+([A-Za-z_][A-Za-z0-9_]*)\s*\(", text)
            language = "python"
        scripts.append(
            {
                "relative_path": str(script_path.relative_to(source_root)).replace("\\", "/"),
                "language": language,
                "functions": functions,
                "migration": "behaviour_contract",
            }
        )
    return scripts


def _convert_o3de_project(source_root: Path, target_root: Path) -> list[Dict[str, Any]]:
    project_candidates = [source_root / "project.json", *_files(source_root, ("project.json",))]
    project_path = next((path for path in project_candidates if path.is_file()), source_root / "project.json")
    project = _read_json(project_path)
    gem_manifests: list[Dict[str, Any]] = []
    for gem_path in _files(source_root, ("gem.json",)):
        manifest = _read_json(gem_path)
        manifest["relative_path"] = str(gem_path.relative_to(source_root)).replace("\\", "/")
        gem_manifests.append(manifest)

    registry: list[Dict[str, Any]] = []
    for path in _files(source_root, ("*.setreg", "*.setregpatch")):
        registry.append(
            {
                "relative_path": str(path.relative_to(source_root)).replace("\\", "/"),
                "data": _read_json(path),
            }
        )
    contract = {
        "schema_version": "reverie.o3de_project/1",
        "source_engine": "o3de",
        "target_engine": ENGINE_NAME,
        "project": project,
        "gems": gem_manifests,
        "registry": registry,
        "asset_pipeline": {
            "portable_formats": sorted(PORTABLE_ASSET_EXTENSIONS),
            "import_root": "assets/imported/o3de",
            "source_asset_count": len([path for path in source_root.rglob("*") if path.is_file() and path.suffix.lower() in PORTABLE_ASSET_EXTENSIONS]),
        },
    }
    contract_path = _write_json(target_root / "data" / "migration" / "o3de_project_contract.json", contract)
    converted: list[Dict[str, Any]] = [
        {"kind": "o3de_project_contract", "source_path": str(project_path), "target_path": str(contract_path)}
    ]

    gem_names = [str(item.get("gem_name") or item.get("display_name") or "").strip() for item in gem_manifests]
    for configured in project.get("gem_names") or []:
        if str(configured).strip() and str(configured).strip() not in gem_names:
            gem_names.append(str(configured).strip())
    for gem_name in gem_names:
        manifest = next((item for item in gem_manifests if str(item.get("gem_name") or "") == gem_name), {})
        archetype = pack_archetype(
            node_from_dict(
                {
                    "name": gem_name,
                    "type": "System",
                    "metadata": {"legacy_engine": "o3de", "gem_manifest": manifest},
                    "components": [
                        {
                            "type": "ScriptBehaviour",
                            "script": str(manifest.get("relative_path") or f"Gems/{gem_name}/gem.json"),
                            "params": {"runtime": ENGINE_NAME, "migration": "gem_contract"},
                        }
                    ],
                    "children": [],
                }
            ),
            archetype_id=f"o3de.{gem_name}",
            metadata={"source_engine": "o3de", "gem": gem_name},
        )
        archetype_path = target_root / "data" / "prefabs" / f"o3de_{_slug(gem_name, 'gem')}.relarchetype.json"
        save_archetype(archetype, archetype_path)
        converted.append(
            {"kind": "o3de_gem", "gem": gem_name, "target_path": str(archetype_path), "archetype_id": archetype.archetype_id}
        )

    scripts = _script_inventory(source_root, ("*.lua", "*.py"))
    scripts_path = _write_json(
        target_root / "data" / "migration" / "o3de_scripts.json",
        {
            "schema_version": "reverie.o3de_scripts/1",
            "source_engine": "o3de",
            "target_engine": ENGINE_NAME,
            "scripts": scripts,
        },
    )
    converted.append({"kind": "o3de_script_contracts", "target_path": str(scripts_path), "script_count": len(scripts)})
    return converted


def detect_legacy_project(project_root: str | Path) -> str:
    """Detect the legacy project family that should be migrated."""
    root = Path(project_root).expanduser().resolve(strict=False)
    if (root / "project.godot").is_file() or any(root.glob("**/project.godot")):
        return "godot"
    project_jsons = [root / "project.json", *_files(root, ("project.json",))]
    for project_json in project_jsons:
        payload = _read_json(project_json)
        if "gem_names" in payload or "project_id" in payload or (project_json.parent / "Gems").is_dir():
            return "o3de"
    if (root / "game").is_dir() and any((root / "game").rglob("*.rpy")):
        return "renpy"
    if any(root.rglob("*.rpy")):
        return "renpy"
    return ""


def inspect_legacy_project(project_root: str | Path) -> Dict[str, Any]:
    """Inspect a legacy source project and return a deterministic migration contract."""
    root = Path(project_root).expanduser().resolve(strict=False)
    if not root.is_dir():
        raise FileNotFoundError(f"Legacy project not found: {root}")
    source = detect_legacy_project(root)
    if not source:
        return {
            "detected": False,
            "source_engine": "",
            "target_engine": ENGINE_NAME,
            "project_root": str(root),
            "errors": ["No Godot, O3DE, or Ren'Py project markers were detected."],
        }

    portable_assets = [path for path in root.rglob("*") if path.is_file() and path.suffix.lower() in PORTABLE_ASSET_EXTENSIONS]
    details: Dict[str, Any] = {}
    untranslated: list[str] = []
    if source == "godot":
        project_file = next(
            (candidate for candidate in [root / "project.godot", *_files(root, ("project.godot",))] if candidate.is_file()),
            root / "project.godot",
        )
        details = {
            "project_file": str(project_file),
            "scene_count": len(_files(root, ("*.tscn", "*.scn"))),
            "script_count": len(_files(root, ("*.gd", "*.cs"))),
            "resource_count": len(_files(root, ("*.tres", "*.res"))),
        }
        untranslated = ["Godot scripts and native scene graphs require semantic review after asset migration."]
    elif source == "o3de":
        project_file = root / "project.json"
        if not project_file.is_file():
            candidates = _files(root, ("project.json",))
            project_file = candidates[0] if candidates else project_file
        project_payload = _read_json(project_file)
        details = {
            "project_file": str(project_file),
            "project_name": str(project_payload.get("project_name") or root.name),
            "gems": list(project_payload.get("gem_names") or []),
            "gem_manifest_count": len(_files(root, ("gem.json",))),
            "script_count": len(_files(root, ("*.lua", "*.py"))),
        }
        untranslated = ["O3DE Gem code and component entities require semantic review after data and asset migration."]
    else:
        details = inspect_renpy_project(root)
        untranslated = ["Embedded Python and custom Ren'Py screens require manual review when reported by the parser."]

    return {
        "detected": True,
        "source_engine": source,
        "target_engine": ENGINE_NAME,
        "project_root": str(root),
        "portable_assets": [str(path.relative_to(root)) for path in portable_assets],
        "portable_asset_count": len(portable_assets),
        "details": details,
        "migration_stages": [
            "create_reverie_project",
            "copy_portable_assets",
            "convert_supported_content",
            "validate_reverie_project",
        ],
        "manual_review": untranslated,
        "errors": [],
    }


def migrate_legacy_project(
    project_root: str | Path,
    output_dir: str | Path,
    *,
    project_name: str = "",
    overwrite: bool = False,
) -> Dict[str, Any]:
    """Create one Reverie Engine project from a supported legacy project source."""
    source_root = Path(project_root).expanduser().resolve(strict=False)
    target_root = Path(output_dir).expanduser().resolve(strict=False)
    inspection = inspect_legacy_project(source_root)
    if not inspection.get("detected"):
        raise ValueError("No supported legacy project markers were detected.")
    source = str(inspection["source_engine"])
    name = project_name or str(inspection.get("details", {}).get("project_name") or source_root.name)
    genre = "galgame" if source == "renpy" else "sandbox"
    dimension = "2D" if source == "renpy" else "3D"
    seed = create_project_skeleton(
        target_root,
        project_name=name,
        dimension=dimension,
        genre=genre,
        overwrite=overwrite,
    )

    copied_assets: list[str] = []
    for relative in inspection.get("portable_assets", []):
        source_path = (source_root / str(relative)).resolve(strict=False)
        target_path = (target_root / "assets" / "imported" / source / str(relative)).resolve(strict=False)
        if target_path.exists() and not overwrite:
            continue
        target_path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source_path, target_path)
        copied_assets.append(str(target_path))

    converted: list[Dict[str, Any]] = []
    conversion_errors: list[str] = []
    if source == "godot":
        try:
            converted.extend(_convert_godot_project(source_root, target_root))
        except Exception as exc:
            conversion_errors.append(f"Godot content conversion: {exc}")
    elif source == "o3de":
        try:
            converted.extend(_convert_o3de_project(source_root, target_root))
        except Exception as exc:
            conversion_errors.append(f"O3DE content conversion: {exc}")
    elif source == "renpy":
        scripts = [Path(path) for path in inspection.get("details", {}).get("scripts", [])]
        for index, relative in enumerate(scripts):
            script_path = relative if relative.is_absolute() else source_root / relative
            try:
                converted.append(
                    import_renpy_script(
                        target_root,
                        script_path,
                        autostart=index == 0,
                        overwrite=overwrite,
                    )
                )
            except Exception as exc:
                conversion_errors.append(f"{script_path}: {exc}")

    report = {
        "schema_version": "reverie.legacy_migration/1",
        "source_engine": source,
        "target_engine": ENGINE_NAME,
        "source_root": str(source_root),
        "target_root": str(target_root),
        "project_name": name,
        "copied_assets": copied_assets,
        "converted_content": converted,
        "conversion_errors": conversion_errors,
        "manual_review": list(inspection.get("manual_review", [])),
        "seed": seed,
        "success": not conversion_errors,
    }
    report_path = target_root / "data" / "migration" / f"{source}_migration.json"
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    report["report_path"] = str(report_path)
    return report


__all__ = [
    "PORTABLE_ASSET_EXTENSIONS",
    "detect_legacy_project",
    "inspect_legacy_project",
    "migrate_legacy_project",
]
