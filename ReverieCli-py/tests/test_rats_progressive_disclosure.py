"""Progressive tool disclosure contracts for the RATS client runtime.

RATS beats an always-on tool protocol only if the model-visible surface stays
small. These tests pin the properties that make that true:

* an always-visible capability card introduces what exists without disclosing it,
* searching does not silently spend a schema on every match,
* the loaded working set is bounded, evicting cold tools instead of growing,
* what a search reports as loaded is what the working set actually holds,
* a supplied service id narrows the search instead of widening it.

The last two exist because both failure modes are invisible to a happy-path
fixture: one needs a catalog row the provider publishes without a schema, the
other needs a second session behind the same provider.
"""

from __future__ import annotations

import os
import shutil
import uuid
from pathlib import Path
from typing import Any, Dict, List

from reverie.rats import (
    _DEFAULT_LOADED_TOOLS,
    _MAX_LOADED_DEFINITIONS_PER_SESSION,
    RatsDescriptor,
    RatsRuntime,
    _RatsSession,
)
from reverie.tools.rats_catalog import RatsCatalogTool


CONTROL_TOKEN = "a" * 64
SESSION_TOKEN = "b" * 64


def _test_root(name: str) -> Path:
    root = Path(__file__).resolve().parents[2] / "dist" / ".reverie" / "test-temp" / f"rats-{name}-{uuid.uuid4().hex}"
    root.mkdir(parents=True, exist_ok=True)
    return root


def _compact_row(name: str, category: str, *, schema: Any = "0123456789abcdef") -> Dict[str, Any]:
    """Build one compact catalog row.

    ``schema`` is ``None`` for any native tool the provider publishes without a
    request schema — the engine writes a JSON null there
    (``reverie_rats.cpp:1146``), so a fixture that always supplies a digest never
    exercises the undisclosable half of the catalog.

    ``flags`` is a list of set flag names, which is what the engine emits
    (``reverie_rats.cpp:1138-1145``) and the only shape ``_compact_tools`` keeps
    (``rats.py:613-615`` turns anything else into ``[]``).
    """
    return {
        "key": name[:8],
        "name": name,
        "category": category,
        "summary": f"Native tool {name}.",
        "permission": "read",
        "flags": [],
        "schema": schema,
    }


def _definition(name: str, category: str = "scene") -> Dict[str, Any]:
    return {
        "name": name,
        "category": category,
        "summary": f"Native tool {name}.",
        "permission": "read",
        "request_schema": {"type": "object", "properties": {}},
        "response_schema": {"type": "object", "properties": {}},
    }


def _publish_session(
    runtime: RatsRuntime,
    root: Path,
    compact: List[Dict[str, Any]],
    *,
    suffix: str = "disclosure",
    provider_id: str = "reverie.engine",
) -> _RatsSession:
    """Publish one session with a known compact catalog and no discovery I/O."""
    executable = (root / "reverie.windows.editor.x86_64.exe").resolve()
    service_id = f"rats-{os.getpid()}-{suffix}"
    descriptor = RatsDescriptor(
        service_id=service_id,
        provider_id=provider_id,
        service_kind="builtin",
        product="Reverie Engine",
        product_version="test",
        executable=executable,
        pid=os.getpid(),
        port=1,
        endpoint="http://127.0.0.1:1/rtp",
        descriptor_path=executable.parent / "ReverieLocal" / "RATS" / "Services" / f"{service_id}.json",
        catalog_revision="catalog-test",
        native_tool_count=len(compact),
        started_utc="2026-08-09T00:00:00Z",
        control_token=CONTROL_TOKEN,
    )
    session = _RatsSession(
        descriptor=descriptor,
        token=SESSION_TOKEN,
        permissions=["read"],
        compact_tools=list(compact),
    )
    with runtime._lock:
        # Snapshot reads must not trigger real descriptor discovery in tests.
        runtime._has_refreshed = True
        runtime._sessions[(descriptor.provider_id, descriptor.service_id)] = session
    return session


