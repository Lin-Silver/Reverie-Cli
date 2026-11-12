"""Reproducible original base/single/multi comparisons, with no default model usage."""

from __future__ import annotations

import argparse
from copy import deepcopy
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import random
import re
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "ReverieCli-py"))

from reverie.agent.agent import ReverieAgent
from reverie.agent.text_completion import IncompleteTextResponse, _clean_text_content
from reverie.config import Config, ConfigManager
from reverie.desktop_catalog import apply_model_selection
from reverie.tools.serial_novel import SerialNovelTool
from reverie.writer.style_runtime import WStyleRuntime


MINIMUM_CHAPTER_CHARS = 5_000
TARGET_CHAPTER_CHARS = 10_000


def load_corpus(path: Path | None = None) -> dict:
    data = json.loads((path or Path(__file__).with_name("wstyle_corpus.json")).read_text(encoding="utf-8"))
    if data.get("schema") != "reverie.writer.evaluation-corpus.v1" or len(data.get("cases", [])) < 3:
        raise ValueError("Evaluation corpus must contain at least three original settings.")
    return data


def scene_prompt(case: dict) -> str:
    return ("这是独立的原创完整章节练习，正文至少 5000 个非空白字符，目标 10000 字（尽量达到 9000–11000 字），不创建小说项目。仅输出正文，不输出规则、评分或分析。\n"
            "通过连续场景、具体行动、人物判断和行动后果达到篇幅；不复述、填充或反复总结，不以提前揭晓真相换篇幅。\n"
            "设定：" + case["premise"] + "\n不可改动的事实：\n" + "\n".join("- " + fact for fact in case["facts"]) + "\n任务：" + case["scene"])


def evaluation_body(text: str) -> str:
    lines = text.splitlines()
    first = next((index for index, line in enumerate(lines) if line.strip()), None)
    for index, line in enumerate(lines):
        if re.match(r"^\s{0,3}#{1,6}(?:\s|$)", line) or (index == first and re.match(
            r"^\s*(?:第\s*[一二三四五六七八九十百零〇\d]+\s*[章节回卷集]|chapter\s*\d+)(?:\s|[:：\-]|$)",
            line, flags=re.IGNORECASE,
        )):
            lines[index] = ""
    return "\n".join(lines)


def observable_signals(text: str, case: dict) -> dict:
    report = SerialNovelTool._quality_report(evaluation_body(text), TARGET_CHAPTER_CHARS, chapter_minimum_chars=MINIMUM_CHAPTER_CHARS)
    return {"characters": report["chars"], "han_characters": report["han_chars"],
            "minimum_met": report["chars"] >= MINIMUM_CHAPTER_CHARS, "target_characters": TARGET_CHAPTER_CHARS,
            "explicit_name_or_item_mentions": {term: term in text for term in case["required_mentions"]},
            "duplicate_paragraphs": report["duplicate_paragraphs"], "style_tic_counts": report["style_tic_counts"],
            "findings": report["findings"], "assessment": "surface_observations_only",
            "limitations": "Mentions and text patterns do not prove fact preservation, style quality or readability."}


def make_agent(root: Path, config: Config, runtime: WStyleRuntime) -> ReverieAgent:
    model = config.active_model
    agent = ReverieAgent(model.base_url if model else "http://127.0.0.1", model.api_key if model else "dry-run",
                          model.model if model else "dry-run", project_root=root, mode="writer", config=config,
                          provider=model.provider if model else "request", endpoint=model.endpoint if model else "",
                          thinking_mode=model.thinking_mode if model else None, custom_headers=model.custom_headers if model else {})
    agent.wstyle_runtime = runtime
    agent.tool_executor.update_context("wstyle_runtime", runtime)
    return agent


def write_json(path: Path, value) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")


def complete_or_reuse(agent, system: str, user: str, request_path: Path, raw_path: Path, *, max_tokens: int) -> tuple[str, dict]:
    expected = {"system": system, "user": user}
    if request_path.exists():
        saved = json.loads(request_path.read_text(encoding="utf-8"))
        if any(saved.get(key) != value for key, value in expected.items()):
            raise ValueError(f"Saved request differs from this evaluation: {request_path.name}")
    else:
        write_json(request_path, expected)
    trace = {}
    if raw_path.exists():
        trace_path = raw_path.with_suffix(".json")
        if trace_path.exists():
            trace = json.loads(trace_path.read_text(encoding="utf-8"))
            if not isinstance(trace, dict):
                raise ValueError(f"Saved response trace must be an object: {trace_path.name}")
        raw = raw_path.read_text(encoding="utf-8")
        body, separated = _clean_text_content(raw)
        trace.update(raw_text=raw, separated_reasoning=separated, reused_response=True)
    else:
        try:
            body = agent.complete_text_only(system, user, max_tokens=max_tokens, long_form=True, response_trace=trace)
        except IncompleteTextResponse as exc:
            raw_path.with_name(raw_path.stem + "-incomplete.txt").write_text(exc.partial_text, encoding="utf-8", newline="\n")
            raise
        raw_path.write_text(trace.get("raw_text", body), encoding="utf-8", newline="\n")
    write_json(raw_path.with_suffix(".json"), {key: value for key, value in trace.items() if key != "raw_text"})
    return body, trace


