# Reverie-Gamer Modeling Pipeline

## Purpose

Reverie CLI includes a built-in modeling workflow for `Reverie-Gamer`.

The pipeline standardizes how modeled assets move from authoring to runtime:

- Blender for direct `.blend` authoring, procedural asset generation, preview rendering, and `.glb`/`.gltf` export
- Blockbench for editing and authoring
- Ashfox for validation, preview, export, and automation
- Reverie Engine for import, registry, and runtime-facing structure

## Integration Strategy

Reverie no longer depends on checked-out Blockbench or Ashfox source trees.

What is built in:

- the `blender_modeling_workbench` tool and `/blender` command
- Blender executable detection through `REVERIE_BLENDER_PATH`, `BLENDER_PATH`, PATH, and common install locations
- generated Blender model plans and workspace-local Python authoring scripts
- Blender background execution for `.blend` source saves, `.glb`/`.gltf` runtime exports, preview renders, and registry sync
- the Reverie-Gamer modeling workspace layout
- the `/modeling` command surface
- a seeded built-in `ashfox` MCP server entry
- Gamer-only Ashfox MCP tool exposure through `/tools`
- model registry, import, and inspection helpers

What remains manual:

- install Blender desktop, or use the official Blender plugin to unpack its embedded portable Blender build to `.reverie/plugins/blender/runtime/blender.exe`, when using direct Blender execution
- install Blockbench desktop
- install the Ashfox plugin inside Blockbench
- launch Blockbench so the local Ashfox MCP endpoint is reachable

## Workspace Layout

The modeling workspace uses these paths:

- `assets/models/source/`: source authoring files such as `.bbmodel`
- `assets/models/source/blender/`: generated Blender plans, scripts, and workflow notes
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

## Blender Workflow

Use `/blender` when the asset should be authored directly in Blender instead of through an external MCP server.

For stylized playable-character blockouts, briefs that mention `anime action`, `Genshin`, `ZZZ`, `Zenless`, `Ananta`, or the Chinese titles for those styles select the `anime_action_character` preset. That preset emits layered clothing shapes, hair clumps, face markers, weapon silhouette, material IDs, rig markers, LOD markers, lighting, and preview/export wiring.

For a heavier production scaffold, briefs that mention `final character asset`, `high poly`, `retopo`, `UV unwrap`, `texture bake`, `rigged`, `skinned`, or the Chinese equivalents select the `production_character_pipeline` preset. That preset generates a high-poly sculpt collection, retopo/game-mesh collection, smart UV layout, texture placeholder exports, bake cages, a humanoid armature, preview actions, face shape-key placeholders, bone attachment sockets, and a turntable camera animation ready for further artist polish.

If Blender is portable rather than globally installed, run `/plugins deploy blender` or call `rc_blender_ensure_runtime`. The official Blender plugin embeds the portable archive in `reverie-blender.exe` and unpacks it to `.reverie/plugins/blender/runtime/blender.exe`.

Common flow:

1. `/blender setup`
2. `/plugins deploy blender`
3. `/blender script hero "AAA final character asset with high poly sculpt, retopo, UV unwrap, texture bake, rigged animation"`
4. inspect or edit `assets/models/source/blender/scripts/hero.py` if needed
5. `/blender create hero "AAA final character asset with high poly sculpt, retopo, UV unwrap, texture bake, rigged animation"`
6. review `assets/models/source/hero.blend`, `assets/models/runtime/hero.glb`, and `playtest/renders/models/hero.png`
7. `/plugins run blender`
   Open the deployed portable Blender build when manual sculpting, retopo cleanup, texture painting, or animation polish is needed.
8. `/blender sync`

The same workflow is exposed to the model through the built-in `blender_modeling_workbench` tool:

- `inspect_stack`
- `setup_workspace`
- `generate_script`
- `create_model`
- `run_script`
- `validate_script`
- `sync_registry`

The generated script is deliberately project-local and auditable. The default path uses Blender background mode and does not require a running MCP server, a Blender add-on server, or a Codex `SKILL.md`.

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
