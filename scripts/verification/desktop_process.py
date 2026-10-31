"""Own only the isolated Desktop process tree launched by a verifier."""
import os
from pathlib import Path
import signal
import subprocess
import sys
import time


def packaged_kernel_path(executable):
    directory = Path(executable).resolve().parent
    if sys.platform == 'darwin':
        directory = directory.parent
    return directory / ('reverie.exe' if sys.platform == 'win32' else 'reverie')


def launch_options(*, visible=False):
    if os.name != 'nt':
        return {'start_new_session': True}
    startup = subprocess.STARTUPINFO()
    startup.dwFlags |= subprocess.STARTF_USESHOWWINDOW
    startup.wShowWindow = int(visible)
    return {'startupinfo': startup}


def stop_process(process):
    if process is None or process.poll() is not None:
        return
    if os.name == 'nt':
        subprocess.run(['taskkill', '/PID', str(process.pid), '/T', '/F'],
                       capture_output=True, creationflags=subprocess.CREATE_NO_WINDOW)
    elif os.getpgid(process.pid) == process.pid:
        os.killpg(process.pid, signal.SIGTERM)
    else:
        process.terminate()
    try:
        process.wait(timeout=30)
    except subprocess.TimeoutExpired:
        if os.name != 'nt' and os.getpgid(process.pid) == process.pid:
            os.killpg(process.pid, signal.SIGKILL)
        else:
            process.kill()
        process.wait(timeout=15)


def wait_for_packaged_page(playwright, process, port, *, attempts=160):
    """Wait for the owned native window; CDP can listen before its page exists."""
    from playwright.sync_api import TimeoutError as BrowserTimeout

    browser = None
    last_error = None
    for _ in range(attempts):
        return_code = process.poll()
        if return_code is not None:
            return_code = getattr(process, 'returncode', return_code)
            raise RuntimeError(
                'Packaged Desktop exited before its page was ready '
                f'(exit code {return_code})'
            )
        if browser is None or not browser.is_connected():
            try:
                browser = playwright.chromium.connect_over_cdp(f'http://127.0.0.1:{port}', timeout=1000)
            except Exception:
                time.sleep(.25)
                continue
        pages = [page for context in browser.contexts for page in context.pages if not page.is_closed()]
        if pages:
            return browser, pages[0]
        # contexts/pages are cached properties. Pump the actual target events;
        # sleeping alone cannot deliver a BrowserWindow created after connect.
        if browser.contexts:
            try:
                page = browser.contexts[0].wait_for_event('page', timeout=250)
                if not page.is_closed():
                    return browser, page
            except BrowserTimeout:
                pass
            except Exception as error:
                # Context closure can arrive before the browser disconnect or
                # owned process exit. Reconnect within the same bounded wait;
                # the next ownership check distinguishes exit from no window.
                last_error = error
                browser = None
                time.sleep(.25)
                continue
        else:
            # A read-only protocol round trip also dispatches context events.
            session = browser.new_browser_cdp_session()
            try:
                session.send('Target.getTargets')
            finally:
                session.detach()
            time.sleep(.25)
    if browser is None:
        raise RuntimeError('No packaged CDP endpoint') from last_error
    raise RuntimeError('No packaged Desktop window page became ready') from last_error