def generate_prose(agent, system: str, user: str, output: Path, label: str, *, max_tokens: int) -> tuple[str, list[dict]]:
    text = ""
    attempts = []
    chars = 0
    for attempt in range(1, 4):
        request = user if not text else (user + "\n以下是已保留的正文，禁止重写或重复。\n<draft>\n" + text + "\n</draft>\n"
            f"仅输出后续新增正文，至少 {MINIMUM_CHAPTER_CHARS - chars + 500} 字，"
            "尽量让全章达到10000字。承接最后动作，展开尚未完成的决定和后果，不添加规则说明或结尾总结。")
        chunk, trace = complete_or_reuse(agent, system, request, output / "private" / f"{label}-attempt-{attempt}.json",
                                       output / "private" / f"{label}-attempt-{attempt}-raw.txt", max_tokens=max_tokens)
        text = (text + "\n\n" + chunk).strip() if text else chunk
        chars = sum(not ch.isspace() for ch in evaluation_body(text))
        attempts.append({"attempt": attempt, "characters": chars, "output_sha256": hashlib.sha256(chunk.encode("utf-8")).hexdigest(),
                         **{key: value for key, value in trace.items() if key != "raw_text"}})
        if chars >= MINIMUM_CHAPTER_CHARS:
            return text, attempts
    raise RuntimeError(f"{label} remains below the required {MINIMUM_CHAPTER_CHARS} characters after the initial request and two preserved continuations.")


def compare_scenes(corpus: dict, output: Path, config: Config, *, execute: bool, seed: int, max_tokens: int, repeats: int = 1) -> list[dict]:
    runtime = WStyleRuntime(output / "scene-workspace", app_root=output / "style-resources", config=config)
    runtime.ensure_resources()
    agent = make_agent(runtime.project_root, config, runtime)
    saved_path = output / "private" / "scene-results.json"
    saved_results = json.loads(saved_path.read_text(encoding="utf-8")) if saved_path.exists() else []
    saved_by_label = {record["blind_label"]: record for record in saved_results}
    results = []
    randomizer = random.Random(seed)
    counter = 0
    for case in corpus["cases"]:
        variants = [("base", []), ("single", case["single"]), ("multi", case["multi"])]
        for repeat in range(1, repeats + 1):
            randomizer.shuffle(variants)
            for variant, ids in variants:
                counter += 1
                label = f"sample-{counter:03d}"
                runtime.set_selection(ids, global_scope=True)
                system = agent._request_system_prompt()
                user = scene_prompt(case)
                snapshot = runtime.snapshot()
                record = {"blind_label": label, "case_id": case["id"], "variant": variant, "repeat": repeat,
                          "wstyle": snapshot, "prompt_sha256": hashlib.sha256((system + "\n" + user).encode("utf-8")).hexdigest(),
                          "state": "planned"}
                write_json(output / "private" / f"{label}-request.json", {"system": system, "user": user, "record": record})
                if execute:
                    try:
                        previous = saved_by_label.get(label)
                        existing_prose = output / "blind" / f"{label}.md"
                        if previous and existing_prose.is_file() and previous.get("output_sha256") != hashlib.sha256(existing_prose.read_bytes()).hexdigest():
                            raise ValueError(f"Edited evaluation output was preserved: {label}")
                        print(f"Generating {label} ({case['id']})", flush=True)
                        text, attempts = generate_prose(agent, system, user, output, label, max_tokens=max_tokens)
                        path = output / "blind" / f"{label}.md"
                        path.parent.mkdir(parents=True, exist_ok=True)
                        path.write_text(text, encoding="utf-8", newline="\n")
                        record.update(state="generated", output_sha256=hashlib.sha256(text.encode("utf-8")).hexdigest(),
                                      attempts=attempts, signals=observable_signals(text, case))
                        print(f"Saved {label}: {record['signals']['characters']} characters", flush=True)
                    except Exception as exc:
                        record.update(state="failed", error=str(exc)[:2000])
                        results.append(record)
                        write_json(output / "private" / "scene-results.json", results)
                        raise RuntimeError(f"Generation failed for {label}: {exc}") from exc
                results.append(record)
                write_json(output / "private" / "scene-results.json", results)
    client = getattr(agent, "client", None)
    if client is not None:
        client.close()
    return results


