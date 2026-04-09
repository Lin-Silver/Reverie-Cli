"""
WebAI2API integration helpers.

This module keeps Reverie's Web source lightweight by:
- Discovering the bundled WebAI2API reference tree
- Parsing adapter manifests without importing Playwright-heavy adapter modules
- Normalizing Reverie's persisted Web source config
- Syncing a dedicated WebAI2API worker instance into the reference YAML config
- Starting/stopping/probing the local WebAI2API OpenAI-compatible relay
"""

from __future__ import annotations

import ast
import base64
import copy
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Optional
from urllib.parse import urlparse

import requests
import yaml

from .web_direct import (
    execute_web_direct_completion,
    format_web_auth_diagnosis,
    get_web_direct_model_catalog,
    inspect_web_runtime_auth_state,
    run_interactive_web_login_session,
)


WEB_SOURCE_RELATIVE_ROOT = ("references", "WebAPI")
WEB_RUNTIME_RELATIVE_ROOT = (".reverie", "webai")
WEB_DEFAULT_PORT = 3000
WEB_DEFAULT_TIMEOUT = 1200
WEB_DEFAULT_ENDPOINT = "/v1/chat/completions"
WEB_DEFAULT_KEEPALIVE_MODE = "comment"
WEB_DEFAULT_AUTH_TOKEN = "sk-change-me-to-your-secure-key"
WEB_DEFAULT_QUEUE_BUFFER = 2
WEB_DEFAULT_IMAGE_LIMIT = 5
WEB_DEFAULT_MAX_CONTEXT_TOKENS = 262_144
WEB_REVERIE_INSTANCE_NAME = "browser_reverie_web"
WEB_REVERIE_USER_DATA_MARK = "reverie_web"
WEB_REVERIE_WORKER_PREFIX = "reverie_web_"
WEB_EXCLUDED_ADAPTER_IDS = (
    "gemini_biz",
    "gemini_biz_text",
    "sora",
    "test",
    "zenmux_ai_text",
)
WEB_ALLOWED_ADAPTER_IDS = (
    "chatgpt",
    "chatgpt_text",
    "deepseek_text",
    "doubao",
    "doubao_text",
    "gemini",
    "gemini_text",
    "google_flow",
    "nanobananafree_ai",
    "zai_is",
    "zai_is_text",
)

_WEB_MANIFEST_CACHE: Dict[str, Any] = {
    "root": "",
    "signature": "",
    "adapters": [],
}
_PYTHON_CAPABILITY_CACHE: Dict[str, bool] = {}


def _candidate_repo_roots() -> List[Path]:
    candidates: List[Path] = []
    seen: set[str] = set()

    def add(path: Optional[Path]) -> None:
        if path is None:
            return
        try:
            resolved = path.resolve(strict=False)
        except OSError:
            resolved = path
        key = str(resolved).strip().lower()
        if not key or key in seen:
            return
        seen.add(key)
        candidates.append(resolved)

    module_root = Path(__file__).resolve().parent.parent
    cwd = Path.cwd()
    argv_path = Path(sys.argv[0]).resolve(strict=False).parent if sys.argv and sys.argv[0] else None
    exec_path = Path(sys.executable).resolve(strict=False).parent if sys.executable else None

    add(module_root)
    add(cwd)
    add(cwd.parent)
    add(argv_path)
    add(argv_path.parent if argv_path else None)
    add(exec_path)
    add(exec_path.parent if exec_path else None)
    return candidates


def _resolve_launcher_root() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve(strict=False).parent

    if sys.argv and sys.argv[0]:
        try:
            exec_path = Path(os.path.abspath(sys.argv[0])).resolve(strict=False)
            if exec_path.name == "__main__.py":
                return exec_path.parent.parent
            if exec_path.exists() and exec_path.is_file():
                return exec_path.parent
        except Exception:
            pass

    return Path(__file__).resolve().parent.parent


def get_web_runtime_root() -> Path:
    return _resolve_launcher_root().joinpath(*WEB_RUNTIME_RELATIVE_ROOT)


def get_web_runtime_data_dir() -> Path:
    return get_web_runtime_root() / "data"


def get_web_runtime_logs_dir() -> Path:
    return get_web_runtime_root() / "logs"


def discover_web_source_root() -> Optional[Path]:
    """Best-effort discovery for the bundled WebAI2API reference root."""
    for repo_root in _candidate_repo_roots():
        candidate = repo_root.joinpath(*WEB_SOURCE_RELATIVE_ROOT)
        if candidate.exists() and candidate.is_dir():
            return candidate
    return None


def default_web_config() -> Dict[str, Any]:
    """Default Reverie-side config for the Web source."""
    return {
        "enabled": True,
        "selected_model_id": "",
        "selected_model_display_name": "",
        "direct_mode": True,
        "api_url": "",
        "endpoint": WEB_DEFAULT_ENDPOINT,
        "auth_token": "",
        "port": WEB_DEFAULT_PORT,
        "timeout": WEB_DEFAULT_TIMEOUT,
        "max_context_tokens": WEB_DEFAULT_MAX_CONTEXT_TOKENS,
        "auto_start": True,
        "python_executable": "",
        "source_root": "",
        "config_path": "",
        "browser_path": "",
        "headless": False,
        "humanize_cursor": True,
        "fission": True,
        "keepalive_mode": WEB_DEFAULT_KEEPALIVE_MODE,
        "queue_buffer": WEB_DEFAULT_QUEUE_BUFFER,
        "image_limit": WEB_DEFAULT_IMAGE_LIMIT,
        "enabled_adapters": list(WEB_ALLOWED_ADAPTER_IDS),
        "browser_profile": "",
        "browser_account_email": "",
    }


