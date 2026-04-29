from __future__ import annotations

from pathlib import Path
from textwrap import dedent
import json
import platform
import stat
import sys
import zipfile

from rich.console import Console

from reverie.cli.commands import CommandHandler
from reverie.plugin.runtime_manager import DEFAULT_RUNTIME_PLUGIN_CATALOG, RuntimePluginManager


def _compiled_entry_name(plugin_id: str) -> str:
    if platform.system() == "Windows":
        return f"dist/reverie-{plugin_id}.cmd"
    return f"dist/reverie-{plugin_id}.sh"


def _write_runtime_script(path: Path, *, marker: str) -> None:
    path.write_text(
        dedent(
            f"""
            import json
            import sys


            def build_handshake():
                return {{
                    "protocol_version": "1.0",
                    "plugin_id": "sample-runtime",
                    "display_name": "Sample Runtime",
                    "version": "0.1.0",
                    "runtime_family": "engine",
                    "description": "Sample runtime plugin for tests.",
                    "commands": [
                        {{
                            "name": "status",
                            "description": "Return runtime health.",
                            "parameters": {{
                                "type": "object",
                                "properties": {{
                                    "message": {{
                                        "type": "string"
                                    }}
                                }},
                                "required": []
                            }},
                            "expose_as_tool": True,
                            "include_modes": ["reverie-gamer"]
                        }}
                    ]
                }}


            if len(sys.argv) >= 2 and sys.argv[1] == "-RC":
                print(json.dumps(build_handshake()))
                raise SystemExit(0)

            if len(sys.argv) >= 2 and sys.argv[1] == "-RC-CALL":
                payload = json.loads(sys.argv[3]) if len(sys.argv) >= 4 and sys.argv[3] else {{}}
                print(json.dumps({{
                    "success": True,
                    "output": "{marker}",
                    "error": "",
                    "data": {{
                        "entry": "{marker}",
                        "echo": str(payload.get("message") or "")
                    }}
                }}))
                raise SystemExit(0)

            print("unsupported", file=sys.stderr)
            raise SystemExit(1)
            """
        ).strip()
        + "\n",
        encoding="utf-8",
    )


def _write_platform_wrapper(wrapper_path: Path, target_script: Path) -> None:
    wrapper_path.parent.mkdir(parents=True, exist_ok=True)
    if platform.system() == "Windows":
        wrapper_path.write_text(
            f'@echo off\r\n"{sys.executable}" "{target_script}" %*\r\n',
            encoding="utf-8",
        )
        return

    wrapper_path.write_text(
        dedent(
            f"""\
            #!/usr/bin/env sh
            "{sys.executable}" "{target_script}" "$@"
            """
        ),
        encoding="utf-8",
    )
    current_mode = wrapper_path.stat().st_mode
    wrapper_path.chmod(current_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)


def _write_manifest(plugin_dir: Path, *, plugin_id: str, compiled_relative_path: str) -> None:
    payload = {
        "schema_version": "2.0",
        "id": plugin_id,
        "display_name": "Sample Runtime",
        "runtime_family": "engine",
        "version": "0.1.0",
        "delivery": "python-exe",
        "template": "runtime_python_exe",
        "description": "Sample runtime plugin for tests.",
        "entry": {
            "preferred": {
                "windows": compiled_relative_path if platform.system() == "Windows" else "",
                "linux": compiled_relative_path if platform.system() == "Linux" else "",
                "darwin": compiled_relative_path if platform.system() == "Darwin" else "",
                "default": compiled_relative_path,
            },
            "fallbacks": {"default": "plugin.py"},
            "strategy": "prefer-packaged",
            "allow_source_fallback": True,
        },
        "packaging": {
            "format": "pyinstaller-onefile",
            "compiled": {"default": compiled_relative_path},
            "source": {"default": "plugin.py"},
            "build": {
                "default": [
                    f"python -m PyInstaller --noconfirm --clean --onefile --name reverie-{plugin_id} plugin.py"
                ]
            },
        },
    }
    (plugin_dir / "plugin.json").write_text(json.dumps(payload, indent=2), encoding="utf-8")


