import json

import pytest

from reverie.tools.serial_novel import SerialNovelTool


def configured_tool(tmp_path, **lengths):
    tool = SerialNovelTool({"project_root": tmp_path})
    result = tool.execute(action="bootstrap", novel_id="length-proof", title="字数边界",
                          brief="原创长度边界测试", target_chars=10_000, **lengths)
    assert result.success, result.error
    assert tool.execute(action="configure", novel_id="length-proof", data={
        "world_bible": "本站只有一台手泵，供水需要人工操作。",
        "cast_bible": "唐望负责维修；谢雨迟负责通知住户。",
        "story_architecture": "共同恢复供水，保留各自目标。",
        "style_guide": "第三人称限知，原始记录不改。",
        "roadmap": "核对名单，修复供水。",
    }).success
    return tool, result.data


def prepare(tool, chapter=1):
    result = tool.execute(action="prepare_chapter", novel_id="length-proof", chapter=chapter,
                          title=f"核对{chapter}", data={"outline": "两人核对名单，形成有依据的分工。"})
    assert result.success, result.error
    return result.data


def boundary_text(size, offset=0):
    # Distinct Han characters isolate length from repetition and prose heuristics.
    return "".join(chr(0x4E00 + offset + index) for index in range(size))


@pytest.mark.parametrize("chapter_target", [None, 10_000])
def test_new_novel_targets_10k_but_commits_at_5k_and_keeps_total_delivery_gate(tmp_path, chapter_target):
    tool, state = configured_tool(tmp_path, **({"chapter_target_chars": chapter_target} if chapter_target is not None else {}))
    assert tool.parameters["properties"]["chapter_target_chars"]["default"] == 10_000
    assert state["chapter_target_chars"] == 10_000
    assert state["chapter_minimum_chars"] == 5_000
    context = prepare(tool)
    assert context["minimum_chars_to_commit"] == 5_000
    assert context["recommended_draft_chars"] == 10_000
    rejected = tool.execute(action="commit_chapter", novel_id="length-proof", chapter=1,
                            data={"content": boundary_text(4_999)})
    assert not rejected.success
    pending = json.loads((tmp_path / "novels/length-proof/drafts/chapter-0001.json").read_text(encoding="utf-8"))
    assert pending["quality"]["minimum_chars"] == 5_000
    accepted = tool.execute(action="commit_chapter", novel_id="length-proof", chapter=1,
                            data={"append_content": boundary_text(1, offset=4_999)})
    assert accepted.success, accepted.error
    assert accepted.data["chapter"]["chars"] == 5_000
    assert not tool.execute(action="audit", novel_id="length-proof").data["completion_ready"]
    second = prepare(tool, chapter=2)
    assert second["minimum_chars_to_commit"] == 5_000
    assert second["recommended_draft_chars"] == 10_000
    assert tool.execute(action="commit_chapter", novel_id="length-proof", chapter=2,
                        data={"content": boundary_text(5_000, offset=5_000)}).success
    assert tool.execute(action="audit", novel_id="length-proof").data["completion_ready"]


def test_explicit_short_chapter_settings_and_old_project_state_keep_original_policy(tmp_path):
    tool, state = configured_tool(tmp_path, chapter_target_chars=1_000)
    assert "chapter_minimum_chars" not in state
    context = prepare(tool)
    assert context["control_card"]["target_chars"] == 1_000
    assert context["minimum_chars_to_commit"] == 1_000
    assert context["recommended_draft_chars"] == 1_150
    state_path = tmp_path / "novels/length-proof/tracking/state.json"
    before = json.loads(state_path.read_text(encoding="utf-8"))
    restored = SerialNovelTool({"project_root": tmp_path}).execute(action="context", novel_id="length-proof")
    assert restored.success
    assert restored.data["minimum_chars_to_commit"] == 1_000
    assert json.loads(state_path.read_text(encoding="utf-8")) == before
