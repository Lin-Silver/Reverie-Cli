"""Try the configured active model + unchanged local official MCP App in an isolated package profile.

Only a synthetic current-time prompt is sent. No user session, source file or
credential is printed or sent as prompt content. Failure stays unverified.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import re
import shutil
import socket
import subprocess
import sys
import time

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "ReverieCli-py"))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--exe", type=Path, required=True)
    parser.add_argument("--sdk-root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--standard-index", type=int, help="Use this already-configured standard model in the isolated test profile only.")
    args = parser.parse_args()
    from reverie.config import ConfigManager
    from reverie.mcp import MCPConfigManager
    from reverie.session.manager import SessionManager
    from playwright.sync_api import expect, sync_playwright
    original = ConfigManager(REPO).load()
    source = "standard" if args.standard_index is not None else original.active_model_source
    active = original.models[args.standard_index] if args.standard_index is not None else original.active_model
    output = args.output.resolve()
    if not output.is_relative_to(REPO):
        raise ValueError("Output must remain repository-local.")
    output.mkdir(parents=True, exist_ok=False)
    report = {"status": "unverified", "model": active.model if active else None, "source": source, "scope": "Configured external model + unchanged official stdio get-time MCP App in production Windows package", "checks": []}
    if active is None:
        report["reason"] = "No active model configured."
        (output / "report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
        return
    workspace, app_root, home = [output / name for name in ("workspace", "app-root", "desktop-home")]
    for directory in (workspace, app_root, home): directory.mkdir()
    os.environ["REVERIE_APP_ROOT"] = str(app_root)
    os.environ["NO_PROXY"] = "127.0.0.1,localhost"
    config = ConfigManager(workspace); config.ensure_dirs(); cfg = config.load()
    cfg.active_model_source = source
    if cfg.active_model_source == "standard":
        cfg.models, cfg.active_model_index = [active], 0
    else:
        # Copy only the active provider, not the user's unrelated credentials.
        setattr(cfg, cfg.active_model_source if cfg.active_model_source != "custom" else "custom_providers", getattr(original, cfg.active_model_source if cfg.active_model_source != "custom" else "custom_providers"))
    cfg.stream_responses, cfg.api_proxy = False, original.api_proxy
    cfg.security = {**cfg.security, "permission_level": "full_control", "permission_mode": "default"}
    config.save(cfg)
    server = args.sdk_root.resolve() / "node_modules/@modelcontextprotocol/server-basic-vanillajs/dist/index.js"
    if not server.is_file(): raise FileNotFoundError(server)
    MCPConfigManager(app_root).save({"mcpServers": {"official": {"command": shutil.which("node"), "args": [str(server), "--stdio"], "trust": True}}})
    manager = SessionManager(config.project_data_dir, project_root=workspace)
    manager.create_session("RIU P4 real model + MCP")
    settings = home / ".reverie/desktop/desktop-settings.json"; settings.parent.mkdir(parents=True)
    settings.write_text(json.dumps({"coreAppRoot": str(app_root), "projectRoot": str(workspace), "ui": {"language": "zh-CN"}}), encoding="utf-8")
    env = {**os.environ, "PORTABLE_EXECUTABLE_DIR": str(home)}; env.pop("ELECTRON_RUN_AS_NODE", None)
    process = browser = page = None
    log = (output / "electron.log").open("w", encoding="utf-8")
    try:
        with sync_playwright() as playwright:
            with socket.socket() as sock: sock.bind(("127.0.0.1", 0)); port = sock.getsockname()[1]
            startup = subprocess.STARTUPINFO(); startup.dwFlags |= subprocess.STARTF_USESHOWWINDOW; startup.wShowWindow = 0
            process = subprocess.Popen([str(args.exe.resolve()), "--gui", "--project", str(workspace), f"--remote-debugging-port={port}"], env=env, stdout=log, stderr=log, startupinfo=startup)
            last_connection_error = ""
            for _ in range(120):
                try: browser = playwright.chromium.connect_over_cdp(f"http://127.0.0.1:{port}", timeout=1000); break
                except Exception as error:
                    last_connection_error = str(error)[:500]
                    if process.poll() is not None: raise RuntimeError("Packaged Electron exited.")
                    time.sleep(.25)
            if browser is None: raise RuntimeError("No package debugging endpoint: " + last_connection_error)
            page = browser.contexts[0].pages[0]
            page.wait_for_selector(".session-item", timeout=120000)
            page.wait_for_load_state("networkidle")
            page.locator(".session-item").filter(has_text="RIU P4 real model + MCP").click()
            page.evaluate("window.__realEvents=[];window.reverie.onEvent(e=>window.__realEvents.push(e));true")
            prompt = "Synthetic RIU acceptance. Use tool_catalog search with query get-time, then call the get-time MCP tool from server official exactly once. The host will display its MCP App. Do not write files or run commands. Report the returned time in one sentence."
            page.locator("textarea[aria-autocomplete=list]").fill(prompt)
            start = time.perf_counter()
            page.get_by_role("button", name="发送", exact=True).click()
            # Explicitly keep external model time separate from render latency.
            target = page.locator('iframe[title="get-time"]')
            page.wait_for_function("()=>document.querySelector('iframe[title=\"get-time\"]') || document.querySelector('.inline-error')", polling=100, timeout=180000)
            if not target.count():
                detail = page.locator(".inline-error").inner_text()
                if active.api_key: detail = detail.replace(active.api_key, "[redacted]")
                report["model_error"] = detail[:4000]
                page.screenshot(path=str(output / "result.png"), full_page=True)
                raise RuntimeError("External model failed before the MCP App was produced.")
            inner = target.element_handle().content_frame()
            expect(inner.locator("#server-time")).to_have_text(__import__("re").compile(r"^20\d\d-"), timeout=30000)
            report["external_prompt_to_app_ms_includes_model"] = (time.perf_counter() - start) * 1000
            report["checks"].append({"name": "real-model-to-mcp-to-app", "passed": True})
            page.get_by_role("button", name="停止", exact=True).wait_for(state="hidden", timeout=180000)
            before = inner.locator("#server-time").inner_text()
            inner.locator("#get-time-btn").click()
            panel = page.get_by_role("alertdialog"); panel.wait_for(timeout=30000)
            page.screenshot(path=str(output / "approval.png"), full_page=True)
            panel.get_by_role("button", name="同意", exact=True).click()
            expect(inner.locator("#server-time")).not_to_have_text(before, timeout=30000)
            report["checks"].append({"name": "real-mcp-approved-app-callback", "passed": inner.locator("#server-time").inner_text() != "[ERROR]"})
            report["status"] = "verified" if all(item["passed"] for item in report["checks"]) else "unverified"
            page.screenshot(path=str(output / "result.png"), full_page=True)
            (output / "events.json").write_text(json.dumps(page.evaluate("window.__realEvents"), ensure_ascii=False, indent=2), encoding="utf-8")
    except Exception as error:
        report["reason"] = str(error)[:1200]
    finally:
        if page:
            try:
                page.screenshot(path=str(output / "result.png"), full_page=True)
                text = page.locator("body").inner_text()
                if active.api_key: text = text.replace(active.api_key, "[redacted]")
                (output / "result.txt").write_text(text, encoding="utf-8")
                events = json.dumps(page.evaluate("window.__realEvents"), ensure_ascii=False, indent=2)
                if active.api_key: events = events.replace(active.api_key, "[redacted]")
                (output / "events.json").write_text(events, encoding="utf-8")
            except Exception: pass
        provider_log = home / ".reverie/desktop/logs/desktop.log"
        if provider_log.is_file():
            log_lines = provider_log.read_text(encoding="utf-8").splitlines()
            service_errors = [line for line in log_lines if "SDK call failed" in line or re.search(r"Error code: (400|401|403|404|429|5\d\d)", line)]
            if service_errors:
                report["external_service_errors"] = [line.replace(active.api_key, "[redacted]") if active.api_key else line for line in service_errors[-12:]]
            lines = [line for line in log_lines if "403" in line or "free tier can only" in line]
            if lines:
                report["external_service_rejection"] = lines
                provider = "OpenCode free-tier" if source == "opencode" else source
                report["reason"] = f"Configured {provider} endpoint rejected this client (HTTP 403); real model-to-MCP-to-UI remains unverified."
        (output / "report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        if browser:
            try: browser.close()
            except Exception: pass
        if process and process.poll() is None:
            subprocess.run(["taskkill", "/pid", str(process.pid), "/t", "/f"], capture_output=True, creationflags=subprocess.CREATE_NO_WINDOW)
        log.close()
    print(json.dumps(report, ensure_ascii=True))


if __name__ == "__main__": main()
