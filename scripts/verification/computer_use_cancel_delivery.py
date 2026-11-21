"""Cancel real native input after an owned window receives mouse-down.

The finite drag may finish. A later click must be refused without delivery.
The original fixture is copied with event logging only; no user data is used.
"""
from pathlib import Path
import argparse
import ctypes
import hashlib
import json
import os
import subprocess
import sys
import threading
import time

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'ReverieCli-py'))
from reverie.computer_use.operations import execute
from reverie.computer_use.runtime import ComputerUseRuntime, NativeDesktopError
from reverie.desktop_control import RunControl


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--binary', type=Path)
    args = parser.parse_args()
    output = args.output.resolve()
    if not output.is_relative_to(ROOT / '.runtime'):
        raise ValueError('Use a fresh project .runtime directory')
    output.mkdir(parents=True, exist_ok=False)
    source = ROOT / 'scripts/verification/fixtures/computer-use/Fixture.cs'
    events = output / 'delivery-events.txt'
    literal = '@"' + str(events).replace('"', '""') + '"'
    original = source.read_text(encoding='utf-8')
    down = 'dragging=true; origin=e.Location;'
    up = 'dragging=false; };'
    assert original.count(down) == 1 and original.count(up) == 1
    instrumented = original.replace(down, down + f' File.AppendAllText({literal}, "down\\n");')
    instrumented = instrumented.replace(up, f'File.AppendAllText({literal}, "up\\n"); ' + up)
    fixture_source = output / 'Fixture.cs'
    fixture_source.write_text(instrumented, encoding='utf-8')
    binary = output / 'ReverieDesktopFixture.exe'
    subprocess.run(['C:/Windows/Microsoft.NET/Framework64/v4.0.30319/csc.exe', '/nologo',
                    '/target:winexe', '/out:' + str(binary), '/r:System.Windows.Forms.dll',
                    '/r:System.Drawing.dll', str(fixture_source)], check=True, capture_output=True)
    process = subprocess.Popen([str(binary), str(output / 'saved.txt')],
        env={**os.environ, 'REVERIE_EXTENDED_FIXTURE': '1'},
        creationflags=subprocess.CREATE_NO_WINDOW)
    control_events = []
    control = RunControl(control_events.append)
    runtime = ComputerUseRuntime(output / 'sender', binary=args.binary, control=control)
    observer = ComputerUseRuntime(output / 'observer', binary=args.binary)
    report = {'passed': False, 'checks': {}, 'control_events': control_events,
              'fixture_sha256': hashlib.sha256(source.read_bytes()).hexdigest(),
              'instrumented_fixture_sha256': hashlib.sha256(fixture_source.read_bytes()).hexdigest()}
    outcome = {}
    report['current_input'] = outcome
    thread = None
    try:
        deadline = time.monotonic() + 20
        while True:
            windows = [w for w in observer.command('list-windows')['data'] if w['pid'] == process.pid]
            if windows:
                assert len(windows) == 1
                wid = windows[0]['id']
                break
            if time.monotonic() >= deadline:
                raise TimeoutError('Owned fixture did not appear')
            time.sleep(.1)
        canvas = execute(runtime, 'computer_find', {'window_id': wid, 'native_id': 'dragCanvas', 'exact': True}, vision=True)['data']['matches']
        assert len(canvas) == 1
        # The noninteractive canvas has bounds but no actionable ref.
        bounds = canvas[0]['bounds']
        report['canvas_observation'] = canvas[0]
        button = execute(runtime, 'computer_find', {'window_id': wid, 'name': 'Increment counter', 'exact': True}, vision=True)['data']['matches']
        assert len(button) == 1
        try:
            execute(runtime, 'computer_window', {'window_id': wid, 'action': 'focus'}, vision=True)
        except NativeDesktopError as error:
            report['focus_error'] = error.envelope
            (output / 'awaiting-foreground.json').write_text(json.dumps({'pid': process.pid, 'window_id': wid}), encoding='utf-8')
            print('READY FOR FOREGROUND ' + str(output), flush=True)
            deadline = time.monotonic() + 90
            while not next(w for w in observer.command('list-windows')['data'] if w['id'] == wid)['is_focused']:
                if time.monotonic() >= deadline:
                    raise TimeoutError('Owned fixture did not acquire foreground within 90 seconds')
                time.sleep(.25)
        image = execute(runtime, 'computer_screenshot', {'window_id': wid}, vision=True)['data']
        origin = image['capture_bounds']
        x = (bounds['x'] + bounds['width'] / 2 - origin['x']) * image['scale_x']
        y = (bounds['y'] + bounds['height'] / 2 - origin['y']) * image['scale_y']
        drag = {'from_image_id': image['image_id'], 'to_image_id': image['image_id'],
                'from_x': x - 60, 'from_y': y - 60, 'to_x': x + 60, 'to_y': y + 60}
        report['image_observation'] = image
        report['drag_arguments'] = drag
        def deliver():
            try:
                outcome['response'] = execute(runtime, 'computer_drag', drag, vision=True)
            except Exception as error:
                outcome['error'] = type(error).__name__ + ': ' + str(error)
                if isinstance(error, NativeDesktopError):
                    outcome['error_envelope'] = error.envelope
            finally:
                outcome['finished_at'] = time.monotonic()
        thread = threading.Thread(target=deliver)
        thread.start()
        deadline = time.monotonic() + 10
        while True:
            observed = events.read_text(encoding='utf-8').splitlines() if events.exists() else []
            if observed:
                break
            if not thread.is_alive() or time.monotonic() >= deadline:
                raise RuntimeError('No mouse-down was independently observed during delivery')
            time.sleep(.005)
        report['checks']['cancel_requested_during_delivery'] = observed == ['down'] and thread.is_alive()
        assert report['checks']['cancel_requested_during_delivery']
        report['cancel_requested_at'] = time.monotonic()
        control.stop()
        thread.join(timeout=10)
        assert not thread.is_alive(), 'Finite input did not finish within its deadline'
        report['current_input'] = outcome
        report['checks']['finite_input_completed'] = outcome.get('response', {}).get('ok') is True
        report['delivery_events'] = events.read_text(encoding='utf-8').splitlines()
        report['checks']['balanced_single_drag'] = report['delivery_events'] == ['down', 'up']
        report['checks']['mouse_button_released'] = not (ctypes.windll.user32.GetAsyncKeyState(1) & 0x8000)
        completed = execute(observer, 'computer_find', {'window_id': wid, 'name': 'Drag completed: 1', 'exact': True}, vision=True)['data']['matches']
        report['checks']['drag_effect_verified'] = len(completed) == 1
        try:
            execute(runtime, 'computer_click', {'ref': button[0]['ref_id'], 'physical': True}, vision=True)
        except NativeDesktopError as error:
            report['next_input_error'] = error.envelope
            report['checks']['next_input_refused'] = error.envelope['error']['code'] == 'CANCELLED'
        else:
            report['checks']['next_input_refused'] = False
        counter = execute(observer, 'computer_find', {'window_id': wid, 'name': 'Count: 0', 'exact': True}, vision=True)['data']['matches']
        report['checks']['no_later_click_effect'] = len(counter) == 1
        report['native_binary_sha256'] = hashlib.sha256(runtime.binary.read_bytes()).hexdigest()
        report['checks']['fixture_input_unchanged'] = hashlib.sha256(source.read_bytes()).hexdigest() == report['fixture_sha256']
        report['passed'] = all(report['checks'].values())
    except Exception as error:
        report['error'] = type(error).__name__ + ': ' + str(error)
        if isinstance(error, NativeDesktopError):
            report['error_envelope'] = error.envelope
    finally:
        if thread and thread.is_alive():
            thread.join(timeout=10)
        runtime.close()
        observer.close()
        report['native_calls'] = runtime.metrics
        report['observer_calls'] = observer.metrics
        process.terminate()
        process.wait(timeout=5)
        report['fixture_exit_code'] = process.returncode
        (output / 'report.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps(report, ensure_ascii=True))
    return 0 if report['passed'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
