"""Catalog refreshes persist through the public config, probe and desktop paths."""

import importlib
import json
from types import SimpleNamespace
from urllib.parse import urlsplit

import pytest
import requests

from reverie import agnes, custom_providers, model_catalog_cache, opencode, sensenova
from reverie.config import Config, ConfigManager
from reverie.provider_probe import collect_provider_rows, probe_provider_rows
from reverie.sdk_bridge import ReverieSdkBridge


OPENAI_SOURCES = ("aihubmix", "nvidia", "modelscope")
API_SOURCES = (*OPENAI_SOURCES, "sensenova", "opencode", "agnes")


@pytest.fixture(autouse=True)
def isolated_catalogs(monkeypatch):
    monkeypatch.setattr(model_catalog_cache, "_OPENAI_MODEL_CACHE", {})
    monkeypatch.setattr(custom_providers, "_MODEL_CACHE", {})
    for module, attribute in ((sensenova, "_MODEL_CACHE"), (opencode, "_OPENCODE_MODEL_CACHE"), (agnes, "_MODEL_CACHE")):
        monkeypatch.setattr(module, attribute, {"key": "", "expires_at": 0.0, "models": []})

    def unavailable(*args, **kwargs):
        raise requests.ConnectionError("Fixture endpoint unavailable")

    monkeypatch.setattr(requests, "get", unavailable)
    monkeypatch.setattr(agnes, "urlopen", unavailable)


def ids(models):
    return [item["id"] for item in models]


@pytest.mark.parametrize("source", ["opencode", "agnes"])
def test_gui_catalog_read_is_offline_and_explicit_refresh_survives_restart(tmp_path, monkeypatch, source):
    manager = ConfigManager(tmp_path)
    config = new_config(source)
    manager.ensure_dirs()
    manager.save(config)
    bridge = ReverieSdkBridge()
    bridge.ensure_interface = lambda: SimpleNamespace(config_manager=manager)

    def unexpected_request(*args, **kwargs):
        pytest.fail("Reading the picker catalog must not contact providers")

    with monkeypatch.context() as offline:
        offline.setattr(requests, "get", unexpected_request)
        offline.setattr(agnes, "urlopen", unexpected_request)
        cached = bridge.model_sources_payload()
    assert next(item for item in cached["sources"] if item["id"] == source)["models"]

    serve_payload(monkeypatch, {"data": [{"id": f"{source}-fresh", "output_modalities": ["text"]}]})
    payload = bridge.model_sources_payload(fetch_live=True)
    refreshed = next(item for item in payload["sources"] if item["id"] == source)
    assert ids(refreshed["models"]) == [f"{source}-fresh"]
    forget_process_caches()
    reloaded = Config.from_dict(json.loads(manager.config_path.read_text(encoding="utf-8")))
    assert ids(getter(source)(getattr(reloaded, source), fetch_live=False)) == [f"{source}-fresh"]
    saved_at = manager.config_path.stat().st_mtime_ns
    bridge.model_sources_payload()
    assert manager.config_path.stat().st_mtime_ns == saved_at


def test_agnes_api_accepts_chat_ids_without_legacy_prefix(monkeypatch):
    config = new_config("agnes")
    serve_payload(monkeypatch, {"data": [{
        "id": "vendor/new-chat", "output_modalities": ["text"], "input_modalities": ["text"],
        "supported_features": [], "context_length": 123456, "max_output_length": 2048,
    }]})
    models = agnes.get_agnes_model_catalog(config.agnes, fetch_live=True, force_refresh=True)
    assert ids(models) == ["vendor/new-chat"]
    assert models[0]["vision"] is False and models[0]["thinking"] is False
    assert models[0]["tool_calling"] is False
    runtime = agnes.build_agnes_runtime_model_data(config.agnes)
    assert runtime["model"] == "vendor/new-chat"
    assert runtime["max_context_tokens"] == 123456


def new_config(source):
    return Config(active_model_source=source, **{source: {
        "api_key": "fixture-key",
        "api_url": f"https://{source}.invalid/v1",
        "selected_model_id": f"{source}-fresh",
    }})


def getter(source):
    module = importlib.import_module(f"reverie.{source}")
    return getattr(module, f"get_{source}_model_catalog")


def serve_payload(monkeypatch, payload):
    monkeypatch.setattr(requests, "get", lambda *args, **kwargs: SimpleNamespace(
        raise_for_status=lambda: None, json=lambda: payload,
    ))
    monkeypatch.setattr(agnes, "urlopen", lambda *args, **kwargs: JsonResponse(payload))


