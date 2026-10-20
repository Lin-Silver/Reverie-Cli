"""RIU P2 focused tests: callViewTool / updateViewModelContext + ViewStore P2.

Written FAILING-FIRST (docs/INTELLIGENT_UI_SPEC.md §6.1/§6.3): these drive the
gated interaction controller before it exists. The security properties under
test:

* ``callViewTool`` runs the tool ONLY through the agent's gated
  ``ToolExecutor.execute`` (cancellation -> read-only review -> security_policy
  -> approval gate). The standalone ``ensure_tool_executor`` is forbidden.
* Approval allow/deny, restricted-tool whitelist, busy executor, Stop during
  the approval wait, duplicate call-id idempotency (no write replay) and
  cross-session rejection all behave per the spec.
* ``updateViewModelContext`` stores an 8 KiB-capped, explicitly
  untrusted-user-data summary that is kept separate from the private
  ``setViewState`` display state and never escalated to a system role.
* ``callable_tools`` ride the manifest (and fork) but never reach the model
  reference; ``list_view_revisions`` enumerates a session's views.
"""

from __future__ import annotations

import json
import threading
import time
from types import SimpleNamespace

import pytest

from reverie.agent.tool_executor import ToolExecutor
from reverie.sdk_bridge import ReverieSdkBridge
from reverie.tools.base import BaseTool, ToolResult, ToolResultStatus
from reverie.views import MAX_VIEW_SUMMARY_BYTES, ViewIdentity, ViewStore, ViewStoreError

_HTML = "<!doctype html><title>chart</title><p>hello</p>"


class _Recorder:
    """Thread-safe event sink standing in for the kernel stdout writer."""

    def __init__(self) -> None:
        self._items = []
        self._lock = threading.Lock()

    def __call__(self, obj) -> None:
        with self._lock:
            self._items.append(obj)

    def snapshot(self):
        with self._lock:
            return list(self._items)

    def approvals(self):
        return [
            (rec.get("event") or {})
            for rec in self.snapshot()
            if rec.get("type") == "prompt.event"
            and (rec.get("event") or {}).get("type") == "approval.request"
        ]


class _EchoTool(BaseTool):
    """A minimal non-read-only tool so the strict-mode gate must fire."""

    name = "view_echo"
    description = "Echo tool used to exercise the RIU view interaction gate."
    read_only = False
    workspace_checkpoint = False
    parameters = {
        "type": "object",
        "properties": {"text": {"type": "string"}},
        "required": [],
    }

    def __init__(self, runs, context=None) -> None:
        super().__init__(context)
        self._runs = runs

    def validate_params(self, params):
        return None

    def execute(self, **kwargs) -> ToolResult:
        self._runs.append(dict(kwargs))
        return ToolResult.ok(f"echoed:{kwargs.get('text', '')}", data={"echo": dict(kwargs)})


def _write_html(tmp_path):
    artifact = tmp_path / "chart.html"
    artifact.write_text(_HTML, encoding="utf-8")
    return artifact


def _register_view(store, session_id, tmp_path, *, callable_tools=("view_echo",)):
    identity = ViewIdentity(session_id=session_id, turn_id="t1", tool_call_id="call-1")
    return store.register(
        artifact_path=_write_html(tmp_path),
        identity=identity,
        title="Chart",
        summary="A chart view.",
        workspace_root=tmp_path,
        callable_tools=callable_tools,
    )


