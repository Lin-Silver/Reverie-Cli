"""Real provider/tool-loop qualification confined to an owned disposable window."""
from pathlib import Path
import copy
import json
import os
import subprocess
import sys
import time
import uuid

sys.stdout.reconfigure(encoding="utf-8")

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'ReverieCli-py'))
from reverie.config import ConfigManager
from reverie.agent.agent import ReverieAgent
from reverie.computer_use.runtime import ComputerUseRuntime
from reverie.computer_use.operations import execute as desktop_execute
from reverie.tools.base import ToolResult
from reverie.tools.computer import supports_vision


def run():
    model_name = sys.argv[1] if len(sys.argv) > 1 else 'active'
    mode = sys.argv[2] if len(sys.argv) > 2 else 'reverie'
    config = copy.deepcopy(ConfigManager(ROOT).load())
    if model_name.startswith('source:'):
        config.active_model_source = model_name.removeprefix('source:')
    elif model_name != 'active':
        config.active_model_source = 'standard'
        config.active_model_index = next(i for i, model in enumerate(config.models) if model.model == model_name)
    model = config.active_model
    if '--vision' in sys.argv:
        model.supports_vision = True
    if '--text' in sys.argv:
        model.supports_vision = False
    if '--vision' in sys.argv or '--text' in sys.argv:
        # Provider sources rebuild active_model on each read. Keep this isolated
        # qualification model in the standard list so the override is effective.
        config.models = [model]
        config.active_model_source = 'standard'
        config.active_model_index = 0
    config.mode = mode
    config.api_max_retries = 0
    config.api_timeout = int(next((arg.split('=', 1)[1] for arg in sys.argv if arg.startswith('--api-timeout=')), '60'))
    config.security = {**config.security, 'permission_level': 'full_control', 'permission_mode': 'default'}
    work = ROOT / '.runtime' / ('computer-model-' + time.strftime('%Y%m%d-%H%M%S') + '-' + uuid.uuid4().hex[:6])
    work.mkdir(parents=True)
    os.environ['REVERIE_APP_ROOT'] = str(work / 'profile')
    exe = work / 'ReverieDesktopFixture.exe'
    subprocess.run(['C:/Windows/Microsoft.NET/Framework64/v4.0.30319/csc.exe', '/nologo', '/target:winexe',
                    '/out:' + str(exe), '/r:System.Windows.Forms.dll', '/r:System.Drawing.dll',
                    str(ROOT / 'scripts/verification/fixtures/computer-use/Fixture.cs')], check=True, capture_output=True)
    canvas_task = '--canvas' in sys.argv
    if canvas_task and not model.supports_vision:
        raise ValueError('Canvas qualification requires a vision model')
    fixture_env = {**os.environ, **({'REVERIE_EXTENDED_FIXTURE': '1'} if canvas_task else {})}
    fixture = subprocess.Popen([str(exe), str(work / 'saved.txt')], env=fixture_env, creationflags=subprocess.CREATE_NO_WINDOW)
    runtime = ComputerUseRuntime(work)
    evidence = {'model': model.model, 'mode': mode, 'provider': model.provider, 'vision': model.supports_vision,
                'requests': [], 'tools': [], 'passed': False}
    agent = None
    try:
        deadline = time.monotonic() + 20
        while True:
            windows = [w for w in runtime.command('list-windows')['data'] if w['pid'] == fixture.pid]
            if windows: break
            if time.monotonic() > deadline: raise RuntimeError('Fixture did not appear')
            time.sleep(.2)
        wid = windows[0]['id']
        if canvas_task:
            try:
                desktop_execute(runtime, 'computer_window', {'window_id': wid, 'action': 'focus'})
            except Exception:
                print('READY FOR FOREGROUND ' + str(work), flush=True)
                focus_deadline = time.monotonic() + 90
                while not next(w for w in runtime.command('list-windows')['data'] if w['id'] == wid)['is_focused']:
                    if time.monotonic() >= focus_deadline:
                        raise TimeoutError('Owned fixture did not acquire foreground within 90 seconds')
                    time.sleep(.25)
        agent = ReverieAgent(model.base_url, model.api_key, model.model, project_root=work,
                             provider=model.provider, config=config, mode=mode,
                             thinking_mode=model.thinking_mode, endpoint=model.endpoint,
                             custom_headers=model.custom_headers)
        agent.tool_executor.context.update(computer_use_runtime=runtime, project_data_dir=work)
        evidence['effective_vision'] = supports_vision(agent.tool_executor.context)
        assert evidence['effective_vision'] == model.supports_vision, 'Qualification capability override did not take effect'
        allowed = {'computer_snapshot', 'computer_find', 'computer_get', 'computer_is',
                   'computer_set_value', 'computer_screenshot', 'computer_wait'}
        if canvas_task:
            allowed.add('computer_drag')
        original_schemas = agent.get_visible_tool_schemas
        agent.get_visible_tool_schemas = lambda *a, **k: [s for s in original_schemas(*a, **k) if s['function']['name'] in allowed]
        original_execute = agent.tool_executor.execute
        def execute(name, arguments, tool_call_id=''):
            if name not in allowed or arguments.get('app') or arguments.get('screen') is not None or arguments.get('window_id', wid) != wid:
                evidence['tools'].append({'name': name, 'success': False, 'scope_denied': True})
                return ToolResult.fail(f'Verification permits window_id={wid} only. Omit app and screen; use this exact window_id. root and role are optional and must come from a successful observation.')
            if name in {'computer_snapshot', 'computer_find', 'computer_screenshot'}:
                arguments = {**arguments, 'window_id': wid}
            started = time.monotonic()
            result = original_execute(name, arguments, tool_call_id)
            evidence['tools'].append({'name': name, 'success': result.success,
                                      'elapsed_ms': round((time.monotonic()-started)*1000, 2)})
            return result
        agent.tool_executor.execute = execute
        def record(payload):
            if len(evidence['requests']) >= (12 if canvas_task else 8):
                raise RuntimeError('Verification model round-trip budget reached')
            serialized = json.dumps(payload, ensure_ascii=False, default=str)
            evidence['requests'].append({'model': payload.get('model'), 'image_parts': serialized.count('data:image/') + serialized.count('"type": "base64"'),
                                         'request_chars': len(serialized),
                                         'tool_names': [t.get('function', t).get('name') for t in payload.get('tools', [])]})
        if model.provider == 'request' or agent._should_use_openai_http_fallback():
            request = agent._make_direct_request
            def tracked_direct(payload, **kwargs):
                record(payload)
                return request(payload, **kwargs)
            agent._make_direct_request = tracked_direct
        else:
            client = agent._ensure_client()
            resource = client.messages if model.provider == 'anthropic' else client.chat.completions
            create = resource.create
            def tracked(**kwargs):
                record(kwargs)
                return create(**kwargs)
            resource.create = tracked
        visual = ('First take a computer_screenshot of this window. Describe the actual visual layout and the color of its editor surface in your final response. ' if model.supports_vision else 'Use accessibility only; do not call computer_screenshot. ')
        if canvas_task:
            visual += ('After seeing the screenshot, drag diagonally inside the light blue canvas on the right, '
                       'from near its upper-left towards its lower-right, using computer_drag with image_id and image-pixel coordinates. '
                       'Perform exactly one drag, then verify the label named Drag completed: 1. Do not drag elsewhere. ')
        agent.messages.append({'role': 'user', 'content': (
            f'This is a bounded Computer Use verification. Work only in window_id={wid}, a disposable test fixture. '
            + visual + ('' if canvas_task else 'Find the editable control named Verification editor, set its value to exactly Reverie MODEL 中文, then use computer_get to verify the exact value. ')
            + 'Do not launch, close, press keys, touch other windows or repeat a delivered write. Finish once verified. Use the provided desktop tools directly.')})
        evidence['answer'] = agent._process_non_streaming()
        snapshot = runtime.command('find', ['--window-id=' + wid, '--name=Verification editor', '--exact'])['data']
        editor_ref = next(m['ref_id'] for m in snapshot['matches'] if m['role'] == 'textfield')
        value = runtime.command('get', [editor_ref, '--property=value'])['data']
        evidence['final_value'] = value
        evidence['passed'] = (bool(evidence['answer']) and 'Reverie MODEL 中文' in json.dumps(value, ensure_ascii=False)
                              and any(t['name'] == 'computer_set_value' and t['success'] for t in evidence['tools'])
                              and (not model.supports_vision or any(r['image_parts'] for r in evidence['requests'])))
        if canvas_task:
            drag = runtime.command('find', ['--window-id=' + wid, '--name=Drag completed: 1', '--exact'])['data']
            evidence['canvas_verified'] = len(drag['matches']) == 1
            evidence['passed'] = (bool(evidence['answer']) and evidence['canvas_verified']
                                  and any(r['image_parts'] for r in evidence['requests'])
                                  and sum(t['name'] == 'computer_drag' and t['success'] for t in evidence['tools']) == 1)
    except Exception as exc:
        # Credentials and raw HTTP responses are never written to verification artifacts.
        evidence['error_type'] = type(exc).__name__
        evidence['error'] = str(exc)[:1500].replace(model.api_key, '[redacted]') if model.api_key else str(exc)[:1500]
    finally:
        if canvas_task:
            try:
                partial = runtime.command('find', ['--window-id=' + wid, '--native-id=dragCount'])['data']
                evidence['actual_canvas_labels'] = [m['name'] for m in partial['matches']]
            except Exception as exc:
                evidence['partial_observation_error_type'] = type(exc).__name__
        if agent is not None:
            # The fixture and task are synthetic; omit system prompts and image bodies.
            observed = [m for m in agent.messages if m.get('role') == 'assistant']
            (work / 'assistant_messages.json').write_text(json.dumps(observed, ensure_ascii=False, indent=2), encoding='utf-8')
        fixture.terminate()
        fixture.wait(timeout=5)
        runtime.close()
        (work / 'summary.json').write_text(json.dumps(evidence, ensure_ascii=False, indent=2), encoding='utf-8')
        print(json.dumps(evidence, ensure_ascii=False), flush=True)
        print('Artifacts: ' + str(work))
    return evidence['passed']


if __name__ == '__main__':
    sys.exit(0 if run() else 1)
