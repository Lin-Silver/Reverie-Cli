from pathlib import Path
import json
import sqlite3

from reverie.context_engine.cache import CacheManager
from reverie.context_engine.compressor import (
    ContextCompressor,
    MEMORY_BLOCK_HEADER,
    _build_compression_transcript,
)
from reverie.context_engine.dependency_graph import DependencyGraph, DependencyType
from reverie.context_engine.fast_context import FastContextExplorer
from reverie.context_engine.fragments import make_context_fragment, render_context_fragments
from reverie.context_engine.indexer import CodebaseIndexer, FileInfo, IndexConfig
from reverie.context_engine.parsers.base import ParseResult
from reverie.context_engine.parsers.config_parser import ConfigParser
from reverie.context_engine.retriever import ContextRetriever, TaskContextFile
from reverie.context_engine.symbol_table import Symbol, SymbolKind, SymbolTable
from reverie.context_engine.workspace import detect_workspace_profile
from reverie.session.memory_indexer import MemoryIndexer
from reverie.tools.codebase_retrieval import CodebaseRetrievalTool


def test_task_context_prioritizes_file_and_symbol_anchors(tmp_path: Path) -> None:
    target = tmp_path / "reverie" / "context_engine" / "retriever.py"
    target.parent.mkdir(parents=True)
    target.write_text(
        "class ContextRetriever:\n"
        "    def retrieve_for_task(self, query):\n"
        "        return query\n",
        encoding="utf-8",
    )
    other = tmp_path / "docs" / "retrieval.md"
    other.parent.mkdir()
    other.write_text("retrieval context documentation\n", encoding="utf-8")

    table = SymbolTable()
    symbol = Symbol(
        name="ContextRetriever",
        qualified_name="reverie.context_engine.retriever.ContextRetriever",
        kind=SymbolKind.CLASS,
        file_path=str(target),
        start_line=1,
        end_line=3,
        source_code=target.read_text(encoding="utf-8"),
        language="python",
    )
    table.add_symbol(symbol)
    file_info = {
        str(target): FileInfo(
            path=str(target),
            mtime=1,
            size=target.stat().st_size,
            content_hash="a",
            language="python",
            symbol_names=["ContextRetriever", "retrieve_for_task"],
            top_level_symbols=[symbol.qualified_name],
            keywords=["context", "retriever", "task"],
            tags=["engine"],
            summary="engine module retriever.py defines ContextRetriever",
        ),
        str(other): FileInfo(
            path=str(other),
            mtime=1,
            size=other.stat().st_size,
            content_hash="b",
            language="markdown",
            keywords=["retrieval", "context"],
            tags=["docs"],
            summary="documentation about retrieval",
        ),
    }
    retriever = ContextRetriever(table, DependencyGraph(), tmp_path, file_info=file_info)

    result = retriever.retrieve_for_task(
        "Optimize ContextRetriever in retriever.py for Context Engine",
        max_files=2,
        max_symbols=4,
        max_tokens=4000,
    )

    assert result.relevant_files[0].file_path == str(target)
    assert result.relevant_symbols[0].qualified_name == symbol.qualified_name
    assert "anchor-file:retriever.py" in result.relevant_files[0].reasons


def test_task_context_includes_workspace_instructions_and_evidence(tmp_path: Path) -> None:
    (tmp_path / "AGENTS.md").write_text("Always inspect Context Engine evidence first.\n", encoding="utf-8")
    (tmp_path / "pyproject.toml").write_text("[project]\nname='demo'\n", encoding="utf-8")
    target = tmp_path / "src" / "engine.py"
    target.parent.mkdir()
    target.write_text(
        "class EvidenceAssembler:\n"
        "    def build_workset(self):\n"
        "        return 'context engine workset evidence'\n",
        encoding="utf-8",
    )

    table = SymbolTable()
    symbol = Symbol(
        name="EvidenceAssembler",
        qualified_name="src.engine.EvidenceAssembler",
        kind=SymbolKind.CLASS,
        file_path=str(target),
        start_line=1,
        end_line=3,
        source_code=target.read_text(encoding="utf-8"),
        language="python",
    )
    table.add_symbol(symbol)
    file_info = {
        str(target): FileInfo(
            path=str(target),
            mtime=1,
            size=target.stat().st_size,
            content_hash="a",
            language="python",
            symbol_names=["EvidenceAssembler", "build_workset"],
            top_level_symbols=[symbol.qualified_name],
            keywords=["context", "engine", "workset", "evidence"],
            tags=["engine"],
            summary="Context Engine evidence workset assembly",
        )
    }

    retriever = ContextRetriever(table, DependencyGraph(), tmp_path, file_info=file_info)
    result = retriever.retrieve_for_task("Build Context Engine evidence workset", max_files=2, max_symbols=4)

    assert result.workspace_profile is not None
    assert result.workspace_profile.languages == ["python"]
    assert result.workspace_profile.instruction_layers
    assert "PROJECT INSTRUCTIONS" in result.context_string
    assert "Always inspect Context Engine evidence first" in result.context_string
    assert result.relevant_files[0].evidence
    assert "index" in result.metadata["evidence_sources"]


def test_fast_task_recommendations_expand_chinese_intent_without_building_prompt_context(tmp_path: Path) -> None:
    target = tmp_path / "reverie" / "context_engine" / "compressor.py"
    target.parent.mkdir(parents=True)
    target.write_text("def compress_context():\n    return 'compact memory'\n", encoding="utf-8")
    decoy = tmp_path / "ui" / "panel.py"
    decoy.parent.mkdir()
    decoy.write_text("def render_panel():\n    return 'panel'\n", encoding="utf-8")
    file_info = {
        str(target): FileInfo(
            path=str(target),
            mtime=target.stat().st_mtime,
            size=target.stat().st_size,
            content_hash="a",
            language="python",
            keywords=["context", "compression", "memory"],
            tags=["engine"],
            summary="Context compression and memory compaction",
        ),
        str(decoy): FileInfo(
            path=str(decoy),
            mtime=decoy.stat().st_mtime,
            size=decoy.stat().st_size,
            content_hash="b",
            language="python",
            keywords=["ui"],
            tags=["ui"],
            summary="Desktop panel rendering",
        ),
    }
    table = SymbolTable()
    retriever = ContextRetriever(table, DependencyGraph(), tmp_path, file_info=file_info)

    result = retriever.retrieve_for_task(
        "优化上下文引擎压缩速度和推荐检索",
        max_files=2,
        max_symbols=2,
        include_history=False,
        include_memory=False,
        fast=True,
    )

    assert result.relevant_files[0].file_path == str(target)
    assert result.context_string == ""
    assert result.token_estimate == 0
    assert result.metadata["fast"] is True
    assert result.metadata["term_weights"]["compression"] > 0


