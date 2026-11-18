"""Store each provider's settings and inventory beside the owning config."""

from contextlib import contextmanager
from copy import deepcopy
import errno
import json
import logging
import os
from pathlib import Path
import re
import time
from typing import Any, Dict

from .config import EXTERNAL_MODEL_SOURCES, MODEL_SOURCE_DISPLAY_NAMES
from .security_utils import write_json_secure


_INVALID_FILENAME_CHAR = re.compile(r'[<>:"/\\|?*\x00-\x1f]')
_RESERVED_FILENAME = re.compile(r'^(CON|PRN|AUX|NUL|COM[1-9¹²³]|LPT[1-9¹²³])(?:\.|$)', re.I)
_FIXED_NAMES = {source: f'{MODEL_SOURCE_DISPLAY_NAMES.get(source, "Pollinations")}.json'
                for source in (*EXTERNAL_MODEL_SOURCES, 'pollinations')}
_FIXED_NAMES['standard'] = 'Manual Models.json'
_FIXED_NAMES['opencode'] = 'OpenCode.json'


class ProviderProfileError(ValueError):
    pass


class ProviderProfiles:
    def __init__(self, legacy_root: Path):
        self.legacy_root = legacy_root
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

    @staticmethod
    @contextmanager
    def write_lock(config_path: Path):
        config_path.parent.mkdir(parents=True, exist_ok=True)
        with config_path.with_name('.config.lock').open('a+b') as handle:
            if os.name == 'nt':
                import msvcrt

                deadline = time.monotonic() + 5
                while True:
                    try:
                        msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
                        break
                    except OSError as exc:
                        if exc.errno != errno.EACCES or time.monotonic() >= deadline:
                            raise
                        time.sleep(0.01)
            else:
                import fcntl

                fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
            yield  # Closing the handle releases the lock on both platforms.

    @staticmethod
    def _path(root: Path, filename: str) -> Path:
        if (not isinstance(filename, str) or not filename.endswith('.json') or filename == '.json'
                or _INVALID_FILENAME_CHAR.search(filename) or _RESERVED_FILENAME.match(filename)):
            raise ProviderProfileError(f'Invalid provider profile filename: {filename!r}')
        return root / filename

    def _read(self, path: Path):
        signature = self._signature(path)
        cached = self._cache.get(path)
        if cached and cached[0] == signature:
            return cached
        data = json.loads(path.read_text(encoding='utf-8-sig'))
        if not isinstance(data, dict):
            raise ProviderProfileError(f'Invalid provider profile: {path}')
        self._cache[path] = (signature, data)
        return signature, data

    def _read_profile(self, path: Path, provider_id: str, loaded: dict, *, inventory: bool = False) -> dict:
        try:
            signature, data = self._read(path)
            if (not provider_id or data.get('provider_id') != provider_id or data.get('id', provider_id) != provider_id
                    or (inventory and not isinstance(data.get('models'), list))):
                raise ProviderProfileError('Provider identity or inventory does not match the reference')
        except (OSError, ValueError) as exc:
            raise ProviderProfileError(f'Cannot load provider profile {path}: {exc}') from exc
        loaded[path] = signature
        # Config records are mutable. Keep the cached on-disk data independent.
        return deepcopy(data)

    def hydrate(self, data: Dict[str, Any], config_path: Path, *, track: bool = False) -> Dict[str, Any]:
        result = dict(data)
        root = config_path.parent / 'Providers'
        loaded: dict = {}
        profiles = result.pop('provider_files', {})
        if not isinstance(profiles, dict):
            raise ProviderProfileError(f'Invalid provider file index in {config_path}')
        for source, filename in profiles.items():
            if source not in _FIXED_NAMES:
                raise ProviderProfileError(f'Unknown built-in provider profile: {source}')
            stored = self._read_profile(self._path(root, filename), source, loaded, inventory=source == 'standard')
            if source == 'standard':
                result['models'] = stored['models']
                continue
            if 'chat' in stored:
                result[source] = stored['chat']
            for kind in ('text_to_image', 'text_to_video'):
                if kind in stored:
                    result[kind] = {**result.get(kind, {}), source: stored[kind]}

        section = result.get('custom_providers')
        if isinstance(section, dict) and isinstance(section.get('providers'), list):
            records = []
            for provider in section['providers']:
                if not isinstance(provider, dict):
                    continue
                record = dict(provider)
                filename = record.pop('profile', None)
                legacy_filename = record.pop('catalog_profile', None)
                if filename:
                    stored = self._read_profile(self._path(root, filename), record.get('id'), loaded, inventory=True)
                    stored.pop('provider_id')
                    record.update(stored)
                elif legacy_filename:
                    stored = self._read_profile(self._path(self.legacy_root, legacy_filename), record.get('id'), loaded, inventory=True)
                    record['models'] = stored['models']
                    record['model_context_limits'] = stored.get('model_context_limits', {})
                    if 'connection_key' in stored:
                        record['model_catalog'] = {'connection_key': stored['connection_key'], 'models': stored['models']}
                models = record.get('models')
                catalog = record.get('model_catalog')
                if isinstance(catalog, dict) and 'models' not in catalog and isinstance(models, list):
                    record['model_catalog'] = {**catalog, 'models': models}
                records.append(record)
            result['custom_providers'] = {**section, 'providers': records}
        if track:
            self._loaded = loaded
        return result

    def _write(self, path: Path, profile: dict):
        try:
            signature, old = self._read(path)
        except FileNotFoundError:
            old = None
        if old != profile:
            if old is not None and old.get('provider_id') != profile['provider_id']:
                raise ProviderProfileError(f'Provider profile belongs to another provider: {path}')
            write_json_secure(path, profile, compact=True)
            signature = self._signature(path)
            self._cache[path] = (signature, deepcopy(profile))
        return signature

    @staticmethod
    def _custom_profile(provider: dict) -> dict:
        record = {**provider, 'provider_id': provider['id']}
        record.pop('catalog_profile', None)
        catalog = record.get('model_catalog')
        if isinstance(catalog, dict) and isinstance(catalog.get('models'), list):
            record['models'] = catalog['models']
            record['model_catalog'] = {key: value for key, value in catalog.items() if key != 'models'}
        return record

    def save_model_selection(self, data: dict, config_path: Path, config) -> bool:
        profiles = data.get('provider_files')
        if not isinstance(profiles, dict):
            return False

        root = config_path.parent / 'Providers'
        source = config.active_model_source
        changed_profile = {}
        updates = {'active_model_source': source, 'active_model_index': config.active_model_index}
        if source == 'custom':
            section = data['custom_providers']
            provider_id = config.custom_providers['active_provider_id']
            ref = next((item for item in section['providers'] if item['id'] == provider_id), None)
            if ref is None or 'profile' not in ref:
                return False
            record = next(item for item in config.custom_providers['providers'] if item['id'] == provider_id)
            path = self._path(root, ref['profile'])
            changed_profile[path] = self._write(path, self._custom_profile(record))
            updates['custom_providers'] = {**section, 'active_provider_id': provider_id}
        elif source != 'standard':
            if source not in profiles:
                return False
            path = self._path(root, profiles[source])
            _, existing = self._read(path)
            changed_profile[path] = self._write(path, {**existing, 'chat': getattr(config, source)})

        if any(data.get(key) != value for key, value in updates.items()):
            write_json_secure(config_path, {**data, **updates})
        self._loaded.update(changed_profile)
        return True

    def store(self, data: Dict[str, Any], config_path: Path, *, track: bool = True) -> None:
        with self.write_lock(config_path):
            try:
                previous = json.loads(config_path.read_text(encoding='utf-8-sig'))
            except (FileNotFoundError, ValueError):
                previous = {}
            self._store(data, config_path, previous, track=track)

    def _store(self, data: dict, config_path: Path, previous: dict, *, track: bool) -> None:
        root = config_path.parent / 'Providers'
        result = dict(data)
        loaded = {}
        profiles = {}
        for kind in ('text_to_image', 'text_to_video'):
            if isinstance(result.get(kind), dict):
                result[kind] = dict(result[kind])
        for source, filename in _FIXED_NAMES.items():
            profile = {'provider_id': source}
            if source == 'standard' and 'models' in result:
                profile['models'] = result.pop('models')
            if source in EXTERNAL_MODEL_SOURCES and source in result:
                profile['chat'] = result.pop(source)
            for kind in ('text_to_image', 'text_to_video'):
                section = result.get(kind)
                if isinstance(section, dict) and source in section:
                    profile[kind] = section.pop(source)
            if len(profile) > 1:
                path = root / filename
                loaded[path] = self._write(path, profile)
                profiles[source] = filename
        result['provider_files'] = profiles

        from .custom_providers import normalize_custom_providers_config

        legacy_section = result.pop('customProviders', {})
        section = dict(result.get('custom_providers', legacy_section) or {})
        providers = section.get('providers') or []
        if not isinstance(providers, list) or any(
            not isinstance(provider, dict) or not {'id', 'name', 'models'} <= provider.keys()
            for provider in providers
        ):
            section = normalize_custom_providers_config(section)
        records = []
        used = {filename.casefold() for filename in _FIXED_NAMES.values()}
        existing = {path.name.casefold(): path for path in root.glob('*.json')}
        for provider in section.get('providers') or []:
            provider_id = provider['id']
            name = _INVALID_FILENAME_CHAR.sub('_', provider['name']).strip().rstrip('. ')[:80].rstrip('. ') or provider_id
            if _RESERVED_FILENAME.match(name):
                name = '_' + name
            filename = f'{name}.json'
            suffix = 0
            while True:
                other = existing.get(filename.casefold())
                if filename.casefold() not in used and (other is None or self._read(other)[1].get('provider_id') == provider_id):
                    break
                suffix += 1
                filename = f'{name}-{provider_id}{"-" + str(suffix) if suffix > 1 else ""}.json'
            used.add(filename.casefold())
            path = other or root / filename
            loaded[path] = self._write(path, self._custom_profile(provider))
            records.append({'id': provider_id, 'profile': path.name})
        section['providers'] = records
        result['custom_providers'] = section

        # Commit the index last so a failed migration still has all its inputs.
        write_json_secure(config_path, result)
        if track:
            self._loaded = loaded
        # Only remove custom files owned by the preceding index in this scope.
        previous_section = previous.get('custom_providers') if isinstance(previous, dict) else None
        old_providers = previous_section.get('providers', []) if isinstance(previous_section, dict) else []
        if isinstance(old_providers, list):
            for ref in old_providers:
                if not isinstance(ref, dict) or not ref.get('profile'):
                    continue
                try:
                    path = self._path(root, ref['profile'])
                    if path not in loaded and self._read(path)[1].get('provider_id') == ref.get('id'):
                        path.unlink()
                        self._cache.pop(path, None)
                except FileNotFoundError:
                    continue
                except (OSError, ValueError):
                    logging.getLogger(__name__).warning('Could not remove superseded provider file %r', ref['profile'], exc_info=True)
