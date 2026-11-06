"""Hidden adapters for the old ten-tool contract; all execution uses the new runtime."""
from __future__ import annotations

import json
import time

from .operations import execute
from .runtime import failure
from .service import AppSnapshot, ElementRecord


class LegacyComputerUse:
    def __init__(self, runtime, *, vision=False):
        self.runtime = runtime
        self.vision = vision

    def _scope(self, app):
        wanted = str(app).lower().removesuffix('.exe')
        windows = self.runtime.command('list-windows')['data']
        matches = [w for w in windows if wanted in {str(w.get('pid')), str(w.get('app_name', '')).lower().removesuffix('.exe'), str(w.get('title', '')).lower()}]
        if not matches:
            matches = [w for w in windows if wanted and wanted in str(w.get('title', '')).lower()]
        if len(matches) != 1:
            raise failure('legacy', 'AMBIGUOUS_TARGET', 'Use computer_list_windows and an exact window_id; the legacy app name is not unique.')
        return matches[0]

    def list_apps(self):
        return [{'name': w['app_name'], 'pid': w['pid'], 'window_title': w['title'], 'status': 'running'}
                for w in self.runtime.command('list-windows')['data']]

    def get_app_state(self, app, *, show_full_text=False):
        window = self._scope(app)
        envelope = execute(self.runtime, 'computer_snapshot', {'window_id': window['id'], 'include_bounds': True})
        data, records, refs, lines = envelope['data'], {}, {}, []
        def visit(node, depth=0):
            if node.get('ref_id'):
                index = str(len(records))
                refs[index] = node['ref_id']
                record = ElementRecord(index, (), '', node.get('name', ''), node.get('role', ''), node.get('role', ''), '',
                                       str(node.get('value', '')), window['pid'], node.get('bounds'), node.get('available_actions', []))
                records[index] = record
                lines.append('  ' * depth + f"{index} {record.control_type} {record.name} [{node['ref_id']}]")
            for child in node.get('children', []):
                visit(child, depth + 1)
        visit(data['tree'])
        self.runtime.legacy[str(app)] = {'refs': refs, 'window_id': window['id'], 'elements': records}
        encoded, path, scale = '', '', 1.0
        if self.vision:
            from .images import capture
            import base64
            from pathlib import Path
            image = capture(self.runtime, {'window_id': window['id']})['data']
            self.runtime.legacy[str(app)]['image_id'] = image['image_id']
            self.runtime.images[image['image_id']]['model_visible'] = False
            path = image['path']
            encoded = base64.b64encode(Path(path).read_bytes()).decode('ascii')
            scale = image['scale_x']
        lines.insert(0, f"complete={data.get('complete')}; truncated={data.get('truncated', False)}; identity_unproven={data.get('identity_unproven', False)}")
        snapshot = AppSnapshot(str(app), window['pid'], window['app_name'], window['title'], window['bounds'], records,
                               path, encoded, lines, time.monotonic(), screenshot_scale=scale)
        snapshot.computer_envelope = envelope
        if self.vision:
            envelope['data'].update(image_id=image['image_id'], path=path)
        return snapshot

    def _state(self, app):
        state = self.runtime.legacy.get(str(app))
        if not state:
            raise failure('legacy', 'STALE_REF', 'Refresh get_app_state in this session before using legacy actions.')
        return state

    def _ref(self, app, index):
        target = self._state(app)['refs'].get(str(index))
        if not target:
            raise failure('legacy', 'STALE_REF', 'Legacy element index does not belong to this observation.')
        return target

    def _execute(self, name, args):
        return json.dumps(execute(self.runtime, name, args, vision=self.vision), ensure_ascii=False)

    def launch_app(self, target, *, arguments=''):
        from .windows_launch import split_arguments
        return self._execute('computer_launch_app', {'target': target, 'arguments': split_arguments(arguments)})

    def click(self, app, *, element_index=None, x=None, y=None, click_count=1, mouse_button='left', **kwargs):
        args = {'count': click_count, 'button': mouse_button, 'physical': True}
        if element_index is not None:
            args['ref'] = self._ref(app, element_index)
        else:
            args.update(image_id=self._state(app).get('image_id'), x=x, y=y)
        return self._execute('computer_click', args)

    def drag(self, app, from_x, from_y, to_x, to_y):
        image = self._state(app).get('image_id')
        return self._execute('computer_drag', dict(from_image_id=image, to_image_id=image, from_x=from_x, from_y=from_y, to_x=to_x, to_y=to_y))

    def perform_secondary_action(self, app, element_index, action):
        command = {'Invoke': 'click', 'Toggle': 'toggle', 'Select': 'select', 'Expand': 'expand', 'Collapse': 'collapse', 'ScrollIntoView': 'scroll-to'}[action]
        args = [self._ref(app, element_index)]
        if action == 'Select':
            args.append(self._state(app)['elements'][str(element_index)].name)
        return json.dumps(self.runtime.command(command, args), ensure_ascii=False)

    def scroll(self, app, element_index, direction, pages=1):
        return self._execute('computer_scroll', {'ref': self._ref(app, element_index), 'direction': direction, 'amount': max(1, round(abs(float(pages or 1))))})

    def set_value(self, app, element_index, value):
        return self._execute('computer_set_value', {'ref': self._ref(app, element_index), 'value': value})

    def press_key(self, app, key):
        return self._execute('computer_press_key', {'window_id': self._state(app)['window_id'], 'key': key})

    def type_text(self, app, text):
        state = self._state(app)
        found = execute(self.runtime, 'computer_snapshot', {'window_id': state['window_id']})['data']
        focused = []
        def visit(node):
            if 'focused' in node.get('states', []) and node.get('ref_id'):
                focused.append(node)
            for child in node.get('children', []):
                visit(child)
        visit(found['tree'])
        if len(focused) != 1:
            raise failure('type', 'AMBIGUOUS_TARGET', 'Use computer_type_text with the exact editable ref; focused target could not be proven.')
        return self._execute('computer_type_text', {'ref': focused[0]['ref_id'], 'text': text})
