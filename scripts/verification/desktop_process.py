"""Own only the isolated Desktop process tree launched by a verifier."""
import os
import ctypes
from contextlib import contextmanager
from pathlib import Path
import json
import signal
import subprocess
import sys
import time


@contextmanager
def keep_windows_awake():
    """Hold a temporary test-thread power request, restoring its prior state on exit."""
    record={'required':os.name=='nt','acquired':False,'released':False}
    previous=None
    if os.name=='nt':
        execution_state=ctypes.windll.kernel32.SetThreadExecutionState
        execution_state.argtypes=[ctypes.c_uint]
        execution_state.restype=ctypes.c_uint
        previous=execution_state(0x80000003)
        if not previous:
            raise RuntimeError('Windows did not acquire the temporary verification power request.')
        record['acquired']=True
    try:
        yield record
    finally:
        if previous is not None:
            record['released']=bool(execution_state(previous | 0x80000000))
            if not record['released']:
                raise RuntimeError('Windows did not release the temporary verification power request.')


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


def native_window_state(root_pid):
    """Read owned native window visibility without changing focus or window state."""
    if os.name != 'nt':
        return {'required': False}
    from ctypes import wintypes
    import psutil

    process = psutil.Process(root_pid)
    owned = {root_pid, *(child.pid for child in process.children(recursive=True))}
    user32 = ctypes.windll.user32
    user32.GetWindowThreadProcessId.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.DWORD)]
    user32.GetWindowThreadProcessId.restype = wintypes.DWORD
    user32.IsWindowVisible.argtypes = [wintypes.HWND]
    user32.IsIconic.argtypes = [wintypes.HWND]
    user32.GetWindowRect.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.RECT)]
    user32.GetForegroundWindow.restype = wintypes.HWND
    foreground = user32.GetForegroundWindow()
    left, top = user32.GetSystemMetrics(76), user32.GetSystemMetrics(77)
    right, bottom = left + user32.GetSystemMetrics(78), top + user32.GetSystemMetrics(79)
    windows = []
    callback_type = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)

    def observe(hwnd, _data):
        pid = wintypes.DWORD()
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
        if pid.value not in owned or not user32.IsWindowVisible(hwnd) or user32.IsIconic(hwnd):
            return True
        bounds = wintypes.RECT()
        if not user32.GetWindowRect(hwnd, ctypes.byref(bounds)):
            return True
        if min(bounds.right, right) <= max(bounds.left, left) or min(bounds.bottom, bottom) <= max(bounds.top, top):
            return True
        windows.append({'pid': pid.value, 'handle': int(hwnd),
                        'bounds': [bounds.left, bounds.top, bounds.right, bounds.bottom],
                        'foreground': hwnd == foreground})
        return True

    callback = callback_type(observe)
    user32.EnumWindows.argtypes = [callback_type, wintypes.LPARAM]
    user32.EnumWindows.restype = wintypes.BOOL
    if not user32.EnumWindows(callback, 0):
        raise ctypes.WinError()
    return {'required': True, 'visible': bool(windows),
            'foreground': any(window['foreground'] for window in windows), 'windows': windows}


def wait_for_native_foreground(page, root_pid, output, phase):
    """Request native test focus; the observer itself never activates a window."""
    if os.name != 'nt':
        return {'required': False}
    started = time.monotonic()
    destination = Path(output) / 'native-foreground.json'
    while True:
        state = native_window_state(root_pid)
        ready = state['visible'] and state['foreground']
        destination.write_text(json.dumps({
            'phase': phase, 'pid': root_pid, 'status': 'ready' if ready else 'waiting',
            'wait_seconds': time.monotonic() - started, 'native': state,
        }, indent=2), encoding='utf-8')
        if ready:
            return state
        if time.monotonic() - started >= 120:
            raise RuntimeError('Native qualification requires the owned window to be visible and in the foreground.')
        page.wait_for_timeout(100)


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
