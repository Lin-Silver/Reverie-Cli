import json
import os
from pathlib import Path
import subprocess
import sys
import time

REPO = Path(__file__).resolve().parents[3]
AUDIT = REPO / '.audit/chat-perf'
ROOT = AUDIT / 'profile'
ROOT.mkdir(parents=True, exist_ok=True)
os.environ['REVERIE_APP_ROOT'] = str(ROOT)
os.environ['NO_PROXY'] = 'localhost,127.0.0.1'
sys.path.insert(0, str(REPO / 'ReverieCli-py'))
from reverie.config import ConfigManager
from reverie.session.manager import Session, SessionManager

config = ConfigManager(ROOT)
config.ensure_dirs()
cfg = config.load()
cfg.models = []
cfg.active_model_source = 'standard'
cfg.api_proxy = ''
config.save(cfg)
manager = SessionManager(config.project_data_dir, project_root=ROOT)
markdown = '# Performance investigation\n\n' + ('A paragraph with **bold**, `code`, and [a link](https://example.com).\n\n' * 8) + '| name | value |\n| --- | --- |\n| cache | warm |\n'
for name, count in [('Small', 2), ('Long', 1200)]:
    session = Session(name, name, '2026-09-27T10:00:00', '2026-09-27T10:00:00',
        [{'role': 'user' if i % 2 == 0 else 'assistant', 'content': f'Record {i}\n' + (markdown if i % 2 else 'Inspect this record')} for i in range(count)])
    manager.save_session(session)
manager.load_session('Small')

from playwright.sync_api import sync_playwright
env = {**os.environ}
env.pop('ELECTRON_RUN_AS_NODE', None)
process = subprocess.Popen([str(REPO / 'ReverieCli-ui/node_modules/electron/dist/electron.exe'), str(Path(__file__).parent / 'host.cjs')],
    env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
try:
    with sync_playwright() as p:
        browser = None
        for attempt in range(60):
            try:
                browser = p.chromium.connect_over_cdp('http://127.0.0.1:9347', timeout=1000)
                break
            except Exception:
                time.sleep(.25)
        if browser is None:
            raise RuntimeError('Electron CDP did not open')
        page = browser.contexts[0].pages[0]
        page.wait_for_selector('.session-item', timeout=120000)
        page.wait_for_function("document.querySelector('.conversation-header')?.innerText.includes('Small')", timeout=120000)
        page.wait_for_timeout(6000)
        page.evaluate("""() => {
          window.perfLongTasks = [];
          new PerformanceObserver(list => window.perfLongTasks.push(...list.getEntries().map(x => ({start_ms:x.startTime, duration_ms:x.duration})))).observe({type:'longtask', buffered:false});
        }""")
        durations = []
        for name in ['Long', 'Small', 'Long']:
            start = time.perf_counter()
            page.locator('.session-item').filter(has_text=name).first.click()
            page.wait_for_function('(name) => document.querySelector(".conversation-header")?.innerText.includes(name) && document.querySelector(".transcript")?.getAttribute("aria-busy") === "false"', arg=name, timeout=120000)
            page.evaluate('() => new Promise(resolve => requestAnimationFrame(() => requestAnimationFrame(resolve)))')
            durations.append({'session': name, 'ms': (time.perf_counter()-start)*1000, 'rows': page.locator('.message').count()})
            page.wait_for_timeout(1000)
        typing_samples = []
        for index in range(5):
            start = time.perf_counter()
            page.locator('textarea').fill(('typing responsiveness ' * 5) + str(index))
            page.evaluate('() => new Promise(resolve => requestAnimationFrame(() => requestAnimationFrame(resolve)))')
            typing_samples.append((time.perf_counter()-start)*1000)
            page.wait_for_timeout(250)
        history_check = None
        if page.locator('.history-load-earlier').count():
            old_top = page.evaluate('''() => {
              const transcript = document.querySelector('.transcript');
              transcript.scrollTop = 0;
              return document.querySelector('.message').getBoundingClientRect().top;
            }''')
            page.wait_for_function("() => document.querySelectorAll('.message').length === 120")
            new_top = page.evaluate("document.querySelectorAll('.message')[60].getBoundingClientRect().top")
            history_check = {'rows_after_scroll': 120, 'anchor_shift_px': new_top-old_top}
        report = {'switches': durations, 'typing_ms': typing_samples[0], 'typing_samples_ms': typing_samples, 'long_tasks_ms': page.evaluate('window.perfLongTasks'),
                  'history_check': history_check, 'ipc': json.loads((AUDIT/'ipc-metrics.json').read_text())}
        (AUDIT / f'{sys.argv[1]}.json').write_text(json.dumps(report, indent=2))
        page.screenshot(path=str(AUDIT / f'{sys.argv[1]}.png'))
        print(json.dumps(report), flush=True)
        browser.close()
finally:
    process.terminate()
    process.wait(timeout=10)
