from types import SimpleNamespace
import json

import pytest
import requests

from reverie.agent.agent import ReverieAgent, make_api_request_with_retry


def make_agent(tmp_path, retries=1):
    return ReverieAgent(
        base_url="https://example.test/v1", api_key="fixture", model="fixture",
        project_root=tmp_path, provider="openai-sdk", mode="computer-controller",
        config=SimpleNamespace(api_max_retries=retries, api_initial_backoff=0.01, api_timeout=17),
    )


def test_desktop_acceptance_can_observe_but_cannot_act_or_run_commands(tmp_path):
    agent = make_agent(tmp_path)
    agent.mode = 'aio'
    agent.tool_executor.context['desktop_read_only_review'] = True
    names = {schema['function']['name'] for schema in agent.get_visible_tool_schemas()}
    assert {'computer_snapshot','computer_find','computer_get'} <= names
    assert not {'computer_click','computer_set_value','command_exec','create_file'} & names
    agent.tool_executor.context['aio_worker'] = True
    assert not any(schema['function']['name'].startswith('computer_') for schema in agent.get_visible_tool_schemas())


@pytest.mark.parametrize("retries", [0, 2])
def test_http_retry_limit_and_backoff_are_honored(monkeypatch, retries):
    calls, sleeps = [], []
    def fail(*args, **kwargs):
        calls.append(kwargs)
        raise requests.ConnectionError("offline")
    monkeypatch.setattr("reverie.agent.agent.provider_post", fail)
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


@pytest.mark.parametrize('transport', ['stream_sdk','stream_request','buffered_sdk','buffered_request','buffered_anthropic'])
def test_final_answer_preserves_whitespace_in_authoritative_history(tmp_path, monkeypatch, transport):
    from reverie.session.sqlite_manager import SQLiteSessionManager

    agent=make_agent(tmp_path)
    store=SQLiteSessionManager(tmp_path/'history',project_root=tmp_path)
    session=store.create_session('Exact answer')
    agent.tool_executor.context['session_manager']=store
    agent.messages=[{'role':'user','content':'Return the supplied text.'}]
    text=' \n完整保存的回答。  \n'
    monkeypatch.setattr(agent,'_check_and_compress_context',lambda **kwargs:None)
    monkeypatch.setattr(agent,'get_visible_tool_schemas',lambda:[])
    message=SimpleNamespace(content=text,reasoning_content=None,tool_calls=[])
    choice=SimpleNamespace(message=message,finish_reason='stop')
    response=SimpleNamespace(choices=[choice],usage=None)
    pieces=[{'choices':[{'delta':{'content':text},'finish_reason':'stop'}]}]
    monkeypatch.setattr(agent,'_create_openai_chat_completion',lambda **kwargs:iter([
        SimpleNamespace(choices=[SimpleNamespace(delta=message,finish_reason='stop')])
    ]) if transport.startswith('stream') else response)
    monkeypatch.setattr(agent,'_make_direct_request',lambda *args,**kwargs:SimpleNamespace(close=lambda:None))
    monkeypatch.setattr(agent,'_iter_sse_data_strings',lambda response:iter(map(json.dumps,pieces)))
    monkeypatch.setattr(agent,'_response_json_with_prompt_cache_fallback',lambda *args,**kwargs:{'choices':[{'message':{'content':text},'finish_reason':'stop'}]})
    monkeypatch.setattr(agent,'_ensure_client',lambda:SimpleNamespace(messages=SimpleNamespace(create=lambda **kwargs:SimpleNamespace(content=[SimpleNamespace(type='text',text=text)],stop_reason='end_turn',usage=None))))
    methods={'stream_sdk':agent._process_streaming_openai_sdk,'stream_request':agent._process_streaming_request,
             'buffered_sdk':agent._process_non_streaming_openai_sdk,'buffered_request':agent._process_non_streaming_request,
             'buffered_anthropic':agent._process_non_streaming_anthropic}
    result=methods[transport](session_id=session.id)
    if transport.startswith('stream'):list(result)
    agent._persist_history_to_session()
    assert store.get_page(session.id)['messages'][-1]=={'role':'assistant','content':text}


@pytest.mark.parametrize("provider,expected_retries", [("openai-chat", 0), ("openai-responses", 0)])
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
    "Fix src/main.py.",
    "Explain src/model.ts.",
])
def test_memory_implementation_edits_still_force_repository_retrieval(tmp_path, prompt):
    agent = make_agent(tmp_path)
    agent.mode = "reverie"
    agent.messages = [{"role": "user", "content": prompt}]
    tools = [{"type": "function", "function": {"name": "codebase-retrieval"}}]
    assert agent._native_tool_choice(tools) == {"type": "function", "function": {"name": "codebase-retrieval"}}


