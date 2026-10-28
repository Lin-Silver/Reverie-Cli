"""One in-app request to a loopback open model; an exploratory renderer smoke only."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import signal
import socket
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'ReverieCli-py'))
sys.path.insert(0, str(ROOT / 'scripts' / 'verification'))
from desktop_process import launch_options, stop_process, wait_for_packaged_page
from local_lfm_ui_smoke import USER_PROMPT, sha256


def stop_owned_process(process: subprocess.Popen | None) -> None:
    """Stop a verifier-owned process tree, escalating when a model ignores TERM."""
    if process is None or process.poll() is not None:
        return
    group_leader = os.name != 'nt' and os.getpgid(process.pid) == process.pid
    try:
        if os.name == 'nt':
            stop_process(process)
            return
        if group_leader:
            os.killpg(process.pid, signal.SIGTERM)
        else:
            process.terminate()
    except ProcessLookupError:
        return
    try:
        process.wait(timeout=8)
    except subprocess.TimeoutExpired:
        try:
            if group_leader:
                os.killpg(process.pid, signal.SIGKILL)
            else:
                process.kill()
        except ProcessLookupError:
            pass
        process.wait(timeout=10)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--exe', type=Path, required=True)
    parser.add_argument('--model', type=Path, required=True)
    parser.add_argument('--manifest', type=Path, required=True)
    parser.add_argument('--server', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--timeout-seconds', type=int, default=5400,
                        help='maximum wait for one complete in-app response (default: 5400)')
    args = parser.parse_args()

    if args.timeout_seconds < 60:
        parser.error('--timeout-seconds must be at least 60')

    # Keep the caller's repository-local evidence path lexical: retained raw
    # evidence may be backed by a symlink into a larger scratch filesystem.
    # Path.absolute() normalizes `..` without following that final symlink.
    output_argument = args.output.absolute()
    if not output_argument.is_relative_to(ROOT / '.runtime'):
        parser.error('evidence must stay under repository .runtime')
    if output_argument.exists():
        parser.error(f'preserving existing evidence; choose a new output path: {output_argument}')
    output = output_argument.resolve()
    if output.exists():
        parser.error(f'preserving existing evidence; choose a new output path: {output}')
    for path in (args.exe, args.model, args.manifest, args.server):
        if not path.is_file():
            parser.error(f'missing local input: {path}')
    manifest = json.loads(args.manifest.read_text(encoding='utf-8'))
    if args.model.name != manifest['file']:
        parser.error('model file does not match selected manifest')
    model_hash = sha256(args.model.resolve())
    if model_hash != manifest['sha256']:
        parser.error('model hash does not match selected manifest')
    model_name = manifest['model'].split('/')[-1].removesuffix('-GGUF')

    output.mkdir(parents=True)
    workspace, app_root, home = (output / name for name in ('workspace', 'app-root', 'desktop-home'))
    for folder in (workspace, app_root, home):
        folder.mkdir()
    os.environ['REVERIE_APP_ROOT'] = str(app_root)
    os.environ['NO_PROXY'] = os.environ['no_proxy'] = '127.0.0.1,localhost'
    environment = {**os.environ, 'HOME': str(home)}

    report = {
        'scope': 'One local loopback request through the packaged Desktop; exploratory only, not a cohort sample.',
        'exploratory_model_completions': 0,
        'formal_model_quality_samples': 0,
        'in_app_provider_request_tested': True,
        'model': manifest['model'],
        'revision': manifest['revision'],
        'model_bytes': manifest['bytes'],
        'model_sha256': model_hash,
        'server_sha256': sha256(args.server.resolve()),
        'desktop_executable_sha256': sha256(args.exe.resolve()),
        'desktop_asar_sha256': sha256(args.exe.resolve().parent / 'resources' / 'app.asar'),
        'kernel_executable_sha256': sha256(args.exe.resolve().parent / 'reverie'),
        'smoke_script_sha256': sha256(Path(__file__).resolve()),
        'timeout_seconds': args.timeout_seconds,
        'llama_template_kwargs': {'enable_thinking': False},
        'server_context_tokens': 32768,
        'server_threads': 3,
        'checks': [],
        'browser_errors': [],
    }
    server_log = (output / 'llama-server.log').open('x', encoding='utf-8')
    app_log = (output / 'desktop.log').open('x', encoding='utf-8')
    server = app = browser = None
    try:
        from playwright.sync_api import sync_playwright
        from reverie.config import ConfigManager, ModelConfig
        from reverie.session.manager import SessionManager
        import requests

        with socket.socket() as sock:
            sock.bind(('127.0.0.1', 0))
            server_port = sock.getsockname()[1]
        server = subprocess.Popen([
            str(args.server.resolve()), '-m', str(args.model.resolve()),
            '--host', '127.0.0.1', '--port', str(server_port), '--ctx-size', '32768',
            '--threads', '3', '--threads-batch', '3', '--n-predict', '768',
            '--seed', '42', '--no-webui', '--alias', model_name,
            '--chat-template-kwargs', '{"enable_thinking":false}',
        ], cwd=str(args.server.resolve().parent), env=environment,
            stdout=server_log, stderr=subprocess.STDOUT)
        http = requests.Session()
        http.trust_env = False
        endpoint = f'http://127.0.0.1:{server_port}'
        for _ in range(180):
            if server.poll() is not None:
                raise RuntimeError(f'llama-server exited early with {server.returncode}')
            try:
                if http.get(endpoint + '/health', timeout=2).ok:
                    break
            except requests.RequestException:
                pass
            time.sleep(1)
        else:
            raise TimeoutError('local llama-server did not become ready within 180 seconds')

        config = ConfigManager(workspace)
        config.ensure_dirs()
        cfg = config.load()
        cfg.models = [ModelConfig(
            model=model_name,
            model_display_name=model_name,
            base_url=endpoint + '/v1',
            api_key='',
            max_context_tokens=32768,
            provider='openai-chat',
        )]
        cfg.active_model_source = 'standard'
        cfg.active_model_index = 0
        cfg.max_context_tokens = 32768
        cfg.stream_responses = True
        cfg.api_timeout = args.timeout_seconds
        config.save(cfg)

        manager = SessionManager(config.project_data_dir, project_root=workspace)
        session = manager.create_session('Qwen 本地应用链路冒烟（合成数据）')
        manager.save_session(session)
        settings = home / '.reverie' / 'desktop' / 'desktop-settings.json'
        settings.parent.mkdir(parents=True)
        settings.write_text(json.dumps({
            'coreAppRoot': str(app_root), 'projectRoot': str(workspace),
            'ui': {'language': 'zh-CN', 'showReasoning': False},
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
            editor = page.locator('textarea[aria-autocomplete=list]')
            editor.fill(USER_PROMPT)
            started = time.monotonic()
            page.get_by_role('button', name='发送', exact=True).click()

            target = page.locator('.message.assistant .answer-markdown').last
            last_text = ''
            stable_rounds = 0
            while time.monotonic() - started < args.timeout_seconds:
                if app.poll() is not None:
                    raise RuntimeError(f'Desktop exited during generation with {app.returncode}')
                if target.count():
                    current = target.inner_text()
                    stop_visible = page.get_by_role('button', name='停止', exact=True).count() > 0 and \
                        page.get_by_role('button', name='停止', exact=True).is_visible()
                    if current and current == last_text and not stop_visible:
                        stable_rounds += 1
                        if stable_rounds >= 3:
                            break
                    else:
                        stable_rounds = 0
                    last_text = current
                page.wait_for_timeout(1000)
            else:
                raise TimeoutError(
                    f'in-app local generation did not settle within {args.timeout_seconds} seconds'
                )
            report['inference_seconds'] = round(time.monotonic() - started, 3)
            report['assistant_chars'] = len(last_text)
            report['exploratory_model_completions'] = 1
            (output / 'assistant-visible.txt').write_text(last_text, encoding='utf-8')
            report['desktop_build'] = page.evaluate('window.reverie.paths()')['desktopBuild']

            def inspect() -> dict:
                return target.evaluate('''e => ({
                  metrics:[...e.querySelectorAll('.answer-metric')].map(x=>[x.querySelector('dt')?.innerText,x.querySelector('dd')?.innerText]),
                  tables:[...e.querySelectorAll('.answer-table')].map(t=>({headers:[...t.querySelectorAll('th')].map(x=>x.innerText),rows:[...t.querySelectorAll('tbody tr')].map(r=>[...r.querySelectorAll('td')].map(x=>x.innerText))})),
                  cards:[...e.querySelectorAll('.answer-card')].map(c=>{const title=c.querySelector('h3')?.innerText||'';return {title:title.replace(/^\\d+\\.\\s*/,''),numbered:/^\\d+\\.\\s*/.test(title),badges:[...c.querySelectorAll('.answer-badge')].map(x=>x.innerText),sources:[...c.querySelectorAll('.answer-source')].map(x=>({label:x.querySelector('span')?.innerText,url:x.getAttribute('href')})),links:[...c.querySelectorAll('.answer-card-links a')].map(x=>({label:x.innerText.replace(/↗\\s*$/,''),url:x.getAttribute('href')}))}}),
                  fallback:[...e.querySelectorAll('.answer-block-fallback pre')].map(x=>x.innerText),
                  width:e.clientWidth,scrollWidth:e.scrollWidth,text:e.innerText
                })''')

            report['rendered'] = inspect()
            expected_metrics = [['计划中', '7'], ['开发中', '5'], ['已有成果', '4'], ['半归档', '1']]
            expected_table = {
                'headers': ['项目名称', '当前状态', '说明'],
                'rows': [
                    ['Reverie CLI', '开发中', '桌面回答 UI 格式测试'],
                    ['本地模型冒烟', '计划中', '一次性 LFM 输出校准'],
                ],
            }
            expected_card = {
                'title': '测试项目',
                'numbered': True,
                'badges': ['测试数据'],
                'sources': [{'label': '测试来源', 'url': 'https://example.com/source'}],
                'links': [{'label': '测试链接', 'url': 'https://example.com/'}],
            }
            semantic_match = bool(
                report['rendered']['metrics'] == expected_metrics
                and report['rendered']['tables'] == [expected_table]
                and report['rendered']['cards'] == [expected_card]
                and not report['rendered']['fallback']
            )
            report['checks'].append({
                'name': 'model-answer-preserves-requested-metrics-table-and-card-data',
                'passed': semantic_match,
                'detail': {
                    'expected_metrics': expected_metrics,
                    'expected_table': expected_table,
                    'expected_card': expected_card,
                    'actual_metrics': report['rendered']['metrics'],
                    'actual_tables': report['rendered']['tables'],
                    'actual_cards': report['rendered']['cards'],
                    'fallbacks': report['rendered']['fallback'],
                },
            })
            for theme, label in (('dark', '深色'), ('light', '浅色')):
                page.get_by_role('button', name='切换主题', exact=True).click()
                page.locator('.theme-menu').get_by_role('button', name=label, exact=False).click()
                page.wait_for_function('t=>document.documentElement.dataset.theme===t', arg=theme)
                for width in (1280, 460):
                    page.set_viewport_size({'width': width, 'height': 1500})
                    report['checks'].append({
                        'name': f'in-app-answer-contained-{theme}-{width}',
                        'passed': target.evaluate('e=>e.clientWidth>0&&e.scrollWidth<=e.clientWidth+1'),
                    })
                    target.screenshot(path=str(output / f'answer-{theme}-{width}.png'))
            report['checks'].append({'name': 'no-browser-errors', 'passed': not report['browser_errors']})
            browser.close()
            browser = None
        report['render_passed'] = all(item['passed'] for item in report['checks'])
    except Exception as error:
        report['error'] = f'{type(error).__name__}: {error}'
        report['render_passed'] = False
    finally:
        cleanup_errors = []
        if browser is not None:
            try:
                browser.close()
            except Exception as error:
                cleanup_errors.append(f'browser: {type(error).__name__}: {error}')
        for name, process in (('desktop', app), ('llama-server', server)):
            try:
                stop_owned_process(process)
            except Exception as error:
                cleanup_errors.append(f'{name}: {type(error).__name__}: {error}')
        if cleanup_errors:
            report['cleanup_errors'] = cleanup_errors
            report['render_passed'] = False
        server_log.flush()
        server_log_text = (output / 'llama-server.log').read_text(encoding='utf-8', errors='replace')
        report['provider_requests_started'] = server_log_text.count('processing task, is_child = 0')
        report['provider_responses_completed'] = server_log_text.count('total time = ')
        server_log.close()
        app_log.close()
        (output / 'report.json').write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')

    print(json.dumps({
        'render_passed': report['render_passed'],
        'exploratory_model_completions': report['exploratory_model_completions'],
        'formal_model_quality_samples': report['formal_model_quality_samples'],
        'checks': report['checks'], 'error': report.get('error'),
    }, ensure_ascii=False))
    return 0 if report['render_passed'] else 2


if __name__ == '__main__':
    raise SystemExit(main())
