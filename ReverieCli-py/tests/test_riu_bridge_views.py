"""Focused tests for the RIU P1 bridge view channel (``reverie.sdk_bridge``).

Written before the dispatch handlers exist (TDD). They pin the P1 contract from
``docs/INTELLIGENT_UI_SPEC.md`` §6.2 for the request/response side of the view
pipeline:

* the ``hello`` handshake advertises the ``views`` capability so a client knows
  inline views are served and MCP-apps are not;
* ``getView`` is the authoritative dereference -- it resolves a kernel-minted
  view id to the on-disk revision directory and a *camelCase* model-safe
  reference, carrying no HTML, no sha256 and no path inside the ``view`` block
  (the paths live only in the separate ``resolved`` block the host consumes);
* a forged view id the kernel never minted resolves to nothing (raises), so a
  fabricated event cannot make the host bind arbitrary HTML;
* ``setViewState`` persists private display state and returns the new revision;
* ``getView`` folds any persisted state into its reference.

Identity (the session) is read from the kernel's current session, never from the
payload. Every write stays under the pytest ``tmp_path`` sandbox; the store is
injected so nothing touches a real project data directory.
"""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

from reverie.sdk_bridge import ReverieSdkBridge
from reverie.views import ViewIdentity, ViewStore

HTML = "<!doctype html><title>chart</title><body>hi</body>"


def _bridge(tmp_path: Path, store: ViewStore, session_id: str = "sess-1") -> ReverieSdkBridge:
    bridge = ReverieSdkBridge.__new__(ReverieSdkBridge)
    bridge.project_root = tmp_path
    session = SimpleNamespace(id=session_id, messages=[])
    interface = SimpleNamespace(session_manager=SimpleNamespace(get_current_session=lambda: session))
    bridge.ensure_interface = lambda *args, **kwargs: interface
    bridge._view_store = lambda: store
    return bridge


def _registered(store: ViewStore, tmp_path: Path, session_id: str = "sess-1"):
    workspace = tmp_path / "workspace"
    workspace.mkdir(parents=True, exist_ok=True)
    artifact = workspace / "chart.html"
    artifact.write_text(HTML, encoding="utf-8")
    identity = ViewIdentity(session_id=session_id, turn_id="t1", tool_call_id="call-1")
    return store.register(
        artifact_path=str(artifact),
        identity=identity,
        title="Sales chart",
        summary="Q3 bars",
        workspace_root=workspace,
        source_kind="generated",
    )


def test_hello_advertises_views_capability(tmp_path: Path) -> None:
    bridge = ReverieSdkBridge.__new__(ReverieSdkBridge)
    bridge.project_root = tmp_path
    response = bridge.dispatch({"id": 1, "action": "hello"})
    assert response["type"] == "ready"
    assert response["capabilities"]["views"] == {"schema_version": 1, "inline": True, "mcp_apps": True,
                                                 "mcp_apps_protocol": "2026-01-26", "mcp_apps_sdk": "2.0.3", "profile": "offline-server-tools-v1"}


def test_get_view_resolves_authoritative_paths_and_camelcase_reference(tmp_path: Path) -> None:
    store = ViewStore(tmp_path / "data" / "views")
    manifest = _registered(store, tmp_path)
    bridge = _bridge(tmp_path, store)
    response = bridge.dispatch(
        {"id": 2, "action": "getView", "payload": {"viewId": manifest.view_id, "revision": manifest.revision}}
    )
    assert response["type"] == "view.resolved"
    resolved = response["resolved"]
    assert Path(resolved["directory"]) == tmp_path / "data" / "views" / "sess-1" / manifest.view_id / "1"
    assert resolved["entry"] == "index.html"
    assert Path(resolved["viewsRoot"]) == tmp_path / "data" / "views"
    view = response["view"]
    assert view["sessionId"] == "sess-1"
    assert view["viewId"] == manifest.view_id
    assert view["revision"] == 1
    assert view["title"] == "Sales chart"
    assert view["summary"] == "Q3 bars"
    assert view["mimeType"] == "text/html"
    assert view["policyId"] == "local-offline-v1"
    assert view["schemaVersion"] == 1
    assert "createdAt" in view
    # The model-safe block never carries HTML, integrity digest or a path.
    assert not any(key in view for key in ("directory", "entry", "viewsRoot", "sha256", "html", "source"))
    assert view.get("state") is None


def test_get_view_rejects_a_forged_view_id(tmp_path: Path) -> None:
    store = ViewStore(tmp_path / "data" / "views")
    _registered(store, tmp_path)
    bridge = _bridge(tmp_path, store)
    with pytest.raises(ValueError, match="not stored"):
        bridge.dispatch({"id": 3, "action": "getView", "payload": {"viewId": "vdeadbeefdeadbeef", "revision": 1}})


def test_get_view_requires_a_view_id(tmp_path: Path) -> None:
    store = ViewStore(tmp_path / "data" / "views")
    bridge = _bridge(tmp_path, store)
    with pytest.raises(ValueError, match="viewId"):
        bridge.dispatch({"id": 4, "action": "getView", "payload": {}})


def test_set_view_state_persists_and_increments_revision(tmp_path: Path) -> None:
    store = ViewStore(tmp_path / "data" / "views")
    manifest = _registered(store, tmp_path)
    bridge = _bridge(tmp_path, store)
    first = bridge.dispatch(
        {"id": 5, "action": "setViewState", "payload": {"viewId": manifest.view_id, "state": {"tab": "q3"}}}
    )
    assert first["type"] == "view.state"
    assert first["revision"] == 1
    assert store.read_state("sess-1", manifest.view_id)["state"] == {"tab": "q3"}
    second = bridge.dispatch(
        {
            "id": 6,
            "action": "setViewState",
            "payload": {"viewId": manifest.view_id, "state": {"tab": "q4"}, "baseRevision": 1},
        }
    )
    assert second["revision"] == 2


def test_get_view_folds_in_persisted_state(tmp_path: Path) -> None:
    store = ViewStore(tmp_path / "data" / "views")
    manifest = _registered(store, tmp_path)
    store.write_state("sess-1", manifest.view_id, state={"tab": "q3"})
    bridge = _bridge(tmp_path, store)
    response = bridge.dispatch({"id": 7, "action": "getView", "payload": {"viewId": manifest.view_id}})
    state = response["view"]["state"]
    assert state["revision"] == 1
    assert state["state"] == {"tab": "q3"}
    assert "updated_at" in state
