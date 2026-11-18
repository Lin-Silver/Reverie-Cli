"""Secret-free, versionable conversation settings and stable model references."""

from __future__ import annotations

from copy import deepcopy
from pathlib import Path
from typing import Any, Dict
from urllib.parse import urlsplit, urlunsplit

from ..config import Config, EXTERNAL_MODEL_SOURCES
from ..proxy import normalize_proxy_url
from ..security_policy import PERMISSION_LEVELS, PERMISSION_MODES, RISK_LEVELS, normalize_security_config


def validate_conversation_workspace(session, project_root):
    if session is None or session.metadata.get('assistant_id')!='aio' or session.id=='aio-mainline':
        return
    owner=session.metadata.get('workspace_path')
    if owner and Path(owner).resolve()!=Path(project_root).resolve():
        raise ValueError(f'This AiO branch belongs to {owner}. Use its original workspace to continue.')


SESSION_SETTINGS = (
    "mode", "max_context_tokens", "stream_responses", "auto_index", "thinking_output_style",
    "tool_output_style", "thinking_tool", "api_compatibility", "api_timeout", "api_max_retries",
    "api_initial_backoff", "api_proxy", "security", "writer_mode", "gamer_mode", "atlas_mode",
    "text_to_image", "text_to_video", "subagents",
)
_SECRET_FIELDS = {"api_key", "custom_headers", "authorization", "password", "token", "access_token", "refresh_token", "cookie"}
_PROVIDER_INVENTORY_FIELDS = {'models', 'models_synced_at', 'model_catalog', 'catalog_profile', 'profile'}
_CUSTOM_SELECTION_FIELDS = {'reasoning_effort', 'thinking', 'model_context_limits', 'max_tokens', 'timeout'}


def _proxy_without_auth(value):
    proxy = urlsplit(normalize_proxy_url(value))
    return urlunsplit(proxy._replace(netloc=proxy.netloc.rsplit('@',1)[-1]))


def _resolve_proxy(defaults, saved):
    address = _proxy_without_auth(saved)
    return defaults.api_proxy if address == _proxy_without_auth(defaults.api_proxy) else address


def update_shared_proxy(defaults, previous_proxy, proxy):
    if proxy != previous_proxy and (_proxy_without_auth(proxy) != normalize_proxy_url(proxy) or _proxy_without_auth(proxy) == _proxy_without_auth(defaults.api_proxy)):
        defaults.api_proxy = proxy
        return True
    return False


def _without_secrets(value):
    if isinstance(value, dict):
        return {key: _proxy_without_auth(item) if key.lower()=='api_proxy' else _without_secrets(item) for key,item in value.items() if key.lower() not in _SECRET_FIELDS}
    if isinstance(value, list):
        return [_without_secrets(item) for item in value]
    return deepcopy(value)


def _provider_settings(source, provider):
    if source == 'custom':
        return _without_secrets({key: value for key, value in provider.items() if key in _CUSTOM_SELECTION_FIELDS})
    return _without_secrets({key: value for key, value in provider.items() if key not in _PROVIDER_INVENTORY_FIELDS})


