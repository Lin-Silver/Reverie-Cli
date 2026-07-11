# Reverie CLI Roadmap

This is the single source of truth for planned product work. Current behavior belongs in the relevant guide; completed work belongs in the changelog.

## Current Baseline

Reverie CLI provides a multi-provider coding agent, Context Engine retrieval and memory, sessions and rollback, managed SubAgents, desktop control, Writer workflows, runtime plugins, and the work-in-progress Reverie-Gamer production pipeline.

Reverie Engine supports deterministic headless gameplay execution, scene and component data, physics queries, navigation, input, animation, UI state, localization, save data, telemetry, video export, and a ModernGL off-screen renderer with reusable mesh resources, basic textures, blending, framebuffer readback, and PNG capture.

## Priority 1: Runtime Presentation

- Add a desktop window and event loop over the verified framebuffer renderer.
- Connect resize, keyboard, pointer, focus, and close events to the engine input lifecycle.
- Add presentation smoke tests on supported Windows and Linux runners.
- Preserve explicit headless fallback diagnostics when a graphics context cannot start.

Completion means a generated sample can launch, accept input, render frames, resize, and shut down cleanly outside the test harness.

## Priority 2: Rendering, Audio, and Live2D

- Add lighting, normal/ORM materials, shadows, skeletal GPU skinning, batching, post-processing, and asset streaming in measured increments.
- Add real-device audio integration tests, spatial playback, and a defined effects/bus processing contract.
- Add verified Live2D expression, motion, lip-sync, and scene-command execution; keep browser-bridge readiness distinct from native rendering readiness.
- Add resource lifetime and long-run leak tests for graphics, audio, and media backends.

Completion requires runtime evidence from actual backend devices, not dependency imports or manifest validation alone.

## Priority 3: Reverie-Gamer Production Depth

- Extend deterministic vertical slices into multi-milestone playtests with progression, region transitions, save migration, and repeatable performance budgets.
- Improve generated asset review gates without presenting procedural candidates as final production art.
- Expand supported migration coverage while keeping unsupported native scripts and scene semantics visible for manual review.
- Add Galgame samples combining dialogue, generated media, save/load, and Live2D character manifests.

AAA/3A production and unrestricted 3D open worlds remain outside the supported scope until the runtime and evidence gates above are complete.

## Priority 4: Agent Harness and Isolation

- Add optional isolated worktree-style execution lanes for risky or long-running repository changes.
- Add explicit context refresh and handoff transitions for long sessions.
- Turn recovery playbooks for failing tests, partial edits, and tool-schema mismatches into safe, action-ready workflows.
- Expand end-to-end release checks for packaged desktop control, SubAgents, browser control, plugins, and provider transports.

Completion means recovery and isolation are enforced by runtime behavior and verified workflows rather than prompt guidance alone.

## Maintenance Rules

- Keep public engine imports consolidated under `reverie.engine`.
- Add planned work only to this file; do not place project roadmaps in code comments or feature guides.
- Remove completed items from this file in the same change that records them under the changelog's unreleased section.
- Keep capability reports conservative: `implemented`, `available`, and `production-ready` are different states.
