import json
from pathlib import Path
import subprocess
from types import SimpleNamespace

import pytest

from reverie.context_engine import CodebaseIndexer, ContextRetriever, IndexConfig
from reverie.context_engine.native import NativeContextError, find_executable
from reverie.context_engine.native_indexer import NativeCodebaseIndexer
from reverie.cli.interface import ReverieInterface


@pytest.fixture
def native_executable():
    executable = find_executable()
    if executable is None:
        pytest.skip("Build the Rust Context Engine with scripts/prepare_context_engine.py")
    return executable


def test_standalone_indexes_searches_and_removes_files(tmp_path, native_executable):
    root = tmp_path / "工作区"
    src = root / "src"
    src.mkdir(parents=True)
    ignored = root / "generated"
    ignored.mkdir()
    (root / ".gitignore").write_text("generated/\n", encoding="utf-8")
    (ignored / "skip.py").write_text("def PrivateGenerated(): pass\n", encoding="utf-8")
    python_source = src / "invoice.py"
    python_source.write_text(
        "#" + "中文" * 2000 + "\nclass RemoteInvoice:\n    def validatePayload(self):\n        return True\n",
        encoding="utf-8",
    )
    typescript = src / "checkout.tsx"
    typescript.write_text("export function CheckoutPanel() { return <div />; }\n", encoding="utf-8")
    (src / "engine.rs").write_text("pub struct RuntimeCatalog;\n", encoding="utf-8")
    database = tmp_path / "index.sqlite3"

    def run(*arguments):
        completed = subprocess.run([native_executable, *arguments], capture_output=True, encoding="utf-8", check=True)
        return json.loads(completed.stdout)

    first = run("index", root, database)
    assert first["indexed"] == 3
    unchanged = run("index", root, database)
    assert unchanged["indexed"] == 0 and unchanged["revision"] == first["revision"]
    assert run("search", database, "PrivateGenerated") == []
    assert run("paths", database, "src/check") == ["src/checkout.tsx"]
    python_hit = run("chunks", database, "validatePayload")[0]
    assert (python_hit["symbol"], python_hit["start_line"]) == ("src.invoice.RemoteInvoice.validatePayload", 3)
    assert run("chunks", database, "CheckoutPanel")[0]["symbol"] == "src.checkout.CheckoutPanel"
    assert run("chunks", database, "RuntimeCatalog")[0]["kind"] == "STRUCT"

    python_source.rename(src / "transaction.py")
    typescript.unlink()
    changed = run("index", root, database)
    assert changed["indexed"] == 1 and changed["removed"] == 2
    assert run("search", database, "CheckoutPanel") == []
    assert run("chunks", database, "validatePayload")[0]["file_path"] == "src/transaction.py"


def _workspace(tmp_path):
    root = tmp_path / "workspace"
    (root / "app" / "build").mkdir(parents=True)
    (root / ".gitignore").write_text("build/\n!/app/build/keep.py\n", encoding="utf-8")
    (root / ".reverieignore").write_text("/unindexed.py\n", encoding="utf-8")
    (root / "unindexed.py").write_text("SKIPPED = True\n", encoding="utf-8")
    (root / "app" / "build" / "keep.py").write_text("def RenderCache():\n    return 'cache'\n", encoding="utf-8")
    (root / "app" / "build" / "hidden.py").write_text("def PrivateSource():\n    pass\n", encoding="utf-8")
    (root / "alpha.py").write_text("class PipelineGuard:\n    def validateInvoice(self):\n        return 'billing epoch'\n", encoding="utf-8")
    (root / "binary.py").write_bytes(b"\x00binary")
    return root


def test_application_native_index_preserves_hits_and_ignores(tmp_path, native_executable):
    root = _workspace(tmp_path)
    native = NativeCodebaseIndexer(root, tmp_path / "native", config=IndexConfig(max_workers=2), executable=native_executable)
    python = CodebaseIndexer(root, tmp_path / "python", config=IndexConfig(max_workers=2))
    try:
        assert set(native.scan_files()) == set(python.scan_files())
        assert native.full_index(show_progress=False).files_parsed == python.full_index(show_progress=False).files_parsed == 2
        assert set(native._file_info) == set(python._file_info)
        assert native.get_index_status()["backend"] == "rust"
        assert native._native.database.is_file()
        weights = [("validateInvoice", 2.0), ("billing", 1.0), ("cache", 0.7)]
        assert native.search_content_terms(weights) == python.search_content_terms(weights)
        assert native.search_code_chunks(weights) == python.search_code_chunks(weights)
        assert native.content_document_frequencies(["invoice", "billing"]) == {"invoice": 0, "billing": 1}
        assert native.content_document_total() == python.content_document_total() == 2
        assert native.search_content_terms([("PrivateSource", 1.0)]) == []
        retriever = ContextRetriever(
            native.symbol_table, native.dependency_graph, root, file_info=native._file_info,
            content_searcher=native.search_content_terms, chunk_searcher=native.search_code_chunks,
            content_frequency=native.content_document_frequencies, content_total=native.content_document_total,
        )
        answer = retriever.retrieve_for_task("定位 PipelineGuard 和 validateInvoice 的实现", fast=True)
        assert Path(answer.relevant_files[0].file_path).name == "alpha.py"
    finally:
        native.close()

    reloaded = NativeCodebaseIndexer(root, tmp_path / "native", executable=native_executable)
    try:
        assert reloaded.load_cache()
        revision = reloaded.get_index_status()["revision"]
        manifest = reloaded._cache_manager.index_path
        before = manifest.stat().st_mtime_ns
        result = reloaded.refresh()
        assert result.success and result.files_scanned == 0
        assert reloaded.get_index_status()["revision"] == revision
        assert manifest.stat().st_mtime_ns == before

        retriever = ContextRetriever(
            reloaded.symbol_table, reloaded.dependency_graph, root, file_info=reloaded._file_info,
            content_searcher=reloaded.search_content_terms, chunk_searcher=reloaded.search_code_chunks,
        )
        query = "Locate the PipelineGuard validateInvoice implementation"
        before_rename = retriever.retrieve_for_task(query, fast=True)
        assert Path(before_rename.relevant_files[0].file_path).name == "alpha.py"
        (root / "alpha.py").rename(root / "beta.py")
        result = reloaded.refresh()
        assert result.success and result.files_parsed == 1
        assert reloaded.get_index_status()["revision"] == revision + 1
        assert reloaded.search_code_chunks([("invoice", 1.0)])[0]["file_path"] == str(root / "beta.py")
        assert str(root / "alpha.py") not in reloaded._file_info
        after_rename = retriever.retrieve_for_task(query, fast=True)
        assert Path(after_rename.relevant_files[0].file_path).name == "beta.py"
    finally:
        reloaded.close()


