"""
Direct Web-source runtime helpers.

This module replaces the localhost relay dependency for chat-style `/web`
models by running provider-specific browser workflows in-process. It keeps the
existing WebAI2API reference tree as an adapter reference, but Reverie now
invokes those browser flows directly instead of depending on
`http://127.0.0.1:<port>/v1/chat/completions`.
"""

from __future__ import annotations

import asyncio
import base64
import copy
import importlib
import json
import os
import re
import shutil
import socket
import sqlite3
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional
from urllib.parse import urlparse


WEB_DIRECT_DEFAULT_CONTEXT = 262_144
WEB_DIRECT_RUNTIME_DIRNAME = "browser-profiles"

WEB_DIRECT_SOURCE_SPECS: Dict[str, Dict[str, Any]] = {
    "chatgpt": {
        "display_name": "ChatGPT",
        "adapter_module": "chatgpt_text",
        "adapter_id": "chatgpt",
        "target_url": "https://chatgpt.com/",
        "profile_hints": ("chatgpt.com", "auth.openai.com", "openai.com"),
        "description": "Direct browser-session ChatGPT access using the real ChatGPT web app.",
        "models": [
            {
                "id": "chatgpt-web",
                "display_name": "ChatGPT",
                "code_name": "ChatGPT",
            },
        ],
    },
    "deepseek": {
        "display_name": "DeepSeek",
        "adapter_module": "deepseek_text",
        "adapter_id": "deepseek",
        "target_url": "https://chat.deepseek.com/",
        "profile_hints": ("chat.deepseek.com", "deepseek.com"),
        "description": "Direct browser-session DeepSeek access using the official DeepSeek chat UI.",
        "models": [
            {
                "id": "deepseek-v3.2",
                "display_name": "DeepSeek V3.2",
                "code_name": "Instant",
                "thinking": False,
                "search": False,
            },
            {
                "id": "deepseek-v3.2-thinking",
                "display_name": "DeepSeek V3.2 Thinking",
                "code_name": "Instant",
                "thinking": True,
                "search": False,
            },
            {
                "id": "deepseek-v3.2-search",
                "display_name": "DeepSeek V3.2 Search",
                "code_name": "Instant",
                "thinking": False,
                "search": True,
            },
            {
                "id": "deepseek-v3.2-thinking-search",
                "display_name": "DeepSeek V3.2 Thinking + Search",
                "code_name": "Instant",
                "thinking": True,
                "search": True,
            },
        ],
    },
    "gemini": {
        "display_name": "Gemini",
        "adapter_module": "gemini_text",
        "adapter_id": "gemini",
        "target_url": "https://gemini.google.com/app",
        "profile_hints": ("gemini.google.com", "accounts.google.com", "google.com"),
        "description": "Direct browser-session Gemini access using the official Gemini web app.",
        "models": [
            {
                "id": "gemini-fast",
                "display_name": "Gemini Fast",
                "code_name": "Fast",
            },
        ],
    },
    "zai": {
        "display_name": "z.ai",
        "adapter_module": "zai_is_text",
        "adapter_id": "zai",
        "target_url": "https://chat.z.ai/",
        "profile_hints": ("chat.z.ai", "z.ai", "zai.is"),
        "description": "Direct browser-session z.ai access restricted to the official GLM-family web models.",
        "models": [
            {
                "id": "glm-5v-turbo",
                "display_name": "GLM-5V-Turbo",
                "code_name": "GLM-5V-Turbo",
            },
        ],
    },
}

_DIRECT_CATALOG_CACHE: Dict[str, Any] = {
    "signature": "",
    "catalog": [],
}


def _normalize_string(value: Any) -> str:
    return str(value or "").strip()


def _normalize_bool(value: Any, default: bool = False) -> bool:
    if isinstance(value, bool):
        return value
    if value is None:
        return default
    lowered = str(value).strip().lower()
    if lowered in {"1", "true", "yes", "on"}:
        return True
    if lowered in {"0", "false", "no", "off"}:
        return False
    return default


def _normalize_positive_int(value: Any, default: int, *, minimum: int = 1, maximum: int = 2_147_483_647) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        parsed = default
    return max(minimum, min(maximum, parsed))


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


def discover_reference_root(configured_root: Any = None) -> Optional[Path]:
    candidate_text = _normalize_string(configured_root)
    if candidate_text:
        candidate = Path(candidate_text).expanduser()
        try:
            candidate = candidate.resolve(strict=False)
        except OSError:
            pass
        if candidate.exists() and candidate.is_dir():
            return candidate

    for repo_root in _candidate_repo_roots():
        candidate = repo_root / "references" / "WebAPI"
        if candidate.exists() and candidate.is_dir():
            return candidate
    return None


def _ensure_reference_import_path(source_root: Path) -> None:
    root_text = str(source_root)
    if root_text and root_text not in sys.path:
        sys.path.insert(0, root_text)


def _load_reference_adapter_module(source_root: Path, module_name: str):
    _ensure_reference_import_path(source_root)
    return importlib.import_module(f"webai2api_py.adapters.{module_name}")


def _source_signature(source_root: Optional[Path]) -> str:
    parts = [str(source_root or "")]
    for source_id in WEB_DIRECT_SOURCE_SPECS:
        spec = WEB_DIRECT_SOURCE_SPECS[source_id]
        parts.append(f"{source_id}:{spec.get('adapter_module', '')}:{spec.get('target_url', '')}")
    return "|".join(parts)


def _display_name_for_model(source_display: str, model_name: str) -> str:
    return f"{model_name} [{source_display}]"


def _catalog_item_from_manifest_model(source_id: str, source_spec: Dict[str, Any], model: Any) -> Dict[str, Any]:
    source_display = _normalize_string(source_spec.get("display_name")) or source_id
    base_model_id = _normalize_string(getattr(model, "id", ""))
    code_name = _normalize_string(getattr(model, "code_name", "")) or base_model_id
    description = _normalize_string(source_spec.get("description"))
    return {
        "id": f"{source_id}/{base_model_id}",
        "base_model_id": base_model_id,
        "display_name": _display_name_for_model(source_display, code_name),
        "description": description,
        "adapter_id": source_id,
        "adapter_display_name": source_display,
        "model_type": _normalize_string(getattr(model, "type", "text") or "text").lower() or "text",
        "image_policy": _normalize_string(getattr(model, "image_policy", "optional") or "optional").lower() or "optional",
        "thinking": bool(getattr(model, "thinking", False)),
        "search": bool(getattr(model, "search", False)),
        "providers": list(getattr(model, "providers", []) or []),
        "image_size": _normalize_string(getattr(model, "image_size", "")),
        "url": _normalize_string(getattr(model, "url", "")) or _normalize_string(source_spec.get("target_url", "")),
        "context_length": WEB_DIRECT_DEFAULT_CONTEXT,
        "source_id": source_id,
        "source_label": source_display,
        "target_url": _normalize_string(source_spec.get("target_url", "")),
        "adapter_module": _normalize_string(source_spec.get("adapter_module", "")),
        "code_name": code_name,
    }


