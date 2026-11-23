"""Measure the unchanged released retrieval chain with a local protocol fixture.

Every trial runs all sixteen frozen basic questions in their frozen order.
Cold batches use a new kernel and an existing complete index. Warm batches
reuse a kernel after an entire prewarming batch. The 21-second wait between
warm batches expires Python's 20-second result cache outside the timed calls.
The fixture supplies tool calls, never context results. No model quality is
claimed. Raw requests, events, actual tool output and final replies are kept.
"""
import argparse
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import hashlib
import importlib.util
import json
from pathlib import Path
import shutil
import sys
import threading
import time
import traceback

ROOT = Path.cwd().resolve()
sys.stdout.reconfigure(encoding="utf-8")
spec = importlib.util.spec_from_file_location(
    "package_baseline", Path(__file__).with_name("measure-python-sdk-baseline.py"))
sdk = importlib.util.module_from_spec(spec)
spec.loader.exec_module(sdk)


class Fixture(BaseHTTPRequestHandler):
    def log_message(self, *_args):
        pass

    def do_POST(self):
        body_bytes = self.rfile.read(int(self.headers["Content-Length"]))
        received = time.perf_counter_ns()
        body = json.loads(body_bytes)
        current = self.server.current
        names = [item.get("function", {}).get("name") for item in body.get("tools", [])]
        returned = [item for item in body.get("messages", []) if item.get("role") == "tool"
                    and item.get("tool_call_id") == current["call_id"]]
        current["requests"].append({"received_ns": received, "path": self.path, "body": body})
        name = next((item for item in names if item in
                    ("codebase-retrieval", "codebase_retrieval", "retrieve_codebase", "repo_context")), None)
        if name and not returned:
            message = {"role": "assistant", "content": None, "tool_calls": [{
                "id": current["call_id"], "type": "function", "function": {
                    "name": name, "arguments": json.dumps(current["arguments"], ensure_ascii=False)}}]}
            reason = "tool_calls"
        else:
            message = {"role": "assistant", "content": "Local retrieval protocol fixture completed."}
            reason = "stop"
            if returned:
                current["returned_ns"] = received
                current["output"] = returned[-1]["content"]
        payload = json.dumps({"id": "phase0-retrieval", "object": "chat.completion",
            "created": int(time.time()), "model": "phase0-context",
            "choices": [{"index": 0, "message": message, "finish_reason": reason}],
            "usage": {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2}}).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        if name and not returned:
            current["dispatch_ns"] = time.perf_counter_ns()
        self.wfile.write(payload)


def prepare(directory, server):
    env = sdk.seed(directory)
    env["NO_PROXY"] = "127.0.0.1,localhost"
    sdk.write_json(directory / "app/.reverie/config.json", {
        "auto_index": False, "stream_responses": False, "active_model_source": "standard",
        "max_context_tokens": 128000, "api_max_retries": 0, "api_timeout": 30,
        "models": [{"model": "phase0-context", "provider": "openai-chat",
            "model_display_name": "Local retrieval protocol fixture",
            "base_url": f"http://127.0.0.1:{server.server_port}/v1", "api_key": "test-only",
            "max_context_tokens": 128000}]})
    source = ROOT / ".runtime/phase0B/baseline/python-sdk-baseline-v1/index-01/app/.reverie/projects"
    database = next(source.rglob("python-search.sqlite3"))
    shutil.copytree(database.parent, directory / "app/.reverie/projects" / database.parent.relative_to(source))
    return env


