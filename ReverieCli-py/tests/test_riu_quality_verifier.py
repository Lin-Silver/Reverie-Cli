"""Verifier fixtures only; these are never real-model generation samples."""
import importlib.util
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
import threading
import time
import subprocess
import shutil

import requests
import pytest

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location("riu_quality_benchmark", ROOT / "scripts/verification/riu_quality_benchmark.py")
benchmark = importlib.util.module_from_spec(spec)
spec.loader.exec_module(benchmark)


@pytest.fixture(scope='module')
def verifier_browser():
    """Real DOM regressions for the external verifier, never model quality samples."""
    from playwright.sync_api import sync_playwright
    executable = shutil.which('chromium') or shutil.which('chromium-browser')
    if not executable:
        pytest.skip('Chromium is needed for verifier DOM regression fixtures')
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(executable_path=executable, headless=True, chromium_sandbox=True)
        yield browser
        browser.close()


def test_registered_frame_can_appear_in_restored_pip_after_its_inline_anchor(verifier_browser):
    page = verifier_browser.new_page()
    try:
        page.set_content('''<section class=interactive-view-anchor style="min-height:100px" data-view-key="scope:session:vlate:1"></section>
            <div id=portal></div><script>window.inlineClicks=0;
            setTimeout(()=>{
                const portal=document.getElementById('portal');
                portal.innerHTML='<button data-view-mode="inline">Return</button><iframe data-view-id="vlate" src="about:blank"></iframe>';
                portal.querySelector('button').onclick=()=>{
                    window.inlineClicks++;
                    document.querySelector('section').appendChild(portal.querySelector('iframe'));
                };
            },200);</script>''')
        iframe, frame = benchmark.wait_for_registered_view_frame(page, ('vlate', 1), timeout_ms=3000)
        assert page.evaluate('inlineClicks') == 1
        assert iframe.evaluate('e=>e.parentElement.matches(".interactive-view-anchor")')
        assert frame.locator('body').is_visible()
    finally:
        page.close()


@pytest.mark.parametrize('static_help,lower,expected', [(False, 1, True), (True, 1, False), (False, -2, False)])
def test_negative_input_understands_new_excluding_bounds_without_accepting_static_or_inclusive_help(
    verifier_browser, static_help, lower, expected,
):
    page = verifier_browser.new_page()
    try:
        page.set_content('''<label>月数<input type="number" value="12"></label><p id="error"></p>
            <script>const input=document.querySelector('input'),error=document.querySelector('#error');
            function render(){error.textContent=STATIC||Number(input.value)<0?'月数必须在 LOWER-12 之间':'';}
            input.addEventListener('input',render);render();</script>'''
            .replace('STATIC', 'true' if static_help else 'false').replace('LOWER', str(lower)))
        result = benchmark.check_negative_input(page, page.get_by_label('月数'))
        assert result['passed'] is expected
    finally:
        page.close()


def test_calculator_negative_probes_start_from_valid_values_after_zero_boundary(verifier_browser):
    page = verifier_browser.new_page()
    try:
        page.set_content('''<label>票价<input id="fare" type="number" value="6"></label>
            <label>天数<input id="days" type="number" value="20"></label>
            <label>月数<input id="months" type="number" value="12"></label>
            <output aria-label="年度费用"></output><p id="error"></p><script>
            const fare=document.querySelector('#fare'),days=document.querySelector('#days'),months=document.querySelector('#months');
            function render(){
              const invalid=Number(months.value)<1;
              months.setAttribute('aria-invalid',String(invalid));
              document.querySelector('#error').textContent=invalid?'月数必须在1-12之间':'';
              document.querySelector('output').textContent=String(Math.max(0,Number(fare.value))*Math.max(0,Number(days.value))*Math.max(0,Number(months.value)));
            }
            document.querySelectorAll('input').forEach(e=>e.addEventListener('input',render));render();</script>''')
        checks, _ = benchmark.semantic_checks(page, {'id': 'calculator', 'control': '天数',
            'initial': 1440, 'changed': 864, 'value': '12'})
        assert next(c for c in checks if c['name'] == 'months-invalid-input')['passed']
    finally:
        page.close()


def test_fresh_quality_workspace_has_its_own_repository_instructions(tmp_path):
    from reverie.context_engine.workspace import detect_workspace_profile

    outer = tmp_path / 'unrelated-repository'
    outer.mkdir()
    subprocess.run(['git', 'init', '--quiet', str(outer)], check=True)
    (outer / 'README.md').write_text('Unrelated project says interactive views are unavailable.')
    workspace = outer / 'evidence' / 'workspace'
    workspace.mkdir(parents=True)
    assert Path(detect_workspace_profile(workspace).vcs_root) == outer

    evidence = benchmark.prepare_isolated_workspace(workspace)
    profile = detect_workspace_profile(workspace)
    assert Path(profile.vcs_root) == workspace
    assert not profile.instruction_layers
    assert evidence['vcs_root'] == str(workspace)
    assert (outer / 'README.md').read_text().startswith('Unrelated project')


def test_quality_workspace_refuses_to_reinitialize_existing_sample(tmp_path):
    (tmp_path / 'old-output.html').write_text('preserved output')
    with pytest.raises(ValueError, match='empty'):
        benchmark.prepare_isolated_workspace(tmp_path)
    assert (tmp_path / 'old-output.html').read_text() == 'preserved output'


def test_feedback_repair_retains_failed_stage_and_counts_feedback_not_tool_calls():
    case, submitted = {'stages': [], 'repair_count': 0}, []

    def send(prompt, stage):
        submitted.append((prompt, stage))
        return {'tool_calls': ['create_file', 'create_file', 'render_view']}

    def assess(saved, stage, record):
        record({'name': 'initial-business-result', 'passed': len(submitted) == 2})
        return {'registered': True}

    saved, value, checks = benchmark.run_quality_stage(case, 'generation', 'natural task', send, assess, 2)
    assert case['repair_count'] == 1
    assert [s['passed'] for s in case['stages']] == [False, True]
    assert case['stages'][0]['checks'][0]['passed'] is False
    assert checks[0]['passed'] is True and value['registered']
    assert 'create_file' not in submitted[1][0] and 'render_view' not in submitted[1][0]


def test_feedback_budget_is_shared_by_generation_and_modification():
    case, submitted = {'stages': [], 'repair_count': 1}, []

    def send(prompt, stage):
        submitted.append(stage)
        return None

    def assess(saved, stage, record):
        record({'name': 'live-host-theme', 'passed': False})

    benchmark.run_quality_stage(case, 'modification', 'natural change', send, assess, 2)
    assert len(submitted) == 2
    assert case['repair_count'] == 2
    assert all(not s['passed'] for s in case['stages'])


def test_transport_failure_does_not_trigger_semantic_feedback_retries():
    case = {'stages': [], 'repair_count': 0}

    def send(prompt, stage):
        raise RuntimeError('upstream protocol error')

    with pytest.raises(RuntimeError, match='upstream protocol'):
        benchmark.run_quality_stage(case, 'generation', 'task', send, None, 2)
    assert len(case['stages']) == 1 and case['repair_count'] == 0
    assert 'upstream protocol' in case['stages'][0]['error']


def test_restored_inputs_do_not_hide_a_stale_visible_total():
    from types import SimpleNamespace

    checks = []
    frame = SimpleNamespace(locator=lambda selector: SimpleNamespace(inner_text=lambda: '总价：200.00元'))
    benchmark.check_restored_business_result(frame, {'id': 'form'}, '3', checks.append)
    assert checks[0]['passed'] is False
    assert checks[0]['detail']['expected'] == 300
    frame = SimpleNamespace(locator=lambda selector: SimpleNamespace(inner_text=lambda: '总价：300.00元'))
    benchmark.check_restored_business_result(frame, {'id': 'form'}, '3', checks.append)
    assert checks[1]['passed'] is True


def test_static_selection_heading_is_not_selected_route_feedback():
    assert not benchmark.selection_feedback('当前选择：未选择\n山谷 120元\n选择')
    assert benchmark.selection_feedback('当前选择：山谷，120元') == ['当前选择：山谷，120元']


@pytest.mark.parametrize(('source', 'url_field'), [('sensenova', 'api_url'), ('nvidia', 'api_url'), ('opencode', 'api_url')])
def test_model_recorder_preserves_original_provider_settings(source, url_field):
    from types import SimpleNamespace

    original = SimpleNamespace(**{source: {url_field: 'https://example.invalid/v1', 'api_key': 'fixture-key', 'reasoning_effort': 'high'}})
    isolated = SimpleNamespace()
    benchmark.configure_model_source(isolated, original, source, 'exact-model-id', api_url='https://new-route.invalid/v1')
    assert getattr(isolated, source)[url_field] == 'https://new-route.invalid/v1'
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


@pytest.mark.parametrize('outcome', ['first_pass', 'repaired_success', 'model_violation'])
def test_recovered_service_errors_do_not_replace_the_observed_quality_verdict(outcome):
    case = {'outcome': outcome, 'requests': [{'upstream_stream_error': {'message': 'transient'}},
            {'transport_error': 'interrupted upstream'}, {'status': 200, 'sse_done': True}]}
    benchmark.record_service_incidents(case)
    assert case['outcome'] == outcome
    assert case['upstream_stream_errors'] == [{'message': 'transient'}]
    assert case['transport_incidents'] == ['interrupted upstream']


def test_unrecovered_upstream_error_and_local_disconnect_have_distinct_attribution():
    case = {'outcome': 'validator_or_product_error', 'requests': [
        {'transport_error': 'client closed', 'transport_error_origin': 'downstream'}]}
    benchmark.record_service_incidents(case)
    assert case['outcome'] == 'validator_or_product_error'
    assert not case['transport_incidents'] and case['downstream_disconnects'] == ['client closed']
    case['requests'].append({'upstream_stream_error': {'message': 'provider unavailable'}})
    benchmark.record_service_incidents(case)
    assert case['outcome'] == 'service_unavailable'


def test_unregistered_modification_fails_without_waiting_for_absent_controls(monkeypatch):
    def unexpected(*args, **kwargs):
        raise AssertionError('The old view cannot contain the requested new controls')

    monkeypatch.setattr(benchmark, 'semantic_checks', unexpected)
    checks = []
    benchmark.check_modified_view(None, {'id': 'table'}, ('view', 1), ('view', 1), checks.append)
    assert checks == [{'name': 'modified-view-registration', 'passed': False,
                       'detail': 'No new view revision was registered after the modification.'}]


def test_registered_modification_still_runs_business_checks(monkeypatch):
    checks, calls = [], []

    def validate(frame, task, *, modified, record):
        calls.append((frame, task, modified))
        record({'name': 'price-filter', 'passed': False})

    monkeypatch.setattr(benchmark, 'semantic_checks', validate)
    task = {'id': 'table'}
    benchmark.check_modified_view('real-frame', task, ('view', 1), ('view', 2), checks.append)
    assert calls == [('real-frame', task, True)]
    assert checks == [{'name': 'modified-price-filter', 'passed': False}]


def test_missing_accessible_business_control_is_an_explicit_quality_failure(monkeypatch):
    from types import SimpleNamespace
    from playwright.sync_api import TimeoutError

    def unavailable(**kwargs):
        raise TimeoutError('No accessible label for the required input')

    monkeypatch.setattr(benchmark, 'control', lambda *args: SimpleNamespace(wait_for=unavailable))
    checks = []
    with pytest.raises(benchmark.MissingBusinessControl, match='倍率'):
        benchmark.semantic_checks(None, {'control': '倍率'}, record=checks.append)
    assert checks[0]['name'] == 'required-accessible-control'
    assert checks[0]['passed'] is False