def test_task_query_tokens_keep_ui_terms_and_drop_stopwords(tmp_path: Path) -> None:
    retriever = ContextRetriever(SymbolTable(), DependencyGraph(), tmp_path)

    tokens = retriever._tokenize_query("Improve UI UX and the Context Engine")
    anchors = retriever._extract_query_anchors("Optimize ContextRetriever in Context Engine")

    assert "ui" in tokens
    assert "ux" in tokens
    assert "and" not in tokens
    assert "the" not in tokens
    assert anchors["symbols"] == ["ContextRetriever"]


def test_task_query_builds_compound_terms_for_code_filenames(tmp_path: Path) -> None:
    retriever = ContextRetriever(SymbolTable(), DependencyGraph(), tmp_path)

    weights = retriever._build_task_term_weights(
        "Duplicate Symbols sections appear for index entries"
    )

    assert weights["indexentries"] > 1.0
    assert weights["symbolssections"] > 1.0


def test_query_anchors_reject_versions_and_dotted_symbols(tmp_path: Path) -> None:
    retriever = ContextRetriever(SymbolTable(), DependencyGraph(), tmp_path)

    anchors = retriever._extract_query_anchors(
        "In 4.2, routing.TelemetryCoordinator fails; inspect src/routing/coordinator.ts:42"
    )

    assert anchors["files"] == ["src/routing/coordinator.ts"]
    assert "4.2" not in anchors["files"]
    assert "routing.TelemetryCoordinator" in anchors["symbols"]
    assert retriever._path_matches_file_anchor("tests/test.py", "test.py") is True
    assert retriever._path_matches_file_anchor("tests/configuration_test.py", "test.py") is False


def test_fast_task_uses_exact_symbol_before_file_cutoff(tmp_path: Path, monkeypatch) -> None:
    target = tmp_path / "src" / "coordinator.ts"
    target.parent.mkdir()
    target.write_text("export class TelemetryCoordinator {}\n", encoding="utf-8")
    table = SymbolTable()
    table.add_symbol(
        Symbol(
            name="TelemetryCoordinator",
            qualified_name="src.coordinator.TelemetryCoordinator",
            kind=SymbolKind.CLASS,
            file_path=str(target),
            start_line=1,
            end_line=2,
            language="typescript",
        )
    )
    file_info = {
        str(target): FileInfo(
            path=str(target), mtime=1, size=target.stat().st_size, content_hash="target", language="typescript"
        )
    }
    for index in range(12):
        decoy = tmp_path / "docs" / f"telemetry_{index}.md"
        decoy.parent.mkdir(exist_ok=True)
        decoy.write_text("telemetry parameter behavior", encoding="utf-8")
        file_info[str(decoy)] = FileInfo(
            path=str(decoy),
            mtime=1,
            size=decoy.stat().st_size,
            content_hash=str(index),
            language="markdown",
            keywords=["telemetry", "parameter", "behavior"],
            tags=["docs"],
            summary="Telemetry parameter behavior documentation",
        )
    retriever = ContextRetriever(table, DependencyGraph(), tmp_path, file_info=file_info)
    monkeypatch.setattr(retriever, "_run_targeted_content_search", lambda *_args, **_kwargs: [])

    result = retriever.retrieve_for_task(
        "TelemetryCoordinator parameter behavior",
        max_files=1,
        max_symbols=1,
        include_history=False,
        include_memory=False,
        fast=True,
    )

    assert result.relevant_files[0].file_path == str(target)
    assert "anchor-symbol:telemetrycoordinator" in result.relevant_files[0].reasons


def test_targeted_content_search_finds_rare_identifiers_across_languages(tmp_path: Path) -> None:
    cases = [
        ("python", "worker.py", "lease_generation_token", "lease renewal failed"),
        ("typescript", "renderer.ts", "renderEpochFence", "renderer state is stale"),
        ("rust", "scheduler.rs", "borrow_epoch_guard", "scheduler retries forever"),
    ]
    paths = []
    for language, filename, identifier, _ in cases:
        target = tmp_path / "src" / filename
        target.parent.mkdir(exist_ok=True)
        target.write_text(f"const marker = '{identifier}'\n", encoding="utf-8")
        paths.append((language, target))
    decoy = tmp_path / "src" / "common.ts"
    decoy.write_text("export const marker = 'ordinary_state'\n", encoding="utf-8")
    paths.append(("typescript", decoy))
    file_info = {
        str(path): FileInfo(
            path=str(path), mtime=1, size=path.stat().st_size, content_hash=path.stem, language=language
        )
        for language, path in paths
    }
    retriever = ContextRetriever(SymbolTable(), DependencyGraph(), tmp_path, file_info=file_info)

    for _, filename, identifier, title in cases:
        query = f"{title}\nRuntime evidence mentions `{identifier}`"
        weights = retriever._calibrate_task_term_weights(retriever._build_task_term_weights(query))
        hits = retriever._run_targeted_content_search(query, weights, limit=5)

        assert Path(hits[0]["file_path"]).name == filename
        assert identifier.lower() in hits[0]["terms"]


def test_query_weights_ignore_verbose_fenced_output(tmp_path: Path) -> None:
    retriever = ContextRetriever(SymbolTable(), DependencyGraph(), tmp_path)

    weights = retriever._build_task_term_weights(
        "Scheduler renewal loses lease state\n"
        "The inline `LeaseCoordinator` should preserve its generation.\n"
        "```text\nTransientOutputWidget generated_marker_9281\n```\n"
    )

    assert "scheduler" in weights
    assert "leasecoordinator" in weights
    assert "generated_marker_9281" not in weights
    assert "transientoutputwidget" not in weights


def test_ambiguous_basename_file_anchors_are_not_trusted(tmp_path: Path) -> None:
    paths = [
        tmp_path / "src" / "engine.py",
        tmp_path / "alpha" / "__init__.py",
        tmp_path / "beta" / "__init__.py",
    ]
    for path in paths:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("value = 1\n", encoding="utf-8")
    file_info = {
        str(path): FileInfo(
            path=str(path), mtime=1, size=path.stat().st_size, content_hash=path.parent.name
        )
        for path in paths
    }
    retriever = ContextRetriever(SymbolTable(), DependencyGraph(), tmp_path, file_info=file_info)

    reliable = retriever._reliable_file_anchor_terms({"engine.py", "__init__.py"})

    assert reliable == {"engine.py"}


def test_stack_trace_file_anchors_resolve_unique_workspace_suffixes(tmp_path: Path) -> None:
    target = tmp_path / "pylint" / "reporters" / "text.py"
    target.parent.mkdir(parents=True)
    target.write_text("class TextReporter:\n    pass\n", encoding="utf-8")
    file_info = {
        str(target): FileInfo(
            path=str(target), mtime=1, size=target.stat().st_size, content_hash="target"
        )
    }
    retriever = ContextRetriever(SymbolTable(), DependencyGraph(), tmp_path, file_info=file_info)

    reliable = retriever._reliable_file_anchor_terms({
        "/home/user/.venv/lib/python3.12/site-packages/pylint/reporters/text.py"
    })

    assert reliable == {"pylint/reporters/text.py"}


