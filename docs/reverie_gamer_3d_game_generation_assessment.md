# Reverie-Gamer Upgrade Plan for Large 3D Game Production

## Direction

This document focuses on the next upgrade sequence for `Reverie-Gamer`.

The target experience is no longer just "generate a prototype scene." The next product goal is:

`one prompt -> game program -> runtime-aware project foundation -> playable 3D slice -> autonomous continuation -> staged expansion`

For large 3D action games in the class of open-world or hub-based action titles, the immediate upgrade path should be:

- use one prompt to initialize the project program, not only a scene scaffold
- generate a first verified slice quickly
- continue the same project across many follow-up production turns without losing structure
- turn Gamer into a long-running production director, not only a one-shot generator

## Current Foundation

The repository already has the right backbone for this upgrade:

- `reverie/gamer/prompt_compiler.py`: prompt-to-structured request compilation
- `reverie/gamer/scope_estimator.py`: scope reduction into a credible vertical slice
- `reverie/gamer/production_plan.py`: milestone and task-shape generation
- `reverie/gamer/runtime_registry.py`: runtime selection and capability routing
- `reverie/gamer/system_generators/`: combat, quest, progression, save/load, and world packets
- `reverie/gamer/asset_pipeline.py`: modeling and runtime asset seed generation
- `reverie/gamer/expansion_planner.py`: continuity, backlog, and resume-state artifacts
- `reverie/gamer/vertical_slice_builder.py`: playable slice scaffolding
- `reverie/gamer/verification/slice_score.py`: baseline quality scoring

This means the next step is not a rewrite. The next step is to turn the existing vertical-slice pipeline into a full production stack.

## Product Goal

`Reverie-Gamer` should evolve into a production operating system for long-running 3D game projects.

The upgraded experience should look like this:

1. The user gives one high-level prompt.
2. Gamer generates a structured game program with scope, pillars, runtime choice, art direction, combat direction, region plan, and milestone plan.
3. Gamer emits a verified first slice with runnable code, starter content, asset backlog, and test plan.
4. The same project can then be expanded through follow-up prompts like "add the second region", "build the first boss", or "upgrade traversal and camera feel" without losing continuity.
5. Validation, scoring, and continuation artifacts stay attached to the project root so the system can keep working over days or weeks.

## Upgrade Workstreams

### 1. Game Program Compiler

Upgrade the prompt compiler from request shaping into full game-program generation.

Add new artifacts:

- `artifacts/game_program.json`
- `artifacts/game_bible.md`
- `artifacts/feature_matrix.json`
- `artifacts/content_matrix.json`
- `artifacts/milestone_board.json`
- `artifacts/risk_register.json`

What this unlocks:

- a one-prompt request becomes a real production brief
- system generation can map back to explicit design pillars
- follow-up sessions can expand the same project without restating everything

Suggested new modules:

- `reverie/gamer/program_compiler.py`
- `reverie/gamer/milestone_planner.py`
- `reverie/gamer/content_lattice.py`

### 2. Runtime Capability Graph

Upgrade runtime selection from "which adapter fits" into a capability graph.

The runtime layer should record:

- combat capability profile
- world-streaming capability
- quest/cutscene capability
- asset-import path
- performance budget profile
- toolchain requirements and blockers

Suggested new artifacts:

- `artifacts/runtime_capability_graph.json`
- `artifacts/runtime_delivery_plan.json`

Suggested new modules:

- `reverie/gamer/runtime_capability_graph.py`
- `reverie/gamer/runtime_delivery.py`

### 3. Gameplay Systems Factory

Upgrade system packets into reusable gameplay factories.

The next generation should cover:

- traversal and locomotion variants
- camera and lock-on presets
- player ability graphs
- enemy archetype families
- encounter director grammars
- boss phase planners
- quest and region event directors

Suggested new modules:

- `reverie/gamer/system_generators/traversal.py`
- `reverie/gamer/system_generators/camera.py`
- `reverie/gamer/system_generators/abilities.py`
- `reverie/gamer/system_generators/boss_director.py`
- `reverie/gamer/system_generators/cutscene.py`

Suggested new tool actions:

- `game_design_orchestrator(action="compile_program")`
- `game_design_orchestrator(action="generate_gameplay_factory")`
- `game_design_orchestrator(action="plan_boss_arc")`

### 4. Asset and DCC Automation

The current modeling pipeline is a good seed, but it needs to become a real production lane.

Next upgrades:

- character kit generation
- environment kit generation
- placeholder rig and animation contracts
- material and VFX placeholder generation
- import profile validation per runtime
- stronger Blockbench and Ashfox round-trip flows

Suggested new artifacts:

- `artifacts/character_kits.json`
- `artifacts/environment_kits.json`
- `artifacts/animation_plan.json`
- `artifacts/asset_budget.json`

Suggested new modules:

- `reverie/gamer/character_factory.py`
- `reverie/gamer/environment_factory.py`
- `reverie/gamer/animation_pipeline.py`
- `reverie/gamer/asset_budgeting.py`

### 5. World and Content Expansion

Large-scale games need a persistent world/content expansion model, not only a starter region.

Next upgrades:

- multi-region assembly plans
- region kit templates
- NPC faction and relationship graphs
- questline chains across many sessions
- dungeon/event generation packs
- save-schema migration for ongoing projects

Suggested new artifacts:

