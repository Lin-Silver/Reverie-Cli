"""Shared pytest fixtures.

Reverie resolves its runtime data directory through `get_app_root()`, which for a
source checkout points at the repository's `dist/` depot. Any test that builds a
`ConfigManager`, a project storage resolver, or a plugin/skill manager therefore
writes into the *live* `dist/.reverie` profile unless it overrides the app root
first -- which silently overwrites the developer's own config, models, and API
keys.

The autouse fixture below pins every test to a disposable app root underneath
`dist/.reverie/test-temp/`, so all test writes stay inside `dist/` (the sandbox
this project designates for real test artifacts) while leaving the real profile
untouched. Tests that need the override themselves may still call
`monkeypatch.setenv("REVERIE_APP_ROOT", ...)`; setting it again simply wins.
"""

from __future__ import annotations

from pathlib import Path
import hashlib
import shutil
import os

import pytest

# The repository `dist/` depot: the only tree tests are allowed to write into.
_DIST_ROOT = Path(__file__).resolve().parent.parent.parent / "dist"
_SANDBOX_ROOT = _DIST_ROOT / ".reverie" / "test-temp" / "roots"


def pytest_configure(config):
    if config.option.basetemp is None:
        root = _DIST_ROOT.parent / ".runtime" / f"pytest-{os.getpid()}"
        if root.exists():
            raise RuntimeError(f"Refusing to reuse pytest temporary directory: {root}")
        config.option.basetemp = str(root)


@pytest.fixture(autouse=True)
def isolated_skill_home(request, tmp_path, monkeypatch):
    if request.node.path.name in {"test_skill_modes.py", "test_skill_pinning.py", "test_skill_shadowing.py"} or request.node.name == "test_skills_manager_uses_header_metadata_for_discovery_without_auto_injection":
        home = tmp_path / "test-home"
        home.mkdir()
        monkeypatch.setattr(Path, "home", classmethod(lambda cls: home))


@pytest.fixture(autouse=True)
def isolated_app_root(request: pytest.FixtureRequest, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Point `REVERIE_APP_ROOT` at a per-test directory inside `dist/`.

    Yields the sandbox path so a test can assert against what was written.
    """
    # Keep the directory name tiny: nested tooling (git checkpoints, plugin
    # sandboxes) appends deep paths and Windows still caps them at 260 chars.
    digest = hashlib.sha1(request.node.nodeid.encode("utf-8")).hexdigest()[:12]
    root = _SANDBOX_ROOT / digest
    root.mkdir(parents=True, exist_ok=True)
    monkeypatch.setenv("REVERIE_APP_ROOT", str(root))
    yield root
    # Keep the tree from growing without bound across runs; failures keep their
    # artifacts so they can be inspected.
    if request.node.stash.get(_FAILED_KEY, False):
        return
    shutil.rmtree(root, ignore_errors=True)


_FAILED_KEY = pytest.StashKey[bool]()


@pytest.hookimpl(hookwrapper=True)
def pytest_runtest_makereport(item: pytest.Item, call: pytest.CallInfo):
    """Record whether a test failed so its sandbox is preserved for debugging."""
    outcome = yield
    report = outcome.get_result()
    if report.when == "call" and report.failed:
        item.stash[_FAILED_KEY] = True
