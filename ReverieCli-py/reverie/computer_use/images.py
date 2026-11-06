"""Screenshots carry their own target identity and image-to-desktop transform."""
from __future__ import annotations

import base64
import io
import math
import time
import uuid
import sys

from .runtime import failure


def _inventory(runtime, p: dict) -> tuple[str, dict]:
    if 'screen' in p:
        if p.get('app') or p.get('window_id'):
            raise failure('screenshot', 'INVALID_ARGS', 'Choose a display or an app/window.')
        displays = runtime.command('list-displays')['data']
        index = p['screen']
        if not isinstance(index, int) or not 0 <= index < len(displays):
            raise failure('screenshot', 'INVALID_ARGS', 'Display index is not in the current inventory.')
        return 'display', displays[index]
    args = ['--app=' + p['app']] if p.get('app') else []
    windows = runtime.command('list-windows', args)['data']
    matches = [w for w in windows if not p.get('window_id') or w['id'] == p['window_id']]
    if len(matches) != 1 or not (p.get('app') or p.get('window_id')):
        err = failure('screenshot', 'AMBIGUOUS_TARGET', 'Select one window_id from list-windows.')
        err.envelope['error']['details'] = {'candidates': matches}
        raise err
    if not matches[0].get('process_instance'):
        raise failure('screenshot', 'STALE_REF', 'The target process identity is unavailable; refresh the window inventory.')
    return 'window', matches[0]


def _identity(kind: str, target: dict) -> tuple:
    return (target.get('id'), target.get('bounds'),
            target.get('pid') if kind == 'window' else target.get('scale'),
            target.get('process_instance') if kind == 'window' else None)


def frame_bounds(window_id: str) -> dict | None:
    """WGC captures the visible DWM frame, excluding invisible resize borders."""
    if sys.platform != 'win32':
        return None
    import ctypes
    from ctypes import wintypes
    bounds = wintypes.RECT()
    dwm = ctypes.WinDLL('dwmapi')
    dwm.DwmGetWindowAttribute.argtypes = [wintypes.HWND, wintypes.DWORD, ctypes.c_void_p, wintypes.DWORD]
    dwm.DwmGetWindowAttribute.restype = ctypes.c_long
    if dwm.DwmGetWindowAttribute(int(window_id.removeprefix('w-')), 9, ctypes.byref(bounds), ctypes.sizeof(bounds)):
        return None
    return {'x': bounds.left, 'y': bounds.top, 'width': bounds.right-bounds.left, 'height': bounds.bottom-bounds.top}


def capture(runtime, parameters: dict) -> dict:
    from PIL import Image
    kind, target = _inventory(runtime, parameters)
    args = [f"--screen={parameters['screen']}"] if kind == 'display' else ['--window-id=' + target['id']]
    data = runtime.command('screenshot', args)['data']
    image = Image.open(io.BytesIO(base64.b64decode(data['data'], validate=True))).convert('RGB')
    original_width, original_height = image.size
    _, after = _inventory(runtime, parameters)
    if _identity(kind, target) != _identity(kind, after):
        raise failure('screenshot', 'STALE_IMAGE', 'Target moved or changed while the screenshot was captured; capture again.')
    capture_bounds = frame_bounds(target['id']) if kind == 'window' else target['bounds']
    if not capture_bounds or (capture_bounds['width'], capture_bounds['height']) != image.size:
        candidate = target['bounds']
        capture_bounds = candidate if (candidate['width'], candidate['height']) == image.size else None
    region = parameters.get('region') or {'x': 0, 'y': 0, 'width': image.width, 'height': image.height}
    x, y, width, height = (region[k] for k in ('x', 'y', 'width', 'height'))
    if not all(isinstance(n, int) and not isinstance(n, bool) for n in (x, y, width, height)) or min(x, y) < 0 or min(width, height) <= 0 or x + width > image.width or y + height > image.height:
        raise failure('screenshot', 'INVALID_ARGS', 'Crop must be inside the original screenshot pixel bounds.')
    image = image.crop((x, y, x + width, y + height))
    maximum = parameters.get('max_dimension', 1400)
    if not isinstance(maximum, int) or not 64 <= maximum <= 2800:
        raise failure('screenshot', 'INVALID_ARGS', 'max_dimension must be between 64 and 2800.')
    image.thumbnail((maximum, maximum))
    image_id = 'img-' + uuid.uuid4().hex
    directory = runtime.root / 'observations'
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / (image_id + '.png')
    image.save(path, format='PNG')
    record = {'kind': kind, 'target': target, 'scope': dict(parameters), 'captured_at': time.monotonic(),
              'width': image.width, 'height': image.height, 'region': region,
              'original_width': original_width, 'original_height': original_height,
              'path': str(path), 'model_visible': True, 'capture_bounds': capture_bounds}
    runtime.images[image_id] = record
    while len(runtime.images) > 64:
        runtime.images.pop(next(iter(runtime.images)))
    return {'version': '2.6', 'ok': True, 'command': 'screenshot', 'data': {
        'image_id': image_id, 'width': image.width, 'height': image.height, 'path': str(path),
        'target': target, 'region': region, 'coordinate_space': 'returned_image_pixels',
        'capture_bounds': capture_bounds, 'coordinate_available': capture_bounds is not None,
        'scale_x': image.width / width, 'scale_y': image.height / height}}


