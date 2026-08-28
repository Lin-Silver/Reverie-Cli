"""The RTP capability contract, and the proof the client is actually driven by it.

Two halves. The first exercises ``reverie.rats_contract`` directly: every way a
published contract can be absent, wrong or malformed has to degrade to the
behaviour this client shipped with, and none of them may raise.

The second is the derivation proof. A stub service publishes a contract whose
operation names, header names, permission classes and limits all differ from the
constants this client used to hardcode, and *refuses* the old ones. A client
still reading its own constants cannot talk to it at all, so the test passing is
evidence that the values now come off the wire. The same test runs a second time
with contract parsing disabled to show that it really does fail that way.
"""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import threading
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest

import reverie.rats as rats_module
from reverie.rats import (
    RATS_PROTOCOL,
    RATS_SUPPORTED_PROVIDERS,
    RatsClientError,
    RatsProviderRegistry,
    RatsProviderSpec,
    RatsRuntime,
)
from reverie.rats_contract import (
    FALLBACK_BOOTSTRAP_TOOLS,
    FALLBACK_CONTROL_HEADER,
    FALLBACK_LIMITS,
    FALLBACK_PERMISSIONS,
    FALLBACK_SESSION_HEADER,
    RATS_CAPABILITY_CONTRACT,
    RATS_CLIENT_ROLES,
    fallback_capabilities,
    parse_capabilities,
)
from reverie.tools.rats_catalog import RatsCatalogTool


CONTROL_TOKEN = "a" * 64
SESSION_TOKEN = "b" * 64


# ---------------------------------------------------------------------------
# Contract reader
# ---------------------------------------------------------------------------


def _reasons(rejections) -> set:
    return {str(item.get("reason") or "") for item in rejections}


def _fields(rejections) -> set:
    return {str(item.get("field") or "") for item in rejections}


def test_absent_contract_reproduces_the_behaviour_this_client_shipped_with() -> None:
    capabilities, rejections = parse_capabilities({"service_id": "rats-1", "protocol": RATS_PROTOCOL})

    assert capabilities.source == "fallback"
    assert capabilities.declared is False
    assert _reasons(rejections) == {"contract_absent"}
    # Not an empty fallback: a service older than the contract must keep working
    # exactly as it did, which means the shipped constants, not absences.
    assert capabilities.control_header == FALLBACK_CONTROL_HEADER
    assert capabilities.session_header == FALLBACK_SESSION_HEADER
    assert capabilities.permissions == FALLBACK_PERMISSIONS
    assert dict(capabilities.limits) == dict(FALLBACK_LIMITS)
    for role in RATS_CLIENT_ROLES:
        assert capabilities.operation(role) == role


def test_unsupported_contract_id_degrades_instead_of_guessing() -> None:
    capabilities, rejections = parse_capabilities(
        {
            "capabilities": {
                "contract": "reverie.rtp.capabilities/99",
                "protocol": RATS_PROTOCOL,
                "roles": {"session.open": "future/open"},
            }
        }
    )

    assert capabilities.source == "fallback"
    assert _reasons(rejections) == {"unsupported_contract"}
    # The unreadable contract's names must not leak through partially: a v99
    # contract may mean something different by the same key.
    assert capabilities.operation("session.open") == "session.open"


def test_protocol_mismatch_is_rejected_even_when_the_contract_id_matches() -> None:
    capabilities, rejections = parse_capabilities(
        {
            "capabilities": {
                "contract": RATS_CAPABILITY_CONTRACT,
                "protocol": "reverie.rtp/2",
                "roles": {"status": "v2/status"},
            }
        }
    )

    assert capabilities.source == "fallback"
    assert _reasons(rejections) == {"protocol_mismatch"}
    assert capabilities.operation("status") == "status"


