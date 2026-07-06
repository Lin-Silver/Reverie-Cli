from pathlib import Path
from types import SimpleNamespace
import json

from reverie.agent.agent import (
    ReverieAgent,
    _StreamingTurnState,
    _compact_tool_calls_for_history,
    parse_tool_arguments,
)
from reverie.agent.system_prompt import build_system_prompt
from reverie.agent.tool_executor import ToolExecutor
from reverie.tools.mode_switch import ModeSwitchTool
from reverie.tools.serial_novel import SerialNovelTool


def _configure(tool: SerialNovelTool, novel_id: str) -> None:
    result = tool.execute(
        action="configure",
        novel_id=novel_id,
        data={
            "world_bible": "An original archipelago where rain stores memories.",
            "cast_bible": "The heroine and three women each have independent work, desires, and boundaries.",
            "story_architecture": "Four relationship arcs cross a slow civic mystery without erasing daily life.",
            "style_guide": "Close third person, restrained imagery, precise sensory detail, and distinct dialogue.",
            "roadmap": "Twenty-five sequential chapters, each changing one relationship and one shared obligation.",
        },
    )
    assert result.success is True


def test_serial_novel_configure_accepts_top_level_payload_fields(tmp_path: Path) -> None:
    tool = SerialNovelTool({"project_root": tmp_path})
    bootstrap = tool.execute(
        action="bootstrap",
        novel_id="top-level-configure",
        title="Top Level Configure",
        brief="Accept provider payloads that omit the nested data wrapper.",
        target_chars=1000,
        chapter_target_chars=1000,
    )
    assert bootstrap.success is True

    configured = tool.execute(
        action="configure",
        novel_id="top-level-configure",
        world_bible="A rain town with memory-storing glass.",
        cast_bible="Two women with separate work and boundaries.",
        story_architecture="A single chapter proves the workflow.",
        style_guide="Close third person and concrete sensory detail.",
        roadmap="Chapter 1 completes the small proof.",
    )
    assert configured.success is True
    assert configured.data["status"] == "writing"


def test_serial_novel_bootstrap_enforces_100k_floor_for_novel_briefs(tmp_path: Path) -> None:
    tool = SerialNovelTool({"project_root": tmp_path})
    result = tool.execute(
        action="bootstrap",
        novel_id="longform-floor",
        title="Cloud Town Story",
        brief="写一部长篇连载小说，女主群像，日常向。",
        target_chars=80000,
        chapter_target_chars=4000,
    )

    assert result.success is True
    assert result.data["target_chars"] == 100000
    assert result.data["planned_chapters"] == 25


def test_serial_novel_bootstrap_respects_explicit_short_form_briefs(tmp_path: Path) -> None:
    tool = SerialNovelTool({"project_root": tmp_path})
    result = tool.execute(
        action="bootstrap",
        novel_id="shortform-exception",
        title="Short Form",
        brief="写一篇短篇小说，控制在5000字以内。",
        target_chars=5000,
        chapter_target_chars=2500,
    )

    assert result.success is True
    assert result.data["target_chars"] == 5000
    assert result.data["planned_chapters"] == 2


def test_writer_history_compacts_large_serial_novel_payloads() -> None:
    tool_calls = [
        {
            "id": "call_configure",
            "type": "function",
            "function": {
                "name": "serial_novel",
                "arguments": json.dumps(
                    {
                        "action": "configure",
                        "novel_id": "glass-river",
                        "data": {
                            "world_bible": "W" * 1800,
                            "cast_bible": "C" * 900,
                        },
                    },
                    ensure_ascii=False,
                ),
            },
        },
        {
            "id": "call_prepare",
            "type": "function",
            "function": {
                "name": "serial_novel",
                "arguments": json.dumps(
                    {
                        "action": "prepare_chapter",
                        "novel_id": "glass-river",
                        "chapter": 2,
                        "title": "Tea Smoke",
                        "data": {
                            "outline": "O" * 1200,
                            "scene_beats": ["beat one", "beat two", "beat three"],
                        },
                    },
                    ensure_ascii=False,
                ),
            },
        },
        {
            "id": "call_commit",
            "type": "function",
            "function": {
                "name": "serial_novel",
                "arguments": json.dumps(
                    {
                        "action": "commit_chapter",
                        "novel_id": "glass-river",
                        "chapter": 2,
                        "data": {
                            "title": "Tea Smoke",
                            "content": "P" * 4600,
                            "summary": "A quiet meeting in the琴馆.",
                        },
                    },
                    ensure_ascii=False,
                ),
            },
        },
    ]

    compacted = _compact_tool_calls_for_history(tool_calls, mode="writer")

    configure_args = parse_tool_arguments(compacted[0]["function"]["arguments"])
    assert configure_args["data"]["world_bible"] == "[Writer history elided: world_bible (1800 chars)]"
    assert configure_args["data"]["cast_bible"] == "[Writer history elided: cast_bible (900 chars)]"

    prepare_args = parse_tool_arguments(compacted[1]["function"]["arguments"])
    assert prepare_args["data"]["outline"] == "[Writer history elided: outline (1200 chars)]"
    assert prepare_args["data"]["scene_beats"] == ["[Writer history elided: scene_beats (3 items, 26 chars)]"]

    commit_args = parse_tool_arguments(compacted[2]["function"]["arguments"])
    assert "content" not in commit_args["data"]
    assert commit_args["data"]["summary"] == "A quiet meeting in the琴馆."

    original_commit_args = parse_tool_arguments(tool_calls[2]["function"]["arguments"])
    assert original_commit_args["data"]["content"] == "P" * 4600


def test_prepare_chapter_clamps_target_to_longform_project_baseline(tmp_path: Path) -> None:
    tool = SerialNovelTool({"project_root": tmp_path})
    assert tool.execute(
        action="bootstrap",
        novel_id="baseline-clamp",
        title="Baseline Clamp",
        brief="An original-world female-led GL slice-of-life novel.",
        target_chars=100000,
        chapter_target_chars=4000,
    ).success
    _configure(tool, "baseline-clamp")

    prepared = tool.execute(
        action="prepare_chapter",
        novel_id="baseline-clamp",
        chapter=1,
        title="Morning Lantern",
        data={
            "outline": "The heroine finds an old lantern and follows the clue it leaves behind.",
            "target_chars": 1000,
        },
    )

    assert prepared.success is True
    assert prepared.data["control_card"]["target_chars"] == 4000
    assert prepared.data["minimum_chars_to_commit"] == 4000
    assert prepared.data["recommended_draft_chars"] == 4600


def test_serial_novel_status_without_projects_returns_bootstrap_guidance(tmp_path: Path) -> None:
    tool = SerialNovelTool({"project_root": tmp_path})
    result = tool.execute(action="status")

    assert result.success is True
    assert "No Writer projects exist yet" in result.output
    assert result.data["projects"] == []


def test_serial_novel_status_infers_single_planning_project_without_active_chapter(tmp_path: Path) -> None:
    tool = SerialNovelTool({"project_root": tmp_path})
    assert tool.execute(
        action="bootstrap",
        novel_id="single-planning",
        title="Single Planning",
        brief="A novel project still being configured should be inferable.",
        target_chars=1000,
        chapter_target_chars=1000,
    ).success

    status = tool.execute(action="status")
    assert status.success is True
    assert status.data["novel_id"] == "single-planning"
    assert status.data["status"] == "planning"


def test_serial_novel_configure_accepts_python_literal_data_string(tmp_path: Path) -> None:
    tool = SerialNovelTool({"project_root": tmp_path})
    assert tool.execute(
        action="bootstrap",
        novel_id="literal-configure",
        title="Literal Configure",
        brief="A long-form novel should tolerate Python-literal tool payloads.",
        target_chars=1000,
        chapter_target_chars=1000,
    ).success

    result = tool.execute(
        action="configure",
        novel_id="literal-configure",
        data=str(
            {
                "world_bible": "A floating city.",
                "cast_bible": "Two leads with distinct desires.",
                "story_architecture": "A single proof chapter.",
                "style_guide": "Close third person.",
                "roadmap": "Chapter 1 opens the tea house.",
            }
        ),
    )

    assert result.success is True
    assert result.data["configured"] is True


def test_serial_novel_prepare_and_commit_accept_top_level_payload_fields(tmp_path: Path) -> None:
    tool = SerialNovelTool({"project_root": tmp_path})
    assert tool.execute(
        action="bootstrap",
        novel_id="top-level-commit",
        title="Top Level Commit",
        brief="Recover provider payloads that flatten action fields.",
        target_chars=1000,
        chapter_target_chars=1000,
    ).success
    _configure(tool, "top-level-commit")

    prepared = tool.execute(
        action="prepare_chapter",
        novel_id="top-level-commit",
        chapter=1,
        title="Draft",
        outline="One complete scene in a small tea room.",
        target_chars=1000,
        scene_beats=["arrival", "tea", "departure"],
    )
    assert prepared.success is True

    committed = tool.execute(
        action="commit_chapter",
        novel_id="top-level-commit",
        chapter=1,
        content="潮" * 1000,
        summary="A complete chapter submitted from flattened tool fields.",
        key_events=["the chapter commits without nested data"],
    )
    assert committed.success is True
    assert committed.data["chapter"]["chars"] == 1000


def test_serial_novel_commit_strips_duplicate_leading_title_from_reader_exports(tmp_path: Path) -> None:
    tool = SerialNovelTool({"project_root": tmp_path})
    assert tool.execute(
        action="bootstrap",
        novel_id="strip-leading-title",
        title="Strip Leading Title",
        brief="A focused chapter commit should not duplicate its heading in reader TXT exports.",
        target_chars=1000,
        chapter_target_chars=1000,
    ).success
    _configure(tool, "strip-leading-title")

    prepared = tool.execute(
        action="prepare_chapter",
        novel_id="strip-leading-title",
        chapter=1,
        title="灯巷的雨",
        outline="A rainy reunion scene in a tea house.",
        target_chars=1000,
        scene_beats=["arrival", "tea", "reunion"],
    )
    assert prepared.success is True

    committed = tool.execute(
        action="commit_chapter",
        novel_id="strip-leading-title",
        chapter=1,
        data={
            "content": "灯巷的雨\n\n" + ("潮" * 1000),
            "summary": "The chapter title should appear only once in reader-facing TXT.",
        },
    )
    assert committed.success is True

    chapter_path = tmp_path / "novel" / "strip-leading-title" / "chapter-0001.txt"
    chapter_text = chapter_path.read_text(encoding="utf-8")
    assert chapter_text.startswith("Chapter 1: 灯巷的雨\n\n潮")
    assert "\n\n灯巷的雨\n\n" not in chapter_text


