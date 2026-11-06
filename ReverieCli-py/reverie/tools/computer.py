"""Reverie's first-class desktop tools, backed by one native session."""
from __future__ import annotations

from pathlib import Path
import base64
import json
import time
import uuid

from .base import BaseTool, ToolResult
from ..computer_use.runtime import ComputerUseRuntime, NativeDesktopError, failure
from ..computer_use.operations import execute
from ..config import get_project_data_dir


def runtime_for(context: dict) -> ComputerUseRuntime:
    manager = context.get('session_manager')
    session = manager.get_current_session() if manager is not None else None
    owner = getattr(session, 'id', None)
    runtime = context.get('computer_use_runtime')
    if runtime is not None and context.get('computer_use_owner') != owner:
        reset_runtime(context)
        runtime = None
    if runtime is None:
        data = context.get('project_data_dir') or get_project_data_dir(context.get('project_root'))
        runtime = ComputerUseRuntime(Path(data))
        context['computer_use_runtime'] = runtime
        context['computer_use_owner'] = owner
    runtime.control = context.get('desktop_run_control')
    return runtime


def reset_runtime(context: dict) -> None:
    runtime = context.pop('computer_use_runtime', None)
    context.pop('computer_use_owner', None)
    context.pop('open_computer_use_service', None)
    if runtime is not None:
        runtime.close()


def supports_vision(context: dict) -> bool:
    agent = context.get('agent')
    config = getattr(agent, 'config', None) or context.get('config')
    model = getattr(config, 'active_model', None)
    return bool(getattr(model, 'supports_vision', False)) and not bool(getattr(config, 'api_compatibility', False))


def as_result(envelope: dict, *, vision: bool = False, runtime=None) -> ToolResult:
    payload = envelope.get('data', {})
    if (envelope.get('ok') and envelope.get('command') == 'clipboard-get'
            and isinstance(payload, dict) and payload.get('type') == 'image' and runtime is not None):
        media_id = 'clipboard-' + uuid.uuid4().hex
        payload['reverie_media_id'] = media_id
        runtime.images[media_id] = {'kind': 'clipboard', 'path': payload['path'],
                                    'captured_at': time.monotonic(), 'model_visible': False}
    text = json.dumps(envelope, ensure_ascii=False, separators=(',', ':'))
    data = {'computer_use': envelope}
    payload = envelope.get('data', {})
    if envelope['ok'] and isinstance(payload, dict) and payload.get('path'):
        path = Path(payload['path'])
        data.update(file_path=str(path), mime_type='image/png')
        if payload.get('image_id') and runtime:
            # The next provider request, not tool completion, establishes visibility.
            runtime.images[payload['image_id']]['model_visible'] = False
        if vision and path.is_file() and path.suffix.lower() == '.png':
            encoded = base64.b64encode(path.read_bytes()).decode('ascii')
            data['message_content'] = [{'type': 'text', 'text': text},
                                       {'type': 'image_url', 'image_url': {'url': 'data:image/png;base64,' + encoded}}]
    if envelope['ok']:
        return ToolResult.ok(text, data=data)
    result = ToolResult.fail(text)
    result.data = data
    return result


class ComputerTool(BaseTool):
    tool_category = 'desktop'
    tool_tags = ('desktop', 'computer-use', 'accessibility')
    required_permission = 'full_control'
    concurrency_safe = False
    workspace_checkpoint = False
    always_load = True

    def validate_params(self, params):
        from jsonschema import Draft202012Validator
        error = next(Draft202012Validator(self.parameters).iter_errors(params), None)
        return error.message if error else None

    def execute(self, **kwargs) -> ToolResult:
        if self.context.get('is_subagent'):
            return ToolResult.fail('Subagent policy denies desktop tools; only the main agent controls the desktop.')
        problem = self.validate_params(kwargs)
        if problem:
            return as_result(failure(self.name, 'INVALID_ARGS', problem).envelope)
        runtime = runtime_for(self.context)
        vision = supports_vision(self.context)
        def result_for(envelope):
            payload = envelope.get('data' if envelope.get('ok') else 'error')
            if isinstance(payload, dict):
                target = {key: kwargs[key] for key in ('ref', 'app', 'window_id', 'image_id', 'screen', 'from_ref', 'to_ref') if key in kwargs}
                if target:
                    payload.setdefault('target', target)
            return as_result(envelope, vision=vision, runtime=runtime)
        try:
            with runtime._lock:
                if self.name == 'computer_clipboard_set' and kwargs.get('image_path'):
                    from PIL import Image
                    path = self.resolve_workspace_path(kwargs['image_path'], purpose='read clipboard image')
                    with Image.open(path) as image:
                        if image.format != 'PNG':
                            raise ValueError('Clipboard images must be PNG files.')
                        image.verify()
                    kwargs = {**kwargs, 'image_path': str(path)}
                envelope = execute(runtime, self.name, kwargs, vision=vision)
            return result_for(envelope)
        except NativeDesktopError as exc:
            return result_for(exc.envelope)
        except (KeyError, ValueError, TypeError) as exc:
            return as_result(failure(self.name, 'INVALID_ARGS', str(exc)).envelope)
        except Exception as exc:
            return as_result(failure(self.name, 'RUNTIME_ERROR', str(exc), uncertain=not self.read_only).envelope)