def test_pointer_actions_wait_for_parent_and_component_paints_after_relocation(verifier_browser):
    page = verifier_browser.new_page(viewport={'width': 800, 'height': 600})
    try:
        page.set_content('<div style="height:3000px"></div><iframe srcdoc="<p>Actual child</p>"></iframe>')
        element = page.locator('iframe')
        frame = element.element_handle().content_frame()
        frame.locator('body').wait_for(state='attached')
        assert element.bounding_box()['y'] > 600
        frame.evaluate('''() => {
            window.paintTicks = 0;
            const tick = () => { window.paintTicks++; requestAnimationFrame(tick); };
            requestAnimationFrame(tick);
        }''')
        identity = frame.evaluate('performance.timeOrigin')
        benchmark.settle_view(page, frame)
        bounds = element.bounding_box()
        assert 0 <= bounds['y'] and bounds['y'] + bounds['height'] <= 602
        assert frame.evaluate('window.paintTicks') >= 2
        assert frame.evaluate('performance.timeOrigin') == identity
    finally:
        page.close()


@pytest.mark.parametrize('unpainted', ['Host', 'Component'])
def test_paint_wait_reports_missing_frames_with_a_bounded_deadline(verifier_browser, unpainted):
    page = verifier_browser.new_page()
    try:
        page.set_content('<iframe srcdoc="<p>Child</p>"></iframe>')
        frame = page.locator('iframe').element_handle().content_frame()
        frame.locator('body').wait_for(state='attached')
        target = page if unpainted == 'Host' else frame
        target.evaluate('window.requestAnimationFrame = () => 0')
        started = time.monotonic()
        with pytest.raises(RuntimeError, match=unpainted + ' did not paint twice within 100ms'):
            benchmark.settle_view(page, frame, paint_timeout_ms=100)
        assert time.monotonic() - started < 1.5
    finally:
        page.close()


def test_paint_wait_reports_a_detached_child_instead_of_waiting_forever(verifier_browser):
    from playwright.sync_api import Error
    page = verifier_browser.new_page()
    try:
        page.set_content('<iframe srcdoc="<p>Child</p>"></iframe>')
        frame = page.locator('iframe').element_handle().content_frame()
        frame.locator('body').wait_for(state='attached')
        page.locator('iframe').evaluate('e => e.remove()')
        with pytest.raises(Error, match='detached'):
            benchmark.settle_view(page, frame)
    finally:
        page.close()


def test_paint_scroll_preserves_the_same_document_and_business_values(verifier_browser):
    page = verifier_browser.new_page(viewport={'width': 800, 'height': 600})
    try:
        page.set_content('''<div style="height:3000px"></div><iframe srcdoc='
            <label>Quantity<input type="number" value="0"></label>
            <label>Name<input value=""></label>
            <label>Enabled<input type="checkbox" checked></label>'></iframe>''')
        frame = page.locator('iframe').element_handle().content_frame()
        frame.locator('body').wait_for(state='attached')
        before = benchmark.snapshot_controls(frame)
        identity = frame.evaluate('performance.timeOrigin')
        benchmark.settle_view(page, frame)
        assert benchmark.snapshot_controls(frame) == before
        assert frame.evaluate('performance.timeOrigin') == identity
    finally:
        page.close()


def test_plain_answer_reads_the_real_stored_assistant_role():
    assert benchmark.assistant_text([{'role': 'Reverie', 'content': '3168'},
                                     {'role': 'user', 'content': 'not an answer'}]) == '3168'


def test_recorder_preserves_live_model_selection_for_new_raw_ids(tmp_path, monkeypatch):
    import json
    from reverie.config import Config
    from reverie.desktop_catalog import apply_model_selection

    monkeypatch.setenv('NO_PROXY', '127.0.0.1,localhost')
    raw = b'{"data":[{"id":"new-free-model"}]}'
    paths = []

    class Upstream(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def do_GET(self):
            paths.append(self.path)
            self.send_response(200)
            self.send_header('Content-Length', str(len(raw)))
            self.end_headers()
            self.wfile.write(raw)

    server = ThreadingHTTPServer(('127.0.0.1', 0), Upstream)
    worker = threading.Thread(target=server.serve_forever, daemon=True)
    worker.start()
    recorder = benchmark.Recorder(tmp_path, f'http://127.0.0.1:{server.server_port}/v1/chat/completions', '')
    try:
        cfg = Config()
        cfg.opencode.update(api_url=f'http://127.0.0.1:{recorder.server.server_port}/v1',
                            api_key='', use_builtin_model_catalog=False)
        selected = apply_model_selection(cfg, 'opencode', 'new-free-model')
        assert selected['id'] == 'new-free-model'
        assert cfg.active_model.model == 'new-free-model'
        assert paths == ['/v1/models']
        assert (tmp_path / 'catalog-response.json').read_bytes() == raw
        assert recorder.records == []  # Discovery is not a generation sample.
    finally:
        recorder.close()
        server.shutdown()
        server.server_close()


def test_recorder_forwards_a_separate_provider_catalog_endpoint(tmp_path, monkeypatch):
    monkeypatch.setenv('NO_PROXY', '127.0.0.1,localhost')
    raw, paths = b'{"data":[{"id":"new-free-model"}]}', []

    class Upstream(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def do_GET(self):
            paths.append(self.path)
            self.send_response(200)
            self.send_header('Content-Length', str(len(raw)))
            self.end_headers()
            self.wfile.write(raw)

    server = ThreadingHTTPServer(('127.0.0.1', 0), Upstream)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    base = f'http://127.0.0.1:{server.server_port}'
    recorder = None
    try:
        recorder = benchmark.Recorder(tmp_path, base + '/inference/openai/v1/chat/completions', '',
                                      models_url=base + '/inference/v1/models')
        assert requests.get(f'http://127.0.0.1:{recorder.server.server_port}/v1/models').content == raw
        assert paths == ['/inference/v1/models']
        assert recorder.records == []
    finally:
        if recorder:
            recorder.close()
        server.shutdown()
        server.server_close()


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
@pytest.mark.parametrize('sort_labels', [('价格升序', '价格降序'), ('价格 ↑', '价格 ↓')])
def test_table_checks_continue_after_missing_clear_and_select_explicit_descending(monkeypatch, has_clear, sort_labels):
    from types import SimpleNamespace

    state = {'keyword': '', 'stock': False, 'descending': False}

    class Locator:
        def __init__(self, actions=()):
            self.actions = actions
            self.first = self

        def count(self):
            return len(self.actions)

        def element_handle(self):
            return self

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
                evaluate=lambda _script: 'INPUT',
                check=lambda: state.update(stock=True), uncheck=lambda: state.update(stock=False)))

        def get_by_role(self, role, name=None):
            if role == 'combobox':
                return Locator()
            choices = [(sort_labels[0], lambda: state.update(descending=False)),
                       (sort_labels[1], lambda: state.update(descending=True))]
            if has_clear:
                choices.append(('清除筛选', lambda: state.update(keyword='')))
            return Locator([action for label, action in choices if name.search(label)])

        def evaluate(self, _script):
            return True

    field = SimpleNamespace(wait_for=lambda **_kw: None, input_value=lambda: state['keyword'],
                            focus=lambda: None, evaluate=lambda *_args: True)
    monkeypatch.setattr(benchmark, 'control', lambda *_args: field)
    monkeypatch.setattr(benchmark, 'change', lambda _field, value: state.update(keyword=value))
    monkeypatch.setattr(benchmark, 'result_items', lambda frame, _task: [
        {'name': name} for name in frame.locator('body').inner_text().split()
        if name in ['笔记本', '水杯', '收纳盒', '台灯']])
    recorded = []
    benchmark.semantic_checks(Frame(), {'id': 'table', 'control': '关键词'}, record=recorded.append)
    by_name = {item['name']: item['passed'] for item in recorded}
    assert by_name['clear-filter-action'] is has_clear
    assert by_name['sort-descending']
    assert by_name['stock-filter']
    assert by_name['keyboard-focus']


def test_semantic_checks_keep_completed_assertions_when_a_later_control_is_missing(verifier_browser):
    from playwright.sync_api import TimeoutError as BrowserTimeout
    page=verifier_browser.new_page()
    try:
        page.set_default_timeout(150)
        page.set_content('<label>天数<input type="number" value="22"></label>'
                         '<output aria-label="年度费用">6336.00元</output>')
        recorded=[]
        with pytest.raises(BrowserTimeout):
            benchmark.semantic_checks(page, {'id':'calculator','control':'天数','initial':3168},
                                      modified=True,record=recorded.append)
        assert len(recorded)==1 and recorded[0]['name']=='initial-business-result'
        assert recorded[0]['passed'] and recorded[0]['detail']['primary_result']['candidates'][0]['value']==6336
    finally:
        page.close()


@pytest.mark.parametrize('changed', [2880, 2880.0])
def test_zero_result_cannot_pass_only_because_a_static_hint_contains_zero(verifier_browser,changed):
    page=verifier_browser.new_page()
    try:
        page.set_content('''<label>票价<input id="fare" type="number" value="12"></label>
            <label>天数<input id="days" type="number" value="22"></label>
            <label>月数<input id="months" type="number" value="12"></label>
            <output aria-label="年度费用">3168.00元</output>
            <p>允许0天，负数不能输入。</p><p id="comparison"></p><p id="error"></p>
            <script>
            const fare=document.querySelector('#fare'),days=document.querySelector('#days'),months=document.querySelector('#months');
            function render(){
                const amount=Math.max(0,+fare.value)*Math.max(0,+days.value)*Math.max(0,+months.value);
                document.querySelector('#comparison').textContent='对比参考 '+amount.toFixed(2);
                document.querySelector('#error').textContent=[fare,days,months].some(e=>+e.value<0)?'输入不能为负数':'';
                // Deliberate fixture defect: zero days leaves the primary result stale.
                if(+days.value!==0) document.querySelector('output').textContent=amount.toFixed(2)+'元';
            }
            document.querySelectorAll('input').forEach(e=>e.addEventListener('input',render));render();
            </script>''')
        checks,_=benchmark.semantic_checks(page,{'id':'calculator','control':'天数',
            'initial':3168,'changed':changed,'value':'20'})
        assert next(check for check in checks if check['name']=='local-recalculation')['passed']
        assert not next(check for check in checks if check['name']=='zero-state')['passed']
    finally:
        page.close()


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
    assert recorder.records[0]['transport_error_origin'] == 'upstream'


@pytest.mark.parametrize('failure_point', ['headers', 'body'])
def test_recorder_distinguishes_a_closed_client_from_an_upstream_failure(tmp_path, monkeypatch, failure_point):
    import io
    import json
    from types import SimpleNamespace

    chunk = b'data: {"choices":[{"delta":{"content":"actual bytes"}}]}\n\n'
    chunks = iter([chunk, b''])

    class Response:
        status_code = 200
        headers = {'Content-Type': 'text/event-stream'}
        raw = SimpleNamespace(read1=lambda *_args, **_kwargs: next(chunks))
        def __enter__(self): return self
        def __exit__(self, *_args): pass

    class ClosedClient:
        def write(self, *_args): raise BrokenPipeError('local Desktop disconnected')
        def flush(self): pass

    def closed_headers():
        raise ConnectionResetError('local Desktop closed before headers')

    recorder = benchmark.Recorder(tmp_path, 'https://provider.invalid/v1/chat/completions', '')
    handler = object.__new__(recorder.server.RequestHandlerClass)
    request = json.dumps({'model': 'fixture', 'messages': []}).encode()
    handler.headers = {'Content-Length': str(len(request))}
    handler.rfile = io.BytesIO(request)
    handler.wfile = ClosedClient()
    handler.send_response = handler.send_header = lambda *_args: None
    handler.end_headers = closed_headers if failure_point == 'headers' else lambda: None
    monkeypatch.setattr(requests, 'post', lambda *_args, **_kwargs: Response())
    try:
        handler.do_POST()
    finally:
        recorder.close()
    record = recorder.records[0]
    assert record['status'] == 200
    assert record['transport_error_origin'] == 'downstream'
    assert 'local Desktop' in record['transport_error']
    if failure_point == 'body':
        assert (tmp_path/'request-0000.sse').read_bytes() == chunk


