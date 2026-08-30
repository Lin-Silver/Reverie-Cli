"""Retry safety: the two published facts, and the decision they justify.

A client that retries on ``retryable`` alone will execute a tool twice. The flag
answers "may the condition pass on a later attempt?", which is not the question a
retry asks — that question is "did my request already take effect?". For
``MAIN_THREAD_TIMEOUT`` the answers differ: the condition may well pass, and the
call the timeout gave up waiting for is still queued.

So the service publishes both. Each error row carries ``retry``
(``safe``/``unsafe``/``never``) and each operation row carries ``effects``
(``none``/``idempotent``/``mutating``). This file proves three things:

1. the reader takes both off the wire, and degrades *restrictively* — a service
   that publishes neither is never retried, which is what this client did before;
2. ``may_retry`` needs both, so a rule consulting only one is visibly wrong here
   rather than subtly wrong in production;
3. the runtime's retry loop obeys it, is bounded by attempts *and* wall clock,
   and records both facts so a retry that turns out to have been wrong is
   diagnosable from the log alone;
4. the loop stays off the paths where a retry costs the user wall clock and buys
   nothing — the liveness probes and teardowns inside a discovery scan, whose
   failure already has a cheap local fallback.
"""

from __future__ import annotations

import contextlib
import hashlib
import json
import socket
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest

import reverie.rats as rats_module
from reverie.rats import (
    RATS_PROTOCOL,
    RATS_SUPPORTED_PROVIDERS,
    RatsClientError,
    RatsDescriptor,
    RatsProviderRegistry,
    RatsProviderSpec,
    RatsRuntime,
)
from reverie.rats_contract import (
    DEFAULT_EFFECTS,
    DEFAULT_ERROR_RETRY,
    EFFECTS_IDEMPOTENT,
    EFFECTS_MUTATING,
    EFFECTS_NONE,
    FEATURE_RETRY_SEMANTICS,
    RATS_CAPABILITY_CONTRACT,
    RATS_CLIENT_ROLES,
    RETRY_NEVER,
    RETRY_SAFE,
    RETRY_UNSAFE,
    fallback_capabilities,
    parse_capabilities,
)


# The effects the engine publishes, restated here rather than imported: this file
# has to fail when the service changes its mind about one of them, and importing
# the engine's own answer would make that impossible.
ENGINE_EFFECTS = {
    "hello": EFFECTS_NONE,
    "session.open": EFFECTS_IDEMPOTENT,
    "session.close": EFFECTS_IDEMPOTENT,
    "status": EFFECTS_NONE,
    "catalog.index": EFFECTS_NONE,
    "catalog.describe": EFFECTS_NONE,
    "catalog.search": EFFECTS_NONE,
    "tool.call": EFFECTS_MUTATING,
    "task.status": EFFECTS_NONE,
    "task.events": EFFECTS_NONE,
    "task.cancel": EFFECTS_IDEMPOTENT,
}


def _reasons(rejections) -> set:
    return {str(item.get("reason") or "") for item in rejections}


def _contract(
    *,
    effects: dict | None = None,
    error_codes: list | None = None,
    default_retry: str | None = RETRY_NEVER,
    default_retryable: bool = False,
    features: list | None = None,
) -> dict:
    """A complete, clean contract, parameterised on the parts under test.

    Complete because an incomplete one produces rejections of its own, and a test
    about ``retry`` must not pass or fail on unrelated noise.
    """
    stated = ENGINE_EFFECTS if effects is None else effects
    operations = []
    for role in RATS_CLIENT_ROLES:
        row = {
            "role": role,
            "operation": role,
            "auth": "none" if role == "hello" else ("control" if role == "session.open" else "session"),
            "summary": f"{role} summary",
        }
        if role in stated:
            row["effects"] = stated[role]
        operations.append(row)
    default: dict = {"status": 400, "retryable": default_retryable, "category": "request"}
    if default_retry is not None:
        default["retry"] = default_retry
    return {
        "contract": RATS_CAPABILITY_CONTRACT,
        "protocol": RATS_PROTOCOL,
        "roles": {role: role for role in RATS_CLIENT_ROLES},
        "operations": operations,
        "auth_headers": {"control": "X-Test-Control", "session": "X-Test-Session"},
        "permissions": [{"name": "read", "tool_count": 4}, {"name": "run", "tool_count": 2}],
        "features": features if features is not None else [FEATURE_RETRY_SEMANTICS],
        "constraints": ["single_active_session"],
        "limits": {"request_bytes": 1 << 20, "deadline_ms": 5_000},
        "errors": {
            "default": default,
            "codes": error_codes
            if error_codes is not None
            else [
                {"code": "deadline_exceeded", "status": 408, "retryable": True, "retry": RETRY_SAFE, "category": "deadline"},
                {
                    "code": "MAIN_THREAD_TIMEOUT",
                    "status": 500,
                    "retryable": True,
                    "retry": RETRY_UNSAFE,
                    "category": "engine",
                },
                {"code": "unauthorized", "status": 401, "retryable": False, "retry": RETRY_NEVER, "category": "auth"},
            ],
        },
        "task_event_schema": "reverie.rtp.task/1",
    }