def _make_bridge(tmp_path, *, session_id="s-main"):
    """Build a bridge wired to a REAL gated ToolExecutor and a recorder.

    No ``agent`` is placed in the executor context, so the gate reads the
    strict ``security`` dict directly; the FakeTool is injected by name.
    """
    runs = []
    recorder = _Recorder()

    executor = ToolExecutor(project_root=tmp_path)
    executor._tools["view_echo"] = _EchoTool(runs)
    executor._rebuild_tool_alias_lookup()
    executor.update_context(
        "security", {"permission_level": "full_control", "permission_mode": "strict"}
    )

    store = ViewStore(tmp_path / "views")
    session = SimpleNamespace(id=session_id, updated="2026-10-11T00:00:00Z")
    manager = SimpleNamespace(get_current_session=lambda: session)
    agent = SimpleNamespace(tool_executor=executor, config=None, mode="reverie")
    interface = SimpleNamespace(session_manager=manager, agent=agent)

    bridge = ReverieSdkBridge.__new__(ReverieSdkBridge)
    bridge.project_root = tmp_path
    bridge.interface = interface
    bridge.ensure_interface = lambda: interface
    bridge._view_store = lambda: store
    bridge.event_writer = recorder
    bridge._approval_waiters = {}
    bridge._approval_lock = threading.Lock()
    bridge._run_lock = threading.Lock()
    bridge._run_control = None
    bridge._run_identity = {}
    bridge._view_call_lock = threading.Lock()
    bridge._view_call_results = {}

    def _forbidden():
        raise AssertionError("callViewTool must not use the standalone ensure_tool_executor")

    bridge.ensure_tool_executor = _forbidden
    return SimpleNamespace(
        bridge=bridge, store=store, recorder=recorder, runs=runs,
        session_id=session_id, executor=executor,
    )


def _wait_for_approval(recorder, timeout=5.0):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        approvals = recorder.approvals()
        if approvals:
            return approvals[0].get("approval_id")
        time.sleep(0.02)
    return None


def _payload(view_id, *, tool="view_echo", call_id="call-A", args=None, source="user-gesture"):
    return {
        "viewId": view_id,
        "toolName": tool,
        "arguments": args if args is not None else {"text": "hi"},
        "callId": call_id,
        "source": source,
    }


def _call_with_approval(env, payload, *, decision="once", stop=False):
    """Dispatch callViewTool while a background thread answers the approval.

    The dispatch blocks in this thread (the approval gate waits), so the
    responder must run concurrently: it waits for the emitted
    ``approval.request`` and either resolves it or issues Stop.
    """
    done = {}

    def responder():
        approval_id = _wait_for_approval(env.recorder)
        if approval_id is None:
            return
        if stop:
            env.bridge.dispatch(
                {"id": "stop", "action": "stopPrompt", "payload": {"sessionId": env.session_id}}
            )
        else:
            env.bridge.dispatch(
                {
                    "id": "res",
                    "action": "resolveApproval",
                    "payload": {"approvalId": approval_id, "decision": decision},
                }
            )

    thread = threading.Thread(target=responder, daemon=True)
    thread.start()
    done["result"] = env.bridge.dispatch({"id": "call", "action": "callViewTool", "payload": payload})
    thread.join(timeout=10)
    return done["result"]


def _assert_no_html_or_path_leak(result, env, tmp_path):
    blob = json.dumps(result)
    assert "<p>hello</p>" not in blob
    assert "<!doctype" not in blob.lower()
    assert "chart.html" not in blob
    assert str(tmp_path) not in blob
    assert str(env.store.views_root) not in blob


def test_call_view_tool_approved_once_runs_through_the_gate(tmp_path):
    env = _make_bridge(tmp_path)
    view = _register_view(env.store, env.session_id, tmp_path)
    result = _call_with_approval(env, _payload(view.view_id), decision="once")

    assert result["status"] == "success"
    assert result.get("duplicate") is False
    assert result["callId"] == "call-A"
    assert result["viewId"] == view.view_id
    assert env.runs == [{"text": "hi"}]
    assert len(env.recorder.approvals()) == 1
    assert "echoed:hi" in json.dumps(result)
    _assert_no_html_or_path_leak(result, env, tmp_path)


def test_call_view_tool_denied_blocks_the_run(tmp_path):
    env = _make_bridge(tmp_path)
    view = _register_view(env.store, env.session_id, tmp_path)
    result = _call_with_approval(env, _payload(view.view_id), decision="deny")

    assert result["status"] == "error"
    assert result.get("error")
    assert env.runs == []
    assert len(env.recorder.approvals()) == 1


