# Contributing

Reverie CLI is currently alpha software. Keep changes focused, preserve cross-platform behavior in the core Python package, and document Windows-only behavior explicitly.

## Development setup

From `ReverieCli-py/`, create a virtual environment and run:

```text
python -m pip install -e ".[dev]"
python -m compileall -q reverie
python -m pytest -q
```

Update root-level `docs/` when behavior or configuration changes. Add focused regression tests for security boundaries, config migrations, and tool behavior. Do not commit build output, virtual environments, downloaded reference repositories, secrets, third-party SDK archives, or generated executables.

Report security issues using [SECURITY.md](SECURITY.md), not a public issue.