def test_literal_file_task_does_not_force_retrieval_from_negative_edit_instructions(tmp_path):
    agent=make_agent(tmp_path)
    agent.mode='reverie'
    agent.messages=[{'role':'user','content':'Create aio-proof.txt with exactly AiO VERIFIED followed by a newline. Do not add a trailing extra newline, BOM, or other characters.'}]
    tools=[{'type':'function','function':{'name':name}} for name in ['codebase-retrieval','create_file','file_ops']]
    assert agent._native_tool_choice(tools) is None


@pytest.mark.parametrize("prompt", [
    "Use render_view to display artifacts/comparison.html. Do not run commands or read other files.",
    "调用 render_view 注册 artifacts/savings-comparator.html。不要重新创建或读取其他文件。",
    "Create artifacts/comparison.html with create_file, then render_view. Only use those two tools.",
])
def test_artifact_paths_do_not_force_repository_retrieval(tmp_path, prompt):
    agent = make_agent(tmp_path)
    agent.mode = "reverie"
    agent.messages = [{"role": "user", "content": prompt}]
    tools = [{"type": "function", "function": {"name": name}} for name in ("codebase-retrieval", "create_file", "render_view")]
    assert agent._native_tool_choice(tools) is None


@pytest.mark.parametrize('prompt', [
    'Create aio-proof.txt with UTF-8 content AiO VERIFIED 中文 followed by one newline. Read it back and verify the file.',
    '创建文件 aio-proof.txt，以 UTF-8 编码写入内容 AiO VERIFIED 中文，然后检查文件的逐字节内容。',
])
def test_supplied_file_content_does_not_restrict_the_worker_to_repository_lookup(tmp_path, prompt):
    agent = make_agent(tmp_path)
    agent.mode = 'reverie'
    agent.messages = [{'role':'user','content':prompt}]
    tools = [{'type':'function','function':{'name':name}} for name in ('codebase-retrieval','create_file','file_ops')]
    assert agent._native_tool_choice(tools) is None


def test_existing_source_change_with_content_still_requires_repository_lookup(tmp_path):
    agent = make_agent(tmp_path)
    agent.mode = 'reverie'
    agent.messages = [{'role':'user','content':'Inspect the repository and write updated content to existing source code in app.py.'}]
    tools = [{'type':'function','function':{'name':name}} for name in ('codebase-retrieval','create_file','file_ops')]
    assert agent._native_tool_choice(tools) == {'type':'function','function':{'name':'codebase-retrieval'}}


@pytest.mark.parametrize("prompt", [
    "做月度图表，倍率修改后总量同步更新。仅使用 create_file 和 render_view，不读取已有文件，不调用其他工具。",
    "增加最高价格筛选并更新同一视图。继续只使用 create_file 和 render_view，不读取其他文件或调用其他工具。",
    "Update this interactive chart. Only use create_file and render_view. Do not inspect existing files.",
])
def test_explicit_view_tool_scope_is_not_overridden_by_negative_file_instructions(tmp_path, prompt):
    agent = make_agent(tmp_path)
    agent.mode = "reverie"
    agent.messages = [{"role": "user", "content": prompt}]
    tools = [{"type": "function", "function": {"name": name}} for name in ("codebase-retrieval", "create_file", "render_view")]
    assert agent._native_tool_choice(tools) is None


@pytest.mark.parametrize("prompt", [
    "请使用 file_ops 的 read 操作读取当前项目中的 inventory.txt，然后仅报告文件内容。不要运行命令，不要修改任何文件，也不要调用其他工具。",
    "只使用 file_ops 读取当前项目文件，不要修改文件。",
    "只允许使用 file_ops 读取项目文件，不要修改文件。",
    "仅限 file_ops 查看项目文件，不要修改文件。",
    "Only use file_ops to read the project file; do not modify any files.",
    "Use file_ops to read the project file. Do not call any other tools.",
])
def test_explicit_file_tool_scope_does_not_force_repository_retrieval(tmp_path, prompt):
    agent = make_agent(tmp_path)
    agent.mode = "reverie"
    agent.messages = [{"role": "user", "content": prompt}]
    tools = [{"type": "function", "function": {"name": name}} for name in ("codebase-retrieval", "file_ops")]
    assert agent._context_engine_native_tool_choice(tools) is None
    assert agent._native_tool_choice(tools) == {"type": "function", "function": {"name": "file_ops"}}


