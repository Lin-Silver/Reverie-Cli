# Reverie CLI

Reverie CLI is a context-engine-powered AI coding assistant for large repositories. It combines repository indexing, multi-provider model routing, session memory, checkpoints, rollback tools, and a rich terminal UI so the agent can work against the real codebase instead of guessing.

## Highlights

- Context Engine for symbol lookup, dependency tracking, semantic retrieval, commit-history learning, and workspace memory
- Multiple operating modes for different workflows: `Reverie`, `Reverie-Atlas`, `Reverie-Gamer`, `Reverie-Ant`, `Spec-Driven`, `Spec-Vibe`, `Writer`, and `Computer Controller`
- Provider integrations for standard OpenAI-compatible models plus `iFlow`, `Qwen Code`, `Gemini CLI`, `Codex`, and `NVIDIA`
- Rich CLI/TUI with selectors, streaming output, help browser, status panels, session browsing, checkpoint rollback, and command discovery
- Workspace-aware safety model for file access, archive extraction, and audited command execution
- Built-in game-production tooling, `Reverie Engine` runtime workflows, and optional text-to-image generation

## Installation

Python `3.10` to `3.14` is supported. `3.10` or `3.11` is the safest default for local development.

```bash
git clone https://github.com/raiden/reverie-cli.git
cd reverie-cli

python -m venv .venv
.venv\Scripts\activate

pip install -e .
```

Optional extras:

```bash
pip install -e ".[dev]"
pip install -e ".[treesitter]"
pip install -r requirements-tti.txt
```

## Quick Start

```bash
reverie
reverie /path/to/project
reverie --index-only
reverie --no-index
reverie --version
```

On first run, configure at least one model source. Reverie can use:

- Standard OpenAI-compatible endpoints stored in `models`
- `iFlow`
- `Qwen Code`
- `Gemini CLI`
- `Codex`
- `NVIDIA` for `Computer Controller`

## Core Capabilities

### Context and Retrieval

- Full-project indexing with symbols, dependencies, and semantic retrieval
- Workspace memory summaries across sessions
- Git-aware retrieval and commit-history learning
- Incremental project-aware context selection to reduce hallucinations

### Workflow Modes

- `Reverie`: general-purpose software delivery
- `Reverie-Atlas`: research-first, document-driven implementation for complex systems
- `Reverie-Gamer`: game design, scaffolding, playtest, asset, and balance workflows
- `Reverie-Ant`: structured planning, execution, and verification
- `Spec-Driven` / `Spec-Vibe`: spec-heavy or lighter spec workflows
- `Writer`: writing and long-form documentation
- `Computer Controller`: NVIDIA-backed desktop control

### Operator Experience

- Interactive `/help` browser and per-command detail pages
- Model, settings, session, and checkpoint selectors
- Session persistence, rollback, undo, redo, and operation history
- Workspace-local cleanup with `/clean`
- Optional `/tti` image generation

## Configuration and Storage

Reverie stores runtime state next to the CLI executable. When you run from source, `app_root` is the repository root. In packaged Windows builds, `app_root` is the folder containing `reverie.exe`.

For each workspace Reverie creates a project cache under:

- Project cache root: `<app_root>/.reverie/project_caches/<project-key>/`
- Default profile: `<app_root>/.reverie/project_caches/<project-key>/config.global.json`
- Workspace profile: `<app_root>/.reverie/project_caches/<project-key>/config.json`
- Rules file: `<app_root>/.reverie/project_caches/<project-key>/rules.txt`
- Common runtime data: `context_cache/`, `sessions/`, `archives/`, `checkpoints/`, `specs/`, `steering/`, `security/`

`<project-key>` is derived from the absolute project path plus a short hash so different workspaces stay isolated.

`config.global.json` is the default profile used when workspace mode is off. `config.json` is the workspace-specific profile used when workspace mode is on.

Legacy `.reverie/config.json` and `rules.txt` files are still read once for migration when present, but new writes stay inside `.reverie/project_caches`.

Useful commands:

```text
/workspace
/workspace enable
/workspace disable
/workspace copy-to-workspace
/workspace copy-to-global
```

For the full configuration schema, provider notes, and text-to-image examples, see [docs/CONFIGURATION.md](docs/CONFIGURATION.md).

## Command Overview

Common commands:

| Command | Purpose |
| --- | --- |
| `/help` | Browse the live command catalog |
| `/status` | Show active model, source, session, and health |
| `/model` | Manage standard model presets |
| `/mode` | Show or switch operating modes |
| `/codex` | Activate Codex and choose model/reasoning |
| `/search <query>` | Run a web search |
| `/index` | Rebuild the workspace index |
| `/tools` | List tools visible in the current mode |
| `/sessions` | Browse sessions |
| `/rollback` | Restore earlier checkpoints or interaction states |
| `/checkpoints` | Open the checkpoint browser |
| `/clean` | Clear current-workspace memory, cache, and audit data |
| `/tti ...` | Manage TTI models or generate an image |

For the full reference, see [docs/CLI_COMMANDS.md](docs/CLI_COMMANDS.md).

## Documentation Map

- [Documentation Index](docs/README.md)
- [Chinese README](docs/README.zh-CN.md)
- [Configuration Guide](docs/CONFIGURATION.md)
- [CLI Command Reference](docs/CLI_COMMANDS.md)
- [Development Guide](docs/DEVELOPMENT.md)
- [Reverie Engine User Guide](docs/engine/reverie_engine_user_guide.md)
- [Change Log](changelog.md)

## Architecture Snapshot

```text
reverie/
|-- __main__.py              # CLI entry point
|-- config.py                # config loading, migration, model source state
|-- modes.py                 # mode registry and aliases
|-- atlas.py                 # Atlas mode config and rules
|-- codex.py                 # Codex provider integration
|-- agent/                   # agent prompts, tool execution, orchestration
|-- cli/                     # command handling, TUI, display helpers
|-- context_engine/          # indexing, retrieval, semantic analysis, graph data
|-- session/                 # sessions, checkpoints, rollback, archives, memory
|-- tools/                   # tool implementations exposed to the agent
|-- engine_lite/             # built-in runtime and engine workflows
|-- writer/                  # writer mode helpers
`-- tests/                   # regression coverage
```

## Development

```bash
pip install -e ".[dev]"
pytest
mypy reverie
black reverie tests
```

Windows executable packaging is handled by `build.bat`:

```bat
.\build.bat
.\build.bat --recreate-venv
```

## Notes

- `requirements-tti.txt` is intentionally separate because text-to-image has heavier optional dependencies.
- `docs/engine/reverie_engine_user_guide.md` covers the built-in runtime workflow surfaced through `/engine`.
- The live command catalog in `reverie/cli/help_catalog.py` is the source of truth for command descriptions and examples.
- The Chinese companion overview lives in [docs/README.zh-CN.md](docs/README.zh-CN.md).

## License

This repository is documented as MIT-licensed by the project author. If you distribute the project externally, add the final license file that matches your intended terms.
