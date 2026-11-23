"""Observe the unchanged released Desktop through CDP and native process counters.

Readiness requires the visible workspace and the enabled streaming control,
which is populated only after the real getState hydration completes. There
are no model calls, input events, synthetic responses or runtime code patches.
Fresh and prewarmed profiles both have no index and no conversation history.
"""
import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import socket
import statistics
import subprocess
import sys
import time
import traceback
import urllib.parse
import urllib.request

import psutil
from playwright.sync_api import sync_playwright
from websockets.sync.client import connect
from websockets.exceptions import ConnectionClosed

ROOT = Path.cwd().resolve()
sys.path.insert(0, str(ROOT / "scripts/verification"))
from desktop_process import launch_options, native_window_state, wait_for_packaged_page, stop_process

sys.stdout.reconfigure(encoding="utf-8")
PAYLOAD = ROOT / ".runtime/phase0B/baseline/desktop-release/.reverie/desktop/app-runtime"
EXE = PAYLOAD / "ReverieUI.exe"
CORE = PAYLOAD / "reverie.exe"
SOURCE = "070fa25b07692c90c56a6b00a9a969ff2abb7804"
READY = """() => Boolean(document.querySelector('.composer-shell textarea') &&
    document.querySelector('.stream-output-toggle')?.disabled === false &&
    document.fonts.status === 'loaded')"""


def digest(file):
    value = hashlib.sha256()
    with file.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            value.update(block)
    return value.hexdigest()


def save(file, data):
    file.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def seed(directory):
    directory.mkdir()
    for name in ("temp", "roaming", "local", "app/.reverie", ".reverie/desktop"):
        (directory / name).mkdir(parents=True)
    save(directory / "app/.reverie/config.json", {"auto_index": False})
    save(directory / ".reverie/desktop/desktop-settings.json", {
        "coreAppRoot": str(directory / "app"), "projectRoot": str(ROOT / ".runtime/phase0B/corpus"),
        "ui": {"startupMode": "gui", "language": "zh-CN"}})
    env = dict(os.environ)
    for key in list(env):
        if key.upper().endswith(("_API_KEY", "_TOKEN")) or key.startswith(("PYTHON", "VIRTUAL_ENV", "CONDA")):
            env.pop(key, None)
    env.pop("ELECTRON_RUN_AS_NODE", None)
    env.update(TEMP=str(directory / "temp"), TMP=str(directory / "temp"),
        APPDATA=str(directory / "roaming"), LOCALAPPDATA=str(directory / "local"),
        PORTABLE_EXECUTABLE_DIR=str(directory), GIT_CEILING_DIRECTORIES=str(ROOT / ".runtime/phase0B/corpus"),
        NO_PROXY="127.0.0.1,localhost")
    return env


def counters(pid):
    parent = psutil.Process(pid)
    rows = []
    for process in (parent, *parent.children(recursive=True)):
        try:
            memory = process.memory_info()
            rows.append({"pid": process.pid, "created": process.create_time(), "name": process.name(),
                "working_set_bytes": memory.wset, "private_commit_bytes": memory.private})
        except psutil.NoSuchProcess:
            continue
    return {"processes": rows, "working_set_bytes": sum(row["working_set_bytes"] for row in rows),
            "private_commit_bytes": sum(row["private_commit_bytes"] for row in rows)}


def send_close(port):
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    with opener.open(f"http://127.0.0.1:{port}/json/list", timeout=5) as response:
        targets = json.load(response)
    assert len(targets) == 1 and targets[0]["type"] == "node"
    endpoint = targets[0]["webSocketDebuggerUrl"]
    address = urllib.parse.urlsplit(endpoint)
    assert address.scheme == "ws" and address.hostname == "127.0.0.1" and address.port == port
    with connect(endpoint, proxy=None, open_timeout=5, close_timeout=1) as channel:
        channel.send(json.dumps({"id": 1, "method": "Runtime.evaluate",
            "params": {"expression": "process.mainModule.require('electron').app.quit()", "awaitPromise": False}}))
        try:
            response = json.loads(channel.recv(timeout=5))
        except ConnectionClosed:
            return {"transport_closed_after_send": True}
        except TimeoutError:
            return {"response_timed_out": True}
        if response.get("error") or response.get("result", {}).get("exceptionDetails"):
            raise RuntimeError(str(response))
        return response


