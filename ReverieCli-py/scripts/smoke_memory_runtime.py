"""Benchmark local memory and run an isolated real Agnes memory CRUD loop."""

from __future__ import annotations

import argparse
import contextlib
import io
import json
import os
from pathlib import Path
import shutil
import statistics
import subprocess
import sys
import tempfile
import time

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


def benchmark(root: Path) -> dict:
    from reverie.memory import MemoryOS
    from reverie.memory.models import EventRecord, MemoryItem

    memory = MemoryOS(root)
    memory.memory_store.save_items([
        MemoryItem.from_dict({"id": f"mem_{i:05d}", "scope": "project", "memory_type": "instruction",
                              "content": f"Component {i} requires deterministic physics verification and packaged runtime tests.",
                              "tags": ["verification"]}) for i in range(2000)
    ])
    with memory.event_store.events_path.open("w", encoding="utf-8") as handle:
        for i in range(50000):
            handle.write(json.dumps(EventRecord.from_dict({
                "id": f"evt_{i}", "event_type": "tool_result" if i % 5 == 0 else "message",
                "payload": {"text": f"record {i} physics verification"},
            }).to_dict()) + "\n")

    def measure(operation):
        times = []
        for _ in range(5):
            started = time.perf_counter()
            operation()
            times.append((time.perf_counter() - started) * 1000)
        return round(statistics.median(times), 3)

    return {
        "items": 2000, "events": 50000,
        "tail_20_ms": measure(lambda: memory.event_store.tail(20)),
        "query_20_ms": measure(lambda: memory.event_store.query(event_type="tool_result", contains="verification", limit=20)),
        "recall_8_ms": measure(lambda: memory.recall("deterministic physics verification", limit=8)),
        "remember_ms": measure(lambda: memory.remember("Use deterministic physics verification for the performance review.", memory_type="instruction")),
        "list_20_ms": measure(lambda: memory.memory_store.load_items(limit=20)),
    }