- `artifacts/world_program.json`
- `artifacts/region_kits.json`
- `artifacts/faction_graph.json`
- `artifacts/questline_program.json`
- `artifacts/save_migration_plan.json`

Suggested new modules:

- `reverie/gamer/world_program.py`
- `reverie/gamer/region_expander.py`
- `reverie/gamer/faction_graph.py`
- `reverie/gamer/save_migration.py`

### 6. Validation and Autonomous Continuation

This is the most important upgrade for quality.

`Reverie-Gamer` should not stop at generation. It should generate, verify, score, repair, and continue.

Next upgrades:

- runtime smoke verification by subsystem
- navigation and traversal checks
- encounter sanity validation
- combat-feel scorecards
- performance-budget checks
- missing-asset detection
- continuation prompts generated from live project state

Suggested new artifacts:

- `playtest/quality_gates.json`
- `playtest/performance_budget.json`
- `playtest/combat_feel_report.json`
- `playtest/continuation_recommendations.md`

Suggested new modules:

- `reverie/gamer/verification/quality_gate_runner.py`
- `reverie/gamer/verification/perf_budget.py`
- `reverie/gamer/verification/combat_feel.py`
- `reverie/gamer/continuation_director.py`

## Mode and Tooling Upgrades

The next Gamer upgrade should also reshape the mode behavior itself.

### A. Multi-Phase Gamer Workflow

Within one Gamer run, the mode should explicitly progress through:

1. program compilation
2. runtime decision
3. slice plan
4. content and asset generation
5. runtime scaffold
6. validation
7. continuation proposal

### B. Gamer Should Create and Reuse Durable Artifacts

The mode should open and reuse existing artifacts before generating replacements.

Priority reopen order:

1. `artifacts/game_program.json`
2. `artifacts/milestone_board.json`
3. `artifacts/runtime_delivery_plan.json`
4. `artifacts/content_expansion.json`
5. `artifacts/asset_pipeline.json`
6. `artifacts/resume_state.json`
7. `playtest/slice_score.json`

### C. Gamer Needs More Specialized Tool Actions

Recommended additions:

- `game_design_orchestrator(action="expand_region")`
- `game_design_orchestrator(action="generate_character_kit")`
- `game_design_orchestrator(action="build_enemy_faction")`
- `game_project_scaffolder(action="upgrade_runtime_project")`
- `game_project_scaffolder(action="apply_system_packet")`
- `game_playtest_lab(action="run_quality_gates")`
- `game_playtest_lab(action="score_combat_feel")`
- `game_playtest_lab(action="plan_next_iteration")`

## Proposed Implementation Sequence

### Stage 1: Program Compiler and Artifact Upgrade

**Dates:** 2026-04-06 to 2026-04-13

Deliverables:

- introduce `game_program.json`, `game_bible.md`, and `milestone_board.json`
- extend `prompt_compiler` outputs into production-grade planning artifacts
- update Gamer prompts so one prompt creates the project program first

### Stage 2: Asset and Runtime Delivery Upgrade

**Dates:** 2026-04-13 to 2026-04-27

Deliverables:

- strengthen `asset_pipeline.json`
- add runtime delivery planning and capability graph outputs
- improve Blockbench/Ashfox round-trip automation
- add richer runtime import contracts for Godot and Reverie Engine

### Stage 3: Gameplay Factory Upgrade

**Dates:** 2026-04-27 to 2026-05-18

Deliverables:

- traversal, camera, abilities, boss, and encounter grammar generators
- higher-quality combat/quest/world packet composition
- better reusable subsystem templates for follow-up expansion

### Stage 4: World Expansion and Continuation

**Dates:** 2026-05-18 to 2026-06-15

Deliverables:

- multi-region expansion workflows
- faction graph and questline program outputs
- save migration planning
- stronger `resume_state` and continuation directives

### Stage 5: Validation and Production Readiness

**Dates:** 2026-06-15 to 2026-07-06

Deliverables:

- quality-gate runner
- performance-budget checks
- combat-feel reports
- automatic "next iteration" suggestions from current project state

## Success Criteria

The next major Gamer milestone should be considered successful when a single prompt can reliably produce:

- a structured game program
- a runtime-aware milestone plan
- a verified runnable 3D vertical slice
- a reusable asset/content backlog
- a continuation package that can grow the same project in later sessions

For the first milestone after this plan, the quality bar should be:

- one prompt produces all core artifacts without manual file bootstrapping
- the generated project passes built-in validation and smoke checks
- the generated slice score is stable enough to use as a baseline for later upgrades
- a second prompt such as "expand the next region" reuses prior artifacts instead of restarting from scratch

## Recommended Immediate Next PRs

If work begins now, the highest-value pull-request sequence is:

1. add `program_compiler.py` plus `game_program.json` and `milestone_board.json`
2. extend `game_design_orchestrator` with `compile_program`
3. add `runtime_capability_graph.json` and runtime delivery planning
4. upgrade asset pipeline outputs into character/environment/animation kits
5. add quality-gate execution beyond `slice_score.json`

## Bottom Line

The next upgrade for `Reverie-Gamer` is to turn it from a vertical-slice generator into a persistent large-project production director.

That path is already compatible with the current repository structure. The right move is to keep the existing prompt compiler, runtime registry, system generators, asset pipeline, expansion planner, and slice verification stack, then layer a game-program compiler, stronger asset/runtime automation, and autonomous validation on top of them.