def _create_portable_blender_zip(zip_path: Path) -> None:
    entry_name = "blender.exe" if platform.system() == "Windows" else "blender"
    archive_root = "blender-5.1.1-windows-x64" if platform.system() == "Windows" else "blender-5.1.1-portable"
    zip_path.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(zip_path, "w") as archive:
        archive.writestr(f"{archive_root}/{entry_name}", "portable blender placeholder\n")


def _create_template_tree(app_root: Path) -> None:
    template_dir = app_root / "plugins" / "_templates" / "runtime_python_exe"
    template_dir.mkdir(parents=True, exist_ok=True)
    build_hint = "build.bat" if platform.system() == "Windows" else "build.sh"
    (template_dir / "template.json").write_text(
        json.dumps(
            {
                "id": "runtime_python_exe",
                "display_name": "Runtime Python EXE",
                "description": "Template for packaged Python runtime plugins.",
                "delivery": "python-exe",
                "entry_template": "plugin.py",
                "manifest_template": "plugin.json",
                "build_hint": build_hint,
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    (template_dir / "plugin.json").write_text(
        json.dumps(
            {
                "schema_version": "2.0",
                "id": "{{plugin_id}}",
                "display_name": "{{plugin_name}}",
                "runtime_family": "{{plugin_runtime_family}}",
                "version": "0.1.0",
                "delivery": "python-exe",
                "template": "runtime_python_exe",
                "description": "{{plugin_description}}",
                "entry": {
                    "preferred": {
                        "windows": "dist/reverie-{{plugin_id}}.cmd",
                        "linux": "dist/reverie-{{plugin_id}}.sh",
                        "darwin": "dist/reverie-{{plugin_id}}.sh",
                        "default": "dist/reverie-{{plugin_id}}.cmd" if platform.system() == "Windows" else "dist/reverie-{{plugin_id}}.sh",
                    },
                    "fallbacks": {"default": "plugin.py"},
                    "strategy": "prefer-packaged",
                    "allow_source_fallback": True,
                },
                "packaging": {
                    "format": "test-wrapper",
                    "compiled": {
                        "windows": "dist/reverie-{{plugin_id}}.cmd",
                        "linux": "dist/reverie-{{plugin_id}}.sh",
                        "darwin": "dist/reverie-{{plugin_id}}.sh",
                        "default": "dist/reverie-{{plugin_id}}.cmd" if platform.system() == "Windows" else "dist/reverie-{{plugin_id}}.sh",
                    },
                    "source": {"default": "plugin.py"},
                    "build": {
                        "windows": ["build.bat"],
                        "linux": ["build.sh"],
                        "darwin": ["build.sh"],
                        "default": [build_hint],
                    },
                },
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    (template_dir / "plugin.py").write_text(
        dedent(
            """
            import json
            import sys


            def build_handshake():
                return {
                    "protocol_version": "1.0",
                    "plugin_id": "{{plugin_id}}",
                    "display_name": "{{plugin_name}}",
                    "version": "0.1.0",
                    "runtime_family": "{{plugin_runtime_family}}",
                    "description": "{{plugin_description}}",
                    "commands": [
                        {
                            "name": "status",
                            "description": "Return runtime health.",
                            "parameters": {
                                "type": "object",
                                "properties": {},
                                "required": []
                            },
                            "expose_as_tool": True,
                            "include_modes": ["reverie-gamer"]
                        },
                        {
                            "name": "{{plugin_tool_name}}",
                            "description": "Return the requested message.",
                            "parameters": {
                                "type": "object",
                                "properties": {
                                    "message": {
                                        "type": "string"
                                    }
                                },
                                "required": []
                            },
                            "expose_as_tool": True,
                            "include_modes": ["reverie-gamer"]
                        }
                    ]
                }


            if len(sys.argv) >= 2 and sys.argv[1] == "-RC":
                print(json.dumps(build_handshake()))
                raise SystemExit(0)

            if len(sys.argv) >= 2 and sys.argv[1] == "-RC-CALL":
                payload = json.loads(sys.argv[3]) if len(sys.argv) >= 4 and sys.argv[3] else {}
                print(json.dumps({
                    "success": True,
                    "output": "{{plugin_name}} ok",
                    "error": "",
                    "data": {
                        "plugin_id": "{{plugin_id}}",
                        "message": str(payload.get("message") or "")
                    }
                }))
                raise SystemExit(0)

            print("unsupported", file=sys.stderr)
            raise SystemExit(1)
            """
        ).strip()
        + "\n",
        encoding="utf-8",
    )
    if platform.system() == "Windows":
        (template_dir / "build.bat").write_text(
            dedent(
                f"""\
                @echo off
                setlocal
                cd /d "%~dp0"
                if not exist dist mkdir dist
                > dist\\reverie-{{{{plugin_id}}}}.cmd echo @echo off
                >> dist\\reverie-{{{{plugin_id}}}}.cmd echo "{sys.executable}" "%%~dp0..\\plugin.py" %%*
                endlocal
                """
            ),
            encoding="utf-8",
        )
    else:
        build_script = template_dir / "build.sh"
        build_script.write_text(
            dedent(
                f"""\
                #!/usr/bin/env sh
                set -eu
                cd "$(dirname "$0")"
                mkdir -p dist
                cat > "dist/reverie-{{{{plugin_id}}}}.sh" <<'EOF'
                #!/usr/bin/env sh
                "{sys.executable}" "$(dirname "$0")/../plugin.py" "$@"
                EOF
                chmod +x "dist/reverie-{{{{plugin_id}}}}.sh"
                """
            ),
            encoding="utf-8",
        )
        current_mode = build_script.stat().st_mode
        build_script.chmod(current_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)


def _create_runtime_plugin(app_root: Path, *, plugin_id: str = "sample-runtime", packaged: bool = False) -> Path:
    plugin_dir = app_root / ".reverie" / "plugins" / plugin_id
    plugin_dir.mkdir(parents=True, exist_ok=True)

    compiled_relative_path = _compiled_entry_name(plugin_id)
    _write_manifest(plugin_dir, plugin_id=plugin_id, compiled_relative_path=compiled_relative_path)
    _write_runtime_script(plugin_dir / "plugin.py", marker="source-fallback")

    if packaged:
        packaged_script = plugin_dir / "packaged_plugin.py"
        _write_runtime_script(packaged_script, marker="packaged")
        _write_platform_wrapper(plugin_dir / compiled_relative_path, packaged_script.resolve(strict=False))

    return plugin_dir


def test_runtime_plugin_manager_uses_python_source_fallback_when_packaged_entry_is_missing(tmp_path: Path) -> None:
    app_root = tmp_path / "app"
    _create_runtime_plugin(app_root, packaged=False)

    manager = RuntimePluginManager(app_root)
    snapshot = manager.scan()

    assert snapshot.detected_count == 1
    record = manager.get_record("sample-runtime")
    assert record is not None
    assert record.status == "ready"
    assert record.delivery == "python-exe"
    assert record.entry_strategy == "prefer-packaged"
    assert record.packaging_format == "pyinstaller-onefile"
    assert record.template_id == "runtime_python_exe"
    assert record.entry_path is not None
    assert record.entry_path.name == "plugin.py"
    assert record.compiled_entry_path is None
    assert record.source_entry_path is not None
    assert record.source_entry_path.name == "plugin.py"
    assert record.protocol_supported is True
    assert "source fallback" in record.detail.lower()

    result = manager.call_tool("sample-runtime", "status", {"message": "hello"})
    assert result["success"] is True
    assert result["data"]["entry"] == "source-fallback"
    assert result["data"]["echo"] == "hello"


def test_runtime_plugin_manager_prefers_packaged_entry_when_available(tmp_path: Path) -> None:
    app_root = tmp_path / "app"
    plugin_dir = _create_runtime_plugin(app_root, packaged=True)

    manager = RuntimePluginManager(app_root)
    manager.scan()
    record = manager.get_record("sample-runtime")

    assert record is not None
    assert record.entry_path is not None
    assert record.compiled_entry_path is not None
    assert record.source_entry_path is not None
    assert record.entry_path == record.compiled_entry_path
    assert record.entry_path != record.source_entry_path
    assert record.entry_path == (plugin_dir / _compiled_entry_name("sample-runtime")).resolve(strict=False)

    result = manager.call_tool("sample-runtime", "status", {"message": "packaged-call"})
    assert result["success"] is True
    assert result["data"]["entry"] == "packaged"
    assert result["data"]["echo"] == "packaged-call"


def test_runtime_plugin_manager_detects_standalone_root_entry_and_sets_plugin_root(tmp_path: Path) -> None:
    app_root = tmp_path / "app"
    install_root = app_root / ".reverie" / "plugins"
    install_root.mkdir(parents=True, exist_ok=True)
    script_path = install_root / "reverie-standalone-sample.py"
    script_path.write_text(
        dedent(
            """
            import json
            import os
            import sys


            def handshake():
                return {
                    "protocol_version": "1.0",
                    "plugin_id": "standalone-sample",
                    "display_name": "Standalone Sample",
                    "version": "0.1.0",
                    "runtime_family": "runtime",
                    "commands": [
                        {
                            "name": "status",
                            "description": "Return current plugin root.",
                            "parameters": {"type": "object", "properties": {}, "required": []},
                            "expose_as_tool": True,
                            "include_modes": ["reverie"],
                        }
                    ],
                }


            if len(sys.argv) >= 2 and sys.argv[1] == "-RC":
                print(json.dumps(handshake()))
                raise SystemExit(0)

            if len(sys.argv) >= 2 and sys.argv[1] == "-RC-CALL":
                print(
                    json.dumps(
                        {
                            "success": True,
                            "output": "ok",
                            "error": "",
                            "data": {
                                "plugin_root": os.environ.get("REVERIE_PLUGIN_ROOT", ""),
                            },
                        }
                    )
                )
                raise SystemExit(0)

            raise SystemExit(1)
            """
        ).strip()
        + "\n",
        encoding="utf-8",
    )

    manager = RuntimePluginManager(app_root)
    record = manager.get_record("standalone_sample", force_refresh=True)

    assert record is not None
    assert record.source == "root-entry"
    assert record.entry_path == script_path.resolve(strict=False)
    assert record.install_dir == (install_root / "standalone_sample").resolve()
    assert record.protocol_supported is True

    result = manager.call_tool("standalone_sample", "status", {})
    assert result["success"] is True
    assert result["data"]["plugin_root"] == str((install_root / "standalone_sample").resolve())


def test_runtime_plugin_manager_detects_third_party_root_exe_without_catalog(tmp_path: Path) -> None:
    app_root = tmp_path / "app"
    install_root = app_root / ".reverie" / "plugins"
    install_root.mkdir(parents=True, exist_ok=True)
    exe_path = install_root / "reverie-third-party-runtime.exe"
    exe_path.write_bytes(b"MZ third-party runtime placeholder")

    manager = RuntimePluginManager(app_root)
    record = manager.get_record("third_party_runtime", force_refresh=True)

    assert record is not None
    assert record.source == "root-entry"
    assert record.catalog_managed is False
    assert record.delivery == "plugin-exe"
    assert record.packaging_format == "standalone-root-entry"
    assert record.entry_path == exe_path.resolve(strict=False)
    assert record.compiled_entry_path == exe_path.resolve(strict=False)
    assert record.install_dir == (install_root / "third_party_runtime").resolve()


def test_runtime_plugin_manager_prefers_root_entry_over_same_name_legacy_wrapper_dir(tmp_path: Path) -> None:
    app_root = tmp_path / "app"
    install_root = app_root / ".reverie" / "plugins"
    install_root.mkdir(parents=True, exist_ok=True)

    script_path = install_root / "reverie-standalone-sample.py"
    script_path.write_text(
        dedent(
            """
            import json
            import sys


            if len(sys.argv) >= 2 and sys.argv[1] == "-RC":
                print(json.dumps({
                    "protocol_version": "1.0",
                    "plugin_id": "standalone-sample",
                    "display_name": "Standalone Root Entry",
                    "version": "0.1.0",
                    "runtime_family": "runtime",
                    "commands": []
                }))
                raise SystemExit(0)

            raise SystemExit(1)
            """
        ).strip()
        + "\n",
        encoding="utf-8",
    )

    legacy_dir = install_root / "standalone_sample"
    legacy_dir.mkdir(parents=True, exist_ok=True)
    _write_manifest(legacy_dir, plugin_id="standalone_sample", compiled_relative_path=_compiled_entry_name("standalone_sample"))
    _write_runtime_script(legacy_dir / "plugin.py", marker="legacy-wrapper")

    manager = RuntimePluginManager(app_root)
    record = manager.get_record("standalone_sample", force_refresh=True)

    assert record is not None
    assert record.source == "root-entry"
    assert record.entry_path == script_path.resolve(strict=False)
    assert record.display_name == "Standalone Root Entry"


def test_runtime_plugin_templates_are_optional_in_repo_source_tree() -> None:
    repo_root = Path(__file__).resolve().parents[1]
    manager = RuntimePluginManager(repo_root)

    templates = manager.list_templates(force_refresh=True)
    template = manager.get_template("runtime_python_exe", force_refresh=False)
    summary = manager.get_status_summary(force_refresh=False)

    assert templates == tuple()
    assert template is None
    assert summary["template_count"] == 0


def test_runtime_plugin_manager_can_scaffold_build_and_install_source_plugin(tmp_path: Path) -> None:
    app_root = tmp_path / "app"
    _create_template_tree(app_root)
    manager = RuntimePluginManager(app_root)

    scaffold = manager.scaffold_source_plugin(
        template_id="runtime_python_exe",
        plugin_id="terrain-runtime",
        display_name="Terrain Runtime",
        runtime_family="engine",
        description="Terrain runtime plugin.",
        command_name="sync_assets",
        overwrite=False,
    )

    assert scaffold["success"] is True
    source_dir = scaffold["source_dir"]
    assert isinstance(source_dir, Path)
    assert (source_dir / "plugin.json").is_file()
    assert (source_dir / "plugin.py").is_file()
    assert "{{plugin_id}}" not in (source_dir / "plugin.py").read_text(encoding="utf-8")

    validation = manager.validate_source_plugin("terrain-runtime")
    assert validation["success"] is True
    assert validation["template_id"] == "runtime_python_exe"
    assert validation["compiled_entry_path"] is None
    assert validation["source_entry_path"] is not None
    assert validation["protocol_supported"] is True

    build = manager.build_source_plugin("terrain-runtime", install=True, overwrite_install=True)
    assert build["success"] is True
    post_validation = build["validation"]
    assert post_validation["compiled_entry_path"] is not None
    assert Path(post_validation["compiled_entry_path"]).exists()
    install_result = build["install_result"]
    assert install_result is not None
    assert install_result["success"] is True

    installed_record = manager.get_record("terrain-runtime", force_refresh=True)
    assert installed_record is not None
    assert installed_record.protocol_supported is True
    assert installed_record.compiled_entry_path is not None

    result = manager.call_tool("terrain-runtime", "sync_assets", {"message": "asset-pass"})
    assert result["success"] is True
    assert result["data"]["plugin_id"] == "terrain_runtime"
    assert result["data"]["message"] == "asset-pass"


def test_install_source_plugin_standalone_cleans_legacy_wrapper_but_keeps_runtime_data(tmp_path: Path) -> None:
    app_root = tmp_path / "app"
    source_dir = app_root / "plugins" / "terrain_runtime"
    source_dir.mkdir(parents=True, exist_ok=True)
    _write_manifest(source_dir, plugin_id="terrain-runtime", compiled_relative_path=_compiled_entry_name("terrain-runtime"))
    _write_runtime_script(source_dir / "plugin.py", marker="source-fallback")
    packaged_script = source_dir / "packaged_plugin.py"
    _write_runtime_script(packaged_script, marker="packaged")
    _write_platform_wrapper(source_dir / _compiled_entry_name("terrain-runtime"), packaged_script.resolve(strict=False))

    install_dir = app_root / ".reverie" / "plugins" / "terrain_runtime"
    (install_dir / "runtime").mkdir(parents=True, exist_ok=True)
    (install_dir / "runtime" / "keep.txt").write_text("keep me\n", encoding="utf-8")
    (install_dir / "plugin.json").write_text("{}", encoding="utf-8")
    (install_dir / "plugin.py").write_text("print('legacy wrapper')\n", encoding="utf-8")
    (install_dir / "README.md").write_text("legacy docs\n", encoding="utf-8")
    (install_dir / "build").mkdir(parents=True, exist_ok=True)
    (install_dir / "dist").mkdir(parents=True, exist_ok=True)
    (install_dir / "terrain-runtime.spec").write_text("# legacy\n", encoding="utf-8")

    manager = RuntimePluginManager(app_root)
    result = manager.install_source_plugin("terrain-runtime", overwrite=True)

    target_path = app_root / ".reverie" / "plugins" / Path(_compiled_entry_name("terrain-runtime")).name
    assert result["success"] is True
    assert result["install_mode"] == "standalone-entry"
    assert target_path.exists()
    installed_record = manager.get_record("terrain-runtime", force_refresh=True)
    assert installed_record is not None
    assert installed_record.source == "root-entry"
    assert installed_record.catalog_managed is False
    assert installed_record.entry_path == target_path.resolve(strict=False)
    assert installed_record.protocol_supported is True
    call_result = manager.call_tool("terrain-runtime", "status", {"message": "generic-onefile"})
    assert call_result["success"] is True
    assert call_result["data"]["entry"] == "packaged"
    assert call_result["data"]["echo"] == "generic-onefile"
    assert (install_dir / "runtime" / "keep.txt").read_text(encoding="utf-8") == "keep me\n"
    assert not (install_dir / "plugin.json").exists()
    assert not (install_dir / "plugin.py").exists()
    assert not (install_dir / "README.md").exists()
    assert not (install_dir / "build").exists()
    assert not (install_dir / "dist").exists()
    assert not (install_dir / "terrain-runtime.spec").exists()
    assert "plugin.json" in result["legacy_cleanup"]


def test_plugins_commands_render_delivery_and_template_surfaces(tmp_path: Path) -> None:
    app_root = tmp_path / "app"
    _create_template_tree(app_root)
    _create_runtime_plugin(app_root, packaged=False)
    manager = RuntimePluginManager(app_root)

    status_console = Console(record=True, force_terminal=False, width=120)
    status_handler = CommandHandler(
        status_console,
        {
            "runtime_plugin_manager": manager,
            "project_root": tmp_path,
        },
    )
    assert status_handler.handle("/plugins") is True
    status_text = status_console.export_text()
    assert "Runtime Plugins" in status_text
    assert "Delivery" in status_text
    assert "Sample Runtime" in status_text

    inspect_console = Console(record=True, force_terminal=False, width=120)
    inspect_handler = CommandHandler(
        inspect_console,
        {
            "runtime_plugin_manager": manager,
            "project_root": tmp_path,
        },
    )
    assert inspect_handler.handle("/plugins inspect sample-runtime") is True
    inspect_text = inspect_console.export_text()
    assert "Compiled Entry" in inspect_text
    assert "Source Fallback" in inspect_text
    assert "Build Commands" in inspect_text

    template_console = Console(record=True, force_terminal=False, width=120)
    template_handler = CommandHandler(
        template_console,
        {
            "runtime_plugin_manager": manager,
            "project_root": tmp_path,
        },
    )
    assert template_handler.handle("/plugins templates") is True
    template_text = template_console.export_text()
    assert "Runtime Plugin Templates" in template_text
    assert "runtime_python_exe" in template_text

    template_inspect_console = Console(record=True, force_terminal=False, width=120)
    template_inspect_handler = CommandHandler(
        template_inspect_console,
        {
            "runtime_plugin_manager": manager,
            "project_root": tmp_path,
        },
    )
    assert template_inspect_handler.handle("/plugins template inspect runtime_python_exe") is True
    template_inspect_text = template_inspect_console.export_text()
    assert "Manifest Preview" in template_inspect_text
    assert "Entry Preview" in template_inspect_text


def test_plugins_sdk_depot_prepares_portable_runtime_manifest(tmp_path: Path) -> None:
    app_root = tmp_path / "app"
    manager = RuntimePluginManager(app_root)

    result = manager.materialize_sdk_package("blender")

    assert result["success"] is True
    manifest_path = app_root / ".reverie" / "plugins" / "blender" / "sdk_manifest.json"
    sdk_dir = app_root / ".reverie" / "plugins" / "blender" / "runtime"
    assert manifest_path.exists()
    assert sdk_dir.exists()
    payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert payload["role"] == "portable SDK/runtime depot"
    assert payload["plugin_id"] == "blender"

    status = manager.sdk_package_status("blender", force_refresh=True)
    assert status["status"] == "prepared"
    assert status["download_page"] == "https://www.blender.org/download/"


def test_default_runtime_catalog_focuses_open_engine_plugins() -> None:
    catalog_ids = {item.plugin_id for item in DEFAULT_RUNTIME_PLUGIN_CATALOG}

    assert {"godot", "o3de", "blender"}.issubset(catalog_ids)
    assert "blockbench" not in catalog_ids
    assert "unity" not in catalog_ids
    assert "unreal" not in catalog_ids


def test_o3de_sdk_manifest_is_deployable_but_not_directly_launched(tmp_path: Path) -> None:
    app_root = tmp_path / "app"
    manifest_path = app_root / ".reverie" / "plugins" / "o3de" / "runtime" / "sdk_manifest.json"
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text(json.dumps({"runtime": "o3de", "source_dir": "source/o3de-2510.2"}), encoding="utf-8")
    manager = RuntimePluginManager(app_root)

    status = manager.sdk_package_status("o3de", force_refresh=True)
    run_result = manager.run_sdk_package("o3de", deploy_if_missing=False)

    assert status["status"] == "ready"
    assert status["entry_path"] == manifest_path.resolve(strict=False)
    assert run_result["success"] is False
    assert "source-managed" in run_result["error"]


def test_godot_sdk_status_detects_nested_plugin_runtime(tmp_path: Path) -> None:
    app_root = tmp_path / "app"
    runtime_path = app_root / ".reverie" / "plugins" / "godot" / "runtime" / "4.6.2-stable" / "Godot_v4.6.2-stable_win64.exe"
    runtime_path.parent.mkdir(parents=True, exist_ok=True)
    runtime_path.write_text("godot", encoding="utf-8")
    manager = RuntimePluginManager(app_root)

    status = manager.sdk_package_status("godot", force_refresh=True)

    assert status["status"] == "ready"
    assert status["entry_path"] == runtime_path.resolve(strict=False)


def test_sdk_runtime_entries_do_not_require_rc_handshake(tmp_path: Path) -> None:
    app_root = tmp_path / "app"
    manager = RuntimePluginManager(app_root)
    result = manager.materialize_sdk_package("blender")
    sdk_dir = Path(result["sdk_dir"])
    entry_name = "blender.exe" if platform.system() == "Windows" else "blender"
    entry_path = sdk_dir / entry_name
    entry_path.write_text("portable blender placeholder\n", encoding="utf-8")
    if platform.system() != "Windows":
        entry_path.chmod(entry_path.stat().st_mode | stat.S_IXUSR)

    record = manager.get_record("blender", force_refresh=True)

    assert record is not None
    assert record.status == "ready"
    assert record.protocol_status == "sdk-only"


def test_plugins_sdk_command_renders_depot_surface(tmp_path: Path) -> None:
    app_root = tmp_path / "app"
    manager = RuntimePluginManager(app_root)

    sdk_console = Console(record=True, force_terminal=False, width=120)
    sdk_handler = CommandHandler(
        sdk_console,
        {
            "runtime_plugin_manager": manager,
            "project_root": tmp_path,
        },
    )
    assert sdk_handler.handle("/plugins sdk blender") is True
    sdk_text = sdk_console.export_text()
    assert "Plugin SDK blender" in sdk_text
    assert "SDK depot prepared." in sdk_text
    assert "www.blender.org/download" in sdk_text


def test_runtime_plugin_manager_can_deploy_portable_blender_archive(tmp_path: Path) -> None:
    app_root = tmp_path / "app"
    archive_path = app_root / "blender-5.1.1-windows-x64.zip"
    _create_portable_blender_zip(archive_path)
    manager = RuntimePluginManager(app_root)

    result = manager.deploy_sdk_package("blender")

    assert result["success"] is True
    status = result["status"]
    assert status["plugin_id"] == "blender"
    assert status["status"] == "ready"
    assert status["bundled_archive"] == archive_path.resolve(strict=False)
    entry_path = status["entry_path"]
    assert isinstance(entry_path, Path)
    assert entry_path.exists()
    assert entry_path.name in {"blender.exe", "blender"}


def test_sdk_archive_can_live_inside_installed_plugin_depot(tmp_path: Path) -> None:
    app_root = tmp_path / "app"
    archive_path = app_root / ".reverie" / "plugins" / "blender" / "blender-5.1.1-windows-x64.zip"
    _create_portable_blender_zip(archive_path)
    manager = RuntimePluginManager(app_root)

    status = manager.sdk_package_status("blender", force_refresh=True)

    assert status["bundled_archive"] == archive_path.resolve(strict=False)


def test_sdk_status_ignores_optional_wrapper_entry_for_runtime_readiness(tmp_path: Path) -> None:
    app_root = tmp_path / "app"
    manager = RuntimePluginManager(app_root)
    prepared = manager.materialize_sdk_package("blender")
    plugin_dir = app_root / ".reverie" / "plugins" / "blender"
    source_script = plugin_dir / "plugin.py"
    source_script.write_text("print('wrapper')\n", encoding="utf-8")
    wrapper_path = plugin_dir / _compiled_entry_name("blender")
    _write_platform_wrapper(wrapper_path, source_script)
    _write_manifest(plugin_dir, plugin_id="blender", compiled_relative_path=_compiled_entry_name("blender"))

    status = manager.sdk_package_status("blender", force_refresh=True)

    assert prepared["success"] is True
    assert status["status"] == "prepared"
    assert status["entry_path"] is None


def test_plugins_deploy_command_extracts_portable_blender_archive(tmp_path: Path) -> None:
    app_root = tmp_path / "app"
    archive_path = app_root / "blender-5.1.1-windows-x64.zip"
    _create_portable_blender_zip(archive_path)
    manager = RuntimePluginManager(app_root)

    deploy_console = Console(record=True, force_terminal=False, width=120)
    deploy_handler = CommandHandler(
        deploy_console,
        {
            "runtime_plugin_manager": manager,
            "project_root": tmp_path,
        },
    )
    assert deploy_handler.handle("/plugins deploy blender") is True
    deploy_text = deploy_console.export_text()
    assert "Deploy blender" in deploy_text
    assert "Plugin deployment completed." in deploy_text
    assert ".reverie\\plugins\\blender\\runtime" in deploy_text or ".reverie/plugins/blender/runtime" in deploy_text


def test_plugins_models_command_plans_trellis_low_vram(tmp_path: Path) -> None:
    app_root = tmp_path / "app"
    manager = RuntimePluginManager(app_root)
    console = Console(record=True, force_terminal=False, width=140)
    handler = CommandHandler(
        console,
        {
            "runtime_plugin_manager": manager,
            "project_root": tmp_path,
        },
    )

    assert handler.handle("/plugins models plan ram=24 vram=8") is True

    text = console.export_text()
    assert "Game Model Plan" in text
    assert "trellis-text-xlarge" in text
    assert "low_vram" in text


def test_plugins_commands_can_scaffold_validate_and_build(tmp_path: Path) -> None:
    app_root = tmp_path / "app"
    _create_template_tree(app_root)
    manager = RuntimePluginManager(app_root)

    scaffold_console = Console(record=True, force_terminal=False, width=120)
    scaffold_handler = CommandHandler(
        scaffold_console,
        {
            "runtime_plugin_manager": manager,
            "project_root": tmp_path,
        },
    )
    assert (
        scaffold_handler.handle(
            '/plugins scaffold terrain-runtime template=runtime_python_exe family=engine name="Terrain Runtime" description="Terrain runtime plugin." command=sync_assets'
        )
        is True
    )
    scaffold_text = scaffold_console.export_text()
    assert "Plugin Scaffold" in scaffold_text
    assert "Created Files" in scaffold_text

    validate_console = Console(record=True, force_terminal=False, width=120)
    validate_handler = CommandHandler(
        validate_console,
        {
            "runtime_plugin_manager": manager,
            "project_root": tmp_path,
        },
    )
    assert validate_handler.handle("/plugins validate terrain-runtime") is True
    validate_text = validate_console.export_text()
    assert "Validate terrain-runtime" in validate_text
    assert "Build Commands" in validate_text

    build_console = Console(record=True, force_terminal=False, width=120)
    build_handler = CommandHandler(
        build_console,
        {
            "runtime_plugin_manager": manager,
            "project_root": tmp_path,
        },
    )
    assert build_handler.handle("/plugins build terrain-runtime install overwrite") is True
    build_text = build_console.export_text()
    assert "Build terrain-runtime" in build_text
    assert "Plugin build completed." in build_text
    assert "Install Target" in build_text
    assert "Install Mode" in build_text