def test_modified_form_checks_required_fields_after_a_previous_valid_submission(monkeypatch):
    from types import SimpleNamespace
    from contextlib import nullcontext
    import playwright.sync_api

    class SubmissionObserved(Exception):
        pass

    class Field:
        def __init__(self, value): self.value = value
        def input_value(self): return self.value
        def fill(self, value): self.value = value
        def wait_for(self, **kwargs): pass
        def count(self): return 1
        def is_visible(self): return True
        def is_enabled(self): return True

    fields = {'人数': Field('3'), '姓名': Field('王小明'), '邮箱': Field('synthetic@example.invalid')}
    attempts = []

    def submit():
        attempts.append((fields['姓名'].value, fields['邮箱'].value))
        raise SubmissionObserved

    button = SimpleNamespace(click=submit)
    body = SimpleNamespace(inner_text=lambda: '总价 300')
    frame = SimpleNamespace(locator=lambda *_args: body,
                            wait_for_function=lambda *_args, **_kwargs: None,
                            get_by_role=lambda *_args, **_kwargs: SimpleNamespace(first=button))
    monkeypatch.setattr(benchmark, 'control', lambda _frame, name: fields[name])
    monkeypatch.setattr(benchmark, 'change', lambda field, value: field.fill(value))
    monkeypatch.setattr(benchmark, 'observe_field_validation', lambda _field: nullcontext())
    monkeypatch.setattr(playwright.sync_api, 'expect', lambda _body: SimpleNamespace(to_contain_text=lambda *_args, **_kwargs: None))
    with pytest.raises(SubmissionObserved):
        benchmark.semantic_checks(frame, {'id': 'form', 'control': '人数', 'initial': 160, 'changed': 240, 'value': '3'}, modified=True)
    assert attempts == [('', '')]


@pytest.mark.parametrize('actual,message,before_marker,after_marker,expected', [
    ('-1', '存在无效输入，请检查红色标记的字段', None, None, True),
    ('-1', '', None, None, False),
    ('-1', '计算完成，数据有效', None, None, False),
    ('0', '', None, None, True),
    ('-1.00', '', None, None, False),
    ('-1', '', None, 'true', True),
    ('-1', '', 'true', 'true', False),
])
def test_negative_input_feedback_does_not_count_static_hints_or_positive_status(
    monkeypatch, actual, message, before_marker, after_marker, expected,
):
    from types import SimpleNamespace
    state = {'changed': False}
    static = '负数不能输入。\n'
    body = SimpleNamespace(inner_text=lambda: static + (message if state['changed'] else '输入为零'))
    field = SimpleNamespace(evaluate=lambda _script: after_marker if state['changed'] else before_marker)
    frame = SimpleNamespace(locator=lambda _selector: body)

    def change(_field, value):
        assert value == '-1'
        state['changed'] = True
        return actual

    monkeypatch.setattr(benchmark, 'change', change)
    feedback = benchmark.check_negative_input(frame, field)
    assert feedback['passed'] is expected
    assert '负数不能输入' not in feedback['new_feedback']


@pytest.mark.parametrize('task,value,modified,expected', [
    ('calculator', '20', False, 2880), ('calculator', '20', True, 5760),
    ('chart', '2', False, 720), ('chart', '2', True, 920),
    ('form', '3', False, 240), ('form', '3', True, 300),
])
def test_generation_and_modified_results_use_their_current_business_values(task, value, modified, expected):
    assert benchmark.expected_business_result({'id': task}, value, modified=modified) == expected


@pytest.mark.parametrize('top,bottom,left,visible,expected', [
    (300, 330, 12, True, True),
    (450, 480, 12, True, False),
    (410, 440, 12, True, False),
    (100, 130, -30, True, False),
    (100, 130, 12, False, False),
])
def test_pip_result_must_be_readable_inside_the_first_viewport(top, bottom, left, visible, expected):
    from types import SimpleNamespace
    box = {'top': top, 'bottom': bottom, 'left': left, 'right': left+80,
           'width': 80, 'height': bottom-top, 'visible': visible}
    locator = SimpleNamespace(evaluate_all=lambda _script: {'width': 398, 'height': 423, 'matches': [box]})
    frame = SimpleNamespace(get_by_text=lambda _pattern: locator)
    assert benchmark.primary_result_in_viewport(frame, 2880)['passed'] is expected


def test_table_result_rows_exclude_static_fixture_notes_but_keep_wrong_rows(verifier_browser):
    page = verifier_browser.new_page()
    try:
        page.set_content('''<table><tr><th>名称</th><th>价格</th></tr>
            <tr><td>台灯</td><td>129元</td></tr></table>
            <footer>数据为示例：水杯39元、台灯129元、笔记本19元、收纳盒59元。</footer>''')
        assert [item['name'] for item in benchmark.result_items(page, 'table')] == ['台灯']
        page.locator('table').evaluate("e=>e.insertAdjacentHTML('beforeend','<tr><td>笔记本</td><td>19元</td></tr>')")
        assert [item['name'] for item in benchmark.result_items(page, 'table')] == ['台灯', '笔记本']
        page.locator('table').evaluate("e=>e.innerHTML='<tr><td>没有匹配的商品</td></tr>'")
        assert benchmark.result_items(page, 'table') == []
    finally:
        page.close()


def test_result_cards_support_different_layout_and_exclude_previous_selection(verifier_browser):
    page = verifier_browser.new_page()
    try:
        page.set_content('''<div><strong>当前选择：山谷，120元，2公里</strong></div>
            <section><div><h3>湖畔路线</h3><p>180元 · 4公里</p><button>选择</button></div>
            <div style="display:none"><h3>城郊</h3>160元 · 8公里<button>选择</button></div></section>
            <p>原始路线：山谷120元，日落220元，城郊160元，湖畔180元。</p>''')
        items = benchmark.result_items(page, 'comparison')
        assert [item['name'] for item in items] == ['湖畔']
        assert page.locator(items[0]['path']).get_by_role('button', name='选择').count() == 1
        page.locator(items[0]['path']).evaluate('e=>e.remove()')
        assert benchmark.result_items(page, 'comparison') == []
    finally:
        page.close()


def test_form_confirmation_cannot_borrow_a_new_price_from_outside_the_confirmation(verifier_browser):
    page = verifier_browser.new_page()
    try:
        page.set_content('''<main><div>当前总价300元，人数3人</div>
            <section role="status">报名成功：王小明，synthetic@example.invalid，3人，总价240元</section></main>''')
        assert not benchmark.submission_confirmation(page, 3, 300)['passed']
        assert benchmark.submission_confirmation(page, 3, 240)['passed']
        page.get_by_role('status').evaluate("e=>e.innerText='报名成功：王小明，synthetic@example.invalid，2人，总价300元'")
        assert not benchmark.submission_confirmation(page, 3, 300)['passed']
        page.get_by_role('status').evaluate("e=>e.innerText='报名成功：王小明，synthetic@example.invalid，3人，总价300元'")
        assert benchmark.submission_confirmation(page, 3, 300)['passed']
    finally:
        page.close()


@pytest.mark.parametrize('reopen', ['none', 'inert', 'working'])
def test_form_confirmation_reenters_through_a_real_action_or_reports_a_semantic_failure(verifier_browser, reopen):
    page = verifier_browser.new_page()
    page.set_default_timeout(1200)
    try:
        page.set_content('''<section id=confirmation>报名成功：王小明，synthetic@example.invalid，3人，总价240元</section>
            <section id=fields hidden><label>人数<input value=3></label><button id=submit>提交报名</button></section>
            <script>document.getElementById('submit').onclick=()=>{
                document.getElementById('fields').hidden=true;
                document.getElementById('confirmation').hidden=false;
            };</script>''')
        if reopen != 'none':
            page.locator('body').evaluate('''(body,working)=>{
                const button=document.createElement('button');button.textContent='编辑信息';
                if(working)button.onclick=()=>{
                    document.getElementById('fields').hidden=false;
                    document.getElementById('confirmation').hidden=true;
                };
                body.append(button);
            }''', reopen == 'working')
        checks = []
        benchmark.submit_form_confirmation(page, modified=False, record=checks.append)
        assert checks[0]['name'] == 'form-reentry-action'
        assert checks[0]['passed'] is (reopen == 'working')
        if reopen == 'working':
            assert checks[-1]['name'] == 'valid-submission' and checks[-1]['passed']
        else:
            assert len(checks) == 1
            assert '再次报名' in benchmark.quality_repair_feedback(checks)
    finally:
        page.close()


def test_form_confirmation_reports_missing_or_disabled_submit_instead_of_timing_out(verifier_browser):
    page = verifier_browser.new_page()
    page.set_default_timeout(1200)
    try:
        page.set_content('<label>人数<input value=3></label><button disabled>提交报名</button>')
        checks = []
        benchmark.submit_form_confirmation(page, modified=False, record=checks.append)
        assert checks == [{'name': 'valid-submission', 'passed': False, 'detail': 'Missing usable submit action.'}]
    finally:
        page.close()


@pytest.mark.parametrize('kind,invalid,valid,message', [
    ('text', '', 'Updated', ''), ('email', 'bad-address', 'synthetic@example.invalid', ''),
    ('number', '0', '3', ''), ('text', 'Too long', 'Fine', 'Use at most 4 characters.'),
])
def test_documented_field_feedback_clears_native_and_custom_errors_without_losing_help(verifier_browser, kind, invalid, valid, message):
    from reverie.agent.system_prompt import build_system_prompt
    helper = build_system_prompt(runtime_surface='desktop').split('### Offline host integration example', 1)[1].split('```javascript\n', 1)[1].split('\n```', 1)[0]
    page = verifier_browser.new_page()
    try:
        page.set_content(f'<label>Value<input required type="{kind}" min=1 max=5 aria-describedby="help hint"></label>'
                         '<p id=help>Help</p><p id=hint>Hint</p><p id=error hidden></p>')
        page.add_script_tag(content=helper)
        field = page.get_by_label('Value')
        field.fill(invalid)
        result = page.evaluate('message=>fieldFeedback(document.querySelector("input"),document.getElementById("error"),{message})', message)
        assert not result and page.locator('#error').is_visible()
        assert field.get_attribute('aria-invalid') == 'true'
        field.fill(valid)
        assert page.evaluate('fieldFeedback(document.querySelector("input"),document.getElementById("error"))')
        assert page.locator('#error').is_hidden()
        assert page.locator('#error').text_content() == ''
        assert field.get_attribute('aria-invalid') == 'false'
        assert field.get_attribute('aria-describedby') == 'help hint error'
        assert field.evaluate('e=>e.validity.valid')
    finally:
        page.close()


def test_documented_field_feedback_defers_messages_and_excludes_disabled_fields(verifier_browser):
    from reverie.agent.system_prompt import build_system_prompt
    helper = build_system_prompt(runtime_surface='desktop').split('### Offline host integration example', 1)[1].split('```javascript\n', 1)[1].split('\n```', 1)[0]
    page = verifier_browser.new_page()
    try:
        page.set_content('<input required><p id=error></p>')
        page.add_script_tag(content=helper)
        assert not page.evaluate('fieldFeedback(document.querySelector("input"),document.getElementById("error"),{show:false})')
        assert page.locator('#error').is_hidden()
        assert page.locator('input').get_attribute('aria-invalid') == 'false'
        page.locator('input').evaluate('e=>e.disabled=true')
        assert page.evaluate('fieldFeedback(document.querySelector("input"),document.getElementById("error"),{message:"old custom error"})')
        assert page.locator('input').evaluate('e=>e.validity.customError') is False
    finally:
        page.close()


