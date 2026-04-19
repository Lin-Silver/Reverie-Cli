# Plugins Source Tree

This directory is the source workspace for Reverie CLI runtime plugins. It is separate from the main-process plugin protocol code in `reverie/plugin/`, and it is also separate from the installed runtime-plugin delivery root under `.reverie/plugins/`.

## Directory roles

- `reverie/plugin/`
  Main-process runtime-plugin protocol, discovery, manifest parsing, dynamic tool exposure, and `/plugins` command integration.
- `plugins/<plugin-id>/`
  Source code for one runtime plugin wrapper before packaging.
- `plugins/_sdk/`
  Shared helpers used by plugin source trees, including the fixed Reverie CLI runtime host shell.
- `plugins/_templates/`
  Reusable source templates for authoring new runtime plugins, especially Python plugins that are later compiled into a single-file `exe`.

## Delivery roots

- Source tree: `plugins/<plugin-id>/`
- Installed runtime root: `.reverie/plugins/<plugin-id>/`

Typical workflow:

1. Author plugin source under `plugins/<plugin-id>/`.
2. Package it into a compiled runtime entry, usually a single-file `exe`.
3. Copy the packaged result plus `plugin.json` into `.reverie/plugins/<plugin-id>/`.
4. Use `/plugins`, `/plugins inspect <plugin-id>`, and `/plugins templates` to validate the delivery.

Command-driven workflow:

1. `/plugins scaffold <plugin-id>`
   Create a source plugin tree from a bundled template such as `runtime_python_exe`.
2. `/plugins validate <plugin-id>`
   Check manifest health, source fallback readiness, and build prerequisites.
3. `/plugins build <plugin-id> install`
   Run the declared build commands and sync the result into `.reverie/plugins/<plugin-id>/`.

## Fixed protocol

Every runnable runtime plugin must support:

- `<plugin-entry> -RC`
  Return the Reverie CLI handshake JSON.
- `<plugin-entry> -RC-CALL <command> <json-arguments>`
  Execute one plugin command and return a JSON result.

Source fallback entries can be `.py`, `.cmd`, `.bat`, `.ps1`, or platform-native executables. Compiled entries are typically `.exe` on Windows.

## Recommended manifest format

Reverie now supports a richer `plugin.json` schema for Python-to-EXE plugins:

```json
{
  "schema_version": "2.0",
  "id": "sample-runtime",
  "display_name": "Sample Runtime Plugin",
  "runtime_family": "engine",
  "version": "0.1.0",
  "delivery": "python-exe",
  "template": "runtime_python_exe",
  "description": "Example Reverie runtime plugin.",
  "entry": {
    "preferred": {
      "windows": "dist/reverie-sample-runtime.exe",
      "linux": "dist/reverie-sample-runtime",
      "darwin": "dist/reverie-sample-runtime"
    },
    "fallbacks": {
      "default": "plugin.py"
    },
    "strategy": "prefer-packaged",
    "allow_source_fallback": true
  },
  "packaging": {
    "format": "pyinstaller-onefile",
    "compiled": {
      "windows": "dist/reverie-sample-runtime.exe",
      "linux": "dist/reverie-sample-runtime",
      "darwin": "dist/reverie-sample-runtime"
    },
    "source": {
      "default": "plugin.py"
    },
    "build": {
      "windows": [
        "build.bat"
      ],
      "default": [
        "python -m PyInstaller --noconfirm --clean --onefile --name reverie-sample-runtime plugin.py"
      ]
    }
  }
}
```

### Key fields

- `schema_version`
  Manifest version tracked by Reverie. `2.0` is the current richer packaged-entry format.
- `delivery`
  High-level plugin delivery type. Use `python-exe` for Python source wrapped into a compiled executable.
- `entry.preferred`
  Compiled entry candidates Reverie should prefer at runtime.
- `entry.fallbacks`
  Source/script entries Reverie can use when the compiled artifact is missing during development.
- `entry.strategy`
  Usually `prefer-packaged` for production-ready plugins.
- `packaging.format`
  Packaging toolchain label, for example `pyinstaller-onefile`.
- `packaging.build`
  Human-readable build commands surfaced in `/plugins inspect`.
- `template`
  Template id that the plugin source was based on.

## Templates

Use `/plugins templates` to inspect the bundled authoring templates. The primary template for packaged runtime wrappers is:

- `runtime_python_exe`
  Python source plugin with a compiled-entry manifest, source fallback, and build-script guidance.

## Current source directories

- `plugins/godot/`
- `plugins/_templates/runtime_python_exe/`
- `plugins/_sdk/`
