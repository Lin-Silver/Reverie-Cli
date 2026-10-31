"""Run RIU P4 acceptance and rendering measurements in the production Windows package.

All sessions, configuration and artifacts are synthetic and repository-local.
Rendering samples start AFTER artifact creation, never at model-request start.
"""
from __future__ import annotations

import argparse
from datetime import datetime
import hashlib
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import math
import os
from pathlib import Path
import platform
import re
import shutil
import socket
import subprocess
import sys
import threading
import time
import uuid

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "ReverieCli-py"))
from desktop_process import launch_options, packaged_kernel_path, stop_process, wait_for_packaged_page
FIXTURE = REPO / "scripts/verification/fixtures/riu-p4/view.html"


class ModelFixture(BaseHTTPRequestHandler):
    requests: list[dict] = []

    def log_message(self, *_args):
        pass

    def do_POST(self):
        payload = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        self.requests.append(payload)
        last = (payload.get("messages") or [{}])[-1]
        message, finish = {"role": "assistant", "content": "参数、筛选和比较可在本地视图中操作。"}, "stop"
        if last.get("role") == "user" and "RIU_P4_GENERATE" in str(last.get("content", "")):
            arguments = {"artifact_path": "view.html", "title": "RIU P4 参数与比较", "summary": "本地参数、图表筛选与比较卡片。"}
            revise = re.search(r"REVISE:([A-Za-z0-9_-]+)", str(last["content"]))
            if revise:
                arguments["replaces_view_id"] = revise[1]
            message = {"role": "assistant", "content": None, "tool_calls": [{"id": f"p4-{len(self.requests)}", "type": "function", "function": {"name": "render_view", "arguments": json.dumps(arguments)}}]}
            finish = "tool_calls"
        body = json.dumps({"id": "p4", "object": "chat.completion", "created": int(time.time()), "model": "riu-p4", "choices": [{"index": 0, "message": message, "finish_reason": finish}], "usage": {"prompt_tokens": 80, "completion_tokens": 20, "total_tokens": 100}}).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


