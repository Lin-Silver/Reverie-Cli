"""Standalone Context Engine commands and JSONL service implemented in Python."""

import argparse
import json
from pathlib import Path
import sqlite3
import sys
import time

from .catalog import Catalog
from .legacy_backup import resolve_database
from .persistent_indexer import PersistentCodebaseIndexer
from .storage_errors import ContextStorageError
from .. import __version__
from ..stdio import configure_utf8_stdio


def _index(root, database):
    started = time.perf_counter()
    root = Path(root).resolve()
    if not root.is_dir():
        raise ValueError("Workspace must be a directory")
    database = resolve_database(database, rebuild=True)
    cache = database.parent if database.name == "python-search.sqlite3" else database.with_name(database.name + ".cache")
    indexer = PersistentCodebaseIndexer(root, cache, database=database)
    try:
        previous = {entry["path"] for entry in indexer._store.request("files")}
        result = indexer.refresh() if indexer.load_cache() else indexer.full_index(show_progress=False)
        if result.fatal_errors:
            raise ContextStorageError("; ".join(result.fatal_errors))
        current = {entry["path"] for entry in indexer._store.request("files")}
        return {"backend": "python", "revision": indexer._store.revision, "scanned": len(current),
                "indexed": result.files_parsed, "skipped": result.files_skipped,
                "removed": len(previous - current), "elapsed_ms": (time.perf_counter() - started) * 1000}
    finally:
        indexer.close()


def _serve(database):
    with Catalog(resolve_database(database, rebuild=True)) as catalog:
        for line in sys.stdin:
            try:
                request = json.loads(line)
                operation = request.pop("op")
                response = {"result": catalog.request(operation, **request)}
            except (ContextStorageError, ValueError, KeyError, TypeError, AttributeError) as error:
                catalog.request("rollback")
                response = {"error": str(error)}
            print(json.dumps(response, ensure_ascii=False, allow_nan=False), flush=True)


def _positive(value):
    value = int(value)
    if value <= 0:
        raise argparse.ArgumentTypeError("Limit must be positive")
    return value


def main(argv=None):
    configure_utf8_stdio()
    parser = argparse.ArgumentParser(prog="reverie --context-engine", description=__doc__)
    parser.add_argument("--version", action="version", version=f"reverie-context-engine {__version__} (python)")
    commands = parser.add_subparsers(dest="operation")
    index = commands.add_parser("index", help="Index or refresh a workspace")
    index.add_argument("workspace", type=Path)
    index.add_argument("database", type=Path)
    for operation in ("search", "chunks", "paths"):
        command = commands.add_parser(operation)
        command.add_argument("database", type=Path)
        command.add_argument("input")
        command.add_argument("limit", nargs="?", type=_positive, default=80)
    for operation in ("status", "serve"):
        command = commands.add_parser(operation)
        command.add_argument("database", type=Path)
    arguments = parser.parse_args(argv)
    if arguments.operation is None:
        parser.print_help()
        return 0
    try:
        if arguments.operation == "serve":
            _serve(arguments.database)
            return 0
        if arguments.operation == "index":
            result = _index(arguments.workspace, arguments.database)
        else:
            database = resolve_database(arguments.database)
            with Catalog(database, readonly=True) as catalog:
                if arguments.operation == "status":
                    result = catalog.request("state")
                elif arguments.operation == "paths":
                    result = catalog.request("paths", prefix=arguments.input, limit=arguments.limit)
                else:
                    result = catalog.request("search", weights=[(word, 1.0) for word in arguments.input.split()],
                                             limit=arguments.limit, chunks=arguments.operation == "chunks")
        print(json.dumps(result, ensure_ascii=False, allow_nan=False))
        return 0
    except (ContextStorageError, sqlite3.Error, OSError, ValueError) as error:
        print(f"Context Engine: {error}", file=sys.stderr)
        return 1
