# Reverie CLI

Reverie CLI is a context-engine-powered AI coding assistant for large repositories. It combines repository indexing, multi-provider model routing, session memory, checkpoints, rollback tools, and a rich terminal UI so the agent can work against the real codebase instead of guessing.

## Highlights

- **Context Engine** - shared by every mode for symbol lookup, dependency tracking, semantic retrieval, commit-history learning, and project-isolated persistent memory
- **Multiple Workflow Modes** - `Reverie`, `Reverie-Atlas`, `Reverie-Gamer` (work in progress), `Reverie-Ant`, `Spec-Driven`, `Spec-Vibe`, `Writer`, `Computer Controller`
- **Multi-Provider** - standard OpenAI-compatible presets plus built-in `Codex`, `AIHubMix`, `Agnes`, `SenseNova`, `unlimited.surf`, `NVIDIA`, `ModelScope`, and `WebGemini`
- **Rich TUI** - selectors, streaming output, help browser, status panels, session browsing, checkpoint rollback, command discovery
- **Workspace Safety** - file-access sandboxing, audited command execution, archive extraction hardening
- **Game Tooling** - built-in `Reverie Engine` runtime, work-in-progress Reverie-Gamer prompt-to-vertical-slice workflow, Blender plugin-assisted authoring, Godot/O3DE migration patterns inside the unified engine, and a built-in Ashfox MCP bridge for optional Blockbench sessions

## Latest Update

Current stable repository version: `v2.3.4`.

- Reverie CLI now exposes a stable terminal core interface for future desktop hosts through direct one-line commands such as `reverie.exe setting status`.
- GitHub Release publishing now builds the Python `reverie.exe`, the official Blender and Game Models plugin executables, and `plugins-manifest.json` directly into the latest Release while deleting retired Godot/O3DE assets.
- Prompt mode, direct settings commands, plugin refresh, and long transcript handling were optimized for lower host overhead.

For the full release notes, see [docs/changelog.md](docs/changelog.md).

## Reverie-Gamer Focus

Reverie-Gamer is currently aimed at:

`one prompt -> structured request -> blueprint -> runtime-aware project foundation -> verified playable vertical slice -> iterative expansion`

Current priorities and completion gates live in the project [roadmap](docs/ROADMAP.md).

## Installation

Python `3.10` to `3.14` is supported. `3.10` or `3.11` is the safest default for local development.

```bash
git clone https://github.com/Lin-Silver/Reverie-Cli.git
cd reverie-cli
cd ReverieCli-py

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
reverie -p "fix failing tests"   # run one prompt non-interactively and exit
reverie --prompt-file task.md    # run a long prompt from a file
Get-Content task.md | reverie --prompt-stdin  # run a long prompt from stdin
reverie -p "fix failing tests" --report-file artifacts/prompt_report.json
reverie /path/to/project -p "add a health check" --mode reverie-atlas
reverie setting status       # run a CLI command directly without entering the TUI
reverie setting mode reverie # update configuration from one terminal command
reverie --version            # print version
```

`reverie -v` prints both the software version and the stable Core Interface version.
Future desktop hosts should use the direct command surface plus the `.reverie`
configuration directory instead of an embedded JSONL bridge.

`--report-file` writes structured JSON for prompt runs, including the final output, activity events, UI events, and a harness report that summarizes tasks, checkpoints, command audit evidence, verification posture, and recent run-history trends. Prompt-mode runs now also persist lightweight harness snapshots in the project cache so `/doctor` can show score and verification drift over time.

For long prompts, use `--prompt-file <path>`, pipe text with `--prompt-stdin`, or use the shorthand `-p @task.md` / `-p -`. Prompt files are decoded as UTF-8 first, then common locale encodings, with replacement fallback instead of aborting on invalid bytes.

For the packaged Windows build, the same one-shot flow works with `dist\reverie.exe -p "<task>"`. On Windows paths and executable names are case-insensitive, so `Reverie.exe -p "<task>"` works the same way.

On first run, configure at least one model source. Reverie supports:

- Standard OpenAI-compatible endpoints (stored in `models`)
- `Codex`, `NVIDIA`, `ModelScope`

Use `/model` to add presets or `/codex`, `/nvidia`, `/modelscope` for provider-specific setup.

## Common Commands

| Command | Purpose |
| --- | --- |
| `/help` | Browse the live command catalog |
| `/status` | Show active model, source, session, and health |
| `/doctor` | Audit the current workspace harness, including verification posture and recent run trends |
| `/model` | Manage standard model presets |
| `/mode` | Show or switch operating modes |
| `/codex` | Activate Codex and choose model/reasoning |
| `/modelscope` | Activate ModelScope and choose Anthropic-SDK-backed models |
| `/search <query>` | Run a web search |
| `/index` | Rebuild the workspace index |
| `/tools` | List tools visible to the active model/provider |
| `/tools all` | Show every loaded tool across modes with detailed parameters |
| `/plugins deploy <plugin-id>` | Prepare plugin-local runtimes or source SDKs under `.reverie/plugins/<plugin-id>/` |
| `/blender` | Create Blender scripts/assets through the built-in modeling workflow |
| `/sessions` | Browse sessions |
| `/rollback` | Restore earlier checkpoints or interaction states |
| `/clean` | Clear current-workspace memory, cache, and audit data |

