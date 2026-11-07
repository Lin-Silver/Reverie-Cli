from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
import importlib.util
import json
import os
import shutil
import struct
import subprocess
import sys
import urllib.request

import pytest

from reverie.plugin.runtime_manager import RuntimePluginManager
from reverie.skills_manager import SkillsManager
from reverie.tools.skill_lookup import SkillLookupTool


REPO_ROOT = Path(__file__).resolve().parents[2]
SKILL_NAME = "RuiC-card-skill"


def _load_module(path: Path):
    spec = importlib.util.spec_from_file_location("blender_skill_test", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_blender_handshake_deploys_complete_skill_without_deploying_runtime(tmp_path, monkeypatch):
    module = _load_module(REPO_ROOT / "plugins/blender/plugin.py")
    root = tmp_path / "app/.reverie/plugins/blender"
    monkeypatch.setenv("REVERIE_BLENDER_PLUGIN_ROOT", str(root))
    plugin = module.BlenderRuntimePlugin()
    skill = next(item for item in plugin.build_handshake()["skills"] if item["name"] == SKILL_NAME)
    resources = Path(skill["metadata"]["resource_dir"])

    assert resources == root / "skills/ruic-card-skill"
    for relative in ("SKILL.md", "LICENSE", "scripts/run_pipeline.py", "scripts/build_card.py",
                     "scripts/export_web.py", "scripts/verify_web.mjs", "assets/web-template/app.bundle.js",
                     "references/avatar-workflows.md", "scripts/run_avatar_pipeline.py", "scripts/build_avatar.py",
                     "assets/avatar-template/avatar.js", "assets/avatar-template/index.html"):
        assert (resources / relative).is_file(), relative
    assert "production_character_pipeline" in skill["body"]
    assert "2.5D" in skill["body"]
    assert not (root / "runtime").exists()
    assert not list(resources.rglob("*.png"))


def test_blender_skill_discovery_resources_and_disable_follow_plugin_state(tmp_path, monkeypatch):
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: tmp_path / "home"))
    app = tmp_path / "app"
    root = app / ".reverie/plugins/blender"
    shutil.copytree(REPO_ROOT / "plugins/blender", root,
                    ignore=shutil.ignore_patterns("build", "dist", "__pycache__", "*.zip", "*.spec"))
    plugins = RuntimePluginManager(app)
    skills = SkillsManager(tmp_path / "project", app, runtime_plugin_manager=plugins)
    tool = SkillLookupTool({"skills_manager": skills})

    for mode in ("reverie", "reverie-gamer"):
        skills.set_active_mode(mode)
        record = skills.get_record(SKILL_NAME, force_refresh=True)
        assert record is not None
        assert record.plugin_id == "blender"
        assert record.skill_dir == root / "skills/ruic-card-skill"
        assert "ruic-card-skill" in skills.describe_for_prompt().lower()
        result = tool.execute(operation="read_resource", skill_name=SKILL_NAME,
                              resource_path="references/avatar-workflows.md")
        assert result.success
        assert "production_character_pipeline" in result.data["body"]
        assert not tool.execute(operation="read_resource", skill_name=SKILL_NAME,
                                resource_path="../../plugin.py").success

    plugins.set_plugin_enabled("blender", False)
    assert skills.get_record(SKILL_NAME, force_refresh=True) is None
    assert not tool.execute(operation="read_resource", skill_name=SKILL_NAME,
                            resource_path="references/avatar-workflows.md").success


@pytest.mark.parametrize("invalid_path", [False, True], ids=["outside-install", "invalid-path"])
def test_plugin_skill_cannot_register_resources_outside_its_installation(tmp_path, monkeypatch, invalid_path):
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: tmp_path / "home"))
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "SKILL.md").write_text("Private file", encoding="utf-8")
    definition = {"plugin_id": "sample", "name": "sample", "body": "Plugin workflow",
                  "install_dir": str(tmp_path / "app/.reverie/plugins/sample"),
                  "metadata": {"resource_dir": "bad\x00path" if invalid_path else str(outside)}}
    plugins = SimpleNamespace(get_skill_definitions=lambda **kwargs: [definition])
    skills = SkillsManager(tmp_path / "project", tmp_path / "app", runtime_plugin_manager=plugins)
    record = skills.get_record("sample", force_refresh=True)
    assert record is not None
    assert record.skill_dir != outside
    assert not SkillLookupTool({"skills_manager": skills}).execute(
        operation="read_resource", skill_name="sample", resource_path="SKILL.md").success


