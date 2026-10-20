"""Exercise prompt identity, genuinely generated RIU and a real MCP App.

Uses only synthetic sessions in a new repository-local profile. Copies only the
selected provider's credentials. Never substitutes a prewritten HTML fixture.
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

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "ReverieCli-py"))


class ServiceUnavailable(RuntimeError):
    pass


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--exe", type=Path, required=True)
    parser.add_argument("--sdk-root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--source", choices=("nvidia", "opencode"), default="nvidia")
    parser.add_argument("--model", help="Override the selected model only inside the isolated test profile.")
    parser.add_argument("--resume-profile", type=Path, help="Continue a previously recorded source-core generation in its existing isolated Desktop profile.")
    parser.add_argument("--resume-artifact", help="Previously model-authored workspace HTML to register in that continued conversation.")
    parser.add_argument("--inspect-only", action="store_true", help="Inspect the resumed real model result without another model request.")
    parser.add_argument("--cases", nargs="+", choices=("identity", "generated", "mcp"), default=["identity", "generated", "mcp"])
    args = parser.parse_args()
    from playwright.sync_api import expect, sync_playwright
    from reverie.config import ConfigManager
    from reverie.mcp import MCPConfigManager
    from reverie.session.manager import SessionManager

    original = ConfigManager(ROOT).load()
    output = args.output.resolve()
    if not output.is_relative_to(ROOT):
        raise ValueError("Keep all evidence inside the repository.")
    output.mkdir(parents=True, exist_ok=False)
    profile = args.resume_profile.resolve() if args.resume_profile else output
    if not profile.is_relative_to(ROOT):
        raise ValueError("The resumed profile must stay inside the repository.")
    if args.resume_profile and (args.cases != ["generated"] or not args.resume_artifact or args.model):
        raise ValueError("A resumed profile requires only --cases generated, --resume-artifact and its original model.")
    if args.inspect_only and not args.resume_profile:
        raise ValueError("--inspect-only requires a recorded real model profile.")
    workspace, app_root, home = [profile / name for name in ("workspace", "app-root", "desktop-home")]
    if not args.resume_profile:
        for directory in (workspace, app_root, home):
            directory.mkdir()
    os.environ["REVERIE_APP_ROOT"] = str(app_root)
    os.environ["NO_PROXY"] = "127.0.0.1,localhost"
    config = ConfigManager(workspace)
    config.ensure_dirs()
    cfg = config.load()
    if not args.resume_profile:
        cfg.active_model_source = args.source
        setattr(cfg, args.source, dict(getattr(original, args.source)))
    else:
        if cfg.active_model_source != args.source:
            raise ValueError("Resume with the original provider source.")
        getattr(cfg, args.source)["api_key"] = getattr(original, args.source).get("api_key", "")
    if args.model:
        getattr(cfg, args.source)["selected_model_id"] = args.model
    cfg.stream_responses = True
    cfg.api_proxy = original.api_proxy
    cfg.security = {**cfg.security, "permission_level": "full_control", "permission_mode": "default"}
    config.save(cfg)
    active = cfg.active_model
    if active is None:
        raise ValueError("Selected provider has no configured model.")
    if args.model and active.model != args.model:
        raise ValueError("Requested test model was not resolved exactly.")
    secret = active.api_key or ""
    server = args.sdk_root.resolve() / "node_modules/@modelcontextprotocol/server-basic-vanillajs/dist/index.js"
    if "mcp" in args.cases:
        if not server.is_file():
            raise FileNotFoundError(server)
        MCPConfigManager(app_root).save({"mcpServers": {"official": {"command": shutil.which("node"), "args": [str(server), "--stdio"], "trust": True}}})
    manager = SessionManager(config.project_data_dir, project_root=workspace)
    if args.resume_profile:
        source_record = json.loads((profile / "source-report.json").read_text(encoding="utf-8"))
        sessions = {"generated": source_record["session_id"]}
        session = manager.load_session(sessions["generated"])
        if session is None:
            raise ValueError("The recorded source session is missing.")
    else:
        sessions = {case: manager.create_session("RIU real · " + case).id for case in args.cases}
    settings = home / ".reverie/desktop/desktop-settings.json"
    settings.parent.mkdir(parents=True, exist_ok=True)
    settings.write_text(json.dumps({"coreAppRoot": str(app_root), "projectRoot": str(workspace), "ui": {"language": "zh-CN", "showReasoning": True, "expandReasoning": True}}), encoding="utf-8")
    env = {**os.environ, "PORTABLE_EXECUTABLE_DIR": str(home)}
    env.pop("ELECTRON_RUN_AS_NODE", None)
    report = {"status": "failed", "scope": "Real configured external model; production Windows package; synthetic workspace", "source": args.source, "model": active.model, "cases": args.cases, "checks": [], "stages": [], "fixture_html": False, "manual_quality_review_required": True}
    if args.resume_profile:
        report["generation_origin"] = "Current source Desktop core authored the HTML; this run continues that real conversation in the production package. No test-authored HTML."
        report["resumed_source_record"] = str(profile / "source-report.json")
    if args.inspect_only:
        report["scope"] = "Production package UI inspection of a saved real-model artifact; no model request in this run."
    process = browser = page = playwright = None
    log = (output / "electron.log").open("w", encoding="utf-8")

    def redact(text):
        return str(text).replace(secret, "[redacted]") if secret else str(text)

    def save_json(name, value):
        (output / name).write_text(redact(json.dumps(value, ensure_ascii=False, indent=2, default=str)), encoding="utf-8")

    def check(name, passed, detail=None, *, fatal=True):
        item = {"name": name, "passed": bool(passed), "detail": detail}
        report["checks"].append(item)
        print(json.dumps(item, ensure_ascii=True), flush=True)
        if not passed and fatal:
            raise AssertionError(name)

    def capture(name):
        page.screenshot(path=str(output / (name + ".png")), full_page=True)
        (output / (name + ".txt")).write_text(redact(page.locator("body").inner_text()), encoding="utf-8")

    def select_session(case):
        page.locator(".session-item").filter(has_text="RIU real · " + case).click()
        page.locator(".session-loading").wait_for(state="hidden", timeout=60000)

    def send(case, prompt):
        select_session(case)
        page.evaluate("window.__riuEvents=[]")
        started = time.perf_counter()
        print(json.dumps({"stage": case, "state": "model-running"}), flush=True)
        page.locator("textarea[aria-autocomplete=list]").fill(prompt)
        page.get_by_role("button", name="发送", exact=True).click()
        page.get_by_role("button", name="停止", exact=True).wait_for(timeout=15000)
        page.get_by_role("button", name="停止", exact=True).wait_for(state="hidden", timeout=600000)
        capture(case)
        if page.locator(".inline-error").count():
            error = redact(page.locator(".inline-error").last.inner_text())
            if re.search(r"\b(400|401|403|404|429|5\d\d)\b|rate.limit|overload", error, re.I):
                raise ServiceUnavailable(error)
            raise RuntimeError(error)
        session = manager.load_session(sessions[case])
        save_json(case + "-session.json", session.to_dict())
        save_json(case + "-events.json", page.evaluate("window.__riuEvents"))
        report["stages"].append({"case": case, "model_turn_ms": round((time.perf_counter() - started) * 1000, 2)})
        return session.messages

    def latest_frame():
        anchor = page.locator(".interactive-view-anchor").last
        anchor.wait_for(timeout=30000)
        anchor.scroll_into_view_if_needed()
        expand = anchor.get_by_role("button", name="展开", exact=True)
        if expand.count():
            expand.click()
        iframe = page.locator(".interactive-view iframe").last
        iframe.wait_for(timeout=30000)
        return iframe, iframe.element_handle().content_frame()

    def number(locator):
        return float(re.search(r"-?\d+(?:\.\d+)?", locator.inner_text().replace(",", "")).group())

    try:
        playwright = sync_playwright().start()
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
                    raise RuntimeError("Packaged Electron exited.")
                time.sleep(.25)
        if browser is None:
            raise RuntimeError("No package debugging endpoint.")
        page = browser.contexts[0].pages[0]
        page.on("pageerror", lambda error: report.setdefault("page_errors", []).append(redact(error)))
        page.set_viewport_size({"width": 1280, "height": 900})
        page.wait_for_selector(".session-item", timeout=120000)
        page.wait_for_load_state("networkidle")
        report["build"] = page.evaluate("window.reverie.paths()")
        page.evaluate("window.__riuEvents=[];window.reverie.onEvent(e=>window.__riuEvents.push(e));window.__riuMessages=[];addEventListener('message',e=>{if(e.data?.jsonrpc==='2.0')window.__riuMessages.push(e.data)});true")
        if "identity" in args.cases:
            messages = send("identity", "你是什么？当前是在什么界面运行，配置的模型标识符是什么？你能做哪些事情？请依据当前实际工具和配置回答，不调用工具，不要推测性能或厂商背景。")
            assistant = [message for message in messages if message.get("role") == "assistant"]
            visible = json.dumps(assistant, ensure_ascii=False)
            reasoning = []
            def collect_reasoning(value):
                if isinstance(value, dict):
                    if value.get("type") == "reasoning.delta":
                        reasoning.append(str(value.get("text", "")))
                    for key, child in value.items():
                        if key in ("thinking_text", "reasoning_content") and isinstance(child, str):
                            reasoning.append(child)
                        elif isinstance(child, (dict, list)):
                            collect_reasoning(child)
                elif isinstance(value, list):
                    for child in value:
                        collect_reasoning(child)
            collect_reasoning(page.evaluate("window.__riuEvents"))
            report["identity_reasoning_characters"] = sum(map(len, reasoning))
            visible += "\n" + "\n".join(reasoning)
            forbidden = ["Ready to close", "Harness Runtime", "Project-Wide Coding Guardrails", "After tool use, always produce a user-visible textual response", "system prompt", "per the instructions", "according to my instructions", "系统提示词", "系统指令", "按规则"]
            found = [value for value in forbidden if value.lower() in visible.lower()]
            check("identity-uses-configured-id", active.model in visible)
            check("identity-stays-on-desktop", "Desktop" in visible or "桌面" in visible or "图形" in visible)
            check("identity-has-no-tools", not any(message.get("tool_calls") for message in assistant))
            check("identity-does-not-recite-runtime-instructions", not found, found)
        if "generated" in args.cases:
            prompt = "创建并展示一个中文交互式储蓄比较器，HTML 必须由你现在编写，不能读取或复制已有样例。方案 A 本金 10000、年利率 3%，方案 B 本金 12000、年利率 5%，默认 10 年，按年复利，金额保留两位小数。年份和两个年利率用可操作的控件调整，输入改变后本地即时重算。为验证可访问性，年份控件设置 aria-label 为“年份”，两个结果用 output 元素并分别设置 aria-label 为“方案 A 终值”和“方案 B 终值”。重要结果优先显示，适配对话内、工作面板和画中画，跟随宿主主题，自动保存并恢复年份等私有 UI 状态。仅使用当前工作区的 create_file 和 render_view 完成这个离线视图，不运行终端、不访问网络、不读取外部文件。注册后说明完成情况和未验证部分。"
            if args.resume_profile:
                prompt = f"继续同一储蓄比较器任务。你已把完整 HTML 写入 {args.resume_artifact}。请调用 render_view 注册它，并说明完成情况与未验证部分。全程只允许 create_file 和 render_view，不调用检索工具，不读取其他文件；若工具给出作者警告，沿正常 create_file/render_view 链修正并注册替换版本。不要运行终端或访问网络。"
            if args.inspect_only:
                select_session("generated")
                messages = manager.load_session(sessions["generated"]).messages
                save_json("generated-session.json", manager.load_session(sessions["generated"]).to_dict())
            else:
                messages = send("generated", prompt)
            tool_names = [call.get("function", {}).get("name") for message in messages for call in message.get("tool_calls", [])]
            check("model-authored-html-through-real-tools", "create_file" in tool_names and "render_view" in tool_names, tool_names)
            latest_user = max(index for index, message in enumerate(messages) if message.get("role") == "user")
            turn_tools = [call.get("function", {}).get("name") for message in messages[latest_user + 1:] for call in message.get("tool_calls", [])]
            report["historical_tool_scope_violations"] = [name for message in messages[:latest_user] for call in message.get("tool_calls", []) if (name := call.get("function", {}).get("name")) not in {"create_file", "render_view"}]
            check("model-respects-requested-tool-scope-this-turn", all(name in {"create_file", "render_view"} for name in turn_tools), turn_tools, fatal=False)
            iframe, inner = latest_frame()
            years = inner.locator('input[aria-label="年份"], select[aria-label="年份"]')
            years.wait_for()
            initial_years = float(years.input_value())
            rate_a = inner.get_by_label(re.compile(r"方案\s*A.*利率"))
            rate_b = inner.get_by_label(re.compile(r"方案\s*B.*利率"))
            initial_a, initial_b = float(rate_a.input_value()), float(rate_b.input_value())
            first, second = inner.locator('output[aria-label="方案 A 终值"]'), inner.locator('output[aria-label="方案 B 终值"]')
            expect(first).to_have_text(re.compile(r"\d"), timeout=30000)
            expect(second).to_have_text(re.compile(r"\d"), timeout=30000)
            if not args.resume_profile:
                check("generated-default-parameters-match-request", (initial_years, initial_a, initial_b) == (10, 3, 5))
            check("generated-compound-interest-is-correct", abs(number(first) - 10000 * (1 + initial_a / 100) ** initial_years) < .1 and abs(number(second) - 12000 * (1 + initial_b / 100) ** initial_years) < .1, {"years": initial_years, "a": number(first), "b": number(second)})
            target_years = "21" if initial_years == 20 else "20"
            years.evaluate("(e,value)=>{e.value=value;e.dispatchEvent(new Event('input',{bubbles:true}));e.dispatchEvent(new Event('change',{bubbles:true}))}", target_years)
            expected = 10000 * (1 + initial_a / 100) ** float(target_years)
            inner.wait_for_function("expected=>Math.abs(Number(document.querySelector('output[aria-label=\"方案 A 终值\"]').textContent.replace(/[^0-9.-]/g,''))-expected)<.1", arg=expected)
            check("generated-controls-recompute-locally", abs(number(first) - expected) < .1, number(first))
            for control, value in ((rate_a, "4"), (rate_b, "6")):
                control.evaluate("(e,value)=>{e.value=value;e.dispatchEvent(new Event('input',{bubbles:true}));e.dispatchEvent(new Event('change',{bubbles:true}))}", value)
            expected_rates = [10000 * 1.04 ** float(target_years), 12000 * 1.06 ** float(target_years)]
            inner.wait_for_function("values=>['方案 A 终值','方案 B 终值'].every((label,i)=>Math.abs(Number(document.querySelector('output[aria-label=\"'+label+'\"]').textContent.replace(/[^0-9.-]/g,''))-values[i])<.1)", arg=expected_rates)
            check("generated-both-rate-controls-recompute", abs(number(first) - expected_rates[0]) < .1 and abs(number(second) - expected_rates[1]) < .1, {"a": number(first), "b": number(second)})
            surface = iframe.locator("..")
            identity = inner.evaluate("window.__riuProbeInstance=crypto.randomUUID()")
            for mode in ("fullscreen", "pip", "inline"):
                surface.locator(f'[data-view-mode="{mode}"]').click()
                expect(surface).to_have_attribute("data-display-mode", mode)
                check("generated-same-document-" + mode, inner.evaluate("window.__riuProbeInstance") == identity and years.input_value() == target_years and float(rate_a.input_value()) == 4 and float(rate_b.input_value()) == 6)
                capture("generated-" + mode)
            before = inner.locator("body").evaluate("e=>({background:getComputedStyle(e).backgroundColor,color:getComputedStyle(e).color})")
            next_theme = "dark" if page.evaluate("document.documentElement.dataset.theme") == "light" else "light"
            page.evaluate("theme=>window.reverie.setAppearance(theme)", next_theme)
            page.wait_for_timeout(250)
            after = inner.locator("body").evaluate("e=>({background:getComputedStyle(e).backgroundColor,color:getComputedStyle(e).color})")
            check("generated-applies-live-host-theme", before != after, {"before": before, "after": after})
            page.wait_for_function("()=>window.__riuMessages.some(m=>m.method==='reverie/view-state')", timeout=10000)
            page.reload()
            page.wait_for_selector(".session-item", timeout=120000)
            select_session("generated")
            anchor = page.locator(".interactive-view-anchor").last
            anchor.scroll_into_view_if_needed()
            expand = anchor.get_by_role("button", name="展开", exact=True)
            if expand.count():
                expand.click()
            _, restored = latest_frame()
            expect(restored.locator('input[aria-label="年份"], select[aria-label="年份"]')).to_have_value(target_years, timeout=30000)
            expect(restored.get_by_label(re.compile(r"方案\s*A.*利率"))).to_have_value(re.compile(r"^4(?:\.0+)?$"))
            expect(restored.get_by_label(re.compile(r"方案\s*B.*利率"))).to_have_value(re.compile(r"^6(?:\.0+)?$"))
            check("generated-restores-private-state-after-reload", True)
            check("generated-has-no-page-errors", not report.get("page_errors"), report.get("page_errors", []))
            capture("generated-restored")
        if "mcp" in args.cases:
            messages = send("mcp", "这是合成测试。请用 tool_catalog 搜索 get-time，找到 official 服务器的 get-time 工具并调用一次。宿主会显示它的 MCP App。不要写文件或运行命令，用一句话说明返回的当前时间。")
            iframe = page.locator('iframe[title="get-time"]')
            iframe.wait_for(timeout=30000)
            inner = iframe.element_handle().content_frame()
            expect(inner.locator("#server-time")).to_have_text(re.compile(r"^20\d\d-"), timeout=30000)
            check("real-model-to-official-mcp-app", True)
            before = inner.locator("#server-time").inner_text()
            inner.locator("#get-time-btn").click()
            dialog = page.get_by_role("alertdialog")
            dialog.wait_for(timeout=30000)
            capture("mcp-approval")
            dialog.get_by_role("button", name="同意", exact=True).click()
            expect(inner.locator("#server-time")).not_to_have_text(before, timeout=30000)
            check("official-mcp-callback-through-host-approval", inner.locator("#server-time").inner_text() != "[ERROR]")
            capture("mcp-result")
        report["status"] = "verified" if all(item["passed"] for item in report["checks"]) else "failed"
    except ServiceUnavailable as error:
        report["status"], report["error"] = "unverified-service", redact(error)
    except Exception as error:
        report["error"] = redact(repr(error))
    finally:
        if page:
            try:
                capture("final")
                save_json("events.json", page.evaluate("window.__riuEvents || []"))
            except Exception:
                pass
        if browser:
            try:
                browser.close()
            except Exception:
                pass
        if process and process.poll() is None:
            subprocess.run(["taskkill", "/pid", str(process.pid), "/t", "/f"], capture_output=True, creationflags=subprocess.CREATE_NO_WINDOW)
            process.wait(timeout=20)
        if playwright:
            playwright.stop()
        log.close()
        save_json("report.json", report)
    print(json.dumps({"status": report["status"], "model": active.model, "passed": sum(item["passed"] for item in report["checks"]), "checks": len(report["checks"]), "error": report.get("error"), "output": str(output)}, ensure_ascii=True))
    if report["status"] != "verified":
        raise SystemExit(2 if report["status"] == "unverified-service" else 1)


if __name__ == "__main__":
    main()
