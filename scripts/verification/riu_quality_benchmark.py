"""Fixed real-model RIU benchmark through the production Windows Desktop.

The loopback recorder forwards unchanged JSON to the configured provider endpoint.
It never authors or repairs HTML. Raw requests, native SSE, sessions and failed
attempts are retained. Credentials are removed from all isolated config backups.
"""
from __future__ import annotations

import argparse
import copy
import codecs
import hashlib
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import re
import shutil
import socket
import subprocess
import sys
import threading
import time

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "ReverieCli-py"))
TASK_FILE = Path(__file__).with_name("fixtures") / "riu-natural-tasks.json"


def dump(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, default=str), encoding="utf-8")


def configure_model_source(cfg, original, source, model, *, recorder_url=None):
    cfg.active_model_source = source
    provider = copy.deepcopy(getattr(original, source))
    provider['selected_model_id'] = model
    if recorder_url:
        provider['api_url'] = recorder_url
        provider['endpoint'] = '/chat/completions'
    setattr(cfg, source, provider)


def tool_scope_violations(names, fixture, task):
    if task['id'] == 'text':
        return list(names)
    if 'forbidden_tools' in fixture:
        return [name for name in names if name in fixture['forbidden_tools']]
    return [name for name in names if name not in ['create_file', 'render_view']]


def quality_outcome(checks, violations, repairs, *, generation_only=False):
    if violations:
        return 'model_violation'
    if generation_only:
        return 'registered_unvalidated'
    if not checks or not all(check['passed'] for check in checks):
        return 'semantic_failure'
    return 'repaired_success' if repairs else 'first_pass'


def execution_state(events, session_id):
    """Observe the production coordinator, independent of transient button layout."""
    started, active = False, False
    for item in events:
        event = item.get('event', {})
        if event.get('type') == 'executors.changed':
            active = any(entry.get('sessionId') == session_id for entry in event.get('entries', []))
            started = started or active
    return started, active


def start_event_capture(page):
    # A full document reload drops both the globals and the old subscription.
    return page.evaluate("""()=>{
        if (!window.__qualityEvents) {
            window.__qualityEvents=[];
            window.reverie.onEvent(e=>window.__qualityEvents.push({at:performance.now(),event:e}));
        }
        return window.__qualityEvents.length;
    }""")


class Recorder:
    def __init__(self, output, upstream, secret):
        self.output, self.upstream, self.secret = output, upstream, secret
        self.records, self.case = [], "startup"
        recorder = self

        class Handler(BaseHTTPRequestHandler):
            protocol_version = "HTTP/1.1"

            def log_message(self, *args):
                pass

            def do_POST(self):
                import requests
                started = time.perf_counter()
                raw = self.rfile.read(int(self.headers["Content-Length"]))
                payload = json.loads(raw)
                index = len(recorder.records)
                target = recorder.output / f"request-{index:04d}"
                public = raw.decode("utf-8").replace(recorder.secret, "[redacted]") if recorder.secret else raw.decode("utf-8")
                target.with_suffix(".json").write_text(public, encoding="utf-8")
                system = [m for m in payload.get("messages", []) if m.get("role") == "system"]
                record = {"case": recorder.case, "request": str(target.with_suffix('.json')), "model": payload.get("model"), "body_bytes": len(raw), "body_characters": len(raw.decode('utf-8')), "system_characters": sum(len(str(m.get('content', ''))) for m in system), "system_messages": len(system), "schema_characters": len(json.dumps(payload.get('tools', []), ensure_ascii=False)), "tools": len(payload.get('tools', [])), "started_monotonic": started}
                record['system_sha256'] = hashlib.sha256(json.dumps(system, ensure_ascii=False).encode()).hexdigest()
                record['schemas_sha256'] = hashlib.sha256(json.dumps(payload.get('tools', []), ensure_ascii=False, sort_keys=True).encode()).hexdigest()
                record['tool_choice'] = payload.get('tool_choice')
                recorder.records.append(record)
                dump(recorder.output / "requests.json", recorder.records)
                headers = {k: v for k, v in self.headers.items() if k.lower() not in {"host", "content-length", "connection", "accept-encoding"}}
                headers["Accept-Encoding"] = "identity"
                try:
                    with requests.post(recorder.upstream, data=raw, headers=headers, stream=True, timeout=(30, 900)) as response:
                        record.update(status=response.status_code, headers_ms=(time.perf_counter()-started)*1000)
                        if response.headers.get('Retry-After'):
                            record['retry_after'] = response.headers['Retry-After']
                        if response.headers.get('Server-Timing'):
                            record['provider_server_timing'] = response.headers['Server-Timing']
                        self.send_response(response.status_code)
                        self.send_header("Content-Type", response.headers.get("Content-Type", "application/json"))
                        self.send_header("Transfer-Encoding", "chunked")
                        self.send_header("Connection", "close")
                        self.end_headers()
                        buffer = ''
                        decoder = codecs.getincrementaldecoder('utf-8')()
                        tool_arguments = {}
                        with target.with_suffix('.sse').open('wb') as stream:
                            for chunk in iter(lambda: response.raw.read1(64 * 1024, decode_content=True), b''):
                                if not chunk:
                                    continue
                                record.setdefault("first_wire_chunk_ms", (time.perf_counter()-started)*1000)
                                buffer += decoder.decode(chunk)
                                while '\n' in buffer:
                                    line, buffer = buffer.split('\n', 1)
                                    if not line.startswith('data:'):
                                        continue
                                    if line[5:].strip() == '[DONE]':
                                        record['sse_done'] = True
                                        continue
                                    try:
                                        event = json.loads(line[5:].strip())
                                    except (ValueError, TypeError):
                                        continue
                                    elapsed = (time.perf_counter()-started)*1000
                                    if event.get('error'):
                                        record['upstream_stream_error'] = event['error']
                                    if event.get('usage'):
                                        record['usage'] = event['usage']
                                    if event.get('nvext'):
                                        record['provider_metrics'] = event['nvext']
                                    for choice in event.get('choices') or []:
                                        if choice.get('finish_reason'):
                                            record.setdefault('finish_reasons', []).append(choice['finish_reason'])
                                        delta = choice.get('delta') or {}
                                        if delta.get('content'):
                                            record.setdefault('first_content_ms', elapsed)
                                        if delta.get('reasoning_content') or delta.get('reasoning'):
                                            record.setdefault('first_reasoning_ms', elapsed)
                                        for call in delta.get('tool_calls', []):
                                            record.setdefault('first_tool_fragment_ms', elapsed)
                                            function = call.get('function') or {}
                                            if function.get('name'):
                                                record.setdefault('response_tool_names', []).append(function['name'])
                                            key = call.get('index', 0)
                                            tool_arguments[key] = tool_arguments.get(key, '') + (function.get('arguments') or '')
                                            try:
                                                if isinstance(json.loads(tool_arguments[key]), dict):
                                                    record.setdefault('first_parseable_tool_arguments_ms', elapsed)
                                            except ValueError:
                                                pass
                                stream.write(chunk)
                                self.wfile.write(f'{len(chunk):x}\r\n'.encode() + chunk + b'\r\n')
                                self.wfile.flush()
                            self.wfile.write(b'0\r\n\r\n')
                            self.wfile.flush()
                except Exception as error:
                    record["transport_error"] = type(error).__name__ + ": " + str(error)
                finally:
                    record["complete_ms"] = (time.perf_counter()-started)*1000
                    dump(recorder.output / "requests.json", recorder.records)
                    self.close_connection = True

        self.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()

    def close(self):
        self.server.shutdown()
        self.server.server_close()