def _normalize_string(value: Any) -> str:
    return str(value or "").strip()


def _normalize_bool(value: Any, default: bool) -> bool:
    if isinstance(value, bool):
        return value
    if value is None:
        return default
    raw = str(value).strip().lower()
    if raw in {"1", "true", "yes", "on"}:
        return True
    if raw in {"0", "false", "no", "off"}:
        return False
    return default


def _normalize_positive_int(value: Any, default: int, *, minimum: int = 1, maximum: int = 2_147_483_647) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        parsed = default
    if parsed < minimum:
        parsed = minimum
    if parsed > maximum:
        parsed = maximum
    return parsed


def _normalize_web_endpoint(value: Any) -> str:
    endpoint = _normalize_string(value)
    if not endpoint:
        return WEB_DEFAULT_ENDPOINT
    if endpoint.lower() in {"clear", "default", "off", "none"}:
        return WEB_DEFAULT_ENDPOINT
    return endpoint


def _normalize_enabled_adapters(value: Any) -> List[str]:
    selected: List[str] = []
    if isinstance(value, list):
        for item in value:
            adapter_id = _normalize_string(item).lower()
            if not adapter_id or adapter_id in WEB_EXCLUDED_ADAPTER_IDS:
                continue
            if adapter_id not in WEB_ALLOWED_ADAPTER_IDS:
                continue
            if adapter_id not in selected:
                selected.append(adapter_id)
    if not selected:
        selected = list(WEB_ALLOWED_ADAPTER_IDS)
    return selected


def _normalize_base_url(value: Any, port: int) -> str:
    candidate = _normalize_string(value)
    if not candidate:
        return f"http://127.0.0.1:{port}"
    if not candidate.startswith(("http://", "https://")):
        candidate = f"http://{candidate}"
    parsed = urlparse(candidate)
    scheme = parsed.scheme or "http"
    host = parsed.netloc or parsed.path
    path = parsed.path if parsed.netloc else ""
    if path and path != "/":
        candidate = f"{scheme}://{host}{path}".rstrip("/")
    else:
        candidate = f"{scheme}://{host}".rstrip("/")
    return candidate


def _paths_match(left: Path, right: Path) -> bool:
    try:
        return left.resolve(strict=False) == right.resolve(strict=False)
    except OSError:
        return left == right


def _ast_value(node: ast.AST) -> Any:
    if isinstance(node, ast.Constant):
        return node.value
    if isinstance(node, ast.Str):
        return node.s
    if isinstance(node, ast.Num):
        return node.n
    if isinstance(node, ast.NameConstant):
        return node.value
    if isinstance(node, ast.List):
        return [_ast_value(item) for item in node.elts]
    if isinstance(node, ast.Tuple):
        return [_ast_value(item) for item in node.elts]
    if isinstance(node, ast.Dict):
        return {
            _ast_value(key): _ast_value(value)
            for key, value in zip(node.keys, node.values)
        }
    return None


def _call_name(node: ast.Call) -> str:
    func = node.func
    if isinstance(func, ast.Name):
        return func.id
    if isinstance(func, ast.Attribute):
        return func.attr
    return ""


def _parse_model_spec(node: ast.AST) -> Optional[Dict[str, Any]]:
    if not isinstance(node, ast.Call) or _call_name(node) != "ModelSpec":
        return None

    parsed: Dict[str, Any] = {
        "id": "",
        "image_policy": "optional",
        "type": "image",
        "code_name": "",
        "search": False,
        "url": "",
        "image_size": "",
        "providers": [],
        "thinking": False,
    }
    for keyword in node.keywords:
        if keyword.arg:
            parsed[keyword.arg] = _ast_value(keyword.value)

    model_id = _normalize_string(parsed.get("id"))
    if not model_id:
        return None

    return {
        "id": model_id,
        "image_policy": _normalize_string(parsed.get("image_policy") or "optional").lower() or "optional",
        "type": _normalize_string(parsed.get("type") or "image").lower() or "image",
        "code_name": _normalize_string(parsed.get("code_name")),
        "search": bool(parsed.get("search")),
        "url": _normalize_string(parsed.get("url")),
        "image_size": _normalize_string(parsed.get("image_size")),
        "providers": [
            _normalize_string(item)
            for item in (parsed.get("providers") or [])
            if _normalize_string(item)
        ],
        "thinking": bool(parsed.get("thinking")),
    }


def _parse_adapter_manifest(path: Path) -> Optional[Dict[str, Any]]:
    try:
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    except Exception:
        return None

    for node in tree.body:
        if not isinstance(node, ast.Assign):
            continue
        if not any(isinstance(target, ast.Name) and target.id == "manifest" for target in node.targets):
            continue
        if not isinstance(node.value, ast.Call) or _call_name(node.value) != "AdapterManifest":
            continue

        raw_manifest: Dict[str, Any] = {}
        for keyword in node.value.keywords:
            if keyword.arg:
                raw_manifest[keyword.arg] = keyword.value

        adapter_id = _normalize_string(_ast_value(raw_manifest.get("id", ast.Constant(value="")))).lower()
        if not adapter_id or adapter_id in WEB_EXCLUDED_ADAPTER_IDS:
            return None

        models_node = raw_manifest.get("models")
        models: List[Dict[str, Any]] = []
        if isinstance(models_node, (ast.List, ast.Tuple)):
            for item in models_node.elts:
                parsed = _parse_model_spec(item)
                if parsed is not None:
                    models.append(parsed)

        if not models:
            return None

        return {
            "id": adapter_id,
            "display_name": _normalize_string(_ast_value(raw_manifest.get("display_name", ast.Constant(value=adapter_id)))) or adapter_id,
            "description": _normalize_string(_ast_value(raw_manifest.get("description", ast.Constant(value="")))),
            "models": models,
            "path": str(path),
        }
    return None


