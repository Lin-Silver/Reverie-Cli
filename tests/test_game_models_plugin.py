from __future__ import annotations

from pathlib import Path
import importlib.util

from reverie.plugin.runtime_manager import RuntimePluginManager


def _load_game_models_plugin():
    plugin_path = Path(__file__).resolve().parents[1] / "plugins" / "game_models" / "plugin.py"
    spec = importlib.util.spec_from_file_location("reverie_game_models_plugin", plugin_path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_game_models_plugin_catalog_marks_heavy_models_as_guarded(tmp_path: Path, monkeypatch) -> None:
    module = _load_game_models_plugin()
    plugin_root = tmp_path / "app" / ".reverie" / "plugins" / "game_models"
    monkeypatch.setenv("REVERIE_PLUGIN_ROOT", str(plugin_root))
    plugin = module.GameModelsPlugin()

    listed = plugin.list_models({"only_8gb": True})
    handshake = plugin.build_handshake()
    ids = {item["id"] for item in listed["data"]["models"]}
    command_names = {item["name"] for item in handshake["commands"]}

    assert listed["success"] is True
    assert "ensure_runtime" in command_names
    assert "stable-fast-3d" in ids
    assert "tripo-sr" in ids
    assert "trellis-text-xlarge" not in ids
    assert "hy-motion-1.0" not in ids
    assert listed["data"]["model_root"] == str(plugin_root / "models")


def test_game_models_plugin_deployment_plan_blocks_hy_motion_and_trellis_on_8gb(tmp_path: Path, monkeypatch) -> None:
    module = _load_game_models_plugin()
    plugin_root = tmp_path / "app" / ".reverie" / "plugins" / "game_models"
    monkeypatch.setenv("REVERIE_PLUGIN_ROOT", str(plugin_root))
    plugin = module.GameModelsPlugin()

    plan = plugin.deployment_plan({"ram_gb": 24, "vram_gb": 8})
    recommended = {item["id"] for item in plan["data"]["recommended"]}
    guarded = {item["id"] for item in plan["data"]["guarded_or_blocked"]}

    assert plan["success"] is True
    assert {"stable-fast-3d", "tripo-sr"}.issubset(recommended)
    assert {"trellis-text-xlarge", "hy-motion-1.0"}.issubset(guarded)


def test_game_models_plugin_download_dry_run_is_plugin_local_and_guards_heavy_models(tmp_path: Path, monkeypatch) -> None:
    module = _load_game_models_plugin()
    plugin_root = tmp_path / "app" / ".reverie" / "plugins" / "game_models"
    monkeypatch.setenv("REVERIE_PLUGIN_ROOT", str(plugin_root))
    plugin = module.GameModelsPlugin()

    guarded = plugin.download_model({"model_id": "trellis-text-xlarge", "dry_run": True})
    dry_run = plugin.download_model({"model_id": "stable-fast-3d", "dry_run": True})

    assert guarded["success"] is False
    assert "allow_heavy=true" in guarded["error"]
    assert dry_run["success"] is True
    assert Path(dry_run["data"]["target"]).is_relative_to(plugin_root)


def test_game_models_plugin_registers_external_model_manifest_without_copying(tmp_path: Path, monkeypatch) -> None:
    module = _load_game_models_plugin()
    plugin_root = tmp_path / "app" / ".reverie" / "plugins" / "game_models"
    external_model = tmp_path / "models" / "local_asset_model"
    external_model.mkdir(parents=True)
    monkeypatch.setenv("REVERIE_PLUGIN_ROOT", str(plugin_root))
    plugin = module.GameModelsPlugin()

    result = plugin.register_model_path({"model_id": "stable-fast-3d", "path": str(external_model)})
    status = plugin.model_status({"model_id": "stable-fast-3d"})

    assert result["success"] is True
    assert result["data"]["path"] == str(external_model.resolve())
    assert result["data"]["copy_policy"] == "not_copied"
    assert status["data"]["state_record"]["source"] == "external_registered_path"


def test_game_models_source_plugin_manifest_validates() -> None:
    repo_root = Path(__file__).resolve().parents[1]
    manager = RuntimePluginManager(repo_root, source_root=repo_root / "plugins")

    validation = manager.validate_source_plugin("game_models")

    assert validation["success"] is True
    assert validation["plugin_id"] == "game_models"
    assert any("build.bat" in command for command in validation["build_commands"])
