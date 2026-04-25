# Runtime Plugin Source Tree

Plugins in Reverie CLI are portable software/runtime bundles, not another user-facing prompt layer beside Skills or MCP. They help users deploy and run heavyweight local environments beside `reverie.exe`, while protocol-ready plugin executables can also expose focused `rc_*` tools to the AI.

## Directory Roles

- `reverie/plugin/`
  Main-process discovery, manifest parsing, protocol handshakes, dynamic `rc_*` tool exposure, and `/plugins` command integration.
- `plugins/<plugin-id>/`
  Source for one official or optional runtime plugin before packaging.
- `dist/.reverie/plugins/<plugin-id>/`
  Installed plugin/runtime depot used by packaged or source-checkout runs.
- `dist/.reverie/plugins/<plugin-id>/runtime/`
  Portable SDK/runtime payloads created by a plugin executable or `/plugins deploy`.

## Official Plugins

- `plugins/blender/`
  Official Blender Portable plugin. Its packaged `reverie-blender.exe` embeds `blender-5.1.1-windows-x64.zip`, can unpack it on demand with `rc_blender_ensure_runtime` or `/plugins deploy blender`, and can clone MMD Tools into its plugin-local `addons/` folder for PMD/PMX/VMD/VPD import workflows.
- `plugins/godot/`
  Godot runtime manager for detection, registration, GitHub release download/unpack, source checkout, project scanning, launch, and headless checks.
- `plugins/o3de/`
  O3DE source SDK manager for GitHub version discovery, plugin-local source checkout, and local SDK manifest generation.
- `plugins/game_models/`
  Game auxiliary model depot manager for plugin-local Python venvs, HuggingFace model snapshots/caches, 8GB-VRAM deployment planning, selectable model profiles, and guarded heavy-model downloads.

## Fixed Protocol

Every runnable runtime plugin should support:

- `<plugin-entry> -RC`
  Return the Reverie CLI handshake JSON.
- `<plugin-entry> -RC-CALL <command> <json-arguments>`
  Execute one plugin command and return a JSON result.

When a command has `"expose_as_tool": true`, Reverie can surface it as `rc_<plugin>_<command>`. Empty `include_modes` means the command is available in every mode unless `exclude_modes` blocks it.

## Blender Flow

1. Build `plugins/blender/dist/reverie-blender.exe`.
2. Install the plugin into `dist/.reverie/plugins/blender/`.
3. Run `/plugins deploy blender` or call `rc_blender_ensure_runtime`.
4. For MMD assets, call `rc_blender_ensure_mmd_tools` once or let `rc_blender_import_mmd_model` prepare it automatically.
5. Run `/plugins run blender`, `rc_blender_run_script`, `rc_blender_import_mmd_model`, or the built-in `blender_modeling_workbench`.

The Blender zip is a build input for the plugin executable. It should not need to remain as a separate file in the installed `dist/.reverie/plugins/blender/` depot after packaging.

MMD Tools is cloned from `https://github.com/MMD-Blender/blender_mmd_tools.git` into `dist/.reverie/plugins/blender/addons/blender_mmd_tools/`. The plugin sets Blender user config and Python paths to plugin-local folders when probing or launching Blender, so this does not require a global Blender add-on install.

## Game Model Flow

1. Build `plugins/game_models/dist/reverie-game-models.exe`.
2. Install the plugin into `dist/.reverie/plugins/game_models/`.
3. Run `/plugins deploy game_models` or call `rc_game_models_prepare_environment`.
4. Run `/plugins models plan ram=24 vram=8` or call `rc_game_models_deployment_plan` before downloads.
5. Run `/plugins models select trellis-text-xlarge profile=low_vram download` or call `rc_game_models_select_model` when choosing a model/profile.
6. Call `rc_game_models_download_model` with `dry_run=true` first, then download only models that fit the local hardware profile.

Model snapshots, caches, and virtual environments must stay inside `dist/.reverie/plugins/game_models/` unless the user explicitly registers an external model path.
