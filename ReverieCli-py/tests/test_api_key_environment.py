import json

import pytest

from reverie.config import Config, ConfigManager, ModelConfig
from reverie import desktop_catalog as desktop
from reverie.custom_providers import find_custom_provider, resolve_custom_provider_api_key


def test_standard_model_resolves_environment_without_persisting_secret(monkeypatch, tmp_path):
    monkeypatch.setenv("REVERIE_TEST_KEY", "test-env-secret")
    config = Config(models=[ModelConfig.from_dict({
        "model": "test-model", "model_display_name": "Test", "base_url": "http://localhost/v1",
        "api_key_env": "REVERIE_TEST_KEY",
    })])
    manager = ConfigManager(project_root=tmp_path)
    manager.save(config)
    loaded = manager.load()
    assert loaded.active_model.api_key == "test-env-secret"
    assert loaded.models[0].api_key == ""
    assert loaded.models[0].api_key_env == "REVERIE_TEST_KEY"
    assert "test-env-secret" not in json.dumps(loaded.to_dict())
    monkeypatch.setenv("REVERIE_TEST_KEY", "rotated-secret")
    assert loaded.active_model.api_key == "rotated-secret"
    monkeypatch.delenv("REVERIE_TEST_KEY")
    assert loaded.active_model.api_key == ""


def test_standard_desktop_switches_key_source_and_exposes_only_reference(monkeypatch):
    monkeypatch.setenv("REVERIE_TEST_KEY", "test-env-secret")
    config = Config(models=[ModelConfig("test-model", "Test", "http://localhost/v1", "old-key")])
    desktop.update_standard_model(config, 0, {"api_key_env": "REVERIE_TEST_KEY"})
    assert config.models[0].api_key == ""
    assert config.active_model.api_key == "test-env-secret"
    entry = desktop._standard_catalog(config)[0]
    assert entry["api_key_env"] == "REVERIE_TEST_KEY"
    assert entry["api_key_configured"] is True
    assert "test-env-secret" not in json.dumps(entry)
    desktop.update_standard_model(config, 0, {"api_key_env": "", "api_key": "new-key"})
    assert config.active_model.api_key == "new-key"


def test_custom_provider_accepts_reference_and_switches_existing_key(monkeypatch):
    monkeypatch.setenv("REVERIE_TEST_KEY", "test-env-secret")
    monkeypatch.setattr("reverie.custom_providers.fetch_custom_provider_models", lambda *a, **kw: [])
    config = Config()
    entry = desktop.create_custom_provider(config, {
        "name": "test-relay", "base_url": "http://localhost/v1", "format": "anthropic",
        "api_key_env": "REVERIE_TEST_KEY",
    })
    assert entry["api_key_env"] == "REVERIE_TEST_KEY"
    assert entry["api_key_source"] == "env"
    assert "test-env-secret" not in json.dumps(config.to_dict())
    desktop.update_custom_provider(config, "test-relay", {"api_key_env": "", "api_key": "manual-key"})
    desktop.update_custom_provider(config, "test-relay", {"api_key_env": "REVERIE_TEST_KEY"})
    record = find_custom_provider(config.custom_providers, "test-relay")
    assert record["api_key"] == ""
    assert resolve_custom_provider_api_key(record) == "test-env-secret"


@pytest.mark.parametrize("source", ["aihubmix", "agnes", "sensenova", "nvidia", "modelscope", "opencode"])
def test_builtin_providers_accept_named_environment(source, monkeypatch):
    import importlib
    module = importlib.import_module(f"reverie.{source}")
    monkeypatch.setenv("REVERIE_TEST_KEY", "test-env-secret")
    normalizer = getattr(module, f"normalize_{source}_config")
    resolver = getattr(module, f"resolve_{source}_api_key")
    normalized = normalizer({"api_key": "", "api_key_env": "REVERIE_TEST_KEY"})
    assert resolver(normalized) == "test-env-secret"
    assert resolver({**normalized, "api_key": "manual-key"}) == "manual-key"
    assert "api_key_env" in {item["key"] for item in desktop._PROVIDER_CONFIG_FIELDS[source]}


@pytest.mark.parametrize("name", ["$OPENAI_API_KEY", "%OPENAI_API_KEY%", "KEY WITH SPACES"])
def test_standard_model_rejects_invalid_environment_name(name):
    with pytest.raises(ValueError, match="environment variable"):
        desktop.add_standard_model(Config(), {
            "model": "test", "base_url": "http://localhost/v1", "api_key_env": name,
        })


def test_bridge_lists_credential_names_without_values(monkeypatch):
    from reverie.sdk_bridge import ReverieSdkBridge
    monkeypatch.setenv("REVERIE_TEST_KEY", "private-value")
    bridge = ReverieSdkBridge.__new__(ReverieSdkBridge)
    result = bridge.dispatch({"action": "listApiKeyEnvironmentVariables", "id": "test"})
    assert "REVERIE_TEST_KEY" in result["names"]
    assert "private-value" not in json.dumps(result)


@pytest.mark.parametrize("source", ["custom", "nvidia"])
def test_cli_provider_key_saves_environment_reference(source, monkeypatch, tmp_path):
    from rich.console import Console
    from reverie.cli.commands import CommandHandler
    from reverie.custom_providers import default_custom_provider, upsert_custom_provider
    monkeypatch.setenv("REVERIE_TEST_KEY", "test-env-secret")
    manager = ConfigManager(project_root=tmp_path)
    config = Config()
    if source == "custom":
        config.custom_providers = upsert_custom_provider(config.custom_providers, default_custom_provider(
            name="test-relay", base_url="http://localhost/v1", api_key="old-key"))
    manager.save(config)
    handler = CommandHandler(Console(record=True), {"config_manager": manager, "project_root": tmp_path})
    provider_name = "test-relay" if source == "custom" else "nvidia"
    handler.cmd_provider(f"{provider_name} key --env REVERIE_TEST_KEY")
    loaded = manager.load()
    record = find_custom_provider(loaded.custom_providers, "test-relay") if source == "custom" else loaded.nvidia
    assert record["api_key"] == ""
    assert record["api_key_env"] == "REVERIE_TEST_KEY"
    assert "test-env-secret" not in json.dumps(loaded.to_dict())


def test_cli_add_model_accepts_environment_reference(monkeypatch, tmp_path):
    from rich.console import Console
    from reverie.cli import commands
    manager = ConfigManager(project_root=tmp_path)
    manager.save(Config())
    answers = iter(["http://localhost/v1", "env:REVERIE_TEST_KEY", "test-model", "Test", "128000", "openai-chat"])
    monkeypatch.setattr(commands.Prompt, "ask", lambda *a, **kw: next(answers))
    monkeypatch.setattr(commands.Confirm, "ask", lambda *a, **kw: False)
    handler = commands.CommandHandler(Console(record=True), {"config_manager": manager})
    handler.cmd_add_model("")
    saved = manager.load().models[0]
    assert saved.api_key == ""
    assert saved.api_key_env == "REVERIE_TEST_KEY"


def test_cli_activation_preserves_environment_reference(monkeypatch):
    from rich.console import Console
    from reverie.cli.commands import CommandHandler
    monkeypatch.setenv("REVERIE_TEST_KEY", "test-env-secret")
    config = Config(aihubmix={"api_key": "", "api_key_env": "REVERIE_TEST_KEY"})
    handler = CommandHandler(Console(record=True), {})
    assert handler._ensure_aihubmix_configuration(config) is True
    assert config.aihubmix["api_key"] == ""
    assert config.aihubmix["api_key_env"] == "REVERIE_TEST_KEY"