def test_file_scoring_ignores_workspace_parent_names_and_unsafe_short_terms(tmp_path: Path) -> None:
    project_root = tmp_path / "snapshots" / "os" / "project"
    target = project_root / "src" / "plain.py"
    target.parent.mkdir(parents=True)
    target.write_text("answer = 42\n", encoding="utf-8")
    info = FileInfo(path=str(target), mtime=1, size=target.stat().st_size, content_hash="plain")
    retriever = ContextRetriever(
        SymbolTable(), DependencyGraph(), project_root, file_info={str(target): info}
    )

    candidate = retriever._score_file_for_task(
        file_path=str(target),
        info=info,
        term_weights={"snapshots": 4.0, "os": 4.0, "t": 4.0},
        active_files=set(),
        changed_files=set(),
    )

    assert candidate is None


def test_test_module_neighborhood_recovers_matching_implementation_file(tmp_path: Path) -> None:
    source = tmp_path / "sympy" / "matrices" / "expressions" / "matexpr.py"
    test_file = source.parent / "tests" / "test_matexpr.py"
    source.parent.mkdir(parents=True)
    test_file.parent.mkdir()
    source.write_text("class MatrixExpr:\n    pass\n", encoding="utf-8")
    test_file.write_text("def test_identity_sum():\n    pass\n", encoding="utf-8")
    file_info = {
        str(path): FileInfo(
            path=str(path), mtime=1, size=path.stat().st_size, content_hash=path.stem
        )
        for path in (source, test_file)
    }
    retriever = ContextRetriever(
        SymbolTable(), DependencyGraph(), tmp_path, file_info=file_info
    )
    seed = TaskContextFile(
        file_path=str(test_file),
        language="python",
        score=10.0,
        summary="identity matrix behavior",
        reasons=["chunk-match"],
    )

    hits = retriever._collect_test_source_hits([seed])

    assert hits[0]["file_path"] == str(source)
    assert hits[0]["reason"] == "test-source:test_matexpr.py->matexpr.py"


def test_test_module_neighborhood_supports_context_prefixed_test_names(tmp_path: Path) -> None:
    source = tmp_path / "sphinx" / "environment" / "adapters" / "indexentries.py"
    test_file = tmp_path / "tests" / "test_environment_indexentries.py"
    source.parent.mkdir(parents=True)
    test_file.parent.mkdir()
    source.write_text("def create_index_entries():\n    return []\n", encoding="utf-8")
    test_file.write_text("def test_duplicate_symbols():\n    pass\n", encoding="utf-8")
    file_info = {
        str(path): FileInfo(
            path=str(path), mtime=1, size=path.stat().st_size, content_hash=path.stem
        )
        for path in (source, test_file)
    }
    retriever = ContextRetriever(
        SymbolTable(), DependencyGraph(), tmp_path, file_info=file_info
    )

    hits = retriever._collect_test_source_hits([
        TaskContextFile(str(test_file), "python", 10.0, "duplicate symbols", ["chunk-match"])
    ])

    assert hits[0]["file_path"] == str(source)


def test_file_tags_ignore_workspace_parent_directory_names(tmp_path: Path) -> None:
    project_root = tmp_path / "engine-tools" / "Reverie-Cli" / "project"
    target = project_root / "src" / "plain.py"
    target.parent.mkdir(parents=True)
    target.write_text("value = 1\n", encoding="utf-8")
    indexer = CodebaseIndexer(project_root, cache_dir=tmp_path / "cache")

    tags = indexer._infer_file_tags(target, ParseResult(file_path=str(target), language="python"))

    assert "engine" not in tags
    assert "cli" not in tags


def test_content_search_index_persists_and_updates_full_file_terms(tmp_path: Path) -> None:
    target = tmp_path / "src" / "scheduler.py"
    target.parent.mkdir()
    target.write_text("def schedule():\n    return 'lease_epoch_guard'\n", encoding="utf-8")
    cache_dir = tmp_path / "cache"
    indexer = CodebaseIndexer(tmp_path, cache_dir=cache_dir)

    result = indexer.full_index(show_progress=False)
    initial_hits = indexer.search_content_terms([("lease_epoch_guard", 1.0)], limit=5)

    assert result.success is True
    assert initial_hits is not None
    assert initial_hits[0]["file_path"] == str(target)

    cached_indexer = CodebaseIndexer(tmp_path, cache_dir=cache_dir)
    assert cached_indexer.load_cache() is True
    persisted_hits = cached_indexer.search_content_terms([("lease_epoch_guard", 1.0)], limit=5)
    assert persisted_hits is not None
    assert persisted_hits[0]["file_path"] == str(target)

    target.write_text("def schedule():\n    return 'renewal_generation_fence'\n", encoding="utf-8")
    cached_indexer.incremental_index([target.resolve()])

    assert cached_indexer.search_content_terms([("lease_epoch_guard", 1.0)], limit=5) == []
    updated_hits = cached_indexer.search_content_terms([("renewal_generation_fence", 1.0)], limit=5)
    assert updated_hits is not None
    assert updated_hits[0]["file_path"] == str(target.resolve())


def test_content_search_fuses_weighted_terms_and_reports_actual_matches(tmp_path: Path) -> None:
    target = tmp_path / "src" / "coordinator.py"
    decoy = tmp_path / "src" / "state.py"
    plural = tmp_path / "src" / "module_loader.py"
    target.parent.mkdir()
    target.write_text("marker = 'lease_generation_guard protects shared state'\n", encoding="utf-8")
    decoy.write_text("marker = 'state state state state state'\n", encoding="utf-8")
    plural.write_text("def expand_modules():\n    pass\n", encoding="utf-8")
    indexer = CodebaseIndexer(tmp_path, cache_dir=tmp_path / "cache")
    assert indexer.full_index(show_progress=False).success is True

    hits = indexer.search_content_terms(
        [("state", 0.2), ("lease_generation_guard", 4.0)],
        limit=5,
    )
    stemmed_hits = indexer.search_content_terms([("module", 1.0)], limit=5)

    assert hits is not None
    assert Path(hits[0]["file_path"]).name == "coordinator.py"
    assert "lease_generation_guard" in hits[0]["terms"]
    decoy_hit = next(hit for hit in hits if Path(hit["file_path"]).name == "state.py")
    assert decoy_hit["terms"] == ["state"]
    assert stemmed_hits is not None
    assert Path(stemmed_hits[0]["file_path"]).name == "module_loader.py"