def _catalog_item_from_static_model(source_id: str, source_spec: Dict[str, Any], model: Dict[str, Any]) -> Dict[str, Any]:
    source_display = _normalize_string(source_spec.get("display_name")) or source_id
    base_model_id = _normalize_string(model.get("id"))
    code_name = _normalize_string(model.get("code_name")) or _normalize_string(model.get("display_name")) or base_model_id
    return {
        "id": f"{source_id}/{base_model_id}",
        "base_model_id": base_model_id,
        "display_name": _display_name_for_model(source_display, _normalize_string(model.get("display_name")) or code_name),
        "description": _normalize_string(source_spec.get("description")),
        "adapter_id": source_id,
        "adapter_display_name": source_display,
        "model_type": "text",
        "image_policy": "forbidden",
        "thinking": bool(model.get("thinking", False)),
        "search": bool(model.get("search", False)),
        "providers": [],
        "image_size": "",
        "url": _normalize_string(source_spec.get("target_url", "")),
        "context_length": WEB_DIRECT_DEFAULT_CONTEXT,
        "source_id": source_id,
        "source_label": source_display,
        "target_url": _normalize_string(source_spec.get("target_url", "")),
        "adapter_module": _normalize_string(source_spec.get("adapter_module", "")),
        "code_name": code_name,
    }


def get_web_direct_model_catalog(*, source_root: Any = None, force_refresh: bool = False) -> List[Dict[str, Any]]:
    resolved_root = discover_reference_root(source_root)
    signature = _source_signature(resolved_root)
    if not force_refresh and _DIRECT_CATALOG_CACHE["signature"] == signature:
        return [dict(item) for item in _DIRECT_CATALOG_CACHE["catalog"]]

    catalog: List[Dict[str, Any]] = []
    for source_id, source_spec in WEB_DIRECT_SOURCE_SPECS.items():
        static_models = source_spec.get("models")
        if isinstance(static_models, list):
            for model in static_models:
                item = _catalog_item_from_static_model(source_id, source_spec, model)
                if item["base_model_id"]:
                    catalog.append(item)
            continue

        module_name = _normalize_string(source_spec.get("adapter_module"))
        if not module_name or resolved_root is None:
            continue
        try:
            module = _load_reference_adapter_module(resolved_root, module_name)
        except Exception:
            continue
        manifest = getattr(module, "manifest", None)
        models = list(getattr(manifest, "models", []) or [])
        allowed = source_spec.get("allow_model_ids")
        if isinstance(allowed, set):
            models = [model for model in models if _normalize_string(getattr(model, "id", "")) in allowed]
        for model in models:
            item = _catalog_item_from_manifest_model(source_id, source_spec, model)
            if item["model_type"] == "text":
                catalog.append(item)

    _DIRECT_CATALOG_CACHE["signature"] = signature
    _DIRECT_CATALOG_CACHE["catalog"] = [dict(item) for item in catalog]
    return [dict(item) for item in catalog]


def _extract_text_fragments(content: Any) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        fragments: List[str] = []
        for item in content:
            if not isinstance(item, dict):
                continue
            item_type = _normalize_string(item.get("type")).lower()
            if item_type in {"text", "input_text"}:
                text_value = item.get("text")
                if text_value is None:
                    text_value = item.get("value")
                if text_value is not None:
                    fragments.append(str(text_value))
        return "\n".join(fragment for fragment in fragments if fragment)
    return str(content or "")


def build_web_direct_prompt(messages: Iterable[Dict[str, Any]], *, max_messages: int = 18) -> str:
    normalized_messages = [dict(message) for message in messages or [] if isinstance(message, dict)]
    if not normalized_messages:
        return ""

    if len(normalized_messages) > max_messages:
        keep_tail = max(1, max_messages - 2)
        normalized_messages = [normalized_messages[0], {"role": "system", "content": "[earlier conversation omitted for brevity]"}, *normalized_messages[-keep_tail:]]

    lines: List[str] = []
    for message in normalized_messages:
        role = _normalize_string(message.get("role")).lower() or "user"
        label = {
            "system": "System",
            "user": "User",
            "assistant": "Assistant",
            "tool": "Tool",
        }.get(role, role.title())
        text = _extract_text_fragments(message.get("content")).strip()
        if not text:
            continue
        lines.append(f"{label}:\n{text}")
    return "\n\n".join(lines).strip()