def test_serial_novel_configure_persists_partial_documents_and_reports_missing(tmp_path: Path) -> None:
    tool = SerialNovelTool({"project_root": tmp_path})
    assert tool.execute(
        action="bootstrap",
        novel_id="partial-configure",
        title="Partial Configure",
        brief="A long-form novel should survive incremental bible submission.",
        target_chars=1000,
        chapter_target_chars=1000,
    ).success

    partial = tool.execute(
        action="configure",
        novel_id="partial-configure",
        data={
            "world_bible": "A floating market city.",
            "cast_bible": "Two women with distinct work and boundaries.",
            "style_guide": "Close third person and concrete sensory detail.",
        },
    )
    assert partial.success is True
    assert partial.data["configured"] is False
    assert partial.data["status"] == "planning"
    assert partial.data["saved_documents"] == ["world_bible", "cast_bible", "style_guide"]
    assert partial.data["missing_documents"] == ["story_architecture", "roadmap"]
    world_bible_path = tmp_path / "novels" / "partial-configure" / "01-world-bible.md"
    assert "A floating market city." in world_bible_path.read_text(encoding="utf-8")

    completed = tool.execute(
        action="configure",
        novel_id="partial-configure",
        data={
            "story_architecture": "Twenty-five chapters of slow relationship change.",
            "roadmap": "Chapter 1 opens the tea house.",
        },
    )
    assert completed.success is True
    assert completed.data["configured"] is True
    assert completed.data["missing_documents"] == []


def test_serial_novel_persists_and_requires_control_card(tmp_path: Path) -> None:
    tool = SerialNovelTool({"project_root": tmp_path})
    bootstrap = tool.execute(
        action="bootstrap",
        novel_id="rain-archive",
        title="Rain Archive",
        brief="Original-world female-led GL slice-of-life serial.",
        target_chars=10000,
        chapter_target_chars=1000,
    )
    assert bootstrap.success is True
    _configure(tool, "rain-archive")

    rejected = tool.execute(
        action="commit_chapter",
        novel_id="rain-archive",
        chapter=1,
        data={"content": "text", "summary": "summary"},
    )
    assert rejected.success is False
    assert "no control card" in str(rejected.error)

    prepared = tool.execute(
        action="prepare_chapter",
        novel_id="rain-archive",
        chapter=1,
        title="Market Rain",
        data={
            "outline": "The heroine starts a new job and meets the conservator.",
            "scene_beats": ["arrival", "shared repair", "quiet disagreement"],
            "relationship_progression": ["professional curiosity becomes personal attention"],
            "ending_hook": "A borrowed umbrella contains a memory that belongs to neither woman.",
            "target_chars": 1000,
        },
    )
    assert prepared.success is True
    assert prepared.data["minimum_chars_to_commit"] == 1000
    assert prepared.data["recommended_draft_chars"] == 1150
    assert "Minimum to commit: 1000 non-whitespace characters" in prepared.output
    assert "Recommended draft size: 1150 non-whitespace characters" in prepared.output
    assert "send only data.append_content" in prepared.output

    content = "第一章的日常从雨声开始。" + ("潮" * 1000)
    committed = tool.execute(
        action="commit_chapter",
        novel_id="rain-archive",
        chapter=1,
        data=json.dumps(
            {
                "content": content,
                "summary": "The heroine and conservator repair a rain vessel and discover an impossible memory.",
                "key_events": ["the memory vessel opens"],
                "relationship_updates": ["mutual curiosity established"],
                "opened_threads": ["owner of the impossible memory"],
            }
        ),
    )
    assert committed.success is True
    reader_chapter = tmp_path / "novel" / "rain-archive" / "chapter-0001.txt"
    reader_manuscript = tmp_path / "novel" / "rain-archive" / "manuscript.txt"
    assert reader_chapter.is_file()
    assert reader_manuscript.is_file()
    assert reader_chapter.read_text(encoding="utf-8").startswith("Chapter 1: Market Rain")
    assert "Rain Archive" in reader_manuscript.read_text(encoding="utf-8")

    resumed = SerialNovelTool({"project_root": tmp_path}).execute(
        action="status",
        novel_id="rain-archive",
    )
    assert resumed.success is True
    assert resumed.data["completed_chapters"] == 1
    assert resumed.data["next_chapter"] == 2
    assert resumed.data["total_chars"] >= 1000
    assert resumed.data["reader_project_dir"] == str(tmp_path / "novel" / "rain-archive")
    assert resumed.data["reader_manuscript_path"] == str(reader_manuscript)
    assert "Readable TXT:" in resumed.output


def test_serial_novel_rejects_generated_prose_tic_padding(tmp_path: Path) -> None:
    tool = SerialNovelTool({"project_root": tmp_path})
    assert tool.execute(
        action="bootstrap",
        novel_id="tic-gate",
        title="Tic Gate",
        brief="Quality gate test.",
        target_chars=1000,
        chapter_target_chars=1000,
    ).success
    _configure(tool, "tic-gate")
    assert tool.execute(
        action="prepare_chapter",
        novel_id="tic-gate",
        chapter=1,
        title="Draft",
        data={"outline": "A complete scene.", "target_chars": 1000},
    ).success
    padded = (("她微微抬眼，仿佛空气中弥漫着一丝雾气。" * 12) + ("潮声落在窗外。" * 60))
    result = tool.execute(
        action="commit_chapter",
        novel_id="tic-gate",
        chapter=1,
        data={"content": padded, "summary": "A padded draft."},
    )
    assert result.success is False
    assert "generated-prose" in str(result.error)


def test_serial_novel_enforces_planned_chapter_delivery_budget(tmp_path: Path) -> None:
    tool = SerialNovelTool({"project_root": tmp_path})
    assert tool.execute(
        action="bootstrap",
        novel_id="delivery-budget",
        title="Delivery Budget",
        brief="Three chapters must satisfy the target without an unplanned fourth chapter.",
        target_chars=6000,
        chapter_target_chars=2000,
    ).success
    _configure(tool, "delivery-budget")
    assert tool.execute(
        action="prepare_chapter",
        novel_id="delivery-budget",
        chapter=1,
        title="Short Draft",
        data={"outline": "A complete daily-life scene.", "target_chars": 2000},
    ).success

    rejected = tool.execute(
        action="commit_chapter",
        novel_id="delivery-budget",
        chapter=1,
        data={"content": "潮" * 1600, "summary": "The scene is complete but under budget."},
    )
    assert rejected.success is False
    assert "400 non-whitespace characters short" in str(rejected.error)
    assert "at least 600 new non-whitespace characters" in str(rejected.error)

    committed = tool.execute(
        action="commit_chapter",
        novel_id="delivery-budget",
        chapter=1,
        data={"content": "潮" * 2000, "summary": "The scene satisfies its delivery budget."},
    )
    assert committed.success is True
    quality = committed.data["chapter"]["quality"]
    assert quality["control_card_minimum_chars"] == 1400
    assert quality["delivery_minimum_chars"] == 2000
    assert quality["minimum_chars"] == 2000
    content_schema = SerialNovelTool.parameters["properties"]["data"]["properties"]["content"]
    append_schema = SerialNovelTool.parameters["properties"]["data"]["properties"]["append_content"]
    world_bible_schema = SerialNovelTool.parameters["properties"]["data"]["properties"]["world_bible"]
    assert "recommended_draft_chars" in content_schema["description"]
    assert "preserved rejected draft" in append_schema["description"]
    assert "world rules" in world_bible_schema["description"]


def test_serial_novel_preserves_short_draft_and_accepts_append_only_retry(tmp_path: Path) -> None:
    tool = SerialNovelTool({"project_root": tmp_path})
    assert tool.execute(
        action="bootstrap",
        novel_id="append-recovery",
        title="Append Recovery",
        brief="Recover a short chapter without regenerating it.",
        target_chars=2000,
        chapter_target_chars=2000,
    ).success
    _configure(tool, "append-recovery")
    prepared = tool.execute(
        action="prepare_chapter",
        novel_id="append-recovery",
        chapter=1,
        title="Draft",
        data={"outline": "One complete scene.", "target_chars": 2000},
    )
    assert prepared.success
    assert prepared.data["recommended_draft_chars"] == 2300

    rejected = tool.execute(
        action="commit_chapter",
        novel_id="append-recovery",
        chapter=1,
        data={"content": "潮" * 1600, "summary": "A complete but short scene."},
    )
    assert rejected.success is False
    assert "preserved locally" in str(rejected.error)
    assert "data.append_content" in str(rejected.error)
    assert "at least 600 new" in str(rejected.error)

    context = tool.execute(action="context", novel_id="append-recovery", chapter=1)
    assert context.success
    assert context.data["pending_draft"]["chars"] == 1600
    assert context.data["pending_draft"]["recommended_append_chars"] == 600
    assert context.data["pending_draft"]["quality_retry_count"] == 1
    assert context.data["pending_draft"]["recovery_mode"] == "append_only"
    assert context.data["pending_draft"]["requires_reprepare"] is False
    assert context.data["pending_draft"]["content_tail"] == "潮" * 1600
    assert "do not resend the full chapter" in context.output
    assert "do not repeat or lightly paraphrase any preserved paragraph" in context.output
    assert "Boundary excerpt from the preserved tail for continuity only" in context.output

    committed = tool.execute(
        action="commit_chapter",
        novel_id="append-recovery",
        chapter=1,
        data={"append_content": "汐" * 600},
    )
    assert committed.success
    assert committed.data["chapter"]["quality"]["chars"] == 2200
    assert not (tmp_path / "novels" / "append-recovery" / "drafts" / "chapter-0001.json").exists()


def test_serial_novel_recovers_append_retry_from_malformed_nested_data_string(tmp_path: Path) -> None:
    tool = SerialNovelTool({"project_root": tmp_path})
    assert tool.execute(
        action="bootstrap",
        novel_id="append-jsonish",
        title="Append Jsonish",
        brief="Recover append-only retries when the provider emits malformed nested JSON strings.",
        target_chars=2000,
        chapter_target_chars=2000,
    ).success
    _configure(tool, "append-jsonish")
    assert tool.execute(
        action="prepare_chapter",
        novel_id="append-jsonish",
        chapter=1,
        title="Draft",
        data={"outline": "One complete scene.", "target_chars": 2000},
    ).success

    rejected = tool.execute(
        action="commit_chapter",
        novel_id="append-jsonish",
        chapter=1,
        data={"content": "潮" * 1600, "summary": "A complete but short scene."},
    )
    assert rejected.success is False

    malformed_append = (
        '{"append_content": "她想，也许这盏灯会更"稳"一些。\\n\\n'
        '\\"你在看什么？\\"她轻声问。'
        + ("汐" * 650)
        + '", "summary": "Append-only retry recovered from malformed nested JSON."}'
    )
    committed = tool.execute(
        action="commit_chapter",
        novel_id="append-jsonish",
        chapter=1,
        data=malformed_append,
    )

    assert committed.success is True
    chapter_text = (tmp_path / "novels" / "append-jsonish" / "chapters" / "chapter-0001.md").read_text(
        encoding="utf-8"
    )
    assert '更"稳"' in chapter_text
    assert '"你在看什么？"' in chapter_text
    assert committed.data["chapter"]["quality"]["chars"] >= 2250


