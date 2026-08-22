from __future__ import annotations

import json
import hashlib
import os
import shutil
import socket
import subprocess
import sys
import threading
import time
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest

import reverie.rats as rats_module
from _engine_pairing import discover_engine_binary, engine_pairing_skip_reason
from reverie.agent.tool_executor import ToolExecutor
from reverie.rats import (
    RATS_PROTOCOL,
    RATS_SUPPORTED_PROVIDERS,
    RatsClientError,
    RatsDescriptor,
    RatsProviderRegistry,
    RatsProviderSpec,
    RatsRuntime,
    _RatsSession,
    parse_rats_descriptor,
)


CONTROL_TOKEN = "a" * 64
SESSION_TOKEN = "b" * 64

ENGINE_BINARY = discover_engine_binary()


def _allow_test_process(_pid: int, _executable: Path) -> bool:
    return True


def _test_provider_registry(
    process_validator=_allow_test_process,
) -> RatsProviderRegistry:
    return RatsProviderRegistry(
        {
            "reverie.engine": RatsProviderSpec(
                provider_id="reverie.engine",
                product="Reverie Engine",
                service_kinds=("builtin",),
                executable_validator=lambda executable: executable.is_file(),
                process_validator=process_validator,
                discovery_root_resolver=lambda executable: executable.parent / "ReverieLocal" / "RATS" / "Services",
                permission_classes=RATS_SUPPORTED_PROVIDERS["reverie.engine"].permission_classes,
                label="Reverie Engine Test Fixture",
                tool_tags=("reverie-engine", "test-fixture"),
            ),
        }
    )


TEST_PROVIDER_REGISTRY = _test_provider_registry()


def _test_root(name: str) -> Path:
    root = Path(__file__).resolve().parents[2] / "dist" / ".reverie" / "test-temp" / f"rats-{name}-{uuid.uuid4().hex}"
    root.mkdir(parents=True, exist_ok=True)
    return root


