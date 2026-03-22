from types import SimpleNamespace

import requests

import reverie.qwencode as qwencode
from reverie.agent import agent as agent_module
from reverie.agent.agent import ReverieAgent


def _make_qwencode_agent(
    *,
    base_url: str = "https://proxy.example/v1/chat/completions",
    api_key: str = "cached-token",
    qwencode_cfg=None,
):
    agent = object.__new__(ReverieAgent)
    agent.provider = "request"
    agent.base_url = base_url
    agent.api_key = api_key
    agent.custom_headers = {}
    agent.api_timeout = 60
    agent.api_max_retries = 3
    agent.api_initial_backoff = 1.0
    agent.iflow_timeout = 1200
    agent.thinking_mode = None
    agent._openai_request_fallback_active = False
    agent.config = SimpleNamespace(
        active_model_source="qwencode",
        qwencode=qwencode_cfg
        or {
            "selected_model_id": "coder-model",
            "api_url": qwencode.QWENCODE_DEFAULT_API_URL,
            "endpoint": "",
            "timeout": 1200,
        },
    )
    return agent


def test_normalize_qwencode_config_accepts_legacy_proxy_keys():
    cfg = qwencode.normalize_qwencode_config(
        {
            "selected_model_id": "coder-model",
            "base_url": "https://proxy.example/v1",
            "customHeader": {"X-Proxy-Key": "secret"},
        }
    )

    assert cfg["api_url"] == "https://proxy.example/v1"
    assert cfg["custom_headers"] == {"X-Proxy-Key": "secret"}


def test_build_qwencode_runtime_model_data_prefers_explicit_custom_api_url(monkeypatch):
    monkeypatch.setattr(
        qwencode,
        "detect_qwencode_cli_credentials",
        lambda refresh_if_needed=True: {
            "found": True,
            "api_key": "oauth-token",
            "resource_url": "https://portal.qwen.ai",
        },
    )

    runtime = qwencode.build_qwencode_runtime_model_data(
        {
            "selected_model_id": "coder-model",
            "api_url": "https://proxy.example/v1",
            "endpoint": "",
        }
    )

    assert runtime is not None
    assert runtime["base_url"] == "https://proxy.example/v1/chat/completions"


def test_build_qwencode_runtime_model_data_uses_oauth_resource_url_by_default(monkeypatch):
    monkeypatch.setattr(
        qwencode,
        "detect_qwencode_cli_credentials",
        lambda refresh_if_needed=True: {
            "found": True,
            "api_key": "oauth-token",
            "resource_url": "https://portal.qwen.ai",
        },
    )

    runtime = qwencode.build_qwencode_runtime_model_data(
        {
            "selected_model_id": "coder-model",
            "api_url": qwencode.QWENCODE_DEFAULT_API_URL,
            "endpoint": "",
        }
    )

    assert runtime is not None
    assert runtime["base_url"] == "https://portal.qwen.ai/v1/chat/completions"


def test_qwencode_request_payload_defaults_apply_for_non_official_proxy_host():
    agent = _make_qwencode_agent()

    payload = ReverieAgent._prepare_request_payload(
        agent,
        {
            "model": "coder-model",
            "messages": [],
            "stream": True,
        },
        session_id="session-1",
    )

    assert payload["enable_thinking"] is True
    assert payload["stream_options"]["include_usage"] is True
    assert payload["metadata"]["sessionId"] == "session-1"


def test_qwencode_request_headers_refresh_credentials_and_timeout(monkeypatch):
    monkeypatch.setattr(
        qwencode,
        "detect_qwencode_cli_credentials",
        lambda refresh_if_needed=True, force_refresh=False: {
            "found": True,
            "api_key": "fresh-oauth-token",
            "resource_url": "https://portal.qwen.ai",
        },
    )

    agent = _make_qwencode_agent(api_key="")
    agent.custom_headers = {"X-Proxy-Key": "secret"}

    headers = ReverieAgent._build_request_headers(agent, stream=True)

    assert agent.api_key == "fresh-oauth-token"
    assert agent.base_url == "https://portal.qwen.ai/v1/chat/completions"
    assert headers["Authorization"] == "Bearer fresh-oauth-token"
    assert headers["X-DashScope-AuthType"] == "qwen-oauth"
    assert headers["X-Proxy-Key"] == "secret"
    assert ReverieAgent._resolve_provider_timeout(agent) == 1200


def test_qwencode_request_retries_once_after_401_with_forced_refresh(monkeypatch):
    detect_calls = []

    def fake_detect(refresh_if_needed=True, force_refresh=False):
        detect_calls.append(force_refresh)
        return {
            "found": True,
            "api_key": "oauth-token-2" if force_refresh else "oauth-token-1",
            "resource_url": "https://portal.qwen.ai",
        }

    monkeypatch.setattr(qwencode, "detect_qwencode_cli_credentials", fake_detect)

    request_calls = []

    def fake_make_api_request_with_retry(
        *,
        url,
        headers,
        payload,
        max_retries,
        initial_backoff,
        stream,
        timeout,
    ):
        request_calls.append((url, headers.get("Authorization")))
        if len(request_calls) == 1:
            response = SimpleNamespace(status_code=401)
            raise requests.exceptions.HTTPError("401 Unauthorized", response=response)
        return "ok"

    monkeypatch.setattr(agent_module, "make_api_request_with_retry", fake_make_api_request_with_retry)

    agent = _make_qwencode_agent(api_key="")
    headers = ReverieAgent._build_request_headers(agent, stream=False)

    result = ReverieAgent._make_request_with_provider_auth_retry(
        agent,
        headers=headers,
        payload={"model": "coder-model", "messages": []},
        stream=False,
        timeout=1200,
    )

    assert result == "ok"
    assert detect_calls == [False, True]
    assert request_calls == [
        ("https://portal.qwen.ai/v1/chat/completions", "Bearer oauth-token-1"),
        ("https://portal.qwen.ai/v1/chat/completions", "Bearer oauth-token-2"),
    ]
