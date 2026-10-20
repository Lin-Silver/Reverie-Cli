"""Focused tests for the RIU P1 restricted artifact store (``reverie.views``).

Written before the implementation exists (TDD): they pin the artifact
correctness row from ``docs/INTELLIGENT_UI_SPEC.md`` §5.1 — valid persist,
size / UTF-8 / type guards, workspace containment, symlink and cross-session
rejection, sha256 integrity, atomic persist-before-publish, and the
revision / replace + state + fork / delete reference behaviour. Nothing here
reaches the network, a model, or a real session; every write stays under the
pytest ``tmp_path`` sandbox.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from reverie.views import (
    MAX_VIEW_ENTRY_BYTES,
    MAX_VIEW_STATE_BYTES,
    VIEW_SCHEMA_VERSION,
    ViewIdentity,
    ViewStore,
    ViewStoreError,
)

HTML = "<!doctype html><html><body><h1>ok</h1></body></html>"


def _store(tmp_path: Path) -> ViewStore:
    return ViewStore(tmp_path / "data" / "views")


def _identity(session: str = "sess-1") -> ViewIdentity:
    return ViewIdentity(session_id=session, turn_id="turn-1", tool_call_id="call-1")


def _artifact(workspace: Path, name: str = "chart.html", body: str = HTML) -> Path:
    workspace.mkdir(parents=True, exist_ok=True)
    path = workspace / name
    path.write_text(body, encoding="utf-8")
    return path


def _register(tmp_path: Path, **overrides):
    store = overrides.pop("store", None) or _store(tmp_path)
    workspace = overrides.pop("workspace", tmp_path / "workspace")
    artifact = overrides.pop("artifact", None)
    if artifact is None:
        artifact = _artifact(workspace)
    manifest = store.register(
        artifact_path=artifact,
        identity=overrides.pop("identity", _identity()),
        title=overrides.pop("title", "Sales chart"),
        summary=overrides.pop("summary", "A bar chart of Q3 sales."),
        workspace_root=workspace,
        **overrides,
    )
    return store, manifest


def test_register_persists_entry_and_manifest(tmp_path):
    store, manifest = _register(tmp_path)
    assert manifest.schema_version == VIEW_SCHEMA_VERSION
    assert manifest.revision == 1
    assert manifest.session_id == "sess-1"
    assert manifest.turn_id == "turn-1"
    assert manifest.mime_type == "text/html"
    directory = store.view_directory(manifest.session_id, manifest.view_id, manifest.revision)
    assert (directory / "index.html").read_text(encoding="utf-8") == HTML
    stored = json.loads((directory / "manifest.json").read_text(encoding="utf-8"))
    assert stored["sha256"] == manifest.sha256
    # persist-before-publish: the committed revision exists with no temp leftovers.
    assert not any(p.name.startswith(".tmp-") for p in directory.parent.iterdir())


def test_model_reference_excludes_html_and_paths(tmp_path):
    _unused, manifest = _register(tmp_path)
    ref = manifest.model_reference()
    blob = json.dumps(ref)
    assert HTML not in blob
    assert "index.html" not in blob
    assert "entry" not in ref
    assert "directory" not in ref
    assert ref["view_id"] == manifest.view_id
    assert ref["revision"] == 1
    assert ref["summary"] == "A bar chart of Q3 sales."


def test_oversize_entry_rejected(tmp_path):
    workspace = tmp_path / "workspace"
    big = "<!doctype html><body>" + ("a" * MAX_VIEW_ENTRY_BYTES) + "</body>"
    artifact = _artifact(workspace, "big.html", big)
    store = _store(tmp_path)
    with pytest.raises(ViewStoreError):
        store.register(artifact_path=artifact, identity=_identity(), title="t", summary="s", workspace_root=workspace)
    assert not store.views_root.exists() or not any(store.views_root.rglob("index.html"))


def test_invalid_utf8_rejected(tmp_path):
    workspace = tmp_path / "workspace"
    workspace.mkdir(parents=True)
    artifact = workspace / "bad.html"
    artifact.write_bytes(b"<html>\xff\xfe not utf8</html>")
    store = _store(tmp_path)
    with pytest.raises(ViewStoreError):
        store.register(artifact_path=artifact, identity=_identity(), title="t", summary="s", workspace_root=workspace)


def test_non_html_suffix_rejected(tmp_path):
    workspace = tmp_path / "workspace"
    artifact = _artifact(workspace, "data.txt", "plain text")
    store = _store(tmp_path)
    with pytest.raises(ViewStoreError):
        store.register(artifact_path=artifact, identity=_identity(), title="t", summary="s", workspace_root=workspace)


def test_directory_artifact_rejected(tmp_path):
    workspace = tmp_path / "workspace"
    (workspace / "d.html").mkdir(parents=True)
    store = _store(tmp_path)
    with pytest.raises(ViewStoreError):
        store.register(artifact_path=workspace / "d.html", identity=_identity(), title="t", summary="s", workspace_root=workspace)


def test_external_path_rejected(tmp_path):
    workspace = tmp_path / "workspace"
    workspace.mkdir(parents=True)
    outside = tmp_path / "outside.html"
    outside.write_text(HTML, encoding="utf-8")
    store = _store(tmp_path)
    with pytest.raises(ViewStoreError):
        store.register(artifact_path=outside, identity=_identity(), title="t", summary="s", workspace_root=workspace)


def test_symlink_escape_rejected(tmp_path):
    workspace = tmp_path / "workspace"
    workspace.mkdir(parents=True)
    outside = tmp_path / "outside.html"
    outside.write_text(HTML, encoding="utf-8")
    link = workspace / "link.html"
    try:
        link.symlink_to(outside)
    except (OSError, NotImplementedError):
        pytest.skip("symlink creation not permitted on this host")
    store = _store(tmp_path)
    with pytest.raises(ViewStoreError):
        store.register(artifact_path=link, identity=_identity(), title="t", summary="s", workspace_root=workspace)


def test_hash_integrity_detects_tamper(tmp_path):
    store, manifest = _register(tmp_path)
    directory = store.view_directory(manifest.session_id, manifest.view_id, manifest.revision)
    (directory / "index.html").write_text(HTML + "<!--tampered-->", encoding="utf-8")
    with pytest.raises(ViewStoreError):
        store.resolve_entry(manifest.session_id, manifest.view_id, manifest.revision)


def test_cross_session_manifest_rejected(tmp_path):
    store, manifest = _register(tmp_path)
    with pytest.raises(ViewStoreError):
        store.manifest("other-session", manifest.view_id)


def test_replaces_increments_revision_same_view(tmp_path):
    store, first = _register(tmp_path)
    workspace = tmp_path / "workspace"
    artifact = _artifact(workspace, "chart2.html", HTML + "<!--v2-->")
    second = store.register(
        artifact_path=artifact, identity=_identity(), title="t2", summary="s2",
        workspace_root=workspace, replaces_view_id=first.view_id,
    )
    assert second.view_id == first.view_id
    assert second.revision == 2
    assert second.replaces_view_id == first.view_id
    assert store.latest_revision(first.session_id, first.view_id) == 2


def test_replaces_unknown_view_rejected(tmp_path):
    store = _store(tmp_path)
    workspace = tmp_path / "workspace"
    artifact = _artifact(workspace)
    with pytest.raises(ViewStoreError):
        store.register(
            artifact_path=artifact, identity=_identity(), title="t", summary="s",
            workspace_root=workspace, replaces_view_id="does-not-exist",
        )


def test_replaces_other_session_rejected(tmp_path):
    store, first = _register(tmp_path)
    workspace = tmp_path / "workspace"
    artifact = _artifact(workspace, "c2.html")
    with pytest.raises(ViewStoreError):
        store.register(
            artifact_path=artifact, identity=_identity("sess-2"), title="t", summary="s",
            workspace_root=workspace, replaces_view_id=first.view_id,
        )


def test_state_roundtrip_and_bounds(tmp_path):
    store, manifest = _register(tmp_path)
    assert store.read_state(manifest.session_id, manifest.view_id) is None
    revision = store.write_state(manifest.session_id, manifest.view_id, state={"tab": 2})
    stored = store.read_state(manifest.session_id, manifest.view_id)
    assert stored["state"] == {"tab": 2}
    assert stored["revision"] == revision
    with pytest.raises(ViewStoreError):
        store.write_state(manifest.session_id, manifest.view_id, state={"blob": "x" * MAX_VIEW_STATE_BYTES})


def test_fork_copies_visible_views_and_rebinds(tmp_path):
    store, manifest = _register(tmp_path)
    store.write_state(manifest.session_id, manifest.view_id, state={"tab": 1})
    store.fork_session(manifest.session_id, "fork-1", [(manifest.view_id, manifest.revision)])
    forked = store.manifest("fork-1", manifest.view_id)
    assert forked.session_id == "fork-1"
    assert forked.sha256 == manifest.sha256
    assert store.read_state("fork-1", manifest.view_id)["state"] == {"tab": 1}


def test_delete_session_removes_only_its_views(tmp_path):
    store, keep = _register(tmp_path)  # sess-1
    workspace = tmp_path / "workspace"
    other = store.register(
        artifact_path=_artifact(workspace, "o.html"), identity=_identity("sess-2"),
        title="t", summary="s", workspace_root=workspace,
    )
    store.delete_session("sess-2")
    with pytest.raises(ViewStoreError):
        store.manifest("sess-2", other.view_id)
    assert store.manifest("sess-1", keep.view_id).view_id == keep.view_id


def test_identity_rejects_malformed_ids(tmp_path):
    with pytest.raises(ViewStoreError):
        ViewIdentity(session_id="bad id with spaces", turn_id="t", tool_call_id="c")


def test_for_project_resolves_under_project_data_dir(tmp_path):
    # Uses the autouse isolated_app_root fixture (REVERIE_APP_ROOT -> dist sandbox).
    from reverie.storage import ProjectStorageResolver

    workspace = tmp_path / "ws"
    workspace.mkdir(parents=True)
    store = ViewStore.for_project(workspace)
    expected = ProjectStorageResolver.for_project(workspace).project_dir / "views"
    assert store.views_root == expected

    artifact = _artifact(workspace, "panel.html")
    manifest = store.register(
        artifact_path=artifact, identity=_identity(), title="Panel", summary="A panel.",
        workspace_root=workspace,
    )
    directory = store.view_directory(manifest.session_id, manifest.view_id, manifest.revision)
    assert directory.is_dir()
    assert str(expected) in str(directory)
