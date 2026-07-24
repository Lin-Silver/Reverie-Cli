import json
import sys
import types
from pathlib import Path
from types import SimpleNamespace

from rich.console import Console

from reverie.agent.agent import ReverieAgent, decode_stream_event
from reverie.codex import build_codex_request_payload
from reverie.cli.display import DisplayComponents
from reverie.cli.help_catalog import HELP_TOPICS
from reverie.tools.serial_novel import DEFAULT_OUTPUT_DIR, STATE_SCHEMA
from reverie.request_identity import REVERIE_CLIENT_HEADER, REVERIE_CLIENT_IDENTITY


def _nvidia_config() -> SimpleNamespace:
    return SimpleNamespace(
        api_max_retries=1,
        api_initial_backoff=0.01,
        api_timeout=17,
        api_enable_debug_logging=False,
        active_model_source="nvidia",
        nvidia={
            "selected_model_id": "deepseek-ai/deepseek-v4-pro",
            "selected_model_display_name": "DeepSeek V4 Pro",
            "reasoning_effort": "max",
            "timeout": 23,
        },
    )


def _install_fake_openai(monkeypatch, seen: dict):
    class FakeCompletions:
        def create(self, **kwargs):
            seen["create_kwargs"] = dict(kwargs)
            return iter(())

    class FakeOpenAI:
        def __init__(self, **kwargs):
            seen["init_kwargs"] = dict(kwargs)
            self.chat = SimpleNamespace(completions=FakeCompletions())

    fake_module = types.ModuleType("openai")
    fake_module.OpenAI = FakeOpenAI
    monkeypatch.setitem(sys.modules, "openai", fake_module)


def _standard_config() -> SimpleNamespace:
    return SimpleNamespace(
        api_max_retries=1,
        api_initial_backoff=0.01,
        api_timeout=17,
        api_enable_debug_logging=False,
        active_model_source="standard",
    )