def test_serial_novel_append_only_retry_trims_repeated_leading_paragraphs(tmp_path: Path) -> None:
    tool = SerialNovelTool({"project_root": tmp_path})
    assert tool.execute(
        action="bootstrap",
        novel_id="append-trimmed-overlap",
        title="Append Trimmed Overlap",
        brief="Append-only retries should trim repeated leading paragraphs from the preserved tail.",
        target_chars=2000,
        chapter_target_chars=2000,
    ).success
    _configure(tool, "append-trimmed-overlap")
    assert tool.execute(
        action="prepare_chapter",
        novel_id="append-trimmed-overlap",
        chapter=1,
        title="Draft",
        data={"outline": "One complete scene.", "target_chars": 2000},
    ).success

    repeated_tail = "\n\n".join(["潮" * 400, "汐" * 400, "灯" * 400, "雾" * 400])
    rejected = tool.execute(
        action="commit_chapter",
        novel_id="append-trimmed-overlap",
        chapter=1,
        data={"content": repeated_tail, "summary": "A complete but short scene."},
    )
    assert rejected.success is False

    committed = tool.execute(
        action="commit_chapter",
        novel_id="append-trimmed-overlap",
        chapter=1,
        data={"append_content": ("雾" * 400) + "\n\n" + ("光" * 700)},
    )

    assert committed.success is True
    chapter_text = (tmp_path / "novels" / "append-trimmed-overlap" / "chapters" / "chapter-0001.md").read_text(
        encoding="utf-8"
    )
    assert chapter_text.count("雾" * 400) == 1
    assert committed.data["chapter"]["quality"]["duplicate_paragraphs"] == 0


def test_serial_novel_append_only_retry_trims_long_suffix_overlap_not_just_recent_tail(tmp_path: Path) -> None:
    tool = SerialNovelTool({"project_root": tmp_path})
    assert tool.execute(
        action="bootstrap",
        novel_id="append-long-overlap",
        title="Append Long Overlap",
        brief="Append-only retries should trim the longest repeated suffix even when it starts earlier than the last six paragraphs.",
        target_chars=2000,
        chapter_target_chars=2000,
    ).success
    _configure(tool, "append-long-overlap")
    assert tool.execute(
        action="prepare_chapter",
        novel_id="append-long-overlap",
        chapter=1,
        title="Draft",
        data={"outline": "One complete scene.", "target_chars": 2000},
    ).success

    base_paragraphs = [syllable * 160 for syllable in "ABCDEFGHIJKL"]
    rejected = tool.execute(
        action="commit_chapter",
        novel_id="append-long-overlap",
        chapter=1,
        data={"content": "\n\n".join(base_paragraphs), "summary": "A complete but short scene."},
    )
    assert rejected.success is False

    committed = tool.execute(
        action="commit_chapter",
        novel_id="append-long-overlap",
        chapter=1,
        data={"append_content": "\n\n".join(base_paragraphs[3:] + [("M" * 800)])},
    )

    assert committed.success is True
    chapter_text = (tmp_path / "novels" / "append-long-overlap" / "chapters" / "chapter-0001.md").read_text(
        encoding="utf-8"
    )
    assert chapter_text.count(base_paragraphs[3]) == 1
    assert chapter_text.rstrip().endswith("M" * 800)
    assert committed.data["chapter"]["quality"]["duplicate_paragraphs"] == 0


def test_serial_novel_append_only_retry_rejects_metadata_only_resubmission(tmp_path: Path) -> None:
    tool = SerialNovelTool({"project_root": tmp_path})
    assert tool.execute(
        action="bootstrap",
        novel_id="append-metadata-only",
        title="Append Metadata Only",
        brief="Length-only retries must stay on the append_content lane.",
        target_chars=2000,
        chapter_target_chars=2000,
    ).success
    _configure(tool, "append-metadata-only")
    assert tool.execute(
        action="prepare_chapter",
        novel_id="append-metadata-only",
        chapter=1,
        title="Draft",
        data={"outline": "One complete scene.", "target_chars": 2000},
    ).success

    rejected = tool.execute(
        action="commit_chapter",
        novel_id="append-metadata-only",
        chapter=1,
        data={"content": "a" * 1600, "summary": "A complete but short scene."},
    )
    assert rejected.success is False
    assert "data.append_content" in str(rejected.error)

    retry = tool.execute(
        action="commit_chapter",
        novel_id="append-metadata-only",
        chapter=1,
        data={
            "summary": "Metadata only retry should be rejected deterministically.",
            "key_events": ["The model forgot to send prose."],
        },
    )
    assert retry.success is False
    assert "Do not resend metadata alone" in str(retry.error)
    assert "do not regenerate the full chapter" in str(retry.error)
    assert "data.append_content containing at least 600 new non-whitespace characters" in str(retry.error)


def test_serial_novel_recovers_full_commit_from_malformed_nested_data_string(tmp_path: Path) -> None:
    tool = SerialNovelTool({"project_root": tmp_path})
    assert tool.execute(
        action="bootstrap",
        novel_id="full-jsonish",
        title="Full Jsonish",
        brief="Recover full chapter commits when the provider emits malformed nested JSON strings.",
        target_chars=1000,
        chapter_target_chars=1000,
    ).success
    _configure(tool, "full-jsonish")
    assert tool.execute(
        action="prepare_chapter",
        novel_id="full-jsonish",
        chapter=1,
        title="Draft",
        data={"outline": "One complete scene.", "target_chars": 1000},
    ).success

    malformed_content = (
        '{"content": "她望着灯芯，觉得今晚的光更"稳"。\\n\\n'
        '\\"你在看什么？\\"有人在门边问。'
        + ("潮" * 1100)
        + '", "summary": "Full commit recovered from malformed nested JSON."}'
    )
    committed = tool.execute(
        action="commit_chapter",
        novel_id="full-jsonish",
        chapter=1,
        data=malformed_content,
    )

    assert committed.success is True
    chapter_text = (tmp_path / "novels" / "full-jsonish" / "chapters" / "chapter-0001.md").read_text(
        encoding="utf-8"
    )
    assert '更"稳"' in chapter_text
    assert '"你在看什么？"' in chapter_text


def test_serial_novel_recovers_prepare_arrays_from_malformed_nested_data_string(tmp_path: Path) -> None:
    tool = SerialNovelTool({"project_root": tmp_path})
    assert tool.execute(
        action="bootstrap",
        novel_id="prepare-jsonish",
        title="Prepare Jsonish",
        brief="Recover prepare_chapter arrays when the provider emits malformed nested JSON strings.",
        target_chars=1000,
        chapter_target_chars=1000,
    ).success
    _configure(tool, "prepare-jsonish")

    malformed_prepare = (
        '{"outline": "她在雨前开门迎客。", '
        '"scene_beats": ["煮水", "迎客", "谈茶"], '
        '"continuity_requirements": ["保持第一章初遇感", "不要直接表白"], '
        '"relationship_progression": ["从礼貌到好奇"], '
        '"ending_hook": "她目送来客离开，忽然想起那只还温热的茶盏。", '
        '"target_chars": 1000}'
    )
    prepared = tool.execute(
        action="prepare_chapter",
        novel_id="prepare-jsonish",
        chapter=1,
        title="雨前茶事",
        data=malformed_prepare,
    )

    assert prepared.success is True
    assert prepared.data["control_card"]["scene_beats"] == ["煮水", "迎客", "谈茶"]
    assert prepared.data["control_card"]["continuity_requirements"] == ["保持第一章初遇感", "不要直接表白"]
    assert prepared.data["control_card"]["relationship_progression"] == ["从礼貌到好奇"]


def test_serial_novel_infers_outline_title_and_extracts_missing_summary(tmp_path: Path) -> None:
    tool = SerialNovelTool({"project_root": tmp_path})
    assert tool.execute(
        action="bootstrap",
        novel_id="fallback-metadata",
        title="Fallback Metadata",
        brief="Avoid resending full prose for omitted metadata.",
        target_chars=1000,
        chapter_target_chars=1000,
    ).success
    _configure(tool, "fallback-metadata")
    prepared = tool.execute(
        action="prepare_chapter",
        novel_id="fallback-metadata",
        chapter=1,
        data={"outline": "第一章《雨灯》。Two women repair a lamp together.", "target_chars": 1000},
    )
    assert prepared.success
    assert prepared.data["control_card"]["title"] == "雨灯"

    committed = tool.execute(
        action="commit_chapter",
        novel_id="fallback-metadata",
        chapter=1,
        data={"content": ("她们在雨夜修灯，讨论各自的工作与边界。" * 100)},
    )
    assert committed.success
    assert committed.data["chapter"]["summary"]
    assert committed.data["chapter"]["summary_source"] == "extractive_fallback"


def test_serial_novel_derives_fallback_title_when_model_omits_it(tmp_path: Path) -> None:
    tool = SerialNovelTool({"project_root": tmp_path})
    assert tool.execute(
        action="bootstrap",
        novel_id="fallback-title",
        title="Fallback Title",
        brief="Recover when the provider omits chapter titles.",
        target_chars=1000,
        chapter_target_chars=1000,
    ).success
    _configure(tool, "fallback-title")

    prepared = tool.execute(
        action="prepare_chapter",
        novel_id="fallback-title",
        chapter=1,
        data={"outline": "清明后第三日，梅雨刚停。两人一起修补茶盏，试探彼此的边界。", "target_chars": 1000},
    )
    assert prepared.success
    assert prepared.data["control_card"]["title"] == "清明后第三日"


def test_serial_novel_rejects_cross_chapter_passage_reuse(tmp_path: Path) -> None:
    tool = SerialNovelTool({"project_root": tmp_path})
    assert tool.execute(
        action="bootstrap",
        novel_id="passage-reuse",
        title="Passage Reuse",
        brief="Two chapters must contain independently written scenes.",
        target_chars=2000,
        chapter_target_chars=1000,
    ).success
    _configure(tool, "passage-reuse")
    repeated = (
        "她把修好的杯子放回木架，窗外雨声压低了屋内的谈话。"
        "两个人各自收拾工具，谁也没有催促谁先离开。门边的伞还滴着水，她们决定再等一会儿。"
    )
    first = repeated + ("潮" * 1000)
    assert tool.execute(
        action="prepare_chapter",
        novel_id="passage-reuse",
        chapter=1,
        title="First",
        data={"outline": "First complete scene.", "target_chars": 1000},
    ).success
    assert tool.execute(
        action="commit_chapter",
        novel_id="passage-reuse",
        chapter=1,
        data={"content": first, "summary": "First scene."},
    ).success
    assert tool.execute(
        action="prepare_chapter",
        novel_id="passage-reuse",
        chapter=2,
        title="Second",
        data={"outline": "Second complete scene.", "target_chars": 1000},
    ).success

    second = ("汐" * 500) + repeated + ("汐" * 500)
    result = tool.execute(
        action="commit_chapter",
        novel_id="passage-reuse",
        chapter=2,
        data={"content": second, "summary": "Second scene repeats the first."},
    )
    assert result.success is False
    assert "reuses a 64-character passage" in str(result.error)


