"""Scene and prefab serialization helpers for Reverie Engine."""

from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass, field
import json
from pathlib import Path
from typing import Any, Dict

from .components import component_from_dict
from .scene import Node, Scene


CURRENT_PACKED_SCENE_VERSION = 2
CURRENT_ARCHETYPE_DOCUMENT_VERSION = 1


@dataclass
class PackedSceneDocument:
    """Portable packed scene wrapper with versioning and local overrides."""

    scene_id: str
    root: Dict[str, Any]
    version: int = CURRENT_PACKED_SCENE_VERSION
    dependencies: list[str] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)
    overrides: list[Dict[str, Any]] = field(default_factory=list)
    format: str = "packed_scene"

    @classmethod
    def from_scene(
        cls,
        scene: Scene,
        *,
        version: int = CURRENT_PACKED_SCENE_VERSION,
        dependencies: list[str] | None = None,
        metadata: Dict[str, Any] | None = None,
        overrides: list[Dict[str, Any]] | None = None,
    ) -> "PackedSceneDocument":
        return cls(
            scene_id=scene.scene_id,
            root=scene_to_dict(scene),
            version=int(version),
            dependencies=list(dependencies or []),
            metadata=dict(metadata or {}),
            overrides=[dict(item) for item in (overrides or [])],
        )

    @classmethod
    def from_dict(cls, payload: Dict[str, Any]) -> "PackedSceneDocument":
        data = migrate_packed_scene_payload(payload)
        return cls(
            scene_id=str(data.get("scene_id") or data.get("root", {}).get("scene_id") or "main"),
            root=dict(data.get("root") or {}),
            version=int(data.get("version", CURRENT_PACKED_SCENE_VERSION)),
            dependencies=[str(item) for item in data.get("dependencies", []) if str(item).strip()],
            metadata=dict(data.get("metadata") or {}),
            overrides=[dict(item) for item in data.get("overrides", []) if isinstance(item, dict)],
            format=str(data.get("format") or "packed_scene"),
        )

    def to_dict(self) -> Dict[str, Any]:
        return {
            "format": self.format,
            "version": self.version,
            "scene_id": self.scene_id,
            "dependencies": list(self.dependencies),
            "metadata": dict(self.metadata),
            "overrides": [dict(item) for item in self.overrides],
            "root": deepcopy(self.root),
        }

    def instantiate(self, overrides: list[Dict[str, Any]] | None = None) -> Scene:
        merged_overrides = [dict(item) for item in self.overrides]
        merged_overrides.extend(dict(item) for item in (overrides or []))
        root_payload = apply_scene_overrides(self.root, merged_overrides)
        return scene_from_dict(root_payload)


@dataclass
class ArchetypeDocument:
    """Reusable entity blueprint document for AI-facing authoring flows."""

    archetype_id: str
    root: Dict[str, Any]
    version: int = CURRENT_ARCHETYPE_DOCUMENT_VERSION
    metadata: Dict[str, Any] = field(default_factory=dict)
    format: str = "archetype"

    @classmethod
    def from_node(
        cls,
        node: Node,
        *,
        archetype_id: str | None = None,
        metadata: Dict[str, Any] | None = None,
        version: int = CURRENT_ARCHETYPE_DOCUMENT_VERSION,
    ) -> "ArchetypeDocument":
        return cls(
            archetype_id=str(archetype_id or node.name),
            root=_normalize_node_payload(node.to_dict(), is_scene_root=False),
            version=int(version),
            metadata=dict(metadata or {}),
        )

    @classmethod
    def from_dict(cls, payload: Dict[str, Any]) -> "ArchetypeDocument":
        data = dict(payload or {})
        return cls(
            archetype_id=str(data.get("archetype_id") or data.get("root", {}).get("name") or "archetype"),
            root=_normalize_node_payload(dict(data.get("root") or {}), is_scene_root=False),
            version=int(data.get("version", CURRENT_ARCHETYPE_DOCUMENT_VERSION)),
            metadata=dict(data.get("metadata") or {}),
            format=str(data.get("format") or "archetype"),
        )

    def to_dict(self) -> Dict[str, Any]:
        return {
            "format": self.format,
            "version": self.version,
            "archetype_id": self.archetype_id,
            "metadata": dict(self.metadata),
            "root": deepcopy(self.root),
        }

    def instantiate(self, overrides: Dict[str, Any] | None = None) -> Node:
        payload = _normalize_node_payload(deepcopy(self.root), is_scene_root=False)
        patch = dict(overrides or {})
        if patch:
            if patch.get("name"):
                payload["name"] = str(patch["name"])
            if isinstance(patch.get("metadata"), dict):
                payload["metadata"] = _deep_merge_dict(payload.get("metadata") or {}, patch["metadata"])
            if isinstance(patch.get("set"), dict):
                preserved_children = payload.get("children", [])
                preserved_components = payload.get("components", [])
                merged = _deep_merge_dict(payload, patch["set"])
                merged["children"] = preserved_children
                merged["components"] = preserved_components
                payload = merged
            if isinstance(patch.get("component_overrides"), dict):
                _apply_component_overrides(payload, patch["component_overrides"])
            for child in patch.get("add_children", []) or []:
                if isinstance(child, dict):
                    payload.setdefault("children", []).append(_normalize_node_payload(child, is_scene_root=False))
        return node_from_dict(payload)


