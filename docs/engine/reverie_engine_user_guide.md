# Reverie Engine User Guide

## Overview

`reverie_engine` is Reverie CLI's canonical built-in runtime surface.
`reverie_engine_lite` remains available as a compatibility alias, but both names point to the same implementation.

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

## Ren'Py And Video Integration

The same built-in engine surface now also supports:

- importing a practical Ren'Py subset through `/engine renpy`
- exporting frame sequences, `gif`, or `mp4` playblasts through `/engine video`
- packaging those capabilities into the Windows one-file `reverie.exe`

When `ffmpeg` is available at build time, the packaged executable embeds it so encoded video export works out of the box. If `ffmpeg` is not bundled, frame-sequence export still works and encoded video falls back to an external runtime install.

## Verification Expectations

When content changes in a Reverie Engine project, the preferred baseline is:

1. `/engine validate`
2. `/engine smoke`
3. `/modeling sync` if model content changed
4. `/engine renpy` if dialogue content came from a `.rpy` source
5. `/blender validate <script_path>` when reviewing generated or edited Blender scripts
6. `/modeling ashfox validate` when using the live Ashfox MCP workflow

That keeps the engine layout, content registry, and active model-authoring workflow in sync.
