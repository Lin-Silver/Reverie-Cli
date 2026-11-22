"""The JSONL boundary rejects malformed requests without altering transactions."""

import json
import subprocess
import sys

import pytest


def _document(body="billing epoch"):
    return {"path": "src/invoice.py", "size": 200, "modified_ns": 1234,
            "body": body, "chunks": []}


def _begin(revision=0, **fields):
    return {"op": "begin", "root": "workspace", "replace": False,
            "expected_revision": revision, **fields}


def _seed():
    return [_begin(), {"op": "apply", "removed": [], "documents": [_document()]}, {"op": "commit"}]


def _search(term, revision):
    return {"op": "search", "weights": [[term, 1.0]], "limit": 10,
            "chunks": False, "expected_revision": revision}


def _run(database, requests):
    payload = "\n".join(request if isinstance(request, str) else json.dumps(request)
                        for request in requests) + "\n"
    result = subprocess.run([sys.executable, "-m", "reverie", "--context-engine", "serve", str(database)],
                            input=payload, capture_output=True, encoding="utf-8", check=True, timeout=60)
    responses = [json.loads(line) for line in result.stdout.splitlines()]
    assert len(responses) == len(requests)
    return responses


@pytest.mark.parametrize("fields", [
    {"replace": "false"}, {"replace": 0}, {"replace": None}, {"root": 17},
    {"expected_revision": True}, {"expected_revision": 1.0},
    {"expected_revision": "1"}, {"expected_revision": 2**63},
])
def test_invalid_begin_cannot_replace_a_committed_index(tmp_path, fields):
    database = tmp_path / "catalog.sqlite3"
    responses = _run(database, _seed() + [_begin(1, **fields), {"op": "commit"},
                                         {"op": "state"}, _search("billing", 1)])
    assert "error" in responses[3]
    assert "not started" in responses[4]["error"]
    assert responses[5]["result"] == {"root": "workspace", "revision": 1}
    assert responses[6]["result"][0]["file_path"] == "src/invoice.py"
    restored = _run(database, [{"op": "state"}, _search("billing", 1)])
    assert restored == responses[5:]


@pytest.mark.parametrize("invalid", [
    "{", "[]", "null", '{"op": "hello", "value": NaN}', '{"op": "hello", "value": 1e400}',
    '{"op": "begin", "root": "workspace", "replace": false, "replace": true, "expected_revision": 1}',
    {}, {"op": 1}, {"op": "unknown"},
    _begin(1, replace="false"), _begin(1, expected_revision=True),
    {"op": "apply", "removed": "src/invoice.py", "documents": []},
    {"op": "apply", "removed": [], "documents": [_document(17)]},
    {"op": "apply", "removed": [], "documents": [{**_document(), "size": True}]},
    {"op": "apply", "removed": [], "documents": [{**_document(), "chunks": None}]},
    {"op": "apply", "removed": [], "documents": [{**_document(), "chunks": [
        {"name": "invoice", "symbol": "invoice", "kind": "FUNCTION", "start_line": True, "end_line": 2}]}]},
    {**_search("billing", 1), "chunks": "false"},
    {**_search("billing", 1), "weights": [["billing", "1"]]},
    {**_search("billing", 1), "weights": [["billing", 10**400]]},
    {**_search("billing", 1), "limit": True},
    {"op": "total"},
    {"op": "paths", "prefix": "src", "limit": 2**32, "expected_revision": 1},
    {"op": "scan", "root": "workspace", "options": {"extensions": "py", "rules": []}},
])
def test_malformed_requests_keep_a_valid_pending_update(tmp_path, invalid):
    database = tmp_path / "catalog.sqlite3"
    pending = [_begin(1, replace=True), {"op": "apply", "removed": [], "documents": [_document("transport")]}]
    responses = _run(database, _seed() + pending + [invalid, {"op": "commit"},
                                                   {"op": "state"}, _search("transport", 2)])
    assert "error" in responses[5]
    assert responses[6]["result"] == {"root": "workspace", "revision": 2}
    assert responses[7]["result"] == responses[6]["result"]
    assert responses[8]["result"][0]["file_path"] == "src/invoice.py"
    assert _run(database, [{"op": "state"}, _search("transport", 2)]) == responses[7:]


