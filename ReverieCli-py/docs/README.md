# Reverie CLI Documentation

## Getting Started

- [English README](../README.md) — project overview, installation, and quick start
- [Chinese README](README.zh-CN.md) — 中文项目概览与快速上手

## Core Guides

| Document | Description |
| --- | --- |
| [Harness Engineering Notes](HARNESS_ENGINEERING.md) | Prompt/context/harness framing, Reverie capability audit, and the runtime harness upgrades inspired by Claude Code patterns and recent Harness Engineering practice |
| [Subagent Upgrade](SUBAGENT_UPGRADE.md) | Base-Reverie Subagent configuration, TUI flow, delegation tool, logging colors, and validation notes |
| [Configuration Guide](CONFIGURATION.md) | Runtime storage layout, profile selection, model sources, TTI config, Atlas settings |
| [CLI Command Reference](CLI_COMMANDS.md) | Full command catalog: core, models, providers, tools, settings, sessions, game workflow |
| [Development Guide](DEVELOPMENT.md) | Local setup, testing, packaging, and documentation maintenance rules |
| [Changelog](changelog.md) | Release history and version notes |

## Gamer and Engine Guides

| Document | Description |
| --- | --- |
| [Reverie Engine User Guide](engine/reverie_engine_user_guide.md) | Built-in runtime architecture, content model, CLI workflow, and authoring expectations |
| [Reverie-Gamer Modeling Guide](engine/reverie_gamer_modeling_pipeline.md) | Built-in Blender authoring, Ashfox MCP integration, model workspace layout, import flow, and `/modeling`/`/blender` usage |
| [Reverie-Gamer Upgrade Plan](reverie_gamer_3d_game_generation_assessment.md) | Next-stage roadmap for evolving Gamer from vertical-slice generation into long-running 3D game production |

## Documentation Structure

- Top-level `docs/*.md` files are the canonical product, configuration, developer, and roadmap documents.
- `docs/engine/` contains runtime-specific guides for Reverie Engine and Gamer production tooling.
- The old top-level `docs/reverie_modeling_pipeline.md` path has been retired in favor of `docs/engine/reverie_gamer_modeling_pipeline.md`.

## Source of Truth

- `reverie/cli/help_catalog.py` is the authoritative source for command names, summaries, and examples.
- `reverie/agent/system_prompt.py` controls runtime storage and spec/steering path references.
