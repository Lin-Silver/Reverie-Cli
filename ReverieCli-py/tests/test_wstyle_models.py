import hashlib
import json

import pytest

from reverie.tools.serial_novel import SerialNovelTool
from reverie.writer.style_runtime import WStyleRuntime
from reverie.writer.style_commands import run_wstyle_command
from test_wstyles import write_card


@pytest.fixture
def novel_runtime(tmp_path):
    runtime = WStyleRuntime(tmp_path, app_root=tmp_path / "app")
    tool = SerialNovelTool(context={"project_root": tmp_path, "wstyle_runtime": runtime})
    result = tool.execute(action="bootstrap", novel_id="reviewable", title="修伞人", brief="原创场景", target_chars=2000)
    assert result.success
    path = tmp_path / "novels" / "reviewable" / "drafts" / "chapter-0001.json"
    content = "她把伞放在门边。\n雨停了，她仍在等。\n她又说了一遍同样的话。"
    path.write_text(json.dumps({"chapter": 1, "title": "门边", "data": {"content": content}, "wstyle_segments": []}, ensure_ascii=False), encoding="utf-8")
    return runtime, path, content


def valid_review(*_):
    return json.dumps({"summary": "等待的动作有依据，结尾可增加一次具体决定。", "issues": [
        {"line_start": 3, "line_end": 3, "quote": "她又说了一遍同样的话。", "category": "narrative",
         "impact": "没有交代重复的话带来的变化。", "suggestion": "保留事实，补出对方的反应或她改变的行动。", "wstyle_ids": []}],
        "limitations": ["仅评审所提供的草稿，无法判断全书关系弧线。"]}, ensure_ascii=False)


def test_review_preserves_draft_saves_evidence_and_is_available_in_native_context(novel_runtime):
    runtime, source, content = novel_runtime
    original = source.read_bytes()
    calls = []

    def model(system, user, max_tokens):
        calls.append((system, user, max_tokens))
        return valid_review()

    result = run_wstyle_command("review --chapter 1", runtime, mode="writer", model_call=model)
    assert result.success, result.error
    report = result.data["report"]
    assert report["source"]["sha256"] == hashlib.sha256(content.encode("utf-8")).hexdigest()
    assert report["model_review"]["issues"][0]["line_start"] == 3
    assert "deterministic" in report and "score" not in report
    assert source.read_bytes() == original
    assert len(calls) == 1 and calls[0][2] <= 8192
    assert "她把伞放在门边。" in calls[0][1]
    tool = SerialNovelTool(context={"project_root": runtime.project_root, "wstyle_runtime": runtime})
    context = tool.execute(action="context", novel_id="reviewable", data={"chapter": 1})
    assert context.success
    assert context.data["editorial_review"]["source_matches_current"] is True
    assert "保留事实" in context.data["editorial_review"]["issues"][0]["suggestion"]


def test_hallucinated_review_location_is_rejected_and_raw_is_saved(novel_runtime):
    runtime, source, _ = novel_runtime
    raw = valid_review().replace("她又说了一遍同样的话。", "并不存在的原文引用")
    result = run_wstyle_command("review --chapter 1", runtime, mode="writer", model_call=lambda *_: raw)
    assert not result.success and "quote" in result.error.lower()
    saved = list((source.parent.parent / "reviews").rglob("raw-response.txt"))
    assert len(saved) == 1 and saved[0].read_text(encoding="utf-8") == raw
    assert not list((source.parent.parent / "reviews").rglob("report.json"))


def test_review_receives_prior_chapter_facts_without_future_chapters(novel_runtime):
    runtime, source, _ = novel_runtime
    draft = json.loads(source.read_text(encoding="utf-8"))
    draft["chapter"] = 2
    second = source.with_name("chapter-0002.json")
    second.write_text(json.dumps(draft, ensure_ascii=False), encoding="utf-8")
    original = second.read_bytes()
    state_path = source.parent.parent / "tracking/state.json"
    state = json.loads(state_path.read_text(encoding="utf-8"))
    state["chapters"] = {
        "1": {"chapter": 1, "title": "周五", "summary": "周五断绳，水泵尚未修好。", "key_events": ["断绳"],
              "timeline_updates": ["周五傍晚"], "relationship_updates": ["两人开始合作"]},
        "3": {"chapter": 3, "title": "未来章节", "summary": "不可预知的后续事实"},
    }
    state_path.write_text(json.dumps(state, ensure_ascii=False), encoding="utf-8")
    requests = []

    def model(_system, user, _max_tokens):
        requests.append(json.loads(user))
        return valid_review()

    result = run_wstyle_command("review --chapter 2", runtime, mode="writer", model_call=model)
    assert result.success, result.error
    prior = requests[0]["previous_chapters"]
    assert [record["chapter"] for record in prior] == [1]
    assert prior[0]["summary"] == "周五断绳，水泵尚未修好。"
    assert prior[0]["timeline_updates"] == ["周五傍晚"]
    assert "不可预知的后续事实" not in json.dumps(requests[0], ensure_ascii=False)
    assert result.data["report"]["continuity_chapters"] == [1]
    assert second.read_bytes() == original


