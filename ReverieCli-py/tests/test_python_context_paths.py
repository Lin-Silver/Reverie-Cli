"""Actual Python Context Engine commands, including Windows extended cache paths."""

import json
import os
from pathlib import Path
import subprocess
import sys

import pytest

from reverie.context_engine.factory import create_indexer
from reverie.context_engine.storage import PythonContext


@pytest.mark.skipif(os.name != "nt", reason="Windows extended paths")
def test_python_catalog_opens_a_cache_beyond_max_path(tmp_path):
    root = tmp_path / "workspace"
    root.mkdir()
    cache = tmp_path / "cache"
    while len(str(cache)) < 270:
        cache /= "nested-cache"
    cache.mkdir(parents=True)
    worker = PythonContext(root, cache)
    try:
        assert worker.request("state") == {"root": "", "revision": 0}
        assert worker.database.is_file()
    finally:
        worker.close()


@pytest.mark.skipif(os.name != "nt", reason="Windows extended paths")
@pytest.mark.parametrize("operation", ["serve", "index", "status", "search", "chunks", "paths"])
def test_cli_uses_long_database_paths_without_changing_workspace_or_query(tmp_path, operation):
    root = tmp_path / "工作区"
    root.mkdir()
    (root / "billing.py").write_text("def verifyInvoice():\n    return 'billing'\n", encoding="utf-8")
    cache = tmp_path / "cache"
    while len(str(cache)) < 270:
        cache /= "nested-cache"
    database = cache / "index #1% 中文.sqlite3"
    command = [sys.executable, "-m", "reverie", "--context-engine"]

    def run(*arguments, input=None):
        completed = subprocess.run([*command, *map(str, arguments)], input=input, capture_output=True,
                                   encoding="utf-8", check=True, timeout=60)
        return [json.loads(line) for line in completed.stdout.splitlines()]

    assert run("index", root, database)[0]["indexed"] == 1
    if operation == "serve":
        responses = run("serve", database, input='{"op":"hello"}\n{"op":"state"}\n')
        assert responses[0]["result"]["backend"] == "python"
        assert responses[1]["result"]["root"] == os.path.normcase(str(root.resolve()))
    elif operation == "index":
        result = run("index", root, database)[0]
        assert result["indexed"] == 0 and result["revision"] == 1
    elif operation == "status":
        assert run("status", database)[0] == {"root": os.path.normcase(str(root.resolve())), "revision": 1}
    elif operation == "paths":
        assert run("paths", database, "bill")[0] == ["billing.py"]
    else:
        result = run(operation, database, "verifyInvoice")[0]
        assert result[0]["file_path"] == "billing.py"
        if operation == "chunks":
            assert result[0]["symbol"] == "billing.verifyInvoice"


@pytest.mark.parametrize("arguments", [[], ["--help"], ["--version"]])
def test_cli_exposes_python_usage_and_version(arguments):
    result = subprocess.run([sys.executable, "-m", "reverie", "--context-engine", *arguments],
                            capture_output=True, encoding="utf-8", check=True, timeout=60)
    assert "reverie-context-engine" in result.stdout if arguments == ["--version"] else "serve" in result.stdout


def test_application_factory_never_starts_a_compiled_context_worker(tmp_path, monkeypatch):
    root = tmp_path / "workspace"
    root.mkdir()
    (root / "billing.py").write_text("def verifyInvoice(): return 'billing'\n", encoding="utf-8")

    def forbidden(*args, **kwargs):
        raise AssertionError("The final Python Context Engine must not spawn a Rust worker")

    monkeypatch.setattr(subprocess, "Popen", forbidden)
    indexer = create_indexer(root, str(tmp_path / "cache"))
    try:
        assert indexer.full_index(show_progress=False).success
        assert indexer.get_index_status()["backend"] == "python"
        assert indexer.search_code_chunks([("verifyInvoice", 1.0)])
    finally:
        indexer.close()
