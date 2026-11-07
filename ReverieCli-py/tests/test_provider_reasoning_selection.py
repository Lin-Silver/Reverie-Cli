"""The reasoning control must reflect the live catalog and saved selection."""

import json
from types import SimpleNamespace

import pytest

from reverie import opencode
from reverie.desktop_catalog import _reasoning_metadata
from reverie.opencode import get_opencode_model_metadata


@pytest.fixture(autouse=True)
def isolate_opencode_catalog(monkeypatch):
    monkeypatch.setattr(opencode, "_OPENCODE_MODEL_CACHE", {"key": "", "expires_at": 0.0, "models": []})


@pytest.mark.parametrize("model_id,choice", [
    ("deepseek-v4-flash-free", "high"),
    ("hy3-free", "medium"),
    ("laguna-s-2.1-free", "low"),
])
def test_opencode_picker_retains_saved_reasoning_depth(model_id, choice):
    model = get_opencode_model_metadata(model_id)
    assert model is not None
    actual = _reasoning_metadata("opencode", model, {"selected_model_id": model_id, "reasoning_effort": choice})
    assert choice in {option["id"] for option in actual["options"]}
    assert actual["value"] == choice


@pytest.fixture
def live_catalog(monkeypatch):
    def fetch(raw_model):
        monkeypatch.setattr(opencode.requests, "get", lambda *args, **kwargs: SimpleNamespace(
            raise_for_status=lambda: None,
            json=lambda: {"data": [raw_model]},
        ))
        config = {"api_url": "https://catalog.invalid/v1", "api_key": "fixture-key"}
        model = opencode.fetch_opencode_model_catalog(config, force_refresh=True)[0]
        return config, model

    return fetch


@pytest.mark.parametrize("model_id,efforts", [
    ("glm-5.3-flash-free", ["low", "high", "max"]),
    ("gpt-6.1-sol", ["low", "medium", "high", "xhigh", "max"]),
])
def test_live_opencode_reasoning_options_reach_the_picker(live_catalog, model_id, efforts):
    # Capability shape and values observed at /zen/v1/models on 2026-11-06.
    config, model = live_catalog({
        "id": model_id,
        "capabilities": {"reasoning": {"supported": True, "effort": efforts}},
    })

    actual = _reasoning_metadata("opencode", model, config)

    assert actual["control"] == "effort"
    assert [option["id"] for option in actual["options"]] == efforts


def test_live_opencode_reasoning_choice_survives_catalog_and_config_reload(live_catalog):
    config, model = live_catalog({
        "id": "glm-5.3-flash-free",
        "capabilities": {"reasoning": {"supported": True, "effort": ["low", "high", "max"]}},
    })

    selected = opencode.apply_opencode_thinking_choice(config, model["id"], "max")
    serialized = json.loads(json.dumps(selected))
    opencode._OPENCODE_MODEL_CACHE.update(key="", expires_at=0.0, models=[])
    reloaded = opencode.normalize_opencode_config(serialized)
    current = opencode.resolve_opencode_selected_model(reloaded)
    actual = _reasoning_metadata("opencode", current, reloaded)

    assert reloaded["selected_model_id"] == model["id"]
    assert reloaded["reasoning_effort"] == "max"
    assert actual["value"] == "max"
    assert "max" in {option["id"] for option in actual["options"]}


def test_big_pickle_does_not_invent_depths_absent_from_official_capabilities(live_catalog):
    config, model = live_catalog({
        "id": "big-pickle",
        "capabilities": {"reasoning": {"supported": True}, "effort_updates": False},
    })

    actual = _reasoning_metadata("opencode", model, config)

    assert actual["control"] == "fixed"
    assert actual["options"] == []


def test_custom_provider_selection_saves_depth_with_first_context_confirmation():
    from reverie.config import Config
    from reverie.custom_providers import default_custom_provider
    from reverie.desktop_catalog import select_custom_provider_model
    provider = default_custom_provider(provider_id='relay', name='Relay', base_url='https://relay.invalid/v1', api_key='fixture-key')
    provider['models'] = [{'id': 'reasoning-model', 'reasoning': True, 'context_length': 128000}]
    config = Config(custom_providers={'providers': [provider], 'active_provider_id': 'relay'})
    select_custom_provider_model(config, 'relay', 'reasoning-model', 96000, reasoning='low')
    saved = config.custom_providers['providers'][0]
    assert saved['reasoning_effort'] == 'low'
    assert saved['thinking'] is True
    assert saved['model_context_limits']['reasoning-model'] == 96000
