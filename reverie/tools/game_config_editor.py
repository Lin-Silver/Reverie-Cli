from typing import Optional, Dict, Any, List
from pathlib import Path
import json
import xml.etree.ElementTree as ET

from .base import BaseTool, ToolResult


class GameConfigEditorTool(BaseTool):
    name = "game_config_editor"
    description = "Edit game configuration files (JSON/YAML/XML) with validation and templates."

    parameters = {
        "type": "object",
        "properties": {
            "action": {
                "type": "string",
                "enum": ["read", "edit", "validate", "generate_template", "merge"],
                "description": "Config editing action"
            },
            "config_path": {"type": "string", "description": "Path to config file"},
            "config_type": {"type": "string", "enum": ["json", "yaml", "xml"], "description": "Config type"},
            "template_kind": {"type": "string", "description": "Template kind (player_stats, enemies, items, levels)"},
            "data": {"type": "object", "description": "Full data to write"},
            "edits": {
                "type": "array",
                "items": {"type": "object"},
                "description": "Edits to apply (list of {path, value})"
            },
            "required_keys": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Required keys for validation (supports dot paths)"
            }
        },
        "required": ["action"]
    }

    def __init__(self, context: Optional[Dict] = None):
        super().__init__(context)
        self.project_root = Path(context.get("project_root")) if context and context.get("project_root") else Path.cwd()

    def execute(self, **kwargs) -> ToolResult:
        action = kwargs.get("action")
        config_path = kwargs.get("config_path")
        config_type = kwargs.get("config_type")

        # Check for unknown action first
        valid_actions = ["read", "edit", "validate", "generate_template", "merge"]
        if action not in valid_actions:
            return ToolResult.fail(f"Unknown action: {action}")

        if action in ["read", "edit", "validate", "merge"] and not config_path:
            return ToolResult.fail("config_path is required")

        if action == "generate_template":
            template_kind = kwargs.get("template_kind", "player_stats")
            template = self._generate_template(template_kind)
            return ToolResult.ok(template, {"template": template})

        path = self._resolve_path(config_path)
        if action == "read":
            try:
                data = self._read_config(path, config_type)
                return ToolResult.ok(json.dumps(data, indent=2), {"data": data})
            except FileNotFoundError:
                return ToolResult.fail(f"Config file not found: {config_path}")
            except Exception as exc:
                return ToolResult.fail(f"Error reading config: {str(exc)}")

        if action == "validate":
            try:
                data = self._read_config(path, config_type)
                required_keys = kwargs.get("required_keys") or []
                missing = self._validate_required(data, required_keys)
                if missing:
                    return ToolResult.fail(f"Missing required keys: {', '.join(missing)}")
            except FileNotFoundError:
                return ToolResult.fail(f"Config file not found: {config_path}")
            except Exception as exc:
                return ToolResult.fail(str(exc))
            return ToolResult.ok("Config is valid.")

        if action == "edit":
            try:
                data = self._read_config(path, config_type)
                edits = kwargs.get("edits") or []
                for edit in edits:
                    self._apply_edit(data, edit.get("path"), edit.get("value"))
                full_data = kwargs.get("data") or data
                self._write_config(path, full_data, config_type)
                return ToolResult.ok(f"Updated config: {path}")
            except FileNotFoundError:
                return ToolResult.fail(f"Config file not found: {config_path}")
            except Exception as exc:
                return ToolResult.fail(f"Error editing config: {str(exc)}")

        if action == "merge":
            try:
                data = self._read_config(path, config_type)
                overrides = kwargs.get("data") or {}
                merged = self._deep_merge(data, overrides)
                self._write_config(path, merged, config_type)
                return ToolResult.ok(f"Merged config into {path}")
            except FileNotFoundError:
                return ToolResult.fail(f"Config file not found: {config_path}")
            except Exception as exc:
                return ToolResult.fail(f"Error merging config: {str(exc)}")

        return ToolResult.fail(f"Unknown action: {action}")

    def _read_config(self, path: Path, config_type: Optional[str]) -> Dict[str, Any]:
        config_type = config_type or self._infer_type(path)
        if config_type == "json":
            return json.loads(path.read_text(encoding="utf-8"))
        if config_type == "yaml":
            return self._read_yaml(path)
        if config_type == "xml":
            return self._read_xml(path)
        raise ValueError("Unsupported config type")

    def _write_config(self, path: Path, data: Dict[str, Any], config_type: Optional[str]) -> None:
        config_type = config_type or self._infer_type(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        if config_type == "json":
            path.write_text(json.dumps(data, indent=2), encoding="utf-8")
            return
        if config_type == "yaml":
            path.write_text(self._dump_yaml(data), encoding="utf-8")
            return
        if config_type == "xml":
            path.write_text(self._dump_xml(data), encoding="utf-8")
            return
        raise ValueError("Unsupported config type")

    def _infer_type(self, path: Path) -> str:
        if path.suffix.lower() in [".yaml", ".yml"]:
            return "yaml"
        if path.suffix.lower() == ".xml":
            return "xml"
        return "json"

    def _apply_edit(self, data: Dict[str, Any], path: Optional[str], value: Any) -> None:
        if not path:
            return
        keys = path.split(".")
        current = data
        for key in keys[:-1]:
            if key not in current or not isinstance(current[key], dict):
                current[key] = {}
            current = current[key]
        current[keys[-1]] = value

    def _generate_template(self, template_kind: str) -> str:
        if template_kind == "enemies":
            return json.dumps({
                "enemies": [
                    {"name": "Slime", "hp": 20, "attack": 4, "defense": 1, "xp": 5}
                ]
            }, indent=2)
        if template_kind == "items":
            return json.dumps({
                "items": [
                    {"name": "Potion", "type": "consumable", "effect": "heal", "value": 25}
                ]
            }, indent=2)
        if template_kind == "levels":
            return json.dumps({
                "levels": [
                    {"id": "level_1", "difficulty": 1, "layout": "level_1.json"}
                ]
            }, indent=2)
        return json.dumps({
            "player_stats": {
                "hp": 100,
                "attack": 10,
                "defense": 5,
                "speed": 6
            }
        }, indent=2)

    def _read_yaml(self, path: Path) -> Dict[str, Any]:
        text = path.read_text(encoding="utf-8")
        data: Dict[str, Any] = {}
        stack = [(0, data)]
        for raw_line in text.splitlines():
            if not raw_line.strip() or raw_line.strip().startswith("#"):
                continue
            indent = len(raw_line) - len(raw_line.lstrip(" "))
            line = raw_line.strip()
            while stack and indent < stack[-1][0]:
                stack.pop()
            current = stack[-1][1]
            if line.startswith("- "):
                value = self._coerce_value(line[2:].strip())
                if not isinstance(current, list):
                    # Convert current mapping to list if needed
                    if isinstance(current, dict):
                        if "_list" not in current:
                            current["_list"] = []
                        current = current["_list"]
                        stack[-1] = (stack[-1][0], current)
                current.append(value)
                continue
            if ":" in line:
                key, val = line.split(":", 1)
                key = key.strip()
                val = val.strip()
                if val == "":
                    current[key] = {}
                    stack.append((indent + 2, current[key]))
                else:
                    current[key] = self._coerce_value(val)
        return data

    def _dump_yaml(self, data: Dict[str, Any], indent: int = 0) -> str:
        lines = []
        for key, value in data.items():
            if isinstance(value, dict):
                lines.append(" " * indent + f"{key}:")
                lines.append(self._dump_yaml(value, indent + 2))
            elif isinstance(value, list):
                lines.append(" " * indent + f"{key}:")
                for item in value:
                    lines.append(" " * (indent + 2) + f"- {item}")
            else:
                lines.append(" " * indent + f"{key}: {value}")
        return "\n".join([line for line in lines if line is not None])

    def _read_xml(self, path: Path) -> Dict[str, Any]:
        root = ET.parse(path).getroot()
        return self._xml_to_dict(root)

    def _dump_xml(self, data: Dict[str, Any]) -> str:
        root = ET.Element("config")
        self._dict_to_xml(root, data)
        return ET.tostring(root, encoding="unicode")

    def _xml_to_dict(self, node: ET.Element) -> Dict[str, Any]:
        result: Dict[str, Any] = {}
        if node.text and node.text.strip():
            result[node.tag] = node.text.strip()
        for child in list(node):
            result[child.tag] = self._xml_to_dict(child).get(child.tag, "")
        return {node.tag: result} if node.tag != "config" else result

    def _dict_to_xml(self, node: ET.Element, data: Dict[str, Any]) -> None:
        for key, value in data.items():
            child = ET.SubElement(node, key)
            if isinstance(value, dict):
                self._dict_to_xml(child, value)
            else:
                child.text = str(value)

    def _coerce_value(self, val: str) -> Any:
        if val.lower() in ["true", "false"]:
            return val.lower() == "true"
        try:
            if "." in val:
                return float(val)
            return int(val)
        except ValueError:
            return val

    def _validate_required(self, data: Dict[str, Any], required_keys: List[str]) -> List[str]:
        missing = []
        for key in required_keys:
            if not self._has_path(data, key):
                missing.append(key)
        return missing

    def _has_path(self, data: Dict[str, Any], path: str) -> bool:
        current = data
        for part in path.split("."):
            if isinstance(current, dict) and part in current:
                current = current[part]
            else:
                return False
        return True

    def _deep_merge(self, base: Dict[str, Any], overrides: Dict[str, Any]) -> Dict[str, Any]:
        for key, value in overrides.items():
            if isinstance(value, dict) and isinstance(base.get(key), dict):
                base[key] = self._deep_merge(base[key], value)
            else:
                base[key] = value
        return base

    def _resolve_path(self, raw: str) -> Path:
        path = Path(raw)
        return path if path.is_absolute() else (self.project_root / path)