def _normalize_node_payload(payload: Dict[str, Any], *, is_scene_root: bool = False) -> Dict[str, Any]:
    node = dict(payload or {})
    if is_scene_root:
        node.setdefault("type", "Scene")
    node.setdefault("name", "Main" if is_scene_root else "Node")
    node.setdefault("type", "Scene" if is_scene_root else "Node")
    node["active"] = bool(node.get("active", True))
    node["tags"] = [str(item) for item in node.get("tags", []) if str(item).strip()]
    node["groups"] = [str(item) for item in node.get("groups", []) if str(item).strip()]
    node["metadata"] = dict(node.get("metadata") or {})
    node["components"] = [
        dict(component) for component in node.get("components", []) if isinstance(component, dict)
    ]
    node["children"] = [
        _normalize_node_payload(child, is_scene_root=False)
        for child in node.get("children", [])
        if isinstance(child, dict)
    ]
    if is_scene_root:
        node["scene_id"] = str(node.get("scene_id") or "main")
    return node


def _deep_merge_dict(base: Dict[str, Any], patch: Dict[str, Any]) -> Dict[str, Any]:
    merged = dict(base or {})
    for key, value in (patch or {}).items():
        existing = merged.get(key)
        if isinstance(existing, dict) and isinstance(value, dict):
            merged[key] = _deep_merge_dict(existing, value)
        else:
            merged[key] = deepcopy(value)
    return merged


def _split_node_path(path: str | None, root_name: str) -> list[str]:
    raw = str(path or "").strip().replace("\\", "/")
    if raw in {"", ".", "/"}:
        return []
    segments = [segment for segment in raw.split("/") if segment and segment != "."]
    if segments and segments[0] == root_name:
        segments = segments[1:]
    return segments


def _find_node_payload(root: Dict[str, Any], path: str | None) -> Dict[str, Any] | None:
    current = root
    for segment in _split_node_path(path, str(root.get("name") or "Main")):
        current = next(
            (child for child in current.get("children", []) if child.get("name") == segment),
            None,
        )
        if current is None:
            return None
    return current


def _find_parent_and_index(root: Dict[str, Any], path: str | None) -> tuple[Dict[str, Any] | None, int]:
    segments = _split_node_path(path, str(root.get("name") or "Main"))
    if not segments:
        return None, -1
    parent = root
    for segment in segments[:-1]:
        parent = next(
            (child for child in parent.get("children", []) if child.get("name") == segment),
            None,
        )
        if parent is None:
            return None, -1
    for index, child in enumerate(parent.get("children", [])):
        if child.get("name") == segments[-1]:
            return parent, index
    return None, -1


def _resolve_override_path(root: Dict[str, Any], target_path: str | None, child_path: str) -> str:
    raw = str(child_path or "").strip()
    if raw.startswith("/"):
        return raw
    target_segments = _split_node_path(target_path, str(root.get("name") or "Main"))
    child_segments = _split_node_path(raw, "")
    merged_segments = target_segments + child_segments
    return "/" + "/".join([str(root.get("name") or "Main"), *merged_segments]).strip("/")


