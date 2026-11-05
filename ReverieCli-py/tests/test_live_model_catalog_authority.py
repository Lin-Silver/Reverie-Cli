"""A successful API inventory remains the authority until another one arrives."""

import json
from pathlib import Path
import subprocess
import sys
from types import SimpleNamespace

import pytest
import requests

from reverie import agnes, custom_providers, opencode, sensenova


@pytest.fixture(autouse=True)
def isolated_catalogs(monkeypatch):
    monkeypatch.setattr(sensenova, "_MODEL_CACHE", {"key": "", "expires_at": 0.0, "models": []})
    monkeypatch.setattr(opencode, "_OPENCODE_MODEL_CACHE", {"key": "", "expires_at": 0.0, "models": []})
    monkeypatch.setattr(agnes, "_MODEL_CACHE", {"key": "", "expires_at": 0.0, "models": []})
    monkeypatch.setattr(custom_providers, "_MODEL_CACHE", {})

    def unavailable(*args, **kwargs):
        raise requests.ConnectionError("Fixture endpoint unavailable")

    monkeypatch.setattr(requests, "get", unavailable)
    monkeypatch.setattr(agnes, "urlopen", unavailable)


def provider(source):
    config = {
        "api_key": "fixture-key",
        "api_url": "https://catalog.invalid/v1",
        "selected_model_id": "fresh-model",
    }
    if source == "sensenova":
        return config, sensenova.get_sensenova_model_catalog
    if source == "opencode":
        return config, opencode.get_opencode_model_catalog
    config.update(
        id="fixture",
        name="Fixture",
        base_url="https://catalog.invalid/v1",
        format="openai-chat",
        models=[{"id": "old-config-model"}],
    )
    return config, custom_providers.get_custom_provider_model_catalog


def serve_models(monkeypatch, models):
    monkeypatch.setattr(requests, "get", lambda *args, **kwargs: SimpleNamespace(
        raise_for_status=lambda: None,
        json=lambda: {"data": models},
    ))


def model_ids(models):
    return [model["id"] for model in models]


@pytest.mark.parametrize("source", ["sensenova", "opencode", "custom"])
def test_normal_catalog_read_keeps_successful_api_inventory(monkeypatch, source):
    config, get_catalog = provider(source)
    serve_models(monkeypatch, [{"id": "fresh-model", "context_length": 123456}])
    refreshed = get_catalog(config, fetch_live=True, force_refresh=True)

    assert model_ids(refreshed) == ["fresh-model"]
    assert get_catalog(config) == refreshed


@pytest.mark.parametrize("source", ["sensenova", "opencode", "custom"])
def test_empty_successful_inventory_does_not_resurrect_old_models(monkeypatch, source):
    config, get_catalog = provider(source)
    serve_models(monkeypatch, [])

    assert get_catalog(config, fetch_live=True, force_refresh=True) == []
    assert get_catalog(config) == []


@pytest.mark.parametrize("source", ["sensenova", "opencode", "custom"])
def test_failed_refresh_keeps_last_successful_inventory(monkeypatch, source):
    config, get_catalog = provider(source)
    serve_models(monkeypatch, [{"id": "fresh-model"}])
    refreshed = get_catalog(config, fetch_live=True, force_refresh=True)

    def unavailable(*args, **kwargs):
        raise requests.ConnectionError("Fixture endpoint unavailable")

    monkeypatch.setattr(requests, "get", unavailable)
    assert get_catalog(config, fetch_live=True, force_refresh=True) == refreshed


@pytest.mark.parametrize("source", ["sensenova", "opencode", "custom"])
def test_latest_inventory_replaces_previous_inventory(monkeypatch, source):
    config, get_catalog = provider(source)
    serve_models(monkeypatch, [{"id": "removed-model"}])
    get_catalog(config, fetch_live=True, force_refresh=True)
    serve_models(monkeypatch, [{"id": "replacement-model"}])

    assert model_ids(get_catalog(config, fetch_live=True, force_refresh=True)) == ["replacement-model"]
    assert model_ids(get_catalog(config)) == ["replacement-model"]


@pytest.mark.parametrize("source", ["sensenova", "opencode", "custom"])
def test_successful_inventory_survives_config_reload_in_new_process(monkeypatch, source):
    config, get_catalog = provider(source)
    serve_models(monkeypatch, [{"id": "fresh-model", "context_length": 123456}])
    get_catalog(config, fetch_live=True, force_refresh=True)
    script = '''import json, sys
from reverie import sensenova, opencode, custom_providers
source = sys.argv[1]
get_catalog = {
    "sensenova": sensenova.get_sensenova_model_catalog,
    "opencode": opencode.get_opencode_model_catalog,
    "custom": custom_providers.get_custom_provider_model_catalog,
}[source]
print(json.dumps(get_catalog(json.loads(sys.stdin.read()))))
'''
    result = subprocess.run(
        [sys.executable, "-c", script, source],
        input=json.dumps(config), capture_output=True, text=True, encoding="utf-8",
        cwd=Path(__file__).resolve().parents[1], check=True, timeout=10,
    )
    reloaded = json.loads(result.stdout)

    assert model_ids(reloaded) == ["fresh-model"]
    assert reloaded[0]["context_length"] == 123456


def test_agnes_does_not_append_selected_model_absent_from_api(monkeypatch):
    monkeypatch.setattr(agnes, "fetch_agnes_model_catalog", lambda *args, **kwargs: [{"id": "agnes-next"}])
    config = {"api_key": "fixture-key", "selected_model_id": "agnes-3.0-flash"}

    assert model_ids(agnes.get_agnes_model_catalog(config)) == ["agnes-next"]


def test_sensenova_explicit_api_capabilities_override_builtin_guesses(monkeypatch):
    serve_models(monkeypatch, [{
        "id": "sensenova-6.8-flash-lite",
        "input_modalities": ["text"],
        "output_modalities": ["text"],
        "supported_features": [],
        "context_length": 123456,
        "max_output_length": 2048,
    }])
    config = {"api_key": "fixture-key", "selected_model_id": "sensenova-6.8-flash-lite"}
    model = sensenova.get_sensenova_model_catalog(config, fetch_live=True, force_refresh=True)[0]

    assert model["vision"] is False
    assert model["tool_calling"] is False
    assert model["thinking"] is False
    assert model["context_length"] == 123456
    assert model["max_output_tokens"] == 2048


def test_sensenova_runtime_uses_limits_from_current_api_inventory(monkeypatch):
    serve_models(monkeypatch, [{
        "id": "deepseek-v4-flash",
        "context_length": 123456,
        "max_output_length": 2048,
        "input_modalities": ["text"],
        "output_modalities": ["text"],
        "supported_features": ["tools"],
    }])
    config = {"api_key": "fixture-key", "selected_model_id": "deepseek-v4-flash"}
    sensenova.get_sensenova_model_catalog(config, fetch_live=True, force_refresh=True)

    runtime = sensenova.build_sensenova_runtime_model_data(config)
    assert runtime["max_context_tokens"] == 123456
    assert sensenova.normalize_sensenova_config(config)["max_tokens"] == 2048