def _browser_candidates(configured_path: Any = None) -> List[Dict[str, Any]]:
    candidates: List[Dict[str, Any]] = []
    configured = _normalize_string(configured_path)
    if configured:
        path = Path(configured).expanduser()
        if path.exists():
            lowered = path.name.lower()
            browser_id = "edge" if "edge" in lowered else "chrome"
            user_root = (
                Path.home() / "AppData" / "Local" / "Microsoft" / "Edge" / "User Data"
                if browser_id == "edge"
                else Path.home() / "AppData" / "Local" / "Google" / "Chrome" / "User Data"
            )
            candidates.append(
                {
                    "browser_id": browser_id,
                    "display_name": "Configured Browser",
                    "executable_path": path,
                    "user_data_root": user_root,
                }
            )

    defaults = [
        (
            "chrome",
            "Google Chrome",
            Path(r"C:\Program Files\Google\Chrome\Application\chrome.exe"),
            Path.home() / "AppData" / "Local" / "Google" / "Chrome" / "User Data",
        ),
        (
            "edge",
            "Microsoft Edge",
            Path(r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"),
            Path.home() / "AppData" / "Local" / "Microsoft" / "Edge" / "User Data",
        ),
    ]
    seen = {str(item["executable_path"]).lower() for item in candidates}
    for browser_id, display_name, executable_path, user_data_root in defaults:
        key = str(executable_path).lower()
        if key in seen:
            continue
        if executable_path.exists() and user_data_root.exists():
            candidates.append(
                {
                    "browser_id": browser_id,
                    "display_name": display_name,
                    "executable_path": executable_path,
                    "user_data_root": user_data_root,
                }
            )
    return candidates


def _profile_names(user_data_root: Path) -> List[str]:
    names: List[str] = []
    for candidate in ["Default", "Profile 1", "Profile 2", "Profile 3", "Profile 4", "Profile 5"]:
        if (user_data_root / candidate).exists():
            names.append(candidate)
    return names


def _profile_account_email(user_data_root: Path, profile_name: str) -> str:
    preferences_path = user_data_root / profile_name / "Preferences"
    if not preferences_path.exists():
        return ""
    try:
        data = json.loads(preferences_path.read_text(encoding="utf-8", errors="ignore"))
    except Exception:
        return ""
    account_info = data.get("account_info") or []
    if isinstance(account_info, list):
        for item in account_info:
            email = _normalize_string((item or {}).get("email")).lower()
            if email:
                return email
    return ""


def _copy_sqlite_for_query(path: Path) -> Optional[Path]:
    if not path.exists() or not path.is_file():
        return None
    try:
        temp_dir = Path(tempfile.mkdtemp(prefix="reverie-web-profile-"))
        temp_path = temp_dir / path.name
        shutil.copy2(path, temp_path)
        return temp_path
    except Exception:
        return None


def _count_history_hits(user_data_root: Path, profile_name: str, hints: Iterable[str]) -> int:
    history_path = user_data_root / profile_name / "History"
    copied = _copy_sqlite_for_query(history_path)
    if copied is None:
        return -1000
    try:
        conn = sqlite3.connect(copied)
        try:
            total = 0
            cursor = conn.cursor()
            for hint in hints:
                total += int(cursor.execute("SELECT COUNT(*) FROM urls WHERE url LIKE ?", (f"%{hint}%",)).fetchone()[0] or 0)
            return total
        finally:
            conn.close()
    except Exception:
        return 0
    finally:
        try:
            copied.unlink(missing_ok=True)
            copied.parent.rmdir()
        except Exception:
            pass


def _cookies_db_accessible(user_data_root: Path, profile_name: str) -> bool:
    cookies_path = user_data_root / profile_name / "Network" / "Cookies"
    copied = _copy_sqlite_for_query(cookies_path)
    if copied is None:
        return False
    try:
        return copied.exists()
    finally:
        try:
            copied.unlink(missing_ok=True)
            copied.parent.rmdir()
        except Exception:
            pass


def select_browser_profile(web_config: Any, source_id: str, *, allow_locked_match: bool = False) -> Dict[str, Any]:
    cfg = dict(web_config) if isinstance(web_config, dict) else {}
    requested_profile = _normalize_string(cfg.get("browser_profile"))
    requested_email = _normalize_string(cfg.get("browser_account_email")).lower()
    candidates = _browser_candidates(cfg.get("browser_path"))
    if not candidates:
        raise RuntimeError("No supported Chromium browser was found for direct Web access.")

    source_spec = WEB_DIRECT_SOURCE_SPECS.get(source_id, {})
    hints = tuple(source_spec.get("profile_hints", ()) or ())

    email_matches: List[Dict[str, Any]] = []
    if requested_email:
        for browser in candidates:
            user_data_root = browser["user_data_root"]
            for profile_name in _profile_names(user_data_root):
                if requested_profile and profile_name != requested_profile:
                    continue
                profile_email = _profile_account_email(user_data_root, profile_name)
                if profile_email != requested_email:
                    continue
                email_matches.append(
                    {
                        **browser,
                        "profile_name": profile_name,
                        "profile_email": profile_email,
                        "cookies_accessible": _cookies_db_accessible(user_data_root, profile_name),
                    }
                )

        chrome_matches = [item for item in email_matches if item.get("browser_id") == "chrome"]
        if chrome_matches:
            accessible_chrome_matches = [item for item in chrome_matches if item.get("cookies_accessible")]
            if accessible_chrome_matches:
                candidates = accessible_chrome_matches
            elif allow_locked_match:
                candidates = chrome_matches
            else:
                locked_match = chrome_matches[0]
                raise RuntimeError(
                    f"Chrome profile '{locked_match['profile_name']}' for {requested_email} was found, "
                    "but its live session database is locked by the running browser. "
                    "Close that Chrome profile before direct Web reuse."
                )
        elif email_matches:
            accessible_matches = [item for item in email_matches if item.get("cookies_accessible")]
            if accessible_matches:
                candidates = accessible_matches
            elif allow_locked_match:
                candidates = email_matches
            else:
                locked_match = email_matches[0]
                raise RuntimeError(
                    f"Browser profile '{locked_match['profile_name']}' for {requested_email} was found, "
                    "but its live session database is locked by the running browser. "
                    "Close that browser profile before direct Web reuse."
                )

    best_choice: Optional[Dict[str, Any]] = None
    best_score = -1
    for browser in candidates:
        if "profile_name" in browser:
            profile_name = str(browser["profile_name"])
            user_data_root = Path(browser["user_data_root"])
            profile_email = _normalize_string(browser.get("profile_email")).lower() or _profile_account_email(user_data_root, profile_name)
            score = _count_history_hits(user_data_root, profile_name, hints)
            if score < 0:
                continue
            if score > best_score:
                best_score = score
                best_choice = {
                    **browser,
                    "profile_name": profile_name,
                    "profile_email": profile_email,
                    "cookies_accessible": bool(browser.get("cookies_accessible", False)),
                    "score": score,
                }
            continue

        user_data_root = browser["user_data_root"]
        for profile_name in _profile_names(user_data_root):
            if requested_profile and profile_name != requested_profile:
                continue
            profile_email = _profile_account_email(user_data_root, profile_name)
            if requested_email and profile_email != requested_email:
                continue
            cookies_accessible = _cookies_db_accessible(user_data_root, profile_name)
            if not cookies_accessible and not allow_locked_match:
                continue
            score = _count_history_hits(user_data_root, profile_name, hints)
            if score < 0:
                continue
            if score > best_score:
                best_score = score
                best_choice = {
                    **browser,
                    "profile_name": profile_name,
                    "profile_email": profile_email,
                    "cookies_accessible": cookies_accessible,
                    "score": score,
                }

    if best_choice is not None:
        return best_choice

    browser = candidates[0]
    profile_name = requested_profile or (_profile_names(browser["user_data_root"]) or ["Default"])[0]
    return {
        **browser,
        "profile_name": profile_name,
        "profile_email": _profile_account_email(browser["user_data_root"], profile_name),
        "cookies_accessible": _cookies_db_accessible(browser["user_data_root"], profile_name),
        "score": 0,
    }


def _safe_copy_file(source: Path, destination: Path) -> None:
    try:
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, destination)
    except Exception:
        pass


def _safe_copy_tree(source: Path, destination: Path) -> None:
    if not source.exists():
        return
    for path in source.rglob("*"):
        relative = path.relative_to(source)
        target = destination / relative
        if path.is_dir():
            target.mkdir(parents=True, exist_ok=True)
            continue
        _safe_copy_file(path, target)


def _snapshot_root_for_profile(runtime_root: Path, profile_info: Dict[str, Any]) -> Path:
    return runtime_root / "browser-source-cache" / str(profile_info["browser_id"]) / str(profile_info["profile_name"]).replace(" ", "_")


def _copy_profile_snapshot_from_source(selected: Dict[str, Any], snapshot_root: Path) -> None:
    user_data_root = Path(selected["user_data_root"])
    profile_name = str(selected["profile_name"])
    if snapshot_root.exists():
        shutil.rmtree(snapshot_root, ignore_errors=True)
    snapshot_root.mkdir(parents=True, exist_ok=True)

    _safe_copy_file(user_data_root / "Local State", snapshot_root / "Local State")
    profile_source_root = user_data_root / profile_name
    profile_dest_root = snapshot_root / profile_name
    _safe_copy_tree(profile_source_root, profile_dest_root)


def prepare_runtime_browser_profile(web_config: Any, source_id: str, runtime_root: Path) -> Dict[str, Any]:
    selected = select_browser_profile(web_config, source_id, allow_locked_match=True)
    profile_name = str(selected["profile_name"])
    runtime_browser_root = runtime_root / WEB_DIRECT_RUNTIME_DIRNAME / selected["browser_id"] / profile_name.replace(" ", "_")
    snapshot_root = _snapshot_root_for_profile(runtime_root, selected)
    legacy_snapshot_available = (runtime_browser_root / profile_name).exists()

    if bool(selected.get("cookies_accessible")):
        _copy_profile_snapshot_from_source(selected, snapshot_root)
    elif not (snapshot_root / profile_name).exists() and legacy_snapshot_available:
        if snapshot_root.exists():
            shutil.rmtree(snapshot_root, ignore_errors=True)
        snapshot_root.mkdir(parents=True, exist_ok=True)
        _safe_copy_tree(runtime_browser_root, snapshot_root)
    elif not (snapshot_root / profile_name).exists():
        requested_email = _normalize_string((web_config or {}).get("browser_account_email")).lower() if isinstance(web_config, dict) else ""
        email_hint = f" for {requested_email}" if requested_email else ""
        raise RuntimeError(
            f"Browser profile '{profile_name}'{email_hint} is currently locked and no cached snapshot is available yet. "
            "Close that browser profile once so Reverie can sync it into .reverie\\webai."
        )

    if runtime_browser_root.exists():
        shutil.rmtree(runtime_browser_root, ignore_errors=True)
    runtime_browser_root.mkdir(parents=True, exist_ok=True)
    _safe_copy_tree(snapshot_root, runtime_browser_root)
    profile_dest_root = runtime_browser_root / profile_name

    return {
        **selected,
        "snapshot_root": snapshot_root,
        "snapshot_fallback": not bool(selected.get("cookies_accessible")),
        "runtime_user_data_dir": runtime_browser_root,
        "runtime_profile_dir": profile_dest_root,
    }