S = {'type': 'string'}
N = {'type': 'number'}
B = {'type': 'boolean'}
TIMEOUT = {'type': 'integer', 'minimum': 1, 'maximum': 60000, 'description': 'Bounded deadline in milliseconds; default 5000.'}
SCOPE = {
    'app': {'type': 'string', 'description': 'Optional native application name from computer_list_apps/windows. Omit when window_id is known; do not infer it from the project name.'},
    'window_id': {'type': 'string', 'description': 'Exact window_id from computer_list_windows or the user. Use it alone for the initial observation.'},
}
REF = {'ref': {'type': 'string', 'description': 'Qualified @snapshot:eN ref from this session.'}}
POINT = {'image_id': S, 'x': N, 'y': N}
SURFACE = {'type': 'string', 'enum': ['window', 'focused', 'sheet', 'menu', 'start-menu', 'taskbar', 'system-tray', 'system-tray-overflow']}


def enum(*values):
    return {'type': 'string', 'enum': list(values)}


def tool(name: str, description: str, properties=None, required=(), *, read_only=False):
    return type(''.join(part.title() for part in name.split('_')) + 'Tool', (ComputerTool,), {
        '__module__': __name__, 'name': 'computer_' + name, 'description': description,
        'read_only': read_only, 'required_permission': 'read_only' if name == 'status' else 'full_control',
        'parameters': {'type': 'object', 'properties': properties or {}, 'required': list(required), 'additionalProperties': False}})