def test_call_view_tool_rejects_tool_outside_callable_allowlist(tmp_path):
    env = _make_bridge(tmp_path)
    view = _register_view(env.store, env.session_id, tmp_path, callable_tools=("data_api",))
    result = env.bridge.dispatch(
        {"id": "c", "action": "callViewTool", "payload": _payload(view.view_id, tool="view_echo")}
    )

    assert result["status"] == "error"
    assert result["reason"] == "restricted-tool"
    assert env.runs == []
    assert env.recorder.approvals() == []


def test_call_view_tool_reports_busy_when_a_run_holds_the_lock(tmp_path):
    env = _make_bridge(tmp_path)
    view = _register_view(env.store, env.session_id, tmp_path)
    env.bridge._run_lock.acquire()
    try:
        result = env.bridge.dispatch(
            {"id": "c", "action": "callViewTool", "payload": _payload(view.view_id)}
        )
    finally:
        env.bridge._run_lock.release()

    assert result["status"] == "busy"
    assert env.runs == []
    assert env.recorder.approvals() == []


def test_call_view_tool_stop_during_approval_cancels_without_running(tmp_path):
    env = _make_bridge(tmp_path)
    view = _register_view(env.store, env.session_id, tmp_path)
    result = _call_with_approval(env, _payload(view.view_id), stop=True)

    assert result["status"] == "cancelled"
    assert env.runs == []
    assert len(env.recorder.approvals()) == 1


def test_call_view_tool_duplicate_call_id_does_not_replay_the_write(tmp_path):
    env = _make_bridge(tmp_path)
    view = _register_view(env.store, env.session_id, tmp_path)
    payload = _payload(view.view_id, call_id="dup-1")

    first = _call_with_approval(env, payload, decision="once")
    assert first["status"] == "success"
    assert first.get("duplicate") is False

    second = env.bridge.dispatch({"id": "c2", "action": "callViewTool", "payload": payload})
    assert second.get("duplicate") is True
    assert second["status"] == "success"
    assert len(env.runs) == 1
    assert len(env.recorder.approvals()) == 1


def test_call_view_tool_rejects_cross_session_view(tmp_path):
    env = _make_bridge(tmp_path, session_id="s-main")
    other = _register_view(env.store, "s-other", tmp_path)
    with pytest.raises(ValueError, match="not stored"):
        env.bridge.dispatch(
            {"id": "c", "action": "callViewTool", "payload": _payload(other.view_id)}
        )
    assert env.runs == []


def test_call_view_tool_requires_view_tool_and_call_ids(tmp_path):
    env = _make_bridge(tmp_path)
    view = _register_view(env.store, env.session_id, tmp_path)
    with pytest.raises(ValueError, match="viewId"):
        env.bridge.dispatch({"id": "c", "action": "callViewTool",
                             "payload": {"toolName": "view_echo", "callId": "c1"}})
    with pytest.raises(ValueError, match="toolName"):
        env.bridge.dispatch({"id": "c", "action": "callViewTool",
                             "payload": {"viewId": view.view_id, "callId": "c1"}})
    with pytest.raises(ValueError, match="callId"):
        env.bridge.dispatch({"id": "c", "action": "callViewTool",
                             "payload": {"viewId": view.view_id, "toolName": "view_echo"}})
    assert env.runs == []


def test_update_view_model_context_stores_capped_untrusted_summary(tmp_path):
    env = _make_bridge(tmp_path)
    view = _register_view(env.store, env.session_id, tmp_path)
    result = env.bridge.dispatch(
        {"id": "ctx", "action": "updateViewModelContext",
         "payload": {"viewId": view.view_id, "summary": "the user typed <b>hi</b>", "source": "component"}}
    )
    assert result["status"] == "stored"

    stored = env.store.read_model_context(env.session_id, view.view_id)
    assert stored["summary"] == "the user typed <b>hi</b>"
    assert stored["trust"] == "untrusted-user-data"
    assert stored["source"] == "component"
    assert "role" not in stored and "system" not in stored


