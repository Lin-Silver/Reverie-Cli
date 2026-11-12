import pytest

from reverie.tools.serial_novel import SerialNovelTool
from reverie.tools.plot_analyzer_tool import PlotAnalyzerTool
from reverie.writer.narrative_analyzer import NarrativeAnalyzer


def test_chinese_repeated_phrases_are_detected_without_whitespace():
    analyzer = NarrativeAnalyzer()
    text = "她把纸伞靠在门边，听见脚步。她把纸伞靠在门边，没有回头。她把纸伞靠在门边，终于坐下。"
    assert "她把纸伞靠在门边" in analyzer.detect_repetitions(text)
    assert analyzer.detect_repetitions("小雨停了。她出门，把票交给窗口的人。") == []


def test_english_last_possible_repeat_and_chinese_punctuation_are_handled():
    analyzer = NarrativeAnalyzer()
    assert "she set the cup" in analyzer.detect_repetitions("she set the cup then she set the cup")
    assert analyzer._detect_pacing("这是" + "一段比较长的连续观察" * 7 + "。") == "slow"
    result = analyzer.analyze_character_consistency("乔沅", ["等等！你拿到票了吗？", "我去问。"])
    assert result["consistency_score"] is None
    assert result["assessment"] == "descriptive_only"
    assert result["speech_patterns"]["questions"] == 1
    assert result["speech_patterns"]["exclamations"] == 1
    assert result["speech_patterns"]["average_sentence_length"] > 1


def test_quality_evidence_has_real_lines_and_keeps_existing_gates():
    paragraph = "她把那张没有签名的单子放到桌上，决定等负责登记的人回来再核对。"
    text = "前面的门打开了。\n" + paragraph + "\n" + paragraph + "\n待补"
    report = SerialNovelTool._quality_report(text, 500)
    assert not report["passed"]
    repeats = [item for item in report["findings"] if item["kind"] == "duplicate_paragraph"]
    assert repeats[0]["locations"] == [2, 3]
    assert repeats[0]["quote"] == paragraph
    placeholder = next(item for item in report["findings"] if item["kind"] == "placeholder")
    assert placeholder["locations"] == [4]
    assert report["assessment"] == "deterministic_checks_only"


def test_normal_mentions_of_omission_and_pending_materials_are_not_placeholders():
    text = "\n".join(f"她核对第{i:03d}页记录，发现那句话写得太省略，另纸记下待补材料的名称，没有改动原件。" for i in range(20))
    report = SerialNovelTool._quality_report(text, 500)
    assert report["passed"], report["blocking_issues"]
    assert report["placeholders"] == []


@pytest.mark.parametrize("marker", ["待补", "省略", "（此处省略后续场景）", "[正文待补]", "此处省略后续场景", "TODO", "[pending]"])
def test_explicit_unwritten_content_markers_still_block_submission(marker):
    text = "\n".join(f"她核对第{i:03d}页记录，写下今天的水位和不同的经办人，整理好之后交给值班室。" for i in range(20)) + "\n" + marker
    report = SerialNovelTool._quality_report(text, 500)
    assert not report["passed"]
    assert report["placeholders"]
    evidence = next(item for item in report["findings"] if item["kind"] == "placeholder")
    assert evidence["locations"] == [21]


def test_phrase_repetition_is_advisory_and_does_not_become_a_new_gate():
    phrase = "她把纸伞靠在门边"
    text = "\n".join(f"{phrase}，核对第{i:03d}张不同的旧票，写下当天水位和各不相同的船名，然后收进文件袋。" for i in range(14))
    report = SerialNovelTool._quality_report(text, 500)
    assert report["passed"]
    findings = [item for item in report["findings"] if item["kind"] == "repeated_phrase"]
    assert findings and all(item["severity"] == "review" for item in findings)


def test_native_voice_tool_does_not_format_a_fixed_semantic_score():
    result = PlotAnalyzerTool().execute(action="check_character_voice", character="乔沅", dialogues=["等等！", "我去问。"])
    assert result.success, result.error
    assert "70.0%" not in result.output and result.data["consistency_score"] is None
    assert "descriptive" in result.output.lower()


def test_optional_chapter_purpose_is_exposed_in_schema_and_accepts_flattened_payloads(tmp_path):
    from test_wstyle_novel import project_tool

    _, _, tool = project_tool(tmp_path)
    fields = ("narrative_function", "character_goal", "causal_change", "emotional_change", "reader_expectation")
    assert all(tool.parameters["properties"]["data"]["properties"][key]["type"] == "string" for key in fields)
    result = tool.execute(action="prepare_chapter", novel_id="harbor", title="核对",
                          outline="两人核对票据，决定保留原件。", character_goal="查明日期来源", causal_change="共同保存一份新说明")
    assert result.success, result.error
    assert result.data["control_card"]["quality_intent"] == {"character_goal": "查明日期来源", "causal_change": "共同保存一份新说明"}