def test_each_malformed_section_degrades_on_its_own() -> None:
    capabilities, rejections = parse_capabilities(
        {
            "capabilities": {
                "contract": RATS_CAPABILITY_CONTRACT,
                "protocol": RATS_PROTOCOL,
                "roles": "not-a-map",
                "auth_headers": {"control": "X-Kept-Control", "session": "X Reverie Session"},
                "permissions": "not-a-list",
                "features": {"not": "a list"},
                "constraints": ["single_active_session"],
                "limits": {
                    "describe_tools": 5,
                    "search_results": 0,
                    "task_events": "many",
                    "deadline_ms": True,
                },
                "errors": "not-a-map",
            }
        }
    )

    # A declared contract with broken sections is still a declared contract: the
    # sections that parsed are used, and only the broken ones fall back.
    assert capabilities.source == "contract"
    assert capabilities.declared is True
    assert _fields(rejections) >= {
        "capabilities.roles",
        "capabilities.operations",
        "capabilities.auth_headers.session",
        "capabilities.permissions",
        "capabilities.features",
        "capabilities.limits",
        "capabilities.errors.default",
        "capabilities.errors.codes",
    }
    assert capabilities.control_header == "X-Kept-Control"
    # A value that cannot be an HTTP field name is not a header name. Sending it
    # anyway would put the session token somewhere the service never reads.
    assert capabilities.session_header == FALLBACK_SESSION_HEADER
    assert {"field": "capabilities.auth_headers.session", "reason": "not_a_header_name", "value": "X Reverie Session"} in rejections
    assert capabilities.operation("catalog.describe") == "catalog.describe"
    assert capabilities.permissions == FALLBACK_PERMISSIONS
    assert capabilities.has_constraint("single_active_session")
    assert capabilities.features == fallback_capabilities().features
    # The one readable limit is honoured; asking for an unreadable one returns
    # the value this client shipped with rather than nothing.
    assert capabilities.limit("describe_tools") == 5
    assert capabilities.limit("search_results") == FALLBACK_LIMITS["search_results"]
    assert capabilities.limit("task_events") == FALLBACK_LIMITS["task_events"]
    assert capabilities.limit("deadline_ms") == FALLBACK_LIMITS["deadline_ms"]


def test_the_role_map_wins_over_the_operation_rows_and_adopts_what_it_omits() -> None:
    capabilities, rejections = parse_capabilities(
        {
            "capabilities": {
                "contract": RATS_CAPABILITY_CONTRACT,
                "protocol": RATS_PROTOCOL,
                "roles": {"tool.call": "v2/invoke"},
                "operations": [
                    {"role": "tool.call", "operation": "v2/call", "auth": "session", "summary": "Call"},
                    {"role": "status", "operation": "v2/status", "auth": "session", "summary": "Probe"},
                ],
            }
        }
    )

    # The map is the authority. A row that disagrees with it is a service
    # inconsistency, and picking the row would send a name the map says is wrong.
    assert capabilities.operation("tool.call") == "v2/invoke"
    assert "role_disagreement" in _reasons(rejections)
    # A row for a role the map omitted is still information the map did not carry.
    assert capabilities.operation("status") == "v2/status"
    assert capabilities.auth("status") == "session"
    assert capabilities.summary("status") == "Probe"
    # Anything neither section mentioned resolves through the identity function.
    assert capabilities.operation("catalog.search") == "catalog.search"
    assert capabilities.declares_role("catalog.search") is False


def test_a_complete_contract_produces_no_rejections_and_resolves_every_role() -> None:
    contract = _future_contract()
    capabilities, rejections = parse_capabilities({"capabilities": contract})

    # A contract id promises every section, so a complete one must read clean:
    # anything reported here would be a false warning on the normal path.
    assert rejections == []
    for role in RATS_CLIENT_ROLES:
        assert capabilities.declares_role(role)
        assert capabilities.operation(role) == RENAMED_OPERATIONS[role]
    assert capabilities.auth("hello") == "none"
    assert capabilities.auth("session.open") == "control"
    assert capabilities.auth("tool.call") == "session"


def test_unknown_error_codes_use_the_declared_default() -> None:
    capabilities, rejections = parse_capabilities(
        {
            "capabilities": {
                "contract": RATS_CAPABILITY_CONTRACT,
                "protocol": RATS_PROTOCOL,
                "errors": {
                    "default": {"status": 418, "retryable": True, "category": "teapot"},
                    "codes": [
                        {"code": "quota_exhausted", "status": 429, "retryable": True, "category": "limit"},
                        {"code": "", "status": 500},
                    ],
                },
            }
        }
    )

    assert "invalid_row" in _reasons(rejections)
    declared = capabilities.error("quota_exhausted")
    assert (declared.status, declared.retryable, declared.category) == (429, True, "limit")
    assert capabilities.describes_error("quota_exhausted") is True
    # A code this build never heard of is classified the way the service says
    # unknown codes should be classified, not the way this build guesses.
    unknown = capabilities.error("something_new")
    assert (unknown.status, unknown.retryable, unknown.category) == (418, True, "teapot")
    assert capabilities.describes_error("something_new") is False