def continuity_plan(case: dict) -> list[dict]:
    return [{"chapter": index, **chapter, "styles": case["multi"] if index < 3 else ["commercial-serial-engagement"],
             "checks": ["保留已发生事件、物品与人物知识", "关系变化承接上一章", "不复制前章正文", "切换只影响第三章表达"]}
            for index, chapter in enumerate(case["chapters"], 1)]


def native_reply(raw: str, *, content_key: str = "content") -> dict:
    if not isinstance(raw, str) or len(raw) > 160_000:
        raise ValueError("Native evaluation response exceeds the long-form output limit.")
    data = SerialNovelTool._data_payload({"data": raw})
    if any(not isinstance(data.get(key), str) or not data[key].strip() for key in (content_key, "summary")):
        raise ValueError("Native response must preserve complete prose and a factual summary.")
    return data


def run_continuity(corpus: dict, output: Path, config: Config, *, max_tokens: int) -> dict:
    case = next(case for case in corpus["cases"] if case.get("chapters"))
    root = output / "continuity-workspace"
    runtime = WStyleRuntime(root, app_root=output / "style-resources", config=config)
    agent = make_agent(root, config, runtime)
    tool = SerialNovelTool({"project_root": root, "agent": agent, "wstyle_runtime": runtime})
    project_dir = root / "novels/water-station"
    if not (project_dir / "tracking/state.json").exists():
        assert tool.execute(action="bootstrap", novel_id="water-station", title="复课之前", brief=case["premise"], target_chars=30_000).success
    _, state = tool._load_state("water-station", {})
    if not state.get("configured"):
        assert tool.execute(action="configure", novel_id="water-station", data={"world_bible":"\n".join(case["facts"]),
        "cast_bible":case["facts"][0] + "\n" + case["facts"][3], "story_architecture":case["premise"],
        "style_guide":"第三人称限知；原件不改；人物知识来自已发生事件。", "roadmap":"\n".join(ch["outline"] for ch in case["chapters"])}).success
    records = []
    for item in continuity_plan(case):
        _, state = tool._load_state("water-station", {})
        if str(item["chapter"]) in state["chapters"]:
            audit = tool.execute(action="audit", novel_id="water-station")
            if audit.data["mismatches"]:
                raise ValueError("Existing native chapters changed; evaluation did not overwrite them.")
            records.append(state["chapters"][str(item["chapter"])])
            continue
        runtime.set_selection(item["styles"])
        prepared = tool.execute(action="prepare_chapter", novel_id="water-station", chapter=item["chapter"], title=item["title"],
                                data={"outline":item["outline"], "relationship_progression":[item["relationship"]], "narrative_function":item["outline"]})
        if not prepared.success:
            raise RuntimeError(prepared.error)
        system = agent._request_system_prompt()
        request_snapshot = deepcopy(runtime.snapshot())
        user = ("评测宿主已经执行原生项目准备，负责保存正文、提交门禁和状态；本调用没有工具。\n"
                "只输出 JSON 对象：content（至少5000个非空白字符，目标10000字的完整正文），summary（具体事件摘要），key_events（数组），relationship_updates（数组）。\n"
                "用实际发生的场景、判断和后果展开篇幅，不填充，不反复总结，不提前执行下一章纲要。\n"
                "延续已提供的事件和事实，不复述前章，不擅自修改原件或关系阶段。\n" + prepared.output)
        print(f"Generating continuity chapter {item['chapter']}", flush=True)
        raw, _ = complete_or_reuse(agent, system, user, output / "private" / f"continuity-{item['chapter']}-request.json",
                                  output / "private" / f"continuity-{item['chapter']}-raw.txt", max_tokens=max_tokens)
        data = native_reply(raw)
        write_json(output / "private" / f"continuity-{item['chapter']}-payload.json",
                   {"parser": "SerialNovelTool._data_payload", "response_sha256": hashlib.sha256(raw.encode("utf-8")).hexdigest(), "data": data})
        agent._last_wstyle_request_snapshot = {**request_snapshot,"source":"model_request"}
        committed = tool.execute(action="commit_chapter", novel_id="water-station", chapter=item["chapter"], data=data)
        for repair in range(1, 3):
            if committed.success:
                break
            pending = tool._load_pending_draft(root / "novels/water-station", item["chapter"])
            if not pending or len(pending["quality"]["blocking_issues"]) != 1 or pending["quality"]["chars"] >= MINIMUM_CHAPTER_CHARS:
                break
            continuation = ("只输出JSON：append_content（承接以下完整草稿的新增正文），summary（全章事件摘要），key_events（数组），relationship_updates（数组）。\n"
                "禁止重写或重复草稿，禁止提前执行下一章。通过尚未展开的动作与后果，让本章目标达到10000字。\n"
                + prepared.output + "\n已保存正文：\n" + pending["data"]["content"] + "\n门禁反馈：" + committed.error)
            raw, _ = complete_or_reuse(agent, system, continuation, output / "private" / f"continuity-{item['chapter']}-repair-{repair}-request.json",
                                      output / "private" / f"continuity-{item['chapter']}-repair-{repair}-raw.txt", max_tokens=max_tokens)
            data = native_reply(raw, content_key="append_content")
            write_json(output / "private" / f"continuity-{item['chapter']}-repair-{repair}-payload.json",
                       {"parser": "SerialNovelTool._data_payload", "response_sha256": hashlib.sha256(raw.encode("utf-8")).hexdigest(), "data": data})
            committed = tool.execute(action="commit_chapter", novel_id="water-station", chapter=item["chapter"], data=data)
        if not committed.success:
            raise RuntimeError("Native continuity gate: " + committed.error)
        records.append(committed.data["chapter"])
        write_json(output / "private" / "continuity-results.json", records)
        print(f"Committed continuity chapter {item['chapter']}: {committed.data['chapter']['chars']} characters", flush=True)
    audit = tool.execute(action="audit", novel_id="water-station")
    return {"state":"generated", "chapters":records,"native_audit":audit.data,
            "assessment":"Native integrity and gate results; semantic continuity still requires reading the chapters."}