def close_app(process, port):
    parent = psutil.Process(process.pid)
    children = parent.children(recursive=True)
    identities = [(item.pid, item.create_time(), item.name()) for item in children]
    error = None
    notification = None
    try:
        notification = send_close(port)
    except Exception as exc:
        error = f"{type(exc).__name__}: {exc}"
    process.wait(timeout=30)
    psutil.wait_procs(children, timeout=30)
    survivors = []
    for pid, created, _name in identities:
        try:
            if psutil.Process(pid).create_time() == created:
                survivors.append(pid)
        except psutil.NoSuchProcess:
            pass
    if process.returncode != 0 or survivors:
        raise RuntimeError(f"Desktop close failed: exit={process.returncode}, owned_survivors={survivors}")
    return {"exit_code": process.returncode, "owned_survivors": survivors,
            "cdp_close_response_error": error, "close_notification": notification}


def distribution(values):
    ordered = sorted(values)
    return {"n": len(values), "median_ms": statistics.median(ordered),
        "p95_ms": ordered[(len(ordered) * 95 + 99) // 100 - 1], "samples_ms": values,
        "p95_method": "nearest rank"}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--count", type=int, default=30)
    args = parser.parse_args()
    output = args.output.resolve()
    if args.count < 1 or output.exists() or not output.is_relative_to(ROOT / ".runtime"):
        parser.error("Use a new project-local output directory and a positive count")
    prepared = json.loads((PAYLOAD.parents[2] / "verified.json").read_bytes())
    assert prepared["passed"] and prepared["source_commit"] == SOURCE
    assert digest(EXE) == prepared["desktop_exe_sha256"]
    assert digest(CORE) == prepared["folder_kernel_sha256"]
    output.mkdir(parents=True)
    report = {"schema": "reverie.desktop-baseline.v1", "source_commit": SOURCE, "method": __doc__,
        "harness_sha256": digest(Path(__file__)), "desktop_exe_sha256": digest(EXE),
        "core_sha256": digest(CORE), "app_asar_sha256": digest(PAYLOAD / "resources/app.asar"),
        "count_per_group": args.count, "formal_sample_count": args.count >= 30, "filesystem_cache": "uncontrolled",
        "observer": "external CDP DOM reads, native counters; Node inspector invokes the unchanged app.quit lifecycle only",
        "observer_flags": ["remote-debugging-port", "inspect=127.0.0.1:allocated-port"],
        "window_launch": "visible; initial Windows ShowWindow uses SW_SHOWNOACTIVATE",
        "history": "empty isolated profile", "no_index": True, "semantic_models_loaded": False,
        "gamer_running": False, "started_at": datetime.now(timezone.utc).isoformat(),
        "startups": [], "idle_samples": [], "passed": False}
    process = browser = None
    try:
        os.environ["NO_PROXY"] = "127.0.0.1,localhost"
        with sync_playwright() as pw:
            for trial in range(1, args.count + 1):
                directory = output / f"profile-{trial:02}"
                env = seed(directory)
                for group in ("fresh_profile", "prewarmed_profile"):
                    with socket.socket() as sock:
                        sock.bind(("127.0.0.1", 0))
                        port = sock.getsockname()[1]
                    with socket.socket() as sock:
                        sock.bind(("127.0.0.1", 0))
                        main_port = sock.getsockname()[1]
                    with (directory / f"{group}.process.log").open("x", encoding="utf-8") as log:
                        started = time.perf_counter_ns()
                        options = launch_options(visible=True)
                        if os.name == "nt":
                            options["startupinfo"].wShowWindow = 4
                        process = subprocess.Popen([str(EXE), "--gui", "--project",
                            str(ROOT / ".runtime/phase0B/corpus"), f"--remote-debugging-port={port}",
                            f"--inspect=127.0.0.1:{main_port}"],
                            cwd=directory, env=env, stdout=log, stderr=log, **options)
                        browser, page = wait_for_packaged_page(pw, process, port)
                        try:
                            page.wait_for_function(READY, timeout=120000, polling=50)
                        except Exception:
                            report["readiness_failure"] = page.evaluate("""() => ({
                                title: document.title, fonts: document.fonts.status,
                                composer: document.querySelector('.composer-shell textarea')?.outerHTML,
                                streaming: document.querySelector('.stream-output-toggle')?.outerHTML,
                                text: document.body.innerText.slice(0, 2000)})""")
                            page.screenshot(path=str(output / "readiness-failure.png"))
                            raise
                        native = native_window_state(process.pid)
                        assert native["visible"], "Readiness requires a real visible native window"
                        elapsed = (time.perf_counter_ns() - started) / 1e6
                        paths = page.evaluate("() => window.reverie.paths()")
                        assert Path(paths["kernelPath"]).resolve() == CORE
                        assert Path(paths["coreAppRoot"]).resolve() == directory / "app"
                        state = page.evaluate("() => window.reverie.request('getContextStatus', {})")
                        assert not state["context_engine"]["indexing"] and state["context_engine"]["files"] == 0
                        row = {"trial": trial, "group": group, "gui_and_kernel_usable_ms": elapsed,
                            "native_window": native, "resources_at_ready": counters(process.pid)}
                        if trial == 1 and group == "prewarmed_profile":
                            page.screenshot(path=str(output / "desktop-ready.png"))
                            page.wait_for_timeout(30000)
                            idle_started = time.perf_counter()
                            for sample in range(60):
                                row_sample = {"sample": sample + 1, "elapsed_seconds": time.perf_counter() - idle_started,
                                    **counters(process.pid)}
                                report["idle_samples"].append(row_sample)
                                save(output / "progress.json", report)
                                page.wait_for_timeout(1000)
                            report["idle_window"] = {"settle_seconds": 30, "samples": 60,
                                "duration_seconds": time.perf_counter() - idle_started}
                        row["close"] = close_app(process, main_port)
                        process = browser = None
                    report["startups"].append(row)
                    save(output / "progress.json", report)
                    print(json.dumps({"trial": trial, "group": group, "startup_ms": elapsed}), flush=True)
            report["startup_distributions"] = {group: distribution([
                row["gui_and_kernel_usable_ms"] for row in report["startups"] if row["group"] == group])
                for group in ("fresh_profile", "prewarmed_profile")}
            report["idle_memory"] = {field: {"samples_bytes": [row[field] for row in report["idle_samples"]],
                "median_bytes": statistics.median(row[field] for row in report["idle_samples"]),
                "p95_bytes": sorted(row[field] for row in report["idle_samples"])[56],
                "peak_bytes": max(row[field] for row in report["idle_samples"])}
                for field in ("working_set_bytes", "private_commit_bytes")}
            report["passed"] = True
    except Exception as error:
        report.update(error=str(error), traceback=traceback.format_exc())
        raise
    finally:
        if process is not None and process.poll() is None:
            try:
                report["failure_cleanup"] = close_app(process, main_port)
            except Exception as error:
                report["cleanup_error"] = str(error)
                stop_process(process)
                report["failure_cleanup_forced"] = True
        report["finished_at"] = datetime.now(timezone.utc).isoformat()
        save(output / "report.json", report)
    print(json.dumps({"passed": report["passed"], "output": str(output)}), flush=True)


if __name__ == "__main__":
    main()
