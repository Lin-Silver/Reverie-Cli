from rich.console import Console

from reverie.agent.agent import ReverieAgent
from reverie.cli.commands import CommandHandler
from reverie.cli.help_catalog import HELP_TOPICS, normalize_help_topic
from reverie.config import Config, ConfigManager
from reverie.opencode import (
    apply_opencode_thinking_choice,
    build_opencode_openai_options,
    build_opencode_request_headers,
    build_opencode_request_headers_from_config,
    build_opencode_runtime_model_data,
    fetch_opencode_model_catalog,
    get_opencode_model_catalog,
    normalize_opencode_config,
    resolve_opencode_client_identity,
    resolve_opencode_thinking_choice,
    resolve_opencode_request_url,
    resolve_opencode_sdk_base_url,
)


def test_opencode_catalog_matches_live_free_models_and_capabilities() -> None:
    catalog = {item["id"]: item for item in get_opencode_model_catalog()}

    assert set(catalog) == {
        "big-pickle",
        "deepseek-v4-flash-free",
        "mimo-v2.5-free",
        "muse-spark-1.3-contributor-free",
        "muse-spark-1.2-contributor-free",
        "hy3-free",
        "nemotron-3-ultra-free",
        "nemotron-3.5-lightning-free",
        "ling-3.0-flash-fin-free",
        "laguna-s-2.1-free",
    }
    assert catalog["mimo-v2.5-free"]["vision"] is True
    assert catalog["mimo-v2.5-free"]["vision_modalities"] == ["image", "audio", "video"]
    assert catalog["muse-spark-1.3-contributor-free"]["transport"] == "openai-responses"
    assert catalog["muse-spark-1.3-contributor-free"]["endpoint"] == "/responses"
    assert catalog["muse-spark-1.3-contributor-free"]["context_length"] == 1_000_000
    assert [item["id"] for item in catalog["deepseek-v4-flash-free"]["thinking_options"]] == [
        "low",
        "high",
        "max",
    ]
    assert [item["id"] for item in catalog["hy3-free"]["thinking_options"]] == ["low", "medium", "high"]
    assert [item["id"] for item in catalog["laguna-s-2.1-free"]["thinking_options"]] == ["low", "medium", "high"]


def test_opencode_live_catalog_keeps_every_api_model_and_known_transport(monkeypatch) -> None:
    from reverie import opencode as opencode_module

    captured = []

    class FakeResponse:
        def raise_for_status(self):
            return None

        def json(self):
            return {
                "data": [
                    {"id": "big-pickle"},
                    {"id": "hy3-free"},
                    {"id": "muse-spark-1.3-contributor-free"},
                    {"id": "muse-spark-1.2-contributor-free"},
                    {"id": "muse-spark-1.3"},
                    {"id": "deepseek-v4-pro"},
                    {"id": "gpt-5.6-sol"},
                    {"id": "claude-fable-5"},
                ]
            }

    def fake_get(url, *, headers, timeout, **kwargs):
        captured.append({"url": url, "headers": dict(headers), "timeout": timeout})
        return FakeResponse()

    monkeypatch.setattr(opencode_module.requests, "get", fake_get)

    anonymous = fetch_opencode_model_catalog({}, force_refresh=True)
    keyed = fetch_opencode_model_catalog({"api_key": "zen-test"}, force_refresh=True)

    expected_ids = [
        "big-pickle",
        "hy3-free",
        "muse-spark-1.3-contributor-free",
        "muse-spark-1.2-contributor-free",
        "muse-spark-1.3",
        "deepseek-v4-pro",
        "gpt-5.6-sol",
        "claude-fable-5",
    ]
    assert [item["id"] for item in anonymous] == expected_ids
    assert [item["id"] for item in keyed] == expected_ids
    assert captured[0]["url"] == "https://opencode.ai/zen/v1/models"
    assert "Authorization" not in captured[0]["headers"]
    assert captured[1]["headers"]["Authorization"] == "Bearer zen-test"
    assert all(item["catalog_source"] == "api" for item in keyed)
    assert next(item for item in keyed if item["id"] == "muse-spark-1.3")["endpoint"] == "/responses"
    unknown = next(item for item in keyed if item["id"] == "claude-fable-5")
    assert unknown["display_name"] == "claude-fable-5"
    assert unknown["transport"] == "anthropic"
    assert unknown["endpoint"] == "/messages"
    gpt = next(item for item in keyed if item["id"] == "gpt-5.6-sol")
    assert gpt["transport"] == "openai-responses"
    assert gpt["endpoint"] == "/responses"


