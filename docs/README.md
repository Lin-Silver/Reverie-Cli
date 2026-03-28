# Reverie CLI Documentation

## Getting Started

- [English README](../README.md) — project overview, installation, and quick start
- [Chinese README](README.zh-CN.md) — 中文项目概览与快速上手

## Core Guides

| Document | Description |
| --- | --- |
| [Configuration Guide](CONFIGURATION.md) | Runtime storage layout, profile selection, model sources, TTI config, Atlas settings |
| [CLI Command Reference](CLI_COMMANDS.md) | Full command catalog: core, models, providers, tools, settings, sessions, game workflow |
| [Development Guide](DEVELOPMENT.md) | Local setup, testing, packaging, and documentation maintenance rules |
| [Reverie Engine User Guide](engine/reverie_engine_user_guide.md) | Built-in runtime architecture, content model, CLI workflow, AI authoring |
| [Reverie-Gamer Modeling Guide](engine/reverie_gamer_modeling_pipeline.md) | Built-in Ashfox MCP integration for Reverie-Gamer, model workspace layout, import flow, and `/modeling` command usage |
| [Changelog](changelog.md) | Release history and version notes |

## Source of Truth

- `reverie/cli/help_catalog.py` is the authoritative source for command names, summaries, and examples.
- `reverie/agent/system_prompt.py` controls runtime storage and spec/steering path references.
