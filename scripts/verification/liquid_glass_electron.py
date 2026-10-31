"""Exercise Liquid Glass in packaged Electron using repository-local fixtures."""
import argparse
import json
import os
from pathlib import Path
import socket
import subprocess
import sys

from desktop_process import stop_process, wait_for_packaged_page

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'ReverieCli-py'))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--exe', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--keep-open', action='store_true')
    args = parser.parse_args()
    output = args.output.resolve()
    if not output.is_relative_to(ROOT):
        raise ValueError('Keep verification artifacts inside this repository')
    output.mkdir(parents=True, exist_ok=False)
    workspace, app_root, home = [output / name for name in ('workspace', 'app-root', 'desktop-home')]
    for directory in (workspace, app_root, home):
        directory.mkdir()
    os.environ['REVERIE_APP_ROOT'] = str(app_root)
    os.environ['NO_PROXY'] = 'localhost,127.0.0.1'
    from reverie.config import ConfigManager, ModelConfig
    from reverie.session.manager import SessionManager
    from playwright.sync_api import sync_playwright, expect
    config = ConfigManager(workspace)
    config.ensure_dirs()
    cfg = config.load()
    cfg.models = [ModelConfig('glass-fixture', 'Local verification', 'http://127.0.0.1:9/v1', 'local-only')]
    cfg.active_model_index, cfg.active_model_source = 0, 'standard'
    cfg.api_proxy = ''
    config.save(cfg)
    manager = SessionManager(config.project_data_dir, project_root=workspace)
    session = manager.create_session('Liquid Glass · 中文与代码阅读')
    session.messages = [
        {'role': 'user', 'content': '请整理今天的界面设计与验证结果。'},
        {'role': 'assistant', 'content': '## 一个清晰、安静的工作空间\n\n玻璃侧栏让导航保持轻盈，正文保留稳定的阅读对比度。\n\n- 项目、会话和文件各有位置\n- 主题切换后保留草稿\n- 键盘也可以完成操作\n\n```typescript\nconst appearance = {\n  material: "Liquid Glass",\n  accent: "Reverie",\n};\n```\n\n这段内容是本地验收样例，不是模型生成结果。'},
    ]
    manager.save_session(session)
    (workspace / 'design-notes.txt').write_text('Local verification document.\n', encoding='utf-8')
    settings = home / '.reverie/desktop/desktop-settings.json'
    settings.parent.mkdir(parents=True)
    settings.write_text(json.dumps({'coreAppRoot': str(app_root), 'projectRoot': str(workspace), 'ui': {'language': 'zh-CN'}}), encoding='utf-8')
    env = {**os.environ, 'PORTABLE_EXECUTABLE_DIR': str(home)}
    env.pop('ELECTRON_RUN_AS_NODE', None)
    report = {'scope': 'Packaged Windows Electron, isolated local data; no external model requests', 'checks': [], 'screenshots': [], 'errors': []}
    process = browser = page = None
    log = (output / 'electron.log').open('w', encoding='utf-8')
    pw = sync_playwright().start()

    def check(name, condition, detail=None):
        report['checks'].append({'name': name, 'passed': bool(condition), 'detail': detail})
        print(json.dumps(report['checks'][-1], ensure_ascii=True), flush=True)
        assert condition, name

    def shot(name):
        page.screenshot(path=str(output / (name + '.png')))
        report['screenshots'].append(name + '.png')

    def launch():
        nonlocal process, browser, page
        with socket.socket() as sock:
            sock.bind(('127.0.0.1', 0))
            port = sock.getsockname()[1]
        startup = subprocess.STARTUPINFO()
        startup.dwFlags |= subprocess.STARTF_USESHOWWINDOW
        startup.wShowWindow = 1 if args.keep_open else 0
        process = subprocess.Popen([str(args.exe.resolve()), '--gui', '--project', str(workspace), f'--remote-debugging-port={port}'], env=env, stdout=log, stderr=log, startupinfo=startup)
        browser, page = wait_for_packaged_page(pw, process, port)
        page.on('pageerror', lambda error: report['errors'].append(str(error)))
        page.wait_for_selector('.session-item', timeout=120000)
        page.wait_for_load_state('networkidle')
        page.locator('.session-item').filter(has_text=session.name).click()
        page.locator('.session-loading').wait_for(state='hidden')

    def appearance_menu():
        page.locator('.topbar-right').get_by_role('button', name='切换主题', exact=True).click()

    def variant(name):
        appearance_menu()
        page.locator('.ui-variant-picker.compact').get_by_role('button', name=name, exact=True).click()
        expect(page.locator('html')).to_have_attribute('data-ui', 'classic' if name == '经典界面' else 'liquid-glass')

    def theme(name, expected):
        appearance_menu()
        page.locator('.theme-menu').get_by_role('button', name=name).click()
        expect(page.locator('html')).to_have_attribute('data-theme', expected)

    try:
        launch()
        report['build'] = page.evaluate('window.reverie.paths()')['desktopBuild']
        page.set_viewport_size({'width': 1500, 'height': 960})
        check('Existing settings keep Classic', page.locator('html').get_attribute('data-ui') == 'classic')
        shot('classic-baseline')
        editor = page.locator('.composer textarea')
        draft = '每个会话独立保存的草稿 · Liquid Glass'
        editor.fill(draft)
        variant('Liquid Glass')
        expect(editor).to_have_value(draft)
        check('Switch preserves draft and transcript', page.get_by_text('一个清晰、安静的工作空间', exact=True).is_visible())
        theme('浅色', 'light')
        shot('glass-light-1500')
        theme('深色', 'dark')
        shot('glass-dark-1500')
        for name in ['工具', 'SubAgents', 'RATS', 'RTP 任务', '技能', '插件', '恢复']:
            button = page.locator('.main-nav').get_by_role('button', name=name, exact=True)
            if button.count() == 0:
                print('NAV', page.locator('.main-nav').inner_text(), flush=True)
            button.click()
            page.wait_for_timeout(200)
            shot('page-' + name)
        page.get_by_role('button', name='设置', exact=True).click()
        page.locator('.settings-nav').get_by_role('button', name='外观', exact=True).click()
        shot('glass-settings')
        page.locator('.settings-content .ui-variant-picker').get_by_role('button', name='经典界面').click()
        expect(page.locator('html')).to_have_attribute('data-ui', 'classic')
        page.locator('.settings-content .ui-variant-picker').get_by_role('button', name='Liquid Glass').click()
        expect(page.locator('html')).to_have_attribute('data-ui', 'liquid-glass')
        check('Both switch entry points work', True)
        page.locator('.main-nav').get_by_role('button', name='对话', exact=True).click()
        expect(editor).to_have_value(draft)
        # Open a real file through the existing workbench event and save through UI.
        page.evaluate("window.dispatchEvent(new CustomEvent('reverie:file-open', {detail:{path:'design-notes.txt',line:1}}))")
        file_editor = page.get_by_role('textbox', name='文件编辑内容', exact=True)
        file_editor.fill('Verified in Liquid Glass.\n')
        variant('经典界面')
        expect(file_editor).to_have_value('Verified in Liquid Glass.\n')
        variant('Liquid Glass')
        expect(file_editor).to_have_value('Verified in Liquid Glass.\n')
        page.get_by_role('button', name='保存文件', exact=True).click()
        expect(page.locator('.unsaved-indicator')).to_have_count(0)
        check('File draft survives both variants and saves to disk', (workspace / 'design-notes.txt').read_text() == 'Verified in Liquid Glass.\n')
        shot('glass-file-workbench')
        for width, height in [(1080, 700), (1500, 960), (1920, 1080)]:
            page.set_viewport_size({'width': width, 'height': height})
            page.wait_for_timeout(250)
            bounds = page.locator('.workbench-panel').bounding_box()
            check(f'Workbench fits {width}x{height}', bounds['x'] >= 0 and bounds['x'] + bounds['width'] <= width + 1 and bounds['y'] + bounds['height'] <= height + 1, bounds)
            check(f'Workbench tabs are uncovered at {width}', page.locator('.workbench-panel').evaluate("e=>getComputedStyle(e,'::before').display") == 'none')
            shot(f'glass-workbench-{width}')
        page.set_viewport_size({'width': 1500, 'height': 960})
        page.locator('.topbar-right').get_by_role('button', name='关闭工作面板', exact=True).click()
        page.emulate_media(reduced_motion='reduce', contrast='more')
        check('High contrast removes glass blur', page.locator('.content-area').evaluate("e=>getComputedStyle(e).backdropFilter") == 'none')
        shot('glass-high-contrast')
        page.emulate_media(reduced_motion='no-preference', contrast='no-preference')
        page.evaluate("window.reverie.setUiPreferences({language:'en-US',fontSize:'large'})")
        page.reload()
        page.wait_for_selector('.composer textarea', timeout=60000)
        expect(page.locator('html')).to_have_attribute('lang', 'en-US')
        expect(page.locator('html')).to_have_attribute('data-font-size', 'large')
        shot('glass-english-large')
        page.evaluate("window.reverie.setUiPreferences({language:'zh-CN',fontSize:'comfortable'})")
        # IPC persistence exercises delayed writes using their explicit appearance owner.
        result = page.evaluate("""async()=>{
          await window.reverie.setUiPreferences({accent:'blue',backgroundBlur:7}, 'classic');
          await window.reverie.setUiPreferences({uiVariant:'classic'});
          await window.reverie.setUiPreferences({backgroundBlur:3}, 'liquid-glass');
          const classic=await window.reverie.uiPreferences();
          const glass=await window.reverie.setUiPreferences({uiVariant:'liquid-glass'});
          await window.reverie.setUiPreferences({backgroundBlur:0}, 'liquid-glass');
          return {classic,glass};
        }""")
        check('Actual IPC isolates delayed appearance writes', result['classic']['accent'] == 'blue' and result['classic']['backgroundBlur'] == 7 and result['glass']['accent'] == 'violet' and result['glass']['backgroundBlur'] == 3)
        page.reload()
        page.wait_for_selector('.composer textarea', timeout=60000)
        expect(page.locator('html')).to_have_attribute('data-ui', 'liquid-glass')
        expect(page.locator('.composer textarea')).to_have_value(draft)
        check('Reload restores variant and per-session draft', True)
        stop_process(process)
        browser = page = None
        launch()
        expect(page.locator('html')).to_have_attribute('data-ui', 'liquid-glass')
        expect(page.locator('.composer textarea')).to_have_value(draft)
        check('Process restart restores variant and per-session draft', True)
        check('No renderer exceptions', not report['errors'], report['errors'])
        theme('浅色', 'light')
        shot('glass-final')
    finally:
        if page:
            (output / 'last-page.txt').write_text(page.locator('body').inner_text(), encoding='utf-8')
            page.screenshot(path=str(output / 'last-page.png'))
        (output / 'report.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
        if not args.keep_open and process:
            stop_process(process)
        pw.stop()
        log.close()


if __name__ == '__main__':
    main()