def test_blender_skill_resources_survive_onefile_bundle_lifetime(tmp_path, monkeypatch):
    module = _load_module(REPO_ROOT / "plugins/blender/plugin.py")
    root = tmp_path / "app/.reverie/plugins/blender"
    bundle = tmp_path / "onefile"
    shutil.copytree(REPO_ROOT / "plugins/blender/skills", bundle / "skills")
    monkeypatch.setenv("REVERIE_BLENDER_PLUGIN_ROOT", str(root))
    monkeypatch.setattr(module.sys, "_MEIPASS", str(bundle), raising=False)
    plugin = module.BlenderRuntimePlugin()
    skill = next(item for item in plugin.build_handshake()["skills"] if item["name"] == SKILL_NAME)
    resource = Path(skill["metadata"]["resource_dir"]) / "scripts/run_pipeline.py"
    expected = resource.read_bytes()
    (bundle / "skills/ruic-card-skill/scripts/run_pipeline.py").unlink()
    assert resource.read_bytes() == expected
    assert resource.is_relative_to(root)


def test_ruic_blender_lookup_uses_plugin_runtime_and_never_downloads_project_copy(tmp_path, monkeypatch):
    path = REPO_ROOT / "plugins/blender/skills/ruic-card-skill/scripts/ensure_blender.py"
    module = _load_module(path)
    root = tmp_path / "app/.reverie/plugins/blender"
    executable = root / "runtime/blender-5.1.1-windows-x64/blender.exe"
    executable.parent.mkdir(parents=True)
    executable.write_bytes(b"runtime fixture")
    monkeypatch.setenv("REVERIE_BLENDER_PLUGIN_ROOT", str(root))
    monkeypatch.setattr(urllib.request, "urlopen", lambda *args, **kwargs: pytest.fail("Unexpected download"))
    project = tmp_path / "project"
    assert module.ensure_blender(project) == executable.resolve()
    assert not (project / "tools").exists()
    executable.unlink()
    monkeypatch.setattr(module.shutil, "which", lambda name: None)
    with pytest.raises(RuntimeError, match="rc_blender_ensure_runtime"):
        module.ensure_blender(project)
    assert not (project / "tools").exists()


def _portable_blender() -> Path:
    candidates = list((REPO_ROOT / "dist/.reverie/plugins/blender/runtime").rglob("blender.exe"))
    if not candidates:
        pytest.skip("The optional portable Blender runtime is not deployed")
    return candidates[0]


def test_python_exception_is_reported_as_failure_by_real_portable_blender(tmp_path):
    blender = _portable_blender()
    script = tmp_path / "fail.py"
    script.write_text("raise RuntimeError('REVERIE_TEST_PYTHON_FAILURE')\n", encoding="utf-8")
    payload = {"script_path": str(script), "blender_executable": str(blender), "timeout_seconds": 30}
    process = subprocess.run(
        [sys.executable, str(REPO_ROOT / "plugins/blender/plugin.py"), "-RC-CALL", "run_script", json.dumps(payload)],
        env={**os.environ, "REVERIE_BLENDER_PLUGIN_ROOT": str(tmp_path / "plugin")},
        capture_output=True, encoding="utf-8", timeout=45,
    )
    result = json.loads(process.stdout)
    assert not result["success"]
    assert result["data"]["exit_code"] != 0
    assert "REVERIE_TEST_PYTHON_FAILURE" in result["data"]["stderr"]


