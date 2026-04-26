# Reverie CLI

Reverie CLI is a context-engine-powered AI coding assistant for large repositories. It combines repository indexing, multi-provider model routing, session memory, checkpoints, rollback tools, and a rich terminal UI so the agent can work against the real codebase instead of guessing.

## Highlights

- **Context Engine** — shared by every mode for symbol lookup, dependency tracking, semantic retrieval, commit-history learning, and workspace memory
- **Multiple Workflow Modes** — `Reverie`, `Reverie-Atlas`, `Reverie-Gamer`, `Reverie-Ant`, `Spec-Driven`, `Spec-Vibe`, `Writer`, `Computer Controller`
- **Multi-Provider** — standard OpenAI-compatible models plus `Gemini CLI`, `Codex`, `NVIDIA`, and `ModelScope`
- **Rich TUI** — selectors, streaming output, help browser, status panels, session browsing, checkpoint rollback, command discovery
- **Workspace Safety** — file-access sandboxing, audited command execution, archive extraction hardening
- **Game Tooling** — built-in `Reverie Engine` runtime, prompt-to-vertical-slice Reverie-Gamer workflow, direct Blender authoring, Godot/O3DE open-runtime plugins, and a built-in Ashfox MCP bridge for optional Blockbench sessions

## Latest Update

Current stable repository version: `v2.1.21`.

- Recent unreleased work adds one-shot prompt execution through `reverie -p "<task>"`, `--mode`, and packaged `Reverie.exe -p "<task>"`.
- `Reverie-Atlas` now downgrades simple Tier 1 tasks back to base `Reverie`, and `Writer` now asks for missing style/brief details more deliberately before long-form generation.
- The docs were cleaned up around the engine/gamer workflow, and the old Gamer assessment note was replaced by a next-stage upgrade roadmap.

For the full release notes, see [docs/changelog.md](docs/changelog.md).

## Reverie-Gamer Roadmap

Reverie-Gamer is currently aimed at:

`one prompt -> structured request -> blueprint -> runtime-aware project foundation -> verified playable vertical slice -> iterative expansion`

Current strategic rollout as of **2026-04-06**:

- **2026-04-06 to 2026-04-20**: project-program compiler outputs, milestone planning, and stronger artifact generation from a single prompt
- **2026-04-20 to 2026-05-11**: asset-pipeline automation, gameplay-system packet upgrades, and runtime delivery polish
- **2026-05-11 to 2026-06-08**: world-scale expansion, autonomous continuation, and richer validation loops for longer-running 3D projects

The current upgrade plan lives in [docs/reverie_gamer_3d_game_generation_assessment.md](docs/reverie_gamer_3d_game_generation_assessment.md).

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
reverie -p "fix failing tests"   # run one prompt non-interactively and exit
reverie --prompt-file task.md    # run a long prompt from a file
Get-Content task.md | reverie --prompt-stdin  # run a long prompt from stdin
reverie -p "fix failing tests" --report-file artifacts/prompt_report.json
reverie /path/to/project -p "add a health check" --mode reverie-atlas
reverie --version            # print version
```

`--report-file` writes structured JSON for prompt runs, including the final output, activity events, UI events, and a harness report that summarizes tasks, checkpoints, command audit evidence, verification posture, and recent run-history trends. Prompt-mode runs now also persist lightweight harness snapshots in the project cache so `/doctor` can show score and verification drift over time.

For long prompts, use `--prompt-file <path>`, pipe text with `--prompt-stdin`, or use the shorthand `-p @task.md` / `-p -`. Prompt files are decoded as UTF-8 first, then common locale encodings, with replacement fallback instead of aborting on invalid bytes.

For the packaged Windows build, the same one-shot flow works with `dist\reverie.exe -p "<task>"`. On Windows paths and executable names are case-insensitive, so `Reverie.exe -p "<task>"` works the same way.

On first run, configure at least one model source. Reverie supports:

- Standard OpenAI-compatible endpoints (stored in `models`)
- `Gemini CLI`, `Codex`, `NVIDIA`, `ModelScope`

Use `/model` to add presets or `/Geminicli`, `/codex`, `/nvidia`, `/modelscope` for provider-specific setup.

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
| `Reverie-Gamer` | Prompt-to-blueprint, runtime scaffolding, vertical-slice delivery, and verification workflows for game production |
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
├── modelscope.py            # ModelScope provider integration
├── agent/                   # agent prompts, tool execution, orchestration
├── cli/                     # command handling, TUI, display helpers
├── context_engine/          # indexing, retrieval, semantic analysis, graph data
├── gamer/                   # Gamer production pipeline and runtime generation
│   ├── runtime_adapters/    # built-in runtime targets such as Godot / Reverie Engine / O3DE
│   ├── system_generators/   # combat, quest, progression, save/load, and world packets
│   └── verification/        # slice scoring and quality-gate helpers
├── session/                 # sessions, checkpoints, rollback, archives, memory
├── tools/                   # tool implementations exposed to the agent
├── engine/                  # canonical public built-in engine API
├── engine_lite/             # shared runtime, project, and modeling implementation
├── skills_manager.py        # SKILL.md discovery, matching, and prompt injection helpers
└── writer/                  # writer mode helpers
```

## Development

```bash
pip install -e ".[dev]"
mypy reverie
black reverie
```

Windows executable packaging:

```bat
.\build.bat
.\build.bat --recreate-venv
.\build.bat --test-exe
```

The packaged `dist/reverie.exe` now includes the built-in Reverie-Gamer runtime flows in one file, including `/engine video`, `/engine renpy`, `/modeling primitive`, and `/blender`. `build.bat` installs the official Blender, Godot, O3DE, and Game Models runtime plugins into `dist/.reverie/plugins/`: Blender can unpack its portable runtime when the build input zip is present and can prepare plugin-local MMD Tools for PMD/PMX/VMD/VPD import, Godot can discover/download official GitHub releases or clone source, O3DE can clone source plus write a plugin-local SDK manifest, and Game Models can prepare a plugin-local venv plus selectable HuggingFace model snapshots such as TRELLIS `low_vram` for local asset assistance. If `ffmpeg` is available during build, `build.bat` bundles it into the executable so `mp4` and `gif` export work without a separate system install. If not, frame-sequence export still works and encoded video falls back to an external `ffmpeg` at runtime.

## Documentation

- [Documentation Index](docs/README.md)
- [Chinese README / 中文 README](docs/README.zh-CN.md)
- [Harness Engineering Notes](docs/HARNESS_ENGINEERING.md)
- [Configuration Guide](docs/CONFIGURATION.md)
- [CLI Command Reference](docs/CLI_COMMANDS.md)
- [Development Guide](docs/DEVELOPMENT.md)
- [Reverie Engine User Guide](docs/engine/reverie_engine_user_guide.md)
- [Reverie-Gamer Modeling Guide](docs/engine/reverie_gamer_modeling_pipeline.md)
- [Reverie-Gamer Upgrade Plan](docs/reverie_gamer_3d_game_generation_assessment.md)
- [Changelog](docs/changelog.md)

## License

This repository is documented as MIT-licensed by the project author. If you distribute the project externally, add the final license file that matches your intended terms.
