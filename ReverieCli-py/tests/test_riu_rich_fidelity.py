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