def test_legacy_hello_pointers_seed_the_fallback_role_map() -> None:
    capabilities = fallback_capabilities(
        {
            "session_open_operation": "legacy.open",
            # v1 publishes this as a flat list of operation names.
            "task_operations": ["task.status", "task.cancel", "run.status"],
        }
    )

    assert capabilities.source == "fallback"
    assert capabilities.operation("session.open") == "legacy.open"
    # v1 names its task roles after their operations, so reading the pointers is
    # what makes those two roles declared rather than merely identity-resolved.
    assert capabilities.declares_role("task.status") is True
    assert capabilities.operation("task.status") == "task.status"
    assert capabilities.declares_role("task.cancel") is True
    # An entry that is not a task role is not placed by guesswork.
    assert capabilities.declares_role("run.status") is False
    # Nothing pointed at events, so it keeps the identity name.
    assert capabilities.declares_role("task.events") is False
    assert capabilities.operation("task.events") == "task.events"


# ---------------------------------------------------------------------------
# Derivation proof against a service that renames everything
# ---------------------------------------------------------------------------


# Deliberately unlike the v1 wire names in every position. Only `hello` is
# shared, because it is the request that fetches the map.
RENAMED_OPERATIONS = {
    "hello": "hello",
    "session.open": "rtp.v2/open-session",
    "session.close": "rtp.v2/close-session",
    "status": "rtp.v2/session-status",
    "catalog.index": "rtp.v2/tool-index",
    "catalog.describe": "rtp.v2/tool-schemas",
    "catalog.search": "rtp.v2/tool-search",
    "tool.call": "rtp.v2/invoke",
    "task.status": "rtp.v2/job-status",
    "task.events": "rtp.v2/job-events",
    "task.cancel": "rtp.v2/job-cancel",
}
WIRE_TO_ROLE = {wire: role for role, wire in RENAMED_OPERATIONS.items()}

FUTURE_CONTROL_HEADER = "X-Future-Rtp-Control"
FUTURE_SESSION_HEADER = "X-Future-Rtp-Session"

# Every one of these differs from the constant the client used to compile in.
FUTURE_LIMITS = {
    "request_bytes": 1 << 20,
    "request_id_bytes": 64,
    "idempotency_key_bytes": 24,
    "client_name_bytes": 64,
    "deadline_ms": 5_000,
    "idempotency_wait_ms": 9_000,
    "describe_tools": 4,
    "search_results": 3,
    "task_events": 7,
    "concurrent_sessions": 1,
}

# `telemetry` is a class no build of this client was compiled knowing about.
FUTURE_PERMISSIONS = [
    {"name": "read", "tool_count": 6},
    {"name": "run", "tool_count": 3},
    {"name": "telemetry", "tool_count": 2},
]

FUTURE_TOOL_NAMES = [
    "ping",
    "version",
    "get_status",
    "project.status",
    "scene.read",
    "run.play",
    "run.status",
    "logs.read",
    "telemetry.sample",
]

# Not the client's own preload list, and deliberately not a prefix of it.
FUTURE_BOOTSTRAP_TOOLS = ["scene.read", "telemetry.sample"]


def _future_contract() -> dict:
    return {
        "contract": RATS_CAPABILITY_CONTRACT,
        "protocol": RATS_PROTOCOL,
        "roles": dict(RENAMED_OPERATIONS),
        "operations": [
            {
                "role": role,
                "operation": operation,
                "auth": "none" if role == "hello" else ("control" if role == "session.open" else "session"),
                "summary": f"Future {role}",
            }
            for role, operation in RENAMED_OPERATIONS.items()
        ],
        "auth_headers": {"control": FUTURE_CONTROL_HEADER, "session": FUTURE_SESSION_HEADER},
        "permissions": FUTURE_PERMISSIONS,
        "features": ["progressive_disclosure", "task_events", "idempotency", "telemetry_sampling"],
        "constraints": ["single_active_session"],
        "limits": dict(FUTURE_LIMITS),
        "errors": {
            "default": {"status": 400, "retryable": False, "category": "request"},
            "codes": [
                {"code": "quota_exhausted", "status": 429, "retryable": True, "category": "limit"},
                {"code": "operation_not_implemented", "status": 501, "retryable": False, "category": "protocol"},
            ],
        },
        "task_event_schema": "reverie.rtp.task/1",
    }