def _manifest_cache_signature(adapters_dir: Path) -> str:
    try:
        files = sorted(
            path for path in adapters_dir.glob("*.py")
            if path.name not in {"__init__.py", "common.py", "parsers.py", "shared.py"}
        )
    except OSError:
        return ""
    return "|".join(f"{path.name}:{path.stat().st_mtime_ns}" for path in files if path.is_file())


def get_web_adapter_manifests(*, force_refresh: bool = False) -> List[Dict[str, Any]]:
    """Parse adapter manifests from the bundled WebAI2API source tree."""
    source_root = discover_web_source_root()
    if source_root is None:
        return []

    adapters_dir = source_root / "webai2api_py" / "adapters"
    if not adapters_dir.exists():
        return []

    signature = _manifest_cache_signature(adapters_dir)
    if (
        not force_refresh
        and _WEB_MANIFEST_CACHE.get("root") == str(source_root)
        and _WEB_MANIFEST_CACHE.get("signature") == signature
        and isinstance(_WEB_MANIFEST_CACHE.get("adapters"), list)
    ):
        return [dict(item) for item in _WEB_MANIFEST_CACHE["adapters"]]

    manifests: List[Dict[str, Any]] = []
    for path in sorted(adapters_dir.glob("*.py")):
        if path.name in {"__init__.py", "common.py", "parsers.py", "shared.py"}:
            continue
        parsed = _parse_adapter_manifest(path)
        if parsed is not None:
            manifests.append(parsed)

    manifests = [
        item
        for item in manifests
        if item.get("id") in WEB_ALLOWED_ADAPTER_IDS
    ]
    manifests.sort(key=lambda item: WEB_ALLOWED_ADAPTER_IDS.index(item["id"]))

    _WEB_MANIFEST_CACHE["root"] = str(source_root)
    _WEB_MANIFEST_CACHE["signature"] = signature
    _WEB_MANIFEST_CACHE["adapters"] = [dict(item) for item in manifests]
    return manifests


def _build_web_model_display_name(
    *,
    base_name: str,
    adapter_display_name: str,
    image_size: str = "",
    thinking: bool = False,
    search: bool = False,
) -> str:
    parts = [base_name, f"[{adapter_display_name}]"]
    if image_size:
        parts.append(f"({image_size})")
    if thinking:
        parts.append("(thinking)")
    if search:
        parts.append("(search)")
    return " ".join(part for part in parts if part)


def _build_web_model_description(adapter: Dict[str, Any], model: Dict[str, Any]) -> str:
    fragments = [
        f"adapter={adapter.get('id', '')}",
        f"type={model.get('type', 'image')}",
        f"image_policy={model.get('image_policy', 'optional')}",
    ]
    if model.get("providers"):
        fragments.append("providers=" + ", ".join(str(item) for item in model["providers"]))
    if model.get("image_size"):
        fragments.append(f"size={model['image_size']}")
    if model.get("thinking"):
        fragments.append("thinking")
    if model.get("search"):
        fragments.append("search")
    adapter_description = _normalize_string(adapter.get("description"))
    if adapter_description:
        fragments.append(adapter_description)
    return " | ".join(fragment for fragment in fragments if fragment)


def _get_legacy_web_manifest_catalog(
    *,
    model_type: str = "text",
    enabled_adapters: Optional[List[str]] = None,
    force_refresh: bool = False,
) -> List[Dict[str, Any]]:
    """Return the legacy manifest-derived catalog used by the old relay/image flow."""
    selected_adapters = set(_normalize_enabled_adapters(enabled_adapters))
    wanted_type = _normalize_string(model_type).lower() or "text"
    catalog: List[Dict[str, Any]] = []
    for adapter in get_web_adapter_manifests(force_refresh=force_refresh):
        adapter_id = _normalize_string(adapter.get("id")).lower()
        if adapter_id not in selected_adapters:
            continue
        adapter_display = _normalize_string(adapter.get("display_name")) or adapter_id
        for model in adapter.get("models", []):
            item_type = _normalize_string(model.get("type") or "image").lower() or "image"
            if wanted_type != "all" and item_type != wanted_type:
                continue
            base_model_id = _normalize_string(model.get("id"))
            if not base_model_id:
                continue
            base_name = _normalize_string(model.get("code_name")) or base_model_id
            catalog.append(
                {
                    "id": f"{adapter_id}/{base_model_id}",
                    "base_model_id": base_model_id,
                    "display_name": _build_web_model_display_name(
                        base_name=base_name,
                        adapter_display_name=adapter_display,
                        image_size=_normalize_string(model.get("image_size")),
                        thinking=bool(model.get("thinking")),
                        search=bool(model.get("search")),
                    ),
                    "description": _build_web_model_description(adapter, model),
                    "adapter_id": adapter_id,
                    "adapter_display_name": adapter_display,
                    "model_type": item_type,
                    "image_policy": _normalize_string(model.get("image_policy") or "optional").lower() or "optional",
                    "thinking": bool(model.get("thinking")),
                    "search": bool(model.get("search")),
                    "providers": list(model.get("providers") or []),
                    "image_size": _normalize_string(model.get("image_size")),
                    "url": _normalize_string(model.get("url")),
                }
            )
    return catalog


