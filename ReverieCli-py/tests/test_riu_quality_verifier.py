"""Verifier fixtures only; these are never real-model generation samples."""
import importlib.util
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
import threading
import time

import requests
import pytest

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location("riu_quality_benchmark", ROOT / "scripts/verification/riu_quality_benchmark.py")
benchmark = importlib.util.module_from_spec(spec)
spec.loader.exec_module(benchmark)


@pytest.mark.parametrize(('source', 'url_field'), [('sensenova', 'api_url'), ('nvidia', 'api_url')])
def test_model_recorder_preserves_original_provider_settings(source, url_field):
    from types import SimpleNamespace

    original = SimpleNamespace(**{source: {url_field: 'https://example.invalid/v1', 'api_key': 'fixture-key', 'reasoning_effort': 'high'}})
    isolated = SimpleNamespace()
    benchmark.configure_model_source(isolated, original, source, 'exact-model-id')
    benchmark.configure_model_source(isolated, original, source, 'exact-model-id', recorder_url='http://127.0.0.1:12345/v1')
    assert isolated.active_model_source == source
    assert getattr(isolated, source)['selected_model_id'] == 'exact-model-id'
    assert getattr(isolated, source)[url_field] == 'http://127.0.0.1:12345/v1'
    assert getattr(isolated, source)['reasoning_effort'] == 'high'
    assert getattr(original, source)[url_field] == 'https://example.invalid/v1'
    assert 'selected_model_id' not in getattr(original, source)


def test_sensenova_recorder_url_reaches_the_actual_runtime_model():
    from reverie.config import Config
    original = Config()
    original.sensenova.update(api_key='fixture-key', selected_model_id='sensenova-6.8-flash-lite')
    isolated = Config()
    benchmark.configure_model_source(isolated, original, 'sensenova', 'sensenova-6.8-flash-lite', recorder_url='http://127.0.0.1:12345/v1')
    assert isolated.active_model.base_url == 'http://127.0.0.1:12345/v1'
    assert original.sensenova['api_url'] != isolated.active_model.base_url


def test_registration_without_business_checks_is_not_quality_success():
    assert benchmark.quality_outcome([], [], 0, generation_only=True) == 'registered_unvalidated'
    assert benchmark.quality_outcome([], [], 0) == 'semantic_failure'
    assert benchmark.quality_outcome([{'passed': False}], [], 1) == 'semantic_failure'
    assert benchmark.quality_outcome([{'passed': True}], [], 1) == 'repaired_success'


def test_natural_tasks_do_not_invent_an_explicit_tool_allowlist():
    task = {'id': 'calculator'}
    fixture = {'forbidden_tools': ['web_fetch']}
    assert benchmark.tool_scope_violations(['file_ops', 'render_view'], fixture, task) == []
    assert benchmark.tool_scope_violations(['web_fetch'], fixture, task) == ['web_fetch']
    assert benchmark.tool_scope_violations(['file_ops'], {}, task) == ['file_ops']


def test_turn_completion_requires_own_execution_lease_to_be_released():
    events = [{"event": {"type": "executors.changed", "entries": [
        {"sessionId": "target", "state": "running"},
    ]}}]
    assert benchmark.execution_state(events, "target") == (True, True)
    # An unrelated event or a transient UI stop-button change cannot finish a turn.
    events.append({"event": {"type": "reasoning.delta", "delta": "still generating"}})
    assert benchmark.execution_state(events, "target") == (True, True)
    events.append({"event": {"type": "executors.changed", "entries": [{"sessionId": "other"}]}})
    assert benchmark.execution_state(events, "target") == (True, False)
    assert benchmark.execution_state(events[2:], "target") == (False, False)


def test_empty_event_history_is_not_a_completed_turn():
    assert benchmark.execution_state([], "target") == (False, False)


def test_event_capture_is_reinstalled_after_document_reload():
    class Page:
        def __init__(self):
            self.document = {}
            self.installs = 0

        def evaluate(self, script):
            if '__qualityEvents=[]' in script:
                self.document['events'] = []
                self.installs += 1

    page = Page()
    benchmark.start_event_capture(page)
    page.document.clear()  # Reload destroys globals and the prior subscription.
    benchmark.start_event_capture(page)
    assert page.document['events'] == []
    assert page.installs == 2