class _FutureRatsHandler(BaseHTTPRequestHandler):
    """A service that answers only its published names, through its own headers."""

    def log_message(self, _format: str, *_args) -> None:
        return

    def _reply(self, status: int, request_id: str, *, result=None, code="", message="") -> None:
        payload = {"id": request_id, "protocol": RATS_PROTOCOL, "ok": status < 400}
        if status < 400:
            value = result or {}
            payload["result"] = value
        else:
            value = {"code": code or "request_failed", "message": message or "failed"}
            payload["error"] = value
        payload["audit_id"] = f"audit-{uuid.uuid4().hex[:24]}"
        payload["result_sha256"] = hashlib.sha256(
            json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
        ).hexdigest()
        body = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    @staticmethod
    def _definition(name: str) -> dict:
        return {
            "name": name,
            "version": "1",
            "permission": "telemetry" if name.startswith("telemetry.") else "read",
            "dry_run": True,
            "summary": f"Future {name} tool",
            "category": name.split(".", 1)[0] if "." in name else "system",
            "tags": ["future"],
            "schema_available": True,
            "main_thread": False,
            "signature": f"sig-{name}",
            "request_schema": {"type": "object", "properties": {}, "required": [], "additionalProperties": False},
            "response_schema": {"type": "object"},
        }

    def do_POST(self) -> None:
        body = json.loads(self.rfile.read(int(self.headers.get("Content-Length", "0"))).decode("utf-8"))
        self.server.requests.append(body)
        request_id = str(body.get("id") or "")
        wire = str(body.get("op") or "")
        self.server.wire_names.append(wire)

        if body.get("protocol") != RATS_PROTOCOL:
            self._reply(409, request_id, code="protocol_mismatch")
            return
        # A client that kept its own constants arrives here, and this is the
        # whole point of the fixture: the old names do not exist on this service.
        if wire not in WIRE_TO_ROLE:
            self.server.unknown_names.append(wire)
            self._reply(501, request_id, code="operation_not_implemented", message=f"no such operation: {wire}")
            return
        role = WIRE_TO_ROLE[wire]
        args = body.get("args") if isinstance(body.get("args"), dict) else {}

        # The old header names are not read at all, so a client still sending
        # them is indistinguishable from one sending no credential.
        if FALLBACK_CONTROL_HEADER in self.headers or FALLBACK_SESSION_HEADER in self.headers:
            self.server.legacy_headers.append(role)

        if role == "hello":
            self._reply(
                200,
                request_id,
                result={
                    "service_id": self.server.service_id,
                    "protocol": RATS_PROTOCOL,
                    "provider_id": self.server.provider_id,
                    "service_kind": self.server.service_kind,
                    "product": self.server.product,
                    "capabilities": _future_contract(),
                },
            )
            return

        if role == "session.open":
            if self.headers.get(FUTURE_CONTROL_HEADER) != self.server.control_token:
                self._reply(401, request_id, code="unauthorized")
                return
            granted = [
                name
                for name in args.get("permissions", [])
                if name in {entry["name"] for entry in FUTURE_PERMISSIONS}
            ]
            self.server.granted_permissions = granted
            self.server.session_open = True
            self._reply(
                200,
                request_id,
                result={
                    "session_token": self.server.session_token,
                    "permissions": granted,
                    "tools": list(FUTURE_TOOL_NAMES),
                    "bootstrap_tools": list(FUTURE_BOOTSTRAP_TOOLS),
                },
            )
            return

        if self.headers.get(FUTURE_SESSION_HEADER) != self.server.session_token or not self.server.session_open:
            self._reply(401, request_id, code="unauthorized")
            return

        if role == "status":
            self._reply(200, request_id, result={"session_active": True})
        elif role == "session.close":
            self.server.session_open = False
            self._reply(200, request_id, result={"closed": True})
        elif role == "catalog.index":
            self._reply(
                200,
                request_id,
                result={
                    "count": len(FUTURE_TOOL_NAMES),
                    "definitions_embedded": False,
                    "tools": [
                        {
                            "key": f"k-{name}",
                            "name": name,
                            "category": name.split(".", 1)[0] if "." in name else "system",
                            "summary": f"Future {name} tool",
                            "permission": "telemetry" if name.startswith("telemetry.") else "read",
                            "flags": ["dry_run"],
                            "schema": f"sig-{name}",
                        }
                        for name in FUTURE_TOOL_NAMES
                    ],
                },
            )
        elif role == "catalog.describe":
            names = args.get("names", [])
            # The service enforces its own published cap rather than trusting the
            # client to have read it.
            if len(names) > FUTURE_LIMITS["describe_tools"]:
                self._reply(400, request_id, code="too_many_names", message="over the published describe cap")
                return
            self.server.describe_batches.append(list(names))
            self._reply(200, request_id, result={"tools": [self._definition(str(name)) for name in names]})
        elif role == "catalog.search":
            limit = args.get("limit")
            if isinstance(limit, int) and limit > FUTURE_LIMITS["search_results"]:
                self._reply(400, request_id, code="too_many_results", message="over the published search cap")
                return
            self.server.search_limits.append(limit)
            self._reply(
                200,
                request_id,
                result={
                    "matches": [
                        {"name": "telemetry.sample", "summary": "Sample telemetry", "category": "telemetry", "score": 500}
                    ]
                },
            )
        elif role == "tool.call":
            name = args.get("name")
            if name == "run.play":
                self.server.task = {
                    "task_id": "future-task-1",
                    "tool": "run.play",
                    "status_operation": "run.status",
                    "cancel_operation": "run.stop",
                    "deadline_msec": 0,
                    "first_event_sequence": 1,
                    "next_event_sequence": 2,
                }
                self.server.task_state = {
                    "task_id": "future-task-1",
                    "state": "running",
                    "running": True,
                    "progress": 0.0,
                }
                self._reply(
                    200,
                    request_id,
                    result={
                        "tool": name,
                        "dry_run": False,
                        "output": self.server.task_state,
                        "task": self.server.task,
                        "idempotent_replay": False,
                    },
                )
            else:
                self._reply(
                    200,
                    request_id,
                    result={
                        "tool": name,
                        "dry_run": bool(args.get("dry_run", False)),
                        "output": {"sampled": True},
                        "idempotent_replay": False,
                    },
                )
        elif role == "task.status":
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
        elif role == "task.events":
            limit = args.get("limit")
            if isinstance(limit, int) and limit > FUTURE_LIMITS["task_events"]:
                self._reply(400, request_id, code="too_many_events", message="over the published event cap")
                return
            self.server.event_limits.append(limit)
            events = [
                {
                    "schema": "reverie.rtp.task/1",
                    "task_id": "future-task-1",
                    "sequence": 1,
                    "type": "task.started",
                    "payload": self.server.task_state,
                }
            ]
            cursor = int(args.get("cursor", 0) or 0)
            selected = [event for event in events if int(event["sequence"]) > cursor]
            self._reply(
                200,
                request_id,
                result={
                    "schema": "reverie.rtp.task/1",
                    "task_id": "future-task-1",
                    "cursor": cursor,
                    "next_cursor": int(selected[-1]["sequence"]) if selected else cursor,
                    "has_more": False,
                    "truncated": False,
                    "events": selected,
                },
            )
        elif role == "task.cancel":
            self.server.task_state = {**self.server.task_state, "state": "stopped", "running": False, "progress": 1.0}
            self._reply(200, request_id, result={**self.server.task, "cancelled": True, "output": self.server.task_state})
        else:  # pragma: no cover - every declared role is handled above
            self._reply(501, request_id, code="operation_not_implemented")