def test_serial_novel_prepare_rejects_control_card_that_repeats_forbidden_terms(tmp_path: Path) -> None:
    tool = SerialNovelTool({"project_root": tmp_path})
    assert tool.execute(
        action="bootstrap",
        novel_id="control-card-lint",
        title="Control Card Lint",
        brief="The chapter plan must not reintroduce forbidden recycled imagery.",
        target_chars=1000,
        chapter_target_chars=1000,
    ).success
    _configure(tool, "control-card-lint")

    result = tool.execute(
        action="prepare_chapter",
        novel_id="control-card-lint",
        chapter=1,
        title="Bad Plan",
        data={
            "outline": "她又站回春屿花市的石板路前，想起左边是石墙的旧路。",
            "opening_hook": "她又站回春屿花市的石板路前。",
            "scene_beats": ["她望向左边是石墙的位置。"],
            "continuity_requirements": [
                "场景必须完全不同——不得出现春屿花市石板路、\"左边的石墙\"等表述",
            ],
            "target_chars": 1000,
        },
    )

    assert result.success is False
    assert "violates its own continuity requirements" in str(result.error)
    assert "春屿花市石板路" in str(result.error)
    assert "左边的石墙" in str(result.error)


def test_serial_novel_mixed_quality_gate_rejection_explicitly_forbids_append_retry(tmp_path: Path) -> None:
    tool = SerialNovelTool({"project_root": tmp_path})
    assert tool.execute(
        action="bootstrap",
        novel_id="mixed-rejection",
        title="Mixed Rejection",
        brief="A short draft that also reuses prior prose must require a full rewrite.",
        target_chars=2000,
        chapter_target_chars=1000,
    ).success
    _configure(tool, "mixed-rejection")
    repeated = (
        "她把修好的杯子放回木架，窗外雨声压低了屋内的谈话。"
        "两个人各自收拾工具，谁也没有催促谁先离开。门边的伞还滴着水，她们决定再等一会儿。"
    )
    assert tool.execute(
        action="prepare_chapter",
        novel_id="mixed-rejection",
        chapter=1,
        title="First",
        data={"outline": "First complete scene.", "target_chars": 1000},
    ).success
    assert tool.execute(
        action="commit_chapter",
        novel_id="mixed-rejection",
        chapter=1,
        data={"content": repeated + ("潮" * 1000), "summary": "First scene."},
    ).success
    assert tool.execute(
        action="prepare_chapter",
        novel_id="mixed-rejection",
        chapter=2,
        title="Second",
        data={"outline": "Second complete scene.", "target_chars": 1000},
    ).success

    result = tool.execute(
        action="commit_chapter",
        novel_id="mixed-rejection",
        chapter=2,
        data={"content": repeated + ("汐" * 200), "summary": "Second scene is short and recycled."},
    )

    assert result.success is False
    assert "reuses a 64-character passage" in str(result.error)
    assert "Do not use data.append_content" in str(result.error)


def test_serial_novel_caps_repeated_quality_gate_retries_and_requires_reprepare(tmp_path: Path) -> None:
    tool = SerialNovelTool({"project_root": tmp_path})
    assert tool.execute(
        action="bootstrap",
        novel_id="repair-budget",
        title="Repair Budget",
        brief="A stubborn chapter rewrite loop must stop cleanly.",
        target_chars=2000,
        chapter_target_chars=1000,
    ).success
    _configure(tool, "repair-budget")
    repeated = (
        "å¥¹æŠŠä¿®å¥½çš„æ¯å­æ”¾å›žæœ¨æž¶ï¼Œçª—å¤–é›¨å£°åŽ‹ä½Žäº†å±‹å†…çš„è°ˆè¯ã€‚"
        "ä¸¤ä¸ªäººå„è‡ªæ”¶æ‹¾å·¥å…·ï¼Œè°ä¹Ÿæ²¡æœ‰å‚¬ä¿ƒè°å…ˆç¦»å¼€ã€‚é—¨è¾¹çš„ä¼žè¿˜æ»´ç€æ°´ï¼Œå¥¹ä»¬å†³å®šå†ç­‰ä¸€ä¼šå„¿ã€‚"
    )
    first = repeated + ("æ½®" * 1000)
    assert tool.execute(
        action="prepare_chapter",
        novel_id="repair-budget",
        chapter=1,
        title="First",
        data={"outline": "First complete scene.", "target_chars": 1000},
    ).success
    assert tool.execute(
        action="commit_chapter",
        novel_id="repair-budget",
        chapter=1,
        data={"content": first, "summary": "First scene."},
    ).success
    assert tool.execute(
        action="prepare_chapter",
        novel_id="repair-budget",
        chapter=2,
        title="Second",
        data={"outline": "Second complete scene.", "target_chars": 1000},
    ).success

    second = ("æ±" * 500) + repeated + ("æ±" * 500)
    first_retry = tool.execute(
        action="commit_chapter",
        novel_id="repair-budget",
        chapter=2,
        data={"content": second, "summary": "Second scene repeats the first."},
    )
    assert first_retry.success is False
    assert "attempt 1/3" in str(first_retry.error)

    second_retry = tool.execute(
        action="commit_chapter",
        novel_id="repair-budget",
        chapter=2,
        data={"content": second + "æ³¢" * 10, "summary": "Still repeats the first."},
    )
    assert second_retry.success is False
    assert "attempt 2/3" in str(second_retry.error)

    third_retry = tool.execute(
        action="commit_chapter",
        novel_id="repair-budget",
        chapter=2,
        data={"content": second + "æ²«" * 20, "summary": "Still repeats the first after more rewrites."},
    )
    assert third_retry.success is False
    assert "exhausted 3 deterministic quality-gate revision attempts" in str(third_retry.error)

    context = tool.execute(action="context", novel_id="repair-budget", chapter=2)
    assert context.success
    assert context.data["pending_draft"]["quality_retry_count"] == 3
    assert context.data["pending_draft"]["requires_reprepare"] is True
    assert context.data["pending_draft"]["recovery_mode"] == "reprepare"
    assert "Latest blocking issues:" in context.output
    assert "Do not call commit_chapter again yet" in context.output

    blocked = tool.execute(
        action="commit_chapter",
        novel_id="repair-budget",
        chapter=2,
        data={"content": "æ¾œ" * 1000, "summary": "A clean retry without re-prepare should still be blocked."},
    )
    assert blocked.success is False
    assert "Call action='prepare_chapter' again" in str(blocked.error)

    reprepared = tool.execute(
        action="prepare_chapter",
        novel_id="repair-budget",
        chapter=2,
        title="Second Revised",
        data={"outline": "A materially revised second scene.", "target_chars": 1000},
    )
    assert reprepared.success
    assert reprepared.data["pending_draft"] is None

    clean_second = ("æ¾œ" * 500) + ("ç¯ä¸‹çš„ç™½ç“·ç¢Ÿåç€ä¸€åœˆæ¸©é’çš„å…‰ï¼Œå¥¹ä»¬æŠŠå½“æ—¥çš„å·¥å…·ä¸€ä»¶ä»¶å½’ä½ã€‚" * 18)
    committed = tool.execute(
        action="commit_chapter",
        novel_id="repair-budget",
        chapter=2,
        data={"content": clean_second, "summary": "The revised second scene finally diverges."},
    )
    assert committed.success is True


def test_serial_novel_refuses_skipping_incomplete_active_chapter(tmp_path: Path) -> None:
    tool = SerialNovelTool({"project_root": tmp_path})
    assert tool.execute(
        action="bootstrap",
        novel_id="skip-guard",
        title="Skip Guard",
        brief="Write a long-form GL serial with multiple chapters.",
        target_chars=2000,
        chapter_target_chars=1000,
    ).success
    _configure(tool, "skip-guard")

    repeated = (
        "她把修好的杯子放回木架，窗外雨声压低了屋内的谈话。"
        "两个人各自收拾工具，谁也没有催促谁先离开。门边的伞还滴着水，"
        "她们决定再等一会儿。"
    )
    first = repeated + ("潮" * 1000)
    assert tool.execute(
        action="prepare_chapter",
        novel_id="skip-guard",
        chapter=1,
        title="First",
        data={"outline": "First complete scene.", "target_chars": 1000},
    ).success
    assert tool.execute(
        action="commit_chapter",
        novel_id="skip-guard",
        chapter=1,
        data={"content": first, "summary": "First scene."},
    ).success

    assert tool.execute(
        action="prepare_chapter",
        novel_id="skip-guard",
        chapter=2,
        title="Second",
        data={"outline": "Second complete scene.", "target_chars": 1000},
    ).success
    rejected = tool.execute(
        action="commit_chapter",
        novel_id="skip-guard",
        chapter=2,
        data={
            "content": ("汐" * 500) + repeated + ("汐" * 500),
            "summary": "Second scene repeats the first.",
        },
    )
    assert rejected.success is False

    skipped = tool.execute(
        action="prepare_chapter",
        novel_id="skip-guard",
        chapter=3,
        title="Third",
        data={"outline": "An incorrectly skipped chapter.", "target_chars": 1000},
    )
    assert skipped.success is False
    assert "Chapter 2 is prepared but not committed" in str(skipped.error)

    status = tool.execute(action="status", novel_id="skip-guard")
    assert status.success is True
    assert status.data["active_chapter"] == 2
    assert not (tmp_path / "novels" / "skip-guard" / "control-cards" / "chapter-0003.json").exists()

    reprepared = tool.execute(
        action="prepare_chapter",
        novel_id="skip-guard",
        chapter=2,
        title="Second Revised",
        data={"outline": "A materially revised second scene.", "target_chars": 1000},
    )
    assert reprepared.success is True
    assert reprepared.data["chapter"] == 2


def test_serial_novel_infers_only_active_project_when_model_omits_id(tmp_path: Path) -> None:
    tool = SerialNovelTool({"project_root": tmp_path})
    assert tool.execute(
        action="bootstrap",
        novel_id="active-project",
        title="Active Project",
        brief="Recover a provider tool call that omitted the known active project id.",
        target_chars=1000,
        chapter_target_chars=1000,
    ).success
    _configure(tool, "active-project")
    assert tool.execute(
        action="prepare_chapter",
        novel_id="active-project",
        chapter=1,
        title="Draft",
        data={"outline": "One complete scene.", "target_chars": 1000},
    ).success

    inferred = tool.execute(
        action="commit_chapter",
        chapter=1,
        data={"content": "潮" * 1000, "summary": "Committed through safe active-project inference."},
    )

    assert inferred.success is True
    assert inferred.data["project"]["novel_id"] == "active-project"


def test_serial_novel_refuses_ambiguous_active_project_inference(tmp_path: Path) -> None:
    tool = SerialNovelTool({"project_root": tmp_path})
    for novel_id in ("first-active", "second-active"):
        assert tool.execute(
            action="bootstrap",
            novel_id=novel_id,
            title=novel_id,
            brief="Ambiguity test.",
            target_chars=1000,
            chapter_target_chars=1000,
        ).success
        _configure(tool, novel_id)
        assert tool.execute(
            action="prepare_chapter",
            novel_id=novel_id,
            chapter=1,
            title="Draft",
            data={"outline": "One scene."},
        ).success

    result = tool.execute(action="status")

    assert result.success is True
    assert "Multiple Writer projects are available" in result.output

    blocked = tool.execute(action="context")
    assert blocked.success is False
    assert "multiple Writer projects have active chapters" in str(blocked.error)


