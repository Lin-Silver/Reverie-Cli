import copy
import importlib.util
import json
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location("riu_rich_fidelity", ROOT / "scripts/verification/riu_rich_answer_benchmark.py")
verifier = importlib.util.module_from_spec(spec)
spec.loader.exec_module(verifier)


@pytest.fixture
def recommendations():
    fixture = json.loads((ROOT / "scripts/verification/fixtures/riu-rich-answer-tasks.json").read_text(encoding="utf-8"))
    expected = next(task for task in fixture["tasks"] if task["id"] == "rich-recommendations")["expected"]
    state = {"unfinished": 0, "invalid": 0, "width": 400, "scrollWidth": 400,
        "transcript": {"width": 400, "scrollWidth": 400}, "text": "", "cards": [],
        "badges": ["项目管理"], "links": expected["link_urls"], "sources": 2}
    for i, title in enumerate(expected["card_titles"]):
        state["cards"].append({"title": title, "number": i + 1,
            "description": expected["card_descriptions"][i], "badges": expected["card_badges"][i],
            "images": [{"src": expected["image_urls"][i], "alt": expected["image_alts"][i], "loaded": True}]})
    return state, expected


def test_supplied_recommendations_pass_without_inferred_content(recommendations):
    state, expected = recommendations
    assert all(c["passed"] for c in verifier.assess_rich_state(state, expected))
    for card in state["cards"]:
        card["number"] = None
    assert all(c["passed"] for c in verifier.assess_rich_state(state, expected))


@pytest.mark.parametrize("prose,passed", [
    (["本周共有3项待办任务。", "待办任务：3项"], False),
    (["本周共有2项待办任务。", "待办任务：3项"], False),
    (["待办：12项"], False),
    (["待办任务：2项", "本周共有2项待办任务。"], True),
    (["待办：2", "另有12个项目"], True),
    (["待办任务3号已分配", "请先处理重点事项"], True),
    (["上周待办3项，本周待办2项"], True),
    (["上周待办3项，本周待办4项"], False),
    (["待办：-2项"], False),
    (["待办：2.5项"], False),
    ([], True),
])
def test_current_metric_counts_agree_with_every_prose_and_list_mention(recommendations, prose, passed):
    state, _ = recommendations
    state.update(metrics=[["待办", "2"]], prose=prose)
    checks = verifier.assess_rich_state(state, {"metrics": [["待办", "2"]]})
    assert all(c["passed"] for c in checks) is passed
    if not passed:
        failed = [c for c in checks if not c["passed"]]
        assert "正文" in verifier.rich_repair_feedback(failed)
        assert "待办" in verifier.rich_repair_feedback(failed)


@pytest.mark.parametrize("value", ["0", "3", "9007199254740993"])
def test_prose_count_comparison_preserves_zero_initial_and_large_integer_values(recommendations, value):
    state, _ = recommendations
    state.update(metrics=[["待办", value]], prose=[f"待办任务：{value}项"])
    assert all(c["passed"] for c in verifier.assess_rich_state(state, {"metrics": [["待办", value]]}))


def test_metric_names_are_literal_in_prose_comparison(recommendations):
    state, _ = recommendations
    state.update(metrics=[["A+B", "2"]], prose=["AB：3项", "A+B：2项"])
    expected = {"metrics": [["A+B", "2"]]}
    assert all(c["passed"] for c in verifier.assess_rich_state(state, expected))
    state["prose"].append("A+B：3项")
    assert not all(c["passed"] for c in verifier.assess_rich_state(state, expected))


@pytest.mark.parametrize("description,passed", [
    ("项目管理工具", True),
    ("Plane是项目管理工具", True),
    (" Plane 是 项目管理工具。 ", True),
    ("项目管理工具。", True),
    ("Plane是项目管理工具.", True),
    ("", False),
    ("项目管理", False),
    ("任务管理工具", False),
    ("Vikunja是项目管理工具", False),
    ("Plane不是项目管理工具", False),
    ("Plane是开源项目管理工具", False),
    ("Plane是项目管理工具，支持自动化", False),
    ("Plane是项目管理工具。开源免费", False),
    ("Plane是项目管理工具?", False),
])
def test_card_description_preserves_facts_with_a_neutral_subject(recommendations, description, passed):
    state, expected = recommendations
    state["cards"][0]["description"] = description
    check = next(c for c in verifier.assess_rich_state(state, expected)
                 if c["name"] == "rich-supplied-descriptions")
    assert check["passed"] is passed