class _RatsHandler(BaseHTTPRequestHandler):
    events: list[str] = []

    def log_message(self, _format: str, *_args) -> None:
        return

    def _reply(self, status: int, request_id: str, *, result=None, code="", message="") -> None:
        payload = {"id": request_id, "protocol": RATS_PROTOCOL, "ok": status < 400}
        if status < 400:
            response_value = result or {}
            payload["result"] = response_value
        else:
            response_value = {"code": code or "request_failed", "message": message or "failed"}
            payload["error"] = response_value
        payload["audit_id"] = f"audit-{uuid.uuid4().hex[:24]}"
        payload["result_sha256"] = hashlib.sha256(
            json.dumps(response_value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
        ).hexdigest()
        operation = str(getattr(self, "_current_operation", ""))
        response_id_mode = self.server.response_id_modes.get(operation, "valid")
        if response_id_mode == "missing":
            payload.pop("id", None)
        elif response_id_mode == "mismatch":
            payload["id"] = f"mismatched-{request_id}"
        result_hash_mode = self.server.result_hash_modes.get(operation, "valid")
        if result_hash_mode == "missing":
            payload.pop("result_sha256", None)
        elif result_hash_mode == "mismatch":
            payload["result_sha256"] = "0" * 64
        body = json.dumps(
            payload,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    @staticmethod
    def _definition(name: str):
        return {
            "name": name,
            "version": "1",
            "permission": "read",
            "dry_run": True,
            "summary": f"Native {name} tool",
            "category": name.split(".", 1)[0] if "." in name else "system",
            "tags": ["native", "test"],
            "schema_available": True,
            "main_thread": name != "ping",
            "signature": f"sig-{name}",
            "request_schema": {
                "type": "object",
                "properties": {"message": {"type": "string"}} if name == "ping" else {},
                "required": [],
                "additionalProperties": False,
            },
            "response_schema": {"type": "object"},
        }

    def do_POST(self) -> None:
        body = json.loads(self.rfile.read(int(self.headers.get("Content-Length", "0"))).decode("utf-8"))
        self.server.requests.append(body)
        request_id = str(body.get("id") or "")
        operation = str(body.get("op") or "")
        self._current_operation = operation
        args = body.get("args") if isinstance(body.get("args"), dict) else {}
        type(self).events.append(operation)
        if body.get("protocol") != RATS_PROTOCOL:
            self._reply(409, request_id, code="protocol_mismatch")
            return
        if operation == "hello":
            self._reply(
                200,
                request_id,
                result={
                    "service_id": self.server.service_id,
                    "protocol": RATS_PROTOCOL,
                    "provider_id": self.server.provider_id,
                    "service_kind": self.server.service_kind,
                    "product": self.server.product,
                },
            )
            return
        if operation == "session.open":
            if self.headers.get("X-Reverie-RATS-Control") != self.server.control_token:
                self._reply(401, request_id, code="unauthorized")
                return
            self.server.session_open = True
            self._reply(
                200,
                request_id,
                result={
                    "session_token": self.server.session_token,
                    "permissions": args.get("permissions", ["read"]),
                    "tools": [
                        "ping",
                        "version",
                        "get_status",
                        "project.status",
                        "scene.read",
                        "run.play",
                        "run.status",
                        "run.stop",
                        "logs.read",
                    ],
                },
            )
            return
        if self.headers.get("X-Reverie-RTP-Session") != self.server.session_token or not self.server.session_open:
            self._reply(401, request_id, code="unauthorized")
            return
        if operation == "status":
            self._reply(200, request_id, result={"session_active": True})
        elif operation == "session.close":
            self.server.session_open = False
            self._reply(200, request_id, result={"closed": True})
        elif operation == "catalog.index":
            names = ["ping", "version", "get_status", "project.status", "scene.read", "run.play", "run.status", "run.stop", "logs.read"]
            self._reply(
                200,
                request_id,
                result={
                    "count": len(names),
                    "definitions_embedded": False,
                    "tools": [
                        {
                            "key": f"k-{name}",
                            "name": name,
                            "category": name.split(".", 1)[0] if "." in name else "system",
                            "summary": f"Native {name} tool",
                            "permission": "read",
                            "flags": ["dry_run"],
                            "schema": f"sig-{name}",
                        }
                        for name in names
                    ],
                },
            )
        elif operation == "catalog.describe":
            names = args.get("names", [])
            self._reply(200, request_id, result={"tools": [self._definition(str(name)) for name in names]})
        elif operation == "catalog.search":
            self._reply(
                200,
                request_id,
                result={"matches": [{"name": "scene.read", "summary": "Read scene", "category": "scene", "score": 500}]},
            )
        elif operation == "tool.call":
            tool_name = args.get("name")
            idempotency_key = str(body.get("idempotency_key") or "")
            request_material = dict(body)
            request_material.pop("id", None)
            if idempotency_key and idempotency_key in self.server.idempotency:
                previous_material, previous_result = self.server.idempotency[idempotency_key]
                if previous_material != request_material:
                    self._reply(400, request_id, code="idempotency_conflict", message="different request")
                    return
                replay = dict(previous_result)
                replay["idempotent_replay"] = True
                self._reply(200, request_id, result=replay)
                return
            if tool_name == "run.play":
                self.server.task = {
                    "task_id": "run-test-task-1",
                    "tool": "run.play",
                    "status_operation": "run.status",
                    "cancel_operation": "run.stop",
                    "deadline_msec": 0,
                    "first_event_sequence": 1,
                    "next_event_sequence": 2,
                }
                self.server.task_state = {"task_id": "run-test-task-1", "state": "running", "running": True, "progress": 0.0}
                result = {"tool": tool_name, "dry_run": False, "output": self.server.task_state, "task": self.server.task, "idempotent_replay": False}
                self._reply(200, request_id, result=result)
            elif tool_name == "logs.read":
                arguments = args.get("arguments", {})
                result = {
                        "tool": tool_name,
                        "dry_run": False,
                        "output": {
                            "task_id": arguments.get("task_id"),
                            "state": "running",
                            "running": True,
                            "text": "run-test-task-1 started\n",
                            "cursor_start": int(arguments.get("cursor", 0) or 0),
                            "cursor_end": 24,
                            "next_cursor": 24,
                            "truncated": False,
                            "has_more": False,
                        },
                    }
                self._reply(200, request_id, result=result)
            else:
                result = {"tool": tool_name, "dry_run": args.get("dry_run", False), "output": {"pong": True, "echo": args.get("arguments", {}).get("message")}, "idempotent_replay": False}
                self._reply(200, request_id, result=result)
            if idempotency_key:
                self.server.idempotency[idempotency_key] = (request_material, result)
        elif operation == "task.status":
            self._reply(
                200,
                request_id,
                result={
                    **self.server.task,
                    "state": self.server.task_state["state"],
                    "running": self.server.task_state["running"],
                    "progress": self.server.task_state["progress"],
                    "output": self.server.task_state,
                    "next_cursor": 2,
                },
            )
        elif operation == "task.events":
            events = [
                {"schema": "reverie.rtp.task/1", "task_id": "run-test-task-1", "sequence": 1, "type": "task.started", "payload": self.server.task_state},
                {"schema": "reverie.rtp.task/1", "task_id": "run-test-task-1", "sequence": 2, "type": "task.progress", "payload": {**self.server.task_state, "progress": 0.25}},
            ]
            cursor = int(args.get("cursor", 0) or 0)
            selected = [event for event in events if int(event["sequence"]) > cursor]
            self._reply(
                200,
                request_id,
                result={
                    "schema": "reverie.rtp.task/1",
                    "task_id": "run-test-task-1",
                    "cursor": cursor,
                    "next_cursor": int(selected[-1]["sequence"]) if selected else cursor,
                    "has_more": False,
                    "truncated": False,
                    "events": selected[: int(args.get("limit", 32) or 32)],
                },
            )
        elif operation == "task.cancel":
            self.server.task_state = {**self.server.task_state, "state": "stopped", "running": False, "progress": 1.0}
            self._reply(
                200,
                request_id,
                result={**self.server.task, "cancelled": True, "output": self.server.task_state},
            )
        else:
            self._reply(404, request_id, code="unknown_operation")


def _start_server(
    *,
    provider_id: str = "reverie.engine",
    service_kind: str = "builtin",
    hello_product: str = "Reverie Engine",
    service_suffix: str = "test",
    control_token: str = CONTROL_TOKEN,
    session_token: str = SESSION_TOKEN,
):
    _RatsHandler.events = []
    server = ThreadingHTTPServer(("127.0.0.1", 0), _RatsHandler)
    server.service_id = f"rats-{os.getpid()}-{service_suffix}"
    server.provider_id = provider_id
    server.service_kind = service_kind
    server.product = hello_product
    server.control_token = control_token
    server.session_token = session_token
    server.session_open = False
    server.task = {}
    server.task_state = {}
    server.requests = []
    server.idempotency = {}
    server.response_id_modes = {}
    server.result_hash_modes = {}
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return server, thread


def _client_descriptor(server: ThreadingHTTPServer) -> RatsDescriptor:
    executable = (Path.cwd() / "reverie.windows.editor.x86_64.exe").resolve()
    return RatsDescriptor(
        service_id=server.service_id,
        provider_id=server.provider_id,
        service_kind=server.service_kind,
        product=server.product,
        product_version="test",
        executable=executable,
        pid=os.getpid(),
        port=server.server_port,
        endpoint=f"http://127.0.0.1:{server.server_port}/rtp",
        descriptor_path=executable.parent / "ReverieLocal" / "RATS" / "Services" / f"{server.service_id}.json",
        catalog_revision="catalog-test",
        native_tool_count=5,
        started_utc="2026-07-29T00:00:00Z",
        control_token=server.control_token,
    )


def _runtime_with_fake_session(root: Path, suffix: str) -> tuple[RatsRuntime, _RatsSession]:
    runtime = RatsRuntime(root)
    executable = (root / "reverie.windows.editor.x86_64.exe").resolve()
    descriptor = RatsDescriptor(
        service_id=f"rats-{os.getpid()}-{suffix}",
        provider_id="reverie.engine",
        service_kind="builtin",
        product="Reverie Engine",
        product_version="test",
        executable=executable,
        pid=os.getpid(),
        port=1,
        endpoint="http://127.0.0.1:1/rtp",
        descriptor_path=executable.parent / "ReverieLocal" / "RATS" / "Services" / f"rats-{os.getpid()}-{suffix}.json",
        catalog_revision="catalog-test",
        native_tool_count=1,
        started_utc="2026-08-09T00:00:00Z",
        control_token=CONTROL_TOKEN,
    )
    session = _RatsSession(descriptor=descriptor, token=SESSION_TOKEN, permissions=["read"])
    with runtime._lock:
        runtime._sessions[(descriptor.provider_id, descriptor.service_id)] = session
    return runtime, session


def _configure_fake_discovery(
    runtime: RatsRuntime,
    descriptor: RatsDescriptor,
    monkeypatch: pytest.MonkeyPatch,
    *,
    enabled: bool,
) -> None:
    selection = {
        "providerId": descriptor.provider_id,
        "executable": str(descriptor.executable),
        "permissions": ["read"],
        "discoveryRoot": str(descriptor.descriptor_path.parent),
    }
    settings = {
        "schemaVersion": 2,
        "discoveryRoots": [],
        "enabledProviders": [selection] if enabled else [],
    }
    monkeypatch.setattr(runtime, "_read_settings", lambda: settings)
    monkeypatch.setattr(runtime, "_roots", lambda _settings: [])
    monkeypatch.setattr(
        rats_module,
        "discover_rats_descriptors",
        lambda _roots, _rejections, _registry: [descriptor],
    )


def _write_descriptor(
    services: Path,
    server: ThreadingHTTPServer,
    executable: Path,
    *,
    provider_id: str,
    service_kind: str,
    product: str,
    control_token: str,
) -> None:
    services.mkdir(parents=True, exist_ok=True)
    (services / f"{server.service_id}.json").write_text(
        json.dumps(
            {
                "schema": "reverie.rats.discovery/1",
                "protocol": RATS_PROTOCOL,
                "service_id": server.service_id,
                "provider_id": provider_id,
                "service_kind": service_kind,
                "product": product,
                "product_version": "test",
                "executable": str(executable.resolve()),
                "pid": os.getpid(),
                "port": server.server_port,
                "endpoint": f"http://127.0.0.1:{server.server_port}/rtp",
                "bind_address": "127.0.0.1",
                "catalog_revision": "catalog-test",
                "native_tool_count": 5,
                "started_utc": "2026-07-29T00:00:00Z",
                "control_token": control_token,
            }
        ),
        encoding="utf-8",
    )


def _descriptor_value(executable: Path, pid: int, *, service_id: str) -> dict:
    return {
        "schema": "reverie.rats.discovery/1",
        "protocol": RATS_PROTOCOL,
        "service_id": service_id,
        "provider_id": "reverie.engine",
        "service_kind": "builtin",
        "product": "Reverie Engine",
        "product_version": "test",
        "executable": str(executable.resolve()),
        "pid": pid,
        "port": 4545,
        "endpoint": "http://127.0.0.1:4545/rtp",
        "bind_address": "127.0.0.1",
        "catalog_revision": "catalog-test",
        "native_tool_count": 5,
        "started_utc": "2026-07-29T00:00:00Z",
        "control_token": CONTROL_TOKEN,
    }


def test_descriptor_validation_rejects_non_loopback_endpoint() -> None:
    descriptor = {
        "schema": "reverie.rats.discovery/1",
        "protocol": RATS_PROTOCOL,
        "service_id": "rats-123-test",
        "provider_id": "reverie.engine",
        "service_kind": "builtin",
        "product": "Reverie Engine",
        "bind_address": "0.0.0.0",
        "endpoint": "http://0.0.0.0:4545/rtp",
        "executable": str((Path.cwd() / "reverie.exe").resolve()),
        "pid": 123,
        "port": 4545,
        "control_token": CONTROL_TOKEN,
    }
    assert parse_rats_descriptor(descriptor, Path.cwd() / "rats-123-test.json") is None


@pytest.mark.skipif(os.name != "nt", reason="Reverie Engine provider identity is Windows-only.")
def test_production_reverie_provider_rejects_a_non_reverie_pe() -> None:
    executable = Path(sys.executable).resolve()
    assert executable.is_file()
    assert RATS_SUPPORTED_PROVIDERS["reverie.engine"].validate_executable(executable) is False


def test_provider_spec_preserves_legacy_optional_positional_arguments() -> None:
    spec = RatsProviderSpec(
        "legacy.provider",
        "Legacy Provider",
        ("builtin",),
        lambda executable: executable.is_file(),
        lambda executable: executable.parent / "Services",
        ("read",),
        "Legacy Provider",
        ("legacy-tag",),
        "Legacy executable error.",
    )

    assert spec.tool_tags == ("legacy-tag",)
    assert spec.executable_error == "Legacy executable error."
    assert spec.process_validator is rats_module._reverie_engine_process


@pytest.mark.skipif(
    os.name != "nt",
    reason=(
        "Terminal-wrapper normalization is Windows-only: the product-name check reads the "
        "Windows version resource, and off-Windows the validator deliberately accepts any file."
    ),
)
def test_reverie_terminal_selection_normalizes_only_a_verified_terminal_wrapper(monkeypatch: pytest.MonkeyPatch) -> None:
    root = _test_root("terminal-provider-normalization")
    terminal = root / "reverie.windows.editor.x86_64.terminal.exe"
    provider = root / "reverie.windows.editor.x86_64.exe"
    impostor = root / "impostor.terminal.exe"
    for path in (terminal, provider, impostor):
        path.write_bytes(b"test")

    product_names = {
        terminal: ("Reverie Engine Terminal",),
        provider: ("Reverie Engine",),
        impostor: ("Reverie Engine Terminal",),
    }
    monkeypatch.setattr(rats_module, "_windows_product_names", lambda executable: product_names.get(Path(executable), ()))

    try:
        spec = RATS_SUPPORTED_PROVIDERS["reverie.engine"]
        assert spec.normalize_executable(terminal) == provider
        assert spec.validate_executable(terminal) is True
        assert spec.discovery_root_for_executable(terminal) == provider.parent / "ReverieLocal" / "RATS" / "Services"
        assert spec.normalize_executable(impostor) == impostor
        assert spec.validate_executable(impostor) is False
    finally:
        shutil.rmtree(root, ignore_errors=True)


@pytest.mark.skipif(os.name != "nt", reason="Windows process image validation is required.")
def test_descriptor_rejects_a_dead_process_id() -> None:
    root = _test_root("dead-process-identity")
    child = subprocess.Popen(
        [sys.executable, "-c", "pass"],
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
    )
    dead_pid = child.pid
    child.wait(timeout=10)
    try:
        executable = root / "reverie.windows.editor.x86_64.exe"
        executable.write_bytes(b"test")
        registry = _test_provider_registry(
            process_validator=RATS_SUPPORTED_PROVIDERS["reverie.engine"].process_validator,
        )
        descriptor_path = executable.parent / "ReverieLocal" / "RATS" / "Services" / "rats-123-dead.json"
        assert parse_rats_descriptor(
            _descriptor_value(executable, dead_pid, service_id="rats-123-dead"),
            descriptor_path,
            registry,
        ) is None
    finally:
        shutil.rmtree(root, ignore_errors=True)


@pytest.mark.skipif(os.name != "nt", reason="Windows process image validation is required.")
def test_process_with_exit_code_259_is_not_mistaken_for_a_live_process() -> None:
    child = subprocess.Popen(
        [sys.executable, "-c", "import os; os._exit(259)"],
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
    )
    try:
        assert child.wait(timeout=10) == 259
        # Keep Popen's real process handle alive while checking the terminated object.
        assert rats_module._windows_process_image_from_handle(int(child._handle)) is None
        assert RATS_SUPPORTED_PROVIDERS["reverie.engine"].validate_process(
            child.pid,
            Path(sys.executable).resolve(),
        ) is False
    finally:
        if child.poll() is None:
            child.kill()
            child.wait(timeout=10)


@pytest.mark.skipif(os.name != "nt", reason="Windows process image validation is required.")
def test_descriptor_rejects_a_pid_whose_image_does_not_match_the_executable() -> None:
    root = _test_root("process-image-mismatch")
    try:
        executable = root / "reverie.windows.editor.x86_64.exe"
        executable.write_bytes(b"test")
        registry = _test_provider_registry(
            process_validator=RATS_SUPPORTED_PROVIDERS["reverie.engine"].process_validator,
        )
        descriptor_path = executable.parent / "ReverieLocal" / "RATS" / "Services" / "rats-123-mismatch.json"
        assert parse_rats_descriptor(
            _descriptor_value(executable, os.getpid(), service_id="rats-123-mismatch"),
            descriptor_path,
            registry,
        ) is None
    finally:
        shutil.rmtree(root, ignore_errors=True)


@pytest.mark.skipif(
    os.name != "nt" or ENGINE_BINARY is None,
    reason=engine_pairing_skip_reason(),
)
def test_production_reverie_provider_accepts_a_real_engine_binary_and_process() -> None:
    assert ENGINE_BINARY is not None
    if not ENGINE_BINARY.is_file():
        pytest.skip(f"Reverie Engine binary does not exist: {ENGINE_BINARY}")
    provider = RATS_SUPPORTED_PROVIDERS["reverie.engine"]
    assert provider.validate_executable(ENGINE_BINARY) is True

    root = _test_root("real-engine-process-identity")
    project = root / "project"
    project.mkdir(parents=True, exist_ok=True)
    (project / "project.godot").write_text(
        '; Reverie-Cli process identity fixture.\nconfig_version=5\n\n[application]\nconfig/name="RATS Identity"\n',
        encoding="utf-8",
    )
    environment = {
        **os.environ,
        "REVERIE_RATS": "0",
        "REVERIE_AI_BRIDGE": "0",
        "TEMP": str(root),
        "TMP": str(root),
    }
    process = subprocess.Popen(
        [str(ENGINE_BINARY), "--editor", "--headless", "--path", str(project), "--quit-after", "1200"],
        cwd=ENGINE_BINARY.parent,
        env=environment,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
    )
    try:
        assert process.poll() is None
        assert provider.validate_process(process.pid, ENGINE_BINARY) is True
    finally:
        if process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=10)
        shutil.rmtree(root, ignore_errors=True)


@pytest.mark.parametrize(("operation", "expected_status"), (("hello", 200), ("session.open", 401)))
@pytest.mark.parametrize(
    ("response_id_mode", "expected_code"),
    (("missing", "response_id_missing"), ("mismatch", "response_id_mismatch")),
)
def test_rtp_rejects_missing_or_mismatched_response_ids(
    operation: str,
    expected_status: int,
    response_id_mode: str,
    expected_code: str,
) -> None:
    root = _test_root(f"response-id-{operation}-{response_id_mode}")
    server, thread = _start_server(service_suffix="responseid")
    runtime = RatsRuntime(root)
    try:
        server.response_id_modes[operation] = response_id_mode
        with pytest.raises(RatsClientError) as failure:
            runtime._request(_client_descriptor(server), operation)
        assert failure.value.code == expected_code
        assert failure.value.status == expected_status
    finally:
        runtime.shutdown()
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)
        shutil.rmtree(root, ignore_errors=True)


