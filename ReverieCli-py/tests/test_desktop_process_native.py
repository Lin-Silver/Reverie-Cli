"""Actual delayed Electron windows for the verification lifecycle helper."""
from pathlib import Path
import importlib.util
import os
import socket
import subprocess
from types import SimpleNamespace

import pytest

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location('desktop_wait_native', ROOT / 'scripts/verification/desktop_process.py')
desktop = importlib.util.module_from_spec(spec)
spec.loader.exec_module(desktop)


@pytest.mark.parametrize('platform,relative,expected', [
    ('darwin', 'Reverie.app/Contents/MacOS/ReverieUI', 'Reverie.app/Contents/reverie'),
    ('win32', 'win-unpacked/ReverieUI.exe', 'win-unpacked/reverie.exe'),
    ('linux', 'linux-unpacked/ReverieUI', 'linux-unpacked/reverie'),
])
def test_kernel_path_matches_native_package_layout(tmp_path, monkeypatch, platform, relative, expected):
    monkeypatch.setattr(desktop.sys, 'platform', platform)
    assert desktop.packaged_kernel_path(tmp_path / relative) == (tmp_path / expected).resolve()


@pytest.mark.parametrize('owns_group', [True, False])
def test_unresponsive_owned_process_is_reaped_without_signalling_another_group(monkeypatch, owns_group):
    calls = []
    waits = iter([subprocess.TimeoutExpired('fixture', 30), None])

    def wait(timeout):
        result = next(waits)
        if result:
            raise result

    process = SimpleNamespace(pid=123, poll=lambda: None, wait=wait,
        terminate=lambda: calls.append('terminate'), kill=lambda: calls.append('kill'))
    monkeypatch.setattr(desktop, 'os', SimpleNamespace(name='posix',
        getpgid=lambda pid: pid if owns_group else 999,
        killpg=lambda pid, sig: calls.append((pid, sig))))
    monkeypatch.setattr(desktop, 'signal', SimpleNamespace(SIGTERM=15, SIGKILL=9))
    desktop.stop_process(process)
    assert calls == ([(123, 15), (123, 9)] if owns_group else ['terminate', 'kill'])


@pytest.mark.parametrize('mode', ['delayed', 'exit', 'none'])
def test_waiter_observes_only_an_actual_owned_electron_window(tmp_path, mode):
    electron = ROOT / 'ReverieCli-ui/node_modules/electron/dist/electron'
    if not electron.exists() or not os.environ.get('DISPLAY'):
        pytest.skip('The native lifecycle fixture requires Electron and a display')
    from playwright.sync_api import sync_playwright
    fixture = tmp_path / 'main.cjs'
    fixture.write_text('''const {app,BrowserWindow}=require('electron');let window;
      app.whenReady().then(()=>{
        require('fs').writeFileSync(process.env.REVERIE_TEST_READY,'ready');
        if(process.env.REVERIE_TEST_MODE==='exit'){setTimeout(()=>app.quit(),700);return}
        if(process.env.REVERIE_TEST_MODE==='none')return;
        setTimeout(()=>{window=new BrowserWindow({show:false});
          window.loadURL('data:text/html,<title>Owned delayed window</title>')},1800);
      });''')
    with socket.socket() as sock:
        sock.bind(('127.0.0.1', 0))
        port = sock.getsockname()[1]
    marker = tmp_path / 'ready'
    env = {**os.environ, 'REVERIE_TEST_MODE': mode, 'REVERIE_TEST_READY': str(marker)}
    env.pop('ELECTRON_RUN_AS_NODE', None)
    with (tmp_path / 'electron.log').open('w') as log, sync_playwright() as playwright:
        process = subprocess.Popen([str(electron), '--no-sandbox', '--disable-gpu', '--disable-dev-shm-usage',
            f'--remote-debugging-port={port}', str(fixture)], env=env, stdout=log, stderr=log,
            **desktop.launch_options())
        try:
            if mode == 'delayed':
                browser, page = desktop.wait_for_packaged_page(playwright, process, port, attempts=24)
                page.wait_for_function('()=>document.title==="Owned delayed window"')
                assert page.title() == 'Owned delayed window'
                assert len([p for c in browser.contexts for p in c.pages]) == 1
                browser.close()
            else:
                with pytest.raises(RuntimeError, match='exited' if mode == 'exit' else 'window page'):
                    desktop.wait_for_packaged_page(playwright, process, port, attempts=8)
        finally:
            desktop.stop_process(process)
        assert process.poll() is not None
        assert marker.exists(), 'The fixture must initialize successfully before testing exit/no-window behavior'
