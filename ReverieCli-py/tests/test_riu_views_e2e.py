"""End-to-end RIU P1 pipeline evidence with the two mandated fixtures.

``docs/INTELLIGENT_UI_SPEC.md`` §6.2 asks that a *parameter simulator* and a
*data chart* drive the whole chain tool -> storage -> host dereference ->
refresh/restart -> degraded view. The focused unit suites already pin each
seam in isolation (``test_riu_views`` the store, ``test_riu_render_view`` the
tool, ``test_riu_bridge_views`` the bridge). This module ties them together on
the two *real* offline fixtures: it drives the real :class:`RenderViewTool` and
the real :meth:`ReverieSdkBridge.dispatch` ``getView`` handler, then rebuilds a
fresh store + bridge over the same on-disk root to prove a view survives a
process restart, and exercises the revision / fork / rewind / delete lifecycle
through that same dereference. Nothing here reaches a model or the network;
every write stays under the pytest ``tmp_path`` sandbox.
"""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from reverie.sdk_bridge import ReverieSdkBridge
from reverie.tools.render_view import RenderViewTool
from reverie.views import ViewStore, ViewStoreError

FIXTURES = Path(__file__).parent / "fixtures" / "riu_p1"
SIMULATOR = FIXTURES / "parameter_simulator.html"
CHART = FIXTURES / "data_chart.html"

# (path, title, summary). The title/summary are the only prose kept in history;
# the renderer-side contract test reuses these exact strings.
CASES = [
    (SIMULATOR, "Compound growth simulator", "Projected balance across years at a chosen rate."),
    (CHART, "Q3 sales by region", "Bar chart of Q3 sales across five regions."),
]

# A marker that lives only in each fixture's inline <script>, never in its
# title/summary -- so finding it in a result/event would prove HTML leaked.
SCRIPT_MARKERS = ["control.addEventListener", "createElementNS"]


class _FakeAgent:
    """Kernel stand-in: owns the session id and the out-of-band event channel."""

    def __init__(self, session_id: str = "sess-1") -> None:
        self._session_id = session_id
        self.events: list[dict] = []

    def _current_session_details(self, fallback_session_id: str = "default"):
        return self._session_id, "Session One"

    def _emit_tool_stream_event(self, event_type: str, **payload):
        self.events.append({"kind": "stream_event", "event": str(event_type).strip().lower(), **payload})

    def ready(self):
        return [event for event in self.events if event["event"] == "view_ready"]


def _store(root: Path) -> ViewStore:
    return ViewStore(root / "data" / "views")


def _bridge(root: Path, store: ViewStore, session_id: str) -> ReverieSdkBridge:
    """Drive the real dispatch() with an injected store and a kernel session."""
    bridge = ReverieSdkBridge.__new__(ReverieSdkBridge)
    bridge.project_root = root
    session = SimpleNamespace(id=session_id, messages=[])
    interface = SimpleNamespace(session_manager=SimpleNamespace(get_current_session=lambda: session))
    bridge.ensure_interface = lambda *args, **kwargs: interface
    bridge._view_store = lambda: store
    return bridge


def _copy_fixture(workspace: Path, source: Path, name: str) -> str:
    workspace.mkdir(parents=True, exist_ok=True)
    (workspace / name).write_bytes(source.read_bytes())
    return name


def _render(agent, store, workspace, *, source, title, summary, name, replaces=None, turn="turn-1", call="call-1"):
    tool = RenderViewTool(
        {
            "agent": agent,
            "project_root": str(workspace),
            "view_store": store,
            "turn_id": turn,
            "active_tool_call_id": call,
        }
    )
    relative = _copy_fixture(workspace, source, name)
    kwargs = {"artifact_path": relative, "title": title, "summary": summary}
    if replaces:
        kwargs["replaces_view_id"] = replaces
    return tool.execute(**kwargs)


def _expected_tui_line(title: str, view_id: str, revision: int, summary: str) -> str:
    # Mirrors reverie/tools/render_view.py exactly -- the one line a pure
    # terminal (no renderer) shows as the view's degradation text.
    return (
        f'Interactive view ready: "{title}" (view_id={view_id}, revision={revision}). '
        f"It is shown to the user in the Reverie view panel. Summary: {summary}"
    )
