"""Real Windows UIA/vision smoke using only an owned disposable fixture."""
from pathlib import Path
import json
import os
import statistics
import subprocess
import sys
import time
import uuid

sys.stdout.reconfigure(encoding="utf-8")

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'ReverieCli-py'))
from reverie.computer_use.runtime import ComputerUseRuntime, NativeDesktopError
from reverie.computer_use.operations import execute


def run():
    work = ROOT / '.runtime' / ('computer-use-' + time.strftime('%Y%m%d-%H%M%S'))
    work.mkdir(parents=True)
    source = ROOT / 'scripts/verification/fixtures/computer-use/Fixture.cs'
    binary = work / 'ReverieDesktopFixture.exe'
    compiler = Path('C:/Windows/Microsoft.NET/Framework64/v4.0.30319/csc.exe')
    subprocess.run([str(compiler), '/nologo', '/target:winexe', '/out:' + str(binary), '/r:System.Windows.Forms.dll', '/r:System.Drawing.dll', str(source)], check=True, capture_output=True)
    process = subprocess.Popen([str(binary), str(work / 'saved.txt')], creationflags=subprocess.CREATE_NO_WINDOW)
    runtime = ComputerUseRuntime(work)
    checks = []
    def call(tool_name, **args):
        response = execute(runtime, 'computer_' + tool_name, args, vision=True)
        checks.append({'tool': tool_name, 'args': args, 'response': response})
        return response['data']
    try:
        deadline = time.monotonic() + 20
        while True:
            windows = [w for w in call('list_windows') if w['pid'] == process.pid]
            if windows: break
            if time.monotonic() >= deadline: raise RuntimeError('Fixture window did not appear')
            time.sleep(.2)
        wid = windows[0]['id']
        if '--wait-for-focus' in sys.argv:
            print('READY ' + str(work), flush=True)
            focus_deadline = time.monotonic() + 90
            while not next(w for w in call('list_windows') if w['id'] == wid)['is_focused']:
                if time.monotonic() > focus_deadline: raise RuntimeError('Fixture was not activated before setup deadline')
                time.sleep(.5)
        call('status')
        snapshot = call('snapshot', window_id=wid, timeout_ms=30000)
        def find(name, role=None):
            result = call('find', window_id=wid, name=name, exact=True, timeout_ms=30000, **({'role':role} if role else {}))
            matches = result['matches']
            if len(matches) != 1: raise AssertionError((name, matches))
            return matches[0]['ref_id']
        editor = find('Verification editor')
        call('set_value', ref=editor, value='Reverie 中文 verification\r\nSecond line')
        value = call('get', ref=editor, property='value')
        assert '中文' in json.dumps(value, ensure_ascii=False) and 'Second line' in json.dumps(value), value
        try:
            call('type_text', ref=editor, text=' semantic append')
            assert 'semantic append' in json.dumps(call('get', ref=editor, property='value'))
        except NativeDesktopError as exc:
            assert exc.envelope['error']['disposition']['delivery'] == 'not_delivered'
            checks.append({'native_limitation': 'semantic_type_not_supported_by_fixture', 'response': exc.envelope})
        call('set_value', ref=editor, value='Reverie 中文 verification\r\nSecond line')
        call('click', ref=find('Increment counter'))
        call('wait', window_id=wid, selector=':Count: 1', timeout_ms=5000)
        check = find('Enable verification')
        call('set_state', ref=check, state='checked', value=True)
        call('is', ref=check, property='checked')
        choice = find('Verification choice', 'combobox')
        call('set_state', ref=choice, state='expanded', value=True)
        call('select', ref=find('Beta', 'option'), value='Beta')
        call('set_state', ref=choice, state='expanded', value=False)
        folder = find('Verification folder')
        call('set_state', ref=folder, state='expanded', value=True)
        assert call('is', ref=folder, property='expanded')['result'] is True
        call('set_state', ref=folder, state='expanded', value=False)
        duplicates = call('find', window_id=wid, name='Identical control', exact=True)
        assert len(duplicates['matches']) == 2
        call('click', ref=find('Save verification'))
        assert (work / 'saved.txt').read_text(encoding='utf-8-sig') == 'Reverie 中文 verification\nSecond line'
        screenshot = call('screenshot', window_id=wid)
        try:
            call('window', window_id=wid, action='focus')
        except NativeDesktopError as exc:
            if exc.envelope['error']['code'] != 'ACTION_FAILED': raise
            checks.append({'environment_limitation': 'foreground_activation', 'response': exc.envelope})
        # Re-capture after a focus request, which invalidates previous images.
        screenshot = call('screenshot', window_id=wid)
        try:
            call('pointer', image_id=screenshot['image_id'], x=30, y=50, action='move')
        except NativeDesktopError as exc:
            if exc.envelope['error']['code'] != 'TARGET_NOT_FOCUSED': raise
            checks.append({'environment_limitation': 'coordinate_input', 'response': exc.envelope})
            call('set_value', ref=editor, value='Reverie 中文 verification\r\nSecond line')
        # A write invalidates coordinates; it must not reuse the old screenshot.
        try:
            call('click', image_id=screenshot['image_id'], x=30, y=50, physical=True)
        except NativeDesktopError as exc:
            assert exc.envelope['error']['code'] == 'STALE_IMAGE'
        else:
            raise AssertionError('A stale image was accepted')
        # Clipboard verification uses only fixture text/images; the owned app restores all original formats.
        call('click', ref=find('Backup clipboard'))
        try:
            call('clipboard_set', text='Reverie clipboard 中文\nline two')
            assert 'Reverie clipboard' in json.dumps(call('clipboard_get', format='text'))
            call('clipboard_set', image_path=screenshot['path'])
            assert call('clipboard_get', format='image')['type'] == 'image'
            call('clipboard_clear')
        finally:
            call('click', ref=find('Restore clipboard'))
        # Multiple windows must return candidates, never an arbitrary close target.
        call('click', ref=find('Open second window'))
        owned = [w for w in call('list_windows') if w['pid'] == process.pid]
        assert len(owned) == 2
        try:
            call('close_app', window_id=wid)
        except NativeDesktopError as exc:
            assert exc.envelope['error']['code'] == 'AMBIGUOUS_TARGET'
        else:
            raise AssertionError('Ambiguous app close was accepted')
        samples = []
        for _ in range(8):
            start = time.monotonic()
            call('find', window_id=wid, name='Verification editor', exact=True)
            samples.append((time.monotonic() - start) * 1000)
        summary = {'semantic_passed': True, 'native_limitations': [c['native_limitation'] for c in checks if 'native_limitation' in c], 'environment_limitations': [c['environment_limitation'] for c in checks if 'environment_limitation' in c], 'checks': len(checks), 'image': screenshot['path'],
                   'find_p50_ms': statistics.median(samples), 'find_p95_ms': sorted(samples)[-1],
                   'initial_tree_bytes': len(json.dumps(snapshot)), 'semantic_image_bytes': 0,
                   'native_calls': runtime.metrics}
        (work / 'summary.json').write_text(json.dumps(summary, indent=2), encoding='utf-8')
        print(json.dumps(summary, ensure_ascii=False))
    finally:
        (work / 'checks.json').write_text(json.dumps(checks, ensure_ascii=False, indent=2), encoding='utf-8')
        process.terminate()
        process.wait(timeout=5)
        runtime.close()
        print('Verification artifacts: ' + str(work))


if __name__ == '__main__':
    run()
