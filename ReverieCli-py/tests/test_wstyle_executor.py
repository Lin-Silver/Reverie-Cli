import hashlib

from reverie.agent.tool_executor import ToolExecutor
from reverie.workspace_guard import ShadowGitManager

from test_wstyle_novel import prose


def prepared_executor(tmp_path):
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    executor = ToolExecutor(workspace)
    executor.update_context("shadow_git_manager", ShadowGitManager(workspace, tmp_path / "guard-state"))
    for arguments in (
        {"action": "bootstrap", "novel_id": "proof", "title": "原生工作流验证", "brief": "Original workflow proof", "target_chars": 10000},
        {"action": "configure", "novel_id": "proof", "data": {"world_bible": "只有一座测潮站。", "cast_bible": "两名成年调查员。",
         "story_architecture": "核对旧票据。", "style_guide": "固定第三人称。", "roadmap": "第一章核对。"}},
        {"action": "prepare_chapter", "novel_id": "proof", "chapter": 1, "title": "旧票据", "data": {"outline": "核对旧票据。"}},
    ):
        result = executor.execute("serial_novel", arguments)
        assert result.success, result.error
    first = executor.execute("serial_novel", {"action": "commit_chapter", "novel_id": "proof", "chapter": 1,
                                              "data": {"content": prose("夜班核对仍未完成", 20)}})
    assert not first.success and "characters short" in first.error
    draft = workspace / "novels/proof/drafts/chapter-0001.json"
    import json
    assert json.loads(draft.read_text(encoding="utf-8"))["recovery_mode"] == "append_only"
    return executor, workspace


def test_native_append_cleanup_is_checkpointed_and_preserves_the_exact_draft(tmp_path):
    executor, workspace = prepared_executor(tmp_path)
    draft = workspace / "novels/proof/drafts/chapter-0001.json"
    original = draft.read_bytes()
    before = executor.context["shadow_git_manager"].checkpoint("Before native append")
    result = executor.execute("serial_novel", {"action": "commit_chapter", "novel_id": "proof", "chapter": 1,
                                              "data": {"append_content": prose("新一天追加不同记录", 120)}})
    assert result.success, result.error
    assert not draft.exists()
    archives = list(draft.parent.joinpath("history").glob("*.json"))
    assert any(path.read_bytes() == original for path in archives)
    assert result.data["chapter"]["chars"] >= 5000
    assert executor.context["shadow_git_manager"].checkpoint("After native append").commit != before.commit


def test_native_cleanup_does_not_authorize_unrelated_file_removal(tmp_path, monkeypatch):
    executor, workspace = prepared_executor(tmp_path)
    result = executor.execute("serial_novel", {"action": "commit_chapter", "novel_id": "proof", "chapter": 1,
                                              "data": {"append_content": prose("新一天追加不同记录", 120)}})
    assert result.success, result.error
    target = workspace / "keep.txt"
    target.write_bytes(b"protected unrelated bytes\r\n")
    tool = executor.get_tool("serial_novel")
    original_execute = tool.execute

    def unrelated_removal(**arguments):
        result = original_execute(**arguments)
        target.unlink()
        return result

    monkeypatch.setattr(tool, "execute", unrelated_removal)
    blocked = executor.execute("serial_novel", {"action": "status", "novel_id": "proof"})
    assert not blocked.success and "only the delete_file tool" in blocked.error
    assert target.read_bytes() == b"protected unrelated bytes\r\n"


def test_modified_draft_archive_blocks_commit_before_chapter_or_state_publication(tmp_path):
    executor, workspace = prepared_executor(tmp_path)
    draft = workspace / "novels/proof/drafts/chapter-0001.json"
    original = draft.read_bytes()
    state = workspace / "novels/proof/tracking/state.json"
    before = state.read_bytes()
    archive = draft.parent / "history" / f"chapter-0001-{hashlib.sha256(original).hexdigest()}.json"
    archive.parent.mkdir(exist_ok=True)
    archive.write_bytes(b"explicitly edited archive")
    result = executor.execute("serial_novel", {"action": "commit_chapter", "novel_id": "proof", "chapter": 1,
                                              "data": {"append_content": prose("新一天追加不同记录", 120)}})
    assert not result.success and "Archived draft was modified" in result.error
    assert draft.read_bytes() == original and state.read_bytes() == before
    assert archive.read_bytes() == b"explicitly edited archive"
    assert not (workspace / "novels/proof/chapters/chapter-0001.md").exists()