def test_update_view_model_context_rejects_oversize_summary(tmp_path):
    env = _make_bridge(tmp_path)
    view = _register_view(env.store, env.session_id, tmp_path)
    with pytest.raises(ValueError, match="exceeds"):
        env.bridge.dispatch(
            {"id": "ctx", "action": "updateViewModelContext",
             "payload": {"viewId": view.view_id, "summary": "A" * (MAX_VIEW_SUMMARY_BYTES + 1)}}
        )
    ok = env.bridge.dispatch(
        {"id": "ctx", "action": "updateViewModelContext",
         "payload": {"viewId": view.view_id, "summary": "B" * MAX_VIEW_SUMMARY_BYTES}}
    )
    assert ok["status"] == "stored"


def test_update_view_model_context_rejects_cross_session(tmp_path):
    env = _make_bridge(tmp_path, session_id="s-main")
    other = _register_view(env.store, "s-other", tmp_path)
    with pytest.raises(ValueError, match="not stored"):
        env.bridge.dispatch(
            {"id": "ctx", "action": "updateViewModelContext",
             "payload": {"viewId": other.view_id, "summary": "hi"}}
        )


def test_callable_tools_persist_on_manifest_but_hidden_from_model(tmp_path):
    store = ViewStore(tmp_path / "views")
    view = _register_view(store, "s-main", tmp_path, callable_tools=("view_echo", "data_api"))

    assert view.callable_tools == ("view_echo", "data_api")
    assert view.to_dict()["callable_tools"] == ["view_echo", "data_api"]
    assert "callable_tools" not in view.model_reference()

    reloaded = ViewStore(tmp_path / "views").manifest("s-main", view.view_id)
    assert reloaded.callable_tools == ("view_echo", "data_api")


def test_list_view_revisions_enumerates_and_ignores_unknown_sessions(tmp_path):
    store = ViewStore(tmp_path / "views")
    view = _register_view(store, "s-main", tmp_path)
    assert store.list_view_revisions("s-main") == [(view.view_id, 1)]
    assert store.list_view_revisions("s-ghost") == []


def test_model_context_is_isolated_from_private_display_state(tmp_path):
    env = _make_bridge(tmp_path)
    view = _register_view(env.store, env.session_id, tmp_path)
    env.store.write_state(env.session_id, view.view_id, state={"secret": "do-not-send"})
    env.bridge.dispatch(
        {"id": "ctx", "action": "updateViewModelContext",
         "payload": {"viewId": view.view_id, "summary": "safe public blurb"}}
    )

    mc = env.store.read_model_context(env.session_id, view.view_id)
    assert mc["summary"] == "safe public blurb"
    assert "do-not-send" not in json.dumps(mc)

    st = env.store.read_state(env.session_id, view.view_id)
    assert st["state"] == {"secret": "do-not-send"}
    assert "safe public blurb" not in json.dumps(st)


def test_fork_view_artifacts_copies_visible_revisions_and_rebinds(tmp_path):
    env = _make_bridge(tmp_path)
    view = _register_view(env.store, "s-main", tmp_path)
    env.bridge._fork_view_artifacts("s-main", "s-fork")
    assert env.store.list_view_revisions("s-fork") == [(view.view_id, 1)]
    assert env.store.manifest("s-fork", view.view_id).session_id == "s-fork"


def test_drop_view_artifacts_removes_the_session(tmp_path):
    env = _make_bridge(tmp_path)
    view = _register_view(env.store, "s-main", tmp_path)
    assert env.store.list_view_revisions("s-main") == [(view.view_id, 1)]
    env.bridge._drop_view_artifacts("s-main")
    assert env.store.list_view_revisions("s-main") == []