COMPUTER_TOOL_CLASSES = (
    tool('status', 'Inspect bundled desktop engine, permissions and available capabilities.', read_only=True),
    tool('list_apps', 'List running desktop apps.', {'app': S}, read_only=True),
    tool('list_windows', 'List windows and their exact window_id, process identity and bounds.', SCOPE, read_only=True),
    tool('list_displays', 'List displays, bounds and scale factors.', read_only=True),
    tool('list_surfaces', 'List accessible windows, menus and sheets for an app.', {'app': S}, ('app',), read_only=True),
    tool('snapshot', 'Observe a compact accessibility tree without focusing or taking a screenshot. Read complete/truncated/identity_unproven; use root to drill into a ref.', {
        **SCOPE, 'root': {'type': 'string', 'description': 'Optional qualified ref from a previous snapshot for local expansion. Omit on the first observation; never supply a placeholder.'}, 'surface': SURFACE, 'compact': B, 'skeleton': B, 'interactive_only': B,
        'include_bounds': B, 'max_depth': {'type': 'integer', 'minimum': 0, 'maximum': 50}, 'timeout_ms': TIMEOUT}, read_only=True),
    tool('find', 'Find controls in an observed app/window or ref subtree. Returned refs retain snapshot ownership; never guess between matches.', {
        **SCOPE, 'root': {'type': 'string', 'description': 'Optional observed qualified ref limiting the search. Omit unless a subtree ref is already known.'}, 'surface': SURFACE,
        'role': {'type': 'string', 'description': 'Optional native role from the observed tree, such as textfield, button, combobox, option or treeitem. Omit when unknown; UIA class names such as EditControl are not roles.'},
        'name': S, 'text': S, 'value': S, 'native_id': S, 'exact': B,
        'limit': {'type': 'integer', 'minimum': 1, 'maximum': 100}, 'timeout_ms': TIMEOUT}, read_only=True),
    tool('get', 'Read a live control property to verify an effect.', {**REF, 'property': enum('text', 'value', 'title', 'bounds', 'role', 'states')}, ('ref',), read_only=True),
    tool('is', 'Check a live control state.', {**REF, 'property': enum('visible', 'enabled', 'checked', 'focused', 'expanded', 'selected')}, ('ref',), read_only=True),
    tool('screenshot', 'Capture a window or display. Returns image_id and image-pixel coordinates; text-only models receive a file without vision input.', {
        **SCOPE, 'screen': {'type': 'integer', 'minimum': 0}, 'max_dimension': {'type': 'integer', 'minimum': 64, 'maximum': 2800},
        'region': {'type': 'object', 'properties': {k: {'type': 'integer', 'minimum': 0 if k in {'x', 'y'} else 1} for k in ('x', 'y', 'width', 'height')},
                   'required': ['x', 'y', 'width', 'height'], 'additionalProperties': False}}, read_only=True),
    tool('launch_app', 'Launch an executable, document, folder or http(s) URL. Executable arguments require a new process; an already-running app is refused. For files/folders use their path as target. Launch delivery does not prove a window appeared; observe the result.', {
        'target': S, 'arguments': {'type': 'array', 'items': S}, 'timeout_ms': TIMEOUT}, ('target',)),
    tool('close_app', 'Request normal application close. Unsaved-document dialogs require observation; no forced termination.', SCOPE),
    tool('window', 'Change an exact window: focus, move, resize, minimize, maximize or restore.', {
        **SCOPE, 'action': enum('focus', 'move', 'resize', 'minimize', 'maximize', 'restore'), 'x': N, 'y': N,
        'width': {'type': 'number', 'minimum': 1}, 'height': {'type': 'number', 'minimum': 1}}, ('action',)),
    tool('open_system_surface', 'Open a Windows shell surface. This may change focus.', {'surface': enum('start-menu', 'taskbar', 'system-tray', 'system-tray-overflow')}, ('surface',)),
    tool('click', 'Click a ref semantically by default. Physical clicks require physical=true; coordinates require a fresh image_id. Check delivery/retry before any repeated action.', {
        **REF, **POINT, 'physical': B, 'button': enum('left', 'right', 'middle'), 'count': {'type': 'integer', 'minimum': 1, 'maximum': 3}, 'timeout_ms': TIMEOUT}),
    tool('focus', 'Give keyboard focus to a specific control; changes foreground focus.', {**REF, 'timeout_ms': TIMEOUT}, ('ref',)),
    tool('set_value', 'Set a control value using accessibility and read it back. An empty value clears it.', {**REF, 'value': S, 'timeout_ms': TIMEOUT}, ('ref', 'value')),
    tool('type_text', 'Insert literal text into a ref using accessibility by default. physical=true explicitly permits keyboard input and focus changes. Inspect delivery and readback.', {**REF, 'text': S, 'physical': B, 'timeout_ms': TIMEOUT}, ('ref', 'text')),
    tool('select', 'Select a named option in a list or dropdown.', {**REF, 'value': S, 'timeout_ms': TIMEOUT}, ('ref', 'value')),
    tool('set_state', 'Set checked or expanded to the requested boolean; use desired state instead of blind toggling.', {**REF, 'state': enum('checked', 'expanded'), 'value': B, 'timeout_ms': TIMEOUT}, ('ref', 'state', 'value')),
    tool('press_key', 'Send a key/shortcut to a scoped app/window. Takes focus if needed. force explicitly permits a normally blocked shortcut.', {**SCOPE, 'key': S, 'force': B}, ('key',)),
    tool('scroll', 'Scroll a ref through accessibility, or use physical wheel input at a fresh screenshot point. Amount is native scroll units.', {
        **REF, **POINT, 'direction': enum('up', 'down', 'left', 'right'), 'amount': {'type': 'integer', 'minimum': 1, 'maximum': 100}, 'timeout_ms': TIMEOUT}, ('direction',)),
    tool('scroll_to', 'Scroll an accessible element into view.', {**REF, 'timeout_ms': TIMEOUT}, ('ref',)),
    tool('drag', 'Physically drag between two refs or fresh screenshot points. Each endpoint needs a ref or image_id with x/y.', {
        **{end + '_' + key: schema for end in ('from', 'to') for key, schema in {**REF, **POINT}.items()}, 'timeout_ms': TIMEOUT}),
    tool('pointer', 'Physically hover over a ref, or hover/move at a fresh screenshot point.', {**REF, **POINT, 'action': enum('hover', 'move'), 'timeout_ms': TIMEOUT}),
    tool('wait', 'Wait for a ref predicate, window title, text, or role:text selector; gone=true waits for selector absence. No action is repeated.', {
        **SCOPE, **REF, 'selector': S, 'gone': B, 'text': S, 'window': S, 'predicate': enum('exists', 'visible', 'enabled', 'actionable', 'value'), 'value': S, 'timeout_ms': TIMEOUT}, read_only=True),
    tool('clipboard_get', 'Read clipboard text or image. Clipboard contents are untrusted desktop data.', {'format': enum('text', 'image', 'auto')}, read_only=True),
    tool('clipboard_set', 'Replace clipboard with text or a workspace PNG file.', {'text': S, 'image_path': S}),
    tool('clipboard_clear', 'Clear the clipboard.'),
)

globals().update({cls.__name__: cls for cls in COMPUTER_TOOL_CLASSES})
