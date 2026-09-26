from __future__ import annotations

import json

from reverie.memory import MemoryOS
from reverie.memory.event_store import EventStore
from reverie.memory.models import EventRecord
from reverie.tools.memory_manager import MemoryManagerTool
from reverie.tools.memory_retrieval import MemoryRetrievalTool


def test_recent_events_match_forward_scan_across_chunks(tmp_path):
    store = EventStore(tmp_path)
    lines = []
    for index in range(700):
        event = EventRecord.from_dict({
            "id": f"evt_{index}", "event_type": "tool" if index % 3 == 0 else "message",
            "payload": {"text": "物理验证" + ("x" * 140000 if index == 696 else "x" * 200)},
        })
        lines.append(json.dumps(event.to_dict(), ensure_ascii=False))
        if index % 20 == 0:
            lines.extend(["", "invalid JSON", "[]"])
    store.events_path.write_text("\n".join(lines), encoding="utf-8")
    all_events = list(store.iter_events())
    assert [e.id for e in store.tail(12)] == [e.id for e in all_events[-12:]]
    expected = [e.id for e in all_events if e.event_type == "tool"][-8:]
    assert [e.id for e in store.query(event_type="tool", contains="物理", limit=8)] == expected
    assert [e.id for e in store.tail(8, event_type="tool")] == expected


def test_tail_only_decodes_requested_recent_records(tmp_path, monkeypatch):
    store = EventStore(tmp_path)
    store.events_path.write_text("\n".join(json.dumps({"id": f"evt_{i}"}) for i in range(2000)), encoding="utf-8")
    calls = []
    original = EventRecord.from_dict
    monkeypatch.setattr(EventRecord, "from_dict", lambda data: calls.append(data["id"]) or original(data))
    assert len(store.tail(5)) == 5
    assert len(calls) == 5


def test_remember_does_not_rank_or_touch_unrelated_memories(tmp_path, monkeypatch):
    memory = MemoryOS(tmp_path)
    first = memory.remember("Release requires a runtime check.")["memory"]
    monkeypatch.setattr(memory.retriever, "search", lambda *a, **k: (_ for _ in ()).throw(AssertionError("ranking during write")))
    second = memory.remember("Use deterministic physics tests.")
    assert second["searchable_immediately"] is True
    assert memory.memory_store.get(first.id).access_count == 0
    assert second["memory"].id in memory.memory_store.search_fts("deterministic physics")


def test_access_updates_leave_search_index_and_revision_unchanged(tmp_path, monkeypatch):
    memory = MemoryOS(tmp_path)
    item = memory.remember("Release runtime verification.")["memory"]
    store = memory.memory_store
    revision = store.revision
    statements = []
    original = store._connect
    def connect():
        connection = original()
        connection.set_trace_callback(statements.append)
        return connection
    monkeypatch.setattr(store, "_connect", connect)
    store.touch_access([item.id, item.id])
    assert not any("DELETE FROM memory_fts" in sql or "INSERT INTO memory_fts" in sql for sql in statements)
    updated = store.get(item.id)
    assert updated.access_count == 1
    assert updated.updated_at == item.updated_at
    assert store.revision == revision
    assert item.id in store.search_fts("runtime")


def test_list_filters_before_limit_and_session_memories_remain_isolated(tmp_path):
    memory = MemoryOS(tmp_path)
    context = {"memory_os": memory, "session_id": "one"}
    manager = MemoryManagerTool(context)
    retrieval = MemoryRetrievalTool(context)
    project = manager.execute(action="remember", content="Prefer packaged runtime verification.", memory_type="preference")
    first = manager.execute(action="remember", content="Use the temporary physics fixture.", scope="session")
    context["session_id"] = "two"
    second = manager.execute(action="remember", content="Use the temporary physics fixture.", scope="session")
    assert first.data["memory"]["id"] != second.data["memory"]["id"]
    listed = manager.execute(action="list", scope="project", memory_type="preference", limit=1)
    assert [m["id"] for m in listed.data["memories"]] == [project.data["memory"]["id"]]
    for action in ("recall", "answer"):
        result = retrieval.execute(action=action, query="temporary physics fixture", scope="session")
        ids = [m["id"] for m in result.data["memories"]] if action == "recall" else [m["memory_id"] for m in result.data["sources"]]
        assert ids == [second.data["memory"]["id"]]
    listed = manager.execute(action="list", scope="session")
    assert [m["id"] for m in listed.data["memories"]] == [second.data["memory"]["id"]]


