"""Keep desktop delivery and observation limits intact when reducing context."""
from __future__ import annotations

import json

from .runtime import COMMANDS

LEGACY_TOOLS = frozenset('list_apps launch_app get_app_state click drag scroll type_text press_key set_value perform_secondary_action'.split())


def diagnostic_result(text) -> str | None:
    if text is None:
        return None
    raw = str(text)
    try:
        envelope = json.loads(raw.removeprefix('Error: '))
        payload = envelope.get('data') if envelope.get('ok') else envelope.get('error')
        metadata = {key: payload[key] for key in ('code', 'disposition', 'complete', 'truncated')
                    if isinstance(payload, dict) and key in payload}
        return json.dumps(metadata, ensure_ascii=False)
    except (ValueError, AttributeError):
        return 'Computer Use result; content remains in the conversation.'


def _bounded(value, depth=0):
    if isinstance(value, str):
        return value[:400] + (' [description truncated]' if len(value) > 400 else '')
    if depth > 4:
        return '[nested description omitted]'
    if isinstance(value, list):
        return [_bounded(item, depth + 1) for item in value[:8]]
    if isinstance(value, dict):
        return {key: _bounded(item, depth + 1) for key, item in list(value.items())[:16]}
    return value


def compact_envelope(envelope: dict, *, truncated: bool = False) -> dict:
    key = 'data' if envelope.get('ok') else 'error'
    payload = envelope.get(key, {})
    fields = ('code', 'message', 'disposition', 'delivery', 'retry', 'target', 'window',
              'ref', 'snapshot_id', 'image_id', 'verification_scope', 'verification',
              'complete', 'truncated', 'identity_unproven', 'after_action', 'steps',
              'property', 'result', 'total_matches')
    data = {name: _bounded(payload[name]) for name in fields if isinstance(payload, dict) and name in payload}
    if truncated:
        data.update(original_complete=data.get('complete'), complete=False, truncated=True,
                    reverie_truncated=True, guidance='Use computer_find or a local computer_snapshot root to observe the needed controls.')
    return {'version': envelope['version'], 'ok': envelope['ok'], 'command': envelope.get('command'), key: data}


def desktop_memory(text) -> str | None:
    """Recognize an envelope even after a tool-name or Error prefix."""
    raw = str(text or '')
    start = raw.find('{')
    if start < 0:
        return None
    try:
        envelope, _ = json.JSONDecoder().raw_decode(raw[start:])
        if envelope.get('version') != '2.6' or envelope.get('command') not in COMMANDS:
            return None
        compact = compact_envelope(envelope)
    except (ValueError, TypeError, AttributeError, KeyError):
        return None
    return 'Desktop history (observe again before acting; never replay uncertain delivery): ' + json.dumps(compact, ensure_ascii=False, separators=(',', ':'))