@pytest.mark.parametrize('overlay', [False, True])
def test_chart_evidence_requires_real_visible_bars_after_leaving_zero(verifier_browser, overlay):
    page = verifier_browser.new_page()
    try:
        page.set_content('''<style>.plot{position:relative;width:300px;height:180px}
            .bars{display:flex;align-items:end;gap:20px;height:180px}
            .bar{background:blue;width:40px}
            .empty{position:absolute;inset:0;display:flex;background:white}</style>
            <div class="plot"><div role="img" aria-label="每月用水柱状图" class="bars">
            <div class="bar" style="height:120px"></div><div class="bar" style="height:80px"></div>
            <div class="bar" style="height:160px"></div></div>
            <div class="empty" hidden>没有用水数据</div></div>
            <table><tr><td>一月</td><td>240升</td></tr><tr><td>二月</td><td>160升</td></tr>
            <tr><td>三月</td><td>320升</td></tr></table>''')
        if not overlay:
            page.add_style_tag(content='[hidden]{display:none!important}')
        evidence = benchmark.chart_evidence(page, 2, modified=False)
        assert evidence['visible_bars'] is not overlay
        assert evidence['readable_data']
    finally:
        page.close()


def test_chart_readable_detail_must_include_the_added_month_and_scaled_values(verifier_browser):
    page = verifier_browser.new_page()
    try:
        page.set_content('''<p>原始数据：一月120升、二月80升、三月160升、四月100升。</p>
            <table><tr><td>一月</td><td>240升</td></tr><tr><td>二月</td><td>160升</td></tr>
            <tr><td>三月</td><td>320升</td></tr></table>''')
        assert not benchmark.chart_evidence(page, 2, modified=True)['readable_data']
        page.locator('table').evaluate("e=>e.insertAdjacentHTML('beforeend','<tr><td>四月</td><td>200升</td></tr>')")
        assert benchmark.chart_evidence(page, 2, modified=True)['readable_data']
    finally:
        page.close()


@pytest.mark.parametrize('overlay', [False, True])
def test_chart_evidence_accepts_css_gradient_bars_without_forcing_a_dom_template(verifier_browser, overlay):
    page = verifier_browser.new_page()
    try:
        page.set_content('''<section style="position:relative"><div style="display:flex;align-items:end;gap:16px;height:220px">
            <div><span style="display:block;width:40px;height:120px;background:linear-gradient(blue,cyan)">120</span>一月</div>
            <div><span style="display:block;width:40px;height:80px;background:linear-gradient(blue,cyan)">80</span>二月</div>
            <div><span style="display:block;width:40px;height:160px;background:linear-gradient(blue,cyan)">160</span>三月</div>
            </div>'''+('<div style="position:absolute;inset:0;background:white">没有用水数据</div>' if overlay else '')+'</section>')
        evidence=benchmark.chart_evidence(page,1,modified=False)
        assert evidence['visible_bars'] is not overlay
        assert any(plot['css_inferred'] for plot in evidence['plots'])
    finally:
        page.close()


@pytest.mark.parametrize('horizontal', [False, True])
def test_css_zero_state_does_not_mistake_dashboard_cards_for_bars(verifier_browser, horizontal):
    page = verifier_browser.new_page()
    try:
        direction = 'flex-direction:column;align-items:start' if horizontal else 'align-items:end'
        bars = ''.join(f'<div><span style="display:block;background:blue;'
                       f'width:{value if horizontal else 40}px;height:{28 if horizontal else value}px"></span>{month}月</div>'
                       for month, value in [('一', 120), ('二', 80), ('三', 160)])
        page.set_content('''<style>.card{background:#eee;margin-bottom:12px;padding:12px;box-sizing:border-box}
            .stat{background:#ddd;width:calc((100% - 16px)/3);height:66.5px}
            [hidden]{display:none!important}</style><div style="width:380px">
            <div class=card style="height:115.5px"><label>倍率<input type=number value=1></label></div>
            <div style="display:flex;gap:8px;margin-bottom:12px"><div class=stat>总量 360</div>
            <div class=stat>平均 120</div><div class=stat>最高 三月</div></div>
            <div class=card style="height:263px"><div id=bars style="display:flex;gap:16px;height:220px;DIRECTION">BARS</div>
            <p id=empty hidden>没有用水数据</p></div>
            <div class=card style="height:236.5px"><table><tr><td>一月</td><td>120</td></tr>
            <tr><td>二月</td><td>80</td></tr><tr><td>三月</td><td>160</td></tr></table></div></div>
            <script>document.querySelector('input').oninput=e=>{
                document.getElementById('bars').hidden=+e.target.value===0;
                document.getElementById('empty').hidden=+e.target.value!==0;
            };</script>'''.replace('DIRECTION', direction).replace('BARS', bars))
        assert benchmark.chart_evidence(page, 1, modified=False)['visible_bars']
        before = page.locator('body').inner_text()
        page.get_by_label('倍率').fill('0')
        assert not benchmark.chart_evidence(page, 0, modified=False)['visible_bars']
        assert benchmark.chart_zero_state(page, before, [], modified=False)['passed']
    finally:
        page.close()


@pytest.mark.parametrize('total,top,expected', [(720, 20, True), (720, 900, False), (360, 20, False)])
@pytest.mark.parametrize('markup', [
    '<section><span>总用水量 (升)</span><strong>VALUE L</strong></section>',
    '<section><strong>VALUE</strong><span>总量</span></section>',
    '<table><tr><th>合计</th><td>VALUE 升</td></tr></table>',
    '<table><thead><tr><th>月份</th><th>原始用量</th><th>调整后用量</th></tr></thead>'
    '<tbody><tr><th>总计</th><td>360</td><td>VALUE L</td></tr></tbody></table>',
    '<table><thead><tr><th>月份</th><th>调整后用量</th><th>原始用量</th></tr></thead>'
    '<tbody><tr><th>总计</th><td>VALUE L</td><td>360</td></tr></tbody></table>',
    '<output aria-label="Total water">VALUE liters</output>',
])
def test_chart_pip_requires_its_labelled_total_instead_of_an_axis_tick(verifier_browser, total, top, expected, markup):
    page = verifier_browser.new_page(viewport={'width': 398, 'height': 423})
    try:
        page.set_content('<svg style="position:fixed;top:0;width:80px;height:40px"><text x=0 y=20>720</text></svg>'
                         f'<div style="margin-top:{top}px">'+markup.replace('VALUE', str(total))+'</div>')
        result = benchmark.primary_result_in_viewport(page, 720, task={'id': 'chart'})
        assert result['passed'] is expected
    finally:
        page.close()


@pytest.mark.parametrize('theme', ['light', 'dark'])
@pytest.mark.parametrize('bad_stock_style', [False, True])
def test_stock_readability_probe_includes_an_actual_out_of_stock_record(verifier_browser, theme, bad_stock_style):
    page = verifier_browser.new_page()
    try:
        palette = 'body{background:white;color:#222}' if theme == 'light' else 'body{background:#202129;color:#eee}'
        defect = ('.missing td{opacity:.55}' if theme == 'light' else '.missing td:last-child{color:#c00}') if bad_stock_style else ''
        page.set_content('<style>'+palette+defect+'''</style>
            <label>关键词<input id=kw></label><label>只看有库存<input id=stock type=checkbox></label>
            <button id=sort>升序 ↑</button><button id=clear>清除</button><table><tbody></tbody></table><p id=empty></p>
            <script>
            const kw=document.getElementById('kw'),stock=document.getElementById('stock'),sort=document.getElementById('sort');
            const data=[['笔记本',19,9],['水杯',39,2],['收纳盒',59,3],['台灯',129,0]];let descending=false;
            function render(){
              const visible=data.filter(r=>r[0].includes(kw.value)&&(!stock.checked||r[2]>0));
              visible.sort((a,b)=>descending?b[1]-a[1]:a[1]-b[1]);
              document.querySelector('tbody').innerHTML=visible.map(r=>'<tr class="'+(r[2]?'':'missing')+'">'+r.map(v=>'<td>'+v+'</td>').join('')+'</tr>').join('');
              document.getElementById('empty').textContent=visible.length?'':'没有匹配商品';
              sort.textContent=descending?'降序 ↓':'升序 ↑';
            }
            kw.oninput=stock.onchange=render;sort.onclick=()=>{descending=!descending;render()};
            document.getElementById('clear').onclick=()=>{kw.value='';stock.checked=false;render()};render();
            </script>''')
        observed = []

        def inspect_state(label):
            if label == 'keyword-filters-data':
                assert page.get_by_label('关键词').input_value() == '台灯'
                assert not page.get_by_label('只看有库存').is_checked()
                evidence = benchmark.swept_text_contrast(page)
                observed.append(evidence)

        checks, _ = benchmark.semantic_checks(page, {'id': 'table', 'control': '关键词', 'value': '台灯'},
                                               inspect_state=inspect_state)
        assert all(c['passed'] for c in checks), [c for c in checks if not c['passed']]
        assert len(observed) == 1
        assert bool(observed[0]['failures']) is bad_stock_style
        assert any(s['text'] == '0' for s in observed[0]['samples'])
    finally:
        page.close()


@pytest.mark.parametrize('offset', [0, 500])
def test_pip_checks_other_business_inputs_as_well_as_the_first_field(verifier_browser, offset):
    page = verifier_browser.new_page(viewport={'width':400,'height':423})
    try:
        page.set_content('<label>预算<input value="200"></label><div style="margin-top:'+str(offset)+'px"><label>距离<input value="5"></label></div>')
        evidence = benchmark.business_controls_in_viewport(page)
        assert evidence['passed'] is (offset == 0)
        assert len(evidence['controls']) == 2
    finally:
        page.close()


def test_zero_budget_probe_cleanup_restores_a_choice_through_its_button_without_toggling_it_off(verifier_browser):
    page = verifier_browser.new_page()
    try:
        page.set_content('''<p id="confirmation"></p><article><h3>山谷</h3>120元 · 2公里
            <button onclick="document.getElementById('confirmation').innerText=document.getElementById('confirmation').innerText?'':'当前选择：山谷，120元'">选择这条</button></article>
            <article><h3>日落</h3>220元 · 5公里<button>选择这条</button></article>''')
        expected = ['山谷']
        assert benchmark.restore_selection_through_button(page, expected)
        assert benchmark.selected_route_names(page) == expected
        assert benchmark.restore_selection_through_button(page, expected)
        assert benchmark.selected_route_names(page) == expected
        assert not benchmark.restore_selection_through_button(page, ['当前选择：湖畔，180元'])
    finally:
        page.close()


def test_input_cleanup_keeps_focus_inside_a_virtualized_view(verifier_browser):
    page = verifier_browser.new_page()
    page.set_default_timeout(1200)
    try:
        page.set_content('''<button>Before view</button><iframe id="view"></iframe><button id="after">After view</button>
            <script>document.getElementById('after').addEventListener('focus',()=>document.getElementById('view').remove());</script>''')
        frame = page.locator('iframe').element_handle().content_frame()
        frame.set_content('<label>First<input id="first" value="1"></label><label>Last<input id="last" value="2" onchange="document.querySelector(\'output\').innerText=this.value"></label><output></output>')
        expected = benchmark.snapshot_controls(frame)
        expected[-1]['value'] = '20'
        assert benchmark.restore_controls_through_inputs(frame, expected)
        assert page.locator('iframe').count() == 1
        assert frame.locator('#last').input_value() == '20'
        assert frame.locator('output').inner_text() == '20'
    finally:
        page.close()