def persist_runtime_browser_profile(profile_info: Dict[str, Any]) -> None:
    snapshot_root = Path(profile_info.get("snapshot_root") or "")
    runtime_user_data_dir = Path(profile_info.get("runtime_user_data_dir") or "")
    if not snapshot_root or not runtime_user_data_dir.exists():
        return
    if snapshot_root.exists():
        shutil.rmtree(snapshot_root, ignore_errors=True)
    snapshot_root.mkdir(parents=True, exist_ok=True)
    _safe_copy_tree(runtime_user_data_dir, snapshot_root)


async def _launch_playwright_context(profile_info: Dict[str, Any], headless: bool):
    from playwright.async_api import async_playwright

    playwright = await async_playwright().start()
    chromium = playwright.chromium
    args = [
        f"--profile-directory={profile_info['profile_name']}",
        "--no-first-run",
        "--no-default-browser-check",
        "--disable-blink-features=AutomationControlled",
    ]
    context = await chromium.launch_persistent_context(
        str(profile_info["runtime_user_data_dir"]),
        executable_path=str(profile_info["executable_path"]),
        headless=headless,
        args=args,
        ignore_default_args=["--enable-automation"],
        viewport={"width": 1366, "height": 900},
    )
    page = context.pages[0] if context.pages else await context.new_page()
    page.auth_state = {"is_handling_auth": False}
    return playwright, context, page


async def _close_playwright_context(playwright, context) -> None:
    try:
        if context is not None:
            await context.close()
    except Exception:
        pass
    try:
        if playwright is not None:
            await playwright.stop()
    except Exception:
        pass


def _load_reference_helper_module(source_root: Path, module_name: str):
    _ensure_reference_import_path(source_root)
    return importlib.import_module(module_name)


async def _click_button_if_present(page, name: str, *, timeout_ms: int = 3000) -> bool:
    locator = page.get_by_role("button", name=name).first
    try:
        if await locator.count() == 0:
            return False
        await locator.click(timeout=timeout_ms)
        return True
    except Exception:
        return False


async def _get_body_text(page) -> str:
    try:
        return await page.locator("body").inner_text()
    except Exception:
        return ""


async def _goto_with_domcontentloaded(page, url: str, *, timeout_ms: int = 60000) -> None:
    response = await page.goto(url, wait_until="domcontentloaded", timeout=timeout_ms)
    if response is not None and int(getattr(response, "status", 0) or 0) >= 400:
        raise RuntimeError(f"Website returned HTTP {response.status} for {url}")
    await page.wait_for_timeout(2500)


def _extract_chatgpt_guest_answer(body_text: str) -> str:
    if "ChatGPT said:" not in body_text:
        return ""
    segment = body_text.rsplit("ChatGPT said:", 1)[-1]
    match = re.search(r"^\s*(.+?)(?:\n\nVoice\b|\nChatGPT can make mistakes\b|$)", segment, flags=re.S)
    if not match:
        return ""
    return match.group(1).strip()


def _parse_zai_sse(body_text: str) -> Dict[str, str]:
    answer_parts: List[str] = []
    reasoning_parts: List[str] = []
    for raw_line in body_text.splitlines():
        line = raw_line.strip()
        if not line.startswith("data:"):
            continue
        payload = line[5:].strip()
        if not payload:
            continue
        try:
            data = json.loads(payload)
        except Exception:
            continue
        if not isinstance(data, dict) or data.get("type") != "chat:completion":
            continue
        item = data.get("data") or {}
        phase = _normalize_string(item.get("phase")).lower()
        delta = str(item.get("delta_content") or "")
        if not delta:
            continue
        if phase == "thinking":
            reasoning_parts.append(delta)
        elif phase == "answer":
            answer_parts.append(delta)
    return {
        "text": "".join(answer_parts).strip(),
        "reasoning": "".join(reasoning_parts).strip(),
    }


def _parse_deepseek_sse(body_text: str) -> Dict[str, str]:
    answer_parts: List[str] = []
    reasoning_parts: List[str] = []

    def append_fragments(fragments: Any) -> None:
        if not isinstance(fragments, list):
            return
        for fragment in fragments:
            if not isinstance(fragment, dict):
                continue
            fragment_type = _normalize_string(fragment.get("type")).upper()
            content = fragment.get("content")
            if not isinstance(content, str) or not content:
                continue
            if fragment_type == "THINK":
                reasoning_parts.append(content)
            elif fragment_type == "RESPONSE":
                answer_parts.append(content)

    for raw_line in body_text.splitlines():
        line = raw_line.strip()
        if not line.startswith("data:"):
            continue
        payload = line[5:].strip()
        if not payload or payload == "{}":
            continue
        try:
            data = json.loads(payload)
        except Exception:
            continue
        if not isinstance(data, dict):
            continue

        value = data.get("v")
        if isinstance(value, dict):
            response = value.get("response")
            if isinstance(response, dict):
                append_fragments(response.get("fragments"))
        if data.get("p") == "response/fragments" and data.get("o") == "APPEND":
            append_fragments(value)
        if data.get("o") == "BATCH" and data.get("p") == "response" and isinstance(value, list):
            for patch in value:
                if not isinstance(patch, dict):
                    continue
                if patch.get("p") == "fragments" and patch.get("o") == "APPEND":
                    append_fragments(patch.get("v"))

    return {
        "text": "".join(answer_parts).strip(),
        "reasoning": "".join(reasoning_parts).strip(),
    }


def _extract_lmarena_auth_cookie_value(cookies: Iterable[Dict[str, Any]]) -> tuple[str, List[str], List[str]]:
    cookie_parts: List[tuple[int, str, str, str]] = []
    for item in cookies or []:
        if not isinstance(item, dict):
            continue
        name = _normalize_string(item.get("name"))
        if not name.startswith("arena-auth-prod-v1"):
            continue
        value = _normalize_string(item.get("value"))
        if not value:
            continue
        suffix_match = re.search(r"\.(\d+)$", name)
        order = int(suffix_match.group(1)) if suffix_match else -1
        cookie_parts.append((order, name, value, _normalize_string(item.get("domain"))))

    if not cookie_parts:
        return "", [], []

    names = [name for _, name, _, _ in cookie_parts]
    domains = sorted({domain for _, _, _, domain in cookie_parts if domain})
    exact = next((value for _, name, value, _ in cookie_parts if name == "arena-auth-prod-v1"), "")
    if exact:
        return exact, names, domains

    ordered_values = [
        value
        for order, _, value, _ in sorted(
            cookie_parts,
            key=lambda part: part[0] if part[0] >= 0 else 1_000_000,
        )
    ]
    return "".join(ordered_values), names, domains


def _decode_base64_json_cookie(raw_value: Any) -> Dict[str, Any]:
    raw = _normalize_string(raw_value)
    if not raw:
        return {}
    if raw.startswith("base64-"):
        raw = raw[7:]
    padding = "=" * (-len(raw) % 4)
    try:
        decoded = base64.b64decode(raw + padding).decode("utf-8", errors="ignore")
        payload = json.loads(decoded)
        return payload if isinstance(payload, dict) else {}
    except Exception:
        return {}


