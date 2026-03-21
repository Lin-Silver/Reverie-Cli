# Development Guide

This guide covers the practical local-development workflow for Reverie CLI.

## Local Setup

```bash
python -m venv .venv
.venv\Scripts\activate
pip install -e ".[dev]"
```

If you want optional tree-sitter language support during development:

```bash
pip install -e ".[treesitter]"
```

If you plan to exercise `/tti`, install its optional dependency set separately:

```bash
pip install -r requirements-tti.txt
```

## Running The App

```bash
reverie
reverie .
reverie --index-only
reverie --no-index
```

## Runtime Data During Development

When running from source, Reverie treats the repository root as `app_root`. Project runtime data is written under:

```text
.reverie/project_caches/<project-key>/
```

That cache root holds the active project's config files, rules, indexes, sessions, checkpoints, specs, steering files, and related runtime artifacts.

Legacy `.reverie` files may still be read for migration, but new writes should stay inside `.reverie/project_caches/`.

## Tests And Quality Checks

Recommended checks:

```bash
pytest
mypy reverie
black reverie tests
```

Current regression coverage includes:

- Atlas mode config and prompt contract
- Codex and Gemini endpoint normalization
- Native streaming resilience when providers terminate early after partial output
- Project cache placement, legacy `.reverie` migration, and command audit routing
- Workspace memory indexing behavior

## Packaging

Windows packaging is handled by `build.bat`.

```bat
.\build.bat
.\build.bat --recreate-venv
```

`build.bat` currently:

- Prepares or recreates `venv`
- Upgrades packaging tools
- Installs the project in editable mode
- Validates dependency health
- Bundles required Comfy assets
- Builds `dist/reverie.exe` with PyInstaller

## Documentation Maintenance

When you change user-facing behavior, update the docs in the same change:

- `README.md` for the English project overview and onboarding
- `docs/README.zh-CN.md` for the Chinese onboarding guide
- `docs/CONFIGURATION.md` for config and runtime-storage changes
- `docs/CLI_COMMANDS.md` for command reference
- `docs/engine/reverie_engine_user_guide.md` for `/engine` behavior
- `changelog.md` for release-facing summaries when appropriate

If the change affects command wording, also update `reverie/cli/help_catalog.py`.

If the change affects runtime storage or spec/steering paths, also update `reverie/agent/system_prompt.py` and the regression tests in `tests/test_runtime_storage_and_streaming.py`.

The command catalog in `reverie/cli/help_catalog.py` is the authoritative source for command descriptions.

## Practical Rules

- Prefer `help_catalog.py` over stale README text when documenting commands.
- Keep examples runnable and matched to current command syntax.
- Do not document helper scripts unless they are verified and maintained.
- If a feature depends on optional credentials or local caches, say that clearly in the docs.
- Keep the English and Chinese README files aligned on installation, quick-start, and storage behavior.
