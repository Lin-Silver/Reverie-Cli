"""Exercise the real packaged UI/kernel/native engine with a deterministic local provider.

This verifies delivery plumbing, not real-model reasoning quality.
"""
from pathlib import Path
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import hashlib
import atexit
import json
import os
import shutil
import socket
import subprocess
import sys
import threading
import time

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'ReverieCli-py'))
sys.path.insert(0, str(ROOT / 'scripts/verification'))
from desktop_process import launch_options, stop_process, wait_for_packaged_page
from reverie.config import ConfigManager, ModelConfig
from reverie.session.manager import SessionManager
from reverie.computer_use.runtime import ComputerUseRuntime

sys.stdout.reconfigure(encoding='utf-8')


def run():
    executable = Path(sys.argv[1]).resolve()
    portable = '--portable' in sys.argv
    work = ROOT / '.runtime' / ('computer-package-' + time.strftime('%Y%m%d-%H%M%S'))
    work.mkdir(parents=True)
    workspace, app_root, home = (work / name for name in ('workspace', 'profile', 'desktop-home'))
    for directory in (workspace, app_root, home): directory.mkdir()
    if portable:
        target = home / executable.name
        shutil.copy2(executable, target)
        executable = target
    os.environ['REVERIE_APP_ROOT'] = str(app_root)
    os.environ['NO_PROXY'] = os.environ['no_proxy'] = '127.0.0.1,localhost'
    evidence = {'scope': 'Packaged UI with local deterministic provider and real native operations', 'requests': [], 'errors': [], 'passed': False}
    fixture_exe = work / 'ReverieDesktopFixture.exe'
    subprocess.run(['C:/Windows/Microsoft.NET/Framework64/v4.0.30319/csc.exe', '/nologo', '/target:winexe',
                    '/out:' + str(fixture_exe), '/r:System.Windows.Forms.dll', '/r:System.Drawing.dll',
                    str(ROOT / 'scripts/verification/fixtures/computer-use/Fixture.cs')], capture_output=True, check=True)
    fixture = subprocess.Popen([str(fixture_exe), str(work / 'saved.txt')], creationflags=subprocess.CREATE_NO_WINDOW)
    atexit.register(stop_process, fixture)
    runtime = ComputerUseRuntime(work)
    deadline = time.monotonic() + 15
    while True:
        windows = [w for w in runtime.command('list-windows')['data'] if w['pid'] == fixture.pid]
        if windows: break
        if time.monotonic() > deadline: raise RuntimeError('Fixture did not appear')
        time.sleep(.2)
    wid = windows[0]['id']

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args): pass
        def do_POST(self):
            request = json.loads(self.rfile.read(int(self.headers['Content-Length'])))
            serialized = json.dumps(request)
            evidence['requests'].append({'model': request['model'], 'images': serialized.count('data:image/'),
                                         'computer_tools': sum(t['function']['name'].startswith('computer_') for t in request.get('tools', []))})
            tools = [m for m in request.get('messages', []) if m.get('role') == 'tool']
            index = len(tools)
            if index < 2:
                name, args = [('computer_status', {}), ('computer_screenshot', {'window_id': wid})][index]
                message = {'role': 'assistant', 'content': None, 'tool_calls': [{'id': 'package_' + str(index), 'type': 'function',
                           'function': {'name': name, 'arguments': json.dumps(args)}}]}
                finish = 'tool_calls'
            else:
                ok = all('"ok":true' in str(m.get('content', '')).replace(' ', '') for m in tools)
                message = {'role': 'assistant', 'content': 'PACKAGE_DESKTOP_VERIFIED' if ok else 'PACKAGE_DESKTOP_FAILED'}
                finish = 'stop'
            if request.get('stream'):
                self.send_response(200); self.send_header('Content-Type', 'text/event-stream'); self.end_headers()
                delta = dict(message)
                if 'tool_calls' in delta:
                    delta['tool_calls'] = [{'index': i, **call} for i, call in enumerate(delta['tool_calls'])]
                payload = {'id': 'package', 'object': 'chat.completion.chunk', 'model': request['model'],
                           'choices': [{'index': 0, 'delta': delta, 'finish_reason': None}]}
                final = {'id': 'package', 'object': 'chat.completion.chunk', 'choices': [{'index': 0, 'delta': {}, 'finish_reason': finish}]}
                self.wfile.write(('data: ' + json.dumps(payload) + '\n\ndata: ' + json.dumps(final) + '\n\ndata: [DONE]\n\n').encode())
            else:
                payload = {'id': 'package', 'object': 'chat.completion', 'model': request['model'],
                           'choices': [{'index': 0, 'message': message, 'finish_reason': finish}],
                           'usage': {'prompt_tokens': 100, 'completion_tokens': 10, 'total_tokens': 110}}
                self.send_response(200); self.send_header('Content-Type', 'application/json'); self.end_headers()
                self.wfile.write(json.dumps(payload).encode())

    server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    config = ConfigManager(workspace)
    cfg = config.load()
    cfg.mode = 'computer-controller'
    cfg.models = [ModelConfig('package-text', 'Package Text', f'http://127.0.0.1:{server.server_port}/v1', api_key='fixture'),
                  ModelConfig('package-vision', 'Package Vision', f'http://127.0.0.1:{server.server_port}/v1', api_key='fixture', supports_vision=True)]
    cfg.active_model_source = 'standard'; cfg.active_model_index = 0
    cfg.security.update(permission_level='full_control', permission_mode='default')
    cfg.api_max_retries = 0; cfg.stream_responses = False
    config.save(cfg)
    manager = SessionManager(config.project_data_dir, project_root=workspace)
    session = manager.create_session('Computer Use package verification')
    manager.save_session(session)
    settings = home / '.reverie/desktop/desktop-settings.json'
    settings.parent.mkdir(parents=True, exist_ok=True)
    settings.write_text(json.dumps({'coreAppRoot': str(app_root), 'projectRoot': str(workspace),
                                   'ui': {'language': 'zh-CN', 'showReasoning': False}}), encoding='utf-8')
    app = browser = playwright = None
    try:
        from playwright.sync_api import expect, sync_playwright
        with socket.socket() as sock:
            sock.bind(('127.0.0.1', 0)); port = sock.getsockname()[1]
        env = {**os.environ, 'PORTABLE_EXECUTABLE_DIR': str(home)}
        env.pop('ELECTRON_RUN_AS_NODE', None)
        # Test a package with no Python/Node/agent-desktop lookup through PATH.
        env['PATH'] = r'C:\Windows\System32;C:\Windows'
        playwright = sync_playwright().start()
        with (work / 'desktop.log').open('w', encoding='utf-8') as log:
            app = subprocess.Popen([str(executable), '--gui', '--project', str(workspace), f'--remote-debugging-port={port}', '--user-data-dir=' + str(home / 'initial-electron-profile')],
                                   env=env, stdout=log, stderr=subprocess.STDOUT, **launch_options())
            if portable:
                extraction_started = time.monotonic()
                extraction_root = home / '.reverie/desktop/app-runtime'
                while not list(extraction_root.glob('.reverie-build-*')):
                    if app.poll() is not None:
                        raise RuntimeError(f'Portable extraction exited with code {app.returncode}')
                    if time.monotonic() - extraction_started > 180:
                        raise TimeoutError('Portable extraction exceeded 180 seconds')
                    time.sleep(.25)
                evidence['portable_extraction_ms'] = round((time.monotonic() - extraction_started) * 1000)
            browser, page = wait_for_packaged_page(playwright, app, port)
            page.on('pageerror', lambda error: evidence['errors'].append(str(error)))
            page.wait_for_selector('textarea[aria-autocomplete=list]', timeout=120000)
            (work / 'initial-visible.txt').write_text(page.locator('body').inner_text(), encoding='utf-8')
            page.locator('.model-trigger').click()
            page.get_by_role('dialog', name='模型来源').wait_for()
            page.get_by_role('button', name='Package Vision', exact=False).click()
            page.locator('.model-trigger').filter(has_text='Package Vision').wait_for(timeout=15000)
            evidence['model_picker_switched'] = True
            for mode in ('reverie', 'computer-controller'):
                tools = page.evaluate('(mode) => window.reverie.request("listTools", {mode})', mode)
                names = [t['name'] for t in tools['tools']]
                evidence[mode + '_computer_tools'] = [n for n in names if n.startswith('computer_')]
                assert len(evidence[mode + '_computer_tools']) == 29
                assert 'get_app_state' not in names
            page.locator('textarea[aria-autocomplete=list]').fill('请执行本地 Computer Use 打包验证。')
            page.get_by_role('button', name='发送', exact=True).click()
            page.get_by_text('PACKAGE_DESKTOP_VERIFIED', exact=False).first.wait_for(timeout=90000)
            # Wait for persisted history: the live activity group remounts when the run ends.
            expect(page.get_by_role('button', name='重命名会话', exact=True)).to_be_enabled(timeout=30000)
            group = page.locator('.activity-group').first
            if group.get_attribute('open') is None:
                group.locator(':scope > summary').click()
            page.locator('.activity-item').first.wait_for()
            evidence['tool_cards'] = page.locator('.activity-item').count()
            assert evidence['tool_cards'] == 2
            for item in page.locator('.activity-item > summary').all(): item.click()
            page.get_by_role('button', name='打开文件预览', exact=True).first.click()
            page.locator('img[src^="data:image/png;base64,"]').first.wait_for(timeout=15000)
            page.get_by_role('button', name='重新加载', exact=True).click()
            page.locator('img[src^="data:image/png;base64,"]').first.wait_for(timeout=15000)
            assert not page.get_by_text('File is outside this workspace.', exact=False).count()
            evidence['screenshot_preview_loaded'] = True
            page.screenshot(path=str(work / 'desktop.png'), full_page=True)
            evidence['desktop_build'] = page.evaluate('window.reverie.paths()')['desktopBuild']
            evidence['passed'] = all(r['model'] == 'package-vision' for r in evidence['requests']) and any(r['images'] > 0 for r in evidence['requests'])
            assert evidence['passed'], evidence
    except Exception as exc:
        evidence['error'] = type(exc).__name__ + ': ' + str(exc)[:2000]
        if browser and browser.contexts and browser.contexts[0].pages:
            page = browser.contexts[0].pages[0]
            page.screenshot(path=str(work / 'failure.png'), full_page=True)
            (work / 'visible.txt').write_text(page.locator('body').inner_text(), encoding='utf-8')
    finally:
        if browser:
            try: browser.close()
            except Exception: pass
        if playwright: playwright.stop()
        stop_process(app)
        fixture.terminate(); fixture.wait(timeout=5)
        server.shutdown(); runtime.close()
        (work / 'summary.json').write_text(json.dumps(evidence, ensure_ascii=False, indent=2), encoding='utf-8')
        print(json.dumps(evidence, ensure_ascii=False)); print('Artifacts: ' + str(work))
    return evidence['passed']


if __name__ == '__main__': sys.exit(0 if run() else 1)
