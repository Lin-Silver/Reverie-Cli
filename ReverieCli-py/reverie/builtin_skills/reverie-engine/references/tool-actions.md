# Reverie Engine actions

Use one action at a time and inspect `success`, `error`, and returned evidence before continuing.

## Plan and inspect

- `list_capabilities`: Read the current modules, supported dimensions, and game-family catalog.
- `assess_scope`: Check dimension, genre, quality tier, and world structure. Stop or reduce scope when it rejects AAA/3A or 3D open-world production.
- `inspect_project`: Summarize scenes, prefabs, content, models, capabilities, and validation.
- `project_health`: Produce a scored validation report; set `include_smoke=true` for runtime evidence.

## Create and author

- `create_project`: Create the canonical Reverie Engine layout. Supply `project_name`, `dimension`, `genre`, and optionally `sample_name`.
- `materialize_sample`: Add a supported playable sample without changing runtime family.
- `generate_scene`, `generate_prefab`, `generate_archetype`: Persist complete authoring payloads.
- `author_scene_blueprint`, `author_prefab_blueprint`: Draft a payload; provide a target path to persist it.
- `validate_authoring_payload`: Validate scene, prefab, archetype, engine config, gameplay manifest, or project data before use.

## Migrate built-in legacy sources

- `inspect_legacy_project`: Detect Godot, O3DE, or Ren'Py and report portable assets plus manual-review boundaries.
- `migrate_legacy_project`: Convert into one Reverie Engine project. Godot `.tscn` nodes become Reverie scenes, GDScript becomes behavior contracts, and O3DE Project/Gem/Registry data becomes project contracts and archetypes.
- `inspect_renpy`, `outline_renpy`, `validate_renpy`: Analyze Ren'Py locally without MCP.
- `import_renpy`: Convert supported dialogue into Reverie conversation data and optionally autostart it.

Never emit a new Godot or O3DE runtime workspace. Preserve unsupported native script semantics in migration contracts and report them for review.

## Verify and deliver

- `run_smoke`: Execute the deterministic headless runtime and persist telemetry.
- `validate_project`: Check required paths, schemas, runtime assets, and project contracts.
- `benchmark_project`: Measure scene instantiation and AI authoring latency.
- `export_video`: Capture a playblast or frame sequence; do not treat it as gameplay validation.
- `package_project`: Package only after validation and smoke evidence pass.

Minimum completion sequence: `validate_project` → `run_smoke` → relevant Gamer quality gates → `project_health` → `package_project`.
