"""Exercise the final Python Context Engine through a packaged Reverie SDK bridge."""

import argparse
import json
import os
from pathlib import Path
from queue import Empty, Queue
import subprocess
from tempfile import TemporaryDirectory, TemporaryFile
from threading import Thread


def verify(executable: Path, directory: Path, timeout: float) -> dict:
    root = directory / "workspace"
    root.mkdir()
    (root / "billing.py").write_text(
        "class QuartzBillingPipeline:\n    def verifyInvoice(self):\n        return 'verified'\n", encoding="utf-8",
    )
    app = directory / "app"
    app.mkdir()
    env = {**os.environ, "REVERIE_APP_ROOT": str(app), "PYTHONIOENCODING": "utf-8"}
    command = [str(executable), "--context-engine"]
    version = subprocess.run([*command, "--version"], cwd=directory, env=env,
                             capture_output=True, text=True, encoding="utf-8", timeout=timeout, check=True).stdout.strip()
    if not version.startswith("reverie-context-engine ") or not version.endswith(" (python)"):
        raise RuntimeError(f"Unexpected Context Engine version output: {version}")

    with TemporaryFile(dir=directory) as stderr:
        process = subprocess.Popen([str(executable), "--sdk-bridge"], cwd=root, env=env,
                                   stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=stderr,
                                   text=True, encoding="utf-8")
        messages = Queue()

        def read_messages():
            try:
                for line in process.stdout:
                    messages.put(line)
            finally:
                messages.put(None)

        def receive(request_id):
            while True:
                try:
                    line = messages.get(timeout=timeout)
                except Empty as error:
                    raise RuntimeError(f"SDK bridge timed out on {request_id}") from error
                if line is None:
                    stderr.seek(0)
                    raise RuntimeError(f"SDK bridge exited: {stderr.read().decode('utf-8', errors='replace')}")
                value = json.loads(line)
                if value.get("id") == request_id:
                    if value.get("type") == "error":
                        raise RuntimeError(value["error"])
                    return value

        def request(action, **payload):
            process.stdin.write(json.dumps({"id": action, "action": action, "payload": payload}) + "\n")
            process.stdin.flush()
            return receive(action)

        reader = Thread(target=read_messages, daemon=True)
        reader.start()
        try:
            if receive(None).get("type") != "ready":
                raise RuntimeError("SDK bridge did not emit ready")
            request("initialize", projectRoot=str(root), deferPayloads=True)
            indexed = request("indexWorkspace")["result"]
            if indexed["files_parsed"] != 1 or indexed["fatal_errors"]:
                raise RuntimeError(f"Packaged SDK did not index the fixture: {indexed}")
            status = request("getContextStatus")["context_engine"]
            if status["backend"] != "python" or status["files"] != 1:
                raise RuntimeError(f"Packaged SDK selected the wrong index: {status}")
            mentions = request("workspaceMentions", query="QuartzBillingPipeline verifyInvoice", limit=8)["items"]
            if not any(item.get("path") == "billing.py" for item in mentions):
                raise RuntimeError(f"Packaged retrieval did not return the fixture: {mentions}")
            request("shutdown")
            if process.wait(timeout=timeout) != 0:
                raise RuntimeError("Packaged SDK failed during shutdown")
        finally:
            if process.poll() is None:
                process.kill()
                process.wait()
            process.stdin.close()
            process.stdout.close()
            reader.join(timeout=5)

    databases = list(app.rglob("python-search.sqlite3"))
    if len(databases) != 1:
        raise RuntimeError(f"Unexpected Python databases: {databases}")
    queried = subprocess.run([*command, "chunks", str(databases[0]), "verifyInvoice"], cwd=directory, env=env,
                             capture_output=True, text=True, encoding="utf-8", timeout=timeout, check=True)
    hits = json.loads(queried.stdout)
    if not hits or hits[0]["file_path"] != "billing.py" or hits[0]["start_line"] != 2:
        raise RuntimeError(f"Unexpected Python symbol hits: {hits}")

    begin = {"op": "begin", "root": "service-workspace", "replace": False, "expected_revision": 0}
    document = {"path": "billing.py", "size": 12, "modified_ns": 1, "body": "billing"}
    requests = [begin, {"op": "apply", "removed": [], "documents": [document]}, {"op": "commit"},
                {**begin, "replace": "false", "expected_revision": 1}, {"op": "commit"}, {"op": "state"},
                {"op": "search", "weights": [["billing", 1.0]], "limit": 10, "chunks": False,
                 "expected_revision": 1},
                {**begin, "replace": True, "expected_revision": 1},
                {"op": "apply", "removed": [], "documents": [{**document, "body": "transport"}]},
                "{", {"op": "commit"}, {"op": "state"},
                {"op": "search", "weights": [["transport", 1.0]], "limit": 10, "chunks": False,
                 "expected_revision": 2}]
    payload = "\n".join(item if isinstance(item, str) else json.dumps(item) for item in requests) + "\n"
    served = subprocess.run([*command, "serve", str(directory / "service.sqlite3")], input=payload,
                            cwd=directory, env=env, capture_output=True, encoding="utf-8",
                            timeout=timeout, check=True)
    responses = [json.loads(line) for line in served.stdout.splitlines()]
    if len(responses) != len(requests) or "error" not in responses[3] or "error" not in responses[4]:
        raise RuntimeError(f"Packaged service accepted an invalid replacement request: {responses}")
    if responses[5].get("result", {}).get("revision") != 1 or not responses[6].get("result"):
        raise RuntimeError(f"Packaged service altered the committed index: {responses}")
    if ("error" not in responses[9] or responses[10].get("result", {}).get("revision") != 2
            or responses[11].get("result") != responses[10].get("result")
            or not responses[12].get("result") or responses[12]["result"][0]["file_path"] != "billing.py"):
        raise RuntimeError(f"Packaged service cancelled a valid pending update: {responses}")
    return {"version": version, "backend": status["backend"], "files": status["files"], "hit": hits[0],
            "service_contract": {"invalid_replace_rejected": True, "pending_update_committed": True,
                                 "revision": responses[11]["result"]["revision"]}}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--executable", type=Path, required=True)
    parser.add_argument("--timeout", type=float, default=90)
    parser.add_argument("--work-dir", type=Path)
    args = parser.parse_args()
    with TemporaryDirectory(prefix="context-engine-", dir=args.work_dir) as temporary:
        report = verify(args.executable.resolve(), Path(temporary).resolve(), args.timeout)
    print(json.dumps(report, ensure_ascii=False))


if __name__ == "__main__":
    main()