def _parse(**kwargs):
    return parse_capabilities({"capabilities": _contract(**kwargs)})


# ---------------------------------------------------------------------------
# Reading the two fields
# ---------------------------------------------------------------------------


def test_both_published_facts_are_read_off_the_wire() -> None:
    capabilities, rejections = _parse()

    assert rejections == []
    assert capabilities.has_feature(FEATURE_RETRY_SEMANTICS) is True
    for role, effects in ENGINE_EFFECTS.items():
        assert capabilities.effects(role) == effects, role
    assert capabilities.error("deadline_exceeded").retry == RETRY_SAFE
    assert capabilities.error("deadline_exceeded").proves_no_effect is True
    assert capabilities.error("MAIN_THREAD_TIMEOUT").retry == RETRY_UNSAFE
    # The distinction the whole design exists for: both are retryable, and only
    # one of them proves the request never ran.
    assert capabilities.error("MAIN_THREAD_TIMEOUT").retryable is True
    assert capabilities.error("MAIN_THREAD_TIMEOUT").proves_no_effect is False


def test_a_service_older_than_the_fields_is_silent_but_gets_no_retries() -> None:
    # Neither field published anywhere. That is a service predating them, not a
    # malformed one, so it must not be reported...
    capabilities, rejections = _parse(effects={}, default_retry=None, error_codes=[
        {"code": "deadline_exceeded", "status": 408, "retryable": True, "category": "deadline"},
    ])

    assert rejections == []
    # ...and it must not be retried either, however retryable it calls its codes.
    assert capabilities.effects("status") == EFFECTS_MUTATING
    assert capabilities.error("deadline_exceeded").retryable is True
    assert capabilities.error("deadline_exceeded").retry == RETRY_NEVER
    assert capabilities.may_retry("status", "deadline_exceeded") is False


def test_an_unrecognised_semantic_is_reported_rather_than_mapped_onto_a_familiar_one() -> None:
    capabilities, rejections = _parse(
        effects={"status": "readonly", "tool.call": EFFECTS_MUTATING},
        error_codes=[{"code": "wedged", "status": 500, "retryable": True, "retry": "probably", "category": "engine"}],
    )

    assert _reasons(rejections) == {"unknown_effects", "unknown_retry"}
    # A value this build cannot evaluate is worth nothing, so it falls to the
    # refusing default in both positions. "readonly" plainly *means* `none`, and
    # that is exactly the inference that must not be made: the next unknown value
    # will not be so obvious.
    assert capabilities.effects("status") == DEFAULT_EFFECTS
    assert capabilities.error("wedged").retry == DEFAULT_ERROR_RETRY
    assert capabilities.may_retry("status", "wedged") is False


def test_an_unrecognised_default_retry_does_not_poison_the_rows_that_state_their_own() -> None:
    capabilities, rejections = _parse(
        default_retry="eventually",
        error_codes=[
            {"code": "stated", "status": 500, "retryable": True, "retry": RETRY_SAFE, "category": "engine"},
            {"code": "silent", "status": 500, "retryable": True, "category": "engine"},
        ],
    )

    assert "unknown_retry" in _reasons(rejections)
    assert capabilities.error("stated").retry == RETRY_SAFE
    # The unreadable default becomes the refusing one, and a row that omitted
    # `retry` inherits that rather than the value nobody could read.
    assert capabilities.error("silent").retry == RETRY_NEVER
    assert capabilities.error("nothing_like_this").retry == RETRY_NEVER


