from pathlib import Path
import json

import reverie.config as config_module

from reverie.config import (
    Config,
    ConfigManager,
    _escape_invalid_json_string_control_chars,
    get_app_root,
    get_project_data_dir,
    normalize_tti_models,
)
from reverie.tools.mcp_resource_tools import ReadMcpResourceTool


def test_escape_invalid_json_string_control_chars_only_changes_string_payloads() -> None:
    raw = '{\n  "message": "line1\nline2\tend",\n  "count": 1\n}\n'
    repaired, changed = _escape_invalid_json_string_control_chars(raw)

    assert changed is True
    assert '"message": "line1\\nline2\\tend"' in repaired
    assert '\n  "count": 1\n' in repaired


def test_normalize_tti_models_preserves_gguf_auxiliary_metadata() -> None:
    models = normalize_tti_models(
        [
            {
                "path": "F:/Models/T2I/ernie-image-turbo-Q4_K_S.gguf",
                "display_name": "ernie-turbo",
                "format": "gguf",
                "clip_model": "F:/Models/T2I/ministral-3-3b.safetensors",
                "vae_model": "F:/Models/T2I/flux2-vae.safetensors",
                "recommended_steps": 8,
                "recommended_cfg": 1.0,
            }
        ]
    )

    assert models[0]["format"] == "gguf"
    assert models[0]["clip_model"].endswith("ministral-3-3b.safetensors")
    assert models[0]["vae_model"].endswith("flux2-vae.safetensors")
    assert models[0]["recommended_steps"] == 8
    assert models[0]["recommended_cfg"] == 1.0


def test_config_manager_repairs_invalid_control_chars_and_emits_notice(tmp_path: Path, monkeypatch) -> None:
    app_root = tmp_path / "app"
    project_root = tmp_path / "project"
    project_root.mkdir(parents=True, exist_ok=True)
    (app_root / ".reverie").mkdir(parents=True, exist_ok=True)

    monkeypatch.setattr("reverie.config.get_app_root", lambda: app_root)

    config_path = app_root / ".reverie" / "config.json"
    config_path.write_text(
        '{\n'
        '  "models": [\n'
        '    {\n'
        '      "model": "gpt-4",\n'
        '      "model_display_name": "GPT-4",\n'
        '      "base_url": "https://api.openai.com/v1",\n'
        '      "api_key": "line1\nline2"\n'
        '    }\n'
        '  ],\n'
        '  "active_model_index": 0,\n'
        '  "active_model_source": "standard"\n'
        '}\n',
        encoding="utf-8",
    )

    manager = ConfigManager(project_root)
    loaded = manager.load()
    notice = manager.consume_load_notice()

    assert loaded.models
    assert loaded.models[0].api_key == "line1\nline2"
    assert notice is not None
    assert notice["title"] == "Recovered malformed config"
    assert "Recovered malformed config at" in notice["detail"]

    repaired_text = config_path.read_text(encoding="utf-8")
    assert '"api_key": "line1\\nline2"' in repaired_text

    backups = sorted(config_path.parent.glob("config.json.invalid-*.bak"))
    assert backups


def test_get_app_root_uses_launcher_root_for_packaged_windows(tmp_path: Path, monkeypatch) -> None:
    launcher_root = tmp_path / "Program Files" / "Reverie"
    launcher_root.mkdir(parents=True, exist_ok=True)

    monkeypatch.setattr(config_module, "get_launcher_root", lambda: launcher_root)
    monkeypatch.setattr(config_module.sys, "frozen", True, raising=False)

    assert get_app_root() == launcher_root.resolve()


def test_get_app_root_uses_dist_depot_for_source_checkout(tmp_path: Path, monkeypatch) -> None:
    source_root = tmp_path / "Reverie-Cli"
    package_dir = source_root / "reverie"
    package_dir.mkdir(parents=True, exist_ok=True)
    (source_root / "setup.py").write_text("# test source marker\n", encoding="utf-8")

    monkeypatch.delenv("REVERIE_APP_ROOT", raising=False)
    monkeypatch.setattr(config_module.sys, "frozen", False, raising=False)
    monkeypatch.setattr(config_module, "__file__", str(package_dir / "config.py"))
    monkeypatch.setattr(config_module, "get_launcher_root", lambda: source_root)

    assert get_app_root() == (source_root / "dist").resolve()
    assert not (source_root / ".reverie").exists()


