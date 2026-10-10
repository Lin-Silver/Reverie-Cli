# Development Guide

This guide covers the practical local-development workflow for Reverie CLI.

Commands in Local Setup and Tests run from the repository root. Current capability limits are in [Feature Status](FEATURE_STATUS.md), and completion gates are in [Roadmap](ROADMAP.md).

## Local Setup

```bash
python -m venv .venv
.venv\Scripts\activate
pip install -e "./ReverieCli-py[dev]"
```

If you want optional tree-sitter language support during development:

```bash
pip install -e "./ReverieCli-py[treesitter]"
```

This extra is not part of `install_requires`, not part of `.[build]`, and not
pinned in `reverie.spec`'s `hiddenimports`, so neither a plain `pip install -e`
nor `build.bat` brings it in. Without it, JavaScript, TypeScript, C, C++, C#,
Rust, Go, Java, HTML and CSS are parsed by the regex fallback in
[treesitter_parser.py](../ReverieCli-py/reverie/context_engine/parsers/treesitter_parser.py)
instead of a concrete syntax tree, and the fallback is silent — the `ImportError`
is swallowed and nothing reports which mode is active. Install the extra before
measuring symbol or dependency extraction for those languages. Python, Lua,
GDScript, configuration, document and script files use this repository's own
parsers and are unaffected. `.zig` is claimed by the parser but has no grammar
dependency and no parse path in either mode, so it yields an empty result with
no error. See G30–G31 in [Feature Status](FEATURE_STATUS.md).

If you plan to exercise `/tti`, install its optional dependency set separately:

```bash
pip install -r ReverieCli-py/requirements-tti.txt
```

## Running The App

```bash
reverie
reverie .
reverie --index-only
reverie --no-index
```

## Runtime Data During Development

When running from source, Reverie treats the repository-local `dist/` folder as `app_root`. Project runtime data is written under:

```text
<app_root>/.reverie/projects/<project-path-key>/
```

That cache root holds the active project's config files, rules, indexes, sessions, checkpoints, specs, steering files, and related runtime artifacts.

`<project-path-key>` is the full absolute project path made filename-safe, for example `G:\Reverie\Reverie-Cli` becomes `G_Reverie_Reverie-Cli`. Legacy project-root `.reverie` files and older `<app_root>/.reverie/project_caches/` directories may still be read for migration, but new writes should stay inside `<app_root>/.reverie/projects/`.

## Tests And Quality Checks

Recommended checks:

```bash
python -m pytest -q -c ReverieCli-py/pytest.ini ReverieCli-py/tests
python scripts/verification/check_docs.py
```

The documentation check covers the maintained guides and Python/Desktop/Plugins README entry points. An ignored local `API.md` is checked when present, but is not required in a Git clone. To verify the checker itself, run `python -m pytest -q -c ReverieCli-py/pytest.ini ReverieCli-py/tests/test_documentation_links.py`.

Desktop checks run inside `ReverieCli-ui`:

```bash
npm ci
npm test
npm run typecheck
npm run build
```

Optional formatting/type diagnostics do not replace the runtime suite:

```bash
mypy ReverieCli-py/reverie
black --check ReverieCli-py/reverie
```

Vitest defaults to two workers and a 15-second test timeout so Windows subprocess / Git tests fit their actual execution time. Desktop test TEMP/TMP are kept under `ReverieCli-ui/.runtime/test-temp`; pytest's default base temp is a unique repository `.runtime/pytest-<pid>` directory. Python tests isolate the app root, and Skill discovery fixtures that require a fixed catalog also isolate the home directory. Tests must not replace a live profile or write verification artifacts to Desktop. Record skips, full-suite failures and fixture limitations explicitly; historical [audit failures](VERIFICATION_HISTORY.md#reverie-cli-feature-audit-2026-10-05) and [later repair results](VERIFICATION_HISTORY.md#reverie-cli-request-profile-repairs-2026-10-05) are separate evidence.

The Python suite's pass/skip totals are host-specific. Eleven `skipif` gates require `os.name == "nt"` or `platform.system() == "Windows"` — RATS provider identity and process-image validation, the real Engine E2E, Blender portable deployment, `taskkill` termination and Windows drive-path normalization — and three more tests branch on the platform inside the test body. A published total such as "1761 passed / 1 skipped" is a Windows figure; always name the host when quoting one, and do not read a non-Windows run's higher skip count as equivalent coverage. See G29 in [Feature Status](FEATURE_STATUS.md).

Provider cancellation tests use real loopback HTTP sockets, SDK clients and curl, including requests stalled before headers and inside body/stream reads. They assert that both the caller and upstream connection stop; cancelling a future alone is insufficient. Keep SSE keepalive, bounded early-close, retry interruption and preflight compression/auth requests covered when changing transport code. Packaged Electron tests must also exercise renderer CSP, actual file upload/crop, persistence and IPC; jsdom image/canvas mocks cannot verify those paths.

## Packaging

Run the following inside `ReverieCli-py` to build the platform-native core. Windows defaults to an EXE with a companion runtime directory for faster startup; Unix builds remain single-file:

```bat
.\build.bat
.\build.bat --recreate-venv
.\build.bat --test-exe
```

```bash
./build.sh --test-exe
```

`build.bat` currently:

