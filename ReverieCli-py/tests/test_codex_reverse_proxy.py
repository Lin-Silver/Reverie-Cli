from __future__ import annotations

import json

import pytest
from rich.console import Console

from reverie import codex
from reverie.cli.commands import CommandHandler
from reverie.config import ConfigManager


@pytest.mark.parametrize(
    ("base_url", "endpoint", "expected"),
    [
        ("https://proxy.example/v1", "", "https://proxy.example/v1/responses"),
        ("https://proxy.example/v1/models", "", "https://proxy.example/v1/responses"),
        ("https://proxy.example/v1/responses?tenant=a", "", "https://proxy.example/v1/responses?tenant=a"),
        ("https://proxy.example/v1?tenant=a", "responses", "https://proxy.example/v1/responses?tenant=a"),
        ("https://proxy.example/root", "https://edge.example/openai/responses?key=x", "https://edge.example/openai/responses?key=x"),
    ],
)
def test_resolve_codex_request_url_handles_proxy_roots_and_full_endpoints(
    base_url: str, endpoint: str, expected: str
) -> None:
    assert codex.resolve_codex_request_url(base_url, endpoint) == expected


def test_proxy_headers_do_not_leak_chatgpt_identity() -> None:
    headers = codex.get_codex_request_headers(
        "proxy-secret",
        account_id="chatgpt-account",
        auth_mode="codex",
        request_url="https://proxy.example/v1/responses",
    )

    assert headers["Authorization"] == "Bearer proxy-secret"
    assert headers["User-Agent"].startswith("Reverie/")
    assert "Originator" not in headers
    assert "Chatgpt-Account-Id" not in headers
    assert "Version" not in headers
    assert "Session_id" not in headers


def test_official_headers_keep_codex_identity(monkeypatch) -> None:
    monkeypatch.setattr(codex, "get_codex_user_agent", lambda: "codex-compatible-agent")
    headers = codex.get_codex_request_headers(
        "codex-token",
        account_id="account-123",
        auth_mode="codex",
        request_url="https://chatgpt.com/backend-api/codex/responses",
    )

    assert headers["User-Agent"] == "codex-compatible-agent"
    assert headers["Originator"] == "codex_cli_rs"
    assert headers["Chatgpt-Account-Id"] == "account-123"


def test_proxy_custom_headers_override_defaults_case_insensitively() -> None:
    headers = codex.get_codex_request_headers(
        "secret",
        request_url="https://proxy.example/responses",
        extra_headers={"authorization": "Token custom", "X-Tenant": "demo"},
    )

    assert "Authorization" not in headers
    assert headers["authorization"] == "Token custom"
    assert headers["X-Tenant"] == "demo"


def test_reverse_proxy_credentials_prefer_configured_environment_key(monkeypatch) -> None:
    monkeypatch.setattr(codex, "get_codex_model_catalog", lambda: [])
    monkeypatch.setattr(codex, "detect_codex_cli_credentials", lambda: {"found": True, "api_key": "local-token", "errors": []})
    monkeypatch.setenv("MY_CODEX_PROXY_KEY", "proxy-token")

    credentials = codex.resolve_codex_credentials(
        {
            "api_url": "https://proxy.example/v1",
            "auth_mode": "auto",
            "api_key_env": "MY_CODEX_PROXY_KEY",
        }
    )

    assert credentials["api_key"] == "proxy-token"
    assert credentials["auth_mode"] == "api_key"
    assert credentials["source"] == "env:MY_CODEX_PROXY_KEY"
    assert credentials["account_id"] == ""


def test_reverse_proxy_can_explicitly_disable_auth(monkeypatch) -> None:
    monkeypatch.setattr(codex, "get_codex_model_catalog", lambda: [])
    monkeypatch.setattr(codex, "detect_codex_cli_credentials", lambda: {"found": False, "errors": []})

    credentials = codex.resolve_codex_credentials(
        {"api_url": "http://127.0.0.1:8080/v1", "auth_mode": "none"}
    )

    assert credentials["found"] is True
    assert credentials["api_key"] == ""
    assert credentials["source"] == "anonymous"