def _runtime_with_catalog(
    root: Path,
    compact: List[Dict[str, Any]],
) -> tuple[RatsRuntime, _RatsSession]:
    runtime = RatsRuntime(root)
    return runtime, _publish_session(runtime, root, compact)


def _describe_only(payload_by_operation: Dict[str, Any] | None = None):
    """Build a fake RTP transport that answers describe from the requested names."""
    extra = dict(payload_by_operation or {})

    def fake_request(_descriptor, operation, payload=None, **_kwargs):
        if operation == "catalog.describe":
            names = (payload or {}).get("names", [])
            return {"tools": [_definition(name) for name in names]}
        return extra.get(operation, {})

    return fake_request


def test_the_cap_clears_the_largest_real_single_task_working_set() -> None:
    """A cap tuned to the average working set breaks real multi-subsystem work.

    ``test_rats_engine_task_e2e`` drives the engine's world-streaming flow with 20
    concurrently loaded native tools, on top of the 4 pinned status tools. The cap
    must stay above that, or eviction starts dropping tools a live task still needs.
    """
    assert _MAX_LOADED_DEFINITIONS_PER_SESSION >= 20 + len(_DEFAULT_LOADED_TOOLS)


def test_capability_card_introduces_the_surface_without_disclosing_schemas() -> None:
    root = _test_root("capability-card")
    compact = [
        _compact_row("scene.create", "scene"),
        _compact_row("scene.add_node", "scene"),
        _compact_row("build.package", "build"),
    ]
    runtime, _session = _runtime_with_catalog(root, compact)
    try:
        cards = runtime.capability_card()
        assert len(cards) == 1
        card = cards[0]
        assert card["providerId"] == "reverie.engine"
        assert card["product"] == "Reverie Engine"
        assert card["toolCount"] == 3
        assert card["loadedCount"] == 0
        assert card["loadedLimit"] == _MAX_LOADED_DEFINITIONS_PER_SESSION
        assert card["categories"] == [{"name": "build", "count": 1}, {"name": "scene", "count": 2}]
        # The card is a summary, not a disclosure: no request schema may leak.
        assert "request_schema" not in repr(card)
    finally:
        shutil.rmtree(root, ignore_errors=True)


def test_catalog_tool_description_carries_the_card_and_stays_far_smaller_than_schemas() -> None:
    root = _test_root("card-in-description")
    # 73 is the Reverie Engine's real catalog size, so the size bound below is
    # measured against a live-scale surface rather than a token fixture.
    compact = [_compact_row(f"world.tool_{index}", "world") for index in range(73)]
    runtime, _session = _runtime_with_catalog(root, compact)
    try:
        tool = RatsCatalogTool({"rats_runtime": runtime})
        description = tool.description
        assert "Reverie Engine" in description
        assert "73 native tools" in description
        assert "world(73)" in description
        # The whole introduction for 73 tools must cost far less than one schema each.
        assert len(description) < 1200
        assert tool.get_schema()["function"]["description"] == description
    finally:
        shutil.rmtree(root, ignore_errors=True)


def test_catalog_tool_description_falls_back_when_no_service_is_connected() -> None:
    root = _test_root("card-empty")
    runtime, session = _runtime_with_catalog(root, [_compact_row("ping", "system")])
    try:
        assert runtime._detach_session(session) is True
        tool = RatsCatalogTool({"rats_runtime": runtime})
        assert "Connected now" not in tool.description
        assert "Search the compact catalogs" in tool.description
        # A missing runtime must not raise while the model is being given tools.
        assert "Connected now" not in RatsCatalogTool({}).description
    finally:
        shutil.rmtree(root, ignore_errors=True)