- Prepares or recreates `venv`
- Reuses the existing dependency environment when `requirements.txt` and `setup.py` are unchanged
- Installs the project in editable mode
- Validates dependency health
- Does not run packaging-time regression tests automatically
- Supports progressive Skill metadata/inspection and mandatory prompt pins. Desktop stores session and draft pins; standalone CLI restore, fork/rotation inheritance and per-turn loading checks have [documented gaps](SKILLS.md). `setup.py` recursively includes built-in resources, excluding reports, bytecode and caches; PyInstaller uses the spec's resource collection. Validate both packaging paths when adding scripts or new resources.
- Bundles required Comfy assets
- Bundles `ffmpeg` into the runtime when it is available at build time
- Builds `dist/reverie.exe` and `dist/reverie-runtime/` with PyInstaller. Keep them together; set `REVERIE_PYINSTALLER_MODE=onefile` only when a single EXE is required.

The desktop directory provides end-to-end platform builds:

```powershell
cd ..\ReverieCli-ui
.\build.bat
```

```bash
cd ../ReverieCli-ui
./build.sh
```

The Windows script produces the core EXE, portable desktop EXE, and installer EXE. The desktop packages contain both the Electron GUI and the fast unpacked kernel; choose the default GUI or terminal startup in Desktop settings, or temporarily override it with `ReverieUI.exe --gui` / `ReverieUI.exe --tui`. The Linux script produces the no-suffix core, AppImage, and deb. CI additionally builds native Apple Silicon and Intel DMGs. `reverie` is the terminal/TUI command and `reverieui` opens the configured desktop interface at the caller's current directory.

Core/desktop artifacts publish through `build-core-release.yml`; plugin-only paths publish through `build-plugins.yml` to `plugins-latest`. Each core asset set includes SHA-256 kernel metadata, and the aggregate release job fails unless every required platform artifact exists and is non-empty.

Incremental builds reuse the PyInstaller work directory, embedded Chromium, and up-to-date official plugins. Use `--clean` for a full PyInstaller rebuild, `--reinstall-deps` to refresh packaging dependencies, `--refresh-browser` to reinstall Chromium, or `--rebuild-plugins` to force plugin rebuilds.

That packaged executable is intended to carry the built-in Reverie-Gamer flows in one file, including the integrated runtime, procedural 3D asset generation, Ren'Py import, and playblast/video export commands.

## Documentation Maintenance

The 2026-10-08 consolidation uses [docs/README.md](README.md) as the navigation entry. Current capability, priorities and release notes belong in `FEATURE_STATUS.md`, `ROADMAP.md` and `changelog.md` respectively. New RIU implementation follows [INTELLIGENT_UI_SPEC.md](INTELLIGENT_UI_SPEC.md), including its packaged isolation gate; the document itself is not implementation evidence.

Append dated audits and runtime evidence to [VERIFICATION_HISTORY.md](VERIFICATION_HISTORY.md), and obsolete decisions/specifications/handoff prompts to [DEVELOPMENT_HISTORY.md](DEVELOPMENT_HISTORY.md). Keep the date, host, command, test scope, failures, skipped paths and local-artifact limits. Keep original machine-readable JSON evidence in `docs/verification/`; do not replace it with a prose summary. Avoid adding another top-level dated report for each iteration.

Before removing a superseded document, migrate its unique content, add a stable destination anchor, update incoming links and run the documentation checker. Do not remove third-party Skill resources, license notices or upstream changelogs as product-document duplicates. New release entries must have one version heading; same-version updates are dated subsections and unverified releases remain Unreleased.

When you change user-facing behavior, update the docs in the same change:

- `README.md` for the English project overview and onboarding
- `docs/README.md` for document navigation and evidence classification
- `docs/README.zh-CN.md` for the Chinese onboarding guide
- `docs/FEATURE_STATUS.md` for current implementation, gaps, explicit exclusions and evidence limits
- `docs/DESKTOP_GUIDE.md` and `docs/SKILLS.md` for Desktop dispatch, Skills and persistence boundaries
- `docs/CONFIGURATION.md` for config and runtime-storage changes
- `docs/CLI_COMMANDS.md` for command reference
- `docs/engine/reverie_engine_user_guide.md` for `/engine` behavior
- `docs/ROADMAP.md` for all planned product work and completion gates
- `docs/changelog.md` for release-facing summaries when appropriate

If the change affects command wording, also update `ReverieCli-py/reverie/cli/help_catalog.py`. Check actual dispatch in `commands.py` / `__main__.py` and Desktop's `App.tsx` / `sdk_bridge.py`; listing a command in the catalog does not implement it.

If the change affects runtime storage or spec/steering paths, also update `ReverieCli-py/reverie/agent/system_prompt.py` and the relevant regression tests under `ReverieCli-py/tests/`.

The command catalog in `ReverieCli-py/reverie/cli/help_catalog.py` is the authoritative source for command descriptions, not proof of implementation in every client surface.

Keep dated reports as dated evidence. Link newly closed gaps to an actual test/build/runtime result rather than relabelling old evidence as fresh. `.runtime`, screenshots and local packages are ignored local materials; public guides must remain useful without them. `check_docs.py` checks local file/heading links, reports local artifact dependencies separately, and does not check external HTTP content or validate prose claims. CI runs that offline check.

## Practical Rules

- Prefer `help_catalog.py` over stale README text when documenting commands.
- Keep examples runnable and matched to current command syntax.
- Do not document helper scripts unless they are verified and maintained.
- If a feature depends on optional credentials or local caches, say that clearly in the docs.
- Keep the English and Chinese README files aligned on installation, quick-start, and storage behavior.
- Keep game-development roadmap material out of code comments and feature guides; planned work belongs only in `docs/ROADMAP.md`.
