"""Real-model native rich-answer acceptance; fixtures contain inputs, never responses."""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
import argparse
import copy
import hashlib
import json
import os
import re
import shutil
import socket
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT/'ReverieCli-py'))
sys.path.insert(0, str(Path(__file__).resolve().parent))
import riu_quality_benchmark as q

TASK_FILE = Path(__file__).with_name('fixtures')/'riu-rich-answer-tasks.json'

RICH_STATE = r'''root=>({
 metrics:[...root.querySelectorAll('.answer-metric')].map(x=>[x.querySelector('dt').innerText.trim(),x.querySelector('dd').innerText.trim()]),
 tables:[...root.querySelectorAll('.answer-table-scroll table')].map(t=>({rows:[...t.querySelectorAll('tbody tr')].map(r=>[...r.querySelectorAll('td')].map(c=>c.innerText.trim())),headers:[...t.querySelectorAll('th')].map(x=>x.innerText.trim())})),
 cards:[...root.querySelectorAll('.answer-card')].map(c=>({title:c.querySelector('h3')?.innerText.replace(/^\d+\.\s*/,'').trim(),number:Number(c.querySelector('h3')?.innerText.match(/^(\d+)\./)?.[1])||null,description:c.querySelector('p')?.innerText.trim()||'',badges:[...c.querySelectorAll('.answer-badge')].map(b=>b.innerText.trim()),images:[...c.querySelectorAll('img')].map(i=>({src:i.getAttribute('src'),alt:i.alt,loaded:i.complete&&i.naturalWidth>0}))})),
 badges:[...root.querySelectorAll('.answer-badge')].map(x=>x.innerText.trim()),
 links:[...root.querySelectorAll('a[href]')].map(x=>x.href),sources:root.querySelectorAll('a.answer-source').length,plainLinks:root.querySelectorAll('a:not(.answer-source)').length,
 headings:[...root.querySelectorAll('h1,h2,h3')].map(x=>x.innerText.trim()),strong:[...root.querySelectorAll('strong')].map(x=>x.innerText.trim()),
 lists:root.querySelectorAll('li').length,code:[...root.querySelectorAll('pre code')].map(x=>x.innerText),
 unfinished:root.querySelectorAll('.answer-block-pending').length,invalid:root.querySelectorAll('.answer-block-fallback,pre code.language-reverie-ui').length,
 rawRichFormat:[...root.querySelectorAll('pre code')].filter(c=>{try{return ['metrics','table','cards','sources'].includes(JSON.parse(c.innerText).type);}catch{return false;}}).length,
 transcript:(()=>{const t=root.closest('.transcript');return t?{width:t.clientWidth,scrollWidth:t.scrollWidth}:null;})(),
 width:root.clientWidth,scrollWidth:root.scrollWidth,text:root.innerText
})'''

RICH_CONTRAST = r'''root=>{
 const c=document.createElement('canvas');c.width=c.height=1;const ctx=c.getContext('2d');
 const rgba=s=>{ctx.clearRect(0,0,1,1);ctx.fillStyle=s;ctx.fillRect(0,0,1,1);return [...ctx.getImageData(0,0,1,1).data];};
 const bg=e=>{let chain=[],rgb=[255,255,255];for(let p=e;p;p=p.parentElement)chain.unshift(p);for(const p of chain){let v=rgba(getComputedStyle(p).backgroundColor),a=v[3]/255;rgb=rgb.map((x,i)=>v[i]*a+x*(1-a));}return rgb;};
 const lum=rgb=>rgb.map(x=>{x/=255;return x<=.04045?x/12.92:((x+.055)/1.055)**2.4;}).reduce((s,x,i)=>s+x*[.2126,.7152,.0722][i],0);
 return [...root.querySelectorAll(':scope>p,:scope>h1,:scope>h2,:scope>h3,li,blockquote,code,a,caption,.answer-metric dt,.answer-metric dd,.answer-card p,.answer-card h3,.answer-badge,.answer-source,.answer-table-scroll th,.answer-table-scroll td')].filter(e=>e.getBoundingClientRect().width>0&&e.innerText.trim()&&!e.querySelector('.answer-badge')).map(e=>{const s=getComputedStyle(e),f=rgba(s.color),b=bg(e),a=f[3]/255,v=f.slice(0,3).map((x,i)=>x*a+b[i]*(1-a)),l=[lum(v),lum(b)],ratio=(Math.max(...l)+.05)/(Math.min(...l)+.05),minimum=parseFloat(s.fontSize)>=24||(parseFloat(s.fontSize)>=18.66&&Number(s.fontWeight)>=700)?3:4.5;return {text:e.innerText,foreground:v,background:b,ratio,minimum,passed:ratio>=minimum};});
}'''