def test_serial_novel_audits_actual_100k_character_manuscript(tmp_path: Path) -> None:
    tool = SerialNovelTool({"project_root": tmp_path})
    assert tool.execute(
        action="bootstrap",
        novel_id="glass-tide",
        title="Glass Tide",
        brief="An original-world, female-led, multi-heroine GL slice-of-life novel with delicate prose.",
        target_chars=100000,
        chapter_target_chars=4000,
    ).success
    _configure(tool, "glass-tide")

    for chapter in range(1, 26):
        assert tool.execute(
            action="prepare_chapter",
            novel_id="glass-tide",
            chapter=chapter,
            title=f"Tide Calendar {chapter}",
            data={
                "outline": f"Daily-life scene {chapter} advances a distinct relationship and civic obligation.",
                "continuity_requirements": [f"preserve consequences from chapter {chapter - 1}"],
                "relationship_progression": [f"relationship beat {chapter}"],
                "ending_hook": f"quiet unresolved choice {chapter}",
                "target_chars": 4000,
            },
        ).success
        chapter_fill = chr(0x4E00 + chapter)
        content = f"第{chapter}章，潮历记录了新的清晨。" + (chapter_fill * 3990)
        assert tool.execute(
            action="commit_chapter",
            novel_id="glass-tide",
            chapter=chapter,
            data={
                "content": content,
                "summary": f"Chapter {chapter} changes one relationship through an ordinary shared task.",
                "key_events": [f"daily event {chapter}"],
                "relationship_updates": [f"relationship change {chapter}"],
                "timeline_updates": [f"day {chapter}"],
                "opened_threads": [f"thread {chapter}"],
                "resolved_threads": [f"thread {chapter - 3}"] if chapter > 3 else [],
            },
        ).success

    audit = tool.execute(action="audit", novel_id="glass-tide")
    assert audit.success is True
    assert audit.data["disk_total_chars"] >= 100000
    assert audit.data["disk_chapter_count"] == 25
    assert audit.data["completion_ready"] is True
    assert audit.data["reader_manuscript_path"] == str(tmp_path / "novel" / "glass-tide" / "manuscript.txt")
    assert (tmp_path / "novel" / "glass-tide" / "chapter-0025.txt").is_file()

    completed = tool.execute(action="complete", novel_id="glass-tide")
    assert completed.success is True
    assert completed.data["status"] == "complete"
    completed_at = json.loads(
        (tmp_path / "novels" / "glass-tide" / "tracking" / "state.json").read_text(encoding="utf-8")
    )["completed_at"]
    completed_again = tool.execute(action="complete", novel_id="glass-tide")
    assert completed_again.success is True
    assert "already complete" in completed_again.output
    assert "No files were changed" in completed_again.output
    assert json.loads(
        (tmp_path / "novels" / "glass-tide" / "tracking" / "state.json").read_text(encoding="utf-8")
    )["completed_at"] == completed_at

    extra = tool.execute(
        action="prepare_chapter",
        novel_id="glass-tide",
        chapter=26,
        title="Unneeded",
        data={"outline": "This chapter must not be opened after completion."},
    )
    assert extra.success is False
    assert "target is already met" in str(extra.error)

    recommit = tool.execute(
        action="commit_chapter",
        novel_id="glass-tide",
        chapter=25,
        data={"content": "澜" * 4000, "summary": "Must not overwrite a completed project."},
    )
    assert recommit.success is False
    assert "project is complete" in str(recommit.error)


def test_writer_has_a_deliberately_small_native_tool_surface(tmp_path: Path) -> None:
    names = {
        schema["function"]["name"]
        for schema in ToolExecutor(project_root=tmp_path).get_tool_schemas(mode="writer")
    }
    assert "serial_novel" in names
    assert {"web_search", "web_fetch", "memory_retrieval", "memory_manager"} <= names
    assert not {"str_replace_editor", "create_file", "codebase-retrieval"} & names
    assert not {
        "command_exec",
        "browser_controler",
        "file_ops",
        "delete_file",
        "skill_lookup",
        "list_mcp_resources",
        "read_mcp_resource",
        "text_to_image",
        "text_to_video",
    } & names


def test_writer_generic_editor_cannot_mutate_native_novel_files(tmp_path: Path) -> None:
    chapter = tmp_path / "novel" / "managed" / "chapter-0001.txt"
    chapter.parent.mkdir(parents=True)
    chapter.write_text("original", encoding="utf-8")
    executor = ToolExecutor(project_root=tmp_path)
    executor.update_context("agent", SimpleNamespace(mode="writer"))

    result = executor.execute(
        "str_replace_editor",
        {"command": "str_replace", "path": str(chapter), "old_str": "original", "new_str": "changed"},
    )
    assert result.success is False
    assert "transaction-managed" in str(result.error)
    assert chapter.read_text(encoding="utf-8") == "original"


def test_chinese_novel_intent_recommends_writer() -> None:
    result = ModeSwitchTool().execute(operation="recommend", query="写一部长篇架空世界GL连载小说")
    assert result.success is True
    assert result.data["recommended_mode"] == "writer"


def test_writer_prompt_requires_native_project_and_verified_completion() -> None:
    prompt = build_system_prompt(model_name="Test Model", mode="writer")
    assert "Automatic Novel Trigger" in prompt
    assert "100k+ Marathon Rule" in prompt
    assert "immediately call `serial_novel" in prompt
    assert "Pass an explicit top-level `title` whenever you have one" in prompt
    assert "Only call `complete` when the audit says" in prompt
    assert "no terminal, browser controller, runtime-plugin" in prompt
    assert "Keep raw chapter prose out of assistant chat" in prompt
    assert "Do not ask for or simulate unavailable tools such as `str_replace_editor`" in prompt
    assert "novel/<novel-id>/" in prompt
    assert "Never edit files under `novels/` or `novel/`" in prompt

    other_mode_prompt = build_system_prompt(model_name="Test Model", mode="reverie")
    assert "explicit request to write or continue a novel" in other_mode_prompt
    assert "`switch_mode` to `writer`" in other_mode_prompt


def test_writer_novel_turn_requires_serial_novel_as_first_tool(tmp_path: Path) -> None:
    config = SimpleNamespace(
        active_model_source="standard",
        api_max_retries=0,
        api_initial_backoff=0.01,
        api_timeout=30,
        api_enable_debug_logging=False,
    )
    agent = ReverieAgent(
        base_url="https://example.test/v1",
        api_key="test",
        model="test-model",
        project_root=tmp_path,
        provider="openai-sdk",
        mode="writer",
        config=config,
    )
    agent.messages = [{"role": "user", "content": "写一部长篇GL连载小说"}]
    tools = [{"type": "function", "function": {"name": "serial_novel", "parameters": {"type": "object"}}}]

    kwargs = agent._build_openai_chat_completion_kwargs(messages=agent._build_messages(), tools=tools, stream=True)
    assert kwargs["tool_choice"] == {"type": "function", "function": {"name": "serial_novel"}}
    assert agent._writer_anthropic_tool_choice() == {"type": "tool", "name": "serial_novel"}

    agent.messages.append(
        {
            "role": "assistant",
            "content": None,
            "tool_calls": [
                {
                    "id": "call_1",
                    "type": "function",
                    "function": {"name": "serial_novel", "arguments": '{"action":"bootstrap"}'},
                }
            ],
        }
    )
    agent.messages.append({"role": "tool", "tool_call_id": "call_1", "content": "Bootstrapped project."})
    assert agent._writer_native_tool_choice() is None


def test_writer_active_chapter_relocks_serial_novel_tool_choice(tmp_path: Path) -> None:
    tool = SerialNovelTool({"project_root": tmp_path})
    bootstrap = tool.execute(
        action="bootstrap",
        novel_id="writer-active-lock",
        title="Writer Active Lock",
        brief="写一部长篇GL连载小说，女主群像，日常向。",
        target_chars=100000,
        chapter_target_chars=4000,
    )
    assert bootstrap.success is True
    _configure(tool, "writer-active-lock")
    prepared = tool.execute(
        action="prepare_chapter",
        novel_id="writer-active-lock",
        chapter=1,
        title="指尖的温度",
        data={
            "outline": "第一章《指尖的温度》：她们在雨后码头相遇，用安静的日常推进关系。",
            "scene_beats": ["码头相遇", "共进晚餐", "约好明日再见"],
            "continuity_requirements": ["保持日常细腻风格"],
            "relationship_progression": ["女主与另一位女主建立更稳定的信任"],
            "opening_hook": "雨后的水汽还停在木栏上。",
            "ending_hook": "她们约好明天一起去看市集。",
            "target_chars": 4000,
        },
    )
    assert prepared.success is True

    config = SimpleNamespace(
        active_model_source="standard",
        api_max_retries=0,
        api_initial_backoff=0.01,
        api_timeout=30,
        api_enable_debug_logging=False,
    )
    agent = ReverieAgent(
        base_url="https://example.test/v1",
        api_key="test",
        model="test-model",
        project_root=tmp_path,
        provider="openai-sdk",
        mode="writer",
        config=config,
    )
    agent.messages = [
        {"role": "user", "content": "continue"},
    ]

    assert agent._writer_native_tool_choice() == {"type": "function", "function": {"name": "serial_novel"}}

    agent.messages.extend(
        [
            {
                "role": "assistant",
                "content": None,
                "tool_calls": [
                    {
                        "id": "call_1",
                        "type": "function",
                        "function": {
                            "name": "serial_novel",
                            "arguments": '{"action":"context","novel_id":"writer-active-lock"}',
                        },
                    }
                ],
            },
            {"role": "tool", "tool_call_id": "call_1", "content": "Prepared chapter context."},
        ]
    )

    assert agent._writer_native_tool_choice() is None