# END-HELPERS


def test_fixtures_are_self_contained_offline_html():
    for source, _title, _summary in CASES:
        assert source.is_file(), f"missing fixture {source}"
        text = source.read_text(encoding="utf-8")
        assert text.lstrip().lower().startswith("<!doctype html>")
        # No network: no remote subresource or socket. The only absolute URL
        # allowed is the SVG XML namespace, which loads nothing.
        for banned in ('src="http', "src='http", 'href="http', "href='http",
                       "<link ", "<script src", "fetch(", "XMLHttpRequest", "WebSocket", "import("):
            assert banned not in text, f"{source.name} is not offline: {banned!r}"
        for stray in text.split('"'):
            if stray.startswith(("http://", "https://")):
                assert stray.startswith("http://www.w3.org/"), f"{source.name} references {stray!r}"


def test_both_fixtures_persist_before_publish_and_resolve_through_bridge(tmp_path):
    store = _store(tmp_path)
    agent = _FakeAgent("sess-1")
    workspace = tmp_path / "workspace"
    bridge = _bridge(tmp_path, store, "sess-1")

    for index, (source, title, summary) in enumerate(CASES):
        result = _render(agent, store, workspace, source=source, title=title, summary=summary, name=f"view{index}.html")
        assert result.success
        view_id = result.data["view"]["view_id"]
        # persist-before-publish: the committed revision is already resolvable
        # the instant the tool returns, with bytes matching the fixture.
        entry, manifest = store.resolve_entry("sess-1", view_id)
        assert entry.read_bytes() == source.read_bytes()
        assert manifest.title == title

        response = bridge.dispatch({"id": index, "action": "getView", "payload": {"viewId": view_id}})
        assert response["type"] == "view.resolved"
        view = response["view"]
        assert view["viewId"] == view_id and view["sessionId"] == "sess-1"
        assert view["title"] == title and view["summary"] == summary
        # The host's authoritative path block points at the stored entry...
        resolved = response["resolved"]
        assert (Path(resolved["directory"]) / resolved["entry"]).read_bytes() == source.read_bytes()
        # ...and the model-safe block leaks no HTML, digest or filesystem path.
        blob = json.dumps(view)
        assert not any(key in view for key in ("directory", "entry", "viewsRoot", "sha256", "html", "source"))
        for marker in SCRIPT_MARKERS:
            assert marker not in blob


def test_result_and_event_never_carry_fixture_script_or_path(tmp_path):
    store = _store(tmp_path)
    agent = _FakeAgent("sess-1")
    workspace = tmp_path / "workspace"
    for index, (source, title, summary) in enumerate(CASES):
        result = _render(agent, store, workspace, source=source, title=title, summary=summary, name=f"v{index}.html")
        event = agent.ready()[-1]
        combined = result.output + json.dumps(result.data) + json.dumps(event)
        for marker in SCRIPT_MARKERS:
            assert marker not in combined
        # The on-disk artifact path and the managed entry name stay host-side.
        assert str(workspace) not in combined
        assert "index.html" not in combined


def test_tui_degradation_line_is_self_describing(tmp_path):
    store = _store(tmp_path)
    agent = _FakeAgent("sess-1")
    workspace = tmp_path / "workspace"
    for index, (source, title, summary) in enumerate(CASES):
        result = _render(agent, store, workspace, source=source, title=title, summary=summary, name=f"v{index}.html")
        view = result.data["view"]
        expected = _expected_tui_line(title, view["view_id"], view["revision"], summary)
        # The tool result IS the terminal degradation: one line naming the view,
        # its opaque handle and the human summary -- no HTML, no panel required.
        assert result.output == expected
        assert title in result.output and summary in result.output
        assert f"view_id={view['view_id']}" in result.output