@pytest.mark.parametrize("prompt", [
    "使用 file_ops 查看仓库文件，再分析并修复代码。",
    "不要只使用 file_ops，请分析并修复仓库文件。",
    "Do not only use file_ops; inspect and fix the repository files.",
])
def test_unrestricted_repository_request_with_file_ops_still_requires_retrieval(tmp_path, prompt):
    agent = make_agent(tmp_path)
    agent.mode = "reverie"
    agent.messages = [{"role": "user", "content": prompt}]
    tools = [{"type": "function", "function": {"name": name}} for name in ("codebase-retrieval", "file_ops")]
    assert agent._native_tool_choice(tools) == {"type": "function", "function": {"name": "codebase-retrieval"}}


def test_explicit_file_ops_is_not_assumed_available(tmp_path):
    agent = make_agent(tmp_path)
    agent.mode = "reverie"
    agent.messages = [{"role": "user", "content": "只使用 file_ops 查看项目文件，不要修改文件。"}]
    tools = [{"type": "function", "function": {"name": "codebase-retrieval"}}]
    assert agent._native_tool_choice(tools) is None


def test_scoped_file_request_keeps_tools_without_forcing_lookup(tmp_path):
    agent = make_agent(tmp_path)
    agent.mode = "reverie"
    agent.messages = [{"role": "user", "content": "请使用 file_ops 读取项目文件，不要修改文件，也不要调用其他工具。"}]
    tools = [{"type": "function", "function": {"name": name, "parameters": {"type": "object"}}} for name in ("codebase-retrieval", "file_ops")]
    request = agent._build_openai_chat_completion_kwargs(messages=agent.messages, tools=tools, stream=False)
    assert request["tools"] == tools
    assert request["tool_choice"] == {"type": "function", "function": {"name": "file_ops"}}


@pytest.mark.parametrize('attempt', [
    {'role': 'assistant', 'tool_calls': [{'function': {'name': 'file_ops'}}]},
    {'role': 'tool', 'name': 'file_ops', 'content': 'Failed'},
    {'role': 'assistant', 'tool_calls': [{'function': {'name': 'other'}}]},
])
def test_explicit_read_choice_ends_after_any_attempt_including_failure(tmp_path, attempt):
    agent = make_agent(tmp_path)
    agent.mode = 'reverie'
    agent.messages = [{'role': 'user', 'content': 'Only use file_ops to read inventory.txt.'}, attempt]
    tools = [{'function': {'name': 'file_ops'}}]
    assert agent._native_tool_choice(tools) is None
    assert agent._anthropic_tool_choice(tools) is None


def test_explicit_read_scopes_visible_tools_until_next_user_turn(tmp_path):
    agent = make_agent(tmp_path)
    agent.mode = 'reverie'
    schemas = [{'function': {'name': n}} for n in ('file_ops', 'computer_click', 'command_exec')]
    agent.tool_executor.get_tool_schemas = lambda **kwargs: schemas
    agent.messages = [{'role': 'user', 'content': 'Only use file_ops to read inventory.txt.'}]
    assert agent.get_visible_tool_schemas() == [schemas[0]]
    assert agent._anthropic_tool_choice([schemas[0]]) == {'type': 'tool', 'name': 'file_ops'}
    agent.messages.append({'role': 'tool', 'content': 'observed'})
    assert agent.get_visible_tool_schemas() == [schemas[0]]
    assert agent._native_tool_choice([schemas[0]]) is None
    agent.messages.append({'role': 'user', 'content': 'Inspect the desktop.'})
    assert agent.get_visible_tool_schemas() == schemas


@pytest.mark.parametrize('prompt', [
    "Only use file_ops to write inventory.txt.",
    "Do not use file_ops to read inventory.txt.",
    "不要读取文件，只使用 file_ops 查看是否存在。",
    "Only use file_ops and command_exec to read inventory.txt.",
])
def test_read_choice_does_not_invent_scope_for_writes_denials_or_multiple_tools(tmp_path, prompt):
    agent = make_agent(tmp_path)
    agent.mode = 'reverie'
    agent.messages = [{'role': 'user', 'content': prompt}]
    assert agent._explicit_file_read_native_tool_choice([{'function': {'name': 'file_ops'}}]) is None


@pytest.mark.parametrize("prompt", [
    "修复 reverie/tools/render_view.py 的代码并添加回归测试。",
    "Analyze src/app.ts, then create a diagram with create_file and render_view.",
])
def test_real_repository_changes_with_view_tool_names_still_require_retrieval(tmp_path, prompt):
    agent = make_agent(tmp_path)
    agent.mode = "reverie"
    agent.messages = [{"role": "user", "content": prompt}]
    tools = [{"type": "function", "function": {"name": "codebase-retrieval"}}]
    assert agent._native_tool_choice(tools) == {"type": "function", "function": {"name": "codebase-retrieval"}}