def review_sheet(corpus: dict, results: list[dict]) -> str:
    lines = ["# WStyle 原创盲评记录", "", "先阅读 blind/ 中的正文，完成一般质量比较后再查看 private/ 的 Card 对照。",
             "planned / failed 记录没有生成正文，不能填写已通过的文学评价。每项判断须引用真实片段、位置、影响与修订目标。", ""]
    for record in results:
        lines.append(f"- {record['blind_label']} · {record['case_id']} · {record['state']}")
    lines.extend(["", "评价维度：" + "、".join(corpus["review_dimensions"]), "",
                  "记录格式：样本标签；维度；原文行号与引用；可观察差异；主观判断及依据；修订目标；不确定性。",
                  "在解盲后另记风格符合度。不得把关键词命中、字数或模型自评替代一般可读性与风格判断。", "",
                  "局限：" + "；".join(corpus["limitations"])])
    return "\n".join(lines) + "\n"


def authorized_config(args) -> tuple[Config, dict]:
    config = deepcopy(ConfigManager(ROOT).load())
    config.mode = "writer"
    config.api_timeout = 300
    config.api_max_retries = 0
    if args.source:
        if not args.model:
            raise ValueError("--source requires an explicit --model.")
        apply_model_selection(config, args.source, args.model)
    model = config.active_model
    if args.execute and model is None:
        raise ValueError("No active model is configured.")
    if args.reasoning_effort is not None:
        if config.active_model_source != "sensenova":
            raise ValueError("This effort override is supported only for the existing SenseNova adapter.")
        from reverie.sensenova import resolve_sensenova_selected_model

        selected = resolve_sensenova_selected_model(config.sensenova, model_id=model.model) or {}
        if args.reasoning_effort == "none" and not selected.get("supports_thinking_disable", True):
            raise ValueError("The selected model does not support disabling thinking.")
        if args.reasoning_effort != "none" and selected.get("thinking_control") != "effort":
            raise ValueError("The selected model manages its own thinking; effort levels cannot be selected.")
        config.sensenova["reasoning_effort"] = args.reasoning_effort
    evidence = {"source":config.active_model_source,"model":model.model if model else "dry-run",
                "max_tokens":args.max_tokens,"minimum_chapter_characters":MINIMUM_CHAPTER_CHARS,
                "target_chapter_characters":TARGET_CHAPTER_CHARS,
                "temperature":"configured provider value, equal across variants", "retries":0,"timeout_seconds":300}
    if config.active_model_source == "sensenova":
        from reverie.sensenova import build_sensenova_anthropic_options

        evidence["sampling_and_thinking"] = build_sensenova_anthropic_options(config.sensenova, model.model)
    if args.execute and not args.allow_model_usage:
        if config.active_model_source != "opencode":
            raise ValueError("Execution needs verified free OpenCode pricing or explicit --allow-model-usage.")
        from reverie.opencode import fetch_opencode_model_catalog

        live = fetch_opencode_model_catalog(config.opencode, timeout=15, force_refresh=True, proxy=config.api_proxy)
        chosen = next((item for item in live if item["id"] == model.model), None)
        pricing = ((chosen or {}).get("cost") or {}).get("text") or {}
        if not chosen or not chosen.get("free") or pricing.get("input", {}).get("price") != 0 or pricing.get("output", {}).get("price") != 0:
            raise ValueError("The selected model does not have verified live zero input/output pricing.")
        evidence["live_free_pricing"] = chosen["cost"]
    return config, evidence


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=ROOT / ".runtime" / "wstyle-evaluation")
    parser.add_argument("--execute", action="store_true", help="Explicitly execute model generation; omitted means offline planning only.")
    parser.add_argument("--resume", action="store_true", help="Reuse matching recorded responses and verified native chapters in this evaluation directory.")
    parser.add_argument("--source", choices=["opencode", "standard", "custom", "nvidia", "modelscope", "aihubmix", "sensenova", "agnes", "codex", "webgemini"])
    parser.add_argument("--model")
    parser.add_argument("--reasoning-effort", choices=["none", "low", "medium", "high", "max"],
                        help="Override SenseNova thinking for this evaluation only; never save it to application settings.")
    parser.add_argument("--allow-model-usage", action="store_true", help="Explicit authorization for configured provider usage, including paid models.")
    parser.add_argument("--max-tokens", type=int, default=32_768)
    parser.add_argument("--seed", type=int, default=20261111)
    parser.add_argument("--repeats", type=int, choices=range(1,4), default=1)
    args = parser.parse_args(argv)
    if not 8192 <= args.max_tokens <= 65_536:
        parser.error("Long-chapter evaluation requires an output budget between 8,192 and 65,536 tokens.")
    output = args.output.resolve()
    if output.exists() and any(output.iterdir()) and not args.resume:
        parser.error("Output must be an empty or new directory; existing evaluation evidence is never overwritten.")
    output.mkdir(parents=True, exist_ok=True)
    corpus = load_corpus()
    if args.resume:
        if not (output / "corpus.json").is_file() or json.loads((output / "corpus.json").read_text(encoding="utf-8")) != corpus:
            parser.error("Resume requires the same saved original corpus.")
        prior_results = output / "private/scene-results.json"
        archive = output / "private/scene-results-before-body-extraction.json"
        if prior_results.exists() and not archive.exists():
            archive.write_bytes(prior_results.read_bytes())
    write_json(output / "corpus.json", corpus)
    write_json(output / "continuity-plan.json", continuity_plan(corpus["cases"][0]))
    results = []
    status = {"schema":"reverie.writer.evaluation-run.v1","started_at":datetime.now(timezone.utc).isoformat(),
              "mode":"live_generation" if args.execute else "offline_plan","literary_quality":"unverified"}
    try:
        config, evidence = authorized_config(args)
        previous_run = output / "run.json"
        if args.resume and previous_run.exists() and json.loads(previous_run.read_text(encoding="utf-8")).get("model_conditions") != evidence:
            raise ValueError("Resume requires the same model, sampling, thinking and output conditions.")
        status["model_conditions"] = evidence
        write_json(output / "run.json", status)
        results = compare_scenes(corpus, output, config, execute=args.execute, seed=args.seed, max_tokens=args.max_tokens, repeats=args.repeats)
        status["scene_comparison"] = "generated" if args.execute else "planned"
        status["continuity"] = run_continuity(corpus, output, config, max_tokens=args.max_tokens) if args.execute else {"state":"planned","chapters":3}
        status["state"] = "generation_complete_reading_pending" if args.execute else "offline_plan_complete"
    except Exception as exc:
        status.update(state="blocked", error=str(exc)[:2000])
        path = output / "private" / "scene-results.json"
        if path.is_file():
            results = json.loads(path.read_text(encoding="utf-8"))
    write_json(output / "run.json", status)
    (output / "reader-review.md").write_text(review_sheet(corpus, results), encoding="utf-8", newline="\n")
    print(json.dumps({"output":str(output),"state":status["state"],"literary_quality":status["literary_quality"],"error":status.get("error","")},ensure_ascii=False))
    return 1 if status["state"] == "blocked" else 0


if __name__ == "__main__":
    raise SystemExit(main())
