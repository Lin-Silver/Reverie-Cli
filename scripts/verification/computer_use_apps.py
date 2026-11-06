"""Native Computer Use observations in disposable real application windows."""
from pathlib import Path
import json
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'ReverieCli-py'))
sys.path.insert(0, str(ROOT / 'scripts/verification'))
from desktop_process import stop_process
from reverie.computer_use.runtime import ComputerUseRuntime
from reverie.computer_use.operations import execute

sys.stdout.reconfigure(encoding='utf-8')


def run():
    work = ROOT / '.runtime' / ('computer-apps-' + time.strftime('%Y%m%d-%H%M%S'))
    work.mkdir(parents=True)
    runtime = ComputerUseRuntime(work)
    records = []
    stage = ''
    def call(tool_name, **args):
        envelope = execute(runtime, 'computer_' + tool_name, args, vision=True)
        (work / ('last-' + tool_name + '.json')).write_text(json.dumps(envelope, ensure_ascii=False, indent=2), encoding='utf-8')
        return envelope['data']
    def window(predicate):
        deadline = time.monotonic() + 20
        while True:
            matches = [w for w in call('list_windows') if predicate(w)]
            if len(matches) == 1: return matches[0]
            if time.monotonic() > deadline: raise RuntimeError('Owned window did not become uniquely observable')
            time.sleep(.25)
    html = work / 'browser-fixture.html'
    html.write_text('<!doctype html><meta charset="utf-8"><title>Reverie Browser Verification</title><label>Browser verification editor<textarea aria-label="Browser verification editor"></textarea></label><button>Verify local browser</button>', encoding='utf-8')
    chrome = subprocess.Popen(['C:/Program Files/Google/Chrome/Application/chrome.exe',
                               '--user-data-dir=' + str(work / 'chrome-profile'), '--no-first-run',
                               '--no-default-browser-check', '--force-renderer-accessibility=complete', '--app=' + html.as_uri()],
                              creationflags=subprocess.CREATE_NO_WINDOW)
    try:
        stage = 'window'
        target = window(lambda w: w['pid'] == chrome.pid)
        stage = 'page_ready'
        call('wait', window_id=target['id'], selector='textfield:Browser verification editor', timeout_ms=20000)
        stage = 'snapshot'
        state = call('snapshot', window_id=target['id'])
        (work / 'chromium-snapshot.json').write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding='utf-8')
        stage = 'find_editor'
        match = call('find', window_id=target['id'], name='Browser verification editor', role='textfield', exact=True)['matches']
        assert len(match) == 1, f'Expected one editor; observed {len(match)} candidates'
        stage = 'set_value'
        call('set_value', ref=match[0]['ref_id'], value='Browser 中文\nSecond line')
        value = call('get', ref=match[0]['ref_id'], property='value')
        stage = 'readback'
        assert 'Second line' in json.dumps(value), 'Editor value did not contain the written second line'
        stage = 'screenshot'
        screenshot = call('screenshot', window_id=target['id'])
        records.append({'app': 'Chromium', 'passed': True, 'complete': state['complete'], 'readback': value, 'screenshot': screenshot['path']})
    except Exception as exc:
        records.append({'app': 'Chromium', 'passed': False, 'stage': stage, 'error': str(exc)})
        if stage != 'window':
            state = call('snapshot', window_id=target['id'])
            (work / 'chromium-failed-snapshot.json').write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding='utf-8')
    finally:
        stop_process(chrome)
    document = work / 'Reverie-Notepad-Verification.txt'
    document.write_text('Reverie 中文\nNotepad observation verification.', encoding='utf-8-sig')
    folder = work / 'Reverie-Explorer-Verification'
    folder.mkdir()
    (folder / 'verification.txt').write_text('Owned Explorer fixture', encoding='utf-8')
    for name, executable, arguments, title in [
        ('Notepad', str(document), [], document.name),
        ('Explorer', str(folder), [], folder.name),
    ]:
        target = None
        try:
            launch = call('launch_app', target=executable, arguments=arguments)
            target = window(lambda w: title.casefold() in w['title'].casefold())
            snapshot = call('snapshot', window_id=target['id'])
            image = call('screenshot', window_id=target['id'])
            records.append({'app': name, 'passed': True, 'complete': snapshot['complete'], 'window_id': target['id'],
                            'tree_bytes': len(json.dumps(snapshot)), 'screenshot': image['path'], 'launch': launch})
        except Exception as exc:
            records.append({'app': name, 'passed': False, 'error': str(exc)})
        finally:
            if target is not None:
                try:
                    call('close_app', window_id=target['id'])
                except Exception as exc:
                    close = call('find', window_id=target['id'], name='Close', role='button', exact=True)['matches']
                    if len(close) == 1:
                        call('click', ref=close[0]['ref_id'])
                    else:
                        records[-1]['cleanup_error'] = str(exc)
    (work / 'summary.json').write_text(json.dumps(records, ensure_ascii=False, indent=2), encoding='utf-8')
    runtime.close()
    print(json.dumps(records, ensure_ascii=False)); print('Artifacts: ' + str(work))
    return all(record['passed'] for record in records)


if __name__ == '__main__': sys.exit(0 if run() else 1)
