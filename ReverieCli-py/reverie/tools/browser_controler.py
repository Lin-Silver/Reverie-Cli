"""Browser Controler tool.

Provides a browser-focused automation and diagnostics surface for opening pages,
driving visible browser UI, inspecting page text, opening DevTools, and checking
web/server endpoints without turning the workflow into a static fetch-only pass.
"""

from __future__ import annotations

import os
import base64
import json
import re
import secrets
import shutil
import socket
import ssl
import subprocess
import zipfile

from ..diagnostics import report_suppressed_exception
import struct
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence
from urllib.parse import quote, urljoin, urlparse

import requests
from bs4 import BeautifulSoup

from .base import BaseTool, ToolResult
from ..config import get_app_root


IS_WINDOWS = os.name == "nt"

if IS_WINDOWS:
    import ctypes
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
    user32.IsIconic.argtypes = (wintypes.HWND,)
    user32.IsIconic.restype = wintypes.BOOL
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
SW_SHOWMINNOACTIVE = 7

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

BROWSER_IMPORT_SUFFIXES = {".json", ".txt", ".cookies"}
BROWSER_IMPORT_NAME_HINTS = (
    "cookie",
    "cookies",
    "storage-state",
    "storage_state",
    "browser-state",
    "browser_state",
    "playwright",
    "auth-state",
    "auth_state",
    "session-state",
    "session_state",
)
BROWSER_IMPORT_MAX_BYTES = 64 * 1024 * 1024
BROWSER_IMPORT_SCAN_SKIP_DIRS = {
    ".git",
    ".hg",
    ".svn",
    ".venv",
    "venv",
    "node_modules",
    "__pycache__",
    "build",
    "dist",
}
BROWSER_REAL_PROFILE_PATH_MARKERS = (
    "/google/chrome/user data/",
    "/microsoft/edge/user data/",
    "/bravesoftware/brave-browser/user data/",
    "/vivaldi/user data/",
    "/mozilla/firefox/profiles/",
    "/opera software/opera stable/",
)

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

DEFAULT_CDP_PORT = 9222
CDP_HOST = "127.0.0.1"


class _CdpWebSocket:
    """Small WebSocket client for Chrome DevTools Protocol JSON messages."""

    def __init__(self, websocket_url: str, *, timeout: float = 5.0):
        self.websocket_url = websocket_url
        self.timeout = max(0.5, float(timeout or 5.0))
        self.sock: Optional[socket.socket] = None

    def __enter__(self) -> "_CdpWebSocket":
        self.connect()
        return self

    def __exit__(self, _exc_type: Any, _exc: Any, _tb: Any) -> None:
        self.close()

    def connect(self) -> None:
        parsed = urlparse(self.websocket_url)
        if parsed.scheme not in {"ws", "wss"}:
            raise RuntimeError(f"Unsupported DevTools WebSocket URL: {self.websocket_url}")
        host = parsed.hostname or CDP_HOST
        port = int(parsed.port or (443 if parsed.scheme == "wss" else 80))
        path = parsed.path or "/"
        if parsed.query:
            path += f"?{parsed.query}"

        raw_sock = socket.create_connection((host, port), timeout=self.timeout)
        if parsed.scheme == "wss":
            raw_sock = ssl.create_default_context().wrap_socket(raw_sock, server_hostname=host)
        raw_sock.settimeout(self.timeout)
        key = base64.b64encode(secrets.token_bytes(16)).decode("ascii")
        request = (
            f"GET {path} HTTP/1.1\r\n"
            f"Host: {host}:{port}\r\n"
            "Connection: Upgrade\r\n"
            "Upgrade: websocket\r\n"
            "Sec-WebSocket-Version: 13\r\n"
            f"Sec-WebSocket-Key: {key}\r\n"
            "\r\n"
        )
        raw_sock.sendall(request.encode("ascii"))

        response = b""
        deadline = time.time() + self.timeout
        while b"\r\n\r\n" not in response:
            if time.time() > deadline:
                raw_sock.close()
                raise RuntimeError("Timed out during DevTools WebSocket handshake")
            chunk = raw_sock.recv(4096)
            if not chunk:
                break
            response += chunk
        first_line = response.split(b"\r\n", 1)[0]
        if b" 101 " not in first_line:
            raw_sock.close()
            preview = response[:300].decode("utf-8", errors="replace")
            raise RuntimeError(f"DevTools WebSocket handshake failed: {preview}")
        self.sock = raw_sock

    def close(self) -> None:
        sock = self.sock
        self.sock = None
        if not sock:
            return
        try:
            self._send_frame(b"", opcode=0x8)
        except Exception:
            report_suppressed_exception("send browser WebSocket close frame")
        try:
            sock.close()
        except Exception:
            report_suppressed_exception("close browser WebSocket")

    def send_json(self, payload: Dict[str, Any]) -> None:
        text = json.dumps(payload, separators=(",", ":"), ensure_ascii=False)
        self._send_frame(text.encode("utf-8"), opcode=0x1)

    def recv_json(self, *, timeout: Optional[float] = None) -> Optional[Dict[str, Any]]:
        payload = self._recv_frame(timeout=timeout)
        if payload is None:
            return None
        try:
            return json.loads(payload.decode("utf-8"))
        except Exception:
            return {"method": "_rawWebSocketMessage", "params": {"payload": payload.decode("utf-8", errors="replace")}}

    def _send_frame(self, payload: bytes, *, opcode: int = 0x1) -> None:
        if not self.sock:
            raise RuntimeError("DevTools WebSocket is not connected")
        first = 0x80 | int(opcode)
        length = len(payload)
        if length < 126:
            header = struct.pack("!BB", first, 0x80 | length)
        elif length < 65536:
            header = struct.pack("!BBH", first, 0x80 | 126, length)
        else:
            header = struct.pack("!BBQ", first, 0x80 | 127, length)
        mask_key = secrets.token_bytes(4)
        masked = bytes(byte ^ mask_key[index % 4] for index, byte in enumerate(payload))
        self.sock.sendall(header + mask_key + masked)

    def _recv_frame(self, *, timeout: Optional[float] = None) -> Optional[bytes]:
        while True:
            header = self._recv_exact(2, timeout=timeout)
            if not header:
                return None
            first, second = header[0], header[1]
            opcode = first & 0x0F
            masked = bool(second & 0x80)
            length = second & 0x7F
            if length == 126:
                extended = self._recv_exact(2, timeout=timeout)
                if not extended:
                    return None
                length = struct.unpack("!H", extended)[0]
            elif length == 127:
                extended = self._recv_exact(8, timeout=timeout)
                if not extended:
                    return None
                length = struct.unpack("!Q", extended)[0]
            mask_key = self._recv_exact(4, timeout=timeout) if masked else b""
            payload = self._recv_exact(length, timeout=timeout) if length else b""
            if payload is None:
                return None
            if masked and mask_key:
                payload = bytes(byte ^ mask_key[index % 4] for index, byte in enumerate(payload))
            if opcode == 0x8:
                return None
            if opcode == 0x9:
                self._send_frame(payload, opcode=0xA)
                continue
            if opcode == 0xA:
                continue
            if opcode in {0x1, 0x2}:
                return payload

    def _recv_exact(self, count: int, *, timeout: Optional[float] = None) -> Optional[bytes]:
        if not self.sock:
            raise RuntimeError("DevTools WebSocket is not connected")
        old_timeout = self.sock.gettimeout()
        if timeout is not None:
            self.sock.settimeout(max(0.01, float(timeout)))
        try:
            chunks: List[bytes] = []
            remaining = int(count)
            while remaining > 0:
                try:
                    chunk = self.sock.recv(remaining)
                except socket.timeout:
                    return None
                if not chunk:
                    return None
                chunks.append(chunk)
                remaining -= len(chunk)
            return b"".join(chunks)
        finally:
            if timeout is not None:
                self.sock.settimeout(old_timeout)


class _CdpConnection:
    """Request/response helper for one DevTools Protocol page target."""

    def __init__(self, websocket_url: str, *, timeout: float = 5.0):
        self.websocket_url = websocket_url
        self.timeout = max(0.5, float(timeout or 5.0))
        self.websocket: Optional[_CdpWebSocket] = None
        self.next_id = 1
        self.events: List[Dict[str, Any]] = []

    def __enter__(self) -> "_CdpConnection":
        self.websocket = _CdpWebSocket(self.websocket_url, timeout=self.timeout)
        self.websocket.connect()
        return self

    def __exit__(self, _exc_type: Any, _exc: Any, _tb: Any) -> None:
        if self.websocket:
            self.websocket.close()

    def call(self, method: str, params: Optional[Dict[str, Any]] = None, *, timeout: Optional[float] = None) -> Dict[str, Any]:
        if not self.websocket:
            raise RuntimeError("DevTools connection is not open")
        message_id = self.next_id
        self.next_id += 1
        self.websocket.send_json({"id": message_id, "method": method, "params": params or {}})
        wait_timeout = max(0.5, float(timeout or self.timeout))
        deadline = time.time() + wait_timeout
        while time.time() < deadline:
            remaining = max(0.01, min(0.5, deadline - time.time()))
            message = self.websocket.recv_json(timeout=remaining)
            if not message:
                continue
            if message.get("id") == message_id:
                if message.get("error"):
                    error = message.get("error") or {}
                    raise RuntimeError(f"{method} failed: {error.get('message') or error}")
                return message.get("result") or {}
            self.events.append(message)
        raise RuntimeError(f"Timed out waiting for DevTools method {method}")

    def collect(self, seconds: float) -> List[Dict[str, Any]]:
        if not self.websocket:
            raise RuntimeError("DevTools connection is not open")
        collected: List[Dict[str, Any]] = []
        deadline = time.time() + max(0.0, float(seconds or 0.0))
        while time.time() < deadline:
            remaining = max(0.01, min(0.5, deadline - time.time()))
            message = self.websocket.recv_json(timeout=remaining)
            if message:
                collected.append(message)
        self.events.extend(collected)
        return collected


