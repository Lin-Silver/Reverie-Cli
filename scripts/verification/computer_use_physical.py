"""Verify actual native input effects in an owned extended WinForms fixture."""
from pathlib import Path
import json
import os
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'ReverieCli-py'))
from reverie.computer_use.runtime import ComputerUseRuntime, NativeDesktopError
from reverie.computer_use.operations import execute

sys.stdout.reconfigure(encoding='utf-8')


def run():
    work = ROOT / '.runtime' / ('computer-physical-' + time.strftime('%Y%m%d-%H%M%S'))
    work.mkdir(parents=True)
    binary = work / 'ReverieDesktopFixture.exe'
    subprocess.run(['C:/Windows/Microsoft.NET/Framework64/v4.0.30319/csc.exe', '/nologo', '/target:winexe',
                    '/out:' + str(binary), '/r:System.Windows.Forms.dll', '/r:System.Drawing.dll',
                    str(ROOT / 'scripts/verification/fixtures/computer-use/Fixture.cs')], check=True, capture_output=True)
    process = subprocess.Popen([str(binary), str(work / 'saved.txt')],
                               env={**os.environ, 'REVERIE_EXTENDED_FIXTURE': '1'}, creationflags=subprocess.CREATE_NO_WINDOW)
    runtime = ComputerUseRuntime(work)
    checks, calls = [], []
    summary = {'passed': False, 'checks': checks}

    def call(tool_name, **args):
        try:
            result = execute(runtime, 'computer_' + tool_name, args, vision=True)
        except NativeDesktopError as exc:
            calls.append({'tool': tool_name, 'args': args, 'result': exc.envelope})
            raise
        calls.append({'tool': tool_name, 'args': args, 'result': result})
        return result['data']

    def check(name, value):
        checks.append({'name': name, 'passed': bool(value)})
        assert value, name

    def find(name=None, native_id=None, **options):
        result = call('find', window_id=wid, exact=True, **({'name': name} if name else {}),
                      **({'native_id': native_id} if native_id else {}), **options)['matches']
        assert len(result) == 1, (name, native_id, result)
        return result[0]

    def image_point(match, image):
        if match.get('ref_id'):
            bounds = call('get', ref=match['ref_id'], property='bounds')
            assert bounds['live'], bounds
            b = bounds['value']
        else:
            tree = call('snapshot', window_id=wid, include_bounds=True)['tree']
            def nodes(node):
                yield node
                for child in node.get('children', []):
                    yield from nodes(child)
            matching = [n for n in nodes(tree) if n.get('name')==match['name']]
            assert len(matching)==1, matching
            b = matching[0]['bounds']
        origin = image['capture_bounds']
        return {'image_id': image['image_id'], 'x': (b['x']+b['width']/2-origin['x'])*image['scale_x'],
                'y': (b['y']+b['height']/2-origin['y'])*image['scale_y']}

    try:
        deadline = time.monotonic() + 20
        while True:
            windows = [w for w in call('list_windows') if w['pid'] == process.pid]
            if windows: break
            if time.monotonic() >= deadline: raise TimeoutError('Owned fixture did not appear')
            time.sleep(.2)
        wid = windows[0]['id']
        try:
            call('window', window_id=wid, action='focus')
        except NativeDesktopError:
            print('READY FOR FOREGROUND ' + str(work), flush=True)
            deadline = time.monotonic() + 90
            while not next(w for w in call('list_windows') if w['id'] == wid)['is_focused']:
                if time.monotonic() >= deadline: raise TimeoutError('Owned fixture needs foreground')
                time.sleep(.3)
        call('snapshot', window_id=wid, include_bounds=True)
        duplicates = call('find', window_id=wid, native_id='duplicateIdentity', exact=True)['matches']
        check('duplicate AutomationId and name remain separate refs', len(duplicates)==2 and len({m['ref_id'] for m in duplicates})==2)
        call('click', ref=find('Increment counter')['ref_id'], physical=True)
        check('physical ref click delivered exactly once', len(call('find', window_id=wid, name='Count: 1', exact=True)['matches'])==1)
        image = call('screenshot', window_id=wid)
        point = image_point(find('Increment counter'), image)
        call('click', **point, physical=True)
        check('image click delivered exactly once', len(call('find', window_id=wid, name='Count: 2', exact=True)['matches'])==1)
        # A failed post-action observation must not cause a second click.
        try:
            call('wait', window_id=wid, selector=':Count: 999', timeout_ms=300)
        except NativeDesktopError as exc:
            check('verification timeout is reported', exc.envelope['error']['code'] in {'TIMEOUT', 'WAIT_TIMEOUT'})
        else:
            raise AssertionError('Absent counter unexpectedly observed')
        check('delivered click not replayed after verification timeout', len(call('find', window_id=wid, name='Count: 2', exact=True)['matches'])==1)
        editor = find('Verification editor')['ref_id']
        call('focus', ref=editor)
        check('editor receives focus', call('is', ref=editor, property='focused')['result'])
        call('press_key', window_id=wid, key='Ctrl+A')
        call('type_text', ref=editor, text='实机键鼠中文\r\nSecond physical line', physical=True)
        value = call('get', ref=editor, property='value')
        check('physical multiline Chinese typing readback', '实机键鼠中文' in json.dumps(value, ensure_ascii=False) and 'Second physical line' in json.dumps(value))
        image = call('screenshot', window_id=wid)
        canvas = image_point(find('Verification drag canvas'), image)
        call('drag', from_image_id=image['image_id'], to_image_id=image['image_id'],
             from_x=canvas['x']-60, from_y=canvas['y']-60, to_x=canvas['x']+60, to_y=canvas['y']+60)
        check('diagonal drag actual counter', find(native_id='dragCount')['name']=='Drag completed: 1')
        target = find('Verification row 39')
        call('scroll_to', ref=target['ref_id'])
        check('scroll_to brings target into viewport', call('is', ref=target['ref_id'], property='visible')['result'])
        scroll = find('Verification scroll')
        call('scroll', ref=scroll['ref_id'], direction='up', amount=3)
        image = call('screenshot', window_id=wid)
        call('scroll', **image_point(scroll, image), direction='down', amount=3)
        check('physical scroll preserves counter', find(native_id='dragCount')['name']=='Drag completed: 1')
        before = next(w for w in call('list_windows') if w['id']==wid)['bounds']
        image = call('screenshot', window_id=wid)
        call('window', window_id=wid, action='move', x=100, y=80)
        after = next(w for w in call('list_windows') if w['id']==wid)['bounds']
        check('window actually moved', (after['x'], after['y']) != (before['x'], before['y']))
        try:
            call('pointer', image_id=image['image_id'], x=20, y=20, action='move')
        except NativeDesktopError as exc:
            check('moved image rejected before input', exc.envelope['error']['code']=='STALE_IMAGE')
        else:
            raise AssertionError('Moved image accepted')
        call('window', window_id=wid, action='resize', width=1050, height=800)
        sized = next(w for w in call('list_windows') if w['id']==wid)['bounds']
        check('window actually resized', sized['width']==1050 and sized['height']==800)
        call('window', window_id=wid, action='minimize')
        check('window actually minimized', next(w for w in call('list_windows') if w['id']==wid)['minimized'])
        call('window', window_id=wid, action='restore')
        call('window', window_id=wid, action='maximize')
        maximized = next(w for w in call('list_windows') if w['id']==wid)['bounds']
        check('window actually maximized', maximized['width'] > sized['width'])
        call('window', window_id=wid, action='restore')
        check('window restored size', next(w for w in call('list_windows') if w['id']==wid)['bounds']['width']==sized['width'])
        summary['passed'] = all(c['passed'] for c in checks)
    except Exception as exc:
        summary['error_type'], summary['error'] = type(exc).__name__, str(exc)
    finally:
        summary['native_calls'] = runtime.metrics
        (work / 'summary.json').write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding='utf-8')
        (work / 'calls.json').write_text(json.dumps(calls, ensure_ascii=False, indent=2), encoding='utf-8')
        process.terminate()
        process.wait(timeout=5)
        runtime.close()
        print(json.dumps(summary, ensure_ascii=False), flush=True)
        print('Artifacts: ' + str(work))
    return summary['passed']


if __name__ == '__main__':
    sys.exit(0 if run() else 1)
