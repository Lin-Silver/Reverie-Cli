---
name: reverie-engine
description: Build, migrate, inspect, validate, smoke-test, benchmark, and package games with the unified built-in Reverie Engine. Use in Reverie-Gamer mode for 2D, 2.5D, focused 3D, visual-novel, gameplay-system, scene/prefab, legacy Godot/O3DE/Ren'Py migration, or prompt-to-playable game work; exclude AAA/3A and 3D open-world production.
---

# Reverie Engine

Use `reverie_engine` as the only runtime target. Treat Godot and O3DE code as architecture references or migration inputs, and treat Ren'Py scripts as importable content. Never create a parallel Godot/O3DE runtime workspace for a new project.

## Execute the workflow

1. Inspect the repository and existing artifacts before changing files.
2. Call `reverie_engine(action="assess_scope")` for ambitious, 3D, open-world, or AAA-like requests. Reduce unsupported requests to a focused AA-or-smaller prototype or vertical slice.
3. Compile the durable request and production plan with `game_design_orchestrator`; keep `artifacts/game_request.json`, `artifacts/game_blueprint.json`, and the runtime artifacts current.
4. Create or upgrade the project with `game_project_scaffolder`, then use `reverie_engine` for scenes, prefabs, archetypes, authoring payloads, and runtime operations.
5. Run the generated genre rule profile and smoke input before adding project-local runtime code. Extend `data/content/rules.yaml` for additional loop actions instead of replacing the unified engine bootstrap.
6. Keep gameplay data under `data/`, source assets under `assets/models/source/`, runtime assets under `assets/models/runtime/`, and generated evidence under `playtest/`.
7. Run focused validation, deterministic smoke execution, project health, and relevant playtest gates. Do not claim playability from generated files alone.

Read [tool-actions.md](references/tool-actions.md) when choosing an engine action or migration path.

## Migrate legacy projects

1. Call `reverie_engine(action="inspect_legacy_project", source_dir=...)`.
2. Review the detected source, portable assets, and manual-review list.
3. Call `reverie_engine(action="migrate_legacy_project", source_dir=..., output_dir=...)`.
4. Rewrite unsupported native scripts or scene semantics as Reverie Engine components and data contracts.
5. Validate and smoke-test the resulting Reverie Engine project.

For Ren'Py, use `inspect_renpy`, `outline_renpy`, and `validate_renpy` before `import_renpy` or full migration. Use an optional external Ren'Py SDK plugin only for native lint, compile, or distribution checks.

## Author assets

Use `blender_modeling_workbench` for auditable Blender authoring jobs and the Blender runtime plugin for execution. Validate exported GLB/glTF files, refresh the model registry, and keep Blender source files separate from runtime exports.

## Preserve boundaries

- Reject AAA/3A production and 3D open-world delivery as unsupported engine scope.
- Prefer the smallest complete game loop over broad placeholder systems.
- Keep Godot/O3DE names out of selected-runtime fields; record them only as heritage or migration sources.
- Record deferred work and failed verification explicitly.
