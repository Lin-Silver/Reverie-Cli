"""Durability and search contracts for the final Python Context Engine."""

import sqlite3

import pytest

from reverie.context_engine.catalog import Catalog
from reverie.context_engine.storage_errors import ContextStorageError


def _document(path="src/invoice.py", *, body="billing epoch"):
    return {
        "path": path, "size": 200, "modified_ns": 1234, "body": body,
        "chunks": [{"name": "validateInvoice", "symbol": "src.invoice.PipelineGuard.validateInvoice",
                    "kind": "METHOD", "start_line": 2, "end_line": 3,
                    "signature": "def validateInvoice(self)", "documentation": "", "body": body}],
    }


def _write(catalog, *, expected=0, documents=None, removed=()):
    catalog.request("begin", root="workspace", replace=False, expected_revision=expected)
    catalog.request("apply", removed=list(removed), documents=documents or [_document()])
    return catalog.request("commit")["revision"]


def _hits(catalog, term, revision=1):
    return catalog.request("search", weights=[(term, 1.0)], limit=10, chunks=False,
                           expected_revision=revision)


def test_python_catalog_indexes_chunks_and_removes_documents(tmp_path):
    with Catalog(tmp_path / "index #1% 中文.sqlite3") as catalog:
        assert catalog.request("state") == {"root": "", "revision": 0}
        assert _write(catalog) == 1
        assert _hits(catalog, "billing")[0]["file_path"] == "src/invoice.py"
        chunk = catalog.request("search", weights=[("validateInvoice", 2.0)], limit=10,
                                chunks=True, expected_revision=1)[0]
        assert (chunk["symbol"], chunk["kind"], chunk["start_line"]) == (
            "src.invoice.PipelineGuard.validateInvoice", "METHOD", 2)
        assert catalog.request("frequencies", terms=["billing", "invoice"], expected_revision=1) == {
            "total": 1, "terms": {"billing": 1, "invoice": 0}}
        assert _write(catalog, expected=1, removed=["src/invoice.py"],
                      documents=[_document("src/a%_name.py", body="transport")]) == 2
        assert _hits(catalog, "billing", 2) == []
        assert catalog.request("paths", prefix="src/a%_", limit=10, expected_revision=2) == ["src/a%_name.py"]


def test_failed_apply_rolls_back_and_does_not_publish_a_revision(tmp_path):
    with Catalog(tmp_path / "index.sqlite3") as catalog:
        _write(catalog)
        previous = _hits(catalog, "billing")
        catalog.request("begin", root="workspace", replace=True, expected_revision=1)
        with pytest.raises(ContextStorageError, match="relative path"):
            catalog.request("apply", removed=[], documents=[_document("../outside.py")])
        assert catalog.request("state")["revision"] == 1
        assert _hits(catalog, "billing") == previous
        with pytest.raises(ContextStorageError, match="not started"):
            catalog.request("commit")
        assert _write(catalog, expected=1) == 2


def test_concurrent_readers_and_writers_use_committed_revisions(tmp_path):
    database = tmp_path / "index.sqlite3"
    with Catalog(database) as first, Catalog(database) as second:
        _write(first)
        previous = _hits(first, "billing")
        second.request("begin", root="workspace", replace=True, expected_revision=1)
        second.request("apply", removed=[], documents=[_document(body="transport")])
        assert _hits(first, "billing") == previous
        assert _hits(second, "billing") == previous
        with Catalog(database) as late_reader:
            assert _hits(late_reader, "billing") == previous
        assert second.request("commit")["revision"] == 2
        with pytest.raises(ContextStorageError, match="since it was loaded"):
            _hits(first, "billing")
        with pytest.raises(ContextStorageError, match="changed while preparing"):
            first.request("begin", root="workspace", replace=True, expected_revision=1)
        assert _hits(first, "transport", 2)
        assert _write(first, expected=2) == 3


def test_unrelated_database_and_workspace_are_preserved(tmp_path):
    database = tmp_path / "unrelated.sqlite3"
    with sqlite3.connect(database) as connection:
        connection.execute("CREATE TABLE private_data(value TEXT)")
        connection.execute("INSERT INTO private_data VALUES ('retain')")
    original = database.read_bytes()
    with Catalog(database) as catalog, pytest.raises(ContextStorageError, match="unrelated"):
        catalog.request("state")
    assert database.read_bytes() == original
    with Catalog(tmp_path / "index.sqlite3") as catalog:
        _write(catalog)
        with pytest.raises(ContextStorageError, match="different workspace"):
            catalog.request("begin", root="other-workspace", replace=True, expected_revision=1)
        assert _hits(catalog, "billing")