def test_code_chunk_search_returns_relevant_symbol_and_line_range(tmp_path: Path) -> None:
    target = tmp_path / "src" / "coordinator.py"
    decoy = tmp_path / "src" / "state.py"
    target.parent.mkdir()
    target.write_text(
        "def renew_lease_generation(owner):\n"
        "    \"\"\"Protect ownership transfer with a monotonic generation fence.\"\"\"\n"
        "    return owner.rotate('generation_fence')\n",
        encoding="utf-8",
    )
    decoy.write_text("def update_state(state):\n    return state\n", encoding="utf-8")
    indexer = CodebaseIndexer(tmp_path, cache_dir=tmp_path / "cache")
    assert indexer.full_index(show_progress=False).success is True

    hits = indexer.search_code_chunks(
        [("ownership", 1.0), ("generation_fence", 4.0), ("state", 0.2)],
        limit=8,
    )

    assert hits is not None
    assert Path(hits[0]["file_path"]).name == "coordinator.py"
    assert hits[0]["symbol"].endswith("renew_lease_generation")
    assert hits[0]["start_line"] == 1
    assert hits[0]["end_line"] == 3
    assert "generation_fence" in hits[0]["terms"]

    cached_indexer = CodebaseIndexer(tmp_path, cache_dir=tmp_path / "cache")
    assert cached_indexer.load_cache() is True
    persisted = cached_indexer.search_code_chunks([("generation_fence", 4.0)], limit=4)
    assert persisted and persisted[0]["symbol"].endswith("renew_lease_generation")

    target.write_text(
        "def renew_lease_generation(owner):\n"
        "    return owner.rotate('ownership_epoch')\n",
        encoding="utf-8",
    )
    cached_indexer.incremental_index([target.resolve()])
    assert cached_indexer.search_code_chunks([("generation_fence", 4.0)], limit=4) == []
    updated = cached_indexer.search_code_chunks([("ownership_epoch", 4.0)], limit=4)
    assert updated and updated[0]["symbol"].endswith("renew_lease_generation")
    with sqlite3.connect(cached_indexer._cache_manager.content_search_path) as connection:
        assert connection.execute("SELECT count(*) FROM content_search").fetchone()[0] == connection.execute(
            "SELECT count(*) FROM content_documents"
        ).fetchone()[0]
        assert connection.execute("SELECT count(*) FROM chunk_search").fetchone()[0] == connection.execute(
            "SELECT count(*) FROM chunk_documents"
        ).fetchone()[0]
        expected_payloads = connection.execute("SELECT count(*) FROM content_documents").fetchone()[0]
        expected_payloads += connection.execute("SELECT count(*) FROM chunk_documents").fetchone()[0]
        assert connection.execute("SELECT count(*) FROM fts_delete_payloads").fetchone()[0] == expected_payloads


def test_parallel_index_builds_produce_identical_tied_rankings(tmp_path: Path) -> None:
    source_root = tmp_path / "workspace"
    source_root.mkdir()
    for index in range(24):
        (source_root / f"module_{index:02d}.py").write_text(
            f"def handler_{index:02d}():\n    return 'shared_marker'\n",
            encoding="utf-8",
        )

    serial = CodebaseIndexer(
        source_root,
        cache_dir=tmp_path / "serial-cache",
        config=IndexConfig(max_workers=1),
    )
    parallel = CodebaseIndexer(
        source_root,
        cache_dir=tmp_path / "parallel-cache",
        config=IndexConfig(max_workers=8),
    )
    assert serial.full_index(show_progress=False).success is True
    assert parallel.full_index(show_progress=False).success is True

    weighted_terms = [("shared_marker", 3.0)]
    serial_content = serial.search_content_terms(weighted_terms, limit=12)
    parallel_content = parallel.search_content_terms(weighted_terms, limit=12)
    serial_chunks = serial.search_code_chunks(weighted_terms, limit=12)
    parallel_chunks = parallel.search_code_chunks(weighted_terms, limit=12)

    assert [item["file_path"] for item in serial_content or []] == [
        item["file_path"] for item in parallel_content or []
    ]
    assert [(item["file_path"], item["symbol"]) for item in serial_chunks or []] == [
        (item["file_path"], item["symbol"]) for item in parallel_chunks or []
    ]

    def retrieve(indexer: CodebaseIndexer) -> list[str]:
        result = ContextRetriever(
            indexer.symbol_table,
            indexer.dependency_graph,
            source_root,
            file_info=indexer._file_info,
            content_searcher=indexer.search_content_terms,
            chunk_searcher=indexer.search_code_chunks,
        ).retrieve_for_task(
            "Fix shared_marker handling",
            max_files=10,
            max_symbols=4,
            include_history=False,
            include_memory=False,
            fast=True,
        )
        return [item.file_path for item in result.relevant_files]

    assert retrieve(serial) == retrieve(parallel)


def test_dependency_resolution_qualifies_relative_import_calls(tmp_path: Path) -> None:
    package = tmp_path / "pkg"
    package.mkdir()
    (package / "__init__.py").write_text("", encoding="utf-8")
    api = package / "api.py"
    implementation = package / "impl.py"
    api.write_text(
        "from .impl import perform_update\n\n"
        "def entry():\n"
        "    return perform_update()\n",
        encoding="utf-8",
    )
    implementation.write_text(
        "def perform_update():\n"
        "    return 'updated'\n",
        encoding="utf-8",
    )
    cache_dir = tmp_path / "cache"
    indexer = CodebaseIndexer(tmp_path, cache_dir=cache_dir)
    assert indexer.full_index(show_progress=False).success is True

    dependencies = indexer.dependency_graph.get_dependencies("pkg.api.entry")
    assert any(dep.to_symbol == "pkg.impl.perform_update" for dep in dependencies)
    module_dependencies = indexer.dependency_graph.get_dependencies("pkg.api")
    assert any(
        dep.dep_type == DependencyType.IMPORTS and dep.to_symbol == "pkg.impl.perform_update"
        for dep in module_dependencies
    )
    assert any(
        dep.dep_type == DependencyType.CONTAINS and dep.to_symbol == "pkg.api.entry"
        for dep in module_dependencies
    )

    cached_indexer = CodebaseIndexer(tmp_path, cache_dir=cache_dir)
    assert cached_indexer.load_cache() is True
    cached_dependencies = cached_indexer.dependency_graph.get_dependencies("pkg.api.entry")
    assert any(dep.to_symbol == "pkg.impl.perform_update" for dep in cached_dependencies)


def test_dependency_resolution_uses_name_index_for_suffix_candidates() -> None:
    qualified_name_reads = 0

    class CountingSymbol:
        def __init__(self, name: str, qualified_name: str) -> None:
            self.name = name
            self._qualified_name = qualified_name
            self.file_path = f"{name}.py"
            self.parent = None

        @property
        def qualified_name(self) -> str:
            nonlocal qualified_name_reads
            qualified_name_reads += 1
            return self._qualified_name

    symbols = [CountingSymbol(f"symbol_{index}", f"pkg.symbol_{index}") for index in range(2000)]
    symbols.append(CountingSymbol("target", "pkg.module.target"))

    class CountingTable:
        def iter_symbols(self):
            return symbols

        @staticmethod
        def get_symbol(_qualified_name):
            return None

    graph = DependencyGraph()
    for index in range(1000):
        graph.add_simple(
            f"caller_{index}",
            "module.target",
            DependencyType.CALLS,
            file_path=f"caller_{index}.py",
        )

    assert graph.resolve_targets(CountingTable()) == 1000
    assert qualified_name_reads < 10000


