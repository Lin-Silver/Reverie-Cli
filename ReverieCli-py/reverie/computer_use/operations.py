"""The fixed mapping from Reverie desktop operations to native CLI commands."""
from __future__ import annotations

from pathlib import Path
import re
import subprocess
import time

from .runtime import failure


def flags(values: dict, keys: tuple | list) -> list[str]:
    result = []
    for key in keys:
        value = values.get(key)
        if value is None or value is False:
            continue
        flag = '--' + key.replace('_', '-')
        result.append(flag if value is True else f'{flag}={value}')
    return result


def ref(value: str) -> str:
    if not isinstance(value, str) or not re.fullmatch(r'@[A-Za-z0-9_-]+:e[0-9]+', value):
        raise failure('ref', 'INVALID_ARGS', 'Use a qualified ref from this session: @<snapshot_id>:eN.')
    return value


def scope(p: dict, *, required: bool = True) -> list[str]:
    if required and not any(p.get(k) for k in ('app', 'window_id', 'root', 'surface')):
        raise failure('scope', 'INVALID_ARGS', 'Specify app or window_id from the desktop inventory.')
    return flags(p, ('app', 'window_id'))


def execute(runtime, name: str, p: dict, *, vision: bool = False) -> dict:
    op = name.removeprefix('computer_')
    timeout = int(p.get('timeout_ms', 5000))
    if not 1 <= timeout <= 60000:
        raise failure(op, 'INVALID_ARGS', 'timeout_ms must be between 1 and 60000.')
    invoke = lambda c, a=None, **kw: runtime.command(c, a, timeout_ms=timeout, **kw)
    if op == 'status':
        result = invoke('status')
        result['data']['reverie_engine'] = {'version': '1.2.0', 'protocol': '2.6', 'vision': vision}
        return result
    if op in {'list_apps', 'list_windows', 'list_displays', 'list_surfaces'}:
        result = invoke(op.replace('_', '-'), flags(p, ('app',)))
        if op == 'list_windows' and p.get('window_id'):
            result['data'] = [w for w in result['data'] if w['id'] == p['window_id']]
        return result
    if op == 'snapshot':
        if p.get('root'):
            ref(p['root'])
        options = {'compact': True, **p}
        return invoke('snapshot', scope(p) + flags(options, ('root', 'surface', 'compact', 'skeleton', 'interactive_only', 'include_bounds', 'max_depth')) + [f'--timeout-ms={timeout}'])
    if op == 'find':
        if p.get('root'):
            ref(p['root'])
        return invoke('find', scope(p) + flags(p, ('root', 'surface', 'role', 'name', 'text', 'value', 'native_id', 'exact', 'limit')) + [f'--timeout-ms={timeout}'])
    if op in {'get', 'is'}:
        return invoke(op, [ref(p['ref']), '--property=' + p.get('property', 'text' if op == 'get' else 'visible')])
    if op == 'screenshot':
        from .images import capture
        return capture(runtime, p)
    if op == 'window':
        command = {'focus': 'focus-window', 'move': 'move-window', 'resize': 'resize-window',
                   'minimize': 'minimize', 'maximize': 'maximize', 'restore': 'restore'}[p['action']]
        return invoke(command, scope(p) + flags(p, ('x', 'y', 'width', 'height')))
    if op == 'launch_app':
        return launch(runtime, p, timeout)
    if op == 'close_app':
        from .images import _inventory
        _, target = _inventory(runtime, p)
        candidates = runtime.command('list-windows', ['--app=' + target['app_name']])['data']
        if len(candidates) != 1 or candidates[0]['id'] != target['id']:
            error = failure('close-app', 'AMBIGUOUS_TARGET', 'Native close addresses an application. Multiple matching windows exist; close a specific window through its observed close control instead.')
            error.envelope['error']['details'] = {'candidates': candidates}
            raise error
        return invoke('close-app', [target['app_name']])
    if op == 'open_system_surface':
        return invoke('open-system-surface', ['--surface=' + p['surface']], headed=True)
    if op == 'wait':
        def waited_snapshot(args):
            result = invoke('snapshot', args)
            result['command'] = 'wait'
            result['data'].pop('tree', None)
            result['data']['verification_scope'] = 'matched_selector' if not p.get('gone') else 'selector_absent'
            return result
        if p.get('selector'):
            wait_flag = '--wait-for-gone=' if p.get('gone') else '--wait-for='
            return waited_snapshot(scope(p) + ['--compact', wait_flag + p['selector'], f'--wait-timeout={timeout}'])
        if p.get('ref'):
            args = ['--element=' + ref(p['ref']), '--predicate=' + p.get('predicate', 'exists')]
            args += flags(p, ('value',))
        elif p.get('text'):
            return waited_snapshot(scope(p) + ['--compact', '--wait-for=:' + p['text'], f'--wait-timeout={timeout}'])
        elif p.get('window'):
            deadline = time.monotonic() + timeout / 1000
            while True:
                windows = invoke('list-windows', flags(p, ('app',)))['data']
                matches = [w for w in windows if p['window'].casefold() in w['title'].casefold()
                           and (not p.get('window_id') or w['id'] == p['window_id'])]
                if len(matches) > 1:
                    error = failure('wait', 'AMBIGUOUS_TARGET', 'Multiple windows match; specify window_id.')
                    error.envelope['error']['details'] = {'candidates': matches}
                    raise error
                if matches:
                    return {'version': '2.6', 'ok': True, 'command': 'wait', 'data': {
                        'window': matches[0], 'verification_scope': 'window_title', 'result': True}}
                if time.monotonic() >= deadline:
                    raise failure('wait', 'TIMEOUT', 'Target window did not appear before the deadline.')
                time.sleep(min(.1, max(0, deadline - time.monotonic())))
        else:
            raise failure(op, 'INVALID_ARGS', 'Wait requires ref, selector, text or window.')
        return invoke('wait', args + [f'--timeout={timeout}'])
    if op == 'clipboard_get':
        return invoke('clipboard-get', flags(p, ('format',)))
    if op == 'clipboard_clear':
        return invoke('clipboard-clear')
    if op == 'clipboard_set':
        if ('text' in p) == bool(p.get('image_path')):
            raise failure(op, 'INVALID_ARGS', 'Provide either text or image_path.')
        if p.get('image_path'):
            return invoke('clipboard-set', ['--image=' + str(Path(p['image_path']).resolve())])
        return invoke('clipboard-set', ['--stdin'], text=p['text'])
    if op == 'press_key':
        return invoke('press', [p['key']] + scope(p) + flags(p, ('force',)), headed=True)
    if op in {'click', 'scroll', 'pointer', 'drag'}:
        return pointer_operation(runtime, op, p, timeout, vision)
    target = ref(p['ref'])
    if op == 'set_state':
        command = {('checked', True): 'check', ('checked', False): 'uncheck',
                   ('expanded', True): 'expand', ('expanded', False): 'collapse'}[(p['state'], p['value'])]
    else:
        command = {'set_value': 'set-value', 'type_text': 'type', 'select': 'select',
                   'focus': 'focus', 'scroll_to': 'scroll-to'}[op]
    args = [target, f'--timeout-ms={timeout}']
    if op in {'set_value', 'type_text'}:
        return invoke(command, args + ['--stdin'], text=p['value' if op == 'set_value' else 'text'], headed=op == 'type_text' and p.get('physical', False))
    if op == 'select':
        args.insert(1, p['value'])
    return invoke(command, args, headed=op == 'focus')