def live_loop(root: Path, config_path: Path, executable: Path | None, cycles: int, step_delay: float) -> list[dict]:
    original = json.loads(config_path.read_text(encoding="utf-8"))
    agnes = original.get("agnes", {})
    api_key = os.environ.get("AGNES_API_KEY") or agnes.get("api_key")
    if not api_key:
        raise ValueError("Agnes API key is required in the supplied config or AGNES_API_KEY.")
    app_root, project = root / "app", root / "project"
    (app_root / ".reverie").mkdir(parents=True)
    project.mkdir()
    config = {
        "config_version": original.get("config_version"), "active_model_source": "agnes",
        "active_model_index": 0, "mode": "reverie", "use_workspace_config": False, "models": [],
        "api_max_retries": original.get("api_max_retries", 5), "api_initial_backoff": original.get("api_initial_backoff", 1), "api_timeout": 30,
        "agnes": {"enabled": True, "api_key": "", "api_url": agnes.get("api_url", "https://apihub.agnes-ai.com/v1"),
                  "endpoint": "", "selected_model_id": "agnes-3.0-flash", "selected_model_display_name": "Agnes 3.0 Flash",
                  "max_context_tokens": 32768, "timeout": 30, "max_tokens": 512, "temperature": 0.2,
                  "top_p": 1, "thinking_mode": "none", "live_model_list": False},
    }
    (app_root / ".reverie" / "config.json").write_text(json.dumps(config), encoding="utf-8")
    previous_env = {key: os.environ.get(key) for key in ("REVERIE_APP_ROOT", "AGNES_API_KEY")}
    os.environ.update(REVERIE_APP_ROOT=str(app_root), AGNES_API_KEY=str(api_key))
    try:
        from reverie.config import get_project_data_dir
        from reverie.memory import MemoryOS
        from reverie.agent.agent import ReverieAgent
        from reverie.cli.interface import ReverieInterface
        from reverie.memory.safety import redact_memory_text

        memory = MemoryOS(get_project_data_dir(project), project_root=project)
        model_calls = []
        original_call = ReverieAgent._call_openai_chat_completion_once

        def measured_call(agent, kwargs):
            started = time.perf_counter()
            sample = {"payload_bytes": len(json.dumps(kwargs, ensure_ascii=False).encode("utf-8")), "tool_schemas": len(kwargs.get("tools") or [])}
            model_calls.append(sample)
            try:
                response = original_call(agent, kwargs)
            except Exception as exc:
                sample.update(error_type=type(exc).__name__, error_status=getattr(exc, "status_code", None), error=redact_memory_text(str(exc).replace(str(api_key), "[REDACTED]"))[:300], request_seconds=round(time.perf_counter() - started, 3))
                raise
            sample["connected_seconds"] = round(time.perf_counter() - started, 3)
            if not kwargs.get("stream"):
                return response
            def stream():
                try:
                    for event in response:
                        sample.setdefault("first_event_seconds", round(time.perf_counter() - started, 3))
                        yield event
                finally:
                    sample["stream_seconds"] = round(time.perf_counter() - started, 3)
                    response.close()
            return stream()

        if not executable:
            ReverieAgent._call_openai_chat_completion_once = measured_call
        results = []
        try:
            for cycle in range(cycles):
                if cycle:
                    print(json.dumps({"cycle": cycle + 1, "cooldown_seconds": 60, "reason": "Avoid bursting the free Agnes API between test cycles."}), flush=True)
                    time.sleep(60)
                current_id = ""
                for step, action in enumerate(("remember", "recall", "correct", "recall_corrected", "delete")):
                    if step and step_delay:
                        print(json.dumps({"action": action, "step_cooldown_seconds": step_delay}), flush=True)
                        time.sleep(step_delay)
                    before_event = memory.event_store.tail(1)
                    before_id = before_event[-1].id if before_event else ""
                    prompts = {
                        "remember": f"请新增一条项目记忆：本次临时测试项目偏好使用中文简洁回答。请自行整理记忆文本，topic 使用 memory-smoke-{cycle}，保存成功后简短确认。",
                        "recall": "请调用 memory_retrieval 检索本次临时测试项目的回答偏好，报告找到的记忆。",
                        "correct": f"请调用 memory_manager correct 修改记忆 {current_id}：本次临时测试项目偏好使用中文详细回答。请自行整理简洁、独立的记忆文本。",
                        "recall_corrected": "请调用 memory_retrieval 检索本次临时测试项目最新的回答偏好，报告找到的记忆。",
                        "delete": f"请调用 memory_manager delete 删除临时测试记忆 {current_id}，成功后简短确认。",
                    }
                    model_calls.clear()
                    started = time.perf_counter()
                    if executable:
                        report_path = root / "turn-report.json"
                        report_path.unlink(missing_ok=True)
                        env = dict(os.environ, PYTHONIOENCODING="utf-8")
                        completed = subprocess.run([str(executable), str(project), "--no-index", "--mode", "reverie", "--prompt", prompts[action], "--report-file", str(report_path)],
                                                   capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=150, env=env)
                        report = json.loads(report_path.read_text(encoding="utf-8")) if report_path.exists() else {}
                        success = completed.returncode == 0 and report.get("success", False)
                    else:
                        with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
                            report = ReverieInterface(project, headless=True).run_prompt_once(prompts[action], no_index=True, mode_override="reverie").to_dict()
                        success = report["success"]
                    elapsed = round(time.perf_counter() - started, 3)
                    events = memory.event_store.tail(100)
                    if before_id:
                        start = next((i + 1 for i, e in enumerate(events) if e.id == before_id), 0)
                        events = events[start:]
                    tools = [e for e in events if e.event_type == "tool_result"]
                    if action == "remember":
                        saved_events = {e.id for e in events if e.event_type == "memory_remembered"}
                        saved = [item for item in memory.memory_store.load_items() if saved_events.intersection(item.source_event_ids)]
                        success = success and len(saved) == 1 and all(term in saved[0].content for term in ("中文", "简洁"))
                        if saved:
                            current_id = saved[0].id
                    elif action == "correct":
                        old = memory.memory_store.get(current_id, include_deleted=True)
                        replacement = memory.memory_store.get(old.superseded_by) if old else None
                        success = success and replacement is not None and replacement.version == 2 and all(term in replacement.content for term in ("中文", "详细"))
                        if replacement:
                            current_id = replacement.id
                    elif action == "delete":
                        item = memory.memory_store.get(current_id, include_deleted=True)
                        success = success and item is not None and item.status == "deleted"
                    else:
                        success = success and any(e.payload.get("tool_name") == "memory_retrieval" and current_id in str(e.payload.get("output")) for e in tools)
                    sample = {"cycle": cycle + 1, "action": action, "success": bool(success), "elapsed_seconds": elapsed,
                              "runtime_seconds": report.get("duration_seconds"),
                              "tools": [{"name": e.payload.get("tool_name"), "action": (e.payload.get("arguments") or {}).get("action"), "elapsed_ms": e.payload.get("elapsed_ms"), "success": e.payload.get("success")} for e in tools],
                              "model_calls": list(model_calls)}
                    if action in {"remember", "correct"} and success:
                        stored_item = memory.memory_store.get(current_id)
                        sample["memory"] = {"scope": stored_item.scope, "type": stored_item.memory_type, "content": stored_item.content, "version": stored_item.version}
                    if not success:
                        sample["error"] = redact_memory_text(str(report.get("error") or "Memory postcondition failed.").replace(str(api_key), "[REDACTED]"))[:300]
                    results.append(sample)
                    print(json.dumps(sample), flush=True)
                    if not success:
                        return results
            return results
        finally:
            ReverieAgent._call_openai_chat_completion_once = original_call
    finally:
        for key, value in previous_env.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, help="Agnes config for real calls; credentials stay in memory/environment.")
    parser.add_argument("--executable", type=Path, help="Test a packaged kernel instead of the source runtime.")
    parser.add_argument("--cycles", type=int, default=1)
    parser.add_argument("--step-delay", type=float, default=15, help="Free-provider test pacing, 0..60 seconds; excluded from per-step timings.")
    parser.add_argument("--report", type=Path)
    args = parser.parse_args()
    if not 0 <= args.step_delay <= 60:
        parser.error("--step-delay must be between 0 and 60 seconds")
    root = Path(tempfile.mkdtemp(prefix="reverie-memory-review-"))
    try:
        report = {"benchmark": benchmark(root / "benchmark")}
        print(json.dumps(report), flush=True)
        if args.config:
            report["cycle_cooldown_seconds"] = 60 if args.cycles > 1 else 0
            report["step_cooldown_seconds"] = args.step_delay
            report["live"] = live_loop(root / "live", args.config, args.executable, max(1, args.cycles), args.step_delay)
        report["success"] = all(item["success"] for item in report.get("live", []))
        if args.report:
            args.report.parent.mkdir(parents=True, exist_ok=True)
            args.report.write_text(json.dumps(report, indent=2), encoding="utf-8")
        return 0 if report["success"] else 1
    finally:
        shutil.rmtree(root, ignore_errors=True)


if __name__ == "__main__":
    raise SystemExit(main())