def test_card_skill_builds_blend_and_glb_with_real_portable_blender(tmp_path):
    from PIL import Image, ImageDraw

    blender = _portable_blender()
    project = tmp_path / "card"
    assets = project / "assets"
    assets.mkdir(parents=True)
    for name in ("subject", "text", "effects"):
        image = Image.new("RGBA", (256, 384), (0, 0, 0, 0))
        ImageDraw.Draw(image).rectangle((60, 90, 190, 290), fill=(80, 170, 210, 255))
        image.save(assets / f"{name}.png")
    Image.new("RGBA", (256, 384), (20, 30, 50, 255)).save(assets / "background.png")
    lineart = Image.new("RGB", (256, 384), "white")
    ImageDraw.Draw(lineart).rectangle((60, 90, 190, 290), outline="black", width=3)
    lineart.save(assets / "lineart.png")
    skill = REPO_ROOT / "plugins/blender/skills/ruic-card-skill"
    shutil.copy2(skill / "references/config.example.json", project / "card-config.json")
    plugin = tmp_path / "plugin"
    result = subprocess.run(
        [sys.executable, str(skill / "scripts/run_pipeline.py"), "--project", str(project),
         "--blender", str(blender), "--skip-render", "--skip-npm"],
        env={**os.environ, "REVERIE_BLENDER_PLUGIN_ROOT": str(plugin), "PYTHONIOENCODING": "utf-8"},
        capture_output=True, encoding="utf-8", timeout=90,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    # Blender can save a compressed .blend; verify it through Blender's parser.
    reopened = subprocess.run(
        [str(blender), "--background", str(project / "card.blend"), "--python-exit-code", "23",
         "--python-expr", "import bpy; assert len(bpy.data.objects) > 0; assert len(bpy.data.images) >= 4"],
        env={**os.environ, "BLENDER_USER_CONFIG": str(plugin / "config")},
        capture_output=True, encoding="utf-8", timeout=30,
    )
    assert reopened.returncode == 0, reopened.stdout + reopened.stderr
    assert (project / "web/assets/card.glb").read_bytes().startswith(b"glTF")
    report = json.loads((project / "verification.json").read_text(encoding="utf-8"))
    assert Path(report["config"]).is_relative_to(plugin)
    assert all(value["packed"] for value in report["images"].values())
    assert not (project / "tools").exists()


def test_2d_avatar_build_preserves_portrait_and_editable_deformation(tmp_path):
    from PIL import Image, ImageDraw

    blender = _portable_blender()
    project = tmp_path / "portrait"
    assets = project / "assets"
    assets.mkdir(parents=True)
    image = Image.new("RGBA", (128, 192), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)
    draw.rectangle((30, 62, 98, 182), fill=(155, 110, 210, 253))
    draw.ellipse((36, 12, 93, 68), fill=(246, 220, 226, 253))
    draw.ellipse((44, 29, 58, 43), fill=(60, 30, 90, 253))
    draw.ellipse((70, 29, 84, 43), fill=(60, 30, 90, 253))
    image.save(assets / "source.png")
    config = {"name": "Portrait test", "image": "assets/source.png", "rig": {
        "headPivot": [64, 66], "faceCenter": [64, 40], "headBand": [60, 85], "bodyBand": [75, 112],
        "feetBand": [160, 188], "hairSides": [20, 40], "hairStart": [30, 90], "hairEnd": [140, 186]},
        "eyes": {"left": {"center": [77, 36], "radius": [8, 8], "skinSample": [66, 49]},
                 "right": {"center": [51, 36], "radius": [8, 8], "skinSample": [63, 49]}},
        "mouth": {"center": [64, 55], "radius": [5, 4], "skinSample": [65, 61]}}
    (project / "avatar-config.json").write_text(json.dumps(config), encoding="utf-8")
    skill = REPO_ROOT / "plugins/blender/skills/ruic-card-skill"
    result = subprocess.run(
        [sys.executable, str(skill / "scripts/run_avatar_pipeline.py"), "--project", str(project), "--blender", str(blender)],
        env={**os.environ, "REVERIE_BLENDER_PLUGIN_ROOT": str(tmp_path / "plugin"), "PYTHONIOENCODING": "utf-8"},
        capture_output=True, encoding="utf-8", timeout=60,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert (assets / "source.png").read_bytes() == (project / "web/assets/source.png").read_bytes()
    manifest = json.loads((project / "web/avatar.json").read_text(encoding="utf-8"))
    assert manifest["schema"] == "reverie.2d-avatar.v1"
    assert set(manifest["expressions"]) == {"blinkLeft", "blinkRight", "mouthOpen", "smile"}
    for expression in manifest["expressions"].values():
        mask = Image.open(project / "web" / expression["image"]).convert("RGBA")
        assert mask.getchannel("A").getextrema() == (0, 255)
    inspection = tmp_path / "inspect.py"
    inspection.write_text(
        "import bpy\n"
        "assert len([obj for obj in bpy.data.objects if obj.type == 'MESH']) == 5\n"
        "assert all(image.packed_file for image in bpy.data.images)\n"
        "body = bpy.data.objects['Portrait deform mesh']\n"
        "control = bpy.data.objects['Avatar controls']\n"
        "assert all(control[name] == 0 for name in ('lookX','lookY','breath','hairSway','blinkLeft','blinkRight','mouthOpen','smile'))\n"
        "assert {'lookX','lookY','breath','hairSway'}.issubset(body.data.shape_keys.key_blocks.keys())\n"
        "control['lookX'] = 1.0\ncontrol.update_tag()\nbpy.context.view_layer.update()\n"
        "assert body.data.shape_keys.key_blocks['lookX'].value == 1.0\n"
        "basis = body.data.shape_keys.reference_key\n"
        "key = body.data.shape_keys.key_blocks['lookX']\n"
        "assert max((v.co-b.co).length for v,b in zip(key.data,basis.data)) > 0.001\n",
        encoding="utf-8",
    )
    reopened = subprocess.run([str(blender), "--background", str(project / "avatar.blend"), "--python-exit-code", "23",
                               "--python", str(inspection)], capture_output=True, encoding="utf-8", timeout=30)
    assert reopened.returncode == 0, reopened.stdout + reopened.stderr
    assert not (project / "tools").exists()


def test_2d_avatar_microphone_stop_cancels_pending_activation():
    node = shutil.which("node")
    if not node:
        pytest.skip("The optional Node.js browser runtime is unavailable")
    harness = REPO_ROOT / "ReverieCli-py/tests/avatar_microphone_lifecycle.cjs"
    viewer = REPO_ROOT / "plugins/blender/skills/ruic-card-skill/assets/avatar-template/avatar.js"
    actual = subprocess.run([node, str(harness), str(viewer)], capture_output=True, text=True, timeout=15)
    assert actual.returncode == 0, actual.stdout + actual.stderr
    mutant = subprocess.run([node, str(harness), str(viewer), "--mutate"], capture_output=True, text=True, timeout=15)
    assert mutant.returncode != 0
    assert "reset must cancel" in mutant.stderr


def test_2d_avatar_local_pose_relay():
    node = shutil.which("node")
    if not node:
        pytest.skip("The optional Node.js browser runtime is unavailable")
    harness = REPO_ROOT / "ReverieCli-py/tests/avatar_pose_relay.cjs"
    server = REPO_ROOT / "plugins/blender/skills/ruic-card-skill/assets/avatar-template/server.mjs"
    actual = subprocess.run([node, str(harness), str(server)], capture_output=True, text=True, timeout=20)
    assert actual.returncode == 0, actual.stdout + actual.stderr


def test_2d_avatar_sync_stop_and_restart_preserve_current_session():
    node = shutil.which("node")
    if not node:
        pytest.skip("The optional Node.js browser runtime is unavailable")
    harness = REPO_ROOT / "ReverieCli-py/tests/avatar_sync_lifecycle.cjs"
    viewer = REPO_ROOT / "plugins/blender/skills/ruic-card-skill/assets/avatar-template/avatar.js"
    actual = subprocess.run([node, str(harness), str(viewer)], capture_output=True, text=True, timeout=15)
    assert actual.returncode == 0, actual.stdout + actual.stderr


def test_rigged_avatar_export_keeps_skin_expressions_and_animation(tmp_path):
    from reverie.engine.blender_modeling import create_blender_authoring_job

    blender = _portable_blender()
    project = tmp_path / "avatar"
    job = create_blender_authoring_job(
        project, brief="Stylized humanoid avatar integration test", model_name="rigged-avatar",
        preset="production_character_pipeline", render_preview=False,
    )
    payload = {"script_path": job["paths"]["script"], "blender_executable": str(blender), "timeout_seconds": 180}
    process = subprocess.run(
        [sys.executable, str(REPO_ROOT / "plugins/blender/plugin.py"), "-RC-CALL", "run_script", json.dumps(payload)],
        env={**os.environ, "REVERIE_BLENDER_PLUGIN_ROOT": str(tmp_path / "plugin")},
        capture_output=True, encoding="utf-8", timeout=200,
    )
    result = json.loads(process.stdout)
    assert result["success"], result
    raw = Path(job["paths"]["runtime"]).read_bytes()
    assert raw[:4] == b"glTF"
    document = json.loads(raw[20:20 + struct.unpack_from("<I", raw, 12)[0]])
    assert document.get("skins")
    assert all(skin["joints"] for skin in document["skins"])
    assert len(document.get("animations", [])) == 3
    assert all(abs(weight) < 1e-7
               for item in document.get("meshes", []) + document.get("nodes", [])
               for weight in item.get("weights", []))
    expressions = {"blink_L", "blink_R", "smile_soft", "mouth_open"}
    assert any(
        expressions.issubset(mesh.get("extras", {}).get("targetNames", []))
        and any(primitive.get("targets") for primitive in mesh["primitives"])
        for mesh in document.get("meshes", [])
    )