def test_config_manager_creates_default_config_file_for_manual_editing(tmp_path: Path, monkeypatch) -> None:
    app_root = tmp_path / "app"
    project_root = tmp_path / "project"
    project_root.mkdir(parents=True, exist_ok=True)

    monkeypatch.setattr("reverie.config.get_app_root", lambda: app_root)
    monkeypatch.setattr("reverie.config.get_launcher_root", lambda: app_root)

    manager = ConfigManager(project_root)
    config = manager.load()
    notice = manager.consume_load_notice()

    config_path = app_root / ".reverie" / "config.json"
    assert config_path.exists()
    assert config.models == []
    assert config.tool_output_style == "compact"
    assert config.thinking_output_style == "full"
    assert config.text_to_image["active_source"] == "local"
    assert config.modelscope["selected_model_id"] == "ZhipuAI/GLM-5.1"
    saved_payload = json.loads(config_path.read_text(encoding="utf-8"))
    assert saved_payload["tool_output_style"] == "compact"
    assert saved_payload["thinking_output_style"] == "full"
    assert saved_payload["text_to_image"]["active_source"] == "local"
    assert saved_payload["modelscope"]["selected_model_id"] == "ZhipuAI/GLM-5.1"
    assert notice is not None
    assert notice["title"] == "Created default config"


def test_config_manager_auto_adds_tool_output_style_on_load(tmp_path: Path, monkeypatch) -> None:
    app_root = tmp_path / "app"
    project_root = tmp_path / "project"
    project_root.mkdir(parents=True, exist_ok=True)
    (app_root / ".reverie").mkdir(parents=True, exist_ok=True)

    monkeypatch.setattr("reverie.config.get_app_root", lambda: app_root)
    monkeypatch.setattr("reverie.config.get_launcher_root", lambda: app_root)

    config_path = app_root / ".reverie" / "config.json"
    config_path.write_text(
        '{\n'
        '  "models": [],\n'
        '  "active_model_index": 0,\n'
        '  "active_model_source": "standard"\n'
        '}\n',
        encoding="utf-8",
    )

    manager = ConfigManager(project_root)
    loaded = manager.load()
    repaired_payload = json.loads(config_path.read_text(encoding="utf-8"))

    assert loaded.tool_output_style == "compact"
    assert repaired_payload["tool_output_style"] == "compact"
    assert loaded.thinking_output_style == "full"
    assert repaired_payload["thinking_output_style"] == "full"
    assert repaired_payload["text_to_image"]["active_source"] == "local"
    assert repaired_payload["modelscope"]["selected_model_id"] == "ZhipuAI/GLM-5.1"


def test_config_manager_backs_up_and_reports_unrepairable_config(tmp_path: Path, monkeypatch) -> None:
    app_root = tmp_path / "app"
    project_root = tmp_path / "project"
    project_root.mkdir(parents=True, exist_ok=True)
    (app_root / ".reverie").mkdir(parents=True, exist_ok=True)

    monkeypatch.setattr("reverie.config.get_app_root", lambda: app_root)
    monkeypatch.setattr("reverie.config.get_launcher_root", lambda: app_root)

    config_path = app_root / ".reverie" / "config.json"
    config_path.write_text(
        '{\n'
        '  "models": [\n'
        '    {"model": "gpt-4", "model_display_name": "GPT-4",}\n'
        '  ]\n',
        encoding="utf-8",
    )

    manager = ConfigManager(project_root)
    config = manager.load()
    notice = manager.consume_load_notice()

    assert config.models == []
    assert notice is not None
    assert notice["title"] == "Failed to repair config"
    assert "Could not automatically repair malformed config" in notice["detail"]

    backups = sorted(config_path.parent.glob("config.json.invalid-*.bak"))
    assert backups


def test_global_config_wins_over_workspace_file_without_explicit_workspace_flag(tmp_path: Path, monkeypatch) -> None:
    app_root = tmp_path / "app"
    project_root = tmp_path / "project"
    project_root.mkdir(parents=True, exist_ok=True)

    monkeypatch.setattr("reverie.config.get_app_root", lambda: app_root)
    monkeypatch.setattr("reverie.config.get_launcher_root", lambda: app_root)

    manager = ConfigManager(project_root)
    manager.ensure_dirs()

    manager.global_config_path.write_text(
        '{\n'
        '  "models": [{"model": "global-model", "model_display_name": "Global", "base_url": "https://example.com"}],\n'
        '  "active_model_index": 0,\n'
        '  "active_model_source": "standard"\n'
        '}\n',
        encoding="utf-8",
    )
    manager.workspace_config_path.write_text(
        '{\n'
        '  "models": [{"model": "workspace-model", "model_display_name": "Workspace", "base_url": "https://example.com"}],\n'
        '  "active_model_index": 0,\n'
        '  "active_model_source": "standard"\n'
        '}\n',
        encoding="utf-8",
    )

    loaded = manager.load()

    assert loaded.models[0].model == "global-model"
    assert manager.get_active_config_path() == manager.global_config_path
    assert manager.is_workspace_mode() is False


