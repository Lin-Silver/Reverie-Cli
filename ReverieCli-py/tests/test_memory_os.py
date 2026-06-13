from pathlib import Path
from types import SimpleNamespace

from reverie.agent.agent import ReverieAgent
from reverie.agent.tool_executor import ToolExecutor
from reverie.memory import MEMORY_CONTEXT_PROMPT_HEADER, MemoryOS
from reverie.tools.memory_retrieval import MemoryRetrievalTool


def test_memory_os_consolidates_user_feedback_and_assembles_bounded_prompt(tmp_path: Path) -> None:
    memory_os = MemoryOS(tmp_path, project_root=tmp_path)
    event = memory_os.record_event(
        "user_message",
        {"content": "Always use pytest -q for this project before final summaries."},
        actor="user",
        session_id="s1",
    )

    hits = memory_os.retriever.search("pytest verification", limit=4)
    assert hits
    assert hits[0].item.source_event_ids == [event.id]
    assert hits[0].item.scope == "project"
    assert hits[0].item.memory_type == "preference"

    agent = ReverieAgent(
        base_url="http://localhost/v1",
        api_key="test",
        model="test-model",
        project_root=tmp_path,
        config=SimpleNamespace(max_context_tokens=128000),
    )
    agent.tool_executor.update_context("project_data_dir", tmp_path)
    agent.tool_executor.update_context("memory_os", memory_os)
    for index in range(36):
        agent.messages.append({"role": "user", "content": f"old user turn {index}"})
        agent.messages.append({"role": "assistant", "content": f"old assistant turn {index}"})
    agent.messages.append({"role": "user", "content": "How should I verify this change?"})

    request_messages = agent._build_messages()
    assert request_messages[1]["content"].startswith(MEMORY_CONTEXT_PROMPT_HEADER)
    assert "pytest -q" in request_messages[1]["content"]
    assert len(request_messages) < len(agent.messages)
    assert "old user turn 0" not in "\n".join(str(message.get("content", "")) for message in request_messages)


def test_memory_retrieval_tool_returns_evidence_ids(tmp_path: Path) -> None:
    memory_os = MemoryOS(tmp_path, project_root=tmp_path)
    memory_os.record_event(
        "user_message",
        {"content": "Never run destructive cleanup without confirmation."},
        actor="user",
        session_id="s1",
    )

    retrieval = MemoryRetrievalTool({"project_root": tmp_path, "project_data_dir": tmp_path, "memory_os": memory_os})
    result = retrieval.execute(query="destructive cleanup confirmation", limit=3)

    assert result.success is True
    assert "Never run destructive cleanup" in result.output
    assert result.data["memories"][0]["evidence_event_ids"]


def test_tool_executor_records_tool_result_and_file_diff_events(tmp_path: Path) -> None:
    memory_os = MemoryOS(tmp_path, project_root=tmp_path)
    executor = ToolExecutor(project_root=tmp_path)
    executor.update_context("project_data_dir", tmp_path)
    executor.update_context("memory_os", memory_os)

    result = executor.execute(
        "create_file",
        {"path": "notes.txt", "content": "hello\n", "overwrite": False},
        tool_call_id="call-1",
    )

    assert result.success is True
    event_types = [event.event_type for event in memory_os.event_store.tail(limit=10)]
    assert "tool_call" in event_types
    assert "tool_result" in event_types
    assert "file_diff" in event_types
    diff_event = [event for event in memory_os.event_store.tail(limit=10) if event.event_type == "file_diff"][0]
    assert "+hello" in diff_event.payload["diff"]