@pytest.mark.parametrize(("operation", "expected_status"), (("hello", 200), ("session.open", 401)))
@pytest.mark.parametrize(
    ("result_hash_mode", "expected_code"),
    (("missing", "result_hash_missing"), ("mismatch", "result_hash_mismatch")),
)
def test_rtp_rejects_missing_or_mismatched_result_hashes(
    operation: str,
    expected_status: int,
    result_hash_mode: str,
    expected_code: str,
) -> None:
    root = _test_root(f"result-hash-{operation}-{result_hash_mode}")
    server, thread = _start_server(service_suffix="resulthash")
    runtime = RatsRuntime(root)
    try:
        server.result_hash_modes[operation] = result_hash_mode
        with pytest.raises(RatsClientError) as failure:
            runtime._request(_client_descriptor(server), operation)
        assert failure.value.code == expected_code
        assert failure.value.status == expected_status
    finally:
        runtime.shutdown()
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)
        shutil.rmtree(root, ignore_errors=True)


def test_runtime_owns_session_persists_locally_and_progressively_loads_tools() -> None:
    root = _test_root("runtime")
    server, thread = _start_server()
    try:
        engine_root = root / "engine"
        executable = engine_root / "reverie.windows.editor.x86_64.exe"
        executable.parent.mkdir(parents=True, exist_ok=True)
        executable.write_bytes(b"test")
        services = engine_root / "ReverieLocal" / "RATS" / "Services"
        services.mkdir(parents=True, exist_ok=True)
        descriptor_path = services / f"{server.service_id}.json"
        descriptor_path.write_text(
            json.dumps(
                {
                    "schema": "reverie.rats.discovery/1",
                    "protocol": RATS_PROTOCOL,
                    "service_id": server.service_id,
                    "provider_id": "reverie.engine",
                    "service_kind": "builtin",
                    "product": "Reverie Engine",
                    "product_version": "test",
                    "executable": str(executable.resolve()),
                    "pid": os.getpid(),
                    "port": server.server_port,
                    "endpoint": f"http://127.0.0.1:{server.server_port}/rtp",
                    "bind_address": "127.0.0.1",
                    "catalog_revision": "catalog-test",
                    "native_tool_count": 5,
                    "started_utc": "2026-07-29T00:00:00Z",
                    "control_token": CONTROL_TOKEN,
                }
            ),
            encoding="utf-8",
        )

        cli_root = root / "cli"
        runtime = RatsRuntime(cli_root, provider_registry=TEST_PROVIDER_REGISTRY)
        state = runtime.add_engine(executable)
        assert state["services"][0]["connection"] == "available"
        state = runtime.set_engine_enabled(executable, True, ["read"])
        service = state["services"][0]
        assert service["connection"] == "connected"
        assert service["sessionActive"] is True
        assert service["providerId"] == "reverie.engine"
        assert service["serviceKind"] == "builtin"
        assert service["probeLatencyMs"] >= 0
        assert state["supportedProviders"][0]["providerId"] == "reverie.engine"
        assert state["supportedProviders"][0]["serviceKind"] == "builtin"
        assert RATS_SUPPORTED_PROVIDERS["reverie.engine"].service_kind == "builtin"
        assert state["enabledProviders"] == [
            {
                "providerId": "reverie.engine",
                "executable": str(executable.resolve()),
                "permissions": ["read"],
                "discoveryRoot": str(services.resolve()),
            }
        ]
        assert state["scanDurationMs"] >= service["probeLatencyMs"]
        assert runtime.settings_path == cli_root / ".reverie" / "rats" / "settings.json"
        assert runtime.settings_path.is_file()
        assert Path(state["diagnosticsPath"]) == runtime.diagnostics_path
        assert runtime.diagnostics_path.is_file()
        assert any(item.get("event") == "discovery.complete" for item in state["diagnostics"])
        assert any(
            item.get("event") == "rtp.request" and item.get("operation") == "hello"
            for item in state["diagnostics"]
        )
        assert CONTROL_TOKEN not in runtime.settings_path.read_text(encoding="utf-8")
        assert SESSION_TOKEN not in runtime.settings_path.read_text(encoding="utf-8")
        diagnostics = runtime.diagnostics_path.read_text(encoding="utf-8")
        assert CONTROL_TOKEN not in diagnostics
        assert SESSION_TOKEN not in diagnostics

        executor = ToolExecutor(root)
        executor.update_context("rats_runtime", runtime)
        names = {schema["function"]["name"] for schema in executor.get_tool_schemas(mode="reverie")}
        assert "rats_catalog" in names
        assert "rats_reverie_engine_ping" in names
        assert "rats_reverie_engine_scene_read" not in names

        ping = executor.execute("rats_reverie_engine_ping", {"message": "stars"})
        assert ping.success is True
        assert ping.data == {"pong": True, "echo": "stars"}

        discovered = executor.execute("rats_catalog", {"operation": "search", "query": "read scene"})
        assert discovered.success is True
        names = {schema["function"]["name"] for schema in executor.get_tool_schemas(mode="reverie")}
        assert "rats_reverie_engine_scene_read" not in names, "a search alone must not spend a schema"

        loaded = executor.execute("rats_catalog", {"operation": "load", "names": ["scene.read"]})
        assert loaded.success is True
        names = {schema["function"]["name"] for schema in executor.get_tool_schemas(mode="reverie")}
        assert "rats_reverie_engine_scene_read" in names

        runtime.shutdown()
        assert "session.close" in _RatsHandler.events
        assert server.session_open is False
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)
        shutil.rmtree(root, ignore_errors=True)