def test_change_commits_a_single_input_without_tabbing_to_a_distant_host_control(verifier_browser):
    page = verifier_browser.new_page()
    page.set_default_timeout(1200)
    try:
        page.set_content('''<button>View mode</button><iframe id="view"></iframe><button id="after">Distant host control</button>
            <script>document.getElementById('after').addEventListener('focus',()=>document.getElementById('view').remove());</script>''')
        frame = page.locator('iframe').element_handle().content_frame()
        frame.set_content('<label>倍率<input value="1" onchange="document.querySelector(\'output\').innerText=this.value"></label><output></output>')
        assert benchmark.change(frame.get_by_label('倍率'), '2') == '2'
        assert page.locator('iframe').count() == 1
        assert frame.locator('output').inner_text() == '2'
    finally:
        page.close()


@pytest.mark.parametrize('descending', [False, True])
def test_result_order_restoration_is_checked_even_when_input_state_matches(verifier_browser, descending):
    page = verifier_browser.new_page()
    try:
        rows = [('水杯',39),('笔记本',19)] if descending else [('笔记本',19),('水杯',39)]
        page.set_content('<label>只看有库存<input type="checkbox" checked></label><table>'+
                         ''.join('<tr><td>'+name+'</td><td>'+str(price)+'元</td></tr>' for name,price in rows)+'</table>')
        assert benchmark.snapshot_controls(page)[0]['checked']
        checks = []
        benchmark.check_result_order(page, ['水杯','笔记本'], checks.append, 'sort-state-reload')
        assert checks[0]['passed'] is descending
    finally:
        page.close()


@pytest.mark.parametrize('fixed_by_switch', [False, True])
def test_round_trip_formula_cannot_be_overridden_by_an_extra_daily_count_input(verifier_browser, fixed_by_switch):
    page = verifier_browser.new_page()
    try:
        page.set_content('''<label>票价<input type="number" id="fare" value="12"></label>
            <label>天数<input type="number" id="days" value="22"></label>
            <label>月数<input type="number" id="months" value="12"></label>
            <label>往返<input type="checkbox" id="round" checked></label>
            <label>每日单程次数<input type="number" id="count" value="2"></label>
            <output aria-label="年度费用"></output><p id="error"></p><script>
            const fare=document.getElementById('fare'),days=document.getElementById('days'),months=document.getElementById('months'),
                  round=document.getElementById('round'),count=document.getElementById('count');
            function render(){
                if(LOCKED)count.value=round.checked?'2':'1';
                document.querySelector('output').innerText=(Number(fare.value)*Number(days.value)*Number(months.value)*Number(count.value)).toFixed(2);
                document.getElementById('error').innerText=[fare,days,months,count].some(e=>Number(e.value)<0)?'数值无效':'';
            }
            document.querySelectorAll('input').forEach(e=>e.addEventListener('input',render));
            round.addEventListener('change',()=>{count.value=round.checked?'2':'1';render()});render();
            </script>'''.replace('LOCKED','true' if fixed_by_switch else 'false'))
        checks,_=benchmark.semantic_checks(page, {'id':'calculator','control':'天数','initial':3168,'changed':2880,'value':'20'}, modified=True)
        check=next(c for c in checks if c['name']=='round-trip-controls-daily-count')
        assert check['passed'] is fixed_by_switch
    finally:
        page.close()


@pytest.mark.parametrize('reopen_label', ['新的报名', '继续报名', 'Continue registration'])
def test_form_can_clamp_long_names_then_replace_inputs_with_a_valid_confirmation(verifier_browser, reopen_label):
    page = verifier_browser.new_page()
    try:
        page.set_content('''<form id="form">
            <label>姓名<input id="name" required maxlength="20"></label>
            <label>邮箱<input id="email" type="email" required></label>
            <label>人数<input id="people" type="number" min="1" max="5" value="2"></label>
            <output id="total">160.00</output><button type="button" id="submit">报名</button></form>
            <section id="confirmation" hidden><p id="receipt"></p><button type="button" id="again">新的报名</button></section>
            <script>
            const form=document.getElementById('form'),name=document.getElementById('name'),email=document.getElementById('email'),
                  people=document.getElementById('people'),confirmation=document.getElementById('confirmation');
            people.addEventListener('input',()=>document.getElementById('total').innerText=(Number(people.value)*80).toFixed(2));
            document.getElementById('submit').onclick=()=>{
                if(!form.checkValidity())return;
                document.getElementById('receipt').innerText=name.value+' '+email.value+' '+people.value+'人 总价'+(Number(people.value)*80);
                form.hidden=true;confirmation.hidden=false;
            };
            document.getElementById('again').onclick=()=>{confirmation.hidden=true;form.hidden=false};
            </script>'''.replace('新的报名', reopen_label))
        checks,_=benchmark.semantic_checks(page,{'id':'form','control':'人数','value':'3','initial':160,'changed':240})
        assert all(check['passed'] for check in checks)
        assert page.get_by_label('人数').is_visible()  # Success is deliberately last.
        benchmark.submit_form_confirmation(page,modified=False,record=checks.append)
        assert checks[-1]['passed']
        assert not page.get_by_label('人数').is_visible()
        assert benchmark.reopen_form_through_button(page)
        assert page.get_by_label('人数').input_value()=='3'
    finally:
        page.close()


def test_comparison_can_use_an_apply_button_and_accessible_whole_card_selection(verifier_browser):
    page = verifier_browser.new_page()
    try:
        page.set_content('''<label>预算<input id="budget" type="number" value="200"></label>
            <label>距离<input id="distance" type="number" value="5"></label>
            <button id="apply">应用筛选</button><p id="error"></p><p id="selection"></p><section id="routes"></section>
            <script>
            const budget=document.getElementById('budget'),distance=document.getElementById('distance'),list=document.getElementById('routes');
            const routes=[['山谷',120,2],['日落',220,5],['城郊',160,8]];
            function render(){
                document.getElementById('error').innerText=Number(budget.value)<0?'预算不能为负数':'';
                list.innerHTML='';
                const eligible=routes.filter(r=>r[1]<=Number(budget.value)&&r[2]<=Number(distance.value));
                eligible.forEach(r=>{
                    const card=document.createElement('div');card.tabIndex=0;card.setAttribute('role','button');
                    card.setAttribute('aria-label','选择'+r[0]);card.innerHTML='<h3>'+r[0]+'</h3><p>'+r[1]+'元 '+r[2]+'公里</p>';
                    card.onclick=()=>document.getElementById('selection').innerText='当前选择：'+r[0];list.appendChild(card);
                });
                if(!eligible.length)list.innerText='没有匹配路线';
            }
            document.getElementById('apply').onclick=render;render();
            </script>''')
        checks,_=benchmark.semantic_checks(page,{'id':'comparison','control':'预算','value':'250'})
        assert all(check['passed'] for check in checks)
        assert benchmark.selection_feedback(page.locator('body').inner_text()) == ['当前选择：山谷']
    finally:
        page.close()


@pytest.mark.parametrize('changes', [False, True])
def test_theme_check_waits_for_delivery_but_rejects_a_page_that_does_not_follow_it(verifier_browser, changes):
    page = verifier_browser.new_page()
    try:
        page.set_content('<body style="background:white;color:black">Local view</body>')
        before=page.locator('body').evaluate('e=>({bg:getComputedStyle(e).backgroundColor,color:getComputedStyle(e).color})')
        if changes:
            page.evaluate("()=>setTimeout(()=>{document.body.style.background='black';document.body.style.color='white'},80)")
        after=benchmark.wait_for_body_theme_change(page,before,timeout=800)
        assert (before!=after) is changes
    finally:
        page.close()


@pytest.mark.parametrize('stock_kind', ['checkbox', 'select'])
@pytest.mark.parametrize('filters_stock', [False, True])
def test_table_accepts_labelled_stock_select_before_price_sort_but_checks_its_behavior(verifier_browser, stock_kind, filters_stock):
    page = verifier_browser.new_page()
    try:
        stock = ('<label>库存条件<select id="stock"><option value="any">全部商品</option>'
                 '<option value="available">只看有库存</option><option value="empty">无库存</option></select></label>'
                 if stock_kind == 'select' else '<label>只看有库存<input id="stock" type="checkbox"></label>')
        page.set_content('''<label>关键词<input id="query"></label>STOCK
            <label>价格排序<select id="sort"><option value="asc">价格升序</option><option value="desc">价格降序</option></select></label>
            <button id="clear">清除筛选</button><table><tbody id="rows"></tbody></table><p id="empty"></p>
            <script>
            const query=document.getElementById('query'),stock=document.getElementById('stock'),sort=document.getElementById('sort');
            function render(){
                const onlyStock=stock.type==='checkbox'?stock.checked:stock.value==='available';
                const products=[['水杯',39,8],['台灯',129,0],['笔记本',19,15],['收纳盒',59,4]];
                const matches=products.filter(p=>p[0].includes(query.value)&&(!FILTERS||!onlyStock||p[2]>0));
                matches.sort((a,b)=>(a[1]-b[1])*(sort.value==='asc'?1:-1));
                document.getElementById('rows').innerHTML=matches.map(p=>'<tr><td>'+p[0]+'</td><td>'+p[1]+'</td><td>'+p[2]+'</td></tr>').join('');
                document.getElementById('empty').innerText=matches.length?'':'没有匹配商品';
            }
            [query,stock,sort].forEach(e=>{e.addEventListener('input',render);e.addEventListener('change',render)});
            document.getElementById('clear').onclick=()=>{query.value='';render()};render();
            </script>'''.replace('STOCK',stock).replace('FILTERS','true' if filters_stock else 'false'))
        checks,_=benchmark.semantic_checks(page,{'id':'table','control':'关键词'})
        by_name={check['name']:check['passed'] for check in checks}
        assert by_name['sort-descending']
        assert by_name['stock-filter'] is filters_stock
        assert by_name['combined-table-filters'] is filters_stock
        assert all(check['passed'] for check in checks) is filters_stock
    finally:
        page.close()


@pytest.mark.parametrize('workday_label', ['每月工作日', '工作天数（天/月）'])
def test_calculator_control_labels_distinguish_monthly_workdays_from_optional_holiday_days(verifier_browser, workday_label):
    page = verifier_browser.new_page()
    try:
        page.set_content('''<label>年假天数<input type="number" id="holiday" value="0"></label>
            <label>WORKDAYS<input type="number" id="days" value="22"></label>
            <label>月份数（月/年）<input type="number" id="months" value="12"></label>
            <label>单次票价（元）<input type="number" id="fare" value="12"></label>'''.replace('WORKDAYS',workday_label))
        assert benchmark.control(page,'天数').get_attribute('id')=='days'
        assert benchmark.control(page,'月数').get_attribute('id')=='months'
        assert benchmark.control(page,'票价').get_attribute('id')=='fare'
    finally:
        page.close()




@pytest.mark.parametrize(('foreground', 'background', 'panel', 'expected'), [
    ('#f4f4f8', '#14151a', '#fff', False),
    ('#22242d', '#fff', '#fff', True),
    ('#f4f4f8', '#14151a', '#21232b', True),
    ('#f4f4f8', '#101010', 'rgba(22,23,25,.7)', True),
    ('rgba(255,255,255,.15)', '#14151a', '#14151a', False),
    ('#777', '#fff', '#fff', False),
    ('#767676', '#fff', '#fff', True),
])
def test_visible_text_and_input_values_use_their_actual_card_background(
    verifier_browser, foreground, background, panel, expected,
):
    page = verifier_browser.new_page()
    try:
        page.set_content(f'''<style>
            body {{background:{background};color:{foreground};font:16px system-ui}}
            section,input {{background:{panel};color:inherit}}
            </style><section><p>年度费用</p><strong>5760.00</strong>
            <label>票价<input aria-label="票价" value="12"></label></section>''')
        evidence = benchmark.visible_text_contrast(page)
        assert evidence['tested'] >= 4
        assert not evidence['indeterminate']
        assert (not evidence['failures']) is expected
        if not expected:
            assert {'text', 'control-value'} <= {sample['kind'] for sample in evidence['failures']}
    finally:
        page.close()


