"""Provider cooldowns must survive both SDK and direct HTTP error paths."""
from types import SimpleNamespace

import pytest
import requests

from reverie.agent import agent as module


@pytest.mark.parametrize("header,expected", [("12", 12), ("0", 1), ("bad", 1), ("-5", 1)])
def test_sdk_retry_respects_provider_cooldown(monkeypatch, header, expected):
    agent = module.ReverieAgent.__new__(module.ReverieAgent)
    agent.api_max_retries, agent.api_initial_backoff = 1, 1
    error = requests.HTTPError(response=SimpleNamespace(headers={"Retry-After": header}))
    error.status_code = 429
    calls, delays = [], []

    def call():
        calls.append(True)
        if len(calls) == 1:
            raise error
        return "ok"

    monkeypatch.setattr(module, "interruptible_sleep", delays.append)
    assert agent._retry_provider_call(call) == "ok"
    assert delays == [expected]
    assert len(calls) == 2


def test_direct_http_retry_respects_provider_cooldown(monkeypatch):
    limited = requests.Response()
    limited.status_code = 429
    limited.headers["Retry-After"] = "12"
    limited._content = b'{"error":"slow down"}'
    ok = requests.Response()
    ok.status_code = 200
    responses = iter([limited, ok])
    delays = []
    monkeypatch.setattr(module, "provider_post", lambda *a, **kw: next(responses))
    monkeypatch.setattr(module, "interruptible_sleep", delays.append)
    assert module.make_api_request_with_retry(
        "https://example.invalid/v1/chat/completions", {},
        {"model": "fixture", "messages": [{"role": "user", "content": "hello"}]},
        max_retries=1,
    ) is ok
    assert delays == [12]


def test_http_date_cooldown_uses_clock_and_never_shortens_backoff(monkeypatch):
    monkeypatch.setattr(module.time, "time", lambda: 0)
    error = SimpleNamespace(response=SimpleNamespace(headers={"retry-after": "Thu, 01 Jan 1970 00:00:20 GMT"}))
    assert module._api_retry_delay(0, 1, error) == 20
    assert module._api_retry_delay(0, 30, error) == 30


@pytest.mark.parametrize("header,expected_calls", [("30", 2), ("", 1)])
def test_402_only_retries_when_service_explicitly_offers_cooldown(monkeypatch, header, expected_calls):
    agent = module.ReverieAgent.__new__(module.ReverieAgent)
    agent.api_max_retries, agent.api_initial_backoff = 1, 1
    error = requests.HTTPError(response=SimpleNamespace(headers={"Retry-After": header}))
    error.status_code = 402
    calls, delays = [], []

    def fail():
        calls.append(True)
        raise error

    monkeypatch.setattr(module, "interruptible_sleep", delays.append)
    with pytest.raises(requests.HTTPError):
        agent._retry_provider_call(fail)
    assert len(calls) == expected_calls
    assert delays == ([30] if header else [])


def test_anonymous_chat_does_not_require_sdk_credentials(tmp_path):
    agent = module.ReverieAgent(
        base_url="https://example.invalid/v1", api_key="", model="anonymous",
        project_root=tmp_path, provider="openai-chat",
    )
    assert agent._should_use_openai_http_fallback()


def test_stop_interrupts_a_long_provider_cooldown():
    import threading
    import time
    from reverie.desktop_control import RunControl
    from reverie.provider_transport import request_scope

    agent = module.ReverieAgent.__new__(module.ReverieAgent)
    agent.api_max_retries, agent.api_initial_backoff = 1, 1
    error = requests.HTTPError(response=SimpleNamespace(headers={"Retry-After": "3600"}))
    error.status_code = 429
    control = RunControl(lambda event: None)
    entered = threading.Event()
    calls = []

    def fail():
        calls.append(True)
        entered.set()
        raise error

    def stop():
        entered.wait(2)
        control.stop()

    worker = threading.Thread(target=stop)
    worker.start()
    started = time.monotonic()
    try:
        with request_scope(control), pytest.raises(RuntimeError, match="stopped by user"):
            agent._retry_provider_call(fail)
    finally:
        worker.join(2)
    assert time.monotonic() - started < 2
    assert len(calls) == 1


@pytest.mark.parametrize('status', [400, 401, 403, 503])
def test_http_errors_do_not_silently_remove_tools_and_their_history(monkeypatch, status):
    response = requests.Response()
    response.status_code = status
    response._content = b'{"error":{"message":"messages validation failed"}}'
    calls = []

    def post(*args, **kwargs):
        calls.append(kwargs['json'])
        return response

    monkeypatch.setattr(module, 'provider_post', post)
    tools = [{'type': 'function', 'function': {'name': 'create_file', 'parameters': {'type': 'object'}}}]
    with pytest.raises(requests.HTTPError):
        module.make_api_request_with_retry('https://example.invalid/v1/chat/completions', {},
            {'model': 'fixture', 'messages': [{'role': 'user', 'content': 'hello'}], 'tools': tools}, max_retries=0)
    assert len(calls) == 1
    assert calls[0]['tools'] == tools