@pytest.mark.parametrize('has_clear', [False, True])
def test_table_checks_continue_after_missing_clear_and_select_explicit_descending(monkeypatch, has_clear):
    from types import SimpleNamespace

    state = {'keyword': '', 'stock': False, 'descending': False}

    class Locator:
        def __init__(self, actions=()):
            self.actions = actions
            self.first = self

        def count(self):
            return len(self.actions)

        def click(self):
            if not self.actions:
                raise LookupError('Missing required control')
            self.actions[0]()

    class Frame:
        def locator(self, _selector):
            def text():
                names = ['笔记本', '水杯', '收纳盒', '台灯']
                if state['descending']:
                    names.reverse()
                names = [name for name in names if state['keyword'] in name and not (state['stock'] and name == '台灯')]
                return ' '.join(names) or '没有匹配商品'
            return SimpleNamespace(inner_text=text)

        def get_by_label(self, _label):
            return SimpleNamespace(first=SimpleNamespace(count=lambda: 1,
                check=lambda: state.update(stock=True), uncheck=lambda: state.update(stock=False)))

        def get_by_role(self, role, name=None):
            if role == 'combobox':
                return Locator()
            choices = [('价格升序', lambda: state.update(descending=False)),
                       ('价格降序', lambda: state.update(descending=True))]
            if has_clear:
                choices.append(('清除筛选', lambda: state.update(keyword='')))
            return Locator([action for label, action in choices if name.search(label)])

        def evaluate(self, _script):
            return True

    field = SimpleNamespace(wait_for=lambda **_kw: None, input_value=lambda: state['keyword'],
                            focus=lambda: None, evaluate=lambda *_args: True)
    monkeypatch.setattr(benchmark, 'control', lambda *_args: field)
    monkeypatch.setattr(benchmark, 'change', lambda _field, value: state.update(keyword=value))
    recorded = []
    benchmark.semantic_checks(Frame(), {'id': 'table', 'control': '关键词'}, record=recorded.append)
    by_name = {item['name']: item['passed'] for item in recorded}
    assert by_name['clear-filter-action'] is has_clear
    assert by_name['sort-descending']
    assert by_name['stock-filter']
    assert by_name['keyboard-focus']


def test_semantic_checks_keep_completed_assertions_when_a_later_control_is_missing(monkeypatch):
    from types import SimpleNamespace
    import playwright.sync_api
    body = SimpleNamespace(inner_text=lambda: "年度费用 3168")
    frame = SimpleNamespace(locator=lambda selector: body)
    field = SimpleNamespace(wait_for=lambda **kwargs: None, input_value=lambda: "22")
    monkeypatch.setattr(benchmark, "control", lambda *_args: field)
    monkeypatch.setattr(playwright.sync_api, "expect", lambda _body: SimpleNamespace(to_contain_text=lambda *args, **kwargs: None))
    recorded = []
    with pytest.raises(AttributeError):
        benchmark.semantic_checks(frame, {"id": "calculator", "control": "天数", "initial": 3168}, modified=True, record=recorded.append)
    assert recorded == [{"name": "initial-business-result", "passed": True, "detail": "年度费用 3168"}]