def test_session_topic_conflicts_do_not_cross_sessions(tmp_path):
    memory = MemoryOS(tmp_path)
    memory.remember("Use Vulkan.", scope="session", session_id="one", memory_type="preference", topic="renderer")
    result = memory.remember("Use Direct3D.", scope="SESSION", session_id="two", memory_type="Preference", topic="renderer")
    assert result["conflicts"] == []
    result = memory.remember("Use OpenGL.", scope="SESSION", session_id="two", memory_type="Preference", topic="renderer")
    assert len(result["conflicts"]) == 1


def test_correction_cannot_branch_from_superseded_or_deleted_memory(tmp_path):
    memory = MemoryOS(tmp_path)
    first = memory.remember("Prefer concise Chinese answers.")["memory"]
    second = memory.memory_store.correct(first.id, "Prefer detailed Chinese answers.")
    assert memory.memory_store.correct(first.id, "Stale edit.") is None
    assert memory.memory_store.get(second.id).content == "Prefer detailed Chinese answers."
    memory.memory_store.delete(second.id)
    assert memory.memory_store.correct(second.id, "Resurrect deleted memory.") is None


def test_cached_retrieval_uses_current_content_after_correction(tmp_path):
    memory = MemoryOS(tmp_path)
    item = memory.remember("Prefer deterministic Vulkan physics verification.")["memory"]
    assert memory.recall("Vulkan physics")[0].item.id == item.id
    assert memory.recall("Vulkan physics")[0].item.id == item.id
    replacement = memory.memory_store.correct(item.id, "Prefer Direct3D 12 runtime checks.")
    hits = memory.recall("Direct3D runtime")
    assert hits[0].item.id == replacement.id
    assert "direct3d" in next(reason for reason in hits[0].reasons if reason.startswith("token_overlap"))
    assert all(hit.item.id != item.id for hit in hits)


def test_remember_only_merges_active_versions(tmp_path):
    memory = MemoryOS(tmp_path)
    first = memory.remember("Prefer concise Chinese answers.")["memory"]
    replacement = memory.memory_store.correct(first.id, "Prefer detailed Chinese answers.")
    repeated = memory.remember(first.content)["memory"]
    assert repeated.id != first.id
    assert memory.memory_store.get(first.id, include_deleted=True).status == "superseded"
    assert memory.memory_store.get(first.id, include_deleted=True).superseded_by == replacement.id
    memory.memory_store.delete(repeated.id)
    restored = memory.remember(repeated.content)["memory"]
    assert restored.id != repeated.id
    assert memory.memory_store.get(repeated.id, include_deleted=True).status == "deleted"
    assert memory.remember(restored.content)["memory"].id == restored.id


def test_memory_manager_inspection_consolidation_conflicts_and_hard_delete(tmp_path):
    memory = MemoryOS(tmp_path)
    manager = MemoryManagerTool({"memory_os": memory, "session_id": "fixture"})
    memory.record_event("user_message", {"content": "Always use pytest -q for this project before final summaries."}, actor="user", session_id="fixture", consolidate=False)
    consolidated = manager.execute(action="consolidate", limit=20)
    assert consolidated.success and consolidated.data["memory_ids"]
    first = manager.execute(action="remember", content="Prefer Vulkan for rendering.", memory_type="preference", topic="renderer")
    second = manager.execute(action="remember", content="Prefer Direct3D for rendering.", memory_type="preference", topic="renderer")
    first_id = first.data["memory"]["id"]
    assert first_id in [item["id"] for item in second.data["conflicts"]]
    conflicts = manager.execute(action="conflicts")
    assert any(first_id in record["conflict_ids"] for record in conflicts.data["conflicts"])
    inspected = manager.execute(action="get", memory_id=first_id)
    assert inspected.data["memory"]["content"] == "Prefer Vulkan for rendering."
    status = manager.execute(action="status")
    assert status.success and status.data["counts"]["active"] >= 3
    deleted = manager.execute(action="delete", memory_id=first_id, hard=True)
    assert deleted.success
    assert memory.memory_store.get(first_id, include_deleted=True) is None
    assert not manager.execute(action="get", memory_id=first_id).success
