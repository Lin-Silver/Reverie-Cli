from pathlib import Path
import json

import reverie.config as config_module

from reverie.config import (
    Config,
    ConfigManager,
    _escape_invalid_json_string_control_chars,
    get_app_root,
    get_project_data_dir,
    get_project_data_name,
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


def test_project_data_dir_uses_projects_safe_full_path_without_hash(tmp_path: Path, monkeypatch) -> None:
    app_root = tmp_path / "app"
    app_root.mkdir(parents=True, exist_ok=True)

    monkeypatch.setattr("reverie.config.get_app_root", lambda: app_root)

    project_root = Path(r"G:\Reverie\Reverie-Cli")

    assert get_project_data_name(project_root) == "G_Reverie_Reverie-Cli"
    assert get_project_data_dir(project_root) == app_root / ".reverie" / "projects" / "G_Reverie_Reverie-Cli"


def test_config_manager_migrates_legacy_project_cache_to_projects(tmp_path: Path, monkeypatch) -> None:
    app_root = tmp_path / "app"
    project_root = tmp_path / "workspace" / "Reverie-Cli"
    project_root.mkdir(parents=True, exist_ok=True)

    monkeypatch.setattr("reverie.config.get_app_root", lambda: app_root)
    monkeypatch.setattr("reverie.config.get_launcher_root", lambda: app_root)

    legacy_name = config_module._get_hashed_project_data_name(project_root)
    legacy_dir = app_root / ".reverie" / "project_caches" / legacy_name
    legacy_sessions_dir = legacy_dir / "sessions"
    legacy_sessions_dir.mkdir(parents=True, exist_ok=True)
    (legacy_sessions_dir / "session.json").write_text('{"id":"legacy"}\n', encoding="utf-8")

    manager = ConfigManager(project_root)
    manager.ensure_dirs()

    expected_dir = app_root / ".reverie" / "projects" / get_project_data_name(project_root)
    assert manager.project_data_dir == expected_dir
    assert manager.project_cache_migration["migrated"] is True
    assert (expected_dir / "sessions" / "session.json").exists()
    assert (legacy_sessions_dir / "session.json").exists()

    metadata = json.loads((expected_dir / "project_metadata.json").read_text(encoding="utf-8"))
    assert metadata["project_data_name"] == get_project_data_name(project_root)
    assert metadata["hash_suffix_used"] is False


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
    assert config.text_to_image["aihubmix"]["default_model"] == "gpt-image-2-free"
    assert config.text_to_image["pollinations"]["default_model"] == "flux"
    assert config.text_to_image["agnes"]["default_model"] == "agnes-image-2.1-flash"
    assert config.text_to_video["active_source"] == "agnes"
    assert config.text_to_video["agnes"]["default_model"] == "agnes-video-v2.0"
    assert config.aihubmix["selected_model_id"] == "gpt-5.5-free"
    assert config.agnes["selected_model_id"] == "agnes-2.0-flash"
    assert config.modelscope["selected_model_id"] == "ZhipuAI/GLM-5.1"
    saved_payload = json.loads(config_path.read_text(encoding="utf-8"))
    assert saved_payload["tool_output_style"] == "compact"
    assert saved_payload["thinking_output_style"] == "full"
    assert saved_payload["text_to_image"]["active_source"] == "local"
    assert saved_payload["text_to_image"]["aihubmix"]["default_model"] == "gpt-image-2-free"
    assert saved_payload["text_to_image"]["pollinations"]["default_model"] == "flux"
    assert saved_payload["text_to_image"]["agnes"]["default_model"] == "agnes-image-2.1-flash"
    assert saved_payload["text_to_video"]["active_source"] == "agnes"
    assert saved_payload["text_to_video"]["agnes"]["default_model"] == "agnes-video-v2.0"
    assert saved_payload["aihubmix"]["selected_model_id"] == "gpt-5.5-free"
    assert saved_payload["agnes"]["selected_model_id"] == "agnes-2.0-flash"
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
    assert repaired_payload["text_to_image"]["aihubmix"]["default_model"] == "gpt-image-2-free"
    assert repaired_payload["text_to_image"]["pollinations"]["default_model"] == "flux"
    assert repaired_payload["text_to_image"]["agnes"]["default_model"] == "agnes-image-2.1-flash"
    assert repaired_payload["text_to_video"]["active_source"] == "agnes"
    assert repaired_payload["text_to_video"]["agnes"]["default_model"] == "agnes-video-v2.0"
    assert repaired_payload["aihubmix"]["selected_model_id"] == "gpt-5.5-free"
    assert repaired_payload["agnes"]["selected_model_id"] == "agnes-2.0-flash"
    assert repaired_payload["modelscope"]["selected_model_id"] == "ZhipuAI/GLM-5.1"


def test_config_manager_migrates_standard_models_to_supports_vision(tmp_path: Path, monkeypatch) -> None:
    app_root = tmp_path / "app"
    project_root = tmp_path / "project"
    project_root.mkdir(parents=True, exist_ok=True)
    (app_root / ".reverie").mkdir(parents=True, exist_ok=True)

    monkeypatch.setattr("reverie.config.get_app_root", lambda: app_root)
    monkeypatch.setattr("reverie.config.get_launcher_root", lambda: app_root)

    config_path = app_root / ".reverie" / "config.json"
    config_path.write_text(
        json.dumps(
            {
                "models": [
                    {
                        "model": "local-model",
                        "model_display_name": "Local",
                        "base_url": "https://example.com/v1",
                        "provider": "openai-sdk",
                        "thinking_mode": None,
                        "endpoint": "",
                    }
                ],
                "active_model_index": 0,
                "active_model_source": "standard",
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    manager = ConfigManager(project_root)
    loaded = manager.load()
    repaired_payload = json.loads(config_path.read_text(encoding="utf-8"))

    assert loaded.models[0].supports_vision is False
    model_payload = repaired_payload["models"][0]
    assert model_payload["supports_vision"] is False
    assert "thinking_mode" not in model_payload
    assert "endpoint" not in model_payload


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


def test_global_config_is_created_when_only_implicit_workspace_file_exists(tmp_path: Path, monkeypatch) -> None:
    app_root = tmp_path / "app"
    project_root = tmp_path / "project"
    project_root.mkdir(parents=True, exist_ok=True)

    monkeypatch.setattr("reverie.config.get_app_root", lambda: app_root)
    monkeypatch.setattr("reverie.config.get_launcher_root", lambda: app_root)

    manager = ConfigManager(project_root)
    manager.ensure_dirs()
    manager.workspace_config_path.write_text(
        '{\n'
        '  "models": [{"model": "workspace-model", "model_display_name": "Workspace", "base_url": "https://workspace.example.com"}],\n'
        '  "active_model_index": 0,\n'
        '  "active_model_source": "standard"\n'
        '}\n',
        encoding="utf-8",
    )

    loaded = manager.load()

    assert loaded.models == []
    assert manager.get_active_config_path() == manager.global_config_path
    assert manager.global_config_path.exists()
    assert manager.is_workspace_mode() is False


def test_global_config_is_not_misclassified_as_legacy_workspace_when_project_is_app_root(
    tmp_path: Path,
    monkeypatch,
) -> None:
    app_root = tmp_path / "dist"
    app_root.mkdir(parents=True, exist_ok=True)

    monkeypatch.setattr("reverie.config.get_app_root", lambda: app_root)
    monkeypatch.setattr("reverie.config.get_launcher_root", lambda: app_root)

    manager = ConfigManager(app_root)
    manager.ensure_dirs()
    manager.global_config_path.write_text(
        '{\n'
        '  "models": [{"model": "global-model", "model_display_name": "Global", "base_url": "https://global.example.com"}],\n'
        '  "active_model_index": 0,\n'
        '  "active_model_source": "standard",\n'
        '  "use_workspace_config": false\n'
        '}\n',
        encoding="utf-8",
    )
    manager.workspace_config_path.write_text(
        '{\n'
        '  "models": [{"model": "workspace-model", "model_display_name": "Workspace", "base_url": "https://workspace.example.com"}],\n'
        '  "active_model_index": 0,\n'
        '  "active_model_source": "standard",\n'
        '  "use_workspace_config": false\n'
        '}\n',
        encoding="utf-8",
    )

    reloaded_manager = ConfigManager(app_root)
    loaded = reloaded_manager.load()
    loaded.active_model_source = "nvidia"
    reloaded_manager.save(loaded)

    global_payload = json.loads(manager.global_config_path.read_text(encoding="utf-8"))
    workspace_payload = json.loads(manager.workspace_config_path.read_text(encoding="utf-8"))

    assert reloaded_manager.is_workspace_mode() is False
    assert reloaded_manager.get_active_config_path() == manager.global_config_path
    assert global_payload["active_model_source"] == "nvidia"
    assert global_payload["use_workspace_config"] is False
    assert workspace_payload["active_model_source"] == "standard"
    assert workspace_payload["use_workspace_config"] is False


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
    saved = json.loads(manager.workspace_config_path.read_text(encoding="utf-8"))
    assert saved["use_workspace_config"] is True
    reloaded = ConfigManager(project_root)
    assert reloaded.is_workspace_mode() is True
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
