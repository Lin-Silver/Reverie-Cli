"""Exercise actual source/frozen CLI completion and failure paths with local HTTP.

Authored transport fixtures only: no external API or model-quality samples.
Every case owns its workspace, HOME, provider configuration and output directory.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import subprocess
import sys
import threading
import time

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "ReverieCli-py"))
from reverie.config import ConfigManager, ModelConfig
from reverie.session.manager import SessionManager


class Fixture(BaseHTTPRequestHandler):
    def log_message(self, *_args):
        pass

    def do_POST(self):
        payload = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        self.server.requests.append(payload)
        number = len(self.server.requests)
        mode = self.server.mode
        if mode == "rate_limited":
            body = json.dumps({"error": {"message": "Local replay of Agnes rate limit", "type": "throttling_error", "code": "429"}}).encode()
            self.send_response(429)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return
        if mode == "partial_failure" and number > 1:
            body = json.dumps({"error": {"message": "Fixture disconnected before final answer", "type": "server_error"}}).encode()
            self.send_response(503)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return
        content = None if mode == "reasoning_only" else "Partial answer."
        reasoning = "Actual unfinished fixture reasoning." if mode == "reasoning_only" else None
        reason = "length"
        if mode == "recovered" and number > 1:
            content, reason = "Complete answer.", "stop"
        message = {"content": content, "reasoning_content": reasoning}
        common = {"id": "turn-integrity", "model": "local-fixture", "created": int(time.time())}
        if payload.get("stream"):
            event = {**common, "object": "chat.completion.chunk", "choices": [{"index": 0, "delta": message, "finish_reason": reason}]}
            body = ("data: " + json.dumps(event) + "\n\ndata: [DONE]\n\n").encode()
            content_type = "text/event-stream"
        else:
            response = {**common, "object": "chat.completion", "choices": [{"index": 0, "message": {"role": "assistant", **message}, "finish_reason": reason}]}
            body, content_type = json.dumps(response).encode(), "application/json"
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


def run_case(output: Path, cli: list[str], mode: str, stream: bool):
    output.mkdir()
    workspace, state, home = [output / name for name in ("Project With Spaces", "app-root", "home")]
    for directory in (workspace, state, home):
        directory.mkdir()
    subprocess.run(["git", "-c", "init.templateDir=", "init", "-q", str(workspace)], check=True)
    server = ThreadingHTTPServer(("127.0.0.1", 0), Fixture)
    server.mode, server.requests = mode, []
    threading.Thread(target=server.serve_forever, daemon=True).start()
    previous = os.environ.get("REVERIE_APP_ROOT")
    os.environ["REVERIE_APP_ROOT"] = str(state)
    try:
        manager = ConfigManager(workspace)
        manager.ensure_dirs()
        cfg = manager.load()
        cfg.models = [ModelConfig("local-fixture", "Local fixture", f"http://127.0.0.1:{server.server_port}/v1", "fixture-only")]
        cfg.active_model_source, cfg.active_model_index = "standard", 0
        if mode == "rate_limited":
            cfg.active_model_source = "agnes"
            cfg.agnes.update(api_url=f"http://127.0.0.1:{server.server_port}/v1", api_key="fixture-only",
                             selected_model_id="agnes-3.0-flash", live_model_list=False, timeout=10)
        cfg.stream_responses, cfg.auto_index, cfg.api_proxy = stream, False, ""
        cfg.api_max_retries, cfg.api_timeout = 0, 10
        manager.save(cfg)
    finally:
        if previous is None:
            os.environ.pop("REVERIE_APP_ROOT", None)
        else:
            os.environ["REVERIE_APP_ROOT"] = previous
    env = {**os.environ, "HOME": str(home), "REVERIE_APP_ROOT": str(state),
           "PYTHONPATH": str(ROOT / "ReverieCli-py"), "NO_PROXY": "127.0.0.1,localhost", "no_proxy": "127.0.0.1,localhost"}
    command = [*cli, str(workspace), "--no-index", "--prompt", "Answer in plain text using the supplied example data.",
               "--report-file", str(output / "prompt-report.json")]
    started = time.monotonic()
    try:
        with (output / "cli.log").open("x") as log:
            process = subprocess.run(command, cwd=workspace, env=env, stdout=log, stderr=subprocess.STDOUT, timeout=60)
    finally:
        server.shutdown()
        server.server_close()
        (output / "requests.json").write_text(json.dumps(server.requests, ensure_ascii=False, indent=2) + "\n")
    report = json.loads((output / "prompt-report.json").read_text())
    session = SessionManager(manager.project_data_dir, project_root=workspace).load_session(report["session_id"])
    success = mode == "recovered"
    harness_report = report["harness_report"]
    current_gate = harness_report["completion_gate"]
    latest_run = harness_report["run_history"]["latest_run"]
    checks = {
        "exit_status": process.returncode == (0 if success else 1),
        "explicit_result": report["success"] is success,
        "error_status": bool(report["error"]) is not success,
        "saved_run_status": session.metadata["prompt_run"]["state"] == ("completed" if success else "interrupted"),
        "bounded_requests": len(server.requests) == (1 if mode == "rate_limited" else 4 if mode == "reasoning_only" else 3 if mode == "truncated" else 2),
        "current_gate_persisted": latest_run["completion_gate_status"] == current_gate["status"]
        and latest_run["completion_gate_label"] == current_gate["label"],
        "failed_run_gate_blocked": success or current_gate["status"] == "blocked",
        "history_success_matches_result": latest_run["success"] is success,
    }
    if mode == "reasoning_only":
        checks["all_reasoning_retained"] = [m["reasoning_content"] for m in session.messages if m.get("reasoning_content")] == ["Actual unfinished fixture reasoning."] * 4
        checks["host_notice_is_failure"] = "the request is not finished" in report["error"]
    elif mode != "rate_limited":
        checks["saved_partial_answer"] = any(m.get("content") == "Partial answer." for m in session.messages)
    if mode == "rate_limited":
        checks["rate_limit_remains_failure"] = "429" in report["error"] and not report["output_text"]
    if success:
        checks["complete_answer"] = report["output_text"] == "Complete answer."
    if mode == "partial_failure":
        checks["failure_not_hidden_by_partial"] = "Fixture disconnected before final answer" in report["error"] and report["output_text"] == "Partial answer."
    result = {"mode": mode, "stream": stream, "cli_exit": process.returncode,
              "seconds": round(time.monotonic() - started, 3), "checks": checks, "passed": all(checks.values())}
    (output / "execution.json").write_text(json.dumps(result, indent=2) + "\n")
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cli-exe", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    output = args.output.resolve()
    if not output.is_relative_to(ROOT / ".runtime"):
        parser.error("Use a fresh repository .runtime output directory")
    output.mkdir(parents=True, exist_ok=False)
    cli = [str(args.cli_exe.resolve())] if args.cli_exe else [sys.executable, "-m", "reverie"]
    report = {"schema": "reverie.provider.turn-integrity.v1", "started_at": datetime.now(timezone.utc).isoformat(),
              "cli": cli, "formal_model_quality_samples": 0, "cases": [], "passed": False}
    try:
        for mode in ("reasoning_only", "truncated", "recovered", "partial_failure", "rate_limited"):
            for stream in (False, True):
                result = run_case(output / f"{mode}-{'stream' if stream else 'buffered'}", cli, mode, stream)
                report["cases"].append(result)
                print(json.dumps(result), flush=True)
        report["passed"] = all(case["passed"] for case in report["cases"])
    except Exception as error:
        report["error"] = type(error).__name__ + ": " + str(error)
    finally:
        (output / "report.json").write_text(json.dumps(report, indent=2) + "\n")
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
