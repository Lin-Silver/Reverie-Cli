from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from reverie.config import Config
from reverie.plugin.runtime_manager import RuntimePluginManager
from reverie.sdk_bridge import ReverieUiBridge, normalize_jsonl_input
from reverie.session.manager import SessionManager
from reverie.settings_catalog import apply_setting_value, get_setting_items


class DummyConfigManager:
    workspace_config_path = Path("workspace-config.json")
    global_config_path = Path("global-config.json")

    def __init__(self) -> None:
        self.workspace_mode = False

    def is_workspace_mode(self) -> bool:
        return self.workspace_mode

    def has_workspace_config(self) -> bool:
        return True

    def has_global_config(self) -> bool:
        return True

    def set_workspace_config_enabled(self, enabled: bool) -> bool:
        self.workspace_mode = bool(enabled)
        return True

    def set_workspace_mode(self, enabled: bool) -> None:
        self.workspace_mode = bool(enabled)

    def copy_config_to_workspace(self) -> bool:
        self.workspace_mode = True
        return True

    def load(self) -> Config:
        config = Config()
        config.use_workspace_config = self.workspace_mode
        return config

    def save(self, config: Config) -> None:
        self.workspace_mode = bool(config.use_workspace_config)


class DummyRulesManager:
    def __init__(self) -> None:
        self._rules: list[str] = []

    def get_rules(self) -> list[str]:
        return list(self._rules)

    def save(self) -> None:
        return None


def test_shared_settings_catalog_and_apply_setting_value() -> None:
    config = Config()
    manager = DummyConfigManager()
    rules = DummyRulesManager()

    keys = {item["key"] for item in get_setting_items(config, manager, rules)}
    assert {"mode", "tool_output_style", "thinking_output_style", "rules", "use_workspace_config"} <= keys

    ok, message, reinit = apply_setting_value(config, manager, rules, "tool_output_style", "full")
    assert ok, message
    assert config.tool_output_style == "full"
    assert reinit is False

    ok, message, reinit = apply_setting_value(config, manager, rules, "rules", "Use tests\nKeep changes scoped")
    assert ok, message
    assert rules.get_rules() == ["Use tests", "Keep changes scoped"]
    assert reinit is True


def test_reverie_ui_exposes_reverie_light_dark_theme_and_shortcuts() -> None:
    ui_root = Path(__file__).resolve().parents[1] / "Reverie UI" / "src" / "Reverie.UI"
    html = (ui_root / "wwwroot" / "index.html").read_text(encoding="utf-8")
    css = (ui_root / "wwwroot" / "styles.css").read_text(encoding="utf-8")
    js = (ui_root / "wwwroot" / "app.js").read_text(encoding="utf-8")

    assert 'value="reverie-dark"' in html
    assert 'value="reverie-light"' in html
    assert 'class="shortcut-grid"' in html
    assert ':root[data-theme="reverie"][data-appearance="dark"]' in css
    assert ':root[data-theme="reverie"][data-appearance="light"]' in css
    assert "--accent: #ff8fc7" in css
    assert "--accent: #db4f9b" in css
    assert "function applyTheme" in js
    assert "setHostTheme" in js
    assert "event.shiftKey && key === \"t\"" in js


def test_sdk_bridge_accepts_bom_prefixed_jsonl_frames() -> None:
    raw = "\ufeff{\"id\":\"init\",\"action\":\"initialize\",\"payload\":{}}\n"
    mojibake_raw = "\xef\xbb\xbf{\"id\":\"init\",\"action\":\"initialize\",\"payload\":{}}\n"

    assert normalize_jsonl_input(raw).startswith("{")
    assert json.loads(normalize_jsonl_input(raw))["action"] == "initialize"
    assert normalize_jsonl_input(mojibake_raw).startswith("{")
    assert json.loads(normalize_jsonl_input(mojibake_raw))["action"] == "initialize"


def test_remote_plugin_manifest_can_be_inferred_from_release_assets() -> None:
    bridge = ReverieUiBridge()
    release = {"tag_name": "latest", "published_at": "2026-05-03T00:00:00Z", "target_commitish": "abc123"}
    assets = [
        {"name": "reverie.exe", "download_url": "https://example.test/reverie.exe", "size": 10},
        {"name": "reverie-blender.exe", "download_url": "https://example.test/reverie-blender.exe", "size": 20},
        {"name": "reverie-godot.exe", "download_url": "https://example.test/reverie-godot.exe", "size": 30},
        {"name": "reverie-o3de.exe", "download_url": "https://example.test/reverie-o3de.exe", "size": 40},
        {"name": "reverie-game-models.exe", "download_url": "https://example.test/reverie-game-models.exe", "size": 50},
    ]

    manifest = bridge.infer_plugin_manifest_from_assets(release, assets)
    assert manifest["schema"] == bridge.RELEASE_SCHEMA
    assert {plugin["id"] for plugin in manifest["plugins"]} == {"blender", "godot", "o3de", "game_models"}


def test_official_source_plugins_validate(tmp_path: Path) -> None:
    source_root = Path(__file__).resolve().parents[1] / "plugins"
    manager = RuntimePluginManager(tmp_path, source_root=source_root)

    for plugin_id in ("blender", "godot", "o3de", "game_models"):
        result = manager.validate_source_plugin(plugin_id)
        assert result["success"], f"{plugin_id}: {result.get('errors')}"


def test_blender_plugin_exposes_mcp_lifecycle_commands() -> None:
    plugin_path = Path(__file__).resolve().parents[1] / "plugins" / "blender" / "plugin.py"
    handshake = subprocess.run(
        [sys.executable, str(plugin_path), "-RC"],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=True,
    )
    payload = json.loads(handshake.stdout)
    command_names = {command["name"] for command in payload.get("commands", [])}
    assert {
        "mcp_install",
        "mcp_start",
        "mcp_stop",
        "mcp_status",
        "mcp_info",
    } <= command_names

    dry_run = subprocess.run(
        [sys.executable, str(plugin_path), "-RC-CALL", "mcp_install", json.dumps({"dry_run": True})],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=True,
    )
    result = json.loads(dry_run.stdout)
    assert result["success"]
    assert result["data"]["storage_policy"] == "plugin-local"
    assert result["data"]["mcp"]["server_name"] == "blender"


def test_session_delete_removes_json_and_index_entry(tmp_path: Path) -> None:
    manager = SessionManager(tmp_path, project_root=tmp_path / "workspace")
    first = manager.create_session("First")
    first_path = manager.sessions_dir / f"{first.id}.json"
    second = manager.create_session("Second")

    assert first_path.exists()
    assert manager.delete_session(first.id)
    assert not first_path.exists()
    assert first.id not in {item.id for item in manager.list_sessions()}
    assert second.id in {item.id for item in manager.list_sessions()}
