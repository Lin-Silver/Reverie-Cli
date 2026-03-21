# Reverie CLI Documentation

This directory contains the maintained reference documentation for Reverie CLI.

## Bilingual README Pair

- [English README](../README.md): project overview, installation, quick start, and architecture snapshot
- [Chinese README](README.zh-CN.md): Chinese overview, installation, quick start, and storage notes

## Core Documentation

- [Configuration Guide](CONFIGURATION.md): config profiles, provider sections, project cache layout, rules, and migration notes
- [CLI Command Reference](CLI_COMMANDS.md): grouped command reference aligned with `reverie/cli/help_catalog.py`
- [Development Guide](DEVELOPMENT.md): local setup, tests, packaging, runtime storage, and doc maintenance
- [Reverie Engine User Guide](engine/reverie_engine_user_guide.md): built-in runtime and `/engine` workflows
- [Change Log](../changelog.md): release-facing summary when maintained

## Storage Layout At A Glance

Reverie keeps runtime state under the app root, not in the directory where the command is launched.

- App root: the repository root when running from source, or the folder containing `reverie.exe` in packaged builds
- Project cache root: `<app_root>/.reverie/project_caches/<project-key>/`
- Default profile: `<app_root>/.reverie/project_caches/<project-key>/config.global.json`
- Workspace profile: `<app_root>/.reverie/project_caches/<project-key>/config.json`
- Common project data: `rules.txt`, `context_cache/`, `sessions/`, `archives/`, `checkpoints/`, `specs/`, `steering/`, `security/`

`<project-key>` is derived from the absolute project path plus a short hash so multiple workspaces remain isolated.

## Maintenance Rules

- Keep command descriptions aligned with `reverie/cli/help_catalog.py`.
- Keep config details aligned with `reverie/config.py` and provider modules.
- Update both README files together when onboarding, installation, or storage behavior changes.
- When command behavior changes, update `README.md`, [CLI Command Reference](CLI_COMMANDS.md), and in-app help text in the same change.
- When storage paths change, also update `reverie/agent/system_prompt.py` so spec and steering workflows keep writing to the right place.
