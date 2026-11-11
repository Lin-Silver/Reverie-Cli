"""Exercise the Windows AiO popup, real scheduler, isolated worker and acceptance path."""
from pathlib import Path
from copy import deepcopy
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import argparse
import hashlib
import json
import os
import socket
import subprocess
import sys
import threading
import time
from urllib.parse import urlsplit

import httpx
import psutil
from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'ReverieCli-py'))
from reverie.config import ConfigManager
from reverie.desktop_catalog import apply_model_selection
from reverie.session.aio_store import AiOStore
from desktop_process import launch_options, native_window_state, stop_process, wait_for_packaged_page


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--exe', type=Path, required=True)
    args = parser.parse_args()
    output = ROOT / '.runtime/aio-implementation' / ('real-host-' + time.strftime('%Y%m%d-%H%M%S'))
    output.mkdir()
    root, app_root, home = [output / name for name in ('workspace', 'app-root', 'desktop-home')]
    for directory in (root, app_root, home):
        directory.mkdir()
    config = deepcopy(ConfigManager(ROOT).load())
    apply_model_selection(config, 'sensenova', 'sensenova-6.8-flash')
    upstream = urlsplit(config.active_model.base_url)
    upstream_origin = f'{upstream.scheme}://{upstream.netloc}'
    request_evidence = []
    class RequestProbe(BaseHTTPRequestHandler):
        def log_message(self, *_args):
            pass
        def do_POST(self):
            body = self.rfile.read(int(self.headers['Content-Length']))
            payload = json.loads(body)
            system = str(payload.get('system', ''))
            evidence = {'model': payload.get('model'),
                        'ownership_context_present': 'managed isolated directory' in system,
                        'verification_round': 'Verify this task against its acceptance conditions:' in str(payload.get('messages', []))}
            request_evidence.append(evidence)
            headers = {key: value for key, value in self.headers.items()
                       if key.lower() not in {'host', 'content-length', 'connection'}}
            try:
                with httpx.Client(timeout=120) as client, client.stream('POST', upstream_origin + self.path, content=body, headers=headers) as response:
                    evidence['status'] = response.status_code
                    self.send_response(response.status_code)
                    self.send_header('Content-Type', response.headers.get('content-type', 'application/json'))
                    self.send_header('Connection', 'close')
                    self.end_headers()
                    for chunk in response.iter_bytes():
                        self.wfile.write(chunk)
                        self.wfile.flush()
            except Exception as error:
                evidence['error'] = type(error).__name__
            self.close_connection = True
    server = ThreadingHTTPServer(('127.0.0.1', 0), RequestProbe)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    config.sensenova = {**config.sensenova, 'api_url': f'http://127.0.0.1:{server.server_port}' + upstream.path}
    config.auto_index = False
    config.api_max_retries = 0
    config.security = {**config.security, 'permission_level':'workspace_write', 'permission_mode':'default'}
    os.environ['REVERIE_APP_ROOT'] = str(app_root)
    os.environ['NO_PROXY'] = os.environ['no_proxy'] = '127.0.0.1,localhost'
    manager = ConfigManager(root)
    manager.ensure_dirs()
    manager.save(config)
    (root / '.gitignore').write_text('.reverie/\n', encoding='utf-8')
    subprocess.run(['git', 'init', '-b', 'main', str(root)], check=True, capture_output=True)
    subprocess.run(['git', '-C', str(root), 'add', '.gitignore'], check=True, capture_output=True)
    subprocess.run(['git', '-C', str(root), '-c', 'user.name=Qualification', '-c', 'user.email=qualification@example.invalid', 'commit', '-m', 'Fixture'], check=True, capture_output=True)
    (root / 'user-work.txt').write_bytes(b'Uncommitted user bytes\r\n')
    settings = home / '.reverie/desktop/desktop-settings.json'
    settings.parent.mkdir(parents=True)
    settings.write_text(json.dumps({'coreAppRoot':str(app_root),'projectRoot':str(root),'workspaceRoots':[str(root)],'ui':{'language':'zh-CN','backgroundPreset':'none'}}), encoding='utf-8')
    environment = {**os.environ, 'HOME':str(home), 'XDG_CONFIG_HOME':str(home / '.config'), 'PORTABLE_EXECUTABLE_DIR':str(home), 'NO_PROXY':'127.0.0.1,localhost', 'no_proxy':'127.0.0.1,localhost'}
    environment.pop('ELECTRON_RUN_AS_NODE', None)
    with socket.socket() as channel:
        channel.bind(('127.0.0.1', 0))
        port = channel.getsockname()[1]
    report = {'model':'sensenova-6.8-flash', 'exe':str(args.exe.resolve()), 'exe_sha256':hashlib.sha256(args.exe.read_bytes()).hexdigest(),
              'asar_sha256':hashlib.sha256((args.exe.parent/'resources/app.asar').read_bytes()).hexdigest(), 'passed':False, 'errors':[]}
    process = browser = None
    tracked = {}
    try:
        with (output / 'desktop.log').open('w', encoding='utf-8') as log, sync_playwright() as playwright:
            process = subprocess.Popen([str(args.exe.resolve()), '--gui', '--project', str(root), f'--remote-debugging-port={port}'], env=environment, stdout=log, stderr=log, **launch_options(visible=True))
            browser, page = wait_for_packaged_page(playwright, process, port)
            page.set_default_timeout(120000)
            page.wait_for_selector('.composer textarea')
            report['native_initial_window'] = native_window_state(process.pid)
            if not report['native_initial_window']['visible']:
                raise RuntimeError('The graphical host has no visible native window.')
            page.wait_for_function("document.querySelector('.transcript')?.getAttribute('aria-busy')==='false'")
            page.on('pageerror', lambda error:report['errors'].append(str(error)))
            page.evaluate("""root => {
              window.__qualificationApprovals=[];
              window.__qualificationHostErrors=[];
              window.reverie.onEvent(message => {
                if(message.type==='aio.error')window.__qualificationHostErrors.push(message.error);
                const event=message.event || {};
                if(event.type==='approval.request') {
                  window.__qualificationApprovals.push({tool:event.tool,reason:event.message,sessionId:event.session_id});
                  window.reverie.request('resolveApproval',{projectRoot:root,sessionId:event.session_id,assistantId:'aio',approvalId:event.approval_id,decision:'deny'}).catch(error=>window.__qualificationApprovals.push({error:String(error)}));
                }
              });
            }""", str(root))
            request = lambda action, payload: page.evaluate('([action,payload])=>window.reverie.request(action,payload)', [action,payload])
            request('aioControl', {'assistantId':'aio','enable':True})
            store = AiOStore(app_root / '.reverie/aio')
            store.append('proactive', {'text':'AiO 实际模型验收\n请在此窗直接回复测试任务。\n' + '这是能够滚动查看的完整正文。\n' * 60}, event_id='host-qualification-popup', visible=True, outbox=True)
            request('aioControl', {'assistantId':'aio','changes':{'proactive':True}})
            deadline = time.monotonic() + 30
            popup = None
            while time.monotonic() < deadline:
                popup = next((candidate for context in browser.contexts for candidate in context.pages if candidate != page and not candidate.is_closed() and candidate.url.startswith('data:text/html')), None)
                if popup:
                    popup.wait_for_function("document.querySelector('#body').textContent.includes('AiO 实际模型验收')")
                    break
                page.wait_for_timeout(100)
            if not popup:
                raise RuntimeError('The AiO reply window did not appear.')
            popup.screenshot(path=str(output / 'popup.png'))
            popup.locator('#reply').fill('This is an explicitly authorized qualification. Create exactly one Reverie worker task in the listed disposable workspace. Create host-proof.txt with UTF-8 content AiO VERIFIED 中文 followed by one LF newline. Acceptance: independently read the saved file and match that exact content. Use native file tools. Do not run shell commands, use desktop tools, or create any other task.')
            popup.locator('#send').click()
            reply_deadline = time.monotonic()+30
            while not any('host-proof.txt' in str(message.get('content','')) and message.get('role')=='user' for message in store.get_page(store.mainline_id)['messages']):
                if time.monotonic()>reply_deadline:raise TimeoutError('The popup reply was not saved.')
                page.wait_for_timeout(100)
            request('aioControl', {'assistantId':'aio','changes':{'proactive':False}})
            deadline = time.monotonic() + 600
            while time.monotonic() < deadline:
                if process.poll() is not None:
                    raise RuntimeError('The graphical host exited.')
                host_errors=page.evaluate('window.__qualificationHostErrors')
                if host_errors:
                    raise RuntimeError('AiO host failed: ' + str(host_errors))
                for child in psutil.Process(process.pid).children(recursive=True):
                    try:
                        tracked[child.pid] = child.create_time()
                    except psutil.NoSuchProcess:
                        pass
                with store.connect() as db:
                    tasks = [dict(row) for row in db.execute('SELECT id,branch,workspace,state,acceptance,result FROM aio_tasks')]
                report['tasks'] = tasks
                if tasks and all(task['state'] in {'completed','failed','cancelled','waiting_user','waiting_incorporation','interrupted'} for task in tasks):
                    break
                page.wait_for_timeout(500)
            else:
                raise TimeoutError('The host did not retain a terminal or review state within ten minutes.')
            report['approval_denials'] = page.evaluate('window.__qualificationApprovals')
            proof = root / 'host-proof.txt'
            report['exact_artifact'] = proof.exists() and proof.read_bytes() == 'AiO VERIFIED 中文\n'.encode('utf-8')
            report['user_work_preserved'] = (root / 'user-work.txt').read_bytes() == b'Uncommitted user bytes\r\n'
            report['reply_owner'] = any('host-proof.txt' in str(message.get('content','')) for message in store.get_page(store.mainline_id)['messages'])
            report['native_review_readback']=report['native_review_size']=False
            if len(tasks)==1:
                with store.connect() as db:
                    history=[json.loads(row[0]) for row in db.execute('SELECT payload FROM messages WHERE session_id=? ORDER BY sequence',(tasks[0]['branch'],))]
                review=False;operations={}
                for message in history:
                    if message.get('role')=='user' and str(message.get('content','')).startswith('Verify this task against its acceptance conditions:'):
                        review=True
                    if not review:continue
                    for call in message.get('tool_calls',[]):
                        if call['function']['name']=='file_ops':
                            operations[call['id']]=json.loads(call['function'].get('arguments') or '{}').get('operation')
                    operation=operations.get(message.get('tool_call_id'))
                    if operation=='read' and message.get('content')=='AiO VERIFIED 中文\n':report['native_review_readback']=True
                    if operation=='info' and '20 bytes' in str(message.get('content','')):report['native_review_size']=True
            files=subprocess.run(['git','-C',str(root),'ls-files','--others','--exclude-standard'],check=True,capture_output=True,text=True).stdout.splitlines()
            report['unignored_files']=files
            report['bounded_artifacts']=set(files)=={'host-proof.txt','user-work.txt'}
            report['passed'] = len(tasks)==1 and tasks[0]['state']=='completed' and report['exact_artifact'] and report['user_work_preserved'] and report['reply_owner'] and report['native_review_readback'] and report['native_review_size'] and report['bounded_artifacts'] and not report['errors']
            page.screenshot(path=str(output / 'desktop.png'))
    except Exception as error:
        report['error'] = type(error).__name__ + ': ' + str(error)
    finally:
        if browser:
            try: browser.close()
            except Exception: pass
        stop_process(process)
        def survivors():
            remaining = []
            for pid, created in tracked.items():
                try:
                    if psutil.Process(pid).create_time() == created:
                        remaining.append(pid)
                except psutil.NoSuchProcess:
                    pass
            return remaining
        deadline = time.monotonic() + 10
        while survivors() and time.monotonic() < deadline:
            time.sleep(.1)
        report['surviving_owned_processes'] = survivors()
        server.shutdown()
        server.server_close()
        report['requests'] = request_evidence
        reviews = [item for item in request_evidence if item['verification_round']]
        report['review_context_transmitted'] = bool(reviews) and all(item['ownership_context_present'] and item.get('status') == 200 for item in reviews)
        if not report['review_context_transmitted']:
            report['passed'] = False
        if report['surviving_owned_processes']:
            report['passed'] = False
        (output / 'report.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps({'passed':report['passed'],'error':report.get('error'),'report':str(output / 'report.json')}, ensure_ascii=False), flush=True)
    return 0 if report['passed'] else 1


if __name__ == '__main__':
    sys.stdout.reconfigure(encoding='utf-8')
    raise SystemExit(main())