def test_runtime_tracks_rtp_task_events_deadlines_cancellation_logs_and_idempotency() -> None:
    root = _test_root("task-lifecycle")
    server, thread = _start_server(service_suffix="task")
    try:
        executable = root / "engine" / "reverie.windows.editor.x86_64.exe"
        executable.parent.mkdir(parents=True, exist_ok=True)
        executable.write_bytes(b"test")
        services = executable.parent / "ReverieLocal" / "RATS" / "Services"
        _write_descriptor(
            services,
            server,
            executable,
            provider_id="reverie.engine",
            service_kind="builtin",
            product="Reverie Engine",
            control_token=CONTROL_TOKEN,
        )

        runtime = RatsRuntime(root / "cli", provider_registry=TEST_PROVIDER_REGISTRY)
        runtime.add_engine(executable)
        state = runtime.set_engine_enabled(executable, True, ["read", "run"])
        service_id = state["services"][0]["serviceId"]

        started = runtime.call_tool(
            service_id,
            "run.play",
            {"mode": "headless"},
            deadline_ms=30_000,
            idempotency_key="cli-task-start-1",
        )
        task = started["task"]
        task_id = task["task_id"]
        assert started["output"]["running"] is True
        request = next(item for item in server.requests if item.get("op") == "tool.call")
        assert request["deadline_ms"] == 30_000
        assert request["idempotency_key"] == "cli-task-start-1"

        replay = runtime.call_tool(
            service_id,
            "run.play",
            {"mode": "headless"},
            deadline_ms=30_000,
            idempotency_key="cli-task-start-1",
        )
        assert replay["idempotent_replay"] is True
        with pytest.raises(RatsClientError) as conflict:
            runtime.call_tool(
                service_id,
                "run.play",
                {"mode": "windowed"},
                idempotency_key="cli-task-start-1",
            )
        assert getattr(conflict.value, "code", "") == "idempotency_conflict"
        with pytest.raises(ValueError):
            runtime.call_tool(service_id, "run.play", {}, deadline_ms=120_001)

        events = runtime.task_events(service_id, task_id)
        assert events["schema"] == "reverie.rtp.task/1"
        assert [event["type"] for event in events["events"]] == ["task.started", "task.progress"]
        status = runtime.task_status(service_id, task_id)
        assert status["running"] is True and status["next_cursor"] == 2
        cancelled = runtime.cancel_task(service_id, task_id)
        assert cancelled["cancelled"] is True and cancelled["output"]["running"] is False
        logs = runtime.task_logs(service_id, task_id)
        assert logs["task_id"] == task_id and "started" in logs["text"]
        terminal_poll_count = sum(
            1 for request_item in server.requests
            if request_item.get("op") in {"task.status", "task.events"}
        )
        synced = runtime.sync_tasks(service_id=service_id)
        assert synced[0]["task_id"] == task_id and synced[0]["status"]["running"] is False
        assert synced[0]["events"]
        assert runtime.sync_tasks(service_id=service_id) == synced
        assert sum(
            1 for request_item in server.requests
            if request_item.get("op") in {"task.status", "task.events"}
        ) == terminal_poll_count

        diagnostic_entries = [
            json.loads(line)
            for line in runtime.diagnostics_path.read_text(encoding="utf-8").splitlines()
        ]
        diagnostics = next(entry for entry in reversed(diagnostic_entries) if entry.get("taskId") == task_id)
        assert diagnostics["event"] == "rtp.request"
        assert diagnostics["auditId"].startswith("audit-")
        assert diagnostics["resultSha256"]
        assert diagnostics["taskId"] == task_id
        runtime.shutdown()
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)
        shutil.rmtree(root, ignore_errors=True)


def test_generation_changes_when_a_same_named_definition_schema_changes() -> None:
    root = _test_root("definition-generation")
    try:
        runtime, session = _runtime_with_fake_session(root, "generation")
        session.definitions["ping"] = {
            "name": "ping",
            "permission": "read",
            "request_schema": {"type": "object", "properties": {}},
            "response_schema": {"type": "object"},
            "metadata": {"revision": 1},
        }
        with runtime._lock:
            runtime._update_generation()
            initial_generation = runtime.get_generation()
            session.definitions["ping"]["request_schema"]["properties"] = {
                "message": {"type": "string"},
            }
            runtime._update_generation()
            changed_generation = runtime.get_generation()

        assert changed_generation == initial_generation + 1
    finally:
        shutil.rmtree(root, ignore_errors=True)