@pytest.mark.parametrize('mode', ['recover', 'exhausted', 'genuine-empty-choice', 'genuine-reasoning-choice'])
def test_empty_wire_retry_preserves_the_actual_http_payload_and_history(tmp_path, monkeypatch, mode):
    import copy
    import json
    import threading
    from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

    done = b'data: [DONE]\n\n'
    response = b'data: {"choices":[{"delta":{"content":"ok"},"finish_reason":"stop"}]}\n\ndata: [DONE]\n\n'
    genuine = b'data: {"choices":[{"delta":{},"finish_reason":"stop"}]}\n\ndata: [DONE]\n\n'
    reasoning = b'data: {"choices":[{"delta":{"reasoning_content":"native reasoning"},"finish_reason":"stop"}]}\n\ndata: [DONE]\n\n'
    bodies = []
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass
        def do_POST(self):
            bodies.append(self.rfile.read(int(self.headers['Content-Length'])))
            wire = reasoning if mode == 'genuine-reasoning-choice' else genuine if mode == 'genuine-empty-choice' else (response if mode == 'recover' and len(bodies) > 1 else done)
            self.send_response(200)
            self.send_header('Content-Type', 'text/event-stream')
            self.send_header('Content-Length', str(len(wire)))
            self.end_headers()
            self.wfile.write(wire)

    server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
    worker = threading.Thread(target=server.serve_forever, daemon=True)
    worker.start()
    try:
        agent = module.ReverieAgent(base_url=f'http://127.0.0.1:{server.server_port}/v1/chat/completions',
            api_key='', model='fixture', project_root=tmp_path, provider='openai-chat', runtime_surface='desktop')
        agent.api_max_retries, agent.api_initial_backoff = 1, 0
        sleeps, retries = [], []
        monkeypatch.setattr(module, 'interruptible_sleep', sleeps.append)
        monkeypatch.setattr(agent, '_emit_api_retry_event', lambda **event: retries.append(event))
        original_history = copy.deepcopy(agent.messages)
        tools = agent.get_visible_tool_schemas()
        # A bare agent also exposes optional MCP resource helpers. Preserve its
        # entire actual surface rather than narrowing it to the native profile.
        assert len(tools) >= 27
        assert {'render_view', 'command_exec', 'browser_controler'} <= {t['function']['name'] for t in tools}
        payload = {'model': 'fixture', 'stream': True, 'tools': tools, 'messages': [
            {'role': 'user', 'content': 'Keep the active task'},
            {'role': 'assistant', 'reasoning_content': 'retain native reasoning', 'content': 'working'},
        ]}
        original_payload = copy.deepcopy(payload)
        stream = agent._make_direct_request(payload, stream=True)
        if mode == 'exhausted':
            with pytest.raises(module.EmptyProviderStreamError, match='empty-provider-stream'):
                list(agent._iter_request_stream_with_empty_retry(stream, payload, 'fixture'))
        else:
            events = list(agent._iter_request_stream_with_empty_retry(stream, payload, 'fixture'))
            assert any(e['type'] == 'finish' for e in events)
            assert any(e.get('text') == 'ok' for e in events) is (mode == 'recover')
            if mode == 'genuine-reasoning-choice':
                assert any(e['type'] == 'reasoning' and e['text'] == 'native reasoning' for e in events)
        expected = 1 if mode.startswith('genuine-') else 2
        assert len(bodies) == expected
        assert all(body == bodies[0] for body in bodies)
        assert all(json.loads(body) == original_payload for body in bodies)
        assert len(retries) == len(sleeps) == expected - 1
        assert payload == original_payload and agent.messages == original_history
        assert not (tmp_path / 'index.html').exists()
    finally:
        server.shutdown()
        server.server_close()
        worker.join(2)


def test_stop_interrupts_empty_wire_backoff_before_another_request(monkeypatch):
    import io
    import time
    from reverie.desktop_control import RunControl
    from reverie.provider_transport import request_scope
    agent = module.ReverieAgent.__new__(module.ReverieAgent)
    agent.api_max_retries, agent.api_initial_backoff, agent.model = 1, 30, 'fixture'
    agent.messages = [{'role': 'user', 'content': 'active task'}]
    response = requests.Response()
    response.status_code = 200
    response.headers['Content-Type'] = 'text/event-stream'
    response.raw = io.BytesIO(b'data: [DONE]\n\n')
    control = RunControl(lambda _event: None)
    monkeypatch.setattr(agent, '_emit_api_retry_event', lambda **_event: control.stop())
    def unexpected(*args, **kwargs):
        raise AssertionError('Stopped empty stream must not send another request')
    monkeypatch.setattr(agent, '_make_direct_request', unexpected)
    started = time.monotonic()
    with request_scope(control), pytest.raises(RuntimeError, match='stopped by user'):
        list(agent._iter_request_stream_with_empty_retry(response, {'model':'fixture'}, 'fixture'))
    assert time.monotonic() - started < 2
    assert agent.messages == [{'role': 'user', 'content': 'active task'}]
