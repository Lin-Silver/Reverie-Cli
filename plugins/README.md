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
  Official Blender Portable plugin. Its packaged `reverie-blender.exe` embeds `blender-5.1.1-windows-x64.zip` and can unpack it on demand with `rc_blender_ensure_runtime` or `/plugins deploy blender`.
- `plugins/godot/`
  Godot runtime manager for detection, registration, download/unpack, project scanning, launch, and headless checks.

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
4. Run `/plugins run blender`, `rc_blender_run_script`, or the built-in `blender_modeling_workbench`.

The Blender zip is a build input for the plugin executable. It should not need to remain as a separate file in the installed `dist/.reverie/plugins/blender/` depot after packaging.