def test_tool_executor_does_not_cache_a_stale_schema_across_a_concurrent_generation_update() -> None:
    root = _test_root("definition-snapshot-race")
    snapshot_captured = threading.Event()
    release_snapshot = threading.Event()
    try:
        runtime, session = _runtime_with_fake_session(root, "snapshotrace")
        with runtime._lock:
            runtime._has_refreshed = True
            session.definitions["ping"] = {
                "name": "ping",
                "permission": "read",
                "request_schema": {
                    "type": "object",
                    "properties": {"legacy": {"type": "string"}},
                },
                "response_schema": {"type": "object"},
            }
            runtime._update_generation()
            initial_generation = runtime._generation

        original_snapshot = runtime.get_tool_definitions_snapshot

        def gated_snapshot(force_refresh: bool = False):
            snapshot = original_snapshot(force_refresh=force_refresh)
            snapshot_captured.set()
            if not release_snapshot.wait(timeout=5):
                raise TimeoutError("test did not release the captured RATS definition snapshot")
            return snapshot

        def separate_generation_read_is_forbidden() -> int:
            raise AssertionError("ToolExecutor must consume the atomic RATS definition snapshot")

        runtime.get_tool_definitions_snapshot = gated_snapshot
        runtime.get_generation = separate_generation_read_is_forbidden
        executor = ToolExecutor(root)
        executor.update_context("rats_runtime", runtime, sync_dynamic=False)
        sync_thread = threading.Thread(target=executor._sync_rats_tools)
        sync_thread.start()
        assert snapshot_captured.wait(timeout=2)

        with runtime._lock:
            session.definitions["ping"] = {
                "name": "ping",
                "permission": "read",
                "request_schema": {
                    "type": "object",
                    "properties": {"current": {"type": "integer"}},
                },
                "response_schema": {"type": "object"},
            }
            runtime._update_generation()
            current_generation = runtime._generation
        release_snapshot.set()
        sync_thread.join(timeout=5)

        assert not sync_thread.is_alive()
        assert executor._rats_generation == initial_generation
        assert "legacy" in executor._tools["rats_reverie_engine_ping"].parameters["properties"]

        executor._sync_rats_tools()

        assert executor._rats_generation == current_generation
        parameters = executor._tools["rats_reverie_engine_ping"].parameters
        assert "current" in parameters["properties"]
        assert "legacy" not in parameters["properties"]
    finally:
        release_snapshot.set()
        sync_thread = locals().get("sync_thread")
        if sync_thread is not None:
            sync_thread.join(timeout=5)
        shutil.rmtree(root, ignore_errors=True)


def test_sync_tasks_skips_cached_terminal_tasks() -> None:
    root = _test_root("terminal-task-sync")
    try:
        runtime, session = _runtime_with_fake_session(root, "terminalsync")
        with runtime._lock:
            runtime._remember_task(session, {"task_id": "done-task", "tool": "run.play"})
            key = runtime._task_key(session, "done-task")
            runtime._tasks[key]["status"] = {
                "task_id": "done-task",
                "state": "stopped",
                "running": False,
            }
        operations: list[str] = []

        def unexpected_request(_descriptor, operation, *_args, **_kwargs):
            operations.append(operation)
            raise AssertionError(f"terminal task was polled with {operation}")

        runtime._request = unexpected_request
        first = runtime.sync_tasks()
        second = runtime.sync_tasks()

        assert first[0]["status"]["running"] is False
        assert second == first
        assert operations == []
    finally:
        shutil.rmtree(root, ignore_errors=True)


def test_task_history_evicts_the_oldest_terminal_task_but_keeps_all_active_tasks() -> None:
    root = _test_root("bounded-task-history")
    try:
        runtime, session = _runtime_with_fake_session(root, "boundedhistory")
        history_limit = rats_module._MAX_TERMINAL_TASK_HISTORY_PER_SESSION
        with runtime._lock:
            runtime._remember_task(session, {"task_id": "active-oldest", "tool": "run.play"})
            for index in range(history_limit):
                task_id = f"terminal-{index:03d}"
                runtime._remember_task(session, {"task_id": task_id, "tool": "run.play"})
                runtime._tasks[runtime._task_key(session, task_id)]["status"] = {
                    "task_id": task_id,
                    "state": "completed",
                    "running": False,
                }
            runtime._remember_task(session, {"task_id": "terminal-newest", "tool": "run.play"})

        runtime._request = lambda *_args, **_kwargs: {
            "task_id": "terminal-newest",
            "cancelled": True,
            "output": {"state": "stopped", "running": False},
        }
        runtime.cancel_task(session.descriptor.service_id, "terminal-newest")

        task_ids = {task["task_id"] for task in runtime.get_tasks()}
        assert len(task_ids) == history_limit + 1
        assert "active-oldest" in task_ids
        assert "terminal-000" not in task_ids
        assert "terminal-newest" in task_ids
    finally:
        shutil.rmtree(root, ignore_errors=True)


def test_blocked_rtp_io_does_not_block_task_or_connection_snapshots() -> None:
    root = _test_root("concurrent-state-read")
    runtime, session = _runtime_with_fake_session(root, "state")
    io_started = threading.Event()
    release_io = threading.Event()
    reader_finished = threading.Event()
    failures: list[BaseException] = []
    snapshot: dict[str, object] = {}
    with runtime._lock:
        runtime._remember_task(session, {"task_id": "cached-task", "tool": "run.play"})

    def blocking_request(*_args, **_kwargs):
        io_started.set()
        if not release_io.wait(timeout=5):
            raise TimeoutError("test did not release blocked RTP request")
        return {"matches": []}

    def search_catalog() -> None:
        try:
            runtime.search(
                "ping",
                service_id=session.descriptor.service_id,
                provider_id=session.descriptor.provider_id,
                load=False,
            )
        except BaseException as error:
            failures.append(error)

    def read_state() -> None:
        try:
            snapshot["tasks"] = runtime.get_tasks()
            snapshot["connected"] = runtime.has_connected_services()
        except BaseException as error:
            failures.append(error)
        finally:
            reader_finished.set()

    runtime._request = blocking_request
    caller = threading.Thread(target=search_catalog)
    reader = threading.Thread(target=read_state)
    try:
        caller.start()
        assert io_started.wait(timeout=2)
        reader.start()
        assert reader_finished.wait(timeout=0.5), "state readers waited for blocked socket I/O"
        assert snapshot["connected"] is True
        assert isinstance(snapshot["tasks"], list) and snapshot["tasks"][0]["task_id"] == "cached-task"
    finally:
        release_io.set()
        caller.join(timeout=5)
        reader.join(timeout=5)
        shutil.rmtree(root, ignore_errors=True)
    assert not caller.is_alive() and not reader.is_alive()
    assert failures == []


def test_refresh_socket_io_does_not_block_state_snapshots(monkeypatch: pytest.MonkeyPatch) -> None:
    root = _test_root("concurrent-refresh-state-read")
    runtime, session = _runtime_with_fake_session(root, "refreshstate")
    _configure_fake_discovery(runtime, session.descriptor, monkeypatch, enabled=False)
    request_started = threading.Event()
    release_request = threading.Event()
    reader_finished = threading.Event()
    failures: list[BaseException] = []
    snapshot: dict[str, object] = {}

    def blocking_request(_descriptor, operation, *_args, **_kwargs):
        if operation == "hello":
            request_started.set()
            if not release_request.wait(timeout=5):
                raise TimeoutError("test did not release refresh RTP request")
            return {
                "service_id": session.descriptor.service_id,
                "protocol": RATS_PROTOCOL,
                "provider_id": session.descriptor.provider_id,
                "service_kind": session.descriptor.service_kind,
                "product": session.descriptor.product,
            }
        if operation == "session.close":
            return {"closed": True}
        raise AssertionError(f"unexpected refresh operation: {operation}")

    def refresh_runtime() -> None:
        try:
            runtime.refresh()
        except BaseException as error:
            failures.append(error)

    def read_state() -> None:
        try:
            snapshot["connected"] = runtime.has_connected_services()
            snapshot["tasks"] = runtime.get_tasks()
        except BaseException as error:
            failures.append(error)
        finally:
            reader_finished.set()

    runtime._request = blocking_request
    refresher = threading.Thread(target=refresh_runtime)
    reader = threading.Thread(target=read_state)
    try:
        refresher.start()
        assert request_started.wait(timeout=2)
        reader.start()
        assert reader_finished.wait(timeout=0.5), "state readers waited for refresh socket I/O"
        assert snapshot == {"connected": True, "tasks": []}
    finally:
        release_request.set()
        refresher.join(timeout=5)
        reader.join(timeout=5)
        shutil.rmtree(root, ignore_errors=True)
    assert not refresher.is_alive() and not reader.is_alive()
    assert failures == []


