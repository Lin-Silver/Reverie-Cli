"""Windows cache paths must work through both Python and the standalone bridge."""
import os
from pathlib import Path
import subprocess
from types import SimpleNamespace

import pytest

from reverie.context_engine.native import NativeContext, find_executable


@pytest.mark.skipif(os.name != "nt", reason="Windows extended paths")
def test_native_worker_opens_a_cache_beyond_max_path(tmp_path):
    executable = find_executable()
    if executable is None:
        pytest.skip("Build the Context Engine first")
    root = tmp_path / "workspace"
    root.mkdir()
    cache = tmp_path / "cache"
    while len(str(cache)) < 270:
        cache /= "nested-cache"
    cache.mkdir(parents=True)
    worker = NativeContext(executable, root, cache)
    try:
        assert worker.request("state") == {"root": "", "revision": 0}
        assert worker.database.is_file()
    finally:
        worker.close()


@pytest.mark.skipif(os.name != "nt", reason="Windows extended paths")
@pytest.mark.parametrize("operation,arguments,database_index", [
    ("serve", ["index.sqlite3"], 1),
    ("index", ["workspace", "index.sqlite3"], 2),
    ("status", ["index.sqlite3"], 1),
    ("search", ["index.sqlite3", "query"], 1),
    ("chunks", ["index.sqlite3", "query"], 1),
    ("paths", ["index.sqlite3", "src"], 1),
])
def test_cli_forwarding_extends_only_the_database_path(tmp_path, monkeypatch, operation, arguments, database_index):
    from reverie import __main__
    from reverie.context_engine import native

    executable = tmp_path / "engine.exe"
    calls = []
    monkeypatch.setattr(native, "find_executable", lambda: executable)
    monkeypatch.setattr(subprocess, "run", lambda command, **kwargs: calls.append(command) or SimpleNamespace(returncode=0))
    command = [operation, *arguments]
    assert __main__.main(["--context-engine", *command]) == 0
    forwarded = calls[0][1:]
    expected = "\\\\?\\" + str(Path(command[database_index]).resolve())
    assert forwarded[database_index] == expected
    assert forwarded[:database_index] == command[:database_index]
    assert forwarded[database_index + 1:] == command[database_index + 1:]


@pytest.mark.parametrize("arguments", [[], ["--help"], ["--version"]])
def test_cli_forwards_native_usage_requests(tmp_path, monkeypatch, arguments):
    from reverie import __main__
    from reverie.context_engine import native

    executable = tmp_path / "engine.exe"
    calls = []
    monkeypatch.setattr(native, "find_executable", lambda: executable)
    monkeypatch.setattr(subprocess, "run", lambda command, **kwargs: calls.append(command) or SimpleNamespace(returncode=7))
    assert __main__.main(["--context-engine", *arguments]) == 7
    assert calls == [[str(executable), *arguments]]
