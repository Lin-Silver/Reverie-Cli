from __future__ import annotations

import json
import os
import shutil
import socket
import threading
import time
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from reverie.agent.tool_executor import ToolExecutor
from reverie.rats import RATS_PROTOCOL, RATS_SUPPORTED_PROVIDERS, RatsRuntime, parse_rats_descriptor


CONTROL_TOKEN = "a" * 64
SESSION_TOKEN = "b" * 64


def _test_root(name: str) -> Path:
    root = Path(__file__).resolve().parents[2] / "dist" / ".reverie" / "test-temp" / f"rats-{name}-{uuid.uuid4().hex}"
    root.mkdir(parents=True, exist_ok=True)
    return root


class _RatsHandler(BaseHTTPRequestHandler):
    events: list[str] = []
    session_open = False
    hello_product = "Reverie Engine"

    def log_message(self, _format: str, *_args) -> None:
        return

    def _reply(self, status: int, request_id: str, *, result=None, code="", message="") -> None:
        payload = {"id": request_id, "protocol": RATS_PROTOCOL, "ok": status < 400}
        if status < 400:
            payload["result"] = result or {}
        else:
            payload["error"] = {"code": code or "request_failed", "message": message or "failed"}
        body = json.dumps(payload).encode("utf-8")
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
        request_id = str(body.get("id") or "")
        operation = str(body.get("op") or "")
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
                    "provider_id": "reverie.engine",
                    "service_kind": "builtin",
                    "product": type(self).hello_product,
                },
            )
            return
        if operation == "session.open":
            if self.headers.get("X-Reverie-RATS-Control") != CONTROL_TOKEN:
                self._reply(401, request_id, code="unauthorized")
                return
            type(self).session_open = True
            self._reply(
                200,
                request_id,
                result={
                    "session_token": SESSION_TOKEN,
                    "permissions": args.get("permissions", ["read"]),
                    "tools": ["ping", "version", "get_status", "project.status", "scene.read"],
                },
            )
            return
        if self.headers.get("X-Reverie-RTP-Session") != SESSION_TOKEN or not type(self).session_open:
            self._reply(401, request_id, code="unauthorized")
            return
        if operation == "status":
            self._reply(200, request_id, result={"session_active": True})
        elif operation == "session.close":
            type(self).session_open = False
            self._reply(200, request_id, result={"closed": True})
        elif operation == "catalog.index":
            names = ["ping", "version", "get_status", "project.status", "scene.read"]
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
            self._reply(
                200,
                request_id,
                result={"tool": args.get("name"), "dry_run": args.get("dry_run", False), "output": {"pong": True, "echo": args.get("arguments", {}).get("message")}},
            )
        else:
            self._reply(404, request_id, code="unknown_operation")


def _start_server(*, hello_product: str = "Reverie Engine"):
    _RatsHandler.events = []
    _RatsHandler.session_open = False
    _RatsHandler.hello_product = hello_product
    server = ThreadingHTTPServer(("127.0.0.1", 0), _RatsHandler)
    server.service_id = f"rats-{os.getpid()}-test"
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return server, thread


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
        runtime = RatsRuntime(cli_root)
        state = runtime.add_engine(executable)
        assert state["services"][0]["connection"] == "available"
        state = runtime.set_engine_enabled(executable, True, ["read"])
        service = state["services"][0]
        assert service["connection"] == "connected"
        assert service["sessionActive"] is True
        assert service["providerId"] == "reverie.engine"
        assert service["serviceKind"] == "builtin"
        assert service["probeLatencyMs"] >= 0
        assert state["supportedProviders"] == [
            {"providerId": "reverie.engine", "product": "Reverie Engine", "serviceKind": "builtin"}
        ]
        assert RATS_SUPPORTED_PROVIDERS["reverie.engine"]["service_kind"] == "builtin"
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
        assert "rats_reverie_engine_scene_read" in names

        runtime.shutdown()
        assert "session.close" in _RatsHandler.events
        assert _RatsHandler.session_open is False
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)
        shutil.rmtree(root, ignore_errors=True)


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

        runtime = RatsRuntime(root / "cli")
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

        runtime = RatsRuntime(root / "cli")
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

        runtime = RatsRuntime(root / "cli", probe_timeout=0.1)
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
