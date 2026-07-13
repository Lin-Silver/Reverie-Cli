"""Small JSONL bridge for settings and runtime-plugin management."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any, Dict, Optional


def _json_safe(value: Any) -> Any:
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, dict):
        return {str(key): _json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [_json_safe(item) for item in value]
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    return str(value)


class ReverieSdkBridge:
    """Long-lived bridge used by desktop/settings hosts."""

    def __init__(self) -> None:
        self.project_root = Path.cwd().resolve()
        self.interface = None
        self.tool_executor = None

    def ensure_interface(self, project_root: Optional[Path] = None):
        from .cli.interface import ReverieInterface

        root = Path(project_root or self.project_root).expanduser().resolve()
        if not root.is_dir():
            raise ValueError(f"Workspace does not exist: {root}")
        if self.interface is None or self.project_root != root:
            self.project_root = root
            self.interface = ReverieInterface(root, headless=True)
            self.tool_executor = None
        return self.interface

    def ensure_tool_executor(self):
        from .agent.tool_executor import ToolExecutor

        interface = self.ensure_interface()
        if self.tool_executor is None:
            self.tool_executor = ToolExecutor(project_root=self.project_root)
        config = interface.config_manager.load()
        self.tool_executor.update_context("security", getattr(config, "security", {}))
        self.tool_executor.update_context("runtime_plugin_manager", interface.runtime_plugin_manager)
        self.tool_executor.update_context("workspace_stats_manager", interface.workspace_stats_manager)
        return self.tool_executor

    def _setting_value(self, item: Dict[str, Any], config: Any, interface: Any) -> Any:
        kind = str(item.get("kind") or "")
        key = str(item.get("key") or "")
        if kind == "plugin-bool":
            return bool(interface.runtime_plugin_manager.get_plugin_state(item.get("plugin_id", "")).get("enabled"))
        if kind == "workspace":
            return bool(interface.config_manager.is_workspace_mode())
        if kind == "rules":
            return "\n".join(interface.rules_manager.get_rules())
        return getattr(config, key, None)

    def settings_payload(self) -> Dict[str, Any]:
        from .settings_catalog import get_setting_items

        interface = self.ensure_interface()
        config = interface.config_manager.load()
        items = []
        for item in get_setting_items(
            config,
            interface.config_manager,
            interface.rules_manager,
            interface.runtime_plugin_manager,
        ):
            normalized = dict(item)
            normalized["value"] = self._setting_value(item, config, interface)
            items.append(_json_safe(normalized))
        return {
            "items": items,
            "config_path": str(interface.config_manager.config_path),
            "workspace_mode": bool(interface.config_manager.is_workspace_mode()),
        }

    @staticmethod
    def _plugin_record(record: Any) -> Dict[str, Any]:
        protocol = getattr(record, "protocol", None)
        return {
            "id": record.plugin_id,
            "name": record.display_name,
            "family": record.runtime_family,
            "version": record.version,
            "status": record.status,
            "status_label": record.status_label,
            "enabled": bool(record.enabled),
            "trusted": bool(record.trusted),
            "protocol_status": record.protocol_status,
            "protocol_label": record.protocol_label,
            "tool_count": record.protocol_tool_count,
            "command_count": record.protocol_command_count,
            "skill_count": len(protocol.skills) if protocol else 0,
            "system_prompt": protocol.system_prompt if protocol else "",
            "entry_path": record.entry_path,
            "install_dir": record.install_dir,
        }

    def plugins_payload(self, *, force_refresh: bool = False) -> Dict[str, Any]:
        manager = self.ensure_interface().runtime_plugin_manager
        snapshot = manager.get_snapshot(force_refresh=force_refresh)
        return {
            "summary": _json_safe(manager.get_status_summary(force_refresh=False)),
            "records": [self._plugin_record(record) for record in snapshot.records],
        }

    def _refresh_plugin_dependents(self) -> None:
        interface = self.ensure_interface()
        interface.skills_manager.scan()
        if interface.agent is not None:
            interface._refresh_agent_prompt_guidance()

    def dispatch(self, message: Dict[str, Any]) -> Dict[str, Any]:
        action = str(message.get("action") or "").strip()
        payload = message.get("payload") if isinstance(message.get("payload"), dict) else {}
        request_id = message.get("id")

        if action == "hello":
            return {"id": request_id, "type": "ready", "project_root": str(self.project_root)}
        if action == "initialize":
            self.ensure_interface(Path(str(payload.get("projectRoot") or self.project_root)))
            return {
                "id": request_id,
                "type": "state",
                "settings": self.settings_payload(),
                "plugins": self.plugins_payload(),
            }
        if action == "getState":
            return {
                "id": request_id,
                "type": "state",
                "settings": self.settings_payload(),
                "plugins": self.plugins_payload(),
            }
        if action == "listSettings":
            return {"id": request_id, "type": "settings", "settings": self.settings_payload()}
        if action == "setSetting":
            from .settings_catalog import apply_setting_value

            interface = self.ensure_interface()
            config = interface.config_manager.load()
            success, detail, reinit = apply_setting_value(
                config,
                interface.config_manager,
                interface.rules_manager,
                str(payload.get("key") or ""),
                payload.get("value"),
                interface.runtime_plugin_manager,
            )
            if success and not str(payload.get("key") or "").startswith("plugin_enabled:"):
                interface.config_manager.save(config)
            if success:
                self._refresh_plugin_dependents()
                if reinit and interface.agent is not None:
                    interface._init_agent(config_override=interface.config_manager.load(), persist_config_changes=False)
            return {
                "id": request_id,
                "type": "setting.updated",
                "success": success,
                "message": detail,
                "settings": self.settings_payload(),
            }
        if action in {"listPlugins", "refreshPlugins"}:
            return {
                "id": request_id,
                "type": "plugins",
                "plugins": self.plugins_payload(force_refresh=action == "refreshPlugins"),
            }
        if action in {"setPluginEnabled", "setPluginTrust"}:
            from .settings_catalog import parse_bool

            interface = self.ensure_interface()
            manager = interface.runtime_plugin_manager
            plugin_id = str(payload.get("pluginId") or payload.get("id") or "").strip()
            if not plugin_id:
                raise ValueError("Plugin id is required.")
            if action == "setPluginEnabled":
                enabled = parse_bool(payload.get("enabled"))
                if enabled is None:
                    raise ValueError("Plugin enabled value must be a boolean.")
                manager.set_plugin_enabled(plugin_id, enabled)
            else:
                trusted = parse_bool(payload.get("trusted"))
                if trusted is None:
                    raise ValueError("Plugin trusted value must be a boolean.")
                manager.set_plugin_trust(plugin_id, trusted)
            self._refresh_plugin_dependents()
            return {
                "id": request_id,
                "type": "plugin.updated",
                "plugin_id": plugin_id,
                "plugins": self.plugins_payload(),
                "settings": self.settings_payload(),
            }
        if action == "inspectPlugin":
            manager = self.ensure_interface().runtime_plugin_manager
            plugin_id = str(payload.get("pluginId") or payload.get("id") or "").strip()
            record = manager.get_record(plugin_id, force_refresh=False)
            return {
                "id": request_id,
                "type": "plugin.inspect",
                "record": self._plugin_record(record) if record else None,
            }
        if action == "listTools":
            mode = str(payload.get("mode") or "reverie").strip()
            schemas = self.ensure_tool_executor().get_tool_schemas(mode)
            return {
                "id": request_id,
                "type": "tools",
                "mode": mode,
                "tools": _json_safe(schemas),
            }
        if action == "callPluginTool":
            from .plugin.dynamic_tool import RuntimePluginDynamicTool

            tool_name = str(payload.get("toolName") or payload.get("name") or "").strip()
            arguments = payload.get("arguments") if isinstance(payload.get("arguments"), dict) else {}
            if not tool_name:
                raise ValueError("Plugin tool name is required.")
            executor = self.ensure_tool_executor()
            tool = executor.get_tool(tool_name)
            if not isinstance(tool, RuntimePluginDynamicTool):
                raise ValueError(f"Not a runtime plugin tool: {tool_name}")
            result = executor.execute(tool_name, arguments)
            self.ensure_interface().workspace_stats_manager.flush()
            return {
                "id": request_id,
                "type": "plugin.tool.result",
                "tool_name": tool.name,
                "success": bool(result.success),
                "output": result.output,
                "error": result.error,
                "data": _json_safe(result.data),
                "status": str(getattr(result.status, "value", result.status)),
            }
        if action == "shutdown":
            return {"id": request_id, "type": "shutdown"}
        raise ValueError(f"Unknown action: {action}")


def main() -> int:
    bridge = ReverieSdkBridge()
    sys.stdout.write(json.dumps({"type": "ready"}, ensure_ascii=False) + "\n")
    sys.stdout.flush()
    for raw_line in sys.stdin:
        raw_line = str(raw_line or "").lstrip("\ufeff").strip()
        if not raw_line:
            continue
        request_id = None
        try:
            message = json.loads(raw_line)
            request_id = message.get("id") if isinstance(message, dict) else None
            result = bridge.dispatch(message if isinstance(message, dict) else {})
        except Exception as exc:
            result = {"id": request_id, "type": "error", "error": str(exc)}
        sys.stdout.write(json.dumps(_json_safe(result), ensure_ascii=False) + "\n")
        sys.stdout.flush()
        if result.get("type") == "shutdown":
            break
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