def test_duplicate_survives_a_new_bridge_and_never_replays(tmp_path):
    env = _make_bridge(tmp_path)
    view = _register_view(env.store, env.session_id, tmp_path)
    payload = _payload(view.view_id)
    assert _call_with_approval(env, payload)["status"] == "success"
    restarted = _make_bridge(tmp_path)
    restarted.bridge._request_tool_approval = lambda *args: "deny"
    result = restarted.bridge.dispatch({"id": "after-restart", "action": "callViewTool", "payload": payload})
    assert result["duplicate"] is True
    assert restarted.runs == []


def test_stop_call_id_cannot_be_reused_after_approval(tmp_path):
    env = _make_bridge(tmp_path)
    view = _register_view(env.store, env.session_id, tmp_path)
    payload = _payload(view.view_id)
    assert _call_with_approval(env, payload, stop=True)["status"] == "cancelled"
    env.bridge._request_tool_approval = lambda *args: "deny"
    result = env.bridge.dispatch({"id": "retry", "action": "callViewTool", "payload": payload})
    assert result["duplicate"] is True
    assert env.runs == []
    assert len(env.recorder.approvals()) == 1


def test_ledger_pending_write_is_unknown_after_restart(tmp_path):
    env = _make_bridge(tmp_path)
    view = _register_view(env.store, env.session_id, tmp_path)
    env.store.begin_call(env.session_id, view.view_id, 1, "call-A", "view_echo", {"text": "hi"})
    restarted = _make_bridge(tmp_path)
    result = restarted.bridge.dispatch({"id": "retry", "action": "callViewTool", "payload": _payload(view.view_id)})
    assert result["status"] == "unknown"
    assert result["duplicate"] is True
    assert restarted.runs == []


def test_stale_content_revision_cannot_change_state_or_execute(tmp_path):
    env = _make_bridge(tmp_path)
    view = _register_view(env.store, env.session_id, tmp_path)
    env.store.register(artifact_path=_write_html(tmp_path), identity=ViewIdentity(env.session_id, "t2", "c2"),
                       title="v2", summary="v2", workspace_root=tmp_path, replaces_view_id=view.view_id)
    with pytest.raises(ValueError, match="revision"):
        env.bridge.dispatch({"id": "stale", "action": "setViewState", "payload": {
            "viewId": view.view_id, "revision": 1, "baseRevision": 0, "state": {"x": 1}}})
    with pytest.raises(ValueError, match="revision"):
        env.bridge.dispatch({"id": "stale", "action": "callViewTool", "payload": {
            **_payload(view.view_id), "revision": 1}})
    assert env.runs == []


def test_component_default_policy_still_requires_host_approval_and_cannot_grant_session(tmp_path):
    env = _make_bridge(tmp_path)
    env.executor.update_context("security", {"permission_level": "full_control", "permission_mode": "default"})
    env.executor._session_approved_tools.add("view_echo")
    view = _register_view(env.store, env.session_id, tmp_path)
    assert _call_with_approval(env, _payload(view.view_id), decision="deny")["status"] == "error"
    assert env.recorder.approvals()[0]["source"] == "component"
    assert env.recorder.approvals()[0]["view_id"] == view.view_id
    assert env.recorder.approvals()[0]["scopes"] == ["once"]
    assert env.runs == []


def test_schema_error_never_reaches_approval(tmp_path):
    env = _make_bridge(tmp_path)
    view = _register_view(env.store, env.session_id, tmp_path)
    result = env.bridge.dispatch({"id": "bad", "action": "callViewTool", "payload": _payload(view.view_id, args={"text": 42})})
    assert result["reason"] == "invalid-arguments"
    assert env.recorder.approvals() == []
    assert env.runs == []


def test_reused_request_with_changed_arguments_is_rejected(tmp_path):
    env = _make_bridge(tmp_path)
    view = _register_view(env.store, env.session_id, tmp_path)
    assert _call_with_approval(env, _payload(view.view_id))["status"] == "success"
    with pytest.raises(ValueError, match="different tool arguments"):
        env.bridge.dispatch({"id": "changed", "action": "callViewTool", "payload": _payload(view.view_id, args={"text": "changed"})})
    assert len(env.runs) == 1


