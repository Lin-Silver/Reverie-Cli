# Runtime Python EXE Template

This template is the recommended starting point for a Reverie runtime plugin that is authored in Python and delivered as a packaged executable.

## Included files

- `plugin.json`
  Manifest using the richer packaged-entry schema.
- `plugin.py`
  Minimal Reverie runtime host with `-RC` and `-RC-CALL` support.
- `build.bat`
  Windows packaging entry point for PyInstaller.

## Placeholder tokens

Replace these tokens after copying the template into `plugins/<plugin-id>/`:

- `{{plugin_id}}`
- `{{plugin_name}}`
- `{{plugin_runtime_family}}`
- `{{plugin_description}}`
- `{{plugin_tool_name}}`

## Recommended workflow

1. Copy the template into `plugins/<plugin-id>/`.
2. Replace the placeholder tokens.
3. Add real runtime commands inside `handle_command`.
4. Build the packaged binary with `build.bat` or your preferred PyInstaller command.
5. Deliver the compiled output plus `plugin.json` into `.reverie/plugins/<plugin-id>/`.
6. Validate with `/plugins inspect <plugin-id>`.

## Packaging notes

- The manifest prefers the packaged entry under `dist/`.
- During development, Reverie can fall back to `plugin.py`.
- The template resolves `_sdk` from both source-tree and frozen-bundle layouts so the same code works before and after packaging.
