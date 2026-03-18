"""Schema definitions and validation helpers for Reverie Engine project files."""

from __future__ import annotations

from typing import Any, Dict, Iterable

from .config import ENGINE_ALIASES, ENGINE_BRAND, SUPPORTED_DIMENSIONS


ENGINE_CONFIG_SCHEMA: Dict[str, Any] = {
    "type": "object",
    "required": ["project", "runtime", "modules", "capabilities", "live2d", "content"],
    "properties": {
        "project": {
            "type": "object",
            "required": ["name", "engine", "dimension", "genre", "brand"],
            "properties": {
                "name": {"type": "string", "min_length": 1},
                "engine": {"type": "string", "enum": list(ENGINE_ALIASES)},
                "dimension": {"type": "string", "enum": list(SUPPORTED_DIMENSIONS)},
                "genre": {"type": "string", "min_length": 1},
                "brand": {"type": "string", "const": ENGINE_BRAND},
            },
        },
        "runtime": {
            "type": "object",
            "required": [
                "entry_scene",
                "fixed_step",
                "target_fps",
                "window_title",
                "headless_default",
                "deterministic_smoke_frames",
                "sample_name",
                "genre",
            ],
            "properties": {
                "entry_scene": {"type": "string", "min_length": 1},
                "fixed_step": {"type": "number", "minimum": 0.0001},
                "target_fps": {"type": "integer", "minimum": 1},
                "window_title": {"type": "string", "min_length": 1},
                "headless_default": {"type": "boolean"},
                "deterministic_smoke_frames": {"type": "integer", "minimum": 1},
                "sample_name": {"type": "string"},
                "genre": {"type": "string", "min_length": 1},
            },
        },
        "modules": {
            "type": "array",
            "min_items": 1,
            "items": {"type": "string", "min_length": 1},
        },
        "capabilities": {
            "type": "object",
            "required": [
                "modules",
                "supports_2d",
                "supports_2_5d",
                "supports_3d",
                "supports_dialogue",
                "supports_quests",
                "supports_tower_defense",
                "supports_live2d",
                "supports_save_data",
                "supports_ai_agents",
                "supports_ui",
            ],
            "properties": {
                "modules": {
                    "type": "array",
                    "min_items": 1,
                    "items": {"type": "string", "min_length": 1},
                },
                "supports_2d": {"type": "boolean"},
                "supports_2_5d": {"type": "boolean"},
                "supports_3d": {"type": "boolean"},
                "supports_dialogue": {"type": "boolean"},
                "supports_quests": {"type": "boolean"},
                "supports_tower_defense": {"type": "boolean"},
                "supports_live2d": {"type": "boolean"},
                "supports_save_data": {"type": "boolean"},
                "supports_ai_agents": {"type": "boolean"},
                "supports_ui": {"type": "boolean"},
            },
        },
        "live2d": {
            "type": "object",
            "required": ["enabled", "renderer", "sdk_candidates", "manifest_path", "models_dir"],
            "properties": {
                "enabled": {"type": "boolean"},
                "renderer": {"type": "string", "enum": ["web", "native", "headless"]},
                "sdk_candidates": {
                    "type": "array",
                    "min_items": 1,
                    "items": {"type": "string", "min_length": 1},
                },
                "manifest_path": {"type": "string", "min_length": 1},
                "models_dir": {"type": "string", "min_length": 1},
            },
        },
        "content": {
            "type": "object",
            "required": ["scene_format", "prefab_format", "config_format", "data_driven", "content_bundle_paths"],
            "properties": {
                "scene_format": {"type": "string", "min_length": 1},
                "prefab_format": {"type": "string", "min_length": 1},
                "config_format": {"type": "string", "min_length": 1},
                "data_driven": {"type": "boolean"},
                "content_bundle_paths": {
                    "type": "array",
                    "min_items": 1,
                    "items": {"type": "string", "min_length": 1},
                },
            },
        },
    },
}


