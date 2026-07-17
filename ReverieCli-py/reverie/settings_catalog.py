"""Shared settings metadata and mutation helpers for CLI and UI surfaces."""

from __future__ import annotations

from typing import Any, Dict, Iterable, List, Optional, Tuple

from .config import normalize_thinking_output_style, normalize_tool_output_style
from .modes import list_modes, normalize_mode
from .security_policy import PERMISSION_LEVELS, normalize_permission_level


def setting_mode_options() -> List[str]:
    """Available runtime modes for `/mode`, `/setting`, and the UI."""
    return list_modes(include_computer=True)


def setting_theme_options() -> List[str]:
    """Available persisted theme values."""
    return ["default", "dark", "light", "ocean", "high-contrast", "minimal"]


def setting_tool_output_choices() -> List[str]:
    """Available completed-tool transcript styles."""
    return ["minimal", "compact", "condensed", "full"]


def setting_thinking_output_choices() -> List[str]:
    """Available streamed reasoning transcript styles."""
    return ["full", "compact", "hidden"]


def get_setting_items(
    config: Any,
    config_manager: Any,
    rules_manager: Any = None,
    runtime_plugin_manager: Any = None,
) -> List[Dict[str, Any]]:
    """Build setting metadata shared by terminal and desktop UI renderers."""
    items = [
        {
            "name": "Mode",
            "key": "mode",
            "kind": "choice",
            "choices": setting_mode_options(),
            "description": "Switch the active Reverie operating mode and prompt strategy.",
            "command": "/setting mode <mode-name>",
        },
        {
            "name": "Active Source",
            "key": "active_model_source",
            "kind": "readonly",
            "description": "Current model source. Use /model or provider-native commands to switch sources.",
            "command": "/status",
        },
        {
            "name": "Standard Model",
            "key": "active_model_index",
            "kind": "choice",
            "choices": list(range(len(getattr(config, "models", []) or []))),
            "description": "Active model inside the standard catalog. Selecting here also switches source back to Standard.",
            "command": "/setting model <index> or /model",
        },
        {
            "name": "Theme",
            "key": "theme",
            "kind": "choice",
            "choices": setting_theme_options(),
            "description": "Persisted theme preset used by the CLI.",
            "command": "/setting theme <theme>",
        },
        {
            "name": "Auto Index",
            "key": "auto_index",
            "kind": "bool",
            "description": "Automatically index the workspace when cache is cold.",
            "command": "/setting auto-index on|off",
        },
        {
            "name": "Status Line",
            "key": "show_status_line",
            "kind": "bool",
            "description": "Show the live status line before and after responses.",
            "command": "/setting status-line on|off",
        },
        {
            "name": "Tool Output Style",
            "key": "tool_output_style",
            "kind": "choice",
            "choices": setting_tool_output_choices(),
            "description": "Choose how completed tool results appear after the live running panel collapses.",
            "command": "/setting tool-output compact|condensed|full",
        },
        {
            "name": "Thinking Output",
            "key": "thinking_output_style",
            "kind": "choice",
            "choices": setting_thinking_output_choices(),
            "description": "Choose whether streamed reasoning stays fully visible, compact, or hidden in the transcript.",
            "command": "/setting thinking full|compact|hidden",
        },
        {
            "name": "Stream Responses",
            "key": "stream_responses",
            "kind": "bool",
            "description": "Stream assistant output token-by-token when the provider supports it.",
            "command": "/setting stream on|off",
        },
        {
            "name": "API Timeout",
            "key": "api_timeout",
            "kind": "int",
            "min": 10,
            "max": 3600,
            "step": 10,
            "description": "Default API timeout in seconds for model requests.",
            "command": "/setting timeout <seconds>",
        },
        {
            "name": "API Retries",
            "key": "api_max_retries",
            "kind": "int",
            "min": 0,
            "max": 12,
            "step": 1,
            "description": "Fixed retry policy for recoverable API failures: 5 retries after 1, 3, 5, 7, and 15 seconds.",
            "command": "/setting retries <count>",
        },
        {
            "name": "Debug Logging",
            "key": "api_enable_debug_logging",
            "kind": "bool",
            "description": "Enable verbose API logging for troubleshooting.",
            "command": "/setting debug on|off",
        },
        {
            "name": "Workspace Config",
            "key": "use_workspace_config",
            "kind": "workspace",
            "description": "Choose whether settings are stored in the current workspace or the global Reverie config.",
            "command": "/setting workspace on|off",
        },
        {
            "name": "Permission Level",
            "key": "permission_level",
            "kind": "choice",
            "choices": list(PERMISSION_LEVELS),
            "description": "Control which tool classes the software permits. Full Control is the default; dangerous operations remain blocked by hard policy.",
            "command": "Edit security.permission_level to reduce the software-enforced tool surface.",
        },
        {
            "name": "Rules",
            "key": "rules",
            "kind": "rules",
            "description": "Edit additional instruction rules applied to the active session.",
            "command": "/setting rules",
        },
    ]
    if runtime_plugin_manager is not None:
        try:
            snapshot = runtime_plugin_manager.get_snapshot(force_refresh=False)
        except Exception:
            snapshot = None
        for record in getattr(snapshot, "records", ()) or ():
            items.append(
                {
                    "name": f"Plugin: {record.display_name}",
                    "key": f"plugin_enabled:{record.plugin_id}",
                    "kind": "plugin-bool",
                    "plugin_id": record.plugin_id,
                    "value": bool(record.enabled),
                    "trusted": bool(record.trusted),
                    "description": (
                        "Enable or disable this plugin's executable tools, system-prompt instructions, and virtual skills."
                    ),
                    "command": f"/plugins enable {record.plugin_id} | /plugins disable {record.plugin_id}",
                }
            )
    return items