def point(runtime, image_id: str, x, y, *, vision: bool = True) -> tuple[int, int]:
    if not vision:
        raise failure('pointer', 'VISION_REQUIRED', 'Coordinate actions require a vision-capable model that received this image. Use accessibility refs.')
    record = runtime.images.get(image_id)
    if record is None or time.monotonic() - record['captured_at'] > 120 or not record.get('model_visible', True):
        raise failure('pointer', 'STALE_IMAGE', 'Capture a fresh screenshot in this session before coordinate input.')
    if record['kind'] not in {'window', 'display'}:
        raise failure('pointer', 'INVALID_ARGS', 'Only desktop screenshots define coordinates; clipboard images do not.')
    if any(isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(v) for v in (x, y)) or not (0 <= x < record['width'] and 0 <= y < record['height']):
        raise failure('pointer', 'INVALID_ARGS', 'Coordinates must be finite and inside the returned image.')
    kind, current = _inventory(runtime, record['scope'])
    if _identity(kind, current) != _identity(record['kind'], record['target']):
        raise failure('pointer', 'STALE_IMAGE', 'Target identity, position or size changed. Capture again before acting.')
    if kind == 'window' and current.get('is_focused') is False:
        raise failure('pointer', 'TARGET_NOT_FOCUSED', 'Focus the target window, then capture it again before coordinate input.')
    bounds, crop = record.get('capture_bounds'), record['region']
    if bounds is None:
        raise failure('pointer', 'GEOMETRY_UNPROVEN', 'The image origin cannot be proven for this capture; use accessibility refs.')
    current_frame = frame_bounds(current['id']) if kind == 'window' else current['bounds']
    if current_frame is not None and current_frame != bounds:
        raise failure('pointer', 'STALE_IMAGE', 'The visible window frame changed; capture again.')
    px = bounds['x'] + (crop['x'] + x * crop['width'] / record['width']) * bounds['width'] / record['original_width']
    py = bounds['y'] + (crop['y'] + y * crop['height'] / record['height']) * bounds['height'] / record['original_height']
    point_x, point_y = math.floor(px), math.floor(py)
    if kind == 'window' and not receives_point(current['id'], point_x, point_y):
        raise failure('pointer', 'TARGET_OCCLUDED', 'Another window covers this screenshot point. Observe the target again before physical input.')
    return point_x, point_y


def receives_point(window_id: str, x: int, y: int) -> bool:
    """Reject an occluding topmost window even when the intended window has focus."""
    import ctypes
    from ctypes import wintypes
    user32 = ctypes.WinDLL('user32', use_last_error=True)
    user32.WindowFromPoint.argtypes = [wintypes.POINT]
    user32.WindowFromPoint.restype = wintypes.HWND
    user32.GetAncestor.argtypes = [wintypes.HWND, wintypes.UINT]
    user32.GetAncestor.restype = wintypes.HWND
    handle = user32.WindowFromPoint(wintypes.POINT(x, y))
    root = user32.GetAncestor(handle, 2) if handle else None  # GA_ROOT
    return bool(root) and str(window_id) == 'w-' + str(root)