def test_failed_native_write_preserves_the_previous_generation(tmp_path, native_executable, monkeypatch):
    root = _workspace(tmp_path)
    indexer = NativeCodebaseIndexer(root, tmp_path / "native", executable=native_executable)
    try:
        assert indexer.full_index(show_progress=False).success
        version = indexer.get_index_status()["revision"]
        previous = indexer.search_content_terms([("billing", 1.0)])
        assert previous
        request = indexer._native.request

        def fail_commit(operation, **kwargs):
            if operation == "commit":
                raise NativeContextError("Injected commit failure")
            return request(operation, **kwargs)

        (root / "alpha.py").write_text("class LocalTransport:\n    pass\n", encoding="utf-8")
        with monkeypatch.context() as patch:
            patch.setattr(indexer._native, "request", fail_commit)
            result = indexer.refresh()
        assert not result.success
        assert indexer.get_index_status()["revision"] == version
        assert indexer.search_content_terms([("billing", 1.0)]) == previous
        assert indexer.search_content_terms([("transport", 1.0)]) == []
        assert indexer.refresh().success
        assert indexer.search_content_terms([("billing", 1.0)]) == []
        assert indexer.search_content_terms([("transport", 1.0)])
    finally:
        indexer.close()


def test_competing_writer_rejects_an_old_full_scan_and_keeps_snapshots_separate(tmp_path, native_executable, monkeypatch):
    root = _workspace(tmp_path)
    cache = tmp_path / "native"
    first = NativeCodebaseIndexer(root, cache, executable=native_executable)
    second = NativeCodebaseIndexer(root, cache, executable=native_executable)
    try:
        assert first.full_index(show_progress=False).success
        assert second.load_cache()
        previous = first._cache_manager.index_path
        original_scan = first.scan_files

        def scan_then_commit(*args, **kwargs):
            candidates = original_scan(*args, **kwargs)
            added = root / "later.py"
            added.write_text("class LaterTransport:\n    pass\n", encoding="utf-8")
            assert second.update_file(added).success
            return candidates

        with monkeypatch.context() as patch:
            patch.setattr(first, "scan_files", scan_then_commit)
            conflict = first.full_index(show_progress=False)
        assert not conflict.success
        assert "changed while preparing" in conflict.fatal_errors[0]
        assert first.search_content_terms([("transport", 1.0)]) is None
        assert second.search_content_terms([("transport", 1.0)])
        assert second._cache_manager.index_path != previous
        assert previous.is_file() and second._cache_manager.index_path.is_file()
        assert first.refresh().success
        assert first.search_content_terms([("transport", 1.0)])
        assert first.get_file_symbols(str(root / "later.py"))
    finally:
        first.close()
        second.close()


def test_clean_releases_the_live_native_database_before_purging(tmp_path, native_executable, monkeypatch):
    root = _workspace(tmp_path)
    indexer = NativeCodebaseIndexer(root, tmp_path / "native", executable=native_executable)
    interface = ReverieInterface.__new__(ReverieInterface)
    interface.project_root = root
    interface.project_data_dir = tmp_path / "native"
    interface.indexer = indexer
    interface.config_manager = SimpleNamespace(ensure_dirs=lambda: None)
    interface.session_manager = SimpleNamespace(get_current_session=lambda: None)
    interface._init_workspace_services = lambda: None
    interface._init_agent = lambda: None
    interface._init_session = lambda: None
    interface._refresh_command_context = lambda: None

    def purge(project_root, project_data_dir):
        assert indexer._native._process is None
        indexer._native.database.rename(project_data_dir / "released.sqlite3")
        return {"errors": []}

    monkeypatch.setattr("reverie.security_utils.purge_workspace_state", purge)
    monkeypatch.setattr("reverie.security_utils.collect_workspace_cleanup_targets", lambda *args: [])
    try:
        assert indexer.full_index(show_progress=False).success
        assert interface.clean_workspace_state()["success"]
    finally:
        indexer.close()
