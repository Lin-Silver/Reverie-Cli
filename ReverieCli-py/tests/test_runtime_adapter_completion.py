from __future__ import annotations

from pathlib import Path

from reverie.gamer.prompt_compiler import compile_game_prompt
from reverie.gamer.runtime_adapters import GodotRuntimeAdapter, O3DERuntimeAdapter
from reverie.gamer.runtime_registry import discover_runtime_profiles, select_runtime_profile


def test_closed_commercial_runtime_requests_do_not_select_adapters(tmp_path: Path) -> None:
    request = compile_game_prompt(
        "Use Unity for a third-person 3D action RPG slice.",
        project_name="Open Runtime Slice",
        requested_runtime="unity",
    )
    selection = select_runtime_profile(request, project_root=tmp_path, requested_runtime="unity")

    assert request["runtime_preferences"]["requested_runtime"] == ""
    assert request["runtime_preferences"]["unsupported_requested_runtime"] == "unity"
    assert selection["selected_runtime"] in {"godot", "reverie_engine"}
    assert selection["selected_runtime"] != "unity"


def test_o3de_adapter_is_scaffold_and_validation_ready(tmp_path: Path) -> None:
    adapter = O3DERuntimeAdapter()
    profile = adapter.detect(tmp_path)

    assert profile.can_scaffold is True
    assert profile.can_validate is True
    assert profile.health != "research-only"
    assert profile.paths["plugin_source_root"].replace("\\", "/").endswith(".reverie/plugins/o3de/source")

    result = adapter.create_project(
        tmp_path,
        project_name="O3DE Slice",
        game_request={},
        blueprint={"meta": {"scope": "vertical_slice"}},
        overwrite=True,
    )
    validation = adapter.validate_project(tmp_path)

    assert result["runtime"] == "o3de"
    assert validation["valid"] is True
    assert (tmp_path / "engine" / "o3de" / "project.json").exists()


def test_discovered_profiles_include_open_runtime_adapters_only(tmp_path: Path) -> None:
    profiles = {item["id"]: item for item in discover_runtime_profiles(tmp_path)}

    assert "unity" not in profiles
    assert "unreal" not in profiles
    assert profiles["o3de"]["can_scaffold"] is True
    assert profiles["o3de"]["can_validate"] is True
    assert profiles["godot"]["health"] != "scaffold-only"


def test_godot_adapter_detects_plugin_local_runtime_and_source(tmp_path: Path) -> None:
    runtime_path = tmp_path / ".reverie" / "plugins" / "godot" / "runtime" / "4.6.2-stable" / "Godot_v4.6.2-stable_win64.exe"
    runtime_path.parent.mkdir(parents=True, exist_ok=True)
    runtime_path.write_text("godot", encoding="utf-8")
    source_path = tmp_path / ".reverie" / "plugins" / "godot" / "source" / "godot-4.6.2-stable"
    source_path.mkdir(parents=True, exist_ok=True)
    (source_path / "SConstruct").write_text("# godot source marker\n", encoding="utf-8")

    profile = GodotRuntimeAdapter().detect(tmp_path, app_root=tmp_path)

    assert profile.source == "runtime-plugin"
    assert profile.health == "ready"
    assert profile.paths["plugin_source_root"].replace("\\", "/").endswith(".reverie/plugins/godot/source")


def test_o3de_adapter_detects_plugin_local_source_sdk_manifest(tmp_path: Path) -> None:
    plugin_root = tmp_path / ".reverie" / "plugins" / "o3de"
    source_path = plugin_root / "source" / "o3de-2510.2"
    source_path.mkdir(parents=True, exist_ok=True)
    (source_path / "scripts").mkdir(parents=True, exist_ok=True)
    (source_path / "scripts" / "o3de.py").write_text("print('o3de')\n", encoding="utf-8")
    manifest_path = plugin_root / "runtime" / "sdk_manifest.json"
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text(
        '{"runtime":"o3de","ref":"2510.2","source_dir":"' + str(source_path).replace("\\", "\\\\") + '"}',
        encoding="utf-8",
    )

    profile = O3DERuntimeAdapter().detect(tmp_path, app_root=tmp_path)

    assert profile.source == "source-sdk-plugin"
    assert profile.health == "source-sdk-ready"
    assert profile.version == "2510.2"
    assert profile.paths["plugin_runtime_manifest"].replace("\\", "/").endswith(".reverie/plugins/o3de/runtime/sdk_manifest.json")


def test_runtime_adapter_classes_are_importable() -> None:
    assert GodotRuntimeAdapter().runtime_id == "godot"
    assert O3DERuntimeAdapter().runtime_id == "o3de"
