"""One-off local LFM generation and packaged-renderer smoke; not a quality cohort."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'ReverieCli-py'))
sys.path.insert(0, str(ROOT / 'scripts' / 'verification'))

from desktop_process import launch_options, stop_process, wait_for_packaged_page


SYSTEM_PROMPT = """你是中文桌面助手。必须原样保留用户提供的数字、项目行和状态；不要补充未给出的事实。
任务明确要求统计卡片、项目总览表和推荐卡片时，禁止用普通散文代替。只输出三个 `reverie-ui` 代码围栏：第一个是 metrics JSON，第二个是 table JSON，第三个是 cards JSON。每个围栏内只能有一个合法 JSON 对象；不要使用普通 JSON 围栏，不要把 UI 对象放在散文里。答案的第一个非空字符必须是反引号。

精确格式示例：
```reverie-ui
{"type":"metrics","items":[{"label":"计划中","value":2}]}
```
```reverie-ui
{"type":"table","title":"项目总览表","columns":["项目名称","当前状态","说明"],"rows":[["示例项目",{"text":"开发中","tone":"info"},"桌面测试"]]}
```
```reverie-ui
{"type":"cards","items":[{"title":"测试项目","description":"仅用于本地校准","badge":{"text":"测试数据","tone":"info"},"sources":[{"label":"测试来源","url":"https://example.com/source"}],"links":[{"label":"测试链接","url":"https://example.com/"}]}]}
```
所有内容都是合成 UI 测试资料，不代表真实项目状态或真实推荐。没有提供真实图片时省略 image 字段。"""

USER_PROMPT = """请用中文展示下面的合成测试资料，保留所有值和行：
统计：计划中7、开发中5、已有成果4、半归档1。
项目总览表只有两行：Reverie CLI｜开发中｜桌面回答 UI 格式测试；本地模型冒烟｜计划中｜一次性 LFM 输出校准。
推荐卡片只有一项：测试项目；说明“仅用于本地展示校准”；徽标“测试数据”；来源标签“测试来源”、链接 https://example.com/source；官网链接标签“测试链接”、链接 https://example.com/。
不需要图片，因为没有提供真实截图。"""


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open('rb') as file:
        for chunk in iter(lambda: file.read(1024 * 1024), b''):
            digest.update(chunk)
    return digest.hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--exe', type=Path, required=True)
    parser.add_argument('--model', type=Path, required=True)
    parser.add_argument('--manifest', type=Path,
                        default=ROOT / '.runtime' / 'riu-completion-20261021' / 'native-model-lfm-manifest.json')
    parser.add_argument('--server', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--disable-thinking', action='store_true',
                        help='pass enable_thinking=false to compatible llama.cpp chat templates')
    args = parser.parse_args()

    output = args.output.resolve()
    if not output.is_relative_to(ROOT / '.runtime'):
        parser.error('evidence must stay under repository .runtime')
    if output.exists():
        parser.error(f'preserving existing evidence; choose a new output path: {output}')
    for item in (args.exe, args.model, args.server):
        if not item.is_file():
            parser.error(f'missing local input: {item}')
    model_manifest_path = args.manifest.resolve()
    model_manifest = json.loads(model_manifest_path.read_text(encoding='utf-8'))
    if args.model.name != model_manifest['file']:
        parser.error(f'model file must match the selected manifest: {model_manifest["file"]}')
    model_sha256 = sha256(args.model.resolve())
    if model_sha256 != model_manifest['sha256']:
        parser.error('local model weight does not match the selected source manifest')
    model_name = model_manifest['model'].split('/')[-1].removesuffix('-GGUF')
    output.mkdir(parents=True)
    workspace, app_root, home = (output / name for name in ('workspace', 'app-root', 'desktop-home'))
    for directory in (workspace, app_root, home):
        directory.mkdir()

    os.environ['REVERIE_APP_ROOT'] = str(app_root)
    os.environ['NO_PROXY'] = '127.0.0.1,localhost'
    os.environ['no_proxy'] = '127.0.0.1,localhost'
    report = {
        'scope': 'One exploratory local model UI smoke, outside the closed formal model cohorts.',
        'exploratory_model_completions': 1,
        'formal_model_quality_samples': 0,
        'model_id': model_manifest['model'],
        'model_revision': model_manifest['revision'],
        'model_manifest': str(model_manifest_path),
        'model_bytes': model_manifest['bytes'],
        'thinking_disabled': args.disable_thinking,
        'in_app_provider_request_tested': False,
        'renderer_replay': 'The verbatim local model completion is saved to an isolated session and displayed by the packaged native renderer.',
        'model_path': str(args.model.resolve()),
        'model_sha256': model_sha256,
        'llama_server': str(args.server.resolve()),
        'smoke_script_sha256': sha256(Path(__file__).resolve()),
        'checks': [],
        'browser_errors': [],
    }
    server = app = browser = page = None
    server_log = (output / 'llama-server.log').open('x', encoding='utf-8')
    app_log = (output / 'desktop.log').open('x', encoding='utf-8')
    try:
        from playwright.sync_api import sync_playwright
        from reverie.config import ConfigManager
        from reverie.session.manager import SessionManager
        import requests

        environment = {**os.environ, 'HOME': str(home)}
        environment['REVERIE_APP_ROOT'] = str(app_root)
        with socket.socket() as sock:
            sock.bind(('127.0.0.1', 0))
            server_port = sock.getsockname()[1]
        server = subprocess.Popen([
            str(args.server.resolve()), '-m', str(args.model.resolve()),
            '--host', '127.0.0.1', '--port', str(server_port),
            '--ctx-size', '4096', '--threads', '2', '--threads-batch', '2',
            '--no-webui', '--seed', '42', '--alias', model_name,
        ], cwd=str(args.server.resolve().parent), env=environment,
            stdout=server_log, stderr=subprocess.STDOUT)
        http = requests.Session()
        http.trust_env = False
        endpoint = f'http://127.0.0.1:{server_port}'
        started = time.monotonic()
        for _ in range(180):
            if server.poll() is not None:
                raise RuntimeError(f'llama-server exited early with {server.returncode}')
            try:
                health = http.get(endpoint + '/health', timeout=2)
                if health.ok:
                    break
            except requests.RequestException:
                pass
            time.sleep(1)
        else:
            raise TimeoutError('local llama-server did not become ready within 180 seconds')
        report['server_ready_seconds'] = round(time.monotonic() - started, 3)

        request_body = {
            'model': model_name,
            'messages': [
                {'role': 'system', 'content': SYSTEM_PROMPT},
                {'role': 'user', 'content': USER_PROMPT},
            ],
            'temperature': 0.1,
            'top_p': 0.9,
            'max_tokens': 512,
            'seed': 42,
            'stream': False,
        }
        if args.disable_thinking:
            request_body['chat_template_kwargs'] = {'enable_thinking': False}
        (output / 'prompt.txt').write_text(SYSTEM_PROMPT + '\n\n' + USER_PROMPT, encoding='utf-8')
        (output / 'request.json').write_text(json.dumps(request_body, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
        started = time.monotonic()
        response = http.post(endpoint + '/v1/chat/completions', json=request_body, timeout=(10, 600))
        report['inference_seconds'] = round(time.monotonic() - started, 3)
        report['http_status'] = response.status_code
        response.raise_for_status()
        result = response.json()
        (output / 'response.json').write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
        text = result['choices'][0]['message']['content']
        if not isinstance(text, str) or not text.strip():
            raise RuntimeError('local model returned empty assistant content')
        report['response_sha256'] = hashlib.sha256(text.encode()).hexdigest()
        report['response_chars'] = len(text)
        report['reported_usage'] = result.get('usage')

        config = ConfigManager(workspace)
        config.ensure_dirs()
        manager = SessionManager(config.project_data_dir, project_root=workspace)
        session = manager.create_session('LFM 本地 UI 冒烟（合成数据）')
        session.messages = [
            {'role': 'user', 'content': USER_PROMPT},
            {'role': 'assistant', 'content': text},
        ]
        manager.save_session(session)
        settings = home / '.reverie' / 'desktop' / 'desktop-settings.json'
        settings.parent.mkdir(parents=True)
        settings.write_text(json.dumps({
            'coreAppRoot': str(app_root),
            'projectRoot': str(workspace),
            'ui': {'language': 'zh-CN'},
        }, ensure_ascii=False, indent=2), encoding='utf-8')

        with sync_playwright() as playwright:
            with socket.socket() as sock:
                sock.bind(('127.0.0.1', 0))
                debug_port = sock.getsockname()[1]
            environment['PORTABLE_EXECUTABLE_DIR'] = str(home)
            environment.pop('ELECTRON_RUN_AS_NODE', None)
            app = subprocess.Popen([
                str(args.exe.resolve()), '--gui', '--project', str(workspace),
                f'--remote-debugging-port={debug_port}',
            ], env=environment, stdout=app_log, stderr=subprocess.STDOUT, **launch_options())
            browser, page = wait_for_packaged_page(playwright, app, debug_port)
            page.on('pageerror', lambda error: report['browser_errors'].append(str(error)))
            page.wait_for_selector('textarea[aria-autocomplete=list]', timeout=120000)
            page.locator('.session-item').filter(has_text=session.name).click(timeout=60000)
            target = page.locator('.message.assistant .answer-markdown').last
            target.wait_for(timeout=30000)
            page.wait_for_timeout(500)
            report['desktop_build'] = page.evaluate('window.reverie.paths()')['desktopBuild']

            def inspect() -> dict:
                return target.evaluate('''e => ({
                  metrics:[...e.querySelectorAll('.answer-metric')].map(x=>[x.querySelector('dt')?.innerText,x.querySelector('dd')?.innerText]),
                  tables:[...e.querySelectorAll('.answer-table')].map(t=>({headers:[...t.querySelectorAll('th')].map(x=>x.innerText),rows:[...t.querySelectorAll('tbody tr')].map(r=>[...r.querySelectorAll('td')].map(x=>x.innerText))})),
                  cards:[...e.querySelectorAll('.answer-card')].map(c=>({title:c.querySelector('h3')?.innerText,badges:[...c.querySelectorAll('.answer-badge')].map(x=>x.innerText),sources:[...c.querySelectorAll('.answer-source span')].map(x=>x.innerText),links:[...c.querySelectorAll('.answer-card-links a')].map(x=>x.innerText)})),
                  fallback:[...e.querySelectorAll('.answer-block-fallback pre')].map(x=>x.innerText),
                  width:e.clientWidth,scrollWidth:e.scrollWidth,text:e.innerText
                })''')

            report['rendered'] = inspect()
            report['checks'].append({
                'name': 'packaged-renderer-displayed-model-generated-rich-blocks',
                'passed': bool(report['rendered']['metrics'] and report['rendered']['tables'] and
                               report['rendered']['cards'] and not report['rendered']['fallback']),
                'detail': {
                    'metric_blocks': len(report['rendered']['metrics']),
                    'tables': len(report['rendered']['tables']),
                    'cards': len(report['rendered']['cards']),
                    'raw_fallback_blocks': len(report['rendered']['fallback']),
                },
            })
            for theme, label in (('dark', '深色'), ('light', '浅色')):
                page.get_by_role('button', name='切换主题', exact=True).click()
                page.locator('.theme-menu').get_by_role('button', name=label, exact=False).click()
                page.wait_for_function('t=>document.documentElement.dataset.theme===t', arg=theme)
                for width in (1280, 460):
                    page.set_viewport_size({'width': width, 'height': 1500})
                    report['checks'].append({
                        'name': f'answer-contained-{theme}-{width}',
                        'passed': target.evaluate('e=>e.clientWidth>0&&e.scrollWidth<=e.clientWidth+1'),
                    })
                    target.screenshot(path=str(output / f'answer-{theme}-{width}.png'))
            report['checks'].append({'name': 'no-browser-errors', 'passed': not report['browser_errors']})
            browser.close()
            browser = None
        report['render_passed'] = all(check['passed'] for check in report['checks'])
    except Exception as error:
        report['error'] = f'{type(error).__name__}: {error}'
        report['render_passed'] = False
    finally:
        if browser is not None:
            try:
                browser.close()
            except Exception:
                pass
        if app is not None:
            stop_process(app)
        if server is not None:
            stop_process(server)
        server_log.close()
        app_log.close()
        (output / 'report.json').write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')

    print(json.dumps({
        'render_passed': report['render_passed'],
        'exploratory_model_completions': report['exploratory_model_completions'],
        'formal_model_quality_samples': report['formal_model_quality_samples'],
        'rendered_counts': report['checks'][0]['detail'] if report.get('checks') else None,
        'error': report.get('error'),
    }, ensure_ascii=False))
    return 0 if report['render_passed'] else 2


if __name__ == '__main__':
    raise SystemExit(main())