def test_search_does_not_disclose_schemas_unless_loading_is_requested() -> None:
    root = _test_root("search-no-load")
    compact = [_compact_row("scene.create", "scene"), _compact_row("scene.add_node", "scene")]
    runtime, session = _runtime_with_catalog(root, compact)
    describe_calls: List[Dict[str, Any]] = []

    def fake_request(_descriptor, operation, payload=None, **_kwargs):
        if operation == "catalog.search":
            return {"matches": [{"name": row["name"], "score": 100} for row in compact]}
        if operation == "catalog.describe":
            describe_calls.append(dict(payload or {}))
            return {"tools": [_definition(name) for name in (payload or {}).get("names", [])]}
        return {}

    runtime._request = fake_request
    try:
        matches = runtime.search("create a scene", service_id=session.descriptor.service_id)
        assert [item["name"] for item in matches] == ["scene.add_node", "scene.create"]
        assert describe_calls == [], "search must not auto-load full schemas"
        assert dict(session.definitions) == {}

        loaded = runtime.search(
            "create a scene",
            service_id=session.descriptor.service_id,
            load=True,
        )
        assert len(describe_calls) == 1
        assert sorted(session.definitions) == ["scene.add_node", "scene.create"]
        assert len(loaded) == 2
    finally:
        shutil.rmtree(root, ignore_errors=True)


def test_catalog_tool_search_defaults_to_metadata_only_and_reports_the_next_step() -> None:
    root = _test_root("tool-search-default")
    runtime, session = _runtime_with_catalog(root, [_compact_row("build.package", "build")])
    runtime._request = _describe_only(
        {"catalog.search": {"matches": [{"name": "build.package", "score": 300}]}}
    )
    tool = RatsCatalogTool({"rats_runtime": runtime})
    try:
        result = tool.execute(operation="search", query="package the project")
        assert result.success is True
        assert "loaded_for_next_step" not in result.data
        assert "operation='load'" in result.data["next_step"]
        assert dict(session.definitions) == {}

        result = tool.execute(operation="search", query="package the project", load=True)
        assert result.data["loaded_for_next_step"] == ["build.package"]
        assert list(session.definitions) == ["build.package"]
    finally:
        shutil.rmtree(root, ignore_errors=True)


def test_search_marks_a_match_the_provider_publishes_without_a_schema_as_unloaded() -> None:
    """Matching is not loading. A tool with no schema cannot become callable.

    RATS is provider-neutral, and ``docs/RATS_RTP.md`` states that a tool without
    an RTP request schema stays visible in the compact catalog without becoming a
    model function. This pins the reporting side of that rule.

    It is a guard, not a reproduction of a live failure: every one of the Reverie
    Engine's 73 catalog entries currently does publish a schema — the eight tool
    families plus the six specials in ``_get_tool_schemas``
    (``reverie_ai_bridge.cpp:239-333``) cover 67 + 6 = 73 exactly — so today the
    engine never takes this path.
    """
    root = _test_root("schemaless-match")
    compact = [
        _compact_row("build.package", "build"),
        _compact_row("build.status", "build", schema=None),
    ]
    runtime, session = _runtime_with_catalog(root, compact)
    describe_calls: List[Dict[str, Any]] = []

    def fake_request(_descriptor, operation, payload=None, **_kwargs):
        if operation == "catalog.search":
            return {
                "matches": [
                    {"name": "build.package", "score": 300},
                    {"name": "build.status", "score": 200},
                ]
            }
        if operation == "catalog.describe":
            describe_calls.append(dict(payload or {}))
            return {"tools": [_definition(name) for name in (payload or {}).get("names", [])]}
        return {}

    runtime._request = fake_request
    try:
        matches = runtime.search("package", service_id=session.descriptor.service_id, load=True)
        assert {item["name"]: item["loaded"] for item in matches} == {
            "build.package": True,
            "build.status": False,
        }
        # The schemaless match must not even be requested: that round trip buys
        # nothing the provider can answer.
        assert describe_calls == [{"names": ["build.package"]}]
        assert list(session.definitions) == ["build.package"]
    finally:
        shutil.rmtree(root, ignore_errors=True)