def test_views_survive_a_simulated_restart(tmp_path):
    # Render under one store/bridge, then throw them away and dereference through
    # a FRESH store + bridge over the same on-disk root -- the restart path.
    writer_store = _store(tmp_path)
    agent = _FakeAgent("sess-1")
    workspace = tmp_path / "workspace"
    view_ids = []
    for index, (source, title, summary) in enumerate(CASES):
        result = _render(agent, writer_store, workspace, source=source, title=title, summary=summary, name=f"v{index}.html")
        view_ids.append((result.data["view"]["view_id"], source))

    reader_bridge = _bridge(tmp_path, _store(tmp_path), "sess-1")
    for order, (view_id, source) in enumerate(view_ids):
        response = reader_bridge.dispatch({"id": 100 + order, "action": "getView", "payload": {"viewId": view_id}})
        resolved = response["resolved"]
        assert (Path(resolved["directory"]) / resolved["entry"]).read_bytes() == source.read_bytes()


def test_in_place_revision_then_rewind_to_earlier_revision(tmp_path):
    store = _store(tmp_path)
    agent = _FakeAgent("sess-1")
    workspace = tmp_path / "workspace"
    first = _render(agent, store, workspace, source=SIMULATOR, title="Compound growth simulator",
                    summary="rev one", name="sim.html")
    view_id = first.data["view"]["view_id"]

    # The model revises the view in place: a new revision reuses the id.
    revised_source = tmp_path / "sim_v2.html"
    revised_source.write_text(SIMULATOR.read_text(encoding="utf-8") + "<!--revision 2-->", encoding="utf-8")
    second = _render(agent, store, workspace, source=revised_source, title="Compound growth simulator",
                     summary="rev two", name="sim2.html", replaces=view_id)
    assert second.data["view"]["view_id"] == view_id
    assert second.data["view"]["revision"] == 2

    bridge = _bridge(tmp_path, store, "sess-1")
    latest = bridge.dispatch({"id": 1, "action": "getView", "payload": {"viewId": view_id}})
    assert latest["view"]["revision"] == 2 and latest["view"]["summary"] == "rev two"
    # Rewind: an earlier revision is still addressable and returns its own bytes.
    earlier = bridge.dispatch({"id": 2, "action": "getView", "payload": {"viewId": view_id, "revision": 1}})
    assert earlier["view"]["revision"] == 1 and earlier["view"]["summary"] == "rev one"
    earlier_resolved = earlier["resolved"]
    earlier_entry = Path(earlier_resolved["directory"]) / earlier_resolved["entry"]
    assert "<!--revision 2-->" not in earlier_entry.read_text(encoding="utf-8")


def test_fork_session_rebinds_and_resolves_under_new_session(tmp_path):
    store = _store(tmp_path)
    agent = _FakeAgent("sess-1")
    workspace = tmp_path / "workspace"
    result = _render(agent, store, workspace, source=CHART, title="Q3 sales by region",
                     summary="Bar chart of Q3 sales across five regions.", name="chart.html")
    view_id = result.data["view"]["view_id"]

    store.fork_session("sess-1", "sess-2", [(view_id, 1)])
    forked_bridge = _bridge(tmp_path, store, "sess-2")
    response = forked_bridge.dispatch({"id": 1, "action": "getView", "payload": {"viewId": view_id}})
    assert response["view"]["sessionId"] == "sess-2"
    resolved = response["resolved"]
    assert (Path(resolved["directory"]) / resolved["entry"]).read_bytes() == CHART.read_bytes()


def test_delete_view_then_session_make_getView_raise(tmp_path):
    store = _store(tmp_path)
    agent = _FakeAgent("sess-1")
    workspace = tmp_path / "workspace"
    first = _render(agent, store, workspace, source=CHART, title="Q3 sales by region", summary="s", name="chart.html")
    view_id = first.data["view"]["view_id"]
    bridge = _bridge(tmp_path, store, "sess-1")

    store.delete_view("sess-1", view_id)
    with pytest.raises(ValueError, match="not stored"):
        bridge.dispatch({"id": 1, "action": "getView", "payload": {"viewId": view_id}})

    second = _render(agent, store, workspace, source=SIMULATOR, title="Compound growth simulator",
                     summary="s", name="sim.html")
    survivor = second.data["view"]["view_id"]
    store.delete_session("sess-1")
    with pytest.raises(ValueError, match="not stored"):
        bridge.dispatch({"id": 2, "action": "getView", "payload": {"viewId": survivor}})