def capture_runtime_config(config: Config, *, rules="", pinned_skills=None, plugins=None, previous=None) -> Dict[str, Any]:
    source = config.active_model_source
    model = config.active_model
    reference = {"source": source, "model": model.model if model else "", "profile_id": ""}
    if source == "standard" and model is not None:
        reference["profile_id"] = model.profile_id
    if source == "custom":
        reference["provider_id"] = config.custom_providers.get("active_provider_id", "")
    settings = _without_secrets({name:getattr(config,name) for name in SESSION_SETTINGS})
    for agent in settings.get('subagents',{}).get('agents',[]):
        ref = agent.get('model_ref',{})
        if ref.get('source','standard') == 'standard' and not ref.get('profile_id'):
            index = ref.get('index',-1)
            if isinstance(index,int) and 0 <= index < len(config.models):
                selected = config.models[index]
                if not ref.get('model') or ref['model'] == selected.model:
                    ref['profile_id'] = selected.profile_id
                    ref['model'] = selected.model
        if ref.get('profile_id'):
            ref.pop('index',None)
    provider = _provider_settings(source, getattr(config, source)) if source in EXTERNAL_MODEL_SOURCES else {}
    if source == "custom":
        active = reference.get("provider_id")
        record = next((item for item in config.custom_providers.get("providers", []) if item.get("id") == active), {})
        provider = _provider_settings(source, record)
    snapshot = {"version":1,"model_ref":reference,"settings":settings,"provider_settings":provider,
                "model_settings": {"max_context_tokens":model.max_context_tokens,"supports_vision":model.supports_vision} if source == 'standard' and model else {},
                "rules":str(rules),"pinned_skills":list(pinned_skills or []),"plugins":dict(plugins or {})}
    previous = previous or {}
    limits = dict(previous.get('custom_context_limits') or {})
    previous_id = (previous.get('model_ref') or {}).get('provider_id')
    previous_limits = (previous.get('provider_settings') or {}).get('model_context_limits')
    if previous_id and previous_limits:
        limits[previous_id] = previous_limits
    limits.pop(reference.get('provider_id'), None)  # The active provider's limits are in provider_settings.
    if limits:
        snapshot['custom_context_limits'] = limits
    return snapshot


def resolve_runtime_config(defaults: Config, snapshot: Dict[str, Any], *, share_catalogs: bool = False) -> Config:
    from ..desktop_catalog import apply_model_selection, select_custom_provider_model

    config = defaults.copy_with_shared_catalogs() if share_catalogs else deepcopy(defaults)
    reference = snapshot.get("model_ref") or {}
    source = str(reference.get("source") or defaults.active_model_source)
    model_id = str(reference.get("model") or "")
    custom_limits = snapshot.get('custom_context_limits') or {}
    if custom_limits:
        for item in config.custom_providers.get('providers', []):
            limits = custom_limits.get(item['id'])
            if isinstance(limits, dict):
                item['model_context_limits'] = {**item.get('model_context_limits', {}), **limits}
    if source == "standard" and not model_id and not reference.get("profile_id"):
        config.active_model_source = source
    elif source == "standard":
        matches = [i for i,item in enumerate(config.models) if item.profile_id == reference.get("profile_id")]
        if len(matches) != 1:
            raise ValueError("Saved conversation model profile is unavailable or ambiguous.")
        config.active_model_source = source
        config.active_model_index = matches[0]
        if config.active_model.model != model_id:
            raise ValueError(f"Saved conversation model is unavailable: {model_id}")
        for key,value in snapshot.get('model_settings',{}).items():
            if key in {'max_context_tokens','supports_vision'}:
                setattr(config.active_model,key,value)
    elif source == "custom":
        select_custom_provider_model(config, reference.get("provider_id"), model_id, describe_provider=False)
    elif source in EXTERNAL_MODEL_SOURCES:
        apply_model_selection(config,source,model_id)
    else:
        raise ValueError(f"Saved model source is unavailable: {source}")
    provider = snapshot.get("provider_settings") or {}
    if source in EXTERNAL_MODEL_SOURCES:
        current = dict(getattr(config,source))
        current.update(_provider_settings(source, provider))
        setattr(config,source,current)
    elif source == "custom":
        for item in config.custom_providers.get("providers",[]):
            if item.get("id") == reference.get("provider_id"):
                overrides = _provider_settings(source, provider)
                overrides['model_context_limits'] = {
                    **item.get('model_context_limits', {}), **overrides.get('model_context_limits', {}),
                }
                item.update(overrides)
    for name,value in (snapshot.get("settings") or {}).items():
        if name in SESSION_SETTINGS and name != "security":
            if name == 'api_proxy':
                config.api_proxy = _resolve_proxy(defaults,value)
            else:
                setattr(config,name,deepcopy(value))
    current = normalize_security_config(defaults.security)
    saved = normalize_security_config((snapshot.get("settings") or {}).get("security",current))
    saved["permission_level"] = PERMISSION_LEVELS[min(PERMISSION_LEVELS.index(current["permission_level"]), PERMISSION_LEVELS.index(saved["permission_level"]))]
    saved["permission_mode"] = PERMISSION_MODES[max(PERMISSION_MODES.index(current["permission_mode"]), PERMISSION_MODES.index(saved["permission_mode"]))]
    saved['strict_allow_read_only'] = current['strict_allow_read_only'] and saved['strict_allow_read_only']
    saved['review']['fail_open'] = current['review']['fail_open'] and saved['review']['fail_open']
    saved['review']['review_read_only'] = current['review']['review_read_only'] or saved['review']['review_read_only']
    saved['review']['approve_risk_at'] = RISK_LEVELS[min(RISK_LEVELS.index(current['review']['approve_risk_at']),RISK_LEVELS.index(saved['review']['approve_risk_at']))]
    config.security = saved
    return config


