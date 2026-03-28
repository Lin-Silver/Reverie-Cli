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
- `assets/models/source/`: authoring files such as `.bbmodel`
- `assets/models/runtime/`: runtime exports such as `.glb` or `.gltf`
- `playtest/renders/models/`: previews or review renders

## Canonical Commands

Use the CLI or in-chat tools around these core flows:

- `/engine create`
- `/engine profile`
- `/engine validate`
- `/engine smoke`
- `/engine health`
- `/engine package`
- `/modeling setup`
- `/modeling sync`
- `/modeling ashfox validate`

## Runtime Authoring Model

The built-in engine is data-driven:

- scenes use `.relscene.json`
- prefabs use `.relprefab.json`
- content data is YAML or JSON
- model assets are tracked through `data/models/model_registry.yaml`

The runtime does not vendor the Blockbench editor itself.
Instead, Reverie-Gamer ships the modeling workflow directly in the CLI, exposes Ashfox MCP as a built-in Gamer-only integration, and only leaves Blockbench desktop plus the Ashfox plugin as manual external installs.

## Modeling Integration

The engine's modeling layer is documented separately in [Reverie-Gamer Modeling Guide](./reverie_gamer_modeling_pipeline.md).

In short:

1. Author source files in `assets/models/source/`
2. Export runtime assets into `assets/models/runtime/`
3. Sync the generated registry
4. Validate the pipeline before playtest or packaging

## Verification Expectations

When content changes in a Reverie Engine project, the preferred baseline is:

1. `/engine validate`
2. `/engine smoke`
3. `/modeling sync` if model content changed
4. `/modeling ashfox validate` when using the live Ashfox MCP workflow

That keeps the engine layout, content registry, and active model-authoring workflow in sync.