def get_web_model_catalog(
    *,
    model_type: str = "text",
    enabled_adapters: Optional[List[str]] = None,
    force_refresh: bool = False,
) -> List[Dict[str, Any]]:
    """
    Return Web models for text or image workflows.

    Text models now come from the direct browser-source catalog so Reverie no
    longer inherits the over-broad relay manifest list. Image models still use
    the legacy manifest path for the existing `/tti source web` flow.
    """
    wanted_type = _normalize_string(model_type).lower() or "text"
    direct_catalog = get_web_direct_model_catalog(source_root=discover_web_source_root(), force_refresh=force_refresh)
    if wanted_type == "text":
        return direct_catalog
    if wanted_type == "image":
        return _get_legacy_web_manifest_catalog(
            model_type="image",
            enabled_adapters=enabled_adapters,
            force_refresh=force_refresh,
        )
    if wanted_type == "all":
        return direct_catalog + _get_legacy_web_manifest_catalog(
            model_type="image",
            enabled_adapters=enabled_adapters,
            force_refresh=force_refresh,
        )
    return []


def _resolve_catalog_item(
    catalog: List[Dict[str, Any]],
    *,
    model_id: str = "",
    display_name: str = "",
) -> Optional[Dict[str, Any]]:
    wanted_id = _normalize_string(model_id).lower()
    wanted_name = _normalize_string(display_name).lower()

    if wanted_id:
        for item in catalog:
            if _normalize_string(item.get("id")).lower() == wanted_id:
                return dict(item)

    if wanted_name:
        for item in catalog:
            if _normalize_string(item.get("display_name")).lower() == wanted_name:
                return dict(item)

    return None


def normalize_web_config(raw_web: Any) -> Dict[str, Any]:
    """Normalize Reverie's persisted Web source config."""
    cfg = default_web_config()
    if isinstance(raw_web, dict):
        cfg.update(raw_web)

    discovered_root = discover_web_source_root()
    configured_root = Path(_normalize_string(cfg.get("source_root"))).expanduser() if _normalize_string(cfg.get("source_root")) else None
    if configured_root:
        try:
            configured_root = configured_root.resolve(strict=False)
        except OSError:
            pass
    source_root = configured_root if configured_root and configured_root.exists() else discovered_root

    cfg["enabled"] = _normalize_bool(cfg.get("enabled"), True)
    cfg["selected_model_id"] = _normalize_string(cfg.get("selected_model_id"))
    cfg["selected_model_display_name"] = _normalize_string(cfg.get("selected_model_display_name"))
    cfg["direct_mode"] = _normalize_bool(cfg.get("direct_mode"), True)
    cfg["port"] = _normalize_positive_int(cfg.get("port"), WEB_DEFAULT_PORT, minimum=1, maximum=65535)
    cfg["timeout"] = _normalize_positive_int(cfg.get("timeout"), WEB_DEFAULT_TIMEOUT, minimum=30, maximum=86400)
    cfg["max_context_tokens"] = _normalize_positive_int(
        cfg.get("max_context_tokens"),
        WEB_DEFAULT_MAX_CONTEXT_TOKENS,
        minimum=4096,
        maximum=4_194_304,
    )
    cfg["auto_start"] = _normalize_bool(cfg.get("auto_start"), True)
    cfg["endpoint"] = _normalize_web_endpoint(cfg.get("endpoint"))
    cfg["auth_token"] = _normalize_string(cfg.get("auth_token")) or WEB_DEFAULT_AUTH_TOKEN
    cfg["python_executable"] = _normalize_string(cfg.get("python_executable"))
    cfg["browser_path"] = _normalize_string(cfg.get("browser_path"))
    cfg["browser_profile"] = _normalize_string(cfg.get("browser_profile"))
    cfg["browser_account_email"] = _normalize_string(cfg.get("browser_account_email")).lower()
    cfg["headless"] = _normalize_bool(cfg.get("headless"), False)
    cfg["humanize_cursor"] = _normalize_bool(cfg.get("humanize_cursor"), True)
    cfg["fission"] = _normalize_bool(cfg.get("fission"), True)
    cfg["queue_buffer"] = _normalize_positive_int(cfg.get("queue_buffer"), WEB_DEFAULT_QUEUE_BUFFER, minimum=0, maximum=128)
    cfg["image_limit"] = _normalize_positive_int(cfg.get("image_limit"), WEB_DEFAULT_IMAGE_LIMIT, minimum=1, maximum=10)
    cfg["enabled_adapters"] = _normalize_enabled_adapters(cfg.get("enabled_adapters"))

    keepalive_mode = _normalize_string(cfg.get("keepalive_mode")).lower()
    if keepalive_mode not in {"comment", "content"}:
        keepalive_mode = WEB_DEFAULT_KEEPALIVE_MODE
    cfg["keepalive_mode"] = keepalive_mode

    cfg["source_root"] = str(source_root) if source_root else ""
    cfg["runtime_root"] = str(get_web_runtime_root())

    configured_config_path = _normalize_string(cfg.get("config_path"))
    if configured_config_path:
        configured_path = Path(configured_config_path).expanduser()
        legacy_default = _default_reference_config_path(source_root)
        old_runtime_default = get_web_runtime_root() / "config.yaml"
        if (
            (legacy_default is not None and _paths_match(configured_path, legacy_default))
            or _paths_match(configured_path, old_runtime_default)
        ):
            configured_path = _default_runtime_config_path()
        cfg["config_path"] = str(configured_path)
    else:
        default_config_path = _default_runtime_config_path()
        cfg["config_path"] = str(default_config_path) if default_config_path else ""

    cfg["api_url"] = _normalize_base_url(cfg.get("api_url"), cfg["port"])

    if cfg["selected_model_id"] or cfg["selected_model_display_name"]:
        selected = resolve_web_selected_model(cfg)
        if selected:
            cfg["selected_model_id"] = selected["id"]
            cfg["selected_model_display_name"] = selected["display_name"]
        elif cfg["selected_model_id"]:
            cfg["selected_model_display_name"] = cfg["selected_model_display_name"] or cfg["selected_model_id"]

    return cfg


