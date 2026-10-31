import hashlib
import importlib.util
import json
from pathlib import Path


path = Path(__file__).resolve().parents[2] / "scripts/verification/riu_full_benchmark.py"
spec = importlib.util.spec_from_file_location("riu_full_benchmark", path)
benchmark = importlib.util.module_from_spec(spec)
spec.loader.exec_module(benchmark)


def test_streamed_digest_matches_sha256(tmp_path):
    data = b"native acceptance\x00" * 100000
    target = tmp_path / "binary"
    target.write_bytes(data)
    assert benchmark.digest(target) == hashlib.sha256(data).hexdigest()


def test_tools_are_suppressed_only_for_self_contained_static_requests(tmp_path):
    target = tmp_path / "request.json"
    for prompt, expected in [
        ("请展示给定统计卡：计划中7、开发中5，以及表格 Alpha / 开发中 / 核心助手。本题不需调查仓库。", 0),
        ("调查仓库并更新项目文件，然后展示当前项目状态。", 27),
        ("创建一个可以编辑、筛选和排序的表格。", 27),
    ]:
        for count in [0, 27]:
            target.write_text(json.dumps({"messages": [{"role": "user", "content": prompt}],
                "tools": [{}] * count}, ensure_ascii=False), encoding="utf-8")
            assert benchmark.request_tool_scope_matches({"request": str(target), "tools": count}) == (count == expected)
            assert not benchmark.request_tool_scope_matches({"request": str(target), "tools": 99})


def test_static_correction_scope_depends_on_retained_data_and_no_tool_calls(tmp_path):
    target = tmp_path / "correction.json"
    supplied = {"role": "user", "content": "展示给定统计卡：计划中7、开发中5，以及表格 Alpha / 开发中 / 核心助手。"}
    reply = {"role": "assistant", "content": "之前的回答"}
    correction = {"role": "user", "content": "把计划中改为0，其余统计卡保持不变。"}
    for messages, expected in [([supplied, reply, correction], 0),
                                ([correction], 27),
                                ([supplied, {**reply, "tool_calls": [{"id": "call"}]}, correction], 27)]:
        for count in [0, 27]:
            target.write_text(json.dumps({"messages": messages, "tools": [{}] * count}, ensure_ascii=False), encoding="utf-8")
            assert benchmark.request_tool_scope_matches({"request": str(target), "tools": count}) == (count == expected)