def _inspect_browser_profile_cookie_inventory(profile_info: Dict[str, Any]) -> Dict[str, Any]:
    result = {
        "source_profile_cookie_db_accessible": False,
        "source_profile_arena_auth_cookie_names": [],
        "source_profile_google_auth_cookie_names": [],
    }

    user_data_root = Path(profile_info.get("user_data_root") or "")
    profile_name = _normalize_string(profile_info.get("profile_name"))
    if not user_data_root.exists() or not profile_name:
        return result

    cookies_path = user_data_root / profile_name / "Network" / "Cookies"
    copied = _copy_sqlite_for_query(cookies_path)
    if copied is None:
        return result

    google_cookie_names = {
        "SID",
        "HSID",
        "SSID",
        "SAPISID",
        "APISID",
        "LSID",
        "__Secure-1PSID",
        "__Secure-3PSID",
        "__Secure-1PAPISID",
        "__Secure-3PAPISID",
        "__Secure-1PSIDTS",
        "__Secure-3PSIDTS",
    }

    try:
        conn = sqlite3.connect(copied)
        try:
            cursor = conn.cursor()
            rows = cursor.execute(
                """
                SELECT host_key, name
                FROM cookies
                WHERE host_key LIKE '%arena.ai%'
                   OR host_key LIKE '%google.com%'
                   OR host_key = 'accounts.google.com'
                """
            ).fetchall()
        finally:
            conn.close()
    except Exception:
        rows = []
    finally:
        try:
            copied.unlink(missing_ok=True)
            copied.parent.rmdir()
        except Exception:
            pass

    arena_cookie_names = sorted(
        {
            _normalize_string(name)
            for host_key, name in rows
            if "arena.ai" in _normalize_string(host_key).lower() and _normalize_string(name).startswith("arena-auth-prod-v1")
        }
    )
    google_auth_cookie_names = sorted(
        {
            _normalize_string(name)
            for host_key, name in rows
            if "google.com" in _normalize_string(host_key).lower() and _normalize_string(name) in google_cookie_names
        }
    )
    result["source_profile_cookie_db_accessible"] = True
    result["source_profile_arena_auth_cookie_names"] = arena_cookie_names
    result["source_profile_google_auth_cookie_names"] = google_auth_cookie_names
    return result


async def _inspect_lmarena_auth_state(page, context, *, source_cookie_inventory: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    cookies = await context.cookies(["https://arena.ai/", "https://auth.arena.ai/", "https://accounts.google.com/"])
    arena_cookie_value, arena_cookie_names, arena_cookie_domains = _extract_lmarena_auth_cookie_value(cookies)
    arena_payload = _decode_base64_json_cookie(arena_cookie_value)
    user_payload = arena_payload.get("user") if isinstance(arena_payload.get("user"), dict) else {}
    google_cookie_names = {
        "SID",
        "HSID",
        "SSID",
        "SAPISID",
        "APISID",
        "LSID",
        "__Secure-1PSID",
        "__Secure-3PSID",
        "__Secure-1PAPISID",
        "__Secure-3PAPISID",
    }
    google_session_cookies = sorted(
        {
            _normalize_string(item.get("name"))
            for item in cookies
            if "google.com" in _normalize_string(item.get("domain")).lower() and _normalize_string(item.get("name")) in google_cookie_names
        }
    )
    body_text = await _get_body_text(page)
    result = {
        "arena_cookie_present": bool(arena_cookie_names),
        "arena_cookie_names": arena_cookie_names,
        "arena_cookie_domain": ", ".join(arena_cookie_domains),
        "arena_session_anonymous": bool(user_payload.get("is_anonymous")),
        "arena_session_email": _normalize_string(user_payload.get("email")),
        "arena_session_user_id": _normalize_string(user_payload.get("id") or user_payload.get("sub")),
        "google_web_signed_in": bool(google_session_cookies),
        "google_session_cookies": google_session_cookies,
        "page_login_visible": "Login or Create Account" in body_text or "\nLogin\n" in body_text,
        "page_url": page.url,
    }
    if isinstance(source_cookie_inventory, dict):
        result.update(source_cookie_inventory)
    return result


def _format_lmarena_auth_error(auth_state: Dict[str, Any]) -> str:
    source_arena_cookie_names = list(auth_state.get("source_profile_arena_auth_cookie_names") or [])
    source_google_cookie_names = list(auth_state.get("source_profile_google_auth_cookie_names") or [])

    if source_arena_cookie_names and not auth_state.get("arena_cookie_present"):
        return (
            "The selected system browser profile has arena auth-cookie entries in its source cookie database, "
            "but the live automation session could not reuse them. "
            "Recent Chrome cookie protections can block copied automation profiles from inheriting real-profile auth state. "
            "Run /web login lmarena once to establish a dedicated Reverie arena session under .reverie\\webai."
        )
    if source_google_cookie_names and not auth_state.get("google_web_signed_in"):
        return (
            "The selected system browser profile has Google sign-in cookies in its source cookie database, "
            "but the live automation session still did not surface a reusable Google web session for arena. "
            "Run /web login lmarena once to complete a dedicated Reverie login handoff under .reverie\\webai."
        )
    if auth_state.get("arena_cookie_present") and auth_state.get("arena_session_anonymous"):
        if not auth_state.get("google_web_signed_in"):
            return (
                "LMArena runtime only has an anonymous arena session cookie. "
                "No reusable signed-in Google web-session cookies were found, so Google OAuth cannot auto-complete. "
                "Run /web login lmarena once inside Reverie's runtime browser to persist a real arena login under .reverie\\webai."
            )
        return (
            "LMArena runtime has an anonymous arena session cookie, but the page still requires completing Google OAuth. "
            "Run /web login lmarena once to finish the sign-in flow inside Reverie's runtime browser."
        )
    if auth_state.get("google_web_signed_in"):
        return (
            "LMArena still requested login even though Google web-session cookies were detected. "
            "Run /web login lmarena once so Reverie can complete and persist the arena OAuth handoff."
        )
    return (
        "LMArena currently requires logging in before Direct chat requests can be sent. "
        "Run /web login lmarena to complete that login in Reverie's runtime browser."
    )


def format_web_auth_diagnosis(source_id: str, auth_state: Dict[str, Any]) -> str:
    if _normalize_string(source_id) == "lmarena":
        return _format_lmarena_auth_error(auth_state)
    return ""


def _pick_free_tcp_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as handle:
        handle.bind(("127.0.0.1", 0))
        return int(handle.getsockname()[1])


def _ensure_windows_junction(link_path: Path, target_path: Path) -> None:
    link_path.parent.mkdir(parents=True, exist_ok=True)
    if link_path.exists():
        return
    target_literal = str(target_path).replace("'", "''")
    link_literal = str(link_path).replace("'", "''")
    subprocess.run(
        [
            "powershell",
            "-NoProfile",
            "-Command",
            (
                f"$target = '{target_literal}'; "
                f"$link = '{link_literal}'; "
                "if (Test-Path -LiteralPath $link) { exit 0 }; "
                "New-Item -ItemType Junction -Path $link -Target $target | Out-Null"
            ),
        ],
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        check=True,
    )


def _can_use_native_source_bridge(profile_info: Dict[str, Any]) -> bool:
    if os.name != "nt":
        return False
    browser_id = _normalize_string(profile_info.get("browser_id")).lower()
    executable_path = Path(_normalize_string(profile_info.get("executable_path"))).expanduser()
    user_data_root = Path(_normalize_string(profile_info.get("user_data_root"))).expanduser()
    return browser_id in {"chrome", "edge"} and executable_path.exists() and user_data_root.exists()


def _wait_for_open_tcp_port(port: int, *, timeout_seconds: int = 20) -> None:
    deadline = time.time() + max(3, timeout_seconds)
    last_error = ""
    while time.time() < deadline:
        try:
            with socket.create_connection(("127.0.0.1", port), timeout=1):
                return
        except OSError as exc:
            last_error = str(exc)
            time.sleep(0.25)
    raise RuntimeError(f"Timed out waiting for browser DevTools port {port}: {last_error}")


async def _launch_native_source_bridge_context(profile_info: Dict[str, Any], *, runtime_root: Path, headless: bool):
    from playwright.async_api import async_playwright

    if not _can_use_native_source_bridge(profile_info):
        raise RuntimeError("Native source-browser bridge is not available for the selected profile.")

    link_root = runtime_root / "browser-source-bridges" / str(profile_info["browser_id"]) / str(profile_info["profile_name"]).replace(" ", "_")
    linked_user_data_root = link_root / "User Data"
    _ensure_windows_junction(linked_user_data_root, Path(profile_info["user_data_root"]))
    port = _pick_free_tcp_port()
    command = [
        str(profile_info["executable_path"]),
        f"--remote-debugging-port={port}",
        f"--user-data-dir={linked_user_data_root}",
        f"--profile-directory={profile_info['profile_name']}",
        "--no-first-run",
        "--no-default-browser-check",
        "about:blank",
    ]
    if headless:
        command.insert(-1, "--headless=new")

    process = subprocess.Popen(
        command,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        creationflags=getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0) if os.name == "nt" else 0,
    )

    try:
        await asyncio.to_thread(_wait_for_open_tcp_port, port, timeout_seconds=20)
    except Exception:
        try:
            process.terminate()
            process.wait(timeout=5)
        except Exception:
            try:
                process.kill()
            except Exception:
                pass
        raise

    playwright = await async_playwright().start()
    try:
        browser = await playwright.chromium.connect_over_cdp(f"http://127.0.0.1:{port}")
        context = browser.contexts[0] if browser.contexts else None
        if context is None:
            raise RuntimeError("Native source-browser bridge connected, but no browser context was exposed.")
        page = context.pages[0] if context.pages else await context.new_page()
        page.auth_state = {"is_handling_auth": False}
        return playwright, browser, context, page, process
    except Exception:
        try:
            await playwright.stop()
        except Exception:
            pass
        try:
            process.terminate()
            process.wait(timeout=5)
        except Exception:
            try:
                process.kill()
            except Exception:
                pass
        raise