def distribution(values):
    ordered = sorted(values)
    return {"n": len(values), "p50_ms": round(ordered[math.ceil(.50 * len(ordered)) - 1], 3), "p95_ms": round(ordered[math.ceil(.95 * len(ordered)) - 1], 3), "max_ms": round(ordered[-1], 3), "samples_ms": values}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--exe", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--samples", type=int, default=20)
    parser.add_argument("--trace-input", action="store_true", help="Retain a diagnostic Chromium trace of the unchanged input workload.")
    parser.add_argument("--keep-open", action="store_true", help="Leave only this isolated acceptance window open for native inspection.")
    args = parser.parse_args()
    output = args.output.resolve()
    if not output.is_relative_to(REPO):
        raise ValueError("Evidence must stay inside this repository.")
    output.mkdir(parents=True, exist_ok=False)
    workspace, app_root, desktop_home = [output / item for item in ("workspace", "app-root", "desktop-home")]
    for directory in (workspace, app_root, desktop_home):
        directory.mkdir()
    os.environ["REVERIE_APP_ROOT"] = str(app_root)
    os.environ["NO_PROXY"] = "localhost,127.0.0.1"
    from reverie.config import ConfigManager, ModelConfig
    from reverie.session.manager import SessionManager
    from reverie.views import ViewIdentity, ViewStore
    from playwright.sync_api import expect, sync_playwright

    server = ThreadingHTTPServer(("127.0.0.1", 0), ModelFixture)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    private_sentinel = "PRIVATE_UI_RUNTIME_" + uuid.uuid4().hex
    config = ConfigManager(workspace)
    config.ensure_dirs()
    cfg = config.load()
    cfg.models = [ModelConfig("riu-p4", "RIU P4 loopback", f"http://127.0.0.1:{server.server_port}/v1", "fixture-local-only")]
    cfg.active_model_index, cfg.active_model_source = 0, "standard"
    cfg.stream_responses, cfg.api_proxy = False, ""
    cfg.security = {**cfg.security, "permission_level": "full_control", "permission_mode": "default"}
    config.save(cfg)
    shutil.copyfile(FIXTURE, workspace / "view.html")
    manager = SessionManager(config.project_data_dir, project_root=workspace)
    store = ViewStore.for_project(workspace)

    def history_view(session, number):
        title = f"History {number:03} · 中文长标题与比较卡片"
        summary = "中文长摘要与空数据、上限数据验收。" * 25
        manifest = store.register(artifact_path="view.html", identity=ViewIdentity(session.id, f"turn-{number}", f"tool-{number}"), title=title, summary=summary, workspace_root=workspace)
        text = f'Interactive view ready: "{title}" (view_id={manifest.view_id}, revision=1). It is shown to the user in the Reverie view panel. Summary: {summary}'
        session.messages.extend([{"role": "assistant", "content": "", "tool_calls": [{"id": f"tool-{number}", "function": {"name": "render_view", "arguments": "{}"}}]}, {"role": "tool", "name": "render_view", "tool_call_id": f"tool-{number}", "content": text}])
        return manifest

    history = manager.create_session("RIU P4 · 100 history views")
    history_manifests = [history_view(history, index) for index in range(100)]
    manager.save_session(history)
    broken = manager.create_session("RIU P4 · missing artifact")
    broken_view = history_view(broken, 999)
    manager.save_session(broken)
    broken_entry, _ = store.resolve_entry(broken.id, broken_view.view_id, 1)
    if not broken_entry.is_relative_to(output):
        raise ValueError("Fixture artifact escaped output.")
    broken_entry.unlink()
    primary = manager.create_session("RIU P4 · acceptance")
    settings = desktop_home / ".reverie/desktop/desktop-settings.json"
    settings.parent.mkdir(parents=True)
    settings.write_text(json.dumps({"coreAppRoot": str(app_root), "projectRoot": str(workspace), "ui": {"language": "zh-CN"}}), encoding="utf-8")
    env = {**os.environ, "PORTABLE_EXECUTABLE_DIR": str(desktop_home)}
    env.pop("ELECTRON_RUN_AS_NODE", None)
    report = {"scope": "Production packaged Electron; synthetic loopback model; no external provider", "checks": [], "measurements": {}, "fixture": {"html_bytes": FIXTURE.stat().st_size, "max_data_rows": 1000, "sha256": hashlib.sha256(FIXTURE.read_bytes()).hexdigest()}, "hardware": {"platform": platform.platform(), "cpu": platform.processor(), "logical_cpus": os.cpu_count()}, "output": str(output)}
    process = browser = page = None
    log = (output / "electron.log").open("w", encoding="utf-8")

    def check(name, passed, detail=None, *, fatal=True):
        result = {"name": name, "passed": bool(passed), "detail": detail}
        report["checks"].append(result)
        print(json.dumps(result, ensure_ascii=True), flush=True)
        if not passed and fatal:
            raise AssertionError(name)

    def observe(name):
        page.screenshot(path=str(output / (name + ".png")), full_page=True)
        (output / (name + ".txt")).write_text(page.locator("body").inner_text(), encoding="utf-8")

    def frame(title="RIU P4 参数与比较"):
        handle = page.locator(f'iframe[title="{title}"]').element_handle(timeout=30000)
        result = handle.content_frame()
        result.wait_for_function("()=>window.__p4?.ready", timeout=30000)
        return result

    def send(text):
        editor = page.locator("textarea[aria-autocomplete=list]")
        editor.fill(text)
        page.get_by_role("button", name="发送", exact=True).click()
        page.get_by_role("button", name="停止", exact=True).wait_for(state="hidden", timeout=90000)

    def open_session(name):
        page.locator(".session-item").filter(has_text=name).click()
        page.locator(".session-loading").wait_for(state="hidden", timeout=60000)

    playwright = sync_playwright().start()
    try:
        if True:
            def launch():
                nonlocal process, browser, page
                with socket.socket() as sock:
                    sock.bind(("127.0.0.1", 0)); port = sock.getsockname()[1]
                process = subprocess.Popen([str(args.exe.resolve()), "--gui", "--project", str(workspace), f"--remote-debugging-port={port}"], env=env, stdout=log, stderr=log, **launch_options(visible=args.keep_open))
                browser, page = wait_for_packaged_page(playwright, process, port, attempts=120)
                page.set_viewport_size({"width": 1280, "height": 800})
                page.wait_for_selector(".session-item", timeout=120000)
                page.wait_for_load_state("domcontentloaded")
                page.locator("textarea[aria-autocomplete=list]").wait_for(state="visible", timeout=60000)
                page.evaluate("window.__p4events=[];window.reverie.onEvent(e=>window.__p4events.push({...e,host_received_at:Date.now()}));true")

            launch()
            page.set_viewport_size({"width": 1280, "height": 800})
            report["build"] = page.evaluate("window.reverie.paths()")
            open_session("RIU P4 · acceptance")
            render_times = []
            for index in range(args.samples):
                send(f"RIU_P4_GENERATE {index}")
                target = frame()
                ready = target.evaluate("window.__p4.readyEpoch")
                # The trusted event timestamp is minted after atomic persistence;
                # model generation and artifact writes are outside this interval.
                key = page.locator('iframe[title="RIU P4 参数与比较"]').evaluate("e=>e.closest('.interactive-view-anchor').dataset.viewKey")
                view_id = re.search(r":(v[0-9a-f]+):\d+$", key)[1]
                _, manifest = store.resolve_entry(primary.id, view_id)
                events = page.evaluate("window.__p4events")
                (output / "generation-events.json").write_text(json.dumps(events, ensure_ascii=False, indent=2), encoding="utf-8")
                def commit_stamp(value):
                    if isinstance(value, dict):
                        if value.get("view_id") == view_id and value.get("committed_at"):
                            return value["committed_at"]
                        for child in value.values():
                            found = commit_stamp(child)
                            if found: return found
                    return None
                stamps = [value for event in events if (value := commit_stamp(event))]
                if not stamps:
                    raise AssertionError("Missing trusted post-commit timestamp; cannot label creation/model time as render latency.")
                render_times.append(ready - datetime.fromisoformat(stamps[-1]).timestamp() * 1000)
                report["measurements"].setdefault("artifact_creation_to_commit_ms", []).append((datetime.fromisoformat(stamps[-1]) - datetime.fromisoformat(manifest.created_at)).total_seconds() * 1000)
                report["measurements"].setdefault("render_phases", []).append(page.evaluate("prefix=>performance.getEntriesByType('mark').filter(e=>e.name.startsWith(prefix)).map(e=>({phase:e.name.split(':').pop(),epoch:performance.timeOrigin+e.startTime}))", f"riu-view:{primary.id}:{view_id}:1"))
                if index < args.samples - 1:
                    # Collapse old views to keep sampling one active instance.
                    page.locator(".interactive-view").filter(has=page.locator('iframe[title="RIU P4 参数与比较"]')).get_by_role("button", name="收起", exact=True).click()
            report["measurements"]["registration_to_interactive_upper_bound"] = distribution(render_times)
            check("artifact-registration-to-interactive-p95-under-1s", 0 <= report["measurements"]["registration_to_interactive_upper_bound"]["p95_ms"] <= 1000, report["measurements"]["registration_to_interactive_upper_bound"], fatal=False)

            target = frame()
            target.evaluate("value=>window.__p4.privateSentinel=value", private_sentinel)
            surface = page.locator(".interactive-view").filter(has=page.locator('iframe[title="RIU P4 参数与比较"]'))
            identity = target.evaluate("window.__p4.instance")
            buttons = surface.locator("[data-view-mode]").evaluate_all("els=>els.map(e=>({label:e.getAttribute('aria-label'),height:e.getBoundingClientRect().height}))")
            check("display-mode-buttons-at-least-32px", all(button["height"] >= 32 for button in buttons), buttons)
            target.locator("#filter").fill("Row 1")
            target.locator("#size").select_option("1000")
            target.locator(".scroll").evaluate("e=>e.scrollTop=80")
            expected_scroll = target.locator(".scroll").evaluate("e=>e.scrollTop")
            target.locator("#rate").focus(); target.locator("#rate").press("ArrowRight")
            expected_rate = target.locator("#rate").input_value()
            target.locator("#layout").select_option("carousel")
            target.locator("#save").click()
            expect(target.locator("#saved")).to_contain_text("Saved")
            for mode in ("fullscreen", "pip", "inline"):
                surface.locator(f'[data-view-mode="{mode}"]').click()
                expect(surface).to_have_attribute("data-display-mode", mode)
                current = frame()
                check("same-js-document-" + mode, current.evaluate("window.__p4.instance") == identity and current.locator("#filter").input_value() == "Row 1" and current.locator("#rate").input_value() == expected_rate and current.locator(".scroll").evaluate("e=>e.scrollTop") == expected_scroll)
                observe(mode)
            check("card-carousel-is-content-layout", target.locator("#cards").get_attribute("class") == "cards carousel")
            bad = target.evaluate("window.__p4.rpc('ui/request-display-mode',{mode:'carousel'}).catch(e=>e)")
            check("invalid-display-mode-explicit-error", bad.get("code") == -32602, bad)
            target.evaluate("window.__p4.rpc('ui/request-display-mode',{mode:'pip'})")
            expect(surface).to_have_attribute("data-display-mode", "pip")
            target.locator("#filter").focus(); target.locator("#filter").press("Escape")
            expect(surface).to_have_attribute("data-display-mode", "inline")
            check("iframe-escape-returns-host-focus", page.evaluate("document.activeElement?.dataset.viewMode") == "fullscreen")
            surface.locator('[data-view-mode="fullscreen"]').focus()
            page.keyboard.press("Enter")
            expect(surface).to_have_attribute("data-display-mode", "fullscreen")
            page.keyboard.press("Escape")
            expect(surface).to_have_attribute("data-display-mode", "inline")
            check("tab-enter-escape-host-navigation", page.evaluate("document.activeElement?.dataset.viewMode") == "fullscreen")

            for theme in ("light", "dark"):
                page.evaluate("theme=>window.reverie.setAppearance(theme)", theme)
                target.wait_for_function("theme=>document.documentElement.dataset.theme===theme", arg=theme)
                colors = target.evaluate("({bg:getComputedStyle(document.body).backgroundColor,fg:getComputedStyle(document.body).color})")
                def luminance(color):
                    channels = [float(item) / 255 for item in re.findall(r"[\d.]+", color)[:3]]
                    return sum((value / 12.92 if value <= .04045 else ((value + .055) / 1.055) ** 2.4) * weight for value, weight in zip(channels, (.2126, .7152, .0722)))
                light, dark = sorted((luminance(colors["bg"]), luminance(colors["fg"])), reverse=True)
                contrast = (light + .05) / (dark + .05)
                check("theme-AA-" + theme, contrast >= 4.5 and target.evaluate("window.__p4.instance") == identity, {**colors, "contrast": contrast})
                observe(theme)
            page.evaluate("window.reverie.setUiPreferences({language:'en-US'})")
            target.wait_for_function("()=>document.documentElement.lang==='en-US'")
            check("live-language-without-reload", target.locator("#heading").inner_text() == "Parameters & comparisons" and target.evaluate("window.__p4.instance") == identity)
            page.emulate_media(reduced_motion="reduce")
            target.wait_for_function("()=>document.documentElement.dataset.reducedMotion==='true'")
            check("reduced-motion-context-and-css", target.locator(".pulse").evaluate("e=>getComputedStyle(e).animationName") == "none")
            page.evaluate("window.reverie.setUiPreferences({language:'zh-CN'})")
            target.wait_for_function("()=>document.documentElement.lang==='zh-CN'")

            page.set_viewport_size({"width": 1080, "height": 700})
            surface.locator('[data-view-mode="fullscreen"]').click()
            check("1080x700-composer-visible", page.locator("textarea[aria-autocomplete=list]").evaluate("e=>{const r=e.getBoundingClientRect();return !!document.elementFromPoint(r.left+10,r.top+10)?.closest('.composer')}"))
            check("1080x700-no-horizontal-overflow", page.evaluate("document.documentElement.scrollWidth<=innerWidth"))
            observe("narrow")
            surface.locator('[data-view-mode="inline"]').click()
            target.locator("#filter").fill("")
            target.locator("#size").select_option("0")
            expect(target.locator("#empty")).to_be_visible()
            check("empty-data-text-equivalent", True)
            target.locator("#size").select_option("1000")
            expect(target.locator("#rows tr")).to_have_count(1000)
            target.locator("#error-button").click()
            expect(target.locator("#error")).to_be_visible()
            target.locator("#filter").fill("Row")
            expect(target.locator("#error")).to_be_hidden()
            check("upper-bound-data-and-recoverable-error", True)
            trace = page.context.new_cdp_session(page) if args.trace_input else None
            trace_complete, trace_events = [], []
            if trace:
                trace.on("Tracing.dataCollected", lambda event: trace_events.extend(event["value"]))
                trace.on("Tracing.tracingComplete", lambda event: trace_complete.append(event))
                trace.send("Tracing.start", {"traceConfig": {"includedCategories": ["devtools.timeline", "blink.user_timing", "v8", "cc"]}})
            samples = [target.evaluate("value=>window.__p4.measureInput(value)", 1 + index % 99) for index in range(60)]
            if trace:
                trace.send("Tracing.end")
                deadline = time.monotonic() + 30
                while not trace_complete and time.monotonic() < deadline:
                    page.wait_for_timeout(50)
                if not trace_complete:
                    raise TimeoutError("Input diagnostic trace did not finish")
                (output / "input-trace.json").write_text(json.dumps({"traceEvents": trace_events, "completion": trace_complete}), encoding="utf-8")
                trace.detach()
            report["measurements"]["local_input_to_two_animation_frames_1000_rows"] = distribution(samples)
            check("local-input-p95-under-100ms", report["measurements"]["local_input_to_two_animation_frames_1000_rows"]["p95_ms"] <= 100, report["measurements"]["local_input_to_two_animation_frames_1000_rows"], fatal=False)

            # Restore saved private UI state and a pinned display preference.
            target.locator("#filter").fill("Row 1")
            target.locator("#save").click(); expect(target.locator("#saved")).to_contain_text("Saved 2")
            surface.locator('[data-view-mode="pip"]').click()
            page.reload(wait_until="domcontentloaded")
            page.locator('textarea[aria-autocomplete="list"]').wait_for(state="visible")
            target = frame()
            expect(page.locator('.view-pip-slot iframe')).to_have_count(1)
            check("refresh-restores-display-and-private-state", target.locator("#filter").input_value() == "Row 1" and target.evaluate("window.__p4.instance") != identity)
            # Actual process restart, not only renderer reload.
            browser.close(); browser = None
            stop_process(process)
            process.wait(timeout=20); process = None
            launch(); target = frame()
            check("process-restart-restores-view-and-private-state", target.locator("#filter").input_value() == "Row 1" and page.locator('.view-pip-slot iframe').count() == 1)
            send(f"RIU_P4_GENERATE REVISE:{view_id}")
            target = frame()
            _, revised = store.resolve_entry(primary.id, view_id, 2)
            check("followup-produces-traceable-new-revision", revised.revision == 2 and store.manifest(primary.id, view_id, 1).revision == 1 and page.locator('iframe[title="RIU P4 参数与比较"]').count() == 1)
            check("revision-state-isolated", target.locator("#filter").input_value() == "" and store.read_state(primary.id, view_id, 1)["state"]["filter"] == "Row 1")
            open_session("RIU P4 · missing artifact")
            expect(page.locator(".interactive-view-error")).to_be_visible(timeout=30000)
            check("missing-file-retains-summary-and-retry", page.locator(".interactive-view-summary").count() == 1)
            broken_entry.write_bytes(FIXTURE.read_bytes())
            page.get_by_role("button", name="重试加载视图").click()
            frame(broken_view.title)
            check("missing-file-retry-recovers", True)

            history_start = time.perf_counter()
            open_session("RIU P4 · 100 history views")
            page.locator(".transcript").evaluate("e=>e.scrollTop=e.scrollHeight")
            frame(history_manifests[-1].title)
            check("latest-history-view-stays-visible-after-lazy-load", page.locator(f'iframe[title="{history_manifests[-1].title}"]').evaluate("e=>{const r=e.getBoundingClientRect(),v=document.querySelector('.transcript').getBoundingClientRect();return r.top<v.bottom&&r.bottom>v.top}"))
            initial_history_ms = (time.perf_counter() - history_start) * 1000
            frame_counts = [page.locator("iframe.interactive-view-frame").count()]
            earlier = []
            for _ in range(5):
                button = page.locator(".history-load-earlier")
                if not button.count(): break
                start = time.perf_counter(); button.click()
                page.evaluate("()=>new Promise(r=>requestAnimationFrame(()=>requestAnimationFrame(r)))")
                earlier.append((time.perf_counter() - start) * 1000)
                frame_counts.append(page.locator("iframe.interactive-view-frame").count())
            check("100-history-views-lazily-mounted", max(frame_counts) <= 4 and page.locator(".interactive-view-anchor").count() == 100, {"frame_counts": frame_counts, "total_view_rows": page.locator(".interactive-view-anchor").count()})
            report["measurements"]["history"] = {"view_count": 100, "message_count": 200, "first_session_load_to_interactive_ms": initial_history_ms, "earlier_page_load_ms": earlier, "mounted_frames": frame_counts}
            observe("history")
            first_history = page.locator(".interactive-view").first
            first_history.scroll_into_view_if_needed()
            first_frame = first_history.locator("iframe")
            first_frame.wait_for(timeout=30000)
            first_document = first_frame.element_handle().content_frame()
            first_document.wait_for_function("()=>window.__p4?.ready", timeout=30000)
            first_identity = first_document.evaluate("window.__p4.instance")
            summary = first_history.locator(".interactive-view-summary")
            collapsed = summary.evaluate("e=>e.getBoundingClientRect().height")
            text_metrics = summary.locator("p").evaluate("e=>({height:e.getBoundingClientRect().height,lineHeight:parseFloat(getComputedStyle(e).lineHeight)})")
            first_history.get_by_role("button", name="展开摘要", exact=True).click()
            expanded = summary.evaluate("e=>e.getBoundingClientRect().height")
            same_document = first_document.evaluate("window.__p4.instance") == first_identity
            check("long-summary-expands-without-reloading-view", text_metrics["height"] <= text_metrics["lineHeight"] * 3 + 1 and expanded > collapsed and same_document, {"collapsed_height": collapsed, "expanded_height": expanded, "text": text_metrics, "same_document": same_document})
            first_history.get_by_role("button", name="收起摘要", exact=True).click()
            observe("history-summary-collapsed")
            before_requests = len(ModelFixture.requests)
            open_session("RIU P4 · acceptance")
            target = frame()
            surface = page.locator(".interactive-view").filter(has=page.locator('iframe[title="RIU P4 参数与比较"]'))
            old_url = page.locator('iframe[title="RIU P4 参数与比较"]').get_attribute("src")
            surface.get_by_role("button", name="收起", exact=True).click()
            expect(page.locator('iframe[title="RIU P4 参数与比较"]')).to_have_count(0)
            # A closed token cannot load another document. Do not weaken the
            # trusted host's connect-src policy just to fetch the custom scheme.
            page.evaluate("url=>{const probe=document.createElement('iframe');probe.id='revoked-probe';probe.sandbox='allow-scripts';probe.src=url;document.body.append(probe)}", old_url)
            page.wait_for_timeout(500)
            stale = page.locator("#revoked-probe").element_handle().content_frame()
            rejected = stale.url in {"", "about:blank"} or "View token is not bound" in stale.locator("body").inner_text()
            check("close-releases-frame-and-resource-token", rejected, {"new_frame_url": stale.url})
            page.locator("#revoked-probe").evaluate("e=>e.remove()")
            send("RIU_P4 ordinary text after closing")
            check("closed-view-does-not-stop-chat", len(ModelFixture.requests) > before_requests)
            captured = json.dumps(ModelFixture.requests, ensure_ascii=False)
            followup = json.dumps(ModelFixture.requests[-1], ensure_ascii=False)
            complete_html = FIXTURE.read_text(encoding="utf-8")
            full_html_requests = [index for index, payload in enumerate(ModelFixture.requests) if any(complete_html in str(message.get("content", "")) for message in payload.get("messages", []))]
            source_evidence = [index for index, payload in enumerate(ModelFixture.requests) if "RIU_P4_PRIVATE_HTML" in json.dumps(payload)]
            report["source_retrieval"] = {"fixture_source_evidence_request_indices": source_evidence, "full_html_request_indices": full_html_requests, "note": "Initial generation and explicit revisions may retrieve original workspace source snippets through FastContext. This is distinct from reattaching a registered artifact or private runtime state."}
            check("private-ui-state-and-html-not-in-followups", private_sentinel not in captured and "RIU_P4_PRIVATE_HTML" not in followup and not full_html_requests)
            # Exercise the shipped plain-text client, not a renderer mock.
            cli = subprocess.run([str(packaged_kernel_path(args.exe)), str(workspace), "--no-index", "--prompt", "RIU_P4_GENERATE plain text client", "--report-file", str(output / "plain-client.json")], env=env, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=120, creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
            (output / "plain-client.txt").write_text(cli.stdout + cli.stderr, encoding="utf-8")
            plain = json.loads((output / "plain-client.json").read_text(encoding="utf-8")) if (output / "plain-client.json").is_file() else {}
            plain_serialized = json.dumps(plain, ensure_ascii=False)
            check("packaged-plain-client-summary-fallback", cli.returncode == 0 and "Interactive view ready" in plain_serialized and "Summary:" in plain_serialized and "RIU_P4_PRIVATE_HTML" not in plain_serialized, {"exit_code": cli.returncode})
            report["measurements"]["method"] = "Nearest-rank quantiles. Commit-to-ready starts at the trusted view_ready.committed_at timestamp after atomic persistence. HTML/model generation and artifact persistence are excluded and recorded separately. Input samples measure local input dispatch, rendering and two requestAnimationFrame callbacks, excluding CDP roundtrip and all model wait; not physical display/photon latency. History includes core I/O and host render; no model request."
            report["passed"] = all(item["passed"] for item in report["checks"])
            if args.keep_open:
                page.locator(f'.interactive-view-anchor[data-view-key$=":{view_id}:2"]').get_by_role("button", name="展开", exact=True).click()
                frame(); observe("native-inspection")
                report["native_inspection"] = {"pid": process.pid, "title": "Reverie", "workspace": str(workspace)}
    except Exception as error:
        report["passed"], report["error"] = False, repr(error)
        if page:
            try: observe("failure")
            except Exception: pass
        raise
    finally:
        if page:
            try: (output / "events.json").write_text(json.dumps(page.evaluate("window.__p4events"), ensure_ascii=False, indent=2), encoding="utf-8")
            except Exception: pass
        (output / "report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        (output / "model-requests.json").write_text(json.dumps(ModelFixture.requests, ensure_ascii=False, indent=2), encoding="utf-8")
        if not args.keep_open or not report.get("passed"):
            if browser:
                try: browser.close()
                except Exception: pass
            if process and process.poll() is None:
                stop_process(process)
        server.shutdown(); log.close()
        playwright.stop()
    if not report.get("passed"):
        raise SystemExit(1)


if __name__ == "__main__":
    main()