def test_review_reports_omitted_prior_records_without_silently_truncating(novel_runtime):
    runtime, source, _ = novel_runtime
    draft = json.loads(source.read_text(encoding="utf-8"))
    draft["chapter"] = 5
    source.with_name("chapter-0005.json").write_text(json.dumps(draft, ensure_ascii=False), encoding="utf-8")
    state_path = source.parent.parent / "tracking/state.json"
    state = json.loads(state_path.read_text(encoding="utf-8"))
    state["chapters"] = {
        str(number): {"chapter": number, "title": str(number), "summary": "完整前章事实"}
        for number in range(1, 5)
    }
    state["chapters"]["4"]["summary"] = "需要完整保留的事实" * 1_000
    state_path.write_text(json.dumps(state, ensure_ascii=False), encoding="utf-8")
    requests = []

    def model(_system, user, _max_tokens):
        requests.append(json.loads(user))
        return valid_review()

    result = run_wstyle_command("review --chapter 5", runtime, mode="writer", model_call=model)
    assert result.success, result.error
    assert [record["chapter"] for record in requests[0]["previous_chapters"]] == [2, 3]
    assert "1 earlier chapter record(s)" in requests[0]["context_omissions"]
    assert "chapter-0004 continuity record" in requests[0]["context_omissions"]
    assert result.data["report"]["context_omissions"] == requests[0]["context_omissions"]


def extracted_reply(body=None):
    return json.dumps({"name": "克制的动作", "description": "用选择和具体细节表现情绪", "layer": "prose",
                       "body": body or ("# 创作原则\n\n用人物的注意力选择细节，以动作和停顿显露情绪。" * 10 +
                       "\n# 应避免\n\n避免固定口癖、独特设定及复述样本。\n# 原创示例\n\n她收起烫手的票根，给对面空座让出一点地方。"),
                       "observations": [{"sample": 1, "quote": "窗外的水汽", "mechanism": "以环境变化承载等待的感受。"}],
                       "limitations": ["一个短样本无法代表作者或作品的全部风格。"]}, ensure_ascii=False)


def test_extract_creates_valid_card_with_sample_provenance_without_enabling_it(tmp_path):
    runtime = WStyleRuntime(tmp_path, app_root=tmp_path / "app")
    sample = tmp_path / "sample.md"
    sample.write_text("第一行\n" + "窗外的水汽让她看不清那班车，但她认得鸣笛声。" * 15 + "\n尾行", encoding="utf-8")
    original = sample.read_bytes()
    result = run_wstyle_command('extract restrained --sample "sample.md" --start-line 2 --end-line 2 --source-note 自写练习',
                               runtime, mode="writer", model_call=lambda *_: extracted_reply())
    assert result.success, result.error
    card = runtime.repository.get("restrained")
    provenance = card.metadata["extraction"]
    assert provenance["sample_count"] == 1
    assert provenance["samples"][0]["start_line"] == 2
    assert provenance["samples"][0]["end_line"] == 2
    assert provenance["source_note"] == "自写练习"
    assert provenance["samples"][0]["file_sha256"] == hashlib.sha256(original).hexdigest()
    assert runtime.selection()[0] == [] and sample.read_bytes() == original


def test_extract_rejects_substantial_copy_and_preserves_output(tmp_path):
    runtime = WStyleRuntime(tmp_path, app_root=tmp_path / "app")
    sample = tmp_path / "sample.txt"
    text = "窗外的水汽" + "甲乙丙丁戊己庚辛壬癸一二三四五六七八九十" * 16
    sample.write_text(text, encoding="utf-8")
    result = run_wstyle_command("extract copied --sample sample.txt", runtime, mode="writer",
                               model_call=lambda *_: extracted_reply("# 原创示例\n\n" + text))
    assert not result.success and "cop" in result.error.lower()
    assert not (runtime.repository.root / "copied.md").exists()
    assert list((tmp_path / ".reverie" / "wstyle-extractions").rglob("raw-response.txt"))


def test_extract_existing_id_and_oversized_samples_do_not_call_model(tmp_path):
    runtime = WStyleRuntime(tmp_path, app_root=tmp_path / "app")
    write_card(runtime.repository, "existing", "keep")
    sample = tmp_path / "sample.txt"
    sample.write_text("中" * 16_001, encoding="utf-8")
    def forbidden(*_):
        pytest.fail("No model call is allowed after input validation fails")
    assert not run_wstyle_command("extract existing --sample sample.txt", runtime, mode="writer", model_call=forbidden).success
    assert not run_wstyle_command("extract large --sample sample.txt", runtime, mode="writer", model_call=forbidden).success