class JsonResponse:
    def __init__(self, payload):
        self.payload = payload

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def read(self):
        return json.dumps(self.payload).encode("utf-8")


def forget_process_caches():
    model_catalog_cache._OPENAI_MODEL_CACHE.clear()
    custom_providers._MODEL_CACHE.clear()
    for cache in (sensenova._MODEL_CACHE, opencode._OPENCODE_MODEL_CACHE, agnes._MODEL_CACHE):
        cache.update(key="", expires_at=0.0, models=[])


@pytest.mark.parametrize("source", OPENAI_SOURCES)
def test_openai_source_inventory_survives_config_roundtrip_and_cache_loss(monkeypatch, source):
    config = new_config(source)
    serve_payload(monkeypatch, {"data": [{
        "id": f"{source}-fresh", "context_length": 123456, "max_output_length": 2048,
    }]})
    refreshed = getter(source)(getattr(config, source), fetch_live=True)
    assert ids(refreshed) == [f"{source}-fresh"]

    reloaded = Config.from_dict(json.loads(json.dumps(config.to_dict())))
    forget_process_caches()
    monkeypatch.setattr(requests, "get", lambda *args, **kwargs: pytest.fail("A normal catalog read must not make a request"))

    assert getter(source)(getattr(reloaded, source)) == refreshed
    assert reloaded.active_model.model == f"{source}-fresh"
    assert reloaded.active_model.max_context_tokens == 123456


@pytest.mark.parametrize("source", API_SOURCES)
def test_successful_empty_inventory_survives_config_roundtrip(monkeypatch, source):
    config = new_config(source)
    serve_payload(monkeypatch, {"data": []})
    assert getter(source)(getattr(config, source), fetch_live=True) == []

    reloaded = Config.from_dict(json.loads(json.dumps(config.to_dict())))
    forget_process_caches()
    assert getter(source)(getattr(reloaded, source)) == []
    assert reloaded.active_model is None


@pytest.mark.parametrize("source", API_SOURCES)
@pytest.mark.parametrize("malformed", [{"error": "bad catalog"}, {"data": {"id": "invalid"}}])
def test_malformed_response_keeps_last_successful_inventory(monkeypatch, source, malformed):
    config = new_config(source)
    record = getattr(config, source)
    serve_payload(monkeypatch, {"data": [{"id": f"{source}-fresh"}]})
    refreshed = getter(source)(record, fetch_live=True)
    serve_payload(monkeypatch, malformed)

    assert getter(source)(record, fetch_live=True) == refreshed
    forget_process_caches()
    assert getter(source)(record) == refreshed


@pytest.mark.parametrize("source", API_SOURCES)
@pytest.mark.parametrize("connection_field", ["api_key", "api_url"])
def test_changed_connection_does_not_inherit_previous_api_inventory(monkeypatch, source, connection_field):
    config = new_config(source)
    record = getattr(config, source)
    serve_payload(monkeypatch, {"data": [{"id": f"{source}-fresh"}]})
    getter(source)(record, fetch_live=True)
    record[connection_field] = "other-fixture-key" if connection_field == "api_key" else "https://another.invalid/v1"

    def unavailable(*args, **kwargs):
        raise requests.ConnectionError("The new connection has no successful inventory")

    monkeypatch.setattr(requests, "get", unavailable)
    monkeypatch.setattr(agnes, "urlopen", unavailable)

    assert f"{source}-fresh" not in ids(getter(source)(record))


@pytest.mark.parametrize("source", API_SOURCES)
def test_provider_probe_updates_actual_config_inventory(monkeypatch, source):
    config = new_config(source)
    serve_payload(monkeypatch, {"data": [{
        "id": f"{source}-fresh", "context_length": 123456, "max_output_length": 2048,
    }]})
    row = next(row for row in collect_provider_rows(config) if row.source == source)
    probe = probe_provider_rows([row])[row.key]
    assert probe.status == "online", probe.detail
    assert ids(probe.models) == [f"{source}-fresh"]

    reloaded = Config.from_dict(json.loads(json.dumps(config.to_dict())))
    forget_process_caches()
    assert ids(getter(source)(getattr(reloaded, source))) == [f"{source}-fresh"]
    assert reloaded.active_model.model == f"{source}-fresh"
    assert reloaded.active_model.max_context_tokens == 123456