class BrowserControlerTool(BaseTool):
    """Control Reverie's embedded Chromium browser and extract page information."""

    name = "browser_controler"
    aliases = ("browser_controller", "browser_control", "Browser Controler")
    search_hint = "open control browser devtools inspect page diagnose endpoint server web app"
    tool_category = "browser"
    tool_tags = ("browser", "web", "desktop", "devtools", "diagnostics", "server", "upload")
    max_result_chars = 80_000
    description = (
        "Browser Controler uses Reverie's embedded open-source Chromium runtime, stores all browser runtime/profile/"
        "cookie/session data under the app root .reverie/browser directory, controls only those embedded browser "
        "windows with mouse/keyboard/scroll actions, opens DevTools, talks to Chromium DevTools Protocol for "
        "console/network/DOM inspection, imports user-provided cookie/storage-state files, uploads workspace files "
        "through file dialogs, copies or extracts page text, diagnoses page structure, and checks web/server endpoints."
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
                    "open_debug_page",
                    "open_devtools",
                    "browser_session_start",
                    "browser_session_list",
                    "browser_session_close",
                    "browser_session_cleanup",
                    "browser_runtime_status",
                    "browser_profile_status",
                    "browser_profile_backup",
                    "browser_profile_backups",
                    "browser_profile_restore",
                    "browser_profile_import",
                    "browser_profile_export",
                    "devtools_targets",
                    "devtools_snapshot",
                    "devtools_screenshot",
                    "devtools_eval",
                    "devtools_console",
                    "devtools_network",
                    "devtools_click",
                    "devtools_type",
                    "devtools_upload",
                    "devtools_wait_for",
                    "devtools_accessibility_snapshot",
                    "devtools_dom_outline",
                    "devtools_find",
                    "safety_policy",
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
            "browser": {"type": "string", "description": "Compatibility hint only. Browser Controler always launches Reverie's embedded Chromium runtime, never the real system browser/profile."},
            "browser_path": {"type": "string", "description": "Reserved for embedded runtime diagnostics; real system browser paths are refused."},
            "profile": {"type": "string", "description": "Embedded browser profile name under .reverie/browser/profiles. Defaults to default."},
            "private": {"type": "boolean", "description": "Open a private/incognito window when possible."},
            "new_window": {"type": "boolean", "description": "Open in a new browser window."},
            "background": {"type": "boolean", "description": "For open_debug_page, keep the browser in the background and use CDP actions without stealing foreground focus."},
            "minimized": {"type": "boolean", "description": "Open or move the browser window minimized when possible. Pair with background=true for non-disruptive CDP runs."},
            "activate": {"type": "boolean", "description": "Whether to activate the opened browser window. Defaults false for background/minimized open_debug_page."},
            "port": {"type": "integer", "description": "Chrome DevTools Protocol remote debugging port for open_debug_page/devtools_* actions."},
            "target_id": {"type": "string", "description": "Optional DevTools target id for devtools_* actions."},
            "url_contains": {"type": "string", "description": "Optional target URL/title substring for activate_browser or devtools_* target selection."},
            "session_id": {"type": "string", "description": "Optional Browser Controler session id for browser_session_* and devtools_* actions."},
            "selector": {"type": "string", "description": "CSS selector for background DevTools DOM actions."},
            "role": {"type": "string", "description": "ARIA role filter for devtools_find."},
            "expression": {"type": "string", "description": "JavaScript expression to run through DevTools Runtime.evaluate."},
            "await_promise": {"type": "boolean", "description": "For devtools_eval, wait for returned promises."},
            "return_by_value": {"type": "boolean", "description": "For devtools_eval, return JSON-serializable values by value."},
            "include_bodies": {"type": "boolean", "description": "For devtools_network, include response body previews when available."},
            "include_request_body": {"type": "boolean", "description": "For devtools_network, include captured request postData previews when available."},
            "include_websockets": {"type": "boolean", "description": "For devtools_network, include WebSocket creation/frame events."},
            "export_har": {"type": "boolean", "description": "For devtools_network, save a simplified HAR-style JSON artifact."},
            "filter_url": {"type": "string", "description": "For devtools_network/devtools_find, filter by URL/text substring."},
            "filter_method": {"type": "string", "description": "For devtools_network, filter by HTTP method."},
            "filter_status": {"type": "string", "description": "For devtools_network, filter by status code or class such as 2xx/4xx."},
            "max_body_chars": {"type": "integer", "description": "For devtools_network, maximum characters per captured response body preview."},
            "max_events": {"type": "integer", "description": "For devtools_console/devtools_network, maximum events/items to render."},
            "reload": {"type": "boolean", "description": "For devtools_network, reload the selected page after enabling Network."},
            "full_page": {"type": "boolean", "description": "For devtools_screenshot, request capture beyond the visible viewport when supported."},
            "format": {"type": "string", "description": "For devtools_screenshot, png or jpeg."},
            "quality": {"type": "integer", "description": "For jpeg devtools_screenshot, quality from 1 to 100."},
            "clear": {"type": "boolean", "description": "For devtools_type, clear the existing value before typing."},
            "poll_interval": {"type": "number", "description": "For devtools_wait_for, seconds between checks."},
            "cleanup_profiles": {"type": "boolean", "description": "For browser_session_cleanup, also remove stale embedded profiles under .reverie/browser/profiles."},
            "include_cache": {"type": "boolean", "description": "For browser_profile_backup, include embedded profile cache folders too. Defaults true."},
            "backup_id": {"type": "string", "description": "Embedded browser profile backup id for browser_profile_restore."},
            "confirm": {"type": "boolean", "description": "Required true for browser_profile_restore because it writes to an embedded .reverie/browser profile."},
            "import_format": {"type": "string", "description": "For browser_profile_import, storage_state/json/netscape. Defaults auto."},
            "user_data_dir": {"type": "string", "description": "Compatibility alias for profile. Relative names are kept under .reverie/browser/profiles; external paths are refused."},
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
            "file_path": {
                "type": "string",
                "description": (
                    "Workspace-relative file path for uploads or browser data import. For browser_profile_import, omit "
                    "this value to open Reverie's interactive export-file picker and user authorization screen."
                ),
            },
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
        self.app_root = get_app_root()
        self.output_dir = self.app_root / ".reverie" / "browser"
        self.pages_dir = self.output_dir / "pages"
        self.observations_dir = self.output_dir / "observations"
        self.runtime_dir = self.output_dir / "runtime"
        self.imports_dir = self.output_dir / "imports"
        self.downloads_dir = self.output_dir / "downloads"
        self.debug_profiles_dir = self.output_dir / "profiles"
        self.profile_backups_dir = self.output_dir / "backups"
        self.import_consent_path = self.output_dir / "import-consent.json"
        self.sessions_path = self.output_dir / "sessions.json"
        self.pages_dir.mkdir(parents=True, exist_ok=True)
        self.observations_dir.mkdir(parents=True, exist_ok=True)
        self.runtime_dir.mkdir(parents=True, exist_ok=True)
        self.imports_dir.mkdir(parents=True, exist_ok=True)
        self.downloads_dir.mkdir(parents=True, exist_ok=True)
        self.debug_profiles_dir.mkdir(parents=True, exist_ok=True)
        self.profile_backups_dir.mkdir(parents=True, exist_ok=True)

    def get_execution_message(self, action: str, **kwargs) -> str:
        action_name = str(action or "").strip().lower()
        return {
            "active_window": "Inspecting active window",
            "list_browser_windows": "Listing browser windows",
            "activate_browser": "Activating browser window",
            "open_browser": "Opening browser window",
            "open_page": "Opening browser page",
            "open_debug_page": "Opening browser page with DevTools Protocol enabled",
            "open_devtools": "Opening browser developer tools",
            "browser_session_start": "Starting background browser session",
            "browser_session_list": "Listing background browser sessions",
            "browser_session_close": "Closing background browser session",
            "browser_session_cleanup": "Cleaning up background browser sessions",
            "browser_runtime_status": "Inspecting embedded browser runtime",
            "browser_profile_status": "Inspecting browser profile backup status",
            "browser_profile_backup": "Backing up browser profile data",
            "browser_profile_backups": "Listing browser profile backups",
            "browser_profile_restore": "Restoring browser profile data",
            "browser_profile_import": "Importing embedded browser cookies/storage state",
            "browser_profile_export": "Exporting embedded browser cookies/storage state",
            "devtools_targets": "Listing DevTools Protocol page targets",
            "devtools_snapshot": "Reading live DOM text through DevTools Protocol",
            "devtools_screenshot": "Capturing browser page screenshot through DevTools Protocol",
            "devtools_eval": "Running JavaScript in the browser through DevTools Protocol",
            "devtools_console": "Reading browser console and log events",
            "devtools_network": "Reading browser network events and responses",
            "devtools_click": "Clicking a page element through DevTools Protocol",
            "devtools_type": "Typing into a page element through DevTools Protocol",
            "devtools_upload": "Uploading a file through DevTools Protocol",
            "devtools_wait_for": "Waiting for page state through DevTools Protocol",
            "devtools_accessibility_snapshot": "Reading accessibility tree through DevTools Protocol",
            "devtools_dom_outline": "Reading semantic DOM outline through DevTools Protocol",
            "devtools_find": "Finding semantic page elements through DevTools Protocol",
            "safety_policy": "Showing Browser Controler safety policy",
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
            isolated_window_actions = {
                "close_page",
                "current_url",
                "copy_page_text",
                "observe",
                "click",
                "scroll",
                "type_text",
                "paste_text",
                "key_press",
                "hotkey",
                "upload_file",
            }
            if action_name in isolated_window_actions:
                guard = self._require_isolated_active_browser()
                if guard is not None:
                    return guard
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
            if action_name == "open_debug_page":
                return self._open_debug_page(**kwargs)
            if action_name == "open_devtools":
                return self._open_devtools(**kwargs)
            if action_name == "browser_session_start":
                return self._browser_session_start(**kwargs)
            if action_name == "browser_session_list":
                return self._browser_session_list()
            if action_name == "browser_session_close":
                return self._browser_session_close(
                    session_id=str(kwargs.get("session_id") or ""),
                    port=kwargs.get("port"),
                    timeout=float(kwargs.get("timeout", 5) or 5),
                )
            if action_name == "browser_session_cleanup":
                return self._browser_session_cleanup(cleanup_profiles=bool(kwargs.get("cleanup_profiles", False)))
            if action_name == "browser_runtime_status":
                return self._browser_runtime_status()
            if action_name == "browser_profile_status":
                return self._browser_profile_status(profile=str(kwargs.get("profile") or kwargs.get("browser") or "default"))
            if action_name == "browser_profile_backup":
                return self._browser_profile_backup(
                    profile=str(kwargs.get("profile") or kwargs.get("browser") or "default"),
                    include_cache=bool(kwargs.get("include_cache", True)),
                )
            if action_name == "browser_profile_backups":
                return self._browser_profile_backups(profile=str(kwargs.get("profile") or kwargs.get("browser") or "default"))
            if action_name == "browser_profile_restore":
                return self._browser_profile_restore(
                    profile=str(kwargs.get("profile") or kwargs.get("browser") or "default"),
                    backup_id=str(kwargs.get("backup_id") or ""),
                    confirm=bool(kwargs.get("confirm", False)),
                )
            if action_name == "browser_profile_import":
                return self._browser_profile_import(
                    file_path=kwargs.get("file_path"),
                    profile=str(kwargs.get("profile") or kwargs.get("browser") or "default"),
                    import_format=str(kwargs.get("import_format") or kwargs.get("format") or "auto"),
                )
            if action_name == "browser_profile_export":
                return self._browser_profile_export(
                    profile=str(kwargs.get("profile") or kwargs.get("browser") or "default"),
                    port=kwargs.get("port"),
                    timeout=float(kwargs.get("timeout", 5) or 5),
                )
            if action_name.startswith("devtools_"):
                cdp_port = self._resolve_cdp_port(
                    session_id=str(kwargs.get("session_id") or ""),
                    port=kwargs.get("port"),
                )
            if action_name == "devtools_targets":
                return self._devtools_targets(
                    port=cdp_port,
                    url_contains=str(kwargs.get("url_contains") or ""),
                    timeout=float(kwargs.get("timeout", 5) or 5),
                )
            if action_name == "devtools_snapshot":
                return self._devtools_snapshot(
                    port=cdp_port,
                    target_id=str(kwargs.get("target_id") or ""),
                    url_contains=str(kwargs.get("url_contains") or ""),
                    max_chars=int(kwargs.get("max_chars", 30000) or 30000),
                    timeout=float(kwargs.get("timeout", 5) or 5),
                )
            if action_name == "devtools_screenshot":
                return self._devtools_screenshot(
                    port=cdp_port,
                    target_id=str(kwargs.get("target_id") or ""),
                    url_contains=str(kwargs.get("url_contains") or ""),
                    full_page=bool(kwargs.get("full_page", True)),
                    image_format=str(kwargs.get("format") or "png"),
                    quality=int(kwargs.get("quality", 90) or 90),
                    observation_name=str(kwargs.get("observation_name") or "devtools-page"),
                    timeout=float(kwargs.get("timeout", 5) or 5),
                )
            if action_name == "devtools_eval":
                return self._devtools_eval(
                    expression=str(kwargs.get("expression") or ""),
                    port=cdp_port,
                    target_id=str(kwargs.get("target_id") or ""),
                    url_contains=str(kwargs.get("url_contains") or ""),
                    await_promise=bool(kwargs.get("await_promise", True)),
                    return_by_value=bool(kwargs.get("return_by_value", True)),
                    timeout=float(kwargs.get("timeout", 5) or 5),
                )
            if action_name == "devtools_console":
                return self._devtools_console(
                    expression=str(kwargs.get("expression") or ""),
                    port=cdp_port,
                    target_id=str(kwargs.get("target_id") or ""),
                    url_contains=str(kwargs.get("url_contains") or ""),
                    wait_seconds=float(kwargs.get("wait_seconds", 1.0) or 1.0),
                    max_events=int(kwargs.get("max_events", 80) or 80),
                    timeout=float(kwargs.get("timeout", 5) or 5),
                )
            if action_name == "devtools_network":
                return self._devtools_network(
                    url=kwargs.get("url"),
                    port=cdp_port,
                    target_id=str(kwargs.get("target_id") or ""),
                    url_contains=str(kwargs.get("url_contains") or ""),
                    wait_seconds=float(kwargs.get("wait_seconds", 3.0) or 3.0),
                    include_bodies=bool(kwargs.get("include_bodies", False)),
                    include_request_body=bool(kwargs.get("include_request_body", False)),
                    include_websockets=bool(kwargs.get("include_websockets", False)),
                    export_har=bool(kwargs.get("export_har", False)),
                    filter_url=str(kwargs.get("filter_url") or ""),
                    filter_method=str(kwargs.get("filter_method") or ""),
                    filter_status=str(kwargs.get("filter_status") or ""),
                    max_body_chars=int(kwargs.get("max_body_chars", 2000) or 2000),
                    max_events=int(kwargs.get("max_events", 120) or 120),
                    reload=bool(kwargs.get("reload", False)),
                    timeout=float(kwargs.get("timeout", 5) or 5),
                )
            if action_name == "devtools_click":
                return self._devtools_click(
                    selector=str(kwargs.get("selector") or ""),
                    port=cdp_port,
                    target_id=str(kwargs.get("target_id") or ""),
                    url_contains=str(kwargs.get("url_contains") or ""),
                    timeout=float(kwargs.get("timeout", 5) or 5),
                )
            if action_name == "devtools_type":
                return self._devtools_type(
                    selector=str(kwargs.get("selector") or ""),
                    text=str(kwargs.get("text") or ""),
                    port=cdp_port,
                    target_id=str(kwargs.get("target_id") or ""),
                    url_contains=str(kwargs.get("url_contains") or ""),
                    clear=bool(kwargs.get("clear", True)),
                    press_enter=bool(kwargs.get("send", False)),
                    timeout=float(kwargs.get("timeout", 5) or 5),
                )
            if action_name == "devtools_upload":
                return self._devtools_upload(
                    selector=str(kwargs.get("selector") or ""),
                    file_path=kwargs.get("file_path"),
                    port=cdp_port,
                    target_id=str(kwargs.get("target_id") or ""),
                    url_contains=str(kwargs.get("url_contains") or ""),
                    timeout=float(kwargs.get("timeout", 5) or 5),
                )
            if action_name == "devtools_wait_for":
                return self._devtools_wait_for(
                    selector=str(kwargs.get("selector") or ""),
                    text=str(kwargs.get("text") or ""),
                    expression=str(kwargs.get("expression") or ""),
                    port=cdp_port,
                    target_id=str(kwargs.get("target_id") or ""),
                    url_contains=str(kwargs.get("url_contains") or ""),
                    wait_seconds=float(kwargs.get("wait_seconds", 10.0) or 10.0),
                    poll_interval=float(kwargs.get("poll_interval", 0.25) or 0.25),
                    timeout=float(kwargs.get("timeout", 5) or 5),
                )
            if action_name == "devtools_accessibility_snapshot":
                return self._devtools_accessibility_snapshot(
                    port=cdp_port,
                    target_id=str(kwargs.get("target_id") or ""),
                    url_contains=str(kwargs.get("url_contains") or ""),
                    max_events=int(kwargs.get("max_events", 120) or 120),
                    timeout=float(kwargs.get("timeout", 5) or 5),
                )
            if action_name == "devtools_dom_outline":
                return self._devtools_dom_outline(
                    port=cdp_port,
                    target_id=str(kwargs.get("target_id") or ""),
                    url_contains=str(kwargs.get("url_contains") or ""),
                    max_events=int(kwargs.get("max_events", 120) or 120),
                    timeout=float(kwargs.get("timeout", 5) or 5),
                )
            if action_name == "devtools_find":
                return self._devtools_find(
                    selector=str(kwargs.get("selector") or ""),
                    text=str(kwargs.get("text") or kwargs.get("filter_url") or ""),
                    role=str(kwargs.get("role") or ""),
                    port=cdp_port,
                    target_id=str(kwargs.get("target_id") or ""),
                    url_contains=str(kwargs.get("url_contains") or ""),
                    max_events=int(kwargs.get("max_events", 80) or 80),
                    timeout=float(kwargs.get("timeout", 5) or 5),
                )
            if action_name == "safety_policy":
                return self._safety_policy()
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
        browser_windows = [
            item for item in self._top_level_windows()
            if item.get("is_browser") and self._is_browser_controler_window(item)
        ]
        needle = str(title_contains or "").strip().lower()
        if needle:
            browser_windows = [item for item in browser_windows if needle in str(item.get("title") or "").lower()]
        if not browser_windows:
            return ToolResult.fail(
                "No matching isolated Browser Controler window found."
                + (f" title_contains={title_contains!r}" if title_contains else "")
                + " Use open_page or browser_session_start first."
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
        browser_windows = [
            item for item in self._top_level_windows()
            if item.get("is_browser") and self._is_browser_controler_window(item)
        ]
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
        minimized = bool(kwargs.get("minimized", False))
        activate = bool(kwargs.get("activate")) if kwargs.get("activate") is not None else not minimized
        browser = str(kwargs.get("browser") or "chromium").strip() or "chromium"
        if browser.lower() in {"default", "system"}:
            browser = "chromium"
        browser_path = str(kwargs.get("browser_path") or "").strip()
        wait_seconds = float(kwargs.get("wait_seconds", 0.75) or 0.75)
        executable = self._resolve_browser_executable(browser=browser, browser_path=browser_path)
        if not executable:
            return ToolResult.fail(self._embedded_browser_missing_message())
        browser = self._browser_key_for_executable(browser, executable)
        profile_name = self._profile_name_from_kwargs(kwargs, default="default")
        profile_dir = self._embedded_browser_profile_dir(profile_name).resolve()
        if self._profile_processes_running(profile_dir):
            return ToolResult.fail(f"Embedded browser profile is already in use: {profile_name}")
        backup = self._ensure_profile_backup(profile_name)
        try:
            profile_dir = self._resolve_debug_profile_dir(
                profile_name,
                browser=browser,
                port=0,
            )
        except ValueError as exc:
            return ToolResult.fail(str(exc))
        profile_dir.mkdir(parents=True, exist_ok=True)
        try:
            download_dir = self._prepare_embedded_profile(profile_name, profile_dir)
        except Exception as exc:
            return ToolResult.fail(f"Could not prepare embedded browser profile {profile_name}: {exc}")
        before_browser_handles: set[int] = set()
        previous_foreground = 0
        if IS_WINDOWS:
            try:
                previous_foreground = int(user32.GetForegroundWindow() or 0)
                before_browser_handles = {
                    int(item.get("handle") or 0)
                    for item in self._top_level_windows()
                    if item.get("is_browser")
                }
            except Exception:
                before_browser_handles = set()

        args = [
            str(executable),
            f"--user-data-dir={profile_dir}",
            "--no-first-run",
            "--no-default-browser-check",
            "--disable-popup-blocking",
            "--disable-sync",
            "--disable-features=Translate,OptimizationHints",
        ]
        args.extend(self._browser_window_flags(executable, private=private, new_window=new_window, minimized=minimized))
        args.append(url)
        process = subprocess.Popen(args, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

        if wait_seconds > 0:
            time.sleep(min(wait_seconds, 10.0))
        activated = False
        minimized_handles: List[int] = []
        restored_foreground = False
        if IS_WINDOWS:
            try:
                browser_windows = [item for item in self._top_level_windows() if item.get("is_browser")]
                new_browser_windows = [
                    item for item in browser_windows
                    if int(item.get("handle") or 0) not in before_browser_handles
                ]
                if minimized:
                    minimized_handles = self._minimize_browser_window_handles(new_browser_windows)
                if activate:
                    for candidate in new_browser_windows + browser_windows:
                        handle = int(candidate.get("handle") or 0)
                        if handle and self._activate_window_handle(handle):
                            activated = True
                            break
                elif previous_foreground:
                    restored_foreground = self._restore_foreground_window(previous_foreground)
            except Exception:
                activated = False
        mode = "private " if private else ""
        details = [f"Opened {mode}browser page: {url}."]
        details.append(f"Profile: {profile_dir}.")
        details.append(f"Downloads: {download_dir}.")
        details.append(f"Embedded browser root: {self.output_dir}.")
        if backup.get("backup_id"):
            details.append(f"Embedded profile backup: {backup.get('backup_id')}.")
        if backup.get("partial"):
            details.append(f"Embedded profile backup status is partial; close Browser Controler sessions and run /browser backup {profile_name}.")
        if activated:
            details.append("Activated a browser window.")
        if minimized_handles:
            details.append(f"Minimized {len(minimized_handles)} browser window(s).")
        if not activate and restored_foreground:
            details.append("Restored the previous foreground window.")
        return ToolResult.ok(
            " ".join(details),
            data={
                "url": url,
                "private": private,
                "profile": profile_name,
                "profile_dir": str(profile_dir),
                "download_dir": str(download_dir),
                "browser": str(executable),
                "process_id": process.pid,
                "profile_backup": backup,
                "activated": activated,
                "activate": activate,
                "minimized": bool(minimized_handles),
                "minimized_handles": minimized_handles,
                "restored_foreground": restored_foreground,
            },
        )

    def _open_devtools(self, **kwargs) -> ToolResult:
        url = str(kwargs.get("url") or "").strip()
        if url:
            opened = self._open_page(**kwargs)
            if not opened.success:
                return opened
            time.sleep(float(kwargs.get("wait_seconds", 1.0) or 1.0))
        else:
            guard = self._require_isolated_active_browser()
            if guard is not None:
                return guard
        self._require_windows_desktop()
        self._send_key("f12")
        return ToolResult.ok("Opened DevTools for the active browser page." + (f" Page: {url}" if url else ""))

    def _open_debug_page(self, **kwargs) -> ToolResult:
        url = str(kwargs.get("url") or "about:blank").strip() or "about:blank"
        port = self._normalize_cdp_port(kwargs.get("port")) if kwargs.get("port") else self._free_tcp_port()
        browser = str(kwargs.get("browser") or "chromium").strip() or "chromium"
        if browser.lower() in {"default", "system"}:
            browser = "chromium"
        browser_path = str(kwargs.get("browser_path") or "").strip()
        executable = self._resolve_browser_executable(browser=browser, browser_path=browser_path)
        if not executable:
            return ToolResult.fail(self._embedded_browser_missing_message())
        browser = self._browser_key_for_executable(browser, executable)
        if self._tcp_port_open(port):
            if self._is_authorized_cdp_port(port):
                return ToolResult.fail(
                    f"DevTools Protocol port {port} is already used by a Browser Controler session. "
                    "Use that session's port for devtools_* actions or choose another port."
                )
            return ToolResult.fail(
                f"Refusing to attach to DevTools Protocol port {port} because it is already open and was not created "
                "by Browser Controler. Choose a free port or start a new Browser Controler session."
            )

        profile_name = self._profile_name_from_kwargs(kwargs, default=str(kwargs.get("session_id") or "default"))
        profile_dir = self._embedded_browser_profile_dir(profile_name).resolve()
        if self._profile_processes_running(profile_dir):
            return ToolResult.fail(f"Embedded browser profile is already in use: {profile_name}")
        backup = self._ensure_profile_backup(profile_name)
        try:
            profile_dir = self._resolve_debug_profile_dir(
                profile_name,
                browser=browser,
                port=port,
            )
        except ValueError as exc:
            return ToolResult.fail(str(exc))
        profile_dir.mkdir(parents=True, exist_ok=True)
        try:
            download_dir = self._prepare_embedded_profile(profile_name, profile_dir)
        except Exception as exc:
            return ToolResult.fail(f"Could not prepare embedded browser profile {profile_name}: {exc}")
        wait_seconds = max(1.0, min(float(kwargs.get("wait_seconds", 15.0) or 15.0), 45.0))
        background = bool(kwargs.get("background", False))
        minimized = bool(kwargs.get("minimized", background))
        activate = bool(kwargs.get("activate")) if kwargs.get("activate") is not None else not (background or minimized)
        before_browser_handles: set[int] = set()
        previous_foreground = 0
        if IS_WINDOWS:
            try:
                previous_foreground = int(user32.GetForegroundWindow() or 0)
                before_browser_handles = {
                    int(item.get("handle") or 0)
                    for item in self._top_level_windows()
                    if item.get("is_browser")
                }
            except Exception:
                before_browser_handles = set()

        args = [
            str(executable),
            f"--remote-debugging-port={port}",
            f"--user-data-dir={profile_dir}",
            "--remote-allow-origins=*",
            "--no-first-run",
            "--no-default-browser-check",
            "--disable-popup-blocking",
            "--disable-sync",
            "--disable-features=Translate,OptimizationHints",
        ]
        for flag in self._browser_window_flags(
            executable,
            private=bool(kwargs.get("private", False)),
            new_window=True,
            minimized=minimized,
        ):
            if flag not in args:
                args.append(flag)
        if "--new-window" not in args:
            args.append("--new-window")
        args.append(url)

        process = subprocess.Popen(args, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        version: Dict[str, Any] = {}
        deadline = time.time() + wait_seconds
        last_error = ""
        while time.time() < deadline:
            try:
                version = self._cdp_version(port, timeout=1.0)
                break
            except Exception as exc:
                last_error = str(exc)
                time.sleep(0.2)
        if not version:
            cleanup = self._cleanup_failed_embedded_browser_launch(
                process=process,
                executable=executable,
                profile_dir=profile_dir,
            )
            return ToolResult.fail(
                f"Opened browser process pid={process.pid}, but DevTools Protocol on port {port} did not respond. "
                f"{last_error} Cleanup: {cleanup}"
            )

        recorded_session_id = ""
        if bool(kwargs.get("_record_session", True)):
            recorded_session_id = self._record_browser_session(
                session_id=str(kwargs.get("session_id") or f"debug-port-{port}"),
                port=port,
                url=url,
                profile=profile_name,
                profile_dir=profile_dir,
                browser=str(executable),
                process_id=int(process.pid or 0),
                background=background,
                minimized=minimized,
                profile_backup=backup,
            )
        import_result = self._apply_profile_imports(port=port, profile=profile_name, timeout=min(wait_seconds, 5.0)) if recorded_session_id else ""
        navigation_result = self._ensure_page_navigation(port=port, url=url, timeout=min(wait_seconds, 10.0)) if recorded_session_id else ""

        activated = False
        minimized_handles: List[int] = []
        restored_foreground = False
        if IS_WINDOWS:
            try:
                browser_windows = [item for item in self._top_level_windows() if item.get("is_browser")]
                new_browser_windows = [
                    item for item in browser_windows
                    if int(item.get("handle") or 0) not in before_browser_handles
                ]
                if minimized:
                    minimized_handles = self._minimize_browser_window_handles(new_browser_windows)
                if activate:
                    for candidate in new_browser_windows + browser_windows:
                        handle = int(candidate.get("handle") or 0)
                        if handle and self._activate_window_handle(handle):
                            activated = True
                            break
                elif previous_foreground:
                    restored_foreground = self._restore_foreground_window(previous_foreground)
            except Exception:
                activated = False

        output = [
            f"Opened DevTools-enabled browser page: {url}",
            f"CDP: http://{CDP_HOST}:{port}",
            f"Profile: {profile_dir}",
            f"Downloads: {download_dir}",
            f"Embedded browser root: {self.output_dir}",
            f"Browser: {version.get('Browser') or executable.name}",
        ]
        if backup.get("backup_id"):
            output.append(f"Embedded profile backup: {backup.get('backup_id')}")
        if backup.get("partial"):
            output.append(f"Embedded profile backup status is partial; close Browser Controler sessions and run /browser backup {profile_name}.")
        if import_result:
            output.append(import_result)
        if navigation_result:
            output.append(navigation_result)
        if background:
            output.append("Background mode: CDP actions can control this page without foreground focus.")
        if minimized_handles:
            output.append(f"Minimized {len(minimized_handles)} browser window(s).")
        if activated:
            output.append("Activated a browser window.")
        elif not activate:
            output.append("Did not activate the browser window.")
        if restored_foreground:
            output.append("Restored the previous foreground window.")
        if recorded_session_id:
            output.append(f"Session: {recorded_session_id}")
        return ToolResult.ok(
            "\n".join(output),
            data={
                "url": url,
                "port": port,
                "profile": profile_name,
                "profile_dir": str(profile_dir),
                "download_dir": str(download_dir),
                "browser": str(executable),
                "process_id": process.pid,
                "session_id": recorded_session_id,
                "profile_backup": backup,
                "version": version,
                "activated": activated,
                "activate": activate,
                "background": background,
                "minimized": bool(minimized_handles),
                "minimized_requested": minimized,
                "minimized_handles": minimized_handles,
                "restored_foreground": restored_foreground,
            },
        )

    def _browser_session_start(self, **kwargs) -> ToolResult:
        session_id = re.sub(r"[^A-Za-z0-9._-]+", "-", str(kwargs.get("session_id") or "").strip()).strip("-._")
        if not session_id:
            session_id = f"session-{int(time.time())}"
        sessions = self._load_browser_sessions()
        if session_id in sessions:
            return ToolResult.fail(f"Browser session already exists: {session_id}")
        port = kwargs.get("port")
        if not port:
            port = self._free_tcp_port()
        open_kwargs = dict(kwargs)
        open_kwargs["port"] = int(port)
        open_kwargs.setdefault("url", "about:blank")
        open_kwargs.setdefault("background", True)
        open_kwargs.setdefault("minimized", True)
        open_kwargs.setdefault("activate", False)
        open_kwargs["session_id"] = session_id
        open_kwargs["_record_session"] = True
        opened = self._open_debug_page(**open_kwargs)
        if not opened.success:
            return opened
        sessions = self._load_browser_sessions()
        session = sessions.get(session_id) or {}
        return ToolResult.ok(opened.output, data={**opened.data, "session_id": session_id, "session": session})

    def _browser_session_list(self) -> ToolResult:
        sessions = self._load_browser_sessions()
        if not sessions:
            return ToolResult.ok("No Browser Controler sessions are recorded.", data={"sessions": {}})
        lines = [f"Browser Controler sessions: {len(sessions)}", ""]
        annotated: Dict[str, Any] = {}
        for session_id, session in sessions.items():
            port = int(session.get("port") or 0)
            reachable = False
            target_count = 0
            safe_record = self._is_safe_browser_session_record(session)
            verified_process = bool(self._validate_embedded_browser_session_process(session).get("valid"))
            if safe_record and verified_process:
                try:
                    targets = self._cdp_list_targets(port, timeout=1.0)
                    reachable = True
                    target_count = len(targets)
                except Exception:
                    target_count = 0
            item = {
                **session,
                "safe_record": safe_record,
                "verified_process": verified_process,
                "reachable": reachable,
                "target_count": target_count,
            }
            annotated[session_id] = item
            state = "reachable" if reachable else ("stale" if safe_record and verified_process else "unsafe-record")
            lines.append(
                f"- {session_id}: port={port} {state} targets={target_count} "
                f"url={session.get('url') or '(empty)'}"
            )
        return ToolResult.ok("\n".join(lines).strip(), data={"sessions": annotated})

    def _browser_session_close(self, *, session_id: str = "", port: Any = None, timeout: float = 5.0) -> ToolResult:
        sessions = self._load_browser_sessions()
        selected_id = str(session_id or "").strip()
        selected = sessions.get(selected_id) if selected_id else None
        selected_port = int(port or (selected or {}).get("port") or 0)
        if not selected_port:
            return ToolResult.fail("session_id or port is required for browser_session_close")
        if not selected:
            for candidate_id, candidate in sessions.items():
                if int(candidate.get("port") or 0) == selected_port:
                    selected_id = candidate_id
                    selected = candidate
                    break
        if selected and not self._is_safe_browser_session_record(selected):
            return ToolResult.fail(
                f"Refusing to close session {selected_id} because its runtime/profile paths are not both under .reverie/browser."
            )
        if not selected and not self._is_authorized_cdp_port(selected_port):
            return ToolResult.fail(
                f"Refusing to close DevTools port {selected_port} because it is not a recorded isolated Browser Controler session."
            )
        process_validation = self._validate_embedded_browser_session_process(selected or {})
        if selected and process_validation.get("already_closed"):
            sessions.pop(selected_id, None)
            self._save_browser_sessions(sessions)
            return ToolResult.ok(
                f"Removed already-closed Browser Controler session on port {selected_port}.",
                data={"session_id": selected_id, "port": selected_port, "termination": process_validation},
            )
        if selected and not process_validation.get("valid"):
            return ToolResult.fail(
                f"Refusing to close session {selected_id}: {process_validation.get('reason') or 'embedded process validation failed'}"
            )
        closed = False
        error = ""
        try:
            version = self._cdp_version(selected_port, timeout=timeout)
            websocket_url = str(version.get("webSocketDebuggerUrl") or "")
            if not websocket_url:
                raise RuntimeError("DevTools version endpoint did not expose a browser WebSocket URL")
            with _CdpConnection(websocket_url, timeout=timeout) as cdp:
                cdp.call("Browser.close", {}, timeout=timeout)
            closed = True
        except Exception as exc:
            error = str(exc)
        termination: Dict[str, Any] = {}
        if selected:
            time.sleep(min(max(float(timeout), 0.0), 1.0))
            termination = self._terminate_embedded_browser_session_process(selected)
            closed = closed or bool(termination.get("terminated") or termination.get("already_closed"))
        if selected_id and selected_id in sessions:
            sessions.pop(selected_id, None)
            self._save_browser_sessions(sessions)
        if closed:
            details = [f"Closed Browser Controler session on port {selected_port}."]
            if termination.get("terminated"):
                details.append("Stopped the verified embedded Chromium process tree.")
            return ToolResult.ok(
                " ".join(details),
                data={"session_id": selected_id, "port": selected_port, "termination": termination},
            )
        return ToolResult.partial(
            f"Removed Browser Controler session record for port {selected_port}." if selected_id else "",
            f"Could not close browser through DevTools: {error}. Embedded process termination: {termination.get('reason') or 'not available'}",
            data={"session_id": selected_id, "port": selected_port, "termination": termination},
        )

    def _browser_session_cleanup(self, *, cleanup_profiles: bool = False) -> ToolResult:
        sessions = self._load_browser_sessions()
        kept: Dict[str, Any] = {}
        stale: Dict[str, Any] = {}
        removed_profiles: List[str] = []
        preserved_profiles: List[str] = []
        for session_id, session in sessions.items():
            port = int(session.get("port") or 0)
            reachable = False
            if port and self._validate_embedded_browser_session_process(session).get("valid"):
                try:
                    self._cdp_version(port, timeout=1.0)
                    reachable = True
                except Exception:
                    reachable = False
            if reachable:
                kept[session_id] = session
            else:
                stale[session_id] = session
                if cleanup_profiles:
                    profile_dir = Path(str(session.get("profile_dir") or ""))
                    if self._is_disposable_debug_profile_path(profile_dir) and profile_dir.exists():
                        shutil.rmtree(profile_dir, ignore_errors=True)
                        removed_profiles.append(str(profile_dir))
                    elif self._is_safe_debug_profile_path(profile_dir) and profile_dir.exists():
                        preserved_profiles.append(str(profile_dir))
        self._save_browser_sessions(kept)
        lines = [
            f"Session cleanup complete: kept={len(kept)}, removed_stale={len(stale)}",
        ]
        if removed_profiles:
            lines.append(f"Removed profiles: {len(removed_profiles)}")
        if preserved_profiles:
            lines.append(f"Preserved non-temporary or credential-bearing profiles: {len(preserved_profiles)}")
        return ToolResult.ok(
            "\n".join(lines),
            data={
                "kept": kept,
                "stale": stale,
                "removed_profiles": removed_profiles,
                "preserved_profiles": preserved_profiles,
            },
        )

    def _browser_runtime_status(self) -> ToolResult:
        executable = self._resolve_browser_executable(browser="chromium", browser_path="")
        lines = [
            "Embedded browser runtime:",
            f"Root: {self.output_dir}",
            f"Runtime: {self.runtime_dir}",
            f"Profiles: {self.debug_profiles_dir}",
            f"Backups: {self.profile_backups_dir}",
            f"Imports: {self.imports_dir}",
            f"Downloads: {self.downloads_dir}",
            f"Chromium executable: {executable if executable else '(not found)'}",
        ]
        return ToolResult.ok(
            "\n".join(lines),
            data={
                "browser_root": str(self.output_dir),
                "runtime_dir": str(self.runtime_dir),
                "profiles_dir": str(self.debug_profiles_dir),
                "backups_dir": str(self.profile_backups_dir),
                "imports_dir": str(self.imports_dir),
                "downloads_dir": str(self.downloads_dir),
                "chromium_executable": str(executable or ""),
            },
        )

    def _browser_profile_status(self, *, profile: str = "default") -> ToolResult:
        profile_name = self._normalize_profile_name(profile)
        source = self._embedded_browser_profile_dir(profile_name)
        backups = self._profile_backup_records(profile_name)
        imports = self._profile_import_records(profile_name)
        stats = self._directory_stats(source) if source.exists() else {"files": 0, "bytes": 0}
        lines = [
            f"Embedded browser profile status: {profile_name}",
            f"Browser root: {self.output_dir}",
            f"Profile: {source}",
            f"Profile exists: {source.exists()}",
            f"Profile files: {stats['files']}",
            f"Profile size: {self._format_size(stats['bytes'])}",
            f"Backups: {len(backups)}",
            f"Imported storage states: {len(imports)}",
        ]
        if backups:
            latest = backups[0]
            lines.append(f"Latest backup: {latest.get('backup_id')} ({latest.get('created_at')})")
        if imports:
            lines.append(f"Latest import: {imports[0].get('import_id')} ({imports[0].get('created_at')})")
        return ToolResult.ok(
            "\n".join(lines),
            data={"profile": profile_name, "profile_dir": str(source), "stats": stats, "backups": backups, "imports": imports},
        )

    def _browser_profile_backups(self, *, profile: str = "default") -> ToolResult:
        profile_name = self._normalize_profile_name(profile)
        backups = self._profile_backup_records(profile_name)
        if not backups:
            return ToolResult.ok(f"No embedded browser profile backups recorded for {profile_name}.", data={"profile": profile_name, "backups": []})
        lines = [f"Embedded browser profile backups for {profile_name}: {len(backups)}", ""]
        for item in backups[:30]:
            lines.append(
                f"- {item.get('backup_id')} | {item.get('created_at')} | "
                f"{self._format_size(item.get('bytes', 0))} | files={item.get('files', 0)} | status={item.get('status')}"
            )
        return ToolResult.ok("\n".join(lines), data={"profile": profile_name, "backups": backups})

    def _browser_profile_backup(self, *, profile: str = "default", include_cache: bool = True) -> ToolResult:
        profile_name = self._normalize_profile_name(profile)
        source = self._embedded_browser_profile_dir(profile_name)
        if not source.exists() or not source.is_dir():
            return ToolResult.fail(f"Embedded browser profile was not found: {source}")
        backup_id = time.strftime("%Y%m%d-%H%M%S", time.localtime())
        backup_dir = self.profile_backups_dir / profile_name / backup_id
        if backup_dir.exists():
            backup_id = f"{backup_id}-{int(time.time() * 1000) % 1000:03d}-{secrets.token_hex(2)}"
            backup_dir = self.profile_backups_dir / profile_name / backup_id
        backup_dir.mkdir(parents=True, exist_ok=False)
        started = time.time()
        copy_result = self._copy_browser_profile(source, backup_dir, include_cache=include_cache)
        stats = self._directory_stats(backup_dir)
        manifest = {
            "backup_id": backup_id,
            "profile": profile_name,
            "source_profile_dir": str(source),
            "backup_dir": str(backup_dir),
            "created_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "include_cache": bool(include_cache),
            "status": "success" if copy_result.get("success") else "partial",
            "duration_seconds": round(time.time() - started, 3),
            "files": stats["files"],
            "bytes": stats["bytes"],
            "copy": copy_result,
        }
        (backup_dir / "browser-profile-backup.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
        lines = [
            f"Backed up embedded browser profile {profile_name}.",
            f"Source: {source}",
            f"Backup: {backup_dir}",
            f"Files: {stats['files']}",
            f"Size: {self._format_size(stats['bytes'])}",
            f"Status: {manifest['status']}",
        ]
        if copy_result.get("warning"):
            lines.append(f"Warning: {copy_result['warning']}")
        if manifest["status"] != "success":
            lines.append(
                f"Backup is partial. Close Browser Controler sessions using profile {profile_name} and run /browser backup {profile_name} again."
            )
            return ToolResult.partial("\n".join(lines), f"Embedded profile {profile_name} backup is partial.", data=manifest)
        return ToolResult.ok("\n".join(lines), data=manifest)

    def _browser_profile_restore(self, *, profile: str = "default", backup_id: str = "", confirm: bool = False) -> ToolResult:
        profile_name = self._normalize_profile_name(profile)
        if not confirm:
            return ToolResult.fail("browser_profile_restore requires confirm=true because it writes to an embedded .reverie/browser profile.")
        backups = self._profile_backup_records(profile_name)
        selected = next((item for item in backups if str(item.get("backup_id") or "") == str(backup_id).strip()), None)
        if not selected:
            return ToolResult.fail(f"Backup id not found for embedded profile {profile_name}: {backup_id}")
        source = Path(str(selected.get("backup_dir") or ""))
        target = self._embedded_browser_profile_dir(profile_name)
        if self._profile_processes_running(target):
            return ToolResult.fail(f"Close Browser Controler sessions using profile {profile_name} before restoring a backup.")
        if not source.exists() or not source.is_dir():
            return ToolResult.fail(f"Backup directory is missing: {source}")
        restore_result = self._mirror_browser_profile(source, target)
        stats = self._directory_stats(target)
        lines = [
            f"Restored embedded browser profile {profile_name} backup {backup_id}.",
            f"Backup: {source}",
            f"Target: {target}",
            f"Files now: {stats['files']}",
            f"Size now: {self._format_size(stats['bytes'])}",
            f"Status: {'success' if restore_result.get('success') else 'partial'}",
        ]
        if restore_result.get("warning"):
            lines.append(f"Warning: {restore_result['warning']}")
        return ToolResult.ok("\n".join(lines), data={"profile": profile_name, "backup": selected, "restore": restore_result, "target": str(target)})

    def _browser_profile_import(self, *, file_path: Any, profile: str = "default", import_format: str = "auto") -> ToolResult:
        profile_name = self._normalize_profile_name(profile)
        selected_by_user = False
        if not file_path:
            selection = self._select_browser_import_file(profile_name)
            if selection.get("cancelled"):
                return ToolResult.ok(
                    "Browser data import cancelled by user.",
                    data={"profile": profile_name, "cancelled": True},
                )
            selected_path = str(selection.get("path") or "").strip()
            if not selected_path:
                return ToolResult.fail(
                    "No browser export files were found. Export cookies/storage state to the workspace, Desktop, "
                    "Documents, or Downloads, then retry browser_profile_import."
                )
            resolved = Path(selected_path).expanduser().resolve()
            selected_by_user = True
        else:
            resolved = self.resolve_workspace_path(file_path, purpose="import browser cookies or storage state")

        if not resolved.exists() or not resolved.is_file():
            return ToolResult.fail(f"Import file not found: {file_path}")
        if self._is_real_browser_profile_path(resolved):
            return ToolResult.fail(
                "Refusing to read a real browser profile. Export cookies/storage state to a separate file and select "
                "that exported copy instead."
            )
        try:
            file_bytes = int(resolved.stat().st_size)
        except OSError as exc:
            return ToolResult.fail(f"Could not inspect browser import file: {exc}")
        if file_bytes > BROWSER_IMPORT_MAX_BYTES:
            return ToolResult.fail(
                f"Browser import file is too large ({self._format_size(file_bytes)}); maximum is "
                f"{self._format_size(BROWSER_IMPORT_MAX_BYTES)}."
            )
        try:
            storage_state = self._load_import_storage_state(resolved, import_format=import_format)
        except Exception as exc:
            return ToolResult.fail(f"Could not read browser import file: {exc}")
        import_id = time.strftime("%Y%m%d-%H%M%S", time.localtime())
        import_dir = self.imports_dir / profile_name / import_id
        import_dir.mkdir(parents=True, exist_ok=False)
        storage_path = import_dir / "storage-state.json"
        source_copy = import_dir / resolved.name
        storage_path.write_text(json.dumps(storage_state, ensure_ascii=False, indent=2), encoding="utf-8")
        try:
            shutil.copy2(resolved, source_copy)
        except Exception:
            source_copy = resolved
        manifest = {
            "import_id": import_id,
            "profile": profile_name,
            "source": str(resolved),
            "source_copy": str(source_copy),
            "storage_state": str(storage_path),
            "created_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "cookies": len(storage_state.get("cookies") or []),
            "origins": len(storage_state.get("origins") or []),
            "selected_by_user": selected_by_user,
        }
        (import_dir / "browser-profile-import.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
        latest_path = self.imports_dir / profile_name / "latest-storage-state.json"
        latest_path.write_text(json.dumps(storage_state, ensure_ascii=False, indent=2), encoding="utf-8")
        return ToolResult.ok(
            f"Browser data imported into embedded profile {profile_name}: {manifest['cookies']} cookies, "
            f"{manifest['origins']} origins; copied to {import_dir}.",
            data=manifest,
        )

    def _select_browser_import_file(self, profile: str) -> Dict[str, Any]:
        """Let the user select and authorize one exported browser-data file."""
        console = self.context.get("console") if self.context else None
        if console is None or not bool(getattr(console, "is_terminal", False)):
            return {"path": "", "cancelled": False}

        candidates = self._browser_import_candidates()
        if not candidates:
            return {"path": "", "cancelled": False}

        from ..cli.tui_selector import SelectorAction, SelectorItem, TUISelector

        get_status_live = self.context.get("get_status_live") if self.context else None
        status_live = get_status_live() if callable(get_status_live) else None
        pause_stream_input = self.context.get("pause_stream_input_capture") if self.context else None
        resume_stream_input = self.context.get("resume_stream_input_capture") if self.context else None
        if status_live:
            status_live.stop()
        if callable(pause_stream_input):
            pause_stream_input()

        try:
            file_items = []
            for index, path in enumerate(candidates):
                try:
                    size = path.stat().st_size
                except OSError:
                    continue
                file_items.append(
                    SelectorItem(
                        id=str(index),
                        title=path.name,
                        description=str(path.parent),
                        metadata={
                            "path": str(path),
                            "size": self._format_size(size),
                            "profile": profile,
                        },
                    )
                )
            if not file_items:
                return {"path": "", "cancelled": False}
            selected = TUISelector(
                console,
                "Import Browser Data Export",
                file_items,
                allow_search=True,
                allow_cancel=True,
                show_descriptions=True,
                max_visible=10,
            ).run()
            if selected.action != SelectorAction.SELECT or selected.selected_item is None:
                return {"path": "", "cancelled": True}

            selected_path = Path(str((selected.selected_item.metadata or {}).get("path") or "")).resolve()
            if self._browser_import_always_allowed():
                return {"path": str(selected_path), "cancelled": False, "authorization": "always"}

            authorization = TUISelector(
                console,
                "Authorize Browser Data Import",
                [
                    SelectorItem(
                        id="once",
                        title="Allow once",
                        description="Read this selected export once and copy the normalized data into .reverie/browser.",
                    ),
                    SelectorItem(
                        id="always",
                        title="Always allow selected imports",
                        description="Skip this authorization step later; file selection is still always required.",
                    ),
                    SelectorItem(
                        id="cancel",
                        title="Cancel",
                        description="Do not read or import the selected file.",
                    ),
                ],
                allow_search=False,
                allow_cancel=True,
                show_descriptions=True,
                max_visible=3,
            ).run()
            if authorization.action != SelectorAction.SELECT or authorization.selected_item is None:
                return {"path": "", "cancelled": True}
            authorization_id = str(authorization.selected_item.id or "").strip().lower()
            if authorization_id == "cancel":
                return {"path": "", "cancelled": True}
            if authorization_id == "always":
                self._set_browser_import_always_allowed(True)
            return {
                "path": str(selected_path),
                "cancelled": False,
                "authorization": authorization_id,
            }
        finally:
            if callable(resume_stream_input):
                resume_stream_input()
            if status_live:
                status_live.start()

    def _browser_import_candidates(self) -> List[Path]:
        """Find likely user-exported cookie/storage-state files without reading real browser profiles."""
        roots: List[Path] = [self.project_root]
        home = Path.home()
        for name in ("Desktop", "Documents", "Downloads"):
            candidate = home / name
            if candidate.exists():
                roots.append(candidate)

        candidates: List[Path] = []
        seen: set[str] = set()
        for root in roots:
            try:
                resolved_root = root.resolve()
            except OSError:
                continue
            if self._is_real_browser_profile_path(resolved_root):
                continue
            for current_root, directory_names, file_names in os.walk(resolved_root):
                current = Path(current_root)
                try:
                    relative_depth = len(current.relative_to(resolved_root).parts)
                except ValueError:
                    continue
                directory_names[:] = [
                    name
                    for name in directory_names
                    if name.lower() not in BROWSER_IMPORT_SCAN_SKIP_DIRS
                    and not self._is_real_browser_profile_path(current / name)
                    and relative_depth < 3
                ]
                for file_name in file_names:
                    lower_name = file_name.lower()
                    suffix = Path(file_name).suffix.lower()
                    if suffix not in BROWSER_IMPORT_SUFFIXES:
                        continue
                    if lower_name != "cookies.txt" and not any(hint in lower_name for hint in BROWSER_IMPORT_NAME_HINTS):
                        continue
                    path = (current / file_name).resolve()
                    if self._is_real_browser_profile_path(path):
                        continue
                    try:
                        size = int(path.stat().st_size)
                    except OSError:
                        continue
                    if size <= 0 or size > BROWSER_IMPORT_MAX_BYTES:
                        continue
                    key = str(path).lower()
                    if key in seen:
                        continue
                    seen.add(key)
                    candidates.append(path)
                    if len(candidates) >= 200:
                        break
                if len(candidates) >= 200:
                    break
            if len(candidates) >= 200:
                break
        def sort_key(path: Path) -> tuple[int, str]:
            try:
                modified = int(path.stat().st_mtime_ns)
            except OSError:
                modified = 0
            return (-modified, str(path).lower())

        candidates.sort(key=sort_key)
        return candidates

    @staticmethod
    def _is_real_browser_profile_path(path: Path) -> bool:
        normalized = str(path.expanduser().resolve(strict=False)).replace("\\", "/").lower()
        return any(marker in f"{normalized}/" for marker in BROWSER_REAL_PROFILE_PATH_MARKERS)

    def _browser_import_always_allowed(self) -> bool:
        try:
            data = json.loads(self.import_consent_path.read_text(encoding="utf-8"))
        except Exception:
            return False
        return bool(isinstance(data, dict) and data.get("always_allow_selected_imports"))

    def _set_browser_import_always_allowed(self, allowed: bool) -> None:
        self.output_dir.mkdir(parents=True, exist_ok=True)
        payload = {
            "always_allow_selected_imports": bool(allowed),
            "updated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "scope": "selected exported files only",
        }
        self.import_consent_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    def _browser_profile_export(self, *, profile: str = "default", port: Any = None, timeout: float = 5.0) -> ToolResult:
        profile_name = self._normalize_profile_name(profile)
        selected_port = int(port or 0)
        if not selected_port:
            sessions = self._load_browser_sessions()
            for session in sessions.values():
                if str(session.get("profile") or "") == profile_name:
                    selected_port = int(session.get("port") or 0)
                    break
        if not selected_port:
            return ToolResult.fail("browser_profile_export requires a running embedded browser session port for now.")
        if not self._is_authorized_cdp_port(selected_port):
            return ToolResult.fail(f"Refusing to export from unrecorded DevTools port {selected_port}.")
        storage_state = self._read_storage_state_from_cdp(selected_port, timeout=timeout)
        export_dir = self.imports_dir / profile_name / "exports"
        export_dir.mkdir(parents=True, exist_ok=True)
        export_path = export_dir / f"storage-state-{int(time.time())}.json"
        export_path.write_text(json.dumps(storage_state, ensure_ascii=False, indent=2), encoding="utf-8")
        return ToolResult.ok(
            f"Exported embedded browser storage state: {export_path}",
            data={"profile": profile_name, "path": str(export_path), "cookies": len(storage_state.get("cookies") or []), "origins": len(storage_state.get("origins") or [])},
        )

    def _safety_policy(self) -> ToolResult:
        lines = [
            "Browser Controler Safety Policy:",
            "- Browser Controler uses Reverie's embedded open-source Chromium runtime, not the real system Edge/Chrome executable.",
            "- All runtime, profile, cookies, imports, backups, downloads, pages, screenshots, and sessions stay under the app root .reverie/browser directory.",
            "- The tool must not read, back up, modify, or launch a user's real browser profile.",
            "- Credentials/cookies can be imported only from user-selected exported storage-state, cookie JSON, or Netscape cookies.txt files.",
            "- Interactive imports scan export-like files in the workspace, Desktop, Documents, and Downloads, then require explicit user selection and authorization.",
            "- DevTools actions only attach to ports recorded by Browser Controler sessions with safe .reverie/browser/profiles paths.",
            "- Visible UI actions refuse non-embedded browser windows, even when the active window is Chrome or Edge.",
            "- Use /browser status, /browser import, /browser backup, /browser backups, and /browser restore <profile> <backup_id> confirm for embedded profile management.",
            "- Use background CDP actions for observation and diagnostics; use visible UI actions only when foreground interaction is required.",
            "- Do not enter credentials, submit payments, or mutate account/security settings unless the user explicitly asks in the current context.",
            "- Upload only workspace files or user-provided files, and verify destination/intent before uploading to external services.",
            "- Treat web AI services as optional helpers; verify their advice against local code and tests before applying it.",
        ]
        return ToolResult.ok("\n".join(lines), data={"policy": lines[1:]})

    def _devtools_targets(self, *, port: int, url_contains: str = "", timeout: float = 5.0) -> ToolResult:
        targets = self._cdp_list_targets(port, timeout=timeout)
        needle = str(url_contains or "").strip().lower()
        if needle:
            targets = [
                item for item in targets
                if needle in str(item.get("url") or "").lower() or needle in str(item.get("title") or "").lower()
            ]
        lines = [f"DevTools targets on {CDP_HOST}:{port}: {len(targets)}"]
        for index, item in enumerate(targets[:60]):
            websocket = "yes" if item.get("webSocketDebuggerUrl") else "no"
            lines.append(
                f"[{index}] id={item.get('id')} type={item.get('type')} websocket={websocket}\n"
                f"    title={item.get('title') or '(untitled)'}\n"
                f"    url={item.get('url') or '(empty)'}"
            )
        return ToolResult.ok("\n".join(lines), data={"port": port, "targets": targets})

    def _devtools_snapshot(
        self,
        *,
        port: int,
        target_id: str = "",
        url_contains: str = "",
        max_chars: int = 30000,
        timeout: float = 5.0,
    ) -> ToolResult:
        expression = (
            "(() => ({"
            "url: location.href,"
            "title: document.title,"
            "text: document.body ? document.body.innerText : '',"
            "html: document.documentElement ? document.documentElement.outerHTML : ''"
            "}))()"
        )
        target = self._cdp_select_target(port, target_id=target_id, url_contains=url_contains, timeout=timeout)
        with _CdpConnection(str(target["webSocketDebuggerUrl"]), timeout=timeout) as cdp:
            self._safe_cdp_call(cdp, "Runtime.enable", timeout=timeout)
            result = cdp.call(
                "Runtime.evaluate",
                {
                    "expression": expression,
                    "awaitPromise": True,
                    "returnByValue": True,
                    "userGesture": True,
                },
                timeout=timeout,
            )
        if result.get("exceptionDetails"):
            details = self._format_cdp_exception(result.get("exceptionDetails") or {})
            return ToolResult.partial(f"DevTools DOM snapshot raised an exception:\n{details}", details, data={"target": target})
        value = (result.get("result") or {}).get("value") or {}
        page_url = str(value.get("url") or target.get("url") or "")
        title = str(value.get("title") or target.get("title") or "")
        text = str(value.get("text") or "")
        html = str(value.get("html") or "")
        saved = self._persist_page_artifacts(page_url or "devtools-snapshot", html, text)
        clipped = text[: max(1, int(max_chars))]
        lines = [
            f"URL: {page_url}",
            f"Title: {title or '(missing)'}",
            f"Text chars: {len(text)}",
            f"HTML chars: {len(html)}",
            "",
            "Live DOM Text:",
            clipped,
        ]
        if len(text) > len(clipped):
            lines.append(f"\n[truncated; full text saved to {saved.get('text_path')}]")
        lines.append(f"\nSaved full page text: {saved.get('text_path')}")
        lines.append(f"Saved HTML: {saved.get('html_path')}")
        return ToolResult.ok(
            "\n".join(lines).strip(),
            data={"target": target, "url": page_url, "title": title, "text_chars": len(text), "html_chars": len(html), **saved},
        )

    def _devtools_eval(
        self,
        *,
        expression: str,
        port: int,
        target_id: str = "",
        url_contains: str = "",
        await_promise: bool = True,
        return_by_value: bool = True,
        timeout: float = 5.0,
    ) -> ToolResult:
        if not str(expression or "").strip():
            return ToolResult.fail("expression is required for devtools_eval")
        target = self._cdp_select_target(port, target_id=target_id, url_contains=url_contains, timeout=timeout)
        with _CdpConnection(str(target["webSocketDebuggerUrl"]), timeout=timeout) as cdp:
            self._safe_cdp_call(cdp, "Runtime.enable", timeout=timeout)
            result = cdp.call(
                "Runtime.evaluate",
                {
                    "expression": expression,
                    "awaitPromise": bool(await_promise),
                    "returnByValue": bool(return_by_value),
                    "userGesture": True,
                },
                timeout=timeout,
            )
        remote = result.get("result") or {}
        value = self._format_cdp_remote_object(remote)
        lines = [
            "DevTools Console Evaluation:",
            f"Target: {target.get('title') or '(untitled)'}",
            f"URL: {target.get('url') or '(empty)'}",
            f"Type: {remote.get('type') or 'unknown'}",
            f"Value: {value}",
        ]
        if result.get("exceptionDetails"):
            details = self._format_cdp_exception(result.get("exceptionDetails") or {})
            lines.append("\nException:\n" + details)
            return ToolResult.partial("\n".join(lines), "DevTools expression raised an exception.", data={"target": target, "result": result})
        return ToolResult.ok("\n".join(lines), data={"target": target, "result": result, "value": remote.get("value")})

    def _devtools_console(
        self,
        *,
        expression: str = "",
        port: int,
        target_id: str = "",
        url_contains: str = "",
        wait_seconds: float = 1.0,
        max_events: int = 80,
        timeout: float = 5.0,
    ) -> ToolResult:
        target = self._cdp_select_target(port, target_id=target_id, url_contains=url_contains, timeout=timeout)
        eval_result: Dict[str, Any] = {}
        with _CdpConnection(str(target["webSocketDebuggerUrl"]), timeout=timeout) as cdp:
            self._safe_cdp_call(cdp, "Runtime.enable", timeout=timeout)
            self._safe_cdp_call(cdp, "Log.enable", timeout=timeout)
            if expression.strip():
                eval_result = cdp.call(
                    "Runtime.evaluate",
                    {
                        "expression": expression,
                        "awaitPromise": True,
                        "returnByValue": True,
                        "userGesture": True,
                    },
                    timeout=timeout,
                )
            cdp.collect(max(0.0, min(float(wait_seconds or 0.0), 30.0)))
            events = list(cdp.events)
        lines = [
            f"DevTools console/log events for {target.get('title') or '(untitled)'}",
            f"URL: {target.get('url') or '(empty)'}",
        ]
        if eval_result:
            remote = eval_result.get("result") or {}
            lines.append(f"Evaluation value: {self._format_cdp_remote_object(remote)}")
            if eval_result.get("exceptionDetails"):
                lines.append("Evaluation exception: " + self._format_cdp_exception(eval_result.get("exceptionDetails") or {}))
        rendered = self._render_cdp_console_events(events, max_events=max_events)
        if rendered:
            lines.append("\nEvents:")
            lines.extend(rendered)
        else:
            lines.append("\nNo console/log events were observed after Runtime/Log were enabled.")
        return ToolResult.ok("\n".join(lines), data={"target": target, "events": events, "evaluation": eval_result})

    def _devtools_network(
        self,
        *,
        url: Any = None,
        port: int,
        target_id: str = "",
        url_contains: str = "",
        wait_seconds: float = 3.0,
        include_bodies: bool = False,
        include_request_body: bool = False,
        include_websockets: bool = False,
        export_har: bool = False,
        filter_url: str = "",
        filter_method: str = "",
        filter_status: str = "",
        max_body_chars: int = 2000,
        max_events: int = 120,
        reload: bool = False,
        timeout: float = 5.0,
    ) -> ToolResult:
        target = self._cdp_select_target(port, target_id=target_id, url_contains=url_contains, timeout=timeout)
        navigate_url = str(url or "").strip()
        with _CdpConnection(str(target["webSocketDebuggerUrl"]), timeout=timeout) as cdp:
            self._safe_cdp_call(cdp, "Network.enable", timeout=timeout)
            self._safe_cdp_call(cdp, "Page.enable", timeout=timeout)
            if navigate_url:
                cdp.call("Page.navigate", {"url": navigate_url}, timeout=timeout)
            elif reload:
                cdp.call("Page.reload", {"ignoreCache": True}, timeout=timeout)
            cdp.collect(max(0.1, min(float(wait_seconds or 0.0), 60.0)))
            summary = self._summarize_cdp_network_events(
                cdp.events,
                max_events=max_events,
                include_request_body=include_request_body,
                include_websockets=include_websockets,
                filter_url=filter_url,
                filter_method=filter_method,
                filter_status=filter_status,
            )
            if include_bodies:
                self._attach_cdp_response_bodies(cdp, summary["responses"], max_body_chars=max_body_chars, timeout=min(timeout, 3.0))
            if export_har:
                summary["har_path"] = str(self._persist_json("devtools-network-har", self._build_simple_har(summary)))
        output = self._render_cdp_network_summary(summary, target=target)
        return ToolResult.ok(output, data={"target": target, **summary})

    def _devtools_screenshot(
        self,
        *,
        port: int,
        target_id: str = "",
        url_contains: str = "",
        full_page: bool = True,
        image_format: str = "png",
        quality: int = 90,
        observation_name: str = "devtools-page",
        timeout: float = 5.0,
    ) -> ToolResult:
        fmt = str(image_format or "png").strip().lower()
        if fmt not in {"png", "jpeg"}:
            return ToolResult.fail("format must be png or jpeg for devtools_screenshot")
        target = self._cdp_select_target(port, target_id=target_id, url_contains=url_contains, timeout=timeout)
        params: Dict[str, Any] = {"format": fmt, "fromSurface": True, "captureBeyondViewport": bool(full_page)}
        if fmt == "jpeg":
            params["quality"] = max(1, min(int(quality or 90), 100))
        fallback_error = ""
        with _CdpConnection(str(target["webSocketDebuggerUrl"]), timeout=timeout) as cdp:
            self._safe_cdp_call(cdp, "Page.enable", timeout=timeout)
            try:
                result = cdp.call("Page.captureScreenshot", params, timeout=max(timeout, 10.0))
            except Exception as exc:
                if not full_page:
                    raise
                fallback_error = str(exc)
                params["captureBeyondViewport"] = False
                result = cdp.call("Page.captureScreenshot", params, timeout=max(timeout, 10.0))
        encoded = str(result.get("data") or "")
        if not encoded:
            return ToolResult.fail("DevTools screenshot returned no image data.")
        stem = re.sub(r"[^A-Za-z0-9._-]+", "-", str(observation_name or "devtools-page")).strip("-._") or "devtools-page"
        suffix = "jpg" if fmt == "jpeg" else "png"
        path = self.observations_dir / f"{stem}-{int(time.time() * 1000)}.{suffix}"
        path.write_bytes(base64.b64decode(encoded))
        return ToolResult.ok(
            f"Saved DevTools screenshot: {path}" + (" (full-page capture fell back to viewport capture)." if fallback_error else ""),
            data={"image_path": str(path), "format": fmt, "target": target, "full_page": full_page, "fallback_error": fallback_error},
        )

    def _devtools_click(self, *, selector: str, port: int, target_id: str = "", url_contains: str = "", timeout: float = 5.0) -> ToolResult:
        if not selector.strip():
            return ToolResult.fail("selector is required for devtools_click")
        script = (
            "(() => {"
            f"const selector = {json.dumps(selector)};"
            "const el = document.querySelector(selector);"
            "if (!el) return {ok:false, error:'selector not found', selector};"
            "el.scrollIntoView({block:'center', inline:'center'});"
            "const rect = el.getBoundingClientRect();"
            "el.click();"
            "return {ok:true, selector, tag:el.tagName, id:el.id || '',"
            "text:(el.innerText || el.value || el.getAttribute('aria-label') || '').slice(0,240),"
            "rect:{x:rect.x, y:rect.y, width:rect.width, height:rect.height}};"
            "})()"
        )
        return self._devtools_dom_action("Clicked element through DevTools", script, port=port, target_id=target_id, url_contains=url_contains, timeout=timeout)

    def _devtools_type(
        self,
        *,
        selector: str,
        text: str,
        port: int,
        target_id: str = "",
        url_contains: str = "",
        clear: bool = True,
        press_enter: bool = False,
        timeout: float = 5.0,
    ) -> ToolResult:
        if not selector.strip():
            return ToolResult.fail("selector is required for devtools_type")
        script = (
            "(async () => {"
            f"const selector = {json.dumps(selector)};"
            f"const value = {json.dumps(text)};"
            f"const clear = {json.dumps(bool(clear))};"
            f"const pressEnter = {json.dumps(bool(press_enter))};"
            "const el = document.querySelector(selector);"
            "if (!el) return {ok:false, error:'selector not found', selector};"
            "el.scrollIntoView({block:'center', inline:'center'});"
            "el.focus();"
            "if ('value' in el) { if (clear) el.value = ''; el.value = clear ? value : (el.value + value); }"
            "else if (el.isContentEditable) { if (clear) el.textContent = ''; el.textContent = clear ? value : (el.textContent + value); }"
            "else return {ok:false, error:'element is not editable', selector, tag:el.tagName};"
            "el.dispatchEvent(new InputEvent('input', {bubbles:true, inputType:'insertText', data:value}));"
            "el.dispatchEvent(new Event('change', {bubbles:true}));"
            "if (pressEnter) {"
            "  el.dispatchEvent(new KeyboardEvent('keydown', {key:'Enter', code:'Enter', bubbles:true}));"
            "  el.dispatchEvent(new KeyboardEvent('keyup', {key:'Enter', code:'Enter', bubbles:true}));"
            "}"
            "return {ok:true, selector, tag:el.tagName, id:el.id || '', value:('value' in el ? el.value : el.textContent).slice(0,240)};"
            "})()"
        )
        return self._devtools_dom_action("Typed into element through DevTools", script, port=port, target_id=target_id, url_contains=url_contains, timeout=timeout)

    def _devtools_upload(
        self,
        *,
        selector: str,
        file_path: Any,
        port: int,
        target_id: str = "",
        url_contains: str = "",
        timeout: float = 5.0,
    ) -> ToolResult:
        if not selector.strip():
            return ToolResult.fail("selector is required for devtools_upload")
        if not file_path:
            return ToolResult.fail("file_path is required for devtools_upload")
        resolved = self.resolve_workspace_path(file_path, purpose="upload browser file")
        if not resolved.exists() or not resolved.is_file():
            return ToolResult.fail(f"Upload file not found: {file_path}")
        target = self._cdp_select_target(port, target_id=target_id, url_contains=url_contains, timeout=timeout)
        with _CdpConnection(str(target["webSocketDebuggerUrl"]), timeout=timeout) as cdp:
            self._safe_cdp_call(cdp, "DOM.enable", timeout=timeout)
            root = cdp.call("DOM.getDocument", {"depth": 1, "pierce": True}, timeout=timeout)
            root_id = int(((root.get("root") or {}).get("nodeId")) or 0)
            if not root_id:
                return ToolResult.fail("DevTools DOM.getDocument returned no root node.")
            result = cdp.call("DOM.querySelector", {"nodeId": root_id, "selector": selector}, timeout=timeout)
            node_id = int(result.get("nodeId") or 0)
            if not node_id:
                return ToolResult.fail(f"No file input matched selector: {selector}")
            cdp.call("DOM.setFileInputFiles", {"nodeId": node_id, "files": [str(resolved)]}, timeout=timeout)
        return ToolResult.ok(
            f"Uploaded file through DevTools selector {selector}: {resolved}",
            data={"target": target, "selector": selector, "file_path": str(resolved)},
        )

    def _devtools_wait_for(
        self,
        *,
        selector: str = "",
        text: str = "",
        expression: str = "",
        port: int,
        target_id: str = "",
        url_contains: str = "",
        wait_seconds: float = 10.0,
        poll_interval: float = 0.25,
        timeout: float = 5.0,
    ) -> ToolResult:
        if not selector.strip() and not text.strip() and not expression.strip():
            return ToolResult.fail("selector, text, or expression is required for devtools_wait_for")
        target = self._cdp_select_target(port, target_id=target_id, url_contains=url_contains, timeout=timeout)
        if selector.strip():
            condition = f"Boolean(document.querySelector({json.dumps(selector)}))"
            label = f"selector {selector!r}"
        elif text.strip():
            condition = f"Boolean((document.body && document.body.innerText || '').includes({json.dumps(text)}))"
            label = f"text {text!r}"
        else:
            condition = f"Boolean(({expression}))"
            label = "expression"
        deadline = time.time() + max(0.1, min(float(wait_seconds or 10.0), 120.0))
        interval = max(0.05, min(float(poll_interval or 0.25), 5.0))
        last_value = None
        with _CdpConnection(str(target["webSocketDebuggerUrl"]), timeout=timeout) as cdp:
            self._safe_cdp_call(cdp, "Runtime.enable", timeout=timeout)
            while time.time() < deadline:
                result = cdp.call(
                    "Runtime.evaluate",
                    {"expression": f"(() => {condition})()", "awaitPromise": True, "returnByValue": True},
                    timeout=timeout,
                )
                last_value = (result.get("result") or {}).get("value")
                if last_value:
                    return ToolResult.ok(f"DevTools wait_for matched {label}.", data={"target": target, "matched": True, "value": last_value})
                time.sleep(interval)
        return ToolResult.fail(f"Timed out waiting for {label}. Last value: {last_value!r}")

    def _devtools_accessibility_snapshot(
        self,
        *,
        port: int,
        target_id: str = "",
        url_contains: str = "",
        max_events: int = 120,
        timeout: float = 5.0,
    ) -> ToolResult:
        target = self._cdp_select_target(port, target_id=target_id, url_contains=url_contains, timeout=timeout)
        with _CdpConnection(str(target["webSocketDebuggerUrl"]), timeout=timeout) as cdp:
            self._safe_cdp_call(cdp, "Accessibility.enable", timeout=timeout)
            result = cdp.call("Accessibility.getFullAXTree", {}, timeout=max(timeout, 10.0))
        nodes = list(result.get("nodes") or [])
        rendered = self._render_ax_nodes(nodes, max_events=max_events)
        lines = [
            f"Accessibility snapshot for {target.get('title') or '(untitled)'}",
            f"URL: {target.get('url') or '(empty)'}",
            f"AX nodes: {len(nodes)}",
            "",
            *rendered,
        ]
        return ToolResult.ok("\n".join(lines).strip(), data={"target": target, "nodes": nodes[: max(1, int(max_events or 120))], "node_count": len(nodes)})

    def _devtools_dom_outline(
        self,
        *,
        port: int,
        target_id: str = "",
        url_contains: str = "",
        max_events: int = 120,
        timeout: float = 5.0,
    ) -> ToolResult:
        script = (
            "(() => {"
            "const clip = v => String(v || '').replace(/\\s+/g, ' ').trim().slice(0, 240);"
            "const attrs = el => ({id:el.id || '', role:el.getAttribute('role') || '', name:el.getAttribute('name') || '',"
            "aria:el.getAttribute('aria-label') || '', testid:el.getAttribute('data-testid') || '', selector:el.tagName.toLowerCase() + (el.id ? '#' + el.id : '')});"
            "const collect = (sel, limit=80) => Array.from(document.querySelectorAll(sel)).slice(0, limit).map(el => ({tag:el.tagName, text:clip(el.innerText || el.value || el.alt || ''), href:el.href || '', type:el.type || '', ...attrs(el)}));"
            "return {url:location.href, title:document.title, headings:collect('h1,h2,h3,h4,h5,h6'),"
            "controls:collect('button,input,textarea,select,[role=button],[role=textbox],[contenteditable=true]'),"
            "links:collect('a[href]'), forms:collect('form'), images:collect('img')};"
            "})()"
        )
        result = self._devtools_eval_value(script, port=port, target_id=target_id, url_contains=url_contains, timeout=timeout)
        if not result.get("ok"):
            return ToolResult.fail(str(result.get("error") or "DevTools DOM outline failed"))
        outline = result.get("value") or {}
        lines = self._render_dom_outline(outline, max_events=max_events)
        return ToolResult.ok("\n".join(lines).strip(), data={"outline": outline, "target": result.get("target")})

    def _devtools_find(
        self,
        *,
        selector: str = "",
        text: str = "",
        role: str = "",
        port: int,
        target_id: str = "",
        url_contains: str = "",
        max_events: int = 80,
        timeout: float = 5.0,
    ) -> ToolResult:
        script = (
            "(() => {"
            f"const selector = {json.dumps(selector)};"
            f"const textNeedle = {json.dumps(text.lower())};"
            f"const roleNeedle = {json.dumps(role.lower())};"
            "const clip = v => String(v || '').replace(/\\s+/g, ' ').trim().slice(0, 240);"
            "let nodes = selector ? Array.from(document.querySelectorAll(selector)) : Array.from(document.querySelectorAll('a,button,input,textarea,select,[role],h1,h2,h3,h4,h5,h6,[data-testid]'));"
            "const matches = [];"
            "for (const el of nodes) {"
            " const role = (el.getAttribute('role') || '').toLowerCase();"
            " const label = clip(el.innerText || el.value || el.getAttribute('aria-label') || el.alt || el.name || el.id);"
            " if (textNeedle && !label.toLowerCase().includes(textNeedle)) continue;"
            " if (roleNeedle && role !== roleNeedle) continue;"
            " const rect = el.getBoundingClientRect();"
            " matches.push({tag:el.tagName, role, id:el.id || '', name:el.name || '', type:el.type || '', text:label, href:el.href || '',"
            " selector:el.tagName.toLowerCase() + (el.id ? '#' + el.id : ''), rect:{x:rect.x, y:rect.y, width:rect.width, height:rect.height}});"
            " if (matches.length >= 200) break;"
            "}"
            "return {url:location.href, title:document.title, count:matches.length, matches};"
            "})()"
        )
        result = self._devtools_eval_value(script, port=port, target_id=target_id, url_contains=url_contains, timeout=timeout)
        if not result.get("ok"):
            return ToolResult.fail(str(result.get("error") or "DevTools find failed"))
        value = result.get("value") or {}
        matches = list(value.get("matches") or [])[: max(1, int(max_events or 80))]
        lines = [f"DevTools find: {len(matches)} rendered of {value.get('count', 0)} match(es)", f"URL: {value.get('url') or ''}", ""]
        for item in matches:
            label = item.get("text") or item.get("id") or item.get("name") or "(no label)"
            lines.append(f"- {item.get('tag')} role={item.get('role') or '-'} selector={item.get('selector') or '-'} text={label}")
        return ToolResult.ok("\n".join(lines).strip(), data={"target": result.get("target"), **value, "matches": matches})

    def _devtools_dom_action(
        self,
        title: str,
        script: str,
        *,
        port: int,
        target_id: str = "",
        url_contains: str = "",
        timeout: float = 5.0,
    ) -> ToolResult:
        result = self._devtools_eval_value(script, port=port, target_id=target_id, url_contains=url_contains, timeout=timeout)
        if not result.get("ok"):
            return ToolResult.fail(str(result.get("error") or f"{title} failed"))
        value = result.get("value")
        if isinstance(value, dict) and not value.get("ok", True):
            return ToolResult.fail(str(value.get("error") or f"{title} failed"))
        return ToolResult.ok(f"{title}: {json.dumps(value, ensure_ascii=False)}", data={"target": result.get("target"), "result": value})

    def _devtools_eval_value(
        self,
        expression: str,
        *,
        port: int,
        target_id: str = "",
        url_contains: str = "",
        timeout: float = 5.0,
    ) -> Dict[str, Any]:
        target = self._cdp_select_target(port, target_id=target_id, url_contains=url_contains, timeout=timeout)
        with _CdpConnection(str(target["webSocketDebuggerUrl"]), timeout=timeout) as cdp:
            self._safe_cdp_call(cdp, "Runtime.enable", timeout=timeout)
            result = cdp.call(
                "Runtime.evaluate",
                {"expression": expression, "awaitPromise": True, "returnByValue": True, "userGesture": True},
                timeout=timeout,
            )
        if result.get("exceptionDetails"):
            return {"ok": False, "target": target, "error": self._format_cdp_exception(result.get("exceptionDetails") or {}), "result": result}
        return {"ok": True, "target": target, "value": (result.get("result") or {}).get("value"), "result": result}

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
            if self._is_browser_controler_window(active):
                return None
            return ToolResult.fail(
                "Refusing to control the active non-embedded browser window. "
                f"{self._render_window_info(active, prefix='Active window')}. "
                "Use open_page or browser_session_start so Browser Controler launches its embedded Chromium runtime."
            )
        return ToolResult.fail(
            "Active window is not a recognized browser. "
            f"{self._render_window_info(active, prefix='Active window')}. "
            "Use list_browser_windows and activate_browser first."
        )

    def _require_isolated_active_browser(self) -> Optional[ToolResult]:
        self._require_windows_desktop()
        active = self._foreground_window_info()
        if not active.get("is_browser"):
            return ToolResult.fail(
                "Active window is not a recognized browser. "
                f"{self._render_window_info(active, prefix='Active window')}. "
                "Use open_page or browser_session_start so Browser Controler creates an isolated profile first."
            )
        if not self._is_browser_controler_window(active):
            return ToolResult.fail(
                "Refusing to control a non-embedded browser window. "
                f"{self._render_window_info(active, prefix='Active window')}. "
                "Browser Controler UI actions only operate on its embedded runtime with .reverie/browser/profiles."
            )
        return None

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

    def _restore_foreground_window(self, hwnd: int) -> bool:
        self._require_windows_desktop()
        hwnd_value = int(hwnd or 0)
        if not hwnd_value:
            return False
        try:
            if int(user32.GetForegroundWindow() or 0) == hwnd_value:
                return True
            self._activate_window_handle(hwnd_value)
            return int(user32.GetForegroundWindow() or 0) == hwnd_value
        except Exception:
            return False

    def _minimize_browser_window_handles(self, windows: Sequence[Dict[str, Any]]) -> List[int]:
        self._require_windows_desktop()
        minimized: List[int] = []
        seen: set[int] = set()
        for item in windows:
            if not item.get("is_browser"):
                continue
            hwnd = int(item.get("handle") or 0)
            if not hwnd or hwnd in seen:
                continue
            seen.add(hwnd)
            if self._minimize_window_handle(hwnd):
                minimized.append(hwnd)
        return minimized

    def _minimize_window_handle(self, hwnd: int) -> bool:
        self._require_windows_desktop()
        hwnd_value = wintypes.HWND(int(hwnd or 0))
        if not hwnd_value:
            return False
        try:
            user32.ShowWindow(hwnd_value, SW_SHOWMINNOACTIVE)
            time.sleep(0.1)
            return bool(user32.IsIconic(hwnd_value))
        except Exception:
            return False

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
        if not IS_WINDOWS:
            try:
                return str((Path("/proc") / str(int(process_id)) / "exe").resolve(strict=True))
            except Exception:
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

    def _process_command_line(self, process_id: int) -> str:
        if not process_id:
            return ""
        if not IS_WINDOWS:
            try:
                raw = (Path("/proc") / str(int(process_id)) / "cmdline").read_bytes()
                return raw.replace(b"\0", b" ").decode("utf-8", errors="replace").strip()
            except Exception:
                return ""
        script = (
            "$p = Get-CimInstance Win32_Process -Filter "
            f"'ProcessId = {int(process_id)}' -ErrorAction SilentlyContinue; "
            "if ($p) { [Console]::OutputEncoding = [Text.Encoding]::UTF8; $p.CommandLine }"
        )
        try:
            completed = subprocess.run(
                ["powershell", "-NoProfile", "-NonInteractive", "-Command", script],
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=3,
            )
        except Exception:
            return ""
        return str(completed.stdout or "").strip()

    def _is_browser_controler_window(self, info: Dict[str, Any]) -> bool:
        if not info.get("is_browser"):
            return False
        return self._is_browser_controler_process(int(info.get("process_id") or 0))

    def _is_browser_controler_process(self, process_id: int) -> bool:
        process_path = self._process_path(process_id)
        if not process_path or not self._is_safe_embedded_runtime_path(Path(process_path)):
            return False
        command_line = self._process_command_line(process_id)
        profile_dir = self._user_data_dir_from_command_line(command_line)
        return bool(profile_dir and self._is_safe_debug_profile_path(profile_dir))

    def _terminate_embedded_browser_session_process(self, session: Dict[str, Any]) -> Dict[str, Any]:
        validation = self._validate_embedded_browser_session_process(session)
        if not validation.get("valid"):
            return {
                "terminated": False,
                "already_closed": bool(validation.get("already_closed")),
                "reason": validation.get("reason") or "embedded process validation failed",
            }
        process_id = int(validation["process_id"])
        if not IS_WINDOWS:
            return {"terminated": False, "already_closed": False, "reason": "verified fallback termination is only implemented on Windows"}
        try:
            completed = subprocess.run(
                ["taskkill", "/PID", str(process_id), "/T", "/F"],
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=10,
            )
        except Exception as exc:
            return {"terminated": False, "already_closed": False, "reason": str(exc)}
        return {
            "terminated": completed.returncode == 0,
            "already_closed": False,
            "reason": str(completed.stderr or completed.stdout or "").strip(),
            "process_id": process_id,
        }

    def _cleanup_failed_embedded_browser_launch(
        self,
        *,
        process: subprocess.Popen,
        executable: Path,
        profile_dir: Path,
    ) -> str:
        termination = self._terminate_embedded_browser_session_process(
            {
                "process_id": int(process.pid or 0),
                "browser": str(executable),
                "profile_dir": str(profile_dir),
            }
        )
        if termination.get("terminated"):
            return "stopped the verified isolated Chromium process tree"
        if termination.get("already_closed"):
            return "isolated Chromium process already exited"
        return f"refused process cleanup because verification failed: {termination.get('reason') or 'unknown reason'}"

    def _validate_embedded_browser_session_process(self, session: Dict[str, Any]) -> Dict[str, Any]:
        process_id = int(session.get("process_id") or 0)
        if not process_id:
            return {"valid": False, "already_closed": False, "reason": "session has no process id"}
        actual_path_text = self._process_path(process_id)
        if not actual_path_text:
            return {"valid": False, "already_closed": True, "reason": "process already exited"}
        actual_path = Path(actual_path_text).resolve()
        recorded_path_text = str(session.get("browser") or "").strip()
        profile_path_text = str(session.get("profile_dir") or "").strip()
        if not recorded_path_text or not profile_path_text:
            return {"valid": False, "already_closed": False, "reason": "session is missing embedded runtime/profile paths"}
        recorded_path = Path(recorded_path_text).resolve()
        profile_path = Path(profile_path_text).resolve()
        if not self._is_safe_embedded_runtime_path(actual_path) or not self._is_safe_embedded_runtime_path(recorded_path):
            return {"valid": False, "already_closed": False, "reason": "process executable is outside .reverie/browser/runtime"}
        if actual_path != recorded_path:
            return {"valid": False, "already_closed": False, "reason": "running executable does not match the recorded embedded runtime"}
        if not self._is_safe_debug_profile_path(profile_path):
            return {"valid": False, "already_closed": False, "reason": "process profile is outside .reverie/browser/profiles"}
        command_profile = self._user_data_dir_from_command_line(self._process_command_line(process_id))
        if not command_profile or command_profile.resolve() != profile_path:
            return {"valid": False, "already_closed": False, "reason": "running process does not use the recorded embedded profile"}
        return {
            "valid": True,
            "already_closed": False,
            "reason": "",
            "process_id": process_id,
        }

    @staticmethod
    def _user_data_dir_from_command_line(command_line: str) -> Optional[Path]:
        text = str(command_line or "")
        if not text:
            return None
        match = re.search(r"--user-data-dir=(?:\"([^\"]+)\"|([^\s]+))", text, flags=re.IGNORECASE)
        if not match:
            return None
        raw = (match.group(1) or match.group(2) or "").strip()
        return Path(raw).expanduser() if raw else None

    @staticmethod
    def _is_browser_process(process_name: str, process_path: str = "") -> bool:
        lowered_name = str(process_name or "").strip().lower()
        if lowered_name in BROWSER_PROCESS_NAMES:
            return True
        lowered_path = str(process_path or "").replace("\\", "/").lower()
        return any(f"/{name[:-4]}/" in lowered_path for name in BROWSER_PROCESS_NAMES if name.endswith(".exe"))

    @staticmethod
    def _normalize_cdp_port(port: Any) -> int:
        value = int(port or DEFAULT_CDP_PORT)
        if value <= 0 or value > 65535:
            raise ValueError(f"Invalid DevTools Protocol port: {port}")
        return value

    @staticmethod
    def _cdp_base_url(port: int) -> str:
        return f"http://{CDP_HOST}:{BrowserControlerTool._normalize_cdp_port(port)}"

    def _cdp_version(self, port: int, *, timeout: float = 5.0) -> Dict[str, Any]:
        response = requests.get(f"{self._cdp_base_url(port)}/json/version", timeout=max(0.5, float(timeout or 5.0)))
        response.raise_for_status()
        return response.json()

    def _cdp_list_targets(self, port: int, *, timeout: float = 5.0) -> List[Dict[str, Any]]:
        if not self._is_authorized_cdp_port(port):
            raise RuntimeError(
                f"Refusing to attach to DevTools Protocol port {port}; it is not a recorded isolated Browser Controler session."
            )
        response = requests.get(f"{self._cdp_base_url(port)}/json/list", timeout=max(0.5, float(timeout or 5.0)))
        response.raise_for_status()
        targets = response.json()
        if not isinstance(targets, list):
            raise RuntimeError("DevTools /json/list did not return a target list")
        return [item for item in targets if isinstance(item, dict)]

    def _cdp_create_target(self, port: int, url: str, *, timeout: float = 5.0) -> Dict[str, Any]:
        if not self._is_authorized_cdp_port(port):
            raise RuntimeError(
                f"Refusing to create a DevTools target on port {port}; it is not a recorded isolated Browser Controler session."
            )
        endpoint = f"{self._cdp_base_url(port)}/json/new?{quote(str(url or 'about:blank'), safe=':/?&=%#')}"
        try:
            response = requests.put(endpoint, timeout=max(0.5, float(timeout or 5.0)))
            response.raise_for_status()
            result = response.json()
        except Exception:
            response = requests.get(endpoint, timeout=max(0.5, float(timeout or 5.0)))
            response.raise_for_status()
            result = response.json()
        if not isinstance(result, dict):
            raise RuntimeError("DevTools target creation did not return a target object")
        return result

    def _cdp_select_target(
        self,
        port: int,
        *,
        target_id: str = "",
        url_contains: str = "",
        timeout: float = 5.0,
    ) -> Dict[str, Any]:
        targets = self._cdp_list_targets(port, timeout=timeout)
        if target_id:
            for item in targets:
                if str(item.get("id") or "") == str(target_id):
                    if item.get("webSocketDebuggerUrl"):
                        return item
                    raise RuntimeError(f"DevTools target has no WebSocket URL: {target_id}")
            raise RuntimeError(f"No DevTools target matched id={target_id}")

        pages = [
            item for item in targets
            if item.get("webSocketDebuggerUrl") and str(item.get("type") or "").lower() == "page"
        ]
        needle = str(url_contains or "").strip().lower()
        if needle:
            pages = [
                item for item in pages
                if needle in str(item.get("url") or "").lower() or needle in str(item.get("title") or "").lower()
            ]
        pages = [item for item in pages if not str(item.get("url") or "").startswith("devtools://")] or pages
        pages.sort(key=self._cdp_target_score, reverse=True)
        if not pages:
            raise RuntimeError(
                f"No DevTools page targets were available on {self._cdp_base_url(port)}. "
                "Use open_debug_page first, or pass the correct port."
            )
        return pages[0]

    @staticmethod
    def _cdp_target_score(target: Dict[str, Any]) -> int:
        url = str(target.get("url") or "").strip().lower()
        title = str(target.get("title") or "").strip()
        score = 0
        if url.startswith(("http://", "https://")):
            score += 100
        elif url and url not in {"about:blank", "chrome://newtab/"}:
            score += 30
        if title:
            score += 10
        if str(target.get("type") or "").lower() == "page":
            score += 5
        if target.get("webSocketDebuggerUrl"):
            score += 5
        if url.startswith(("devtools://", "chrome-extension://")):
            score -= 100
        if url in {"about:blank", "chrome://newtab/"}:
            score -= 20
        return score

    @staticmethod
    def _safe_cdp_call(cdp: _CdpConnection, method: str, params: Optional[Dict[str, Any]] = None, *, timeout: float = 5.0) -> Dict[str, Any]:
        try:
            return cdp.call(method, params or {}, timeout=timeout)
        except Exception:
            return {}

    @staticmethod
    def _format_cdp_remote_object(remote: Dict[str, Any]) -> str:
        if not isinstance(remote, dict):
            return str(remote)
        if "unserializableValue" in remote:
            return str(remote.get("unserializableValue"))
        if "value" in remote:
            value = remote.get("value")
            if isinstance(value, (dict, list)):
                return json.dumps(value, ensure_ascii=False, indent=2)
            return str(value)
        if remote.get("description"):
            return str(remote.get("description"))
        if remote.get("type"):
            return str(remote.get("type"))
        return ""

    @staticmethod
    def _format_cdp_exception(details: Dict[str, Any]) -> str:
        exception = details.get("exception") if isinstance(details, dict) else None
        if isinstance(exception, dict):
            description = exception.get("description") or exception.get("value")
            if description:
                return str(description)
        text = details.get("text") if isinstance(details, dict) else ""
        line = details.get("lineNumber") if isinstance(details, dict) else None
        column = details.get("columnNumber") if isinstance(details, dict) else None
        suffix = f" at {line}:{column}" if line is not None and column is not None else ""
        return (str(text or "unknown exception") + suffix).strip()

    @classmethod
    def _render_cdp_console_events(cls, events: Sequence[Dict[str, Any]], *, max_events: int = 80) -> List[str]:
        lines: List[str] = []
        limit = max(1, int(max_events or 80))
        for event in events:
            method = str(event.get("method") or "")
            params = event.get("params") or {}
            if method == "Runtime.consoleAPICalled":
                level = str(params.get("type") or "console")
                args = [
                    cls._format_cdp_remote_object(arg)
                    for arg in (params.get("args") or [])
                    if isinstance(arg, dict)
                ]
                lines.append(f"- console.{level}: {' '.join(arg for arg in args if arg)}".rstrip())
            elif method == "Runtime.exceptionThrown":
                lines.append(f"- exception: {cls._format_cdp_exception(params.get('exceptionDetails') or {})}")
            elif method == "Log.entryAdded":
                entry = params.get("entry") or {}
                level = entry.get("level") or "log"
                text = entry.get("text") or entry.get("url") or ""
                source = entry.get("source") or "unknown"
                lines.append(f"- {source}.{level}: {text}")
            if len(lines) >= limit:
                lines.append(f"- [truncated at {limit} rendered console/log events]")
                break
        return lines

    @classmethod
    def _summarize_cdp_network_events(
        cls,
        events: Sequence[Dict[str, Any]],
        *,
        max_events: int = 120,
        include_request_body: bool = False,
        include_websockets: bool = False,
        filter_url: str = "",
        filter_method: str = "",
        filter_status: str = "",
    ) -> Dict[str, Any]:
        requests_by_id: Dict[str, Dict[str, Any]] = {}
        responses_by_id: Dict[str, Dict[str, Any]] = {}
        failures: List[Dict[str, Any]] = []
        websockets_by_id: Dict[str, Dict[str, Any]] = {}
        finished: set[str] = set()
        for event in events:
            method = str(event.get("method") or "")
            params = event.get("params") or {}
            request_id = str(params.get("requestId") or "")
            if method == "Network.requestWillBeSent":
                request = params.get("request") or {}
                item = {
                    "request_id": request_id,
                    "url": request.get("url") or "",
                    "method": request.get("method") or "GET",
                    "resource_type": params.get("type") or "",
                    "document_url": params.get("documentURL") or "",
                    "headers": request.get("headers") or {},
                }
                if include_request_body and request.get("postData") is not None:
                    item["post_data_preview"] = str(request.get("postData") or "")[:4000]
                requests_by_id[request_id] = item
            elif method == "Network.responseReceived":
                response = params.get("response") or {}
                request = requests_by_id.get(request_id) or {}
                responses_by_id[request_id] = {
                    "request_id": request_id,
                    "url": response.get("url") or request.get("url") or "",
                    "method": request.get("method") or "",
                    "status": int(response.get("status") or 0),
                    "status_text": response.get("statusText") or "",
                    "mime_type": response.get("mimeType") or "",
                    "resource_type": params.get("type") or request.get("resource_type") or "",
                    "headers": response.get("headers") or {},
                    "post_data_preview": request.get("post_data_preview") or "",
                }
            elif method == "Network.loadingFailed":
                request = requests_by_id.get(request_id) or {}
                failures.append(
                    {
                        "request_id": request_id,
                        "url": request.get("url") or "",
                        "method": request.get("method") or "",
                        "resource_type": request.get("resource_type") or params.get("type") or "",
                        "error_text": params.get("errorText") or "failed",
                    }
                )
            elif method == "Network.loadingFinished":
                finished.add(request_id)
            elif include_websockets and method == "Network.webSocketCreated":
                websockets_by_id[request_id] = {
                    "request_id": request_id,
                    "url": params.get("url") or "",
                    "frames": [],
                }
            elif include_websockets and method in {"Network.webSocketFrameSent", "Network.webSocketFrameReceived"}:
                frame = params.get("response") or {}
                item = websockets_by_id.setdefault(request_id, {"request_id": request_id, "url": "", "frames": []})
                item["frames"].append(
                    {
                        "direction": "sent" if method.endswith("Sent") else "received",
                        "opcode": frame.get("opcode"),
                        "mask": frame.get("mask"),
                        "payload_preview": str(frame.get("payloadData") or "")[:2000],
                    }
                )

        responses = list(responses_by_id.values())
        for item in responses:
            item["finished"] = item.get("request_id") in finished
        requests = list(requests_by_id.values())
        responses = cls._filter_network_items(responses, filter_url=filter_url, filter_method=filter_method, filter_status=filter_status)
        requests = cls._filter_network_items(requests, filter_url=filter_url, filter_method=filter_method, filter_status="")
        failures = cls._filter_network_items(failures, filter_url=filter_url, filter_method=filter_method, filter_status="")
        limit = max(1, int(max_events or 120))
        return {
            "request_count": len(requests_by_id),
            "response_count": len(responses_by_id),
            "failure_count": len(failures),
            "filtered_request_count": len(requests),
            "filtered_response_count": len(responses),
            "requests": requests[:limit],
            "responses": responses[:limit],
            "failures": failures[:limit],
            "websockets": list(websockets_by_id.values())[:limit],
            "events": list(events)[:limit],
            "filters": {"url": filter_url, "method": filter_method, "status": filter_status},
        }

    @classmethod
    def _filter_network_items(
        cls,
        items: Sequence[Dict[str, Any]],
        *,
        filter_url: str = "",
        filter_method: str = "",
        filter_status: str = "",
    ) -> List[Dict[str, Any]]:
        url_needle = str(filter_url or "").strip().lower()
        method_needle = str(filter_method or "").strip().upper()
        status_needle = str(filter_status or "").strip().lower()
        filtered: List[Dict[str, Any]] = []
        for item in items:
            if url_needle and url_needle not in str(item.get("url") or "").lower():
                continue
            if method_needle and method_needle != str(item.get("method") or "").upper():
                continue
            if status_needle and not cls._status_matches(item.get("status"), status_needle):
                continue
            filtered.append(dict(item))
        return filtered

    @staticmethod
    def _status_matches(status: Any, filter_status: str) -> bool:
        try:
            status_int = int(status)
        except Exception:
            return False
        text = str(filter_status or "").strip().lower()
        if re.fullmatch(r"[1-5]xx", text):
            return status_int // 100 == int(text[0])
        if re.fullmatch(r"\d{3}", text):
            return status_int == int(text)
        return False

    @classmethod
    def _attach_cdp_response_bodies(
        cls,
        cdp: _CdpConnection,
        responses: List[Dict[str, Any]],
        *,
        max_body_chars: int,
        timeout: float = 3.0,
    ) -> None:
        limit = max(1, int(max_body_chars or 2000))
        for item in responses[:20]:
            request_id = str(item.get("request_id") or "")
            if not request_id:
                continue
            try:
                result = cdp.call("Network.getResponseBody", {"requestId": request_id}, timeout=timeout)
                body = str(result.get("body") or "")
                if result.get("base64Encoded"):
                    try:
                        body = base64.b64decode(body).decode("utf-8", errors="replace")
                    except Exception:
                        body = "[base64 response body omitted]"
                item["body_preview"] = body[:limit]
                item["body_truncated"] = len(body) > limit
            except Exception as exc:
                item["body_error"] = str(exc)

    @staticmethod
    def _render_cdp_network_summary(summary: Dict[str, Any], *, target: Dict[str, Any]) -> str:
        lines = [
            f"DevTools network events for {target.get('title') or '(untitled)'}",
            f"URL: {target.get('url') or '(empty)'}",
            (
                "Counts: "
                f"requests={summary.get('request_count', 0)}, "
                f"responses={summary.get('response_count', 0)}, "
                f"failures={summary.get('failure_count', 0)}"
            ),
        ]
        responses = list(summary.get("responses") or [])
        if responses:
            lines.append("\nResponses:")
            for item in responses[:60]:
                method = item.get("method") or ""
                status = item.get("status") or 0
                resource_type = item.get("resource_type") or ""
                mime_type = item.get("mime_type") or ""
                lines.append(f"- {status} {method} {item.get('url') or ''} [{resource_type} {mime_type}]".strip())
                if item.get("post_data_preview"):
                    lines.append("  Request Body Preview:\n" + str(item.get("post_data_preview")))
                if item.get("body_preview"):
                    lines.append("  Body Preview:\n" + str(item.get("body_preview")))
                elif item.get("body_error"):
                    lines.append(f"  Body unavailable: {item.get('body_error')}")
        failures = list(summary.get("failures") or [])
        if failures:
            lines.append("\nFailures:")
            for item in failures[:40]:
                lines.append(f"- {item.get('method') or ''} {item.get('url') or ''}: {item.get('error_text') or 'failed'}")
        websockets = list(summary.get("websockets") or [])
        if websockets:
            lines.append("\nWebSockets:")
            for item in websockets[:20]:
                lines.append(f"- {item.get('url') or '(unknown websocket)'} frames={len(item.get('frames') or [])}")
                for frame in (item.get("frames") or [])[:6]:
                    lines.append(f"  {frame.get('direction')}: {frame.get('payload_preview')}")
        if summary.get("har_path"):
            lines.append(f"\nSaved HAR JSON: {summary.get('har_path')}")
        return "\n".join(lines).strip()

    @staticmethod
    def _build_simple_har(summary: Dict[str, Any]) -> Dict[str, Any]:
        entries = []
        requests_by_id = {item.get("request_id"): item for item in (summary.get("requests") or [])}
        for response in summary.get("responses") or []:
            request = requests_by_id.get(response.get("request_id")) or {}
            entries.append(
                {
                    "request": {
                        "method": response.get("method") or request.get("method") or "",
                        "url": response.get("url") or request.get("url") or "",
                        "headers": request.get("headers") or {},
                        "postData": request.get("post_data_preview") or "",
                    },
                    "response": {
                        "status": response.get("status") or 0,
                        "statusText": response.get("status_text") or "",
                        "headers": response.get("headers") or {},
                        "mimeType": response.get("mime_type") or "",
                        "bodyPreview": response.get("body_preview") or "",
                    },
                    "resourceType": response.get("resource_type") or "",
                }
            )
        return {"log": {"version": "1.2", "creator": {"name": "Reverie Browser Controler"}, "entries": entries}}

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
        if explicit:
            resolved = explicit.resolve()
            if resolved.exists() and resolved.is_file() and self._is_safe_embedded_runtime_path(resolved):
                return resolved
            return None

        copied = self._ensure_bundled_browser_runtime()
        if copied:
            return copied

        for candidate in self._embedded_chromium_candidates(self.runtime_dir):
            if candidate.exists() and candidate.is_file():
                return candidate.resolve()
        return None

    def _embedded_browser_missing_message(self) -> str:
        return (
            "Embedded Chromium runtime was not found. Browser Controler no longer uses real Edge/Chrome profiles. "
            f"Expected runtime under {self.runtime_dir}. For development, install it with "
            f"`$env:PLAYWRIGHT_BROWSERS_PATH='{self.runtime_dir / 'ms-playwright'}'; python -m playwright install chromium --no-shell`. "
            "The Windows exe build bundles this runtime into reverie_resources/browser and copies it into .reverie/browser/runtime on first use."
        )

    def _ensure_bundled_browser_runtime(self) -> Optional[Path]:
        existing = next((path for path in self._embedded_chromium_candidates(self.runtime_dir) if path.exists() and path.is_file()), None)
        source = self._bundled_browser_resource_dir()
        archive = self._bundled_browser_resource_archive()
        if not source and not archive:
            return existing.resolve() if existing else None
        bundled = next((path for path in self._embedded_chromium_candidates(source) if path.exists() and path.is_file()), None) if source else None
        bundled_revision = self._embedded_chromium_revision(bundled) if bundled else self._bundled_browser_archive_revision(archive)
        if existing and (
            bundled_revision < 0
            or self._embedded_chromium_revision(existing) >= bundled_revision
        ):
            return existing.resolve()
        target = self.runtime_dir / "ms-playwright"
        try:
            if source:
                shutil.copytree(source, target, dirs_exist_ok=True)
            elif archive:
                runtime_root = self.runtime_dir.resolve()
                with zipfile.ZipFile(archive) as packed:
                    for member in packed.infolist():
                        destination = (runtime_root / member.filename).resolve()
                        if not destination.is_relative_to(runtime_root):
                            raise ValueError(f"Unsafe browser archive member: {member.filename}")
                    packed.extractall(runtime_root)
        except Exception:
            return existing.resolve() if existing else None
        existing = next((path for path in self._embedded_chromium_candidates(self.runtime_dir) if path.exists() and path.is_file()), None)
        return existing.resolve() if existing else None

    def _bundled_browser_resource_dir(self) -> Optional[Path]:
        candidates: List[Path] = []
        mei = Path(str(getattr(sys, "_MEIPASS", "") or ""))
        if mei:
            candidates.append(mei / "reverie_resources" / "browser" / "ms-playwright")
        candidates.append(self.app_root / "reverie_resources" / "browser" / "ms-playwright")
        candidates.append(Path(__file__).resolve().parents[2] / "reverie_resources" / "browser" / "ms-playwright")
        for candidate in candidates:
            if candidate.exists() and candidate.is_dir():
                return candidate.resolve()
        return None

    def _bundled_browser_resource_archive(self) -> Optional[Path]:
        candidates: List[Path] = []
        mei = Path(str(getattr(sys, "_MEIPASS", "") or ""))
        if mei:
            candidates.append(mei / "reverie_resources" / "browser.zip")
        candidates.append(self.app_root / "reverie_resources" / "browser.zip")
        candidates.append(Path(__file__).resolve().parents[2] / "reverie_resources" / "browser.zip")
        for candidate in candidates:
            if candidate.exists() and candidate.is_file():
                return candidate.resolve()
        return None

    @staticmethod
    def _bundled_browser_archive_revision(archive: Optional[Path]) -> int:
        if not archive:
            return -1
        try:
            with zipfile.ZipFile(archive) as packed:
                revisions = [
                    int(match.group(1))
                    for name in packed.namelist()
                    if (match := re.search(r"(?:^|/)chromium-(\d+)(?:/|$)", name, flags=re.IGNORECASE))
                ]
            return max(revisions, default=-1)
        except Exception:
            return -1

    def _embedded_chromium_candidates(self, root: Path) -> List[Path]:
        patterns = [
            "ms-playwright/chromium-*/chrome-win/chrome.exe",
            "ms-playwright/chromium-*/chrome-win64/chrome.exe",
            "ms-playwright/chromium-*/chrome-linux/chrome",
            "ms-playwright/chromium-*/chrome-linux64/chrome",
            "ms-playwright/chromium-*/chrome-mac*/Chromium.app/Contents/MacOS/Chromium",
            "ms-playwright/chromium-*/chrome-mac*/Google Chrome for Testing.app/Contents/MacOS/Google Chrome for Testing",
            "chromium-*/chrome-win/chrome.exe",
            "chromium-*/chrome-win64/chrome.exe",
            "chromium-*/chrome-linux/chrome",
            "chromium-*/chrome-linux64/chrome",
            "chromium-*/chrome-mac*/Chromium.app/Contents/MacOS/Chromium",
            "chromium-*/chrome-mac*/Google Chrome for Testing.app/Contents/MacOS/Google Chrome for Testing",
            "chrome-win/chrome.exe",
            "chrome-win64/chrome.exe",
            "chrome-linux/chrome",
            "chrome-linux64/chrome",
        ]
        candidates: List[Path] = []
        for pattern in patterns:
            candidates.extend(root.glob(pattern))
        return sorted(
            set(candidates),
            key=lambda path: (self._embedded_chromium_revision(path), str(path).lower()),
            reverse=True,
        )

    @staticmethod
    def _embedded_chromium_revision(path: Path) -> int:
        match = re.search(r"(?:^|[\\/])chromium-(\d+)(?:[\\/]|$)", str(path), flags=re.IGNORECASE)
        return int(match.group(1)) if match else -1

    def _is_safe_embedded_runtime_path(self, path: Path) -> bool:
        try:
            path.resolve().relative_to(self.runtime_dir.resolve())
            return True
        except Exception:
            return False

    @staticmethod
    def _browser_window_flags(executable: Path, *, private: bool, new_window: bool, minimized: bool = False) -> List[str]:
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
        if minimized and "firefox" not in name:
            flags.append("--start-minimized")
        return flags

    def _load_browser_sessions(self) -> Dict[str, Any]:
        try:
            if not self.sessions_path.exists():
                return {}
            data = json.loads(self.sessions_path.read_text(encoding="utf-8"))
            return data if isinstance(data, dict) else {}
        except Exception:
            return {}

    def _resolve_cdp_port(self, *, session_id: str = "", port: Any = None) -> int:
        if port not in (None, ""):
            return self._normalize_cdp_port(port)
        selected_id = str(session_id or "").strip()
        if not selected_id:
            return DEFAULT_CDP_PORT
        session = self._load_browser_sessions().get(selected_id)
        if not isinstance(session, dict):
            raise ValueError(f"Browser Controler session not found: {selected_id}")
        selected_port = session.get("port")
        if selected_port in (None, "", 0):
            raise ValueError(f"Browser Controler session has no CDP port: {selected_id}")
        return self._normalize_cdp_port(selected_port)

    def _save_browser_sessions(self, sessions: Dict[str, Any]) -> None:
        self.sessions_path.parent.mkdir(parents=True, exist_ok=True)
        self.sessions_path.write_text(json.dumps(sessions, ensure_ascii=False, indent=2), encoding="utf-8")

    def _record_browser_session(
        self,
        *,
        session_id: str,
        port: int,
        url: str,
        profile: str,
        profile_dir: Path,
        browser: str,
        process_id: int,
        background: bool,
        minimized: bool,
        profile_backup: Optional[Dict[str, Any]] = None,
    ) -> str:
        safe_id = re.sub(r"[^A-Za-z0-9._-]+", "-", str(session_id or "").strip()).strip("-._")
        if not safe_id:
            safe_id = f"debug-port-{int(port)}"
        sessions = self._load_browser_sessions()
        sessions[safe_id] = {
            "session_id": safe_id,
            "port": int(port),
            "url": str(url or "about:blank"),
            "profile": self._normalize_profile_name(profile),
            "profile_dir": str(profile_dir),
            "browser": str(browser or ""),
            "process_id": int(process_id or 0),
            "created_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "background": bool(background),
            "minimized": bool(minimized),
            "profile_backup": profile_backup or {},
        }
        self._save_browser_sessions(sessions)
        return safe_id

    @staticmethod
    def _free_tcp_port() -> int:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            sock.bind((CDP_HOST, 0))
            return int(sock.getsockname()[1])

    @staticmethod
    def _tcp_port_open(port: int) -> bool:
        try:
            with socket.create_connection((CDP_HOST, BrowserControlerTool._normalize_cdp_port(port)), timeout=0.25):
                return True
        except OSError:
            return False

    def _is_authorized_cdp_port(self, port: int) -> bool:
        selected_port = self._normalize_cdp_port(port)
        sessions = self._load_browser_sessions()
        for session in sessions.values():
            try:
                if int(session.get("port") or 0) != selected_port:
                    continue
                if self._is_safe_browser_session_record(session) and self._validate_embedded_browser_session_process(session).get("valid"):
                    return True
            except Exception:
                continue
        return False

    def _is_safe_browser_session_record(self, session: Dict[str, Any]) -> bool:
        try:
            profile_dir = Path(str(session.get("profile_dir") or "")).resolve()
            browser_path = Path(str(session.get("browser") or "")).resolve()
            return self._is_safe_debug_profile_path(profile_dir) and self._is_safe_embedded_runtime_path(browser_path)
        except Exception:
            return False

    def _normalize_profile_browser(self, browser: str) -> str:
        key = str(browser or "chromium").strip().lower()
        if key in {"", "default", "system", "msedge", "edge", "chrome", "google", "brave", "brave-browser"}:
            return "chromium"
        return key

    def _browser_key_for_executable(self, browser: str, executable: Path) -> str:
        name = executable.name.lower()
        if self._is_safe_embedded_runtime_path(executable):
            return "chromium"
        return self._normalize_profile_browser(browser)

    def _profile_name_from_kwargs(self, kwargs: Dict[str, Any], *, default: str = "default") -> str:
        raw = str(kwargs.get("profile") or kwargs.get("user_data_dir") or default or "default").strip()
        return self._normalize_profile_name(raw)

    @staticmethod
    def _normalize_profile_name(profile: str) -> str:
        value = str(profile or "default").strip()
        if not value:
            value = "default"
        if Path(value).is_absolute():
            raise ValueError("Browser profile must be a relative .reverie/browser profile name, not an absolute path.")
        safe = re.sub(r"[^A-Za-z0-9._-]+", "-", value.strip().strip("/\\")).strip("-._")
        if not safe or safe in {".", ".."}:
            safe = "default"
        return safe

    def _embedded_browser_profile_dir(self, profile: str) -> Path:
        return self.debug_profiles_dir / self._normalize_profile_name(profile)

    def _prepare_embedded_profile(self, profile: str, profile_dir: Path) -> Path:
        profile_name = self._normalize_profile_name(profile)
        resolved_profile = profile_dir.resolve()
        if not self._is_safe_debug_profile_path(resolved_profile):
            raise ValueError("Embedded browser profile must stay under .reverie/browser/profiles.")
        download_dir = (self.downloads_dir / profile_name).resolve()
        try:
            download_dir.relative_to(self.downloads_dir.resolve())
        except ValueError as exc:
            raise ValueError("Embedded browser downloads must stay under .reverie/browser/downloads.") from exc
        download_dir.mkdir(parents=True, exist_ok=True)
        preferences_path = resolved_profile / "Default" / "Preferences"
        preferences: Dict[str, Any] = {}
        if preferences_path.exists():
            loaded = json.loads(preferences_path.read_text(encoding="utf-8"))
            if not isinstance(loaded, dict):
                raise ValueError(f"Embedded browser Preferences is not a JSON object: {preferences_path}")
            preferences = loaded
        preferences_path.parent.mkdir(parents=True, exist_ok=True)
        download_preferences = preferences.setdefault("download", {})
        if not isinstance(download_preferences, dict):
            download_preferences = {}
            preferences["download"] = download_preferences
        download_preferences.update(
            {
                "default_directory": str(download_dir),
                "directory_upgrade": True,
                "prompt_for_download": False,
            }
        )
        savefile_preferences = preferences.setdefault("savefile", {})
        if not isinstance(savefile_preferences, dict):
            savefile_preferences = {}
            preferences["savefile"] = savefile_preferences
        savefile_preferences["default_directory"] = str(download_dir)
        preferences_path.write_text(json.dumps(preferences, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
        return download_dir

    def _ensure_profile_backup(self, profile: str) -> Dict[str, Any]:
        profile_name = self._normalize_profile_name(profile)
        source = self._embedded_browser_profile_dir(profile_name)
        if not source.exists():
            return {"success": True, "backup_id": "", "backup_dir": "", "status": "not-needed", "partial": False, "reused": False}
        latest = self._latest_profile_backup(profile_name)
        if latest:
            return {
                "success": True,
                "backup_id": latest.get("backup_id"),
                "backup_dir": latest.get("backup_dir"),
                "status": latest.get("status"),
                "partial": str(latest.get("status") or "") != "success",
                "reused": True,
            }
        result = self._browser_profile_backup(profile=profile_name, include_cache=True)
        if not result.success:
            return {"success": False, "error": result.error or result.output}
        return {
            "success": True,
            "backup_id": result.data.get("backup_id"),
            "backup_dir": result.data.get("backup_dir"),
            "status": result.data.get("status"),
            "partial": str(result.data.get("status") or "") != "success",
            "reused": False,
        }

    def _latest_profile_backup(self, browser: str) -> Optional[Dict[str, Any]]:
        backups = self._profile_backup_records(browser)
        return backups[0] if backups else None

    def _profile_backup_records(self, browser: str) -> List[Dict[str, Any]]:
        profile_name = self._normalize_profile_name(browser)
        root = self.profile_backups_dir / profile_name
        if not root.exists():
            return []
        records: List[Dict[str, Any]] = []
        for manifest_path in root.glob("*/browser-profile-backup.json"):
            try:
                record = json.loads(manifest_path.read_text(encoding="utf-8"))
                record.setdefault("backup_id", manifest_path.parent.name)
                record.setdefault("backup_dir", str(manifest_path.parent))
                records.append(record)
            except Exception:
                continue
        records.sort(key=lambda item: str(item.get("created_at") or item.get("backup_id") or ""), reverse=True)
        return records

    def _profile_import_records(self, profile: str) -> List[Dict[str, Any]]:
        profile_name = self._normalize_profile_name(profile)
        root = self.imports_dir / profile_name
        if not root.exists():
            return []
        records: List[Dict[str, Any]] = []
        for manifest_path in root.glob("*/browser-profile-import.json"):
            try:
                record = json.loads(manifest_path.read_text(encoding="utf-8"))
                record.setdefault("import_id", manifest_path.parent.name)
                record.setdefault("import_dir", str(manifest_path.parent))
                records.append(record)
            except Exception:
                continue
        records.sort(key=lambda item: str(item.get("created_at") or item.get("import_id") or ""), reverse=True)
        return records

    def _latest_storage_state_path(self, profile: str) -> Path:
        return self.imports_dir / self._normalize_profile_name(profile) / "latest-storage-state.json"

    def _load_import_storage_state(self, path: Path, *, import_format: str = "auto") -> Dict[str, Any]:
        fmt = str(import_format or "auto").strip().lower()
        text = path.read_text(encoding="utf-8", errors="replace")
        if fmt in {"auto", "json", "storage_state", "storage-state"}:
            try:
                data = json.loads(text)
                if isinstance(data, dict):
                    return self._normalize_storage_state(data)
                if isinstance(data, list):
                    return self._normalize_storage_state({"cookies": data, "origins": []})
            except Exception:
                if fmt not in {"auto"}:
                    raise
        if fmt in {"auto", "netscape", "cookies.txt", "cookie"}:
            return {"cookies": self._parse_netscape_cookies(text), "origins": []}
        raise ValueError(f"Unsupported import_format: {import_format}")

    def _normalize_storage_state(self, data: Dict[str, Any]) -> Dict[str, Any]:
        cookies = []
        for item in data.get("cookies") or []:
            if not isinstance(item, dict):
                continue
            cookie = {
                "name": str(item.get("name") or ""),
                "value": str(item.get("value") or ""),
                "domain": str(item.get("domain") or ""),
                "path": str(item.get("path") or "/") or "/",
                "expires": float(item.get("expires", -1) if item.get("expires") is not None else -1),
                "httpOnly": bool(item.get("httpOnly", item.get("httponly", False))),
                "secure": bool(item.get("secure", False)),
                "sameSite": str(item.get("sameSite") or item.get("samesite") or "Lax").capitalize(),
            }
            if cookie["sameSite"] not in {"Strict", "Lax", "None"}:
                cookie["sameSite"] = "Lax"
            if cookie["name"] and cookie["domain"]:
                cookies.append(cookie)
        origins = []
        for origin in data.get("origins") or []:
            if not isinstance(origin, dict):
                continue
            origin_url = str(origin.get("origin") or "").strip()
            local_storage = [
                {"name": str(entry.get("name") or ""), "value": str(entry.get("value") or "")}
                for entry in (origin.get("localStorage") or [])
                if isinstance(entry, dict) and str(entry.get("name") or "")
            ]
            if origin_url and local_storage:
                origins.append({"origin": origin_url, "localStorage": local_storage})
        return {"cookies": cookies, "origins": origins}

    def _parse_netscape_cookies(self, text: str) -> List[Dict[str, Any]]:
        cookies: List[Dict[str, Any]] = []
        for raw_line in str(text or "").splitlines():
            line = raw_line.strip()
            if not line or line.startswith("#"):
                continue
            parts = line.split("\t")
            if len(parts) < 7:
                continue
            domain, _include_subdomains, path, secure, expires, name, value = parts[:7]
            try:
                expires_value = float(expires)
            except Exception:
                expires_value = -1
            cookies.append(
                {
                    "name": name,
                    "value": value,
                    "domain": domain,
                    "path": path or "/",
                    "expires": expires_value,
                    "httpOnly": False,
                    "secure": str(secure).upper() == "TRUE",
                    "sameSite": "Lax",
                }
            )
        return cookies

    def _apply_profile_imports(self, *, port: int, profile: str, timeout: float = 5.0) -> str:
        state_path = self._latest_storage_state_path(profile)
        if not state_path.exists():
            return ""
        try:
            storage_state = self._normalize_storage_state(json.loads(state_path.read_text(encoding="utf-8")))
            cookies = list(storage_state.get("cookies") or [])
            origins = list(storage_state.get("origins") or [])
            target = self._cdp_select_target(port, timeout=timeout)
            with _CdpConnection(str(target["webSocketDebuggerUrl"]), timeout=timeout) as cdp:
                self._safe_cdp_call(cdp, "Network.enable", timeout=timeout)
                if cookies:
                    cdp.call("Network.setCookies", {"cookies": cookies}, timeout=timeout)
                for origin in origins[:20]:
                    origin_url = str(origin.get("origin") or "")
                    if not origin_url.startswith(("http://", "https://")):
                        continue
                    cdp.call("Page.navigate", {"url": origin_url}, timeout=timeout)
                    time.sleep(0.2)
                    assignments = ""
                    for entry in origin.get("localStorage") or []:
                        assignments += f"localStorage.setItem({json.dumps(entry.get('name') or '')}, {json.dumps(entry.get('value') or '')});"
                    if assignments:
                        cdp.call("Runtime.evaluate", {"expression": assignments, "awaitPromise": True}, timeout=timeout)
            return f"Applied imported storage state: cookies={len(cookies)}, origins={len(origins)}."
        except Exception as exc:
            return f"Imported storage state is present but could not be applied yet: {exc}"

    def _ensure_page_navigation(self, *, port: int, url: str, timeout: float = 5.0) -> str:
        target_url = str(url or "about:blank").strip() or "about:blank"
        if target_url == "about:blank":
            return ""
        try:
            target = self._cdp_select_target(port, timeout=timeout)
            with _CdpConnection(str(target["webSocketDebuggerUrl"]), timeout=timeout) as cdp:
                self._safe_cdp_call(cdp, "Page.enable", timeout=timeout)
                cdp.call("Page.navigate", {"url": target_url}, timeout=timeout)
                deadline = time.time() + max(1.0, min(float(timeout or 5.0), 10.0))
                ready_state = ""
                current_url = ""
                while time.time() < deadline:
                    result = cdp.call(
                        "Runtime.evaluate",
                        {
                            "expression": "({url:location.href, ready:document.readyState})",
                            "awaitPromise": True,
                            "returnByValue": True,
                        },
                        timeout=min(timeout, 3.0),
                    )
                    value = (result.get("result") or {}).get("value") or {}
                    current_url = str(value.get("url") or "")
                    ready_state = str(value.get("ready") or "")
                    if current_url and current_url != "about:blank" and ready_state in {"interactive", "complete"}:
                        break
                    time.sleep(0.2)
            return f"Confirmed embedded browser navigation: {current_url or target_url} ({ready_state or 'loading'})."
        except Exception as exc:
            return f"Embedded browser started, but navigation confirmation was partial: {exc}"

    def _read_storage_state_from_cdp(self, port: int, *, timeout: float = 5.0) -> Dict[str, Any]:
        target = self._cdp_select_target(port, timeout=timeout)
        with _CdpConnection(str(target["webSocketDebuggerUrl"]), timeout=timeout) as cdp:
            self._safe_cdp_call(cdp, "Network.enable", timeout=timeout)
            cookies_result = cdp.call("Network.getAllCookies", {}, timeout=timeout)
            local_result = cdp.call(
                "Runtime.evaluate",
                {
                    "expression": "(() => Object.keys(localStorage).map(name => ({name, value: localStorage.getItem(name) || ''})))()",
                    "awaitPromise": True,
                    "returnByValue": True,
                },
                timeout=timeout,
            )
        origin = ""
        target_url = str(target.get("url") or "")
        if target_url.startswith(("http://", "https://")):
            parsed = urlparse(target_url)
            origin = f"{parsed.scheme}://{parsed.netloc}"
        local_storage = ((local_result.get("result") or {}).get("value") or []) if isinstance(local_result, dict) else []
        origins = [{"origin": origin, "localStorage": local_storage}] if origin and local_storage else []
        return self._normalize_storage_state({"cookies": cookies_result.get("cookies") or [], "origins": origins})

    def _copy_browser_profile(self, source: Path, target: Path, *, include_cache: bool = True) -> Dict[str, Any]:
        if IS_WINDOWS:
            args = [
                "robocopy",
                str(source),
                str(target),
                "/E",
                "/COPY:DAT",
                "/DCOPY:DAT",
                "/XJ",
                "/R:1",
                "/W:1",
                "/NP",
            ]
            if not include_cache:
                args.extend(["/XD", "Cache", "Code Cache", "GPUCache", "ShaderCache", "GrShaderCache", "DawnCache"])
            completed = subprocess.run(args, capture_output=True, text=True, encoding="utf-8", errors="replace")
            success = int(completed.returncode) <= 7
            return {
                "success": success,
                "method": "robocopy",
                "exit_code": int(completed.returncode),
                "warning": "" if success else (completed.stderr or completed.stdout)[-1000:],
            }
        shutil.copytree(source, target, dirs_exist_ok=True)
        return {"success": True, "method": "copytree", "exit_code": 0}

    def _mirror_browser_profile(self, source: Path, target: Path) -> Dict[str, Any]:
        target.mkdir(parents=True, exist_ok=True)
        if IS_WINDOWS:
            completed = subprocess.run(
                ["robocopy", str(source), str(target), "/MIR", "/COPY:DAT", "/DCOPY:DAT", "/XJ", "/R:1", "/W:1", "/NP"],
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
            )
            success = int(completed.returncode) <= 7
            return {
                "success": success,
                "method": "robocopy",
                "exit_code": int(completed.returncode),
                "warning": "" if success else (completed.stderr or completed.stdout)[-1000:],
            }
        shutil.copytree(source, target, dirs_exist_ok=True)
        return {"success": True, "method": "copytree", "exit_code": 0}

    def _directory_stats(self, path: Optional[Path]) -> Dict[str, int]:
        files = 0
        total = 0
        if not path or not path.exists():
            return {"files": 0, "bytes": 0}
        for item in path.rglob("*"):
            try:
                if item.is_file():
                    files += 1
                    total += int(item.stat().st_size)
            except Exception:
                continue
        return {"files": files, "bytes": total}

    @staticmethod
    def _format_size(size: Any) -> str:
        try:
            value = float(size or 0)
        except (TypeError, ValueError):
            return str(size)
        for unit in ("B", "KB", "MB", "GB", "TB"):
            if value < 1024 or unit == "TB":
                return f"{value:.1f} {unit}" if unit != "B" else f"{int(value)} B"
            value /= 1024

    def _profile_processes_running(self, profile_dir: Path) -> bool:
        if not IS_WINDOWS:
            return False
        target = str(profile_dir.resolve()).lower()
        try:
            completed = subprocess.run(
                [
                    "powershell",
                    "-NoProfile",
                    "-NonInteractive",
                    "-Command",
                    "Get-CimInstance Win32_Process | "
                    "Where-Object { $_.CommandLine -match '--user-data-dir=' } | "
                    "ForEach-Object { $_.CommandLine }",
                ],
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=5,
            )
            return target in str(completed.stdout or "").lower()
        except Exception:
            return False

    def _resolve_debug_profile_dir(self, user_data_dir: str, *, browser: str, port: int) -> Path:
        root = self.debug_profiles_dir.resolve()
        if user_data_dir:
            profile_name = self._normalize_profile_name(user_data_dir)
            candidate = root / profile_name
        else:
            safe_browser = re.sub(r"[^A-Za-z0-9._-]+", "-", str(browser or "chromium").lower()).strip("-._") or "chromium"
            candidate = root / safe_browser / f"port-{int(port)}"
        resolved = candidate.resolve()
        try:
            resolved.relative_to(root)
        except ValueError as exc:
            raise ValueError(
                "Refusing to use a browser profile outside .reverie/browser/profiles. "
                f"Requested user_data_dir={resolved}. Use a relative embedded profile name instead."
            ) from exc
        if resolved == root:
            raise ValueError("Refusing to use the .reverie/browser/profiles root directly.")
        return resolved

    def _is_safe_debug_profile_path(self, path: Path) -> bool:
        try:
            resolved = path.resolve()
            root = self.debug_profiles_dir.resolve()
            resolved.relative_to(root)
            return resolved != root
        except Exception:
            return False

    def _is_disposable_debug_profile_path(self, path: Path) -> bool:
        if not self._is_safe_debug_profile_path(path):
            return False
        resolved = path.resolve()
        relative = resolved.relative_to(self.debug_profiles_dir.resolve())
        profile_name = relative.parts[0] if relative.parts else ""
        temporary = (
            profile_name.startswith(("session-", "debug-port-", "temp-"))
            or (
                len(relative.parts) == 2
                and relative.parts[0] == "chromium"
                and relative.parts[1].startswith("port-")
            )
        )
        if not temporary:
            return False
        if (self.imports_dir / profile_name).exists():
            return False
        if (self.profile_backups_dir / profile_name).exists():
            return False
        return True

    def _persist_text(self, stem: str, text: str) -> Path:
        safe_stem = re.sub(r"[^A-Za-z0-9._-]+", "-", str(stem or "page").strip()).strip("-._") or "page"
        path = self.pages_dir / f"{safe_stem}-{int(time.time() * 1000)}.txt"
        path.write_text(str(text or ""), encoding="utf-8")
        return path

    def _persist_json(self, stem: str, data: Any) -> Path:
        safe_stem = re.sub(r"[^A-Za-z0-9._-]+", "-", str(stem or "data").strip()).strip("-._") or "data"
        path = self.pages_dir / f"{safe_stem}-{int(time.time() * 1000)}.json"
        path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
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

    @classmethod
    def _render_ax_nodes(cls, nodes: Sequence[Dict[str, Any]], *, max_events: int = 120) -> List[str]:
        lines: List[str] = []
        limit = max(1, int(max_events or 120))
        for node in nodes:
            role = cls._ax_value(node.get("role"))
            name = cls._ax_value(node.get("name"))
            value = cls._ax_value(node.get("value"))
            if not role and not name and not value:
                continue
            label = name or value or "(unnamed)"
            lines.append(f"- role={role or '-'} name={str(label)[:240]}")
            if len(lines) >= limit:
                lines.append(f"- [truncated at {limit} accessibility nodes]")
                break
        return lines

    @staticmethod
    def _ax_value(value: Any) -> str:
        if isinstance(value, dict):
            return str(value.get("value") or "").strip()
        return str(value or "").strip()

    @staticmethod
    def _render_dom_outline(outline: Dict[str, Any], *, max_events: int = 120) -> List[str]:
        lines = [
            f"DOM outline for {outline.get('title') or '(untitled)'}",
            f"URL: {outline.get('url') or '(empty)'}",
        ]
        remaining = max(1, int(max_events or 120))
        for section in ("headings", "controls", "links", "forms", "images"):
            items = list(outline.get(section) or [])
            if not items:
                continue
            lines.append(f"\n{section.title()} ({len(items)}):")
            for item in items[:remaining]:
                label = item.get("text") or item.get("aria") or item.get("name") or item.get("id") or item.get("href") or "(no label)"
                detail = item.get("selector") or item.get("tag") or ""
                extra = item.get("href") or item.get("type") or item.get("role") or ""
                lines.append(f"- {detail} {extra}: {label}".strip())
                remaining -= 1
                if remaining <= 0:
                    lines.append("- [DOM outline truncated]")
                    return lines
        return lines
