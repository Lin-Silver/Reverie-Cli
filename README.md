# Reverie CLI Workspace

This repository now separates the legacy Python CLI and the Rust rewrite:

- `ReverieCli-py/` contains the current Python Reverie CLI source, tests, packaging scripts, and the Python runtime used by Reverie UI.
- `ReverieCli-Rs/` contains the Rust rewrite based on OpenAI Codex.
- `plugins/` and `comfy/` are shared resource folders used by both CLI implementations and the build scripts.
- `Reverie UI/` remains the Windows desktop host. Its embedded Python runtime is sourced from `ReverieCli-py/ui-runtime`.
- `dist/` is intentionally left in place as the root runtime/output depot.

Python build entry:

```bat
cd ReverieCli-py
.\build.bat
```

Python development entry:

```bat
cd ReverieCli-py
python -m venv .venv
.venv\Scripts\activate
pip install -e ".[dev]"
python -m pytest -q
```

Rust build entry:

```bat
cd ReverieCli-Rs
.\build.bat
```

The Rust build writes `dist\Reverie-Rs.exe` and uses `ReverieCli-Rs\Reverie-Rs.ico`.