def test_error_rows_inherit_the_declared_retry_default() -> None:
    capabilities, rejections = _parse(
        default_retry=RETRY_SAFE,
        error_codes=[
            {"code": "silent", "status": 500, "retryable": True, "category": "engine"},
            {"code": "stated", "status": 500, "retryable": True, "retry": RETRY_UNSAFE, "category": "engine"},
        ],
    )

    assert rejections == []
    # A service states its own baseline once instead of repeating it on every row.
    assert capabilities.error("silent").retry == RETRY_SAFE
    assert capabilities.error("stated").retry == RETRY_UNSAFE
    # An unfamiliar code inherits that baseline too — but `retryable` is a
    # separate gate, and this contract's default row does not open it. A `safe`
    # retry semantic on a code the service calls non-retryable means "re-sending
    # would not double anything", not "re-sending would help".
    assert capabilities.error("added_later").retry == RETRY_SAFE
    assert capabilities.error("added_later").retryable is False
    assert capabilities.describes_error("added_later") is False
    assert capabilities.may_retry("tool.call", "added_later") is False

    # With both defaults open, a code added after this client shipped is
    # retryable without a client change, which is the point of publishing them.
    permissive, _ = _parse(default_retry=RETRY_SAFE, default_retryable=True, error_codes=[])
    assert permissive.may_retry("tool.call", "added_later") is True


# ---------------------------------------------------------------------------
# may_retry: the whole truth table
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("effects", [EFFECTS_NONE, EFFECTS_IDEMPOTENT, EFFECTS_MUTATING])
@pytest.mark.parametrize(
    ("retryable", "retry"),
    [
        (False, RETRY_NEVER),
        (False, RETRY_SAFE),  # contradictory; `retryable` is the harder gate
        (False, RETRY_UNSAFE),
        (True, RETRY_NEVER),
        (True, RETRY_SAFE),
        (True, RETRY_UNSAFE),
    ],
)
def test_may_retry_truth_table(retryable: bool, retry: str, effects: str) -> None:
    capabilities, rejections = parse_capabilities(
        {
            "capabilities": {
                **_contract(
                    effects={"probe": effects},
                    error_codes=[
                        {"code": "probe_failed", "status": 500, "retryable": retryable, "retry": retry, "category": "x"}
                    ],
                ),
                # A role invented for this table, declared the way any other is.
                "roles": {**{role: role for role in RATS_CLIENT_ROLES}, "probe": "probe"},
                "operations": [
                    {"role": "probe", "operation": "probe", "auth": "session", "effects": effects, "summary": "probe"}
                ],
            }
        }
    )
    assert _reasons(rejections) <= {"role_disagreement"}, rejections

    # Two independent gates, and both must open. `retryable` says the condition
    # may pass; `retry` says whether the request already took effect; `effects`
    # says whether acting twice matters — and only `unsafe` has to ask.
    if not retryable or retry == RETRY_NEVER:
        expected = False
    elif retry == RETRY_SAFE:
        expected = True
    else:
        expected = effects in (EFFECTS_NONE, EFFECTS_IDEMPOTENT)

    assert capabilities.may_retry("probe", "probe_failed") is expected


def test_the_engine_case_that_makes_effects_necessary() -> None:
    capabilities, _ = _parse()

    # One code, two operations, two answers. `MAIN_THREAD_TIMEOUT` means the call
    # was queued and the wait gave up — it was not cancelled, and the engine
    # releases the idempotency reservation on error while writing the replay
    # record only on success, so a retry re-dispatches rather than replaying.
    assert capabilities.error("MAIN_THREAD_TIMEOUT").retryable is True
    assert capabilities.may_retry("tool.call", "MAIN_THREAD_TIMEOUT") is False
    assert capabilities.may_retry("session.open", "MAIN_THREAD_TIMEOUT") is True
    assert capabilities.may_retry("status", "MAIN_THREAD_TIMEOUT") is True

    # A failure that proves nothing ran needs no such question asked.
    assert capabilities.may_retry("tool.call", "deadline_exceeded") is True


def test_a_pre_contract_service_is_retried_for_nothing_but_hello() -> None:
    capabilities = fallback_capabilities({"protocol": RATS_PROTOCOL})

    assert capabilities.declared is False
    # `hello` is the request that fetches the contract, so it can never be
    # governed by one; the protocol defines it as an anonymous read. Without this
    # a transport blip during discovery could never be retried, and discovery is
    # precisely when no contract exists.
    assert capabilities.effects("hello") == EFFECTS_NONE
    for role in RATS_CLIENT_ROLES:
        if role == "hello":
            continue
        assert capabilities.effects(role) == EFFECTS_MUTATING, role
    # It publishes no taxonomy at all, so every code lands on the refusing default.
    assert capabilities.error("deadline_exceeded").retry == RETRY_NEVER
    assert capabilities.may_retry("hello", "deadline_exceeded") is False


