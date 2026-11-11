from pathlib import Path
import json
import pytest
import subprocess
import sys
from unittest.mock import Mock

from reverie.computer_use.runtime import ComputerUseRuntime, NativeDesktopError
from reverie.desktop_control import RunControl


def _desktop_holder():
    script = "from reverie.computer_use.runtime import desktop_occupation; import sys; lock=desktop_occupation('hold',lambda _:None,mutation=False); lock.__enter__(); print('locked',flush=True); sys.stdin.readline(); lock.__exit__(None,None,None)"
    process = subprocess.Popen([sys.executable,'-c',script],stdin=subprocess.PIPE,stdout=subprocess.PIPE,text=True,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
    assert process.stdout.readline().strip() == 'locked'
    return process


@pytest.mark.skipif(sys.platform != 'win32',reason='Windows logon-session mutex')
def test_real_desktop_mutex_serializes_separate_processes():
    from reverie.computer_use.runtime import desktop_occupation
    holder = _desktop_holder()
    try:
        with pytest.raises(NativeDesktopError,match='owns the desktop'):
            with desktop_occupation('click',lambda _:None,mutation=True,timeout_ms=100):
                pytest.fail('Overlapping action was granted')
    finally:
        holder.communicate('\n',timeout=5)
    with desktop_occupation('snapshot',lambda _:None,mutation=False,timeout_ms=100):
        pass


@pytest.mark.skipif(sys.platform != 'win32',reason='Windows abandoned-mutex recovery')
def test_abandoned_desktop_owner_requires_observation():
    from reverie.computer_use.runtime import desktop_occupation
    holder = _desktop_holder()
    checks = 0
    def check(_):
        nonlocal checks
        checks += 1
        if checks == 2:
            holder.kill()
            holder.wait(timeout=5)
    try:
        with pytest.raises(NativeDesktopError) as error:
            with desktop_occupation('click',check,mutation=True,timeout_ms=2000):
                pytest.fail('Uncertain prior owner was ignored')
        assert error.value.envelope['error']['code'] == 'DESKTOP_OWNER_INTERRUPTED'
        assert error.value.envelope['error']['disposition']['retry'] == 'unsafe'
    finally:
        if holder.poll() is None:
            holder.kill()
        holder.communicate(timeout=5)


def test_missing_engine_is_an_actionable_error(tmp_path):
    runtime = ComputerUseRuntime(tmp_path, binary=tmp_path / 'absent.exe')
    with pytest.raises(NativeDesktopError) as failure:
        runtime.command('snapshot', ['--app', 'test'])
    assert failure.value.envelope['error']['code'] == 'ENGINE_UNAVAILABLE'
    assert failure.value.envelope['error']['disposition']['delivery'] == 'not_delivered'


def test_only_approved_native_commands_are_dispatched(tmp_path):
    runtime = ComputerUseRuntime(tmp_path)
    with pytest.raises(NativeDesktopError) as failure:
        runtime.command('batch', ['[]'])
    assert failure.value.envelope['error']['code'] == 'INVALID_ARGS'


def test_sessions_are_unique_even_for_same_reverie_data_directory(tmp_path):
    assert ComputerUseRuntime(tmp_path).session_id != ComputerUseRuntime(tmp_path).session_id


def test_uncertain_failure_keeps_delivery_and_retry(tmp_path):
    payload = {'version': '2.6', 'ok': False, 'command': 'click', 'error': {
        'code': 'TIMEOUT', 'message': 'readback timed out',
        'disposition': {'delivery': 'delivery_uncertain', 'retry': 'unsafe'}}}
    with pytest.raises(NativeDesktopError) as failure:
        ComputerUseRuntime.decode(json.dumps(payload), 'click')
    assert failure.value.envelope == payload


@pytest.mark.parametrize('raw', ['not json', '{"version":"9","ok":true,"data":{}}'])
def test_invalid_protocol_never_becomes_success(raw):
    with pytest.raises(NativeDesktopError):
        ComputerUseRuntime.decode(raw, 'click')


def process_runtime(tmp_path, monkeypatch, process):
    runtime = ComputerUseRuntime(tmp_path)
    monkeypatch.setattr(runtime, '_verify_binary', lambda: None)
    start = Mock(return_value=process)
    monkeypatch.setattr(subprocess, 'Popen', start)
    return runtime, start


def test_action_timeout_is_unknown_and_never_replayed(tmp_path, monkeypatch):
    process = Mock()
    process.communicate.side_effect = [subprocess.TimeoutExpired('click', 2), (b'', b'')]
    runtime, start = process_runtime(tmp_path, monkeypatch, process)
    runtime.images['old'] = {}
    with pytest.raises(NativeDesktopError) as error:
        runtime.command('click', ['@s:e1'], timeout_ms=5)
    assert error.value.envelope['error']['disposition'] == {'delivery': 'unknown', 'retry': 'unsafe'}
    assert start.call_count == 1
    process.kill.assert_called_once()
    assert runtime.images == {}


@pytest.mark.parametrize('output,code', [(b'', 'NATIVE_EXIT'), (b'\xff', 'INVALID_RESPONSE'), (b'not json', 'INVALID_RESPONSE')])
def test_bad_native_output_keeps_action_uncertainty(tmp_path, monkeypatch, output, code):
    process = Mock(returncode=1)
    process.communicate.return_value = output, b''
    runtime, start = process_runtime(tmp_path, monkeypatch, process)
    with pytest.raises(NativeDesktopError) as error:
        runtime.command('type', ['@s:e1', '--stdin'], text='中文\nprivate')
    assert error.value.envelope['error']['code'] == code
    assert error.value.envelope['error']['disposition']['retry'] == 'unsafe'
    assert 'private' not in str(start.call_args)
    assert process.communicate.call_args.args == ('中文\nprivate'.encode('utf-8'),)
    assert start.call_count == 1


def test_stopped_run_cannot_start_an_action(tmp_path, monkeypatch):
    runtime, start = process_runtime(tmp_path, monkeypatch, Mock())
    runtime.control = RunControl(lambda event: None)
    runtime.control.stop()
    with pytest.raises(NativeDesktopError) as error:
        runtime.command('click', ['@s:e1'])
    assert error.value.envelope['error']['code'] == 'CANCELLED'
    assert error.value.envelope['error']['disposition']['delivery'] == 'not_delivered'
    start.assert_not_called()


def test_cancellation_during_atomic_input_keeps_delivery_then_blocks_next_action(tmp_path, monkeypatch):
    process = Mock(returncode=0)
    runtime, start = process_runtime(tmp_path, monkeypatch, process)
    control = runtime.control = RunControl(lambda event: None)
    payload = {'version': '2.6', 'ok': True, 'data': {'disposition': {'delivery': 'delivered_unverified', 'retry': 'unsafe'}}}
    def communicate(*args, **kwargs):
        control.stop()
        return json.dumps(payload).encode(), b''
    process.communicate.side_effect = communicate
    assert runtime.command('press', ['Enter']) == payload
    process.terminate.assert_not_called()
    with pytest.raises(NativeDesktopError):
        runtime.command('press', ['Enter'])
    assert start.call_count == 1


def test_cancellation_terminates_observation_and_releases_callback(tmp_path, monkeypatch):
    process = Mock(returncode=-1)
    process.poll.return_value = None
    runtime, _ = process_runtime(tmp_path, monkeypatch, process)
    control = runtime.control = RunControl(lambda event: None)
    def communicate(*args, **kwargs):
        control.stop()
        return b'', b''
    process.communicate.side_effect = communicate
    with pytest.raises(NativeDesktopError) as error:
        runtime.command('snapshot', ['--app=test'])
    assert error.value.envelope['error']['code'] == 'CANCELLED'
    process.terminate.assert_called_once()
    assert not control._cancel_callbacks