def _apply_component_overrides(node: Dict[str, Any], patches: Dict[str, Any]) -> None:
    components = [dict(component) for component in node.get("components", []) if isinstance(component, dict)]
    by_type = {str(component.get("type") or ""): component for component in components}

    for component_type, patch in (patches or {}).items():
        component_name = str(component_type).strip()
        if not component_name:
            continue
        if patch is None:
            components = [component for component in components if component.get("type") != component_name]
            by_type.pop(component_name, None)
            continue

        existing = by_type.get(component_name, {"type": component_name})
        if component_name == "Transform" and isinstance(patch, dict):
            merged = dict(existing)
            transform_patch = dict(patch)
            if "transform" in merged or any(
                key in transform_patch for key in ("position", "rotation", "scale", "quaternion")
            ):
                base_transform = dict(merged.get("transform") or {})
                if "transform" in transform_patch and isinstance(transform_patch["transform"], dict):
                    base_transform = _deep_merge_dict(base_transform, transform_patch.pop("transform"))
                base_transform = _deep_merge_dict(base_transform, transform_patch)
                merged["transform"] = base_transform
                patch = {}
            existing = merged

        merged_component = _deep_merge_dict(existing, dict(patch))
        merged_component["type"] = component_name
        by_type[component_name] = merged_component

        replaced = False
        for index, component in enumerate(components):
            if component.get("type") == component_name:
                components[index] = merged_component
                replaced = True
                break
        if not replaced:
            components.append(merged_component)

    node["components"] = components


def apply_scene_overrides(
    root_payload: Dict[str, Any],
    overrides: list[Dict[str, Any]] | None = None,
) -> Dict[str, Any]:
    """Apply local packed-scene overrides to a serialized scene payload."""
    root = _normalize_node_payload(deepcopy(root_payload), is_scene_root=True)

    for override in overrides or []:
        if not isinstance(override, dict):
            continue

        target_path = str(override.get("target_path") or override.get("target") or "/").strip() or "/"
        if override.get("delete"):
            parent, index = _find_parent_and_index(root, target_path)
            if parent is not None and index >= 0:
                parent["children"].pop(index)
            continue

        target = _find_node_payload(root, target_path)
        if target is None:
            continue

        node_patch = dict(override.get("set") or override.get("properties") or {})
        if node_patch:
            preserved_children = target.get("children", [])
            preserved_components = target.get("components", [])
            merged = _deep_merge_dict(target, node_patch)
            merged["children"] = preserved_children
            merged["components"] = preserved_components
            target.clear()
            target.update(merged)

        metadata_patch = override.get("metadata")
        if isinstance(metadata_patch, dict):
            target["metadata"] = _deep_merge_dict(dict(target.get("metadata") or {}), metadata_patch)

        for tag in override.get("tags_add", []) or []:
            value = str(tag).strip()
            if value and value not in target["tags"]:
                target["tags"].append(value)
        remove_tags = {str(tag).strip() for tag in override.get("tags_remove", []) or [] if str(tag).strip()}
        if remove_tags:
            target["tags"] = [tag for tag in target["tags"] if tag not in remove_tags]

        for group in override.get("groups_add", []) or []:
            value = str(group).strip()
            if value and value not in target["groups"]:
                target["groups"].append(value)
        remove_groups = {
            str(group).strip() for group in override.get("groups_remove", []) or [] if str(group).strip()
        }
        if remove_groups:
            target["groups"] = [group for group in target["groups"] if group not in remove_groups]

        component_patches = override.get("component_overrides") or override.get("components")
        if isinstance(component_patches, dict):
            _apply_component_overrides(target, component_patches)

        add_children = override.get("add_children") or []
        if add_children:
            for child in add_children:
                if isinstance(child, dict):
                    target["children"].append(_normalize_node_payload(child, is_scene_root=False))

        for child_path in override.get("remove_children", []) or []:
            resolved = _resolve_override_path(root, target_path, str(child_path))
            parent, index = _find_parent_and_index(root, resolved)
            if parent is not None and index >= 0:
                parent["children"].pop(index)

    return root


