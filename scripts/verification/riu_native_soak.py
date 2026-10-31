"""Keep the real packaged P4 lifecycle active for a measured duration.

The authored loopback fixture spaces its requests; existing P4 checks and
acceptance thresholds remain unchanged. This is synthetic local stability,
not model quality, physical-device use, or an external-provider endurance test.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import io
import json
from pathlib import Path
import subprocess
import sys
import threading
import time

import riu_p4_electron as p4


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    if sys.platform != "linux":
        parser.error("This resource sampler currently supports Linux only")
    parser.add_argument("--exe", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--duration-seconds", type=float, default=3600)
    parser.add_argument("--samples", type=int, default=81)
    args = parser.parse_args()
    if not 60 <= args.duration_seconds <= 14400 or args.samples < 3:
        parser.error("Use a bounded duration of 60–14400 seconds and at least 3 samples")
    if args.duration_seconds / (args.samples - 1) > 45:
        parser.error("Use enough samples to keep each fixture wait below the default 60-second API timeout")
    output = args.output.resolve()
    if output.exists() or not output.is_relative_to(p4.REPO / ".runtime"):
        parser.error("Use a fresh repository .runtime directory")
    started = time.monotonic()
    stop = threading.Event()
    generations, resources, browser_errors, page_samples = [], [], [], []
    current = {"process": None, "page": None}
    original_post = p4.ModelFixture.do_POST
    original_wait = p4.wait_for_packaged_page
    original_distribution = p4.distribution

    def paced_post(handler):
        raw = handler.rfile.read(int(handler.headers["Content-Length"]))
        payload = json.loads(raw)
        last = (payload.get("messages") or [{}])[-1]
        generated = last.get("role") == "user" and "RIU_P4_GENERATE" in str(last.get("content", "")) and len(generations) < args.samples
        if generated:
            target = (generations[0]["monotonic"] if generations else time.monotonic()) + len(generations) * args.duration_seconds / (args.samples - 1)
            while time.monotonic() < target and not stop.is_set():
                stop.wait(min(1, max(0, target - time.monotonic())))
            generations.append({"index": len(generations), "monotonic": time.monotonic(), "at": datetime.now(timezone.utc).isoformat()})
            (output / "soak-progress.json").write_text(json.dumps({"generated": len(generations), "requested": args.samples, "elapsed_seconds": time.monotonic() - started}, indent=2) + "\n")
        original = handler.rfile
        try:
            handler.rfile = io.BytesIO(raw)
            original_post(handler)
        finally:
            handler.rfile = original

    def observed_wait(playwright, process, port, **kwargs):
        browser, page = original_wait(playwright, process, port, **kwargs)
        current.update(process=process, page=page)
        page.on("pageerror", lambda error: browser_errors.append(str(error)))
        page.evaluate("""() => {
          window.__soak = [];
          setInterval(() => window.__soak.push({at:Date.now(), heapBytes:performance.memory?.usedJSHeapSize ?? null,
            iframes:document.querySelectorAll('iframe').length, messages:document.querySelectorAll('.message').length}), 30000);
        }""")
        return browser, page

    def observed_distribution(values):
        page = current["page"]
        if page and not page.is_closed():
            page_samples.append(page.evaluate("window.__soak ?? []"))
            (output / f"soak-page-samples-{len(page_samples)}.json").write_text(json.dumps(page_samples[-1], indent=2) + "\n")
        return original_distribution(values)

    def heartbeat():
        while not stop.wait(30):
            process = current["process"]
            if not process or process.poll() is not None:
                continue
            rows = subprocess.run(["ps", "-eo", "pid=,ppid=,rss="], capture_output=True, text=True, check=True).stdout.splitlines()
            table = [tuple(map(int, row.split())) for row in rows]
            owned = {process.pid}
            while True:
                children = {pid for pid, parent, rss in table if parent in owned}
                if children <= owned:
                    break
                owned.update(children)
            resources.append({"at": datetime.now(timezone.utc).isoformat(), "elapsed_seconds": time.monotonic() - started,
                              "processes": len(owned), "summed_rss_kib": sum(rss for pid, parent, rss in table if pid in owned)})
            (output / "soak-resources.json").write_text(json.dumps(resources, indent=2) + "\n")

    p4.ModelFixture.do_POST = paced_post
    p4.wait_for_packaged_page = observed_wait
    p4.distribution = observed_distribution
    sys.argv = [__file__, "--exe", str(args.exe), "--output", str(output), "--samples", str(args.samples)]
    threading.Thread(target=heartbeat, daemon=True).start()
    report = {"scope": __doc__, "formal_model_quality_samples": 0, "requested_duration_seconds": args.duration_seconds,
              "requested_samples": args.samples, "budgets": {"js_heap_bytes": 512 * 1024 ** 2, "summed_process_rss_kib": 2 * 1024 ** 2}, "passed": False}
    try:
        p4.main()
        # P4.main returns None on success and raises on failure. Its JSON
        # report is the acceptance result; None is not an exit status.
        lifecycle = json.loads((output / "report.json").read_text())
        lifecycle_checks = lifecycle.get("checks", [])
        lifecycle_passed = lifecycle.get("passed") is True and bool(lifecycle_checks) and all(item.get("passed") is True for item in lifecycle_checks)
        span = generations[-1]["monotonic"] - generations[0]["monotonic"] if len(generations) > 1 else 0
        samples = page_samples[0] if page_samples else []
        checks = {
            "p4_lifecycle_checks": lifecycle_passed,
            "actual_elapsed_duration": span >= args.duration_seconds - .1 and len(generations) == args.samples,
            "no_unhandled_browser_errors": not browser_errors,
            "periodic_resource_samples": len(resources) >= int(args.duration_seconds / 30) - 2,
            "bounded_process_rss": bool(resources) and max(v["summed_rss_kib"] for v in resources) <= report["budgets"]["summed_process_rss_kib"],
            "bounded_observed_js_heap": bool(samples) and all(v["heapBytes"] is not None and v["heapBytes"] <= report["budgets"]["js_heap_bytes"] for v in samples),
        }
        report.update(checks=checks, measured_generation_span_seconds=span, lifecycle_passed=lifecycle_passed, passed=all(checks.values()))
    except (Exception, SystemExit) as error:
        report["error"] = type(error).__name__ + ": " + str(error)
    finally:
        stop.set()
        report.update(elapsed_seconds=time.monotonic() - started, generations=generations, resources=resources, browser_errors=browser_errors)
        if output.is_dir():
            (output / "soak-report.json").write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps({k: v for k, v in report.items() if k not in ("resources", "generations")}), flush=True)
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