@pytest.mark.parametrize(('decoration', 'reason'), [
    ('opacity:.5', 'group-opacity'),
    ('filter:brightness(.8)', 'filter-or-blend'),
    ('background-image:linear-gradient(#000,#fff)', 'background-image'),
])
def test_contrast_records_unknown_paint_instead_of_inventing_a_ratio(verifier_browser, decoration, reason):
    page = verifier_browser.new_page()
    try:
        # Outer group opacity still matters when the inner card is opaque.
        outer = decoration if reason != 'background-image' else ''
        inner = decoration if reason == 'background-image' else 'background:#fff'
        page.set_content(f'<body style="background:#fff"><section style="{outer}"><p style="{inner};color:#000">输入说明</p></section>')
        evidence = benchmark.visible_text_contrast(page)
        assert not evidence['failures']
        assert any(sample['reason'] == reason for sample in evidence['indeterminate'])
    finally:
        page.close()


def test_contrast_does_not_assume_white_behind_a_transparent_component(verifier_browser):
    page = verifier_browser.new_page()
    try:
        page.set_content('<p style="color:#222">透明视图</p>')
        evidence = benchmark.visible_text_contrast(page)
        assert not evidence['samples']
        assert evidence['indeterminate'][0]['reason'] == 'transparent-to-host'
    finally:
        page.close()


def test_contrast_skips_hidden_clipped_offscreen_and_disabled_text(verifier_browser):
    page = verifier_browser.new_page(viewport={'width': 500, 'height': 400})
    try:
        page.set_content('''<style>body{background:#fff;color:#111}.bad{color:white}</style>
            <p>可读文字</p><p class="bad" hidden>隐藏</p>
            <section style="opacity:0"><p class="bad">透明</p></section>
            <p class="bad" style="position:absolute;top:900px">屏外</p>
            <section style="height:0;overflow:hidden"><p class="bad">裁剪</p></section>
            <input class="bad" disabled value="禁用">''')
        evidence = benchmark.visible_text_contrast(page)
        assert not evidence['failures']
        assert [sample['text'] for sample in evidence['samples']] == ['可读文字']
    finally:
        page.close()


def test_contrast_uses_the_large_bold_text_threshold(verifier_browser):
    page = verifier_browser.new_page()
    try:
        page.set_content('<body style="background:#fff;color:#888"><p style="font:700 20px system-ui">大号粗体</p><p style="font:400 20px system-ui">普通文字</p>')
        evidence = benchmark.visible_text_contrast(page)
        assert [sample['text'] for sample in evidence['failures']] == ['普通文字']
        assert next(sample for sample in evidence['samples'] if sample['text'] == '大号粗体')['passed']
    finally:
        page.close()


@pytest.mark.parametrize('above', [True, False])
def test_chart_labels_use_backgrounds_that_actually_cover_their_glyphs(verifier_browser, above):
    page = verifier_browser.new_page()
    try:
        page.set_content('''<style>body{background:#fff;color:#111}.bar{position:relative;margin:50px;
            background:#1d4ed8;width:70px;height:100px}.value{position:absolute;font:700 14px system-ui;TOP}</style>
            <div class="bar"><span class="value">320</span></div>'''.replace('TOP','top:-24px' if above else 'top:10px'))
        evidence = benchmark.visible_text_contrast(page)
        assert (not evidence['failures']) is above
        assert evidence['samples'][0]['background'] == ([255,255,255] if above else [29,78,216])
    finally:
        page.close()


def test_contrast_waits_for_card_color_transitions(verifier_browser):
    page = verifier_browser.new_page()
    try:
        page.set_content('''<style>body{background:#15151a;color:#f4f4f8}
            section{background:#fff;transition:background-color .15s}
            section.dark{background:#21232b}</style><section>费用 5760.00</section>''')
        page.locator('section').evaluate('e=>{getComputedStyle(e).backgroundColor;e.classList.add("dark")}')
        evidence = benchmark.visible_text_contrast(page)
        assert not evidence['failures']
    finally:
        page.close()


@pytest.mark.parametrize('linked', [True, False])
def test_custom_inline_required_errors_do_not_need_a_particular_alert_role(verifier_browser, linked):
    page = verifier_browser.new_page()
    try:
        page.set_content('''<label>姓名<input id="name"></label><p id="error"></p>
            <button type="button" onclick="document.getElementById('error').textContent='姓名不能为空'">报名</button>''')
        field = page.get_by_label('姓名')
        if linked:
            field.evaluate('e=>e.setAttribute("aria-describedby","error")')
        before = page.locator('body').inner_text()
        page.get_by_role('button', name='报名').click()
        assert benchmark.field_validation_feedback(page, field, '姓名.*空', before)
    finally:
        page.close()


@pytest.mark.parametrize('hidden', [False, True])
def test_static_hints_and_hidden_errors_do_not_prove_validation(verifier_browser, hidden):
    page = verifier_browser.new_page()
    try:
        page.set_content(f'''<label>姓名<input id="name" aria-describedby="error"></label>
            <p id="error" {'hidden' if hidden else ''}>姓名不能为空</p><button type="button">报名</button>''')
        field = page.get_by_label('姓名')
        before = page.locator('body').inner_text()
        page.get_by_role('button', name='报名').click()
        assert not benchmark.field_validation_feedback(page, field, '姓名.*空', before)
    finally:
        page.close()


def test_reading_field_validity_does_not_dispatch_an_invalid_event(verifier_browser):
    page = verifier_browser.new_page()
    try:
        page.set_content('<label>姓名<input required oninvalid="document.querySelector(\'output\').textContent=\'event dispatched\'"></label><output></output>')
        before = page.locator('body').inner_text()
        assert benchmark.field_validation_feedback(page, page.get_by_label('姓名'), '姓名.*空', before)
        assert page.locator('output').inner_text() == ''
    finally:
        page.close()


def test_contrast_failure_feedback_describes_the_visible_problem():
    feedback = benchmark.quality_repair_feedback([{'name':'readable-text-after-theme','passed':False}])
    assert '对比' in feedback and '文字' in feedback
    assert 'create_file' not in feedback and 'render_view' not in feedback and '<style>' not in feedback


@pytest.mark.parametrize('checks_empty_email', [True, False])
def test_form_validation_accepts_inline_errors_but_checks_empty_email_independently(verifier_browser, checks_empty_email):
    page = verifier_browser.new_page()
    try:
        page.set_content('''<label>姓名<input id="name" maxlength="20" aria-describedby="error"></label>
            <label>邮箱<input id="email" type="email" aria-describedby="error"></label>
            <label>人数<input id="people" type="number" min="1" max="5" value="2"></label>
            <output id="total">160.00</output><p id="error"></p><button type="button" id="submit">报名</button>
            <script>
            const nameInput=document.getElementById('name'),emailInput=document.getElementById('email'),
                  people=document.getElementById('people'),error=document.getElementById('error');
            people.oninput=()=>document.getElementById('total').textContent=(Number(people.value)*80).toFixed(2);
            document.getElementById('submit').onclick=()=>{
                error.textContent=!nameInput.value.trim()?'姓名不能为空':
                    CHECK_EMAIL&&!emailInput.value.trim()?'邮箱不能为空':'';
            };
            </script>'''.replace('CHECK_EMAIL', 'true' if checks_empty_email else 'false'))
        checks, _ = benchmark.semantic_checks(page, {'id':'form','control':'人数','value':'3','initial':160,'changed':240})
        required = next(check for check in checks if check['name'] == 'required-field-validation')
        assert required['passed'] is checks_empty_email
    finally:
        page.close()


@pytest.mark.parametrize('tab_key', [None, 'Tab', 'Shift+Tab'])
def test_only_control_blurs_inside_the_component_when_either_host_focus_would_unmount_it(verifier_browser, tab_key):
    page = verifier_browser.new_page()
    page.set_default_timeout(1200)
    try:
        page.set_content('''<button id="before">Earlier host control</button><iframe id="view"></iframe>
            <button id="after">Later host control</button><script>
            for(const id of ['before','after'])document.getElementById(id).onfocus=()=>document.getElementById('view')?.remove();
            </script>''')
        frame = page.locator('iframe').element_handle().content_frame()
        frame.set_content('<label>倍率<input value="1" onchange="document.querySelector(\'output\').innerText=this.value"></label><output></output>')
        assert benchmark.change(frame.get_by_label('倍率'), '2', tab_key=tab_key) == '2'
        assert page.locator('iframe').count() == 1
        assert frame.locator('output').inner_text() == '2'
    finally:
        page.close()


def test_native_cdp_connection_waits_for_the_existing_window_target(monkeypatch):
    from types import SimpleNamespace
    target = SimpleNamespace(is_closed=lambda: False)
    context = SimpleNamespace(pages=[])
    browser = SimpleNamespace(contexts=[context], is_connected=lambda: True)
    connections, delivered = [], []

    def connect(url, **kwargs):
        connections.append(url)
        return browser

    def later_window(event, **kwargs):
        delivered.append(event)
        context.pages = [target]
        return target

    context.wait_for_event = later_window
    playwright = SimpleNamespace(chromium=SimpleNamespace(connect_over_cdp=connect))
    observed_browser, observed_page = benchmark.wait_for_packaged_page(playwright, SimpleNamespace(poll=lambda: None), 1234, attempts=4)
    assert observed_browser is browser and observed_page is target
    assert len(connections) == 1 and delivered == ['page']
    assert context.pages == [target]  # The verifier never creates another window.


@pytest.mark.parametrize('exited', [True, False])
def test_native_readiness_distinguishes_process_exit_from_a_missing_window(monkeypatch, exited):
    from types import SimpleNamespace
    from playwright.sync_api import TimeoutError as BrowserTimeout
    def no_page(*args, **kwargs):
        raise BrowserTimeout('no window event')
    browser = SimpleNamespace(contexts=[SimpleNamespace(pages=[], wait_for_event=no_page)], is_connected=lambda: True)
    playwright = SimpleNamespace(chromium=SimpleNamespace(connect_over_cdp=lambda *_args, **_kwargs: browser))
    monkeypatch.setattr(benchmark.time, 'sleep', lambda _: None)
    with pytest.raises(RuntimeError, match='exited' if exited else 'window page'):
        benchmark.wait_for_packaged_page(playwright, SimpleNamespace(poll=lambda: 1 if exited else None), 1234, attempts=2)


def test_stage_snapshots_survive_accumulating_a_later_phase():
    case = {'stages': [], 'repair_count': 0}
    def assess(saved, stage, record):
        record({'name': stage + '-behavior', 'passed': True})
        return {'ref': ['same-view', len(case['stages'])]}
    _, _, accumulated = benchmark.run_quality_stage(case, 'generation', 'task', lambda *_: {}, assess, 2)
    _, _, modification = benchmark.run_quality_stage(case, 'modification', 'change', lambda *_: {}, assess, 2)
    accumulated.extend(modification)
    assert len(accumulated) == 2
    assert [s['checks'] for s in case['stages']] == [
        [{'name': 'generation-behavior', 'passed': True}],
        [{'name': 'modification-behavior', 'passed': True}],
    ]


