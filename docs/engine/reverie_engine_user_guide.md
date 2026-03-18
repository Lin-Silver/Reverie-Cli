# Reverie Engine User Guide

## Overview

Reverie Engine is the built-in runtime that powers `reverie_engine` and the compatibility alias `reverie_engine_lite`.
It is designed for AI-assisted project generation, deterministic smoke testing, data-driven gameplay authoring, and lightweight packaging inside Reverie CLI.

## Runtime Architecture

The runtime is split into clear services so AI and human authors can modify projects in structured layers:

- `scene.py`
  - Scene tree, node lifecycle, deferred calls, notifications, groups, timers, scene switching.
- `serialization.py`
  - `.relscene.json`, `.relprefab.json`, packed scenes, archetypes, overrides, migrations.
- `resources.py`
  - Resource loading, cache control, remaps, dependency graphs.
- `rendering.py`
  - Headless-friendly rendering server model for 2D, 2.5D, 3D, and UI extraction.
- `physics.py`
  - Query and simulation helpers for raycasts, overlaps, motion, and collision masks.
- `navigation.py`
  - Waypoint, grid, and tower-defense lane navigation.
- `animation.py`
  - Tracks, clips, timelines, cutscenes, and generic state machines.
- `systems.py`
  - Narrative flow, quests, counters, tower-defense logic, and shared gameplay state.
- `ui.py`
  - Control-style layout solving and gameplay-bound HUD/dialogue widgets.
- `live2d.py`
  - Live2D manifest validation, runtime bundle generation, bridge page output, SDK wiring.
- `audio.py`
  - Stream loading, bus routing, mixer snapshots, category volumes, mute/solo/send controls.
- `save_data.py`
  - Scene and gameplay snapshot capture plus slot-based persistence.
- `localization.py`
  - Locale table loading and `loc:` key resolution.
- `benchmarking.py`
  - Scene instantiation and AI authoring baseline measurements.

## Content Model

Reverie Engine favors structured content over handwritten runtime glue:

- `data/config/engine.yaml`
  - Engine profile, runtime defaults, modules, capabilities, Live2D config.
- `data/content/gameplay_manifest.yaml`
  - High-level gameplay system switches and economy defaults.
- `data/scenes/*.relscene.json`
  - Scene definitions.
- `data/prefabs/*.relprefab.json`
  - Reusable node hierarchies.
- `data/prefabs/*.relarchetype.json`
  - Reusable entity blueprints for AI authoring and runtime generation.
- `data/live2d/models.yaml`
  - Live2D manifest and model registration.
- `data/localization/*.yaml`
  - Locale tables.

## CLI Workflow

Use the direct `/engine` command family for the full built-in workflow:

- `/engine profile`
  - Inspect current project config, capabilities, counts, and validation state.
- `/engine create`
  - Scaffold a new engine project.
- `/engine sample <sample_name>`
  - Materialize a bundled template such as `2d_platformer`, `topdown_action`, `iso_adventure`, `3d_arena`, `galgame_live2d`, or `tower_defense`.
- `/engine run`
  - Run the entry scene and emit a session log.
- `/engine validate`
  - Validate structure plus engine/gameplay schemas.
- `/engine smoke`
  - Run a deterministic smoke path with telemetry output.
- `/engine health`
  - Produce a health report with score, status, and recommendations.
- `/engine benchmark`
  - Record baseline scene instantiation and AI authoring latency.
- `/engine package`
  - Produce a portable runtime package zip with manifest and validated project data.
- `/engine test`
  - Validate then smoke-test in one command.

## AI Authoring Workflow

The engine tool exposes structured actions for AI-assisted generation:

- `author_scene_blueprint`
  - Build a scene payload without immediately committing to disk.
- `author_prefab_blueprint`
  - Build a reusable prefab payload.
- `generate_scene`
  - Save a scene payload as `.relscene.json`.
- `generate_prefab`
  - Save a prefab payload as `.relprefab.json`.
- `generate_archetype`
  - Save a reusable archetype document.
- `validate_authoring_payload`
  - Validate scene, prefab, archetype, config, manifest, or full project data.

This makes it possible for Reverie mode to decompose a large game request into many small, verifiable authoring steps instead of one opaque generation pass.

## Supported Game Styles

The current Lite runtime is designed to cover these project classes:

- 2D platformers
- top-down action games
- 2.5D exploration projects
- 3D arena or third-person prototypes
- galgame / visual novel projects
- tower-defense projects

The runtime also includes reusable building blocks that can be recombined for hybrid genres.

## Live2D Workflow

Place models under `assets/live2d/` and register them in `data/live2d/models.yaml`.
The engine will:

- validate model references and related assets
- generate `web/live2d_bridge.html`
- generate `web/live2d_bridge.runtime.json`
- copy the bundled SDK from `reverie/engine_lite/vendor/live2d/live2dcubismcore.min.js` into `web/vendor/live2d/`

## Packaging and Delivery

The Lite runtime is optimized for internal delivery, iteration, and reference implementation work:

- health reporting helps quickly judge whether a project is stable enough to hand off
- packaging creates a focused runtime bundle zip instead of archiving the entire repository
- benchmarking establishes coarse but repeatable baselines for future regression checks

## Recommended Transition Plan

This Lite runtime is the final built-in iteration before the dedicated Reverie Engine SDK line.
Use it to:

1. validate game concepts quickly
2. exercise AI authoring flows
3. collect content conventions and telemetry patterns
4. define which systems should graduate into the standalone SDK