def assess_rich_state(state, expected):
    """Compare independently supplied task data with the actual rendered answer."""
    checks = []
    def check(name, passed, detail=None):
        checks.append({'name': name, 'passed': bool(passed), 'detail': detail})
    check('rich-no-unfinished-or-raw-format', not state['unfinished'] and not state['invalid'] and not state.get('rawRichFormat'))
    check('rich-contained-layout', state['width'] > 0 and state['scrollWidth'] <= state['width'] + 1,
          {key: state[key] for key in ['width', 'scrollWidth']})
    transcript = state.get('transcript') or {}
    check('rich-chat-contained-layout', transcript.get('width', 0) > 0 and
          transcript.get('scrollWidth', 1) <= transcript.get('width', 0) + 1, transcript)
    if 'metrics' in expected:
        check('rich-metric-values-and-labels', state['metrics'] == expected['metrics'], state['metrics'])
    if 'table_rows' in expected:
        rows = [[str(value) for value in row] for row in expected['table_rows']]
        check('rich-all-supplied-table-rows', any(table['rows'] == rows for table in state['tables']), state['tables'])
    if 'empty_tables' in expected:
        check('rich-explicit-empty-table', sum(not t['rows'] for t in state['tables']) >= expected['empty_tables']
              and bool(re.search('暂无数据|没有数据', state['text'])))
    if 'min_badges' in expected:
        check('rich-status-badges', len(state['badges']) >= expected['min_badges'], state['badges'])
    if 'badge_text' in expected:
        check('rich-requested-badge', expected['badge_text'] in state['badges'], state['badges'])
    if 'card_titles' in expected:
        check('rich-card-order-and-titles', [c['title'] for c in state['cards']] == expected['card_titles'], state['cards'])
        numbers = [c.get('number') for c in state['cards']]
        check('rich-card-numbering', not any(numbers) or numbers == list(range(1, len(numbers)+1)), numbers)
    if 'card_descriptions' in expected:
        check('rich-supplied-descriptions', [c.get('description') for c in state['cards']] == expected['card_descriptions'], state['cards'])
    if 'card_badges' in expected:
        check('rich-per-item-badges', [c.get('badges') for c in state['cards']] == expected['card_badges'], state['cards'])
    if 'image_urls' in expected:
        images = [i for card in state['cards'] for i in card['images']]
        check('rich-supplied-image-sources', [i['src'] for i in images] == expected['image_urls'], images)
        check('rich-images-loaded-and-described', bool(images) and all(i['loaded'] and i['alt'].strip() for i in images), images)
    if 'image_alts' in expected:
        alts = [i['alt'] for card in state['cards'] for i in card['images']]
        check('rich-supplied-image-descriptions', alts == expected['image_alts'], alts)
    if 'link_urls' in expected:
        check('rich-supplied-source-links', all(url.rstrip('/') in {v.rstrip('/') for v in state['links']}
              for url in expected['link_urls']), state['links'])
    if 'min_sources' in expected:
        check('rich-source-pills', state['sources'] >= expected['min_sources'], state['sources'])
    if 'min_plain_links' in expected:
        check('rich-ordinary-markdown-links', state['plainLinks'] >= expected['min_plain_links'], state['plainLinks'])
    if 'heading' in expected:
        check('rich-markdown-heading', expected['heading'] in state['headings'], state['headings'])
    if 'strong' in expected:
        check('rich-markdown-emphasis', expected['strong'] in state['strong'], state['strong'])
    if 'min_list_items' in expected:
        check('rich-markdown-list', state['lists'] >= expected['min_list_items'], state['lists'])
    if 'code_pattern' in expected:
        check('rich-ordinary-code-preserved', any(re.search(expected['code_pattern'], code) for code in state['code']), state['code'])
    return checks


