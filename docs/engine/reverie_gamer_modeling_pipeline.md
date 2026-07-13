# Reverie-Gamer Modeling Pipeline

## Purpose

Reverie CLI includes a built-in modeling workflow for `Reverie-Gamer`.

The pipeline standardizes how modeled assets move from authoring to runtime. Blender and Blockbench support should be understood as editor control, source generation, validation, and export automation rather than a guarantee that Reverie can synthesize final hand-authored character art by itself.

- Blender for direct `.blend` authoring control, procedural scaffold generation, preview rendering, and `.glb`/`.gltf` export
- a built-in Ashfox MCP server configuration for live Blockbench automation when an editor session is already running
- headless `.bbmodel` validation/export for simple Blockbench-style cuboid assets
- Reverie Engine for import, registry, and runtime-facing structure
- the `game_models` runtime plugin for optional local auxiliary open model packages under `.reverie/plugins/game_models/`

## Integration Strategy

Reverie no longer depends on checked-out Blockbench or Ashfox source trees.

What is built in:

- the `blender_modeling_workbench` tool and `/blender` command
- Blender executable detection through `REVERIE_BLENDER_PATH`, `BLENDER_PATH`, PATH, and common install locations
- generated Blender model plans and workspace-local Python authoring scripts
- Blender background execution for `.blend` source saves, `.glb`/`.gltf` runtime exports, preview renders, and registry sync
- the Reverie-Gamer modeling workspace layout
- the `/modeling` command surface
- headless `.bbmodel` validation and simple cuboid `.bbmodel` -> `.gltf` export through `game_modeling_workbench`
- a seeded built-in `ashfox` MCP server entry
- Gamer-only Ashfox MCP tool exposure through `/tools`
- model registry, import, and inspection helpers

What remains optional:

- install Blender desktop, or use the official Blender plugin to unpack its embedded portable Blender build to `.reverie/plugins/blender/runtime/blender.exe`, when using direct Blender execution
- use Blockbench desktop only when visual `.bbmodel` editing is desired
- enable the Ashfox plugin inside Blockbench only for live editor automation
- launch Blockbench only when the local Ashfox MCP endpoint should be queried

Without a desktop Blockbench/Ashfox session, Reverie still validates simple `.bbmodel` files and exports cuboid elements to runtime `.gltf` files. Complex Blockbench features such as rotations, custom face UV paint, and editor previews remain optional live-editor work.

For model-assisted asset generation, use `/plugins deploy game_models`, `/plugins models ...`, and the exposed `rc_game_models_*` tools. The default policy targets 24GB RAM / 8GB VRAM and treats `microsoft/TRELLIS-text-xlarge` as selectable through `profile=low_vram`; `stable-fast-3d`, `tencent/Hunyuan3D-2mini`, and `tripo-sr` remain image-to-3D fallback/ideation helpers. `tencent/HY-Motion-1.0` remains guarded and requires explicit `allow_heavy=true`.

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
3. `/modeling export-bbmodel assets/models/source/hero_body.bbmodel`
4. optionally edit the generated `.bbmodel` in Blockbench for richer authored detail
5. optionally run `/modeling ashfox validate`
6. optionally run `/modeling ashfox export gltf assets/models/runtime/hero_body.glb`
7. `/modeling import exports/hero_body.glb assets/models/source/hero_body.bbmodel`
8. `/modeling sync`

## Blender Workflow

Use `/blender` when the asset should be controlled or scaffolded directly in Blender instead of through an external MCP server.

For stylized playable-character blockouts, briefs that mention `anime action`, `Genshin`, `ZZZ`, `Zenless`, `Ananta`, or the Chinese titles for those styles select the `anime_action_character` preset. That preset emits layered clothing shapes, hair clumps, face markers, weapon silhouette, material IDs, rig markers, LOD markers, lighting, and preview/export wiring.

For a heavier production scaffold, briefs that mention `final character asset`, `high poly`, `retopo`, `UV unwrap`, `texture bake`, `rigged`, `skinned`, or the Chinese equivalents select the `production_character_pipeline` preset. That preset generates a fused continuous body core, high-poly sculpt collection, retopo/game-mesh collection, smart UV layout, procedural basecolor/normal/ORM/material-ID texture seed maps, texture authoring metadata, bake cages, mesh metrics, body-continuity report, PBR material tuning, a humanoid armature, weight hints, a skinning manifest, IK targets and constraints, animation clips plus an animation manifest, non-zero facial shape-key deformation data, a skinning stress-test action, bone attachment sockets, runtime collision proxies, LOD variants, a visual QA report, an engine import contract, a turntable camera animation, a production stage manifest, a black-box iteration plan, a production asset card, and quality gates ready for downstream runtime use. It remains a scaffold/control workflow; final anatomy, appeal, clothing design, topology polish, and texture paint still require manual DCC or model-assisted passes.

For playable humanoids, do not accept disconnected limb/torso blockouts as final. The reference target is closer to the local `Nahida Dragon` sample: one primary Body mesh, one Armature, UVs, multiple material slots, external 2048 texture maps, and many facial/shape-key targets. Reverie-generated output should therefore keep a continuous deformable body core under layered hair, clothing, accessories, weapon meshes, and VFX.

If Blender is portable rather than globally installed, run `/plugins deploy blender` or call `rc_blender_ensure_runtime`. The official Blender plugin embeds the portable archive in `reverie-blender.exe` and unpacks it to `.reverie/plugins/blender/runtime/blender.exe`.

For imported MMD characters, use `rc_blender_import_mmd_model` with a `.pmx` or `.pmd` path. The command automatically prepares the open-source MMD Tools add-on in `.reverie/plugins/blender/addons/blender_mmd_tools/`, can apply optional `.vmd` motion or `.vpd` pose files, saves a `.blend` source, and can export `.glb`/`.gltf` when requested. This is the preferred route for high-quality externally authored MMD models; Reverie should treat those assets as reference/production inputs rather than trying to rebuild the full character from primitives.

Common flow:

1. `/blender setup`
2. `/plugins deploy blender`
3. `/plugins models plan ram=24 vram=8`
4. `/plugins models select trellis-text-xlarge profile=low_vram download`
5. `/blender script hero "AAA final character asset with high poly sculpt, retopo, UV unwrap, texture bake, rigged animation"`
6. inspect or edit `assets/models/source/blender/scripts/hero.py` if needed
7. `/blender create hero "AAA final character asset with high poly sculpt, retopo, UV unwrap, texture bake, rigged animation"`
   Successful Blender runs automatically attach an audit result to the tool output.
8. review `assets/models/source/hero.blend`, `assets/models/runtime/hero.glb`, and `playtest/renders/models/hero.png`
9. `/blender audit hero`
   Check generated artifacts, GLB header validity, texture completeness, validation schema, production manifest, black-box iteration plan, body-continuity report, material/skin/animation/facial manifests, pose-stress action, visual QA report, engine import contract, rig/action/IK coverage, weights, sockets, collision proxies, LOD coverage, and in-Blender production gates.
10. `/plugins run blender`
   Open the deployed portable Blender build when manual sculpting, retopo cleanup, texture painting, or animation polish is needed.
11. Optional MMD import: `rc_blender_import_mmd_model` with `model_path`, optional `motion_path`, optional `pose_path`, and optional `export_path`.
12. `/blender sync`

The same workflow is exposed to the model through the built-in `blender_modeling_workbench` tool:

- `inspect_stack`
- `setup_workspace`
- `generate_script`
- `create_model`
- `run_script`
- `validate_script`
- `audit_model`
- `repair_model`
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
