from __future__ import annotations

from pathlib import Path
import importlib.util


def _load_blender_plugin():
    plugin_path = Path(__file__).resolve().parents[1] / "plugins" / "blender" / "plugin.py"
    spec = importlib.util.spec_from_file_location("reverie_blender_plugin", plugin_path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_blender_plugin_exposes_mmd_tools_commands(tmp_path: Path, monkeypatch) -> None:
    module = _load_blender_plugin()
    plugin_root = tmp_path / "app" / ".reverie" / "plugins" / "blender"
    monkeypatch.setenv("REVERIE_BLENDER_PLUGIN_ROOT", str(plugin_root))
    plugin = module.BlenderRuntimePlugin()

    handshake = plugin.build_handshake()
    command_names = {item["name"] for item in handshake["commands"]}

    assert handshake["version"] == "0.3.0"
    assert "mmd_tools_status" in command_names
    assert "ensure_mmd_tools" in command_names
    assert "import_mmd_model" in command_names
    assert "PMD/PMX" in handshake["description"]


def test_blender_plugin_mmd_tools_dry_run_stays_plugin_local(tmp_path: Path, monkeypatch) -> None:
    module = _load_blender_plugin()
    plugin_root = tmp_path / "app" / ".reverie" / "plugins" / "blender"
    monkeypatch.setenv("REVERIE_BLENDER_PLUGIN_ROOT", str(plugin_root))
    plugin = module.BlenderRuntimePlugin()

    result = plugin.handle_command("ensure_mmd_tools", {"dry_run": True, "enable": True})

    assert result["success"] is True
    assert result["data"]["repo_url"] == "https://github.com/MMD-Blender/blender_mmd_tools.git"
    assert Path(result["data"]["target"]).is_relative_to(plugin_root)
    assert "git clone --depth 1" in "\n".join(result["data"]["planned_commands"])
    assert "blender --background" in "\n".join(result["data"]["planned_commands"])


def test_blender_plugin_mmd_status_detects_local_module(tmp_path: Path, monkeypatch) -> None:
    module = _load_blender_plugin()
    plugin_root = tmp_path / "app" / ".reverie" / "plugins" / "blender"
    module_dir = plugin_root / "addons" / "blender_mmd_tools" / "mmd_tools"
    module_dir.mkdir(parents=True)
    (module_dir / "__init__.py").write_text("bl_info = {}\n", encoding="utf-8")
    monkeypatch.setenv("REVERIE_BLENDER_PLUGIN_ROOT", str(plugin_root))
    plugin = module.BlenderRuntimePlugin()

    result = plugin.handle_command("mmd_tools_status", {})

    assert result["success"] is True
    assert result["data"]["installed"] is True
    assert result["data"]["module_path"] == str(module_dir.resolve(strict=False))
    assert str((plugin_root / "addons" / "blender_mmd_tools").resolve(strict=False)) in result["data"]["python_paths"]


def test_blender_plugin_rejects_invalid_mmd_import_before_blender(tmp_path: Path, monkeypatch) -> None:
    module = _load_blender_plugin()
    plugin_root = tmp_path / "app" / ".reverie" / "plugins" / "blender"
    model_path = tmp_path / "not_mmd.obj"
    model_path.write_text("o Cube\n", encoding="utf-8")
    monkeypatch.setenv("REVERIE_BLENDER_PLUGIN_ROOT", str(plugin_root))
    plugin = module.BlenderRuntimePlugin()

    result = plugin.handle_command("import_mmd_model", {"model_path": str(model_path)})

    assert result["success"] is False
    assert ".pmx or .pmd" in result["error"]