# ---------------------------------------------------------------------------
# The runtime's retry loop
# ---------------------------------------------------------------------------


def _descriptor(port: int = 65_000) -> RatsDescriptor:
    return RatsDescriptor(
        service_id="rats-retry-fixture",
        provider_id="reverie.engine",
        service_kind="builtin",
        product="Reverie Engine",
        product_version="test",
        executable=Path("reverie.windows.editor.x86_64.exe"),
        pid=1,
        port=port,
        endpoint=f"http://127.0.0.1:{port}/rtp",
        descriptor_path=Path("rats-retry-fixture.json"),
        catalog_revision="catalog-retry",
        native_tool_count=1,
        started_utc="2026-08-29T00:00:00Z",
        control_token="c" * 64,
    )


class _Attempts:
    """Stands in for the transport, counting calls and failing on cue."""

    def __init__(self, failures: int, error: RatsClientError) -> None:
        self.remaining = failures
        self.error = error
        self.calls = 0

    def __call__(self, *_args, **_kwargs) -> dict:
        self.calls += 1
        if self.remaining > 0:
            self.remaining -= 1
            raise self.error
        return {"ok": True}


def _runtime(tmp_path: Path) -> RatsRuntime:
    return RatsRuntime(tmp_path / "cli")


def _failure(code: str, retry: str, *, retryable: bool = True) -> RatsClientError:
    return RatsClientError(f"{code} from fixture", status=500, code=code, retryable=retryable, retry=retry)


def _run(runtime: RatsRuntime, role: str, attempts: _Attempts, capabilities) -> dict:
    runtime._attempt_request = attempts  # type: ignore[method-assign]
    return runtime._request(_descriptor(), role, {}, capabilities=capabilities)


@pytest.fixture(autouse=True)
def _fast_backoff(monkeypatch: pytest.MonkeyPatch) -> None:
    # The shipped backoff is 0.12 s doubling, which is right against a ~0.6 ms
    # `status` and wrong for a test suite. Only the delay is shortened; every
    # gate under test keeps its real value.
    monkeypatch.setattr(rats_module, "_RETRY_BACKOFF_SECONDS", 0.001)


def test_the_attempt_ceiling_is_reachable_within_the_wall_clock_budget() -> None:
    # If the budget were smaller than the worst-case backoff sum, the attempt
    # limit would be dead code and every failure would report a different count
    # than the constant says. Asserted on the shipped values, not the patched one.
    worst_case = sum(0.12 * (2 ** i) for i in range(rats_module._RETRY_MAX_ATTEMPTS - 1))
    assert worst_case < rats_module._RETRY_TOTAL_BUDGET_SECONDS
    assert rats_module._RETRY_MAX_ATTEMPTS >= 2


def test_a_safe_failure_is_retried_even_on_a_mutating_operation(tmp_path: Path) -> None:
    capabilities, _ = _parse()
    attempts = _Attempts(1, _failure("deadline_exceeded", RETRY_SAFE))

    result = _run(_runtime(tmp_path), "tool.call", attempts, capabilities)

    assert result == {"ok": True}
    assert attempts.calls == 2


def test_an_unsafe_failure_is_refused_on_tool_call_and_retried_on_session_open(tmp_path: Path) -> None:
    capabilities, _ = _parse()

    mutating = _Attempts(1, _failure("MAIN_THREAD_TIMEOUT", RETRY_UNSAFE))
    with pytest.raises(RatsClientError) as raised:
        _run(_runtime(tmp_path), "tool.call", mutating, capabilities)
    # One attempt, and the caller can tell that from the exception rather than
    # having to infer it: a first-attempt failure is a different situation from
    # one that survived retrying, even with an identical code.
    assert mutating.calls == 1
    assert raised.value.attempts == 1
    assert raised.value.retry == RETRY_UNSAFE

    idempotent = _Attempts(1, _failure("MAIN_THREAD_TIMEOUT", RETRY_UNSAFE))
    assert _run(_runtime(tmp_path), "session.open", idempotent, capabilities) == {"ok": True}
    assert idempotent.calls == 2