def migrate_packed_scene_payload(payload: Dict[str, Any]) -> Dict[str, Any]:
    """Migrate older packed-scene payloads to the current document version."""
    data = deepcopy(dict(payload or {}))
    version = int(data.get("version", 1) or 1)

    if version <= 1:
        metadata = dict(data.get("metadata") or {})
        if "overrides" not in data and isinstance(data.get("instance_overrides"), list):
            data["overrides"] = list(data.get("instance_overrides") or [])
        if "overrides" not in data and isinstance(metadata.get("instance_overrides"), list):
            data["overrides"] = list(metadata.pop("instance_overrides") or [])
        data["metadata"] = metadata
        version = 2

    data["format"] = str(data.get("format") or "packed_scene")
    data["version"] = max(version, CURRENT_PACKED_SCENE_VERSION)
    data["dependencies"] = [str(item) for item in data.get("dependencies", []) if str(item).strip()]
    data["metadata"] = dict(data.get("metadata") or {})
    data["overrides"] = [dict(item) for item in data.get("overrides", []) if isinstance(item, dict)]
    data["root"] = _normalize_node_payload(dict(data.get("root") or {}), is_scene_root=True)
    if "scene_id" not in data:
        data["scene_id"] = str(data["root"].get("scene_id") or "main")
    return data


def node_from_dict(payload: Dict[str, Any]) -> Node:
    payload = dict(payload or {})
    node_type = str(payload.get("type", "Node"))
    scene_id = str(payload.get("scene_id", "main"))
    if node_type == "Scene":
        node: Node = Scene(
            payload.get("name", "Main"),
            scene_id=scene_id,
            metadata=payload.get("metadata") or {},
            tags=payload.get("tags") or [],
            groups=payload.get("groups") or [],
            process_mode=payload.get("process_mode") or Node.PROCESS_MODE_ALWAYS,
            active=payload.get("active", True),
        )
    else:
        node = Node(
            payload.get("name", "Node"),
            node_type=node_type,
            metadata=payload.get("metadata") or {},
            tags=payload.get("tags") or [],
            groups=payload.get("groups") or [],
            process_mode=payload.get("process_mode") or Node.PROCESS_MODE_INHERIT,
            active=payload.get("active", True),
        )

    for component_payload in payload.get("components", []):
        node.add_component(component_from_dict(component_payload))

    for child_payload in payload.get("children", []):
        node.add_child(node_from_dict(child_payload))
    return node


def scene_from_dict(payload: Dict[str, Any]) -> Scene:
    scene = node_from_dict(_normalize_node_payload(dict(payload or {}), is_scene_root=True))
    if isinstance(scene, Scene):
        return scene
    fallback = Scene(payload.get("name", "Main"), scene_id=payload.get("scene_id", "main"))
    for child in scene.children:
        fallback.add_child(child)
    return fallback


def scene_to_dict(scene: Scene) -> Dict[str, Any]:
    return scene.to_dict()


def load_scene(path: str | Path) -> Scene:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    if str(payload.get("format", "")).strip().lower() == "packed_scene":
        return PackedSceneDocument.from_dict(payload).instantiate()
    return scene_from_dict(payload)


def save_scene(scene: Scene, path: str | Path) -> Path:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(scene_to_dict(scene), indent=2, ensure_ascii=False), encoding="utf-8")
    return target


def pack_scene(
    scene: Scene,
    *,
    version: int = CURRENT_PACKED_SCENE_VERSION,
    dependencies: list[str] | None = None,
    metadata: Dict[str, Any] | None = None,
    overrides: list[Dict[str, Any]] | None = None,
) -> PackedSceneDocument:
    return PackedSceneDocument.from_scene(
        scene,
        version=version,
        dependencies=dependencies,
        metadata=metadata,
        overrides=overrides,
    )


def pack_archetype(
    node: Node,
    *,
    archetype_id: str | None = None,
    metadata: Dict[str, Any] | None = None,
    version: int = CURRENT_ARCHETYPE_DOCUMENT_VERSION,
) -> ArchetypeDocument:
    return ArchetypeDocument.from_node(
        node,
        archetype_id=archetype_id,
        metadata=metadata,
        version=version,
    )


def load_packed_scene(path: str | Path) -> PackedSceneDocument:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    return PackedSceneDocument.from_dict(payload)


def load_archetype(path: str | Path) -> ArchetypeDocument:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    return ArchetypeDocument.from_dict(payload)


