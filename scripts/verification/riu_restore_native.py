"""Open an installed payload against a copied P4 profile; no model calls."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import socket
import subprocess
import sys

from desktop_process import launch_options, stop_process, wait_for_packaged_page
from riu_quality_benchmark import latest_published_view_reference, settle_view, wait_for_registered_view_frame

ROOT = Path(__file__).resolve().parents[2]


def main():
    from playwright.sync_api import expect, sync_playwright
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--exe', type=Path, required=True)
    parser.add_argument('--profile', type=Path, required=True)
    parser.add_argument('--fixture', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--expected-build', required=True)
    parser.add_argument('--compare', type=Path)
    parser.add_argument('--seed-state', action='store_true', help='Save nondefault state through the authored fixture controls before upgrade.')
    args = parser.parse_args()
    profile, fixture, output = [p.resolve() for p in [args.profile, args.fixture, args.output]]
    if not all(p.is_relative_to(ROOT/'.runtime') for p in [profile, fixture, output]):
        raise ValueError('Keep copied profiles and evidence repository-local')
    output.mkdir(parents=True, exist_ok=False)
    app_root, home = profile/'app-root', profile/'desktop-home'
    if not profile.exists():
        profile.mkdir()
        shutil.copytree(fixture/'app-root', app_root, ignore=shutil.ignore_patterns('browser', 'git-checkpoints'))
        settings = home/'.reverie/desktop/desktop-settings.json'
        settings.parent.mkdir(parents=True)
        source = json.loads((fixture/'desktop-home/.reverie/desktop/desktop-settings.json').read_text(encoding='utf-8'))
        source.update(coreAppRoot=str(app_root), projectRoot=str(fixture/'workspace'))
        settings.write_text(json.dumps(source), encoding='utf-8')
    report = {'scope': __doc__, 'executable': str(args.exe.resolve()), 'model_quality_samples': 0,
              'checks': [], 'passed': False, 'browser_errors': []}
    process = None
    log = (output/'electron.log').open('x', encoding='utf-8')
    try:
        with sync_playwright() as playwright:
            with socket.socket() as sock:
                sock.bind(('127.0.0.1', 0))
                port = sock.getsockname()[1]
            env = {**os.environ, 'REVERIE_APP_ROOT': str(app_root),
                   'PORTABLE_EXECUTABLE_DIR': str(home), 'NO_PROXY': '127.0.0.1,localhost'}
            env.pop('ELECTRON_RUN_AS_NODE', None)
            process = subprocess.Popen([str(args.exe.resolve()), '--gui', '--project', str(fixture/'workspace'),
                                        f'--remote-debugging-port={port}'], env=env, stdout=log,
                                       stderr=subprocess.STDOUT, **launch_options())
            browser, page = wait_for_packaged_page(playwright, process, port)
            page.on('pageerror', lambda error: report['browser_errors'].append(str(error)))
            page.wait_for_selector('.session-item', timeout=120000)
            page.locator('.session-item').filter(has_text='RIU P4 · acceptance').click()
            report['build'] = page.evaluate('window.reverie.paths()')['desktopBuild']
            report['checks'].append({'name': 'expected-native-build', 'passed': report['build']['id'] == args.expected_build})
            from reverie.config import ConfigManager
            from reverie.session.manager import SessionManager
            from reverie.views import ViewStore
            os.environ['REVERIE_APP_ROOT'] = str(app_root)
            config = ConfigManager(fixture / 'workspace')
            manager = SessionManager(config.project_data_dir, project_root=fixture / 'workspace')
            sessions = [item for item in manager.list_sessions() if item.name == 'RIU P4 · acceptance']
            if len(sessions) != 1:
                raise RuntimeError('Fixture must identify one acceptance session.')
            session = manager.load_session(sessions[0].id)
            ref = latest_published_view_reference(session.messages, ViewStore.for_project(fixture / 'workspace'), session.id)
            if ref is None:
                raise RuntimeError('Fixture has no published primary view.')
            view_id, revision = ref
            report['selected_registered_reference'] = [view_id, revision]
            target, frame = wait_for_registered_view_frame(page, (view_id, revision), process=process)
            # Keep the actual view active while exercising nondefault inputs;
            # scrolling an inline field must not trigger its offscreen unloading.
            surface = page.locator('.interactive-view').filter(has=target)
            surface.locator('[data-view-mode="fullscreen"]').click()
            settle_view(page, frame)
            frame.wait_for_function('()=>window.__p4?.ready', timeout=30000)
            identity = frame.evaluate('window.__p4.instance')
            if args.seed_state:
                frame.locator('#filter').fill('Row 1')
                frame.locator('#rate').press('Home')
                frame.locator('#rate').press('ArrowRight')
                frame.locator('#layout').select_option('carousel')
                frame.locator('#size').select_option('0')
                # Explicit synthetic fixture instrumentation, never model HTML.
                frame.evaluate('window.__p4.privateSentinel="RIU_INSTALL_UPGRADE_PRIVATE"')
                frame.locator('#save').click()
                expect(frame.locator('#saved')).to_contain_text('Saved')
            report['restored_values'] = frame.evaluate('()=>Object.fromEntries(["filter","rate","layout","size"].map(k=>[k,document.getElementById(k).value]))')
            private = frame.evaluate('window.__p4.privateSentinel')
            report['private_state_sha256'] = hashlib.sha256(json.dumps(private).encode()).hexdigest()
            if args.seed_state:
                report['checks'].append({'name': 'saved-nondefault-fixture-state', 'passed':
                    report['restored_values'] == {'filter': 'Row 1', 'rate': '2', 'layout': 'carousel', 'size': '0'}
                    and private == 'RIU_INSTALL_UPGRADE_PRIVATE'})
            if args.compare:
                previous = json.loads(args.compare.read_text(encoding='utf-8'))
                report['checks'].append({'name': 'upgrade-preserves-input-and-private-state', 'passed':
                    previous['restored_values'] == report['restored_values'] and
                    previous['private_state_sha256'] == report['private_state_sha256']})
            surface = page.locator('.interactive-view').filter(has=target)
            for mode in ['fullscreen', 'pip', 'inline']:
                surface.locator(f'[data-view-mode="{mode}"]').click()
                expect(surface).to_have_attribute('data-display-mode', mode)
                report['checks'].append({'name': 'same-document-'+mode,
                                         'passed': frame.evaluate('window.__p4.instance') == identity})
            report['checks'].append({'name': 'no-browser-errors', 'passed': not report['browser_errors']})
            page.screenshot(path=str(output/'restored.png'), full_page=True)
            browser.close()
            report['passed'] = all(c['passed'] for c in report['checks'])
    except Exception as error:
        report['error'] = type(error).__name__+': '+str(error)
        if 'page' in locals() and not page.is_closed():
            try:
                page.screenshot(path=str(output/'failure.png'), full_page=True)
                (output/'failure-dom.json').write_text(json.dumps(page.evaluate('''()=>({
                    text:document.body.innerText,
                    anchors:[...document.querySelectorAll('.interactive-view-anchor')].map(e=>({key:e.dataset.viewKey,text:e.innerText})),
                    frames:[...document.querySelectorAll('iframe')].map(e=>({title:e.title,viewId:e.dataset.viewId,src:e.getAttribute('src')}))
                })'''),ensure_ascii=False,indent=2),encoding='utf-8')
            except Exception:
                pass
    finally:
        stop_process(process)
        log.close()
        (output/'report.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps({'passed': report['passed'], 'error': report.get('error'), 'build': report.get('build')}))
    return 0 if report['passed'] else 2


if __name__ == '__main__':
    raise SystemExit(main())