def _allow_test_process(_pid: int, _executable: Path) -> bool:
    return True


def _future_registry() -> RatsProviderRegistry:
    return RatsProviderRegistry(
        {
            "reverie.engine": RatsProviderSpec(
                provider_id="reverie.engine",
                product="Reverie Engine",
                service_kinds=("builtin",),
                executable_validator=lambda executable: executable.is_file(),
                process_validator=_allow_test_process,
                discovery_root_resolver=lambda executable: executable.parent / "ReverieLocal" / "RATS" / "Services",
                # Deliberately narrower than what the service declares, so the
                # only way `telemetry` can reach a request is off the wire.
                permission_classes=RATS_SUPPORTED_PROVIDERS["reverie.engine"].permission_classes,
                label="Future RATS Test Fixture",
                tool_tags=("reverie-engine", "test-fixture"),
            )
        }
    )


def _test_root(name: str) -> Path:
    root = Path(__file__).resolve().parents[2] / "dist" / ".reverie" / "test-temp" / f"rats-{name}-{uuid.uuid4().hex}"
    root.mkdir(parents=True, exist_ok=True)
    return root


def _start_future_server():
    server = ThreadingHTTPServer(("127.0.0.1", 0), _FutureRatsHandler)
    server.service_id = f"rats-{os.getpid()}-future"
    server.provider_id = "reverie.engine"
    server.service_kind = "builtin"
    server.product = "Reverie Engine"
    server.control_token = CONTROL_TOKEN
    server.session_token = SESSION_TOKEN
    server.session_open = False
    server.granted_permissions = []
    server.task = {}
    server.task_state = {}
    server.requests = []
    server.wire_names = []
    server.unknown_names = []
    server.legacy_headers = []
    server.describe_batches = []
    server.search_limits = []
    server.event_limits = []
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return server, thread