def test_opencode_builtin_catalog_switch_uses_only_the_dedicated_list(monkeypatch) -> None:
    from reverie import opencode as opencode_module

    def fail_get(*args, **kwargs):
        raise AssertionError("built-in catalog mode must not call /models")

    monkeypatch.setattr(opencode_module.requests, "get", fail_get)
    config = normalize_opencode_config({"use_builtin_model_catalog": True, "api_key": "zen-test"})

    assert config["use_builtin_model_catalog"] is True
    catalog = get_opencode_model_catalog(config, fetch_live=True, force_refresh=True)
    assert {item["id"] for item in catalog} == {
        item["id"] for item in opencode_module._OPENCODE_MODEL_CATALOG
    }
    assert all(item.get("catalog_source") != "api" for item in catalog)


def test_opencode_keyed_fallback_catalog_includes_chat_and_responses_models() -> None:
    catalog = {item["id"]: item for item in get_opencode_model_catalog({"api_key": "zen-test"})}

    assert {"deepseek-v4-pro", "minimax-m3", "glm-5.2", "kimi-k3"} <= set(catalog)
    assert catalog["muse-spark-1.3"]["transport"] == "openai-responses"
    assert catalog["muse-spark-1.3"]["endpoint"] == "/responses"
    assert not {"gpt-5.6-sol", "claude-fable-5", "gemini-3.6-flash"} & set(catalog)
    assert catalog["deepseek-v4-pro"]["free"] is False


def test_opencode_paid_selection_falls_back_when_key_is_removed() -> None:
    anonymous = normalize_opencode_config({"selected_model_id": "deepseek-v4-pro", "api_key": ""})
    keyed = normalize_opencode_config({"selected_model_id": "deepseek-v4-pro", "api_key": "zen-test"})

    assert anonymous["selected_model_id"] == "deepseek-v4-flash-free"
    assert keyed["selected_model_id"] == "deepseek-v4-pro"


def test_opencode_base_url_normalizes_chat_completion_urls() -> None:
    assert resolve_opencode_sdk_base_url("opencode.ai/zen/v1/chat/completions") == "https://opencode.ai/zen/v1"
    assert resolve_opencode_sdk_base_url("https://opencode.ai/zen") == "https://opencode.ai/zen/v1"


def test_opencode_runtime_model_data_supports_anonymous_free_models() -> None:
    runtime = build_opencode_runtime_model_data(
        {
            "selected_model_id": "deepseek-v4-flash-free",
            "api_url": "https://opencode.ai/zen/v1/chat/completions",
        }
    )

    assert runtime is not None
    assert runtime["model"] == "deepseek-v4-flash-free"
    assert runtime["model_display_name"] == "DeepSeek V4 Flash Free"
    assert runtime["provider"] == "openai-chat"
    assert runtime["base_url"] == "https://opencode.ai/zen/v1"
    assert runtime["endpoint"] == "/chat/completions"
    assert runtime["api_key"] == ""


def test_opencode_runtime_model_data_routes_muse_spark_through_responses() -> None:
    runtime = build_opencode_runtime_model_data({"selected_model_id": "muse-spark-1.3-contributor-free"})

    assert runtime is not None
    assert runtime["model"] == "muse-spark-1.3-contributor-free"
    assert runtime["provider"] == "openai-responses"
    assert runtime["endpoint"] == "/responses"


def test_opencode_runtime_model_data_preserves_a_live_only_model() -> None:
    runtime = build_opencode_runtime_model_data(
        {"selected_model_id": "claude-fable-5", "api_key": "zen-test"}
    )

    assert runtime is not None
    assert runtime["model"] == "claude-fable-5"
    assert runtime["model_display_name"] == "claude-fable-5"
    assert runtime["provider"] == "anthropic"
    assert runtime["endpoint"] == "/messages"


def test_config_active_model_resolves_opencode_without_key() -> None:
    config = Config(
        active_model_source="opencode",
        opencode=normalize_opencode_config({"selected_model_id": "laguna-s-2.1-free"}),
    )

    active = config.active_model

    assert active is not None
    assert active.model == "laguna-s-2.1-free"
    assert active.model_display_name == "Laguna S 2.1 Free"
    assert active.provider == "openai-chat"
    assert active.endpoint == "/chat/completions"