def parse_bool(value: Any) -> Optional[bool]:
    """Parse the common boolean spellings used by CLI and UI payloads."""
    if isinstance(value, bool):
        return value
    lowered = str(value or "").strip().lower()
    if lowered in ("on", "true", "1", "yes", "enable", "enabled"):
        return True
    if lowered in ("off", "false", "0", "no", "disable", "disabled"):
        return False
    return None


def apply_workspace_mode_setting(config_manager: Any, enabled: bool) -> Tuple[bool, str]:
    """Apply workspace/global config mode and return success with a message."""
    if not config_manager:
        return False, "Config manager not available."

    if enabled:
        if config_manager.is_workspace_mode():
            return True, "Workspace mode is already enabled."
        if not config_manager.has_workspace_config():
            if not config_manager.has_global_config():
                return False, "No configuration found. Configure a model before enabling workspace mode."
            if not config_manager.copy_config_to_workspace():
                return False, "Failed to copy the global config into the workspace."
        if not config_manager.set_workspace_config_enabled(True):
            return False, "Failed to mark the workspace profile as enabled."
        config_manager.set_workspace_mode(True)
        config = config_manager.load()
        config.use_workspace_config = True
        config_manager.save(config)
        return True, f"Workspace mode enabled. Config path: {config_manager.workspace_config_path}"

    if not config_manager.is_workspace_mode():
        return True, "Workspace mode is already disabled."
    if not config_manager.set_workspace_config_enabled(False):
        return False, "Failed to mark the workspace profile as disabled."
    config_manager.set_workspace_mode(False)
    config = config_manager.load()
    config.use_workspace_config = False
    config_manager.save(config)
    return True, f"Workspace mode disabled. Config path: {config_manager.global_config_path}"


def _coerce_choice(value: Any, choices: Iterable[Any]) -> Tuple[bool, Any]:
    choice_list = list(choices)
    if value in choice_list:
        return True, value
    text = str(value or "").strip()
    for choice in choice_list:
        if str(choice).lower() == text.lower():
            return True, choice
    return False, None


