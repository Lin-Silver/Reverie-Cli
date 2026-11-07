# Blender Official Plugin

This is Reverie CLI's official Blender Portable plugin.

The packaged `reverie-blender.exe` embeds `blender-5.1.1-windows-x64.zip`. Users do not need to manage that zip in the installed plugin depot: Reverie can call the plugin, the plugin extracts Blender into `dist/.reverie/plugins/blender/runtime/`, and AI tools can then run Blender scripts against that portable executable.

The plugin also manages MMD Tools as a plugin-local Blender add-on. It clones `https://github.com/MMD-Blender/blender_mmd_tools.git` into `dist/.reverie/plugins/blender/addons/blender_mmd_tools/`, injects that path into Blender only for Reverie-managed launches/probes, and supports PMD/PMX model import with optional VMD motion or VPD pose files.

## Automatically loaded illustration and avatar Skill

Enabling and trusting the plugin automatically registers `RuiC-card-skill` in
Reverie's Skill catalog. Its pinned upstream source is
[`HRuiCcc/RuiC-card-skill` at `8f31e323`](https://github.com/HRuiCcc/RuiC-card-skill/tree/8f31e323ccab637671ee5553772873d448868dd4).
The executable includes its MIT notice, references, Python scripts and bundled
Three.js viewer. Each handshake materializes these text resources under
`dist/.reverie/plugins/blender/skills/ruic-card-skill/`, so they remain readable
after the one-file executable's temporary extraction directory disappears.
Disabling or untrusting the plugin removes its Skill from the model's catalog.

The Skill includes source-preserving 2D virtual avatars for browser and OBS:
deformable portrait meshes, blinking, smile and mouth masks, head/body/hair motion,
local microphone mouth movement, browser-to-OBS pose synchronization,
transparent PNG export and an editable
`avatar.blend`. It also covers layered illustration-to-3D-style cards. Its
Reverie avatar reference connects full humanoid authoring to
`blender_modeling_workbench`'s `production_character_pipeline`, rigging, facial
shape keys and export QA. The procedural preset is a starting point; an actual
reference image still requires identity-specific modeling and visual review.
VRM requires an installed compatible exporter and target-runtime validation.

Inspect the Skill with `skill_lookup`, and use `read_resource` for the packaged
`references/avatar-workflows.md` or scripts. For cards, prepare the specified
transparent layers and configuration in the output project, then run:

```text
python <skill-resource-dir>/scripts/run_pipeline.py --project <output-project> --blender <data.detected.path> --skip-npm
node <skill-resource-dir>/scripts/verify_web.mjs <output-project>
```

For a 2D avatar, inspect the actual eye/mouth positions and write
`avatar-config.json` from `references/avatar-config.example.json`, then run:

```text
python <skill-resource-dir>/scripts/run_avatar_pipeline.py --project <output-project> --blender <data.detected.path>
node <output-project>/web/server.mjs
```

The 2D viewer requires no npm dependencies. Its OBS browser-source URL ends in
`?obs=1`; use the source dimensions from `web/avatar.json`. Open the regular
browser viewer, enable 同步到 OBS, then use its controls or allow microphone
mouth movement. The loopback server sends eight numeric pose values to OBS;
audio stays in the browser. Stopping synchronization restores independent
motion. Without synchronization, OBS Interact supports B to blink, S to smile
and T for the talking demo.
The original portrait remains byte-identical in the output project. Expression
masks and movement still require visual checks against that portrait.

The integration, browser/OBS and frozen-package checks are recorded in
[VERIFICATION.md](VERIFICATION.md).

Obtain `data.detected.path` from `rc_blender_ensure_runtime`. Python with Pillow
and Node.js are required for the card scripts/browser verifier. The shipped
bundled viewer works without installing npm dependencies; omit `--skip-npm`
when modifying and rebuilding its source. Blender remains in the existing
plugin-local `runtime/` directory, Blender configuration remains plugin-local,
and artwork, exports and web dependency caches remain in the output project.

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
- `inspect_scene`
  Open a `.blend` file in background mode and report bounded scene, object, material, animation, image, and missing linked-file metadata.
- `import_mmd_model`
  Import a `.pmx` or `.pmd` model through MMD Tools, optionally apply `.vmd` motion or `.vpd` pose, save a `.blend`, and optionally export `.glb`/`.gltf`.

All exposed commands are intended to be available in every Reverie mode. In the model tool surface they include `rc_blender_ensure_runtime`, `rc_blender_runtime_status`, `rc_blender_mmd_tools_status`, `rc_blender_ensure_mmd_tools`, `rc_blender_detect_runtime`, `rc_blender_version`, `rc_blender_open_blender`, `rc_blender_run_script`, `rc_blender_inspect_scene`, and `rc_blender_import_mmd_model`.

The built-in `blender_modeling_workbench` remains the preferred authoring layer for generating auditable modeling scripts, production character pipeline plans, `.blend` files, `.glb` exports, and preview renders. This plugin supplies the portable Blender application that executes those scripts.

## Build

Place `blender-5.1.1-windows-x64.zip` beside this README or in the legacy staging location `dist/.reverie/plugins/blender/`, then run:

```bat
build.bat
```

The build output is `dist/reverie-blender.exe`. Installation places the executable
at `dist/.reverie/plugins/reverie-blender.exe`; the runtime and Skill resources
remain in the Blender subdirectory. The installed plugin relies on the embedded
archive and does not need a separate Blender zip. The builder includes only
Skill text resources, excluding generated artwork, dependencies and caches.