def test_writer_append_only_recovery_does_not_force_another_tool_call(tmp_path: Path) -> None:
    tool = SerialNovelTool({"project_root": tmp_path})
    assert tool.execute(
        action="bootstrap",
        novel_id="writer-append-recovery",
        title="Writer Append Recovery",
        brief="写一部长篇GL连载小说，女主群像，日常向。",
        target_chars=100000,
        chapter_target_chars=4000,
    ).success
    _configure(tool, "writer-append-recovery")
    assert tool.execute(
        action="prepare_chapter",
        novel_id="writer-append-recovery",
        chapter=1,
        title="潮湿的夜路",
        data={
            "outline": "第一章《潮湿的夜路》：女主在雨夜回城，用细腻日常推进关系。",
            "scene_beats": ["回城", "路灯下交谈", "分别前约定重逢"],
            "continuity_requirements": ["保持细腻日常风格"],
            "relationship_progression": ["两位女主建立试探性的好感"],
            "opening_hook": "雨水沿着屋檐慢慢滴下。",
            "ending_hook": "她们约好下次一起看潮汐灯。",
            "target_chars": 4000,
        },
    ).success
    rejected = tool.execute(
        action="commit_chapter",
        novel_id="writer-append-recovery",
        chapter=1,
        data={"content": "潮" * 1600, "summary": "A complete but short scene."},
    )
    assert rejected.success is False

    config = SimpleNamespace(
        active_model_source="standard",
        api_max_retries=0,
        api_initial_backoff=0.01,
        api_timeout=30,
        api_enable_debug_logging=False,
    )
    agent = ReverieAgent(
        base_url="https://example.test/v1",
        api_key="test",
        model="test-model",
        project_root=tmp_path,
        provider="openai-sdk",
        mode="writer",
        config=config,
    )
    agent.messages = [{"role": "user", "content": "continue"}]

    assert agent._writer_native_tool_choice() is None


def test_writer_committed_chapter_relocks_serial_novel_for_next_chapter(tmp_path: Path) -> None:
    tool = SerialNovelTool({"project_root": tmp_path})
    assert tool.execute(
        action="bootstrap",
        novel_id="writer-next-chapter-lock",
        title="Writer Next Chapter Lock",
        brief="写一部长篇GL连载小说，女主群像，日常向。",
        target_chars=100000,
        chapter_target_chars=4000,
    ).success
    _configure(tool, "writer-next-chapter-lock")
    assert tool.execute(
        action="prepare_chapter",
        novel_id="writer-next-chapter-lock",
        chapter=1,
        title="雾里的茶香",
        data={
            "outline": "第一章《雾里的茶香》：两位女主在清晨茶馆初遇，用细腻日常推进关系。",
            "scene_beats": ["开门", "点茶", "试探交谈"],
            "continuity_requirements": ["保持原创架空世界观和细腻日常风格"],
            "relationship_progression": ["从陌生走向试探性的信任"],
            "opening_hook": "雾从街口慢慢漫进来。",
            "ending_hook": "她们约好明日再见。",
            "target_chars": 4000,
        },
    ).success
    assert tool.execute(
        action="commit_chapter",
        novel_id="writer-next-chapter-lock",
        chapter=1,
        data={
            "content": "潮" * 4200,
            "summary": "Chapter one commits cleanly so Writer should move on to chapter two planning.",
        },
    ).success

    config = SimpleNamespace(
        active_model_source="standard",
        api_max_retries=0,
        api_initial_backoff=0.01,
        api_timeout=30,
        api_enable_debug_logging=False,
    )
    agent = ReverieAgent(
        base_url="https://example.test/v1",
        api_key="test",
        model="test-model",
        project_root=tmp_path,
        provider="openai-sdk",
        mode="writer",
        config=config,
    )
    agent.messages = [
        {"role": "user", "content": "continue"},
        {
            "role": "assistant",
            "content": None,
            "tool_calls": [
                {
                    "id": "call_commit",
                    "type": "function",
                    "function": {
                        "name": "serial_novel",
                        "arguments": '{"action":"commit_chapter","novel_id":"writer-next-chapter-lock","chapter":1}',
                    },
                }
            ],
        },
        {"role": "tool", "tool_call_id": "call_commit", "content": "Chapter 1 committed successfully."},
    ]

    assert agent._writer_should_hide_tools_for_direct_prose() is False
    assert agent._writer_native_tool_choice() == {"type": "function", "function": {"name": "serial_novel"}}


def test_writer_active_chapter_hides_tools_after_native_context(tmp_path: Path) -> None:
    tool = SerialNovelTool({"project_root": tmp_path})
    assert tool.execute(
        action="bootstrap",
        novel_id="writer-direct-prose-lane",
        title="Writer Direct Prose Lane",
        brief="写一部长篇GL连载小说，女主群像，日常向。",
        target_chars=100000,
        chapter_target_chars=4000,
    ).success
    _configure(tool, "writer-direct-prose-lane")
    assert tool.execute(
        action="prepare_chapter",
        novel_id="writer-direct-prose-lane",
        chapter=1,
        title="雨后的石阶",
        data={
            "outline": "第一章《雨后的石阶》：女主在雨夜回家，用安静日常推进关系。",
            "scene_beats": ["回家", "楼道寒暄", "窗边停留"],
            "continuity_requirements": ["保持细腻日常风格"],
            "relationship_progression": ["两位女主建立最初的熟悉感"],
            "opening_hook": "灯影落在潮湿的石阶上。",
            "ending_hook": "她把茶杯放在窗沿边。",
            "target_chars": 4000,
        },
    ).success

    config = SimpleNamespace(
        active_model_source="standard",
        api_max_retries=0,
        api_initial_backoff=0.01,
        api_timeout=30,
        api_enable_debug_logging=False,
    )
    agent = ReverieAgent(
        base_url="https://example.test/v1",
        api_key="test",
        model="test-model",
        project_root=tmp_path,
        provider="openai-sdk",
        mode="writer",
        config=config,
    )
    agent.messages = [
        {"role": "user", "content": "continue"},
        {
            "role": "assistant",
            "content": None,
            "tool_calls": [
                {
                    "id": "call_1",
                    "type": "function",
                    "function": {
                        "name": "serial_novel",
                        "arguments": '{"action":"context","novel_id":"writer-direct-prose-lane"}',
                    },
                }
            ],
        },
        {"role": "tool", "tool_call_id": "call_1", "content": "Prepared chapter context."},
    ]

    assert agent._writer_should_hide_tools_for_direct_prose() is True
    assert agent.get_visible_tool_schemas() == []


def test_writer_context_infers_active_project_from_recent_novel_id_when_multiple_projects_exist(
    tmp_path: Path,
) -> None:
    tool = SerialNovelTool({"project_root": tmp_path})
    for novel_id in ("writer-direct-prose-a", "writer-direct-prose-b"):
        assert tool.execute(
            action="bootstrap",
            novel_id=novel_id,
            title=f"Project {novel_id}",
            brief="写一部长篇GL连载小说，女主群像，日常向。",
            target_chars=100000,
            chapter_target_chars=4000,
        ).success
        _configure(tool, novel_id)
        assert tool.execute(
            action="prepare_chapter",
            novel_id=novel_id,
            chapter=1,
            title="雨后的石阶",
            data={
                "outline": "第一章《雨后的石阶》：女主在雨夜回家，用安静日常推进关系。",
                "scene_beats": ["回家", "楼道寒暄", "窗边停留"],
                "continuity_requirements": ["保持细腻日常风格"],
                "relationship_progression": ["两位女主建立最初的熟悉感"],
                "opening_hook": "灯影落在潮湿的石阶上。",
                "ending_hook": "她把茶杯放在窗沿边。",
                "target_chars": 4000,
            },
        ).success

    config = SimpleNamespace(
        active_model_source="standard",
        api_max_retries=0,
        api_initial_backoff=0.01,
        api_timeout=30,
        api_enable_debug_logging=False,
    )
    agent = ReverieAgent(
        base_url="https://example.test/v1",
        api_key="test",
        model="test-model",
        project_root=tmp_path,
        provider="openai-sdk",
        mode="writer",
        config=config,
    )
    agent.messages = [
        {"role": "user", "content": "continue"},
        {
            "role": "assistant",
            "content": None,
            "tool_calls": [
                {
                    "id": "call_1",
                    "type": "function",
                    "function": {
                        "name": "serial_novel",
                        "arguments": '{"action":"context","novel_id":"writer-direct-prose-b"}',
                    },
                }
            ],
        },
        {"role": "tool", "tool_call_id": "call_1", "content": "Prepared chapter context."},
    ]

    active_project = agent._writer_active_project_state()
    assert active_project is not None
    assert active_project["novel_id"] == "writer-direct-prose-b"
    assert agent._writer_native_tool_choice() is None
    assert agent._writer_should_hide_tools_for_direct_prose() is True
    assert agent.get_visible_tool_schemas() == []


def test_writer_promotes_textual_serial_novel_wrapper_in_direct_prose_lane(tmp_path: Path) -> None:
    tool = SerialNovelTool({"project_root": tmp_path})
    assert tool.execute(
        action="bootstrap",
        novel_id="writer-textual-wrapper",
        title="Writer Textual Wrapper",
        brief="写一部长篇GL连载小说，女主群像，日常向。",
        target_chars=100000,
        chapter_target_chars=4000,
    ).success
    _configure(tool, "writer-textual-wrapper")
    assert tool.execute(
        action="prepare_chapter",
        novel_id="writer-textual-wrapper",
        chapter=1,
        title="雨天的访客",
        data={
            "outline": "第一章《雨天的访客》：女主在茶馆与来客相遇，用安静日常推进关系。",
            "scene_beats": ["茶馆", "避雨", "交谈"],
            "continuity_requirements": ["保持细腻日常风格"],
            "relationship_progression": ["两位女主建立初步默契"],
            "opening_hook": "雨丝敲在木窗上。",
            "ending_hook": "她说下次还会再来。",
            "target_chars": 4000,
        },
    ).success

    config = SimpleNamespace(
        active_model_source="standard",
        api_max_retries=0,
        api_initial_backoff=0.01,
        api_timeout=30,
        api_enable_debug_logging=False,
    )
    agent = ReverieAgent(
        base_url="https://example.test/v1",
        api_key="test",
        model="test-model",
        project_root=tmp_path,
        provider="openai-sdk",
        mode="writer",
        config=config,
    )
    agent.messages = [
        {"role": "user", "content": "continue"},
        {
            "role": "assistant",
            "content": None,
            "tool_calls": [
                {
                    "id": "call_1",
                    "type": "function",
                    "function": {
                        "name": "serial_novel",
                        "arguments": '{"action":"context","novel_id":"writer-textual-wrapper"}',
                    },
                }
            ],
        },
        {"role": "tool", "tool_call_id": "call_1", "content": "Prepared chapter context."},
    ]

    state = _StreamingTurnState()
    state.collected_content = """<tool_call>
<function=serial_novel>
<parameter=action>
commit_chapter
</parameter>
<parameter=novel_id>
writer-textual-wrapper
</parameter>
<parameter=chapter>
1
</parameter>
<parameter=data>
{"content":"潮""" + ("潮" * 1600) + """","summary":"Rainy-day chapter."}
</parameter>
</function>
</tool_call>"""

    promoted = agent._promote_writer_json_tool_call(state)
    assert promoted is True
    assert state.tool_calls[0]["function"]["name"] == "serial_novel"
    arguments = parse_tool_arguments(state.tool_calls[0]["function"]["arguments"])
    assert arguments["action"] == "commit_chapter"
    assert arguments["novel_id"] == "writer-textual-wrapper"
    assert arguments["chapter"] == 1
    assert arguments["data"]["summary"] == "Rainy-day chapter."
    assert arguments["data"]["content"].startswith("潮")


