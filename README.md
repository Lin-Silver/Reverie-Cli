# Reverie CLI

Reverie CLI is a context-engine-powered AI coding assistant for large repositories. It combines repository indexing, multi-provider model routing, session memory, checkpoints, rollback tools, and a rich terminal UI so the agent can work against the real codebase instead of guessing.

## Highlights

- **Context Engine** — shared by every mode for symbol lookup, dependency tracking, semantic retrieval, commit-history learning, and workspace memory
- **Multiple Workflow Modes** — `Reverie`, `Reverie-Atlas`, `Reverie-Gamer`, `Reverie-Ant`, `Spec-Driven`, `Spec-Vibe`, `Writer`, `Computer Controller`
- **Multi-Provider** — standard OpenAI-compatible models plus `Qwen Code`, `Gemini CLI`, `Codex`, and `NVIDIA`
- **Rich TUI** — selectors, streaming output, help browser, status panels, session browsing, checkpoint rollback, command discovery
- **Workspace Safety** — file-access sandboxing, audited command execution, archive extraction hardening
- **Game Tooling** — built-in `Reverie Engine` runtime, Reverie-Gamer design/playtest workflows, and a built-in Ashfox MCP modeling flow that works with manual Blockbench + Ashfox plugin installs

## Installation

Python `3.10` to `3.14` is supported. `3.10` or `3.11` is the safest default for local development.

```bash
git clone https://github.com/Lin-Silver/Reverie-Cli.git
cd reverie-cli

python -m venv .venv
.venv\Scripts\activate

pip install -e .
```

Optional extras:

```bash
pip install -e ".[dev]"          # development tools (pytest, mypy, black)
pip install -e ".[treesitter]"   # tree-sitter language support
pip install -r requirements-tti.txt  # text-to-image dependencies
```

## Quick Start

```bash
reverie                      # launch in current directory
reverie /path/to/project     # launch targeting a specific project
reverie --index-only         # build index and exit
reverie --no-index           # skip indexing on startup
reverie --version            # print version
```

On first run, configure at least one model source. Reverie supports:

- Standard OpenAI-compatible endpoints (stored in `models`)
- `Qwen Code`, `Gemini CLI`, `Codex`, `NVIDIA`

Use `/model` to add presets or `/qwencode`, `/Geminicli`, `/codex`, `/nvidia` for provider-specific setup.

## Common Commands

| Command | Purpose |
| --- | --- |
| `/help` | Browse the live command catalog |
| `/status` | Show active model, source, session, and health |
| `/model` | Manage standard model presets |
| `/mode` | Show or switch operating modes |
| `/codex` | Activate Codex and choose model/reasoning |
| `/search <query>` | Run a web search |
| `/index` | Rebuild the workspace index |
| `/tools` | List tools visible to the active model/provider |
| `/sessions` | Browse sessions |
| `/rollback` | Restore earlier checkpoints or interaction states |
| `/clean` | Clear current-workspace memory, cache, and audit data |

For the full reference, see [docs/CLI_COMMANDS.md](docs/CLI_COMMANDS.md).

## Workflow Modes

| Mode | Description |
| --- | --- |
| `Reverie` | General-purpose coding with the smallest useful toolset |
| `Reverie-Atlas` | Document-driven spec development for complex systems |
| `Reverie-Gamer` | Game design, scaffolding, playtest, asset, and balance workflows |
| `Reverie-Ant` | Structured long-running planning, execution, and verification |
| `Spec-Driven` | Spec authoring for requirements, design, and task breakdown |
| `Spec-Vibe` | Lighter spec implementation for approved plans |
| `Writer` | Creative writing and narrative continuity |
| `Computer Controller` | Pinned NVIDIA desktop autopilot through `computer_control` |

## Architecture

```text
reverie/
├── __main__.py              # CLI entry point
├── config.py                # config loading, migration, model source state
├── modes.py                 # mode registry and aliases
├── atlas.py                 # Atlas mode config and rules
├── codex.py                 # Codex provider integration
├── agent/                   # agent prompts, tool execution, orchestration
├── cli/                     # command handling, TUI, display helpers
├── context_engine/          # indexing, retrieval, semantic analysis, graph data
├── session/                 # sessions, checkpoints, rollback, archives, memory
├── tools/                   # tool implementations exposed to the agent
├── engine/                  # canonical public built-in engine API
├── engine_lite/             # shared runtime, project, and modeling implementation
├── writer/                  # writer mode helpers
└── reverie/tests/           # regression coverage
```

## Development

```bash
pip install -e ".[dev]"
pytest
mypy reverie
black reverie
```

Windows executable packaging:

```bat
.\build.bat
.\build.bat --recreate-venv
```

## Documentation

- [Documentation Index](docs/README.md)
- [Chinese README / 中文 README](docs/README.zh-CN.md)
- [Configuration Guide](docs/CONFIGURATION.md)
- [CLI Command Reference](docs/CLI_COMMANDS.md)
- [Development Guide](docs/DEVELOPMENT.md)
- [Reverie Engine User Guide](docs/engine/reverie_engine_user_guide.md)
- [Reverie-Gamer Modeling Guide](docs/engine/reverie_gamer_modeling_pipeline.md)
- [Changelog](docs/changelog.md)

## License

This repository is documented as MIT-licensed by the project author. If you distribute the project externally, add the final license file that matches your intended terms.
