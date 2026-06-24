"""Network proxy resolution helpers."""

from __future__ import annotations

import os
import sys
from typing import Any, Dict, Optional, Tuple


_ENV_PROXY_KEYS = (
    "ALL_PROXY",
    "all_proxy",
    "HTTPS_PROXY",
    "https_proxy",
    "HTTP_PROXY",
    "http_proxy",
)


def normalize_proxy_url(value: Any) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    if text.lower() in {"clear", "default", "none", "off", "auto", "system"}:
        return ""
    if "://" not in text:
        return f"http://{text}"
    return text


def resolve_proxy_url(configured_proxy: Any = "", *, prefer_system: bool = False) -> str:
    """Return explicit, env, or OS-level proxy URL suitable for HTTP clients."""
    explicit = normalize_proxy_url(configured_proxy)
    if explicit:
        return explicit

    if prefer_system:
        system_proxy = _windows_system_proxy_url()
        if system_proxy:
            return system_proxy

    env_proxy = _environment_proxy_url()
    if env_proxy:
        return env_proxy

    system_proxy = _windows_system_proxy_url()
    if system_proxy:
        return system_proxy

    return ""


def resolve_proxy_url_with_source(configured_proxy: Any = "", *, prefer_system: bool = False) -> Tuple[str, str]:
    explicit = normalize_proxy_url(configured_proxy)
    if explicit:
        return explicit, "configured"

    if prefer_system:
        system_proxy = _windows_system_proxy_url()
        if system_proxy:
            return system_proxy, "system"

    env_proxy = _environment_proxy_url()
    if env_proxy:
        return env_proxy, "environment"

    system_proxy = _windows_system_proxy_url()
    if system_proxy:
        return system_proxy, "system"

    return "", "direct"


def requests_proxy_dict(configured_proxy: Any = "", *, prefer_system: bool = False) -> Optional[Dict[str, str]]:
    proxy = resolve_proxy_url(configured_proxy, prefer_system=prefer_system)
    if not proxy:
        return None
    return {"http": proxy, "https": proxy}


def _environment_proxy_url() -> str:
    for key in _ENV_PROXY_KEYS:
        proxy = normalize_proxy_url(os.environ.get(key, ""))
        if proxy:
            return proxy
    return ""


def _windows_system_proxy_url() -> str:
    if not sys.platform.startswith("win"):
        return ""
    try:
        import winreg  # type: ignore
    except Exception:
        return ""

    try:
        with winreg.OpenKey(
            winreg.HKEY_CURRENT_USER,
            r"Software\Microsoft\Windows\CurrentVersion\Internet Settings",
        ) as key:
            proxy_enabled = int(winreg.QueryValueEx(key, "ProxyEnable")[0] or 0)
            if not proxy_enabled:
                return ""
            proxy_server = str(winreg.QueryValueEx(key, "ProxyServer")[0] or "").strip()
    except Exception:
        return ""

    return _proxy_from_windows_proxy_server(proxy_server)


def _proxy_from_windows_proxy_server(proxy_server: str) -> str:
    text = str(proxy_server or "").strip()
    if not text:
        return ""

    if "=" not in text:
        return normalize_proxy_url(text)

    entries: Dict[str, str] = {}
    for part in text.split(";"):
        if "=" not in part:
            continue
        key, value = part.split("=", 1)
        key = key.strip().lower()
        value = value.strip()
        if key and value:
            entries[key] = value

    for key in ("https", "http", "socks"):
        value = entries.get(key, "")
        if not value:
            continue
        if key == "socks" and "://" not in value:
            return f"socks5://{value}"
        return normalize_proxy_url(value)

    return ""


def proxy_display(configured_proxy: Any = "", *, prefer_system: bool = False) -> str:
    proxy, source = resolve_proxy_url_with_source(configured_proxy, prefer_system=prefer_system)
    if not proxy:
        return "(direct)"
    if source == "configured":
        return proxy
    return f"{proxy} ({source})"