async def _close_native_source_bridge(playwright, browser, process) -> None:
    try:
        if browser is not None:
            await browser.close()
    except Exception:
        pass
    try:
        if playwright is not None:
            await playwright.stop()
    except Exception:
        pass
    try:
        if process is not None:
            process.terminate()
            process.wait(timeout=5)
    except Exception:
        try:
            process.kill()
        except Exception:
            pass


async def _run_chatgpt_best_effort(
    *,
    model_item: Dict[str, Any],
    prompt: str,
    headless: bool,
    profile_info: Dict[str, Any],
) -> Dict[str, Any]:
    playwright = None
    context = None
    try:
        playwright, context, page = await _launch_playwright_context(profile_info, headless=headless)
        await _goto_with_domcontentloaded(page, model_item.get("target_url", "https://chatgpt.com/"))
        await _click_button_if_present(page, "Accept all")
        await _click_button_if_present(page, "Reject non-essential")

        input_locator = page.locator(".ProseMirror[contenteditable='true']").first
        await input_locator.wait_for(state="visible", timeout=15000)
        await input_locator.click(timeout=5000)
        await page.keyboard.insert_text(prompt)

        sent = await _click_button_if_present(page, "Send prompt", timeout_ms=5000)
        if not sent:
            await page.keyboard.press("Enter")

        deadline = time.time() + 120
        last_answer = ""
        stable_count = 0
        while time.time() < deadline:
            body_text = await _get_body_text(page)
            answer = _extract_chatgpt_guest_answer(body_text)
            if answer:
                if answer == last_answer:
                    stable_count += 1
                    if stable_count >= 2:
                        return {"text": answer}
                else:
                    last_answer = answer
                    stable_count = 0
            await asyncio.sleep(1.5)

        if last_answer:
            return {"text": last_answer}
        return {"error": "ChatGPT guest response was not detected before timeout.", "retryable": True}
    finally:
        await _close_playwright_context(playwright, context)


async def _run_lmarena_best_effort(
    *,
    source_root: Path,
    model_item: Dict[str, Any],
    prompt: str,
    headless: bool,
    profile_info: Dict[str, Any],
    runtime_root: Path,
    timeout_seconds: int,
) -> Dict[str, Any]:
    source_cookie_inventory = _inspect_browser_profile_cookie_inventory(profile_info)
    native_bridge_error = ""

    if _can_use_native_source_bridge(profile_info):
        native_playwright = None
        native_browser = None
        native_context = None
        native_process = None
        try:
            native_playwright, native_browser, native_context, native_page, native_process = await _launch_native_source_bridge_context(
                profile_info,
                runtime_root=runtime_root,
                headless=headless,
            )
            native_result = await _run_lmarena_page_flow(
                page=native_page,
                context=native_context,
                source_root=source_root,
                model_item=model_item,
                prompt=prompt,
                timeout_seconds=timeout_seconds,
                source_cookie_inventory=source_cookie_inventory,
            )
            if _normalize_string(native_result.get("text")) or not bool(native_result.get("retryable", False)):
                native_result["auth_mode"] = "native-source-bridge"
                return native_result
            native_bridge_error = _normalize_string(native_result.get("error"))
        except Exception as exc:
            native_bridge_error = str(exc)
        finally:
            await _close_native_source_bridge(native_playwright, native_browser, native_process)

    playwright = None
    context = None
    try:
        playwright, context, page = await _launch_playwright_context(profile_info, headless=headless)
        result = await _run_lmarena_page_flow(
            page=page,
            context=context,
            source_root=source_root,
            model_item=model_item,
            prompt=prompt,
            timeout_seconds=timeout_seconds,
            source_cookie_inventory=source_cookie_inventory,
        )
        if native_bridge_error and not _normalize_string(result.get("error")):
            result["bridge_error"] = native_bridge_error
        elif native_bridge_error and bool(result.get("retryable", False)):
            result["error"] = f"{_normalize_string(result.get('error'))} Native source-bridge attempt also failed: {native_bridge_error}".strip()
        result["auth_mode"] = "runtime-copy"
        return result
    finally:
        await _close_playwright_context(playwright, context)