def test_refresh_serializes_with_task_io_and_does_not_close_the_session_mid_request(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root = _test_root("concurrent-refresh-task-io")
    runtime, session = _runtime_with_fake_session(root, "refreshtask")
    _configure_fake_discovery(runtime, session.descriptor, monkeypatch, enabled=True)
    task_started = threading.Event()
    refresh_request_started = threading.Event()
    release_task = threading.Event()
    counter_lock = threading.Lock()
    active_requests = 0
    maximum_active_requests = 0
    task_running = False
    closed_during_task = False
    operations: list[str] = []
    failures: list[BaseException] = []

    def serialized_request(_descriptor, operation, *_args, **_kwargs):
        nonlocal active_requests, maximum_active_requests, task_running, closed_during_task
        with counter_lock:
            active_requests += 1
            maximum_active_requests = max(maximum_active_requests, active_requests)
            operations.append(operation)
            if operation == "tool.call":
                task_running = True
                task_started.set()
            else:
                refresh_request_started.set()
            if operation == "session.close" and task_running:
                closed_during_task = True
        try:
            if operation == "tool.call":
                if not release_task.wait(timeout=5):
                    raise TimeoutError("test did not release task RTP request")
                return {"tool": "ping", "output": {"pong": True}}
            if operation == "hello":
                return {
                    "service_id": session.descriptor.service_id,
                    "protocol": RATS_PROTOCOL,
                    "provider_id": session.descriptor.provider_id,
                    "service_kind": session.descriptor.service_kind,
                    "product": session.descriptor.product,
                }
            if operation == "status":
                return {"session_active": True}
            if operation == "session.close":
                return {"closed": True}
            raise AssertionError(f"unexpected concurrent operation: {operation}")
        finally:
            with counter_lock:
                if operation == "tool.call":
                    task_running = False
                active_requests -= 1

    def call_tool() -> None:
        try:
            runtime.call_tool(
                session.descriptor.service_id,
                "ping",
                {},
                provider_id=session.descriptor.provider_id,
            )
        except BaseException as error:
            failures.append(error)

    def refresh_runtime() -> None:
        try:
            runtime.refresh()
        except BaseException as error:
            failures.append(error)

    runtime._request = serialized_request
    caller = threading.Thread(target=call_tool)
    refresher = threading.Thread(target=refresh_runtime)
    try:
        caller.start()
        assert task_started.wait(timeout=2)
        refresher.start()
        assert not refresh_request_started.wait(timeout=0.3), "refresh entered RTP while task I/O was active"
    finally:
        release_task.set()
        caller.join(timeout=5)
        refresher.join(timeout=5)
        shutil.rmtree(root, ignore_errors=True)
    assert not caller.is_alive() and not refresher.is_alive()
    assert maximum_active_requests == 1
    assert closed_during_task is False
    assert operations == ["tool.call", "hello", "status"]
    assert failures == []


def test_shutdown_is_terminal_and_a_later_refresh_cannot_restore_sessions(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root = _test_root("shutdown-terminal-refresh")
    runtime, session = _runtime_with_fake_session(root, "terminal")
    _configure_fake_discovery(runtime, session.descriptor, monkeypatch, enabled=True)
    operations: list[str] = []
    close_started = threading.Event()
    release_close = threading.Event()
    refresh_finished = threading.Event()
    refresh_errors: list[RatsClientError] = []
    failures: list[BaseException] = []

    def request(_descriptor, operation, *_args, **_kwargs):
        operations.append(operation)
        if operation == "hello":
            return {
                "service_id": session.descriptor.service_id,
                "protocol": RATS_PROTOCOL,
                "provider_id": session.descriptor.provider_id,
                "service_kind": session.descriptor.service_kind,
                "product": session.descriptor.product,
            }
        if operation == "session.open":
            return {"session_token": "c" * 64, "permissions": ["read"]}
        if operation == "catalog.index":
            return {"tools": []}
        raise AssertionError(f"unexpected terminal lifecycle operation: {operation}")

    def blocking_close(_session: _RatsSession, **_kwargs) -> None:
        close_started.set()
        if not release_close.wait(timeout=5):
            raise TimeoutError("test did not release shutdown session close")

    def shutdown_runtime() -> None:
        try:
            runtime.shutdown()
        except BaseException as error:
            failures.append(error)

    def refresh_runtime() -> None:
        try:
            runtime.refresh()
        except RatsClientError as error:
            refresh_errors.append(error)
        except BaseException as error:
            failures.append(error)
        finally:
            refresh_finished.set()

    runtime._request = request
    monkeypatch.setattr(runtime, "_close_session", blocking_close)
    shutdown_thread = threading.Thread(target=shutdown_runtime)
    refresh_thread = threading.Thread(target=refresh_runtime)
    try:
        shutdown_thread.start()
        assert close_started.wait(timeout=2)
        assert runtime.has_connected_services() is False
        refresh_thread.start()
        assert not refresh_finished.wait(timeout=0.3), "refresh bypassed the active shutdown lifecycle"
        release_close.set()
        shutdown_thread.join(timeout=5)
        refresh_thread.join(timeout=5)
        assert not shutdown_thread.is_alive() and not refresh_thread.is_alive()
        assert [error.code for error in refresh_errors] == ["runtime_closed"]
        assert runtime.has_connected_services() is False
        assert operations == []
        assert failures == []
    finally:
        release_close.set()
        shutdown_thread.join(timeout=5)
        refresh_thread.join(timeout=5)
        shutil.rmtree(root, ignore_errors=True)


def test_force_refresh_does_not_hold_state_lock_while_waiting_for_session_io(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root = _test_root("force-refresh-lock-order")
    runtime, session = _runtime_with_fake_session(root, "forcerefresh")
    _configure_fake_discovery(runtime, session.descriptor, monkeypatch, enabled=True)
    force_started = threading.Event()
    request_entered = threading.Event()
    release_request = threading.Event()
    reader_finished = threading.Event()
    failures: list[BaseException] = []
    definitions: list[list[dict]] = []

    def blocking_request(_descriptor, operation, *_args, **_kwargs):
        request_entered.set()
        if not release_request.wait(timeout=5):
            raise TimeoutError("test did not release force-refresh RTP request")
        if operation == "hello":
            return {
                "service_id": session.descriptor.service_id,
                "protocol": RATS_PROTOCOL,
                "provider_id": session.descriptor.provider_id,
                "service_kind": session.descriptor.service_kind,
                "product": session.descriptor.product,
            }
        if operation == "status":
            return {"session_active": True}
        raise AssertionError(f"unexpected force-refresh operation: {operation}")

    def force_refresh() -> None:
        force_started.set()
        try:
            definitions.append(runtime.get_tool_definitions(force_refresh=True))
        except BaseException as error:
            failures.append(error)

    def read_state() -> None:
        try:
            runtime.has_connected_services()
        except BaseException as error:
            failures.append(error)
        finally:
            reader_finished.set()

    runtime._request = blocking_request
    refresher = threading.Thread(target=force_refresh)
    reader = threading.Thread(target=read_state)
    session.io_lock.acquire()
    try:
        refresher.start()
        assert force_started.wait(timeout=2)
        request_entered.wait(timeout=0.3)
        reader.start()
        assert reader_finished.wait(timeout=0.5), "force_refresh held state while waiting for session I/O"
    finally:
        release_request.set()
        session.io_lock.release()
        refresher.join(timeout=5)
        reader.join(timeout=5)
        shutil.rmtree(root, ignore_errors=True)
    assert not refresher.is_alive() and not reader.is_alive()
    assert definitions == [[]]
    assert failures == []


def test_same_rats_session_serializes_concurrent_socket_io() -> None:
    root = _test_root("concurrent-session-io")
    runtime, session = _runtime_with_fake_session(root, "serial")
    first_request_started = threading.Event()
    second_calling = threading.Event()
    second_request_started = threading.Event()
    release_io = threading.Event()
    counter_lock = threading.Lock()
    active_requests = 0
    maximum_active_requests = 0
    request_count = 0
    failures: list[BaseException] = []

    def blocking_request(_descriptor, operation, *_args, **_kwargs):
        nonlocal active_requests, maximum_active_requests, request_count
        with counter_lock:
            active_requests += 1
            request_count += 1
            maximum_active_requests = max(maximum_active_requests, active_requests)
            if request_count == 1:
                first_request_started.set()
            else:
                second_request_started.set()
        try:
            if not release_io.wait(timeout=5):
                raise TimeoutError("test did not release blocked RTP request")
            return {"tools": []} if operation == "catalog.describe" else {"tool": "ping", "output": {"pong": True}}
        finally:
            with counter_lock:
                active_requests -= 1

    def call_tool() -> None:
        try:
            runtime.call_tool(
                session.descriptor.service_id,
                "ping",
                {},
                provider_id=session.descriptor.provider_id,
            )
        except BaseException as error:
            failures.append(error)

    def describe_tool() -> None:
        try:
            second_calling.set()
            runtime.describe(
                session.descriptor.service_id,
                ["ping"],
                provider_id=session.descriptor.provider_id,
            )
        except BaseException as error:
            failures.append(error)

    runtime._request = blocking_request
    callers = [threading.Thread(target=call_tool), threading.Thread(target=describe_tool)]
    try:
        callers[0].start()
        assert first_request_started.wait(timeout=2)
        callers[1].start()
        assert second_calling.wait(timeout=2)
        assert not second_request_started.wait(timeout=0.3), "a second request entered the same session concurrently"
        with counter_lock:
            assert request_count == 1
            assert maximum_active_requests == 1
    finally:
        release_io.set()
        for caller in callers:
            caller.join(timeout=5)
        shutil.rmtree(root, ignore_errors=True)
    assert all(not caller.is_alive() for caller in callers)
    assert request_count == 2
    assert maximum_active_requests == 1
    assert failures == []


def test_session_rotation_discards_a_stale_task_status_writeback() -> None:
    root = _test_root("concurrent-session-rotation")
    runtime, session = _runtime_with_fake_session(root, "rotate")
    io_started = threading.Event()
    release_io = threading.Event()
    rotation_finished = threading.Event()
    failures: list[BaseException] = []
    results: list[dict] = []
    with runtime._lock:
        runtime._remember_task(session, {"task_id": "stale-task", "tool": "run.play"})

    def blocking_request(*_args, **_kwargs):
        io_started.set()
        if not release_io.wait(timeout=5):
            raise TimeoutError("test did not release blocked RTP request")
        return {"task_id": "stale-task", "running": False, "next_cursor": 99}

    def read_status() -> None:
        try:
            results.append(runtime.task_status(
                session.descriptor.service_id,
                "stale-task",
                provider_id=session.descriptor.provider_id,
            ))
        except BaseException as error:
            failures.append(error)

    replacement = _RatsSession(
        descriptor=session.descriptor,
        token="c" * 64,
        permissions=["read"],
    )

    def rotate_session() -> None:
        try:
            with runtime._lifecycle_lock:
                with runtime._lock:
                    runtime._sessions[(session.descriptor.provider_id, session.descriptor.service_id)] = replacement
                    runtime._drop_tasks_for_session(session)
                    runtime._remember_task(replacement, {"task_id": "stale-task", "tool": "replacement.run"})
                    replacement_task = runtime._tasks[
                        (replacement.descriptor.provider_id, replacement.descriptor.service_id, "stale-task")
                    ]
                    replacement_task["status"] = {"source": "replacement"}
                    replacement_task["cursor"] = 7
        except BaseException as error:
            failures.append(error)
        finally:
            rotation_finished.set()

    runtime._request = blocking_request
    caller = threading.Thread(target=read_status)
    rotator = threading.Thread(target=rotate_session)
    try:
        caller.start()
        assert io_started.wait(timeout=2)
        rotator.start()
        assert rotation_finished.wait(timeout=0.5), "session rotation waited for blocked socket I/O"
        release_io.set()
        caller.join(timeout=5)
        assert not caller.is_alive()
        assert results == [{"task_id": "stale-task", "running": False, "next_cursor": 99}]
        tasks = runtime.get_tasks()
        assert len(tasks) == 1
        assert tasks[0]["tool"] == "replacement.run"
        assert tasks[0]["status"] == {"source": "replacement"}
        assert tasks[0]["cursor"] == 7
    finally:
        release_io.set()
        caller.join(timeout=5)
        rotator.join(timeout=5)
        shutil.rmtree(root, ignore_errors=True)
    assert failures == []


def test_unknown_provider_is_rejected_and_recorded_without_becoming_visible() -> None:
    root = _test_root("unknown-provider")
    try:
        engine_root = root / "engine"
        executable = engine_root / "reverie.windows.editor.x86_64.exe"
        executable.parent.mkdir(parents=True, exist_ok=True)
        executable.write_bytes(b"test")
        services = engine_root / "ReverieLocal" / "RATS" / "Services"
        services.mkdir(parents=True, exist_ok=True)
        descriptor_path = services / "rats-123-unknown.json"
        descriptor_path.write_text(
            json.dumps(
                {
                    "schema": "reverie.rats.discovery/1",
                    "protocol": RATS_PROTOCOL,
                    "service_id": "rats-123-unknown",
                    "provider_id": "unrecognized.vendor",
                    "service_kind": "builtin",
                    "product": "Unknown Tool Server",
                    "executable": str(executable.resolve()),
                    "pid": 123,
                    "port": 4545,
                    "endpoint": "http://127.0.0.1:4545/rtp",
                    "bind_address": "127.0.0.1",
                    "control_token": CONTROL_TOKEN,
                }
            ),
            encoding="utf-8",
        )

        runtime = RatsRuntime(root / "cli", provider_registry=TEST_PROVIDER_REGISTRY)
        state = runtime.add_engine(executable)
        assert state["services"] == []
        assert state["rejectedDescriptorCount"] == 1
        assert any(
            item.get("event") == "discovery.rejected" and item.get("reason") == "unsupported_provider"
            for item in state["diagnostics"]
        )
    finally:
        shutil.rmtree(root, ignore_errors=True)


def test_hello_identity_mismatch_is_hidden_and_names_the_failed_field() -> None:
    root = _test_root("identity-mismatch")
    server, thread = _start_server(hello_product="Impostor Engine")
    try:
        engine_root = root / "engine"
        executable = engine_root / "reverie.windows.editor.x86_64.exe"
        executable.parent.mkdir(parents=True, exist_ok=True)
        executable.write_bytes(b"test")
        services = engine_root / "ReverieLocal" / "RATS" / "Services"
        services.mkdir(parents=True, exist_ok=True)
        (services / f"{server.service_id}.json").write_text(
            json.dumps(
                {
                    "schema": "reverie.rats.discovery/1",
                    "protocol": RATS_PROTOCOL,
                    "service_id": server.service_id,
                    "provider_id": "reverie.engine",
                    "service_kind": "builtin",
                    "product": "Reverie Engine",
                    "executable": str(executable.resolve()),
                    "pid": os.getpid(),
                    "port": server.server_port,
                    "endpoint": f"http://127.0.0.1:{server.server_port}/rtp",
                    "bind_address": "127.0.0.1",
                    "control_token": CONTROL_TOKEN,
                }
            ),
            encoding="utf-8",
        )

        runtime = RatsRuntime(root / "cli", provider_registry=TEST_PROVIDER_REGISTRY)
        state = runtime.add_engine(executable)
        assert state["services"] == []
        assert any(
            item.get("event") == "provider.rejected"
            and item.get("reason") == "hello_product_mismatch"
            for item in state["diagnostics"]
        )
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)
        shutil.rmtree(root, ignore_errors=True)


def test_unreachable_supported_provider_fast_fails_and_remains_hidden() -> None:
    root = _test_root("unreachable")
    try:
        engine_root = root / "engine"
        executable = engine_root / "reverie.windows.editor.x86_64.exe"
        executable.parent.mkdir(parents=True, exist_ok=True)
        executable.write_bytes(b"test")
        services = engine_root / "ReverieLocal" / "RATS" / "Services"
        services.mkdir(parents=True, exist_ok=True)
        descriptor_path = services / "rats-123-offline.json"
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
            probe.bind(("127.0.0.1", 0))
            closed_port = probe.getsockname()[1]
        descriptor_path.write_text(
            json.dumps(
                {
                    "schema": "reverie.rats.discovery/1",
                    "protocol": RATS_PROTOCOL,
                    "service_id": "rats-123-offline",
                    "provider_id": "reverie.engine",
                    "service_kind": "builtin",
                    "product": "Reverie Engine",
                    "executable": str(executable.resolve()),
                    "pid": 123,
                    "port": closed_port,
                    "endpoint": f"http://127.0.0.1:{closed_port}/rtp",
                    "bind_address": "127.0.0.1",
                    "control_token": CONTROL_TOKEN,
                }
            ),
            encoding="utf-8",
        )

        runtime = RatsRuntime(root / "cli", provider_registry=TEST_PROVIDER_REGISTRY, probe_timeout=0.1)
        started = time.perf_counter()
        state = runtime.add_engine(executable)
        elapsed = time.perf_counter() - started
        assert elapsed < 1.0
        assert state["scanDurationMs"] < 1000
        assert state["services"] == []
        assert any(
            item.get("event") == "rtp.request"
            and item.get("operation") == "hello"
            and item.get("reason") == "transport_error"
            for item in state["diagnostics"]
        )
    finally:
        shutil.rmtree(root, ignore_errors=True)


def test_legacy_enabled_engines_migrate_losslessly_and_idempotently() -> None:
    root = _test_root("settings-migration")
    try:
        executable = root / "engine" / "reverie.windows.editor.x86_64.exe"
        executable.parent.mkdir(parents=True, exist_ok=True)
        executable.write_bytes(b"test")
        discovery_root = root / "legacy-discovery"
        cli_root = root / "cli"
        settings_path = cli_root / ".reverie" / "rats" / "settings.json"
        settings_path.parent.mkdir(parents=True, exist_ok=True)
        settings_path.write_text(
            json.dumps(
                {
                    "discoveryRoots": [str(discovery_root), str(discovery_root)],
                    "enabledEngines": [{"executable": str(executable), "permissions": ["run", "read"]}],
                }
            ),
            encoding="utf-8",
        )

        runtime = RatsRuntime(cli_root, provider_registry=TEST_PROVIDER_REGISTRY)
        first = runtime.refresh()
        persisted = json.loads(settings_path.read_text(encoding="utf-8"))
        assert persisted["schemaVersion"] == 2
        assert "enabledEngines" not in persisted
        assert persisted["discoveryRoots"] == [str(discovery_root.resolve()), str((executable.parent / "ReverieLocal" / "RATS" / "Services").resolve())]
        assert persisted["enabledProviders"] == [
            {
                "providerId": "reverie.engine",
                "executable": str(executable.resolve()),
                "permissions": ["read", "run"],
                "discoveryRoot": str((executable.parent / "ReverieLocal" / "RATS" / "Services").resolve()),
            }
        ]
        assert first["enabledProviders"] == persisted["enabledProviders"]

        second = runtime.refresh()
        assert json.loads(settings_path.read_text(encoding="utf-8")) == persisted
        assert second["enabledProviders"] == first["enabledProviders"]
    finally:
        shutil.rmtree(root, ignore_errors=True)


def test_unknown_provider_selection_is_dropped_and_diagnosed_without_sensitive_data() -> None:
    root = _test_root("unknown-selection")
    try:
        cli_root = root / "cli"
        settings_path = cli_root / ".reverie" / "rats" / "settings.json"
        settings_path.parent.mkdir(parents=True, exist_ok=True)
        settings_path.write_text(
            json.dumps(
                {
                    "schemaVersion": 2,
                    "enabledProviders": [{
                        "providerId": "unrecognized.provider",
                        "executable": str(root / "unknown.exe"),
                        "permissions": ["read"],
                    }],
                }
            ),
            encoding="utf-8",
        )
        runtime = RatsRuntime(cli_root)
        state = runtime.refresh()
        assert state["enabledProviders"] == []
        assert any(
            item.get("event") == "settings.rejected"
            and item.get("providerId") == "unrecognized.provider"
            and item.get("reason") == "unsupported_provider"
            for item in state["diagnostics"]
        )
        persisted = settings_path.read_text(encoding="utf-8")
        assert "unrecognized.provider" not in persisted
        assert "control_token" not in persisted
        assert "session_token" not in persisted
    finally:
        shutil.rmtree(root, ignore_errors=True)


def test_test_only_provider_registry_proves_selection_and_catalog_isolation() -> None:
    root = _test_root("multi-provider")
    engine_server, engine_thread = _start_server(service_suffix="same")
    second_control = "c" * 64
    second_session = "d" * 64
    second_server, second_thread = _start_server(
        provider_id="test.provider",
        service_kind="sandbox",
        hello_product="Test Provider",
        service_suffix="same",
        control_token=second_control,
        session_token=second_session,
    )
    try:
        second_spec = RatsProviderSpec(
            provider_id="test.provider",
            product="Test Provider",
            service_kinds=("sandbox",),
            executable_validator=lambda executable: executable.is_file(),
            process_validator=_allow_test_process,
            discovery_root_resolver=lambda executable: executable.parent / "ProviderLocal" / "Services",
            permission_classes=("read", "run"),
            label="Test Provider",
            tool_tags=("test-provider",),
        )
        registry = RatsProviderRegistry({
            **TEST_PROVIDER_REGISTRY.providers,
            "test.provider": second_spec,
        })
        engine_executable = root / "engine" / "reverie.windows.editor.x86_64.exe"
        second_executable = root / "second" / "test-provider.exe"
        engine_executable.parent.mkdir(parents=True, exist_ok=True)
        second_executable.parent.mkdir(parents=True, exist_ok=True)
        engine_executable.write_bytes(b"engine")
        second_executable.write_bytes(b"provider")
        _write_descriptor(
            root / "engine" / "ReverieLocal" / "RATS" / "Services",
            engine_server,
            engine_executable,
            provider_id="reverie.engine",
            service_kind="builtin",
            product="Reverie Engine",
            control_token=CONTROL_TOKEN,
        )
        _write_descriptor(
            root / "second" / "ProviderLocal" / "Services",
            second_server,
            second_executable,
            provider_id="test.provider",
            service_kind="sandbox",
            product="Test Provider",
            control_token=second_control,
        )

        runtime = RatsRuntime(root / "cli", provider_registry=registry)
        assert len(RATS_SUPPORTED_PROVIDERS) == 1
        runtime.register_provider_executable("reverie.engine", engine_executable)
        runtime.register_provider_executable("test.provider", second_executable)
        runtime.set_provider_enabled("reverie.engine", engine_executable, True, ["read"])
        state = runtime.set_provider_enabled("test.provider", second_executable, True, ["run"])

        assert {item["providerId"] for item in state["enabledProviders"]} == {"reverie.engine", "test.provider"}
        assert {(item["providerId"], item["serviceId"]) for item in state["services"]} == {
            ("reverie.engine", engine_server.service_id),
            ("test.provider", second_server.service_id),
        }
        assert all(item["connection"] == "connected" for item in state["services"])
        assert state["supportedProviders"][-1]["providerId"] == "test.provider"

        definitions = runtime.get_tool_definitions()
        ping_definitions = [item for item in definitions if item["native_tool_name"] == "ping"]
        assert len(ping_definitions) == 2
        assert {item["provider_id"] for item in ping_definitions} == {"reverie.engine", "test.provider"}
        assert len({item["name"] for item in ping_definitions}) == 2
        assert all(item["provider_id"] in item["qualified_name"] for item in ping_definitions)
        assert any("reverie-engine" in item["tags"] for item in ping_definitions if item["provider_id"] == "reverie.engine")
        assert all("reverie-engine" not in item["tags"] for item in ping_definitions if item["provider_id"] == "test.provider")
        assert runtime.describe(second_server.service_id, ["ping"], provider_id="test.provider")[0]["name"] == "ping"

        with pytest.raises(ValueError, match="Unsupported RATS provider"):
            runtime.register_provider_executable("unknown.provider", second_executable)

        offline = root / "offline" / "provider.exe"
        state = runtime.set_provider_enabled("test.provider", offline, True, ["read"])
        assert any(item["executable"] == str(offline.resolve()) for item in state["enabledProviders"])
        assert not any(item["executable"] == str(offline.resolve()) for item in state["services"])
        persisted = runtime.settings_path.read_text(encoding="utf-8")
        assert second_control not in persisted
        assert second_session not in persisted
        assert "arguments" not in json.dumps(state)
    finally:
        runtime = locals().get("runtime")
        if runtime is not None:
            runtime.shutdown()
        engine_server.shutdown()
        engine_server.server_close()
        engine_thread.join(timeout=5)
        second_server.shutdown()
        second_server.server_close()
        second_thread.join(timeout=5)
        shutil.rmtree(root, ignore_errors=True)