def test_opencode_openai_options_match_provider_defaults() -> None:
    options = build_opencode_openai_options({"selected_model_id": "big-pickle"})

    assert options == {
        "temperature": 0.7,
        "top_p": 1.0,
        "max_tokens": 16384,
    }


def test_opencode_reasoning_choice_is_model_specific_and_sent_to_gateway() -> None:
    cfg = apply_opencode_thinking_choice(
        {"selected_model_id": "deepseek-v4-flash-free"},
        "deepseek-v4-flash-free",
        "max",
    )
    assert resolve_opencode_thinking_choice(cfg) == "max"
    assert build_opencode_openai_options(cfg)["extra_body"] == {"reasoning_effort": "max"}

    hy3 = normalize_opencode_config({"selected_model_id": "hy3-free"})
    assert resolve_opencode_thinking_choice(hy3) == "high"


def test_opencode_activate_does_not_require_a_key(tmp_path, monkeypatch) -> None:
    app_root = tmp_path / "app"
    project_root = tmp_path / "project"
    project_root.mkdir(parents=True, exist_ok=True)

    monkeypatch.setattr("reverie.config.get_app_root", lambda: app_root)
    monkeypatch.setattr("reverie.config.get_launcher_root", lambda: app_root)

    config_manager = ConfigManager(project_root)
    handler = CommandHandler(
        Console(record=True, force_terminal=False, width=120),
        {"config_manager": config_manager, "project_root": project_root},
    )

    assert handler.cmd_opencode("activate") is True

    reloaded = config_manager.load()
    active = reloaded.active_model
    assert reloaded.active_model_source == "opencode"
    assert reloaded.opencode["api_key"] == ""
    assert active is not None
    assert active.model == "deepseek-v4-flash-free"


def test_opencode_request_url_uses_chat_completions_path() -> None:
    assert resolve_opencode_request_url("https://opencode.ai/zen/v1", "") == "https://opencode.ai/zen/v1/chat/completions"
    assert resolve_opencode_request_url("https://opencode.ai/zen/v1", "/responses") == "https://opencode.ai/zen/v1/responses"


def test_opencode_reverse_proxy_url_preserves_query_string() -> None:
    # A proxy that carries auth in the query must not be mangled: the path
    # normalization has to leave the query in place at the end of the URL.
    proxy = "https://proxy.example.com/zen/v1?key=abc123"
    assert resolve_opencode_sdk_base_url(proxy) == "https://proxy.example.com/zen/v1?key=abc123"
    assert (
        resolve_opencode_request_url(proxy, "")
        == "https://proxy.example.com/zen/v1/chat/completions?key=abc123"
    )
    # A proxy that also spells out the chat path keeps the query after the path.
    spelled = "https://proxy.example.com/relay/opencode/v1/chat/completions?token=xyz"
    assert resolve_opencode_sdk_base_url(spelled) == "https://proxy.example.com/relay/opencode/v1?token=xyz"
    assert (
        resolve_opencode_request_url(spelled, "/responses")
        == "https://proxy.example.com/relay/opencode/v1/responses?token=xyz"
    )


def test_opencode_reverse_proxy_url_survives_config_normalization() -> None:
    cfg = normalize_opencode_config({"api_url": "https://proxy.example.com/zen/v1?key=abc123"})
    assert cfg["api_url"] == "https://proxy.example.com/zen/v1?key=abc123"


def test_opencode_catalog_uses_explicit_proxy(monkeypatch) -> None:
    from reverie import opencode as opencode_module

    captured = {}

    class FakeResponse:
        def raise_for_status(self):
            return None

        def json(self):
            return {"data": [{"id": "muse-spark-1.3-contributor-free"}]}

    def fake_get(url, *, headers, timeout, **kwargs):
        captured.update(url=url, headers=dict(headers), timeout=timeout, kwargs=kwargs)
        return FakeResponse()

    monkeypatch.setattr(opencode_module.requests, "get", fake_get)
    models = fetch_opencode_model_catalog({}, force_refresh=True, proxy="127.0.0.1:7890")

    assert [item["id"] for item in models] == ["muse-spark-1.3-contributor-free"]
    assert captured["kwargs"]["proxies"] == {
        "http": "http://127.0.0.1:7890",
        "https": "http://127.0.0.1:7890",
    }


