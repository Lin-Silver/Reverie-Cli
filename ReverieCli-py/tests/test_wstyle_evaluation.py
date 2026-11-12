from pathlib import Path
import runpy


EVALUATION = runpy.run_path(str(Path(__file__).resolve().parents[2] / "scripts/verification/evaluate_wstyles.py"))


def test_original_corpus_and_three_chapter_switch_plan_are_executable_offline(tmp_path):
    corpus = EVALUATION["load_corpus"]()
    assert len(corpus["cases"]) == 3
    assert all(case["facts"] and case["single"] and len(case["multi"]) >= 2 for case in corpus["cases"])
    plan = EVALUATION["continuity_plan"](corpus["cases"][0])
    assert len(plan) == 3 and plan[0]["styles"] != plan[2]["styles"]
    assert EVALUATION["main"](["--output",str(tmp_path / "evaluation")]) == 0
    import json
    run = json.loads((tmp_path / "evaluation/run.json").read_text(encoding="utf-8"))
    results = json.loads((tmp_path / "evaluation/private/scene-results.json").read_text(encoding="utf-8"))
    assert run["state"] == "offline_plan_complete" and run["literary_quality"] == "unverified"
    assert len(results) == 9 and all(result["state"] == "planned" for result in results)
    assert not (tmp_path / "evaluation/blind").exists()
    assert {result["variant"] for result in results} == {"base","single","multi"}
    request = json.loads(next((tmp_path / "evaluation/private").glob("sample-*-request.json")).read_text(encoding="utf-8"))
    assert "至少 5000" in request["user"] and "10000" in request["user"]
    assert run["model_conditions"]["minimum_chapter_characters"] == 5_000
    assert run["model_conditions"]["max_tokens"] == 32_768


def test_evaluation_surface_signals_do_not_claim_semantic_facts_or_scores():
    corpus = EVALUATION["load_corpus"]()
    result = EVALUATION["observable_signals"]("唐望与谢雨迟坐在手泵旁。",corpus["cases"][0])
    assert all(result["explicit_name_or_item_mentions"].values())
    assert result["assessment"] == "surface_observations_only"
    assert "score" not in result


def test_saved_response_reuse_counts_only_prose_and_keeps_raw_provider_text(tmp_path):
    from types import SimpleNamespace
    import pytest

    private = tmp_path / "private"
    private.mkdir()
    request = private / "sample-001-attempt-1.json"
    raw = private / "sample-001-attempt-1-raw.txt"
    EVALUATION["write_json"](request, {"system": "system", "user": "user"})
    body = "正文" * 2_500
    provider_text = "model planning text" * 1_000 + "</think>" + body
    raw.write_text(provider_text, encoding="utf-8", newline="\n")
    EVALUATION["write_json"](raw.with_suffix(".json"), {"usage": {"output_tokens": 7_000}})
    agent = SimpleNamespace(complete_text_only=lambda *_args, **_kwargs: pytest.fail("Matching saved response must be reused"))
    text, attempts = EVALUATION["generate_prose"](agent, "system", "user", tmp_path, "sample-001", max_tokens=65_536)
    assert text == body and attempts[0]["characters"] == 5_000
    assert attempts[0]["separated_reasoning"] is True
    assert attempts[0]["usage"] == {"output_tokens": 7_000}
    assert raw.read_text(encoding="utf-8") == provider_text
    with pytest.raises(ValueError, match="differs"):
        EVALUATION["generate_prose"](agent, "changed system", "user", tmp_path, "sample-001", max_tokens=65_536)


def test_native_evaluation_recovers_provider_wrapper_without_rewriting_prose():
    import json
    import pytest

    prose = "清晨，两人核对名单。\n\n唐望把原件放回柜里。"
    raw = json.dumps({"content": prose}, ensure_ascii=False) + '],"summary":"核对名单，保留原件。","key_events":["核对名单"]}'
    result = EVALUATION["native_reply"](raw)
    assert result["content"] == prose
    assert result["summary"] == "核对名单，保留原件。"
    assert result["key_events"] == ["核对名单"]
    long_reply = json.dumps({"append_content": "后续正文" * 10_000, "summary": "完整摘要。"}, ensure_ascii=False)
    assert len(EVALUATION["native_reply"](long_reply, content_key="append_content")["append_content"]) == 40_000
    with pytest.raises(ValueError, match="complete prose"):
        EVALUATION["native_reply"]('{"summary":"缺少正文"}')


def test_evaluation_minimum_excludes_markdown_and_plain_chapter_titles():
    corpus = EVALUATION["load_corpus"]()
    prose = "正文" * 2_498
    for heading in ("# 第0417号票根\n\n## 一\n\n", "第十二章 夜班\n\n"):
        signals = EVALUATION["observable_signals"](heading + prose, corpus["cases"][0])
        assert signals["characters"] == 4_996
        assert signals["minimum_met"] is False


def test_evaluation_keeps_prose_and_original_line_numbers_when_excluding_titles():
    prose = "第十二章的页边有一处更正。"
    text = "# 夜班\n\n" + prose + "\n\n## 二\n\nChapter 12 was printed on the old ticket."
    body = EVALUATION["evaluation_body"](text)
    assert body.splitlines()[2] == prose
    assert body.splitlines()[6] == "Chapter 12 was printed on the old ticket."
    assert EVALUATION["observable_signals"](text, EVALUATION["load_corpus"]()["cases"][0])["characters"] == sum(
        not char.isspace() for char in prose + "Chapter 12 was printed on the old ticket."
    )


def test_evaluation_preserves_short_prose_and_continues_when_titles_mask_the_minimum(tmp_path):
    from types import SimpleNamespace

    first = "# 第0417号票根\n\n## 一\n\n" + "正文" * 2_498
    followup = "她核对下一条记录。" * 60
    requests = []

    def complete(_system, request, **_kwargs):
        requests.append(request)
        return first if len(requests) == 1 else followup

    agent = SimpleNamespace(complete_text_only=complete)
    text, attempts = EVALUATION["generate_prose"](agent, "system", "user", tmp_path, "sample-008", max_tokens=65_536)
    assert len(requests) == 2
    assert first in requests[1] and "至少 504 字" in requests[1]
    assert text == first + "\n\n" + followup
    assert attempts[0]["characters"] == 4_996 and attempts[1]["characters"] >= 5_000
