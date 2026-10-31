"""Native renderer calibration with authored fixtures; zero model-quality samples."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import socket
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT/'ReverieCli-py'))
from desktop_process import launch_options, stop_process, wait_for_packaged_page
from riu_rich_answer_benchmark import RICH_CONTRAST, RICH_STATE, assess_rich_state

def recommendation_preview_png() -> str:
    """Return a tiny, deterministic dashboard thumbnail for native UI calibration."""
    import base64
    import struct
    import zlib

    width, height = 320, 240
    pixels = bytearray((12, 16, 24, 255)) * (width * height)

    def rect(x, y, w, h, color):
        color = bytes(color)
        for row in range(max(0, y), min(height, y + h)):
            for column in range(max(0, x), min(width, x + w)):
                offset = (row * width + column) * 4
                pixels[offset:offset + 4] = color

    rect(0, 0, 54, height, (18, 23, 33, 255))
    rect(54, 0, width - 54, 30, (21, 27, 38, 255))
    rect(54, 29, width - 54, 1, (52, 61, 75, 255))
    for y in (44, 62, 80):
        rect(14, y, 25, 3, (116, 88, 255, 255) if y == 44 else (58, 69, 89, 255))
    for x in (66, 151, 236):
        rect(x, 45, 73, 16, (29, 36, 49, 255))
        rect(x + 6, 51, 32, 3, (110, 124, 147, 255))
        for y in (69, 101, 133, 165):
            rect(x, y, 73, 25, (25, 31, 43, 255))
            rect(x + 6, y + 6, 34, 3, (125, 139, 162, 255))
            rect(x + 6, y + 14, 51, 2, (73, 86, 108, 255))
        for y, color in ((86, (70, 186, 132, 255)), (118, (76, 153, 238, 255)),
                         (150, (238, 167, 70, 255))):
            rect(x + 6, y, 20, 3, color)

    def chunk(kind, data):
        return (struct.pack('!I', len(data)) + kind + data +
                struct.pack('!I', zlib.crc32(kind + data) & 0xffffffff))

    scanlines = b''.join(b'\0' + pixels[row * width * 4:(row + 1) * width * 4]
                         for row in range(height))
    png = (b'\x89PNG\r\n\x1a\n' +
           chunk(b'IHDR', struct.pack('!IIBBBBB', width, height, 8, 6, 0, 0, 0)) +
           chunk(b'IDAT', zlib.compress(scanlines, 9)) + chunk(b'IEND', b''))
    return base64.b64encode(png).decode('ascii')


def main():
    from playwright.sync_api import sync_playwright
    from reverie.config import ConfigManager
    from reverie.session.manager import SessionManager

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--exe', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--ui-variant', choices=['classic', 'liquid-glass'], default='classic')
    args = parser.parse_args()
    output = args.output.resolve()
    if not output.is_relative_to(ROOT/'.runtime'):
        raise ValueError('Evidence must stay under repository .runtime')
    output.mkdir(parents=True, exist_ok=False)
    app_root, workspace, home = [output/n for n in ['app-root', 'workspace', 'desktop-home']]
    for directory in [app_root, workspace, home]:
        directory.mkdir()
    os.environ['REVERIE_APP_ROOT'] = str(app_root)
    os.environ['NO_PROXY'] = '127.0.0.1,localhost'
    config = ConfigManager(workspace)
    config.ensure_dirs()
    manager = SessionManager(config.project_data_dir, project_root=workspace)
    session = manager.create_session('Renderer calibration: authored fixture')
    recommendation_image = 'data:image/png;base64,' + recommendation_preview_png()
    recommendation = {
        'type': 'cards', 'items': [{
            'title': 'Plane', 'description': '开源项目管理看板，支持工作项和项目视图。',
            'badge': {'text': '综合首选', 'tone': 'success'},
            'image': {'url': recommendation_image, 'alt': 'Plane 看板界面预览'},
            'details': ['社区版支持自行部署。'],
            'sources': [{'label': 'Plane 社区', 'url': 'https://example.com/source'}],
            'links': [{'label': '官方网站', 'url': 'https://example.com/'}]
        }]
    }
    content = '''# 渲染校准

**零值与布尔值**

- 保留普通正文
- 保留普通链接

[项目主页](https://example.com/)

```reverie-ui
{"type":"metrics","items":[{"label":"计划中","value":7},{"label":"开发中","value":5},{"label":"已有成果","value":4},{"label":"半归档","value":1}]}
```

## 项目总览表

| 项目 | 数量 | 完成 |
| --- | --- | --- |
| 项目01 | 0 | 否 |
| 项目02 | 1 | 是 |

```python
print(0)
```

## 最值得考虑的开源软件
'''
    content += '\n```reverie-ui\n' + json.dumps(recommendation, ensure_ascii=False) + '\n```\n'
    user_text = '校准长链接换行：https://example.com/' + 'a'*320 + '\n保留链接原文。'
    session.messages = [{'role': 'user', 'content': user_text},
                        {'role': 'assistant', 'content': content}]
    manager.save_session(session)
    fidelity = manager.create_session('Renderer calibration: literal data')
    extra_source = '{"type":"table","columns":["项目"],"rows":[["保留的项目"]],"note":"尚有两项未完成"}'
    literal_source = '''```reverie-ui
{"type":"metrics","items":[{"label":"Record  ID\\n编号","value":9007199254740993},{"label":"精确金额","value":1.2300}]}
```

```reverie-ui
{"type":"table","columns":["编号","精确小数","原始文本","完成","空值"],"rows":[[9007199254740993,0.1234567890123456789,"ID  01\\n第二行",false,null]]}
```

```reverie-ui
{"type":"cards","items":[{"title":"Card  01\\n第二行","description":"首段  双空格\\n次段","badge":{"text":"综合首选","tone":"success"},"image":{"url":"__RECOMMENDATION_IMAGE__","alt":"项目看板截图"},"sources":[{"label":"社区来源","url":"https://example.com/source"}],"links":[{"label":"官方网站","url":"https://example.com/"}]}]}
```
''' + '\n```reverie-ui\n' + extra_source + '\n```\n'
    literal_source = literal_source.replace('"__RECOMMENDATION_IMAGE__"', json.dumps(recommendation_image))
    fidelity.messages = [{'role': 'user', 'content': '校准数据保真；保留编号、数值与空白。'},
                         {'role': 'assistant', 'content': literal_source}]
    manager.save_session(fidelity)
    settings = home/'.reverie/desktop/desktop-settings.json'
    settings.parent.mkdir(parents=True)
    settings.write_text(json.dumps({'coreAppRoot': str(app_root), 'projectRoot': str(workspace),
                                   'ui': {'language': 'zh-CN', 'uiVariant': args.ui_variant}}), encoding='utf-8')
    report = {'scope': __doc__, 'model_quality_samples': 0, 'checks': [], 'captures': [],
              'fixture_sha256': hashlib.sha256(content.encode()).hexdigest(),
              'literal_fixture_sha256': hashlib.sha256(literal_source.encode()).hexdigest(),
              'browser_errors': []}
    process = None
    log = (output/'electron.log').open('x', encoding='utf-8')
    try:
        with sync_playwright() as playwright:
            with socket.socket() as sock:
                sock.bind(('127.0.0.1', 0))
                port = sock.getsockname()[1]
            env = {**os.environ, 'PORTABLE_EXECUTABLE_DIR': str(home)}
            env.pop('ELECTRON_RUN_AS_NODE', None)
            process = subprocess.Popen([str(args.exe.resolve()), '--gui', '--project', str(workspace),
                                        f'--remote-debugging-port={port}'], env=env, stdout=log,
                                       stderr=subprocess.STDOUT, **launch_options())
            browser, page = wait_for_packaged_page(playwright, process, port)
            page.on('pageerror', lambda error: report['browser_errors'].append(str(error)))
            page.wait_for_selector('textarea[aria-autocomplete=list]', timeout=120000)
            page.locator('.session-item').filter(has_text=session.name).click(timeout=60000)
            page.get_by_role('heading', name='渲染校准', exact=True).wait_for()
            target = page.locator('.message.assistant .answer-markdown').last
            target.locator('.answer-metric').first.wait_for(timeout=30000)
            report['build'] = page.evaluate('window.reverie.paths()')['desktopBuild']
            expected = {'metrics': [['计划中', '7'], ['开发中', '5'], ['已有成果', '4'], ['半归档', '1']],
                        'table_rows': [['项目01', '0', '否'], ['项目02', '1', '是']],
                        'heading': '渲染校准', 'strong': '零值与布尔值', 'min_list_items': 2,
                        'min_plain_links': 1, 'link_urls': ['https://example.com/', 'https://example.com/source'],
                        'card_titles': ['Plane'], 'image_urls': [recommendation_image],
                        'min_sources': 1, 'badge_text': '综合首选',
                        'code_pattern': r'print\(0\)'}
            report['checks'].append({'name': 'long-user-source-text-preserved',
                'passed': page.locator('.user-text').first.text_content() == user_text})
            state = target.evaluate(RICH_STATE)
            report['checks'].extend(assess_rich_state(state, expected))
            (output/'dom.json').write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding='utf-8')
            wrong = assess_rich_state(state, {**expected, 'table_rows': [['项目01', '9', '否']]})
            report['checks'].append({'name': 'reject-incorrect-gfm-table-data', 'passed':
                any(c['name'] == 'rich-all-supplied-table-rows' and not c['passed'] for c in wrong)})
            for theme, label in [('dark', '深色'), ('light', '浅色')]:
                page.get_by_role('button', name='切换主题', exact=True).click()
                page.locator('.theme-menu').get_by_role('button', name=label, exact=False).click()
                page.wait_for_function('t=>document.documentElement.dataset.theme===t', arg=theme)
                contrast = target.evaluate(RICH_CONTRAST)
                report['checks'].append({'name': 'actual-text-contrast-'+theme,
                    'passed': bool(contrast) and all(x['passed'] for x in contrast), 'detail': contrast})
                for width in [1280, 460]:
                    page.set_viewport_size({'width': width, 'height': 1500})
                    target.screenshot(path=str(output/f'{theme}-{width}.png'))
                    page.screenshot(path=str(output/f'whole-chat-{theme}-{width}.png'), full_page=True)
                    dimensions = target.evaluate('e=>({width:e.clientWidth,scrollWidth:e.scrollWidth})')
                    transcript = page.locator('.transcript').evaluate('e=>({width:e.clientWidth,scrollWidth:e.scrollWidth})')
                    report['checks'].append({'name': f'whole-chat-contained-{theme}-{width}',
                        'passed': transcript['width'] > 0 and transcript['scrollWidth'] <= transcript['width']+1,
                        'detail': transcript})
                    report['checks'].append({'name': f'contained-{theme}-{width}', 'passed':
                        dimensions['width'] > 0 and dimensions['scrollWidth'] <= dimensions['width']+1,
                        'detail': dimensions})
                    report['captures'].append(f'{theme}-{width}.png')
            page.set_viewport_size({'width': 1280, 'height': 1500})
            page.locator('.session-item').filter(has_text=fidelity.name).click()
            literal_target = page.locator('.message.assistant .answer-markdown').last
            literal_target.locator('.answer-metric').first.wait_for()
            for theme, label in [('dark', '深色'), ('light', '浅色')]:
                page.get_by_role('button', name='切换主题', exact=True).click()
                page.locator('.theme-menu').get_by_role('button', name=label, exact=False).click()
                page.wait_for_function('t=>document.documentElement.dataset.theme===t', arg=theme)
                for width in [1280, 460]:
                    page.set_viewport_size({'width': width, 'height': 1500})
                    observed = literal_target.evaluate('''e => ({
                      metrics: [...e.querySelectorAll('.answer-metric dd')].map(x => x.innerText),
                      metricValueLines: (() => {
                        const x = e.querySelector('.answer-metric-value-long');
                        if (!x) return 0;
                        const range = document.createRange();
                        range.selectNodeContents(x);
                        return range.getClientRects().length;
                      })(),
                      metricColumns: getComputedStyle(e.querySelector('.answer-metrics')).gridTemplateColumns.split(' ').length,
                      metricHorizontalAccess: (() => {
                        const x = e.querySelector('.answer-metric-value-long');
                        return Boolean(x && x.tabIndex === 0 && getComputedStyle(x).overflowX === 'auto');
                      })(),
                      label: e.querySelector('.answer-metric dt')?.innerText,
                      cells: [...e.querySelectorAll('.answer-table tbody td')].map(x => x.innerText),
                      numericCellLines: (() => {
                        const x = e.querySelector('.answer-number');
                        if (!x) return 0;
                        const range = document.createRange();
                        range.selectNodeContents(x);
                        return range.getClientRects().length;
                      })(),
                      title: e.querySelector('.answer-card h3')?.innerText,
                      description: e.querySelector('.answer-card p')?.innerText,
                      image: (() => {
                        const x = e.querySelector('.answer-card-image');
                        if (!x) return null;
                        const s = getComputedStyle(x);
                        return {alt:x.alt, complete:x.complete, width:x.naturalWidth,
                          objectFit:s.objectFit, aspectRatio:s.aspectRatio};
                      })(),
                      badge: e.querySelector('.answer-card .answer-badge')?.innerText,
                      badgeTone: e.querySelector('.answer-card .answer-badge')?.className,
                      sourceLabel: e.querySelector('.answer-card .answer-source span')?.innerText,
                      sourceHref: e.querySelector('.answer-card .answer-source')?.getAttribute('href'),
                      officialLink: e.querySelector('.answer-card-links a')?.innerText,
                      officialHref: e.querySelector('.answer-card-links a')?.getAttribute('href'),
                      cardDimensions: (() => {
                        const x = e.querySelector('.answer-card');
                        return x ? {width:x.clientWidth,scrollWidth:x.scrollWidth,
                          imageWidth:x.querySelector('.answer-card-image')?.getBoundingClientRect().width} : null;
                      })(),
                      original: e.querySelector('.answer-block-fallback pre')?.textContent,
                      tableCount: e.querySelectorAll('.answer-table').length
                    })''')
                    suffix = f'{theme}-{width}'
                    for name, passed in [
                        ('literal-metric-numbers', observed['metrics'] == ['9007199254740993', '1.2300']),
                        ('long-metric-one-line', observed['metricValueLines'] == 1),
                        ('long-metric-responsive-columns', observed['metricColumns'] == 2),
                        ('long-metric-horizontal-accessible', observed['metricHorizontalAccess']),
                        ('literal-metric-spacing', observed.get('label') == 'Record  ID\n编号'),
                        ('literal-table-data', observed['cells'] == ['9007199254740993', '0.1234567890123456789', 'ID  01\n第二行', '否', '—']),
                        ('long-table-number-one-line', observed['numericCellLines'] == 1),
                        ('literal-card-text', observed.get('title') == 'Card  01\n第二行' and observed.get('description') == '首段  双空格\n次段'),
                        ('recommendation-image-renders', bool(observed.get('image') and observed['image']['complete'] and observed['image']['width'] == 320 and observed['image']['alt'] == '项目看板截图' and observed['image']['objectFit'] == 'contain' and observed['image']['aspectRatio'] == '4 / 3')),
                        ('recommendation-badge-renders', observed.get('badge') == '综合首选' and 'answer-badge-success' in (observed.get('badgeTone') or '')),
                        ('recommendation-source-pill-renders', observed.get('sourceLabel') == '社区来源' and observed.get('sourceHref') == 'https://example.com/source'),
                        ('recommendation-official-link-renders', observed.get('officialLink', '').startswith('官方网站') and observed.get('officialHref') == 'https://example.com/'),
                        ('recommendation-card-responsive-contained', bool(observed.get('cardDimensions') and observed['cardDimensions']['width'] > 0 and observed['cardDimensions']['scrollWidth'] <= observed['cardDimensions']['width'] + 1 and observed['cardDimensions']['imageWidth'] > 0)),
                        ('unsupported-fields-retain-source', extra_source in (observed.get('original') or '') and observed['tableCount'] == 1),
                    ]:
                        report['checks'].append({'name': name+'-'+suffix, 'passed': passed, 'detail': observed})
                    literal_target.screenshot(path=str(output/f'literal-{suffix}.png'))
                    page.screenshot(path=str(output/f'literal-chat-{suffix}.png'), full_page=True)
                    report['captures'].extend([f'literal-{suffix}.png', f'literal-chat-{suffix}.png'])
            page.set_viewport_size({'width': 1280, 'height': 1500})
            page.reload()
            page.wait_for_selector('textarea[aria-autocomplete=list]', timeout=120000)
            page.locator('.session-item').filter(has_text=fidelity.name).click()
            literal_target = page.locator('.message.assistant .answer-markdown').last
            literal_target.locator('.answer-metric').first.wait_for()
            reloaded = literal_target.evaluate('''e => ({
              number: e.querySelector('.answer-metric dd')?.innerText,
              original: e.querySelector('.answer-block-fallback pre')?.textContent
            })''')
            report['checks'].append({'name': 'literal-data-after-reload', 'passed':
                reloaded['number'] == '9007199254740993' and
                extra_source in (reloaded.get('original') or ''), 'detail': reloaded})
            report['checks'].append({'name': 'no-browser-errors', 'passed': not report['browser_errors']})
            browser.close()
    except Exception as error:
        report['error'] = type(error).__name__+': '+str(error)
    finally:
        stop_process(process)
        log.close()
        report['passed'] = not report.get('error') and bool(report['checks']) and all(c['passed'] for c in report['checks'])
        (output/'report.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps({'passed': report['passed'], 'error': report.get('error'),
                      'failed_checks': [c['name'] for c in report['checks'] if not c['passed']]}))
    return 0 if report['passed'] else 2


if __name__ == '__main__':
    raise SystemExit(main())