def _write_future_descriptor(services: Path, server: ThreadingHTTPServer, executable: Path) -> None:
    services.mkdir(parents=True, exist_ok=True)
    (services / f"{server.service_id}.json").write_text(
        json.dumps(
            {
                "schema": "reverie.rats.discovery/1",
                "protocol": RATS_PROTOCOL,
                "service_id": server.service_id,
                "provider_id": server.provider_id,
                "service_kind": server.service_kind,
                "product": server.product,
                "product_version": "test",
                "executable": str(executable.resolve()),
                "pid": os.getpid(),
                "port": server.server_port,
                "endpoint": f"http://127.0.0.1:{server.server_port}/rtp",
                "bind_address": "127.0.0.1",
                "catalog_revision": "catalog-future",
                "native_tool_count": len(FUTURE_TOOL_NAMES),
                "started_utc": "2026-08-28T00:00:00Z",
                "control_token": server.control_token,
            }
        ),
        encoding="utf-8",
    )


def _prepare_future_service(root: Path, server: ThreadingHTTPServer) -> Path:
    executable = root / "engine" / "reverie.windows.editor.x86_64.exe"
    executable.parent.mkdir(parents=True, exist_ok=True)
    executable.write_bytes(b"test")
    _write_future_descriptor(executable.parent / "ReverieLocal" / "RATS" / "Services", server, executable)
    return executable


