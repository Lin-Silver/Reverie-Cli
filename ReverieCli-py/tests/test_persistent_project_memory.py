from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

from reverie.agent.system_prompt import build_system_prompt
from reverie.memory import MEMANTO_MEMORY_TYPES, MemoryOS
from reverie.tools.codebase_retrieval import CodebaseRetrievalTool
from reverie.tools.memory_manager import MemoryManagerTool
from reverie.tools.memory_retrieval import MemoryRetrievalTool


def test_project_memory_is_isolated_persistent_and_immediately_searchable(tmp_path: Path) -> None:
    project_a = tmp_path / "project-a"
    project_b = tmp_path / "project-b"
    data_a = tmp_path / "app" / "projects" / "a"
    data_b = tmp_path / "app" / "projects" / "b"

    memory_a = MemoryOS(data_a, project_root=project_a)
    remembered = memory_a.remember(
        "Combat uses a deterministic fixed-step collision solver.",
        memory_type="decision",
        topic="combat-physics",
        provenance="verified_artifact",
    )

    assert remembered["searchable_immediately"] is True
    assert memory_a.status()["fts5"] is True
    assert (data_a / "memory" / "memory.sqlite3").is_file()

    reopened_a = MemoryOS(data_a, project_root=project_a)
    memory_b = MemoryOS(data_b, project_root=project_b)
    assert reopened_a.recall("deterministc collison fixed step")[0].item.id == remembered["memory"].id
    assert memory_b.recall("deterministic collision") == []
    assert reopened_a.workspace_id != memory_b.workspace_id


def test_memory_supports_cjk_hybrid_retrieval_temporal_filters_and_types(tmp_path: Path) -> None:
    memory = MemoryOS(tmp_path / "data", project_root=tmp_path / "repo")
    remembered = memory.remember(
        "战斗系统默认使用确定性物理碰撞检测。",
        memory_type="instruction",
        confidence=0.93,
        topic="physics",
    )["memory"]

    hits = memory.recall("物理碰撞", min_confidence=0.9)
    future = (datetime.now(timezone.utc) + timedelta(days=1)).isoformat()

    assert hits and hits[0].item.id == remembered.id
    assert hits[0].components["fts_rrf"] > 0
    assert memory.recall("物理碰撞", changed_since=future) == []
    assert set(MEMANTO_MEMORY_TYPES).issubset(
        {
            "instruction", "fact", "decision", "goal", "commitment", "preference",
            "relationship", "context", "event", "learning", "observation", "artifact", "error",
        }
    )


def test_memory_conflicts_are_explicit_and_corrections_create_versions(tmp_path: Path) -> None:
    memory = MemoryOS(tmp_path / "data", project_root=tmp_path / "repo")
    first = memory.remember(
        "Always use Vulkan for the renderer.",
        memory_type="preference",
        topic="renderer",
    )["memory"]
    second_result = memory.remember(
        "Never use Vulkan for the renderer.",
        memory_type="preference",
        topic="renderer",
    )

    assert [item.id for item in second_result["conflicts"]] == [first.id]
    corrected = memory.memory_store.correct(first.id, "Prefer Direct3D 12 for the renderer.")

    assert corrected is not None
    assert corrected.version == 2
    assert corrected.supersedes == [first.id]
    assert corrected.provenance == "explicit_correction"
    assert memory.memory_store.get(first.id) is None
    assert memory.memory_store.get(first.id, include_deleted=True).status == "superseded"


def test_memory_redacts_secrets_and_tools_cover_remember_recall_answer_status(tmp_path: Path) -> None:
    memory = MemoryOS(tmp_path / "data", project_root=tmp_path / "repo")
    context = {"project_root": tmp_path / "repo", "project_data_dir": tmp_path / "data", "memory_os": memory}
    manager = MemoryManagerTool(context)
    retrieval = MemoryRetrievalTool(context)
    fake_secret = "sk-" + "a" * 24

    stored = manager.execute(
        action="remember",
        content=f"Deployment uses api_key={fake_secret} and pytest -q.",
        memory_type="instruction",
        topic="verification",
        confidence=0.95,
    )
    answer = retrieval.execute(action="answer", query="How is deployment verified?", limit=4)
    status = manager.execute(action="status")

    assert stored.success is True
    assert stored.data["searchable_immediately"] is True
    assert fake_secret not in stored.data["memory"]["content"]
    assert "[REDACTED" in stored.data["memory"]["content"]
    assert answer.success is True and answer.data["grounded"] is True
    assert answer.data["sources"][0]["provenance"] == "explicit_statement"
    assert status.data["project_isolated"] is True
    assert status.data["cross_session"] is True


def test_context_engine_memory_query_and_system_prompt_use_active_memory(tmp_path: Path) -> None:
    memory = MemoryOS(tmp_path / "data", project_root=tmp_path / "repo")
    memory.remember("Release verification requires the packaged executable smoke test.", memory_type="instruction")
    tool = CodebaseRetrievalTool(
        {"project_root": tmp_path / "repo", "project_data_dir": tmp_path / "data", "memory_os": memory}
    )

    result = tool.execute(query_type="memory", query="release verification", limit=4)
    prompt = build_system_prompt(model_name="test", mode="reverie")

    assert result.success is True
    assert result.data["backend"] == "memory_os"
    assert "packaged executable" in result.output
    assert "Proactively call `memory_retrieval" in prompt
    assert "memory_manager(action=\"remember\"" in prompt