def test_dependency_resolution_does_not_rebind_external_qualified_calls() -> None:
    table = SymbolTable()
    caller = Symbol(
        name="caller",
        qualified_name="pkg.caller",
        kind=SymbolKind.FUNCTION,
        file_path="pkg.py",
        start_line=1,
        end_line=1,
        language="python",
    )
    unrelated = Symbol(
        name="join",
        qualified_name="pkg.text.join",
        kind=SymbolKind.FUNCTION,
        file_path="pkg.py",
        start_line=1,
        end_line=1,
        language="python",
    )
    table.add_symbol(caller)
    table.add_symbol(unrelated)
    graph = DependencyGraph()
    graph.add_simple(caller.qualified_name, "os.path.join", DependencyType.CALLS, file_path="pkg.py")

    assert graph.resolve_targets(table) == 0
    assert graph.get_dependencies(caller.qualified_name)[0].to_symbol == "os.path.join"


def test_dependency_graph_respects_related_symbol_result_limit() -> None:
    graph = DependencyGraph()
    for index in range(100):
        graph.add_simple("module", f"module.child_{index}", DependencyType.CONTAINS)
    graph.add_simple("subclass", "module", DependencyType.INHERITS)

    related = graph.get_related_symbols("module", max_distance=2, max_results=7)

    assert len(related) == 7
    assert related[0] == ("subclass", 1, DependencyType.INHERITS)


def test_graph_evidence_enters_file_candidates_before_cutoff(tmp_path: Path) -> None:
    facade = tmp_path / "src" / "facade.py"
    implementation = tmp_path / "src" / "implementation.py"
    facade.parent.mkdir()
    facade.write_text("class FacadeEntry:\n    pass\n", encoding="utf-8")
    implementation.write_text("def execute_transition():\n    return True\n", encoding="utf-8")

    table = SymbolTable()
    facade_symbol = Symbol(
        name="FacadeEntry",
        qualified_name="src.facade.FacadeEntry",
        kind=SymbolKind.CLASS,
        file_path=str(facade),
        start_line=1,
        end_line=2,
        source_code=facade.read_text(encoding="utf-8"),
        language="python",
    )
    implementation_symbol = Symbol(
        name="execute_transition",
        qualified_name="src.implementation.execute_transition",
        kind=SymbolKind.FUNCTION,
        file_path=str(implementation),
        start_line=1,
        end_line=2,
        source_code=implementation.read_text(encoding="utf-8"),
        language="python",
    )
    table.add_symbol(facade_symbol)
    table.add_symbol(implementation_symbol)
    graph = DependencyGraph()
    graph.add_simple(
        facade_symbol.qualified_name,
        implementation_symbol.qualified_name,
        DependencyType.CALLS,
        file_path=str(facade),
        line=1,
    )

    file_info = {}
    for path in (facade, implementation):
        file_info[str(path)] = FileInfo(
            path=str(path), mtime=1, size=path.stat().st_size, content_hash=path.stem,
            language="python", summary=f"module {path.stem}",
        )
    for index in range(8):
        decoy = tmp_path / "src" / f"delegation_{index}.py"
        decoy.write_text("def behavior():\n    return None\n", encoding="utf-8")
        file_info[str(decoy)] = FileInfo(
            path=str(decoy), mtime=1, size=decoy.stat().st_size, content_hash=str(index),
            language="python", keywords=["delegation", "behavior"], summary="delegation behavior helper",
        )

    retriever = ContextRetriever(table, graph, tmp_path, file_info=file_info)
    result = retriever.retrieve_for_task(
        "Fix FacadeEntry delegation behavior",
        max_files=2,
        max_symbols=4,
        include_history=False,
        include_memory=False,
        fast=True,
    )

    selected = {item.file_path: item for item in result.relevant_files}
    assert str(facade) in selected
    assert str(implementation) in selected
    assert any(item["source"] == "graph" for item in selected[str(implementation)].evidence)


def test_rank_fusion_rewards_agreement_across_independent_sources(tmp_path: Path) -> None:
    dominant = TaskContextFile("dominant.py", "python", 100.0, "dominant", [])
    corroborated = TaskContextFile("corroborated.py", "python", 35.0, "corroborated", [])
    candidates = [dominant, corroborated]
    evidence = {
        "dominant.py": [{"source": "index", "score": 100.0}],
        "corroborated.py": [
            {"source": "chunk", "score": 4.0},
            {"source": "graph", "score": 3.0},
            {"source": "fts", "score": 2.0},
        ],
    }

    ContextRetriever._rerank_task_file_candidates(candidates, evidence)

    assert corroborated.score > dominant.score
    assert corroborated.reasons[0] == "rank-fusion:chunk+fts+graph"


def test_symbol_context_respects_source_flag_and_line_limit() -> None:
    source = "\n".join(f"line_{index}" for index in range(1, 121))
    symbol = Symbol(
        name="large_symbol",
        qualified_name="module.large_symbol",
        kind=SymbolKind.FUNCTION,
        file_path="module.py",
        start_line=1,
        end_line=120,
        signature="def large_symbol():",
        source_code=source,
        language="python",
    )

    metadata_only = symbol.get_context_string(include_source=False, max_lines=10)
    bounded = symbol.get_context_string(include_source=True, max_lines=10)

    assert "line_1" not in metadata_only
    assert "line_1" in bounded
    assert "line_120" in bounded
    assert "line_60" not in bounded
    assert "lines omitted" in bounded


def test_task_context_budget_preserves_multiple_ranked_file_excerpts(tmp_path: Path) -> None:
    retriever = ContextRetriever(SymbolTable(), DependencyGraph(), tmp_path)
    files = []
    for index in range(3):
        path = tmp_path / "src" / f"module_{index}.py"
        excerpt = "\n".join(f"line_{index}_{line}: value = {line}" for line in range(240))
        files.append(
            TaskContextFile(
                file_path=str(path),
                language="python",
                score=10.0 - index,
                summary=f"implementation module {index}",
                reasons=["chunk:implementation", "graph:calls"],
                excerpt=excerpt,
            )
        )

    context, token_estimate = retriever._format_task_context(
        "Update the implementation flow",
        files,
        [],
        [],
        [],
        max_tokens=1000,
    )

    assert token_estimate <= 1000
    assert str(tmp_path) not in context
    assert all(f"module_{index}.py" in context for index in range(3))
    assert "excerpt truncated to token budget" in context