@pytest.mark.parametrize("source", API_SOURCES)
def test_empty_provider_probe_replaces_persisted_inventory(monkeypatch, source):
    config = new_config(source)
    serve_payload(monkeypatch, {"data": [{"id": f"{source}-fresh"}]})
    getter(source)(getattr(config, source), fetch_live=True)
    serve_payload(monkeypatch, {"data": []})
    row = next(row for row in collect_provider_rows(config) if row.source == source)

    probe = probe_provider_rows([row])[row.key]
    assert probe.status == "empty", probe.detail
    reloaded = Config.from_dict(json.loads(json.dumps(config.to_dict())))
    forget_process_caches()
    assert getter(source)(getattr(reloaded, source)) == []
    assert reloaded.active_model is None


@pytest.mark.parametrize("models", [[{"id": "custom-fresh", "context_length": 123456}], []])
def test_custom_provider_probe_persists_actual_record(monkeypatch, models):
    provider = custom_providers.default_custom_provider(
        provider_id="fixture", name="Fixture", base_url="https://custom.invalid/v1", api_key="fixture-key",
    )
    config = Config(active_model_source="custom")
    config.custom_providers = custom_providers.upsert_custom_provider(config.custom_providers, provider, activate=True)
    serve_payload(monkeypatch, {"data": models})
    row = next(row for row in collect_provider_rows(config) if row.kind == "custom")

    probe = probe_provider_rows([row])[row.key]
    assert probe.status == ("online" if models else "empty"), probe.detail
    reloaded = Config.from_dict(json.loads(json.dumps(config.to_dict())))
    forget_process_caches()
    stored = custom_providers.resolve_active_custom_provider(reloaded.custom_providers)
    assert ids(custom_providers.get_custom_provider_model_catalog(stored)) == ids(models)
    if not models:
        assert reloaded.active_model is None


def test_desktop_refresh_read_and_selection_persist_all_provider_inventories(monkeypatch, tmp_path):
    config = new_config("nvidia")
    for source in API_SOURCES:
        setattr(config, source, getattr(new_config(source), source))
    for provider_id in ("active", "inactive"):
        provider = custom_providers.default_custom_provider(
            provider_id=provider_id, name=provider_id,
            base_url=f"https://{provider_id}.invalid/v1", api_key="fixture-key",
        )
        config.custom_providers = custom_providers.upsert_custom_provider(
            config.custom_providers, provider, activate=provider_id == "active",
        )

    requested_hosts = []

    def payload_for(url):
        host = urlsplit(url).hostname
        requested_hosts.append(host)
        return {"data": [{"id": host.split(".")[0] + "-fresh", "context_length": 123456}]}

    monkeypatch.setattr(requests, "get", lambda url, **kwargs: SimpleNamespace(
        raise_for_status=lambda: None, json=lambda: payload_for(url),
    ))
    monkeypatch.setattr(agnes, "urlopen", lambda request, **kwargs: JsonResponse(payload_for(request.full_url)))
    manager = ConfigManager(tmp_path)
    manager.save(config)
    interface = SimpleNamespace(config_manager=manager)
    bridge = ReverieSdkBridge.__new__(ReverieSdkBridge)
    bridge.ensure_interface = lambda: interface
    bridge._refresh_agent = lambda: None
    bridge.workspace_payload = lambda: {}

    refreshed = bridge.dispatch({"id": "refresh", "action": "refreshModelSources"})
    assert set(requested_hosts) >= {f"{source}.invalid" for source in API_SOURCES} | {"active.invalid", "inactive.invalid"}
    for source in API_SOURCES:
        entry = next(item for item in refreshed["models"]["sources"] if item["id"] == source)
        assert ids(entry["models"]) == [f"{source}-fresh"]

    forget_process_caches()
    interface.config_manager = ConfigManager(tmp_path)
    monkeypatch.setattr(requests, "get", lambda *args, **kwargs: pytest.fail("Reading or selecting a refreshed model must not request the API"))
    monkeypatch.setattr(agnes, "urlopen", lambda *args, **kwargs: pytest.fail("Reading or selecting a refreshed model must not request the API"))
    read = bridge.dispatch({"id": "read", "action": "getModelSources"})
    custom_entry = next(item for item in read["models"]["sources"] if item["id"] == "custom")
    assert {item["id"]: ids(item["models"]) for item in custom_entry["custom_providers"]} == {
        "active": ["active-fresh"], "inactive": ["inactive-fresh"],
    }
    for source in API_SOURCES:
        selected = bridge.dispatch({
            "id": f"select-{source}", "action": "selectModel",
            "payload": {"source": source, "modelId": f"{source}-fresh"},
        })
        assert selected["type"] == "model.selected"
        stored = interface.config_manager.load()
        assert stored.active_model.model == f"{source}-fresh"
        assert stored.active_model.max_context_tokens == 123456
