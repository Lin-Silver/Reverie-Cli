"""Qualify bundled NVIDIA profiles against real text, tool and image requests."""
from __future__ import annotations

import argparse
import base64
from io import BytesIO
import json
from pathlib import Path
import sys
import time

from openai import OpenAI
from PIL import Image

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'ReverieCli-py'))
from reverie.config import ConfigManager
from reverie.nvidia import (
    build_nvidia_openai_options, get_nvidia_model_metadata, normalize_nvidia_config,
    resolve_nvidia_api_key, resolve_nvidia_sdk_base_url,
)


def qualify(model_id: str, config: dict) -> dict:
    cfg = normalize_nvidia_config({**config, 'selected_model_id': model_id, 'max_tokens': 4096})
    metadata = get_nvidia_model_metadata(model_id)
    if metadata is None:
        raise ValueError('Model must be in the bundled NVIDIA catalog')
    rows = []
    with OpenAI(api_key=resolve_nvidia_api_key(cfg), base_url=resolve_nvidia_sdk_base_url(cfg['api_url']),
                timeout=45, max_retries=0) as client:
        def request(stage, messages, **kwargs):
            started = time.monotonic()
            options = build_nvidia_openai_options(cfg, messages=messages)
            completion = client.chat.completions.create(model=model_id, messages=messages, **options, **kwargs)
            if kwargs.get('stream'):
                with completion:
                    completion = ''.join(chunk.choices[0].delta.content or '' for chunk in completion if chunk.choices)
            rows.append({'stage': stage, 'elapsed_ms': round((time.monotonic() - started) * 1000, 2)})
            return completion

        try:
            messages = [{'role': 'user', 'content': 'Call read_probe once, then report its exact numeric result.'}]
            tool = {'type': 'function', 'function': {'name': 'read_probe', 'description': 'Read the test value.',
                    'parameters': {'type': 'object', 'properties': {}, 'additionalProperties': False}}}
            result = request('tool_call', messages, tools=[tool],
                             tool_choice={'type': 'function', 'function': {'name': 'read_probe'}})
            reply = result.choices[0].message
            calls = reply.tool_calls or []
            if len(calls) != 1 or calls[0].function.name != 'read_probe' or json.loads(calls[0].function.arguments) != {}:
                raise ValueError('Expected exactly one valid probe call')
            assistant = {'role': 'assistant', 'content': reply.content, 'tool_calls': [calls[0].model_dump()]}
            if metadata.get('preserve_reasoning_history') and getattr(reply, 'reasoning_content', None):
                assistant['reasoning_content'] = reply.reasoning_content
            messages.extend([assistant, {'role': 'tool', 'tool_call_id': calls[0].id, 'content': '{"value":5017}'}])
            final = request('tool_result', messages)
            if '5017' not in (final.choices[0].message.content or ''):
                raise ValueError('Final answer did not use the observed probe value')
            if metadata['vision']:
                buffer = BytesIO()
                Image.new('RGB', (32, 32), 'red').save(buffer, 'PNG')
                url = 'data:image/png;base64,' + base64.b64encode(buffer.getvalue()).decode('ascii')
                visual = request('image', [{'role': 'user', 'content': [
                    {'type': 'text', 'text': 'Name the single color in English. One word only.'},
                    {'type': 'image_url', 'image_url': {'url': url}},
                ]}])
                if 'red' not in (visual.choices[0].message.content or '').lower():
                    raise ValueError('Image color was not identified')
            content = request('stream', [{'role': 'user', 'content': 'Reply exactly OK.'}], stream=True)
            if content.strip() != 'OK':
                raise ValueError('Stream did not produce the expected answer')
            return {'model': model_id, 'passed': True, 'checks': rows}
        except Exception as error:
            # Do not record response bodies, credentials, reasoning or image data.
            return {'model': model_id, 'passed': False, 'checks': rows,
                    'error': type(error).__name__, 'status': getattr(error, 'status_code', None)}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--models', nargs='+', default=[
        'mistralai/mistral-large-4-1t-a52b', 'nvidia/nemotron-3.5-bolt-e4b',
    ])
    args = parser.parse_args()
    output = args.output.resolve()
    if not output.is_relative_to(ROOT / '.runtime') or output.exists():
        parser.error('Use a fresh output directory within .runtime')
    cfg = ConfigManager(ROOT).load().nvidia
    if not resolve_nvidia_api_key(cfg):
        parser.error('Configure the NVIDIA source API key before live qualification')
    output.mkdir(parents=True)
    results = []
    for model_id in args.models:
        result = qualify(model_id, cfg)
        results.append(result)
        print(json.dumps(result), flush=True)
    (output / 'report.json').write_text(json.dumps(results, indent=2), encoding='utf-8')
    return 0 if all(row['passed'] for row in results) else 1


if __name__ == '__main__':
    raise SystemExit(main())
