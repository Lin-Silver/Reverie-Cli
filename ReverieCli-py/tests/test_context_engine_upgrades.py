from pathlib import Path
import json

from reverie.context_engine.compressor import ContextCompressor, MEMORY_BLOCK_HEADER
from reverie.context_engine.dependency_graph import DependencyGraph
from reverie.context_engine.fragments import make_context_fragment, render_context_fragments
from reverie.context_engine.indexer import FileInfo
from reverie.context_engine.retriever import ContextRetriever
from reverie.context_engine.symbol_table import Symbol, SymbolKind, SymbolTable
from reverie.session.memory_indexer import MemoryIndexer


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