def test_browser_geometry_numbers_are_not_http_failures():
    from playwright.sync_api import TimeoutError as BrowserTimeout
    error = BrowserTimeout('separator aria-valuenow="592" intercepts pointer; waiting 500ms')
    assert benchmark.classify_quality_error(error, 'browser-generation') == 'validator_or_product_error'
    assert benchmark.classify_quality_error(error, 'model-generation') == 'validator_or_product_error'
    assert benchmark.classify_quality_error(TimeoutError('native execution deadline'), 'model-generation') == 'timeout'
    assert benchmark.classify_quality_error(RuntimeError('HTTP status 503'), 'model-generation') == 'service_unavailable'


def test_generation_scope_is_explicit_without_removing_tools():
    import json
    fixture = json.loads(benchmark.TASK_FILE.read_text(encoding="utf-8"))
    assert all(name in fixture['common'] for name in fixture['forbidden_tools'])
    assert 'render_view' not in fixture['common']
    assert '其余工具仍按原权限使用' in fixture['common']


def test_single_field_blur_avoids_a_real_parent_separator(verifier_browser):
    page = verifier_browser.new_page(viewport={'width': 700, 'height': 500})
    try:
        page.set_content('''<style>iframe{position:absolute;left:0;top:0;width:400px;height:320px;border:0}
          #separator{position:absolute;left:0;top:0;width:6px;height:320px;z-index:5}</style>
          <iframe></iframe><div id="separator" role="separator"></div>''')
        page.locator('iframe').evaluate(r'''e=>e.srcdoc=`<body style="margin:0;min-height:320px;background:white">
          <h1>Multiplier</h1><label>倍率<input type=number value=1></label><output>1</output>
          <script>document.querySelector('input').onchange=e=>document.querySelector('output').textContent=e.target.value<\/script>`''')
        frame = page.locator('iframe').element_handle().content_frame()
        field = frame.get_by_label('倍率')
        field.wait_for()
        assert benchmark.change(field, '2') == '2'
        assert frame.locator('output').inner_text() == '2'
        assert not field.evaluate('e=>e===document.activeElement')
    finally:
        page.close()


def test_native_label_radio_records_and_changed_selection(verifier_browser):
    page = verifier_browser.new_page()
    try:
        page.set_content('''<fieldset><legend>路线</legend>
          <label><input name=route type=radio><strong>山谷</strong>120元 2公里</label>
          <label><input name=route type=radio><strong>日落</strong>220元 5公里</label></fieldset>
          <p role=status></p><script>document.querySelectorAll('input').forEach(e=>e.onchange=()=>{
            document.querySelector('[role=status]').textContent='你选了'+e.parentElement.querySelector('strong').textContent;
          })</script>''')
        items = benchmark.result_items(page, 'comparison')
        assert [i['name'] for i in items] == ['山谷', '日落']
        assert benchmark.selected_route_names(page) == []
        benchmark.choose_result_item(page, items[1])
        assert benchmark.selected_route_names(page) == ['日落']
        benchmark.choose_result_item(page, items[0])
        assert benchmark.selected_route_names(page) == ['山谷']
    finally:
        page.close()


def test_multiline_confirmation_is_selection_but_unselected_prose_is_not(verifier_browser):
    page = verifier_browser.new_page()
    try:
        page.set_content('<section><h3>当前选择：未选择</h3><p>山谷120元 2公里</p></section>')
        assert benchmark.selected_route_names(page) == []
        page.set_content('''<button onclick="document.querySelector('output').textContent='日落'">日落</button>
          <section><h3>已选择方案</h3><output>山谷</output></section>''')
        assert benchmark.selected_route_names(page) == ['山谷']
        page.get_by_role('button', name='日落').click()
        assert benchmark.selected_route_names(page) == ['日落']
    finally:
        page.close()


@pytest.mark.parametrize('dynamic', [True, False])
def test_existing_associated_error_needs_observed_validation_activity(verifier_browser, dynamic):
    page = verifier_browser.new_page()
    try:
        page.set_content('''<label>邮箱<input aria-describedby=error></label>
          <p id=error role=alert>邮箱不能为空</p><p id=unrelated></p><button>验证</button>''')
        page.locator('button').evaluate('''(e,dynamic)=>e.onclick=()=>{
            document.getElementById(dynamic?'error':'unrelated').textContent=dynamic?'邮箱不能为空':'unrelated update';
        }''', dynamic)
        field = page.get_by_label('邮箱')
        with benchmark.observe_field_validation(field) as observation:
            before = page.locator('body').inner_text()
            field.fill('')
            page.get_by_role('button').click()
            assert not benchmark.field_validation_feedback(page, field, '邮箱.*空', before)
            assert benchmark.field_validation_feedback(page, field, '邮箱.*空', before, observation=observation) is dynamic
    finally:
        page.close()


def test_bounded_native_people_select_is_not_sent_impossible_values(verifier_browser):
    page = verifier_browser.new_page()
    try:
        page.set_content('''<label>姓名<input required maxlength=20></label>
          <label>邮箱<input required type=email></label>
          <label>人数<select><option>1</option><option selected>2</option><option>3</option><option>4</option><option>5</option></select></label>
          <output>160</output><button type=button>报名</button>
          <script>document.querySelector('select').onchange=e=>document.querySelector('output').textContent=Number(e.target.value)*80</script>''')
        checks, _ = benchmark.semantic_checks(page, {'id': 'form', 'control': '人数', 'value': '3', 'initial': 160, 'changed': 240})
        by_name = {c['name']: c for c in checks}
        assert by_name['local-recalculation']['passed']
        assert by_name['people-range-validation']['passed']
        assert by_name['people-maximum-validation']['passed']
        assert by_name['people-range-validation']['detail']['unavailable_native_choice'] == '0'
        assert page.get_by_label('人数').input_value() == '3'
    finally:
        page.close()


@pytest.mark.parametrize(('background','foreground','passes'), [('#f9f9fc','#757575',False),('#15161c','#757575',False),('#f9f9fc','#444',True),('#15161c','#ddd',True)])
def test_placeholder_uses_its_pseudo_style_and_actual_background(verifier_browser, background, foreground, passes):
    page = verifier_browser.new_page()
    try:
        page.set_content(f'<style>body,input{{background:{background}}}input::placeholder{{color:{foreground};opacity:1}}</style><input placeholder="Keyword">')
        evidence = benchmark.visible_text_contrast(page)
        sample = next(s for s in evidence['samples'] if s['kind'] == 'placeholder')
        assert sample['passed'] is passes
        assert page.locator('input').input_value() == ''
    finally:
        page.close()


def test_leaf_opacity_is_composited_but_nested_group_opacity_stays_unknown(verifier_browser):
    page = verifier_browser.new_page()
    try:
        page.set_content('<body style="background:rgb(77,148,255)"><span style="color:white;opacity:.9;font:12px sans-serif">Label</span>')
        evidence = benchmark.visible_text_contrast(page)
        sample = next(s for s in evidence['samples'] if s['text'] == 'Label')
        # Analytic alpha blending precedes the native PNG's 8-bit quantization.
        assert sample['ratio'] == pytest.approx(2.720056795, abs=.001)
        assert not sample['passed']
        page.set_content('<body style="background:white"><div style="opacity:.9"><span>Group</span></div>')
        assert any(s['reason'] == 'group-opacity' for s in benchmark.visible_text_contrast(page)['indeterminate'])
    finally:
        page.close()


def test_scroll_revealed_button_is_checked_and_viewport_restored(verifier_browser):
    page = verifier_browser.new_page(viewport={'width': 600, 'height': 300})
    try:
        page.set_content('''<body style="background:white;height:2000px"><h1>Top</h1>
          <button style="position:absolute;top:1600px;color:white;background:rgb(96,165,250);font-size:14px">Continue</button>''')
        assert not benchmark.visible_text_contrast(page)['failures']
        result = benchmark.swept_text_contrast(page)
        assert any(s['text'] == 'Continue' for s in result['failures'])
        assert page.evaluate('scrollY') == 0
    finally:
        page.close()


def test_documented_control_wiring_saves_actual_changes_and_falsy_state(verifier_browser):
    from reverie.agent.system_prompt import build_system_prompt
    prompt = build_system_prompt(runtime_surface='desktop').split('### Offline host integration example', 1)[1]
    helper = prompt.split('```javascript\n', 1)[1].split('\n```', 1)[0]
    example = prompt.split('#### Wiring actual controls', 1)[1]
    markup = example.split('```html\n', 1)[1].split('\n```', 1)[0]
    wiring = example.split('```javascript\n', 1)[1].split('\n```', 1)[0]
    page = verifier_browser.new_page()
    try:
        page.set_content('<iframe sandbox="allow-scripts"></iframe>')
        page.evaluate('''()=>{
          window.saved=[];let revision=4;
          addEventListener('message',event=>{
            const m=event.data;
            const reply=result=>event.source.postMessage({jsonrpc:'2.0',id:m.id,result},'*');
            if(m.method==='ui/initialize')reply({capability:'fixture-capability',
              reverieViewState:{revision,state:{label:'',enabled:false}},
              hostContext:{theme:'light',locale:'zh-CN',displayMode:'pip',styles:{variables:{}}}});
            else if(m.method==='ui/notifications/initialized')window.initialized=true;
            else if(m.method==='reverie/view-state'){
              if(m.capability!=='fixture-capability'||m.params.baseRevision!==revision)throw Error('Ownership or revision changed');
              saved.push(m.params.state);reply({revision:++revision});
            }
          });
        }''')
        page.locator('iframe').evaluate('(e,html)=>e.srcdoc=html', markup + '<script>' + helper + '\n' + wiring + '</script>')
        page.wait_for_function('()=>window.initialized===true')
        frame = page.locator('iframe').element_handle().content_frame()
        assert frame.get_by_label('Label', exact=True).input_value() == ''
        assert not frame.get_by_role('checkbox').is_checked()
        assert page.evaluate('saved.length') == 0
        frame.get_by_label('Label', exact=True).fill('changed')
        frame.get_by_role('checkbox').check()
        assert frame.locator('output').inner_text() == 'changed'
        frame.get_by_role('button', name='Clear', exact=True).click()
        page.wait_for_function('()=>saved.length===3')
        assert page.evaluate('saved') == [
            {'label': 'changed', 'enabled': False},
            {'label': 'changed', 'enabled': True},
            {'label': '', 'enabled': False},
        ]
        assert frame.locator('output').inner_text() == ''
    finally:
        page.close()


def test_bidirectional_ascending_button_completes_real_table_checks(verifier_browser):
    page = verifier_browser.new_page()
    try:
        page.set_content('''<label>关键词<input id=kw></label>
          <label><input id=stock type=checkbox>只看有库存</label>
          <button id=sort aria-describedby=sortHelp>升序 ↑</button><span id=sortHelp>价格排序</span>
          <button id=clear>清除筛选</button><table><tbody></tbody></table><p id=empty></p>
          <script>
          const rows=[['水杯',39,8],['台灯',129,0],['笔记本',19,15],['收纳盒',59,4]];
          const kw=document.getElementById('kw'),stock=document.getElementById('stock'),sort=document.getElementById('sort');
          let descending=false;
          function render(){const visible=rows.filter(r=>r[0].includes(kw.value)&&(!stock.checked||r[2]>0))
            .sort((a,b)=>(a[1]-b[1])*(descending?-1:1));
            document.querySelector('tbody').innerHTML=visible.map(r=>'<tr><td>'+r[0]+'</td><td>'+r[1]+'</td><td>'+r[2]+'</td></tr>').join('');
            document.getElementById('empty').textContent=visible.length?'':'没有匹配';
            sort.textContent=descending?'降序 ↓':'升序 ↑';}
          kw.oninput=stock.onchange=render;sort.onclick=()=>{descending=!descending;render()};
          document.getElementById('clear').onclick=()=>{kw.value='';stock.checked=false;render()};render();
          </script>''')
        checks, _ = benchmark.semantic_checks(page, {'id': 'table', 'control': '关键词', 'value': '台灯'})
        assert next(c for c in checks if c['name'] == 'sort-descending')['passed']
        assert all(c['passed'] for c in checks), [c for c in checks if not c['passed']]
    finally:
        page.close()


