# Reverie-Gamer Modeling Pipeline

## Purpose

Reverie CLI `2.1.5` introduces a built-in modeling workflow for `Reverie-Gamer`.

The pipeline standardizes how modeled assets move from authoring to runtime:

- Blockbench for editing and authoring
- Ashfox for validation, preview, export, and automation
- Reverie Engine for import, registry, and runtime-facing structure

## Integration Strategy

Reverie no longer depends on checked-out Blockbench or Ashfox source trees.

What is built in:

- the Reverie-Gamer modeling workspace layout
- the `/modeling` command surface
- a seeded built-in `ashfox` MCP server entry
- Gamer-only Ashfox MCP tool exposure through `/tools`
- model registry, import, and inspection helpers

What remains manual:

- install Blockbench desktop
- install the Ashfox plugin inside Blockbench
- launch Blockbench so the local Ashfox MCP endpoint is reachable

## Workspace Layout

The modeling workspace uses these paths:

- `assets/models/source/`: source authoring files such as `.bbmodel`
- `assets/models/runtime/`: engine-facing exports such as `.glb` and `.gltf`
- `playtest/renders/models/`: previews and review snapshots
- `data/models/pipeline.yaml`: modeling-pipeline manifest
- `data/models/model_registry.yaml`: generated registry of discovered models

## CLI Workflow

The main command surface is `/modeling`, and it is intended for `reverie-gamer` mode only.

Common flow:

1. `/modeling setup`
2. `/modeling stub hero_body`
3. edit the generated `.bbmodel` in Blockbench
4. `/modeling ashfox validate`
5. `/modeling ashfox export gltf assets/models/runtime/hero_body.glb`
6. `/modeling import exports/hero_body.glb assets/models/source/hero_body.bbmodel`
7. `/modeling sync`

## Ashfox MCP Notes

The default Ashfox endpoint is:

`http://127.0.0.1:8787/mcp`

Reverie seeds the `ashfox` MCP server entry automatically and limits its discovered tools to `reverie-gamer` mode. When Blockbench is running with the Ashfox plugin, those tools will show up in `/tools` and can also be reached through `/modeling ashfox ...`.

Useful subcommands:

- `/modeling ashfox tools`
- `/modeling ashfox capabilities`
- `/modeling ashfox state summary`
- `/modeling ashfox validate`
- `/modeling ashfox export <format> <dest_path>`
- `/modeling ashfox call <tool_name> <json_arguments>`

## Registry Behavior

`data/models/model_registry.yaml` is generated from the current workspace.
It scans:

- source model files
- runtime model files
- preview images

The registry records:

- primary source file
- primary runtime file
- previews
- light metadata for `.bbmodel`, `.gltf`, `.glb`, and `.obj`

## Recommended Conventions

- Keep `.bbmodel` as the editable source-of-truth
- Prefer `.glb` or `.gltf` for runtime imports
- Re-run the registry sync after imports or exports
- Validate Ashfox MCP state before large export batches
- Keep model naming stable between source and runtime files so the registry can pair them cleanly