def test_request_headers_omit_authorization_when_api_key_is_empty(tmp_path) -> None:
    config = Config(active_model_source="opencode")
    agent = ReverieAgent(
        base_url="https://opencode.ai/zen/v1",
        api_key="",
        model="big-pickle",
        project_root=tmp_path,
        provider="request",
        config=config,
    )

    headers = agent._build_request_headers(stream=False)

    assert "Authorization" not in headers
    assert headers["Content-Type"] == "application/json"
    assert headers["Accept"] == "application/json"
    assert headers["x-opencode-session"].startswith("ses_")
    assert len(headers["x-opencode-session"]) == 68
    assert headers["x-opencode-request"].startswith("msg_")
    assert headers["x-opencode-client"] == "reverie-cli"
    assert headers["User-Agent"].startswith("Reverie-Cli/")


def test_opencode_request_headers_keep_provider_shape_without_account_identity() -> None:
    headers = build_opencode_request_headers(
        "local-session",
        request_id="msg_0123456789abcdef0123456789abcdef",
        project_id="project-1",
    )

    assert headers["x-opencode-session"].startswith("ses_")
    assert len(headers["x-opencode-session"]) == 68
    assert headers["x-opencode-request"] == "msg_0123456789abcdef0123456789abcdef"
    assert headers["x-opencode-project"] == "project-1"
    assert headers["x-opencode-client"] == "reverie-cli"


def test_opencode_client_identity_defaults_to_reverie() -> None:
    identity = resolve_opencode_client_identity({})
    assert identity["client_name"] == "reverie-cli"
    assert identity["user_agent"].startswith("Reverie-Cli/")


def test_opencode_client_identity_can_mimic_official_client() -> None:
    # A non-OpenCode client reaching the free models through a strict proxy can
    # borrow the official client's identity so the proxy forwards the request.
    cfg = normalize_opencode_config(
        {"client_name": "opencode", "user_agent": "opencode/0.5.1"}
    )
    identity = resolve_opencode_client_identity(cfg)
    assert identity["client_name"] == "opencode"
    assert identity["user_agent"] == "opencode/0.5.1"

    headers = build_opencode_request_headers_from_config(cfg, "local-session")
    assert headers["x-opencode-client"] == "opencode"
    assert headers["User-Agent"] == "opencode/0.5.1"
    # The rest of the provider shape is untouched.
    assert headers["x-opencode-session"].startswith("ses_")
    assert headers["x-opencode-request"].startswith("msg_")


def test_opencode_agent_headers_honor_configured_identity(tmp_path) -> None:
    config = Config(
        active_model_source="opencode",
        opencode=normalize_opencode_config(
            {"client_name": "opencode", "user_agent": "opencode/0.5.1"}
        ),
    )
    agent = ReverieAgent(
        base_url="https://opencode.ai/zen/v1",
        api_key="",
        model="big-pickle",
        project_root=tmp_path,
        provider="request",
        config=config,
    )

    headers = agent._build_request_headers(stream=False)

    assert headers["x-opencode-client"] == "opencode"
    assert headers["User-Agent"] == "opencode/0.5.1"


def test_opencode_request_headers_suppress_reverie_identity(tmp_path) -> None:
    # OpenCode's gateway must see only the (spoofable) official client identity;
    # leaking Reverie's own X-Reverie-Client header would give the client away.
    from reverie.request_identity import REVERIE_CLIENT_HEADER

    config = Config(active_model_source="opencode")
    agent = ReverieAgent(
        base_url="https://opencode.ai/zen/v1",
        api_key="",
        model="big-pickle",
        project_root=tmp_path,
        provider="request",
        config=config,
    )

    headers = agent._build_request_headers(stream=False)

    assert REVERIE_CLIENT_HEADER not in headers
    assert headers["x-opencode-client"] == "reverie-cli"