def rich_repair_feedback(checks):
    labels = {
        'rich-no-unfinished-or-raw-format': '部分内容仍是未完成提示或原始格式代码，没有显示为回答',
        'rich-contained-layout': '回答内容超出了正文宽度',
        'rich-chat-contained-layout': '对话内容超出了窗口宽度',
        'rich-metric-values-and-labels': '统计卡片的标签或数值与给定资料不一致',
        'rich-all-supplied-table-rows': '表格遗漏或改变了给定记录、字段或顺序',
        'rich-explicit-empty-table': '缺少要求的空表格或明确的无数据提示',
        'rich-status-badges': '表格状态没有显示为带文字的标签',
        'rich-requested-badge': '指定的推荐标签没有正确显示',
        'rich-card-order-and-titles': '图文推荐的名称或顺序不符合要求',
        'rich-card-numbering': '推荐卡片重复编号，编号应连续或全部省略',
        'rich-supplied-descriptions': '推荐描述没有照给定资料保留，或添加了未提供的功能、许可等信息',
        'rich-per-item-badges': '各推荐项的标签没有与各自给定资料一致，或额外添加了标签',
        'rich-supplied-image-sources': '图文推荐没有使用给定的图片',
        'rich-images-loaded-and-described': '图片没有成功显示或缺少说明',
        'rich-supplied-image-descriptions': '图片说明没有照给定资料保留',
        'rich-supplied-source-links': '给定的官网或源码链接没有完整保留',
        'rich-source-pills': '缺少来源胶囊链接',
        'rich-ordinary-markdown-links': '缺少要求的普通正文链接',
        'rich-markdown-heading': '缺少要求的正文标题',
        'rich-markdown-emphasis': '缺少要求的加粗文字',
        'rich-markdown-list': '缺少要求的普通列表',
        'rich-ordinary-code-preserved': '普通代码示例没有保留',
    }
    problems = []
    for check in checks:
        if check['passed']: continue
        name = check['name']
        label = labels.get(name, '部分文字难以阅读' if name.startswith('rich-text-contrast-')
                           else '窄窗口中的回答布局不完整')
        if label not in problems: problems.append(label)
    return '刚才的回答还有这些问题：'+'；'.join(problems)+'。请在对话中修正，保留给定的数据和原有内容；不需要添加可编辑控件。'


