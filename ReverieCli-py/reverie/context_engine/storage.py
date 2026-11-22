"""Python index storage used directly by the CLI, SDK and desktop kernel."""

import os
from pathlib import Path

from .catalog import Catalog
from .indexer import CodebaseIndexer


class PythonContext:
    def __init__(self, root, cache_dir, *, database=None, scanner=None):
        self.root = Path(root).resolve()
        self.identity = os.path.normcase(str(self.root))
        self.database = Path(database).resolve() if database else Path(cache_dir).resolve() / "python-search.sqlite3"
        self.revision = None
        self.writing = False
        self._catalog = Catalog(self.database, scanner=scanner)

    def request(self, operation, **fields):
        return self._catalog.request(operation, **fields)

    def close(self):
        self._catalog.close()

    def attach(self, revision):
        if not revision or not self.database.is_file():
            return False
        if self.request("state") != {"root": self.identity, "revision": revision}:
            return False
        self.revision = revision
        return True

    def scan(self, rules, extensions, *, incremental):
        fields = {"root": str(self.root), "options": {"extensions": sorted(extensions), "rules": list(rules)}}
        if incremental:
            return self.request("changes", expected_revision=self.revision, **fields)
        return self.request("scan", **fields), []

    def begin(self, *, replace, expected_revision):
        self.request("begin", root=self.identity, replace=replace, expected_revision=expected_revision)
        self.writing = True

    def remove(self, path):
        self.request("apply", removed=[Path(path).relative_to(self.root).as_posix()], documents=[])

    def document(self, path, size, modified_ns, body, symbols=()):
        chunks = []
        for symbol in list(symbols)[:512] if body is not None else ():
            if CodebaseIndexer._symbol_search_fields(symbol) is None:
                continue
            chunks.append({"name": symbol.name, "symbol": symbol.qualified_name or symbol.name,
                           "kind": symbol.kind.name, "start_line": max(1, symbol.start_line or 1),
                           "end_line": max(1, symbol.end_line or symbol.start_line or 1),
                           "signature": symbol.signature or "", "documentation": symbol.docstring or "",
                           "body": symbol.source_code or ""})
        self.request("apply", removed=[], documents=[{
            "path": Path(path).relative_to(self.root).as_posix(), "size": size,
            "modified_ns": modified_ns, "body": body, "chunks": chunks,
        }])

    def commit(self):
        self.revision = self.request("commit")["revision"]
        self.writing = False

    def rollback(self):
        if self.writing:
            self.writing = False
            self.request("rollback")

    def hits(self, weights, limit, *, chunks):
        if not self.revision:
            return None
        hits = self.request("search", weights=weights, limit=max(1, limit), chunks=chunks,
                            expected_revision=self.revision)
        for hit in hits:
            hit["file_path"] = str(self.root / hit["file_path"])
        return hits
