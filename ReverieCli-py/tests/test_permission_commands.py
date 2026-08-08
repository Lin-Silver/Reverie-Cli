"""Coverage for the /permission command family.

These tests drive the real CommandHandler against a real ConfigManager so the
persisted security block is asserted, not just the rendered console output.
"""

from pathlib import Path

import pytest
from rich.console import Console

from reverie.cli.commands import CommandHandler
from reverie.config import ConfigManager, ModelConfig
from reverie.security_policy import normalize_security_config


@pytest.fixture(autouse=True)
def _isolated_app_root(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Keep ConfigManager writes inside tmp_path.

    Without this the manager resolves the real `<app_root>/.reverie/config.json`
    and these tests would overwrite the developer's own settings and models.
    """
    monkeypatch.setenv("REVERIE_APP_ROOT", str(tmp_path / "app"))


def _model(name: str, base_url: str, api_key: str) -> ModelConfig:
    return ModelConfig.from_dict(
        {"model": name, "provider": "openai-chat", "base_url": base_url, "api_key": api_key}
    )


def _handler(tmp_path: Path) -> tuple[CommandHandler, Console, ConfigManager, list[str]]:
    config_path = tmp_path / "config.json"
    config_manager = ConfigManager(config_path)
    config_manager.save(config_manager.load())
    console = Console(record=True, width=200, no_color=True, legacy_windows=False)
    reinits: list[str] = []
    handler = CommandHandler(
        console,
        {
            "project_root": tmp_path,
            "config_manager": config_manager,
            "reinit_agent": lambda: reinits.append("reinit"),
        },
    )
    return handler, console, config_manager, reinits


def _security(config_manager: ConfigManager) -> dict:
    return normalize_security_config(getattr(config_manager.load(), "security", {}) or {})


def test_permission_status_renders_without_a_configured_agent(tmp_path: Path) -> None:
    handler, console, _config_manager, _reinits = _handler(tmp_path)

    assert handler.handle("/permission") is True

    rendered = console.export_text()
    assert "Default" in rendered or "default" in rendered


def test_permission_mode_persists_each_canonical_mode(tmp_path: Path) -> None:
    handler, _console, config_manager, reinits = _handler(tmp_path)

    for spelling, expected in (
        ("auto_check", "auto_check"),
        ("strict", "strict"),
        ("default", "default"),
    ):
        assert handler.handle(f"/permission mode {spelling}") is True
        assert _security(config_manager)["permission_mode"] == expected

    assert len(reinits) == 3


def test_permission_mode_accepts_friendly_aliases(tmp_path: Path) -> None:
    handler, _console, config_manager, _reinits = _handler(tmp_path)

    assert handler.handle("/permission mode auto") is True
    assert _security(config_manager)["permission_mode"] == "auto_check"

    assert handler.handle("/permission mode always_ask") is True
    assert _security(config_manager)["permission_mode"] == "strict"

    assert handler.handle("/permission mode builtin") is True
    assert _security(config_manager)["permission_mode"] == "default"


def test_permission_mode_rejects_an_unknown_mode_without_saving(tmp_path: Path) -> None:
    handler, console, config_manager, reinits = _handler(tmp_path)

    assert handler.handle("/permission mode paranoid") is True

    assert _security(config_manager)["permission_mode"] == "default"
    assert reinits == []
    assert "Unknown mode" in console.export_text()


def test_permission_threshold_persists_and_validates(tmp_path: Path) -> None:
    handler, console, config_manager, _reinits = _handler(tmp_path)

    assert handler.handle("/permission threshold high") is True
    assert _security(config_manager)["review"]["approve_risk_at"] == "high"

    assert handler.handle("/permission risk low") is True
    assert _security(config_manager)["review"]["approve_risk_at"] == "low"

    assert handler.handle("/permission threshold spicy") is True
    assert _security(config_manager)["review"]["approve_risk_at"] == "low"
    assert "Unknown risk level" in console.export_text()


def test_permission_model_follow_clears_any_pinned_reviewer(tmp_path: Path) -> None:
    handler, _console, config_manager, _reinits = _handler(tmp_path)

    assert handler.handle("/permission model nvidia reviewer-mini") is True
    review = _security(config_manager)["review"]
    assert review["model_mode"] == "custom"
    assert review["source"] == "nvidia"
    assert review["model"] == "reviewer-mini"

    assert handler.handle("/permission model follow") is True
    review = _security(config_manager)["review"]
    assert review["model_mode"] == "follow"
    assert review["source"] == ""
    assert review["model"] == ""


def test_permission_model_pins_a_standard_model_by_name_and_index(tmp_path: Path) -> None:
    handler, _console, config_manager, _reinits = _handler(tmp_path)
    config = config_manager.load()
    config.models = [
        _model("main-model", "https://a/v1", "k1"),
        _model("cheap-reviewer", "https://b/v1", "k2"),
    ]
    config_manager.save(config)

    assert handler.handle("/permission model standard cheap-reviewer") is True
    review = _security(config_manager)["review"]
    assert review["source"] == "standard"
    assert review["model"] == "cheap-reviewer"
    assert review["model_index"] == 1

    assert handler.handle("/permission model standard 0") is True
    review = _security(config_manager)["review"]
    assert review["model"] == "main-model"
    assert review["model_index"] == 0


def test_permission_model_reports_an_unmatched_standard_model(tmp_path: Path) -> None:
    handler, console, config_manager, _reinits = _handler(tmp_path)
    config = config_manager.load()
    config.models = [_model("main-model", "https://a/v1", "k")]
    config_manager.save(config)

    assert handler.handle("/permission model standard nope") is True

    assert _security(config_manager)["review"]["model_mode"] == "follow"
    assert "No standard model matches" in console.export_text()


def test_permission_reviewer_integers_clamp_to_their_documented_range(tmp_path: Path) -> None:
    handler, console, config_manager, _reinits = _handler(tmp_path)

    assert handler.handle("/permission timeout 45") is True
    assert _security(config_manager)["review"]["timeout"] == 45

    assert handler.handle("/permission timeout 4") is True
    assert _security(config_manager)["review"]["timeout"] == 45

    assert handler.handle("/permission max-tokens 1024") is True
    assert _security(config_manager)["review"]["max_tokens"] == 1024

    assert handler.handle("/permission max-tokens abc") is True
    assert _security(config_manager)["review"]["max_tokens"] == 1024

    rendered = console.export_text()
    assert "must be between" in rendered
    assert "must be an integer" in rendered


def test_permission_reviewer_toggles_persist(tmp_path: Path) -> None:
    handler, _console, config_manager, _reinits = _handler(tmp_path)

    assert handler.handle("/permission fail-open on") is True
    assert _security(config_manager)["review"]["fail_open"] is True

    assert handler.handle("/permission fail-open off") is True
    assert _security(config_manager)["review"]["fail_open"] is False

    assert handler.handle("/permission review-read-only on") is True
    assert _security(config_manager)["review"]["review_read_only"] is True

    assert handler.handle("/permission readonly off") is True
    assert _security(config_manager)["strict_allow_read_only"] is False


def test_permission_level_changes_the_hard_ceiling(tmp_path: Path) -> None:
    handler, _console, config_manager, _reinits = _handler(tmp_path)

    assert handler.handle("/permission level read_only") is True
    assert _security(config_manager)["permission_level"] == "read_only"


def test_permission_rejects_an_unknown_subcommand_and_prints_usage(tmp_path: Path) -> None:
    handler, console, _config_manager, reinits = _handler(tmp_path)

    assert handler.handle("/permission frobnicate") is True

    rendered = console.export_text()
    assert "Unknown /permission subcommand" in rendered
    assert "/permission mode" in rendered
    assert reinits == []
