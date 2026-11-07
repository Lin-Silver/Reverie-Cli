"""Store custom provider inventories under the executable's .reverie directory."""

from pathlib import Path
from copy import deepcopy
import json
import re
from typing import Any, Dict

from .security_utils import write_json_secure


class ProviderProfileError(ValueError):
    pass


class ProviderProfiles:
    def __init__(self, root: Path):
        self.root = root
        self._cache = {}
        self._loaded = {}

    @staticmethod
    def _signature(path: Path):
        stat = path.stat()
        return stat.st_mtime_ns, stat.st_size

    def changed(self) -> bool:
        for path, signature in self._loaded.items():
            try:
                if self._signature(path) != signature:
                    return True
            except OSError:
                return True
        return False

    def _read(self, path: Path) -> Dict[str, Any]:
        signature = self._signature(path)
        cached = self._cache.get(path)
        if cached and cached[0] == signature:
            return cached[1]
        data = json.loads(path.read_text(encoding='utf-8'))
        if not isinstance(data, dict) or not isinstance(data.get('models'), list):
            raise ProviderProfileError(f'Invalid provider profile: {path}')
        self._cache[path] = (signature, data)
        return data

    def hydrate(self, data: Dict[str, Any]) -> Dict[str, Any]:
        result = dict(data)
        if not isinstance(data.get('custom_providers'), dict):
            return result
        section = dict(data['custom_providers'])
        providers = section.get('providers') or []
        if not isinstance(providers, list):
            return result
        records = []
        self._loaded = {}
        for provider in providers:
            if not isinstance(provider, dict):
                continue
            record = dict(provider)
            filename = record.get('catalog_profile')
            if filename:
                if Path(filename).name != filename or not str(filename).endswith('.json'):
                    raise ProviderProfileError(f'Invalid provider profile filename: {filename}')
                path = self.root / filename
                try:
                    profile = self._read(path)
                    if profile.get('provider_id') != record.get('id'):
                        raise ProviderProfileError(f'Provider profile belongs to another provider: {path}')
                except (OSError, ValueError) as exc:
                    raise ProviderProfileError(f'Cannot load provider profile {path}: {exc}') from exc
                record['models'] = profile['models']
                record['model_context_limits'] = profile.get('model_context_limits', {})
                if 'connection_key' in profile:
                    record['model_catalog'] = {'connection_key': profile['connection_key'], 'models': profile['models']}
                self._loaded[path] = self._signature(path)
            records.append(record)
        section['providers'] = records
        result['custom_providers'] = section
        return result

    def store(self, data: Dict[str, Any]) -> Dict[str, Any]:
        result = dict(data)
        section = dict(data.get('custom_providers') or {})
        records = []
        used = set()
        self._loaded = {}
        for provider in section.get('providers') or []:
            record = dict(provider)
            name = re.sub(r'[<>:"/\\|?*\x00-\x1f]', '_', str(record['name'])).strip().rstrip('. ') or record['id']
            if re.match(r'^(CON|PRN|AUX|NUL|COM[1-9]|LPT[1-9])(?:\.|$)', name, re.I):
                name = '_' + name
            filename = name + '.json'
            path = self.root / filename
            if filename.casefold() in used or (path.exists() and self._read(path).get('provider_id') != record['id']):
                filename = f'{name}-{record["id"]}.json'
                path = self.root / filename
            used.add(filename.casefold())
            catalog = record.pop('model_catalog', None)
            models = record.pop('models', [])
            profile = {'provider_id': record['id'], 'name': record['name'],
                       'models': catalog['models'] if isinstance(catalog, dict) and 'models' in catalog else models,
                       'model_context_limits': record.pop('model_context_limits', {})}
            if isinstance(catalog, dict) and 'connection_key' in catalog:
                profile['connection_key'] = catalog['connection_key']
            if not path.exists() or self._read(path) != profile:
                write_json_secure(path, profile)
                self._cache[path] = (self._signature(path), deepcopy(profile))
            self._loaded[path] = self._signature(path)
            record['catalog_profile'] = filename
            records.append(record)
        section['providers'] = records
        result['custom_providers'] = section
        return result