GAMEPLAY_MANIFEST_SCHEMA: Dict[str, Any] = {
    "type": "object",
    "required": ["project", "dimension", "genre", "systems", "economy"],
    "properties": {
        "project": {"type": "string", "min_length": 1},
        "dimension": {"type": "string", "enum": list(SUPPORTED_DIMENSIONS)},
        "genre": {"type": "string", "min_length": 1},
        "systems": {
            "type": "object",
            "required": ["dialogue", "quests", "tower_defense", "live2d"],
            "properties": {
                "dialogue": {"type": "boolean"},
                "quests": {"type": "boolean"},
                "tower_defense": {"type": "boolean"},
                "live2d": {"type": "boolean"},
            },
        },
        "economy": {
            "type": "object",
            "required": ["starting_resources"],
            "properties": {
                "starting_resources": {
                    "type": "object",
                    "required": ["gold", "lives"],
                    "properties": {
                        "gold": {"type": "integer", "minimum": 0},
                        "lives": {"type": "integer", "minimum": 0},
                    },
                }
            },
        },
    },
}


def _type_name(value: Any) -> str:
    if isinstance(value, bool):
        return "boolean"
    if isinstance(value, int):
        return "integer"
    if isinstance(value, float):
        return "number"
    if isinstance(value, str):
        return "string"
    if isinstance(value, list):
        return "array"
    if isinstance(value, dict):
        return "object"
    return type(value).__name__


def _matches_type(value: Any, expected: str) -> bool:
    if expected == "object":
        return isinstance(value, dict)
    if expected == "array":
        return isinstance(value, list)
    if expected == "string":
        return isinstance(value, str)
    if expected == "boolean":
        return isinstance(value, bool)
    if expected == "integer":
        return isinstance(value, int) and not isinstance(value, bool)
    if expected == "number":
        return (isinstance(value, int) and not isinstance(value, bool)) or isinstance(value, float)
    return False


def _validate_node(value: Any, schema: Dict[str, Any], path: str, errors: list[str]) -> None:
    expected_type = schema.get("type")
    if expected_type and not _matches_type(value, str(expected_type)):
        errors.append(f"{path}: expected {expected_type}, got {_type_name(value)}")
        return

    if "const" in schema and value != schema["const"]:
        errors.append(f"{path}: expected constant {schema['const']!r}, got {value!r}")

    if "enum" in schema and value not in schema["enum"]:
        errors.append(f"{path}: expected one of {schema['enum']!r}, got {value!r}")

    if isinstance(value, str):
        min_length = schema.get("min_length")
        if min_length is not None and len(value.strip()) < int(min_length):
            errors.append(f"{path}: expected non-empty string with min length {min_length}")

    if isinstance(value, (int, float)) and not isinstance(value, bool):
        minimum = schema.get("minimum")
        if minimum is not None and float(value) < float(minimum):
            errors.append(f"{path}: expected value >= {minimum}, got {value}")

    if isinstance(value, list):
        min_items = schema.get("min_items")
        if min_items is not None and len(value) < int(min_items):
            errors.append(f"{path}: expected at least {min_items} items")
        item_schema = schema.get("items")
        if isinstance(item_schema, dict):
            for index, item in enumerate(value):
                _validate_node(item, item_schema, f"{path}[{index}]", errors)

    if isinstance(value, dict):
        required = [str(item) for item in schema.get("required") or []]
        for key in required:
            if key not in value:
                errors.append(f"{path}: missing required key '{key}'")

        properties = dict(schema.get("properties") or {})
        for key, child_schema in properties.items():
            if key in value and isinstance(child_schema, dict):
                _validate_node(value[key], child_schema, f"{path}.{key}", errors)


def validate_document_schema(payload: Dict[str, Any], schema: Dict[str, Any], *, root_name: str) -> list[str]:
    errors: list[str] = []
    _validate_node(dict(payload or {}), schema, root_name, errors)
    return errors


def validate_engine_config_schema(payload: Dict[str, Any]) -> list[str]:
    return validate_document_schema(payload, ENGINE_CONFIG_SCHEMA, root_name="engine.yaml")


def validate_gameplay_manifest_schema(payload: Dict[str, Any]) -> list[str]:
    return validate_document_schema(payload, GAMEPLAY_MANIFEST_SCHEMA, root_name="gameplay_manifest.yaml")


def summarize_schema_required_keys(schema: Dict[str, Any]) -> Dict[str, Iterable[str]]:
    properties = dict(schema.get("properties") or {})
    return {key: list((definition or {}).get("required") or []) for key, definition in properties.items()}