def test_neutral_subject_does_not_allow_an_inferred_badge(recommendations):
    state, expected = recommendations
    for card in state["cards"]:
        card["description"] = card["title"] + "是" + card["description"]
    state["cards"][1]["badges"] = ["任务管理"]
    checks = {c["name"]: c["passed"] for c in verifier.assess_rich_state(state, expected)}
    assert checks["rich-supplied-descriptions"]
    assert not checks["rich-per-item-badges"]


@pytest.mark.parametrize("description,passed", [("A+B是项目管理工具", True), ("AB是项目管理工具", False)])
def test_description_subject_is_a_literal_card_title(recommendations, description, passed):
    state, expected = recommendations
    state["cards"][0].update(title="A+B", description=description)
    expected["card_titles"][0] = "A+B"
    check = next(c for c in verifier.assess_rich_state(state, expected)
                 if c["name"] == "rich-supplied-descriptions")
    assert check["passed"] is passed


@pytest.mark.parametrize("extra", [False, True])
def test_description_comparison_requires_every_supplied_card(recommendations, extra):
    state, expected = recommendations
    if extra:
        state["cards"].append(copy.deepcopy(state["cards"][0]))
    else:
        state["cards"].pop()
    check = next(c for c in verifier.assess_rich_state(state, expected)
                 if c["name"] == "rich-supplied-descriptions")
    assert not check["passed"]


@pytest.mark.parametrize("mutation,failed_check", [
    ("description", "rich-supplied-descriptions"),
    ("badge", "rich-per-item-badges"),
    ("alt", "rich-supplied-image-descriptions"),
    ("number", "rich-card-numbering"),
])
def test_visible_cards_do_not_hide_changed_data_or_restarted_numbering(recommendations, mutation, failed_check):
    original, expected = recommendations
    state = copy.deepcopy(original)
    if mutation == "description":
        state["cards"][0]["description"] += "，支持未提供的功能"
    elif mutation == "badge":
        state["cards"][1]["badges"] = ["额外推断的标签"]
    elif mutation == "alt":
        state["cards"][0]["images"][0]["alt"] = "非空但不符合给定说明"
    else:
        state["cards"][1]["number"] = 1
    check = next(c for c in verifier.assess_rich_state(state, expected) if c["name"] == failed_check)
    assert not check["passed"]
    assert verifier.rich_repair_feedback([check])


@pytest.mark.parametrize("emphasis,passed", [
    (["重点"], True),
    (["重点："], True),
    (["重点:"], True),
    ([], False),
    (["次重点"], False),
    (["重点事项"], False),
    (["重点：内容已被改写"], False),
])
def test_requested_emphasis_allows_a_label_colon_without_rewriting(recommendations, emphasis, passed):
    state, expected = recommendations
    state["strong"] = emphasis
    expected["strong"] = "重点"
    check = next(c for c in verifier.assess_rich_state(state, expected) if c["name"] == "rich-markdown-emphasis")
    assert check["passed"] is passed


@pytest.mark.parametrize("actual,expected", [
    ("项目 01", "项目01"),
    ("项目1", "项目01"),
    ("A-1", "A_1"),
    ("AB", "A B"),
])
def test_table_feedback_identifies_the_exact_changed_cell(recommendations, actual, expected):
    state, _ = recommendations
    state["tables"] = [{"headers": ["名称", "数量"], "rows": [[actual, "0"]]}, {"rows": []}]
    checks = verifier.assess_rich_state(state, {"table_rows": [[expected, 0]]})
    failure = next(c for c in checks if c["name"] == "rich-all-supplied-table-rows")
    assert not failure["passed"]
    feedback = verifier.rich_repair_feedback([failure])
    assert "第1行第1列" in feedback
    assert json.dumps(expected, ensure_ascii=False) in feedback
    assert json.dumps(actual, ensure_ascii=False) in feedback
    assert "空格" in feedback and "前导零" in feedback


def test_missing_row_feedback_preserves_the_failed_fidelity_verdict(recommendations):
    state, _ = recommendations
    state["tables"] = [{"rows": [["项目01", "0"]]}]
    checks = verifier.assess_rich_state(state, {"table_rows": [["项目01", 0], ["项目02", 1]]})
    failure = next(c for c in checks if c["name"] == "rich-all-supplied-table-rows")
    assert not failure["passed"]
    feedback = verifier.rich_repair_feedback([failure])
    assert "第2行第1列" in feedback
    assert '"项目02"' in feedback