def test_save_writes_back_to_loaded_source_instead_of_overwriting_other_profile(tmp_path: Path, monkeypatch) -> None:
    app_root = tmp_path / "app"
    project_root = tmp_path / "project"
    project_root.mkdir(parents=True, exist_ok=True)

    monkeypatch.setattr("reverie.config.get_app_root", lambda: app_root)
    monkeypatch.setattr("reverie.config.get_launcher_root", lambda: app_root)

    manager = ConfigManager(project_root)
    manager.ensure_dirs()

    manager.global_config_path.write_text(
        '{\n'
        '  "models": [{"model": "global-model", "model_display_name": "Global", "base_url": "https://global.example.com"}],\n'
        '  "active_model_index": 0,\n'
        '  "active_model_source": "standard"\n'
        '}\n',
        encoding="utf-8",
    )
    manager.workspace_config_path.write_text(
        '{\n'
        '  "models": [{"model": "workspace-model", "model_display_name": "Workspace", "base_url": "https://workspace.example.com"}],\n'
        '  "active_model_index": 0,\n'
        '  "active_model_source": "standard",\n'
        '  "use_workspace_config": true\n'
        '}\n',
        encoding="utf-8",
    )

    loaded = manager.load()
    assert loaded.models[0].model == "workspace-model"

    loaded.models.append(
        loaded.models[0].__class__(
            model="added-model",
            model_display_name="Added",
            base_url="https://added.example.com",
        )
    )
    manager.save(loaded)

    reloaded_workspace = ConfigManager(project_root)
    reloaded = reloaded_workspace.load()

    assert reloaded.models[0].model == "workspace-model"
    assert any(model.model == "added-model" for model in reloaded.models)

    global_text = manager.global_config_path.read_text(encoding="utf-8")
    assert "added-model" not in global_text


def test_workspace_mode_save_does_not_create_project_root_reverie_dir(tmp_path: Path, monkeypatch) -> None:
    app_root = tmp_path / "app"
    project_root = tmp_path / "project"
    project_root.mkdir(parents=True, exist_ok=True)

    monkeypatch.setattr("reverie.config.get_app_root", lambda: app_root)
    monkeypatch.setattr("reverie.config.get_launcher_root", lambda: app_root)

    manager = ConfigManager(project_root)
    manager.ensure_dirs()
    manager.set_workspace_mode(True)
    manager.save(Config())

    assert manager.workspace_config_path.exists()
    assert not (project_root / ".reverie").exists()


def test_legacy_workspace_config_is_migrated_without_rewriting_project_root_reverie_dir(tmp_path: Path, monkeypatch) -> None:
    app_root = tmp_path / "app"
    project_root = tmp_path / "project"
    legacy_dir = project_root / ".reverie"
    legacy_dir.mkdir(parents=True, exist_ok=True)

    monkeypatch.setattr("reverie.config.get_app_root", lambda: app_root)
    monkeypatch.setattr("reverie.config.get_launcher_root", lambda: app_root)

    manager = ConfigManager(project_root)
    legacy_payload = Config().to_dict()
    legacy_payload["use_workspace_config"] = True
    manager.legacy_workspace_config_path.write_text(
        json.dumps(legacy_payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    legacy_before = manager.legacy_workspace_config_path.read_text(encoding="utf-8")

    loaded = manager.load()
    loaded.tool_output_style = "full"
    manager.save(loaded)

    assert manager.workspace_config_path.exists()
    migrated_payload = json.loads(manager.workspace_config_path.read_text(encoding="utf-8"))
    assert migrated_payload["tool_output_style"] == "full"
    assert manager.legacy_workspace_config_path.read_text(encoding="utf-8") == legacy_before


def test_read_mcp_resource_cache_defaults_to_project_cache_not_project_root_reverie(tmp_path: Path, monkeypatch) -> None:
    app_root = tmp_path / "app"
    project_root = tmp_path / "project"
    project_root.mkdir(parents=True, exist_ok=True)

    monkeypatch.setattr("reverie.config.get_app_root", lambda: app_root)
    monkeypatch.setattr("reverie.config.get_launcher_root", lambda: app_root)

    tool = ReadMcpResourceTool({"project_root": project_root})
    cache_dir = tool._resource_cache_dir()

    assert cache_dir == get_project_data_dir(project_root) / "mcp_resources"
    assert cache_dir.exists()
    assert not (project_root / ".reverie").exists()