def test_fenced_trace_identifiers_are_recalled_without_dominating_title_terms(tmp_path: Path) -> None:
    retriever = ContextRetriever(SymbolTable(), DependencyGraph(), tmp_path)
    query = (
        "Fix backend selection failure\n"
        "```text\n"
        "Traceback: resolve_backend(config) called from internal_dispatch\n"
        "```\n"
    )

    weights = retriever._build_task_term_weights(query)
    ranked_terms = dict(retriever._rank_task_search_terms(query, weights, limit=18))

    assert "resolve_backend" in ranked_terms
    assert ranked_terms["resolve_backend"] < ranked_terms["backend"]


def test_task_file_roles_follow_explicit_documentation_intent(tmp_path: Path) -> None:
    implementation = tmp_path / "src" / "migration.py"
    documentation = tmp_path / "docs" / "migration-guide.md"
    implementation.parent.mkdir()
    documentation.parent.mkdir()
    implementation.write_text("def migrate_schema():\n    return True\n", encoding="utf-8")
    documentation.write_text("Migration guide and upgrade examples\n", encoding="utf-8")
    file_info = {
        str(implementation): FileInfo(
            path=str(implementation), mtime=1, size=implementation.stat().st_size,
            content_hash="code", language="python", keywords=["migration", "upgrade"],
            summary="Schema migration implementation",
        ),
        str(documentation): FileInfo(
            path=str(documentation), mtime=1, size=documentation.stat().st_size,
            content_hash="docs", language="markdown", keywords=["migration", "guide", "upgrade"],
            tags=["docs"], summary="Migration guide documentation",
        ),
    }
    retriever = ContextRetriever(SymbolTable(), DependencyGraph(), tmp_path, file_info=file_info)

    result = retriever.retrieve_for_task(
        "Update the migration guide documentation",
        max_files=1,
        max_symbols=1,
        include_history=False,
        include_memory=False,
        fast=True,
    )

    assert result.relevant_files[0].file_path == str(documentation)


def test_fast_task_recommendations_ignore_generated_bundle_copies(tmp_path: Path) -> None:
    source = tmp_path / "src" / "tool_manifest.json"
    generated = tmp_path / ".runtime" / "temp" / "tool_manifest.json"
    source.parent.mkdir(parents=True)
    generated.parent.mkdir(parents=True)
    source.write_text('{"tool": "codebase-retrieval"}', encoding="utf-8")
    generated.write_text(source.read_text(encoding="utf-8"), encoding="utf-8")
    file_info = {
        str(path): FileInfo(
            path=str(path),
            mtime=path.stat().st_mtime,
            size=path.stat().st_size,
            content_hash=path.parent.name,
            language="json",
            keywords=["tool", "context", "retrieval"],
            tags=["tools"],
            summary="Context Engine tool manifest",
        )
        for path in (source, generated)
    }
    retriever = ContextRetriever(SymbolTable(), DependencyGraph(), tmp_path, file_info=file_info)

    result = retriever.retrieve_for_task(
        "context engine tool manifest",
        max_files=1,
        max_symbols=1,
        include_history=False,
        include_memory=False,
        fast=True,
    )

    assert result.relevant_files[0].file_path == str(source)
    assert result.metadata["fast_context_skipped"] is True


def test_fast_task_recommendations_skip_file_scans_when_index_has_enough_candidates(
    tmp_path: Path,
    monkeypatch,
) -> None:
    file_info = {}
    for index in range(4):
        target = tmp_path / "reverie" / "context_engine" / f"engine_{index}.py"
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(f"def optimize_context_{index}():\n    return 'fast retrieval'\n", encoding="utf-8")
        file_info[str(target)] = FileInfo(
            path=str(target),
            mtime=target.stat().st_mtime,
            size=target.stat().st_size,
            content_hash=str(index),
            language="python",
            keywords=["context", "engine", "retrieval", "performance"],
            tags=["engine"],
            summary="Context Engine retrieval performance optimization",
        )

    table = SymbolTable()
    retriever = ContextRetriever(table, DependencyGraph(), tmp_path, file_info=file_info)

    def fail_if_called(*_args, **_kwargs):
        raise AssertionError("fast indexed recommendations should not scan file contents")

    monkeypatch.setattr(retriever, "_run_fast_context_for_task", fail_if_called)
    monkeypatch.setattr(retriever, "_score_file_content_for_task", fail_if_called)
    monkeypatch.setattr(table, "search", fail_if_called)

    result = retriever.retrieve_for_task(
        "optimize context engine retrieval performance",
        max_files=4,
        max_symbols=2,
        include_history=False,
        include_memory=False,
        fast=True,
    )

    assert len(result.relevant_files) == 4
    assert result.metadata["fast_context_skipped"] is True


def test_workspace_mention_ranking_deduplicates_files_and_diversifies_directories() -> None:
    from reverie.cli.interface import ReverieInterface

    candidates = [
        {"path": "src/context/retriever.py", "name": "retriever.py", "kind": "file", "score": 100.0},
        {"path": "src/context/retriever.py", "name": "retrieve_for_task", "kind": "symbol", "score": 99.0},
        {"path": "src/context/cache.py", "name": "cache.py", "kind": "file", "score": 98.0},
        {"path": "tests/test_context.py", "name": "test_context.py", "kind": "file", "score": 97.5},
    ]

    ranked = ReverieInterface._diversify_workspace_mention_candidates(candidates, limit=3)

    assert [item["path"] for item in ranked] == [
        "src/context/retriever.py",
        "tests/test_context.py",
        "src/context/cache.py",
    ]
    assert len({item["path"] for item in ranked}) == len(ranked)


def test_compound_task_selection_reserves_results_for_each_active_intent(tmp_path: Path) -> None:
    retriever = ContextRetriever(SymbolTable(), DependencyGraph(), tmp_path)

    def candidate(path: str, score: float, tags=None) -> TaskContextFile:
        return TaskContextFile(path, "python", score, path, [], tags=list(tags or []))

    candidates = [
        candidate("src/core.py", 100.0),
        candidate("src/irrelevant.py", 90.0),
        candidate("src/context/retriever.py", 60.0),
        candidate("src/context/compressor.py", 55.0),
        candidate("src/tools/codebase.py", 50.0, ["tools"]),
        candidate("src/agent/system_prompt.py", 45.0),
        candidate("src/agent/agent.py", 44.0),
        candidate("desktop/src/styles.css", 40.0, ["ui"]),
        candidate("desktop/src/App.tsx", 39.0, ["ui"]),
    ]

    selected = retriever._select_task_file_candidates(
        candidates,
        term_weights={
            "retrieval": 1.0,
            "compression": 1.0,
            "tool": 1.0,
            "llm": 1.0,
            "ui": 1.0,
        },
        limit=8,
    )

    selected_paths = {item.file_path for item in selected}
    assert selected[0].file_path == "src/core.py"
    assert "src/irrelevant.py" not in selected_paths
    assert {
        "src/context/retriever.py",
        "src/context/compressor.py",
        "src/tools/codebase.py",
        "src/agent/system_prompt.py",
        "src/agent/agent.py",
        "desktop/src/styles.css",
        "desktop/src/App.tsx",
    } <= selected_paths