def test_late_tool_after_stop_is_not_delivered_as_success_or_replayed(tmp_path):
    env = _make_bridge(tmp_path)
    view = _register_view(env.store, env.session_id, tmp_path)
    entered, release = threading.Event(), threading.Event()
    def slow_execute(**kwargs):
        env.runs.append(kwargs)
        entered.set()
        assert release.wait(5)
        return ToolResult.ok("late success")
    env.executor._tools["view_echo"].execute = slow_execute
    env.bridge._request_tool_approval = lambda *args: "once"
    outcome = {}
    thread = threading.Thread(target=lambda: outcome.update(env.bridge.dispatch({"id": "slow", "action": "callViewTool", "payload": _payload(view.view_id)})))
    thread.start()
    assert entered.wait(5)
    env.bridge.dispatch({"id": "stop", "action": "stopPrompt", "payload": {"sessionId": env.session_id}})
    release.set()
    thread.join(5)
    assert outcome["status"] == "cancelled"
    assert "late success" not in json.dumps(outcome)
    assert env.bridge.dispatch({"id": "repeat", "action": "callViewTool", "payload": _payload(view.view_id)})["duplicate"] is True
    assert len(env.runs) == 1


def test_private_state_context_and_fork_rewind_boundaries(tmp_path):
    from reverie.views import model_context_message
    env = _make_bridge(tmp_path)
    view = _register_view(env.store, env.session_id, tmp_path)
    env.store.write_state(env.session_id, view.view_id, state={"private": "PRIVATE_ONLY"}, base_revision=0)
    env.store.write_model_context(env.session_id, view.view_id, summary="selected row 3")
    env.store.begin_call(env.session_id, view.view_id, 1, "unknown", "view_echo", {})
    messages = [{"role": "tool", "content": f"view_id={view.view_id}, revision=1"}]
    context = model_context_message(env.store, env.session_id, messages)
    assert context["role"] == "user"
    assert "selected row 3" in context["content"]
    assert "PRIVATE_ONLY" not in json.dumps(context)
    assert str(tmp_path) not in json.dumps(context)
    env.store.fork_session(env.session_id, "forked", [(view.view_id, 1)])
    assert env.store.read_state("forked", view.view_id)["state"] == {"private": "PRIVATE_ONLY"}
    assert env.store.call_receipts("forked", view.view_id, 1) == []
    env.store.write_state("forked", view.view_id, state={"tab": "fork"}, base_revision=1)
    assert env.store.read_state(env.session_id, view.view_id)["state"] == {"private": "PRIVATE_ONLY"}
    env.store.register(artifact_path=_write_html(tmp_path), identity=ViewIdentity(env.session_id, "t2", "c2"),
                       title="new", summary="new", workspace_root=tmp_path, replaces_view_id=view.view_id)
    env.store.restrict_visible(env.session_id, [(view.view_id, 1)])
    with pytest.raises(ValueError, match="hidden"):
        env.store.resolve_entry(env.session_id, view.view_id, 2)
    assert env.store.current_manifest(env.session_id, view.view_id).revision == 1
    env.store.delete_session("forked")
    assert env.store.manifest(env.session_id, view.view_id, 1).revision == 1


def test_approval_timeout_fails_closed_and_expired_approval_is_rejected(tmp_path, monkeypatch):
    import reverie.sdk_bridge as sdk
    env = _make_bridge(tmp_path)
    view = _register_view(env.store, env.session_id, tmp_path)
    ticks = iter([0, 301])
    monkeypatch.setattr(sdk, "time", SimpleNamespace(monotonic=lambda: next(ticks)))
    outcome = env.bridge.dispatch({"id": "timeout", "action": "callViewTool", "payload": _payload(view.view_id)})
    assert outcome["status"] == "error"
    assert env.runs == []
    approval = env.recorder.approvals()[0]["approval_id"]
    with pytest.raises(ValueError, match="no longer active"):
        env.bridge.dispatch({"id": "late", "action": "resolveApproval", "payload": {"approvalId": approval, "decision": "once"}})
