from __future__ import annotations

from pathlib import Path
import shutil
import zipfile

from reverie.engine import inspect_renpy_project, outline_renpy_script, validate_renpy_project
from reverie.plugin.runtime_manager import RuntimePluginManager


REPO_ROOT = Path(__file__).resolve().parents[2]


def _install_source_plugin(app_root: Path, plugin_id: str) -> None:
    source = REPO_ROOT / "plugins" / plugin_id
    target = app_root / ".reverie" / "plugins" / plugin_id
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copytree(source, target, ignore=shutil.ignore_patterns("build", "dist", "__pycache__", "*.spec"))


def test_renpy_analysis_is_built_into_engine_and_plugin_has_no_fake_mcp(tmp_path: Path) -> None:
    app_root = tmp_path / "app"
    _install_source_plugin(app_root, "renpy")
    project_root = tmp_path / "game"
    project_root.mkdir()
    script_path = project_root / "script.rpy"
    script_path.write_text(
        "\n".join(
            [
                "define e = Character('Eileen')",
                "image eileen happy = 'eileen_happy.png'",
                "label start:",
                "    e 'Hello.'",
                "    menu:",
                "        'Go':",
                "            jump route_a",
                "label route_a:",
                "    return",
            ]
        ),
        encoding="utf-8",
    )

    manager = RuntimePluginManager(app_root)
    record = manager.get_record("renpy", force_refresh=True)

    assert record is not None
    assert record.protocol_supported is True
    assert "Ren'Py" in manager.describe_for_prompt("reverie-gamer")
    assert any(skill["name"] == "renpy-galgame-workflow" for skill in manager.get_skill_definitions())
    tool_names = {tool["name"] for tool in manager.get_tool_definitions()}
    assert "rc_renpy_script_outline" not in tool_names
    assert "rc_renpy_project_inspect" not in tool_names
    assert "rc_renpy_lint" in tool_names
    assert "renpy_reference" not in manager.get_mcp_server_definitions()

    result = outline_renpy_script(script_path)
    inspected = inspect_renpy_project(project_root)
    validation = validate_renpy_project(project_root)

    assert [item["name"] for item in result["labels"]] == ["start", "route_a"]
    assert result["characters"][0]["alias"] == "e"
    assert inspected["script_count"] == 1
    assert inspected["analysis_backend"] == "reverie_engine_builtin"
    assert validation["valid"] is True


def test_live2d_plugin_installs_cubism_core_from_sdk_zip(tmp_path: Path) -> None:
    app_root = tmp_path / "app"
    _install_source_plugin(app_root, "live2d")
    project_root = tmp_path / "game"
    project_root.mkdir()
    sdk_zip = tmp_path / "CubismSdkForWeb-5-r.5.zip"
    core_bytes = b"/* cubism core test */\n"
    with zipfile.ZipFile(sdk_zip, "w") as archive:
        archive.writestr("CubismSdkForWeb-5-r.5/Core/live2dcubismcore.min.js", core_bytes)

    manager = RuntimePluginManager(app_root)
    record = manager.get_record("live2d", force_refresh=True)

    assert record is not None
    assert record.protocol_supported is True
    assert "Live2D" in manager.describe_for_prompt("reverie-gamer")
    assert any(skill["name"] == "live2d-dynamic-cg-workflow" for skill in manager.get_skill_definitions())
    tool_names = {tool["name"] for tool in manager.get_tool_definitions()}
    assert "rc_live2d_install_cubism_core" in tool_names
    assert "rc_live2d_validate_model3" in tool_names
    assert "rc_live2d_mcp_info" in tool_names
    assert "live2d_control" in manager.get_mcp_server_definitions()

    result = manager.call_tool(
        "live2d",
        "install_cubism_core",
        {"sdk_zip": str(sdk_zip), "project_root": str(project_root)},
    )

    assert result["success"] is True
    installed = {Path(item["path"]) for item in result["data"]["installed"]}
    assert app_root / ".reverie" / "plugins" / "live2d" / "runtime" / "vendor" / "live2d" / "live2dcubismcore.min.js" in installed
    assert project_root / "vendor" / "live2d" / "live2dcubismcore.min.js" in installed
    assert project_root / "web" / "vendor" / "live2d" / "live2dcubismcore.min.js" in installed
    assert (project_root / "web" / "vendor" / "live2d" / "live2dcubismcore.min.js").read_bytes() == core_bytes

    model_dir = project_root / "models" / "hero"
    model_dir.mkdir(parents=True)
    (model_dir / "hero.moc3").write_bytes(b"moc")
    (model_dir / "texture.png").write_bytes(b"png")
    (model_dir / "idle.motion3.json").write_text("{}", encoding="utf-8")
    (model_dir / "happy.exp3.json").write_text("{}", encoding="utf-8")
    model3 = model_dir / "hero.model3.json"
    model3.write_text(
        """
{
  "Version": 3,
  "FileReferences": {
    "Moc": "hero.moc3",
    "Textures": ["texture.png"],
    "Motions": {"Idle": [{"File": "idle.motion3.json"}]},
    "Expressions": [{"Name": "happy", "File": "happy.exp3.json"}]
  }
}
""".strip(),
        encoding="utf-8",
    )
    validation = manager.call_tool("live2d", "validate_model3", {"model3_path": str(model3)})
    assert validation["success"] is True
    assert validation["data"]["motion_count"] == 1
