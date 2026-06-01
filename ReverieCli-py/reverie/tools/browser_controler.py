"""Browser Controler tool.

Provides a browser-focused automation and diagnostics surface for opening pages,
driving visible browser UI, inspecting page text, opening DevTools, and checking
web/server endpoints without turning the workflow into a static fetch-only pass.
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
import time
import webbrowser
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup

from .base import BaseTool, ToolResult
from ..config import get_project_data_dir


IS_WINDOWS = os.name == "nt"

if IS_WINDOWS:
    import ctypes
    import winreg
    from ctypes import wintypes

    ENUM_WINDOWS_PROC = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
    user32 = ctypes.windll.user32
    kernel32 = ctypes.windll.kernel32

    class RECT(ctypes.Structure):
        _fields_ = [
            ("left", ctypes.c_long),
            ("top", ctypes.c_long),
            ("right", ctypes.c_long),
            ("bottom", ctypes.c_long),
        ]

    user32.OpenClipboard.argtypes = (ctypes.c_void_p,)
    user32.OpenClipboard.restype = wintypes.BOOL
    user32.EmptyClipboard.argtypes = ()
    user32.EmptyClipboard.restype = wintypes.BOOL
    user32.CloseClipboard.argtypes = ()
    user32.CloseClipboard.restype = wintypes.BOOL
    user32.GetClipboardData.argtypes = (wintypes.UINT,)
    user32.GetClipboardData.restype = ctypes.c_void_p
    user32.SetClipboardData.argtypes = (wintypes.UINT, ctypes.c_void_p)
    user32.SetClipboardData.restype = ctypes.c_void_p
    user32.GetForegroundWindow.argtypes = ()
    user32.GetForegroundWindow.restype = wintypes.HWND
    user32.GetWindowTextLengthW.argtypes = (wintypes.HWND,)
    user32.GetWindowTextLengthW.restype = ctypes.c_int
    user32.GetWindowTextW.argtypes = (wintypes.HWND, wintypes.LPWSTR, ctypes.c_int)
    user32.GetWindowTextW.restype = ctypes.c_int
    user32.IsWindowVisible.argtypes = (wintypes.HWND,)
    user32.IsWindowVisible.restype = wintypes.BOOL
    user32.GetWindowThreadProcessId.argtypes = (wintypes.HWND, ctypes.POINTER(wintypes.DWORD))
    user32.GetWindowThreadProcessId.restype = wintypes.DWORD
    user32.ShowWindow.argtypes = (wintypes.HWND, ctypes.c_int)
    user32.ShowWindow.restype = wintypes.BOOL
    user32.SetForegroundWindow.argtypes = (wintypes.HWND,)
    user32.SetForegroundWindow.restype = wintypes.BOOL
    user32.BringWindowToTop.argtypes = (wintypes.HWND,)
    user32.BringWindowToTop.restype = wintypes.BOOL
    user32.SetActiveWindow.argtypes = (wintypes.HWND,)
    user32.SetActiveWindow.restype = wintypes.HWND
    user32.SetFocus.argtypes = (wintypes.HWND,)
    user32.SetFocus.restype = wintypes.HWND
    user32.AttachThreadInput.argtypes = (wintypes.DWORD, wintypes.DWORD, wintypes.BOOL)
    user32.AttachThreadInput.restype = wintypes.BOOL
    user32.GetWindowRect.argtypes = (wintypes.HWND, ctypes.POINTER(RECT))
    user32.GetWindowRect.restype = wintypes.BOOL
    user32.EnumWindows.argtypes = (ENUM_WINDOWS_PROC, wintypes.LPARAM)
    user32.EnumWindows.restype = wintypes.BOOL
    kernel32.GlobalAlloc.argtypes = (wintypes.UINT, ctypes.c_size_t)
    kernel32.GlobalAlloc.restype = ctypes.c_void_p
    kernel32.GlobalLock.argtypes = (ctypes.c_void_p,)
    kernel32.GlobalLock.restype = ctypes.c_void_p
    kernel32.GlobalUnlock.argtypes = (ctypes.c_void_p,)
    kernel32.GlobalUnlock.restype = wintypes.BOOL
    kernel32.OpenProcess.argtypes = (wintypes.DWORD, wintypes.BOOL, wintypes.DWORD)
    kernel32.OpenProcess.restype = ctypes.c_void_p
    kernel32.QueryFullProcessImageNameW.argtypes = (
        ctypes.c_void_p,
        wintypes.DWORD,
        wintypes.LPWSTR,
        ctypes.POINTER(wintypes.DWORD),
    )
    kernel32.QueryFullProcessImageNameW.restype = wintypes.BOOL
    kernel32.CloseHandle.argtypes = (ctypes.c_void_p,)
    kernel32.CloseHandle.restype = wintypes.BOOL
    kernel32.GetCurrentThreadId.argtypes = ()
    kernel32.GetCurrentThreadId.restype = wintypes.DWORD
else:
    ctypes = None  # type: ignore[assignment]
    winreg = None  # type: ignore[assignment]
    wintypes = None  # type: ignore[assignment]
    user32 = None  # type: ignore[assignment]
    kernel32 = None  # type: ignore[assignment]
    ENUM_WINDOWS_PROC = None  # type: ignore[assignment]
    RECT = None  # type: ignore[assignment]


CF_UNICODETEXT = 13
GMEM_MOVEABLE = 0x0002
KEYEVENTF_KEYUP = 0x0002
MOUSEEVENTF_LEFTDOWN = 0x0002
MOUSEEVENTF_LEFTUP = 0x0004
MOUSEEVENTF_RIGHTDOWN = 0x0008
MOUSEEVENTF_RIGHTUP = 0x0010
MOUSEEVENTF_WHEEL = 0x0800
PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
SW_RESTORE = 9

VK_CODES = {
    "ctrl": 0x11,
    "control": 0x11,
    "shift": 0x10,
    "alt": 0x12,
    "menu": 0x12,
    "enter": 0x0D,
    "return": 0x0D,
    "tab": 0x09,
    "esc": 0x1B,
    "escape": 0x1B,
    "space": 0x20,
    "backspace": 0x08,
    "delete": 0x2E,
    "up": 0x26,
    "down": 0x28,
    "left": 0x25,
    "right": 0x27,
    "home": 0x24,
    "end": 0x23,
    "pageup": 0x21,
    "pagedown": 0x22,
    "pgup": 0x21,
    "pgdn": 0x22,
}
for _index in range(1, 13):
    VK_CODES[f"f{_index}"] = 0x6F + _index


AI_SERVICE_URLS = {
    "chatgpt": "https://chatgpt.com/",
    "deepseek": "https://chat.deepseek.com/",
    "gemini": "https://gemini.google.com/app",
    "claude": "https://claude.ai/new",
    "kimi": "https://www.kimi.com/",
    "doubao": "https://www.doubao.com/chat/",
    "perplexity": "https://www.perplexity.ai/",
}

BROWSER_PROCESS_NAMES = {
    "chrome.exe",
    "msedge.exe",
    "firefox.exe",
    "brave.exe",
    "brave-browser.exe",
    "opera.exe",
    "opera_gx.exe",
    "vivaldi.exe",
    "arc.exe",
    "browser.exe",
}


class BrowserControlerTool(BaseTool):
    """Control the default browser and extract page information."""

    name = "browser_controler"
    aliases = ("browser_controller", "browser_control", "Browser Controler")
    search_hint = "open control browser devtools inspect page diagnose endpoint server web app"
    tool_category = "browser"
    tool_tags = ("browser", "web", "desktop", "devtools", "diagnostics", "server", "upload")
    max_result_chars = 80_000
    description = (
        "Browser Controler opens the system browser, including private windows when possible, "
        "controls visible browser pages with mouse/keyboard/scroll actions, opens DevTools, uploads "
        "workspace files through file dialogs, copies or extracts page text, diagnoses page structure, "
        "and checks web/server endpoints."
    )
    parameters = {
        "type": "object",
        "properties": {
            "action": {
                "type": "string",
                "enum": [
                    "active_window",
                    "list_browser_windows",
                    "activate_browser",
                    "open_browser",
                    "open_page",
                    "open_devtools",
                    "diagnose_page",
                    "check_endpoint",
                    "open_ai_service",
                    "ai_chat",
                    "close_page",
                    "current_url",
                    "extract_page",
                    "copy_page_text",
                    "observe",
                    "click",
                    "scroll",
                    "type_text",
                    "paste_text",
                    "key_press",
                    "hotkey",
                    "upload_file",
                    "wait",
                ],
                "description": "Browser action to perform.",
            },
            "url": {"type": "string", "description": "URL to open or extract. If omitted for extract_page, the current browser URL is copied from the address bar."},
            "service": {"type": "string", "description": "Optional web service shortcut for open_ai_service/ai_chat."},
            "browser": {"type": "string", "description": "Optional browser hint: default, chrome, edge, firefox, brave."},
            "browser_path": {"type": "string", "description": "Optional explicit browser executable path."},
            "private": {"type": "boolean", "description": "Open a private/incognito window when possible."},
            "new_window": {"type": "boolean", "description": "Open in a new browser window."},
            "include_all_windows": {"type": "boolean", "description": "For list_browser_windows, include non-browser top-level windows too."},
            "title_contains": {"type": "string", "description": "For activate_browser, choose a browser window whose title contains this text."},
            "window_index": {"type": "integer", "description": "For activate_browser, zero-based index among matching browser windows."},
            "text": {"type": "string", "description": "Text to type or paste into the active browser page."},
            "prompt": {"type": "string", "description": "Prompt text for ai_chat."},
            "send": {"type": "boolean", "description": "Press Enter after pasting text in ai_chat or paste_text."},
            "x": {"type": "integer", "description": "Screen X coordinate for click or upload button."},
            "y": {"type": "integer", "description": "Screen Y coordinate for click or upload button."},
            "button": {"type": "string", "description": "Mouse button: left or right."},
            "delta": {"type": "integer", "description": "Mouse wheel delta. Positive scrolls up, negative scrolls down. One notch is 120."},
            "key": {"type": "string", "description": "Single key for key_press."},
            "keys": {"type": "array", "items": {"type": "string"}, "description": "Key chord for hotkey, e.g. ['ctrl', 'l']."},
            "file_path": {"type": "string", "description": "Workspace-relative file path to upload through the active file dialog."},
            "file_paths": {"type": "array", "items": {"type": "string"}, "description": "Workspace-relative files to upload sequentially."},
            "wait_seconds": {"type": "number", "description": "Delay for wait or after opening pages."},
            "max_chars": {"type": "integer", "description": "Maximum page text characters to include in the tool output."},
            "include_links": {"type": "boolean", "description": "Include links/images/forms when extracting a page."},
            "check_assets": {"type": "boolean", "description": "For diagnose_page, also check scripts, stylesheets, and images with HEAD/GET requests."},
            "method": {"type": "string", "description": "HTTP method for check_endpoint, such as GET, POST, PUT, PATCH, DELETE, OPTIONS, or HEAD."},
            "headers": {"type": "object", "description": "Optional HTTP headers for check_endpoint."},
            "body": {"type": "string", "description": "Optional raw request body for check_endpoint."},
            "json_body": {"type": "object", "description": "Optional JSON request body for check_endpoint."},
            "timeout": {"type": "number", "description": "HTTP timeout in seconds for diagnose_page/check_endpoint."},
            "close_window": {"type": "boolean", "description": "For close_page, close the whole browser window instead of the active tab."},
            "observation_name": {"type": "string", "description": "Optional screenshot file stem for observe."},
            "grid_cols": {"type": "integer", "description": "Optional screenshot grid columns."},
            "grid_rows": {"type": "integer", "description": "Optional screenshot grid rows."},
        },
        "required": ["action"],
    }

    def __init__(self, context: Optional[Dict] = None):
        super().__init__(context)
        self.project_root = self.get_project_root()
        self.output_dir = get_project_data_dir(self.project_root) / "browser_controler"
        self.pages_dir = self.output_dir / "pages"
        self.observations_dir = self.output_dir / "observations"
        self.pages_dir.mkdir(parents=True, exist_ok=True)
        self.observations_dir.mkdir(parents=True, exist_ok=True)

    def get_execution_message(self, action: str, **kwargs) -> str:
        action_name = str(action or "").strip().lower()
        return {
            "active_window": "Inspecting active window",
            "list_browser_windows": "Listing browser windows",
            "activate_browser": "Activating browser window",
            "open_browser": "Opening browser window",
            "open_page": "Opening browser page",
            "open_devtools": "Opening browser developer tools",
            "diagnose_page": "Diagnosing web page structure and resources",
            "check_endpoint": "Checking web/server endpoint",
            "open_ai_service": "Opening web AI service",
            "ai_chat": "Interacting with web AI service",
            "close_page": "Closing browser page",
            "current_url": "Reading current browser URL",
            "extract_page": "Extracting browser page content",
            "copy_page_text": "Copying visible page text",
            "observe": "Capturing browser observation",
            "click": "Clicking browser surface",
            "scroll": "Scrolling browser surface",
            "type_text": "Typing into browser",
            "paste_text": "Pasting text into browser",
            "key_press": "Pressing browser key",
            "hotkey": "Sending browser hotkey",
            "upload_file": "Uploading file through browser dialog",
            "wait": "Waiting for browser UI",
        }.get(action_name, "Controlling browser")

    def execute(self, action: str, **kwargs) -> ToolResult:
        action_name = str(action or "").strip().lower()
        try:
            if action_name == "active_window":
                return self._active_window()
            if action_name == "list_browser_windows":
                return self._list_browser_windows(include_all=bool(kwargs.get("include_all_windows", False)))
            if action_name == "activate_browser":
                return self._activate_browser(
                    title_contains=str(kwargs.get("title_contains") or ""),
                    window_index=int(kwargs.get("window_index", 0) or 0),
                )
            if action_name in {"open_browser", "open_page"}:
                return self._open_page(**kwargs)
            if action_name == "open_devtools":
                return self._open_devtools(**kwargs)
            if action_name == "diagnose_page":
                return self._diagnose_page(
                    url=kwargs.get("url"),
                    max_chars=int(kwargs.get("max_chars", 20000) or 20000),
                    include_links=bool(kwargs.get("include_links", True)),
                    check_assets=bool(kwargs.get("check_assets", False)),
                    timeout=float(kwargs.get("timeout", 20) or 20),
                )
            if action_name == "check_endpoint":
                return self._check_endpoint(**kwargs)
            if action_name == "open_ai_service":
                service_url = self._resolve_service_url(kwargs.get("service"), kwargs.get("url"))
                return self._open_page(url=service_url, **{k: v for k, v in kwargs.items() if k != "url"})
            if action_name == "ai_chat":
                return self._ai_chat(**kwargs)
            if action_name == "close_page":
                return self._close_page(close_window=bool(kwargs.get("close_window", False)))
            if action_name == "current_url":
                return self._current_url()
            if action_name == "extract_page":
                return self._extract_page(
                    url=kwargs.get("url"),
                    max_chars=int(kwargs.get("max_chars", 20000) or 20000),
                    include_links=bool(kwargs.get("include_links", True)),
                )
            if action_name == "copy_page_text":
                return self._copy_page_text(max_chars=int(kwargs.get("max_chars", 30000) or 30000))
            if action_name == "observe":
                return self._observe(**kwargs)
            if action_name == "click":
                return self._click(kwargs.get("x"), kwargs.get("y"), button=str(kwargs.get("button", "left") or "left"))
            if action_name == "scroll":
                return self._scroll(int(kwargs.get("delta", -360) or -360))
            if action_name == "type_text":
                return self._type_text(str(kwargs.get("text", "") or ""), press_enter=bool(kwargs.get("send", False)))
            if action_name == "paste_text":
                return self._paste_text(str(kwargs.get("text", "") or ""), press_enter=bool(kwargs.get("send", False)))
            if action_name == "key_press":
                return self._key_press(str(kwargs.get("key", "") or ""))
            if action_name == "hotkey":
                return self._hotkey(kwargs.get("keys") or [])
            if action_name == "upload_file":
                return self._upload_file(kwargs.get("file_path"), x=kwargs.get("x"), y=kwargs.get("y"))
            if action_name == "wait":
                return self._wait(float(kwargs.get("wait_seconds", 1.0) or 1.0))
            return ToolResult.fail(f"Unknown browser_controler action: {action_name}")
        except Exception as exc:
            return ToolResult.fail(f"Browser Controler failed: {exc}")

    def _active_window(self) -> ToolResult:
        self._require_windows_desktop()
        info = self._foreground_window_info()
        return ToolResult.ok(self._render_window_info(info, prefix="Active window"), data={"window": info})

    def _list_browser_windows(self, *, include_all: bool = False) -> ToolResult:
        self._require_windows_desktop()
        windows = self._top_level_windows()
        browser_windows = [item for item in windows if item.get("is_browser")]
        selected = windows if include_all else browser_windows
        if not selected:
            return ToolResult.ok(
                "No browser windows were found." if not include_all else "No top-level windows were found.",
                data={"windows": selected, "browser_count": len(browser_windows), "window_count": len(windows)},
            )
        lines = [
            f"Browser windows: {len(browser_windows)}",
            f"Top-level windows: {len(windows)}",
            "",
        ]
        for index, item in enumerate(selected):
            marker = "browser" if item.get("is_browser") else "window"
            lines.append(
                f"[{index}] {marker}: {item.get('title') or '(untitled)'} "
                f"({item.get('process_name') or 'unknown'}, pid={item.get('process_id') or 0})"
            )
        return ToolResult.ok(
            "\n".join(lines).strip(),
            data={"windows": selected, "browser_count": len(browser_windows), "window_count": len(windows)},
        )

    def _activate_browser(self, *, title_contains: str = "", window_index: int = 0) -> ToolResult:
        self._require_windows_desktop()
        browser_windows = [item for item in self._top_level_windows() if item.get("is_browser")]
        needle = str(title_contains or "").strip().lower()
        if needle:
            browser_windows = [item for item in browser_windows if needle in str(item.get("title") or "").lower()]
        if not browser_windows:
            return ToolResult.fail(
                "No matching browser window found."
                + (f" title_contains={title_contains!r}" if title_contains else "")
            )
        index = max(0, min(int(window_index or 0), len(browser_windows) - 1))
        selected = browser_windows[index]
        hwnd = int(selected.get("handle") or 0)
        if not hwnd:
            return ToolResult.fail("Selected browser window has no handle.")
        activated = self._activate_window_handle(hwnd)
        if not activated:
            active = self._foreground_window_info()
            return ToolResult.fail(
                "Tried to activate the browser window, but Windows kept another foreground window. "
                f"{self._render_window_info(active, prefix='Active window')}"
            )
        return ToolResult.ok(self._render_window_info(selected, prefix="Activated browser window"), data={"window": selected})

    def _activate_first_browser_window(self) -> bool:
        browser_windows = [item for item in self._top_level_windows() if item.get("is_browser")]
        if not browser_windows:
            return False
        hwnd = int(browser_windows[0].get("handle") or 0)
        if not hwnd:
            return False
        return self._activate_window_handle(hwnd)

    def _open_page(self, **kwargs) -> ToolResult:
        url = str(kwargs.get("url") or "about:blank").strip() or "about:blank"
        private = bool(kwargs.get("private", False))
        new_window = bool(kwargs.get("new_window", True))
        browser = str(kwargs.get("browser") or "default").strip()
        browser_path = str(kwargs.get("browser_path") or "").strip()
        wait_seconds = float(kwargs.get("wait_seconds", 0.75) or 0.75)
        before_browser_handles: set[int] = set()
        if IS_WINDOWS:
            try:
                before_browser_handles = {
                    int(item.get("handle") or 0)
                    for item in self._top_level_windows()
                    if item.get("is_browser")
                }
            except Exception:
                before_browser_handles = set()

        if private or browser_path or browser.lower() not in {"", "default", "system"}:
            executable = self._resolve_browser_executable(browser=browser, browser_path=browser_path)
            if not executable:
                if private:
                    return ToolResult.fail("Could not resolve a browser executable for private mode.")
                webbrowser.open_new(url) if new_window else webbrowser.open(url)
            else:
                args = [str(executable)]
                args.extend(self._browser_window_flags(executable, private=private, new_window=new_window))
                args.append(url)
                subprocess.Popen(args, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        else:
            webbrowser.open_new(url) if new_window else webbrowser.open(url)

        if wait_seconds > 0:
            time.sleep(min(wait_seconds, 10.0))
        activated = False
        if IS_WINDOWS:
            try:
                browser_windows = [item for item in self._top_level_windows() if item.get("is_browser")]
                new_browser_windows = [
                    item for item in browser_windows
                    if int(item.get("handle") or 0) not in before_browser_handles
                ]
                for candidate in new_browser_windows + browser_windows:
                    handle = int(candidate.get("handle") or 0)
                    if handle and self._activate_window_handle(handle):
                        activated = True
                        break
            except Exception:
                activated = False
        mode = "private " if private else ""
        suffix = " Activated a browser window." if activated else ""
        return ToolResult.ok(f"Opened {mode}browser page: {url}.{suffix}", data={"url": url, "private": private, "activated": activated})

    def _open_devtools(self, **kwargs) -> ToolResult:
        url = str(kwargs.get("url") or "").strip()
        if url:
            opened = self._open_page(**kwargs)
            if not opened.success:
                return opened
            time.sleep(float(kwargs.get("wait_seconds", 1.0) or 1.0))
        self._require_windows_desktop()
        self._send_key("f12")
        return ToolResult.ok("Opened DevTools for the active browser page." + (f" Page: {url}" if url else ""))

    def _ai_chat(self, **kwargs) -> ToolResult:
        service_url = self._resolve_service_url(kwargs.get("service"), kwargs.get("url"))
        open_result = self._open_page(
            url=service_url,
            private=bool(kwargs.get("private", False)),
            new_window=bool(kwargs.get("new_window", True)),
            browser=kwargs.get("browser") or "default",
            browser_path=kwargs.get("browser_path") or "",
            wait_seconds=float(kwargs.get("wait_seconds", 2.0) or 2.0),
        )
        if not open_result.success:
            return open_result

        uploaded: List[str] = []
        file_paths = list(kwargs.get("file_paths") or [])
        if kwargs.get("file_path"):
            file_paths.insert(0, kwargs.get("file_path"))
        for file_path in file_paths:
            upload_result = self._upload_file(file_path, x=kwargs.get("x"), y=kwargs.get("y"))
            if not upload_result.success:
                return upload_result
            uploaded.append(str(upload_result.data.get("file_path", "")))
            time.sleep(0.5)

        text = str(kwargs.get("prompt") or kwargs.get("text") or "").strip()
        if text:
            paste_result = self._paste_text(text, press_enter=bool(kwargs.get("send", True)))
            if not paste_result.success:
                return paste_result

        details = [f"Opened {service_url}"]
        if uploaded:
            details.append(f"uploaded {len(uploaded)} file(s)")
        if text:
            details.append("submitted prompt" if bool(kwargs.get("send", True)) else "pasted prompt")
        return ToolResult.ok("AI service interaction prepared: " + ", ".join(details), data={"url": service_url, "uploaded": uploaded})

    def _resolve_service_url(self, service: Any, fallback_url: Any = None) -> str:
        fallback = str(fallback_url or "").strip()
        if fallback:
            return fallback
        key = str(service or "deepseek").strip().lower()
        return AI_SERVICE_URLS.get(key, key if key.startswith(("http://", "https://")) else AI_SERVICE_URLS["deepseek"])

    def _close_page(self, *, close_window: bool = False) -> ToolResult:
        self._require_windows_desktop()
        active_error = self._active_browser_error()
        if active_error:
            return active_error
        self._send_hotkey(["alt", "f4"] if close_window else ["ctrl", "w"])
        return ToolResult.ok("Closed the active browser window." if close_window else "Closed the active browser tab.")

    def _current_url(self) -> ToolResult:
        self._require_windows_desktop()
        active_error = self._active_browser_error()
        if active_error:
            return active_error
        old_clipboard = self._get_clipboard_text()
        try:
            self._send_hotkey(["ctrl", "l"])
            time.sleep(0.1)
            self._send_hotkey(["ctrl", "c"])
            time.sleep(0.1)
            url = self._get_clipboard_text().strip()
            self._send_key("esc")
        finally:
            self._set_clipboard_text(old_clipboard)
        if not url:
            return ToolResult.fail("Could not read the current browser URL from the address bar.")
        return ToolResult.ok(f"Current browser URL: {url}", data={"url": url})

    def _extract_page(self, *, url: Any = None, max_chars: int = 20000, include_links: bool = True) -> ToolResult:
        page_url = str(url or "").strip()
        if not page_url:
            current = self._current_url()
            if not current.success:
                return current
            page_url = str(current.data.get("url", "") or "").strip()
        if not page_url.startswith(("http://", "https://")):
            return ToolResult.fail(f"extract_page requires an http(s) URL, got: {page_url}")

        response = requests.get(
            page_url,
            timeout=20,
            headers={"User-Agent": "ReverieCLI-BrowserControler/1.0"},
        )
        response.raise_for_status()
        html = response.text
        summary = self._summarize_html(page_url, html, include_links=include_links)
        text = str(summary.get("text", "") or "")
        saved = self._persist_page_artifacts(page_url, html, text)
        output = self._render_page_summary(summary, max_chars=max_chars)
        if saved:
            output += f"\n\nSaved full page text: {saved.get('text_path')}\nSaved HTML: {saved.get('html_path')}"
        return ToolResult.ok(output, data={**summary, **saved, "status_code": response.status_code})

    def _diagnose_page(
        self,
        *,
        url: Any = None,
        max_chars: int = 20000,
        include_links: bool = True,
        check_assets: bool = False,
        timeout: float = 20.0,
    ) -> ToolResult:
        page_url = str(url or "").strip()
        if not page_url:
            current = self._current_url()
            if not current.success:
                return current
            page_url = str(current.data.get("url", "") or "").strip()
        if not page_url.startswith(("http://", "https://")):
            return ToolResult.fail(f"diagnose_page requires an http(s) URL, got: {page_url}")

        response = requests.get(
            page_url,
            timeout=max(1.0, float(timeout)),
            headers={"User-Agent": "ReverieCLI-BrowserControler/1.0"},
        )
        summary = self._summarize_html(page_url, response.text, include_links=include_links)
        diagnostics = self._build_page_diagnostics(page_url, response, summary)
        if check_assets:
            diagnostics["asset_checks"] = self._check_page_assets(page_url, response.text, timeout=max(1.0, float(timeout)))

        saved = self._persist_page_artifacts(page_url, response.text, str(summary.get("text", "") or ""))
        output = self._render_page_diagnostics(diagnostics, summary, max_chars=max_chars)
        output += f"\n\nSaved full page text: {saved.get('text_path')}\nSaved HTML: {saved.get('html_path')}"
        return ToolResult.ok(output, data={**diagnostics, "summary": summary, **saved})

    def _check_endpoint(self, **kwargs) -> ToolResult:
        url = str(kwargs.get("url") or "").strip()
        if not url.startswith(("http://", "https://")):
            return ToolResult.fail("check_endpoint requires an http(s) url")
        method = str(kwargs.get("method") or "GET").strip().upper()
        if method not in {"GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS", "HEAD"}:
            return ToolResult.fail(f"Unsupported HTTP method: {method}")
        headers = kwargs.get("headers") if isinstance(kwargs.get("headers"), dict) else {}
        timeout = max(1.0, float(kwargs.get("timeout", 20) or 20))
        json_body = kwargs.get("json_body") if isinstance(kwargs.get("json_body"), dict) else None
        body = kwargs.get("body")

        started = time.time()
        response = requests.request(
            method,
            url,
            headers={str(key): str(value) for key, value in (headers or {}).items()},
            data=None if json_body is not None else body,
            json=json_body,
            timeout=timeout,
            allow_redirects=True,
        )
        elapsed_ms = int((time.time() - started) * 1000)
        content_type = response.headers.get("content-type", "")
        text_preview = response.text[:4000] if method != "HEAD" else ""
        result = {
            "url": response.url,
            "requested_url": url,
            "method": method,
            "status_code": response.status_code,
            "ok": 200 <= int(response.status_code) < 400,
            "elapsed_ms": elapsed_ms,
            "content_type": content_type,
            "headers": dict(response.headers),
            "redirected": response.url != url,
            "body_preview": text_preview,
        }
        output = [
            f"Endpoint: {method} {url}",
            f"Status: {response.status_code} {'OK' if result['ok'] else 'FAILED'}",
            f"Final URL: {response.url}",
            f"Elapsed: {elapsed_ms} ms",
            f"Content-Type: {content_type}",
        ]
        if text_preview:
            output.append("\nBody Preview:\n" + text_preview)
        return ToolResult.ok("\n".join(output).strip(), data=result)

    def _copy_page_text(self, *, max_chars: int = 30000) -> ToolResult:
        self._require_windows_desktop()
        active_error = self._active_browser_error()
        if active_error:
            return active_error
        old_clipboard = self._get_clipboard_text()
        try:
            self._focus_active_browser_page()
            self._send_hotkey(["ctrl", "a"])
            time.sleep(0.1)
            self._send_hotkey(["ctrl", "c"])
            time.sleep(0.25)
            text = self._get_clipboard_text()
            self._send_key("esc")
        finally:
            self._set_clipboard_text(old_clipboard)
        if not text.strip():
            return ToolResult.fail("No page text was copied. Click the page body and try copy_page_text again.")
        text_path = self._persist_text("copied-page-text", text)
        clipped = text[: max(1, int(max_chars))]
        if len(text) > len(clipped):
            clipped += f"\n\n[truncated; full text saved to {text_path}]"
        return ToolResult.ok(clipped, data={"text_path": str(text_path), "char_count": len(text)})

    def _observe(self, **kwargs) -> ToolResult:
        self._require_windows_desktop()
        active_error = self._active_browser_error()
        if active_error:
            return active_error
        try:
            from PIL import ImageDraw, ImageGrab
        except Exception as exc:
            return ToolResult.fail(f"Browser observation requires Pillow ImageGrab support: {exc}")

        image = ImageGrab.grab()
        grid_cols = int(kwargs.get("grid_cols", 0) or 0)
        grid_rows = int(kwargs.get("grid_rows", 0) or 0)
        if grid_cols > 0 and grid_rows > 0:
            draw = ImageDraw.Draw(image)
            width, height = image.size
            for col in range(1, grid_cols):
                x = int(width * col / grid_cols)
                draw.line([(x, 0), (x, height)], fill=(255, 80, 80), width=2)
            for row in range(1, grid_rows):
                y = int(height * row / grid_rows)
                draw.line([(0, y), (width, y)], fill=(255, 80, 80), width=2)

        stem = re.sub(r"[^A-Za-z0-9._-]+", "-", str(kwargs.get("observation_name") or "browser").strip()).strip("-._") or "browser"
        path = self.observations_dir / f"{stem}-{int(time.time() * 1000)}.png"
        image.save(path)
        return ToolResult.ok(f"Saved browser screenshot: {path}", data={"image_path": str(path), "width": image.size[0], "height": image.size[1]})

    def _click(self, x: Any, y: Any, *, button: str = "left") -> ToolResult:
        self._require_windows_desktop()
        active_error = self._active_browser_error()
        if active_error:
            return active_error
        x_value = int(x)
        y_value = int(y)
        user32.SetCursorPos(x_value, y_value)
        time.sleep(0.05)
        if str(button or "left").lower() == "right":
            down, up = MOUSEEVENTF_RIGHTDOWN, MOUSEEVENTF_RIGHTUP
        else:
            down, up = MOUSEEVENTF_LEFTDOWN, MOUSEEVENTF_LEFTUP
        user32.mouse_event(down, 0, 0, 0, 0)
        time.sleep(0.03)
        user32.mouse_event(up, 0, 0, 0, 0)
        return ToolResult.ok(f"Clicked browser surface at ({x_value}, {y_value}).")

    def _scroll(self, delta: int) -> ToolResult:
        self._require_windows_desktop()
        active_error = self._active_browser_error()
        if active_error:
            return active_error
        user32.mouse_event(MOUSEEVENTF_WHEEL, 0, 0, int(delta), 0)
        return ToolResult.ok(f"Scrolled browser surface by {int(delta)}.")

    def _type_text(self, text: str, *, press_enter: bool = False) -> ToolResult:
        return self._paste_text(text, press_enter=press_enter)

    def _paste_text(self, text: str, *, press_enter: bool = False) -> ToolResult:
        self._require_windows_desktop()
        active_error = self._active_browser_error()
        if active_error:
            return active_error
        if not text:
            return ToolResult.fail("text is required")
        old_clipboard = self._get_clipboard_text()
        try:
            self._set_clipboard_text(text)
            self._send_hotkey(["ctrl", "v"])
            time.sleep(0.1)
            if press_enter:
                self._send_key("enter")
        finally:
            self._set_clipboard_text(old_clipboard)
        return ToolResult.ok("Pasted text into the active browser page." + (" Pressed Enter." if press_enter else ""))

    def _key_press(self, key: str) -> ToolResult:
        self._require_windows_desktop()
        active_error = self._active_browser_error()
        if active_error:
            return active_error
        self._send_key(key)
        return ToolResult.ok(f"Pressed key: {key}")

    def _hotkey(self, keys: Sequence[Any]) -> ToolResult:
        self._require_windows_desktop()
        active_error = self._active_browser_error()
        if active_error:
            return active_error
        key_list = [str(key or "").strip() for key in keys if str(key or "").strip()]
        if not key_list:
            return ToolResult.fail("keys is required for hotkey")
        self._send_hotkey(key_list)
        return ToolResult.ok(f"Sent hotkey: {'+'.join(key_list)}")

    def _upload_file(self, file_path: Any, *, x: Any = None, y: Any = None) -> ToolResult:
        self._require_windows_desktop()
        active_error = self._active_browser_error()
        if active_error:
            return active_error
        if not file_path:
            return ToolResult.fail("file_path is required")
        resolved = self.resolve_workspace_path(file_path, purpose="upload browser file")
        if not resolved.exists() or not resolved.is_file():
            return ToolResult.fail(f"Upload file not found: {file_path}")
        if x is not None and y is not None:
            click_result = self._click(x, y)
            if not click_result.success:
                return click_result
            time.sleep(0.7)

        old_clipboard = self._get_clipboard_text()
        try:
            self._set_clipboard_text(str(resolved))
            self._send_hotkey(["ctrl", "v"])
            time.sleep(0.1)
            self._send_key("enter")
        finally:
            self._set_clipboard_text(old_clipboard)
        return ToolResult.ok(f"Uploaded file through active browser dialog: {resolved}", data={"file_path": str(resolved)})

    def _wait(self, seconds: float) -> ToolResult:
        duration = max(0.0, min(float(seconds), 60.0))
        time.sleep(duration)
        return ToolResult.ok(f"Waited {duration:.1f} seconds.")

    def _require_windows_desktop(self) -> None:
        if not IS_WINDOWS or user32 is None:
            raise RuntimeError("desktop browser control currently requires Windows")

    def _active_browser_error(self) -> Optional[ToolResult]:
        active = self._foreground_window_info()
        if active.get("is_browser"):
            return None
        return ToolResult.fail(
            "Active window is not a recognized browser. "
            f"{self._render_window_info(active, prefix='Active window')}. "
            "Use list_browser_windows and activate_browser first."
        )

    def _activate_window_handle(self, hwnd: int) -> bool:
        self._require_windows_desktop()
        hwnd_value = wintypes.HWND(int(hwnd or 0))
        if not hwnd_value:
            return False

        foreground_hwnd = user32.GetForegroundWindow()
        foreground_thread = user32.GetWindowThreadProcessId(foreground_hwnd, None) if foreground_hwnd else 0
        target_thread = user32.GetWindowThreadProcessId(hwnd_value, None)
        current_thread = kernel32.GetCurrentThreadId()
        attached: List[tuple[int, int]] = []

        for source, target in ((current_thread, target_thread), (current_thread, foreground_thread), (foreground_thread, target_thread)):
            if source and target and source != target:
                if user32.AttachThreadInput(wintypes.DWORD(source), wintypes.DWORD(target), True):
                    attached.append((source, target))
        try:
            user32.ShowWindow(hwnd_value, SW_RESTORE)
            user32.BringWindowToTop(hwnd_value)
            user32.SetActiveWindow(hwnd_value)
            user32.SetFocus(hwnd_value)
            user32.SetForegroundWindow(hwnd_value)
            time.sleep(0.25)
        finally:
            for source, target in reversed(attached):
                user32.AttachThreadInput(wintypes.DWORD(source), wintypes.DWORD(target), False)

        active = self._foreground_window_info()
        return int(active.get("handle") or 0) == int(hwnd or 0) or bool(active.get("is_browser"))

    def _focus_active_browser_page(self) -> None:
        self._send_key("esc")
        time.sleep(0.08)
        hwnd = user32.GetForegroundWindow()
        rect = RECT()
        if not hwnd or not user32.GetWindowRect(hwnd, ctypes.byref(rect)):
            return
        width = max(1, int(rect.right - rect.left))
        height = max(1, int(rect.bottom - rect.top))
        x = int(rect.left + width * 0.5)
        y = int(rect.top + max(140, height * 0.45))
        user32.SetCursorPos(x, y)
        time.sleep(0.03)
        user32.mouse_event(MOUSEEVENTF_LEFTDOWN, 0, 0, 0, 0)
        time.sleep(0.02)
        user32.mouse_event(MOUSEEVENTF_LEFTUP, 0, 0, 0, 0)
        time.sleep(0.08)

    def _foreground_window_info(self) -> Dict[str, Any]:
        self._require_windows_desktop()
        hwnd = user32.GetForegroundWindow()
        return self._window_info(hwnd)

    def _top_level_windows(self) -> List[Dict[str, Any]]:
        self._require_windows_desktop()
        windows: List[Dict[str, Any]] = []

        @ENUM_WINDOWS_PROC
        def enum_callback(hwnd: Any, _lparam: Any) -> bool:
            try:
                if not user32.IsWindowVisible(hwnd):
                    return True
                title = self._window_title(hwnd)
                if not title:
                    return True
                windows.append(self._window_info(hwnd, title=title))
            except Exception:
                return True
            return True

        user32.EnumWindows(enum_callback, 0)
        return windows

    def _window_info(self, hwnd: Any, *, title: Optional[str] = None) -> Dict[str, Any]:
        self._require_windows_desktop()
        hwnd_int = int(hwnd or 0)
        pid_value = 0
        if hwnd_int:
            pid = wintypes.DWORD()
            user32.GetWindowThreadProcessId(wintypes.HWND(hwnd_int), ctypes.byref(pid))
            pid_value = int(pid.value or 0)
        process_path = self._process_path(pid_value)
        process_name = Path(process_path).name.lower() if process_path else ""
        return {
            "handle": hwnd_int,
            "title": title if title is not None else self._window_title(hwnd),
            "process_id": pid_value,
            "process_name": process_name,
            "process_path": process_path,
            "is_browser": self._is_browser_process(process_name, process_path),
        }

    @staticmethod
    def _render_window_info(info: Dict[str, Any], *, prefix: str = "Window") -> str:
        title = str(info.get("title") or "(untitled)")
        process_name = str(info.get("process_name") or "unknown")
        pid = int(info.get("process_id") or 0)
        browser_flag = "browser" if info.get("is_browser") else "not-browser"
        return f"{prefix}: {title} ({process_name}, pid={pid}, {browser_flag})"

    def _window_title(self, hwnd: Any) -> str:
        self._require_windows_desktop()
        hwnd_value = wintypes.HWND(int(hwnd or 0))
        length = int(user32.GetWindowTextLengthW(hwnd_value) or 0)
        if length <= 0:
            return ""
        buffer = ctypes.create_unicode_buffer(length + 1)
        user32.GetWindowTextW(hwnd_value, buffer, length + 1)
        return str(buffer.value or "").strip()

    def _process_path(self, process_id: int) -> str:
        if not process_id:
            return ""
        handle = kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, int(process_id))
        if not handle:
            return ""
        try:
            buffer = ctypes.create_unicode_buffer(32768)
            size = wintypes.DWORD(len(buffer))
            if not kernel32.QueryFullProcessImageNameW(handle, 0, buffer, ctypes.byref(size)):
                return ""
            return str(buffer.value or "")
        finally:
            kernel32.CloseHandle(handle)

    @staticmethod
    def _is_browser_process(process_name: str, process_path: str = "") -> bool:
        lowered_name = str(process_name or "").strip().lower()
        if lowered_name in BROWSER_PROCESS_NAMES:
            return True
        lowered_path = str(process_path or "").replace("\\", "/").lower()
        return any(f"/{name[:-4]}/" in lowered_path for name in BROWSER_PROCESS_NAMES if name.endswith(".exe"))

    def _vk_for_key(self, key: Any) -> int:
        text = str(key or "").strip().lower()
        if not text:
            raise ValueError("empty key")
        if text in VK_CODES:
            return int(VK_CODES[text])
        if len(text) == 1:
            char = text.upper()
            if "A" <= char <= "Z" or "0" <= char <= "9":
                return ord(char)
        raise ValueError(f"Unsupported key: {key}")

    def _send_key(self, key: Any) -> None:
        vk = self._vk_for_key(key)
        user32.keybd_event(vk, 0, 0, 0)
        time.sleep(0.03)
        user32.keybd_event(vk, 0, KEYEVENTF_KEYUP, 0)

    def _send_hotkey(self, keys: Sequence[Any]) -> None:
        vks = [self._vk_for_key(key) for key in keys]
        for vk in vks:
            user32.keybd_event(vk, 0, 0, 0)
            time.sleep(0.02)
        for vk in reversed(vks):
            user32.keybd_event(vk, 0, KEYEVENTF_KEYUP, 0)
            time.sleep(0.02)

    def _get_clipboard_text(self) -> str:
        self._require_windows_desktop()
        if not user32.OpenClipboard(None):
            return ""
        try:
            handle = user32.GetClipboardData(CF_UNICODETEXT)
            if not handle:
                return ""
            locked = kernel32.GlobalLock(handle)
            if not locked:
                return ""
            try:
                return ctypes.wstring_at(locked) if ctypes is not None else ""
            finally:
                kernel32.GlobalUnlock(handle)
        finally:
            user32.CloseClipboard()

    def _set_clipboard_text(self, text: str) -> None:
        self._require_windows_desktop()
        data = (str(text or "") + "\0").encode("utf-16-le")
        handle = kernel32.GlobalAlloc(GMEM_MOVEABLE, len(data))
        if not handle:
            raise RuntimeError("GlobalAlloc failed while setting clipboard text")
        locked = kernel32.GlobalLock(handle)
        if not locked:
            raise RuntimeError("GlobalLock failed while setting clipboard text")
        ctypes.memmove(locked, data, len(data))
        kernel32.GlobalUnlock(handle)
        if not user32.OpenClipboard(None):
            raise RuntimeError("OpenClipboard failed")
        try:
            user32.EmptyClipboard()
            if not user32.SetClipboardData(CF_UNICODETEXT, handle):
                raise RuntimeError("SetClipboardData failed")
            handle = None
        finally:
            user32.CloseClipboard()

    def _resolve_browser_executable(self, *, browser: str = "default", browser_path: str = "") -> Optional[Path]:
        explicit = Path(browser_path).expanduser() if browser_path else None
        if explicit and explicit.exists() and explicit.is_file():
            return explicit.resolve()

        browser_key = str(browser or "default").strip().lower()
        if browser_key in {"", "default", "system"}:
            default_path = self._default_windows_browser_path()
            if default_path:
                return default_path

        aliases = {
            "chrome": ["chrome", "chrome.exe"],
            "google": ["chrome", "chrome.exe"],
            "edge": ["msedge", "msedge.exe"],
            "msedge": ["msedge", "msedge.exe"],
            "firefox": ["firefox", "firefox.exe"],
            "brave": ["brave", "brave.exe", "brave-browser"],
        }
        names = aliases.get(browser_key, aliases.get("chrome", []))
        for name in names:
            found = shutil.which(name)
            if found:
                return Path(found).resolve()

        if IS_WINDOWS:
            for candidate in self._common_windows_browser_paths(browser_key):
                if candidate.exists() and candidate.is_file():
                    return candidate.resolve()
        return None

    def _default_windows_browser_path(self) -> Optional[Path]:
        if not IS_WINDOWS or winreg is None:
            return None
        try:
            with winreg.OpenKey(
                winreg.HKEY_CURRENT_USER,
                r"Software\Microsoft\Windows\Shell\Associations\UrlAssociations\https\UserChoice",
            ) as key:
                prog_id = str(winreg.QueryValueEx(key, "ProgId")[0] or "").strip()
        except Exception:
            prog_id = ""
        if not prog_id:
            return None

        for root in (winreg.HKEY_CURRENT_USER, winreg.HKEY_LOCAL_MACHINE):
            try:
                with winreg.OpenKey(root, rf"Software\Classes\{prog_id}\shell\open\command") as key:
                    command = str(winreg.QueryValueEx(key, "")[0] or "")
            except Exception:
                continue
            path = self._browser_path_from_command(command)
            if path:
                return path
        return None

    @staticmethod
    def _browser_path_from_command(command: str) -> Optional[Path]:
        text = str(command or "").strip()
        if not text:
            return None
        match = re.search(r'"([^"]+?\.exe)"', text, flags=re.IGNORECASE)
        if not match:
            match = re.search(r"([A-Za-z]:\\[^\"]+?\.exe)", text, flags=re.IGNORECASE)
        if not match:
            return None
        candidate = Path(match.group(1)).expanduser()
        return candidate.resolve() if candidate.exists() and candidate.is_file() else None

    @staticmethod
    def _common_windows_browser_paths(browser_key: str) -> List[Path]:
        program_files = [
            os.environ.get("PROGRAMFILES", ""),
            os.environ.get("PROGRAMFILES(X86)", ""),
            os.environ.get("LOCALAPPDATA", ""),
        ]
        suffixes = {
            "chrome": [r"Google\Chrome\Application\chrome.exe"],
            "google": [r"Google\Chrome\Application\chrome.exe"],
            "edge": [r"Microsoft\Edge\Application\msedge.exe"],
            "msedge": [r"Microsoft\Edge\Application\msedge.exe"],
            "firefox": [r"Mozilla Firefox\firefox.exe"],
            "brave": [r"BraveSoftware\Brave-Browser\Application\brave.exe"],
            "default": [
                r"Microsoft\Edge\Application\msedge.exe",
                r"Google\Chrome\Application\chrome.exe",
                r"Mozilla Firefox\firefox.exe",
                r"BraveSoftware\Brave-Browser\Application\brave.exe",
            ],
        }
        selected_suffixes = suffixes.get(browser_key, suffixes["default"])
        candidates: List[Path] = []
        for root in program_files:
            if not root:
                continue
            for suffix in selected_suffixes:
                candidates.append(Path(root) / suffix)
        return candidates

    @staticmethod
    def _browser_window_flags(executable: Path, *, private: bool, new_window: bool) -> List[str]:
        name = executable.name.lower()
        flags: List[str] = []
        if private:
            if "firefox" in name:
                flags.append("-private-window")
            elif "msedge" in name:
                flags.append("--inprivate")
            else:
                flags.append("--incognito")
        if new_window and "firefox" not in name:
            flags.append("--new-window")
        return flags

    def _persist_text(self, stem: str, text: str) -> Path:
        safe_stem = re.sub(r"[^A-Za-z0-9._-]+", "-", str(stem or "page").strip()).strip("-._") or "page"
        path = self.pages_dir / f"{safe_stem}-{int(time.time() * 1000)}.txt"
        path.write_text(str(text or ""), encoding="utf-8")
        return path

    def _persist_page_artifacts(self, url: str, html: str, text: str) -> Dict[str, str]:
        stem = re.sub(r"[^A-Za-z0-9._-]+", "-", str(url or "page")).strip("-._")[:80] or "page"
        timestamp = int(time.time() * 1000)
        html_path = self.pages_dir / f"{stem}-{timestamp}.html"
        text_path = self.pages_dir / f"{stem}-{timestamp}.txt"
        html_path.write_text(str(html or ""), encoding="utf-8")
        text_path.write_text(str(text or ""), encoding="utf-8")
        return {"html_path": str(html_path), "text_path": str(text_path)}

    @staticmethod
    def _summarize_html(url: str, html: str, *, include_links: bool = True) -> Dict[str, Any]:
        soup = BeautifulSoup(html or "", "html.parser")
        for node in soup(["script", "style", "noscript"]):
            node.decompose()
        title = soup.title.get_text(" ", strip=True) if soup.title else ""
        meta_description = ""
        meta = soup.find("meta", attrs={"name": re.compile("^description$", re.I)})
        if meta and meta.get("content"):
            meta_description = str(meta.get("content") or "").strip()
        headings = []
        for tag in soup.find_all(re.compile("^h[1-6]$"))[:80]:
            text = tag.get_text(" ", strip=True)
            if text:
                headings.append({"level": tag.name.upper(), "text": text})
        text = soup.get_text("\n", strip=True)
        text = re.sub(r"\n{3,}", "\n\n", text)

        links: List[Dict[str, str]] = []
        images: List[Dict[str, str]] = []
        forms: List[Dict[str, Any]] = []
        if include_links:
            for link in soup.find_all("a", href=True)[:120]:
                label = link.get_text(" ", strip=True)
                href = str(link.get("href") or "").strip()
                if href:
                    links.append({"text": label[:160], "href": href})
            for image in soup.find_all("img")[:80]:
                src = str(image.get("src") or "").strip()
                if src:
                    images.append({"alt": str(image.get("alt") or "").strip()[:160], "src": src})
            for form in soup.find_all("form")[:20]:
                inputs = []
                for field in form.find_all(["input", "textarea", "select"])[:40]:
                    inputs.append(
                        {
                            "tag": field.name,
                            "name": str(field.get("name") or "").strip(),
                            "type": str(field.get("type") or "").strip(),
                        }
                    )
                forms.append(
                    {
                        "method": str(form.get("method") or "get").upper(),
                        "action": str(form.get("action") or "").strip(),
                        "inputs": inputs,
                    }
                )

        return {
            "url": url,
            "title": title,
            "meta_description": meta_description,
            "headings": headings,
            "text": text,
            "links": links,
            "images": images,
            "forms": forms,
        }

    @staticmethod
    def _build_page_diagnostics(url: str, response: requests.Response, summary: Dict[str, Any]) -> Dict[str, Any]:
        headers = dict(getattr(response, "headers", {}) or {})
        status_code = int(getattr(response, "status_code", 0) or 0)
        content_type = headers.get("content-type", headers.get("Content-Type", ""))
        text = str(summary.get("text", "") or "")
        forms = list(summary.get("forms") or [])
        links = list(summary.get("links") or [])
        images = list(summary.get("images") or [])
        warnings: List[str] = []

        if status_code >= 400:
            warnings.append(f"HTTP status is {status_code}.")
        if "text/html" not in str(content_type).lower():
            warnings.append(f"Content-Type is not HTML: {content_type or '(missing)'}.")
        if not str(summary.get("title", "") or "").strip():
            warnings.append("Page title is missing.")
        if not text.strip():
            warnings.append("Extracted page text is empty.")
        if forms:
            missing_actions = [form for form in forms if not str(form.get("action", "") or "").strip()]
            if missing_actions:
                warnings.append(f"{len(missing_actions)} form(s) have no action attribute.")

        return {
            "url": getattr(response, "url", url),
            "requested_url": url,
            "status_code": status_code,
            "ok": 200 <= status_code < 400,
            "content_type": content_type,
            "headers": headers,
            "title": summary.get("title", ""),
            "meta_description": summary.get("meta_description", ""),
            "heading_count": len(summary.get("headings") or []),
            "link_count": len(links),
            "image_count": len(images),
            "form_count": len(forms),
            "text_chars": len(text),
            "warnings": warnings,
        }

    @staticmethod
    def _asset_urls_from_html(page_url: str, html: str) -> List[Dict[str, str]]:
        soup = BeautifulSoup(html or "", "html.parser")
        assets: List[Dict[str, str]] = []

        def add(kind: str, raw_url: Any) -> None:
            raw = str(raw_url or "").strip()
            if not raw or raw.startswith(("data:", "javascript:", "mailto:", "#")):
                return
            absolute = urljoin(page_url, raw)
            if not absolute.startswith(("http://", "https://")):
                return
            assets.append({"kind": kind, "url": absolute})

        for node in soup.find_all("script", src=True):
            add("script", node.get("src"))
        for node in soup.find_all("link", href=True):
            rel = " ".join(str(part).lower() for part in (node.get("rel") or []))
            kind = "stylesheet" if "stylesheet" in rel else "link"
            add(kind, node.get("href"))
        for node in soup.find_all("img", src=True):
            add("image", node.get("src"))

        deduped: List[Dict[str, str]] = []
        seen: set[str] = set()
        for item in assets:
            key = item["url"]
            if key in seen:
                continue
            seen.add(key)
            deduped.append(item)
        return deduped

    @classmethod
    def _check_page_assets(cls, page_url: str, html: str, *, timeout: float = 20.0, limit: int = 40) -> Dict[str, Any]:
        assets = cls._asset_urls_from_html(page_url, html)[: max(1, int(limit))]
        checks: List[Dict[str, Any]] = []
        for item in assets:
            asset_url = item["url"]
            try:
                response = requests.head(
                    asset_url,
                    timeout=max(1.0, float(timeout)),
                    allow_redirects=True,
                    headers={"User-Agent": "ReverieCLI-BrowserControler/1.0"},
                )
                if response.status_code in {405, 501}:
                    response = requests.get(
                        asset_url,
                        timeout=max(1.0, float(timeout)),
                        allow_redirects=True,
                        stream=True,
                        headers={"User-Agent": "ReverieCLI-BrowserControler/1.0"},
                    )
                checks.append(
                    {
                        "kind": item["kind"],
                        "url": asset_url,
                        "status_code": int(response.status_code),
                        "ok": 200 <= int(response.status_code) < 400,
                        "content_type": response.headers.get("content-type", ""),
                    }
                )
            except Exception as exc:
                checks.append(
                    {
                        "kind": item["kind"],
                        "url": asset_url,
                        "status_code": 0,
                        "ok": False,
                        "error": str(exc),
                    }
                )
        broken = [item for item in checks if not item.get("ok")]
        return {
            "checked": len(checks),
            "broken": len(broken),
            "items": checks,
        }

    @staticmethod
    def _render_page_diagnostics(diagnostics: Dict[str, Any], summary: Dict[str, Any], *, max_chars: int) -> str:
        lines = [
            f"URL: {diagnostics.get('url', '')}",
            f"Status: {diagnostics.get('status_code')} {'OK' if diagnostics.get('ok') else 'FAILED'}",
            f"Content-Type: {diagnostics.get('content_type') or '(missing)'}",
            f"Title: {diagnostics.get('title') or '(missing)'}",
            (
                "Counts: "
                f"headings={diagnostics.get('heading_count', 0)}, "
                f"links={diagnostics.get('link_count', 0)}, "
                f"images={diagnostics.get('image_count', 0)}, "
                f"forms={diagnostics.get('form_count', 0)}, "
                f"text_chars={diagnostics.get('text_chars', 0)}"
            ),
        ]
        warnings = list(diagnostics.get("warnings") or [])
        if warnings:
            lines.append("\nWarnings:")
            lines.extend(f"- {item}" for item in warnings)

        asset_checks = diagnostics.get("asset_checks")
        if isinstance(asset_checks, dict):
            lines.append(
                f"\nAsset Checks: checked={asset_checks.get('checked', 0)}, broken={asset_checks.get('broken', 0)}"
            )
            broken_items = [item for item in (asset_checks.get("items") or []) if not item.get("ok")]
            for item in broken_items[:20]:
                status = item.get("status_code") or item.get("error") or "failed"
                lines.append(f"- {item.get('kind')}: {status} {item.get('url')}")

        lines.append("\nPage Summary:")
        lines.append(BrowserControlerTool._render_page_summary(summary, max_chars=max_chars))
        return "\n".join(lines).strip()

    @staticmethod
    def _render_page_summary(summary: Dict[str, Any], *, max_chars: int) -> str:
        lines = [
            f"URL: {summary.get('url', '')}",
            f"Title: {summary.get('title', '')}",
        ]
        if summary.get("meta_description"):
            lines.append(f"Description: {summary.get('meta_description')}")
        headings = summary.get("headings") or []
        if headings:
            lines.append("\nHeadings:")
            for heading in headings[:30]:
                lines.append(f"- {heading.get('level')}: {heading.get('text')}")
        if summary.get("links"):
            lines.append("\nLinks:")
            for link in (summary.get("links") or [])[:40]:
                label = str(link.get("text") or "").strip() or "(no text)"
                lines.append(f"- {label}: {link.get('href')}")
        if summary.get("forms"):
            lines.append("\nForms:")
            for form in (summary.get("forms") or [])[:10]:
                lines.append(f"- {form.get('method')} {form.get('action')} inputs={len(form.get('inputs') or [])}")

        text = str(summary.get("text") or "")
        clipped = text[: max(1, int(max_chars))]
        lines.append("\nPage Text:\n" + clipped)
        if len(text) > len(clipped):
            lines.append("\n[page text truncated in tool output]")
        return "\n".join(lines).strip()
