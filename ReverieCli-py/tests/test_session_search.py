import json
import sqlite3
from pathlib import Path

from reverie.session.manager import SessionManager


def test_indexed_search_preserves_title_unicode_reasoning_and_tool_hits(tmp_path):
    manager = SessionManager(tmp_path / "state", project_root=tmp_path)
    session = manager.create_session('主题 "quoted"')
    session.messages = [
        {"role": "user", "content": '中文 emoji 😀 needle "quoted"'},
        {"role": "assistant", "content": "", "reasoning_content": "reasoning-needle"},
        {"role": "assistant", "content": "", "tool_calls": [{"function": {"name": "file_read_needle"}}]},
    ]
    manager.save_session(session)
    assert [hit["message_index"] for hit in manager.search_sessions("needle")] == [0, 1, 2]
    assert manager.search_sessions('"quoted"')[0]["role"] == "session"
    assert manager.search_sessions("中文")[0]["message_index"] == 0
    assert manager.search_sessions("😀")[0]["session_id"] == session.id
    assert len(manager.search_sessions("needle", limit=2)) == 2
    assert manager.search_sessions("needle", limit=0) == []


def test_warm_search_and_restart_do_not_read_unchanged_transcripts(tmp_path, monkeypatch):
    manager = SessionManager(tmp_path / "state", project_root=tmp_path)
    session = manager.create_session("Search")
    session.messages = [{"role": "user", "content": "Find this target."}]
    manager.save_session(session)
    assert manager.search_sessions("target")
    restarted = SessionManager(tmp_path / "state", project_root=tmp_path)
    original = Path.read_text
    reads = []

    def tracked_read(path, *args, **kwargs):
        if path.parent == manager.sessions_dir:
            reads.append(path)
        return original(path, *args, **kwargs)

    monkeypatch.setattr(Path, "read_text", tracked_read)
    assert manager.search_sessions("target") == restarted.search_sessions("target")
    assert reads == []


def test_search_tracks_saved_and_external_changes_deletion_and_workspace_scope(tmp_path):
    manager = SessionManager(tmp_path / "shared", project_root=tmp_path / "one")
    session = manager.create_session("One")
    session.messages = [{"role": "user", "content": "old needle"}]
    manager.save_session(session)
    assert manager.search_sessions("old needle")
    session.messages[0]["content"] = "new needle"
    manager.save_session(session)
    assert manager.search_sessions("old needle") == []
    assert manager.search_sessions("new needle")
    file = manager.sessions_dir / f"{session.id}.json"
    data = json.loads(file.read_text(encoding="utf-8"))
    data["messages"][0]["content"] = "external needle"
    file.write_text(json.dumps(data), encoding="utf-8")
    assert manager.search_sessions("new needle") == []
    assert manager.search_sessions("external needle")
    other = SessionManager(tmp_path / "shared", project_root=tmp_path / "two")
    assert other.search_sessions("external needle") == []
    manager.delete_session(session.id)
    assert manager.search_sessions("needle") == []


def test_compact_index_checks_the_entire_literal_after_candidate_filtering(tmp_path):
    manager=SessionManager(tmp_path / "state",project_root=tmp_path)
    session=manager.create_session("Literal query")
    session.messages=[{"role":"user","content":"abc scattered xyz"}]
    manager.save_session(session)
    assert manager.search_sessions("abc scattered xyz")
    assert manager.search_sessions("abc absent xyz")==[]


def test_old_search_cache_is_rebuilt_from_the_authoritative_transcripts(tmp_path):
    manager=SessionManager(tmp_path / "state",project_root=tmp_path)
    session=manager.create_session("Migration")
    session.messages=[{"role":"user","content":"authoritative target"}]
    manager.save_session(session)
    assert manager.search_sessions("target")
    with sqlite3.connect(manager._search_index.path) as db:
        db.execute("PRAGMA user_version=0")
    restarted=SessionManager(tmp_path / "state",project_root=tmp_path)
    assert restarted.search_sessions("authoritative target")[0]["session_id"]==session.id
    with sqlite3.connect(restarted._search_index.path) as db:
        assert db.execute("PRAGMA user_version").fetchone()[0]==1