def test_failed_read_does_not_cancel_a_valid_pending_update(tmp_path):
    responses = _run(tmp_path / "catalog.sqlite3", _seed() + [
        _begin(1, replace=True), {"op": "apply", "removed": [], "documents": [_document("transport")]},
        _search("billing", 0), {"op": "commit"}, _search("transport", 2)])
    assert "changed since it was loaded" in responses[5]["error"]
    assert responses[6]["result"]["revision"] == 2
    assert responses[7]["result"][0]["file_path"] == "src/invoice.py"


def test_valid_write_failure_rolls_back_the_whole_update(tmp_path):
    document = {**_document("transport"), "path": "../outside.py"}
    responses = _run(tmp_path / "catalog.sqlite3", _seed() + [
        _begin(1, replace=True), {"op": "apply", "removed": [], "documents": [document]},
        {"op": "commit"}, {"op": "state"}, _search("billing", 1)])
    assert "relative path" in responses[4]["error"]
    assert "not started" in responses[5]["error"]
    assert responses[6]["result"]["revision"] == 1
    assert responses[7]["result"][0]["file_path"] == "src/invoice.py"


def test_service_preserves_valid_queries_and_default_document_fields(tmp_path):
    document = {**_document(), "chunks": [{"name": "invoice", "symbol": "invoice",
                                          "kind": "FUNCTION", "start_line": 1, "end_line": 2}]}
    unindexed = {"path": "src/unindexed.py", "size": 12, "modified_ns": 7}
    responses = _run(tmp_path / "catalog.sqlite3", [
        _begin(extra="ignored"), {"op": "apply", "removed": [], "documents": [document, unindexed]},
        {"op": "commit"}, _search("invoice", 1) | {"chunks": True},
        {"op": "paths", "prefix": "src", "limit": 10, "expected_revision": 1},
        {"op": "frequencies", "terms": ["billing"], "expected_revision": 1},
        {"op": "total", "expected_revision": 1}, {"op": "files"},
        _search("billing", 1) | {"limit": 2**64 - 1}])
    assert responses[3]["result"][0]["symbol"] == "invoice"
    assert responses[4]["result"] == ["src/invoice.py", "src/unindexed.py"]
    assert responses[5]["result"] == {"total": 1, "terms": {"billing": 1}}
    assert responses[6]["result"] == 1
    assert responses[7]["result"] == [
        {"path": "src/invoice.py", "size": 200, "modified_ns": 1234}, unindexed]
    assert responses[8]["result"][0]["file_path"] == "src/invoice.py"


def test_service_scan_and_changes_keep_the_manifest_contract(tmp_path):
    root = tmp_path / "workspace"
    source = root / "src/invoice.py"
    source.parent.mkdir(parents=True)
    source.write_text("def invoice(): return 'billing'\n", encoding="utf-8")
    metadata = source.stat()
    entry = {"path": "src/invoice.py", "size": metadata.st_size, "modified_ns": metadata.st_mtime_ns}
    options = {"root": str(root), "options": {"extensions": ["py"], "rules": []}}
    database = tmp_path / "catalog.sqlite3"
    responses = _run(database, [
        _begin(), {"op": "apply", "removed": [], "documents": [{**entry, "body": "billing"}]},
        {"op": "commit"}, {"op": "scan", **options},
        {"op": "changes", "expected_revision": 1, **options}])
    assert responses[3]["result"] == [entry]
    assert responses[4]["result"] == [[], []]
    source.rename(root / "src/renamed.py")
    changes = _run(database, [{"op": "changes", "expected_revision": 1, **options}])[0]["result"]
    assert changes == [[{**entry, "path": "src/renamed.py"}], ["src/invoice.py"]]