def batch(bridge, server, queries, group, trial, output):
    rows = []
    for query in queries:
        arguments = {"query_type": "task", "query": query["query"], "max_files": 6,
            "max_symbols": 12, "max_tokens": 12000, "include_history": True, "include_memory": True}
        current = {"call_id": f"phase0_{group}_{trial}_{query['id']}", "arguments": arguments, "requests": []}
        server.current = current
        event_start = len(bridge.events)
        response = bridge.request("runPrompt", {"prompt": "执行一次只读上下文查询后结束。",
            "stream": False, "freshSession": True, "noIndex": True})
        assert response["response"]["type"] == "prompt.result"
        assert response["response"]["result"]["success"], response["response"]
        text = current.get("output")
        assert isinstance(text, str) and "CURATED EXCERPTS" in text and "TASK CONTEXT" in text
        assert query["query"] in text and len(current["requests"]) == 2
        stream = [(stamp, item.get("event", {}).get("event", {})) for stamp, item in bridge.events[event_start:]
                  if item.get("type") == "prompt.event" and item.get("event", {}).get("type") == "ui.event"]
        starts = [stamp for stamp, item in stream if item.get("event") == "tool_start"
                  and item.get("tool_call_id") == current["call_id"]]
        ends = [(stamp, item) for stamp, item in stream if item.get("event") == "tool_result"
                and item.get("tool_call_id") == current["call_id"]]
        assert len(starts) == len(ends) == 1 and ends[0][1]["success"]
        assert ends[0][1]["output"] == text
        token_estimate = len(text) // 4
        assert token_estimate <= 12000
        record = {"group": group, "trial": trial, "query_id": query["id"], "arguments": arguments,
            "sdk_prompt_request_ms": response["request_ms"],
            "query_dispatch_to_complete_return_ms": (current["returned_ns"] - current["dispatch_ns"]) / 1e6,
            "observed_tool_start_to_result_ms": (ends[0][0] - starts[0]) / 1e6,
            "context_sha256": hashlib.sha256(text.encode()).hexdigest(),
            "context_bytes": len(text.encode()), "estimated_tokens": token_estimate}
        raw = {**record, "context_string": text, "response": response["response"],
            "requests": current["requests"], "events": bridge.events[event_start:]}
        sdk.write_json(output / f"{group}-{trial:02}-{query['id']}.json", raw)
        rows.append(record)
    state = bridge.request("getContextStatus")["response"]["context_engine"]
    assert state["ready"] and not state["indexing"] and state["files"] == 1451 and state["backend"] == "python"
    return {"group": group, "trial": trial, "queries": rows, "context_status": state,
        "complete_query_batch_ms": sum(item["query_dispatch_to_complete_return_ms"] for item in rows),
        "complete_sdk_batch_ms": sum(item["sdk_prompt_request_ms"] for item in rows)}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--count", type=int, default=30)
    parser.add_argument("--pilot", action="store_true")
    args = parser.parse_args()
    output = args.output.resolve()
    if output.exists() or not output.is_relative_to(ROOT / ".runtime") or args.count < 1:
        parser.error("Use a new project-local output directory and a positive count")
    executable = ROOT / ".runtime/phase0B/baseline/py-release/reverie.exe"
    assert sdk.digest(executable) == sdk.EXPECTED_EXE
    labels_file = ROOT / "testdata/context-evaluation/queries-v1.json"
    labels = json.loads(labels_file.read_bytes())
    queries = [item for item in labels["queries"] if item["family"] == "basic"]
    assert len(queries) == 16 and labels["status"] == "frozen_after_independent_cross_review"
    if args.pilot:
        queries = queries[:1]
    output.mkdir(parents=True)
    server = ThreadingHTTPServer(("127.0.0.1", 0), Fixture)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    report = {"schema": "reverie.python-context-package-baseline.v1", "source_commit": sdk.SOURCE,
        "exe_sha256": sdk.EXPECTED_EXE, "harness_sha256": sdk.digest(Path(__file__)),
        "bridge_harness_sha256": sdk.digest(Path(__file__).with_name("measure-python-sdk-baseline.py")),
        "labels_sha256": sdk.digest(labels_file), "query_ids": [item["id"] for item in queries],
        "corpus_manifest_sha256": sdk.digest(ROOT / "testdata/context-evaluation/frozen-corpus-v1.json"),
        "method": __doc__, "formal": args.count >= 30 and not args.pilot,
        "filesystem_cache": "uncontrolled", "query_cache_expiry_wait_seconds": 21,
        "started_at": datetime.now(timezone.utc).isoformat(), "batches": [], "passed": False}
    bridge = None
    try:
        for trial in range(1, args.count + 1):
            directory = output / f"cold-profile-{trial:02}"
            bridge = sdk.Bridge(executable, directory, prepare(directory, server))
            bridge.request("initialize", {"projectRoot": str(sdk.CORPUS), "deferPayloads": True})
            row = batch(bridge, server, queries, "fresh_process", trial, output)
            row["close"] = bridge.close()
            bridge = None
            report["batches"].append(row)
            sdk.write_json(output / "progress.json", report)
            print(json.dumps({"group": row["group"], "trial": trial,
                "query_batch_ms": row["complete_query_batch_ms"]}), flush=True)
        directory = output / "warm-profile"
        bridge = sdk.Bridge(executable, directory, prepare(directory, server))
        bridge.request("initialize", {"projectRoot": str(sdk.CORPUS), "deferPayloads": True})
        report["warmup"] = batch(bridge, server, queries, "warmup", 0, output)
        for trial in range(1, args.count + 1):
            time.sleep(21)
            row = batch(bridge, server, queries, "prewarmed_process", trial, output)
            report["batches"].append(row)
            sdk.write_json(output / "progress.json", report)
            print(json.dumps({"group": row["group"], "trial": trial,
                "query_batch_ms": row["complete_query_batch_ms"]}), flush=True)
        report["warm_close"] = bridge.close()
        bridge = None
        report["distributions"] = {group: sdk.distribution([
            row["complete_query_batch_ms"] for row in report["batches"] if row["group"] == group])
            for group in ("fresh_process", "prewarmed_process")}
        assert sdk.digest(executable) == sdk.EXPECTED_EXE
        report["passed"] = True
    except Exception as error:
        report.update(error=str(error), traceback=traceback.format_exc())
        raise
    finally:
        if bridge is not None:
            report["failure_cleanup"] = bridge.close()
        server.shutdown()
        report["finished_at"] = datetime.now(timezone.utc).isoformat()
        sdk.write_json(output / "report.json", report)
    print(json.dumps({"passed": report["passed"], "formal": report["formal"], "output": str(output)}), flush=True)


if __name__ == "__main__":
    main()
