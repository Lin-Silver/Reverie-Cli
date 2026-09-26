from types import SimpleNamespace

import pytest
import requests

from reverie.agent.agent import ReverieAgent, make_api_request_with_retry


def make_agent(tmp_path, retries=1):
    return ReverieAgent(
        base_url="https://example.test/v1", api_key="fixture", model="fixture",
        project_root=tmp_path, provider="openai-sdk", mode="computer-controller",
        config=SimpleNamespace(api_max_retries=retries, api_initial_backoff=0.01, api_timeout=17),
    )


@pytest.mark.parametrize("retries", [0, 2])
def test_http_retry_limit_and_backoff_are_honored(monkeypatch, retries):
    calls, sleeps = [], []
    def fail(*args, **kwargs):
        calls.append(kwargs)
        raise requests.ConnectionError("offline")
    monkeypatch.setattr(requests, "post", fail)
    monkeypatch.setattr("reverie.agent.agent.time.sleep", sleeps.append)
    with pytest.raises(requests.ConnectionError):
        make_api_request_with_retry("https://example.test/v1", {}, {"model": "fixture", "messages": [{"role": "user", "content": "hello"}]}, max_retries=retries, initial_backoff=0.01)
    assert len(calls) == retries + 1
    assert sleeps == [0.01, 0.03][:retries]


@pytest.mark.parametrize("status,retries,expected_calls", [(401, 1, 1), (502, 0, 1), (502, 2, 3)])
def test_sdk_errors_use_one_retry_policy_and_preserve_tools(tmp_path, monkeypatch, status, retries, expected_calls):
    agent = make_agent(tmp_path, retries)
    calls, sleeps, events = [], [], []
    class ProviderError(Exception):
        status_code = status
    def fail(kwargs):
        calls.append(dict(kwargs))
        raise ProviderError("gateway error")
    monkeypatch.setattr(agent, "_call_openai_chat_completion_once", fail)
    monkeypatch.setattr(agent, "_emit_api_retry_event", lambda **kwargs: events.append(kwargs))
    monkeypatch.setattr("reverie.agent.agent.time.sleep", sleeps.append)
    tools = [{"type": "function", "function": {"name": "read_file", "parameters": {"type": "object"}}}]
    with pytest.raises(ProviderError):
        agent._create_openai_chat_completion(model="fixture", messages=[{"role": "user", "content": "hello"}], tools=tools)
    assert len(calls) == expected_calls
    assert len(sleeps) == len(events) == expected_calls - 1
    assert all(call["tools"] == tools for call in calls)
    assert agent.api_max_retries == retries


def test_streaming_chat_assembles_context_once_per_request(tmp_path, monkeypatch):
    agent = make_agent(tmp_path)
    assemblies = []
    monkeypatch.setattr(agent, "_check_and_compress_context", lambda **kwargs: None)
    monkeypatch.setattr(agent, "get_visible_tool_schemas", lambda: [])
    monkeypatch.setattr(agent, "_memory_context_package_message", lambda: assemblies.append(True) or {"role": "system", "content": "memory evidence"})
    captured = []
    def complete(**kwargs):
        captured.append(kwargs)
        choice = SimpleNamespace(delta=SimpleNamespace(content="Done.", reasoning_content=None, tool_calls=None), finish_reason="stop")
        return iter([SimpleNamespace(choices=[choice])])
    monkeypatch.setattr(agent, "_create_openai_chat_completion", complete)
    assert "Done." in list(agent._process_streaming_openai_sdk())
    assert len(assemblies) == len(captured) == 1
    assert any("memory evidence" in str(message["content"]) for message in captured[0]["messages"])


@pytest.mark.parametrize("provider,expected_retries", [("openai-chat", 0), ("openai-responses", 1)])
def test_openai_client_keeps_one_retry_owner(tmp_path, monkeypatch, provider, expected_retries):
    import sys
    import types
    captured = []
    module = types.ModuleType("openai")
    module.OpenAI = lambda **kwargs: captured.append(kwargs) or SimpleNamespace()
    monkeypatch.setitem(sys.modules, "openai", module)
    agent = make_agent(tmp_path)
    agent.provider = provider
    agent._ensure_client()
    assert captured[0]["max_retries"] == expected_retries


@pytest.mark.parametrize("prompt", [
    "请调用 memory_manager correct 修改记忆 mem_abc：本项目先进行实际测试，再交付。",
    "请调用 memory_manager delete 删除临时测试记忆 mem_abc。",
    'Please call memory_manager(action="remember", content="Always build and test app.py before delivery").',
    "请修改记忆 mem_abc：以后项目使用中文详细回答。",
    "Delete memory mem_abc about this project's API tests.",
])
def test_memory_requests_do_not_force_repository_retrieval(tmp_path, prompt):
    agent = make_agent(tmp_path)
    agent.mode = "reverie"
    agent.messages = [{"role": "user", "content": prompt}]
    tools = [{"type": "function", "function": {"name": name}} for name in ("codebase-retrieval", "memory_manager", "memory_retrieval")]
    assert agent._native_tool_choice(tools) is None


@pytest.mark.parametrize("prompt", [
    "修复 memory_manager 工具代码并添加项目测试。",
    "Update memory_manager.py and its tests in this repository.",
    "修改 reverie/memory/store.py 的版本逻辑。",
])
def test_memory_implementation_edits_still_force_repository_retrieval(tmp_path, prompt):
    agent = make_agent(tmp_path)
    agent.mode = "reverie"
    agent.messages = [{"role": "user", "content": prompt}]
    tools = [{"type": "function", "function": {"name": "codebase-retrieval"}}]
    assert agent._native_tool_choice(tools) == {"type": "function", "function": {"name": "codebase-retrieval"}}