def test_writer_promotes_embedded_textual_tool_wrapper_before_direct_prose_commit(tmp_path: Path) -> None:
    tool = SerialNovelTool({"project_root": tmp_path})
    assert tool.execute(
        action="bootstrap",
        novel_id="writer-embedded-wrapper",
        title="Writer Embedded Wrapper",
        brief="å†™ä¸€éƒ¨é•¿ç¯‡GLè¿žè½½å°è¯´ï¼Œå¥³ä¸»ç¾¤åƒï¼Œæ—¥å¸¸å‘ã€‚",
        target_chars=100000,
        chapter_target_chars=4000,
    ).success
    _configure(tool, "writer-embedded-wrapper")
    assert tool.execute(
        action="prepare_chapter",
        novel_id="writer-embedded-wrapper",
        chapter=1,
        title="é›¨éœ²è½¬è§’",
        data={
            "outline": "ç¬¬ä¸€ç« ã€Šé›¨éœ²è½¬è§’ã€‹ï¼šå¥³ä¸»åœ¨é›¨å¤œé‡Œä¸Žå¦ä¸€ä½å¥³ä¸»ç›¸é‡ã€‚",
            "scene_beats": ["é›¨å¤œç›¸é‡", "å…±ä¼åŒè¡Œ", "åˆ†åˆ«åçš„çº¦å®š"],
            "continuity_requirements": ["ä¿æŒåŽŸåˆ›æž¶ç©ºä¸–ç•Œè§‚å’Œç»†è…»æ–‡é£Ž"],
            "relationship_progression": ["ä¸¤äººä»Žé™Œç”Ÿåˆ°äº§ç”Ÿåæ­¥ä¿¡ä»»"],
            "opening_hook": "é›¨ç‚¹é¡ºç€çŸ³é˜¶æ¾„æ¾„åœ°å¾€ä¸‹æ»šã€‚",
            "ending_hook": "å¥¹ä»¬çº¦å¥½æ˜Žæ—¥å†è§ã€‚",
            "target_chars": 4000,
        },
    ).success

    config = SimpleNamespace(
        active_model_source="standard",
        api_max_retries=0,
        api_initial_backoff=0.01,
        api_timeout=30,
        api_enable_debug_logging=False,
    )
    agent = ReverieAgent(
        base_url="https://example.test/v1",
        api_key="test",
        model="test-model",
        project_root=tmp_path,
        provider="openai-sdk",
        mode="writer",
        config=config,
    )
    state = _StreamingTurnState()
    state.collected_content = (
        "I need to provide the actual chapter draft next.\n\n"
        "<tool_call>\n"
        "<function=serial_novel>\n"
        "<parameter=action>\n"
        "commit_chapter\n"
        "</parameter>\n"
        "<parameter=novel_id>\n"
        "writer-embedded-wrapper\n"
        "</parameter>\n"
        "<parameter=chapter>\n"
        "1\n"
        "</parameter>\n"
        "<parameter=data>\n"
        '{"content":"'
        + ("æ½®" * 1800)
        + '","summary":"Embedded wrapper chapter."}\n'
        "</parameter>\n"
        "</function>\n"
        "</tool_call>"
    )

    promoted = agent._promote_writer_json_tool_call(state)
    assert promoted is True
    assert state.tool_calls[0]["function"]["name"] == "serial_novel"
    arguments = parse_tool_arguments(state.tool_calls[0]["function"]["arguments"])
    assert arguments["action"] == "commit_chapter"
    assert arguments["novel_id"] == "writer-embedded-wrapper"
    assert arguments["chapter"] == 1
    assert arguments["data"]["summary"] == "Embedded wrapper chapter."
    assert arguments["data"]["content"].startswith("æ½®")
    assert state.collected_content == ""


def test_writer_retries_plain_prose_instead_of_executing_metadata_only_commit_wrapper(
    tmp_path: Path,
) -> None:
    tool = SerialNovelTool({"project_root": tmp_path})
    assert tool.execute(
        action="bootstrap",
        novel_id="writer-direct-prose-retry",
        title="Writer Direct Prose Retry",
        brief="å†™ä¸€éƒ¨é•¿ç¯‡GLè¿žè½½å°è¯´ï¼Œå¥³ä¸»ç¾¤åƒï¼Œæ—¥å¸¸å‘ã€‚",
        target_chars=100000,
        chapter_target_chars=4000,
    ).success
    _configure(tool, "writer-direct-prose-retry")
    assert tool.execute(
        action="prepare_chapter",
        novel_id="writer-direct-prose-retry",
        chapter=1,
        title="é›¨åŽçš„çŸ³é˜¶",
        data={
            "outline": "ç¬¬ä¸€ç« ã€Šé›¨åŽçš„çŸ³é˜¶ã€‹ï¼šå¥³ä¸»åœ¨é›¨å¤œå›žå®¶ï¼Œç”¨å®‰é™æ—¥å¸¸æŽ¨è¿›å…³ç³»ã€‚",
            "scene_beats": ["å›žå®¶", "æ¥¼é“å¯’æš„", "çª—è¾¹åœç•™"],
            "continuity_requirements": ["ä¿æŒç»†è…»æ—¥å¸¸é£Žæ ¼"],
            "relationship_progression": ["ä¸¤ä½å¥³ä¸»å»ºç«‹æœ€åˆçš„ç†Ÿæ‚‰æ„Ÿ"],
            "opening_hook": "ç¯å½±è½åœ¨æ½®æ¹¿çš„çŸ³é˜¶ä¸Šã€‚",
            "ending_hook": "å¥¹æŠŠèŒ¶æ¯æ”¾åœ¨çª—æ²¿è¾¹ã€‚",
            "target_chars": 4000,
        },
    ).success

    config = SimpleNamespace(
        active_model_source="standard",
        api_max_retries=0,
        api_initial_backoff=0.01,
        api_timeout=30,
        api_enable_debug_logging=False,
    )
    agent = ReverieAgent(
        base_url="https://example.test/v1",
        api_key="test",
        model="test-model",
        project_root=tmp_path,
        provider="openai-sdk",
        mode="writer",
        config=config,
    )
    agent.messages = [
        {"role": "user", "content": "continue"},
        {
            "role": "assistant",
            "content": None,
            "tool_calls": [
                {
                    "id": "call_1",
                    "type": "function",
                    "function": {
                        "name": "serial_novel",
                        "arguments": '{"action":"context","novel_id":"writer-direct-prose-retry"}',
                    },
                }
            ],
        },
        {"role": "tool", "tool_call_id": "call_1", "content": "Prepared chapter context."},
    ]

    relay_messages = list(agent.messages)
    state = _StreamingTurnState()
    state.tool_calls = [
        {
            "id": "writer_native_bad",
            "type": "function",
            "function": {
                "name": "serial_novel",
                "arguments": json.dumps(
                    {
                        "action": "commit_chapter",
                        "novel_id": "writer-direct-prose-retry",
                        "chapter": 1,
                        "data": {
                            "summary": "Metadata only wrapper that should trigger a prose retry.",
                        },
                    },
                    ensure_ascii=False,
                ),
            },
        }
    ]

    outcome, clean_content = agent._commit_stream_state(
        state=state,
        request_messages=relay_messages,
        messages=relay_messages,
        session_id="writer-direct-prose-retry-session",
    )

    assert outcome == "retry_direct_prose"
    assert clean_content == ""
    assert state.tool_calls == []
    assert agent.messages[-1]["role"] == "system"
    assert "Do not emit JSON, XML, summaries, or serial_novel calls." in agent.messages[-1]["content"]
    assert "Write only the chapter prose in plain text" in agent.messages[-1]["content"]


def test_writer_retries_direct_prose_that_only_repeats_preserved_tail(tmp_path: Path) -> None:
    tool = SerialNovelTool({"project_root": tmp_path})
    assert tool.execute(
        action="bootstrap",
        novel_id="writer-repeat-tail",
        title="Writer Repeat Tail",
        brief="å†™ä¸€éƒ¨é•¿ç¯‡GLè¿žè½½å°è¯´ï¼Œå¥³ä¸»ç¾¤åƒï¼Œæ—¥å¸¸å‘ã€‚",
        target_chars=100000,
        chapter_target_chars=4000,
    ).success
    _configure(tool, "writer-repeat-tail")
    assert tool.execute(
        action="prepare_chapter",
        novel_id="writer-repeat-tail",
        chapter=1,
        title="è¿œç¯ä¸‹çš„èŒ¶ç›˜",
        data={
            "outline": "ç¬¬ä¸€ç« ã€Šè¿œç¯ä¸‹çš„èŒ¶ç›˜ã€‹ï¼šå¥³ä¸»åœ¨èŒ¶é¦™å’Œå¯¹è¯é‡Œå¼€å§‹å»ºç«‹å…³ç³»ã€‚",
            "scene_beats": ["æ”¶æ‹¾æ¡Œé¢", "é€’å‡ºèŒ¶ç›˜", "å®‰é™å¯¹è§†"],
            "continuity_requirements": ["ä¿æŒç»†è…»æ—¥å¸¸å‘ä¸ŽåŽŸåˆ›æž¶ç©ºä¸–ç•Œè§‚"],
            "relationship_progression": ["ä¸¤äººä»Žå°å¿ƒè¯•æŽ¢åˆ°å‡ºçŽ°åˆæ­¥é»˜å¥‘"],
            "opening_hook": "èŒ¶æ°´åœ¨çª„å£çš„å¾®å…‰é‡Œåå°„å‡ºä¸€çº¿é‡‘è‰²ã€‚",
            "ending_hook": "å¥¹ä»¬æŠŠæœ€åŽä¸€ç›èŒ¶ç‚¹å¹¶æŽ’æ‘†å¥½ã€‚",
            "target_chars": 4000,
        },
    ).success
    rejected = tool.execute(
        action="commit_chapter",
        novel_id="writer-repeat-tail",
        chapter=1,
        data={
            "content": (
                "å¥¹æŠŠèŒ¶ç›˜æ”¶åˆ°çª—å°ä¸Šï¼Œå¬è§é›¨å£°åœ¨ç“¦æªä¸Šæ…¢æ…¢æ»šè¿‡ã€‚\n\n"
                "å¯¹é¢çš„å¥³å­©æ²¡æœ‰ç«‹åˆ»è¯´è¯ï¼Œåªæ˜¯ç”¨æŒ‡å°–è½»è½»åŽ‹ä½çƒ­æ°”ã€‚\n\n"
                "å¥¹æŠŠæœ€åŽä¸€åªèŒ¶ç›æŽ¨åˆ°å¯¹æ–¹é¢å‰ï¼Œæ£‰å¸ƒè¢–å£è¹­è¿‡æ¡Œæ²¿ï¼Œç•™ä¸‹ä¸€å°æ®µæ¸©çƒ­çš„æ°´ç—•ã€‚"
            ),
            "summary": "A complete but intentionally short tea-room scene.",
        },
    )
    assert rejected.success is False

    config = SimpleNamespace(
        active_model_source="standard",
        api_max_retries=0,
        api_initial_backoff=0.01,
        api_timeout=30,
        api_enable_debug_logging=False,
    )
    agent = ReverieAgent(
        base_url="https://example.test/v1",
        api_key="test",
        model="test-model",
        project_root=tmp_path,
        provider="openai-sdk",
        mode="writer",
        config=config,
    )
    agent.messages = [
        {"role": "user", "content": "continue"},
        {
            "role": "assistant",
            "content": None,
            "tool_calls": [
                {
                    "id": "call_1",
                    "type": "function",
                    "function": {
                        "name": "serial_novel",
                        "arguments": '{"action":"context","novel_id":"writer-repeat-tail"}',
                    },
                }
            ],
        },
        {"role": "tool", "tool_call_id": "call_1", "content": "Prepared chapter context."},
    ]
    active_project = agent._writer_active_project_state()
    assert active_project is not None
    preserved = agent._writer_pending_draft_content(active_project)
    repeated_tail = preserved.split("\n\n")[-1]
    relay_messages = list(agent.messages)
    state = _StreamingTurnState(collected_content=repeated_tail)

    outcome, clean_content = agent._commit_stream_state(
        state=state,
        request_messages=relay_messages,
        messages=relay_messages,
        session_id="writer-repeat-tail-session",
    )

    assert outcome == "retry_direct_prose"
    assert clean_content == ""
    assert agent.messages[-1]["role"] == "system"
    assert "only repeated the preserved tail" in agent.messages[-1]["content"]
    assert "data.append_content automatically" in agent.messages[-1]["content"]