def test_new_state_feedback_never_forwards_private_field_values():
    feedback = benchmark.quality_repair_feedback([
        {'name': 'readable-state-required-field-validation-dark', 'passed': False,
         'detail': {'failures': [{'text': 'private-canary@example.invalid'}]}},
        {'name': 'theme-state-required-field-validation-light', 'passed': False,
         'expected': [{'value': 'private-canary@example.invalid'}]},
    ])
    assert 'private-canary' not in feedback
    assert '对比过低' in feedback and '输入、选择或表单状态' in feedback


@pytest.mark.parametrize('dynamic', [True, False])
def test_required_fields_use_real_error_clearance_and_retain_email_feedback(verifier_browser, dynamic):
    page = verifier_browser.new_page()
    try:
        page.set_content('''<label>姓名<input id=name maxlength=20></label><p id=nameError>姓名不能为空</p>
          <label>邮箱<input id=email aria-describedby=emailError></label><p id=emailError role=alert>邮箱不能为空</p>
          <label>人数<select><option>1</option><option selected>2</option><option>3</option><option>4</option><option>5</option></select></label>
          <output>160</output><button type=button>报名</button>
          <script>document.querySelector('select').onchange=e=>document.querySelector('output').textContent=Number(e.target.value)*80;</script>''')
        if dynamic:
            page.locator('button').evaluate('''e=>e.onclick=()=>{
              const name=document.getElementById('name'),email=document.getElementById('email');
              document.getElementById('nameError').textContent=name.value?'':'姓名不能为空';
              document.getElementById('emailError').textContent=email.value.includes('@')?'':email.value?'邮箱格式错误':'邮箱不能为空';
            }''')
        checks, _ = benchmark.semantic_checks(page, {'id':'form','control':'人数','value':'3','initial':160,'changed':240})
        assert next(c for c in checks if c['name'] == 'required-field-validation')['passed'] is dynamic
    finally:
        page.close()


@pytest.mark.parametrize('linked', [False, True])
@pytest.mark.parametrize('dynamic', [False, True])
def test_both_empty_submit_preserves_unassociated_email_feedback(verifier_browser, linked, dynamic):
    """DOM fixtures only; repeated visible errors must not become false negatives."""
    page = verifier_browser.new_page()
    try:
        association = 'aria-describedby=emailError' if linked else ''
        help_name = '' if dynamic else '姓名不能为空'
        help_email = '' if dynamic else '邮箱不能为空'
        page.set_content(f'''<label>姓名<input id=name maxlength=20></label><p id=nameError>{help_name}</p>
          <label>邮箱<input id=email type=email {association}></label><p id=emailError>{help_email}</p>
          <label>人数<select><option>1</option><option selected>2</option><option>3</option><option>4</option><option>5</option></select></label>
          <output>160</output><button type=button>报名</button>
          <script>document.querySelector('select').onchange=e=>document.querySelector('output').textContent=Number(e.target.value)*80;</script>''')
        if dynamic:
            page.locator('button').evaluate('''button=>button.onclick=()=>{
              const name=document.getElementById('name'),email=document.getElementById('email');
              document.getElementById('nameError').textContent='';
              document.getElementById('emailError').textContent='';
              if(!name.value)document.getElementById('nameError').textContent='姓名不能为空';
              if(!email.value)document.getElementById('emailError').textContent='邮箱不能为空';
              else if(!email.value.includes('@'))document.getElementById('emailError').textContent='邮箱格式错误';
            }''')
        checks, _ = benchmark.semantic_checks(page, {'id':'form','control':'人数','value':'3','initial':160,'changed':240})
        assert next(c for c in checks if c['name'] == 'required-field-validation')['passed'] is dynamic
    finally:
        page.close()


# Authored primary-result and pressed-button regressions; zero model quality samples.
def calculator_html(defect='', *, roundtrip=False, daily_count=1):
    return '''<label>票价<input id="fare" type="number" value="12"></label>
        <label>天数<input id="days" type="number" value="22"></label>
        <label>月数<input id="months" type="number" value="12"></label>
        <label>往返<input id="round" type="checkbox" CHECKED></label>
        <label>每天单程次数<input id="count" type="number" value="COUNT"></label>
        <section><span>年度通勤费用</span><output id="total"></output></section>
        <p id="comparison"></p><p id="error"></p>
        <script>
        const defect='DEFECT';
        const fare=document.querySelector('#fare'),days=document.querySelector('#days'),months=document.querySelector('#months');
        const round=document.querySelector('#round'),count=document.querySelector('#count'),total=document.querySelector('#total');
        function render(){
            const amount=Math.max(0,+fare.value)*Math.max(0,+days.value)*Math.max(0,+months.value)*(round.checked?2:1);
            document.querySelector('#error').textContent=[fare,days,months].some(e=>+e.value<0)?'输入不能为负数':'';
            document.querySelector('#comparison').textContent='对比参考 '+amount.toFixed(2);
            if(defect==='initial'&&+days.value===22) total.textContent=round.checked?'12672.00':'6336.00';
            else if(defect==='local'&&+days.value===20) total.textContent='3168.00';
            else if(defect==='zero'&&+days.value===0) total.textContent='2880.00';
            else if(defect==='fare-zero'&&+fare.value===0) total.textContent='2880.00';
            else if(defect==='months-zero'&&+months.value===0) total.textContent='2880.00';
            else if(defect==='currency'&&+days.value===20) total.textContent=String(amount);
            else if(defect==='async') setTimeout(()=>total.textContent=amount.toFixed(2),25);
            else total.textContent=amount.toFixed(2);
        }
        document.querySelectorAll('input').forEach(e=>e.addEventListener('input',render));render();
        </script>'''.replace('CHECKED', 'checked' if roundtrip else '').replace('COUNT', str(daily_count)).replace('DEFECT', defect)

@pytest.mark.parametrize('defect,check_name', [
    ('initial','initial-business-result'), ('local','local-recalculation'),
    ('zero','zero-state'), ('fare-zero','fare-zero-state'),
    ('months-zero','months-zero-state'), ('currency','two-decimal-currency'),
])
@pytest.mark.parametrize('modified', [False, True])
def test_comparison_amount_cannot_cover_a_wrong_main_result(verifier_browser, defect, check_name, modified):
    page=verifier_browser.new_page()
    try:
        page.set_content(calculator_html(defect,roundtrip=modified))
        checks,_=benchmark.semantic_checks(page, {'id':'calculator','control':'天数',
            'initial':3168,'changed':2880,'value':'20'}, modified=modified)
        assert not next(check for check in checks if check['name']==check_name)['passed']
    finally:
        page.close()

@pytest.mark.parametrize('modified', [False, True])
def test_correct_primary_amount_updates_asynchronously_without_body_match_counts(verifier_browser, modified):
    page=verifier_browser.new_page()
    try:
        page.set_content(calculator_html('async',roundtrip=modified))
        checks,_=benchmark.semantic_checks(page, {'id':'calculator','control':'天数',
            'initial':3168,'changed':2880,'value':'20'}, modified=modified)
        assert all(check['passed'] for check in checks), [check for check in checks if not check['passed']]
    finally:
        page.close()

@pytest.mark.parametrize('roundtrip,daily_count,failed_check', [
    (True,1,'single-trip-default'), (False,2,'single-trip-daily-count'),
])
def test_generation_singletrip_defaults_are_checked_separately_from_amounts(verifier_browser, roundtrip,daily_count,failed_check):
    page=verifier_browser.new_page()
    try:
        page.set_content(calculator_html(roundtrip=roundtrip,daily_count=daily_count))
        checks,_=benchmark.semantic_checks(page, {'id':'calculator','control':'天数',
            'initial':3168,'changed':2880,'value':'20'})
        assert not next(check for check in checks if check['name']==failed_check)['passed']
    finally:
        page.close()

@pytest.mark.parametrize('main_amount,top,expected', [(3168,20,True),(3168,900,False),(6336,20,False)])
def test_pip_inspects_the_identified_primary_region_not_the_comparison(verifier_browser,main_amount,top,expected):
    page=verifier_browser.new_page(viewport={'width':398,'height':423})
    try:
        page.set_content(f'<p style="position:fixed;top:0">对比3168元</p>'
            f'<section style="margin-top:{top}px"><span>年度费用</span><strong>{main_amount}.00元</strong></section>')
        state=benchmark.primary_result_in_viewport(page,3168,task={'id':'calculator'})
        assert state['passed'] is expected
    finally:
        page.close()

@pytest.mark.parametrize('main_amount,expected', [(2880,True),(6336,False)])
def test_restored_fields_must_recompute_the_primary_result(verifier_browser,main_amount,expected):
    page=verifier_browser.new_page()
    try:
        page.set_content(f'<section><span>年度费用</span><b>{main_amount}.00元</b></section><p>对比2880元</p>')
        checks=[]
        benchmark.check_restored_business_result(page,{'id':'calculator'},'20',checks.append,modified=False)
        assert checks[0]['passed'] is expected
    finally:
        page.close()

@pytest.mark.parametrize('element', ['button', 'div role="button" tabindex="0"'])
def test_stock_filter_accepts_named_pressed_buttons_and_observes_real_toggle(verifier_browser,element):
    page=verifier_browser.new_page()
    try:
        tag=element.split()[0]
        page.set_content(f'<{element} aria-pressed="false" onclick="this.setAttribute(\'aria-pressed\',String(this.getAttribute(\'aria-pressed\')!==\'true\'))">只看有库存</{tag}>')
        field=benchmark.stock_filter_control(page)
        assert benchmark.set_stock_filter(field,True)
        assert field.get_attribute('aria-pressed')=='true'
        assert benchmark.set_stock_filter(field,True)  # Idempotent: do not flip it back.
        assert benchmark.set_stock_filter(field,False)
        assert field.get_attribute('aria-pressed')=='false'
    finally:
        page.close()

@pytest.mark.parametrize('attributes', ['', 'aria-pressed="false"'])
def test_stock_filter_does_not_accept_unstated_or_nonfunctional_toggle_buttons(verifier_browser,attributes):
    page=verifier_browser.new_page()
    try:
        page.set_content(f'<button aria-label="只看有库存" {attributes}>只看有库存</button>')
        assert not benchmark.set_stock_filter(benchmark.stock_filter_control(page),True)
    finally:
        page.close()

def test_pressed_stock_state_is_snapshotted_and_restored_through_real_button(verifier_browser):
    page=verifier_browser.new_page()
    try:
        page.set_content('<button aria-pressed="false" onclick="this.setAttribute(\'aria-pressed\',String(this.getAttribute(\'aria-pressed\')!==\'true\'))">只看有库存</button>')
        original=benchmark.snapshot_controls(page)
        assert len(original)==1 and original[0]['type']=='pressed-button' and not original[0]['checked']
        page.get_by_role('button',name='只看有库存').click()
        assert benchmark.snapshot_controls(page)[0]['checked']
        assert benchmark.restore_controls_through_inputs(page,original)
        assert benchmark.snapshot_controls(page)==original
    finally:
        page.close()

def test_pressed_stock_control_below_pip_fold_does_not_pass_input_visibility(verifier_browser):
    page=verifier_browser.new_page(viewport={'width':398,'height':423})
    try:
        page.set_content('<label>关键词<input></label><button style="margin-top:900px" aria-pressed="false">只看有库存</button>')
        assert not benchmark.business_controls_in_viewport(page)['passed']
    finally:
        page.close()