def test_fast_context_explorer_returns_line_citations(tmp_path: Path) -> None:
    target = tmp_path / "src" / "settings.py"
    target.parent.mkdir()
    target.write_text(
        "class SettingsStore:\n"
        "    def save_config(self):\n"
        "        return 'persist workspace settings quickly'\n",
        encoding="utf-8",
    )
    file_info = {
        str(target): FileInfo(
            path=str(target),
            mtime=1,
            size=target.stat().st_size,
            content_hash="a",
            language="python",
            symbol_names=["SettingsStore", "save_config"],
            keywords=["settings", "config", "persist"],
            tags=["config"],
            summary="Settings persistence store",
        )
    }

    result = FastContextExplorer(tmp_path, file_info=file_info).explore(
        "Where is workspace settings persistence saved?",
        term_weights={"settings": 1.0, "persistence": 0.8, "saved": 0.6},
        max_hits=8,
        max_files=4,
    )

    assert result.hits
    assert any(Path(hit.file_path) == target and hit.line_start >= 1 for hit in result.hits)
    assert "settings.py" in result.render_markdown()


def test_codebase_retrieval_explore_exposes_fast_context(tmp_path: Path) -> None:
    target = tmp_path / "src" / "context_engine.py"
    target.parent.mkdir()
    target.write_text("def fast_context_lookup():\n    return 'line evidence'\n", encoding="utf-8")
    file_info = {
        str(target): FileInfo(
            path=str(target),
            mtime=1,
            size=target.stat().st_size,
            content_hash="a",
            language="python",
            symbol_names=["fast_context_lookup"],
            keywords=["fast", "context", "lookup"],
            tags=["engine"],
            summary="Fast context lookup helper",
        )
    }
    retriever = ContextRetriever(SymbolTable(), DependencyGraph(), tmp_path, file_info=file_info)
    tool = CodebaseRetrievalTool({"project_root": tmp_path, "retriever": retriever})

    result = tool.execute(query_type="explore", query="fast context lookup", limit=8)

    assert result.success is True
    assert "FastContext Exploration" in result.output
    assert result.data["hits"]
    assert any("context_engine.py" in hit["file_path"] for hit in result.data["hits"])


def test_workspace_profile_detects_nested_project_boundaries(tmp_path: Path) -> None:
    (tmp_path / "package.json").write_text("{}", encoding="utf-8")
    nested = tmp_path / "packages" / "api"
    nested.mkdir(parents=True)
    (nested / "go.mod").write_text("module demo/api\n", encoding="utf-8")

    profile = detect_workspace_profile(tmp_path, focus_files=[str(nested / "main.go")])
    kinds = {boundary.kind for boundary in profile.project_boundaries}

    assert {"node", "go"} <= kinds


def test_config_parser_keeps_github_actions_on_key_as_string(tmp_path: Path) -> None:
    workflow = tmp_path / ".github" / "workflows" / "tests.yaml"
    workflow.parent.mkdir(parents=True)
    workflow.write_text(
        "name: Tests\n"
        "on:\n"
        "  push:\n"
        "    branches: [main]\n",
        encoding="utf-8",
    )

    result = ConfigParser(tmp_path).parse_file(workflow)

    assert not result.errors
    assert any(symbol.name == "on" for symbol in result.symbols)
    assert all(isinstance(symbol.name, str) for symbol in result.symbols)


def test_config_parser_accepts_top_level_json_array(tmp_path: Path) -> None:
    configuration = tmp_path / "configuration.json"
    configuration.write_text('[{"name": "first"}, {"name": "second"}]\n', encoding="utf-8")

    result = ConfigParser(tmp_path).parse_file(configuration)

    assert result.success is True
    assert result.errors == []


def test_compressor_uses_deterministic_fallback_when_provider_fails(tmp_path: Path) -> None:
    class BrokenClient:
        class chat:
            class completions:
                @staticmethod
                def create(**kwargs):
                    raise TimeoutError("network timeout")

    messages = [{"role": "system", "content": "system"}]
    for index in range(10):
        messages.append({"role": "user", "content": f"Fix timeout bug in reverie/agent/agent.py step {index}"})
        messages.append({"role": "assistant", "content": f"Changed retry handling step {index}"})

    compressor = ContextCompressor(tmp_path)
    compressed = compressor.compress(
        messages,
        client=BrokenClient(),
        model="test-model",
        provider="openai-sdk",
    )

    assert len(compressed) < len(messages)
    assert compressed[1]["content"].startswith(MEMORY_BLOCK_HEADER)
    assert "reverie/agent/agent.py" in compressed[1]["content"]


def test_compression_transcript_is_bounded_and_preserves_oldest_and_newest_work() -> None:
    messages = [
        {"role": "user", "content": "oldest architectural decision " + "a" * 30000},
        *(
            {"role": "tool", "name": f"tool-{index}", "content": f"middle output {index} " + "b" * 12000}
            for index in range(18)
        ),
        {"role": "assistant", "content": "newest verified result " + "c" * 30000},
    ]

    transcript = _build_compression_transcript(messages, max_chars=40000)

    assert len(transcript) <= 40000
    assert "oldest architectural decision" in transcript
    assert "newest verified result" in transcript
    assert "omitted for faster compression" in transcript


def test_successful_provider_compression_skips_deterministic_fallback(monkeypatch, tmp_path: Path) -> None:
    class SuccessfulClient:
        class chat:
            class completions:
                @staticmethod
                def create(**kwargs):
                    class Message:
                        content = "Current Goal\n- Continue the verified implementation."

                    class Choice:
                        message = Message()

                    class Response:
                        choices = [Choice()]
                        usage = None

                    return Response()

    fallback_calls = 0

    def unexpected_fallback(*args, **kwargs):
        nonlocal fallback_calls
        fallback_calls += 1
        return "fallback"

    monkeypatch.setattr(
        "reverie.context_engine.compressor._build_deterministic_compression_summary",
        unexpected_fallback,
    )
    messages = [
        {"role": "system", "content": "system"},
        *(
            {"role": "user" if index % 2 == 0 else "assistant", "content": f"message {index}"}
            for index in range(20)
        ),
    ]

    compressed = ContextCompressor(tmp_path).compress(
        messages,
        client=SuccessfulClient(),
        model="test-model",
        provider="openai-sdk",
    )

    assert fallback_calls == 0
    assert compressed[1]["content"].startswith(MEMORY_BLOCK_HEADER)


def test_context_cache_uses_fast_compact_gzip_roundtrip(tmp_path: Path) -> None:
    manager = CacheManager(tmp_path)
    payload = {"中文": {"symbols": ["ContextRetriever"], "summary": "compression " * 40}}

    manager._save_compressed(manager.symbols_path, payload)

    assert manager.COMPRESSION_LEVEL == 3
    assert manager._load_compressed(manager.symbols_path) == payload