def test_opencode_free_tier_gate_error_is_humanized(tmp_path) -> None:
    # The gateway refuses anonymous free-tier calls with a raw 403; the agent
    # must translate that into actionable guidance rather than leaking the
    # traceback, and only for the OpenCode source.
    import requests

    raw = requests.exceptions.HTTPError(
        "403 Client Error: Forbidden for url: https://opencode.ai/zen/v1/responses "
        "| Provider said: OpenCode's free tier can only be used from within OpenCode"
    )

    config = Config(active_model_source="opencode")
    agent = ReverieAgent(
        base_url="https://opencode.ai/zen/v1",
        api_key="",
        model="muse-spark-1.3-contributor-free",
        project_root=tmp_path,
        provider="openai-responses",
        endpoint="/responses",
        config=config,
    )

    message = agent._humanize_turn_error(raw)
    assert message is not None
    assert "gated server-side" in message
    assert "/opencode key" in message
    # A configured key produces the key-specific variant instead.
    keyed = ReverieAgent(
        base_url="https://opencode.ai/zen/v1",
        api_key="sk-real-key",
        model="muse-spark-1.3-contributor-free",
        project_root=tmp_path,
        provider="openai-responses",
        endpoint="/responses",
        config=config,
    )
    keyed_message = keyed._humanize_turn_error(raw)
    assert keyed_message is not None
    assert "configured API key" in keyed_message


def test_free_tier_gate_error_left_alone_for_other_sources(tmp_path) -> None:
    import requests

    raw = requests.exceptions.HTTPError(
        "403 ... OpenCode's free tier can only be used from within OpenCode"
    )
    config = Config(active_model_source="custom")
    agent = ReverieAgent(
        base_url="https://api.example.com/v1",
        api_key="",
        model="some-model",
        project_root=tmp_path,
        provider="request",
        config=config,
    )
    # Not the OpenCode source, and an unrelated error, both pass through.
    assert agent._humanize_turn_error(raw) is None
    assert agent._humanize_turn_error(ValueError("boom")) is None


def test_non_opencode_request_headers_keep_reverie_identity(tmp_path) -> None:
    # Every other source keeps Reverie's real client identity.
    from reverie.request_identity import REVERIE_CLIENT_HEADER, REVERIE_CLIENT_IDENTITY

    config = Config(active_model_source="custom")
    agent = ReverieAgent(
        base_url="https://api.example.com/v1",
        api_key="sk-test",
        model="some-model",
        project_root=tmp_path,
        provider="request",
        config=config,
    )

    headers = agent._build_request_headers(stream=False)

    assert headers[REVERIE_CLIENT_HEADER] == REVERIE_CLIENT_IDENTITY
    assert "x-opencode-client" not in headers


def test_direct_request_uses_configured_proxy(monkeypatch, tmp_path) -> None:
    captured = {}

    def fake_request(**kwargs):
        captured.update(kwargs)
        return object()

    monkeypatch.setattr("reverie.agent.agent.make_api_request_with_retry", fake_request)
    config = Config(active_model_source="opencode", api_proxy="127.0.0.1:7890")
    agent = ReverieAgent(
        base_url="https://opencode.ai/zen/v1/chat/completions",
        api_key="",
        model="big-pickle",
        project_root=tmp_path,
        provider="request",
        config=config,
    )

    agent._make_direct_request({"model": "big-pickle", "messages": []}, stream=False)

    assert captured["proxies"] == {
        "http": "http://127.0.0.1:7890",
        "https": "http://127.0.0.1:7890",
    }


def test_direct_responses_request_uses_muse_spark_responses_url(monkeypatch, tmp_path) -> None:
    captured = {}

    def fake_request(**kwargs):
        captured.update(kwargs)
        return object()

    monkeypatch.setattr("reverie.agent.agent.make_api_request_with_retry", fake_request)
    model_id = "muse-spark-1.3-contributor-free"
    config = Config(
        active_model_source="opencode",
        opencode=normalize_opencode_config({"selected_model_id": model_id}),
    )
    agent = ReverieAgent(
        base_url="https://opencode.ai/zen/v1",
        api_key="",
        model=model_id,
        project_root=tmp_path,
        provider="openai-responses",
        endpoint="/responses",
        config=config,
    )

    agent._make_direct_request({"model": model_id, "input": []}, stream=False)

    assert captured["url"] == "https://opencode.ai/zen/v1/responses"


def test_opencode_help_uses_alias_and_mentions_current_free_models() -> None:
    topic = HELP_TOPICS["opencode"]

    assert topic["command"] == "/opencode"
    assert "/oc" in topic["aliases"]
    assert "ling-3.0-flash-fin-free" in topic["detail"]
    assert "muse-spark-1.3-contributor-free" in topic["detail"]
    assert "nemotron-3.5-lightning-free" in topic["detail"]
    assert "laguna-s-2.1-free" in topic["detail"]
    assert normalize_help_topic("oc") == "opencode"
    assert normalize_help_topic("opencode") == "opencode"