def save_packed_scene(document: PackedSceneDocument, path: str | Path) -> Path:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(document.to_dict(), indent=2, ensure_ascii=False), encoding="utf-8")
    return target


def save_archetype(document: ArchetypeDocument, path: str | Path) -> Path:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(document.to_dict(), indent=2, ensure_ascii=False), encoding="utf-8")
    return target


def load_prefab(path: str | Path) -> Node:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    return node_from_dict(payload)


def save_prefab(node: Node, path: str | Path) -> Path:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(node.to_dict(), indent=2, ensure_ascii=False), encoding="utf-8")
    return target


def validate_scene_document(payload: Dict[str, Any]) -> list[str]:
    errors: list[str] = []

    wrapper = dict(payload or {})
    if str(wrapper.get("format", "")).strip().lower() == "packed_scene":
        if not isinstance(wrapper.get("root"), dict):
            return ["packed scene root must be an object"]
        if "version" in wrapper and not isinstance(wrapper.get("version"), int):
            errors.append("packed scene version must be an integer")
        if "dependencies" in wrapper and not isinstance(wrapper.get("dependencies"), list):
            errors.append("packed scene dependencies must be a list")
        if "overrides" in wrapper and not isinstance(wrapper.get("overrides"), list):
            errors.append("packed scene overrides must be a list")
        for index, override in enumerate(wrapper.get("overrides", []) or []):
            if not isinstance(override, dict):
                errors.append(f"packed scene override[{index}] must be an object")
                continue
            if "target_path" in override and not isinstance(override.get("target_path"), str):
                errors.append(f"packed scene override[{index}].target_path must be a string")
            if "metadata" in override and not isinstance(override.get("metadata"), dict):
                errors.append(f"packed scene override[{index}].metadata must be an object")
            if "component_overrides" in override and not isinstance(override.get("component_overrides"), dict):
                errors.append(f"packed scene override[{index}].component_overrides must be an object")
            if "add_children" in override and not isinstance(override.get("add_children"), list):
                errors.append(f"packed scene override[{index}].add_children must be a list")
        payload = dict(wrapper.get("root") or {})

    def _validate_node(node: Dict[str, Any], path: str) -> None:
        node_type = str(node.get("type", ""))
        if not str(node.get("name", "")).strip():
            errors.append(f"{path} requires a non-empty name")
        if not isinstance(node.get("components", []), list):
            errors.append(f"{path} components must be a list")
        if not isinstance(node.get("children", []), list):
            errors.append(f"{path} children must be a list")
            return
        if "groups" in node and not isinstance(node.get("groups"), list):
            errors.append(f"{path} groups must be a list")
        if "process_mode" in node and not isinstance(node.get("process_mode"), str):
            errors.append(f"{path} process_mode must be a string")
        for index, child in enumerate(node.get("children", [])):
            if not isinstance(child, dict):
                errors.append(f"{path}.children[{index}] must be an object")
                continue
            _validate_node(child, f"{path}.{node_type or 'Node'}[{index}]")

    if str(payload.get("type", "")) != "Scene":
        errors.append("scene root must declare type=Scene")
    _validate_node(payload, "scene root")
    return errors


def validate_archetype_document(payload: Dict[str, Any]) -> list[str]:
    wrapper = dict(payload or {})
    errors: list[str] = []
    if str(wrapper.get("format", "")).strip().lower() not in {"", "archetype"}:
        errors.append("archetype format must be 'archetype'")
    if "version" in wrapper and not isinstance(wrapper.get("version"), int):
        errors.append("archetype version must be an integer")
    if not str(wrapper.get("archetype_id", "")).strip():
        errors.append("archetype_id requires a non-empty value")
    root = dict(wrapper.get("root") or {})
    if not root:
        errors.append("archetype root must be an object")
        return errors
    if str(root.get("type", "")).strip() == "Scene":
        errors.append("archetype root cannot declare type=Scene")
    if not str(root.get("name", "")).strip():
        errors.append("archetype root requires a non-empty name")
    if not isinstance(root.get("components", []), list):
        errors.append("archetype root components must be a list")
    if not isinstance(root.get("children", []), list):
        errors.append("archetype root children must be a list")
    return errors