def main():
    from playwright.sync_api import sync_playwright
    from reverie.config import ConfigManager
    from reverie.session.manager import SessionManager
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--exe', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--model', required=True)
    parser.add_argument('--api-url', required=True)
    parser.add_argument('--task-file', type=Path, default=TASK_FILE)
    parser.add_argument('--tasks', nargs=1, required=True)
    parser.add_argument('--source', choices=['standard'], default='standard')
    parser.add_argument('--attempts', type=int, choices=[1], default=1)
    parser.add_argument('--max-model-repairs', type=int, default=2)
    parser.add_argument('--timeout', type=int, default=1800)
    args = parser.parse_args()
    assert 0 <= args.max_model_repairs <= 2
    output = args.output.resolve()
    assert output.is_relative_to(ROOT/'.runtime')
    output.mkdir(exist_ok=False)
    source_dir = output/'executed-source'
    source_dir.mkdir()
    sources = [Path(__file__).resolve(), Path(q.__file__).resolve(),
               Path(__file__).with_name('desktop_process.py'), args.task_file.resolve()]
    source_manifest = []
    for source in sources:
        destination = source_dir/source.name
        shutil.copyfile(source, destination)
        source_manifest.append({'path': str(source), 'copy': str(destination.relative_to(output)),
                                'sha256': hashlib.sha256(destination.read_bytes()).hexdigest()})
    q.dump(output/'executed-source.json', source_manifest)
    q.dump(output/'executed-verifier.py.json', {'path': str(Path(__file__).resolve()),
           'sha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest()})
    fixture = json.loads(args.task_file.read_text())
    task = next(t for t in fixture['tasks'] if t['id'] == args.tasks[0])
    q.dump(output/'fixed-tasks.json', fixture)
    app_root, workspace, home = [output/name for name in ['app-root', 'workspace', 'desktop-home']]
    for folder in [app_root, workspace, home]: folder.mkdir()
    original = ConfigManager(ROOT).load()
    isolation = q.prepare_isolated_workspace(workspace)
    os.environ['REVERIE_APP_ROOT'] = str(app_root)
    os.environ['NO_PROXY'] = '127.0.0.1,localhost'
    config = ConfigManager(workspace)
    cfg = config.load()
    recorder = q.Recorder(output, args.api_url.rstrip('/')+'/chat/completions', '', request_timeout=args.timeout)
    q.configure_model_source(cfg, original, 'standard', args.model,
        recorder_url=f'http://127.0.0.1:{recorder.server.server_port}/v1')
    cfg.security = copy.deepcopy(original.security)
    cfg.api_proxy = original.api_proxy
    cfg.api_max_retries = original.api_max_retries
    cfg.api_initial_backoff = original.api_initial_backoff
    cfg.api_timeout = args.timeout
    cfg.stream_responses = True
    config.ensure_dirs(); config.save(cfg)
    manager = SessionManager(config.project_data_dir, project_root=workspace)
    case_id = task['id']+'-1'
    session = manager.create_session('RIU quality '+case_id)
    case_out = output/case_id; case_out.mkdir()
    settings = home/'.reverie/desktop/desktop-settings.json'; settings.parent.mkdir(parents=True)
    q.dump(settings, {'coreAppRoot': str(app_root), 'projectRoot': str(workspace),
                     'ui': {'language': 'zh-CN', 'showReasoning': False, 'showToolCalls': False, 'showToolResults': False}})
    report = {'scope': 'Actual native model response, no authored model output or HTML repair.',
        'model': args.model, 'source': 'standard', 'task_version': fixture['version'],
        'task_sha256': hashlib.sha256(args.task_file.read_bytes()).hexdigest(), 'cases': [],
        'attempts_per_task': 1, 'max_model_repairs': args.max_model_repairs,
        'workspace_isolation': isolation, 'credential_cleanup': False, 'report_schema': 'riu-rich-quality.v1',
        'verifier_sha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        'model_turn_timeout_seconds': args.timeout, 'isolated_http_read_timeout_seconds': args.timeout,
        'browser_errors': []}
    case = {'id': case_id, 'task': task['id'], 'attempt': 1, 'session_id': session.id,
            'checks': [], 'stages': [], 'turns': [], 'repair_count': 0, 'violations': [],
            'presentation_kind': 'native-rich-answer', 'feedback_messages': []}
    def save(): q.dump(output/'report.json', report)
    save()
    process = browser = page = None
    log = (output/'electron.log').open('x')
    try:
        with sync_playwright() as playwright:
            def launch():
                nonlocal process, browser, page
                with socket.socket() as sock: sock.bind(('127.0.0.1', 0)); port = sock.getsockname()[1]
                env = {**os.environ, 'DISPLAY': ':94', 'PORTABLE_EXECUTABLE_DIR': str(home)}
                env.pop('ELECTRON_RUN_AS_NODE', None)
                process = subprocess.Popen([str(args.exe.resolve()), '--gui', '--project', str(workspace),
                    f'--remote-debugging-port={port}'], env=env, stdout=log, stderr=log, **q.launch_options())
                browser, page = q.wait_for_packaged_page(playwright, process, port)
                page.on('pageerror', lambda error: report['browser_errors'].append(str(error)))
                page.set_viewport_size({'width': 1280, 'height': 1500})
                page.wait_for_selector('textarea[aria-autocomplete=list]', timeout=120000)
                page.locator('.session-item').filter(has_text='RIU quality '+case_id).click(timeout=60000)
                page.locator('.session-loading').wait_for(state='hidden', timeout=30000)
            launch()
            report['build'] = page.evaluate('window.reverie.paths()')['desktopBuild']
            report['cases'].append(case); recorder.case = case_id; save()

            def send(prompt, stage):
                if '-repair-' in stage:
                    # Keep the existing shared budget/stage recorder, but feedback
                    # describes rich content instead of asking for interactive inputs.
                    prompt = rich_repair_feedback(case['stages'][-2]['checks'])
                    case['feedback_messages'].append({'stage': stage, 'text': prompt})
                case['phase'] = 'model-'+stage; save()
                event_start = q.start_event_capture(page); start = time.monotonic(); request_start = len(recorder.records)
                page.locator('textarea[aria-autocomplete=list]').fill(prompt)
                page.get_by_role('button', name='发送', exact=True).click()
                while True:
                    events = page.evaluate('n=>window.__qualityEvents.slice(n)', event_start)
                    began, active = q.execution_state(events, session.id)
                    if began and not active: break
                    if time.monotonic()-start > args.timeout: raise TimeoutError('Native execution lease did not finish')
                    page.wait_for_timeout(500)
                page.get_by_role('button', name='停止', exact=True).wait_for(state='hidden', timeout=30000)
                native_errors = q.inspect_native_model_errors(events, session.id)
                case['turns'].append({'stage': stage, 'model_turn_ms': (time.monotonic()-start)*1000,
                    'request_indices': list(range(request_start, len(recorder.records))),
                    'native_model_errors': native_errors['errors'], 'terminal_native_model_error': native_errors['terminal_error']})
                q.dump(case_out/(stage+'-events.json'), events)
                saved = manager.load_session(session.id)
                q.dump(case_out/(stage+'-session.json'), saved.to_dict()); save()
                if native_errors['terminal_error']:
                    error = native_errors['terminal_error']
                    raise RuntimeError(error.get('detail') or error.get('message') or 'Native model request failed')
                errors = page.locator('.inline-error').all_text_contents()
                if errors: raise RuntimeError('\n'.join(errors))
                case['phase'] = 'browser-'+stage
                calls = [call for message in saved.messages for call in message.get('tool_calls', [])]
                names = [call.get('function', {}).get('name') for call in calls]
                case['tool_names'] = names; case['violations'] = [name for name in names if name in fixture['forbidden_tools']]
                return saved

            def inspect(saved, stage, record, expected):
                target = page.locator('.message.assistant .answer-markdown').last
                target.wait_for(timeout=10000)
                for image in target.locator('.answer-card img').all():
                    image.scroll_into_view_if_needed()
                    try: image.evaluate('e=>e.complete?null:new Promise(resolve=>{e.addEventListener("load",resolve,{once:true});e.addEventListener("error",resolve,{once:true});setTimeout(resolve,10000)})')
                    except Exception: pass
                state = target.evaluate(RICH_STATE)
                for check in assess_rich_state(state, expected): record(check)
                q.dump(case_out/(stage+'-dom.json'), state)
                for value, label in [('dark','深色'),('light','浅色')]:
                    page.get_by_role('button', name='切换主题', exact=True).click()
                    page.locator('.theme-menu').get_by_role('button', name=label, exact=False).click()
                    page.wait_for_function('v=>document.documentElement.dataset.theme===v', arg=value)
                    contrasts = target.evaluate(RICH_CONTRAST)
                    record({'name': 'rich-text-contrast-'+value, 'passed': bool(contrasts) and all(x['passed'] for x in contrasts), 'detail': contrasts})
                    for width in [1280,460]:
                        page.set_viewport_size({'width': width, 'height': 1500}); page.wait_for_timeout(200)
                        geometry = target.evaluate('e=>({height:e.getBoundingClientRect().height,visibleHeight:e.closest(".transcript")?.clientHeight||innerHeight})')
                        oversized = geometry['height'] > geometry['visibleHeight']
                        capture_path = case_out/(stage+f'-{value}-{width}'+('-viewport' if oversized else '')+'.png')
                        if oversized:
                            page.screenshot(path=str(capture_path), full_page=True)
                        else:
                            target.screenshot(path=str(capture_path))
                        case['stages'][-1].setdefault('captures', []).append({
                            'path': str(capture_path), 'kind': 'actual-viewport' if oversized else 'contained-answer',
                            'geometry': geometry, 'sha256': hashlib.sha256(capture_path.read_bytes()).hexdigest()})
                        dimensions = target.evaluate('e=>({width:e.clientWidth,scrollWidth:e.scrollWidth})')
                        record({'name': f'rich-layout-{value}-{width}', 'passed': dimensions['scrollWidth'] <= dimensions['width']+1, 'detail': dimensions})
                        if len(expected.get('table_rows', [])) > 12:
                            rows = target.locator('.answer-table-scroll table tbody tr')
                            for position, row in [('first', rows.first), ('last', rows.last)]:
                                row.scroll_into_view_if_needed()
                                page.screenshot(path=str(case_out/(stage+f'-{value}-{width}-{position}-rows.png')), full_page=True)
                    page.set_viewport_size({'width':1280,'height':1500})
                provenance = {
                    'model_conversation_text_sha256': hashlib.sha256(q.assistant_text(saved.messages).encode()).hexdigest(),
                    'rendered_text_sha256': hashlib.sha256(state['text'].encode()).hexdigest(),
                }
                case['stages'][-1]['rendered_answer_provenance'] = provenance
                return provenance

            for phase in ['generation', 'modification']:
                expected = task['expected' if phase == 'generation' else 'modified_expected']
                prompt = fixture['common']+'\n'+task['prompt'] if phase == 'generation' else task['modify']
                saved, value, checks = q.run_quality_stage(case, phase, prompt, send,
                    lambda saved, stage, record: inspect(saved, stage, record, expected), args.max_model_repairs, checkpoint=save)
                case['checks'] += checks
                if phase == 'generation':
                    case['generation_first_pass'] = case['stages'][0]['passed']
                    case['generation_passed'] = case['stages'][-1]['passed']
                else: case['modified_answer'] = value
                if not case['stages'][-1]['passed']: break
            if case.get('modified_answer'):
                browser.close(); q.stop_process(process); process = None
                launch()
                target = page.locator('.message.assistant .answer-markdown').last; target.wait_for(timeout=30000)
                for image in target.locator('.answer-card img').all():
                    image.scroll_into_view_if_needed()
                    image.evaluate('e=>e.complete?null:new Promise(resolve=>{e.addEventListener("load",resolve,{once:true});e.addEventListener("error",resolve,{once:true});setTimeout(resolve,10000)})')
                restored = assess_rich_state(target.evaluate(RICH_STATE), task['modified_expected'])
                case['checks'].append({'name': 'actual-process-restart-recovery', 'passed': bool(restored) and all(x['passed'] for x in restored), 'detail': restored})
                page.screenshot(path=str(case_out/'actual-process-restart.png'), full_page=True)
            case['checks'].append({'name': 'native-no-browser-errors',
                                   'passed': not report['browser_errors'],
                                   'detail': report['browser_errors']})
            case['outcome'] = q.quality_outcome(case['checks'], case['violations'], case['repair_count'])
            browser.close()
    except Exception as error:
        if report['cases']:
            case['error'] = type(error).__name__+': '+str(error)
            case['outcome'] = q.classify_quality_error(error, case.get('phase',''))
            if page and not page.is_closed():
                try:
                    q.dump(case_out/'failure-events.json', page.evaluate('window.__qualityEvents||[]'))
                    page.screenshot(path=str(case_out/'failure.png'), full_page=True)
                    stop = page.get_by_role('button',name='停止',exact=True)
                    if stop.is_visible(): stop.click(); stop.wait_for(state='hidden',timeout=30000)
                except Exception as capture_error: case['capture_error'] = str(capture_error)
        else: report['startup_error'] = type(error).__name__+': '+str(error)
    finally:
        q.stop_process(process); recorder.close(); log.close()
        if report['cases']:
            saved = manager.load_session(session.id)
            names = [call.get('function', {}).get('name') for message in saved.messages
                     for call in message.get('tool_calls', [])]
            case['requests'] = recorder.records; case['all_tool_names'] = names
            case['violations'] = [name for name in names if name in fixture['forbidden_tools']]
            if case['violations']:
                case['outcome'] = 'model_violation'
            case['final_phase'] = case.get('phase'); q.record_service_incidents(case)
            q.dump(case_out/'final-session.json', saved.to_dict())
        report['credential_cleanup'] = {'complete': True, 'files': []}  # Isolated standard model has no credential.
        report['finished_at_utc'] = datetime.now(timezone.utc).isoformat(); save()
    print(json.dumps({'task':task['id'],'outcome':case.get('outcome'),'checks':len(case['checks']),'error':case.get('error'),'startup_error':report.get('startup_error')},ensure_ascii=False),flush=True)
    return 0 if case.get('outcome') in {'first_pass','repaired_success'} else 2


if __name__ == '__main__':
    raise SystemExit(main())