def apply_setting_value(
    config: Any,
    config_manager: Any,
    rules_manager: Any,
    key: str,
    value: Any,
    runtime_plugin_manager: Any = None,
) -> Tuple[bool, str, bool]:
    """Mutate one setting. Returns (success, message, should_reinit_agent)."""
    normalized_key = str(key or "").strip()
    items = {
        str(item.get("key") or ""): item
        for item in get_setting_items(config, config_manager, rules_manager, runtime_plugin_manager)
    }
    item = items.get(normalized_key)
    if item is None:
        return False, f"Unknown setting: {normalized_key}", False

    kind = str(item.get("kind") or "").strip()
    if kind == "plugin-bool":
        if runtime_plugin_manager is None:
            return False, "Runtime plugin manager not available.", False
        parsed = parse_bool(value)
        if parsed is None:
            return False, "Plugin state expects on/off.", False
        plugin_id = str(item.get("plugin_id") or "").strip()
        runtime_plugin_manager.set_plugin_enabled(plugin_id, parsed)
        return True, f"Plugin {plugin_id} {'enabled' if parsed else 'disabled'}.", True
    if kind == "readonly":
        return False, f"{item.get('name', normalized_key)} is read-only.", False
    if kind == "workspace":
        parsed = parse_bool(value)
        if parsed is None:
            return False, "Workspace config expects a boolean value.", False
        ok, message = apply_workspace_mode_setting(config_manager, parsed)
        return ok, message, ok
    if kind == "rules":
        if rules_manager is None:
            return False, "Rules manager not available.", False
        if isinstance(value, str):
            rules = [line.strip() for line in value.splitlines() if line.strip()]
        elif isinstance(value, list):
            rules = [str(line or "").strip() for line in value if str(line or "").strip()]
        else:
            return False, "Rules expects a string or list value.", False
        rules_manager._rules = rules
        rules_manager.save()
        return True, f"Rules updated ({len(rules)} total).", True
    if kind == "bool":
        parsed = parse_bool(value)
        if parsed is None:
            return False, f"{item.get('name', normalized_key)} expects on/off.", False
        setattr(config, normalized_key, parsed)
        return True, f"{item.get('name', normalized_key)} set to {'on' if parsed else 'off'}.", False
    if kind == "int":
        try:
            parsed_int = int(value)
        except (TypeError, ValueError):
            return False, f"{item.get('name', normalized_key)} must be an integer.", False
        minimum = int(item.get("min", 0) or 0)
        maximum = int(item.get("max", 0) or 0)
        if parsed_int < minimum or parsed_int > maximum:
            return False, f"{item.get('name', normalized_key)} must be between {minimum} and {maximum}.", False
        setattr(config, normalized_key, parsed_int)
        return True, f"{item.get('name', normalized_key)} set to {parsed_int}.", False
    if kind == "choice":
        if normalized_key == "permission_level":
            level = normalize_permission_level(value)
            if str(value or "").strip().lower() not in PERMISSION_LEVELS:
                return False, "Unsupported permission level.", False
            config.security = dict(getattr(config, "security", {}) or {})
            config.security["permission_level"] = level
            return True, f"Permission level set to {level}.", True
        if normalized_key == "mode":
            config.mode = normalize_mode(value)
            return True, f"Mode set to {config.mode}.", True
        if normalized_key == "active_model_index":
            try:
                index = int(value)
            except (TypeError, ValueError):
                return False, "Standard Model expects a model index.", False
            if index < 0 or index >= len(getattr(config, "models", []) or []):
                return False, "Model index is out of range.", False
            config.active_model_index = index
            config.active_model_source = "standard"
            return True, f"Standard model set to index {index}.", True
        ok, choice = _coerce_choice(value, item.get("choices", []) or [])
        if not ok:
            return False, f"Unsupported value for {item.get('name', normalized_key)}.", False
        if normalized_key == "tool_output_style":
            choice = normalize_tool_output_style(choice, "compact")
        elif normalized_key == "thinking_output_style":
            choice = normalize_thinking_output_style(choice, "full")
        setattr(config, normalized_key, choice)
        return True, f"{item.get('name', normalized_key)} set to {choice}.", False

    return False, f"Unsupported setting kind: {kind}", False
