import hashlib
import json
from pathlib import Path

from reverie.agent.agent import ReverieAgent
from reverie.config import Config
from reverie.session.sqlite_manager import SQLiteSessionManager
from reverie.tools.serial_novel import SerialNovelTool
from reverie.writer.style_runtime import WStyleRuntime

from test_wstyles import write_card


def prose(prefix, count):
    return "\n\n".join(f"{prefix}，她看过编号{index:04d}的旧凭证，记录不同的日期和水位，再将纸张递给等候的同伴。" for index in range(count))


def project_tool(tmp_path):
    runtime = WStyleRuntime(tmp_path, app_root=tmp_path / "app")
    write_card(runtime.repository, "a", "STYLE_A_具体细节")
    write_card(runtime.repository, "b", "STYLE_B_选择与后果", layer="narrative")
    runtime.set_selection(["a"], global_scope=True)
    agent = ReverieAgent("http://127.0.0.1/v1", "test", "proof", project_root=tmp_path, mode="writer", config=Config(mode="writer"))
    agent.wstyle_runtime = runtime
    tool = SerialNovelTool({"project_root": tmp_path, "agent": agent, "wstyle_runtime": runtime})
    assert tool.execute(action="bootstrap", novel_id="harbor", title="旧水位", brief="A short original story proof", target_chars=1000, chapter_target_chars=500).success
    assert tool.execute(action="configure", novel_id="harbor", data={
        "world_bible": "雨港仅有一座测潮站。昨日的票据不能修改。",
        "cast_bible": "许汀负责测潮；余棠寻找家人的旧档案。两人都是成年人。",
        "story_architecture": "两章解决遗失票据的误会。",
        "style_guide": "第三人称限知，不改变测潮站规则。",
        "roadmap": "第一章核对票据，第二章共同解释异常日期。",
    }).success
    return agent, runtime, tool


def test_explicit_revision_can_retain_original_passages_and_archives_previous_record(tmp_path):
    agent, runtime, tool = project_tool(tmp_path)
    assert tool.execute(action="prepare_chapter", novel_id="harbor", title="夜班", data={"outline": "核对票据并保留原件。"}).success
    original = prose("雨停以后站里安静下来", 14)
    agent._build_messages()
    first = tool.execute(action="commit_chapter", novel_id="harbor", chapter=1, data={"content": original})
    assert first.success, first.error
    chapter_path = tmp_path / "novels/harbor/chapters/chapter-0001.md"
    legacy_bytes = chapter_path.read_bytes().replace(b"\n", b"\r\n")
    chapter_path.write_bytes(legacy_bytes)
    revised = original + "\n\n她在新说明上记录了这次核对的日期，将原件放回玻璃柜。"
    agent._build_messages()
    result = tool.execute(action="commit_chapter", novel_id="harbor", chapter=1, data={"content": revised})
    assert result.success, result.error
    archives = list((tmp_path / "novels/harbor/chapters/revisions").glob("*.md"))
    assert len(archives) == 1 and original in archives[0].read_text(encoding="utf-8")
    assert archives[0].read_bytes() == legacy_bytes
    assert json.loads(archives[0].with_suffix(".json").read_text(encoding="utf-8")) == first.data["chapter"]


def test_native_tools_bind_novel_and_save_actual_request_style_segments(tmp_path):
    agent, runtime, tool = project_tool(tmp_path)
    agent._build_messages()
    prepared = tool.execute(action="prepare_chapter", novel_id="harbor", chapter=1, title="夜班",
                            data={"outline": "许汀与余棠核对旧票据，决定共同找出被改动的日期。"})
    assert prepared.success
    assert prepared.data["control_card"]["wstyle"]["cards"][0]["id"] == "a"
    original = prose("夜里的票据有潮气", 4)
    agent._build_messages()
    rejected = tool.execute(action="commit_chapter", novel_id="harbor", chapter=1, data={"content": original})
    assert not rejected.success
    pending_path = tmp_path / "novels" / "harbor" / "drafts" / "chapter-0001.json"
    pending_before = pending_path.read_bytes()
    pending = json.loads(pending_before)
    assert pending["wstyle_segments"][0]["wstyle"]["cards"][0]["id"] == "a"
    runtime.set_selection(["b"])
    assert pending_path.read_bytes() == pending_before
    agent._build_messages()
    assert "STYLE_B" in agent._request_system_prompt()
    continuation = prose("窗外船灯照着账簿", 14)
    committed = tool.execute(action="commit_chapter", novel_id="harbor", chapter=1,
                             data={"append_content": continuation, "summary": "两人核对票据并承诺共同查清日期。"})
    assert committed.success, committed.error
    segments = committed.data["chapter"]["wstyle_segments"]
    assert [segment["wstyle"]["cards"][0]["id"] for segment in segments] == ["a", "b"]
    chapter_path = tmp_path / "novels" / "harbor" / "chapters" / "chapter-0001.md"
    raw = chapter_path.read_bytes()
    runtime.set_selection(["a", "b"])
    assert chapter_path.read_bytes() == raw
    assert hashlib.sha256(raw).hexdigest() == committed.data["chapter"]["sha256"]
    reader = tmp_path / "novel" / "harbor" / "chapter-0001.txt"
    assert original in reader.read_text(encoding="utf-8")
    assert "WStyle" not in reader.read_text(encoding="utf-8")


def test_sqlite_session_binding_and_different_novels_restore_their_own_overrides(tmp_path):
    agent, runtime, tool = project_tool(tmp_path)
    sessions = SQLiteSessionManager(tmp_path / "sessions", project_root=tmp_path)
    first = sessions.create_session("First")
    runtime.session_manager = sessions
    runtime.bind_project("harbor", tmp_path / "novels" / "harbor")
    runtime.set_selection(["b"])
    second = sessions.create_session("Second")
    assert tool.execute(action="bootstrap", novel_id="island", title="孤岛", brief="A different original proof", target_chars=1000, chapter_target_chars=500).success
    runtime.select_novel("island")
    runtime.set_selection([])
    sessions.select_session(first.id)
    sessions.load_session(first.id)
    assert runtime.snapshot()["scope"] == "novel:harbor"
    assert runtime.composition().active_ids == ["b"]
    sessions.select_session(second.id)
    sessions.load_session(second.id)
    assert runtime.snapshot()["scope"] == "novel:island"
    assert runtime.composition().active_ids == []
