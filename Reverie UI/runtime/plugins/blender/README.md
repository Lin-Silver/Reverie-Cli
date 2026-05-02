# Blender Official Plugin

This is Reverie CLI's official Blender Portable plugin.

The packaged `reverie-blender.exe` embeds `blender-5.1.1-windows-x64.zip`. Users do not need to manage that zip in the installed plugin depot: Reverie can call the plugin, the plugin extracts Blender into `dist/.reverie/plugins/blender/runtime/`, and AI tools can then run Blender scripts against that portable executable.

The plugin also manages MMD Tools as a plugin-local Blender add-on. It clones `https://github.com/MMD-Blender/blender_mmd_tools.git` into `dist/.reverie/plugins/blender/addons/blender_mmd_tools/`, injects that path into Blender only for Reverie-managed launches/probes, and supports PMD/PMX model import with optional VMD motion or VPD pose files.

## Commands

- `ensure_runtime`
  Extract the embedded Blender archive into the plugin-local `runtime/` folder.
- `runtime_status`
  Report plugin root, runtime root, embedded archive availability, detected Blender executable, and version probe details.
- `mmd_tools_status`
  Report the plugin-local MMD Tools checkout, supported extensions, Python paths, and optional Blender enablement probe.
- `ensure_mmd_tools`
  Clone/update MMD Tools from GitHub into the plugin-local `addons/` folder and optionally verify that Blender can enable it.
- `detect_runtime`
  Find Blender from explicit paths, environment variables, the plugin runtime folder, `PATH`, or common install folders.
- `version`
  Run `blender --version`.
- `open_blender`
  Launch Blender for interactive user work.
- `run_script`
  Run a Blender Python script in background mode.
- `import_mmd_model`
  Import a `.pmx` or `.pmd` model through MMD Tools, optionally apply `.vmd` motion or `.vpd` pose, save a `.blend`, and optionally export `.glb`/`.gltf`.

All exposed commands are intended to be available in every Reverie mode. In the model tool surface they appear as `rc_blender_ensure_runtime`, `rc_blender_runtime_status`, `rc_blender_mmd_tools_status`, `rc_blender_ensure_mmd_tools`, `rc_blender_detect_runtime`, `rc_blender_version`, `rc_blender_open_blender`, `rc_blender_run_script`, and `rc_blender_import_mmd_model`.

The built-in `blender_modeling_workbench` remains the preferred authoring layer for generating auditable modeling scripts, production character pipeline plans, `.blend` files, `.glb` exports, and preview renders. This plugin supplies the portable Blender application that executes those scripts.

## Build

Place `blender-5.1.1-windows-x64.zip` beside this README or in the legacy staging location `dist/.reverie/plugins/blender/`, then run:

```bat
build.bat
```

The build output is `dist/reverie-blender.exe`. During installation, Reverie copies the executable and manifest but ignores standalone zip files so the installed depot relies on the embedded archive.
