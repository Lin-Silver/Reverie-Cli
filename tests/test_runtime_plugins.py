from __future__ import annotations

from pathlib import Path
from textwrap import dedent
import json
import platform
import stat
import sys

from rich.console import Console

from reverie.cli.commands import CommandHandler
from reverie.plugin.runtime_manager import RuntimePluginManager


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


def test_runtime_plugin_templates_are_discoverable_from_repo() -> None:
    repo_root = Path(__file__).resolve().parents[1]
    manager = RuntimePluginManager(repo_root)

    templates = manager.list_templates(force_refresh=True)
    template = manager.get_template("runtime_python_exe", force_refresh=False)
    summary = manager.get_status_summary(force_refresh=False)

    assert any(item.template_id == "runtime_python_exe" for item in templates)
    assert template is not None
    assert template.build_hint == "build.bat"
    assert (template.template_dir / "plugin.json").is_file()
    assert (template.template_dir / "plugin.py").is_file()
    assert summary["template_count"] >= 1


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