def pointer_operation(runtime, op: str, p: dict, timeout: int, vision: bool) -> dict:
    from .images import point
    command, args, headed = '', [], True
    if op == 'drag':
        for end in ('from', 'to'):
            if p.get(end + '_ref'):
                if p.get(end + '_image_id') or any(end + '_' + key in p for key in ('x', 'y')):
                    raise failure(op, 'INVALID_ARGS', 'Choose one target form for each drag endpoint.')
                args.append('--' + end + '=' + ref(p[end + '_ref']))
            else:
                x, y = point(runtime, p.get(end + '_image_id'), p.get(end + '_x'), p.get(end + '_y'), vision=vision)
                args.append(f'--{end}-xy={x},{y}')
        command = 'drag'
    else:
        targeted = bool(p.get('ref'))
        if targeted and (p.get('image_id') or 'x' in p or 'y' in p):
            raise failure(op, 'INVALID_ARGS', 'Choose ref or image_id with x/y, not both.')
        physical = p.get('physical', False)
        if targeted:
            target = ref(p['ref'])
            if op == 'click':
                count, button = p.get('count', 1), p.get('button', 'left')
                if (count > 1 or button != 'left') and not physical:
                    raise failure(op, 'POLICY_DENIED', 'Multi-click and secondary buttons require physical=true.')
                if button == 'middle':
                    raise failure(op, 'INVALID_ARGS', 'Middle click requires image_id and coordinates.')
                command = 'right-click' if button == 'right' else {1: 'click', 2: 'double-click', 3: 'triple-click'}[count]
                headed, args = physical, [target, f'--timeout-ms={timeout}']
            elif op == 'scroll':
                command, headed = 'scroll', False
                args = [target, '--direction=' + p['direction'], '--amount=' + str(p.get('amount', 3)), f'--timeout-ms={timeout}']
            else:
                command, args = 'hover', [target, f'--timeout-ms={timeout}']
        else:
            x, y = point(runtime, p.get('image_id'), p.get('x'), p.get('y'), vision=vision)
            if op == 'click':
                if not physical:
                    raise failure(op, 'POLICY_DENIED', 'Coordinate clicks require physical=true.')
                command, args = 'mouse-click', [f'--xy={x},{y}', '--button=' + p.get('button', 'left'), '--count=' + str(p.get('count', 1))]
            elif op == 'scroll':
                direction, amount = p['direction'], p.get('amount', 3)
                axis = 'dy' if direction in {'up', 'down'} else 'dx'
                signed = amount if direction in {'up', 'right'} else -amount
                command, args = 'mouse-wheel', [f'--x={x}', f'--y={y}', f'--{axis}={signed}']
            else:
                command, args = ('hover' if p.get('action', 'hover') == 'hover' else 'mouse-move'), [f'--xy={x},{y}']
    return runtime.command(command, args, headed=headed, timeout_ms=timeout)