def test_writer_promotes_direct_prose_into_commit_tool_call(tmp_path: Path) -> None:
    tool = SerialNovelTool({"project_root": tmp_path})
    bootstrap = tool.execute(
        action="bootstrap",
        novel_id="writer-direct-prose",
        title="Writer Direct Prose",
        brief="写一部长篇GL连载小说，女主群像，日常向。",
        target_chars=100000,
        chapter_target_chars=4000,
    )
    assert bootstrap.success is True
    _configure(tool, "writer-direct-prose")
    prepared = tool.execute(
        action="prepare_chapter",
        novel_id="writer-direct-prose",
        chapter=1,
        title="指尖的温度",
        data={
            "outline": "第一章《指尖的温度》：女主在码头与另一位女主相遇，用细腻日常推进关系。",
            "scene_beats": ["码头相遇", "同行回城", "分开前约定再见"],
            "continuity_requirements": ["维持原创架空世界观和细腻文风"],
            "relationship_progression": ["两人从陌生到产生试探性信任"],
            "opening_hook": "海风把湿润的雾推向码头尽头。",
            "ending_hook": "她们约好明日去看市集的晨露花。",
            "target_chars": 4000,
        },
    )
    assert prepared.success is True

    config = SimpleNamespace(
        active_model_source="standard",
        api_max_retries=0,
        api_initial_backoff=0.01,
        api_timeout=30,
        api_enable_debug_logging=False,
    )
    agent = ReverieAgent(
        base_url="https://example.test/v1",
        api_key="test",
        model="test-model",
        project_root=tmp_path,
        provider="openai-sdk",
        mode="writer",
        config=config,
    )
    state = _StreamingTurnState()
    state.collected_content = (
        "第一章：指尖的温度\n\n"
        + "她站在码头边，看着雨水顺着木栏的纹理慢慢往下滚。" * 120
    )

    promoted = agent._promote_writer_direct_prose_commit(state)
    assert promoted is True
    assert state.tool_calls[0]["function"]["name"] == "serial_novel"
    arguments = json.loads(state.tool_calls[0]["function"]["arguments"])
    assert arguments["action"] == "commit_chapter"
    assert arguments["novel_id"] == "writer-direct-prose"
    assert arguments["chapter"] == 1
    assert arguments["data"]["content"].startswith("她站在码头边")


def test_writer_promotes_direct_prose_into_append_only_retry(tmp_path: Path) -> None:
    tool = SerialNovelTool({"project_root": tmp_path})
    assert tool.execute(
        action="bootstrap",
        novel_id="writer-direct-append",
        title="Writer Direct Append",
        brief="写一部长篇GL连载小说，女主群像，日常向。",
        target_chars=100000,
        chapter_target_chars=4000,
    ).success
    _configure(tool, "writer-direct-append")
    assert tool.execute(
        action="prepare_chapter",
        novel_id="writer-direct-append",
        chapter=1,
        title="潮汐长阶",
        data={
            "outline": "第一章《潮汐长阶》：女主夜里回到灯塔，情感在安静日常中慢慢推进。",
            "scene_beats": ["回塔", "整理衣摆", "窗前对话"],
            "continuity_requirements": ["保持原创架空世界观和细腻文风"],
            "relationship_progression": ["两人从陌生到建立信任"],
            "opening_hook": "风把雾推到石阶边上。",
            "ending_hook": "她们约好明早一起出门。",
            "target_chars": 4000,
        },
    ).success
    rejected = tool.execute(
        action="commit_chapter",
        novel_id="writer-direct-append",
        chapter=1,
        data={"content": "潮" * 1600, "summary": "A complete but short scene."},
    )
    assert rejected.success is False

    config = SimpleNamespace(
        active_model_source="standard",
        api_max_retries=0,
        api_initial_backoff=0.01,
        api_timeout=30,
        api_enable_debug_logging=False,
    )
    agent = ReverieAgent(
        base_url="https://example.test/v1",
        api_key="test",
        model="test-model",
        project_root=tmp_path,
        provider="openai-sdk",
        mode="writer",
        config=config,
    )
    state = _StreamingTurnState()
    state.collected_content = "她把潮湿的袖口轻轻拧干，又抬头去看窗外缓慢移动的雾。" * 120

    promoted = agent._promote_writer_direct_prose_commit(state)
    assert promoted is True
    arguments = json.loads(state.tool_calls[0]["function"]["arguments"])
    assert arguments["action"] == "commit_chapter"
    assert arguments["novel_id"] == "writer-direct-append"
    assert arguments["chapter"] == 1
    assert "append_content" in arguments["data"]
    assert "content" not in arguments["data"]
    assert arguments["data"]["append_content"].startswith("她把潮湿的袖口轻轻拧干")


def test_writer_promotes_short_append_only_direct_prose_into_commit_tool_call(tmp_path: Path) -> None:
    tool = SerialNovelTool({"project_root": tmp_path})
    assert tool.execute(
        action="bootstrap",
        novel_id="writer-short-append",
        title="Writer Short Append",
        brief="å†™ä¸€éƒ¨é•¿ç¯‡GLè¿žè½½å°è¯´ï¼Œå¥³ä¸»ç¾¤åƒï¼Œæ—¥å¸¸å‘ã€‚",
        target_chars=100000,
        chapter_target_chars=4000,
    ).success
    _configure(tool, "writer-short-append")
    assert tool.execute(
        action="prepare_chapter",
        novel_id="writer-short-append",
        chapter=1,
        title="çª—å°å°æ°”å€™",
        data={
            "outline": "ç¬¬ä¸€ç« ã€Šçª—å°å°æ°”å€™ã€‹ï¼šå¥³ä¸»åœ¨æ—¥å¸¸ç…§æ–™èŠ±æˆ¿çš„è¿‡ç¨‹ä¸­æŽ¨è¿›å…³ç³»ã€‚",
            "scene_beats": ["æ¸…æ™¨æµ‡æ°´", "æ•´ç†çª—å°", "è½»å£°å¯¹è¯"],
            "continuity_requirements": ["ä¿æŒæž¶ç©ºä¸–ç•Œè§‚ä¸Žç»†è…»æ—¥å¸¸é£Žæ ¼"],
            "relationship_progression": ["ä¸¤äººä»Žç”Ÿç–åˆ°äº§ç”Ÿè¯•æŽ¢æ€§ä¿¡ä»»"],
            "opening_hook": "æ•£éœ¾è¿˜åœåœ¨çª—æ£‚å¤–ä¾§ã€‚",
            "ending_hook": "å¥¹æŠŠçƒ­èŒ¶æŽ¨åˆ°å¯¹æ–¹æ‰‹è¾¹ã€‚",
            "target_chars": 4000,
        },
    ).success
    rejected = tool.execute(
        action="commit_chapter",
        novel_id="writer-short-append",
        chapter=1,
        data={"content": "rain" * 200, "summary": "A complete but intentionally short opening chapter."},
    )
    assert rejected.success is False

    config = SimpleNamespace(
        active_model_source="standard",
        api_max_retries=0,
        api_initial_backoff=0.01,
        api_timeout=30,
        api_enable_debug_logging=False,
    )
    agent = ReverieAgent(
        base_url="https://example.test/v1",
        api_key="test",
        model="test-model",
        project_root=tmp_path,
        provider="openai-sdk",
        mode="writer",
        config=config,
    )
    state = _StreamingTurnState()
    state.collected_content = "å¥¹æŠŠæ¹¿æ¶¦çš„è¢–å£å‘å†…æŠ˜äº†ä¸€æŠ˜ï¼ŒåˆæŠŠæŒ‡å°–åœåœ¨æ¯æ²¿ä¸Šï¼Œå¬ç€çª—å¤–é›¾æ°”ç¼“ç¼“ç§»åŠ¨ã€‚" * 6

    promoted = agent._promote_writer_direct_prose_commit(state)

    assert promoted is True
    arguments = json.loads(state.tool_calls[0]["function"]["arguments"])
    assert arguments["action"] == "commit_chapter"
    assert arguments["novel_id"] == "writer-short-append"
    assert arguments["chapter"] == 1
    assert "append_content" in arguments["data"]
    assert "content" not in arguments["data"]
    assert arguments["data"]["append_content"].startswith("å¥¹æŠŠæ¹¿æ¶¦çš„è¢–å£å‘å†…æŠ˜äº†ä¸€æŠ˜")


def test_writer_promotes_provider_json_into_real_tool_call(tmp_path: Path) -> None:
    config = SimpleNamespace(
        active_model_source="agnes",
        api_max_retries=0,
        api_initial_backoff=0.01,
        api_timeout=30,
        api_enable_debug_logging=False,
        agnes={},
    )
    agent = ReverieAgent(
        base_url="https://apihub.agnes-ai.com/v1",
        api_key="test",
        model="agnes-2.0-flash",
        project_root=tmp_path,
        provider="openai-sdk",
        mode="writer",
        config=config,
    )
    agent.messages = [
        {
            "role": "user",
            "content": "写一部长篇小说，novel_id为native-json-test，目标至少2500个非空白字符",
        }
    ]
    state = _StreamingTurnState(
        collected_content='{"action":"bootstrap","novel_id":"native-json-test","title":"雨历"}'
    )

    assert agent._promote_writer_json_tool_call(state) is True
    assert state.collected_content == ""
    assert state.tool_calls[0]["function"]["name"] == "serial_novel"
    arguments = parse_tool_arguments(state.tool_calls[0]["function"]["arguments"])
    assert arguments["brief"].startswith("写一部长篇小说")
    assert arguments["target_chars"] == 2500
