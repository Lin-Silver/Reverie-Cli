"""Exercise the production packaged Electron host against a local model fixture.

All profiles, requests, logs, screenshots and writes stay in --output (repo-local).
No real provider, credential or user session is used. Run after build + package --dir.
"""
from __future__ import annotations

import argparse
import json
import os
import re
from pathlib import Path
import shutil
import socket
import subprocess
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "ReverieCli-py"))


class Fixture(BaseHTTPRequestHandler):
    requests = []
    hold = threading.Event()

    def log_message(self, *_args):
        pass

    def do_POST(self):
        payload = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        self.requests.append(payload)
        messages = payload.get("messages", [])
        last = str(messages[-1].get("content", "")) if messages else ""
        if "RIU_P2_HOLD" in last:
            self.hold.wait(30)
        message = {"role": "assistant", "content": "Fixture completed."}
        finish = "stop"
        if "RIU_P2_GENERATE" in last and messages[-1].get("role") == "user":
            message = {"role": "assistant", "content": None, "tool_calls": [{"id": "fixture-render", "type": "function", "function": {
                "name": "render_view", "arguments": json.dumps({"artifact_path": "interaction.html", "title": "RIU P2 fixture", "summary": "Local approval, state and recovery demo.", "callable_tools": ["create_file", "command_exec"]})}}]}
            finish = "tool_calls"
        body = json.dumps({"id": "fixture-response", "object": "chat.completion", "created": int(time.time()), "model": "riu-fixture", "choices": [{"index": 0, "message": message, "finish_reason": finish}], "usage": {"prompt_tokens": 100, "completion_tokens": 20, "total_tokens": 120}}).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--exe", type=Path, required=True)
    parser.add_argument("--output", type=Path, default=REPO / ".runtime" / "riu-p2" / time.strftime("%Y%m%d-%H%M%S"))
    args = parser.parse_args()
    output = args.output.resolve()
    if not output.is_relative_to(REPO):
        raise ValueError("Evidence output must stay in the repository.")
    output.mkdir(parents=True, exist_ok=False)
    workspace, app_root, desktop_home = (output / name for name in ("workspace", "app-root", "desktop-home"))
    for directory in (workspace, app_root, desktop_home):
        directory.mkdir()
    os.environ["REVERIE_APP_ROOT"] = str(app_root)
    os.environ["NO_PROXY"] = "127.0.0.1,localhost"
    from reverie.config import ConfigManager, ModelConfig
    from reverie.session.manager import SessionManager
    from playwright.sync_api import expect, sync_playwright
    server = ThreadingHTTPServer(("127.0.0.1", 0), Fixture)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    config = ConfigManager(workspace)
    config.ensure_dirs()
    cfg = config.load()
    cfg.models = [ModelConfig("riu-fixture", "RIU loopback fixture", f"http://127.0.0.1:{server.server_port}/v1", "fixture-local-only")]
    cfg.active_model_index, cfg.active_model_source = 0, "standard"
    cfg.stream_responses, cfg.api_proxy = False, ""
    cfg.security = {**cfg.security, "permission_level": "full_control", "permission_mode": "default"}
    config.save(cfg)
    manager = SessionManager(config.project_data_dir, project_root=workspace)
    session = manager.create_session("RIU P2 fixture")
    shutil.copyfile(REPO / "ReverieCli-py/tests/fixtures/riu_p2/interaction.html", workspace / "interaction.html")
    (workspace / "slow_write.py").write_text("from pathlib import Path\nimport time\np=Path('slow-effects.txt')\np.write_text((p.read_text() if p.exists() else '')+'effect\\n')\ntime.sleep(60)\nprint('finished')\n", encoding="utf-8")
    settings = desktop_home / ".reverie/desktop/desktop-settings.json"
    settings.parent.mkdir(parents=True)
    settings.write_text(json.dumps({"coreAppRoot": str(app_root), "projectRoot": str(workspace), "ui": {"language": "zh-CN"}}), encoding="utf-8")
    checks, process, browser, page = [], None, None, None
    report = {"scope": "production packaged Electron + loopback model; no external provider", "output": str(output), "checks": checks}
    env = {**os.environ, "PORTABLE_EXECUTABLE_DIR": str(desktop_home)}
    env.pop("ELECTRON_RUN_AS_NODE", None)
    log = (output / "electron.log").open("w", encoding="utf-8")

    def check(name, condition, detail=None):
        checks.append({"name": name, "passed": bool(condition), "detail": detail})
        print(json.dumps(checks[-1]), flush=True)
        if not condition:
            raise AssertionError(name)

    def stop():
        nonlocal process
        if process and process.poll() is None:
            subprocess.run(["taskkill", "/pid", str(process.pid), "/t", "/f"], capture_output=True, creationflags=subprocess.CREATE_NO_WINDOW)
            process.wait(timeout=15)
        process = None

    def request(action, payload):
        return page.evaluate("async ([action,payload]) => { try { return await window.reverie.request(action,payload); } catch(e) { return {error:String(e)}; } }", [action, payload])

    def observe(name):
        page.screenshot(path=str(output / (name + ".png")), full_page=True)
        (output / (name + ".txt")).write_text(page.locator("body").inner_text(), encoding="utf-8")
        (output / "events.json").write_text(json.dumps(page.evaluate("window.__riuEvents"), ensure_ascii=False, indent=2), encoding="utf-8")

    def launch(playwright):
        nonlocal process, browser, page
        with socket.socket() as sock:
            sock.bind(("127.0.0.1", 0))
            port = sock.getsockname()[1]
        startup = subprocess.STARTUPINFO()
        startup.dwFlags |= subprocess.STARTF_USESHOWWINDOW
        startup.wShowWindow = 0
        process = subprocess.Popen([str(args.exe.resolve()), "--gui", "--project", str(workspace), f"--remote-debugging-port={port}"], env=env, stdout=log, stderr=log, startupinfo=startup)
        for _ in range(120):
            try:
                browser = playwright.chromium.connect_over_cdp(f"http://127.0.0.1:{port}", timeout=1000)
                break
            except Exception:
                if process.poll() is not None:
                    raise RuntimeError("Electron exited: " + str(process.returncode))
                time.sleep(.25)
        else:
            raise RuntimeError("Electron CDP did not start.")
        page = browser.contexts[0].pages[0]
        page.wait_for_selector(".session-item", timeout=120000)
        page.wait_for_load_state("networkidle")
        page.locator(".session-item").filter(has_text="RIU P2 fixture").click()
        expect(page.locator(".model-copy strong")).to_have_text("RIU loopback fixture", timeout=30000)
        page.evaluate("window.__riuEvents=[];window.reverie.onEvent(e=>window.__riuEvents.push(e));true")
        observe("launch")
        print("Electron ready", flush=True)

    def frame():
        page.get_by_role("region", name="RIU P2 fixture", exact=True).scroll_into_view_if_needed()
        page.wait_for_selector("iframe.interactive-view-frame", timeout=120000)
        found = page.frame_locator("iframe.interactive-view-frame").first
        expect(found.locator("#ready")).to_have_text(re.compile("^Ready"), timeout=120000)
        return found

    def result(target, call_id):
        expect(target.locator("#result")).to_contain_text('"id":"' + call_id + '"', timeout=120000)
        return json.loads(target.locator("#result").inner_text())

    def approve(decision="once"):
        panel = page.get_by_role("alertdialog")
        panel.wait_for(timeout=120000)
        observe("approval-" + decision + "-" + str(len(checks)))
        panel.get_by_role("button", name="同意" if decision == "once" else "拒绝", exact=True).click()

    try:
        with sync_playwright() as playwright:
            launch(playwright)
            # Observe the rendered form before selecting and filling its composer.
            check("composer-observed", page.locator("textarea[aria-autocomplete=list]").count() == 1)
            page.locator("textarea[aria-autocomplete=list]").fill("RIU_P2_GENERATE")
            expect(page.locator("textarea[aria-autocomplete=list]")).to_have_value("RIU_P2_GENERATE")
            page.get_by_role("button", name="发送", exact=True).click()
            for _ in range(200):
                if len(Fixture.requests) >= 2: break
                page.wait_for_timeout(50)
            page.get_by_role("button", name="发送", exact=True).wait_for(timeout=120000)
            page.wait_for_selector(".live-message", state="detached", timeout=120000)
            target = frame()
            observe("view-ready")
            initial_requests = len(Fixture.requests)
            check("startup-message-only-proposes", page.get_by_role("button", name="发送追问", exact=True).count() == 1)
            page.wait_for_timeout(300)
            check("automatic-message-does-not-call-model", len(Fixture.requests) == initial_requests)
            target.locator("#write").click()
            approve()
            check("allowed-tool-result", result(target, "write-once").get("result", {}).get("status") == "success")
            check("approved-write-exists", (workspace / "approved.txt").read_text() == "APPROVED_ONCE")
            observe("tool-result")
            target.locator("#duplicate").click()
            check("duplicate-rejected", "duplicate" in json.dumps(result(target, "write-once")).lower())
            target.locator("#deny").click()
            approve("deny")
            check("denied-no-side-effect", "error" in result(target, "denied-once") and not (workspace / "denied.txt").exists())
            target.locator("#bad").click()
            check("schema-error-no-approval", "error" in result(target, "invalid-once") and page.get_by_role("alertdialog").count() == 0)
            target.locator("#stop").click()
            page.get_by_role("alertdialog").filter(has_text="stopped.txt").wait_for()
            observe("stop-approval")
            page.get_by_role("button", name="停止", exact=True).click()
            stopped = result(target, "stopped-once")
            check("stop-during-approval", "stop" in json.dumps(stopped).lower() and not (workspace / "stopped.txt").exists(), stopped)
            target.locator("#filter").fill("restored-filter")
            target.locator("#save").click()
            check("private-state-saved", result(target, "state").get("result", {}).get("revision") == 1)
            target.locator("#context").click()
            result(target, "context")
            before_followup = len(Fixture.requests)
            page.get_by_role("button", name="发送追问", exact=True).click()
            page.get_by_role("button", name="发送", exact=True).wait_for(timeout=120000)
            target = frame()
            check("host-followup-reaches-model-with-summary", any("Selected row 3" in json.dumps(p) for p in Fixture.requests))
            check("private-state-always-excluded-from-model", all("PRIVATE_UI_SENTINEL" not in json.dumps(p) for p in Fixture.requests))
            check("registered-html-not-reinjected-on-followup", len(Fixture.requests) > before_followup and all("RIU_P2_HTML_ONLY" not in json.dumps(p) for p in Fixture.requests[before_followup:]))
            report["generationInputBoundary"] = "Initial workspace retrieval may contain the source HTML before registration. It remains real model input; no zero-token claim. The follow-up must not re-add it."
            page.locator("textarea[aria-autocomplete=list]").fill("RIU_P2_HOLD")
            page.get_by_role("button", name="发送", exact=True).click()
            for _ in range(100):
                if "RIU_P2_HOLD" in str(Fixture.requests[-1].get("messages", [])[-1].get("content")): break
                page.wait_for_timeout(50)
            target = frame()
            target.locator("#busy").click()
            busy_reply = result(target, "busy-once")
            check("model-run-blocks-view-callback", "error" in busy_reply and not (workspace / "busy.txt").exists(), busy_reply)
            before_busy_followup = len(Fixture.requests)
            target.locator("#followup").click()
            page.get_by_role("button", name="发送追问", exact=True).click()
            check("busy-followup-retains-proposal", page.get_by_role("button", name="发送追问", exact=True).count() == 1 and len(Fixture.requests) == before_busy_followup)
            Fixture.hold.set()
            page.get_by_role("button", name="发送", exact=True).wait_for(timeout=120000)
            target = frame()
            target.locator("#slow").click()
            approve()
            for _ in range(100):
                if (workspace / "slow-effects.txt").exists(): break
                page.wait_for_timeout(100)
            check("slow-tool-side-effect-before-crash", (workspace / "slow-effects.txt").read_text() == "effect\n")
            observe("before-crash")
            stop()
            launch(playwright)
            target = frame()
            check("restart-restores-private-state", target.locator("#filter").input_value() == "restored-filter")
            check("restart-shows-unknown-write", "unknown" in target.locator("#receipts").inner_text())
            target.locator("#slow").click()
            unknown = result(target, "slow-once")
            check("unknown-write-never-replayed", "unknown" in json.dumps(unknown).lower() and (workspace / "slow-effects.txt").read_text() == "effect\n" and page.get_by_role("alertdialog").count() == 0, unknown)
            observe("restored-unknown")
            current = request("getSession", {})["session"]
            active_session_id = current["id"]
            view_id = next(item.name for item in (config.project_data_dir / "views" / active_session_id).iterdir() if item.is_dir())
            view = request("getView", {"sessionId": active_session_id, "viewId": view_id, "revision": 1})["view"]
            forked = request("forkSession", {"sessionId": active_session_id, "messageCount": len(current["messages"])})["session"]
            fork_view = request("getView", {"sessionId": forked["id"], "viewId": view_id, "revision": 1})["view"]
            check("fork-copies-private-state-without-call-replay", fork_view["state"]["state"]["filter"] == "restored-filter" and fork_view["toolCalls"] == [])
            stale = request("setViewState", {**{k:view[k] for k in ("sessionId", "viewId", "revision", "interactionId")}, "state": {}, "baseRevision": 1})
            check("old-instance-cross-session-rejected", "error" in stale)
            request("rewindSession", {"sessionId": forked["id"], "messageCount": 0, "confirmed": True})
            check("rewind-hides-later-view", "error" in request("getView", {"viewId": view_id, "sessionId": forked["id"], "revision": 1}))
            request("deleteSession", {"sessionId": forked["id"], "confirmed": True})
            request("getSession", {"sessionId": active_session_id})
            check("delete-fork-preserves-original", "view" in request("getView", {"sessionId": active_session_id, "viewId": view_id, "revision": 1}))
            approvals = []
            for receipt in (workspace / ".reverie/desktop/runs").glob("*.json.jsonl"):
                owner = json.loads(receipt.with_suffix("").read_text(encoding="utf-8"))
                for line in receipt.read_text(encoding="utf-8").splitlines():
                    event = json.loads(line)
                    if event.get("type") == "approval.request" and event.get("view_id"):
                        approvals.append({"event": event, "owner": {key: owner.get(key) for key in ("id", "sessionId", "pid")}})
            check("approvals-owned-by-execution-worker", len(approvals) >= 4 and all(item["event"]["run_id"] == item["owner"]["id"] and item["event"]["session_id"] == item["owner"]["sessionId"] and item["owner"]["pid"] and item["event"]["source"] == "component" for item in approvals))
            report["approvalOwners"] = approvals
            observe("complete")
            report["passed"] = True
    except Exception as exc:
        report["passed"], report["error"] = False, repr(exc)
        if page:
            try: observe("failure")
            except Exception: pass
        raise
    finally:
        if page:
            try: (output / "events.json").write_text(json.dumps(page.evaluate("window.__riuEvents"), ensure_ascii=False, indent=2), encoding="utf-8")
            except Exception: pass
        stop()
        server.shutdown()
        log.close()
        (output / "model-requests.json").write_text(json.dumps(Fixture.requests, ensure_ascii=False, indent=2), encoding="utf-8")
        (output / "report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        print("Evidence: " + str(output / "report.json"), flush=True)


if __name__ == "__main__":
    main()
