"""Localized mechanical evidence; these findings do not rate literary merit."""

from __future__ import annotations

from collections import defaultdict
import re

from .narrative_analyzer import NarrativeAnalyzer


def localized_quality_findings(content: str, report: dict) -> list[dict]:
    lines = content.splitlines()
    findings = []

    def add(kind, quote, locations, impact, suggestion, *, blocking=False):
        findings.append({"kind": kind, "severity": "blocking" if blocking else "review", "quote": quote,
                         "locations": locations[:12], "occurrences": len(locations), "impact": impact,
                         "suggestion": suggestion, "evidence_type": "deterministic_text_match"})

    paragraphs = defaultdict(list)
    for number, line in enumerate(lines, 1):
        if len(line.strip()) >= 20:
            paragraphs[line.strip()].append(number)
    for quote, locations in paragraphs.items():
        if len(locations) > 1:
            add("duplicate_paragraph", quote, locations, "相同段落重复出现。",
                "核对是否为有意回声；若没有新的叙事作用，保留一次并补写新的行动或后果。",
                blocking=report["duplicate_ratio"] > 0.12)
            if len(findings) >= 8:
                break
    for term in report["placeholders"][:5]:
        add("placeholder", term, [number for number, line in enumerate(lines, 1) if term in line],
            "已有原生门禁识别到待写标记。", "核对上下文，完成确实缺失的正文后重新提交。", blocking=True)
    for term in report["overused_style_tics"]:
        add("style_tic", term, [number for number, line in enumerate(lines, 1) if term in line],
            "该固定表达超过原生重复阈值；计数不能独立证明文笔好坏。",
            "核对每次使用是否增加新的信息，优先删除重复解释或改为具体反应。", blocking=True)
    for phrase in NarrativeAnalyzer().detect_repetitions(content, min_length=8):
        locations = [content.count("\n", 0, match.start()) + 1 for match in re.finditer(re.escape(phrase), content)]
        if len(locations) >= 3 and not any(phrase in item["quote"] for item in findings):
            add("repeated_phrase", phrase, locations, "相同长短语多次出现，可能是模板句，也可能是有意回收。",
                "比较这些位置的意义和反应；保留有效回声，修改只有换名或复述的段落。")
    if report["cross_chapter_duplicate_passage"]:
        passage = report["cross_chapter_duplicate_passage"]
        match = re.search(r"\s*".join(map(re.escape, passage)), content)
        if match:
            quote = match.group()
            add("cross_chapter_copy", quote, [content.count("\n", 0, match.start()) + 1],
                "原生门禁发现前章中相同的 64 个非空白字符。",
                "读取前章确认是否误复制，续写应从尚未发生的事件开始。", blocking=True)
    return findings[:24]
