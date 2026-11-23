"""Audit-only measurement of the archived, released Python executable.

Fresh-profile startup is observed through SDK initialize. Prewarmed-profile
startup uses the same profile before any index exists. Index measurements wait
for the complete indexWorkspace response; warm trials rebuild every file in
the same running process. Filesystem cache state is not controlled.
"""
import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import platform
import queue
import sqlite3
import statistics
import subprocess
import sys
import threading
import time
import traceback

import psutil

sys.stdout.reconfigure(encoding="utf-8")
ROOT = Path.cwd().resolve()
SOURCE = "070fa25b07692c90c56a6b00a9a969ff2abb7804"
CORPUS = ROOT / ".runtime/phase0B/corpus"
EXPECTED_EXE = "4ffe83790c184707ad3f77ef5fd0de68d779889d1636aaeffcc4da40694b442d"


def digest(file):
    value = hashlib.sha256()
    with file.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            value.update(block)
    return value.hexdigest()


def write_json(file, data):
    file.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def seed(directory):
    directory.mkdir()
    for name in ("temp", "roaming", "local", "app/.reverie"):
        (directory / name).mkdir(parents=True)
    # Explicitly selected no-index scenario. All other behavior uses release
    # defaults; no real provider or secret is needed for startup and indexing.
    write_json(directory / "app/.reverie/config.json", {"auto_index": False})
    env = dict(os.environ)
    for key in list(env):
        if key.upper().endswith(("_API_KEY", "_TOKEN")) or key.startswith(("PYTHON", "VIRTUAL_ENV", "CONDA")):
            env.pop(key, None)
    env.update(TEMP=str(directory / "temp"), TMP=str(directory / "temp"),
               APPDATA=str(directory / "roaming"), LOCALAPPDATA=str(directory / "local"),
               REVERIE_APP_ROOT=str(directory / "app"), GIT_CEILING_DIRECTORIES=str(CORPUS),
               PYTHONUTF8="1", PYTHONIOENCODING="utf-8")
    return env


class Bridge:
    def __init__(self, executable, directory, env):
        self.directory, self.sequence, self.events = directory, 0, []
        self.inbox = queue.Queue()
        self.log = (directory / "bridge.jsonl").open("a", encoding="utf-8")
        self.error_log = (directory / "bridge.stderr.log").open("a", encoding="utf-8")
        self.started = time.perf_counter_ns()
        self.process = subprocess.Popen([str(executable), "--sdk-bridge"], cwd=CORPUS,
            env=env, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=self.error_log,
            text=True, encoding="utf-8", creationflags=subprocess.CREATE_NO_WINDOW)
        self.resource = psutil.Process(self.process.pid)
        self.owned = []
        self.reader = threading.Thread(target=self.read, daemon=True)
        self.reader.start()
        self.ready = self.wait(lambda message: message.get("type") == "ready", 120)
        self.hello_ms = (time.perf_counter_ns() - self.started) / 1e6

    def read(self):
        try:
            for line in self.process.stdout:
                self.log.write(line)
                self.log.flush()
                self.inbox.put((time.perf_counter_ns(), json.loads(line)))
        except Exception as error:
            self.inbox.put((None, error))
        finally:
            self.inbox.put((None, EOFError("Bridge closed")))

    def wait(self, matches, timeout):
        deadline = time.monotonic() + timeout
        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise TimeoutError("No matching final SDK response")
            observed, message = self.inbox.get(timeout=remaining)
            if isinstance(message, Exception):
                raise message
            self.events.append((observed, message))
            if matches(message):
                return observed, message

    def request(self, action, payload=None):
        self.sequence += 1
        request_id = str(self.sequence)
        start = time.perf_counter_ns()
        self.process.stdin.write(json.dumps({"id": request_id, "action": action,
                                           "payload": payload or {}}, ensure_ascii=False) + "\n")
        self.process.stdin.flush()
        stop, message = self.wait(lambda value: str(value.get("id")) == request_id
                                  and value.get("type") != "event"
                                  and not str(value.get("type", "")).endswith(".event"), 300)
        if message.get("type") == "error":
            raise RuntimeError(str(message.get("error") or message))
        return {"request_ms": (stop - start) / 1e6, "response": message}

    def close(self):
        if self.process.poll() is not None:
            self.log.close()
            self.error_log.close()
            return {"already_exited": True, "exit_code": self.process.returncode}
        try:
            children = self.resource.children(recursive=True)
            self.owned = [(child.pid, child.create_time()) for child in children]
            child_identities = [{"pid": child.pid, "created": child.create_time(), "name": child.name()}
                                for child in children]
            response = self.request("shutdown")
            self.process.stdin.close()
            self.process.wait(timeout=30)
            self.reader.join(timeout=5)
            if self.process.returncode != 0:
                raise RuntimeError(f"Bridge exited with {self.process.returncode}")
            waiting = time.perf_counter_ns()
            psutil.wait_procs(children, timeout=30)
            child_wait_ms = (time.perf_counter_ns() - waiting) / 1e6
            survivors = []
            for pid, created in self.owned:
                try:
                    current = psutil.Process(pid)
                    if current.create_time() == created:
                        survivors.append(pid)
                except psutil.NoSuchProcess:
                    pass
            if survivors:
                raise RuntimeError(f"Owned processes survived shutdown: {survivors}")
            return {"exit_code": 0, "owned_survivors": survivors, "owned_children": child_identities,
                    "child_wait_ms": child_wait_ms,
                    "shutdown_request_ms": response["request_ms"]}
        finally:
            if self.process.poll() is None:
                self.process.terminate()
                self.process.wait(timeout=30)
            self.log.close()
            self.error_log.close()