class ConversationConfigView:
    """Terminal settings edit the loaded conversation; catalogs stay shared."""

    def __init__(self, manager, sessions, changed):
        self.manager = manager
        self.sessions = sessions
        self.changed = changed

    def __getattr__(self, name):
        return getattr(self.manager,name)

    def load(self):
        defaults = self.manager.load()
        session = self.sessions.get_current_session()
        snapshot = session.metadata.get('runtime_config') if session else None
        config = resolve_runtime_config(defaults,snapshot) if snapshot else defaults
        self._loaded = deepcopy(config)
        return config

    def save(self, config):
        session = self.sessions.get_current_session()
        if session is None:
            self.manager.save(config)
            return
        defaults = self.manager.load()
        # Credentials and catalogs have application/workspace identity, never conversation identity.
        loaded = getattr(self,'_loaded',defaults)
        update_shared_proxy(defaults,loaded.api_proxy,config.api_proxy)
        for model in config.models:
            before = next((item for item in loaded.models if item.profile_id == model.profile_id),None)
            shared = next((item for item in defaults.models if item.profile_id == model.profile_id),None)
            if before and shared:
                for name in ('api_key','api_key_env','custom_headers','model_display_name','base_url','endpoint','provider'):
                    if getattr(model,name) != getattr(before,name):
                        setattr(shared,name,deepcopy(getattr(model,name)))
        previous = {item['id']:item for item in loaded.custom_providers.get('providers',[])}
        updated = {item['id']:item for item in config.custom_providers.get('providers',[])}
        shared = {item['id']:item for item in defaults.custom_providers.get('providers',[])}
        for key in previous.keys() - updated.keys():
            shared.pop(key,None)
        for key,item in updated.items():
            if key not in previous:
                shared[key] = deepcopy(item)
            elif key in shared:
                for field,value in item.items():
                    if value != previous[key].get(field):
                        shared[key][field] = deepcopy(value)
        defaults.custom_providers['providers'] = list(shared.values())
        for name in ('theme','show_status_line','api_enable_debug_logging','use_workspace_config'):
            setattr(defaults,name,deepcopy(getattr(config,name)))
        for source in EXTERNAL_MODEL_SOURCES:
            current = getattr(defaults,source)
            edited = getattr(config,source)
            for key,value in edited.items():
                if key.lower() in _SECRET_FIELDS or key.endswith('_key_env'):
                    current[key] = deepcopy(value)
        self.manager.save(defaults)
        previous = session.metadata.get('runtime_config') or {}
        snapshot = capture_runtime_config(config,rules=previous.get('rules',''),pinned_skills=session.metadata.get('pinned_skills',[]),plugins=previous.get('plugins',{}),previous=previous)
        page = self.sessions.get_page(session.id,limit=1)
        self.sessions.update_metadata(session.id,{'runtime_config':snapshot},expected_revision=page['revision'])
        session.metadata['runtime_config'] = snapshot
        self.changed(resolve_runtime_config(defaults,snapshot))

    def set_active_model(self,index):
        config = self.load()
        if not 0 <= index < len(config.models):
            return False
        config.active_model_source = 'standard'
        config.active_model_index = index
        self.save(config)
        return True

    def get_active_model(self):
        return self.load().active_model

    def add_model(self,model):
        self.manager.add_model(model)

    def remove_model(self,index):
        return self.manager.remove_model(index)