def test_custom_proxy_model_id_survives_normalization(monkeypatch) -> None:
    monkeypatch.setattr(codex, "get_codex_model_catalog", lambda: [])
    config = codex.normalize_codex_config(
        {
            "api_url": "https://proxy.example/v1",
            "selected_model_id": "vendor/codex-latest",
            "custom_headers": {"X-Tenant": "demo", "": "ignored"},
        }
    )

    assert config["selected_model_id"] == "vendor/codex-latest"
    assert config["selected_model_display_name"] == "vendor/codex-latest"
    assert config["custom_headers"] == {"X-Tenant": "demo"}


def test_live_codex_cache_is_not_filtered_by_stale_source(monkeypatch, tmp_path) -> None:
    cache_path = tmp_path / "models_cache.json"
    cache_path.write_text(
        json.dumps(
            {
                "client_version": "0.145.0",
                "models": [
                    {
                        "slug": "gpt-6-proxy-preview",
                        "display_name": "GPT-6 Proxy Preview",
                        "description": "New cache-only model",
                        "supported_in_api": True,
                        "context_window": 200000,
                        "effective_context_window_percent": 90,
                        "supported_reasoning_levels": [{"effort": "medium"}, {"effort": "high"}],
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(codex, "_models_cache_path", lambda: cache_path)
    monkeypatch.setattr(
        codex,
        "_load_local_codex_source_catalog",
        lambda errors: [{"id": "gpt-stale", "display_name": "Stale"}],
    )

    catalog = codex.get_codex_model_catalog()

    assert [item["id"] for item in catalog] == ["gpt-6-proxy-preview"]
    assert catalog[0]["context_length"] == 180000
    assert codex.get_codex_client_version() == "0.145.0"


def test_codex_payload_preserves_function_strict_mode(monkeypatch) -> None:
    monkeypatch.setattr(codex, "get_codex_model_catalog", lambda: [])
    payload = codex.build_codex_request_payload(
        "proxy-model",
        [{"role": "user", "content": "hello"}],
        tools=[
            {
                "type": "function",
                "function": {
                    "name": "lookup",
                    "description": "Lookup data",
                    "parameters": {"type": "object", "properties": {}},
                    "strict": True,
                },
            }
        ],
    )

    assert payload["tools"][0]["strict"] is True


def test_codex_sse_failure_becomes_explicit_error_event() -> None:
    events, _ = codex.parse_codex_sse_event(
        json.dumps({"type": "response.failed", "response": {"error": {"message": "upstream failed"}}})
    )

    assert events == [{"type": "error", "message": "upstream failed"}]


def test_codex_model_command_accepts_proxy_only_model_id(monkeypatch, tmp_path) -> None:
    app_root = tmp_path / "app"
    project_root = tmp_path / "project"
    project_root.mkdir()
    monkeypatch.setattr("reverie.config.get_app_root", lambda: app_root)
    monkeypatch.setattr("reverie.config.get_launcher_root", lambda: app_root)
    monkeypatch.setattr(codex, "get_codex_model_catalog", lambda: [])
    monkeypatch.setattr(codex, "detect_codex_cli_credentials", lambda: {"found": False, "errors": []})

    manager = ConfigManager(project_root)
    config = manager.load()
    config.codex = codex.normalize_codex_config(
        {
            "api_url": "http://127.0.0.1:8080/v1",
            "auth_mode": "none",
        }
    )
    manager.save(config)
    handler = CommandHandler(
        Console(record=True, force_terminal=False, width=120),
        {"config_manager": manager, "project_root": project_root},
    )

    assert handler._cmd_codex_model("vendor/codex-latest") is True
    saved = manager.load()
    assert saved.active_model_source == "codex"
    assert saved.codex["selected_model_id"] == "vendor/codex-latest"
