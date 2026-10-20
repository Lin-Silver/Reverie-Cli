"""Boot a Windows installer/portable payload with the already-created P4 fixture.

The model is never called. Profiles and evidence stay under the repository.
For the portable launcher, --home must be its containing directory.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import socket
import subprocess
import time

from playwright.sync_api import expect, sync_playwright

ROOT = Path(__file__).resolve().parents[2]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--exe", type=Path, required=True)
    parser.add_argument("--home", type=Path, required=True)
    parser.add_argument("--fixture", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    output, home, fixture = (path.resolve() for path in (args.output, args.home, args.fixture))
    if not all(path.is_relative_to(ROOT) for path in (output, home, fixture, args.exe.resolve())):
        raise ValueError("Keep the executable, profile and evidence repository-local.")
    output.mkdir(parents=True, exist_ok=False)
    settings = home / ".reverie/desktop/desktop-settings.json"
    settings.parent.mkdir(parents=True, exist_ok=True)
    source = json.loads((fixture / "desktop-home/.reverie/desktop/desktop-settings.json").read_text(encoding="utf-8"))
    settings.write_text(json.dumps(source), encoding="utf-8")
    workspace = fixture / "workspace"
    os.environ["NO_PROXY"] = "127.0.0.1,localhost"
    env = {**os.environ, "PORTABLE_EXECUTABLE_DIR": str(home)}
    env.pop("ELECTRON_RUN_AS_NODE", None)
    report = {"passed": False, "launcher": str(args.exe.resolve()), "checks": [], "scope": "Actual Windows payload, existing synthetic artifact, no model request",
              "portable_runtime_marker_present_before_launch": any((home / ".reverie/desktop/app-runtime").glob(".reverie-build-*"))}
    process, page = None, None
    with (output / "electron.log").open("w", encoding="utf-8") as log:
        try:
            with sync_playwright() as p:
                with socket.socket() as sock:
                    sock.bind(("127.0.0.1", 0)); port = sock.getsockname()[1]
                startup = subprocess.STARTUPINFO(); startup.dwFlags |= subprocess.STARTF_USESHOWWINDOW; startup.wShowWindow = 0
                launch_start = time.perf_counter()
                process = subprocess.Popen([str(args.exe.resolve()), "--gui", "--project", str(workspace), f"--remote-debugging-port={port}"], env=env, stdout=log, stderr=log, startupinfo=startup)
                browser = None
                # The 500 MB portable carrier must finish its one-time extraction.
                # Keep this startup interval separate from P4 render measurements.
                while time.perf_counter() - launch_start < 600:
                    try:
                        browser = p.chromium.connect_over_cdp(f"http://127.0.0.1:{port}", timeout=1000)
                        break
                    except Exception:
                        if process.poll() is not None:
                            raise RuntimeError(f"Launcher exited with {process.returncode} before GUI startup.")
                        time.sleep(.25)
                if browser is None:
                    raise RuntimeError("Windows payload did not expose its test endpoint.")
                page = browser.contexts[0].pages[0]
                page.wait_for_selector(".session-item", timeout=120000)
                page.locator(".session-item").filter(has_text="RIU P4 · acceptance").click()
                report["paths"] = page.evaluate("window.reverie.paths()")
                anchor = page.locator(".interactive-view-anchor").last
                anchor.scroll_into_view_if_needed()
                if anchor.get_by_role("button", name="展开", exact=True).count():
                    anchor.get_by_role("button", name="展开", exact=True).click()
                target = page.locator('iframe[title="RIU P4 参数与比较"]')
                target.wait_for(timeout=30000)
                inner = target.element_handle().content_frame()
                inner.wait_for_function("()=>window.__p4?.ready", timeout=30000)
                report["launcher_to_restored_view_ms_includes_extraction_and_core_startup"] = (time.perf_counter() - launch_start) * 1000
                identity = inner.evaluate("window.__p4.instance")
                surface = page.locator(".interactive-view").filter(has=target)
                for mode in ("fullscreen", "pip", "inline"):
                    surface.locator(f'[data-view-mode="{mode}"]').click()
                    expect(surface).to_have_attribute("data-display-mode", mode)
                    intact = inner.evaluate("window.__p4.instance") == identity
                    report["checks"].append({"name": "payload-same-frame-" + mode, "passed": intact})
                    if not intact:
                        raise AssertionError("The payload reloaded the frame during a display switch.")
                page.screenshot(path=str(output / "result.png"), full_page=True)
                report["passed"] = True
        except Exception as error:
            report["error"] = repr(error)
            if page:
                try:
                    report['failure_dom'] = page.locator('.interactive-view').evaluate_all("es=>es.map(e=>({title:e.getAttribute('aria-label'),mode:e.dataset.displayMode,frames:e.querySelectorAll('iframe').length,buttons:[...e.querySelectorAll('button')].map(b=>({label:b.textContent,mode:b.dataset.viewMode}))}))")
                    page.screenshot(path=str(output / 'failure.png'), full_page=True)
                except Exception as capture_error:
                    report['capture_error'] = str(capture_error)
        finally:
            if process and process.poll() is None:
                subprocess.run(["taskkill", "/pid", str(process.pid), "/t", "/f"], capture_output=True, creationflags=subprocess.CREATE_NO_WINDOW)
                process.wait(timeout=20)
            (output / "report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=True))
    if not report["passed"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