def test_auto_memory_redacts_secrets_and_builds_typed_fragments(tmp_path: Path) -> None:
    sessions_dir = tmp_path / "sessions"
    sessions_dir.mkdir()
    fake_modelscope_token = "ms-" + "abcdef1234567890"
    (sessions_dir / "s1.json").write_text(
        json.dumps(
            {
                "id": "s1",
                "name": "Provider fixes",
                "updated_at": "2026-05-05T10:00:00",
                "messages": [
                    {
                        "role": "user",
                        "content": f"Always keep ModelScope on Anthropic stream in reverie/modelscope.py api_key={fake_modelscope_token}.",
                    },
                    {
                        "role": "assistant",
                        "content": "Implemented retry timeout handling in reverie/agent/agent.py and tests passed.",
                    },
                ],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    indexer = MemoryIndexer(tmp_path)
    indexer.build_index()
    learned = indexer.auto_learn_from_sessions(max_items=8)
    summary = indexer.build_memory_summary("ModelScope stream", max_chars=1600)
    fragments = indexer.build_context_fragments("ModelScope stream", max_fragments=4)

    assert learned
    assert "[REDACTED" in summary
    assert fake_modelscope_token[:9] not in summary
    assert any(fragment.fragment_type == "auto_memory" for fragment in fragments)
    assert all(fragment.token_cap > 0 and fragment.cache_key for fragment in fragments)


def test_context_fragment_renderer_is_stable_and_token_bounded() -> None:
    fragments = [
        make_context_fragment("tool_output", "b", "x" * 200, token_cap=8, priority=1.0),
        make_context_fragment("recent_turn", "a", "short", token_cap=20, priority=2.0),
    ]

    rendered = render_context_fragments(fragments, max_tokens=32)

    assert rendered.splitlines()[1].startswith("- [recent_turn] a")
    assert "..." in rendered


def _make_symbol(name: str, qualified_name: str, file_path: str) -> Symbol:
    return Symbol(
        name=name,
        qualified_name=qualified_name,
        kind=SymbolKind.FUNCTION,
        file_path=file_path,
        start_line=1,
        end_line=2,
        language="python",
    )


def test_symbol_table_reads_are_independent_of_insertion_order() -> None:
    """Parallel parsing merges symbols in thread-completion order, which varies
    run to run. After ``replace_with`` the table must present a canonical order so
    that lookups, iteration, and serialization are reproducible."""
    symbols = [
        _make_symbol("run", "pkg.beta.run", "pkg/beta.py"),
        _make_symbol("run", "pkg.alpha.run", "pkg/alpha.py"),
        _make_symbol("run", "pkg.gamma.run", "pkg/gamma.py"),
        _make_symbol("load", "pkg.delta.load", "pkg/delta.py"),
        _make_symbol("save", "pkg.delta.save", "pkg/delta.py"),
    ]

    def build(order: list[Symbol]) -> SymbolTable:
        source = SymbolTable()
        for symbol in order:
            source.add_symbol(symbol)
        committed = SymbolTable()
        committed.replace_with(source)  # canonicalizes like a live index swap
        return committed

    forward = build(symbols)
    reversed_order = build(list(reversed(symbols)))

    # Same simple name resolves to the same ordered candidates -> the first
    # match (used as the ranking anchor) is stable regardless of parse order.
    assert [s.qualified_name for s in forward.find_by_name("run")] == [
        "pkg.alpha.run",
        "pkg.beta.run",
        "pkg.gamma.run",
    ]
    assert [s.qualified_name for s in forward.find_by_name("run")] == [
        s.qualified_name for s in reversed_order.find_by_name("run")
    ]

    # Iteration, prefix/pattern search, and truncated pattern search all match.
    assert [s.qualified_name for s in forward.iter_symbols()] == [
        s.qualified_name for s in reversed_order.iter_symbols()
    ]
    assert [s.qualified_name for s in forward.find_by_pattern("pkg.*.run", limit=2)] == [
        "pkg.alpha.run",
        "pkg.beta.run",
    ]
    assert [s.qualified_name for s in forward.find_by_pattern("pkg.*.run", limit=2)] == [
        s.qualified_name for s in reversed_order.find_by_pattern("pkg.*.run", limit=2)
    ]

    # The persisted cache is byte-identical across parse orders.
    assert forward.to_dict() == reversed_order.to_dict()


def test_dependency_graph_edges_are_independent_of_insertion_order() -> None:
    """Edge adjacency lists are appended in parallel-parse order; after commit
    they must be canonical so serialization and capped neighbor queries are
    reproducible."""
    edges = [
        ("pkg.a.run", "pkg.b.helper"),
        ("pkg.a.run", "pkg.c.helper"),
        ("pkg.a.run", "pkg.b.setup"),
    ]

    def build(order: list[tuple[str, str]]) -> DependencyGraph:
        source = DependencyGraph()
        for src, dst in order:
            source.add_simple(src, dst, DependencyType.CALLS, file_path="pkg/a.py", line=1)
        committed = DependencyGraph()
        committed.replace_with(source)
        return committed

    forward = build(edges)
    shuffled = build([edges[2], edges[0], edges[1]])

    assert forward.to_dict() == shuffled.to_dict()


def test_parallel_full_index_matches_serial_and_is_reproducible(tmp_path: Path) -> None:
    """A full index built with many workers must extract exactly the same
    symbols as a serial build, in the same order, on every run.

    Regression guard for a data-corruption race: parser instances carry
    per-parse state (current file content/module name), so sharing one set
    across worker threads dropped and misattributed symbols. Each thread now
    owns its parser pipeline.
    """
    pkg = tmp_path / "src" / "pkg"
    pkg.mkdir(parents=True)
    (pkg / "__init__.py").write_text("", encoding="utf-8")
    # Enough distinct modules that an 8-worker pool parses several at once.
    for i in range(12):
        (pkg / f"mod_{i:02d}.py").write_text(
            f"CONST_{i} = {i}\n\n\n"
            f"def func_{i}(value):\n"
            f"    return value + {i}\n\n\n"
            f"class Widget_{i}:\n"
            f"    def method_a(self):\n        return {i}\n\n"
            f"    def method_b(self):\n        return {i} * 2\n",
            encoding="utf-8",
        )

    project_root = tmp_path / "src"

    def build(workers: int) -> list[str]:
        # Keep caches outside the indexed tree so a later build never indexes
        # an earlier build's cache files.
        cache_dir = tmp_path / "caches" / f"cache_{workers}"
        indexer = CodebaseIndexer(
            project_root=project_root,
            cache_dir=cache_dir,
            config=IndexConfig(max_workers=workers),
        )
        indexer.full_index(show_progress=False)
        return [s.qualified_name for s in indexer.symbol_table.iter_symbols()]

    serial = build(1)
    parallel_runs = [build(8) for _ in range(3)]

    # Parallel extraction loses nothing relative to serial...
    assert parallel_runs[0] == serial
    # ...and is bit-for-bit reproducible across runs.
    assert all(run == parallel_runs[0] for run in parallel_runs)