def test_catalog_tool_never_names_an_unloaded_match_as_callable() -> None:
    """The payload's promise has to match the working set, or the next call fails."""
    root = _test_root("honest-loaded-list")
    compact = [
        _compact_row("build.package", "build"),
        _compact_row("build.status", "build", schema=None),
    ]
    runtime, session = _runtime_with_catalog(root, compact)
    runtime._request = _describe_only(
        {
            "catalog.search": {
                "matches": [
                    {"name": "build.package", "score": 300},
                    {"name": "build.status", "score": 200},
                ]
            }
        }
    )
    tool = RatsCatalogTool({"rats_runtime": runtime})
    try:
        result = tool.execute(operation="search", query="package the project", load=True)
        assert result.success is True
        assert result.data["loaded_for_next_step"] == ["build.package"]
        assert result.data["not_loaded"] == ["build.status"]
        assert list(session.definitions) == ["build.package"]
    finally:
        shutil.rmtree(root, ignore_errors=True)


def test_catalog_tool_load_reports_names_the_provider_did_not_describe() -> None:
    """``describe`` drops what it cannot disclose, and silence there reads as success."""
    root = _test_root("load-not-described")
    compact = [
        _compact_row("build.package", "build"),
        _compact_row("build.status", "build", schema=None),
    ]
    runtime, session = _runtime_with_catalog(root, compact)

    def fake_request(_descriptor, operation, payload=None, **_kwargs):
        if operation == "catalog.describe":
            described: List[Dict[str, Any]] = []
            for name in (payload or {}).get("names", []):
                if name == "build.status":
                    # The provider answers, but with no schema it can disclose.
                    described.append({"name": name, "category": "build", "summary": "No schema."})
                else:
                    described.append(_definition(name, "build"))
            return {"tools": described}
        return {}

    runtime._request = fake_request
    tool = RatsCatalogTool({"rats_runtime": runtime})
    try:
        result = tool.execute(
            operation="load",
            service_id=session.descriptor.service_id,
            names=["build.package", "build.status"],
        )
        assert result.success is True
        assert result.data["loaded_for_next_step"] == ["build.package"]
        assert result.data["not_loaded"] == ["build.status"]
        assert list(session.definitions) == ["build.package"]
    finally:
        shutil.rmtree(root, ignore_errors=True)


def test_search_with_both_ids_stays_inside_the_named_service() -> None:
    """A supplied service id narrows the search; it must not fall through.

    Both ids together is the precise case that used to widen: with a resolvable
    service id the provider branch still ran, so the search reached services the
    caller had excluded and, under ``load=True``, spent schemas in a session it
    never named.
    """
    root = _test_root("both-ids")
    runtime = RatsRuntime(root)
    named = _publish_session(runtime, root, [_compact_row("scene.create", "scene")], suffix="named")
    other = _publish_session(runtime, root, [_compact_row("build.package", "build")], suffix="other")
    matches_by_service = {
        named.descriptor.service_id: [{"name": "scene.create", "score": 300}],
        other.descriptor.service_id: [{"name": "build.package", "score": 300}],
    }
    searched: List[str] = []

    def fake_request(descriptor, operation, payload=None, **_kwargs):
        if operation == "catalog.search":
            searched.append(descriptor.service_id)
            return {"matches": matches_by_service[descriptor.service_id]}
        if operation == "catalog.describe":
            return {"tools": [_definition(name) for name in (payload or {}).get("names", [])]}
        return {}

    runtime._request = fake_request
    try:
        matches = runtime.search(
            "create a scene",
            service_id=named.descriptor.service_id,
            provider_id=named.descriptor.provider_id,
            load=True,
        )
        assert searched == [named.descriptor.service_id]
        assert [item["name"] for item in matches] == ["scene.create"]
        assert list(named.definitions) == ["scene.create"]
        assert list(other.definitions) == [], "an unnamed session must keep its schemas undisclosed"

        # A provider id on its own still means provider-wide, which is the
        # behaviour the narrowing fix must not remove.
        searched.clear()
        runtime.search("create a scene", provider_id=named.descriptor.provider_id)
        assert sorted(searched) == sorted([named.descriptor.service_id, other.descriptor.service_id])
    finally:
        shutil.rmtree(root, ignore_errors=True)


