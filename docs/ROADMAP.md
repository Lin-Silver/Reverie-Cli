# Reverie CLI Roadmap

This is the single source of truth for planned product work. Current behavior belongs in the relevant guide; completed work belongs in the changelog.

## Current Baseline

Reverie CLI provides a multi-provider coding agent, Context Engine retrieval and memory, sessions and rollback, scoped managed SubAgents, explicit handoff and recovery surfaces, desktop control, Writer workflows, runtime plugins, cross-platform CI, and packaged SDK bridge verification.

Reverie Engine supports deterministic headless gameplay execution, scene and component data, physics queries, navigation, input, animation, UI state, localization, save data, telemetry, video export, and a ModernGL off-screen renderer with reusable mesh resources, basic textures, blending, framebuffer readback, and PNG capture.

## Desktop Coding Workflow and UI/UX

Product decision: 2026-09-30. The detailed specification is [Reverie CLI feature additions](REVERIE_CLI_FEATURE_ADDITIONS_2026-09-30.md); it defines the default implementation scope S01–S21, UI states, dependencies, acceptance checks, and a complete mapping from the [Codex gap analysis](CODEX_GAP_ANALYSIS_2026-09-29.md). The [implementation prompt](REVERIE_CLI_IMPLEMENTATION_PROMPT_2026-09-30.md) is the handoff for a new coding chat.

- R1 — Input and execution control: deliver the shared desktop shell, independent structured drafts/attachments, image paste and preview, explicit queue/steer/stop, workspace result isolation, sidebar states, and accurate approval scope.
- R2 — Single-repository review and publication: deliver full Git diffs, file/hunk staging and revert, commit/ordinary push, branch preflight, line feedback/read-only review, and local artifact previews.
- R3 — Validation and long-running feedback: deliver a session-bound terminal, project actions, run records/recovery, lightweight plan/goal controls, notifications, and effective plugin/skill/connection states.
- R4 — Local parallel work: deliver managed local worktrees and independent session executors together with checkout write coordination and correctly routed events/approvals.

Each feature requires its working UI/UX and real runtime evidence before completion. Existing customizable message names, branch selection, file drops, and text drafts are the baseline to extend. Conditional items T01–T05 and deferred items X01–X08 in the specification are excluded from the default scope. In particular, no Local/Cloud selector or hosted cloud service is planned in this track. This desktop track does not change the Engine priorities below.

Implementation update, 2026-09-30: S01–S21 now have code and UI entry points across R1–R4. All stages have Windows packaged runtime evidence. Completion remains conditional for the model/authorization/native-IME checks listed in the [implementation and acceptance report](REVERIE_CLI_IMPLEMENTATION_REPORT_2026-09-30.md); code implementation, interface delivery, passed checks and missing evidence are tracked separately there. No project commit or push was performed.

Validation update, 2026-10-01: the user authorized local submission after deeper checks. Photo preview focus/resolution, failed-card controls, queued workspace ownership, draft isolation, model capability identity, loopback transport, and sent-photo transcript previews were corrected. Final build, runtime screenshots, test results and remaining service/IME evidence are recorded in the [deep validation report](REVERIE_CLI_DEEP_VALIDATION_2026-10-01.md). No push was requested.

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

## Maintenance Rules

- Keep public engine imports consolidated under `reverie.engine`.
- Add planned game/runtime work only to this file; do not place project roadmaps in code comments or feature guides.
- Remove completed items from this file in the same change that records them under the changelog's unreleased section.
- Keep capability reports conservative: `implemented`, `available`, and `production-ready` are different states.
