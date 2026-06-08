from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from reverie.config import Config
from reverie.codex import CODEX_CLIENT_VERSION, CODEX_DEFAULT_MAX_CONTEXT_TOKENS, get_codex_model_catalog
from reverie.config import Config, EXTERNAL_MODEL_SOURCES
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


def workspace_root() -> Path:
    py_root = Path(__file__).resolve().parents[1]
    if (py_root / "Reverie UI").exists():
        return py_root
    return py_root.parent


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
    ui_root = workspace_root() / "Reverie UI" / "src" / "Reverie.UI"
    html = (ui_root / "wwwroot" / "index.html").read_text(encoding="utf-8")
    css = (ui_root / "wwwroot" / "styles.css").read_text(encoding="utf-8")
    js = (ui_root / "wwwroot" / "app.js").read_text(encoding="utf-8")

    assert 'value="reverie-dark"' in html
    assert 'value="reverie-light"' in html
    assert 'href="../Assets/reverie.ico"' in html
    assert 'src="../Assets/reverie.ico"' in html
    assert 'id="totalsView"' in html
    assert 'class="shortcut-grid"' in html
    assert ':root[data-theme="reverie"][data-appearance="dark"]' in css
    assert ':root[data-theme="reverie"][data-appearance="light"]' in css
    assert "--accent: #ff9d45" in css
    assert "--accent: #c96a1a" in css
    assert "function applyTheme" in js
    assert "function renderTotals" in js
    assert "runAgentRegression" in js
    assert "setHostTheme" in js
    assert "event.shiftKey && key === \"t\"" in js
    assert "No custom provider profiles" in js
    assert "Built-in model source catalog is not available" in js
    assert '<select id="builtinSourceThinking"' in html
    assert '<option value="webgemini">WebGemini</option>' in html
    assert '<option value="aihubmix">AIhubMix</option>' in html
    assert 'id="modelSupportsVision"' in html
    assert "function populateBuiltinThinkingOptions" in js
    assert "function getVisibleBuiltinModels" in js
    assert 'aihubmix: "AIhubMix"' in js
    assert 'webgemini: "WebGemini"' in js
    assert "supports_vision" in js


def test_bundled_ui_runtime_bridge_exposes_model_source_actions() -> None:
    bridge = (workspace_root() / "ReverieCli-py" / "ui-runtime" / "reverie" / "sdk_bridge.py").read_text(encoding="utf-8")

    assert '"saveBuiltinSource": self.handle_save_builtin_source' in bridge
    assert '"selectBuiltinSource": self.handle_select_builtin_source' in bridge
    assert '"testProviders": self.handle_test_providers' in bridge
    assert '"builtin_sources": self.summarize_builtin_sources(config)' in bridge
    assert "get_codex_reasoning_catalog" in bridge
    assert "get_aihubmix_model_catalog" in bridge
    assert "get_webgemini_model_catalog" in bridge
    assert '"reasoning_choices": get_codex_reasoning_catalog' in bridge
    assert "get_nvidia_thinking_options" in bridge
    assert "def summarize_builtin_sources" in bridge


def test_codex_catalog_prefers_checked_out_source_models() -> None:
    catalog = get_codex_model_catalog()
    visible_ids = [str(item.get("id") or "") for item in catalog if str(item.get("visibility") or "list").lower() == "list"]

    assert visible_ids[:5] == ["gpt-5.5", "gpt-5.4", "gpt-5.4-mini", "gpt-5.3-codex", "gpt-5.2"]
    assert [item["id"] for item in catalog] == visible_ids + ["codex-auto-review"]
    assert all(item["context_length"] == 272_000 for item in catalog)
    assert CODEX_CLIENT_VERSION == "0.137.0"
    assert CODEX_DEFAULT_MAX_CONTEXT_TOKENS == 272_000


def test_gemini_cli_reverse_proxy_source_is_migrated_away() -> None:
    config = Config.from_dict({"active_model_source": "geminicli", "geminicli": {"selected_model_id": "legacy"}})

    assert "geminicli" not in EXTERNAL_MODEL_SOURCES
    assert config.active_model_source == "standard"
    assert "geminicli" not in config.to_dict()


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
    assert manifest["cli_asset"]["name"] == "reverie.exe"
    assert {plugin["id"] for plugin in manifest["plugins"]} == {"blender", "godot", "o3de", "game_models"}


def test_official_source_plugins_validate(tmp_path: Path) -> None:
    source_root = Path(__file__).resolve().parents[2] / "plugins"
    manager = RuntimePluginManager(tmp_path, source_root=source_root)

    for plugin_id in ("blender", "godot", "o3de", "game_models"):
        result = manager.validate_source_plugin(plugin_id)
        assert result["success"], f"{plugin_id}: {result.get('errors')}"


def test_blender_plugin_exposes_mcp_lifecycle_commands() -> None:
    plugin_path = Path(__file__).resolve().parents[2] / "plugins" / "blender" / "plugin.py"
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