def resolve_web_selected_model(
    web_config: Any,
    *,
    model_type: str = "text",
    force_refresh: bool = False,
) -> Optional[Dict[str, Any]]:
    """Resolve the currently selected Web chat model."""
    cfg = dict(web_config) if isinstance(web_config, dict) else default_web_config()
    catalog = get_web_model_catalog(
        model_type=model_type,
        enabled_adapters=cfg.get("enabled_adapters"),
        force_refresh=force_refresh,
    )
    if not catalog:
        return None

    selected = _resolve_catalog_item(
        catalog,
        model_id=cfg.get("selected_model_id", ""),
        display_name=cfg.get("selected_model_display_name", ""),
    )
    if selected:
        return selected
    return dict(catalog[0])


def resolve_web_image_model(
    web_config: Any,
    text_to_image_config: Any = None,
    *,
    force_refresh: bool = False,
) -> Optional[Dict[str, Any]]:
    """Resolve the Web-backed text-to-image model selection."""
    web_cfg = dict(web_config) if isinstance(web_config, dict) else default_web_config()
    tti_cfg = dict(text_to_image_config) if isinstance(text_to_image_config, dict) else {}
    catalog = get_web_model_catalog(
        model_type="image",
        enabled_adapters=web_cfg.get("enabled_adapters"),
        force_refresh=force_refresh,
    )
    if not catalog:
        return None

    selected = _resolve_catalog_item(
        catalog,
        model_id=tti_cfg.get("web_default_model_id", ""),
        display_name=tti_cfg.get("web_default_model_display_name", ""),
    )
    if selected:
        return selected
    return dict(catalog[0])


def resolve_web_request_url(web_config: Any) -> str:
    """Resolve the WebAI2API request URL used for OpenAI-compatible chat calls."""
    cfg = normalize_web_config(web_config)
    endpoint = _normalize_string(cfg.get("endpoint")) or WEB_DEFAULT_ENDPOINT
    if endpoint.startswith(("http://", "https://")):
        return endpoint
    if not endpoint.startswith("/"):
        endpoint = f"/{endpoint}"
    return f"{str(cfg.get('api_url', '')).rstrip('/')}{endpoint}"


def build_web_runtime_model_data(web_config: Any) -> Optional[Dict[str, Any]]:
    """Build runtime model config dict for the direct Web source."""
    cfg = normalize_web_config(web_config)
    if not cfg.get("enabled", True):
        return None

    selected = resolve_web_selected_model(cfg, model_type="text")
    if not selected:
        return None

    return {
        "model": selected["id"],
        "model_display_name": selected["display_name"],
        "base_url": _normalize_string(selected.get("target_url", "")) or _normalize_string(selected.get("url", "")),
        "api_key": "",
        "max_context_tokens": int(selected.get("context_length") or cfg.get("max_context_tokens", WEB_DEFAULT_MAX_CONTEXT_TOKENS)),
        "provider": "web-direct",
        "thinking_mode": "true" if bool(selected.get("thinking")) else None,
        "endpoint": "",
        "custom_headers": {},
    }