def test_loaded_definitions_are_bounded_and_evict_least_recently_used_first() -> None:
    root = _test_root("bounded-working-set")
    total = _MAX_LOADED_DEFINITIONS_PER_SESSION + 6
    compact = [_compact_row(f"scene.tool_{index:02d}", "scene") for index in range(total)]
    runtime, session = _runtime_with_catalog(root, compact)
    runtime._request = _describe_only()
    try:
        for index in range(total):
            runtime.describe(session.descriptor.service_id, [f"scene.tool_{index:02d}"])
        assert len(session.definitions) == _MAX_LOADED_DEFINITIONS_PER_SESSION
        # The six oldest went; the newest cap-many stayed.
        assert "scene.tool_00" not in session.definitions
        assert "scene.tool_05" not in session.definitions
        assert "scene.tool_06" in session.definitions
        assert f"scene.tool_{total - 1:02d}" in session.definitions
        # The model-visible surface is bounded too, not just the internal dict.
        _generation, definitions = runtime.get_tool_definitions_snapshot()
        assert len(definitions) == _MAX_LOADED_DEFINITIONS_PER_SESSION
    finally:
        shutil.rmtree(root, ignore_errors=True)


def test_pinned_status_tools_survive_eviction() -> None:
    root = _test_root("pinned-survive")
    total = _MAX_LOADED_DEFINITIONS_PER_SESSION + 4
    compact = [_compact_row("get_status", "system")]
    compact.extend(_compact_row(f"scene.tool_{index:02d}", "scene") for index in range(total))
    runtime, session = _runtime_with_catalog(root, compact)
    runtime._request = _describe_only()
    try:
        runtime._describe_into_session(session, ["get_status"], pin=True)
        assert session.pinned == {"get_status"}
        for index in range(total):
            runtime.describe(session.descriptor.service_id, [f"scene.tool_{index:02d}"])
        assert len(session.definitions) == _MAX_LOADED_DEFINITIONS_PER_SESSION
        assert "get_status" in session.definitions, "pinned status tools must never be evicted"
    finally:
        shutil.rmtree(root, ignore_errors=True)


def test_calling_a_tool_keeps_it_out_of_the_eviction_path() -> None:
    root = _test_root("call-keeps-hot")
    total = _MAX_LOADED_DEFINITIONS_PER_SESSION
    compact = [_compact_row(f"scene.tool_{index:02d}", "scene") for index in range(total + 1)]
    runtime, session = _runtime_with_catalog(root, compact)
    runtime._request = _describe_only({"tool.call": {"ok": True}})
    try:
        for index in range(total):
            runtime.describe(session.descriptor.service_id, [f"scene.tool_{index:02d}"])
        assert "scene.tool_00" in session.definitions
        # Using the coldest tool makes it the hottest, so the next load cannot drop it.
        runtime.call_tool(session.descriptor.service_id, "scene.tool_00", {})
        runtime.describe(session.descriptor.service_id, [f"scene.tool_{total:02d}"])
        assert len(session.definitions) == total
        assert "scene.tool_00" in session.definitions
        assert "scene.tool_01" not in session.definitions
    finally:
        shutil.rmtree(root, ignore_errors=True)


def test_catalog_tool_reports_what_eviction_removed() -> None:
    root = _test_root("evicted-report")
    total = _MAX_LOADED_DEFINITIONS_PER_SESSION
    compact = [_compact_row(f"scene.tool_{index:02d}", "scene") for index in range(total + 1)]
    runtime, session = _runtime_with_catalog(root, compact)
    runtime._request = _describe_only()
    tool = RatsCatalogTool({"rats_runtime": runtime})
    try:
        for index in range(total):
            runtime.describe(session.descriptor.service_id, [f"scene.tool_{index:02d}"])
        result = tool.execute(
            operation="load",
            service_id=session.descriptor.service_id,
            names=[f"scene.tool_{total:02d}"],
        )
        assert result.success is True
        assert result.data["loaded_for_next_step"] == [f"scene.tool_{total:02d}"]
        assert result.data["evicted"] == ["scene.tool_00"]
    finally:
        shutil.rmtree(root, ignore_errors=True)
