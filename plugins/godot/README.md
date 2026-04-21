# Godot Plugin Source

This directory contains the source code for the Reverie CLI `godot` runtime plugin.

Current capabilities:

- Reverie CLI `-RC` handshake and `-RC-CALL` execution
- Plugin-local runtime status inspection
- Existing Godot runtime registration
- Plugin-local Godot runtime installation from zip archives or official release downloads
- Runtime detection and `--version` probing
- Godot project scanning
- `--editor --path` launch
- `--headless --path --quit` validation

Source-tree development install:

1. Copy `plugin.py` and `plugin.json` to `.reverie/plugins/godot/`
2. Optional: set `REVERIE_GODOT_EXE` if Godot already exists elsewhere

Compiled delivery target:

- Build the wrapper as `godot.exe`, not `plugin.exe`
- The `-RC` handshake metadata is embedded in the executable output
- Runtime state is persisted without `runtime_config.json`
- The bundled Godot archive is unpacked into `.reverie/plugins/godot/runtime/` on first use
- Godot `rc_*` commands are exposed to both Reverie and Reverie-Gamer modes.

After installation, Reverie can expose:

- `/plugins`
- `/plugins inspect godot`
- `rc_godot_runtime_status`
- `rc_godot_register_runtime`
- `rc_godot_install_runtime`
- `rc_godot_detect_runtime`
- `rc_godot_version`
- `rc_godot_scan_project`
- `rc_godot_open_editor`
- `rc_godot_headless_check`
