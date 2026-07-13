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

## Runtime Maturity

Reverie Engine is an alpha runtime. Its capability report deliberately separates declared APIs from paths that have runtime evidence:

| Surface | Current level |
| --- | --- |
| Scene graph, deterministic gameplay, physics queries, navigation, input, save data | Runtime implemented and covered by headless integration tests |
| Native rendering | ModernGL framebuffer rendering for primitive/custom meshes, transforms, flat or textured materials, depth, alpha/add/multiply blending, pixel readback, and PNG capture |
| Native presentation | Off-screen framebuffer only; a desktop window/event-loop presentation layer is not yet part of the engine |
| Audio | Pyglet decoding/playback when the host backend succeeds; status distinguishes installed, unverified, operational, and failed states |
| Live2D | Manifest validation, Cubism Core discovery, motion routing, and browser-bridge generation; no native Cubism renderer |
| Reverie-Gamer | Work in progress: project planning, generation, deterministic slice execution, and evidence gates are implemented, but this is not a general one-prompt production-game guarantee |

`/engine profile` exposes these distinctions under `capability_levels`. A dependency being importable is not treated as proof that a native device or external asset pipeline works.

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

The main Reverie executable does not embed full desktop DCC/editor applications by default. The official Blender plugin can embed Blender Portable inside `reverie-blender.exe` and unpack it into `.reverie/plugins/blender/runtime/` on demand. Blender authoring is handled by the built-in `blender_modeling_workbench` tool through background `bpy` scripts, while Blockbench authoring remains available through the built-in Ashfox MCP integration when that optional editor/plugin pair is running. Godot and O3DE are migration inputs and implementation references inside Reverie Engine; they no longer have release plugins.

## Modeling Integration

The engine's modeling layer is documented separately in [Reverie-Gamer Modeling Guide](./reverie_gamer_modeling_pipeline.md).

In short:

1. Author source files in `assets/models/source/`
2. Export runtime assets into `assets/models/runtime/`
3. Sync the generated registry
4. Validate the pipeline before playtest or packaging

For quick generated starter assets, `/modeling primitive` can create a built-in runtime `.gltf` plus preview image directly into the standard project layout. For richer authored assets, `/blender create <model_name> <brief>` generates a `.blend` source, `.glb` runtime export, preview render, audit evidence, and optional repair loop without configuring an external MCP server.

## Galgame And Migration Boundaries

The built-in engine keeps only lightweight, reusable runtime surfaces:

- first-party scene/prefab/project scaffolding
- smoke validation and playtest telemetry
- lightweight Live2D bridge files that consume already-deployed Cubism Core
- frame sequences, `gif`, or `mp4` playblasts through `/engine video`

When `ffmpeg` is available at build time, the packaged executable embeds it so encoded video export works out of the box. If `ffmpeg` is not bundled, frame-sequence export still works and encoded video falls back to an external runtime install.

Ren'Py analysis and migration are built into Reverie Engine:

- `reverie_engine`: `.rpy` project inspection, script outlines, parser validation, dialogue import, and full project migration.
- `plugins/renpy/`: optional external Ren'Py SDK management for native lint, compile, and distribution only.
- `plugins/live2d/`: Cubism Core deployment, Live2D manifest inspection, and dynamic CG guidance.

Godot and O3DE no longer ship as runtime plugins. Use `/engine inspect-legacy` and `/engine migrate` to move portable assets and supported content into one Reverie Engine project; native scripts and scene semantics remain explicit manual-review items.

## Playable Contract And Runtime Evidence

Every supported game family now seeds a deterministic stateful slice contract rather than a single isolated action. The smoke path starts an objective, performs a genre-specific challenge, grants a reward, completes the slice, writes and reads a real save slot, and records executed frames plus measured average frame time. Card games preserve their draw/play/victory sequence before the common completion step.

Reverie-Gamer evaluates the resulting smoke or playtest telemetry. A slice cannot score 70 or receive a credible/strong verdict unless evidence proves:

- a successful run with session start and end
- inspectable events with no failure event
- executed frames and frame timing within the target budget
- every requested combat, quest, reward, and save/load loop

Missing evidence caps the score at 69. Planning documents, packet counts, or declared tests cannot satisfy this runtime gate.

The production scope remains explicit: AAA/3A projects and 3D open-world games are unsupported. Passing the deterministic contract proves the generated foundation's tested loop; it does not certify final art, platform compliance, or subjective polish.

## Verification Expectations

When content changes in a Reverie Engine project, the preferred baseline is:

1. `/engine validate`
2. `/engine smoke`
3. `/modeling sync` if model content changed
4. `/engine renpy` if dialogue content came from a `.rpy` source
5. `/blender validate <script_path>` when reviewing generated or edited Blender scripts
6. `/modeling ashfox validate` when using the live Ashfox MCP workflow

That keeps the engine layout, content registry, and active model-authoring workflow in sync.

Planned runtime and Gamer work is maintained in the project [Roadmap](../ROADMAP.md).