def test_a_permanent_failure_is_never_retried(tmp_path: Path) -> None:
    capabilities, _ = _parse()
    attempts = _Attempts(1, _failure("unauthorized", RETRY_NEVER, retryable=False))

    with pytest.raises(RatsClientError) as raised:
        _run(_runtime(tmp_path), "status", attempts, capabilities)

    assert attempts.calls == 1
    assert raised.value.attempts == 1


def test_the_attempt_ceiling_bounds_a_failure_that_never_clears(tmp_path: Path) -> None:
    capabilities, _ = _parse()
    attempts = _Attempts(99, _failure("deadline_exceeded", RETRY_SAFE))

    with pytest.raises(RatsClientError) as raised:
        _run(_runtime(tmp_path), "status", attempts, capabilities)

    assert attempts.calls == rats_module._RETRY_MAX_ATTEMPTS
    assert raised.value.attempts == rats_module._RETRY_MAX_ATTEMPTS


def test_the_wall_clock_budget_stops_the_sequence_before_the_attempt_ceiling(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # `deadline_ms` is measured by the service from each request's arrival, so a
    # retry restarts the service-side clock and only the client can hold a
    # ceiling over the whole sequence. A budget too small to sleep in must stop
    # the sequence rather than sleep past it.
    monkeypatch.setattr(rats_module, "_RETRY_BACKOFF_SECONDS", 1.0)
    monkeypatch.setattr(rats_module, "_RETRY_TOTAL_BUDGET_SECONDS", 0.05)
    capabilities, _ = _parse()
    attempts = _Attempts(99, _failure("deadline_exceeded", RETRY_SAFE))

    with pytest.raises(RatsClientError) as raised:
        _run(_runtime(tmp_path), "status", attempts, capabilities)

    assert attempts.calls == 1
    assert raised.value.attempts == 1
    assert rats_module._RETRY_MAX_ATTEMPTS > 1  # so the ceiling is not what stopped it


def test_a_transport_failure_is_judged_by_effects_because_the_service_never_answered(tmp_path: Path) -> None:
    capabilities, _ = _parse()
    # No `retry` on the exception: this class of failure is raised by the client,
    # so there is no published statement to read. The service could not classify
    # what it never received.
    for code in ("transport_error", "result_hash_mismatch", "response_id_mismatch"):
        readable = _Attempts(1, RatsClientError("no answer", code=code))
        assert _run(_runtime(tmp_path), "status", readable, capabilities) == {"ok": True}
        assert readable.calls == 2, code

        mutating = _Attempts(1, RatsClientError("no answer", code=code))
        with pytest.raises(RatsClientError):
            _run(_runtime(tmp_path), "tool.call", mutating, capabilities)
        assert mutating.calls == 1, code


def test_a_client_detected_protocol_disagreement_is_permanent(tmp_path: Path) -> None:
    capabilities, _ = _parse()
    # Not in the transport class: the client and service disagree about the
    # protocol itself, and re-sending the same envelope cannot change that.
    attempts = _Attempts(1, RatsClientError("wrong protocol", code="protocol_mismatch"))

    with pytest.raises(RatsClientError):
        _run(_runtime(tmp_path), "status", attempts, capabilities)

    assert attempts.calls == 1


def test_a_retry_records_both_published_facts(tmp_path: Path) -> None:
    capabilities, _ = _parse()
    runtime = _runtime(tmp_path)
    attempts = _Attempts(1, _failure("MAIN_THREAD_TIMEOUT", RETRY_UNSAFE))

    _run(runtime, "session.open", attempts, capabilities)

    logged = [entry for entry in runtime._diagnostics if entry.get("event") == "rtp.retry"]
    assert len(logged) == 1
    entry = logged[0]
    # "Why did it retry" is answerable from the log alone, which needs both facts
    # and not the decision they produced.
    assert entry["retry"] == RETRY_UNSAFE
    assert entry["effects"] == EFFECTS_IDEMPOTENT
    assert entry["reason"] == "MAIN_THREAD_TIMEOUT"
    assert entry["attempt"] == 1
    assert entry["operation"] == "session.open"
    assert entry["level"] == "warning"
    assert "delayMs" in entry
    # And it reached the file, not just the in-memory ring.
    written = [
        json.loads(line)
        for line in runtime.diagnostics_path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    assert any(item.get("event") == "rtp.retry" for item in written)


def test_a_pre_contract_service_gets_no_retries_from_the_runtime_either(tmp_path: Path) -> None:
    # The end-to-end shape of the restrictive default: no contract, a code the
    # service calls retryable, and still exactly one attempt.
    attempts = _Attempts(1, _failure("deadline_exceeded", ""))

    with pytest.raises(RatsClientError) as raised:
        _run(_runtime(tmp_path), "status", attempts, fallback_capabilities())

    assert attempts.calls == 1
    assert raised.value.attempts == 1


# ---------------------------------------------------------------------------
# The field actually crossing the wire
# ---------------------------------------------------------------------------


class _ScriptedRatsHandler(BaseHTTPRequestHandler):
    """Replies from a script, so a wire field can be asserted end to end."""

    def log_message(self, _format: str, *_args) -> None:
        return

    def do_POST(self) -> None:
        request = json.loads(self.rfile.read(int(self.headers.get("Content-Length", "0"))).decode("utf-8"))
        self.server.operations.append(str(request.get("op") or ""))
        reply = self.server.script.pop(0) if self.server.script else None

        if reply is None:
            status, value, key = 200, {"ok": True}, "result"
        else:
            status, value, key = reply[0], dict(reply[1]), "error"
        payload = {
            "id": request.get("id"),
            "protocol": RATS_PROTOCOL,
            "ok": status < 400,
            key: value,
            "audit_id": "audit-scripted",
            "result_sha256": hashlib.sha256(
                json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
            ).hexdigest(),
        }
        body = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


@contextlib.contextmanager
def _scripted_service(*replies):
    server = ThreadingHTTPServer(("127.0.0.1", 0), _ScriptedRatsHandler)
    server.script = list(replies)
    server.operations = []
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield server
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def _wire_error(code: str, *, retryable: bool = True, retry: str = "") -> tuple:
    error = {"code": code, "message": f"{code} from scripted service"}
    if retryable:
        error["retryable"] = True
    if retry:
        error["retry"] = retry
    return (500, error)


def test_the_retry_semantic_is_read_off_a_failed_response(tmp_path: Path) -> None:
    capabilities, _ = _parse()
    # `tool.call` is `mutating` and the taxonomy calls this code `unsafe`, so a
    # retry hangs entirely on what the response itself says.
    with _scripted_service(_wire_error("MAIN_THREAD_TIMEOUT", retry=RETRY_SAFE)) as server:
        runtime = _runtime(tmp_path)
        result = runtime._request(_descriptor(server.server_port), "tool.call", {}, capabilities=capabilities)

    assert result == {"ok": True}
    assert server.operations == ["tool.call", "tool.call"]


def test_an_inline_statement_the_caller_can_see(tmp_path: Path) -> None:
    capabilities, _ = _parse()
    with _scripted_service(_wire_error("MAIN_THREAD_TIMEOUT", retry=RETRY_UNSAFE)) as server:
        runtime = _runtime(tmp_path)
        with pytest.raises(RatsClientError) as raised:
            runtime._request(_descriptor(server.server_port), "tool.call", {}, capabilities=capabilities)

    # Refused, and the reason is on the exception rather than only in a log: a
    # caller deciding whether to surface "try again" needs the service's own word.
    assert server.operations == ["tool.call"]
    assert raised.value.retry == RETRY_UNSAFE
    assert raised.value.retryable is True
    assert raised.value.attempts == 1


def test_an_inline_semantic_this_build_cannot_evaluate_is_refused(tmp_path: Path) -> None:
    capabilities, _ = _parse()
    # Comes straight off the wire, so it bypasses the validating contract reader.
    # A service that has invented a fourth semantic gets no retry for it.
    with _scripted_service(_wire_error("deadline_exceeded", retry="probably")) as server:
        runtime = _runtime(tmp_path)
        with pytest.raises(RatsClientError):
            runtime._request(_descriptor(server.server_port), "status", {}, capabilities=capabilities)

    assert server.operations == ["status"]


def test_a_response_stating_retry_without_retryable_is_not_topped_up_from_the_taxonomy(tmp_path: Path) -> None:
    capabilities, _ = _parse()
    assert capabilities.error("deadline_exceeded").retryable is True
    # The taxonomy would allow this; the response would not. Mixing the two is how
    # a `safe` from one source authorises a retry the other never allowed, so the
    # response is read whole or not at all.
    with _scripted_service(_wire_error("deadline_exceeded", retryable=False, retry=RETRY_SAFE)) as server:
        runtime = _runtime(tmp_path)
        with pytest.raises(RatsClientError):
            runtime._request(_descriptor(server.server_port), "status", {}, capabilities=capabilities)

    assert server.operations == ["status"]


def test_a_response_that_states_nothing_falls_back_to_the_taxonomy(tmp_path: Path) -> None:
    capabilities, _ = _parse()
    # Every response a pre-`retry` service sends looks like this. The published
    # taxonomy calls the code safe, so the retry still happens.
    with _scripted_service(_wire_error("deadline_exceeded")) as server:
        runtime = _runtime(tmp_path)
        result = runtime._request(_descriptor(server.server_port), "tool.call", {}, capabilities=capabilities)

    assert result == {"ok": True}
    assert server.operations == ["tool.call", "tool.call"]



# ---------------------------------------------------------------------------
# Where the loop must stay out of the way
# ---------------------------------------------------------------------------


def test_a_caller_can_bound_the_sequence_to_one_attempt(tmp_path: Path) -> None:
    capabilities, _ = _parse(effects={"status": EFFECTS_NONE})
    attempts = _Attempts(1, _failure("deadline_exceeded", RETRY_SAFE))
    runtime = _runtime(tmp_path)
    runtime._attempt_request = attempts  # type: ignore[method-assign]

    # The failure is safe and the operation reads nothing, so the policy would
    # retry it. `attempts=1` is the caller saying the answer is wanted now.
    with pytest.raises(RatsClientError) as raised:
        runtime._request(_descriptor(), "status", {}, capabilities=capabilities, attempts=1)

    assert attempts.calls == 1
    assert raised.value.attempts == 1


def _probe_registry() -> RatsProviderRegistry:
    return RatsProviderRegistry(
        {
            "reverie.engine": RatsProviderSpec(
                provider_id="reverie.engine",
                product="Reverie Engine",
                service_kinds=("builtin",),
                executable_validator=lambda executable: executable.is_file(),
                process_validator=lambda _pid, _executable: True,
                discovery_root_resolver=lambda executable: executable.parent / "ReverieLocal" / "RATS" / "Services",
                permission_classes=RATS_SUPPORTED_PROVIDERS["reverie.engine"].permission_classes,
                label="Reverie Engine Retry Fixture",
                tool_tags=("reverie-engine", "retry-fixture"),
            ),
        }
    )


def test_a_dead_descriptor_is_probed_once_not_three_times(tmp_path: Path) -> None:
    """A stale descriptor must not put the backoff sequence in front of the user.

    A crashed editor leaves its descriptor behind, so an unreachable service is
    the ordinary case rather than the exceptional one, and a scan walks every
    descriptor in the directory. `hello` is `effects: none`, which makes a
    transport failure retryable on the general policy — correct for an
    operational request and wrong for a liveness probe. This asserts the count of
    transport attempts rather than the elapsed time, so it stays meaningful on a
    machine fast enough to absorb the sleeping.
    """
    executable = tmp_path / "engine" / "reverie.windows.editor.x86_64.exe"
    executable.parent.mkdir(parents=True, exist_ok=True)
    executable.write_bytes(b"test")
    services = executable.parent / "ReverieLocal" / "RATS" / "Services"
    services.mkdir(parents=True, exist_ok=True)
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as reserved:
        reserved.bind(("127.0.0.1", 0))
        closed_port = reserved.getsockname()[1]
    service_id = "rats-4321-dead"
    (services / f"{service_id}.json").write_text(
        json.dumps(
            {
                "schema": "reverie.rats.discovery/1",
                "protocol": RATS_PROTOCOL,
                "service_id": service_id,
                "provider_id": "reverie.engine",
                "service_kind": "builtin",
                "product": "Reverie Engine",
                "executable": str(executable.resolve()),
                "pid": 4321,
                "port": closed_port,
                "endpoint": f"http://127.0.0.1:{closed_port}/rtp",
                "bind_address": "127.0.0.1",
                "control_token": "c" * 64,
            }
        ),
        encoding="utf-8",
    )

    runtime = RatsRuntime(tmp_path / "cli", provider_registry=_probe_registry(), probe_timeout=0.1)
    state = runtime.add_engine(executable)

    assert state["services"] == []
    diagnostics = state["diagnostics"]
    probes = [
        item
        for item in diagnostics
        if item.get("event") == "rtp.request" and item.get("reason") == "transport_error"
    ]
    assert len(probes) == 1, diagnostics
    assert [item for item in diagnostics if item.get("event") == "rtp.retry"] == []


def test_closing_a_discarded_session_is_attempted_once(tmp_path: Path) -> None:
    """The caller has already stopped using the session, so a retry helps nobody.

    ``session.close`` is ``idempotent`` and the transport failure below is
    retryable on the general policy, which would make a teardown the slowest step
    in a scan that is about to discard the session either way. The service expires
    an abandoned session on its own.
    """
    capabilities, _ = _parse()
    attempts = _Attempts(3, RatsClientError("closed", code="transport_error"))
    runtime = _runtime(tmp_path)
    runtime._attempt_request = attempts  # type: ignore[method-assign]

    runtime._close_session(
        rats_module._RatsSession(
            descriptor=_descriptor(),
            token="s" * 64,
            permissions=["read"],
            capabilities=capabilities,
        )
    )

    assert attempts.calls == 1


class _PerOperation:
    """Stands in for the transport, answering per role and recording the order.

    ``_Attempts`` is enough where one request is under test. A refresh issues
    five, and the one being measured sits behind the others, so this answers each
    by name instead of by position.
    """

    def __init__(self, answers: dict) -> None:
        self.answers = answers
        self.calls: list[str] = []

    def __call__(self, _descriptor, role, _args=None, **_kwargs) -> dict:
        self.calls.append(str(role))
        answer = self.answers[str(role)]
        if isinstance(answer, RatsClientError):
            raise answer
        return answer


def _only_service(runtime: RatsRuntime, descriptor: RatsDescriptor, monkeypatch) -> None:
    """Point one refresh at one descriptor with its provider enabled."""
    settings = {
        "schemaVersion": rats_module.RATS_SETTINGS_VERSION,
        "discoveryRoots": [],
        "enabledProviders": [
            {
                "providerId": descriptor.provider_id,
                "executable": str(descriptor.executable),
                "permissions": ["read"],
                "discoveryRoot": str(descriptor.descriptor_path.parent),
            }
        ],
        "providerPermissionClasses": {},
    }
    monkeypatch.setattr(runtime, "_read_settings", lambda: settings)
    monkeypatch.setattr(runtime, "_roots", lambda _settings: [])
    monkeypatch.setattr(
        rats_module,
        "discover_rats_descriptors",
        lambda _roots, _rejections, _registry: [descriptor],
    )


def test_a_held_session_is_revalidated_once_and_then_reopened(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Asking twice whether a session is still good is the wrong second question.

    Every refresh revalidates each held session with a `status`, which is
    `effects: none`, so the general policy would retry a retryable failure there
    three times with backoff in between — inside the scan the user is waiting on.
    The failure branch already has a better answer than a second `status`:
    reopening. A service that dropped one request will answer `session.open`, and
    one that lost the session was never going to answer `status` at all.
    """
    capabilities, rejections = _parse()
    assert not rejections
    descriptor = _descriptor()
    hello = {
        "service_id": descriptor.service_id,
        "protocol": RATS_PROTOCOL,
        "provider_id": descriptor.provider_id,
        "service_kind": descriptor.service_kind,
        "product": descriptor.product,
        "capabilities": _contract(),
    }
    transport = _PerOperation(
        {
            "hello": hello,
            # Retryable and safe on a `none` operation: the one shape the policy
            # would retry, so the opt-out is the only thing stopping it.
            "status": _failure("deadline_exceeded", RETRY_SAFE),
            "session.close": {},
            "session.open": {"session_token": "a" * 64, "bootstrap_tools": []},
            "catalog.index": {"tools": []},
        }
    )
    runtime = _runtime(tmp_path)
    runtime._attempt_request = transport  # type: ignore[method-assign]
    with runtime._lock:
        runtime._sessions[(descriptor.provider_id, descriptor.service_id)] = rats_module._RatsSession(
            descriptor=descriptor,
            token="s" * 64,
            permissions=["read"],
            capabilities=capabilities,
        )
    _only_service(runtime, descriptor, monkeypatch)

    state = runtime.refresh()

    # Asked once, and the reopen actually happened rather than the refresh
    # reporting the service as gone.
    assert transport.calls.count("status") == 1, transport.calls
    assert transport.calls.count("session.open") == 1, transport.calls
    service = state["services"][0]
    assert service["connection"] == "connected", service
    assert service["sessionActive"] is True, service
    assert [item for item in state["diagnostics"] if item.get("event") == "rtp.retry"] == []

