from __future__ import annotations

import json
import os
import shutil
import subprocess
import time
from pathlib import Path

import pytest

from reverie.rats import RatsRuntime


ENGINE_BIN = str(os.environ.get("REVERIE_RATS_ENGINE_BIN", "")).strip()


@pytest.mark.skipif(not ENGINE_BIN, reason="Set REVERIE_RATS_ENGINE_BIN to run the real Engine/Cli RTP E2E.")
def test_cli_consumes_real_engine_rtp_task_lifecycle() -> None:
    launch_binary = Path(ENGINE_BIN).resolve()
    if not launch_binary.is_file():
        pytest.fail(f"REVERIE_RATS_ENGINE_BIN does not point to a file: {launch_binary}")
    binary = launch_binary
    if launch_binary.name.lower().endswith(".console.exe"):
        binary = launch_binary.with_name(launch_binary.name[: -len(".console.exe")] + ".exe")
    if not binary.is_file():
        pytest.fail(f"The Engine provider executable beside the console wrapper is missing: {binary}")
    engine_root = launch_binary.parent
    local_root = engine_root / "ReverieLocal"
    project_root = local_root / "Projects" / "RatsCliTaskE2E"
    test_temp = local_root / "TestTemp"
    cli_state_root = test_temp / "RatsCliTaskPython"
    log_path = test_temp / "rats_cli_task_engine.log"
    if project_root.exists():
        shutil.rmtree(project_root)
    project_root.mkdir(parents=True, exist_ok=True)
    test_temp.mkdir(parents=True, exist_ok=True)
    (project_root / "project.godot").write_text(
        '; Reverie-Cli RTP task fixture.\nconfig_version=5\n\n[application]\nconfig/name="Rats CLI Task E2E"\nrun/main_scene="res://main.tscn"\nconfig/features=PackedStringArray("4.8", "GL Compatibility")\n',
        encoding="utf-8",
    )
    (project_root / "main.tscn").write_text(
        "[gd_scene format=3]\n\n[node name=\"RatsCliTaskFixture\" type=\"Node2D\"]\n",
        encoding="utf-8",
    )
    env = os.environ.copy()
    env.update(
        {
            "TEMP": str(test_temp),
            "TMP": str(test_temp),
            "REVERIE_RATS": "1",
            "REVERIE_RATS_PORT": "0",
            "REVERIE_AI_BRIDGE": "0",
        }
    )
    process = None
    log = log_path.open("w", encoding="utf-8")
    runtime = RatsRuntime(cli_state_root, request_timeout=2.0, probe_timeout=0.5, tool_timeout=15.0)
    try:
        process = subprocess.Popen(
            [str(launch_binary), "--editor", "--headless", "--path", str(project_root), "--quit-after", "900"],
            cwd=engine_root,
            env=env,
            stdout=log,
            stderr=subprocess.STDOUT,
        )
        runtime.register_provider_executable("reverie.engine", binary)
        state = {}
        deadline = time.time() + 45.0
        while time.time() < deadline:
            state = runtime.refresh()
            if state.get("services"):
                break
            if process.poll() is not None:
                pytest.fail(f"Engine exited before discovery with code {process.returncode}: {log_path.read_text(encoding='utf-8', errors='replace')[-2000:]}")
            time.sleep(0.1)
        assert state.get("services"), state
        state = runtime.set_provider_enabled("reverie.engine", binary, True, ["read", "run"])
        service = next(item for item in state["services"] if item["serviceId"])
        assert service["connection"] == "connected", service
        service_id = service["serviceId"]

        started = runtime.call_tool(
            service_id,
            "run.play",
            {"mode": "headless", "timeout_ms": 5_000},
            provider_id="reverie.engine",
            deadline_ms=30_000,
            idempotency_key="cli-engine-task-e2e-1",
        )
        task = started.get("task", {})
        task_id = task.get("task_id", "")
        assert started.get("output", {}).get("running") is True and task_id

        events = runtime.task_events(service_id, task_id, provider_id="reverie.engine")
        assert events.get("schema") == "reverie.rtp.task/1"
        assert events.get("events", [])[0].get("type") == "task.started"
        status = runtime.task_status(service_id, task_id, provider_id="reverie.engine")
        assert status.get("task_id") == task_id
        cancelled = runtime.cancel_task(service_id, task_id, provider_id="reverie.engine")
        assert cancelled.get("cancelled") is True and cancelled.get("output", {}).get("running") is False
        logs = runtime.task_logs(service_id, task_id, provider_id="reverie.engine")
        assert logs.get("task_id") == task_id and "started" in str(logs.get("text", ""))

        tasks = runtime.sync_tasks(service_id=service_id, provider_id="reverie.engine")
        tracked = next(item for item in tasks if item.get("task_id") == task_id)
        assert tracked.get("status", {}).get("running") is False
        diagnostics = [
            json.loads(line)
            for line in runtime.diagnostics_path.read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]
        task_diagnostics = [entry for entry in diagnostics if entry.get("taskId") == task_id]
        assert task_diagnostics and all(entry.get("auditId") and entry.get("resultSha256") for entry in task_diagnostics)
        assert runtime._tasks
    finally:
        runtime.shutdown()
        if process is not None and process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=15)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=15)
        log.close()
        if project_root.exists():
            shutil.rmtree(project_root)
