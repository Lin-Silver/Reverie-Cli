"""Real vision/tool qualification through a frozen SDK kernel and owned editor."""
from copy import deepcopy
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
import argparse
import hashlib
import json
import os
import queue
import sqlite3
import subprocess
import sys
import threading
import time
from urllib.parse import urlsplit

import httpx

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'ReverieCli-py'))
from reverie.config import ConfigManager
from reverie.desktop_catalog import apply_model_selection
from reverie.computer_use.runtime import ComputerUseRuntime
from desktop_process import stop_process


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--exe', type=Path, required=True)
    args = parser.parse_args()
    output = ROOT / '.runtime/aio-implementation' / ('packaged-vision-' + time.strftime('%Y%m%d-%H%M%S'))
    output.mkdir()
    workspace = output / 'workspace'
    workspace.mkdir()
    config = deepcopy(ConfigManager(ROOT).load())
    apply_model_selection(config, 'sensenova', 'sensenova-6.8-flash')
    assert config.active_model.supports_vision, 'Configured model must support vision'
    assert not config.api_compatibility, 'Vision requires structured API requests'
    upstream=urlsplit(config.active_model.base_url)
    upstream_origin=f'{upstream.scheme}://{upstream.netloc}'
    request_evidence=[]
    class RequestProbe(BaseHTTPRequestHandler):
        def log_message(self,*_args):
            pass
        def do_POST(self):
            body=self.rfile.read(int(self.headers['Content-Length']))
            payload=json.loads(body)
            def count_images(value):
                if isinstance(value,dict):
                    return int(value.get('type') in {'image','image_url'})+sum(count_images(item) for item in value.values())
                if isinstance(value,list):
                    return sum(count_images(item) for item in value)
                return 0
            evidence={'model':payload.get('model'),'image_parts':count_images(payload.get('messages',[]))}
            request_evidence.append(evidence)
            headers={key:value for key,value in self.headers.items() if key.lower() not in {'host','content-length','connection'}}
            try:
                with httpx.Client(timeout=90) as client:
                    response=client.post(upstream_origin+self.path,content=body,headers=headers)
                evidence['status']=response.status_code
                self.send_response(response.status_code)
                self.send_header('Content-Type',response.headers.get('content-type','application/json'))
                self.send_header('Content-Length',str(len(response.content)))
                self.end_headers()
                self.wfile.write(response.content)
            except Exception as error:
                evidence['error']=type(error).__name__
                self.send_error(502,'Qualification forwarding failed')
    server=ThreadingHTTPServer(('127.0.0.1',0),RequestProbe)
    threading.Thread(target=server.serve_forever,daemon=True).start()
    config.sensenova={**config.sensenova,'api_url':f'http://127.0.0.1:{server.server_port}'+upstream.path}
    config.mode, config.api_max_retries, config.api_timeout = 'aio', 0, 60
    config.auto_index, config.stream_responses = False, False
    config.security = {**config.security, 'permission_level':'full_control', 'permission_mode':'default'}
    os.environ['REVERIE_APP_ROOT'] = str(output / 'app-root')
    os.environ['NO_PROXY']=os.environ['no_proxy']='127.0.0.1,localhost'
    manager = ConfigManager(workspace)
    manager.ensure_dirs()
    manager.save(config)
    fixture_exe = output / 'ReverieDesktopFixture.exe'
    subprocess.run(['C:/Windows/Microsoft.NET/Framework64/v4.0.30319/csc.exe', '/nologo', '/target:winexe',
                    '/out:' + str(fixture_exe), '/r:System.Windows.Forms.dll', '/r:System.Drawing.dll',
                    str(ROOT / 'scripts/verification/fixtures/computer-use/Fixture.cs')], check=True, capture_output=True)
    fixture = subprocess.Popen([str(fixture_exe), str(output / 'saved.txt')], creationflags=subprocess.CREATE_NO_WINDOW)
    process = None
    runtime = ComputerUseRuntime(output)
    report = {'exe':str(args.exe.resolve()), 'exe_sha256':hashlib.sha256(args.exe.read_bytes()).hexdigest(),
              'model':'sensenova-6.8-flash', 'vision':True, 'passed':False, 'tools':[], 'approval_denials':[]}
    messages = queue.Queue()
    try:
        deadline = time.monotonic() + 20
        while True:
            windows = [window for window in runtime.command('list-windows')['data'] if window['pid'] == fixture.pid]
            if windows:
                break
            if time.monotonic() > deadline:
                raise TimeoutError('Owned fixture did not appear')
            time.sleep(.2)
        window_id = windows[0]['id']
        process = subprocess.Popen([str(args.exe.resolve()), '--sdk-bridge'], cwd=workspace, env=os.environ.copy(),
                                   stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                                   text=True, encoding='utf-8', creationflags=subprocess.CREATE_NO_WINDOW)
        def read():
            for line in process.stdout:
                try:
                    messages.put(json.loads(line))
                except json.JSONDecodeError:
                    pass
        threading.Thread(target=read, daemon=True).start()
        sequence = 0
        def send(action, payload, identity):
            process.stdin.write(json.dumps({'id':identity,'action':action,'payload':payload},ensure_ascii=False)+'\n')
            process.stdin.flush()
        def request(action, payload):
            nonlocal sequence
            sequence += 1
            identity = f'qualification-{sequence}'
            send(action,payload,identity)
            deadline = time.monotonic() + 300
            while time.monotonic() < deadline:
                response = messages.get(timeout=max(.01,deadline-time.monotonic()))
                event = response.get('event',{})
                if event.get('type') == 'approval.request':
                    report['approval_denials'].append({'tool':event.get('tool')})
                    send('resolveApproval',{'approvalId':event['approval_id'],'decision':'deny'},'refusal')
                if event.get('type') in {'tool_start','tool.start'}:
                    arguments = event.get('arguments') or event.get('tool_arguments') or {}
                    report['tools'].append({'name':event.get('tool_name') or event.get('tool'),'arguments':arguments})
                if response.get('id') == identity and response.get('type') != 'prompt.event':
                    if response.get('type') == 'error':
                        raise RuntimeError(response.get('error'))
                    return response
            raise TimeoutError('Frozen kernel request did not complete')
        request('initialize',{'projectRoot':str(workspace),'deferPayloads':True})
        request('aioControl',{'assistantId':'aio','enable':True})
        request('aioControl',{'assistantId':'aio','changes':{'proactive':False}})
        prompt = (f'Perform a bounded desktop verification only in window_id={window_id}, an owned disposable fixture. '
                  'First use computer_screenshot with this exact window_id and describe its visual layout. '
                  'Then use computer_find to find the textfield named Verification editor, '
                  'computer_set_value once to set exactly Reverie MODEL 中文, and computer_get to verify the exact value. '
                  'Use only these four desktop tools. Do not touch other windows, launch programs, press keys, write files, '
                  'or repeat a delivered write. For screenshot and find pass only this window_id, never app or screen. '
                  'Report the editor surface color and finish after verification.')
        result = request('runPrompt',{'projectRoot':str(workspace),'assistantId':'aio','sessionId':'aio-mainline',
                                     'prompt':prompt,'noIndex':True,'stream':False})['result']
        matches = runtime.command('find',['--window-id='+window_id,'--name=Verification editor','--exact'])['data']['matches']
        reference = next(item['ref_id'] for item in matches if item['role']=='textfield')
        value = runtime.command('get',[reference,'--property=value'])['data']['value']
        # Non-streaming requests need not emit streaming tool events. The
        # committed transcript is the authoritative record of their calls.
        with sqlite3.connect((output/'app-root/.reverie/aio/conversations.sqlite3').as_uri()+'?mode=ro',uri=True) as database:
            history=[json.loads(row[0]) for row in database.execute("SELECT payload FROM messages WHERE session_id='aio-mainline' ORDER BY sequence")]
        report['tools']=[{'name':call['function']['name'],'arguments':json.loads(call['function'].get('arguments') or '{}')} for message in history for call in message.get('tool_calls',[])]
        report['tool_source']='committed conversation history'
        report['screenshots_inline_in_database']=any('data:image/' in json.dumps(message) for message in history)
        report['final_value'], report['answer'], report['result_success'] = value,result.get('output_text'),result.get('success')
        names = [tool['name'] for tool in report['tools']]
        scope_verified=all(tool['name'] in {'computer_screenshot','computer_find','computer_set_value','computer_get'} and
                           tool['arguments'].get('window_id',window_id)==window_id and not tool['arguments'].get('app') and
                           'screen' not in tool['arguments'] for tool in report['tools'])
        report['scope_verified']=scope_verified
        report['requests']=request_evidence
        report['vision_transmitted']=any(item['image_parts']>0 and item.get('status')==200 for item in request_evidence)
        report['passed'] = bool(result.get('success') and value=='Reverie MODEL 中文' and
                                scope_verified and report['vision_transmitted'] and 'computer_screenshot' in names and names.count('computer_set_value')==1 and 'computer_get' in names)
        request('shutdown',{})
    except Exception as error:
        report['error'] = type(error).__name__ + ': ' + str(error)
    finally:
        stop_process(process)
        stop_process(fixture)
        runtime.close()
        server.shutdown();server.server_close()
        (output / 'report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps({'passed':report['passed'],'error':report.get('error'),'report':str(output/'report.json')},ensure_ascii=False),flush=True)
    return 0 if report['passed'] else 1


if __name__=='__main__':
    sys.stdout.reconfigure(encoding='utf-8')
    raise SystemExit(main())
