# Reverie Engine User Guide

## Overview

`reverie_engine` is Reverie CLI's canonical built-in runtime surface.
The previous lightweight compatibility package has been migrated into `reverie.engine`; new projects should use only `reverie_engine`.

This runtime is designed for `Reverie-Gamer` workflows that need:

- a first-party project skeleton
- data-driven scenes and prefabs
- deterministic smoke validation
- content, telemetry, and playtest structure
- an integrated modeling pipeline for authored assets

## Standard Project Layout

The built-in engine now seeds a project with these key areas:

- `data/config/engine.yaml`: runtime, capability, Live2D, and modeling settings
- `data/scenes/` and `data/prefabs/`: engine-authored content
- `data/content/`: gameplay data
- `data/live2d/`: Live2D manifests
- `data/models/`: modeling pipeline manifest plus generated model registry
- `assets/models/source/`: authoring files such as `.bbmodel` and `.blend`
- `assets/models/source/blender/`: generated Blender plans and Python authoring scripts
- `assets/models/runtime/`: runtime exports such as `.glb` or `.gltf`
- `playtest/renders/models/`: previews or review renders

## Canonical Commands

Use the CLI or in-chat tools around these core flows:

- `/engine create`
- `/engine profile`
- `/engine validate`
- `/engine smoke`
- `/engine video`
- `/engine renpy`
- `/engine health`
- `/engine package`
- `/modeling setup`
- `/modeling sync`
- `/modeling primitive`
- `/modeling ashfox validate`
- `/blender status`
- `/blender create`

## Runtime Authoring Model

The built-in engine is data-driven:

- scenes use `.relscene.json`
- prefabs use `.relprefab.json`
- content data is YAML or JSON
- model assets are tracked through `data/models/model_registry.yaml`

The main Reverie executable does not embed full desktop DCC/editor applications by default. The official Blender plugin can embed Blender Portable inside `reverie-blender.exe` and unpack it into `.reverie/plugins/blender/runtime/` on demand; Godot and O3DE plugins manage releases, source checkouts, and SDK metadata under `.reverie/plugins/<plugin-id>/runtime/` and `.reverie/plugins/<plugin-id>/source/`. Blender authoring is handled by the built-in `blender_modeling_workbench` tool through background `bpy` scripts, while Blockbench authoring remains available through the built-in Ashfox MCP integration when that optional editor/plugin pair is running.

## Modeling Integration

The engine's modeling layer is documented separately in [Reverie-Gamer Modeling Guide](./reverie_gamer_modeling_pipeline.md).

In short:

1. Author source files in `assets/models/source/`
2. Export runtime assets into `assets/models/runtime/`
3. Sync the generated registry
4. Validate the pipeline before playtest or packaging

For quick generated starter assets, `/modeling primitive` can create a built-in runtime `.gltf` plus preview image directly into the standard project layout. For richer authored assets, `/blender create <model_name> <brief>` generates a `.blend` source, `.glb` runtime export, preview render, audit evidence, and optional repair loop without configuring an external MCP server.

## Galgame And Plugin Boundaries

The built-in engine keeps only lightweight, reusable runtime surfaces:

- first-party scene/prefab/project scaffolding
- smoke validation and playtest telemetry
- lightweight Live2D bridge files that consume already-deployed Cubism Core
- frame sequences, `gif`, or `mp4` playblasts through `/engine video`

When `ffmpeg` is available at build time, the packaged executable embeds it so encoded video export works out of the box. If `ffmpeg` is not bundled, frame-sequence export still works and encoded video falls back to an external runtime install.

Specialized Galgame work is owned by plugins:

- `plugins/renpy/`: Ren'Py-specific `.rpy` script inspection, engine workflow guidance, and future lint/package/runtime commands.
- `plugins/live2d/`: Cubism Core deployment, Live2D manifest inspection, dynamic CG guidance, and future MCP-style model control helpers.

The legacy `/engine renpy` importer remains a compatibility path for a practical Ren'Py subset, but full Ren'Py engine support should be delivered through the Ren'Py plugin rather than expanded inside the core CLI.

## Roadmap

Future game-development work should prioritize:

1. Build packaged `reverie-renpy.exe` and `reverie-live2d.exe` plugin releases and install them into `dist/.reverie/plugins/`.
2. Add plugin-local Ren'Py runtime deployment, lint, launch, packaging, and project-template commands.
3. Extend the Live2D plugin with MCP-compatible expression, motion, lip-sync, and scene-command bridges inspired by open Live2D MCP projects.
4. Keep Reverie-Gamer's prompt work focused on game concept quality, routes, system design, asset contracts, and verification plans.
5. Add Galgame-focused smoke projects that combine TTI backgrounds/still CG, optional TTV inserts, and Live2D interactive character manifests.
6. Keep public imports consolidated on `reverie.engine` and avoid reintroducing legacy runtime aliases.

## Verification Expectations

When content changes in a Reverie Engine project, the preferred baseline is:

1. `/engine validate`
2. `/engine smoke`
3. `/modeling sync` if model content changed
4. `/engine renpy` if dialogue content came from a `.rpy` source
5. `/blender validate <script_path>` when reviewing generated or edited Blender scripts
6. `/modeling ashfox validate` when using the live Ashfox MCP workflow

That keeps the engine layout, content registry, and active model-authoring workflow in sync.
