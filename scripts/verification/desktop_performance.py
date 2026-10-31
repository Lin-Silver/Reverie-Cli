"""Measure a real Desktop window with synthetic history and an OpenAI SSE fixture.

Frame intervals describe rAF scheduling in this environment, not physical display
or GPU FPS. Input timings include two animation frames, excluding CDP roundtrip.
No model-quality samples, approvals, or product security settings are changed.
Passive heap, visibility and long-animation-frame records aid diagnosis; these
records do not identify GC by themselves and do not change acceptance budgets.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import math
import os
from pathlib import Path
import socket
import subprocess
import sys
import threading
import time

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "ReverieCli-py"))
from desktop_process import launch_options, stop_process, wait_for_packaged_page


def summary(values):
    ordered = sorted(values)
    if not ordered:
        return {"n": 0}
    return {"n": len(values), "p50_ms": round(ordered[math.ceil(len(values) * .5) - 1], 3),
            "p95_ms": round(ordered[math.ceil(len(values) * .95) - 1], 3),
            "max_ms": round(ordered[-1], 3), "samples_ms": values}


def rich_answer(index):
    blocks = [
        {"type": "metrics", "items": [{"label": name, "value": str(n)} for name, n in
                                        [("待处理", 6), ("进行中", 3), ("已完成", 2), ("暂停", 1)]]},
        {"type": "table", "title": "项目总览", "columns": ["项目", "状态", "下一步"],
         "rows": [[f"项目 {index}-{i}", {"text": "进行中", "tone": "info"}, "检查中文排版和响应"]
                  for i in range(8)]},
    ]
    return f"## 第 {index} 轮状态\n\n" + ("中文正文、**加粗**、`代码`和[来源](https://example.com/)。\n\n" * 4) + "\n\n".join(
        "```reverie-ui\n" + json.dumps(block, ensure_ascii=False) + "\n```" for block in blocks)


class StreamFixture(BaseHTTPRequestHandler):
    requests = []

    def log_message(self, *_args):
        pass

    def do_POST(self):
        payload = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        type(self).requests.append(payload)
        answer = "\n\n".join(rich_answer(index) for index in range(18)) + "\n\nPERF_STREAM_COMPLETE"
        if not payload.get("stream"):
            body = json.dumps({"id": "perf", "object": "chat.completion", "model": "perf-fixture",
                               "choices": [{"index": 0, "message": {"role": "assistant", "content": answer},
                                            "finish_reason": "stop"}]}).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.send_header("Cache-Control", "no-cache")
        self.end_headers()
        try:
            for offset in range(0, len(answer), 120):
                event = {"id": "perf", "object": "chat.completion.chunk", "created": int(time.time()),
                         "model": "perf-fixture", "choices": [{"index": 0,
                         "delta": {"content": answer[offset:offset + 120]}, "finish_reason": None}]}
                self.wfile.write(("data: " + json.dumps(event, ensure_ascii=False) + "\n\n").encode())
                self.wfile.flush()
                time.sleep(.035)
            self.wfile.write(b'data: {"id":"perf","choices":[{"index":0,"delta":{},"finish_reason":"stop"}]}\n\ndata: [DONE]\n\n')
            self.wfile.flush()
        except (BrokenPipeError, ConnectionResetError):
            pass


MONITOR = """() => {
  const environment = () => ({visibility:document.visibilityState, focused:document.hasFocus()});
  const loafSupported = PerformanceObserver.supportedEntryTypes?.includes('long-animation-frame') ?? false;
  window.__perf = {frames: [], longTasks: [], inputs: [], longAnimationFrames: [], loafSupported,
    environment: {before:environment()}};
  let previous = performance.now();
  let active = true;
  const tick = now => { if (!active) return; window.__perf.frames.push(now - previous); previous = now; requestAnimationFrame(tick); };
  requestAnimationFrame(tick);
  const tasks = entries => window.__perf.longTasks.push(...entries.map(e => ({at:e.startTime,ms:e.duration})));
  const observer = new PerformanceObserver(list => tasks(list.getEntries()));
  observer.observe({type:'longtask',buffered:false});
  const animationFrames = entries => window.__perf.longAnimationFrames.push(...entries.map(e => ({
    at:e.startTime, ms:e.duration, blocking_ms:e.blockingDuration, render_start:e.renderStart,
    style_layout_start:e.styleAndLayoutStart, first_ui_event:e.firstUIEventTimestamp,
    script_count:e.scripts.length,
    script_total_ms:e.scripts.reduce((total, script) => total + script.duration, 0),
    forced_style_layout_ms:e.scripts.reduce((total, script) => total + script.forcedStyleAndLayoutDuration, 0)
  })));
  const animationObserver = loafSupported ? new PerformanceObserver(list => animationFrames(list.getEntries())) : null;
  animationObserver?.observe({type:'long-animation-frame',buffered:false});
  const input = e => {
    if (!e.target.matches('.composer textarea')) return;
    const start = performance.now();
    requestAnimationFrame(() => requestAnimationFrame(() => window.__perf.inputs.push(performance.now() - start)));
  };
  document.addEventListener('input', input, true);
  window.__stopPerf = () => {
    active = false;
    tasks(observer.takeRecords()); observer.disconnect();
    if (animationObserver) { animationFrames(animationObserver.takeRecords()); animationObserver.disconnect(); }
    document.removeEventListener('input',input,true);
    window.__perf.environment.after = environment();
    return window.__perf;
  };
}"""


def measure(page, seconds, *, scrolling=False, typing=False):
    profiler = page.context.new_cdp_session(page)
    profiler.send('Performance.enable')
    before = {v['name']: v['value'] for v in profiler.send('Performance.getMetrics')['metrics']}
    page.evaluate(MONITOR)
    if scrolling:
        page.evaluate("""() => { const box=document.querySelector('.transcript'); let t=0;
          window.__scrollPerf=setInterval(()=>{t+=.06;box.scrollTop=160+(box.scrollHeight-box.clientHeight-320)*(.5+.45*Math.sin(t));},16); }""")
    if typing:
        # Playwright dispatches actual keyboard input. Browser timestamps exclude its transport wait.
        page.locator('.composer textarea').press_sequentially("中文界面 response latency " * 3, delay=35)
    page.wait_for_timeout(seconds * 1000)
    page.evaluate("clearInterval(window.__scrollPerf)")
    data = page.evaluate("window.__stopPerf()")
    frames = data["frames"][2:]  # Exclude observer startup only; all active stalls remain.
    data["frame_intervals"] = summary(frames)
    data["raf_frames_per_second"] = round(1000 * len(frames) / sum(frames), 2) if frames else 0
    data["frames_over_33ms"] = sum(v > 33.5 for v in frames)
    data["frames_over_50ms"] = sum(v > 50 for v in frames)
    data["input_to_two_frames"] = summary(data.pop("inputs"))
    data.pop("frames")
    data["long_task_total_ms"] = round(sum(v["ms"] for v in data["longTasks"]), 2)
    after = {v['name']: v['value'] for v in profiler.send('Performance.getMetrics')['metrics']}
    data['js_heap_bytes'] = {
        'before': int(before['JSHeapUsedSize']) if 'JSHeapUsedSize' in before else None,
        'after': int(after['JSHeapUsedSize']) if 'JSHeapUsedSize' in after else None,
    }
    animation_frames = data.pop('longAnimationFrames')
    data['long_animation_frames'] = {
        'supported': data.pop('loafSupported'), 'count': len(animation_frames),
        'max_ms': round(max((v['ms'] for v in animation_frames), default=0), 3),
        'entries': animation_frames,
    }
    data['cpu_seconds'] = {key: round(after.get(key, 0) - before.get(key, 0), 4)
                           for key in ['LayoutDuration', 'RecalcStyleDuration', 'ScriptDuration', 'TaskDuration']}
    profiler.detach()
    return data


def resource_snapshot():
    """Optional Linux cgroup evidence, without changing limits or scoring."""
    values = {}
    for name in ('cpu.max', 'memory.max', 'memory.current', 'memory.events'):
        try:
            values[name] = (Path('/sys/fs/cgroup') / name).read_text().strip()
        except OSError:
            values[name] = None
    return values


def main():
    from playwright.sync_api import sync_playwright
    from reverie.config import ConfigManager, ModelConfig
    from reverie.session.manager import SessionManager

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--exe", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--seconds", type=float, default=8)
    parser.add_argument("--theme", choices=("light", "dark"), default="light")
    parser.add_argument("--width", type=int, default=1480)
    parser.add_argument("--history-pages", type=int, default=1, help="Additional 60-message pages to materialise (1–19)")
    parser.add_argument("--experiment-css", type=Path, help="Explicit local .runtime-only CSS experiment; never packaged acceptance")
    args = parser.parse_args()
    if args.experiment_css and not args.experiment_css.resolve().is_relative_to(ROOT / '.runtime'):
        parser.error('Experimental CSS must be an explicit file under .runtime')
    output = args.output.resolve()
    if not output.is_relative_to(ROOT / ".runtime") or args.seconds < 3 or not 360 <= args.width <= 2000 or not 1 <= args.history_pages <= 19:
        parser.error("Use a fresh .runtime output, --seconds >= 3 and width 360–2000")
    output.mkdir(parents=True, exist_ok=False)
    workspace, app_root, home = [output / name for name in ("workspace", "app-root", "desktop-home")]
    for directory in (workspace, app_root, home):
        directory.mkdir()
    os.environ["REVERIE_APP_ROOT"] = str(app_root)
    os.environ["NO_PROXY"] = os.environ["no_proxy"] = "127.0.0.1,localhost"
    server = ThreadingHTTPServer(("127.0.0.1", 0), StreamFixture)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    config = ConfigManager(workspace)
    config.ensure_dirs()
    cfg = config.load()
    cfg.models = [ModelConfig("perf-fixture", "Synthetic performance fixture", f"http://127.0.0.1:{server.server_port}/v1", "")]
    cfg.active_model_source, cfg.active_model_index = "standard", 0
    cfg.stream_responses, cfg.api_proxy = True, ""
    config.save(cfg)
    sessions = SessionManager(config.project_data_dir, project_root=workspace)
    for name, count in [("Performance small", 2), ("Performance long 1200", 1200)]:
        session = sessions.create_session(name)
        session.messages = [{"role": "assistant" if i % 2 else "user",
                             "content": rich_answer(i) if i % 2 else f"请检查第 {i} 个项目"} for i in range(count)]
        sessions.save_session(session)
    settings = home / ".reverie/desktop/desktop-settings.json"
    settings.parent.mkdir(parents=True)
    settings.write_text(json.dumps({"coreAppRoot": str(app_root), "projectRoot": str(workspace), "theme": args.theme,
                                   "ui": {"language": "zh-CN", "backgroundPreset": "none"}}))
    env = {**os.environ, "HOME": str(home), "XDG_CONFIG_HOME": str(home / ".config"), "PORTABLE_EXECUTABLE_DIR": str(home)}
    env.pop("ELECTRON_RUN_AS_NODE", None)
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
    report = {"schema": "reverie.desktop.performance.v1", "started_at": datetime.now(timezone.utc).isoformat(),
              "exe": str(args.exe.resolve()), "exe_sha256": hashlib.sha256(args.exe.read_bytes()).hexdigest(),
              "display": os.environ.get("DISPLAY", ""), "formal_model_quality_samples": 0,
              "theme": args.theme, "viewport_width": args.width, "additional_history_pages": args.history_pages,
              "experimental_css": str(args.experiment_css.resolve()) if args.experiment_css else None,
              "method": __doc__, "checks": [], "scenarios": {}, "switches": [], "browser_errors": [],
              "resource_limits_before": resource_snapshot()}
    app = browser = None

    def check(name, passed, detail=None):
        report["checks"].append({"name": name, "passed": bool(passed), "detail": detail})

    try:
        with (output / "desktop.log").open("x") as log, sync_playwright() as pw:
            app = subprocess.Popen([str(args.exe.resolve()), "--gui", "--project", str(workspace),
                                    f"--remote-debugging-port={port}"], env=env, stdout=log, stderr=log, **launch_options())
            browser, page = wait_for_packaged_page(pw, app, port)
            page.on("pageerror", lambda error: report["browser_errors"].append(str(error)))
            page.wait_for_selector(".composer textarea", timeout=90000)
            page.set_viewport_size({"width": args.width, "height": 960})
            page.wait_for_function("theme=>document.documentElement.dataset.theme===theme", arg=args.theme)
            if args.experiment_css:
                css = args.experiment_css.read_text()
                report['experimental_css_sha256'] = hashlib.sha256(css.encode()).hexdigest()
                page.add_style_tag(content=css)
            report['viewport'] = page.evaluate('({width:innerWidth,height:innerHeight,theme:document.documentElement.dataset.theme})')
            asar = args.exe.resolve().parent / 'resources/app.asar'
            if asar.is_file():
                report['asar_sha256'] = hashlib.sha256(asar.read_bytes()).hexdigest()
            cdp = browser.new_browser_cdp_session()
            report["system_info"] = cdp.send("SystemInfo.getInfo")
            cdp.detach()
            page.wait_for_timeout(1000)
            for name in ["Performance small", "Performance long 1200", "Performance small", "Performance long 1200"]:
                start = time.perf_counter()
                item = page.locator(".session-item").filter(has_text=name).first
                if not item.is_visible():
                    page.get_by_role('button', name='展开左侧栏 (Ctrl+B)', exact=True).click()
                    item.wait_for(state='visible')
                item.click()
                page.wait_for_function("name=>document.querySelector('.conversation-header')?.innerText.includes(name)&&document.querySelector('.transcript')?.getAttribute('aria-busy')==='false'", arg=name)
                if args.width < 850 and page.locator('.sidebar').is_visible():
                    page.get_by_role('button', name='收起左侧栏', exact=True).click()
                    item.wait_for(state='hidden')
                page.evaluate("()=>new Promise(r=>requestAnimationFrame(()=>requestAnimationFrame(r)))")
                report["switches"].append({"session": name, "ms": round((time.perf_counter() - start) * 1000, 2),
                                           "messages_in_dom": page.locator(".message").count()})
            check("initial_history_dom_bounded", page.locator(".message").count() <= 60)
            check("viewport_containment", page.evaluate('document.documentElement.scrollWidth<=innerWidth+1'))
            metrics = page.context.new_cdp_session(page)
            report['initial_dom'] = metrics.send('Memory.getDOMCounters')
            for label, scrolling, typing in [("long_idle", False, False), ("long_scroll", True, False),
                                              ("long_typing", False, True)]:
                report["scenarios"][label] = measure(page, args.seconds, scrolling=scrolling, typing=typing)
            page.locator('.composer textarea').fill('')
            # Load another history page and verify the previously visible row keeps its position.
            for index in range(args.history_pages):
                page.evaluate("document.querySelector('.transcript').scrollTop=160")
                old_rows = page.locator('.message').count()
                anchor = page.locator('.message').first
                before = anchor.bounding_box()["y"]
                text = anchor.inner_text()
                # Playwright.click scrolls the offscreen button into view first,
                # changing the anchor before the app receives its click. Activate
                # directly so this check measures the app's own prepend behavior.
                page.locator('.history-load-earlier').evaluate('button=>button.click()')
                page.wait_for_function("n=>document.querySelectorAll('.message').length>n", arg=old_rows)
                after = page.locator('.message').nth(page.locator('.message').count() - old_rows).bounding_box()["y"]
                check(f"history_anchor_preserved_{index + 1}", abs(after - before) <= 3, {"shift_px": after - before, "text": text})
            report['expanded_dom'] = metrics.send('Memory.getDOMCounters')
            report['messages_in_dom_after_history'] = page.locator('.message').count()
            expected_history = min(1200, 60 * (args.history_pages + 1))
            check('all_requested_history_loaded', report['messages_in_dom_after_history'] == expected_history)
            history_nodes = [page.locator('.message').nth(index).element_handle()
                             for index in (0, expected_history // 2, expected_history - 1)]
            report["scenarios"]["expanded_scroll"] = measure(page, args.seconds, scrolling=True)
            page.locator('.composer textarea').fill('只根据给出的数字做静态展示：待处理6、进行中3、已完成2、暂停1，列出项目总览表。')
            page.get_by_role('button', name='发送', exact=True).click()
            page.wait_for_selector('.live-message', timeout=15000)
            live_node = page.locator('.live-message').element_handle()
            report['live_message_in_history_slot'] = live_node.evaluate('element => Boolean(element.closest(".history-render-chunk"))')
            report["scenarios"]["streaming_typing"] = measure(page, args.seconds, typing=True)
            page.wait_for_function("document.querySelector('.transcript')?.textContent.includes('PERF_STREAM_COMPLETE')", timeout=60000)
            page.wait_for_selector('.stop-button', state='hidden', timeout=30000)
            page.wait_for_timeout(400)
            check("stream_completed", 'PERF_STREAM_COMPLETE' in page.locator('.transcript').inner_text())
            check('loaded_history_nodes_retained', all(node.evaluate('element => element.isConnected && Boolean(element.closest(".transcript"))') for node in history_nodes))
            if report['live_message_in_history_slot']:
                check('completed_stream_node_retained', live_node.evaluate('element => element.isConnected && Boolean(element.closest(".transcript"))'))
            check("fixture_requests_bounded", len(StreamFixture.requests) == 1, len(StreamFixture.requests))
            editor = page.locator('.composer textarea')
            draft = editor.input_value()
            editor.fill('中文草稿')
            page.evaluate('() => new Promise(resolve => requestAnimationFrame(() => requestAnimationFrame(resolve)))')
            short_height = editor.bounding_box()['height']
            editor.fill(('中文换行草稿 ' * 20 + '\n') * 12)
            page.evaluate('() => new Promise(resolve => requestAnimationFrame(() => requestAnimationFrame(resolve)))')
            long_height = editor.bounding_box()['height']
            editor.fill('中文草稿')
            page.evaluate('() => new Promise(resolve => requestAnimationFrame(() => requestAnimationFrame(resolve)))')
            restored_height = editor.bounding_box()['height']
            check('composer_grows_and_shrinks', short_height + 10 <= long_height <= 221 and abs(short_height - restored_height) <= 1,
                  {'short_px': short_height, 'long_px': long_height, 'restored_px': restored_height})
            editor.fill(draft)
            # Exercise real wrapping changes after the measured workload. Every
            # loaded node must remain present, with no clipped or estimated
            # chunk heights when the viewport changes and then returns.
            responsive_chunks = []
            for width in [460 if args.width > 700 else 1480, args.width]:
                page.set_viewport_size({'width': width, 'height': 900})
                page.wait_for_timeout(200)
                responsive_chunks.append(page.evaluate('''() => {
                  const chunks = [...document.querySelectorAll('.history-render-chunk.is-static')];
                  return {width:innerWidth, messages:document.querySelectorAll('.message').length,
                    chunks:chunks.length, invalid:chunks.flatMap((box,index) => {
                      const outer=box.getBoundingClientRect().height;
                      const inner=box.querySelector('.history-chunk-content')?.getBoundingClientRect().height;
                      return inner > 0 && Math.abs(outer-inner) <= 1 ? [] : [{index,outer,inner}];
                    })};
                }'''))
            check('history_chunks_track_responsive_content', all(
                item['chunks'] > 0 and item['messages'] >= expected_history and not item['invalid']
                for item in responsive_chunks), responsive_chunks)
            page.screenshot(path=str(output / 'desktop.png'))
            report['requests'] = [{"stream": p.get('stream'), "tools": len(p.get('tools', []))} for p in StreamFixture.requests]
            check('no_browser_errors', not report['browser_errors'], report['browser_errors'])
            for label, data in report['scenarios'].items():
                check(label + '_raf_at_least_50', data['raf_frames_per_second'] >= 50, data['raf_frames_per_second'])
                check(label + '_frame_p95_under_34ms', data['frame_intervals'].get('p95_ms', float('inf')) <= 34,
                      data['frame_intervals'])
                check(label + '_max_frame_under_200ms', data['frame_intervals'].get('max_ms', float('inf')) <= 200)
                inputs = data['input_to_two_frames']
                if inputs['n']:
                    check(label + '_input_p95_under_100ms', inputs['p95_ms'] <= 100, inputs)
            report['passed'] = all(item['passed'] for item in report['checks'])
    except Exception as error:
        report['error'] = type(error).__name__ + ': ' + str(error)
        report['passed'] = False
    finally:
        if browser:
            try:
                browser.close()
            except Exception:
                pass
        try:
            stop_process(app)
        except Exception as error:
            report['cleanup_error'] = str(error)
            report['passed'] = False
        server.shutdown()
        server.server_close()
        report['resource_limits_after'] = resource_snapshot()
        (output / 'report.json').write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n')
    print(json.dumps({"passed": report['passed'], "error": report.get('error'), "scenarios": {
        name: {k: {subkey: value for subkey, value in v.items() if subkey not in {'samples_ms', 'entries'}} if isinstance(v, dict) else v
               for k, v in data.items() if k != 'longTasks'} for name, data in report['scenarios'].items()
    }, "checks": [{"name": c['name'], "passed": c['passed']} for c in report['checks']]}, ensure_ascii=False))
    return 0 if report['passed'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
