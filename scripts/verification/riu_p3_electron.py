"""Production packaged Electron + unchanged ext-apps 2.0.3 example and hostile fixtures.

Install the pinned scripts/verification/fixtures/mcp-apps manifest in a repo-local
directory, then pass --sdk-root. No component source or bundle is rewritten.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import socket
import subprocess
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "ReverieCli-py"))
from desktop_process import launch_options, packaged_kernel_path, stop_process, wait_for_packaged_page
from riu_quality_benchmark import settle_view, start_event_capture
SECRET = "PRIVATE_META_MUST_NEVER_REACH_MODEL"


class ModelFixture(BaseHTTPRequestHandler):
    requests = []

    def log_message(self, *_args):
        pass

    def do_POST(self):
        payload = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        self.requests.append(payload)
        messages = payload.get("messages", [])
        latest = next((str(item.get("content", "")) for item in reversed(messages) if item.get("role") == "user" and "RIU_P3_" in str(item.get("content", ""))), "")
        match = re.search(r"RIU_P3_TOOL:([A-Za-z0-9_-]+)", latest)
        message, finish = {"role": "assistant", "content": "MCP tool completed; its text remains available."}, "stop"
        if match:
            suffix = match[1]
            name = "mcp_official_get_time" if suffix == "official" else "mcp_negative_" + suffix.replace("-", "_")
            last = messages[-1] if messages else {}
            if last.get("role") == "user":
                tool, arguments = "tool_catalog", {"operation": "search", "query": "get-time" if suffix == "official" else suffix}
            elif last.get("role") == "tool" and "search" in str(last.get("name", "")):
                tool, arguments = name, {}
            else:
                # Chat tool messages need not retain a name; the previous
                # assistant's canonical tool name is authoritative in that case.
                previous = next((item for item in reversed(messages) if item.get("tool_calls")), {})
                called = (previous.get("tool_calls") or [{}])[-1].get("function", {}).get("name")
                tool, arguments = (name, {}) if called in {"tool_search", "tool_catalog"} else (None, {})
            if tool:
                if tool == "tool_catalog": time.sleep(.5)
                message = {"role": "assistant", "content": None, "tool_calls": [{"id": f"p3-{len(self.requests)}", "type": "function", "function": {"name": tool, "arguments": json.dumps(arguments)}}]}
                finish = "tool_calls"
            elif last.get("role") == "tool" and str(last.get("content", "")).startswith("Useful text"):
                message["content"] = str(last["content"])
        body = json.dumps({"id": "p3-model", "object": "chat.completion", "created": int(time.time()), "model": "riu-p3-fixture", "choices": [{"index": 0, "message": message, "finish_reason": finish}], "usage": {"prompt_tokens": 80, "completion_tokens": 20, "total_tokens": 100}}).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--exe", type=Path, required=True)
    parser.add_argument("--sdk-root", type=Path, required=True)
    parser.add_argument("--output", type=Path, default=REPO / ".runtime/riu-p3" / time.strftime("%Y%m%d-%H%M%S"))
    args = parser.parse_args()
    output = args.output.resolve()
    if not output.is_relative_to(REPO): raise ValueError("Evidence must stay in this repository.")
    output.mkdir(parents=True, exist_ok=False)
    workspace, app_root, desktop_home = (output / name for name in ("workspace", "app-root", "desktop-home"))
    for directory in (workspace, app_root, desktop_home): directory.mkdir()
    os.environ["REVERIE_APP_ROOT"] = str(app_root)
    os.environ["NO_PROXY"] = "127.0.0.1,localhost"
    from reverie.config import ConfigManager, ModelConfig
    from reverie.mcp import MCPConfigManager
    from reverie.session.manager import SessionManager
    from playwright.sync_api import expect, sync_playwright
    official = args.sdk_root.resolve() / "node_modules/@modelcontextprotocol/server-basic-vanillajs/dist"
    original_html = (official / "mcp-app.html").read_bytes()
    original_hash = hashlib.sha256(original_html).hexdigest()
    MCPConfigManager(app_root).save({"mcpServers": {
        "official": {"command": shutil.which("node"), "args": [str(official / "index.js"), "--stdio"], "trust": True},
        "negative": {"command": sys.executable, "args": [str(REPO / "ReverieCli-py/tests/fixtures/riu_p3/server.py"), "--state", str(output / "effects")], "trust": True},
    }})
    model = ThreadingHTTPServer(("127.0.0.1", 0), ModelFixture)
    threading.Thread(target=model.serve_forever, daemon=True).start()
    config = ConfigManager(workspace); config.ensure_dirs(); cfg = config.load()
    cfg.models = [ModelConfig("riu-p3-fixture", "RIU P3 loopback", f"http://127.0.0.1:{model.server_port}/v1", "fixture-local-only")]
    cfg.active_model_index, cfg.active_model_source = 0, "standard"
    cfg.stream_responses, cfg.api_proxy = False, ""
    cfg.security = {**cfg.security, "permission_level": "full_control", "permission_mode": "default"}
    config.save(cfg)
    manager = SessionManager(config.project_data_dir, project_root=workspace)
    manager.create_session("RIU P3 interoperability")
    settings = desktop_home / ".reverie/desktop/desktop-settings.json"
    settings.parent.mkdir(parents=True)
    settings.write_text(json.dumps({"coreAppRoot": str(app_root), "projectRoot": str(workspace), "ui": {"language": "zh-CN"}}), encoding="utf-8")
    env = {**os.environ, "PORTABLE_EXECUTABLE_DIR": str(desktop_home)}
    env.pop("ELECTRON_RUN_AS_NODE", None)
    checks, process, page, browser = [], None, None, None
    report = {"scope": "Production packaged Electron + unchanged official stdio MCP example + local negative fixtures; loopback model", "versions": {"ext_apps": "2.0.3", "ui_protocol": "2026-01-26", "mcp_core": "2025-06-18"}, "output": str(output), "official_html_sha256": original_hash, "checks": checks}
    log = (output / "electron.log").open("w", encoding="utf-8")

    def check(name, passed, detail=None):
        checks.append({"name": name, "passed": bool(passed), "detail": detail})
        print(json.dumps(checks[-1]), flush=True)
        if not passed: raise AssertionError(name)

    def request(action, payload):
        return page.evaluate("async ([a,p])=>{try{return await window.reverie.request(a,p)}catch(e){return {error:String(e)}}}", [action, payload])

    def observe(name):
        page.screenshot(path=str(output / (name + ".png")), full_page=True)
        (output / (name + ".txt")).write_text(page.locator("body").inner_text(), encoding="utf-8")

    def send_tool(name):
        old_requests = len(ModelFixture.requests)
        editor = page.locator("textarea[aria-autocomplete=list]")
        editor.fill("RIU_P3_TOOL:" + name)
        page.get_by_role("button", name="发送", exact=True).click()
        for _ in range(2400):
            page.wait_for_timeout(50)
            if len(ModelFixture.requests) >= old_requests + 3 and page.locator(".live-message").count() == 0:
                break
        else: raise RuntimeError("Model/tool run did not finish: " + name)
        observe("tool-" + name)

    def frame(title):
        page.get_by_role("region", name=title, exact=True).scroll_into_view_if_needed()
        element = page.locator(f'iframe[title="{title}"]')
        element.wait_for(timeout=30000)
        return element.content_frame

    def approve(decision="同意"):
        panel = page.get_by_role("alertdialog")
        panel.wait_for(timeout=30000)
        observe("approval-" + str(len(checks)))
        panel.get_by_role("button", name=decision, exact=True).click()

    try:
        hello = subprocess.run([str(packaged_kernel_path(args.exe)), "--sdk-bridge"],
                               input=json.dumps({"id": "p3-hello", "action": "hello"}) + "\n",
                               text=True, encoding="utf-8", capture_output=True, env=env, cwd=workspace,
                               timeout=60, creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
        envelopes = [json.loads(line) for line in hello.stdout.splitlines() if line.startswith("{")]
        profile = next(item for item in envelopes if item.get("id") == "p3-hello")
        report["kernel_hello"] = profile
        check("packaged-hello-profile", profile["capabilities"]["views"]["mcp_apps"] is True)
        with sync_playwright() as playwright:
            with socket.socket() as sock: sock.bind(("127.0.0.1", 0)); port = sock.getsockname()[1]
            process = subprocess.Popen([str(args.exe.resolve()), "--gui", "--project", str(workspace), f"--remote-debugging-port={port}"], env=env, stdout=log, stderr=log, **launch_options())
            browser, page = wait_for_packaged_page(playwright, process, port, attempts=120)
            page.set_viewport_size({"width": 1280, "height": 900})
            context = page.context
            context.add_init_script("window.__p3wire=[];addEventListener('message',e=>{if(window.__p3wire.length<256)window.__p3wire.push(e.data)});")
            context.add_init_script("window.__p3input=[];for(const type of ['pointerdown','pointerup','click'])addEventListener(type,e=>window.__p3input.push({type,id:e.target.id,x:e.clientX,y:e.clientY,time:performance.now()}),true);")
            page.wait_for_selector(".session-item", timeout=120000)
            page.wait_for_load_state("domcontentloaded")
            page.locator('textarea[aria-autocomplete="list"]').wait_for(state="visible")
            page.locator(".session-item").filter(has_text="RIU P3 interoperability").click()
            expect(page.locator(".model-copy strong")).to_have_text("RIU P3 loopback", timeout=30000)
            page.on("console", lambda message: (output / "console.log").open("a", encoding="utf-8").write(message.text + "\n"))
            send_tool("official")
            target = frame("get-time")
            expect(target.locator("#server-time")).to_have_text(re.compile(r"^20\d\d-"), timeout=30000)
            official_frame = page.locator('iframe[title="get-time"]').element_handle().content_frame()
            wire = official_frame.evaluate("window.__p3wire")
            methods = [item.get("method") for item in wire if isinstance(item, dict)]
            check("official-sdk-initialize-and-notifications", methods.index("ui/notifications/tool-input") < methods.index("ui/notifications/tool-result"), methods)
            background = page.locator('iframe[title="get-time"]').evaluate("el=>getComputedStyle(el).backgroundColor")
            foreground = official_frame.evaluate("getComputedStyle(document.getElementById('server-time')).color")
            def luminance(color):
                channels = [float(value) / 255 for value in re.findall(r"[\d.]+", color)[:3]]
                linear = [value / 12.92 if value <= .04045 else ((value + .055) / 1.055) ** 2.4 for value in channels]
                return sum(value * weight for value, weight in zip(linear, (.2126, .7152, .0722)))
            light, dark = sorted((luminance(background), luminance(foreground)), reverse=True)
            contrast = (light + .05) / (dark + .05)
            check("official-transparent-canvas-text-readable", contrast >= 4.5, {"background": background, "foreground": foreground, "contrast": contrast})
            observe("official-ready")
            before = target.locator("#server-time").inner_text()
            target.locator("#get-time-btn").click(); approve()
            expect(target.locator("#server-time")).not_to_have_text(before, timeout=30000)
            check("official-unchanged-component-tool-callback", target.locator("#server-time").inner_text() != "[ERROR]")
            target.locator("#get-time-btn").click(); approve("拒绝")
            expect(target.locator("#server-time")).to_have_text("[ERROR]", timeout=30000)
            check("official-callback-denial", True)
            target.locator("#message-text").fill("RIU_P3_CAPTURE")
            target.locator("#send-message-btn").click()
            page.get_by_role("button", name="发送追问", exact=True).wait_for()
            count_before = len(ModelFixture.requests); page.wait_for_timeout(300)
            check("official-message-proposal-no-automatic-model-turn", len(ModelFixture.requests) == count_before)
            page.get_by_role("button", name="忽略建议", exact=True).click()
            observe("official-example")
            entries = list(config.project_data_dir.glob("views/*/*/*/index.html"))
            check("official-html-byte-identical", any(path.read_bytes() == original_html for path in entries), original_hash)
            card = page.locator(".interactive-view").filter(has=page.locator('iframe[title="get-time"]'))
            card.get_by_role("button", name="收起", exact=True).click()
            expect(card.locator("iframe")).to_have_count(0)
            check("official-graceful-teardown-ack", "App is being torn down" in (output / "console.log").read_text(encoding="utf-8"))

            send_tool("show")
            target = frame("show")
            expect(target.locator("#ready")).to_have_text("Ready")
            expect(target.locator("#meta")).to_contain_text(SECRET)
            check("private-meta-delivered-only-to-component", True)
            attacks = json.loads(target.locator("#attacks").inner_text())
            check("hostile-parent-preload-node-network-blocked", attacks.get("parent") == "blocked" and attacks.get("node") == "undefined" and attacks.get("preload") == "undefined" and attacks.get("fetch") == "blocked", attacks)
            target.locator("#increment").click(); approve()
            expect(target.locator("#result")).to_contain_text('"count":1')
            effects = output / "effects/effects.json"
            check("app-only-through-normal-approval-executor", json.loads(effects.read_text())["count"] == 1)
            target.locator("#duplicate").click()
            expect(target.locator("#result")).to_contain_text("duplicate")
            check("duplicate-does-not-replay-write", json.loads(effects.read_text())["count"] == 1)
            target.locator("#model-only").click()
            expect(target.locator("#result")).to_contain_text("not callable")
            check("model-only-rejected-from-app", page.get_by_role("alertdialog").count() == 0)
            target.locator("#unknown").click()
            expect(target.locator("#result")).to_contain_text('"code":-32601')
            check("unsupported-standard-method-explicit-error", True)
            target.locator("#context").click()
            expect(target.locator("#result")).to_contain_text('"result":{}')
            target.locator("#message").click()
            page.get_by_role("button", name="发送追问", exact=True).wait_for()
            before = len(ModelFixture.requests); page.wait_for_timeout(300)
            check("model-context-does-not-trigger-model", len(ModelFixture.requests) == before)
            event_offset = start_event_capture(page)
            page.get_by_role("button", name="发送追问", exact=True).click()
            for _ in range(600):
                if len(ModelFixture.requests) > before and page.locator(".live-message").count() == 0: break
                page.wait_for_timeout(50)
            page.wait_for_function("""offset=>{
                const runs=window.__qualityEvents.slice(offset).filter(x=>x.event.type==='executors.changed');
                return runs.some(x=>x.event.entries.length>0)&&runs.at(-1).event.entries.length===0;
            }""", arg=event_offset, timeout=30000)
            page.wait_for_selector(".live-message", state="detached", timeout=30000)
            check("model-context-untrusted-user-data", any("P3_CONTEXT_PUBLIC_SELECTION" in str(item.get("content")) and item.get("role") == "user" for item in ModelFixture.requests[-1]["messages"]))
            check("no-private-meta-or-app-only-descriptor-in-model", SECRET not in json.dumps(ModelFixture.requests) and "APP_ONLY_HIDDEN_DESCRIPTOR" not in json.dumps(ModelFixture.requests))
            observe("negative-boundaries")
            # The follow-up scrolls this history view offscreen. Lazy mounting
            # may create a fresh instance when we return; wait for its handshake.
            target = frame("show")
            expect(target.locator("#ready")).to_have_text("Ready", timeout=30000)
            # Wait for the remounted OOPIF's pointer hit regions after scrolling.
            actual_frame = page.locator('iframe[title="show"]').element_handle().content_frame()
            settle_view(page, actual_frame)
            report["teardown_before"] = {
                "button": target.locator("#teardown").bounding_box(),
                "window": page.evaluate("({innerWidth,innerHeight,outerWidth,outerHeight,screenWidth:screen.width,screenHeight:screen.height,devicePixelRatio})"),
                "frame": target.locator("body").evaluate("()=>({ready:document.querySelector('#ready').textContent,handler:String(document.querySelector('#teardown').onclick),time:performance.now()})"),
            }
            page.evaluate("window.__p3TeardownSeen=false;addEventListener('message',e=>{if(e.data?.method==='ui/notifications/request-teardown')window.__p3TeardownSeen=true});true")
            target.locator("#teardown").click()
            try:
                expect(page.locator('iframe[title="show"]')).to_have_count(0)
            except Exception:
                report["teardown_request_seen"] = page.evaluate("window.__p3TeardownSeen")
                report["teardown_after"] = target.locator("body").evaluate("()=>({input:window.__p3input,wire:window.__p3wire,time:performance.now()})")
                observe("teardown-failure")
                raise
            check("app-requested-teardown", True)
            for name in ("missing", "bad-mime", "wrong-uri", "network", "oversize"):
                send_tool(name)
                text = page.locator("body").inner_text()
                check(name + "-text-fallback", f"Useful text for {name}" in text and page.locator(f'iframe[title="{name}"]').count() == 0)
            send_tool("alias")
            expect(frame("alias").locator("#ready")).to_have_text("Ready")
            check("output-template-resource-alias", True)
            check("official-distribution-unmodified", hashlib.sha256((official / "mcp-app.html").read_bytes()).hexdigest() == original_hash)
            check("model-privacy-after-all-negative-fixtures", SECRET not in json.dumps(ModelFixture.requests) and "APP_ONLY_HIDDEN_DESCRIPTOR" not in json.dumps(ModelFixture.requests))
            report["passed"] = True
    except Exception as error:
        report.update(passed=False, error=repr(error))
        if page:
            try: observe("failure")
            except Exception: pass
        raise
    finally:
        (output / "model-requests.json").write_text(json.dumps(ModelFixture.requests, indent=2, ensure_ascii=False), encoding="utf-8")
        (output / "report.json").write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
        if process and process.poll() is None:
            stop_process(process)
            process.wait(timeout=15)
        model.shutdown(); log.close()
    print(str(output / "report.json"), flush=True)


if __name__ == "__main__": main()