For the full reference, see [docs/CLI_COMMANDS.md](docs/CLI_COMMANDS.md).

## Workflow Modes

| Mode | Description |
| --- | --- |
| `Reverie` | Full-spectrum Ultra Agentic execution for general software, automation, runtime, and repository work |
| `Reverie-Atlas` | Document-driven spec development for complex systems |
| `Reverie-Gamer` | Work-in-progress game-production mode for prompt-to-blueprint, runtime scaffolding, vertical-slice delivery, and verification |
| `Reverie-Ant` | Structured long-running planning, execution, and verification |
| `Spec-Driven` | Spec authoring for requirements, design, and task breakdown |
| `Spec-Vibe` | Lighter spec implementation for approved plans |
| `Writer` | Native long-form fiction workflow with disk-backed chapters, reader TXT exports, and continuity control |
| `Computer Controller` | Embedded Open Computer Use-compatible desktop runtime plus managed Reverie SubAgents; entered explicitly for desktop work and free to hand off when the task changes |

## Architecture

```text
reverie/
├── __main__.py              # CLI entry point
├── config.py                # config loading, migration, model source state
├── modes.py                 # mode registry and aliases
├── atlas.py                 # Atlas mode config and rules
├── codex.py                 # Codex provider integration
├── modelscope.py            # ModelScope provider integration
├── agent/                   # agent prompts, tool execution, orchestration
├── cli/                     # command handling, TUI, display helpers
├── context_engine/          # indexing, retrieval, semantic analysis, graph data
├── gamer/                   # Gamer production pipeline and runtime generation
│   ├── runtime_adapters/    # engine delivery and legacy-engine inspection/migration
│   ├── system_generators/   # combat, quest, progression, save/load, and world packets
│   └── verification/        # slice scoring and quality-gate helpers
├── session/                 # sessions, checkpoints, rollback, archives, memory
├── tools/                   # tool implementations exposed to the agent
├── engine/                  # public API, runtime, project, and modeling implementation
├── computer_use/            # embedded Open Computer Use Windows adapter
└── skills_manager.py        # SKILL.md discovery, matching, and prompt injection helpers
```

## Development

```bash
pip install -e ".[dev]"
mypy reverie
black reverie
```

Windows executable packaging:

```bat
cd ReverieCli-py
.\build.bat
.\build.bat --recreate-venv
.\build.bat --test-exe
```

`build.bat` runs from `ReverieCli-py` and writes the Python PyInstaller executable to the repository-root `dist\reverie.exe`.
Builds are incremental by default; use `--clean`, `--reinstall-deps`, `--refresh-browser`, or `--rebuild-plugins` when those parts need an explicit refresh.
GitHub Actions builds that Python PyInstaller executable as the primary `dist\reverie.exe`, runs the same release job on a daily schedule, and refreshes the rolling `latest` release assets.

The packaged `dist/reverie.exe` includes the unified Reverie Engine, work-in-progress Reverie-Gamer flows, the Gamer-only `reverie-engine` skill, `/engine video`, built-in Ren'Py inspection/migration, and modeling tools. Godot and O3DE no longer ship as runtime plugins; their useful scene, component, data-contract, and asset-pipeline patterns feed the one built-in engine. `build.bat` still installs the official Blender and Game Models plugins into `dist/.reverie/plugins/`; Ren'Py and Live2D remain optional source plugins instead of rolling Release assets. If `ffmpeg` is available during build, it is bundled for `mp4` and `gif` export; otherwise frame-sequence export remains available.

## Documentation

- [Documentation Index](docs/README.md)
- [Chinese README / 中文说明](docs/README.zh-CN.md)
- [Harness Engineering Notes](docs/HARNESS_ENGINEERING.md)
- [Configuration Guide](docs/CONFIGURATION.md)
- [CLI Command Reference](docs/CLI_COMMANDS.md)
- [Context Engine Project Memory](docs/CONTEXT_ENGINE_MEMORY.md)
- [Development Guide](docs/DEVELOPMENT.md)
- [Roadmap](docs/ROADMAP.md)
- [Reverie Engine User Guide](docs/engine/reverie_engine_user_guide.md)
- [Reverie-Gamer Modeling Guide](docs/engine/reverie_gamer_modeling_pipeline.md)
- [Changelog](docs/changelog.md)

## License

This project is licensed under the MIT License. See the repository-root [LICENSE](../LICENSE).
