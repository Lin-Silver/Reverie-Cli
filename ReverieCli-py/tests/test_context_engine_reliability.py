from pathlib import Path

from reverie.context_engine.cache import CacheManager
from reverie.context_engine.dependency_graph import DependencyGraph
from reverie.context_engine.indexer import CodebaseIndexer
from reverie.context_engine.symbol_table import SymbolTable
from reverie.diagnostics import (
    clear_recovery_diagnostics,
    get_recent_recovery_diagnostics,
    report_suppressed_exception,
)


def test_indexer_applies_gitignore_anchors_negations_and_generated_directories(tmp_path: Path) -> None:
    (tmp_path / ".gitignore").write_text(
        "/root_only.py\n*.tmp\n!important.tmp\nbuild/\n!/app/build/\n!/app/build/keep.py\n",
        encoding="utf-8",
    )
    files = {
        "root_only.py": "ROOT = True\n",
        "nested/root_only.py": "NESTED = True\n",
        "discard.tmp": "discard\n",
        "nested/important.tmp": "keep\n",
        "build/drop.py": "DROP = True\n",
        "app/build/keep.py": "KEEP = True\n",
        ".runtime/generated.py": "GENERATED = True\n",
        ".kernel/generated.py": "GENERATED = True\n",
        "release/generated.py": "GENERATED = True\n",
    }
    for relative, content in files.items():
        path = tmp_path / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")

    indexed = {
        path.relative_to(tmp_path).as_posix()
        for path in CodebaseIndexer(tmp_path, cache_dir=tmp_path / ".cache-data").scan_files()
    }

    assert "nested/root_only.py" in indexed
    assert "app/build/keep.py" in indexed
    assert "root_only.py" not in indexed
    assert "build/drop.py" not in indexed
    assert not any(path.startswith((".runtime/", ".kernel/", "release/")) for path in indexed)


def test_cache_is_rejected_before_loading_when_ignore_rules_change(tmp_path: Path) -> None:
    cache_dir = tmp_path / "cache"
    first = CodebaseIndexer(tmp_path, cache_dir=cache_dir)
    assert first.save_cache()

    (tmp_path / ".gitignore").write_text("generated/\n", encoding="utf-8")
    second = CodebaseIndexer(tmp_path, cache_dir=cache_dir)

    assert second.load_cache() is False


def test_refresh_removes_deleted_and_renamed_paths_from_search(tmp_path: Path) -> None:
    root = tmp_path / "project"
    root.mkdir()
    deleted = root / "obsolete.py"
    deleted.write_text("class ObsoleteBeacon:\n    pass\n", encoding="utf-8")
    original = root / "original.py"
    original.write_text("class TransferBeacon:\n    pass\n", encoding="utf-8")
    cache = tmp_path / "cache"
    indexer = CodebaseIndexer(root, cache_dir=cache)
    assert indexer.full_index(show_progress=False).files_parsed == 2
    assert len(indexer.search_content_terms([("beacon", 1.0)])) == 2

    deleted.unlink()
    renamed = root / "renamed.py"
    original.rename(renamed)
    assert indexer.refresh().files_parsed == 1

    reloaded = CodebaseIndexer(root, cache_dir=cache)
    assert reloaded.load_cache()
    assert {Path(hit["file_path"]) for hit in reloaded.search_content_terms([("beacon", 1.0)])} == {renamed}
    assert {Path(hit["file_path"]) for hit in reloaded.search_code_chunks([("beacon", 1.0)])} == {renamed}
    assert reloaded.content_document_total() == 1
    assert not reloaded.get_file_symbols(str(deleted))
    assert not reloaded.get_file_symbols(str(original))
    assert reloaded.get_file_symbols(str(renamed))


def test_refresh_without_changes_leaves_cache_files_unchanged(tmp_path: Path) -> None:
    root = tmp_path / "project"
    root.mkdir()
    (root / "entry.py").write_text("def main():\n    pass\n", encoding="utf-8")
    cache = tmp_path / "cache"
    indexer = CodebaseIndexer(root, cache_dir=cache)
    assert indexer.full_index(show_progress=False).files_parsed == 1
    before = {path.name: (path.stat().st_mtime_ns, path.read_bytes()) for path in cache.iterdir()}

    assert indexer.refresh().files_parsed == 0

    assert {path.name: (path.stat().st_mtime_ns, path.read_bytes()) for path in cache.iterdir()} == before
    assert indexer.get_index_status()["stage"] == "complete"


def test_full_index_accepts_utf8_source_with_a_split_sample_character(tmp_path: Path) -> None:
    source = tmp_path / "localized.py"
    source.write_text("#" + "中文" * 2000 + "\nclass LocalizedWidget:\n    pass\n", encoding="utf-8")
    disguised_binary = tmp_path / "disguised.py"
    disguised_binary.write_bytes(b"\xff" * 100)
    indexer = CodebaseIndexer(tmp_path, cache_dir=tmp_path / "cache")

    result = indexer.full_index(show_progress=False)

    assert result.files_parsed == 1
    assert result.files_skipped == 1
    assert {Path(hit["file_path"]) for hit in indexer.search_content_terms([("widget", 1.0)])} == {source}


def test_corrupt_cache_records_a_structured_recovery_diagnostic(tmp_path: Path) -> None:
    clear_recovery_diagnostics()
    manager = CacheManager(tmp_path)
    assert manager.save(SymbolTable(), DependencyGraph(), {})
    manager.symbols_path.write_bytes(b"not-gzip")

    assert manager.load() is None
    events = get_recent_recovery_diagnostics()

    assert events
    assert events[0]["operation"].startswith("load compressed Context Engine cache file")
    assert events[0]["exception_type"]
    assert events[0]["count"] == 1


def test_recovery_diagnostics_deduplicate_repeated_failures() -> None:
    clear_recovery_diagnostics()
    for _ in range(2):
        try:
            raise ValueError("same failure")
        except ValueError:
            report_suppressed_exception("optional probe")

    events = get_recent_recovery_diagnostics()

    assert len(events) == 1
    assert events[0]["operation"] == "optional probe"
    assert events[0]["exception_type"] == "ValueError"
    assert events[0]["message"] == "same failure"
    assert events[0]["count"] == 2
