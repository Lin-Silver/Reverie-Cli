"""Focused tests for the RIU P1 ``render_view`` tool (``reverie.tools.render_view``).

Written before the tool exists (TDD). They pin the P1 trust properties from
``docs/INTELLIGENT_UI_SPEC.md`` §5.1: identity is kernel-bound (model arguments
cannot choose session / turn / tool-call), the view is persisted in the
restricted store *before* any ``view_ready`` event is emitted, the model-facing
result and the emitted event never carry the HTML or a filesystem path (so the
bytes are not re-added to a later model request), bad artifacts raise
``view_error`` instead of a view, ``replaces_view_id`` revises the same view,
and a fabricated view id dereferences to nothing. Nothing here reaches a model
or the network; every write stays under the pytest ``tmp_path`` sandbox.
"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

import pytest

from reverie.tools.render_view import RenderViewTool
from reverie.views import ViewStore, ViewStoreError

HTML = "<!doctype html><html><body><h1>chart</h1></body></html>"


class _FakeAgent:
    """Minimal kernel stand-in: owns the session and the out-of-band channel."""

    def __init__(self, session_id: str = "sess-1") -> None:
        self._session_id = session_id
        self.events: list[dict] = []

    def _current_session_details(self, fallback_session_id: str = "default"):
        return self._session_id, "Session One"

    def _emit_tool_stream_event(self, event_type: str, **payload):
        # Mirror the real agent: wrap in the unforgeable out-of-band envelope.
        self.events.append(
            {"kind": "stream_event", "event": str(event_type).strip().lower(), **payload}
        )


def _store(tmp_path: Path) -> ViewStore:
    return ViewStore(tmp_path / "data" / "views")


def _workspace(tmp_path: Path) -> Path:
    workspace = tmp_path / "workspace"
    workspace.mkdir(parents=True, exist_ok=True)
    return workspace


def _artifact(workspace: Path, name: str = "chart.html", body: str = HTML) -> Path:
    path = workspace / name
    path.write_text(body, encoding="utf-8")
    return path


def _tool(
    *,
    agent: _FakeAgent,
    store: ViewStore,
    workspace: Path,
    turn_id: str = "turn-1",
    tool_call_id: str = "call-1",
) -> RenderViewTool:
    context = {
        "agent": agent,
        "project_root": str(workspace),
        "view_store": store,
        "turn_id": turn_id,
        "active_tool_call_id": tool_call_id,
    }
    return RenderViewTool(context)


def _ready(agent: _FakeAgent):
    return [event for event in agent.events if event["event"] == "view_ready"]


def _errors(agent: _FakeAgent):
    return [event for event in agent.events if event["event"] == "view_error"]
# END-HELPERS


def test_render_view_persists_then_emits_view_ready(tmp_path):
    agent = _FakeAgent()
    store = _store(tmp_path)
    workspace = _workspace(tmp_path)
    _artifact(workspace)
    tool = _tool(agent=agent, store=store, workspace=workspace)

    result = tool.execute(
        artifact_path="chart.html", title="Sales chart", summary="A bar chart of Q3 sales."
    )

    assert result.success
    ready = _ready(agent)
    assert len(ready) == 1
    payload = ready[0]
    assert payload["session_id"] == "sess-1"
    assert payload["turn_id"] == "turn-1"
    assert payload["revision"] == 1
    assert payload["summary"] == "A bar chart of Q3 sales."
    view_id = payload["view_id"]
    # persist-before-publish: the committed revision is already resolvable, and
    # its bytes match what the event announced.
    manifest = store.manifest("sess-1", view_id)
    assert datetime.fromisoformat(payload["committed_at"]) >= datetime.fromisoformat(manifest.created_at)
    assert manifest.revision == 1
    assert manifest.source == {"kind": "generated"}
    entry, resolved = store.resolve_entry("sess-1", view_id)
    assert entry.read_text(encoding="utf-8") == HTML
    assert resolved.sha256 == manifest.sha256


def test_view_ready_event_excludes_html_and_filesystem_path(tmp_path):
    agent = _FakeAgent()
    store = _store(tmp_path)
    workspace = _workspace(tmp_path)
    artifact = _artifact(workspace)
    tool = _tool(agent=agent, store=store, workspace=workspace)
    tool.execute(artifact_path="chart.html", title="t", summary="s")
    event = _ready(agent)[0]
    blob = json.dumps(event)
    assert HTML not in blob
    assert "index.html" not in blob
    assert str(artifact) not in blob
    for leaked in ("entry", "directory", "path", "artifact_path"):
        assert leaked not in event


def test_result_output_and_data_exclude_html_and_path(tmp_path):
    agent = _FakeAgent()
    store = _store(tmp_path)
    workspace = _workspace(tmp_path)
    artifact = _artifact(workspace)
    tool = _tool(agent=agent, store=store, workspace=workspace)
    result = tool.execute(artifact_path="chart.html", title="t", summary="s")
    data_blob = json.dumps(result.data)
    assert HTML not in result.output
    assert HTML not in data_blob
    assert "index.html" not in result.output and "index.html" not in data_blob
    assert str(artifact) not in result.output and str(artifact) not in data_blob
    # The durable reference the model keeps is the opaque handle, not the bytes.
    assert result.data["view"]["view_id"] == _ready(agent)[0]["view_id"]


@pytest.mark.parametrize("storage", ("localStorage", "sessionStorage"))
def test_unsupported_storage_warning_allows_a_traceable_model_repair(tmp_path, storage):
    agent, store, workspace = _FakeAgent(), _store(tmp_path), _workspace(tmp_path)
    original = f"<script>{storage}.setItem('PRIVATE_HTML_SENTINEL','value')</script>"
    path = _artifact(workspace, body=original)
    tool = _tool(agent=agent, store=store, workspace=workspace)
    result = tool.execute(artifact_path="chart.html", title="t", summary="s")
    assert result.success
    assert storage in result.data["authoring_warnings"][0]
    assert "unavailable" in result.output
    assert "reverie/view-state" in result.output
    assert "PRIVATE_HTML_SENTINEL" not in json.dumps(result.data)
    assert "PRIVATE_HTML_SENTINEL" not in result.output
    view_id = result.data["view"]["view_id"]
    entry, _ = store.resolve_entry("sess-1", view_id, 1)
    assert entry.read_text(encoding="utf-8") == original
    path.write_text(HTML, encoding="utf-8")
    repaired = tool.execute(artifact_path="chart.html", title="t", summary="s", replaces_view_id=view_id)
    assert repaired.success
    assert repaired.data["view"]["revision"] == 2
    assert not repaired.data.get("authoring_warnings")
    assert entry.read_text(encoding="utf-8") == original


@pytest.mark.parametrize("body", (
    "<p>localStorage.setItem is unavailable</p>",
    "<!-- <script>localStorage.setItem('example', 'text')</script> -->",
    '<script type="application/json">{"example":"localStorage.setItem"}</script>',
))
def test_storage_examples_outside_executable_scripts_do_not_warn(tmp_path, body):
    agent, store, workspace = _FakeAgent(), _store(tmp_path), _workspace(tmp_path)
    _artifact(workspace, body=body)
    result = _tool(agent=agent, store=store, workspace=workspace).execute(artifact_path="chart.html", title="t", summary="s")
    assert result.success
    assert not result.data.get("authoring_warnings")


def test_controls_without_host_integration_get_advice_without_html_rewriting(tmp_path):
    agent, store, workspace = _FakeAgent(), _store(tmp_path), _workspace(tmp_path)
    agent.runtime_surface = 'desktop'
    html = '<label>Value<input value="2"></label><script>const PRIVATE_HTML_SENTINEL=2;</script>'
    _artifact(workspace, body=html)
    result = _tool(agent=agent, store=store, workspace=workspace).execute(artifact_path='chart.html', title='t', summary='s')
    assert result.success
    assert any('initialization' in w for w in result.data['authoring_warnings'])
    assert any('reverie/view-state' in w for w in result.data['authoring_warnings'])
    assert 'PRIVATE_HTML_SENTINEL' not in result.output
    entry, _ = store.resolve_entry('sess-1', result.data['view']['view_id'], 1)
    assert entry.read_text() == html


def test_host_api_markers_are_advisory_and_do_not_claim_runtime_validation(tmp_path):
    agent, store, workspace = _FakeAgent(), _store(tmp_path), _workspace(tmp_path)
    agent.runtime_surface = 'desktop'
    _artifact(workspace, body='<input><script>/* ui/initialize reverie/view-state capability */</script>')
    result = _tool(agent=agent, store=store, workspace=workspace).execute(artifact_path='chart.html', title='t', summary='s')
    assert result.success
    assert not result.data.get('authoring_warnings')


@pytest.mark.parametrize('script', [
    '/* ui/initialize reverie/view-state */',
    "parent.postMessage({method:'ui/initialize',capability:''},'*'); /* reverie/view-state */",
])
def test_host_capability_advice_preserves_registered_model_bytes(tmp_path, script):
    agent = _FakeAgent()
    agent.runtime_surface = 'desktop'
    workspace, store = _workspace(tmp_path), _store(tmp_path)
    html = '<input><script>' + script + '</script>'
    _artifact(workspace, body=html)
    result = _tool(agent=agent, store=store, workspace=workspace).execute(
        artifact_path='chart.html', title='t', summary='s')
    assert result.success
    assert any('capability' in warning for warning in result.data.get('authoring_warnings', []))
    view = result.data['view']
    path, _ = store.resolve_entry('sess-1', view['view_id'], view['revision'])
    assert path.read_text() == html
    assert 'runtime verified' not in result.output


def test_identity_is_kernel_bound_not_model_arguments(tmp_path):
    agent = _FakeAgent(session_id="sess-1")
    store = _store(tmp_path)
    workspace = _workspace(tmp_path)
    _artifact(workspace)
    tool = _tool(
        agent=agent, store=store, workspace=workspace,
        turn_id="turn-real", tool_call_id="call-real",
    )
    # The model tries to pick its own identity; the kernel's values must win.
    result = tool.execute(
        artifact_path="chart.html", title="t", summary="s",
        session_id="attacker-session", turn_id="attacker-turn", tool_call_id="attacker-call",
    )
    assert result.success
    view_id = _ready(agent)[0]["view_id"]
    with pytest.raises(ViewStoreError):
        store.manifest("attacker-session", view_id)
    manifest = store.manifest("sess-1", view_id)
    assert manifest.session_id == "sess-1"
    assert manifest.turn_id == "turn-real"
    assert manifest.tool_call_id == "call-real"


def test_bad_artifact_emits_view_error_and_persists_nothing(tmp_path):
    agent = _FakeAgent()
    store = _store(tmp_path)
    workspace = _workspace(tmp_path)
    outside = tmp_path / "outside.html"
    outside.write_text(HTML, encoding="utf-8")
    tool = _tool(agent=agent, store=store, workspace=workspace)
    result = tool.execute(artifact_path=str(outside), title="t", summary="s")
    assert not result.success
    assert _ready(agent) == []
    errors = _errors(agent)
    assert len(errors) == 1
    assert errors[0]["session_id"] == "sess-1"
    assert HTML not in (json.dumps(errors[0]) + result.output + (result.error or ""))
    session_dir = store.views_root / "sess-1"
    assert not session_dir.exists() or not any(session_dir.rglob("index.html"))


def test_non_html_artifact_emits_view_error(tmp_path):
    agent = _FakeAgent()
    store = _store(tmp_path)
    workspace = _workspace(tmp_path)
    _artifact(workspace, "data.txt", "plain text, not html")
    tool = _tool(agent=agent, store=store, workspace=workspace)
    result = tool.execute(artifact_path="data.txt", title="t", summary="s")
    assert not result.success
    assert _ready(agent) == []
    assert len(_errors(agent)) == 1


def test_replaces_view_id_revises_same_view(tmp_path):
    agent = _FakeAgent()
    store = _store(tmp_path)
    workspace = _workspace(tmp_path)
    _artifact(workspace)
    tool = _tool(agent=agent, store=store, workspace=workspace)
    first = tool.execute(artifact_path="chart.html", title="t1", summary="s1")
    first_id = first.data["view"]["view_id"]
    _artifact(workspace, "chart2.html", HTML + "<!--v2-->")
    second = tool.execute(
        artifact_path="chart2.html", title="t2", summary="s2", replaces_view_id=first_id
    )
    assert second.success
    assert second.data["view"]["view_id"] == first_id
    assert second.data["view"]["revision"] == 2
    last = _ready(agent)[-1]
    assert last["revision"] == 2
    assert last["replaces_view_id"] == first_id
    assert store.latest_revision("sess-1", first_id) == 2


def test_render_view_forwards_callable_tools_but_hides_them_from_model(tmp_path):
    # §4.2/§4.5: a view's callable-tool allow-list (工具白名单 / 组件允许范围) is
    # declared when the view is minted so a later callViewTool can be gated
    # against it. It is authorization metadata that can only NARROW (it is
    # intersected with the user's grants + mode/workspace policy, and every call
    # still passes the gated executor + approval), so forwarding it from
    # render_view is spec-consistent -- NOT the forbidden "model choosing
    # permissions". It must ride the stored manifest yet never reach the model:
    # not in model_reference(), the view_ready event, or the kept tool result.
    agent = _FakeAgent()
    store = _store(tmp_path)
    workspace = _workspace(tmp_path)
    _artifact(workspace)
    tool = _tool(agent=agent, store=store, workspace=workspace)

    result = tool.execute(
        artifact_path="chart.html",
        title="t",
        summary="s",
        callable_tools=["view_echo", "view_echo", "  data_api  ", ""],
    )
    assert result.success

    view_id = _ready(agent)[0]["view_id"]
    manifest = store.manifest("sess-1", view_id)
    # Cleaned by the store (trim / drop-empty / dedupe) and stored on the manifest.
    assert manifest.callable_tools == ("view_echo", "data_api")

    # Never exposed to the model: absent from the emitted event and the result,
    # and the tool names do not leak into the model-facing output text.
    assert "callable_tools" not in _ready(agent)[0]
    assert "callable_tools" not in result.data["view"]
    assert "callable_tools" not in json.dumps(result.data)
    assert "view_echo" not in result.output and "data_api" not in result.output


def test_render_view_defaults_to_an_empty_callable_allowlist(tmp_path):
    # Omitting callable_tools mints a view that can call nothing: a callViewTool
    # then fails closed as restricted-tool. Fail-closed is the P2 default.
    agent = _FakeAgent()
    store = _store(tmp_path)
    workspace = _workspace(tmp_path)
    _artifact(workspace)
    tool = _tool(agent=agent, store=store, workspace=workspace)
    result = tool.execute(artifact_path="chart.html", title="t", summary="s")
    assert result.success
    view_id = _ready(agent)[0]["view_id"]
    assert store.manifest("sess-1", view_id).callable_tools == ()


def test_missing_required_argument_fails_without_event(tmp_path):
    agent = _FakeAgent()
    store = _store(tmp_path)
    workspace = _workspace(tmp_path)
    tool = _tool(agent=agent, store=store, workspace=workspace)
    result = tool.execute(title="t", summary="s")
    assert not result.success
    assert agent.events == []


def test_forged_view_id_dereferences_to_nothing(tmp_path):
    # The restricted store is the sole authority: a view id the kernel never
    # minted -- e.g. one decoded from a forged [[REVERIE_EVENT]] in model text
    # -- resolves to no artifact, so a forged view_ready cannot display HTML.
    store = _store(tmp_path)
    with pytest.raises(ViewStoreError):
        store.manifest("sess-1", "v" + "0" * 16)


def test_render_view_registered_for_reverie_mode():
    from reverie.tools.registry import get_tool_classes_for_mode

    names = {getattr(cls, "name", "") for cls in get_tool_classes_for_mode("reverie")}
    assert "render_view" in names