async def _run_lmarena_page_flow(
    *,
    page,
    context,
    source_root: Path,
    model_item: Dict[str, Any],
    prompt: str,
    timeout_seconds: int,
    source_cookie_inventory: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    await _goto_with_domcontentloaded(page, model_item.get("target_url", "https://arena.ai/text/direct"))
    await _click_button_if_present(page, "Accept Cookies", timeout_ms=5000)
    await _click_button_if_present(page, "Close", timeout_ms=2000)
    auth_state = await _inspect_lmarena_auth_state(page, context, source_cookie_inventory=source_cookie_inventory)
    if auth_state.get("page_login_visible") and not auth_state.get("arena_cookie_present") and not auth_state.get("google_web_signed_in"):
        return {
            "error": _format_lmarena_auth_error(auth_state),
            "retryable": False,
            "auth_state": auth_state,
        }
    textarea = page.locator("textarea").first
    try:
        await textarea.wait_for(state="visible", timeout=15000)
    except Exception:
        body_text = await _get_body_text(page)
        if "Login or Create Account" in body_text or "Continue with Google" in body_text or "Login" in body_text:
            return {
                "error": _format_lmarena_auth_error(auth_state),
                "retryable": False,
                "auth_state": auth_state,
            }
        return {
            "error": "LMArena input box did not become available.",
            "retryable": True,
            "auth_state": auth_state,
        }
    await textarea.fill(prompt)

    request_error = ""
    try:
        async with page.expect_response(
            lambda r: "/nextjs-api/stream" in r.url and r.request.method == "POST",
            timeout=max(30000, int(timeout_seconds * 1000)),
        ) as info:
            await page.locator('button[type="submit"]').first.click(timeout=10000)
        response = await info.value
        body = await response.text()
        shared = _load_reference_helper_module(source_root, "webai2api_py.adapters.shared")
        parsed = shared.parse_lmarena_text_response(body)
        text = _normalize_string((parsed or {}).get("text"))
        if text:
            result = {"text": text, "auth_state": auth_state}
            reasoning = _normalize_string((parsed or {}).get("reasoning"))
            if reasoning:
                result["reasoning"] = reasoning
            return result
    except Exception as exc:
        request_error = str(exc)

    await page.wait_for_timeout(2000)
    body_text = await _get_body_text(page)
    if "Login or Create Account" in body_text or "Continue with Google" in body_text:
        return {
            "error": _format_lmarena_auth_error(auth_state),
            "retryable": False,
            "auth_state": auth_state,
        }
    if "intercepts pointer events" in request_error and auth_state.get("page_login_visible"):
        return {
            "error": _format_lmarena_auth_error(auth_state),
            "retryable": False,
            "auth_state": auth_state,
        }

    message = "LMArena did not return a completion before timeout."
    if request_error:
        message = f"{message} Request detail: {request_error}"
    return {
        "error": message,
        "retryable": True,
        "auth_state": auth_state,
    }


async def _set_deepseek_toggle(page, name: str, target_state: bool) -> None:
    locator = page.get_by_role("button", name=name).first
    if await locator.count() == 0:
        return
    class_name = str(await locator.get_attribute("class") or "")
    selected = "selected" in class_name.lower()
    if selected != target_state:
        await locator.click(timeout=5000)
        await page.wait_for_timeout(500)


async def _run_deepseek_best_effort(
    *,
    model_item: Dict[str, Any],
    prompt: str,
    headless: bool,
    profile_info: Dict[str, Any],
    timeout_seconds: int,
) -> Dict[str, Any]:
    playwright = None
    context = None
    try:
        playwright, context, page = await _launch_playwright_context(profile_info, headless=headless)
        await _goto_with_domcontentloaded(page, model_item.get("target_url", "https://chat.deepseek.com/"))
        await _click_button_if_present(page, "Accept all cookies")
        await _click_button_if_present(page, "Necessary cookies only")

        textarea = page.locator("textarea").first
        await textarea.wait_for(state="visible", timeout=15000)
        await _set_deepseek_toggle(page, "DeepThink", bool(model_item.get("thinking")))
        await _set_deepseek_toggle(page, "Search", bool(model_item.get("search")))
        await textarea.fill(prompt)

        async with page.expect_response(
            lambda r: "/api/v0/chat/completion" in r.url and r.request.method == "POST",
            timeout=max(30000, int(timeout_seconds * 1000)),
        ) as info:
            await page.keyboard.press("Enter")
        response = await info.value
        body = await response.text()
        parsed = _parse_deepseek_sse(body)
        text = _normalize_string(parsed.get("text"))
        reasoning = _normalize_string(parsed.get("reasoning"))
        if not text:
            return {"error": "DeepSeek returned an empty reply.", "retryable": True}
        result = {"text": text}
        if reasoning:
            result["reasoning"] = reasoning
        return result
    finally:
        await _close_playwright_context(playwright, context)


async def _select_gemini_mode(page, mode_name: str) -> bool:
    normalized_mode = _normalize_string(mode_name)
    if not normalized_mode or normalized_mode.lower() == "fast":
        return True
    mode_button = page.get_by_role("button", name="Open mode picker").first
    if await mode_button.count() == 0:
        return False
    await mode_button.click(timeout=5000)
    await page.wait_for_timeout(700)
    menu_item = page.get_by_role("menuitem").filter(has_text=re.compile(rf"^\s*{re.escape(normalized_mode)}")).first
    if await menu_item.count() > 0:
        disabled = _normalize_string(await menu_item.get_attribute("aria-disabled")).lower() == "true"
        if disabled:
            await page.keyboard.press("Escape")
            return False
        await menu_item.click(timeout=5000)
        await page.wait_for_timeout(700)
        return True
    await page.keyboard.press("Escape")
    return False


async def _run_gemini_best_effort(
    *,
    source_root: Path,
    model_item: Dict[str, Any],
    prompt: str,
    headless: bool,
    profile_info: Dict[str, Any],
    timeout_seconds: int,
) -> Dict[str, Any]:
    playwright = None
    context = None
    try:
        playwright, context, page = await _launch_playwright_context(profile_info, headless=headless)
        await _goto_with_domcontentloaded(page, model_item.get("target_url", "https://gemini.google.com/app?hl=en"))
        if "consent.google.com" in page.url:
            await _click_button_if_present(page, "Accept all", timeout_ms=5000)
            await page.wait_for_timeout(5000)

        textbox = page.get_by_role("textbox").first
        await textbox.wait_for(state="visible", timeout=20000)
        selected_mode = await _select_gemini_mode(page, _normalize_string(model_item.get("code_name")))
        if not selected_mode:
            return {
                "error": f"Gemini mode '{_normalize_string(model_item.get('code_name'))}' is not available for the current browser session.",
                "retryable": False,
            }
        await textbox.click(timeout=5000)
        await page.keyboard.insert_text(prompt)

        async with page.expect_response(
            lambda r: "BardFrontendService/StreamGenerate" in r.url and r.request.method == "POST",
            timeout=max(30000, int(timeout_seconds * 1000)),
        ) as info:
            await _click_button_if_present(page, "Send message", timeout_ms=10000)
        response = await info.value
        body = await response.body()
        shared = _load_reference_helper_module(source_root, "webai2api_py.adapters.shared")
        parsed = shared.get_final_ai_text_from_response(body)
        text = _normalize_string((parsed or {}).get("text"))
        if not text:
            return {"error": "Gemini returned an empty reply.", "retryable": True}
        result = {"text": text}
        reasoning = _normalize_string((parsed or {}).get("reasoning"))
        if reasoning:
            result["reasoning"] = reasoning
        return result
    finally:
        await _close_playwright_context(playwright, context)


async def _run_zai_best_effort(
    *,
    model_item: Dict[str, Any],
    prompt: str,
    headless: bool,
    profile_info: Dict[str, Any],
    timeout_seconds: int,
) -> Dict[str, Any]:
    playwright = None
    context = None
    try:
        playwright, context, page = await _launch_playwright_context(profile_info, headless=headless)
        await _goto_with_domcontentloaded(page, model_item.get("target_url", "https://chat.z.ai/"))
        await _click_button_if_present(page, "New Chat", timeout_ms=5000)
        await page.wait_for_timeout(1200)

        textarea = page.locator("textarea").first
        await textarea.wait_for(state="visible", timeout=15000)
        await textarea.fill(prompt)

        async with page.expect_response(
            lambda r: "/api/v2/chat/completions" in r.url and r.request.method == "POST",
            timeout=max(30000, int(timeout_seconds * 1000)),
        ) as info:
            await page.locator('button[type="submit"]').first.click(timeout=10000)
        response = await info.value
        body = await response.text()
        parsed = _parse_zai_sse(body)
        text = _normalize_string(parsed.get("text"))
        if not text:
            return {"error": "z.ai returned an empty reply.", "retryable": True}
        result = {"text": text}
        reasoning = _normalize_string(parsed.get("reasoning"))
        if reasoning:
            result["reasoning"] = reasoning
        return result
    finally:
        await _close_playwright_context(playwright, context)


def execute_web_direct_completion(
    *,
    web_config: Any,
    model_id: str,
    messages: Iterable[Dict[str, Any]],
    source_root: Any = None,
) -> Dict[str, Any]:
    catalog = get_web_direct_model_catalog(source_root=source_root)
    selected = next((item for item in catalog if _normalize_string(item.get("id")) == _normalize_string(model_id)), None)
    if selected is None:
        raise ValueError(f"Unsupported Web direct model: {model_id}")

    prompt = build_web_direct_prompt(messages)
    if not prompt:
        raise ValueError("Web direct prompt is empty")

    source_id = _normalize_string(selected.get("source_id"))
    source_spec = WEB_DIRECT_SOURCE_SPECS.get(source_id)
    if source_spec is None:
        raise ValueError(f"Unknown Web source: {source_id}")

    resolved_source_root = discover_reference_root(source_root or (web_config.get("source_root") if isinstance(web_config, dict) else ""))
    if source_id in {"gemini"} and resolved_source_root is None:
        raise RuntimeError("Bundled Web reference source was not found.")

    cfg = dict(web_config) if isinstance(web_config, dict) else {}
    timeout_seconds = _normalize_positive_int(cfg.get("timeout"), 1200, minimum=30, maximum=86_400)
    headless = _normalize_bool(cfg.get("headless"), False)
    runtime_root = Path(_normalize_string(cfg.get("runtime_root"))).expanduser() if _normalize_string(cfg.get("runtime_root")) else None
    if runtime_root is None:
        runtime_root = Path.cwd() / ".reverie" / "webai"
    runtime_root.mkdir(parents=True, exist_ok=True)
    profile_info = prepare_runtime_browser_profile(cfg, source_id, runtime_root)

    if source_id == "chatgpt":
        result = asyncio.run(
            _run_chatgpt_best_effort(
                model_item=selected,
                prompt=prompt,
                headless=headless,
                profile_info=profile_info,
            )
        )
    elif source_id == "lmarena":
        result = asyncio.run(
            _run_lmarena_best_effort(
                source_root=resolved_source_root,
                model_item=selected,
                prompt=prompt,
                timeout_seconds=timeout_seconds,
                headless=headless,
                profile_info=profile_info,
                runtime_root=runtime_root,
            )
        )
    elif source_id == "deepseek":
        result = asyncio.run(
            _run_deepseek_best_effort(
                model_item=selected,
                prompt=prompt,
                timeout_seconds=timeout_seconds,
                headless=headless,
                profile_info=profile_info,
            )
        )
    elif source_id == "gemini":
        result = asyncio.run(
            _run_gemini_best_effort(
                source_root=resolved_source_root,
                model_item=selected,
                prompt=prompt,
                timeout_seconds=timeout_seconds,
                headless=headless,
                profile_info=profile_info,
            )
        )
    elif source_id == "zai":
        result = asyncio.run(
            _run_zai_best_effort(
                model_item=selected,
                prompt=prompt,
                timeout_seconds=timeout_seconds,
                headless=headless,
                profile_info=profile_info,
            )
        )
    else:
        raise ValueError(f"Unsupported Web source: {source_id}")

    if not isinstance(result, dict):
        raise RuntimeError("Web direct adapter returned an invalid result.")
    normalized = dict(result)
    normalized["source_id"] = source_id
    normalized["browser_id"] = profile_info.get("browser_id", "")
    normalized["browser_profile"] = profile_info.get("profile_name", "")
    normalized["browser_account_email"] = profile_info.get("profile_email", "")
    normalized["browser_path"] = str(profile_info.get("executable_path", "") or "")
    normalized["runtime_user_data_dir"] = str(profile_info.get("runtime_user_data_dir", "") or "")
    return normalized


async def _run_interactive_login_session_async(
    *,
    source_id: str,
    web_config: Any,
    source_root: Any = None,
) -> Dict[str, Any]:
    cfg = dict(web_config) if isinstance(web_config, dict) else {}
    source_spec = WEB_DIRECT_SOURCE_SPECS.get(source_id)
    if source_spec is None:
        raise ValueError(f"Unknown Web source: {source_id}")

    runtime_root = Path(_normalize_string(cfg.get("runtime_root"))).expanduser() if _normalize_string(cfg.get("runtime_root")) else None
    if runtime_root is None:
        runtime_root = Path.cwd() / ".reverie" / "webai"
    runtime_root.mkdir(parents=True, exist_ok=True)
    profile_info = prepare_runtime_browser_profile(cfg, source_id, runtime_root)

    playwright = None
    context = None
    page = None
    try:
        playwright, context, page = await _launch_playwright_context(profile_info, headless=False)
        await _goto_with_domcontentloaded(page, _normalize_string(source_spec.get("target_url")) or "https://arena.ai/text/direct")

        if source_id == "lmarena":
            try:
                textarea = page.locator("textarea").first
                await textarea.wait_for(state="visible", timeout=10000)
                await textarea.fill("login bootstrap")
                await page.locator('button[type="submit"]').first.click(timeout=5000)
                await page.wait_for_timeout(1500)
            except Exception:
                pass

        await asyncio.to_thread(
            input,
            f"Complete the {source_id} login in the opened browser, then press Enter here to continue...",
        )

        auth_state: Dict[str, Any] = {}
        if source_id == "lmarena":
            auth_state = await _inspect_lmarena_auth_state(
                page,
                context,
                source_cookie_inventory=_inspect_browser_profile_cookie_inventory(profile_info),
            )

        persist_runtime_browser_profile(profile_info)
        return {
            "success": True,
            "source_id": source_id,
            "browser_profile": profile_info.get("profile_name", ""),
            "browser_account_email": profile_info.get("profile_email", ""),
            "runtime_user_data_dir": str(profile_info.get("runtime_user_data_dir", "") or ""),
            "auth_state": auth_state,
        }
    except Exception as exc:
        return {
            "success": False,
            "source_id": source_id,
            "error": str(exc),
            "browser_profile": profile_info.get("profile_name", ""),
            "browser_account_email": profile_info.get("profile_email", ""),
            "runtime_user_data_dir": str(profile_info.get("runtime_user_data_dir", "") or ""),
        }
    finally:
        await _close_playwright_context(playwright, context)


def run_interactive_web_login_session(
    web_config: Any,
    source_id: str,
    *,
    source_root: Any = None,
) -> Dict[str, Any]:
    return asyncio.run(
        _run_interactive_login_session_async(
            source_id=source_id,
            web_config=web_config,
            source_root=source_root,
        )
    )


def inspect_web_runtime_auth_state(
    web_config: Any,
    source_id: str,
) -> Dict[str, Any]:
    cfg = dict(web_config) if isinstance(web_config, dict) else {}
    runtime_root = Path(_normalize_string(cfg.get("runtime_root"))).expanduser() if _normalize_string(cfg.get("runtime_root")) else None
    if runtime_root is None:
        runtime_root = Path.cwd() / ".reverie" / "webai"
    runtime_root.mkdir(parents=True, exist_ok=True)
    profile_info = prepare_runtime_browser_profile(cfg, source_id, runtime_root)

    async def _inspect() -> Dict[str, Any]:
        playwright = None
        context = None
        try:
            playwright, context, page = await _launch_playwright_context(profile_info, headless=True)
            await _goto_with_domcontentloaded(page, _normalize_string(WEB_DIRECT_SOURCE_SPECS.get(source_id, {}).get("target_url")) or "https://arena.ai/text/direct")
            auth_state: Dict[str, Any] = {}
            if source_id == "lmarena":
                auth_state = await _inspect_lmarena_auth_state(
                    page,
                    context,
                    source_cookie_inventory=_inspect_browser_profile_cookie_inventory(profile_info),
                )
            return auth_state
        finally:
            await _close_playwright_context(playwright, context)

    result = asyncio.run(_inspect())
    result.update(
        {
            "source_id": source_id,
            "browser_profile": profile_info.get("profile_name", ""),
            "browser_account_email": profile_info.get("profile_email", ""),
        }
    )
    return result