def launch(runtime, p: dict, timeout: int) -> dict:
    target = str(p['target']).strip()
    arguments = p.get('arguments', [])
    path = Path(target)
    if target.startswith(('https://', 'http://')) or path.is_dir() or (path.is_file() and path.suffix.lower() not in {'.exe', '.com'}):
        from .service import OpenComputerUseService
        # Retain ShellExecute's document/folder/URL support; observations use the new engine.
        service = OpenComputerUseService.__new__(OpenComputerUseService)
        runtime._verify_binary()
        runtime.check_cancel('launch')
        result = service._shell_execute(target, subprocess.list2cmdline(arguments))
        if result <= 32:
            raise failure('launch', 'ACTION_FAILED', f'Windows Shell refused launch ({result}).')
        runtime.images.clear()
        data = {
            'target': target, 'disposition': {'delivery': 'delivered_unverified', 'retry': 'unsafe'},
            'verification_scope': 'launch_request_only'}
        try:
            data['windows'] = runtime.command('list-windows')['data']
        except Exception:
            # Delivery is already known. A cancelled/failed observation cannot undo it.
            data['verification'] = 'Window inventory unavailable after launch; observe before another launch.'
        return {'version': '2.6', 'ok': True, 'command': 'launch', 'data': data}
    if not path.is_absolute():
        import winreg
        for hive in (winreg.HKEY_CURRENT_USER, winreg.HKEY_LOCAL_MACHINE):
            try:
                key_name = target if target.lower().endswith('.exe') else target + '.exe'
                with winreg.OpenKey(hive, 'Software\\Microsoft\\Windows\\CurrentVersion\\App Paths\\' + key_name) as key:
                    target = winreg.QueryValue(key, None).strip('"')
                break
            except FileNotFoundError:
                continue
    # Attaching to an existing process discards launch arguments upstream.
    # Refuse that path rather than report a request that was never delivered.
    return runtime.command('launch', [target, f'--timeout={timeout}', *(['--no-attach'] if arguments else []),
                                      *['--arg=' + arg for arg in arguments]], timeout_ms=timeout)