def test_the_client_is_driven_by_the_published_contract_not_its_own_constants() -> None:
    root = _test_root("contract-derivation")
    server, thread = _start_future_server()
    try:
        executable = _prepare_future_service(root, server)
        runtime = RatsRuntime(root / "cli", provider_registry=_future_registry())
        runtime.add_engine(executable)
        # `telemetry` is not in this build's provider spec. It survives storage by
        # shape and reaches the request because the service declared it.
        state = runtime.set_engine_enabled(executable, True, ["read", "run", "telemetry"])
        service = state["services"][0]
        service_id = service["serviceId"]

        # -- the service was reached at all, which required its renamed names ----
        assert service["connection"] == "connected"
        assert service["error"] == ""
        assert server.unknown_names == []
        assert server.legacy_headers == []
        assert set(server.wire_names) <= set(RENAMED_OPERATIONS.values())
        assert "rtp.v2/open-session" in server.wire_names
        assert "rtp.v2/tool-index" in server.wire_names

        # -- the published facts, not the compiled-in ones -----------------------
        assert service["contract"] == RATS_CAPABILITY_CONTRACT
        assert service["declaredPermissions"] == ["read", "run", "telemetry"]
        assert service["permissionToolCounts"] == {"read": 6, "run": 3, "telemetry": 2}
        assert service["limits"] == FUTURE_LIMITS
        assert "telemetry_sampling" in service["features"]
        assert service["permissions"] == ["read", "run", "telemetry"]
        assert server.granted_permissions == ["read", "run", "telemetry"]

        # -- the preload budget came from session.open, not from the client ------
        assert sorted(service["loadedToolNames"]) == sorted(FUTURE_BOOTSTRAP_TOOLS)
        assert set(FUTURE_BOOTSTRAP_TOOLS) != set(FALLBACK_BOOTSTRAP_TOOLS)

        # -- request bounds are the service's, and it enforces them itself -------
        assert runtime.request_limits() == {"describe_tools": 4, "search_results": 3, "task_events": 7}
        definitions = runtime.describe(service_id, FUTURE_TOOL_NAMES)
        assert len(definitions) == FUTURE_LIMITS["describe_tools"]
        assert all(len(batch) <= FUTURE_LIMITS["describe_tools"] for batch in server.describe_batches)

        matches = runtime.search("telemetry", limit=50, service_id=service_id)
        assert matches and matches[0]["name"] == "telemetry.sample"
        assert all(value is None or value <= FUTURE_LIMITS["search_results"] for value in server.search_limits)

        # -- the tool the client could not have known about is callable ----------
        sampled = runtime.call_tool(service_id, "telemetry.sample", {})
        assert sampled["output"] == {"sampled": True}

        # -- envelope limits are the service's too -------------------------------
        with pytest.raises(ValueError):
            runtime.call_tool(service_id, "ping", {}, deadline_ms=FUTURE_LIMITS["deadline_ms"] + 1)
        runtime.call_tool(service_id, "ping", {}, deadline_ms=FUTURE_LIMITS["deadline_ms"])
        with pytest.raises(ValueError):
            runtime.call_tool(service_id, "ping", {}, idempotency_key="k" * (FUTURE_LIMITS["idempotency_key_bytes"] + 1))

        started = runtime.call_tool(service_id, "run.play", {})
        task_id = started["task"]["task_id"]
        with pytest.raises(ValueError) as event_limit:
            runtime.task_events(service_id, task_id, limit=FUTURE_LIMITS["task_events"] + 1)
        assert str(FUTURE_LIMITS["task_events"]) in str(event_limit.value)
        events = runtime.task_events(service_id, task_id, limit=FUTURE_LIMITS["task_events"])
        assert [event["type"] for event in events["events"]] == ["task.started"]
        assert runtime.task_status(service_id, task_id)["running"] is True
        assert runtime.cancel_task(service_id, task_id)["cancelled"] is True

        # -- the schema shown to the model carries the service's bounds ----------
        catalog_tool = RatsCatalogTool(context={"rats_runtime": runtime})
        parameters = catalog_tool.parameters["properties"]
        assert parameters["names"]["maxItems"] == FUTURE_LIMITS["describe_tools"]
        assert parameters["max_results"]["maximum"] == FUTURE_LIMITS["search_results"]
        assert parameters["max_results"]["default"] <= FUTURE_LIMITS["search_results"]

        # -- the learned class is persisted, so it survives the service going away
        settings = json.loads((root / "cli" / ".reverie" / "rats" / "settings.json").read_text(encoding="utf-8"))
        assert settings["schemaVersion"] == 3
        assert settings["providerPermissionClasses"]["reverie.engine"] == ["read", "run", "telemetry"]
        assert settings["enabledProviders"][0]["permissions"] == ["read", "run", "telemetry"]
        assert "telemetry" in state["supportedProviders"][0]["permissions"]

        runtime.shutdown()
        assert "rtp.v2/close-session" in server.wire_names
        assert server.session_open is False
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)
        shutil.rmtree(root, ignore_errors=True)


def test_the_same_service_is_unreachable_when_the_contract_is_not_read(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Prove the test above can go red.

    With contract parsing forced to the pre-contract fallback, the client sends
    the v1 names through the v1 headers — exactly what it did before this change
    — and this service has neither. If the assertions above could pass in this
    state they would be measuring nothing.
    """
    root = _test_root("contract-blind")
    server, thread = _start_future_server()
    try:
        executable = _prepare_future_service(root, server)
        monkeypatch.setattr(
            rats_module,
            "parse_capabilities",
            lambda hello_result, protocol=RATS_PROTOCOL: (rats_module.fallback_capabilities(), []),
        )
        runtime = RatsRuntime(root / "cli", provider_registry=_future_registry())
        runtime.add_engine(executable)
        state = runtime.set_engine_enabled(executable, True, ["read", "run", "telemetry"])
        service = state["services"][0]

        assert service["connection"] != "connected"
        assert service["sessionActive"] is False
        assert service["error"]
        # It failed for the reason claimed: it asked for a name this service does
        # not publish.
        assert "session.open" in server.unknown_names
        assert service["contract"] == ""
        assert service["limits"] == dict(FALLBACK_LIMITS)
        # A blind client also cannot see the class it was granted.
        assert service["declaredPermissions"] == sorted(FALLBACK_PERMISSIONS)
        assert "telemetry" not in service["permissions"]
        with pytest.raises((RatsClientError, ValueError)):
            runtime.call_tool(service["serviceId"], "telemetry.sample", {})
        runtime.shutdown()
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)
        shutil.rmtree(root, ignore_errors=True)