@pytest.mark.parametrize('changed', [2880, 2880.0])
def test_zero_result_cannot_pass_only_because_a_static_hint_contains_zero(monkeypatch, changed):
    from types import SimpleNamespace
    import playwright.sync_api

    field = SimpleNamespace(value='22', wait_for=lambda **kwargs: None,
                            input_value=lambda: field.value, focus=lambda: None,
                            evaluate=lambda *_args: True)
    result = ['3168']
    body = SimpleNamespace(inner_text=lambda: '允许0天，负数不能输入。年度费用 ' + result[0])
    frame = SimpleNamespace(locator=lambda *_args: body, evaluate=lambda *_args: True)

    def change(_field, value):
        field.value = value
        if value == '20':
            result[0] = '2880'
        # Deliberate fixture defect: the displayed result does not update at zero.
        return value

    def assert_amount(pattern, **_kwargs):
        assert pattern.search(body.inner_text())

    def wait_for_function(_function, *, arg, **_kwargs):
        if len(__import__('re').findall(arg['pattern'], body.inner_text())) <= arg['count']:
            raise playwright.sync_api.TimeoutError('No changed numerical result')

    frame.wait_for_function = wait_for_function
    monkeypatch.setattr(benchmark, 'control', lambda *_args: field)
    monkeypatch.setattr(benchmark, 'change', change)
    monkeypatch.setattr(playwright.sync_api, 'expect', lambda _body: SimpleNamespace(to_contain_text=assert_amount))
    checks, _ = benchmark.semantic_checks(frame, {'id': 'calculator', 'control': '天数', 'initial': 3168, 'changed': changed, 'value': '20'})
    assert next(c for c in checks if c['name'] == 'local-recalculation')['passed']
    assert not next(c for c in checks if c['name'] == 'zero-state')['passed']


def test_recorder_forwards_a_partial_http_chunk_without_buffering_the_turn(tmp_path, monkeypatch):
    monkeypatch.setenv("NO_PROXY", "127.0.0.1,localhost")
    first = b'data: {"choices":[{"delta":{"content":"first"}}]}\n\n'
    second = b'data: {"choices":[{"delta":{"content":"second"}}]}\n\n'
    delivered = threading.Event()

    class Upstream(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"

        def log_message(self, *args):
            pass

        def do_POST(self):
            self.rfile.read(int(self.headers["Content-Length"]))
            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream")
            self.send_header("Transfer-Encoding", "chunked")
            self.end_headers()
            self.wfile.write(f"{len(first)+len(second):x}\r\n".encode() + first)
            self.wfile.flush()
            # A buffered recorder cannot expose first until this timeout expires.
            delivered.wait(2)
            self.wfile.write(second + b"\r\n0\r\n\r\n")
            self.wfile.flush()

    server = ThreadingHTTPServer(("127.0.0.1", 0), Upstream)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    recorder = benchmark.Recorder(tmp_path, f"http://127.0.0.1:{server.server_port}", "")
    try:
        started = time.perf_counter()
        with requests.post(f"http://127.0.0.1:{recorder.server.server_port}", json={"model": "transport-fixture", "messages": []}, stream=True, timeout=5) as response:
            lines = response.iter_lines(chunk_size=1)
            assert next(lines) == first.splitlines()[0]
            assert time.perf_counter()-started < 1.5
            delivered.set()
            list(lines)
    finally:
        delivered.set()
        recorder.close()
        server.shutdown()
        server.server_close()
    assert (tmp_path / "request-0000.sse").read_bytes() == first + second


def test_recorder_does_not_turn_an_upstream_transport_failure_into_clean_eof(tmp_path, monkeypatch):
    monkeypatch.setenv("NO_PROXY", "127.0.0.1,localhost")
    first = b'data: {"choices":[{"delta":{"content":"partial"}}]}\n\n'

    class BrokenUpstream(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"

        def log_message(self, *args):
            pass

        def do_POST(self):
            self.rfile.read(int(self.headers["Content-Length"]))
            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream")
            self.send_header("Transfer-Encoding", "chunked")
            self.end_headers()
            self.wfile.write(b"1000\r\n" + first)
            self.wfile.flush()
            self.close_connection = True

    server = ThreadingHTTPServer(("127.0.0.1", 0), BrokenUpstream)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    recorder = benchmark.Recorder(tmp_path, f"http://127.0.0.1:{server.server_port}", "")
    try:
        with requests.post(f"http://127.0.0.1:{recorder.server.server_port}", json={"model": "broken-transport-fixture"}, stream=True, timeout=5) as response:
            with pytest.raises(requests.exceptions.ChunkedEncodingError):
                list(response.iter_content(chunk_size=1))
    finally:
        recorder.close()
        server.shutdown()
        server.server_close()
    assert recorder.records[0]['transport_error'].startswith('ProtocolError:')