def control(frame, name):
    aliases = {"关键词": "关键词|搜索|查找|商品名称", "倍率": "倍率|倍数|系数|缩放", "预算": "预算|最高费用|最高价格", "姓名": "姓名|名字", "邮箱": "邮箱|电子邮件|email"}
    return frame.get_by_label(re.compile(aliases.get(name, name), re.I)).and_(frame.locator('input,select,textarea')).first


def change(locator, value):
    kind = locator.evaluate("e=>e.type")
    if kind == "range":
        limits = locator.evaluate("e=>({min:Number(e.min||0),max:Number(e.max||100),step:Number(e.step||1)})")
        target = min(limits['max'], max(limits['min'], float(value)))
        locator.focus()
        locator.press('Home')
        for _ in range(round((target-limits['min'])/limits['step'])):
            locator.press('ArrowRight')
    elif kind == 'select-one':
        locator.select_option(value=value)
    else:
        locator.fill(value)
        locator.press("Tab")
    return locator.input_value()


def semantic_checks(frame, task, *, modified=False, record=None):
    """Assert business semantics through labels/text/roles, allowing varied DOMs."""
    from playwright.sync_api import TimeoutError as BrowserTimeout, expect
    checks = []

    def check(name, passed, detail=None):
        result = {"name": name, "passed": bool(passed), "detail": detail}
        checks.append(result)
        if record:
            record(result)

    def text():
        return frame.locator('body').inner_text()

    def amount(value, previous_text=None):
        if value == int(value):
            value = int(value)
        pattern = re.compile(r'(?<![\d.-])' + f'{value:,}'.replace(',', '[,，]?') + r'(?:\.0+)?(?![\d.])')
        try:
            if previous_text is None:
                expect(frame.locator('body')).to_contain_text(pattern, timeout=3000)
            else:
                frame.wait_for_function("args=>[...document.body.innerText.matchAll(new RegExp(args.pattern,'g'))].length>args.count", arg={'pattern': pattern.pattern, 'count': len(pattern.findall(previous_text))}, timeout=3000)
            return True
        except (AssertionError, BrowserTimeout):
            return False

    def invalid(locator, message):
        return locator.evaluate('e=>!e.checkValidity() || e.getAttribute("aria-invalid")==="true"') or bool(re.search(message, '\n'.join(frame.get_by_role('alert').all_text_contents())))

    field = control(frame, task['control'])
    field.wait_for(timeout=15000)
    initial = field.input_value()
    if task['id'] in {'calculator', 'chart', 'form'}:
        expected = task['initial']
        if modified:
            expected = float(initial) * {'calculator': 12*12*2, 'chart': 460, 'form': 100}[task['id']]
        check('initial-business-result', amount(int(expected) if expected == int(expected) else expected), text())
    if task['id'] == 'calculator' and modified:
        return_trip = frame.get_by_label(re.compile('往返')).first
        check('round-trip-default', return_trip.is_checked())
        return_trip.uncheck()
        check('round-trip-changes-formula', amount(12*float(initial)*12), text())
        return_trip.check()
    if task['id'] == 'table':
        price = None
        if modified:
            price = frame.get_by_label(re.compile('最高价格|价格上限|最高价')).first
            check('new-price-filter-default', float(price.input_value()) == 50)
            change(field, '')
            check('natural-language-price-filter', '台灯' not in text() and '收纳盒' not in text(), text())
            change(price, '200')
        else:
            check('default-price-order', bool(re.search(r'笔记本[\s\S]*水杯', text())), text())
        stock = frame.get_by_label(re.compile('库存|有货')).first
        if stock.count():
            stock.uncheck()
        change(field, '台灯')
        check('keyword-filters-data', '台灯' in text() and '笔记本' not in text(), text())
        change(field, '不存在的商品')
        check('empty-data-feedback', not any(name in text() for name in ['水杯', '台灯', '笔记本', '收纳盒']) and bool(re.search('无|没有|未找到|暂无', text())), text())
        clear = frame.get_by_role('button', name=re.compile('清除|清空|重置')).first
        if clear.count():
            clear.click()
            check('clear-filter-action', field.input_value() == '' and '水杯' in text(), text())
        else:
            check('clear-filter-action', False, 'Missing clear-filter action')
            change(field, '')  # Continue independent checks through the real input.
        if modified:
            change(price, '200')
        if stock.count():
            stock.uncheck()
        sort = frame.get_by_role('combobox').first
        if sort.count():
            options = sort.locator('option').all_text_contents()
            descending = next((v for v in options if re.search('降|高到低', v)), None)
            if descending:
                sort.select_option(label=descending)
                check('sort-descending', bool(re.search(r'台灯[\s\S]*收纳盒', text())), text())
            else:
                check('sort-control', False, options)
        else:
            button = frame.get_by_role('button', name=re.compile('降序|高到低')).first
            if not button.count():
                button = frame.get_by_role('button', name=re.compile('价格')).first
            if button.count():
                button.click()
                check('sort-descending', bool(re.search(r'台灯[\s\S]*收纳盒', text())), text())
            else:
                check('sort-control', False)
        if stock.count():
            stock.check()
            check('stock-filter', '台灯' not in text(), text())
        else:
            check('stock-filter', False)
        if modified:
            change(price, '50')
            check('natural-language-price-filter', '台灯' not in text() and '收纳盒' not in text(), text())
    elif task['id'] == 'comparison':
        check('default-combined-filter', '山谷' in text() and (not modified or '湖畔' in text()), text())
        if not modified:
            check('both-route-constraints', '日落' not in text() and '城郊' not in text(), text())
        change(field, '50')
        check('empty-data-feedback', not any(name in text() for name in ['山谷', '日落', '城郊', '湖畔']) and bool(re.search('无|没有|未找到|暂无', text())), text())
        change(field, '-1')
        check('invalid-budget-feedback', bool(re.search('错误|不能|大于|至少|有效|不小于|非负|≥', text())), text())
        change(field, '250')
        button = frame.get_by_role('button', name=re.compile('选择|选中')).first
        button.click()
        check('selection-feedback', bool(re.search('已选|选择了|当前选择', text())), text())
    else:
        before_change = text()
        value = task['value']
        if modified and field.input_value() == value:
            value = str(float(value) + 1)
        change(field, value)
        if task['id'] in {'calculator', 'chart', 'form'}:
            expected = float(value) * {'calculator': 12*12*2, 'chart': 460, 'form': 100}[task['id']] if modified else task['changed']
            check('local-recalculation', amount(expected, before_change), text())
        if task['id'] in {'calculator', 'chart'}:
            before_zero = text()
            change(field, '0')
            check('zero-state', amount(0, before_zero), text())
            actual = change(field, '-1')
            check('invalid-input-feedback', actual != '-1' or bool(re.search('错误|不能|大于|至少|有效|不小于|非负|≥', text())), {'actual': actual, 'text': text()})
        if task['id'] == 'form':
            name, email = control(frame, '姓名'), control(frame, '邮箱')
            submit = frame.get_by_role('button', name=re.compile('报名|提交')).first
            submit.click()
            check('required-field-validation', invalid(name, '姓名.*(填|空)|请.*姓名'), text())
            name.fill('王小明')
            email.fill('bad-address')
            submit.click()
            check('email-validation', invalid(email, '邮箱.*(错误|格式)|有效.*邮箱'), text())
            email.fill('synthetic@example.invalid')
            name.fill('长中文姓名用于边界验证长中文姓名用于边界验证')
            submit.click()
            check('name-length-validation', len(name.input_value()) <= 20 or invalid(name, '20|二十|姓名.*(长|字数)'), text())
            name.fill('王小明')
            change(field, '0')
            submit.click()
            check('people-range-validation', invalid(field, '人数.*(1|一)|至少'), text())
            change(field, '6')
            submit.click()
            check('people-maximum-validation', invalid(field, '人数.*(5|五)|最多|不超过'), text())
            change(field, '3')
            submit.click()
            check('valid-submission', '王小明' in text() and 'synthetic@example.invalid' in text(), text())
        change(field, task['value'])
    field.focus()
    check('keyboard-focus', field.evaluate('e=>e===document.activeElement && e.tabIndex>=0 && !e.disabled'))
    check('no-horizontal-overflow', frame.evaluate('document.documentElement.scrollWidth <= innerWidth + 2'))
    return checks, initial


