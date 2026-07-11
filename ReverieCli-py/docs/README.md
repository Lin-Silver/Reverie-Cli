# Reverie CLI Documentation

## Getting Started

- [English README](../README.md) — project overview, installation, and quick start
- [Chinese README](README.zh-CN.md) — 中文项目概览与快速上手

## Core Guides

| Document | Description |
| --- | --- |
| [Harness Engineering Notes](HARNESS_ENGINEERING.md) | Prompt/context/harness framing, Reverie capability audit, and the runtime harness upgrades inspired by Claude Code patterns and recent Harness Engineering practice |
| [Managed SubAgents](SUBAGENTS.md) | SubAgent configuration, TUI flow, delegation tools, logging, isolation, and validation |
| [Computer Controller](COMPUTER_CONTROLLER.md) | Embedded Open Computer Use-compatible desktop runtime, semantic desktop workflow, and SubAgent orchestration |
| [Writer Mode](writer_mode.md) | Native long-form fiction projects, chapter control cards, continuity ledgers, resumption, and verified completion |
| [Configuration Guide](CONFIGURATION.md) | Runtime storage layout, profile selection, model sources, TTI config, Atlas settings |
| [CLI Command Reference](CLI_COMMANDS.md) | Full command catalog: core, models, providers, tools, settings, sessions, game workflow |
| [Context Engine Project Memory](CONTEXT_ENGINE_MEMORY.md) | Project-isolated cross-session memory, immediate hybrid retrieval, provenance, conflict/version handling, and AI tool behavior |
| [Development Guide](DEVELOPMENT.md) | Local setup, testing, packaging, and documentation maintenance rules |
| [Roadmap](ROADMAP.md) | Single source of truth for planned runtime, Gamer, harness, and release work |
| [Changelog](changelog.md) | Release history and version notes |

## Gamer and Engine Guides

| Document | Description |
| --- | --- |
| [Reverie Engine User Guide](engine/reverie_engine_user_guide.md) | Built-in runtime architecture, content model, CLI workflow, and authoring expectations |
| [Reverie-Gamer Modeling Guide](engine/reverie_gamer_modeling_pipeline.md) | Work-in-progress Blender plugin-assisted authoring, Ashfox MCP integration, model workspace layout, import flow, and `/modeling`/`/blender` usage |

## Documentation Structure

- Top-level `docs/*.md` files are the canonical product, configuration, developer, and roadmap documents; all planned work belongs in `ROADMAP.md`.
- `docs/engine/` contains runtime-specific guides for Reverie Engine and Gamer production tooling.
- The old top-level `docs/reverie_modeling_pipeline.md` path has been retired in favor of `docs/engine/reverie_gamer_modeling_pipeline.md`.

## Source of Truth

- `reverie/cli/help_catalog.py` is the authoritative source for command names, summaries, and examples.
- `reverie/agent/system_prompt.py` controls runtime storage and spec/steering path references.