def _seed_writer_project(
    tmp_path: Path,
    novel_id: str,
    *,
    chapter: int = 1,
    pending_recovery_mode: str = "",
    pending_requires_reprepare: bool = False,
    pending_recommended_append_chars: int = 0,
) -> Path:
    project_dir = tmp_path / DEFAULT_OUTPUT_DIR / novel_id
    (project_dir / "tracking").mkdir(parents=True, exist_ok=True)
    (project_dir / "control-cards").mkdir(parents=True, exist_ok=True)
    state = {
        "schema": STATE_SCHEMA,
        "status": "writing",
        "novel_id": novel_id,
        "active_chapter": chapter,
    }
    (project_dir / "tracking" / "state.json").write_text(
        json.dumps(state, ensure_ascii=False),
        encoding="utf-8",
    )
    (project_dir / "control-cards" / f"chapter-{chapter:04d}.json").write_text(
        json.dumps({"chapter": chapter, "title": "Prepared"}, ensure_ascii=False),
        encoding="utf-8",
    )
    if pending_recovery_mode or pending_requires_reprepare or pending_recommended_append_chars:
        (project_dir / "drafts").mkdir(parents=True, exist_ok=True)
        (project_dir / "drafts" / f"chapter-{chapter:04d}.json").write_text(
            json.dumps(
                {
                    "recovery_mode": pending_recovery_mode,
                    "requires_reprepare": pending_requires_reprepare,
                    "recommended_append_chars": pending_recommended_append_chars,
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
    return project_dir


def test_openai_sdk_client_receives_resolved_provider_timeout_when_needed(monkeypatch, tmp_path):
    seen = {}
    _install_fake_openai(monkeypatch, seen)

    agent = ReverieAgent(
        base_url="https://integrate.api.nvidia.com/v1",
        api_key="x",
        model="deepseek-ai/deepseek-v4-pro",
        project_root=tmp_path,
        provider="openai-sdk",
        config=_nvidia_config(),
    )

    assert "init_kwargs" not in seen
    agent._ensure_client()

    assert seen["init_kwargs"]["timeout"] == 23
    assert seen["init_kwargs"]["default_headers"][REVERIE_CLIENT_HEADER] == REVERIE_CLIENT_IDENTITY


def test_openai_sdk_provider_error_retries_once_with_tool_fields_preserved(tmp_path):
    class FakeProviderError(Exception):
        status_code = 502

    calls = []

    class FakeCompletions:
        def create(self, **kwargs):
            calls.append(dict(kwargs))
            if len(calls) == 1:
                raise FakeProviderError("tool calling is not supported")
            return "ok"

    fake_client = SimpleNamespace(chat=SimpleNamespace(completions=FakeCompletions()))
    agent = ReverieAgent(
        base_url="https://token.sensenova.cn/v1",
        api_key="x",
        model="sensenova-6.7-flash-lite",
        project_root=tmp_path,
        provider="openai-sdk",
        config=_standard_config(),
    )
    agent._ensure_client = lambda: fake_client

    response = agent._create_openai_chat_completion(
        model="sensenova-6.7-flash-lite",
        messages=[
            {"role": "system", "content": "primary system"},
            {"role": "system", "content": "workspace memory"},
            {"role": "user", "content": "hello"},
            {
                "role": "assistant",
                "content": None,
                "tool_calls": [
                    {
                        "id": "call_1",
                        "type": "function",
                        "function": {"name": "read_file", "arguments": "{}"},
                    }
                ],
            },
            {"role": "tool", "tool_call_id": "call_1", "content": "result"},
        ],
        tools=[{"type": "function", "function": {"name": "read_file", "parameters": {"type": "object"}}}],
        stream=True,
        timeout=17,
    )

    assert response == "ok"
    assert len(calls) == 2
    assert "tools" in calls[0]
    assert "tools" in calls[1]
    assert calls[1]["tools"] == calls[0]["tools"]
    assert calls[1]["messages"] == calls[0]["messages"]


def test_openai_sdk_provider_error_preserves_tool_fields_on_retry_failure(tmp_path):
    class FakeProviderError(Exception):
        status_code = 502

    calls = []

    class FakeCompletions:
        def create(self, **kwargs):
            calls.append(dict(kwargs))
            if len(calls) < 2:
                raise FakeProviderError("local server rejected payload")
            return "ok"

    fake_client = SimpleNamespace(chat=SimpleNamespace(completions=FakeCompletions()))
    agent = ReverieAgent(
        base_url="http://127.0.0.1:8080/v1",
        api_key="x",
        model="local.gguf",
        project_root=tmp_path,
        provider="openai-sdk",
        config=_standard_config(),
    )
    agent._ensure_client = lambda: fake_client

    response = agent._create_openai_chat_completion(
        model="local.gguf",
        messages=[
            {"role": "system", "content": "large system" * 5000},
            {"role": "user", "content": "hello"},
        ],
        tools=[{"type": "function", "function": {"name": "read_file", "parameters": {"type": "object"}}}],
        stream=True,
        timeout=17,
    )

    assert response == "ok"
    assert len(calls) == 2
    assert "tools" in calls[0]
    assert "tools" in calls[1]
    assert calls[1]["tools"] == calls[0]["tools"]
    assert calls[1]["messages"] == calls[0]["messages"]


def test_agnes_retries_once_with_fresh_user_query_after_tool_chain(tmp_path):
    class FakeProviderError(Exception):
        status_code = 400

    calls = []

    class FakeCompletions:
        def create(self, **kwargs):
            calls.append(dict(kwargs))
            if len(calls) == 1:
                raise FakeProviderError("No user query found in messages.")
            return "ok"

    config = _standard_config()
    config.active_model_source = "agnes"
    fake_client = SimpleNamespace(chat=SimpleNamespace(completions=FakeCompletions()))
    agent = ReverieAgent(
        base_url="https://apihub.agnes-ai.com/v1",
        api_key="x",
        model="agnes-2.0-flash",
        project_root=tmp_path,
        provider="openai-sdk",
        config=config,
    )
    agent._ensure_client = lambda: fake_client
    agent.messages = [{"role": "user", "content": "Build and verify CardBattle."}]

    response = agent._create_openai_chat_completion(
        model="agnes-2.0-flash",
        messages=[
            {"role": "system", "content": "system"},
            {"role": "user", "content": "Build and verify CardBattle."},
            {"role": "assistant", "content": None, "tool_calls": []},
            {"role": "tool", "tool_call_id": "call_1", "content": "verified"},
        ],
        stream=True,
    )

    assert response == "ok"
    assert len(calls) == 2
    assert calls[1]["messages"][:-1] == calls[0]["messages"]
    assert calls[1]["messages"][-1] == {
        "role": "user",
        "content": "Build and verify CardBattle.",
    }


def test_sensenova_retries_once_with_fresh_user_query_after_tool_chain(tmp_path):
    class FakeProviderError(Exception):
        status_code = 400

    calls = []

    class FakeCompletions:
        def create(self, **kwargs):
            calls.append(dict(kwargs))
            if len(calls) == 1:
                raise FakeProviderError("No user query found in messages.")
            return "ok"

    config = _standard_config()
    config.active_model_source = "sensenova"
    config.sensenova = {"selected_model_id": "sensenova-6.7-flash-lite"}
    fake_client = SimpleNamespace(chat=SimpleNamespace(completions=FakeCompletions()))
    agent = ReverieAgent(
        base_url="https://token.sensenova.cn/v1",
        api_key="x",
        model="sensenova-6.7-flash-lite",
        project_root=tmp_path,
        provider="openai-sdk",
        config=config,
    )
    agent._ensure_client = lambda: fake_client
    agent.messages = [{"role": "user", "content": "Continue and complete the novel."}]

    response = agent._create_openai_chat_completion(
        model="sensenova-6.7-flash-lite",
        messages=[
            {"role": "system", "content": "system"},
            {"role": "user", "content": "Continue and complete the novel."},
            {"role": "tool", "tool_call_id": "call_1", "content": "audit passed"},
        ],
        stream=True,
    )

    assert response == "ok"
    assert len(calls) == 2
    assert calls[1]["messages"][-1] == {
        "role": "user",
        "content": "Continue and complete the novel.",
    }


def test_sensenova_non_streaming_sdk_preserves_reasoning_effort_and_sampling_options(tmp_path):
    captured = {}

    class FakeCompletions:
        def create(self, **kwargs):
            captured.update(kwargs)
            return SimpleNamespace(
                choices=[
                    SimpleNamespace(
                        message=SimpleNamespace(content="ok", reasoning=None, reasoning_content=None, tool_calls=[]),
                        finish_reason="stop",
                    )
                ]
            )

    config = _standard_config()
    config.active_model_source = "sensenova"
    config.sensenova = {"selected_model_id": "sensenova-6.7-flash-lite", "reasoning_effort": "none"}
    fake_client = SimpleNamespace(chat=SimpleNamespace(completions=FakeCompletions()))
    agent = ReverieAgent(
        base_url="https://token.sensenova.cn/v1",
        api_key="x",
        model="sensenova-6.7-flash-lite",
        project_root=tmp_path,
        provider="openai-sdk",
        config=config,
        mode="writer",
    )
    agent._ensure_client = lambda: fake_client
    agent.get_visible_tool_schemas = lambda mode=None: []
    agent.messages = [{"role": "user", "content": "Write the next novel chapter."}]

    result = agent._process_non_streaming_openai_sdk(session_id="test")

    assert result == "ok"
    assert captured["stream"] is False
    assert captured["extra_body"] == {
        "reasoning_effort": "none",
        "top_k": 20,
        "min_p": 0.0,
        "repetition_penalty": 1.0,
    }
    assert captured["temperature"] == 0.7
    assert captured["top_p"] == 0.8
    assert captured["presence_penalty"] == 1.5
    assert captured["max_tokens"] == 6144


def test_sensenova_openai_chat_prefers_http_fallback_only_in_writer_direct_prose(tmp_path):
    config = _standard_config()
    config.active_model_source = "sensenova"
    config.sensenova = {"selected_model_id": "sensenova-6.7-flash-lite"}
    agent = ReverieAgent(
        base_url="https://token.sensenova.cn/v1",
        api_key="x",
        model="sensenova-6.7-flash-lite",
        project_root=tmp_path,
        provider="openai-chat",
        config=config,
        mode="writer",
    )
    agent.messages = [{"role": "user", "content": "Continue the novel."}]
    agent._writer_should_hide_tools_for_direct_prose = lambda: True

    called = []

    def fake_http(session_id: str = "default"):
        called.append(("http", session_id))
        yield "http-fallback"

    def fake_sdk(session_id: str = "default"):
        called.append(("sdk", session_id))
        yield "sdk"

    agent._process_streaming_openai_http_fallback = fake_http
    agent._process_streaming_openai_sdk = fake_sdk

    chunks = list(agent._process_streaming(session_id="writer-test"))

    assert agent._should_use_openai_http_fallback() is True
    assert chunks == ["http-fallback"]
    assert called == [("http", "writer-test")]


def test_sensenova_http_fallback_streaming_preserves_openai_payload_options(tmp_path):
    captured = {}

    class FakeResponse:
        def close(self):
            return None

    config = _standard_config()
    config.active_model_source = "sensenova"
    config.sensenova = {
        "selected_model_id": "sensenova-6.7-flash-lite",
        "reasoning_effort": "none",
    }
    agent = ReverieAgent(
        base_url="https://token.sensenova.cn/v1",
        api_key="x",
        model="sensenova-6.7-flash-lite",
        project_root=tmp_path,
        provider="openai-chat",
        config=config,
        mode="writer",
    )
    agent.messages = [{"role": "user", "content": "Write the next novel chapter."}]
    agent.get_visible_tool_schemas = lambda mode=None: []

    def fake_make_direct_request(payload, *, stream):
        captured["payload"] = dict(payload)
        captured["stream"] = stream
        return FakeResponse()

    agent._make_direct_request = fake_make_direct_request
    agent._iter_request_stream_events = lambda response, provider_label: iter(
        [
            {"type": "content", "text": "ok"},
            {"type": "finish", "reason": "stop"},
        ]
    )

    chunks = list(agent._process_streaming_openai_http_fallback(session_id="writer-test"))

    assert captured["stream"] is True
    assert captured["payload"]["model"] == "sensenova-6.7-flash-lite"
    assert captured["payload"]["stream"] is True
    assert captured["payload"]["temperature"] == 0.7
    assert captured["payload"]["top_p"] == 0.8
    assert captured["payload"]["presence_penalty"] == 1.5
    assert captured["payload"]["max_tokens"] == 6144
    assert captured["payload"]["extra_body"] == {
        "reasoning_effort": "none",
        "top_k": 20,
        "min_p": 0.0,
        "repetition_penalty": 1.0,
    }
    assert not captured["payload"].get("tools")
    assert any(chunk == "ok" for chunk in chunks)


def test_sensenova_request_messages_proactively_end_with_user_query(tmp_path):
    config = _standard_config()
    config.active_model_source = "sensenova"
    config.sensenova = {"selected_model_id": "sensenova-6.7-flash-lite"}
    agent = ReverieAgent(
        base_url="https://token.sensenova.cn/v1",
        api_key="x",
        model="sensenova-6.7-flash-lite",
        project_root=tmp_path,
        provider="openai-sdk",
        config=config,
    )
    agent.messages = [
        {"role": "user", "content": "Continue the novel."},
        {"role": "assistant", "content": None, "tool_calls": []},
        {"role": "tool", "tool_call_id": "call_1", "content": "chapter committed"},
    ]

    messages = agent._build_messages()

    assert messages[-1]["role"] == "user"
    assert "immediately preceding tool result" in messages[-1]["content"]
    assert "do not resend unchanged tool arguments" in messages[-1]["content"]
    assert agent.messages[-1]["role"] == "tool"


def test_sensenova_writer_context_followup_requests_append_only_plain_prose(tmp_path):
    _seed_writer_project(
        tmp_path,
        "writer-append-followup",
        pending_recovery_mode="append_only",
        pending_recommended_append_chars=600,
    )
    config = _standard_config()
    config.active_model_source = "sensenova"
    config.sensenova = {"selected_model_id": "sensenova-6.7-flash-lite"}
    agent = ReverieAgent(
        base_url="https://token.sensenova.cn/v1",
        api_key="x",
        model="sensenova-6.7-flash-lite",
        project_root=tmp_path,
        provider="openai-sdk",
        mode="writer",
        config=config,
    )
    agent.messages = [
        {"role": "user", "content": "Continue the novel."},
        {
            "role": "assistant",
            "content": None,
            "tool_calls": [
                {
                    "id": "call_1",
                    "type": "function",
                    "function": {
                        "name": "serial_novel",
                        "arguments": '{"action":"context","novel_id":"writer-append-followup"}',
                    },
                }
            ],
        },
        {"role": "tool", "tool_call_id": "call_1", "content": "Preserved draft tail available."},
    ]

    messages = agent._build_messages()

    assert messages[-1]["role"] == "user"
    assert "Write only the missing new chapter prose in plain text." in messages[-1]["content"]
    assert "Provide at least 600 new non-whitespace characters." in messages[-1]["content"]
    assert "data.append_content automatically" in messages[-1]["content"]
    assert "Do not repeat the preserved tail" in messages[-1]["content"]
    assert agent.messages[-1]["role"] == "tool"


def test_sensenova_writer_failed_commit_followup_requires_prepare_chapter(tmp_path):
    _seed_writer_project(
        tmp_path,
        "writer-reprepare-followup",
        pending_recovery_mode="reprepare",
        pending_requires_reprepare=True,
    )
    config = _standard_config()
    config.active_model_source = "sensenova"
    config.sensenova = {"selected_model_id": "sensenova-6.7-flash-lite"}
    agent = ReverieAgent(
        base_url="https://token.sensenova.cn/v1",
        api_key="x",
        model="sensenova-6.7-flash-lite",
        project_root=tmp_path,
        provider="openai-sdk",
        mode="writer",
        config=config,
    )
    agent.messages = [
        {"role": "user", "content": "Continue the novel."},
        {
            "role": "assistant",
            "content": None,
            "tool_calls": [
                {
                    "id": "call_1",
                    "type": "function",
                    "function": {
                        "name": "serial_novel",
                        "arguments": (
                            '{"action":"commit_chapter","novel_id":"writer-reprepare-followup","chapter":1}'
                        ),
                    },
                }
            ],
        },
        {"role": "tool", "tool_call_id": "call_1", "content": "Repair budget exhausted."},
    ]

    messages = agent._build_messages()

    assert messages[-1]["role"] == "user"
    assert "action='prepare_chapter'" in messages[-1]["content"]
    assert "materially revised outline/control card" in messages[-1]["content"]
    assert "Do not call commit_chapter yet" in messages[-1]["content"]
    assert agent.messages[-1]["role"] == "tool"


def test_legacy_nvidia_default_timeout_does_not_override_global_timeout_when_needed(monkeypatch, tmp_path):
    seen = {}
    _install_fake_openai(monkeypatch, seen)
    config = _nvidia_config()
    config.api_timeout = 41
    config.nvidia["timeout"] = 300

    agent = ReverieAgent(
        base_url="https://integrate.api.nvidia.com/v1",
        api_key="x",
        model="deepseek-ai/deepseek-v4-pro",
        project_root=tmp_path,
        provider="openai-sdk",
        config=config,
    )

    assert "init_kwargs" not in seen
    agent._ensure_client()

    assert seen["init_kwargs"]["timeout"] == 41


def test_openai_sdk_stream_emits_visible_wait_event_before_request(monkeypatch, tmp_path):
    seen = {}
    _install_fake_openai(monkeypatch, seen)
    agent = ReverieAgent(
        base_url="https://integrate.api.nvidia.com/v1",
        api_key="x",
        model="deepseek-ai/deepseek-v4-pro",
        project_root=tmp_path,
        provider="openai-sdk",
        config=_nvidia_config(),
    )
    agent.tool_executor.get_tool_schemas = lambda mode="reverie": []
    agent.messages.append({"role": "system", "content": "late system note"})

    stream = agent._process_streaming_openai_sdk()
    event = decode_stream_event(next(stream))

    assert event["event"] == "model_request"
    assert event["message"] == "Waiting for NVIDIA API response"
    assert event["detail"] == "deepseek-ai/deepseek-v4-pro | stream"
    assert event["meta"] == "timeout 23s"
    assert "create_kwargs" not in seen

    try:
        next(stream)
    except StopIteration:
        pass

    create_kwargs = seen["create_kwargs"]
    assert create_kwargs["timeout"] == 23
    assert create_kwargs["extra_body"] == {
        "chat_template_kwargs": {
            "thinking": True,
            "reasoning_effort": "max",
        }
    }
    assert create_kwargs["messages"][0]["role"] == "system"
    assert all(message["role"] != "system" for message in create_kwargs["messages"][1:])


def test_openai_sdk_retries_transient_create_errors(monkeypatch, tmp_path):
    seen = {"calls": 0}

    class APIConnectionError(Exception):
        pass

    class FakeCompletions:
        def create(self, **kwargs):
            seen["calls"] += 1
            if seen["calls"] == 1:
                raise APIConnectionError("peer closed connection")
            seen["create_kwargs"] = dict(kwargs)
            return iter(())

    class FakeOpenAI:
        def __init__(self, **kwargs):
            self.chat = SimpleNamespace(completions=FakeCompletions())

    fake_module = types.ModuleType("openai")
    fake_module.OpenAI = FakeOpenAI
    monkeypatch.setitem(sys.modules, "openai", fake_module)
    config = _nvidia_config()
    config.api_max_retries = 2
    config.api_initial_backoff = 0.01
    agent = ReverieAgent(
        base_url="https://integrate.api.nvidia.com/v1",
        api_key="x",
        model="deepseek-ai/deepseek-v4-pro",
        project_root=tmp_path,
        provider="openai-sdk",
        config=config,
    )

    response = agent._create_openai_chat_completion(model="m", messages=[], stream=True)

    assert list(response) == []
    assert seen["calls"] == 2
    assert seen["create_kwargs"]["model"] == "m"


def test_compaction_memory_is_persisted_to_memory_index(monkeypatch, tmp_path):
    seen = {}
    _install_fake_openai(monkeypatch, seen)

    class FakeMemoryIndexer:
        def __init__(self):
            self.summary = None
            self.refreshed = None

        def set_session_summary(self, session_id, summary):
            self.summary = (session_id, summary)

        def refresh_session(self, session_id):
            self.refreshed = session_id
            return 0

    memory_indexer = FakeMemoryIndexer()
    agent = ReverieAgent(
        base_url="https://integrate.api.nvidia.com/v1",
        api_key="x",
        model="deepseek-ai/deepseek-v4-pro",
        project_root=tmp_path,
        provider="openai-sdk",
        config=_nvidia_config(),
    )
    agent.tool_executor.update_context("memory_indexer", memory_indexer)

    agent._record_compaction_memory(
        [
            {"role": "system", "content": "[MEMORY CONSOLIDATION - Context Engine Cache]\nKeep retry policy.\n[END MEMORY]"},
            {"role": "user", "content": "recent"},
        ],
        "session-1",
    )

    assert memory_indexer.summary == ("session-1", "Compaction memory: Keep retry policy.")
    assert memory_indexer.refreshed == "session-1"


def test_automatic_context_compaction_emits_compact_token_log(monkeypatch, tmp_path):
    seen = {}
    _install_fake_openai(monkeypatch, seen)
    agent = ReverieAgent(
        base_url="https://example.test/v1",
        api_key="x",
        model="test-model",
        project_root=tmp_path,
        provider="request",
        config=_standard_config(),
    )
    agent.messages = [
        {"role": "user", "content": "old context " * 500},
        {"role": "assistant", "content": "old response " * 500},
        {"role": "user", "content": "current request"},
    ]
    events = []
    agent.tool_executor.update_context("ui_event_handler", events.append)

    from reverie.context_engine.compressor import ContextCompressor

    monkeypatch.setattr(
        ContextCompressor,
        "compress",
        lambda self, **_kwargs: [
            {"role": "system", "content": "[MEMORY CONSOLIDATION - Context Engine Cache]\nsummary\n[END MEMORY]"},
            {"role": "user", "content": "current request"},
        ],
    )

    compressed_tokens = agent._handle_context_compaction(12_345, 20_000, session_id="session-1")

    assert compressed_tokens < 12_345
    assert any(
        event.get("compact") is True
        and event.get("message", "").startswith("Context compressed: 12,345 -> ")
        and event.get("message", "").endswith(" tokens")
        for event in events
    )


def test_nvidia_short_turn_keeps_full_tools_and_reasoning(monkeypatch, tmp_path):
    seen = {}
    _install_fake_openai(monkeypatch, seen)
    agent = ReverieAgent(
        base_url="https://integrate.api.nvidia.com/v1",
        api_key="x",
        model="deepseek-ai/deepseek-v4-pro",
        project_root=tmp_path,
        provider="openai-sdk",
        config=_nvidia_config(),
    )
    tool_schema = {"type": "function", "function": {"name": "codebase-retrieval", "parameters": {"type": "object"}}}
    agent.tool_executor.get_tool_schemas = lambda mode="reverie": [tool_schema]
    agent.messages.append({"role": "user", "content": "你是谁？"})

    stream = agent._process_streaming_openai_sdk()
    next(stream)
    try:
        next(stream)
    except StopIteration:
        pass

    create_kwargs = seen["create_kwargs"]
    assert create_kwargs["tools"] == [tool_schema]
    assert create_kwargs["extra_body"] == {
        "chat_template_kwargs": {
            "thinking": True,
            "reasoning_effort": "max",
        }
    }
    assert create_kwargs["max_tokens"] <= 262144
    assert create_kwargs["max_tokens"] > 250000


def test_repository_turn_requires_one_context_engine_call_then_returns_to_auto(tmp_path):
    agent = ReverieAgent(
        base_url="https://example.test/v1",
        api_key="x",
        model="test-model",
        project_root=tmp_path,
        provider="openai-sdk",
        config=_standard_config(),
    )
    tool_schema = {
        "type": "function",
        "function": {
            "name": "codebase-retrieval",
            "description": "Context Engine",
            "parameters": {"type": "object", "properties": {}},
        },
    }
    agent.messages.append(
        {"role": "user", "content": "Optimize the Context Engine recommendation code and compression tests."}
    )

    first = agent._build_openai_chat_completion_kwargs(
        messages=agent._build_messages(),
        tools=[tool_schema],
        stream=True,
    )

    assert first["tool_choice"] == {
        "type": "function",
        "function": {"name": "codebase-retrieval"},
    }

    agent.messages.append(
        {
            "role": "assistant",
            "content": "",
            "tool_calls": [
                {
                    "id": "context-1",
                    "type": "function",
                    "function": {
                        "name": "codebase-retrieval",
                        "arguments": '{"query_type":"task","query":"optimize context"}',
                    },
                }
            ],
        }
    )
    second = agent._build_openai_chat_completion_kwargs(
        messages=agent._build_messages(),
        tools=[tool_schema],
        stream=True,
    )

    assert "tool_choice" not in second


def test_general_chat_does_not_force_context_engine_tool(tmp_path):
    agent = ReverieAgent(
        base_url="https://example.test/v1",
        api_key="x",
        model="test-model",
        project_root=tmp_path,
        provider="openai-sdk",
        config=_standard_config(),
    )
    tool_schema = {"type": "function", "function": {"name": "codebase-retrieval", "parameters": {"type": "object"}}}
    agent.messages.append({"role": "user", "content": "Tell me a short joke."})

    kwargs = agent._build_openai_chat_completion_kwargs(
        messages=agent._build_messages(),
        tools=[tool_schema],
        stream=True,
    )

    assert "tool_choice" not in kwargs


def test_general_programming_explanation_does_not_force_repository_tool(tmp_path):
    agent = ReverieAgent(
        base_url="https://example.test/v1",
        api_key="x",
        model="test-model",
        project_root=tmp_path,
        provider="openai-sdk",
        config=_standard_config(),
    )
    tool_schema = {"type": "function", "function": {"name": "codebase-retrieval", "parameters": {"type": "object"}}}
    agent.messages.append({"role": "user", "content": "Explain how Python classes work."})

    kwargs = agent._build_openai_chat_completion_kwargs(
        messages=agent._build_messages(),
        tools=[tool_schema],
        stream=True,
    )

    assert "tool_choice" not in kwargs


def test_nvidia_request_provider_clamps_output_to_remaining_context(tmp_path):
    config = _nvidia_config()
    config.nvidia = {
        "selected_model_id": "mistralai/mistral-medium-3.5-128b",
        "selected_model_display_name": "Mistral Medium 3.5 128B",
        "max_tokens": 262144,
    }
    agent = ReverieAgent(
        base_url="https://integrate.api.nvidia.com/v1/chat/completions",
        api_key="x",
        model="mistralai/mistral-medium-3.5-128b",
        project_root=tmp_path,
        provider="request",
        config=config,
    )
    payload = {
        "model": "mistralai/mistral-medium-3.5-128b",
        "messages": [
            {"role": "system", "content": "system" * 2000},
            {"role": "user", "content": "hello" * 4000},
        ],
        "tools": [
            {
                "type": "function",
                "function": {
                    "name": "large_tool",
                    "parameters": {"type": "object", "description": "schema" * 4000},
                },
            }
        ],
        "stream": True,
    }

    prepared = agent._prepare_request_payload(payload)

    assert prepared["max_tokens"] < 262144
    assert prepared["max_tokens"] > 200000
    assert prepared["reasoning_effort"] == "high"


def test_nvidia_minimax_m3_request_payload_uses_thinking_mode_and_stream_reasoning(tmp_path):
    config = _nvidia_config()
    config.nvidia = {
        "selected_model_id": "minimaxai/minimax-m3",
        "selected_model_display_name": "MiniMax M3",
        "reasoning_effort": "high",
    }
    agent = ReverieAgent(
        base_url="https://integrate.api.nvidia.com/v1/chat/completions",
        api_key="x",
        model="minimaxai/minimax-m3",
        project_root=tmp_path,
        provider="request",
        config=config,
    )
    payload = agent._prepare_request_payload(
        {
            "model": "minimaxai/minimax-m3",
            "messages": [{"role": "user", "content": "hello"}],
            "stream": True,
        }
    )

    assert payload["chat_template_kwargs"] == {"thinking_mode": "enabled"}
    assert "reasoning_effort" not in payload

    class FakeResponse:
        def iter_lines(self, decode_unicode=False, chunk_size=None):
            yield 'data: {"choices":[{"delta":{"reasoning_content":"thinking"},"finish_reason":null}]}'
            yield ""
            yield 'data: {"choices":[{"delta":{"content":"answer"},"finish_reason":null}]}'
            yield ""
            yield "data: [DONE]"

    events = list(agent._iter_request_stream_events(FakeResponse(), "NVIDIA"))

    assert events[:2] == [
        {"type": "reasoning", "text": "thinking"},
        {"type": "content", "text": "answer"},
    ]


def test_codex_native_provider_payload_preserves_inline_image_parts():
    messages = [
        {
            "role": "user",
            "content": [
                {"type": "text", "text": "Describe this image"},
                {
                    "type": "image_url",
                    "image_url": {"url": "data:image/png;base64,AAAA"},
                },
            ],
        }
    ]

    codex_payload = build_codex_request_payload(
        model_name="gpt-test",
        messages=messages,
    )
    codex_parts = codex_payload["input"][0]["content"]
    assert {"type": "input_text", "text": "Describe this image"} in codex_parts
    assert {"type": "input_image", "image_url": "data:image/png;base64,AAAA"} in codex_parts


def test_display_suppresses_model_request_stream_event():
    console = Console(record=True, force_terminal=False, width=120)
    display = DisplayComponents(console)

    handled = display.show_stream_event(
        {
            "event": "model_request",
            "category": "Model",
            "message": "Waiting for NVIDIA API response",
            "status": "working",
            "detail": "deepseek-ai/deepseek-v4-pro | stream",
            "meta": "timeout 23s",
        }
    )

    assert handled is True
    assert "Waiting for NVIDIA API response" not in console.export_text()


def test_nvidia_help_matches_supported_commands():
    nvidia_help = HELP_TOPICS["nvidia"]
    subcommand_usages = [item["usage"] for item in nvidia_help["subcommands"]]

    assert "/nvidia fast on" not in subcommand_usages
    assert "/nvidia fast off" not in subcommand_usages
    assert "thinking" in nvidia_help["overview"]


def test_webgemini_help_matches_supported_commands():
    webgemini_help = HELP_TOPICS["webgemini"]
    subcommand_usages = [item["usage"] for item in webgemini_help["subcommands"]]

    assert "/webgemini activate" in subcommand_usages
    assert "/webgemini model <model-id>" in subcommand_usages
    assert "/webgemini proxy <url|clear>" in subcommand_usages
    assert "/wgemini" in subcommand_usages
