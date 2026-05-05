"""JSONL SDK bridge used by Reverie UI and other host applications.

The bridge is intentionally line-oriented and long-lived: hosts write one JSON
object per line to stdin and receive JSON events on stdout. Keeping the full
Reverie runtime warm lets the desktop UI reuse the CLI as an SDK without paying
Python/package startup costs for every action.
"""

from __future__ import annotations

import contextlib
import dataclasses
import hashlib
import json
import os
import shutil
import subprocess
import sys
import traceback
import urllib.error
import urllib.request
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Dict, Iterable, Optional


PACKAGE_ROOT = Path(__file__).resolve().parent
RUNTIME_ROOT = PACKAGE_ROOT.parent
if str(RUNTIME_ROOT) not in sys.path:
    sys.path.insert(0, str(RUNTIME_ROOT))

OUT = sys.stdout
for stream in (sys.stdout, sys.stderr):
    if hasattr(stream, "reconfigure"):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass


def emit(payload: Dict[str, Any]) -> None:
    OUT.write(json.dumps(json_safe(payload), ensure_ascii=False) + "\n")
    OUT.flush()


def json_safe(value: Any) -> Any:
    if dataclasses.is_dataclass(value):
        return json_safe(dataclasses.asdict(value))
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, dict):
        return {str(key): json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [json_safe(item) for item in value]
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    return str(value)


def object_to_dict(value: Any, fields: Iterable[str]) -> Dict[str, Any]:
    return {field: json_safe(getattr(value, field, None)) for field in fields}


class ReverieUiBridge:
    RELEASE_REPOSITORY = "Lin-Silver/Reverie-Cli"
    RELEASE_SCHEMA = "reverie.plugins.release.v1"
    OFFICIAL_PLUGIN_IDS = ("blender", "godot", "o3de", "game_models")

    def __init__(self) -> None:
        self.project_root = Path.cwd()
        self.interface = None
        self.last_activity = ""
        self._remote_release_cache: Optional[Dict[str, Any]] = None

    def dispatch(self, message: Dict[str, Any]) -> None:
        action = str(message.get("action", "") or "").strip()
        request_id = message.get("id")
        payload = message.get("payload") if isinstance(message.get("payload"), dict) else {}
        if not action:
            emit({"id": request_id, "type": "error", "error": "Missing action."})
            return

        handlers: Dict[str, Callable[[Any, Dict[str, Any]], None]] = {
            "hello": self.handle_hello,
            "initialize": self.handle_initialize,
            "getState": self.handle_get_state,
            "locateRuntime": self.handle_locate_runtime,
            "setWorkspace": self.handle_set_workspace,
            "setMode": self.handle_set_mode,
            "listSettings": self.handle_list_settings,
            "setSetting": self.handle_set_setting,
            "savePreferences": self.handle_save_preferences,
            "saveModel": self.handle_save_model,
            "deleteModel": self.handle_delete_model,
            "selectModel": self.handle_select_model,
            "saveBuiltinSource": self.handle_save_builtin_source,
            "selectBuiltinSource": self.handle_select_builtin_source,
            "testProviders": self.handle_test_providers,
            "chat": self.handle_chat,
            "indexWorkspace": self.handle_index_workspace,
            "newSession": self.handle_new_session,
            "switchSession": self.handle_switch_session,
            "renameSession": self.handle_rename_session,
            "deleteSession": self.handle_delete_session,
            "clearSession": self.handle_clear_session,
            "listPlugins": self.handle_list_plugins,
            "refreshPlugins": self.handle_refresh_plugins,
            "listRemoteReleases": self.handle_list_remote_releases,
            "installRemotePlugin": self.handle_install_remote_plugin,
            "buildPlugin": self.handle_build_plugin,
            "deployPlugin": self.handle_deploy_plugin,
            "inspectPlugin": self.handle_inspect_plugin,
            "callPluginCommand": self.handle_call_plugin_command,
            "listTools": self.handle_list_tools,
            "gitStatus": self.handle_git_status,
            "diagnostics": self.handle_diagnostics,
            "shutdown": self.handle_shutdown,
        }

        handler = handlers.get(action)
        if handler is None:
            emit({"id": request_id, "type": "error", "error": f"Unknown action: {action}"})
            return

        try:
            with contextlib.redirect_stdout(sys.stderr):
                handler(request_id, payload)
        except SystemExit:
            raise
        except Exception as exc:
            traceback.print_exc(file=sys.stderr)
            emit({"id": request_id, "type": "error", "error": str(exc)})

    def ensure_interface(self, project_root: Optional[Path] = None) -> Any:
        from reverie.cli.interface import ReverieInterface

        root = Path(project_root or self.project_root).expanduser().resolve()
        if not root.exists() or not root.is_dir():
            raise ValueError(f"Workspace does not exist: {root}")

        if self.interface is None or Path(self.project_root).resolve() != root:
            self.project_root = root
            self.interface = ReverieInterface(root, headless=True)
        return self.interface

    def summarize_config(self) -> Dict[str, Any]:
        from reverie.modes import get_mode_display_name, list_modes

        interface = self.ensure_interface()
        config = interface.config_manager.load()
        active_model = config.active_model
        models = []
        for index, model in enumerate(getattr(config, "models", []) or []):
            item = object_to_dict(
                model,
                (
                    "model",
                    "model_display_name",
                    "base_url",
                    "provider",
                    "endpoint",
                    "thinking_mode",
                    "max_context_tokens",
                    "custom_headers",
                ),
            )
            item["index"] = index
            item["has_api_key"] = bool(getattr(model, "api_key", ""))
            models.append(item)

        return {
            "mode": getattr(config, "mode", "reverie"),
            "mode_display_name": get_mode_display_name(getattr(config, "mode", "reverie")),
            "modes": [
                {"id": mode, "name": get_mode_display_name(mode)}
                for mode in list_modes(include_computer=True, switchable_only=False)
            ],
            "stream_responses": bool(getattr(config, "stream_responses", True)),
            "auto_index": bool(getattr(config, "auto_index", True)),
            "show_status_line": bool(getattr(config, "show_status_line", True)),
            "tool_output_style": getattr(config, "tool_output_style", "compact"),
            "thinking_output_style": getattr(config, "thinking_output_style", "full"),
            "theme": getattr(config, "theme", "default"),
            "api_timeout": int(getattr(config, "api_timeout", 60) or 60),
            "api_max_retries": int(getattr(config, "api_max_retries", 3) or 3),
            "active_model_source": getattr(config, "active_model_source", "standard"),
            "active_model_index": int(getattr(config, "active_model_index", 0) or 0),
            "active_model": object_to_dict(
                active_model,
                ("model", "model_display_name", "base_url", "provider", "endpoint", "thinking_mode", "max_context_tokens"),
            )
            if active_model
            else None,
            "models": models,
            "builtin_sources": self.summarize_builtin_sources(config),
            "config_path": str(interface.config_manager.config_path),
            "app_root": str(interface.config_manager.app_root),
            "sdk": self.runtime_info(),
        }

    def summarize_builtin_sources(self, config: Any) -> list[Dict[str, Any]]:
        """Return safe GUI metadata for Reverie's first-party model sources."""
        from reverie.codex import (
            detect_codex_cli_credentials,
            get_codex_model_catalog,
            normalize_codex_config,
            resolve_codex_selected_model,
        )
        from reverie.geminicli import (
            detect_geminicli_cli_credentials,
            get_geminicli_model_catalog,
            normalize_geminicli_config,
            resolve_geminicli_selected_model,
        )
        from reverie.modelscope import (
            get_modelscope_model_catalog,
            normalize_modelscope_config,
            resolve_modelscope_api_key,
            resolve_modelscope_selected_model,
        )
        from reverie.nvidia import (
            get_nvidia_model_catalog,
            normalize_nvidia_config,
            resolve_nvidia_api_key,
            resolve_nvidia_selected_model,
            resolve_nvidia_thinking_choice,
        )

        active_source = str(getattr(config, "active_model_source", "standard") or "standard").strip().lower()
        sources: list[Dict[str, Any]] = []

        geminicli_cfg = normalize_geminicli_config(getattr(config, "geminicli", {}))
        geminicli_cred = detect_geminicli_cli_credentials(refresh_if_needed=False)
        geminicli_selected = resolve_geminicli_selected_model(geminicli_cfg)
        sources.append(
            {
                "source": "geminicli",
                "label": "Gemini CLI",
                "active": active_source == "geminicli",
                "credential": "found" if geminicli_cred.get("found") else "missing",
                "has_api_key": bool(geminicli_cred.get("found")),
                "selected_model_id": str(geminicli_cfg.get("selected_model_id", "") or ""),
                "selected_model_display_name": str(
                    (geminicli_selected or {}).get("display_name") or geminicli_cfg.get("selected_model_display_name") or ""
                ),
                "api_url": str(geminicli_cfg.get("api_url", "") or ""),
                "endpoint": str(geminicli_cfg.get("endpoint", "") or ""),
                "project_id": str(geminicli_cfg.get("project_id", "") or ""),
                "models": get_geminicli_model_catalog(),
            }
        )

        codex_cfg = normalize_codex_config(getattr(config, "codex", {}))
        codex_cred = detect_codex_cli_credentials()
        codex_selected = resolve_codex_selected_model(codex_cfg)
        sources.append(
            {
                "source": "codex",
                "label": "Codex",
                "active": active_source == "codex",
                "credential": "found" if codex_cred.get("found") else "missing",
                "has_api_key": bool(codex_cred.get("found")),
                "selected_model_id": str(codex_cfg.get("selected_model_id", "") or ""),
                "selected_model_display_name": str(
                    (codex_selected or {}).get("display_name") or codex_cfg.get("selected_model_display_name") or ""
                ),
                "api_url": str(codex_cfg.get("api_url", "") or ""),
                "endpoint": str(codex_cfg.get("endpoint", "") or ""),
                "reasoning_effort": str(codex_cfg.get("reasoning_effort", "") or ""),
                "models": get_codex_model_catalog(),
            }
        )

        nvidia_cfg = normalize_nvidia_config(getattr(config, "nvidia", {}))
        nvidia_key = resolve_nvidia_api_key(nvidia_cfg)
        nvidia_selected = resolve_nvidia_selected_model(nvidia_cfg)
        selected_nvidia_id = str((nvidia_selected or {}).get("id") or nvidia_cfg.get("selected_model_id") or "")
        sources.append(
            {
                "source": "nvidia",
                "label": "NVIDIA",
                "active": active_source == "nvidia",
                "credential": "found" if nvidia_key else "missing",
                "has_api_key": bool(nvidia_key),
                "selected_model_id": selected_nvidia_id,
                "selected_model_display_name": str(
                    (nvidia_selected or {}).get("display_name") or nvidia_cfg.get("selected_model_display_name") or ""
                ),
                "api_url": str(nvidia_cfg.get("api_url", "") or ""),
                "endpoint": str(nvidia_cfg.get("endpoint", "") or ""),
                "thinking_choice": resolve_nvidia_thinking_choice(nvidia_cfg, selected_nvidia_id),
                "models": get_nvidia_model_catalog(),
            }
        )

        modelscope_cfg = normalize_modelscope_config(getattr(config, "modelscope", {}))
        modelscope_key = resolve_modelscope_api_key(modelscope_cfg)
        modelscope_selected = resolve_modelscope_selected_model(modelscope_cfg)
        sources.append(
            {
                "source": "modelscope",
                "label": "ModelScope",
                "active": active_source == "modelscope",
                "credential": "found" if modelscope_key else "missing",
                "has_api_key": bool(modelscope_key),
                "selected_model_id": str(modelscope_cfg.get("selected_model_id", "") or ""),
                "selected_model_display_name": str(
                    (modelscope_selected or {}).get("display_name") or modelscope_cfg.get("selected_model_display_name") or ""
                ),
                "api_url": str(modelscope_cfg.get("api_url", "") or ""),
                "endpoint": "",
                "models": get_modelscope_model_catalog(),
            }
        )
        return json_safe(sources)

    def summarize_sessions(self) -> Dict[str, Any]:
        interface = self.ensure_interface()
        sessions = [
            object_to_dict(item, ("id", "name", "created_at", "updated_at", "message_count"))
            for item in interface.session_manager.list_sessions()
        ]
        current = interface.session_manager.get_current_session()
        if current is None:
            current = interface.session_manager.restore_last_session()
        return {
            "current_session_id": getattr(current, "id", ""),
            "current_session_name": getattr(current, "name", ""),
            "sessions": sessions,
            "messages": self.summarize_messages(getattr(current, "messages", []) if current else []),
        }

    def summarize_messages(self, messages: Iterable[Dict[str, Any]]) -> list[Dict[str, Any]]:
        summarized = []
        for message in messages or []:
            role = str(message.get("role", "") or "")
            content = message.get("content", "")
            if isinstance(content, list):
                text_parts = []
                for part in content:
                    if isinstance(part, dict):
                        text_parts.append(str(part.get("text") or part.get("content") or ""))
                    else:
                        text_parts.append(str(part))
                content = "\n".join(part for part in text_parts if part).strip()
            summarized.append({"role": role, "content": str(content or "")})
        return summarized[-80:]

    def summarize_tools(self, mode: Optional[str] = None) -> list[Dict[str, Any]]:
        from reverie.tools.registry import get_tool_registrations

        config = self.ensure_interface().config_manager.load()
        active_mode = mode or getattr(config, "mode", "reverie")
        tools = []
        for registration in get_tool_registrations(include_hidden=True):
            tool_class = registration.tool_class
            tools.append(
                {
                    "name": registration.name,
                    "description": str(getattr(tool_class, "description", "") or "").strip(),
                    "category": str(getattr(tool_class, "tool_category", "general") or "general"),
                    "tags": list(getattr(tool_class, "tool_tags", ()) or ()),
                    "visible": bool(registration.expose_schema and registration.enabled_in_mode(active_mode)),
                    "read_only": bool(getattr(tool_class, "read_only", False)),
                    "destructive": bool(getattr(tool_class, "destructive", False)),
                    "supported_modes": registration.supported_modes(include_hidden=True),
                }
            )
        return tools

    def summarize_settings(self) -> Dict[str, Any]:
        from reverie.settings_catalog import get_setting_items

        interface = self.ensure_interface()
        config = interface.config_manager.load()
        rules_manager = getattr(interface, "rules_manager", None)
        items = []
        for item in get_setting_items(config, interface.config_manager, rules_manager):
            key = str(item.get("key") or "")
            kind = str(item.get("kind") or "")
            current_value = self.setting_value_for_ui(item, config, interface.config_manager, rules_manager)
            normalized = dict(item)
            normalized["value"] = current_value
            normalized["options"] = self.setting_options_for_ui(item, config)
            if kind == "rules" and rules_manager is not None:
                normalized["rules"] = [str(rule) for rule in rules_manager.get_rules()]
                normalized["value"] = "\n".join(normalized["rules"])
            if kind == "workspace":
                normalized["workspace_config_path"] = str(interface.config_manager.workspace_config_path)
                normalized["global_config_path"] = str(interface.config_manager.global_config_path)
            if key == "active_model_index":
                normalized["model_source"] = getattr(config, "active_model_source", "standard")
            items.append(json_safe(normalized))

        return {
            "items": items,
            "config_path": str(interface.config_manager.config_path),
            "workspace_mode": bool(interface.config_manager.is_workspace_mode()),
            "rules_path": str(getattr(rules_manager, "rules_txt_path", "")) if rules_manager else "",
        }

    def setting_value_for_ui(self, item: Dict[str, Any], config: Any, config_manager: Any, rules_manager: Any) -> Any:
        key = str(item.get("key") or "")
        kind = str(item.get("kind") or "")
        if kind == "workspace":
            return bool(config_manager.is_workspace_mode())
        if kind == "rules":
            return "\n".join(rules_manager.get_rules()) if rules_manager else ""
        if key == "active_model_index":
            return int(getattr(config, "active_model_index", 0) or 0)
        return json_safe(getattr(config, key, None))

    def setting_options_for_ui(self, item: Dict[str, Any], config: Any) -> list[Dict[str, Any]]:
        key = str(item.get("key") or "")
        if key == "active_model_index":
            options = []
            for index, model in enumerate(getattr(config, "models", []) or []):
                label = str(getattr(model, "model_display_name", "") or getattr(model, "model", "") or f"Model {index + 1}")
                options.append({"value": index, "label": label})
            return options
        return [{"value": choice, "label": str(choice)} for choice in item.get("choices", []) or []]

    def plugin_manager(self) -> Any:
        interface = self.ensure_interface()
        manager = getattr(interface, "runtime_plugin_manager", None)
        if manager is None:
            from reverie.config import get_app_root
            from reverie.plugin.runtime_manager import RuntimePluginManager

            manager = RuntimePluginManager(get_app_root())
            interface.runtime_plugin_manager = manager
        return manager

    def plugin_record_to_dict(self, record: Any) -> Dict[str, Any]:
        commands = []
        protocol = getattr(record, "protocol", None)
        if protocol is not None:
            for command in getattr(protocol, "commands", ()) or ():
                commands.append(
                    {
                        "name": getattr(command, "name", ""),
                        "description": getattr(command, "description", ""),
                        "expose_as_tool": bool(getattr(command, "expose_as_tool", False)),
                        "parameters": json_safe(getattr(command, "parameters", {})),
                        "include_modes": list(getattr(command, "include_modes", ()) or ()),
                        "exclude_modes": list(getattr(command, "exclude_modes", ()) or ()),
                        "example": getattr(command, "example", ""),
                    }
                )
        return {
            "id": getattr(record, "plugin_id", ""),
            "name": getattr(record, "display_name", ""),
            "family": getattr(record, "runtime_family", ""),
            "version": getattr(record, "version", ""),
            "status": getattr(record, "status", ""),
            "status_label": getattr(record, "status_label", ""),
            "protocol_status": getattr(record, "protocol_status", ""),
            "protocol_label": getattr(record, "protocol_label", ""),
            "protocol_error": getattr(record, "protocol_error", ""),
            "source": getattr(record, "source_label", getattr(record, "source", "")),
            "delivery": getattr(record, "delivery_label", getattr(record, "delivery", "")),
            "description": getattr(record, "description", ""),
            "detail": getattr(record, "detail", ""),
            "entry": getattr(record, "entry_display", ""),
            "entry_path": getattr(record, "entry_path", None),
            "install_dir": getattr(record, "install_dir", None),
            "manifest_path": getattr(record, "manifest_path", None),
            "compiled_entry_path": getattr(record, "compiled_entry_path", None),
            "capabilities": list(getattr(record, "capabilities", ()) or ()),
            "tool_count": int(getattr(record, "protocol_tool_count", 0) or 0),
            "command_count": int(getattr(record, "protocol_command_count", 0) or 0),
            "commands": commands,
            "catalog_managed": bool(getattr(record, "catalog_managed", False)),
            "build_commands": list(getattr(record, "build_commands", ()) or ()),
        }

    def summarize_plugins(self, *, force_refresh: bool = False, include_remote: bool = True) -> Dict[str, Any]:
        manager = self.plugin_manager()
        summary = manager.get_status_summary(force_refresh=force_refresh)
        snapshot = manager.get_snapshot(force_refresh=False)
        records = [self.plugin_record_to_dict(record) for record in getattr(snapshot, "records", ()) or ()]
        source_validations = []
        for plugin_id in self.OFFICIAL_PLUGIN_IDS:
            try:
                source_validations.append(self.compact_plugin_validation(manager.validate_source_plugin(plugin_id)))
            except Exception as exc:
                source_validations.append({"plugin_id": plugin_id, "success": False, "error": str(exc)})
        remote = self.fetch_remote_release(force_refresh=False) if include_remote else {}
        return {
            "summary": json_safe(summary),
            "records": records,
            "source_validations": source_validations,
            "remote": remote,
        }

    def compact_plugin_validation(self, result: Dict[str, Any]) -> Dict[str, Any]:
        """Return source-plugin validation without embedding the full protocol record."""
        keys = (
            "success",
            "plugin_id",
            "display_name",
            "runtime_family",
            "delivery",
            "source_dir",
            "manifest_path",
            "entry_path",
            "compiled_entry_path",
            "source_entry_path",
            "build_commands",
            "protocol_status",
            "protocol_supported",
            "template_id",
            "packaging_format",
            "entry_strategy",
            "errors",
            "warnings",
            "unresolved_tokens",
        )
        return {key: json_safe(result.get(key)) for key in keys if key in result}

    def github_json(self, url: str) -> Dict[str, Any]:
        request = urllib.request.Request(
            url,
            headers={
                "Accept": "application/vnd.github+json",
                "User-Agent": "Reverie-UI-SDK/1.0",
            },
        )
        with urllib.request.urlopen(request, timeout=20) as response:
            data = response.read()
        parsed = json.loads(data.decode("utf-8", errors="replace"))
        return parsed if isinstance(parsed, dict) else {}

    def fetch_text_url(self, url: str) -> str:
        request = urllib.request.Request(url, headers={"User-Agent": "Reverie-UI-SDK/1.0"})
        with urllib.request.urlopen(request, timeout=30) as response:
            return response.read().decode("utf-8", errors="replace")

    def fetch_remote_release(self, *, force_refresh: bool = False) -> Dict[str, Any]:
        if self._remote_release_cache is not None and not force_refresh:
            return self._remote_release_cache
        repository = os.getenv("REVERIE_RELEASE_REPOSITORY") or self.RELEASE_REPOSITORY
        try:
            release = self.github_json(f"https://api.github.com/repos/{repository}/releases/latest")
            assets = [
                {
                    "name": str(asset.get("name") or ""),
                    "size": int(asset.get("size") or 0),
                    "download_url": str(asset.get("browser_download_url") or ""),
                    "content_type": str(asset.get("content_type") or ""),
                    "updated_at": str(asset.get("updated_at") or ""),
                }
                for asset in release.get("assets", []) or []
                if isinstance(asset, dict)
            ]
            manifest = self.resolve_remote_plugin_manifest(release, assets)
            payload = {
                "success": True,
                "repository": repository,
                "tag_name": release.get("tag_name", ""),
                "name": release.get("name", ""),
                "published_at": release.get("published_at", ""),
                "html_url": release.get("html_url", ""),
                "assets": assets,
                "manifest": manifest,
            }
        except Exception as exc:
            payload = {
                "success": False,
                "repository": repository,
                "error": str(exc),
                "assets": [],
                "manifest": {"schema": self.RELEASE_SCHEMA, "plugins": []},
            }
        self._remote_release_cache = payload
        return payload

    def resolve_remote_plugin_manifest(self, release: Dict[str, Any], assets: list[Dict[str, Any]]) -> Dict[str, Any]:
        manifest_asset = next((asset for asset in assets if asset["name"].lower() == "plugins-manifest.json"), None)
        if manifest_asset and manifest_asset.get("download_url"):
            try:
                payload = json.loads(self.fetch_text_url(manifest_asset["download_url"]))
                if isinstance(payload, dict) and payload.get("schema") == self.RELEASE_SCHEMA:
                    return payload
            except Exception:
                pass
        return self.infer_plugin_manifest_from_assets(release, assets)

    def infer_plugin_manifest_from_assets(self, release: Dict[str, Any], assets: list[Dict[str, Any]]) -> Dict[str, Any]:
        plugins = []
        by_name = {asset["name"].lower(): asset for asset in assets}
        expected = {
            "blender": "reverie-blender.exe",
            "godot": "reverie-godot.exe",
            "o3de": "reverie-o3de.exe",
            "game_models": "reverie-game-models.exe",
        }
        for plugin_id, asset_name in expected.items():
            asset = by_name.get(asset_name.lower())
            if not asset:
                continue
            plugins.append(
                {
                    "id": plugin_id,
                    "name": plugin_id.replace("_", " ").title(),
                    "version": str(release.get("tag_name") or "latest"),
                    "asset_name": asset["name"],
                    "download_url": asset["download_url"],
                    "sha256": "",
                    "size": asset["size"],
                    "capabilities": [],
                    "manifest": {},
                }
            )
        return {
            "schema": self.RELEASE_SCHEMA,
            "generated_at": str(release.get("published_at") or ""),
            "commit": str(release.get("target_commitish") or ""),
            "cli_asset": next((asset for asset in assets if asset["name"].lower() == "reverie.exe"), None),
            "plugins": plugins,
            "inferred": True,
        }

    def emit_state(self, request_id: Any, event_type: str = "state") -> None:
        emit(
            {
                "id": request_id,
                "type": event_type,
                "project_root": str(self.project_root),
                "config": self.summarize_config(),
                "sessions": self.summarize_sessions(),
                "tools": self.summarize_tools(),
                "runtime": self.runtime_info(),
                "git": self.git_status_summary(),
            }
        )

    def runtime_info(self) -> Dict[str, Any]:
        from reverie.config import get_app_root
        from reverie.version import __version__

        executable = Path(sys.executable).resolve()
        return {
            "kind": "reverie-sdk-bridge",
            "runtime_root": str(RUNTIME_ROOT),
            "package_root": str(PACKAGE_ROOT),
            "app_root": str(get_app_root()),
            "executable": str(executable),
            "frozen": bool(getattr(sys, "frozen", False)),
            "version": __version__,
            "python": sys.version.split()[0],
        }

    def git_status_summary(self) -> Dict[str, Any]:
        root = Path(self.project_root)
        try:
            result = subprocess.run(
                ["git", "-C", str(root), "status", "--short", "--branch"],
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=5,
                check=False,
            )
        except Exception as exc:
            return {"available": False, "branch": "", "changes": [], "error": str(exc)}

        if result.returncode != 0:
            return {
                "available": False,
                "branch": "",
                "changes": [],
                "error": (result.stderr or result.stdout or "").strip(),
            }

        lines = [line for line in str(result.stdout or "").splitlines() if line.strip()]
        branch = lines[0].replace("##", "", 1).strip() if lines else ""
        changes = lines[1:]
        return {
            "available": True,
            "branch": branch,
            "changes": changes[:200],
            "change_count": len(changes),
            "dirty": bool(changes),
        }

    def handle_hello(self, request_id: Any, payload: Dict[str, Any]) -> None:
        emit({"id": request_id, "type": "ready", **self.runtime_info()})

    def handle_locate_runtime(self, request_id: Any, payload: Dict[str, Any]) -> None:
        emit({"id": request_id, "type": "runtime", **self.runtime_info()})

    def handle_initialize(self, request_id: Any, payload: Dict[str, Any]) -> None:
        root = Path(str(payload.get("projectRoot") or self.project_root)).expanduser()
        self.ensure_interface(root)
        self.emit_state(request_id)

    def handle_get_state(self, request_id: Any, payload: Dict[str, Any]) -> None:
        self.ensure_interface()
        self.emit_state(request_id)

    def handle_set_workspace(self, request_id: Any, payload: Dict[str, Any]) -> None:
        root = Path(str(payload.get("projectRoot") or "")).expanduser()
        self.ensure_interface(root)
        self.emit_state(request_id)

    def handle_set_mode(self, request_id: Any, payload: Dict[str, Any]) -> None:
        from reverie.modes import normalize_mode

        interface = self.ensure_interface()
        config = interface.config_manager.load()
        config.mode = normalize_mode(payload.get("mode") or "reverie")
        interface.config_manager.save(config)
        if interface.agent is not None:
            interface._init_agent(config_override=config, persist_config_changes=False)
        self.emit_state(request_id)

    def handle_list_settings(self, request_id: Any, payload: Dict[str, Any]) -> None:
        emit({"id": request_id, "type": "settings", "settings": self.summarize_settings()})

    def handle_set_setting(self, request_id: Any, payload: Dict[str, Any]) -> None:
        from reverie.settings_catalog import apply_setting_value

        interface = self.ensure_interface()
        key = str(payload.get("key") or "").strip()
        value = payload.get("value")
        config = interface.config_manager.load()
        success, message, reinit = apply_setting_value(
            config,
            interface.config_manager,
            getattr(interface, "rules_manager", None),
            key,
            value,
        )
        if success and key != "use_workspace_config":
            interface.config_manager.save(config)
        if success:
            if reinit and interface.agent is not None:
                interface._init_agent(config_override=interface.config_manager.load(), persist_config_changes=False)
            elif interface.agent is not None:
                interface._bind_agent_runtime_context(interface.config_manager.load())
                interface._refresh_agent_prompt_guidance()
        emit({"id": request_id, "type": "setting.updated", "success": success, "message": message, "key": key})
        emit({"id": request_id, "type": "settings", "settings": self.summarize_settings()})
        self.emit_state(request_id, event_type="state")

    def handle_save_preferences(self, request_id: Any, payload: Dict[str, Any]) -> None:
        from reverie.config import normalize_thinking_output_style, normalize_tool_output_style

        interface = self.ensure_interface()
        config = interface.config_manager.load()
        if "stream_responses" in payload:
            config.stream_responses = bool(payload.get("stream_responses"))
        if "auto_index" in payload:
            config.auto_index = bool(payload.get("auto_index"))
        if "show_status_line" in payload:
            config.show_status_line = bool(payload.get("show_status_line"))
        if "theme" in payload:
            config.theme = str(payload.get("theme") or "default").strip() or "default"
        if "tool_output_style" in payload:
            config.tool_output_style = normalize_tool_output_style(payload.get("tool_output_style"), "compact")
        if "thinking_output_style" in payload:
            config.thinking_output_style = normalize_thinking_output_style(payload.get("thinking_output_style"), "full")
        if "api_timeout" in payload:
            config.api_timeout = max(5, int(payload.get("api_timeout") or 60))
        if "api_max_retries" in payload:
            config.api_max_retries = max(0, int(payload.get("api_max_retries") or 0))

        interface.config_manager.save(config)
        if interface.agent is not None:
            interface._bind_agent_runtime_context(config)
            interface._refresh_agent_prompt_guidance()
        self.emit_state(request_id)

    def handle_save_model(self, request_id: Any, payload: Dict[str, Any]) -> None:
        from reverie.config import ModelConfig

        interface = self.ensure_interface()
        config = interface.config_manager.load()
        index = payload.get("index")
        model = ModelConfig(
            model=str(payload.get("model") or "").strip(),
            model_display_name=str(payload.get("model_display_name") or payload.get("model") or "").strip(),
            base_url=str(payload.get("base_url") or "").strip(),
            api_key=str(payload.get("api_key") or "").strip(),
            max_context_tokens=int(payload.get("max_context_tokens") or 128000),
            provider=str(payload.get("provider") or "openai-sdk").strip(),
            endpoint=str(payload.get("endpoint") or "").strip(),
            thinking_mode=payload.get("thinking_mode") or None,
            custom_headers=payload.get("custom_headers") if isinstance(payload.get("custom_headers"), dict) else {},
        )

        if index is None or int(index) < 0 or int(index) >= len(config.models):
            config.models.append(model)
            config.active_model_index = len(config.models) - 1
        else:
            config.models[int(index)] = model
            config.active_model_index = int(index)
        config.active_model_source = "standard"
        interface.config_manager.save(config)
        self.emit_state(request_id)

    def handle_delete_model(self, request_id: Any, payload: Dict[str, Any]) -> None:
        interface = self.ensure_interface()
        index = int(payload.get("index") or -1)
        ok = interface.config_manager.remove_model(index)
        emit({"id": request_id, "type": "model.deleted", "success": ok})
        self.emit_state(request_id, event_type="state")

    def handle_select_model(self, request_id: Any, payload: Dict[str, Any]) -> None:
        interface = self.ensure_interface()
        index = int(payload.get("index") or 0)
        ok = interface.config_manager.set_active_model(index)
        emit({"id": request_id, "type": "model.selected", "success": ok})
        self.emit_state(request_id, event_type="state")

    def handle_save_builtin_source(self, request_id: Any, payload: Dict[str, Any]) -> None:
        from reverie.codex import normalize_codex_config
        from reverie.config import EXTERNAL_MODEL_SOURCES
        from reverie.geminicli import normalize_geminicli_config
        from reverie.modelscope import normalize_modelscope_config
        from reverie.nvidia import apply_nvidia_thinking_choice, normalize_nvidia_config

        interface = self.ensure_interface()
        source = str(payload.get("source") or "").strip().lower()
        if source not in EXTERNAL_MODEL_SOURCES:
            raise ValueError(f"Unsupported built-in source: {source}")

        config = interface.config_manager.load()
        selected_model_id = str(payload.get("selected_model_id") or payload.get("model") or "").strip()
        api_key = str(payload.get("api_key") or "").strip()
        api_url = str(payload.get("api_url") or "").strip()
        endpoint = str(payload.get("endpoint") or "").strip()

        if source == "geminicli":
            cfg = normalize_geminicli_config(getattr(config, "geminicli", {}))
            if selected_model_id:
                cfg["selected_model_id"] = selected_model_id
            if api_url:
                cfg["api_url"] = api_url
            cfg["endpoint"] = endpoint
            if "project_id" in payload:
                cfg["project_id"] = str(payload.get("project_id") or "").strip()
            config.geminicli = normalize_geminicli_config(cfg)
        elif source == "codex":
            cfg = normalize_codex_config(getattr(config, "codex", {}))
            if selected_model_id:
                cfg["selected_model_id"] = selected_model_id
            if api_url:
                cfg["api_url"] = api_url
            cfg["endpoint"] = endpoint
            if payload.get("reasoning_effort"):
                cfg["reasoning_effort"] = str(payload.get("reasoning_effort") or "").strip().lower()
            config.codex = normalize_codex_config(cfg)
        elif source == "nvidia":
            cfg = normalize_nvidia_config(getattr(config, "nvidia", {}))
            if api_key:
                cfg["api_key"] = api_key
            if selected_model_id:
                cfg["selected_model_id"] = selected_model_id
            if api_url:
                cfg["api_url"] = api_url
            cfg["endpoint"] = endpoint
            if payload.get("thinking_choice"):
                cfg = apply_nvidia_thinking_choice(cfg, selected_model_id or cfg.get("selected_model_id"), payload.get("thinking_choice"))
            config.nvidia = normalize_nvidia_config(cfg)
        elif source == "modelscope":
            cfg = normalize_modelscope_config(getattr(config, "modelscope", {}))
            if api_key:
                cfg["api_key"] = api_key
            if selected_model_id:
                cfg["selected_model_id"] = selected_model_id
            if api_url:
                cfg["api_url"] = api_url
            config.modelscope = normalize_modelscope_config(cfg)

        if bool(payload.get("activate", True)):
            config.active_model_source = source
        interface.config_manager.save(config)
        if interface.agent is not None:
            interface._init_agent(config_override=interface.config_manager.load(), persist_config_changes=False)
        emit({"id": request_id, "type": "builtin.source.saved", "source": source, "success": True})
        self.emit_state(request_id, event_type="state")

    def handle_select_builtin_source(self, request_id: Any, payload: Dict[str, Any]) -> None:
        from reverie.config import EXTERNAL_MODEL_SOURCES

        interface = self.ensure_interface()
        source = str(payload.get("source") or "").strip().lower()
        if source not in EXTERNAL_MODEL_SOURCES:
            raise ValueError(f"Unsupported built-in source: {source}")
        config = interface.config_manager.load()
        config.active_model_source = source
        interface.config_manager.save(config)
        if interface.agent is not None:
            interface._init_agent(config_override=interface.config_manager.load(), persist_config_changes=False)
        emit({"id": request_id, "type": "builtin.source.selected", "source": source, "success": True})
        self.emit_state(request_id, event_type="state")

    def handle_test_providers(self, request_id: Any, payload: Dict[str, Any]) -> None:
        from reverie.provider_smoke import BUILTIN_PROVIDER_NAMES, run_provider_smoke

        providers = payload.get("providers")
        if isinstance(providers, str):
            wanted = [part.strip().lower() for part in providers.split(",") if part.strip()]
        elif isinstance(providers, list):
            wanted = [str(part or "").strip().lower() for part in providers if str(part or "").strip()]
        else:
            wanted = list(BUILTIN_PROVIDER_NAMES)
        timeout_seconds = max(5, int(payload.get("timeout_seconds") or payload.get("timeout") or 45))
        config_path = payload.get("config_path")
        emit({"id": request_id, "type": "provider.smoke.started", "providers": wanted})
        results = run_provider_smoke(
            wanted,
            config_path=Path(str(config_path)).expanduser() if config_path else None,
            timeout_seconds=timeout_seconds,
        )
        emit({"id": request_id, "type": "provider.smoke", "results": [result.to_dict() for result in results]})

    def handle_new_session(self, request_id: Any, payload: Dict[str, Any]) -> None:
        interface = self.ensure_interface()
        name = str(payload.get("name") or "").strip() or f"GUI Session {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
        session = interface.session_manager.create_session(name=name)
        if interface.agent is not None:
            interface.agent.set_history(session.messages)
        self.emit_state(request_id)

    def handle_switch_session(self, request_id: Any, payload: Dict[str, Any]) -> None:
        interface = self.ensure_interface()
        session = interface.session_manager.load_session(str(payload.get("sessionId") or ""))
        if session is None:
            raise ValueError("Session not found.")
        if interface.agent is not None:
            interface.agent.set_history(session.messages)
        self.emit_state(request_id)

    def handle_rename_session(self, request_id: Any, payload: Dict[str, Any]) -> None:
        interface = self.ensure_interface()
        session_id = str(payload.get("sessionId") or "").strip()
        name = str(payload.get("name") or "").strip()
        if not session_id:
            raise ValueError("Session id is required.")
        if not name:
            raise ValueError("Session name is required.")
        session = interface.session_manager.load_session(session_id)
        if session is None:
            raise ValueError("Session not found.")
        session.name = name
        interface.session_manager.save_session(session)
        emit({"id": request_id, "type": "session.renamed", "success": True, "session_id": session_id, "name": name})
        self.emit_state(request_id, event_type="state")

    def handle_delete_session(self, request_id: Any, payload: Dict[str, Any]) -> None:
        interface = self.ensure_interface()
        session_id = str(payload.get("sessionId") or "").strip()
        if not session_id:
            raise ValueError("Session id is required.")
        session_path = interface.session_manager.sessions_dir / f"{session_id}.json"
        existed_before = session_path.exists()
        ok = interface.session_manager.delete_session(session_id)
        remaining = [item for item in interface.session_manager.list_sessions() if item.id != session_id]
        replacement = interface.session_manager.load_session(remaining[0].id) if remaining else None
        if replacement is None:
            replacement = interface.session_manager.create_session(name=f"GUI Session {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        if interface.agent is not None and replacement is not None:
            interface.agent.set_history(replacement.messages)
        emit(
            {
                "id": request_id,
                "type": "session.deleted",
                "success": ok,
                "session_id": session_id,
                "session_path": str(session_path),
                "existed_before": existed_before,
                "file_exists_after": session_path.exists(),
                "replacement_session_id": getattr(replacement, "id", ""),
            }
        )
        self.emit_state(request_id, event_type="state")

    def handle_clear_session(self, request_id: Any, payload: Dict[str, Any]) -> None:
        interface = self.ensure_interface()
        session = interface.session_manager.get_current_session()
        if session is None:
            session, _ = interface.session_manager.ensure_session()
        session.messages = []
        interface.session_manager.save_session(session)
        if interface.agent is not None:
            interface.agent.set_history([])
        self.emit_state(request_id)

    def handle_list_plugins(self, request_id: Any, payload: Dict[str, Any]) -> None:
        emit({"id": request_id, "type": "plugins", "plugins": self.summarize_plugins(force_refresh=False, include_remote=True)})

    def handle_refresh_plugins(self, request_id: Any, payload: Dict[str, Any]) -> None:
        self._remote_release_cache = None
        emit({"id": request_id, "type": "plugins.refresh.started"})
        emit({"id": request_id, "type": "plugins", "plugins": self.summarize_plugins(force_refresh=True, include_remote=True)})
        if self.ensure_interface().agent is not None:
            self.ensure_interface()._refresh_agent_prompt_guidance()

    def handle_list_remote_releases(self, request_id: Any, payload: Dict[str, Any]) -> None:
        force = bool(payload.get("force"))
        emit({"id": request_id, "type": "remote.release", "remote": self.fetch_remote_release(force_refresh=force)})

    def handle_install_remote_plugin(self, request_id: Any, payload: Dict[str, Any]) -> None:
        manager = self.plugin_manager()
        plugin_id = str(payload.get("pluginId") or payload.get("id") or "").strip()
        asset_name = str(payload.get("assetName") or "").strip()
        download_url = str(payload.get("downloadUrl") or "").strip()
        sha256 = str(payload.get("sha256") or "").strip().lower()

        if not download_url:
            remote = self.fetch_remote_release(force_refresh=False)
            for plugin in (remote.get("manifest", {}) or {}).get("plugins", []) or []:
                if str(plugin.get("id") or "") == plugin_id:
                    asset_name = asset_name or str(plugin.get("asset_name") or "")
                    download_url = str(plugin.get("download_url") or "")
                    sha256 = sha256 or str(plugin.get("sha256") or "").lower()
                    break
        if not download_url:
            raise ValueError("Remote plugin download URL was not found.")
        if not asset_name:
            asset_name = Path(download_url.split("?", 1)[0]).name or f"reverie-{plugin_id}.exe"

        manager.ensure_install_root()
        target_path = (manager.install_root / asset_name).resolve()
        temp_path = target_path.with_name(f"{target_path.name}.download-{os.getpid()}.tmp")
        emit({"id": request_id, "type": "plugin.install.started", "plugin_id": plugin_id, "asset_name": asset_name})
        hasher = hashlib.sha256()
        request = urllib.request.Request(download_url, headers={"User-Agent": "Reverie-UI-SDK/1.0"})
        with urllib.request.urlopen(request, timeout=120) as response:
            total = int(response.headers.get("Content-Length") or 0)
            downloaded = 0
            last_percent = -1
            with open(temp_path, "wb") as handle:
                while True:
                    chunk = response.read(1024 * 1024)
                    if not chunk:
                        break
                    hasher.update(chunk)
                    handle.write(chunk)
                    downloaded += len(chunk)
                    percent = int(downloaded * 100 / total) if total else 0
                    if total and (percent >= last_percent + 2 or percent == 100):
                        last_percent = percent
                        emit(
                            {
                                "id": request_id,
                                "type": "plugin.install.progress",
                                "plugin_id": plugin_id,
                                "asset_name": asset_name,
                                "downloaded": downloaded,
                                "total": total,
                                "percent": percent,
                            }
                        )
                    elif not total:
                        emit(
                            {
                                "id": request_id,
                                "type": "plugin.install.progress",
                                "plugin_id": plugin_id,
                                "asset_name": asset_name,
                                "downloaded": downloaded,
                                "total": 0,
                                "percent": 0,
                            }
                        )
        digest = hasher.hexdigest()
        if sha256 and digest.lower() != sha256:
            temp_path.unlink(missing_ok=True)
            raise ValueError(f"SHA256 mismatch for {asset_name}: expected {sha256}, got {digest}")
        shutil.move(str(temp_path), str(target_path))
        manager.scan()
        emit(
            {
                "id": request_id,
                "type": "plugin.installed",
                "success": True,
                "plugin_id": plugin_id,
                "target_path": str(target_path),
                "sha256": digest,
            }
        )
        emit({"id": request_id, "type": "plugins", "plugins": self.summarize_plugins(force_refresh=True, include_remote=True)})

    def handle_build_plugin(self, request_id: Any, payload: Dict[str, Any]) -> None:
        manager = self.plugin_manager()
        plugin_id = str(payload.get("pluginId") or payload.get("id") or "").strip()
        if not plugin_id:
            raise ValueError("Plugin id is required.")
        emit({"id": request_id, "type": "plugin.build.started", "plugin_id": plugin_id})
        result = manager.build_source_plugin(
            plugin_id,
            install=bool(payload.get("install", True)),
            overwrite_install=bool(payload.get("overwrite", True)),
        )
        emit({"id": request_id, "type": "plugin.build.complete", "plugin_id": plugin_id, "result": json_safe(result)})
        emit({"id": request_id, "type": "plugins", "plugins": self.summarize_plugins(force_refresh=True, include_remote=True)})

    def handle_deploy_plugin(self, request_id: Any, payload: Dict[str, Any]) -> None:
        manager = self.plugin_manager()
        plugin_id = str(payload.get("pluginId") or payload.get("id") or "").strip()
        if not plugin_id:
            raise ValueError("Plugin id is required.")
        archive_path = str(payload.get("archivePath") or payload.get("archive") or "").strip()
        if hasattr(manager, "deploy_sdk_package"):
            result = manager.deploy_sdk_package(plugin_id, archive_path=archive_path, overwrite=bool(payload.get("overwrite", False)))
        else:
            result = manager.materialize_sdk_package(plugin_id, overwrite=bool(payload.get("overwrite", False)))
        emit({"id": request_id, "type": "plugin.deploy.complete", "plugin_id": plugin_id, "result": json_safe(result)})
        emit({"id": request_id, "type": "plugins", "plugins": self.summarize_plugins(force_refresh=True, include_remote=True)})

    def handle_inspect_plugin(self, request_id: Any, payload: Dict[str, Any]) -> None:
        manager = self.plugin_manager()
        plugin_id = str(payload.get("pluginId") or payload.get("id") or "").strip()
        if not plugin_id:
            raise ValueError("Plugin id is required.")
        record = manager.get_record(plugin_id, force_refresh=True)
        validation = {}
        try:
            validation = manager.validate_source_plugin(plugin_id)
        except Exception as exc:
            validation = {"success": False, "error": str(exc)}
        emit(
            {
                "id": request_id,
                "type": "plugin.inspect",
                "plugin_id": plugin_id,
                "record": self.plugin_record_to_dict(record) if record else None,
                "validation": json_safe(validation),
            }
        )

    def handle_call_plugin_command(self, request_id: Any, payload: Dict[str, Any]) -> None:
        manager = self.plugin_manager()
        plugin_id = str(payload.get("pluginId") or payload.get("id") or "").strip()
        command_name = str(payload.get("command") or payload.get("commandName") or "").strip()
        arguments = payload.get("arguments") if isinstance(payload.get("arguments"), dict) else {}
        if not plugin_id or not command_name:
            raise ValueError("Plugin id and command are required.")
        emit({"id": request_id, "type": "plugin.command.started", "plugin_id": plugin_id, "command": command_name})
        result = manager.call_tool(plugin_id, command_name, arguments)
        emit({"id": request_id, "type": "plugin.command.complete", "plugin_id": plugin_id, "command": command_name, "result": json_safe(result)})

    def handle_list_tools(self, request_id: Any, payload: Dict[str, Any]) -> None:
        emit({"id": request_id, "type": "tools", "tools": self.summarize_tools(payload.get("mode"))})

    def handle_git_status(self, request_id: Any, payload: Dict[str, Any]) -> None:
        root = Path(str(payload.get("projectRoot") or self.project_root)).expanduser()
        if root.exists() and root.is_dir():
            self.project_root = root.resolve()
        emit({"id": request_id, "type": "git.status", "git": self.git_status_summary()})

    def handle_diagnostics(self, request_id: Any, payload: Dict[str, Any]) -> None:
        interface = self.ensure_interface()
        config = interface.config_manager.load()
        active_model = config.active_model
        emit(
            {
                "id": request_id,
                "type": "diagnostics",
                "items": [
                    {"label": "Workspace", "value": str(self.project_root), "ok": self.project_root.exists()},
                    {"label": "Config", "value": str(interface.config_manager.config_path), "ok": True},
                    {"label": "Active model", "value": getattr(active_model, "model_display_name", "") if active_model else "not configured", "ok": bool(active_model)},
                    {"label": "Runtime", "value": str(RUNTIME_ROOT), "ok": True},
                    {"label": "Executable", "value": str(sys.executable), "ok": True},
                    {"label": "Python", "value": sys.version.split()[0], "ok": True},
                ],
            }
        )

    def handle_index_workspace(self, request_id: Any, payload: Dict[str, Any]) -> None:
        from reverie.config import get_project_data_dir
        from reverie.context_engine import CodebaseIndexer

        root = Path(str(payload.get("projectRoot") or self.project_root)).expanduser().resolve()
        self.ensure_interface(root)
        emit({"id": request_id, "type": "index.started", "project_root": str(root)})

        def progress(snapshot: Any) -> None:
            emit(
                {
                    "id": request_id,
                    "type": "index.progress",
                    "stage": getattr(snapshot, "stage", ""),
                    "message": getattr(snapshot, "message", ""),
                    "percent": getattr(snapshot, "display_percent", getattr(snapshot, "percent", 0.0)),
                    "current_file": getattr(snapshot, "current_file", ""),
                    "files_scanned": getattr(snapshot, "files_scanned", 0),
                    "files_parsed": getattr(snapshot, "files_parsed", 0),
                    "files_failed": getattr(snapshot, "files_failed", 0),
                    "files_skipped": getattr(snapshot, "files_skipped", 0),
                }
            )

        indexer = CodebaseIndexer(root, cache_dir=get_project_data_dir(root) / "context_cache")
        result = indexer.full_index(progress_callback=progress)
        emit(
            {
                "id": request_id,
                "type": "index.complete",
                "result": object_to_dict(
                    result,
                    (
                        "files_scanned",
                        "files_parsed",
                        "files_failed",
                        "files_skipped",
                        "symbols_extracted",
                        "dependencies_extracted",
                        "parse_time_ms",
                        "total_time_ms",
                        "total_bytes",
                        "errors",
                        "warnings",
                        "fatal_errors",
                    ),
                ),
                "success": bool(getattr(result, "success", False)),
            }
        )

    def handle_chat(self, request_id: Any, payload: Dict[str, Any]) -> None:
        from reverie.agent import STREAM_EVENT_MARKER, THINKING_END_MARKER, THINKING_START_MARKER, decode_stream_event
        from reverie.agent.agent import HIDDEN_STREAM_TOKEN

        prompt = str(payload.get("message") or "").strip()
        if not prompt:
            raise ValueError("Message is empty.")

        interface = self.ensure_interface(Path(str(payload.get("projectRoot") or self.project_root)))
        config = interface.config_manager.load()
        if payload.get("mode"):
            from reverie.modes import normalize_mode

            config.mode = normalize_mode(payload.get("mode"))
        config.stream_responses = True

        emit({"id": request_id, "type": "chat.started"})
        interface._runtime_config_override = interface._clone_config(config)
        try:
            interface._init_agent(config_override=config, persist_config_changes=False)
            if interface.agent is None:
                raise ValueError("No active model is configured.")

            session_id = str(payload.get("sessionId") or "")
            session = interface.session_manager.load_session(session_id) if session_id else None
            if session is None:
                session, _ = interface.session_manager.ensure_session()

            interface._sync_workspace_memory_message(session)
            interface.agent.set_history(session.messages)
            context_ready = interface.ensure_context_engine(announce=False)
            emit({"id": request_id, "type": "chat.context", "context_engine_initialized": bool(context_ready)})

            thinking = False
            response_text = []
            for chunk in interface.agent.process_message(prompt, stream=True, session_id=session.id, user_display_text=prompt):
                if chunk == THINKING_START_MARKER:
                    thinking = True
                    emit({"id": request_id, "type": "chat.thinking.start"})
                    continue
                if chunk == THINKING_END_MARKER:
                    thinking = False
                    emit({"id": request_id, "type": "chat.thinking.end"})
                    continue
                if chunk == HIDDEN_STREAM_TOKEN:
                    continue

                event = decode_stream_event(chunk) if isinstance(chunk, str) and chunk.startswith(STREAM_EVENT_MARKER) else None
                if event is not None:
                    emit({"id": request_id, "type": "chat.tool", "event": event})
                    continue

                event_type = "chat.thinking" if thinking else "chat.chunk"
                if not thinking:
                    response_text.append(chunk)
                emit({"id": request_id, "type": event_type, "chunk": chunk})

            interface.session_manager.update_messages(interface.agent.get_history())
            emit(
                {
                    "id": request_id,
                    "type": "chat.complete",
                    "message": "".join(response_text),
                    "session": object_to_dict(session, ("id", "name", "created_at", "updated_at")),
                }
            )
            self.emit_state(request_id, event_type="state")
        finally:
            interface._runtime_config_override = None

    def handle_shutdown(self, request_id: Any, payload: Dict[str, Any]) -> None:
        emit({"id": request_id, "type": "shutdown"})
        raise SystemExit(0)


def main() -> int:
    bridge = ReverieUiBridge()
    emit({"type": "ready", **bridge.runtime_info()})
    for raw in sys.stdin:
        line = raw.strip()
        if not line:
            continue
        try:
            message = json.loads(line)
        except Exception as exc:
            emit({"type": "error", "error": f"Invalid JSON: {exc}"})
            continue
        bridge.dispatch(message if isinstance(message, dict) else {})
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