def snapshot_controls(frame):
    return frame.locator('input,select,textarea').evaluate_all("es=>es.map(e=>({tag:e.tagName,type:e.type,id:e.id,name:e.name,value:e.value,checked:e.checked}))")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--exe', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--source', choices=['sensenova', 'nvidia'], default='sensenova')
    parser.add_argument('--model', default='sensenova-6.8-flash-lite')
    parser.add_argument('--task-file', type=Path, default=TASK_FILE)
    parser.add_argument('--attempts', type=int, default=3)
    parser.add_argument('--tasks', nargs='+', default=['calculator', 'table', 'chart', 'form', 'comparison', 'text'])
    parser.add_argument('--timeout', type=int, default=900, help='Wall-clock deadline per model turn; no output/token cap is added.')
    parser.add_argument('--generation-only', action='store_true', help='Retain generation baseline without semantic/mutation checks.')
    args = parser.parse_args()
    from playwright.sync_api import sync_playwright
    from reverie.config import ConfigManager
    from reverie.session.manager import SessionManager
    from reverie.views import ViewStore, visible_view_references

    output = args.output.resolve()
    if not output.is_relative_to(ROOT):
        raise ValueError('Evidence must stay in this repository')
    output.mkdir(parents=True, exist_ok=False)
    shutil.copy2(__file__, output / 'executed-verifier.py')
    temporary = output / 'temp'
    temporary.mkdir()
    os.environ['TEMP'] = os.environ['TMP'] = str(temporary)
    original = ConfigManager(ROOT).load()
    app_root, workspace, home = [output / name for name in ('app-root', 'workspace', 'desktop-home')]
    for directory in (app_root, workspace, home):
        directory.mkdir()
    os.environ['REVERIE_APP_ROOT'] = str(app_root)
    os.environ['NO_PROXY'] = '127.0.0.1,localhost'
    cfg = ConfigManager(workspace).load()
    configure_model_source(cfg, original, args.source, args.model)
    active = cfg.active_model
    if not active or active.model != args.model:
        raise ValueError('Configured model not resolved exactly')
    upstream = active.base_url.rstrip('/')
    if not upstream.endswith('/chat/completions'):
        upstream += '/chat/completions'
    recorder = Recorder(output, upstream, active.api_key)
    configure_model_source(cfg, original, args.source, args.model, recorder_url=f'http://127.0.0.1:{recorder.server.server_port}/v1')
    cfg.security = copy.deepcopy(original.security)
    cfg.api_proxy = original.api_proxy
    cfg.api_timeout = original.api_timeout
    cfg.api_max_retries = original.api_max_retries
    cfg.api_initial_backoff = original.api_initial_backoff
    cfg.stream_responses = True
    config = ConfigManager(workspace)
    config.ensure_dirs()
    config.save(cfg)
    manager = SessionManager(config.project_data_dir, project_root=workspace)
    task_file = args.task_file.resolve()
    if not task_file.is_relative_to(ROOT):
        raise ValueError('Task fixtures must stay in this repository')
    fixture = json.loads(task_file.read_text(encoding='utf-8'))
    sessions = {f"{task['id']}-{attempt}": manager.create_session(f"RIU quality {task['id']}-{attempt}") for task in fixture['tasks'] if task['id'] in args.tasks for attempt in range(1, args.attempts+1)}
    dump(output / 'fixed-tasks.json', fixture)
    settings = home / '.reverie/desktop/desktop-settings.json'
    settings.parent.mkdir(parents=True)
    dump(settings, {'coreAppRoot': str(app_root), 'projectRoot': str(workspace), 'ui': {'language': 'zh-CN', 'showReasoning': True, 'expandReasoning': True}})
    report = {'scope': 'Fresh packaged Desktop sessions, real configured model and executor, no test-authored HTML', 'model': active.model, 'source': args.source, 'task_version': fixture['version'], 'task_sha256': hashlib.sha256(task_file.read_bytes()).hexdigest(), 'attempts_per_task': args.attempts, 'cases': [], 'credential_cleanup': False}
    report['generation_only'] = args.generation_only
    report['verifier_sha256'] = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
    report['browser_errors'] = []
    process = None
    log = (output / 'electron.log').open('w', encoding='utf-8')

    def save():
        dump(output / 'report.json', report)

    def launch(playwright):
        nonlocal process
        with socket.socket() as sock:
            sock.bind(('127.0.0.1', 0))
            port = sock.getsockname()[1]
        env = {**os.environ, 'PORTABLE_EXECUTABLE_DIR': str(home)}
        env.pop('ELECTRON_RUN_AS_NODE', None)
        process = subprocess.Popen([str(args.exe.resolve()), '--gui', '--project', str(workspace), f'--remote-debugging-port={port}'], env=env, stdout=log, stderr=log, creationflags=subprocess.CREATE_NO_WINDOW)
        browser = None
        for _ in range(160):
            try:
                browser = playwright.chromium.connect_over_cdp(f'http://127.0.0.1:{port}', timeout=1000)
                break
            except Exception:
                if process.poll() is not None:
                    raise RuntimeError('Packaged Desktop exited')
                time.sleep(.25)
        if browser is None:
            raise RuntimeError('No packaged CDP endpoint')
        page = browser.contexts[0].pages[0]
        page.on('pageerror', lambda error: report['browser_errors'].append({'case': recorder.case, 'at': time.time(), 'error': str(error).replace(active.api_key, '[redacted]') if active.api_key else str(error)}))
        page.set_viewport_size({'width': 1280, 'height': 900})
        page.wait_for_selector('textarea[aria-autocomplete=list]', timeout=120000)
        return browser, page

    try:
        with sync_playwright() as p:
            started = time.perf_counter()
            browser, page = launch(p)
            report['desktop_startup_ms'] = (time.perf_counter()-started)*1000
            report['build'] = page.evaluate('window.reverie.paths()')
            for task in fixture['tasks']:
                if task['id'] not in args.tasks:
                    continue
                for attempt in range(1, args.attempts+1):
                    case_id = f"{task['id']}-{attempt}"
                    case_out = output / case_id
                    case_out.mkdir()
                    session = sessions[case_id]
                    # Production API refreshes the real sidebar after external synthetic-session creation.
                    page.reload()
                    page.locator('.session-item').filter(has_text='RIU quality ' + case_id).click(timeout=120000)
                    page.locator('.session-loading').wait_for(state='hidden', timeout=60000)
                    case = {'id': case_id, 'task': task['id'], 'attempt': attempt, 'session_id': session.id, 'checks': [], 'turns': []}
                    report['cases'].append(case)
                    recorder.case = case_id
                    start_event_capture(page)
                    print(json.dumps({'stage': case_id, 'model': active.model}), flush=True)

                    def send(prompt, stage):
                        case['phase'] = 'model-' + stage
                        started = time.perf_counter()
                        request_start = len(recorder.records)
                        event_start = start_event_capture(page)
                        page_start = page.evaluate('performance.now()')
                        page.locator('textarea[aria-autocomplete=list]').fill(prompt)
                        page.get_by_role('button', name='发送', exact=True).click()
                        stop = page.get_by_role('button', name='停止', exact=True)
                        mismatches = []
                        while True:
                            events = page.evaluate('n=>window.__qualityEvents.slice(n).filter(item=>item.event.type==="executors.changed")', event_start)
                            began, active_lease = execution_state(events, session.id)
                            if began and not active_lease:
                                break
                            elapsed = time.perf_counter()-started
                            if active_lease and not stop.is_visible() and not mismatches:
                                mismatches.append({'at_ms': elapsed*1000, 'event_count': len(events)})
                            if elapsed > args.timeout:
                                case['turns'].append({'stage': stage, 'model_turn_ms': elapsed*1000, 'timeout': True, 'request_indices': list(range(request_start, len(recorder.records)))})
                                raise TimeoutError('Production execution lease did not finish before the turn deadline')
                            page.wait_for_timeout(500)
                        stop.wait_for(state='hidden', timeout=30000)
                        page.wait_for_timeout(250)
                        turn = {'stage': stage, 'model_turn_ms': (time.perf_counter()-started)*1000, 'request_indices': list(range(request_start, len(recorder.records)))}
                        requests = recorder.records[request_start:]
                        if requests:
                            turn['local_before_first_request_ms'] = (requests[0]['started_monotonic']-started)*1000
                            last = requests[-1]
                            if 'complete_ms' in last:
                                turn['local_after_last_response_ms'] = (time.perf_counter()-last['started_monotonic'])*1000-last['complete_ms']
                        turn['active_lease_without_stop_button'] = mismatches
                        turn_events = page.evaluate('n=>window.__qualityEvents.slice(n)', event_start)
                        for item in turn_events:
                            event = item.get('event', {})
                            if event.get('type') == 'prompt.event':
                                event = event.get('event', {})
                            kind = event.get('type')
                            if kind in {'reasoning.delta', 'assistant.delta'} and event.get('text'):
                                turn.setdefault('first-' + kind + '-renderer-event-ms', item['at']-page_start)
                            if kind == 'ui.event':
                                inner = event.get('event', {})
                                if inner.get('event') in {'tool_start', 'tool_result', 'view_ready'}:
                                    turn.setdefault('first-' + inner['event'] + '-renderer-event-ms', item['at']-page_start)
                        case['turns'].append(turn)
                        dump(case_out / (stage + '-events.json'), page.evaluate('window.__qualityEvents'))
                        restored = manager.load_session(session.id)
                        dump(case_out / (stage + '-session.json'), restored.to_dict())
                        errors = page.locator('.inline-error').all_text_contents()
                        if errors:
                            raise RuntimeError('\n'.join(errors))
                        case['phase'] = 'browser-' + stage
                        return restored

                    def frame():
                        anchor = page.locator('.interactive-view-anchor').last
                        anchor.wait_for(timeout=15000)
                        anchor.scroll_into_view_if_needed()
                        expand = anchor.get_by_role('button', name='展开', exact=True)
                        if expand.count():
                            expand.click()
                        iframe = page.locator('.interactive-view iframe').last
                        iframe.wait_for(timeout=30000)
                        inside = iframe.element_handle().content_frame()
                        inside.locator('body').wait_for()
                        return iframe, inside

                    try:
                        prompt = task['prompt'] if task['id'] == 'text' else fixture['common'] + task['prompt']
                        saved = send(prompt, 'generation')
                        calls = [c for m in saved.messages for c in m.get('tool_calls', [])]
                        names = [c.get('function', {}).get('name') for c in calls]
                        case['tool_names'] = names
                        case['violations'] = tool_scope_violations(names, fixture, task)
                        case['repair_count'] = max(0, names.count('render_view')-1, names.count('create_file')-1)
                        if task['id'] == 'text':
                            answer = '\n'.join(str(m.get('content') or '') for m in saved.messages if m.get('role') == 'assistant')
                            case['checks'].append({'name': 'plain-text-answer', 'passed': not calls and bool(re.search('3[,，]?168', answer)), 'detail': answer})
                        else:
                            iframe, inside = frame()
                            store = ViewStore.for_project(workspace)
                            original_ref = visible_view_references(saved.messages)[-1]
                            original_path, original_manifest = store.resolve_entry(session.id, *original_ref)
                            original_hash = hashlib.sha256(original_path.read_bytes()).hexdigest()
                            case['original_revision'] = {'manifest': original_manifest.to_dict(), 'sha256': original_hash}
                            case['local_render_marks'] = page.evaluate("({time_origin:performance.timeOrigin,marks:performance.getEntriesByType('mark').filter(e=>e.name.startsWith('riu-view:')).map(e=>({name:e.name,start_ms:e.startTime}))})")
                            inside.evaluate("window.__qualityInputTimings=[];document.addEventListener('input',e=>{const start=performance.now(),control=e.target.getAttribute('aria-label')||e.target.id||e.target.type;requestAnimationFrame(()=>requestAnimationFrame(()=>window.__qualityInputTimings.push({control,input_to_two_frames_ms:performance.now()-start})))},true)")
                            page.screenshot(path=str(case_out / 'generated.png'), full_page=True)
                            dump(case_out / 'generated-dom.json', {'text': inside.locator('body').inner_text(), 'controls': inside.locator('input,select,button').evaluate_all("es=>es.map(e=>({tag:e.tagName,type:e.type,label:e.getAttribute('aria-label'),id:e.id,text:e.textContent,value:e.value}))")})
                            if not args.generation_only:
                                # Tab may leave an inline frame and scroll to a long
                                # following reply, legitimately evicting the lazy view.
                                # Pin its presentation for business checks; mode and
                                # reload checks below still exercise the real lifecycle.
                                iframe.locator('..').locator('[data-view-mode="fullscreen"]').click()
                                case['business_check_display_mode'] = 'fullscreen'
                                semantic_checks(inside, task, record=case['checks'].append)
                                doc_id = inside.evaluate('window.__qualityInstance=String(performance.timeOrigin)+String(Math.random())')
                                for mode in ['fullscreen', 'pip', 'inline']:
                                    iframe.locator('..').locator(f'[data-view-mode="{mode}"]').click()
                                    page.wait_for_timeout(150)
                                    case['checks'].append({'name': 'same-instance-' + mode, 'passed': inside.evaluate('window.__qualityInstance') == doc_id})
                                    inside.evaluate('window.scrollTo(0,0)')
                                    layout = control(inside, task['control']).evaluate('e=>({top:e.getBoundingClientRect().top,bottom:e.getBoundingClientRect().bottom,height:innerHeight,width:innerWidth,scroll:document.documentElement.scrollWidth})')
                                    case['checks'].append({'name': 'layout-' + mode, 'passed': layout['scroll'] <= layout['width']+2 and (mode != 'pip' or 0 <= layout['top'] < layout['height']), 'detail': layout})
                                    page.screenshot(path=str(case_out / (mode+'.png')), full_page=True)
                                    iframe.screenshot(path=str(case_out / (mode+'-frame.png')))
                                before = inside.locator('body').evaluate('e=>({bg:getComputedStyle(e).backgroundColor,color:getComputedStyle(e).color})')
                                theme = 'dark' if page.evaluate('document.documentElement.dataset.theme') == 'light' else 'light'
                                page.evaluate('v=>window.reverie.setAppearance(v)', theme)
                                page.wait_for_timeout(300)
                                after = inside.locator('body').evaluate('e=>({bg:getComputedStyle(e).backgroundColor,color:getComputedStyle(e).color})')
                                case['checks'].append({'name': 'live-host-theme', 'passed': before != after, 'detail': {'before': before, 'after': after}})
                                expected = control(inside, task['control']).input_value()
                                expected_controls = snapshot_controls(inside)
                                page.wait_for_timeout(1000)
                                case['local_input_samples'] = inside.evaluate('window.__qualityInputTimings || []')
                                page.reload()
                                page.locator('.session-item').filter(has_text='RIU quality ' + case_id).click(timeout=120000)
                                _, inside = frame()
                                page.wait_for_timeout(500)
                                case['checks'].append({'name': 'saved-state-reload', 'passed': control(inside, task['control']).input_value() == expected, 'expected': expected})
                                case['checks'].append({'name': 'all-control-state-reload', 'passed': snapshot_controls(inside) == expected_controls, 'expected': expected_controls, 'actual': snapshot_controls(inside)})
                                case['generation_passed'] = all(c['passed'] for c in case['checks']) and not case['violations']
                                # Natural-language change always travels through the normal composer/executor.
                                modification = task['modify']
                                if 'forbidden_tools' not in fixture:
                                    modification += '继续只使用 create_file 和 render_view，不读取其他文件或调用其他工具。'
                                saved = send(modification, 'modification')
                                modified_iframe, inside = frame()
                                modified_iframe.locator('..').locator('[data-view-mode="fullscreen"]').click()
                                revised_ref = visible_view_references(saved.messages)[-1]
                                revised_path, revised_manifest = store.resolve_entry(session.id, *revised_ref)
                                case['modified_revision'] = {'manifest': revised_manifest.to_dict(), 'sha256': hashlib.sha256(revised_path.read_bytes()).hexdigest()}
                                case['checks'].append({'name': 'stored-version-history', 'passed': revised_ref[0] == original_ref[0] and revised_ref[1] > original_ref[1] and hashlib.sha256(original_path.read_bytes()).hexdigest() == original_hash})
                                page.screenshot(path=str(case_out/'modified.png'), full_page=True)
                                semantic_checks(inside, task, modified=True, record=lambda c: case['checks'].append({**c, 'name': 'modified-'+c['name']}))
                                case['recovery_control'] = control(inside, task['control']).input_value()
                                case['recovery_controls'] = snapshot_controls(inside)
                                page.wait_for_timeout(1000)
                                old_views = [c for m in saved.messages for c in m.get('tool_calls', []) if c.get('function', {}).get('name') == 'render_view']
                                try:
                                    arguments = json.loads(old_views[-1]['function']['arguments'])
                                    case['checks'].append({'name': 'replacement-version-provenance', 'passed': bool(arguments.get('replaces_view_id')), 'detail': arguments.get('replaces_view_id')})
                                except (ValueError, IndexError, KeyError):
                                    case['checks'].append({'name': 'replacement-version-provenance', 'passed': False})
                        case['outcome'] = quality_outcome(case['checks'], case['violations'], case['repair_count'], generation_only=args.generation_only and task['id'] != 'text')
                    except Exception as error:
                        case['error'] = type(error).__name__ + ': ' + str(error)
                        case['outcome'] = 'timeout' if 'Timeout' in type(error).__name__ and case.get('phase', '').startswith('model-') else ('service_unavailable' if re.search(r'\b(400|401|403|404|429|5\d\d)\b|rate.limit|overload', str(error), re.I) else 'validator_or_product_error')
                        try:
                            dump(case_out/'failure-before-cancel-events.json', page.evaluate('window.__qualityEvents'))
                            page.screenshot(path=str(case_out/'failure-before-cancel.png'), full_page=True)
                            stop = page.get_by_role('button', name='停止', exact=True)
                            if stop.is_visible():
                                stop.click()
                                stop.wait_for(state='hidden', timeout=30000)
                            state = page.evaluate('window.reverie.workbench("executors")')
                            if any(entry.get('sessionId') == session.id for entry in state.get('entries', [])):
                                case['host_cancel_fallback'] = 'Execution lease still active after UI cancellation; invoked the same host cancellation action.'
                                page.evaluate('owner=>window.reverie.cancel(owner)', {'projectRoot': str(workspace), 'sessionId': session.id})
                                page.wait_for_function('async id=>!(await window.reverie.workbench("executors")).entries.some(e=>e.sessionId===id)', arg=session.id, timeout=30000)
                            dump(case_out/'failure-events.json', page.evaluate('window.__qualityEvents'))
                            page.screenshot(path=str(case_out/'failure.png'), full_page=True)
                        except Exception as cleanup_error:
                            case['capture_error'] = str(cleanup_error)
                    finally:
                        saved = manager.load_session(session.id)
                        if saved:
                            dump(case_out/'final-session.json', saved.to_dict())
                            final_names = [c.get('function', {}).get('name') for m in saved.messages for c in m.get('tool_calls', [])]
                            case['all_tool_names'] = final_names
                            case['violations'] = tool_scope_violations(final_names, fixture, task)
                            if case['violations']:
                                case['outcome'] = 'model_violation'
                        case['requests'] = [r for r in recorder.records if r['case'] == case_id]
                        forced = [name for r in case['requests'] for name in r.get('response_tool_names', []) if name in case.get('violations', []) and (r.get('tool_choice') or {}).get('function', {}).get('name') == name]
                        case['host_forced_scope_violations'] = forced
                        case['model_scope_violations'] = [name for name in case.get('violations', []) if name not in forced]
                        if forced and not case['model_scope_violations']:
                            case['outcome'] = 'host_routing_violation'
                        if any(r.get('upstream_stream_error') for r in case['requests']):
                            case['outcome'] = 'service_unavailable'
                        case['transport_incidents'] = [r['transport_error'] for r in case['requests'] if r.get('transport_error')]
                        if case['transport_incidents'] and case.get('outcome') not in {'timeout', 'first_pass', 'repaired_success', 'model_violation', 'host_routing_violation'}:
                            case['outcome'] = 'service_transport_error'
                        case['final_phase'] = case.get('phase')
                        case['artifacts'] = []
                        artifact_paths = set()
                        for message in saved.messages if saved else []:
                            for call in message.get('tool_calls', []):
                                function = call.get('function', {})
                                if function.get('name') not in {'create_file', 'render_view'}:
                                    continue
                                try:
                                    arguments = json.loads(function.get('arguments', '{}'))
                                    candidate = arguments.get('artifact_path') or arguments.get('path')
                                    if candidate:
                                        artifact_paths.add((workspace / candidate).resolve())
                                except (ValueError, TypeError):
                                    pass
                        for f in sorted(artifact_paths):
                            if not f.is_relative_to(workspace) or not f.is_file() or f.suffix.lower() not in {'.html', '.htm'}:
                                continue
                            snapshot = case_out / 'model-artifacts' / f.relative_to(workspace)
                            snapshot.parent.mkdir(parents=True, exist_ok=True)
                            shutil.copy2(f, snapshot)
                            case['artifacts'].append({'path': str(snapshot), 'workspace_path': str(f), 'sha256': hashlib.sha256(snapshot.read_bytes()).hexdigest(), 'bytes': snapshot.stat().st_size})
                        save()
                        print(json.dumps({'case': case_id, 'outcome': case.get('outcome'), 'checks': len(case['checks']), 'error': case.get('error')}, ensure_ascii=True), flush=True)
                        time.sleep(5)
            browser.close()
            recoverable = [case for case in report['cases'] if 'recovery_control' in case]
            if recoverable:
                if process.poll() is None:
                    subprocess.run(['taskkill', '/PID', str(process.pid), '/T', '/F'], capture_output=True)
                    process.wait(timeout=30)
                time.sleep(2)
                request_count = len(recorder.records)
                started = time.perf_counter()
                browser, page = launch(p)
                report['restart_startup_ms'] = (time.perf_counter()-started)*1000
                for case in recoverable:
                    started = time.perf_counter()
                    task = next(task for task in fixture['tasks'] if task['id'] == case['task'])
                    try:
                        page.locator('.session-item').filter(has_text='RIU quality ' + case['id']).click(timeout=120000)
                        page.locator('.session-loading').wait_for(state='hidden', timeout=60000)
                        anchor = page.locator('.interactive-view-anchor').last
                        anchor.scroll_into_view_if_needed()
                        expand = anchor.get_by_role('button', name='展开', exact=True)
                        if expand.count():
                            expand.click()
                        iframe = page.locator('.interactive-view iframe').last
                        iframe.wait_for(timeout=30000)
                        inside = iframe.element_handle().content_frame()
                        actual = control(inside, task['control']).input_value()
                        case['checks'].append({'name': 'actual-process-restart-recovery', 'passed': actual == case['recovery_control'], 'detail': {'actual': actual, 'expected': case['recovery_control'], 'local_ms': (time.perf_counter()-started)*1000}})
                        page.wait_for_timeout(500)
                        case['checks'].append({'name': 'all-control-process-restart-recovery', 'passed': snapshot_controls(inside) == case['recovery_controls'], 'expected': case['recovery_controls'], 'actual': snapshot_controls(inside)})
                        page.screenshot(path=str(output/case['id']/'restart.png'), full_page=True)
                    except Exception as error:
                        case['checks'].append({'name': 'actual-process-restart-recovery', 'passed': False, 'detail': str(error)})
                    if case.get('outcome') in {'first_pass', 'repaired_success'} and not all(c['passed'] for c in case['checks']):
                        case['outcome'] = 'semantic_failure'
                    save()
                report['restart_makes_no_model_requests'] = len(recorder.records) == request_count
                browser.close()
    finally:
        if process and process.poll() is None:
            subprocess.run(['taskkill', '/PID', str(process.pid), '/T', '/F'], capture_output=True)
        recorder.close()
        log.close()
        cleaned = []
        for f in app_root.rglob('*'):
            if f.is_file() and ('config' in f.name.lower() or f.suffix in {'.json', '.bak'}):
                data = f.read_text(encoding='utf-8', errors='replace')
                if active.api_key and active.api_key in data:
                    f.write_text(data.replace(active.api_key, ''), encoding='utf-8')
                    cleaned.append(str(f))
        report['credential_cleanup'] = {'complete': True, 'files': cleaned}
        save()


if __name__ == '__main__':
    main()