def distribution(values):
    ordered = sorted(values)
    return {"n": len(values), "median_ms": statistics.median(ordered),
            "p95_ms": ordered[(len(ordered) * 95 + 99) // 100 - 1],
            "p95_method": "nearest rank", "samples_ms": values}


def persisted_index(directory):
    databases = list((directory / "app/.reverie/projects").rglob("python-search.sqlite3"))
    if len(databases) != 1:
        raise RuntimeError("Expected one isolated project index")
    database = databases[0]
    reader = sqlite3.connect(database.resolve().as_uri() + "?mode=ro", uri=True)
    try:
        root, revision = reader.execute("SELECT root,revision FROM state WHERE id=1").fetchone()
        files = reader.execute("SELECT COUNT(*) FROM files WHERE indexed=1").fetchone()[0]
        scanned = reader.execute("SELECT COUNT(*) FROM files").fetchone()[0]
    finally:
        reader.close()
    snapshot = database.parent / "python-snapshots" / str(revision)
    if Path(root).resolve() != CORPUS or not (snapshot / "index.json").is_file() or not (snapshot / "files.json").is_file():
        raise RuntimeError("The committed index and matching snapshot are not complete")
    snapshot_files = json.loads((snapshot / "files.json").read_bytes())
    return {"revision": revision, "searchable_files": files, "scanned_files": scanned,
            "parsed_files": len(snapshot_files),
            "snapshot_index_sha256": digest(snapshot / "index.json"),
            "snapshot_files_sha256": digest(snapshot / "files.json")}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--exe", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--count", type=int, default=30)
    parser.add_argument("--warm-only", action="store_true")
    args = parser.parse_args()
    output = args.output.resolve()
    if not output.is_relative_to(ROOT / ".runtime") or output.exists() or args.count < 1:
        parser.error("Use a new .runtime output directory and a positive count")
    assert digest(args.exe) == EXPECTED_EXE, "Released executable identity mismatch"
    manifest_file = ROOT / "testdata/context-evaluation/frozen-corpus-v1.json"
    manifest = json.loads(manifest_file.read_bytes())
    for file in manifest["files"]:
        assert digest(CORPUS / file["repo_relative_path"]) == file["working_tree_sha256"]
    output.mkdir(parents=True)
    report = {"schema": "reverie.python-package-baseline.v1", "source_commit": SOURCE,
              "exe_sha256": EXPECTED_EXE, "harness_sha256": digest(Path(__file__)),
              "corpus_manifest_sha256": digest(manifest_file), "started_at": datetime.now(timezone.utc).isoformat(),
              "method": __doc__, "hardware": {"platform": platform.platform(),
                  "physical_cores": psutil.cpu_count(logical=False), "logical_cores": psutil.cpu_count(),
                  "memory_bytes": psutil.virtual_memory().total},
              "formal": args.count >= 30, "no_index": True, "passed": False,
              "startups": [], "cold_indexes": [], "warm_indexes": []}
    write_json(output / "contract.json", report)
    bridge = None
    try:
        profiles = []
        for trial in (range(args.count) if not args.warm_only else ()):
            directory = output / f"startup-{trial + 1:02}"
            env = seed(directory)
            profiles.append((directory, env))
            for group in ("fresh_profile", "prewarmed_profile"):
                bridge = Bridge(args.exe.resolve(), directory, env)
                response = bridge.request("initialize", {"projectRoot": str(CORPUS), "deferPayloads": True})
                total = (time.perf_counter_ns() - bridge.started) / 1e6
                assert response["response"]["type"] == "state"
                row = {"trial": trial + 1, "group": group, "hello_ms": bridge.hello_ms,
                       "initialize_ms": response["request_ms"], "kernel_usable_ms": total,
                       "cpu_percent_after": psutil.cpu_percent(interval=None),
                       "close": bridge.close()}
                bridge = None
                report["startups"].append(row)
                write_json(output / "progress.json", report)
                print(json.dumps({"phase": "startup", **row}), flush=True)
        for trial in (range(args.count) if not args.warm_only else ()):
            directory = output / f"index-{trial + 1:02}"
            env = seed(directory)
            bridge = Bridge(args.exe.resolve(), directory, env)
            bridge.request("initialize", {"projectRoot": str(CORPUS), "deferPayloads": True})
            row = bridge.request("indexWorkspace")
            result = row["response"]["result"]
            assert result["files_parsed"] == 1451 and result["files_skipped"] == 3
            assert not result.get("fatal_errors") and not result.get("failed_files")
            row.update(trial=trial + 1, group="fresh_process_missing_index")
            row["persisted_index"] = persisted_index(directory)
            row["close"] = bridge.close()
            bridge = None
            report["cold_indexes"].append(row)
            write_json(output / "progress.json", report)
            print(json.dumps({"phase": "index", "group": row["group"], "trial": trial + 1,
                              "request_ms": row["request_ms"], "files_parsed": result["files_parsed"]}), flush=True)
        directory = output / "warm-index"
        env = seed(directory)
        bridge = Bridge(args.exe.resolve(), directory, env)
        bridge.request("initialize", {"projectRoot": str(CORPUS), "deferPayloads": True})
        report["warmup_index"] = bridge.request("indexWorkspace")
        previous = persisted_index(directory)
        report["warmup_persisted_index"] = previous
        report["inter_request_settle_ms"] = 100
        report["warm_only"] = args.warm_only
        for trial in range(args.count):
            # Separate successive completed requests beyond Windows' legacy
            # monotonic-clock tick. This wait is outside the timed request.
            time.sleep(.1)
            row = bridge.request("indexWorkspace")
            result = row["response"]["result"]
            assert result["files_parsed"] == 1451 and result["files_skipped"] == 3
            assert not result.get("fatal_errors") and not result.get("failed_files")
            current = persisted_index(directory)
            if current["revision"] != previous["revision"] + 1 or (
                current["searchable_files"], current["scanned_files"], current["parsed_files"]
            ) != (1449, 1454, 1451):
                raise RuntimeError("The request did not complete one full persistent index rebuild")
            if row["request_ms"] + 100 < result["total_time_ms"]:
                raise RuntimeError("A previous index result was returned instead of a complete timed rebuild")
            row["persisted_index"] = current
            previous = current
            row.update(trial=trial + 1, group="same_process_complete_rebuild")
            report["warm_indexes"].append(row)
            write_json(output / "progress.json", report)
            print(json.dumps({"phase": "index", "group": row["group"], "trial": trial + 1,
                              "request_ms": row["request_ms"], "files_parsed": result["files_parsed"]}), flush=True)
        report["warm_close"] = bridge.close()
        bridge = None
        assert digest(args.exe) == EXPECTED_EXE
        report["distributions"] = {"warm_index": distribution([item["request_ms"] for item in report["warm_indexes"]])}
        if not args.warm_only:
            report["distributions"].update({**{group: distribution([item["kernel_usable_ms"] for item in report["startups"]
                if item["group"] == group]) for group in ("fresh_profile", "prewarmed_profile")},
                "cold_index": distribution([item["request_ms"] for item in report["cold_indexes"]])})
        report["passed"] = True
    except Exception as error:
        report["error"] = str(error)
        report["traceback"] = traceback.format_exc()
        raise
    finally:
        if bridge is not None:
            try:
                report["failure_cleanup"] = bridge.close()
            except Exception as error:
                report["cleanup_error"] = str(error)
        report["finished_at"] = datetime.now(timezone.utc).isoformat()
        write_json(output / "report.json", report)
    print(json.dumps({"passed": report["passed"], "formal": report["formal"], "output": str(output)}), flush=True)


if __name__ == "__main__":
    main()
