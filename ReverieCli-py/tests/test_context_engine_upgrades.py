from pathlib import Path
import json

from reverie.context_engine.cache import CacheManager
from reverie.context_engine.compressor import (
    ContextCompressor,
    MEMORY_BLOCK_HEADER,
    _build_compression_transcript,
)
from reverie.context_engine.dependency_graph import DependencyGraph
from reverie.context_engine.fast_context import FastContextExplorer
from reverie.context_engine.fragments import make_context_fragment, render_context_fragments
from reverie.context_engine.indexer import FileInfo
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