def run_web_direct_completion(web_config: Any, model_id: str, messages: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Run a direct browser-backed Web completion using the selected site adapter."""
    cfg = normalize_web_config(web_config)
    return execute_web_direct_completion(
        web_config=cfg,
        model_id=model_id,
        messages=messages,
        source_root=cfg.get("source_root", ""),
    )


def inspect_web_auth_state(web_config: Any, source_id: str) -> Dict[str, Any]:
    """Inspect the browser-backed auth state for one direct Web source."""
    cfg = normalize_web_config(web_config)
    return inspect_web_runtime_auth_state(cfg, source_id)


def run_web_login_session(web_config: Any, source_id: str) -> Dict[str, Any]:
    """Launch an interactive login flow for one direct Web source."""
    cfg = normalize_web_config(web_config)
    return run_interactive_web_login_session(
        cfg,
        source_id,
        source_root=cfg.get("source_root", ""),
    )


def format_web_auth_state_diagnosis(source_id: str, auth_state: Dict[str, Any]) -> str:
    """Return a friendly auth diagnosis for one direct Web source."""
    return format_web_auth_diagnosis(source_id, auth_state)


def _load_yaml_config(path: Path) -> Dict[str, Any]:
    if not path.exists():
        return {}
    try:
        raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    return raw if isinstance(raw, dict) else {}


def _default_reference_config_path(source_root: Optional[Path]) -> Optional[Path]:
    if source_root is None:
        return None
    return source_root / "data" / "config.yaml"


def _default_runtime_config_path() -> Path:
    return get_web_runtime_data_dir() / "config.yaml"


def _example_reference_config_path(source_root: Optional[Path]) -> Optional[Path]:
    if source_root is None:
        return None
    for candidate in (
        source_root / "config.example.yaml",
        source_root / "WebAI2API" / "config.example.yaml",
    ):
        if candidate.exists():
            return candidate
    return None


def _build_reverie_web_instance(enabled_adapters: List[str]) -> Dict[str, Any]:
    workers = [
        {
            "name": f"{WEB_REVERIE_WORKER_PREFIX}{adapter_id}",
            "type": adapter_id,
        }
        for adapter_id in enabled_adapters
    ]
    return {
        "name": WEB_REVERIE_INSTANCE_NAME,
        "userDataMark": WEB_REVERIE_USER_DATA_MARK,
        "workers": workers,
    }


def sync_reference_web_config(web_config: Any) -> Dict[str, Any]:
    """
    Sync Reverie's Web settings into the bundled WebAI2API YAML config.

    Returns metadata describing the effective config path and whether a write occurred.
    """
    cfg = normalize_web_config(web_config)
    source_root = Path(cfg["source_root"]).resolve(strict=False) if cfg.get("source_root") else None
    if source_root is None or not source_root.exists():
        return {
            "success": False,
            "error": "Bundled WebAI2API source root was not found.",
            "config_path": cfg.get("config_path", ""),
            "source_root": cfg.get("source_root", ""),
        }

    runtime_root = get_web_runtime_root()
    runtime_data_dir = get_web_runtime_data_dir()

    config_path = Path(cfg["config_path"]).expanduser() if cfg.get("config_path") else _default_runtime_config_path()
    if config_path is None:
        return {
            "success": False,
            "error": "Unable to resolve WebAI2API config path.",
            "config_path": "",
            "source_root": str(source_root),
        }

    config_path.parent.mkdir(parents=True, exist_ok=True)
    if config_path.exists():
        raw_config = _load_yaml_config(config_path)
    else:
        example_path = _example_reference_config_path(source_root)
        raw_config = _load_yaml_config(example_path) if example_path else {}

    config_data = copy.deepcopy(raw_config) if isinstance(raw_config, dict) else {}
    config_data.setdefault("logLevel", "info")
    config_data.setdefault("server", {})
    config_data.setdefault("backend", {})
    config_data["backend"].setdefault("pool", {})
    config_data.setdefault("queue", {})
    config_data.setdefault("browser", {})
    config_data.setdefault("paths", {})

    config_data["server"]["port"] = int(cfg["port"])
    config_data["server"]["auth"] = str(cfg["auth_token"])
    config_data["server"].setdefault("keepalive", {})
    config_data["server"]["keepalive"]["mode"] = str(cfg["keepalive_mode"])

    config_data["queue"]["queueBuffer"] = int(cfg["queue_buffer"])
    config_data["queue"]["imageLimit"] = int(cfg["image_limit"])
    config_data["paths"]["tempDir"] = str(runtime_data_dir / "temp")

    config_data["browser"]["path"] = str(cfg.get("browser_path", "") or "")
    config_data["browser"]["headless"] = bool(cfg["headless"])
    config_data["browser"]["humanizeCursor"] = bool(cfg["humanize_cursor"])
    config_data["browser"]["fission"] = bool(cfg["fission"])

    config_data["backend"]["pool"]["waitTimeout"] = int(cfg["timeout"]) * 1000
    config_data["backend"]["pool"]["instances"] = [_build_reverie_web_instance(cfg["enabled_adapters"])]

    serialized = yaml.safe_dump(config_data, sort_keys=False, indent=2, allow_unicode=True)
    previous = config_path.read_text(encoding="utf-8") if config_path.exists() else ""
    updated = previous != serialized
    if updated:
        config_path.write_text(serialized, encoding="utf-8")

    return {
        "success": True,
        "updated": updated,
        "config_path": str(config_path),
        "source_root": str(source_root),
        "runtime_root": str(runtime_root),
        "runtime_data_dir": str(runtime_data_dir),
        "instance_name": WEB_REVERIE_INSTANCE_NAME,
        "worker_count": len(cfg["enabled_adapters"]),
        "enabled_adapters": list(cfg["enabled_adapters"]),
    }


def _web_headers(auth_token: str) -> Dict[str, str]:
    headers: Dict[str, str] = {}
    token = _normalize_string(auth_token)
    if token:
        headers["Authorization"] = f"Bearer {token}"
    return headers


def get_web_service_status(web_config: Any, *, timeout_seconds: int = 3) -> Dict[str, Any]:
    """Probe the local/remote WebAI2API relay and return a friendly status object."""
    cfg = normalize_web_config(web_config)
    base_url = _normalize_string(cfg.get("api_url"))
    admin_url = f"{base_url.rstrip('/')}/admin/status" if base_url else ""
    models_url = f"{base_url.rstrip('/')}/v1/models" if base_url else ""

    result = {
        "success": True,
        "running": False,
        "reachable": False,
        "safe_mode": False,
        "safe_mode_reason": "",
        "models_count": 0,
        "base_url": base_url,
        "admin_url": admin_url,
        "models_url": models_url,
        "config_path": cfg.get("config_path", ""),
        "source_root": cfg.get("source_root", ""),
        "runtime_root": str(get_web_runtime_root()),
        "runtime_data_dir": str(get_web_runtime_data_dir()),
        "error": "",
    }

    if not base_url:
        result["success"] = False
        result["error"] = "Web API URL is empty."
        return result

    try:
        response = requests.get(admin_url, headers=_web_headers(cfg.get("auth_token", "")), timeout=timeout_seconds)
        response.raise_for_status()
        payload = response.json() if response.content else {}
        result["running"] = True
        result["reachable"] = True
        safe_mode = payload.get("safeMode", {})
        if isinstance(safe_mode, dict):
            result["safe_mode"] = bool(safe_mode.get("enabled"))
            result["safe_mode_reason"] = _normalize_string(safe_mode.get("reason"))
    except Exception as exc:
        result["error"] = str(exc)
        return result

    try:
        models_response = requests.get(models_url, headers=_web_headers(cfg.get("auth_token", "")), timeout=timeout_seconds)
        models_response.raise_for_status()
        models_payload = models_response.json() if models_response.content else {}
        if isinstance(models_payload, dict):
            models = models_payload.get("data", [])
            if isinstance(models, list):
                result["models_count"] = len(models)
    except Exception:
        pass

    return result


def _tail_file(path: Path, limit: int = 6000) -> str:
    if not path.exists():
        return ""
    try:
        with open(path, "rb") as handle:
            handle.seek(0, os.SEEK_END)
            size = handle.tell()
            handle.seek(max(0, size - limit), os.SEEK_SET)
            content = handle.read().decode("utf-8", errors="replace")
    except Exception:
        return ""
    return content.strip()


def _python_can_run_webai(executable: Path) -> bool:
    key = str(executable.resolve(strict=False)).lower()
    cached = _PYTHON_CAPABILITY_CACHE.get(key)
    if cached is not None:
        return cached

    try:
        probe = subprocess.run(
            [
                str(executable),
                "-c",
                "import fastapi, uvicorn, playwright, psutil, PIL, httpx, yaml",
            ],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=20,
            check=False,
        )
        ok = probe.returncode == 0
    except Exception:
        ok = False

    _PYTHON_CAPABILITY_CACHE[key] = ok
    return ok


def _resolve_python_executable(web_config: Any, source_root: Optional[Path] = None) -> Optional[Path]:
    cfg = normalize_web_config(web_config)
    configured = _normalize_string(cfg.get("python_executable"))
    if configured:
        return Path(configured).expanduser()

    candidate_roots: List[Path] = []
    root = source_root or (Path(cfg["source_root"]).resolve(strict=False) if cfg.get("source_root") else None)
    if root is not None:
        candidate_roots.append(root)

    launcher_root = _resolve_launcher_root()
    if not any(_paths_match(launcher_root, existing) for existing in candidate_roots):
        candidate_roots.append(launcher_root)

    for base_root in candidate_roots:
        for candidate in (
            base_root / ".venv" / "Scripts" / "python.exe",
            base_root / ".venv" / "bin" / "python",
            base_root / "venv" / "Scripts" / "python.exe",
            base_root / "venv" / "bin" / "python",
        ):
            if candidate.exists() and _python_can_run_webai(candidate):
                return candidate

    if getattr(sys, "frozen", False):
        for command in ("python", "python3", "py"):
            discovered = shutil.which(command)
            if discovered:
                candidate = Path(discovered).resolve()
                if _python_can_run_webai(candidate):
                    return candidate
        return None

    executable = Path(sys.executable).resolve()
    if (
        executable.name.lower().endswith("python.exe")
        or executable.name.lower().startswith("python")
    ) and _python_can_run_webai(executable):
        return executable

    for command in ("python", "python3", "py"):
        discovered = shutil.which(command)
        if discovered:
            candidate = Path(discovered).resolve()
            if _python_can_run_webai(candidate):
                return candidate
    return None


def start_web_service(web_config: Any, *, wait_seconds: int = 25) -> Dict[str, Any]:
    """Start the bundled WebAI2API service as a background process."""
    cfg = normalize_web_config(web_config)
    current_status = get_web_service_status(cfg, timeout_seconds=2)
    if current_status.get("running"):
        current_status["started"] = False
        current_status["success"] = True
        return current_status

    sync_result = sync_reference_web_config(cfg)
    if not sync_result.get("success"):
        return sync_result

    source_root = Path(sync_result["source_root"]).resolve(strict=False)
    runtime_root = Path(sync_result["runtime_root"]).resolve(strict=False)
    runtime_data_dir = Path(sync_result["runtime_data_dir"]).resolve(strict=False)
    python_executable = _resolve_python_executable(cfg, source_root)
    if python_executable is None:
        return {
            "success": False,
            "error": "No usable Python interpreter was found for WebAI2API.",
            "source_root": str(source_root),
            "runtime_root": str(runtime_root),
        }
    if not python_executable.exists():
        return {
            "success": False,
            "error": f"Python executable not found: {python_executable}",
            "source_root": str(source_root),
            "runtime_root": str(runtime_root),
        }
    if not _python_can_run_webai(python_executable):
        return {
            "success": False,
            "error": f"Python environment is missing required WebAI2API dependencies: {python_executable}",
            "source_root": str(source_root),
            "runtime_root": str(runtime_root),
        }

    runtime_root.mkdir(parents=True, exist_ok=True)
    runtime_data_dir.mkdir(parents=True, exist_ok=True)

    temp_dir = runtime_data_dir / "temp"
    home_dir = runtime_root / "home"
    appdata_dir = runtime_root / "appdata"
    localappdata_dir = runtime_root / "localappdata"
    xdg_cache_dir = runtime_root / "xdg" / "cache"
    xdg_config_dir = runtime_root / "xdg" / "config"
    xdg_data_dir = runtime_root / "xdg" / "data"
    playwright_browsers_dir = runtime_root / "playwright-browsers"
    for path in (
        temp_dir,
        home_dir,
        appdata_dir,
        localappdata_dir,
        xdg_cache_dir,
        xdg_config_dir,
        xdg_data_dir,
        playwright_browsers_dir,
    ):
        path.mkdir(parents=True, exist_ok=True)

    log_dir = get_web_runtime_logs_dir()
    log_dir.mkdir(parents=True, exist_ok=True)
    log_path = log_dir / "reverie_web_service.log"
    command = [str(python_executable), "-m", "webai2api_py"]
    service_env = os.environ.copy()
    service_env.update(
        {
            "WEBAI2API_RUNTIME_ROOT": str(runtime_root),
            "WEBAI2API_DATA_DIR": str(runtime_data_dir),
            "REVERIE_WEBAI_RUNTIME_ROOT": str(runtime_root),
            "REVERIE_WEBAI_DATA_DIR": str(runtime_data_dir),
            "TMP": str(temp_dir),
            "TEMP": str(temp_dir),
            "HOME": str(home_dir),
            "USERPROFILE": str(home_dir),
            "APPDATA": str(appdata_dir),
            "LOCALAPPDATA": str(localappdata_dir),
            "XDG_CACHE_HOME": str(xdg_cache_dir),
            "XDG_CONFIG_HOME": str(xdg_config_dir),
            "XDG_DATA_HOME": str(xdg_data_dir),
            "PLAYWRIGHT_BROWSERS_PATH": str(playwright_browsers_dir),
        }
    )

    creationflags = 0
    startupinfo = None
    if os.name == "nt":
        creationflags = getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
        startupinfo = subprocess.STARTUPINFO()
        startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW

    with open(log_path, "ab") as log_handle:
        try:
            process = subprocess.Popen(
                command,
                cwd=str(source_root),
                stdin=subprocess.DEVNULL,
                stdout=log_handle,
                stderr=subprocess.STDOUT,
                env=service_env,
                creationflags=creationflags,
                startupinfo=startupinfo,
                start_new_session=(os.name != "nt"),
            )
        except Exception as exc:
            return {
                "success": False,
                "error": f"Failed to start WebAI2API: {exc}",
                "log_path": str(log_path),
                "runtime_root": str(runtime_root),
            }

    deadline = time.time() + max(5, wait_seconds)
    last_error = ""
    while time.time() < deadline:
        status = get_web_service_status(cfg, timeout_seconds=2)
        if status.get("running"):
            status["success"] = True
            status["started"] = True
            status["pid"] = process.pid
            status["log_path"] = str(log_path)
            status["runtime_root"] = str(runtime_root)
            status["runtime_data_dir"] = str(runtime_data_dir)
            return status
        last_error = _normalize_string(status.get("error"))
        if process.poll() is not None:
            break
        time.sleep(0.5)

    return {
        "success": False,
        "error": last_error or "WebAI2API did not become ready before timeout.",
        "pid": process.pid,
        "log_path": str(log_path),
        "log_tail": _tail_file(log_path),
        "source_root": str(source_root),
        "runtime_root": str(runtime_root),
        "runtime_data_dir": str(runtime_data_dir),
    }


def stop_web_service(web_config: Any, *, wait_seconds: int = 12) -> Dict[str, Any]:
    """Ask the WebAI2API relay to stop gracefully."""
    cfg = normalize_web_config(web_config)
    status = get_web_service_status(cfg, timeout_seconds=2)
    if not status.get("running"):
        status["success"] = True
        status["stopped"] = False
        return status

    try:
        response = requests.post(
            f"{str(cfg.get('api_url', '')).rstrip('/')}/admin/stop",
            headers=_web_headers(cfg.get("auth_token", "")),
            timeout=5,
        )
        response.raise_for_status()
    except Exception as exc:
        return {
            "success": False,
            "error": f"Failed to stop WebAI2API: {exc}",
            "base_url": cfg.get("api_url", ""),
        }

    deadline = time.time() + max(5, wait_seconds)
    while time.time() < deadline:
        current = get_web_service_status(cfg, timeout_seconds=2)
        if not current.get("running"):
            current["success"] = True
            current["stopped"] = True
            return current
        time.sleep(0.5)

    return {
        "success": False,
        "error": "Timed out waiting for WebAI2API to stop.",
        "base_url": cfg.get("api_url", ""),
    }


def ensure_web_service_running(web_config: Any, *, start_if_needed: Optional[bool] = None) -> Dict[str, Any]:
    """Ensure the local WebAI2API relay is reachable."""
    cfg = normalize_web_config(web_config)
    status = get_web_service_status(cfg, timeout_seconds=2)
    if status.get("running"):
        return status

    should_start = cfg.get("auto_start", True) if start_if_needed is None else bool(start_if_needed)
    if not should_start:
        status["success"] = False
        status["error"] = status.get("error") or "WebAI2API is not running."
        return status

    return start_web_service(cfg)


def save_data_url_to_file(data_url: str, output_path: Path) -> Path:
    """Persist a `data:image/...;base64,...` payload to disk and return the saved path."""
    raw = _normalize_string(data_url)
    if not raw.startswith("data:") or "," not in raw:
        raise ValueError("Expected a data URL image payload.")

    header, payload = raw.split(",", 1)
    is_base64 = ";base64" in header.lower()
    mime_type = header[5:].split(";", 1)[0].strip().lower()
    extension = {
        "image/png": ".png",
        "image/jpeg": ".jpg",
        "image/jpg": ".jpg",
        "image/webp": ".webp",
        "image/gif": ".gif",
    }.get(mime_type, ".png")

    destination = Path(output_path)
    if destination.suffix:
        final_path = destination
        final_path.parent.mkdir(parents=True, exist_ok=True)
    else:
        destination.mkdir(parents=True, exist_ok=True)
        timestamp = time.strftime("%Y%m%d_%H%M%S")
        final_path = destination / f"web_image_{timestamp}{extension}"

    if is_base64:
        binary = base64.b64decode(payload)
    else:
        binary = payload.encode("utf-8")
    final_path.write_bytes(binary)
    return final_path
