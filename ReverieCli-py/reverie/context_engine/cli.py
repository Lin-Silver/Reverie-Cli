"""Standalone Context Engine commands and JSONL service implemented in Python."""

import argparse
import json
import math
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


_REQUEST_FIELDS = {
    "hello": {}, "state": {}, "files": {}, "commit": {}, "rollback": {},
    "begin": {"root": str, "replace": bool, "expected_revision": int},
    "apply": {"removed": list, "documents": list},
    "scan": {"root": str, "options": dict},
    "changes": {"root": str, "options": dict, "expected_revision": int},
    "search": {"weights": list, "limit": int, "chunks": bool, "expected_revision": int},
    "frequencies": {"terms": list, "expected_revision": int},
    "total": {"expected_revision": int},
    "paths": {"prefix": str, "limit": int, "expected_revision": int},
}


def _fields(value, schema, label):
    if type(value) is not dict:
        raise ValueError(f"Invalid {label}: expected an object")
    for name, expected in schema.items():
        if name not in value or type(value[name]) is not expected:
            raise ValueError(f"Invalid {label}.{name}: expected {expected.__name__}")
        if expected is int:
            lower, upper = (0, 2**64) if name == "limit" else (-(2**63), 2**63)
            if not lower <= value[name] < upper:
                raise ValueError(f"Invalid {label}.{name}: outside the integer range")


def _strings(value, label):
    if type(value) is not list or any(type(item) is not str for item in value):
        raise ValueError(f"Invalid {label}: expected an array of strings")


def _json_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"Duplicate JSON field: {key}")
        result[key] = value
    return result


def _json_constant(value):
    raise ValueError(f"Invalid JSON constant: {value}")


def _json_float(value):
    result = float(value)
    if not math.isfinite(result):
        raise ValueError("JSON number is outside the finite range")
    return result


def _decode_request(line):
    request = json.loads(line, object_pairs_hook=_json_object, parse_constant=_json_constant,
                        parse_float=_json_float)
    _fields(request, {"op": str}, "request")
    operation = request.pop("op")
    if operation not in _REQUEST_FIELDS:
        raise ValueError(f"Unknown Context Engine operation: {operation}")
    _fields(request, _REQUEST_FIELDS[operation], "request")
    if operation == "apply":
        _strings(request["removed"], "request.removed")
        for document in request["documents"]:
            _fields(document, {"path": str, "size": int, "modified_ns": int}, "document")
            if document.get("body") is not None and type(document["body"]) is not str:
                raise ValueError("Invalid document.body: expected text or null")
            chunks = document.get("chunks", [])
            if type(chunks) is not list:
                raise ValueError("Invalid document.chunks: expected an array")
            for chunk in chunks:
                _fields(chunk, {"name": str, "symbol": str, "kind": str,
                                "start_line": int, "end_line": int}, "chunk")
                for name in ("start_line", "end_line"):
                    if not 0 <= chunk[name] < 2**32:
                        raise ValueError(f"Invalid chunk.{name}: outside the line range")
                for name in ("signature", "documentation", "body"):
                    if name in chunk and type(chunk[name]) is not str:
                        raise ValueError(f"Invalid chunk.{name}: expected text")
    elif operation in {"scan", "changes"}:
        _fields(request["options"], {"extensions": list, "rules": list}, "options")
        for name in ("extensions", "rules"):
            _strings(request["options"][name], f"options.{name}")
    elif operation == "search":
        for pair in request["weights"]:
            if (type(pair) is not list or len(pair) != 2 or type(pair[0]) is not str
                    or type(pair[1]) not in {int, float} or not math.isfinite(pair[1])):
                raise ValueError("Invalid request.weights: expected text and finite numeric pairs")
    elif operation == "frequencies":
        _strings(request["terms"], "request.terms")
    if operation == "paths" and request["limit"] >= 2**32:
        raise ValueError("Invalid request.limit: outside the path limit range")
    return operation, request


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
                operation, request = _decode_request(line)
                response = {"result": catalog.request(operation, **request)}
            except (ContextStorageError, ValueError, KeyError, TypeError, AttributeError, OverflowError) as error:
                # Catalog rolls back failed writes; decode and read errors preserve pending updates.
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
